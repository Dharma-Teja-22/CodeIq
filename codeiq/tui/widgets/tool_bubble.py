"""Interactive tool execution bubble widget."""

from __future__ import annotations
import json
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widget import Widget
from textual.widgets import Static

from ...models import ToolCall, ToolState
from .diff_viewer import DiffViewerWidget


class ToolBubble(Widget):
    """Visual card representing a tool call, its execution status, and results/diffs."""

    def __init__(self, tool_call: ToolCall, **kwargs):
        super().__init__(classes="tool-bubble", **kwargs)
        self.tool_call = tool_call

    def compose(self) -> ComposeResult:
        with Vertical():
            self.header_static = Static(self._render_header())
            yield self.header_static

            # Optional Diff Preview container
            self.diff_container = Container(classes="tool-diff-container")
            if self.tool_call.diff_preview:
                self.diff_container.mount(
                    DiffViewerWidget(
                        diff_text=self.tool_call.diff_preview,
                        filename=self.tool_call.args.get("path", ""),
                    )
                )
            else:
                self.diff_container.display = False
            yield self.diff_container

            # Output block
            self.output_static = Static(self._render_output(), classes="tool-output-block")
            if not self.tool_call.result and not self.tool_call.error:
                self.output_static.display = False
            yield self.output_static

        self._apply_state_class()

    def _render_header(self) -> Text:
        header = Text()
        name = self.tool_call.name
        header.append("🛠️  ", style="bold yellow")
        header.append(f"{name}", style="bold #fab387")

        # Format key arguments in header
        arg_summary = []
        if "path" in self.tool_call.args:
            arg_summary.append(f"path='{self.tool_call.args['path']}'")
        if "command" in self.tool_call.args:
            cmd = self.tool_call.args["command"]
            if len(cmd) > 40:
                cmd = cmd[:37] + "..."
            arg_summary.append(f"cmd='{cmd}'")
        if "query" in self.tool_call.args:
            arg_summary.append(f"query='{self.tool_call.args['query']}'")

        if arg_summary:
            header.append(f" ({', '.join(arg_summary)})", style="dim white")

        # State badge
        state = self.tool_call.state
        if state == ToolState.PENDING_APPROVAL:
            header.append("  [WAITING APPROVAL]", style="bold #f9e2af on #313244")
        elif state == ToolState.RUNNING:
            header.append("  [RUNNING...]", style="bold #89dceb on #313244")
        elif state == ToolState.SUCCESS:
            header.append("  [✓ COMPLETED]", style="bold #a6e3a1 on #183020")
        elif state == ToolState.REJECTED:
            header.append("  [✗ REJECTED]", style="bold #f38ba8 on #381a1a")
        elif state == ToolState.ERROR:
            header.append("  [✗ ERROR]", style="bold #f38ba8 on #381a1a")

        return header

    def _render_output(self) -> Text:
        txt = Text()
        if self.tool_call.result:
            lines = self.tool_call.result.strip().splitlines()
            if len(lines) > 20:
                preview_text = "\n".join(lines[:20]) + f"\n... [and {len(lines) - 20} more lines]"
            else:
                preview_text = "\n".join(lines)
            txt.append("Result:\n", style="bold dim white")
            txt.append(preview_text, style="dim #cdd6f4")
        elif self.tool_call.error:
            txt.append("Error:\n", style="bold red")
            txt.append(self.tool_call.error, style="#f38ba8")
        return txt

    def _apply_state_class(self) -> None:
        for c in ("tool-pending", "tool-running", "tool-success", "tool-error"):
            self.remove_class(c)

        state = self.tool_call.state
        if state == ToolState.PENDING_APPROVAL:
            self.add_class("tool-pending")
        elif state == ToolState.RUNNING:
            self.add_class("tool-running")
        elif state == ToolState.SUCCESS:
            self.add_class("tool-success")
        elif state in (ToolState.ERROR, ToolState.REJECTED):
            self.add_class("tool-error")

    def update_state(self, state: ToolState, result: str = None, error: str = None, diff_preview: str = None) -> None:
        self.tool_call.state = state
        if result is not None:
            self.tool_call.result = result
        if error is not None:
            self.tool_call.error = error
        if diff_preview is not None:
            self.tool_call.diff_preview = diff_preview

        self.header_static.update(self._render_header())
        self._apply_state_class()

        if self.tool_call.diff_preview and not self.diff_container.display:
            self.diff_container.mount(
                DiffViewerWidget(
                    diff_text=self.tool_call.diff_preview,
                    filename=self.tool_call.args.get("path", ""),
                )
            )
            self.diff_container.display = True

        if self.tool_call.result or self.tool_call.error:
            self.output_static.update(self._render_output())
            self.output_static.display = True
