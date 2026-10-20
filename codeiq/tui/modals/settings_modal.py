"""Settings modal for configuring LLM providers, models, and API keys."""

from __future__ import annotations
from typing import Dict, Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from ...config import Config
from ...llm.catalog import PROVIDER_LABELS, SUPPORTED_PROVIDERS


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
        self.provider_models = {
            provider: self.config.get_models_for_provider(provider)
            for provider in SUPPORTED_PROVIDERS
        }

    @staticmethod
    def _to_select_options(provider: str, values: list[str]) -> list[tuple[str, str]]:
        return [(f"{provider} | {name}", name) for name in values]

    def _current_provider(self) -> str:
        provider = str(self.query_one("#select-provider", Select).value)
        if provider in SUPPORTED_PROVIDERS:
            return provider
        return "gemini"

    def _refresh_model_select(self, provider: str, selected_model: Optional[str] = None) -> None:
        model_select = self.query_one("#select-model", Select)
        models = self.provider_models.get(provider, [])
        options = self._to_select_options(provider, models)
        model_select.set_options(options)

        target_model = selected_model or self.current_model
        if target_model in models:
            model_select.value = target_model
        elif models:
            model_select.value = models[0]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Static("⚙️  CodeIq Settings & LLM Configuration", id="settings-title")

            with VerticalScroll():
                # Provider Selection
                yield Label("LLM Provider:", classes="form-label")
                provider_options = [
                    ("Google Gemini", "gemini"),
                    ("OpenAI GPT", "openai"),
                    ("Anthropic Claude", "anthropic"),
                    ("Groq", "groq"),
                    ("Ollama", "ollama"),
                ]
                yield Select(
                    options=provider_options,
                    value=self.current_provider,
                    id="select-provider",
                )

                # Model selection and add custom model
                yield Label("Model:", classes="form-label")
                initial_provider = self.current_provider if self.current_provider in SUPPORTED_PROVIDERS else "gemini"
                initial_models = self.provider_models.get(initial_provider, [])
                fallback_model = self.current_model if self.current_model else (initial_models[0] if initial_models else "")
                if fallback_model and fallback_model not in self.provider_models[initial_provider]:
                    self.provider_models[initial_provider] = [fallback_model] + self.provider_models[initial_provider]

                yield Select(
                    options=self._to_select_options(initial_provider, self.provider_models[initial_provider]),
                    value=fallback_model,
                    id="select-model",
                )

                with Horizontal(classes="form-group"):
                    yield Input(
                        placeholder="Add custom model for provider",
                        id="input-custom-model",
                        classes="form-input",
                    )
                    yield Button("Add Model", id="btn-add-model", classes="btn-cancel")

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

                # OpenAI API Key
                yield Label("OpenAI API Key:", classes="form-label")
                openai_masked = self.config.get_api_key("openai")
                yield Input(
                    value=openai_masked,
                    placeholder="sk-...",
                    password=True,
                    id="input-openai-key",
                    classes="form-input",
                )

                # Anthropic API Key
                yield Label("Anthropic API Key:", classes="form-label")
                anthropic_masked = self.config.get_api_key("anthropic")
                yield Input(
                    value=anthropic_masked,
                    placeholder="sk-ant-...",
                    password=True,
                    id="input-anthropic-key",
                    classes="form-input",
                )

                yield Label("Configured Providers:", classes="form-label")
                configured_labels = []
                for provider in ("gemini", "openai", "anthropic"):
                    has_key = bool(self.config.get_api_key(provider))
                    configured_labels.append(f"{PROVIDER_LABELS[provider]}: {'configured' if has_key else 'missing key'}")
                yield Static("  |  ".join(configured_labels), classes="form-input")

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
            self._refresh_model_select(prov)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-add-model":
            provider_val = self._current_provider()
            model_name = self.query_one("#input-custom-model", Input).value.strip()
            if not model_name:
                return

            models = self.provider_models.get(provider_val, [])
            if model_name not in models:
                models.insert(0, model_name)
            self.provider_models[provider_val] = models
            self._refresh_model_select(provider_val, selected_model=model_name)
            self.query_one("#input-custom-model", Input).value = ""
        elif event.button.id == "btn-save":
            provider_val = str(self.query_one("#select-provider", Select).value)
            model_val = str(self.query_one("#select-model", Select).value)
            if not model_val:
                model_candidates = self.provider_models.get(provider_val, [])
                model_val = model_candidates[0] if model_candidates else self.current_model

            gemini_key = self.query_one("#input-gemini-key", Input).value.strip()
            openai_key = self.query_one("#input-openai-key", Input).value.strip()
            anthropic_key = self.query_one("#input-anthropic-key", Input).value.strip()
            auto_approve_val = self.query_one("#switch-auto-approve", Switch).value

            result = {
                "provider": provider_val,
                "model": model_val,
                "gemini_api_key": gemini_key,
                "openai_api_key": openai_key,
                "anthropic_api_key": anthropic_key,
                "provider_models": self.provider_models,
                "auto_approve": auto_approve_val,
            }
            self.dismiss(result)
