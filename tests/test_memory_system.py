
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


def test_global_memory_deduplication_and_superseding(tmp_path, monkeypatch):
    test_dir = tmp_path / ".neo"
    monkeypatch.setattr("neo.core.memory.NEO_HOME", test_dir)
    monkeypatch.setattr("neo.core.memory.MEMORY_DIR", test_dir / "memory")
    monkeypatch.setattr("neo.core.memory.PROJECTS_MEMORY_DIR", test_dir / "memory" / "projects")
    monkeypatch.setattr("neo.core.memory.CONCEPTS_DIR", test_dir / "memory" / "concepts")
    monkeypatch.setattr("neo.core.memory.GLOBAL_MEMORY_FILE", test_dir / "memory" / "global_memory.md")
    monkeypatch.setattr("neo.core.memory.DEBUG_HISTORY_FILE", test_dir / "memory" / "debug_history.md")

    # 1. Emoji preference superseding
    res1 = save_to_memory("Use emojis", "Preference")
    assert "Saved new" in res1
    mem = load_global_memory()
    assert "-Preference: Use emojis" in mem

    # Duplicate rejection
    res1_dup = save_to_memory("Use emojis", "Preference")
    assert "already contains" in res1_dup

    # Contradiction: 'Never use emojis from now on' should overwrite 'Use emojis'
    res2 = save_to_memory("I don't want to use emojis. Never use emojis from now on.", "Preference")
    assert "Updated and superseded" in res2
    mem2 = load_global_memory()
    assert "Never use emojis from now on" in mem2
    assert "Use emojis" not in mem2 or "Never use emojis" in mem2
    # Ensure no duplicate lines
    lines = [l for l in mem2.splitlines() if "emoji" in l.lower()]
    assert len(lines) == 1
    assert "never use emojis" in lines[0].lower()

    # 2. Antonym / format opposition: Tabs vs Spaces
    save_to_memory("Always use tabs for indentation", "Preference")
    save_to_memory("Never use tabs, use 2 spaces for indentation", "Preference")
    mem3 = load_global_memory()
    lines_indent = [l for l in mem3.splitlines() if "indent" in l.lower() or "tab" in l.lower() or "space" in l.lower()]
    assert len(lines_indent) == 1
    assert "2 spaces" in lines_indent[0]

    # 3. Light mode vs Dark mode
    save_to_memory("Prefer dark mode", "Preference")
    save_to_memory("Switch to light mode", "Preference")
    mem4 = load_global_memory()
    lines_mode = [l for l in mem4.splitlines() if "mode" in l.lower()]
    assert len(lines_mode) == 1
    assert "light mode" in lines_mode[0]


def test_project_memory_deduplication_and_superseding(tmp_path, monkeypatch):
    test_dir = tmp_path / ".neo"
    monkeypatch.setattr("neo.core.memory.NEO_HOME", test_dir)
    monkeypatch.setattr("neo.core.memory.MEMORY_DIR", test_dir / "memory")
    monkeypatch.setattr("neo.core.memory.PROJECTS_MEMORY_DIR", test_dir / "memory" / "projects")

    # In append mode, conflicting items should supersede existing items instead of accumulating duplicates
    update_project_memory("Critical Constraints, Preferences", "- Use emojis in git commit messages", mode="append", project_name="myproj")
    update_project_memory("Critical Constraints, Preferences", "- Never use emojis in commit messages, keep plain text", mode="append", project_name="myproj")

    loaded = load_project_memory("myproj")
    lines = [l for l in loaded.splitlines() if "emoji" in l.lower()]
    assert len(lines) == 1
    assert "Never use emojis" in lines[0]


def test_project_memory_canonical_schema(tmp_path, monkeypatch):
    test_dir = tmp_path / ".neo"
    monkeypatch.setattr("neo.core.memory.NEO_HOME", test_dir)
    monkeypatch.setattr("neo.core.memory.MEMORY_DIR", test_dir / "memory")
    monkeypatch.setattr("neo.core.memory.PROJECTS_MEMORY_DIR", test_dir / "memory" / "projects")

    res = update_project_memory(
        section="Tech Stack & Runtime",
        content="- Python 3.12\n- FastAPI",
        mode="replace",
        project_name="myproj"
    )
    assert "Successfully updated" in res
    loaded = load_project_memory("myproj")
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

