import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from codeiq_dev.core.llm import _create_chat_completion_with_retry
from codeiq_dev.core.settings import settings
from codeiq_dev.core.session import save_session
from codeiq_dev.tools.registry import tool_schema
from codeiq_dev.core.cost_metrics import record_cost_metric

logger = logging.getLogger(__name__)

TOKEN_THRESHOLD = int(os.getenv("CODEIQ_TOKEN_THRESHOLD", "100000"))
SUMMARY_MAX_TOKENS = int(os.getenv("CODEIQ_SUMMARY_MAX_TOKENS", "6000"))
SAFETY_MARGIN = int(os.getenv("CODEIQ_SAFETY_MARGIN", "5000"))
SUMMARY_FLAG = "is_compaction_summary"


def count_text_tokens(text: str) -> int:
    """
    Count tokens in a plain text string using character/word heuristic approximation.
    Does not use tiktoken.
    Standard approximation: ~4 characters per token for English text/code.

    Args:
        text (str): Text to measure.

    Returns:
        int: Estimated number of tokens in the text.
    """
    if not text:
        return 0
    # Standard LLM token estimation heuristic: max of char-length // 4 or word count
    # For mixed prose and code, len(text) / 4 is the widely accepted standard
    char_estimate = (len(text) + 3) // 4
    word_estimate = len(text.split())
    return max(char_estimate, word_estimate)


def count_system_prompt_tokens(system_prompt: Optional[str]) -> int:
    """Count tokens for the system prompt including role overhead."""
    if not system_prompt:
        return 0
    return 4 + count_text_tokens(system_prompt)


def count_tool_schemas_tokens(schemas: Optional[List[Dict[str, Any]]] = None) -> int:
    """Count tokens for tool definitions and function calling schemas."""
    target_schemas = schemas if schemas is not None else tool_schema
    if not target_schemas:
        return 0
    try:
        return count_text_tokens(json.dumps(target_schemas, ensure_ascii=False))
    except Exception:
        return 0


def count_repo_url_tokens(file_repo_url: Optional[str]) -> int:
    """Count tokens for the file repository URL context."""
    if not file_repo_url:
        return 0
    return count_text_tokens(str(file_repo_url))


def calculate_static_overhead(
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    file_repo_url: Optional[str] = None,
) -> int:
    """Calculate combined static overhead: system prompt + tool schemas + file repo URL."""
    return (
        count_system_prompt_tokens(system_prompt)
        + count_tool_schemas_tokens(tools)
        + count_repo_url_tokens(file_repo_url)
    )


def _message_payload(message: Dict[str, Any]) -> str:
    """
    Build the full text payload of a message for token accounting.
    Accounts for user/system/assistant content, tool calls, tool responses,
    names, and arguments across input, output, and tool executions.

    Args:
        message (Dict[str, Any]): A conversation message.

    Returns:
        str: Concatenated content, tool calls, and tool identifiers.
    """
    parts = []
    content = message.get("content")
    if content:
        parts.append(str(content))
    tool_calls = message.get("tool_calls")
    if tool_calls:
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function") or {}
                    parts.append(f"{tc.get('id', '')} {fn.get('name', '')} {fn.get('arguments', '')}")
                else:
                    fn = getattr(tc, "function", None)
                    fn_name = getattr(fn, "name", "") if fn else ""
                    fn_args = getattr(fn, "arguments", "") if fn else ""
                    tc_id = getattr(tc, "id", "")
                    parts.append(f"{tc_id} {fn_name} {fn_args}")
        parts.append(json.dumps(tool_calls, default=str, ensure_ascii=False))
    if message.get("tool_call_id"):
        parts.append(str(message["tool_call_id"]))
    if message.get("name"):
        parts.append(str(message["name"]))
    return "\n".join(parts)


def count_message_tokens(message: Dict[str, Any]) -> int:
    """
    Count tokens for one conversation message including role overhead.

    Args:
        message (Dict[str, Any]): A conversation message.

    Returns:
        int: Estimated token count for the message.
    """
    return 4 + count_text_tokens(_message_payload(message))


def count_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    Count tokens for a list of conversation messages.

    Args:
        messages (List[Dict[str, Any]]): Conversation messages.

    Returns:
        int: Total token count for all messages.
    """
    return sum(count_message_tokens(message) for message in messages)


def is_summary_message(message: Dict[str, Any]) -> bool:
    """
    Check whether a message is a compaction summary.

    Args:
        message (Dict[str, Any]): A conversation message.

    Returns:
        bool: True if the message is a compaction summary.
    """
    return bool((message.get("metadata") or {}).get(SUMMARY_FLAG))


def render_for_summary(messages: List[Dict[str, Any]], max_chars_per_message: int = 6000) -> str:
    """
    Render messages as a compact transcript for summarization.

    Args:
        messages (List[Dict[str, Any]]): Messages to summarize.
        max_chars_per_message (int): Maximum characters retained per message.

    Returns:
        str: Rendered transcript.
    """
    blocks = []
    for message in messages:
        role = message.get("role", "unknown")
        content = str(message.get("content") or "")
        if len(content) > max_chars_per_message:
            content = content[:max_chars_per_message] + "\n...[truncated]..."
        if message.get("tool_calls"):
            content += "\nTool calls: " + json.dumps(message["tool_calls"], ensure_ascii=False)
        if message.get("tool_call_id"):
            content += f"\nTool call id: {message['tool_call_id']}"
        blocks.append(f"[{role}]\n{content}")
    return "\n\n".join(blocks)


async def generate_context_summary(
    existing_summary: str,
    messages_to_summarize: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> str:
    """
    Generate a concise summary of conversation turns using LLM.

    Args:
        existing_summary (str): Prior compaction summary to carry forward.
        messages_to_summarize (List[Dict[str, Any]]): Messages to fold into the summary.
        model (Optional[str]): Model override for summarization.

    Returns:
        str: Compacted conversation summary.
    """
    transcript = render_for_summary(messages_to_summarize)
    system_prompt = (
        "You compress conversation history for a coding assistant. "
        "Produce a dense, factual summary that preserves continuity. "
        "You must preserve: user requests and inputs (user intent, instructions, goals, constraints); "
        "assistant responses and outputs (explanations, proposed solutions, code, decisions, and rationale); "
        "tool calls (tool names, functions, arguments, files/paths accessed or modified, git operations, shell commands executed); "
        "tool execution outputs (command results, file contents/diffs, error messages, fixes, web search findings); "
        "open tasks, unresolved bugs, and next steps; "
        "exact identifiers, names, versions, and values. "
        "Do not invent facts. Do not include secrets or .env contents. "
        "Use short markdown bullets."
    )
    user_prompt = (
        f"Existing summary to carry forward and merge:\n"
        f"{existing_summary or '(none)'}\n\n"
        f"Conversation history to fold into the summary:\n"
        f"{transcript}\n\n"
        f"Return only the updated summary, no preamble, maximum "
        f"{SUMMARY_MAX_TOKENS} tokens.\n"
    )

    model_to_use = model or settings.SMALL_MODEL or settings.MODEL
    t_start = time.perf_counter()
    response = await _create_chat_completion_with_retry(
        {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": SUMMARY_MAX_TOKENS,
        }
    )
    t_latency = round(time.perf_counter() - t_start, 3)

    if getattr(response, "usage", None):
        try:
            record_cost_metric(
                model_name=model_to_use,
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                call_type="compaction_summary",
                ttft=t_latency,
                total_latency=t_latency,
            )
        except Exception:
            pass
    return (response.choices[0].message.content or "").strip()


async def maybe_compact_session(
    session: Dict[str, Any],
    current_context_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    file_repo_url: Optional[str] = None,
) -> bool:
    """
    Compact a session when its total context/tokens reaches the token threshold.

    When triggered:
    1. Generates an LLM summary of the entire conversation history up to that point.
    2. Replaces the existing conversation context in systemPromptTokens with the newly
       generated compacted summary, while retaining toolSchema and fileRepoUrl:
       systemPromptTokens = newCompactedSummaryTokens + toolSchemaTokens + fileRepoUrlTokens
    3. Replaces previous messages with the compacted summary message.
    4. Automatically recalculates and updates all dependent token counts, including total_tokens.
    5. Strips out the 'compaction' key from the session dict.

    Args:
        session (Dict[str, Any]): Session data to inspect and compact.
        current_context_tokens (Optional[int]): Current context tokens if known.
        system_prompt (Optional[str]): System prompt content.
        tools (Optional[List[Dict[str, Any]]]): Tool definitions.
        file_repo_url (Optional[str]): Git/File repository URL.

    Returns:
        bool: True if compaction occurred, False otherwise.
    """
    # Remove compact/compaction key from session if present
    if "compaction" in session:
        session.pop("compaction", None)

    # Compute static component token counts
    tool_schema_tokens = count_tool_schemas_tokens(tools)
    file_repo_tokens = count_repo_url_tokens(file_repo_url)

    messages: List[Dict[str, Any]] = session.get("messages", [])
    message_tokens = count_messages_tokens(messages)

    # If systemPromptTokens is not already initialized, initialize it with
    # systemPrompt + toolSchema + fileRepoUrl
    base_sys_prompt_tokens = count_system_prompt_tokens(system_prompt)
    if not session.get("systemPromptTokens"):
        session["systemPromptTokens"] = base_sys_prompt_tokens + tool_schema_tokens + file_repo_tokens

    session["toolSchemaTokens"] = tool_schema_tokens
    session["fileRepoUrlTokens"] = file_repo_tokens

    # Current measured total tokens across context: systemPromptTokens + message tokens
    # Or session's recorded total_tokens
    session_total = session.get("total_tokens", 0)
    current_total = max(session_total, session["systemPromptTokens"] + message_tokens)
    if current_context_tokens is not None:
        current_total = max(current_total, current_context_tokens)

    # Check whether token threshold has been reached
    if current_total < TOKEN_THRESHOLD:
        return False

    # Extract any existing summary and normal conversation messages
    summary_messages = [m for m in messages if is_summary_message(m)]
    normal_messages = [m for m in messages if not is_summary_message(m)]

    if not normal_messages and not summary_messages:
        return False

    existing_summary = ""
    if summary_messages:
        existing_summary = "\n\n".join(
            str(m.get("content") or "") for m in summary_messages
        )

    try:
        summary_text = await generate_context_summary(
            existing_summary,
            normal_messages if normal_messages else summary_messages,
        )
    except Exception as exc:
        logger.warning("Compaction failed; history unchanged: %s", exc)
        return False

    if not summary_text:
        return False

    # Create new compacted summary message
    summary_message = {
        "role": "system",
        "content": f"Conversation summary so far:\n{summary_text}",
        "metadata": {
            SUMMARY_FLAG: True,
            "created_at": datetime.now().isoformat(),
        },
    }

    # Replace previous conversation history with the compacted summary
    session["messages"] = [summary_message]

    # Calculate tokens for the newly generated compacted summary
    new_compacted_summary_tokens = count_message_tokens(summary_message)

    # Update systemPromptTokens:
    # systemPromptTokens = newCompactedSummaryTokens + toolSchemaTokens + fileRepoUrlTokens
    session["systemPromptTokens"] = new_compacted_summary_tokens + tool_schema_tokens + file_repo_tokens

    # Dependent token count recalculation:
    # Recalculate prompt tokens and total_tokens based on updated compacted context
    recalculated_prompt_tokens = session["systemPromptTokens"]
    completion_tokens = session.get("session_completion_tokens", 0)
    recalculated_total_tokens = recalculated_prompt_tokens + completion_tokens

    session["session_prompt_tokens"] = recalculated_prompt_tokens
    session["total_tokens"] = recalculated_total_tokens

    # Explicitly ensure compaction key is removed
    session.pop("compaction", None)

    session["updated_at"] = datetime.now().isoformat()
    save_session(session)
    return True
