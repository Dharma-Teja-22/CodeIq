"""OpenAI-compatible LLM provider for OpenAI, Groq, Ollama, and OpenRouter."""

from __future__ import annotations
import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

from ..models import ChatMessage, Role, ToolCall, TokenUsage
from .base import BaseLLMProvider, StreamChunk
from .pricing import calculate_cost, estimate_tokens


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for OpenAI, Groq, Ollama, and other OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.base_url = base_url or kwargs.get("base_url") or "https://api.openai.com/v1"
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key or "sk-dummy-key-for-local",
                base_url=self.base_url if self.base_url else None,
            )
        except Exception:
            self._client = None

    def _convert_messages(self, messages: List[ChatMessage], system_prompt: Optional[str]) -> List[Dict[str, Any]]:
        formatted = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue

            entry: Dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content or "",
            }

            if msg.role == Role.ASSISTANT and msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.args),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.role == Role.TOOL:
                for tc in msg.tool_calls:
                    formatted.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": tc.result or tc.error or "",
                    })
                continue

            formatted.append(entry)

        return formatted

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[StreamChunk, None]:
        if not self.api_key and "localhost" not in (self.base_url or "") and "127.0.0.1" not in (self.base_url or ""):
            yield StreamChunk(
                text_delta=(
                    f"⚠️ **No API Key configured for {self.model}**\n\n"
                    f"Please set your API key in CodeIq settings (`Ctrl+S`) or via `OPENAI_API_KEY`."
                )
            )
            return

        if self._client is None:
            self._init_client()
            if self._client is None:
                yield StreamChunk(text_delta="Error: Could not initialize OpenAI client. Ensure `openai` package is installed.")
                return

        formatted_messages = self._convert_messages(messages, system_prompt)

        req_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }

        if tools:
            req_kwargs["tools"] = tools
            req_kwargs["tool_choice"] = "auto"

        try:
            stream = await self._client.chat.completions.create(**req_kwargs)
        except Exception as e:
            yield StreamChunk(text_delta=f"❌ **API Error ({self.model}):** {str(e)}")
            return

        accumulated_tools: Dict[int, Dict[str, Any]] = {}
        total_text = ""

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                text_delta = delta.content or ""
                total_text += text_delta

                # Handle tool call streaming chunks
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in accumulated_tools:
                            accumulated_tools[idx] = {
                                "id": tc_delta.id or f"call_{uuid.uuid4().hex[:8]}",
                                "name": tc_delta.function.name or "" if tc_delta.function else "",
                                "arguments": tc_delta.function.arguments or "" if tc_delta.function else "",
                            }
                        else:
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    accumulated_tools[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    accumulated_tools[idx]["arguments"] += tc_delta.function.arguments

                prompt_tokens = estimate_tokens("".join(m.content for m in messages))
                completion_tokens = estimate_tokens(total_text)
                cost = calculate_cost(self.model, prompt_tokens, completion_tokens)
                usage = TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    estimated_cost=cost,
                )

                if text_delta:
                    yield StreamChunk(text_delta=text_delta, token_usage=usage)

            # Finalize accumulated tool calls if any
            final_tool_calls = []
            for item in accumulated_tools.values():
                args_dict = {}
                try:
                    args_dict = json.loads(item["arguments"]) if item["arguments"] else {}
                except Exception:
                    args_dict = {"raw": item["arguments"]}

                final_tool_calls.append(
                    ToolCall(
                        id=item["id"],
                        name=item["name"],
                        args=args_dict,
                    )
                )

            if final_tool_calls:
                yield StreamChunk(tool_calls=final_tool_calls)

        except Exception as e:
            yield StreamChunk(text_delta=f"\n\n❌ **Stream Error:** {str(e)}")
