"""Anthropic Claude provider implementation using the official anthropic SDK."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional
import json

from ..models import ChatMessage, Role, ToolCall, TokenUsage
from .base import BaseLLMProvider, StreamChunk
from .pricing import calculate_cost, estimate_tokens


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider supporting streaming and tool calling."""

    def __init__(self, api_key: str, model: str = "claude-3-7-sonnet-latest", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._client = None
        if self.api_key:
            self._init_client()

    def _init_client(self):
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self.api_key)
        except Exception:
            self._client = None

    @staticmethod
    def _to_anthropic_messages(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue

            if msg.role == Role.USER:
                formatted.append({"role": "user", "content": msg.content or ""})
                continue

            if msg.role == Role.ASSISTANT:
                blocks: List[Dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.args,
                        }
                    )
                formatted.append({"role": "assistant", "content": blocks or ""})
                continue

            if msg.role == Role.TOOL:
                tool_result_blocks: List[Dict[str, Any]] = []
                for tc in msg.tool_calls:
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": tc.result or tc.error or "",
                        }
                    )
                if tool_result_blocks:
                    formatted.append({"role": "user", "content": tool_result_blocks})

        return formatted

    @staticmethod
    def _to_anthropic_tools(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if not tools:
            return []

        transformed: List[Dict[str, Any]] = []
        for tool in tools:
            fn = tool.get("function", {})
            transformed.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        return transformed

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[StreamChunk, None]:
        if not self.api_key:
            yield StreamChunk(
                text_delta=(
                    "⚠️ **No Anthropic API Key configured**\n\n"
                    "Please set your key in Settings (`Ctrl+S`) or via `ANTHROPIC_API_KEY`."
                )
            )
            return

        if self._client is None:
            self._init_client()
            if self._client is None:
                yield StreamChunk(text_delta="Error: Could not initialize Anthropic client. Ensure `anthropic` is installed.")
                return

        formatted_messages = self._to_anthropic_messages(messages)
        anthropic_tools = self._to_anthropic_tools(tools)

        req_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": True,
        }
        if system_prompt:
            req_kwargs["system"] = system_prompt
        if anthropic_tools:
            req_kwargs["tools"] = anthropic_tools

        try:
            stream = await self._client.messages.create(**req_kwargs)
        except Exception as e:
            yield StreamChunk(text_delta=f"❌ **Anthropic API Error ({self.model}):** {str(e)}")
            return

        partial_tool_calls: Dict[str, Dict[str, Any]] = {}
        prompt_tokens = estimate_tokens("".join(m.content for m in messages))
        completion_text = ""
        final_usage: Optional[TokenUsage] = None

        try:
            async for event in stream:
                event_type = getattr(event, "type", "")

                if event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    block = getattr(event, "content_block", None)
                    if delta and getattr(delta, "type", "") == "text_delta":
                        text_delta = getattr(delta, "text", "")
                        completion_text += text_delta
                        completion_tokens = estimate_tokens(completion_text)
                        usage = TokenUsage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens,
                            estimated_cost=calculate_cost(self.model, prompt_tokens, completion_tokens),
                        )
                        final_usage = usage
                        if text_delta:
                            yield StreamChunk(text_delta=text_delta, token_usage=usage)
                    elif delta and getattr(delta, "type", "") == "input_json_delta":
                        idx = str(getattr(event, "index", "0"))
                        if idx not in partial_tool_calls:
                            partial_tool_calls[idx] = {
                                "id": getattr(block, "id", f"call_{idx}"),
                                "name": getattr(block, "name", ""),
                                "json": "",
                            }
                        partial_tool_calls[idx]["json"] += getattr(delta, "partial_json", "")

                elif event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", "") == "tool_use":
                        idx = str(getattr(event, "index", "0"))
                        partial_tool_calls[idx] = {
                            "id": getattr(block, "id", f"call_{idx}"),
                            "name": getattr(block, "name", ""),
                            "json": "",
                        }

                elif event_type == "message_delta":
                    usage_obj = getattr(event, "usage", None)
                    if usage_obj:
                        prompt = int(getattr(usage_obj, "input_tokens", prompt_tokens) or prompt_tokens)
                        completion = int(getattr(usage_obj, "output_tokens", estimate_tokens(completion_text)) or 0)
                        final_usage = TokenUsage(
                            prompt_tokens=prompt,
                            completion_tokens=completion,
                            total_tokens=prompt + completion,
                            estimated_cost=calculate_cost(self.model, prompt, completion),
                        )

            finalized_tools: List[ToolCall] = []
            for item in partial_tool_calls.values():
                args = {}
                raw_json = item["json"].strip()
                if raw_json:
                    try:
                        args = json.loads(raw_json)
                    except Exception:
                        args = {"raw": raw_json}

                finalized_tools.append(
                    ToolCall(
                        id=item["id"],
                        name=item["name"],
                        args=args,
                    )
                )

            if finalized_tools:
                yield StreamChunk(tool_calls=finalized_tools, token_usage=final_usage)

        except Exception as e:
            yield StreamChunk(text_delta=f"\n\n❌ **Stream Error:** {str(e)}")
