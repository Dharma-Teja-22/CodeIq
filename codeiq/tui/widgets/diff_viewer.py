"""Unified colored diff preview widget."""

from __future__ import annotations
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class DiffViewerWidget(Widget):
    """Renders unified diffs with green additions, red deletions, and cyan chunk headers."""

    DEFAULT_CSS = """
    DiffViewerWidget {
        background: #11111b;
        border: solid #313244;
        padding: 0 1;
        max-height: 18;
        overflow-y: auto;
    }
    """

    def __init__(self, diff_text: str, filename: str = "", **kwargs):
        super().__init__(**kwargs)
        self.diff_text = diff_text
        self.filename = filename

    def compose(self) -> ComposeResult:
        yield Static(self._format_diff())

    def _format_diff(self) -> Text:
        text = Text()
        if self.filename:
            text.append(f"📄 Diff Preview: {self.filename}\n", style="bold yellow")

        lines = self.diff_text.splitlines()
        for line in lines:
            if line.startswith("+++") or line.startswith("---"):
                text.append(line + "\n", style="bold dim white")
            elif line.startswith("@@"):
                text.append(line + "\n", style="bold cyan")
            elif line.startswith("+"):
                text.append(line + "\n", style="bold green on #142e18")
            elif line.startswith("-"):
                text.append(line + "\n", style="bold red on #381a1a")
            else:
                text.append(line + "\n", style="dim #a6adc8")

        return text
