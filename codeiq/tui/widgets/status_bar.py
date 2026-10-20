"""Status bar widget showing live metrics, tokens, and model details."""

from __future__ import annotations
from pathlib import Path
from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from ...models import TokenUsage
from ...tools.git_tools import get_git_status_summary


class AppStatusBar(Widget):
    """Bottom status bar with real-time token tracking, cost, and active model status."""

    def __init__(self, cwd: Path, model: str = "gemini-2.5-flash", provider: str = "gemini", **kwargs):
        super().__init__(id="app-status-bar", **kwargs)
        self.cwd = cwd
        self.model = model
        self.provider = provider
        self.total_tokens = TokenUsage()
        self.git_summary = get_git_status_summary(self.cwd)

    def compose(self) -> ComposeResult:
        self.status_static = Static(self._render_bar())
        yield self.status_static

    def update_metrics(self, tokens: TokenUsage, model: str = None, provider: str = None) -> None:
        self.total_tokens = tokens
        if model:
            self.model = model
        if provider:
            self.provider = provider
        self.git_summary = get_git_status_summary(self.cwd)
        self.status_static.update(self._render_bar())

    def _render_bar(self) -> Text:
        bar = Text()

        # Model badge
        bar.append("⚡ ", style="bold yellow")
        bar.append(f"{self.model} ", style="bold green")
        bar.append(f"({self.provider.capitalize()})  │  ", style="dim white")

        # Git status
        if self.git_summary.is_git_repo:
            bar.append(f"{self.git_summary.badge}  │  ", style="cyan")
        else:
            bar.append("no-git  │  ", style="dim white")

        # Tokens
        prompt_k = f"{self.total_tokens.prompt_tokens / 1000:.1f}k" if self.total_tokens.prompt_tokens >= 1000 else str(self.total_tokens.prompt_tokens)
        comp_k = f"{self.total_tokens.completion_tokens / 1000:.1f}k" if self.total_tokens.completion_tokens >= 1000 else str(self.total_tokens.completion_tokens)
        tot_k = f"{self.total_tokens.total_tokens / 1000:.1f}k" if self.total_tokens.total_tokens >= 1000 else str(self.total_tokens.total_tokens)

        bar.append("Tokens: ", style="dim")
        bar.append(f"{tot_k} ", style="bold #89dceb")
        bar.append(f"(in:{prompt_k} out:{comp_k})  │  ", style="dim #89dceb")

        # Cost
        cost_str = f"${self.total_tokens.estimated_cost:.5f}"
        bar.append("Cost: ", style="dim")
        bar.append(f"{cost_str}  │  ", style="bold #f9e2af")

        # Key shortcuts
        bar.append("^B:Tree  ^S:Model  ^N:New  ^O:Sessions  /help", style="dim #a6adc8")

        return bar
