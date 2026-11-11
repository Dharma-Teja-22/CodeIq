import asyncio
from typing import List, Dict, Any
from codeiq_dev.core import compaction
from codeiq_dev.core.llm import to_llm_messages


def _small_messages(count: int) -> List[Dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": f"small response {index}",
        }
        for index in range(count)
    ]


def test_find_split_index_does_not_orphan_tool_messages():
    tool_message = {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "done",
    }
    messages = [
        {"role": "user", "content": "run the tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "testTool", "arguments": "{}"},
                }
            ],
        },
        tool_message,
    ] + _small_messages(compaction.MIN_RECENT_MESSAGES)

    recent_budget = compaction.count_message_tokens(tool_message) + sum(
        compaction.count_message_tokens(m)
        for m in _small_messages(compaction.MIN_RECENT_MESSAGES)
    )

    split = compaction.find_split_index(messages, recent_budget)

    assert split == 1
    assert messages[split].get("role") != "tool"


def test_to_llm_messages_removes_internal_metadata():
    messages = [
        {
            "role": "system",
            "content": "summary",
            "metadata": {"is_compaction_summary": True},
        },
        {
            "role": "user",
            "content": "hello",
            "internal": "drop me",
        },
    ]

    sanitized = to_llm_messages(messages)

    assert "metadata" not in sanitized[0]
    assert "internal" not in sanitized[1]
    assert sanitized[0]["content"] == "summary"


def test_compaction_replaces_older_messages_and_prevents_repeat(monkeypatch):
    async def fake_summary(existing_summary, older_messages, model=None):
        return "- User goal: test compaction\n- Decision: preserve recent messages"

    monkeypatch.setattr(compaction, "generate_context_summary", fake_summary)
    monkeypatch.setattr(compaction, "save_session", lambda session: None)

    session = {
        "session_id": "test-session",
        "messages": [
            {"role": "user", "content": "token " * 60000},
            {"role": "assistant", "content": "token " * 60000},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
            {"role": "user", "content": "latest question"},
            {"role": "assistant", "content": "latest answer"},
            {"role": "user", "content": "current question"},
        ],
    }

    changed = asyncio.run(compaction.maybe_compact_session(session))

    assert changed is True
    assert compaction.is_summary_message(session["messages"][0])
    assert "Conversation summary so far:" in session["messages"][0]["content"]
    assert compaction.count_messages_tokens(session["messages"]) < compaction.TOKEN_THRESHOLD
    assert session["compaction"]["compaction_count"] == 1
    assert session["compaction"]["compacted_message_count"] == 2
    assert session["compaction"]["context_tokens"] < compaction.TOKEN_THRESHOLD

    unchanged = asyncio.run(compaction.maybe_compact_session(session))

    assert unchanged is False
    assert session["compaction"]["compaction_count"] == 1
    assert len([m for m in session["messages"] if compaction.is_summary_message(m)]) == 1


def test_compaction_accounts_for_output_and_tool_calls(monkeypatch):
    """
    Test that compaction accounts for tokens across input (user),
    output (assistant), and tool calls / tool execution results.
    """
    async def fake_summary(existing_summary, older_messages, model=None):
        # Verify that tool calls and outputs were properly included in the older messages
        roles = [m.get("role") for m in older_messages]
        assert "assistant" in roles
        assert "tool" in roles
        return "- Handled tool executions and large tool responses"

    monkeypatch.setattr(compaction, "generate_context_summary", fake_summary)
    monkeypatch.setattr(compaction, "save_session", lambda session: None)

    # Large tool output and tool call
    large_tool_output = "data-record " * 60000
    session = {
        "session_id": "test-tool-compaction",
        "messages": [
            {"role": "user", "content": "Fetch database records"},
            {
                "role": "assistant",
                "content": "Fetching the database records now...",
                "tool_calls": [
                    {
                        "id": "call-read-1",
                        "type": "function",
                        "function": {
                            "name": "fileOperations",
                            "arguments": '{"operation": "read_file", "file_path": "big_data.txt"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-read-1",
                "name": "fileOperations",
                "content": large_tool_output,
            },
            {
                "role": "assistant",
                "content": "output analysis " * 30000,
            },
            {"role": "user", "content": "What is the next step?"},
            {"role": "assistant", "content": "Next step is to filter."},
            {"role": "user", "content": "Apply the filter."},
            {"role": "assistant", "content": "Filter applied successfully."},
            {"role": "user", "content": "Can you verify?"},
            {"role": "assistant", "content": "Verification completed."},
        ],
    }

    # Verify that the message payload accounts for both output tokens and tool calls
    asst_tokens = compaction.count_message_tokens(session["messages"][1])
    tool_tokens = compaction.count_message_tokens(session["messages"][2])
    output_tokens = compaction.count_message_tokens(session["messages"][3])

    assert asst_tokens > 10
    assert tool_tokens > 50000
    assert output_tokens > 25000

    total_tokens = compaction.count_messages_tokens(session["messages"])
    assert total_tokens > compaction.TOKEN_THRESHOLD

    changed = asyncio.run(compaction.maybe_compact_session(session))
    assert changed is True
    assert compaction.is_summary_message(session["messages"][0])
    assert compaction.count_messages_tokens(session["messages"]) < compaction.TOKEN_THRESHOLD


