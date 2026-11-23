from openai import AsyncOpenAI
from typing import Dict, Any, List, Optional
import logging
import time
# Tenacity : Exponential Backoff with built in Jitter 
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception,
    before_log,
    after_log
)
from neo.core.settings import settings
from neo.tools.registry import tool_schema as tools
from neo.core.cost_metrics import record_cost_metric, record_model_attempt, categorize_error
from neo.core.guardrails import EnvGuardrail
import re
logger = logging.getLogger(__name__)

# Initialize the shared AsyncOpenAI client
client = AsyncOpenAI(
    api_key=settings.GEMINI_API_KEY,
    base_url=settings.GEMINI_BASE_URL,
)

_ALLOWED_MESSAGE_KEYS = frozenset({"role", "content", "name", "tool_call_id", "tool_calls"})


def to_llm_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sanitize messages for the LLM API by stripping internal metadata
    and scrubbing any secrets, credentials, or .env values with EnvGuardrail.

    Args:
        messages (List[Dict[str, Any]]): Raw session messages.

    Returns:
        List[Dict[str, Any]]: Messages containing only keys accepted by OpenAI chat APIs with masked secrets.
    """
    clean_messages = [
        {k: v for k, v in message.items() if k in _ALLOWED_MESSAGE_KEYS}
        for message in messages
    ]
    return EnvGuardrail.sanitize_messages(clean_messages)


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


def _is_rate_limit_or_resource_exhausted(exception: Exception) -> bool:
    """
    Custom retry predicate for tenacity.
    Returns True if the exception indicates rate limiting (429), resource exhaustion, or quota issues.
    Explicitly ignores 401 (Unauthorized), 404 (Not Found),..etc.
    """
    error_str = str(exception).lower()
    
    # Do not retry on 401 or 404 errors
    if "401" in error_str or "unauthorized" in error_str or "404" in error_str or "not found" in error_str:
        return False
        
    # Retry on 429, resource exhaustion, or quota errors
    if "429" in error_str or "exhausted" in error_str or "quota" in error_str:
        return True
        
    return False


def _on_retry_attempt(retry_state):
    """Callback fired right before retry sleep to log and record the retry attempt."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    model_name = settings.MODEL
    if retry_state.args and isinstance(retry_state.args[0], dict):
        model_name = retry_state.args[0].get("model", model_name)
    category = categorize_error(exc)
    record_model_attempt(
        model_name=model_name,
        outcome="failed",
        error_category=category,
        error_message=str(exc),
        is_retry=True,
    )


@retry(
    stop=stop_after_attempt(5), # Stop retrying after 5 failed attempts
    # Exponential backoff with random jitter to prevent sync spikes / thundering herd
    wait=wait_random_exponential(multiplier=1, max=16),
    retry=retry_if_exception(_is_rate_limit_or_resource_exhausted),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARNING),
    before_sleep=_on_retry_attempt,
    reraise=True # reraise=True ensures that if all attempts fail, the final exception is raised to the caller
)
async def _create_chat_completion_with_retry(kwargs: Dict[str, Any]):
    """
    Helper wrapper around client.chat.completions.create protected by tenacity 
    jittered exponential backoff for 429 / resource exhausted / quota errors.
    """
    model_name = kwargs.get("model", settings.MODEL)
    try:
        response = await client.chat.completions.create(**kwargs)
        record_model_attempt(model_name=model_name, outcome="success")
        return response
    except Exception as exc:
        category = categorize_error(exc)
        record_model_attempt(
            model_name=model_name,
            outcome="failed",
            error_category=category,
            error_message=str(exc),
            is_retry=False,
        )
        raise


async def create_chat_stream(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    with_tools: bool = True,
):
    """
    Initiate an async streaming chat completion via the OpenAI client with exponential backoff and jitter.

    Args:
        messages (List[Dict[str, Any]]): Conversation history messages.
        model (Optional[str]): Model name or override identifier. Defaults to None.
        with_tools (bool): Whether to provide registered tool schemas. Defaults to True.

    Returns:
        AsyncStream: Asynchronous iterator of chat completion chunks.
    """
    model_name = settings.MODEL
    kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": to_llm_messages(messages),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if with_tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return await _create_chat_completion_with_retry(kwargs)


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
        start_time = time.perf_counter()
        first_token_time = None
        stream = await create_chat_stream(messages=messages, model=model, with_tools=with_tools)
        full_content = ""
        requested_tool_calls = []
        usage_info = {
            "query_tokens": 0,
            "completion_tokens": 0,
            "session_tokens": 0,
            "ttft": 0.0,
            "total_latency": 0.0,
        }

        async for chunk in stream:
            if first_token_time is None:
                first_token_time = time.perf_counter()

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

        end_time = time.perf_counter()
        ttft_val = (first_token_time - start_time) if first_token_time else (end_time - start_time)
        usage_info["ttft"] = round(ttft_val, 3)
        usage_info["total_latency"] = round(end_time - start_time, 3)

        return AssistantMessage(full_content, requested_tool_calls), usage_info

    except Exception as e:
        # Capture the exact underlying exception message (e.g. 429 Rate Limit, Quota Exceeded, etc.)
        # and return it as the assistant message so it renders directly in the UI.
        category = categorize_error(e)
        model_name = model or settings.MODEL
        record_model_attempt(
            model_name=model_name,
            outcome="failed",
            error_category=category,
            error_message=str(e),
            is_retry=False,
        )
        error_msg = f"Error communicating with AI service: {str(e)}"
        raise Exception(error_msg)
        # return AssistantMessage(error_msg, []), {"query_tokens": 0, "completion_tokens": 0, "session_tokens": 0}


async def generate_commit_message(diff: str, model: Optional[str] = None) -> str:
    """
    Generate a conventional Git commit message from a git diff.
    Protected by tenacity exponential backoff with jitter for 429 / resource exhaustion.

    Args:
        diff (str): The staged changes diff text.
        model (Optional[str]): Model name identifier. Defaults to None.

    Returns:
        str: Concise Conventional Commit message string.
    """
    try:
        model_name = settings.MODEL
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
        # Use our retry-wrapped helper to protect against rate limits and resource exhaustion
        t_start = time.perf_counter()
        response = await _create_chat_completion_with_retry({
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate a concise Git commit messages with the Conventional Commits format. Return only the commit message text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        })
        t_latency = round(time.perf_counter() - t_start, 3)

        if getattr(response, "usage", None):
            try:
                record_cost_metric(
                    model_name=model_name,
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    call_type="commit_generation",
                    ttft=t_latency,
                    total_latency=t_latency,
                )
            except Exception:
                pass
        return (response.choices[0].message.content or "").strip().strip('"').strip("'")
    except Exception as e:
        return f"Error generating commit message: {str(e)}"


async def generate_session_title(user_prompt: str, model: Optional[str] = None) -> str:
    """
    Generate a concise 2-5 word title for a chat session based on the first user query.
    Protected by tenacity exponential backoff with jitter for 429 / resource exhaustion.

    Args:
        user_prompt (str): The initial prompt submitted by the user.
        model (Optional[str]): AI model identifier to use. Defaults to selected model.

    Returns:
        str: Concise title string without quotes or punctuation.
    """
    try:
        model_name = settings.SMALL_MODEL
        cleaned_prompt = user_prompt.strip()[:300]
        
        # Use our retry-wrapped helper to protect against rate limits and resource exhaustion
        t_start = time.perf_counter()
        response = await _create_chat_completion_with_retry({
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Generate a concise 2 to 5 word title summarizing the user's intent or topic. "
                        "Return ONLY the plain title text in title case. Do not wrap in quotes or add markdown or trailing punctuation."
                        "NOTE: ensure never provide spacing between the words(Filename must don't have speacing instead you can replace them using '_' or '-')"
                    ),
                },
                {"role": "user", "content": cleaned_prompt},
            ],
        })
        t_latency = round(time.perf_counter() - t_start, 3)

        if getattr(response, "usage", None):
            try:
                record_cost_metric(
                    model_name=model_name,
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    call_type="title_generation",
                    ttft=t_latency,
                    total_latency=t_latency,
                )
            except Exception:
                pass
        title = (response.choices[0].message.content or "").strip().strip('"').strip("'").strip("`")
        # Sanitize for safe, space-free filenames
        sanitized = re.sub(r"[^\w\-]+", "_", title.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return sanitized or "New_Session"
    except Exception:
        # Fallback to truncated first words if AI call fails
        words = user_prompt.strip().split()
        fallback = "_".join(words[:4]).title()
        fallback = re.sub(r"[^\w\-]+", "_", fallback).strip("_")
        return fallback or "New_Session"
