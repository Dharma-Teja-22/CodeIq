"""Approval modal dialog before executing risky operations."""

from __future__ import annotations
from typing import Optional
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ...models import ToolCall
from ..widgets.diff_viewer import DiffViewerWidget


class ApprovalModal(ModalScreen[str]):
    """Modal screen requesting user confirmation before risky tool operations."""

    DEFAULT_CSS = """
    ApprovalModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #approval-box {
        width: 84;
        max-width: 92%;
        max-height: 85%;
        background: #1e1e2e;
        border: thick #fab387;
        padding: 1 2;
    }

    #approval-title {
        color: #fab387;
        text-style: bold;
        margin-bottom: 1;
    }

    #approval-details {
        margin-bottom: 1;
        color: #cdd6f4;
    }

    #approval-content-scroll {
        max-height: 16;
        background: #11111b;
        border: solid #313244;
        padding: 0 1;
        margin: 1 0;
    }

    #approval-buttons {
        layout: horizontal;
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    .btn-approve {
        background: #a6e3a1;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }

    .btn-reject {
        background: #f38ba8;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }

    .btn-always {
        background: #89b4fa;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("enter", "approve", "Approve", show=True),
        Binding("y", "approve", "Approve", show=False),
        Binding("escape", "reject", "Reject", show=True),
        Binding("n", "reject", "Reject", show=False),
        Binding("a", "always", "Always Approve", show=True),
    ]

    def __init__(self, tool_call: ToolCall, diff_preview: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.tool_call = tool_call
        self.diff_preview = diff_preview

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-box"):
            yield Static("⚠️  Approval Required: Risky Operation", id="approval-title")
            yield Static(self._render_details(), id="approval-details")

            with VerticalScroll(id="approval-content-scroll"):
                if self.diff_preview:
                    yield DiffViewerWidget(
                        diff_text=self.diff_preview,
                        filename=self.tool_call.args.get("path", ""),
                    )
                else:
                    yield Static(self._render_fallback_content())

            with Horizontal(id="approval-buttons"):
                yield Button("Reject (Esc / N)", id="btn-reject", classes="btn-reject")
                yield Button("Always Approve (A)", id="btn-always", classes="btn-always")
                yield Button("Approve (Enter / Y)", id="btn-approve", classes="btn-approve")

    def _render_details(self) -> Text:
        t = Text()
        name = self.tool_call.name
        if name in ("write_file", "edit_file"):
            action = "Create / Overwrite File" if name == "write_file" else "Edit File"
            path = self.tool_call.args.get("path", "")
            t.append(f"Action: ", style="dim")
            t.append(f"{action}\n", style="bold yellow")
            t.append(f"Target: ", style="dim")
            t.append(f"{path}\n", style="bold cyan")
        elif name == "execute_command":
            cmd = self.tool_call.args.get("command", "")
            t.append(f"Action: ", style="dim")
            t.append("Execute Shell Command\n", style="bold red")
            t.append(f"Command: ", style="dim")
            t.append(f"{cmd}\n", style="bold yellow")
        elif name == "git_commit":
            msg = self.tool_call.args.get("message", "")
            t.append("Action: ", style="dim")
            t.append("Git Commit\n", style="bold green")
            t.append("Message: ", style="dim")
            t.append(f'"{msg}"\n', style="italic")
        else:
            t.append(f"Action: {name}\n", style="bold yellow")

        t.append("\nPlease review the preview below before confirming:", style="dim white")
        return t

    def _render_fallback_content(self) -> Text:
        t = Text()
        name = self.tool_call.name
        if name == "execute_command":
            cmd = self.tool_call.args.get("command", "")
            t.append(f"$ {cmd}\n", style="bold cyan")
        else:
            for k, v in self.tool_call.args.items():
                t.append(f"{k}: ", style="bold dim")
                t.append(f"{v}\n", style="white")
        return t

    def action_approve(self) -> None:
        self.dismiss("approve")

    def action_reject(self) -> None:
        self.dismiss("reject")

    def action_always(self) -> None:
        self.dismiss("always")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-approve":
            self.action_approve()
        elif event.button.id == "btn-reject":
            self.action_reject()
        elif event.button.id == "btn-always":
            self.action_always()
