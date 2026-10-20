"""Main CodeIq Textual Terminal User Interface Application."""

from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Input, Label, Static

from ..agent.agent import CodeIqAgent
from ..config import Config
from ..models import ChatMessage, Role, Session, ToolCall, ToolState
from ..storage.session_store import SessionStore
from ..tools.git_tools import get_git_status_summary, git_diff, git_status
from ..tools.registry import ToolRegistry
from .modals.approval_modal import ApprovalModal
from .modals.session_modal import SessionManagerModal
from .modals.settings_modal import SettingsModal
from .widgets.diff_viewer import DiffViewerWidget
from .widgets.file_tree import WorkspaceFileTree
from .widgets.message_bubble import MessageBubble
from .widgets.status_bar import AppStatusBar
from .widgets.tool_bubble import ToolBubble


WELCOME_BANNER = """# 🚀 CodeIq — Terminal AI Coding Assistant
*OpenCode-inspired • Local-First • Context-Aware • Gemini-Powered*

- **Workspace:** `{cwd}`
- **Active Model:** `{model}` ({provider})
- **Shortcuts:** `Ctrl+B` Files | `Ctrl+S` Settings | `Ctrl+N` New Session | `Ctrl+O` Resume | `Ctrl+L` Clear | `Ctrl+Q` Quit
- **Mention files:** Type `@filename` (or click files in the left sidebar) to load them into context.
- **Slash Commands:** Type `/help`, `/exit`, `/git`, `/diff`, `/sessions`, `/model`, `/stats`, `/autoapprove`, `/export`
"""


class CodeIqApp(App):
    """The terminal-native AI coding assistant application."""

    CSS_PATH = "styles.tcss"
    TITLE = "CodeIq"
    SUB_TITLE = "Terminal AI Coding Assistant"

    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Toggle Explorer", show=True),
        Binding("ctrl+s", "open_settings", "Settings / Model", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=True),
        Binding("ctrl+o", "open_sessions", "Session History", show=True),
        Binding("ctrl+l", "clear_chat", "Clear Chat", show=True),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
    ]

    def __init__(
        self,
        cwd: Optional[Path] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        session_id: Optional[str] = None,
        auto_approve: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.cwd = (cwd or Path.cwd()).resolve()
        self.config = Config(cwd=str(self.cwd))
        if auto_approve:
            self.config.auto_approve = True
        if model:
            self.config.model = model
        if provider:
            self.config.provider = provider

        self.session_store = SessionStore(cwd=str(self.cwd))
        self.tool_registry = ToolRegistry(cwd=self.cwd)

        # Initialize or resume session
        self.session: Session = None
        if session_id:
            loaded = self.session_store.load_session(session_id)
            if loaded:
                self.session = loaded

        if not self.session:
            self.session = self.session_store.create_session(
                cwd=str(self.cwd),
                model=self.config.model,
                provider=self.config.provider,
                title=f"Session in {self.cwd.name}",
            )

        self.agent = CodeIqAgent(
            session=self.session,
            config=self.config,
            tool_registry=self.tool_registry,
            session_store=self.session_store,
        )

        self.active_tool_bubbles = {}
        self.current_stream_bubble: Optional[MessageBubble] = None
        self._is_busy = False

    def compose(self) -> ComposeResult:
        # 1. Custom Header
        with Horizontal(id="app-header"):
            yield Static("⚡ CodeIq", id="header-title")
            yield Static(f"v1.0", id="header-badge")
            yield Static(f"📂 {self.cwd}", id="header-cwd")
            git_badge = get_git_status_summary(self.cwd).badge
            yield Static(git_badge, id="header-git")

        # 2. Main Container
        with Horizontal(id="main-container"):
            # Left Sidebar: Workspace File Explorer
            with Vertical(id="sidebar"):
                yield Static("📁 Project Explorer", id="sidebar-header")
                yield WorkspaceFileTree(self.cwd)

            # Center: Chat View
            with Vertical(id="chat-container"):
                with VerticalScroll(id="chat-scroll-area"):
                    banner_text = WELCOME_BANNER.format(
                        cwd=self.cwd,
                        model=self.session.model,
                        provider=self.session.provider.capitalize(),
                    )
                    from textual.widgets import Markdown
                    yield Markdown(banner_text, id="welcome-banner")

                    # Rehydrate previous messages if resumed session
                    for msg in self.session.messages:
                        if msg.role in (Role.USER, Role.ASSISTANT):
                            yield MessageBubble(msg, model_name=self.session.model)
                        elif msg.role == Role.TOOL:
                            for tc in msg.tool_calls:
                                yield ToolBubble(tc)

                # Bottom Chat Input Area
                with Vertical(id="input-container"):
                    self.chat_input = Input(
                        placeholder="Ask CodeIq anything... (use @file to mention, /help for commands)",
                        id="chat-input",
                    )
                    yield self.chat_input

                    with Horizontal(id="input-hints-bar"):
                        yield Static("Enter: Send  │  Shift+Enter: Newline  │  @file: Attach file", id="input-hints-left")
                        yield Static("Press Ctrl+B to toggle Files", id="input-hints-right")

        # 3. Status Bar
        self.status_bar = AppStatusBar(
            cwd=self.cwd,
            model=self.session.model,
            provider=self.session.provider,
        )
        yield self.status_bar

    def on_mount(self) -> None:
        self.chat_input.focus()
        self.status_bar.update_metrics(
            tokens=self.session.total_tokens,
            model=self.session.model,
            provider=self.session.provider,
        )

    # --- Key Actions ---
    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.toggle_class("hidden")

    def action_open_settings(self) -> None:
        def on_settings_closed(result: Optional[dict]):
            if result:
                self.config.apply_dict(result)
                self.session.provider = result["provider"]
                self.session.model = result["model"]
                self.agent.switch_model(result["provider"], result["model"])
                self.status_bar.update_metrics(
                    tokens=self.session.total_tokens,
                    model=result["model"],
                    provider=result["provider"],
                )
                self._append_system_notice(
                    f"✓ Settings updated: Provider **{result['provider']}**, Model **{result['model']}**."
                )

        self.push_screen(
            SettingsModal(
                config=self.config,
                current_model=self.session.model,
                current_provider=self.session.provider,
            ),
            on_settings_closed,
        )

    def action_new_session(self) -> None:
        self.session = self.session_store.create_session(
            cwd=str(self.cwd),
            model=self.config.model,
            provider=self.config.provider,
            title=f"Session in {self.cwd.name}",
        )
        self.agent = CodeIqAgent(
            session=self.session,
            config=self.config,
            tool_registry=self.tool_registry,
            session_store=self.session_store,
        )
        self._clear_chat_widgets()
        self.status_bar.update_metrics(
            tokens=self.session.total_tokens,
            model=self.session.model,
            provider=self.session.provider,
        )
        self._append_system_notice(f"✨ Started new session `{self.session.id}`.")

    def action_open_sessions(self) -> None:
        def on_session_picked(action: Optional[str]):
            if not action:
                return
            if action == "new":
                self.action_new_session()
            elif action.startswith("resume:"):
                sid = action.split(":", 1)[1]
                loaded = self.session_store.load_session(sid)
                if loaded:
                    self.session = loaded
                    self.agent = CodeIqAgent(
                        session=self.session,
                        config=self.config,
                        tool_registry=self.tool_registry,
                        session_store=self.session_store,
                    )
                    self._clear_chat_widgets()
                    # Rehydrate chat
                    scroll = self.query_one("#chat-scroll-area", VerticalScroll)
                    for msg in self.session.messages:
                        if msg.role in (Role.USER, Role.ASSISTANT):
                            scroll.mount(MessageBubble(msg, model_name=self.session.model))
                        elif msg.role == Role.TOOL:
                            for tc in msg.tool_calls:
                                scroll.mount(ToolBubble(tc))
                    self.status_bar.update_metrics(
                        tokens=self.session.total_tokens,
                        model=self.session.model,
                        provider=self.session.provider,
                    )
                    self._append_system_notice(f"✓ Resumed session `{sid}` ({len(self.session.messages)} messages).")
                    scroll.scroll_end(animate=False)

        self.push_screen(SessionManagerModal(self.session_store), on_session_picked)

    def action_clear_chat(self) -> None:
        self._clear_chat_widgets()
        self._append_system_notice("Chat display cleared. History is safely preserved in session.")

    def action_quit_app(self) -> None:
        self.exit()

    def _clear_chat_widgets(self) -> None:
        scroll = self.query_one("#chat-scroll-area", VerticalScroll)
        scroll.remove_children()

    def _append_system_notice(self, markdown_text: str) -> None:
        scroll = self.query_one("#chat-scroll-area", VerticalScroll)
        notice_msg = ChatMessage(role=Role.ASSISTANT, content=markdown_text)
        bubble = MessageBubble(notice_msg, model_name="System")
        scroll.mount(bubble)
        scroll.scroll_end(animate=True)

    # --- Tree interaction: auto insert @path into prompt ---
    def on_workspace_file_tree_file_picked(self, event: WorkspaceFileTree.FilePicked) -> None:
        try:
            rel = event.path.relative_to(self.cwd).as_posix()
        except ValueError:
            rel = event.path.name

        current_val = self.chat_input.value
        token = f"@{rel} "
        if current_val and not current_val.endswith(" "):
            self.chat_input.value = f"{current_val} {token}"
        else:
            self.chat_input.value = f"{current_val}{token}"
        self.chat_input.focus()

    # --- Prompt Handling & Agent Turn ---
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self._is_busy:
            return

        self.chat_input.value = ""

        # Check for Slash Commands
        if text.startswith("/"):
            await self._handle_slash_command(text)
            return

        self._is_busy = True
        scroll = self.query_one("#chat-scroll-area", VerticalScroll)

        # 1. Mount User Bubble
        user_msg = ChatMessage(role=Role.USER, content=text)
        user_bubble = MessageBubble(user_msg)
        await scroll.mount(user_bubble)

        # 2. Mount Assistant Stream Bubble
        assist_msg = ChatMessage(role=Role.ASSISTANT, content="")
        self.current_stream_bubble = MessageBubble(assist_msg, model_name=self.session.model)
        await scroll.mount(self.current_stream_bubble)
        scroll.scroll_end(animate=True)

        # 3. Run Agent in background task
        asyncio.create_task(self._execute_agent_turn(text))

    async def _handle_slash_command(self, cmd: str) -> None:
        parts = cmd.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if name == "/help":
            help_md = """### 📖 CodeIq Command Cheat Sheet:
- **`/help`**: Show this help manual
- **`/exit`** or **`/quit`**: Exit and close the CodeIq TUI
- **`/clear`**: Clear current chat screen
- **`/sessions`** or **`/resume`**: Open session history manager
- **`/model <name>`**: Switch model (e.g. `/model gemini-2.5-pro` or `/model gpt-4o`)
- **`/provider <name>`**: Switch provider (`gemini`, `openai`, `groq`, `ollama`)
- **`/git`**: Inspect current Git repository status
- **`/diff`**: View unstaged/staged Git diff
- **`/files`**: Toggle project directory explorer sidebar
- **`/stats`** or **`/cost`**: View cumulative token usage and estimated dollar cost
- **`/autoapprove`**: Toggle auto-approval mode on/off
- **`/export`**: Export session to markdown file
- **`@filename`**: Type anywhere in your prompt to attach file contents
- **Shortcut:** `Ctrl+Q` also exits the application immediately
-"""
            self._append_system_notice(help_md)

        elif name in ("/exit", "/quit", "/q"):
            self.action_quit_app()
            return

        elif name in ("/clear", "/cls"):
            self.action_clear_chat()

        elif name in ("/sessions", "/resume"):
            self.action_open_sessions()

        elif name in ("/settings", "/config"):
            self.action_open_settings()

        elif name == "/model":
            if arg:
                self.session.model = arg
                self.agent.switch_model(self.session.provider, arg)
                self.status_bar.update_metrics(
                    tokens=self.session.total_tokens,
                    model=arg,
                    provider=self.session.provider,
                )
                self._append_system_notice(f"Switched model to **{arg}**.")
            else:
                self.action_open_settings()

        elif name == "/provider":
            if arg:
                self.session.provider = arg
                self.agent.switch_model(arg, self.session.model)
                self.status_bar.update_metrics(
                    tokens=self.session.total_tokens,
                    model=self.session.model,
                    provider=arg,
                )
                self._append_system_notice(f"Switched provider to **{arg}**.")
            else:
                self.action_open_settings()

        elif name == "/git":
            out = git_status(self.cwd)
            self._append_system_notice(f"### Git Status:\n```\n{out}\n```")

        elif name == "/diff":
            out = git_diff(cwd=self.cwd)
            if out.strip() == "No changes detected in git diff.":
                self._append_system_notice("No unstaged Git changes detected.")
            else:
                scroll = self.query_one("#chat-scroll-area", VerticalScroll)
                await scroll.mount(DiffViewerWidget(out, filename="Workspace Diff"))
                scroll.scroll_end(animate=True)

        elif name == "/files":
            self.action_toggle_sidebar()

        elif name in ("/stats", "/cost"):
            t = self.session.total_tokens
            stats_md = f"""### 📊 Session Token & Cost Statistics:
- **Total Prompt Tokens:** {t.prompt_tokens:,}
- **Total Completion Tokens:** {t.completion_tokens:,}
- **Total Tokens:** {t.total_tokens:,}
- **Estimated Total Cost:** **${t.estimated_cost:.5f} USD**
- **Session Messages:** {len(self.session.messages)}
- **Model:** `{self.session.model}` ({self.session.provider})
"""
            self._append_system_notice(stats_md)

        elif name == "/autoapprove":
            self.config.auto_approve = not self.config.auto_approve
            state_str = "ENABLED" if self.config.auto_approve else "DISABLED"
            self._append_system_notice(f"Auto-approval mode is now **{state_str}**.")

        elif name == "/export":
            path = self.session_store.export_markdown(self.session)
            self._append_system_notice(f"Session successfully exported to: `{path.name}`")

        else:
            self._append_system_notice(f"Unknown command: `{cmd}`. Type `/help` for available commands.")

    async def _execute_agent_turn(self, user_input: str) -> None:
        scroll = self.query_one("#chat-scroll-area", VerticalScroll)

        def on_text_delta(delta: str):
            if self.current_stream_bubble:
                self.current_stream_bubble.append_text(delta)
                scroll.scroll_end(animate=False)

        def on_thought_delta(thought: str):
            pass

        def on_tool_detected(tool_call: ToolCall):
            # Mount a new tool bubble
            tb = ToolBubble(tool_call)
            self.active_tool_bubbles[tool_call.id] = tb
            scroll.mount(tb)
            scroll.scroll_end(animate=True)

        async def on_approval_requested(tool_call: ToolCall) -> bool:
            diff_preview = tool_call.diff_preview
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

            def on_modal_result(choice: Optional[str]):
                if not future.done():
                    future.set_result(choice or "reject")

            self.push_screen(
                ApprovalModal(tool_call, diff_preview=diff_preview),
                on_modal_result,
            )

            choice = await future
            if choice == "always":
                self.config.auto_approve = True
                self._append_system_notice("Auto-approval enabled for the rest of this session.")
                return True
            return choice == "approve"

        def on_tool_finished(tool_call: ToolCall):
            tb = self.active_tool_bubbles.get(tool_call.id)
            if tb:
                tb.update_state(
                    state=tool_call.state,
                    result=tool_call.result,
                    error=tool_call.error,
                    diff_preview=tool_call.diff_preview,
                )
                scroll.scroll_end(animate=False)

        try:
            await self.agent.run_turn(
                user_input=user_input,
                on_text_delta=on_text_delta,
                on_thought_delta=on_thought_delta,
                on_tool_call_detected=on_tool_detected,
                on_tool_approved=on_approval_requested,
                on_tool_finished=on_tool_finished,
            )
        except Exception as e:
            if self.current_stream_bubble:
                self.current_stream_bubble.append_text(f"\n\n❌ **Unexpected Agent Error:** {str(e)}")
        finally:
            self._is_busy = False
            self.status_bar.update_metrics(
                tokens=self.session.total_tokens,
                model=self.session.model,
                provider=self.session.provider,
            )
            scroll.scroll_end(animate=True)
            self.chat_input.focus()
