"""Session manager modal dialog for resuming and managing local JSON sessions."""

from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label, Static

from ...storage.session_store import SessionStore


class SessionManagerModal(ModalScreen[Optional[str]]):
    """Modal screen for listing, resuming, and deleting past sessions."""

    DEFAULT_CSS = """
    SessionManagerModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #session-box {
        width: 90;
        max-width: 95%;
        max-height: 85%;
        background: #1e1e2e;
        border: thick #a6e3a1;
        padding: 1 2;
    }

    #session-title {
        color: #a6e3a1;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid #313244;
        padding-bottom: 1;
    }

    #session-table {
        height: 12;
        background: #11111b;
        color: #cdd6f4;
        margin-bottom: 1;
    }

    #session-buttons {
        layout: horizontal;
        height: 3;
        align-horizontal: right;
    }

    .btn-resume {
        background: #a6e3a1;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }

    .btn-new {
        background: #89b4fa;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }

    .btn-delete {
        background: #f38ba8;
        color: #11111b;
        margin-left: 1;
    }

    .btn-close {
        background: #313244;
        color: #cdd6f4;
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
        Binding("enter", "resume", "Resume", show=True),
    ]

    def __init__(self, session_store: SessionStore, **kwargs):
        super().__init__(**kwargs)
        self.store = session_store
        self.sessions = []

    def compose(self) -> ComposeResult:
        with Vertical(id="session-box"):
            yield Static("🗂️  CodeIq Session History (Local JSON)", id="session-title")

            self.table = DataTable(id="session-table")
            self.table.cursor_type = "row"
            yield self.table

            self.status_label = Label("", id="session-status-label")
            yield self.status_label

            with Horizontal(id="session-buttons"):
                yield Button("Close (Esc)", id="btn-close", classes="btn-close")
                yield Button("Delete", id="btn-delete", classes="btn-delete")
                yield Button("Export MD", id="btn-export", classes="btn-close")
                yield Button("New Session", id="btn-new", classes="btn-new")
                yield Button("Resume Selected", id="btn-resume", classes="btn-resume")

    def on_mount(self) -> None:
        self.table.add_columns("Title", "Model", "Msgs", "Tokens", "Cost ($)", "Updated")
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.clear()
        self.sessions = self.store.list_sessions()
        for s in self.sessions:
            cost_str = f"${s['cost']:.5f}" if s.get("cost") else "$0.00"
            tokens_str = f"{s['total_tokens']:,}"
            updated_part = s["updated_at"].replace("T", " ")[:16] if s.get("updated_at") else ""
            self.table.add_row(
                s["title"],
                s["model"],
                str(s["message_count"]),
                tokens_str,
                cost_str,
                updated_part,
                key=s["id"],
            )

    def _get_selected_session_id(self) -> Optional[str]:
        if self.table.cursor_row is not None and self.sessions:
            idx = self.table.cursor_row
            if 0 <= idx < len(self.sessions):
                return self.sessions[idx]["id"]
        return None

    def action_close(self) -> None:
        self.dismiss(None)

    def action_resume(self) -> None:
        sid = self._get_selected_session_id()
        if sid:
            self.dismiss(f"resume:{sid}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.action_close()
        elif event.button.id == "btn-resume":
            self.action_resume()
        elif event.button.id == "btn-new":
            self.dismiss("new")
        elif event.button.id == "btn-delete":
            sid = self._get_selected_session_id()
            if sid:
                self.store.delete_session(sid)
                self.status_label.update(f"Deleted session '{sid}'.")
                self._refresh_table()
        elif event.button.id == "btn-export":
            sid = self._get_selected_session_id()
            if sid:
                session_obj = self.store.load_session(sid)
                if session_obj:
                    export_path = self.store.export_markdown(session_obj)
                    self.status_label.update(f"Exported markdown to: {export_path.name}")
