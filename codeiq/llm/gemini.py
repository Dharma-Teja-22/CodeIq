"""Google Gemini provider implementation using the official google-genai SDK."""

from __future__ import annotations
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

from ..models import ChatMessage, Role, ToolCall, TokenUsage
from .base import BaseLLMProvider, StreamChunk
from .pricing import calculate_cost, estimate_tokens


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider supporting streaming and function calling."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._client = None
        if self.api_key:
            self._init_client()

    def _init_client(self):
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            self._client = None

    def _convert_messages(self, messages: List[ChatMessage]) -> List[Any]:
        """Converts CodeIq ChatMessage history into Gemini content format."""
        from google.genai import types

        contents = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue

            role_str = "user" if msg.role == Role.USER else "model"
            parts = []

            if msg.content:
                parts.append(types.Part.from_text(text=msg.content))

            # Add tool calls if this is an assistant message with function calls
            if msg.role == Role.ASSISTANT and msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append(
                        types.Part.from_function_call(
                            name=tc.name,
                            args=tc.args,
                        )
                    )

            # Add tool responses if this is a tool message
            if msg.role == Role.TOOL:
                role_str = "user"
                for tc in msg.tool_calls:
                    resp_dict = {"output": tc.result or tc.error or ""}
                    parts.append(
                        types.Part.from_function_response(
                            name=tc.name,
                            response=resp_dict,
                        )
                    )

            if parts:
                contents.append(types.Content(role=role_str, parts=parts))

        return contents

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
                    "⚠️ **No Gemini API Key Detected**\n\n"
                    "Please configure your Gemini API Key using one of the following methods:\n"
                    "1. Press **`Ctrl+S`** inside CodeIq to open the Settings modal.\n"
                    "2. Set the environment variable: `export GEMINI_API_KEY='your-key'`\n"
                    "3. Add `GEMINI_API_KEY=your-key` into your `.env` file.\n\n"
                    "You can get a free Gemini API key at: [Google AI Studio](https://aistudio.google.com/)"
                )
            )
            return

        if self._client is None:
            self._init_client()
            if self._client is None:
                yield StreamChunk(text_delta="Error: Could not initialize Gemini client. Check that `google-genai` is installed.")
                return

        from google.genai import types

        # Build tools config
        genai_tools = []
        if tools:
            for t_group in tools:
                if "function_declarations" in t_group:
                    funcs = []
                    for f in t_group["function_declarations"]:
                        funcs.append(
                            types.FunctionDeclaration(
                                name=f["name"],
                                description=f.get("description", ""),
                                parameters=f.get("parameters"),
                            )
                        )
                    genai_tools.append(types.Tool(function_declarations=funcs))

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt if system_prompt else None,
            tools=genai_tools if genai_tools else None,
        )

        contents = self._convert_messages(messages)
        if not contents:
            return

        loop = asyncio.get_running_loop()

        def _call_stream():
            return self._client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )

        try:
            stream = await loop.run_in_executor(None, _call_stream)
        except Exception as e:
            yield StreamChunk(text_delta=f"❌ **Gemini API Error:** {str(e)}")
            return

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_text = ""

        # Stream iterations in executor thread to prevent blocking Textual async loop
        def _get_next_chunk(iterator):
            try:
                return next(iterator)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, _get_next_chunk, stream)
            if chunk is None:
                break

            text_delta = ""
            thought_delta = ""
            tool_calls = []

            # Check usage metadata
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                um = chunk.usage_metadata
                total_prompt_tokens = getattr(um, "prompt_token_count", total_prompt_tokens) or total_prompt_tokens
                total_completion_tokens = getattr(um, "candidates_token_count", total_completion_tokens) or total_completion_tokens

            # Extract content parts
            if hasattr(chunk, "candidates") and chunk.candidates:
                candidate = chunk.candidates[0]
                if hasattr(candidate, "content") and candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        # Text part
                        if hasattr(part, "text") and part.text:
                            text_delta += part.text
                            total_text += part.text

                        # Thought / reasoning part
                        if hasattr(part, "thought") and part.thought:
                            thought_delta += str(part.thought)

                        # Function call part
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            call_name = getattr(fc, "name", "")
                            call_args = getattr(fc, "args", {})
                            if isinstance(call_args, types.Struct):
                                call_args = dict(call_args)
                            elif hasattr(call_args, "items"):
                                call_args = dict(call_args)

                            tool_calls.append(
                                ToolCall(
                                    name=call_name,
                                    args=dict(call_args),
                                    id=f"call_{uuid.uuid4().hex[:8]}",
                                )
                            )

            # If token stats were not provided, estimate them
            if total_prompt_tokens == 0:
                prompt_text = "".join(m.content for m in messages)
                total_prompt_tokens = estimate_tokens(prompt_text)
            if total_completion_tokens == 0:
                total_completion_tokens = estimate_tokens(total_text)

            cost = calculate_cost(self.model, total_prompt_tokens, total_completion_tokens)
            usage = TokenUsage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                total_tokens=total_prompt_tokens + total_completion_tokens,
                estimated_cost=cost,
            )

            if text_delta or thought_delta or tool_calls:
                yield StreamChunk(
                    text_delta=text_delta,
                    thought_delta=thought_delta,
                    tool_calls=tool_calls,
                    token_usage=usage,
                )
