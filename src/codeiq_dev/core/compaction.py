import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import tiktoken

from codeiq_dev.core.llm import _create_chat_completion_with_retry
from codeiq_dev.core.settings import settings
from codeiq_dev.core.session import save_session
from codeiq_dev.tools.registry import tool_schema

logger = logging.getLogger(__name__)

TOKEN_THRESHOLD = int(os.getenv("CODEIQ_TOKEN_THRESHOLD", "100000"))
SUMMARY_MAX_TOKENS = int(os.getenv("CODEIQ_SUMMARY_MAX_TOKENS", "6000"))
MIN_RECENT_MESSAGES = 6
MIN_OLDER_MESSAGES = 2
SAFETY_MARGIN = int(os.getenv("CODEIQ_SAFETY_MARGIN", "5000"))
SUMMARY_FLAG = "is_compaction_summary"

_ENC = tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str) -> int:
    """
    Count tokens in a plain text string using tiktoken.

    Args:
        text (str): Text to measure.

    Returns:
        int: Number of tokens in the text.
    """
    if not text:
        return 0
    return len(_ENC.encode(text, disallowed_special=()))


def count_system_prompt_tokens(system_prompt: Optional[str]) -> int:
    """Count tokens for the system prompt including overhead."""
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


def calculate_static_overhead(
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Calculate combined static overhead for system prompt and tool schemas."""
    return count_system_prompt_tokens(system_prompt) + count_tool_schemas_tokens(tools)


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


def find_split_index(messages: List[Dict[str, Any]], keep_recent_tokens: int) -> int:
    """
    Find a safe boundary that keeps the newest messages within a token budget.

    The boundary never leaves an orphan tool result without its assistant
    tool-call message.

    Args:
        messages (List[Dict[str, Any]]): Non-summary conversation messages.
        keep_recent_tokens (int): Token budget for the recent messages.

    Returns:
        int: Index of the first recent message.
    """
    total = 0
    idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        message_tokens = count_message_tokens(messages[i])
        kept = len(messages) - i
        if total + message_tokens > keep_recent_tokens and kept >= MIN_RECENT_MESSAGES:
            break
        total += message_tokens
        idx = i

    while idx > 0 and messages[idx].get("role") == "tool":
        idx -= 1

    return idx


def render_for_summary(messages: List[Dict[str, Any]], max_chars_per_message: int = 6000) -> str:
    """
    Render messages as a compact transcript for summarization.

    Args:
        messages (List[Dict[str, Any]]): Older messages to summarize.
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
    older_messages: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> str:
    """
    Generate a concise summary of older conversation turns.

    Args:
        existing_summary (str): Prior compaction summary to carry forward.
        older_messages (List[Dict[str, Any]]): Older turns to fold into the summary.
        model (Optional[str]): Model override for summarization.

    Returns:
        str: Updated conversation summary.
    """
    transcript = render_for_summary(older_messages)
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
        f"Older conversation turns to fold into the summary:\n"
        f"{transcript}\n\n"
        f"Return only the updated summary, no preamble, maximum "
        f"{SUMMARY_MAX_TOKENS} tokens.\n"
    )

    response = await _create_chat_completion_with_retry(
        {
            "model": model or settings.SMALL_MODEL or settings.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": SUMMARY_MAX_TOKENS,
        }
    )
    return (response.choices[0].message.content or "").strip()


async def maybe_compact_session(
    session: Dict[str, Any],
    current_context_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Compact a session when its active context exceeds the token threshold.

    Older messages are summarized, the most recent messages are preserved, and
    the session's message list is replaced with the summary plus recent turns.
    Accounts for system prompt and tool schema static overhead in context budgeting.

    Args:
        session (Dict[str, Any]): Session data to inspect and potentially compact.
        current_context_tokens (Optional[int]): Measured request context size.
        system_prompt (Optional[str]): Current system prompt text.
        tools (Optional[List[Dict[str, Any]]]): Tool schemas sent to LLM.

    Returns:
        bool: True if the session was compacted, otherwise False.
    """
    messages: List[Dict[str, Any]] = session.get("messages", [])
    summary_messages = [message for message in messages if is_summary_message(message)]
    normal_messages = [message for message in messages if not is_summary_message(message)]

    message_tokens = count_messages_tokens(messages)
    static_overhead = calculate_static_overhead(system_prompt=system_prompt, tools=tools)
    measured = current_context_tokens if current_context_tokens is not None else (static_overhead + message_tokens)
    session.setdefault("compaction", {})["context_tokens"] = measured

    if measured <= TOKEN_THRESHOLD:
        return False

    budget_after = TOKEN_THRESHOLD - static_overhead - SUMMARY_MAX_TOKENS - SAFETY_MARGIN
    keep_recent_tokens = max(2000, budget_after)

    split = find_split_index(normal_messages, keep_recent_tokens)
    if len(normal_messages) - split < MIN_OLDER_MESSAGES:
        desired_split = min(
            MIN_OLDER_MESSAGES,
            len(normal_messages) - MIN_RECENT_MESSAGES,
        )
        if desired_split > split:
            split = desired_split

    older = normal_messages[:split]
    recent = normal_messages[split:]

    if not older:
        logger.warning("Compaction skipped: no older messages to summarize.")
        return False

    existing_summary = ""
    if summary_messages:
        existing_summary = "\n\n".join(
            str(message.get("content") or "") for message in summary_messages
        )

    try:
        summary_text = await generate_context_summary(existing_summary, older)
    except Exception as exc:
        logger.warning("Compaction failed; history unchanged: %s", exc)
        return False

    if not summary_text:
        return False

    previous = session.get("compaction", {})
    summary_message = {
        "role": "system",
        "content": f"Conversation summary so far:\n{summary_text}",
        "metadata": {
            SUMMARY_FLAG: True,
            "summary_version": int(previous.get("compaction_count", 0)) + 1,
            "covered_messages": len(older),
            "created_at": datetime.now().isoformat(),
        },
    }

    new_messages = [summary_message] + recent
    new_total = static_overhead + count_messages_tokens(new_messages)

    attempts = 0
    while new_total > TOKEN_THRESHOLD and attempts < 3 and len(recent) > MIN_RECENT_MESSAGES:
        attempts += 1
        extra_count = max(1, len(recent) // 4)
        extra_messages = recent[:extra_count]
        older.extend(extra_messages)
        recent = recent[extra_count:]
        try:
            summary_text = await generate_context_summary(summary_text, extra_messages)
        except Exception:
            break
        summary_message["content"] = f"Conversation summary so far:\n{summary_text}"
        new_messages = [summary_message] + recent
        new_total = static_overhead + count_messages_tokens(new_messages)

    while new_total > TOKEN_THRESHOLD and len(recent) > 1:
        recent = recent[1:]
        while recent and recent[0].get("role") == "tool":
            recent = recent[1:]
        new_messages = [summary_message] + recent
        new_total = static_overhead + count_messages_tokens(new_messages)

    if new_total > TOKEN_THRESHOLD:
        logger.warning("Compaction could not bring context below threshold: %s tokens", new_total)

    session["messages"] = new_messages
    session["compaction"] = {
        "summary": summary_text,
        "summary_tokens": count_text_tokens(summary_text),
        "context_tokens": count_messages_tokens(new_messages),
        "compaction_count": int(previous.get("compaction_count", 0)) + 1,
        "compacted_message_count": int(previous.get("compacted_message_count", 0)) + len(older),
        "last_compacted_at": datetime.now().isoformat(),
        "threshold": TOKEN_THRESHOLD,
    }
    session["updated_at"] = datetime.now().isoformat()
    save_session(session)
    return True

