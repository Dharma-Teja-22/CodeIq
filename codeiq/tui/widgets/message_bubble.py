"""Rich markdown message bubble for chat conversations."""

from __future__ import annotations
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widget import Widget
from textual.widgets import Markdown, Static

from ...models import ChatMessage, Role


class MessageBubble(Widget):
    """Renders a single conversation turn with role headers, timestamps, and rich markdown."""

    def __init__(self, message: ChatMessage, model_name: str = "", **kwargs):
        role_class = "message-user" if message.role == Role.USER else "message-assistant"
        classes = f"message-bubble {role_class}"
        super().__init__(classes=classes, **kwargs)
        self.message = message
        self.model_name = model_name
        self.content_text = message.content or ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._render_header(), classes="message-header")

            if self.message.thought:
                self.thought_static = Static(self._render_thought(), classes="message-thought")
                yield self.thought_static

            # Use Textual's Markdown widget for beautiful rich terminal formatting
            self.markdown_widget = Markdown(self.content_text if self.content_text else "...")
            yield self.markdown_widget

    def _render_header(self) -> Text:
        header = Text()
        if self.message.role == Role.USER:
            header.append("👤 You", style="bold #89b4fa")
        else:
            header.append("🤖 CodeIq", style="bold #a6e3a1")
            if self.model_name:
                header.append(f" ({self.model_name})", style="dim #a6e3a1")

        if self.message.timestamp:
            time_part = self.message.timestamp.split("T")[-1][:8]
            header.append(f"  {time_part}", style="dim #6c7086")

        return header

    def _render_thought(self) -> Text:
        t = Text()
        t.append("💭 Thinking:\n", style="italic cyan")
        t.append(self.message.thought or "", style="dim #a6adc8")
        return t

    def append_text(self, text_delta: str) -> None:
        self.content_text += text_delta
        self.message.content = self.content_text
        self.markdown_widget.update(self.content_text)

    def set_content(self, full_text: str) -> None:
        self.content_text = full_text
        self.message.content = full_text
        self.markdown_widget.update(full_text)
