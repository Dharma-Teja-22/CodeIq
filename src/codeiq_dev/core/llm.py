from openai import AsyncOpenAI
from typing import Dict, Any, List, Optional
from codeiq_dev.core.settings import *
from codeiq_dev.core.config import get_selected_model
from codeiq_dev.tools.registry import tool_schema as tools

# Initialize the shared AsyncOpenAI client
client = AsyncOpenAI(
    api_key=GEMINI_API_KEY,
    base_url=GEMINI_BASE_URL,
)

async def close_client() -> None:
    """
    Close the AsyncOpenAI client session gracefully.

    Args:
        None

    Returns:
        None
    """
    try:
        await client.close()
    except Exception as e:
        pass


class AssistantMessage:
    """Helper representing an assistant turn output."""
    def __init__(self, content: str, tool_calls: list):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> Dict[str, Any]:
        """
        Serialize the message into OpenAI-compatible role dictionary.

        Args:
            exclude_none (bool): Whether to omit None values. Defaults to False.

        Returns:
            Dict[str, Any]: Formatted role dictionary.
        """
        d: Dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in self.tool_calls
            ]
        return d


async def create_chat_stream(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    with_tools: bool = True,
):
    """
    Initiate an async streaming chat completion via the OpenAI client.

    Args:
        messages (List[Dict[str, Any]]): Conversation history messages.
        model (Optional[str]): Model name or override identifier. Defaults to None.
        with_tools (bool): Whether to provide registered tool schemas. Defaults to True.

    Returns:
        AsyncStream: Asynchronous iterator of chat completion chunks.
    """
    model_name = model or get_selected_model()
    kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if with_tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return await client.chat.completions.create(**kwargs)


async def stream_chat_turn(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    with_tools: bool = True,
    on_token = None,
    on_tool_call = None,
) -> tuple[AssistantMessage, dict]:
    """
    Handles streaming a single chat completion turn and accumulates usage metrics.

    Args:
        messages (List[Dict[str, Any]]): Message history passed to the LLM.
        model (Optional[str]): The model identifier to use. Defaults to configured model.
        with_tools (bool): Flag indicating if tool calling is enabled. Defaults to True.
        on_token (Optional[Callable]): Callback invoked on receipt of each text chunk. Defaults to None.
        on_tool_call (Optional[Callable]): Callback invoked when tool calls arrive. Defaults to None.

    Returns:
        tuple[AssistantMessage, dict]: Assistant message instance and token usage summary dictionary.
    """
    try:
        stream = await create_chat_stream(messages=messages, model=model, with_tools=with_tools)
        full_content = ""
        requested_tool_calls = []
        usage_info = {"query_tokens": 0, "completion_tokens": 0, "session_tokens": 0}

        async for chunk in stream:
            if getattr(chunk, "usage", None) and chunk.usage:
                q = chunk.usage.prompt_tokens or usage_info["query_tokens"]
                c = chunk.usage.completion_tokens or usage_info["completion_tokens"]
                usage_info["query_tokens"] = q
                usage_info["completion_tokens"] = c
                usage_info["session_tokens"] = q + c

            if getattr(chunk, "choices", None):
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            content_chunk = delta.content
                            if on_token:
                                on_token(content_chunk)
                            full_content += content_chunk
                        if getattr(delta, "tool_calls", None):
                            requested_tool_calls.extend(delta.tool_calls)
                            if on_tool_call:
                                for tc in delta.tool_calls:
                                    on_tool_call(tc)

        return AssistantMessage(full_content, requested_tool_calls), usage_info
    except Exception as e:
        return AssistantMessage(f"Error communicating with AI service: {str(e)}", []), {"query_tokens": 0, "completion_tokens": 0, "session_tokens": 0}


async def generate_commit_message(diff: str, model: Optional[str] = None) -> str:
    """
    Generate a conventional Git commit message from a git diff.

    Args:
        diff (str): The staged changes diff text.
        model (Optional[str]): Model name identifier. Defaults to None.

    Returns:
        str: Concise Conventional Commit message string.
    """
    try:
        model_name = model or get_selected_model()
        diff_lines = diff.splitlines()
        limited_diff = "\n".join(diff_lines[:200])
        prompt = f'''Generate a short, descriptive Git commit message based on the staged changes. Follow Conventional Commits format.
                     Use one of these prefixes:
                        - feat: for new functionality
                        - fix: for bug fixes
                        - refactor: for code restructuring
                        - docs: for documentation changes
                        - test: for test changes
                        - perf: for performance improvements
                        - chore: for maintenance tasks
                        - style: for formatting changes

                    Rules:
                    - Use simple, clear English.
                    - Start with the appropriate prefix.
                    - Use lowercase after the prefix.
                    - Keep the message under 72 characters.
                    - Describe the actual change, not the implementation process.
                    - Return only the commit message, without quotes or Markdown.
                    - Do not invent changes that are not evident from the diff.

                    Staged changes:
                    {limited_diff}
                '''
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip().strip('"').strip("'")
    except Exception as e:
        return f"Error generating commit message: {str(e)}"
