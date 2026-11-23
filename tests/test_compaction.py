import asyncio
from typing import List, Dict, Any
from neo.core import compaction
from neo.core.llm import to_llm_messages


def _small_messages(count: int) -> List[Dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "content": f"small response {index}",
        }
        for index in range(count)
    ]


def test_prune_message_payload_does_not_orphan_tool_messages():
    tool_message = {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "testTool",
        "content": "A" * 300,
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
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "turn 3"},
        {"role": "assistant", "content": "reply 3"},
    ]

    pruned = compaction.prune_message_payload(messages, retention_turns=2, stub_char_threshold=150)
    assert len(pruned) == len(messages)
    # Outside retention horizon: tool message is stubbed but role and tool_call_id are intact
    assert "[Output of testTool omitted:" in pruned[2]["content"]
    assert pruned[2]["tool_call_id"] == "call-1"
    assert pruned[2]["role"] == "tool"


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
    assert "compaction" not in session

    unchanged = asyncio.run(compaction.maybe_compact_session(session))

    assert unchanged is False
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


