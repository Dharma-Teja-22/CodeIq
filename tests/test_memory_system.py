
import os
import tempfile
from pathlib import Path
from neo.core.memory import (
    save_to_memory,
    load_global_memory,
    update_project_memory,
    load_project_memory,
    log_successful_debug,
    save_concept,
    recall_memory,
    BM25Retriever,
)
from neo.core.compaction import prune_message_payload
from neo.core.session import create_session, fork_session, archive_session_snapshot


def test_micro_compaction_pruning():
    messages = [
        {"role": "user", "content": "Run command 1"},
        {"role": "assistant", "content": "Running..."},
        {"role": "tool", "name": "executeTool", "tool_call_id": "call_1", "content": "A" * 300},
        {"role": "user", "content": "Run command 2"},
        {"role": "assistant", "content": "Running 2..."},
        {"role": "tool", "name": "executeTool", "tool_call_id": "call_2", "content": "B" * 300},
        {"role": "user", "content": "Current turn"},
        {"role": "assistant", "content": "Answering"},
    ]
    # retention_turns = 2 means the last 2 user turns (command 2 and Current turn) stay intact.
    # Older tool output (call_1) should be stubbed.
    pruned = prune_message_payload(messages, retention_turns=2, stub_char_threshold=150)
    assert len(pruned) == len(messages)
    assert "[Output of executeTool omitted:" in pruned[2]["content"]
    assert pruned[2]["tool_call_id"] == "call_1"  # API pairing invariant strictly preserved
    assert pruned[5]["content"] == "B" * 300  # Within retention horizon: untouched


def test_global_memory_deduplication_and_superseding():
    res1 = save_to_memory("Use strictly TypeScript for all backend code", "Preference")
    assert "Saved new" in res1 or "Memory already contains" in res1

    # Exact duplicate rejected
    res2 = save_to_memory("Use strictly TypeScript for all backend code", "Preference")
    assert "already contains" in res2

    # Topic overwrite test
    res3 = save_to_memory("Use strictly Python and FastAPI for all backend code", "Preference")
    assert "Updated and superseded" in res3 or "Saved new" in res3


def test_project_memory_canonical_schema():
    res = update_project_memory(
        section="Tech Stack & Runtime",
        content="- Python 3.12\n- FastAPI",
        mode="replace"
    )
    assert "Successfully updated" in res
    loaded = load_project_memory()
    assert "## Tech Stack & Runtime" in loaded
    assert "FastAPI" in loaded
    assert "## Active Architecture & Key Modules" in loaded


def test_bm25_episodic_retrieval():
    log_successful_debug(
        error_description="ConnectionTimeout in Redis Cluster client",
        solution="Set socket_timeout=5.0 and retry_on_timeout=True"
    )
    save_concept(
        concept_name="redis_cluster_config",
        explanation="Redis cluster configuration requires explicit socket timeouts to avoid connection drops."
    )

    result = recall_memory("Redis Cluster ConnectionTimeout")
    assert "ConnectionTimeout" in result or "redis_cluster_config" in result


def test_session_forking_and_snapshot():
    session = create_session(save=False)
    session["messages"].append({"role": "user", "content": "Hello"})
    forked = fork_session(session)
    assert forked["session_id"] != session["session_id"]
    assert forked["title"].startswith("Fork of")
    assert len(forked["messages"]) == 1

    snap = archive_session_snapshot(session)
    assert snap is not None
    assert snap.exists()

