"""Integration tests for agent reasoning loop, tool execution, and approval gates."""

import asyncio
from pathlib import Path
import tempfile
import pytest

from codeiq.agent.agent import CodeIqAgent
from codeiq.config import Config
from codeiq.llm.base import BaseLLMProvider, StreamChunk
from codeiq.models import ChatMessage, Role, Session, ToolCall, ToolState, TokenUsage
from codeiq.storage.session_store import SessionStore
from codeiq.tools.git_tools import git_commit, git_diff, git_log, git_status, run_git
from codeiq.tools.registry import ToolRegistry


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for predictable test scenarios."""

    def __init__(self, script=None):
        super().__init__(api_key="mock", model="mock-model")
        self.script = script or []
        self.turn = 0

    async def stream_chat(self, messages, tools=None, system_prompt=None, temperature=0.2):
        if self.turn < len(self.script):
            step = self.script[self.turn]
            self.turn += 1
            for chunk in step:
                yield chunk
        else:
            yield StreamChunk(text_delta="Task complete.")


@pytest.mark.asyncio
async def test_agent_tool_execution_flow(tmp_path: Path):
    store = SessionStore(cwd=tmp_path)
    session = store.create_session(cwd=str(tmp_path), model="mock-model", provider="mock")
    reg = ToolRegistry(cwd=tmp_path)
    cfg = Config(cwd=str(tmp_path))
    cfg.auto_approve = True

    # LLM requests to write a file
    mock_script = [
        [
            StreamChunk(text_delta="I will create app.py for you.\n"),
            StreamChunk(
                tool_calls=[
                    ToolCall(
                        name="write_file",
                        args={"path": "app.py", "content": "print('hello world')\n"},
                    )
                ]
            ),
        ],
        [
            StreamChunk(text_delta="File app.py has been created successfully!"),
        ]
    ]

    agent = CodeIqAgent(session, config=cfg, tool_registry=reg, session_store=store)
    agent.llm = MockLLMProvider(script=mock_script)

    tools_detected = []
    tools_finished = []

    await agent.run_turn(
        user_input="Create app.py",
        on_tool_call_detected=lambda tc: tools_detected.append(tc),
        on_tool_finished=lambda tc: tools_finished.append(tc),
    )

    assert (tmp_path / "app.py").exists()
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print('hello world')\n"
    assert len(tools_detected) == 1
    assert len(tools_finished) == 1
    assert tools_finished[0].state == ToolState.SUCCESS


@pytest.mark.asyncio
async def test_agent_approval_rejection_flow(tmp_path: Path):
    store = SessionStore(cwd=tmp_path)
    session = store.create_session(cwd=str(tmp_path), model="mock-model", provider="mock")
    reg = ToolRegistry(cwd=tmp_path)
    cfg = Config(cwd=str(tmp_path))
    cfg.auto_approve = False

    mock_script = [
        [
            StreamChunk(
                tool_calls=[
                    ToolCall(
                        name="write_file",
                        args={"path": "danger.py", "content": "import os; os.abort()"},
                    )
                ]
            )
        ],
        [
            StreamChunk(text_delta="I understand you rejected creating danger.py."),
        ]
    ]

    agent = CodeIqAgent(session, config=cfg, tool_registry=reg, session_store=store)
    agent.llm = MockLLMProvider(script=mock_script)

    async def mock_approval(tc: ToolCall) -> bool:
        # User rejects this risky action
        return False

    await agent.run_turn(
        user_input="Create danger.py",
        on_tool_approved=mock_approval,
    )

    assert not (tmp_path / "danger.py").exists()
    # Check that tool was marked rejected
    tool_msg = [m for m in session.messages if m.role == Role.TOOL][0]
    assert tool_msg.tool_calls[0].state == ToolState.REJECTED


def test_git_tools_in_real_repo(tmp_path: Path):
    # Initialize a temporary git repository
    run_git(["init"], cwd=tmp_path)
    run_git(["config", "user.name", "Tester"], cwd=tmp_path)
    run_git(["config", "user.email", "test@codeiq.ai"], cwd=tmp_path)

    # Initial file
    (tmp_path / "main.py").write_text("print('v1')\n", encoding="utf-8")
    run_git(["add", "main.py"], cwd=tmp_path)
    run_git(["commit", "-m", "Initial commit"], cwd=tmp_path)

    # Status check
    status_str = git_status(tmp_path)
    assert "clean" in status_str or "Initial" in status_str or "main" in status_str

    # Modify file
    (tmp_path / "main.py").write_text("print('v2 modified')\n", encoding="utf-8")
    diff_str = git_diff(cwd=tmp_path)
    assert "print('v2 modified')" in diff_str

    # Commit change
    commit_res = git_commit("Updated to v2", cwd=tmp_path)
    assert "Updated to v2" in commit_res

    # Log check
    log_str = git_log(max_count=2, cwd=tmp_path)
    assert "Updated to v2" in log_str
