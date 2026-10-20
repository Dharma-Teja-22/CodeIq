"""Settings modal for configuring LLM providers, models, and API keys."""

from __future__ import annotations
from typing import Dict, Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from ...config import Config
from ...llm.factory import POPULAR_MODELS


class SettingsModal(ModalScreen[Optional[Dict[str, str]]]):
    """Modal dialog for updating model, provider, API keys, and preferences."""

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #settings-box {
        width: 76;
        max-width: 90%;
        max-height: 85%;
        background: #1e1e2e;
        border: thick #89b4fa;
        padding: 1 2;
    }

    #settings-title {
        color: #89b4fa;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid #313244;
        padding-bottom: 1;
    }

    .form-group {
        margin-bottom: 1;
    }

    .form-label {
        color: #89dceb;
        text-style: bold;
        margin-bottom: 0;
    }

    .form-input {
        background: #11111b;
        color: #cdd6f4;
        border: solid #45475a;
        margin-top: 0;
    }

    #settings-buttons {
        layout: horizontal;
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    .btn-save {
        background: #a6e3a1;
        color: #11111b;
        text-style: bold;
        margin-left: 1;
    }

    .btn-cancel {
        background: #313244;
        color: #cdd6f4;
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self, config: Config, current_model: str, current_provider: str, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.current_model = current_model
        self.current_provider = current_provider

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Static("⚙️  CodeIq Settings & LLM Configuration", id="settings-title")

            with VerticalScroll():
                # Provider Selection
                yield Label("LLM Provider:", classes="form-label")
                provider_options = [
                    ("Google Gemini (Primary / Recommended)", "gemini"),
                    ("OpenAI (GPT-4o, o3-mini)", "openai"),
                    ("Groq (High Speed Llama 3.3)", "groq"),
                    ("Ollama (Local Offline LLM)", "ollama"),
                ]
                yield Select(
                    options=provider_options,
                    value=self.current_provider,
                    id="select-provider",
                )

                # Model Name Input
                yield Label("Model Name:", classes="form-label")
                yield Input(
                    value=self.current_model,
                    placeholder="e.g. gemini-2.5-flash, gpt-4o, llama-3.3-70b",
                    id="input-model",
                    classes="form-input",
                )

                # Gemini API Key Input
                yield Label("Gemini API Key:", classes="form-label")
                gemini_masked = self.config.get_api_key("gemini")
                yield Input(
                    value=gemini_masked,
                    placeholder="AIzaSy...",
                    password=True,
                    id="input-gemini-key",
                    classes="form-input",
                )

                # OpenAI / Compatible API Key Input
                yield Label("OpenAI / Groq API Key:", classes="form-label")
                openai_masked = self.config.get_api_key("openai")
                yield Input(
                    value=openai_masked,
                    placeholder="sk-...",
                    password=True,
                    id="input-openai-key",
                    classes="form-input",
                )

                # Auto-approve Switch
                with Horizontal(classes="form-group"):
                    yield Label("Auto-approve safe operations without prompting: ", classes="form-label")
                    yield Switch(value=self.config.auto_approve, id="switch-auto-approve")

            with Horizontal(id="settings-buttons"):
                yield Button("Cancel (Esc)", id="btn-cancel", classes="btn-cancel")
                yield Button("Save & Apply", id="btn-save", classes="btn-save")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "select-provider":
            prov = str(event.value)
            # Suggest default model for selected provider
            model_input = self.query_one("#input-model", Input)
            if prov == "gemini":
                model_input.value = "gemini-2.5-flash"
            elif prov == "openai":
                model_input.value = "gpt-4o"
            elif prov == "groq":
                model_input.value = "llama-3.3-70b-versatile"
            elif prov == "ollama":
                model_input.value = "qwen2.5-coder:latest"

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-save":
            provider_val = str(self.query_one("#select-provider", Select).value)
            model_val = self.query_one("#input-model", Input).value.strip() or "gemini-2.5-flash"
            gemini_key = self.query_one("#input-gemini-key", Input).value.strip()
            openai_key = self.query_one("#input-openai-key", Input).value.strip()
            auto_approve_val = self.query_one("#switch-auto-approve", Switch).value

            result = {
                "provider": provider_val,
                "model": model_val,
                "gemini_api_key": gemini_key,
                "openai_api_key": openai_key,
                "auto_approve": auto_approve_val,
            }
            self.dismiss(result)
