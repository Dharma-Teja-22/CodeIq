"""Unit tests for CodeIq core subsystems."""

import json
from pathlib import Path
import tempfile
import pytest

from codeiq.diff.diff_engine import DiffEngine
from codeiq.llm.pricing import calculate_cost, estimate_tokens, get_model_rate
from codeiq.models import ChatMessage, Role, Session, ToolCall, ToolState, TokenUsage
from codeiq.storage.session_store import SessionStore
from codeiq.tools.bash_tools import execute_command_sync, is_risky_command
from codeiq.tools.file_tools import (
    edit_file,
    get_ignored_patterns,
    grep_search,
    is_ignored,
    list_dir,
    read_file,
    search_files,
    write_file,
)
from codeiq.tools.registry import ToolRegistry
from codeiq.agent.context import ContextManager
from codeiq.config import Config


def test_models_serialization():
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, estimated_cost=0.00012)
    msg = ChatMessage(role=Role.USER, content="Hello CodeIq", token_usage=usage)
    data = msg.to_dict()
    restored = ChatMessage.from_dict(data)

    assert restored.role == Role.USER
    assert restored.content == "Hello CodeIq"
    assert restored.token_usage.total_tokens == 150


def test_diff_engine():
    old_content = "line 1\nline 2\nline 3\n"
    new_content = "line 1\nline 2 modified\nline 3\nline 4\n"

    diff_res = DiffEngine.compute_diff("test.py", old_content, new_content)
    assert diff_res.additions >= 2
    assert diff_res.deletions >= 1
    assert "line 2 modified" in diff_res.diff_text
    assert diff_res.filename == "test.py"


def test_pricing_calculator():
    # Gemini 2.5 Flash: $0.075 / 1M prompt, $0.30 / 1M completion
    cost = calculate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert round(cost, 2) == 0.38

    # Local Ollama is free
    cost_ollama = calculate_cost("ollama/qwen", 5000, 5000)
    assert cost_ollama == 0.0

    # Token estimation
    tokens = estimate_tokens("hello world codeiq test string")
    assert tokens > 0


def test_file_tools_in_tempdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Write file
        w_res = write_file("sample.py", "def foo():\n    return 42\n", cwd=tmp_path)
        assert "Successfully wrote" in w_res
        assert (tmp_path / "sample.py").exists()

        # Read file
        r_res = read_file("sample.py", cwd=tmp_path)
        assert "def foo():" in r_res
        assert "return 42" in r_res

        # Edit file
        e_res = edit_file("sample.py", "return 42", "return 100", cwd=tmp_path)
        assert "Successfully updated" in e_res
        updated_read = read_file("sample.py", cwd=tmp_path)
        assert "return 100" in updated_read
        assert "return 42" not in updated_read

        # Search files
        s_res = search_files("*.py", cwd=tmp_path)
        assert "sample.py" in s_res

        # Grep search
        g_res = grep_search("return 100", cwd=tmp_path)
        assert "sample.py" in g_res
        assert "return 100" in g_res


def test_bash_tools():
    # Safe command
    code, out = execute_command_sync("python -c \"print('CodeIq Terminal Test')\"")
    assert code == 0
    assert "CodeIq Terminal Test" in out

    # Risky command detector
    assert is_risky_command("rm -rf /")
    assert is_risky_command("del /s /q C:\\*")
    assert is_risky_command("git reset --hard HEAD~1")
    assert not is_risky_command("git status")
    assert not is_risky_command("pytest -v")


def test_session_store_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(cwd=tmpdir)
        session = store.create_session(cwd=tmpdir, title="Test Persistence")
        session.messages.append(ChatMessage(role=Role.USER, content="Initial message"))
        session.total_tokens.prompt_tokens = 50
        store.save_session(session)

        loaded = store.load_session(session.id)
        assert loaded is not None
        assert loaded.id == session.id
        assert loaded.title == "Test Persistence"
        assert len(loaded.messages) == 1
        assert loaded.total_tokens.prompt_tokens == 50

        # List sessions
        listed = store.list_sessions()
        assert any(s["id"] == session.id for s in listed)

        # Export markdown
        md_file = store.export_markdown(session)
        assert md_file.exists()
        assert "CodeIq Session: Test Persistence" in md_file.read_text(encoding="utf-8")

        # Delete session
        deleted = store.delete_session(session.id)
        assert deleted is True
        assert store.load_session(session.id) is None


def test_context_manager_mentions():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "hello.py").write_text("print('inside hello.py')", encoding="utf-8")

        cm = ContextManager(cwd=tmp_path)
        mentions = cm.extract_file_mentions("Can you inspect @hello.py please?")
        assert "hello.py" in mentions

        enriched, attached = cm.resolve_mentions_and_enrich_prompt("Check @hello.py")
        assert "hello.py" in attached
        assert "inside hello.py" in enriched


def test_tool_registry_schemas():
    reg = ToolRegistry()
    gemini_tools = reg.to_gemini_tools()
    assert len(gemini_tools) == 1
    assert "function_declarations" in gemini_tools[0]
    func_names = [f["name"] for f in gemini_tools[0]["function_declarations"]]
    assert "read_file" in func_names
    assert "write_file" in func_names
    assert "edit_file" in func_names
    assert "execute_command" in func_names
    assert "git_status" in func_names

    openai_tools = reg.to_openai_tools()
    assert len(openai_tools) >= 10
    assert openai_tools[0]["type"] == "function"


def test_config_provider_model_catalog(tmp_path: Path):
    cfg = Config(cwd=str(tmp_path))

    assert "gemini-2.5-flash" in cfg.get_models_for_provider("gemini")
    assert "gpt-4o" in cfg.get_models_for_provider("openai")
    assert "claude-3-7-sonnet-latest" in cfg.get_models_for_provider("anthropic")

    updated = cfg.add_model_for_provider("gemini", "gemini-experimental-preview")
    assert updated[0] == "gemini-experimental-preview"

    cfg.save_project_config()
    loaded = Config(cwd=str(tmp_path))
    assert "gemini-experimental-preview" in loaded.get_models_for_provider("gemini")
