"""Settings modal for configuring providers, models, and API keys."""

from __future__ import annotations

from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from ...config import Config


MASKED_API_KEY = "xxx"


class SettingsModal(ModalScreen[Optional[Dict[str, Any]]]):
    """Modal dialog for model/provider/api-key management."""

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.78);
    }

    #settings-box {
        width: 88%;
        max-width: 104;
        min-width: 72;
        height: 86%;
        max-height: 92%;
        min-height: 22;
        background: #1b1f2a;
        border: round #7aa2f7;
        padding: 1 2;
        layout: vertical;
    }

    #settings-scroll {
        height: 1fr;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-color: #7aa2f7 #141824;
        scrollbar-color-hover: #9ece6a #141824;
        scrollbar-color-active: #e0af68 #141824;
        scrollbar-size-vertical: 2;
        padding-right: 1;
        min-height: 8;
    }

    #settings-title {
        color: #7aa2f7;
        text-style: bold;
        margin: 0 1 1 1;
        border-bottom: solid #2a3144;
        padding: 0 0 1 0;
    }

    .section-title {
        color: #73daca;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    #config-grid {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }

    .config-col {
        width: 1fr;
        background: #171c2a;
        border: round #2a3144;
        padding: 1;
        margin-right: 1;
    }

    .config-col.last { margin-right: 0; }

    .column-title {
        color: #7aa2f7;
        text-style: bold;
        margin-bottom: 1;
    }

    .form-label {
        color: #a9b1d6;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    .helper-text {
        color: #6f7a9b;
        margin-top: 0;
        margin-bottom: 0;
    }

    .form-input {
        background: #111522;
        color: #cdd6f4;
        border: solid #394260;
        margin-top: 0;
        min-height: 3;
    }

    .form-row {
        height: auto;
        align-vertical: middle;
        margin-top: 0;
    }

    .form-row Select,
    .form-row Input {
        width: 1fr;
    }

    .mini-btn {
        width: 5;
        min-width: 5;
        height: 3;
        margin-left: 1;
        background: #2b3247;
        color: #d6def7;
    }

    #settings-buttons {
        dock: bottom;
        layout: horizontal;
        height: auto;
        min-height: 3;
        align-horizontal: right;
        margin: 1 1 0 1;
        border-top: solid #2a3144;
        padding-top: 1;
        background: #1b1f2a;
    }

    .btn-save {
        background: #9ece6a;
        color: #111522;
        text-style: bold;
        width: 12;
        min-width: 10;
        height: 3;
        margin-left: 1;
    }

    .btn-cancel {
        background: #2b3247;
        color: #d6def7;
        width: 10;
        min-width: 8;
        height: 3;
        margin-left: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def __init__(self, config: Config, current_model: str, current_provider: str, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.current_model = current_model
        self.current_provider = current_provider

        self.providers = self.config.get_all_providers()
        self.provider_models = {
            provider: self.config.get_models_for_provider(provider)
            for provider in self.providers
        }
        self.provider_api_keys = {
            provider: self.config.get_api_key(provider)
            for provider in self.providers
        }

        self.reveal_api_key = False
        self.provider_filter = ""
        self.model_filter = ""

    @staticmethod
    def _to_select_options(provider: str, values: list[str]) -> list[tuple[str, str]]:
        return [(f"{provider} | {name}", name) for name in values]

    def _provider_options(self, query: str = "") -> list[tuple[str, str]]:
        q = query.strip().lower()
        options = []
        for provider in self.providers:
            label = self.config.get_provider_label(provider)
            if not q or q in provider or q in label.lower():
                options.append((label, provider))
        return options

    def _current_provider(self) -> str:
        provider = str(self.query_one("#select-provider", Select).value)
        if provider in self.providers:
            return provider
        return self.providers[0] if self.providers else "gemini"

    def _refresh_provider_select(self, selected_provider: Optional[str] = None, query: Optional[str] = None) -> None:
        if query is not None:
            self.provider_filter = query

        options = self._provider_options(self.provider_filter)
        select = self.query_one("#select-provider", Select)
        select.set_options(options)

        values = [value for _, value in options]
        if selected_provider and selected_provider in values:
            select.value = selected_provider
        elif values:
            select.value = values[0]

    def _refresh_model_select(self, provider: str, selected_model: Optional[str] = None, query: Optional[str] = None) -> None:
        if query is not None:
            self.model_filter = query

        models = self.provider_models.get(provider, [])
        q = self.model_filter.strip().lower()
        filtered = [m for m in models if not q or q in m.lower()]

        if not filtered and selected_model:
            filtered = [selected_model]

        select = self.query_one("#select-model", Select)
        select.set_options(self._to_select_options(provider, filtered))

        target = selected_model or self.current_model
        if target in filtered:
            select.value = target
        elif filtered:
            select.value = filtered[0]

    def _refresh_api_key_input(self, provider: str) -> None:
        key_input = self.query_one("#input-provider-key", Input)
        key = self.provider_api_keys.get(provider, "")
        key_input.password = False
        key_input.value = key if self.reveal_api_key else (MASKED_API_KEY if key else "")

    def _store_current_provider_key_from_input(self) -> None:
        provider = self._current_provider()
        key_input = self.query_one("#input-provider-key", Input)
        raw = key_input.value.strip()

        if self.reveal_api_key:
            self.provider_api_keys[provider] = raw
            return

        existing = self.provider_api_keys.get(provider, "")
        if (raw == "" or raw == MASKED_API_KEY) and existing:
            return
        self.provider_api_keys[provider] = raw

    def _refresh_provider_key_summary(self) -> None:
        widget = self.query_one("#providers-key-status", Static)
        items = []
        for provider in self.providers:
            state = "configured" if self.provider_api_keys.get(provider) else "missing key"
            items.append(f"{self.config.get_provider_label(provider)}: {state}")
        widget.update("  |  ".join(items) if items else "No providers configured")

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Static("⚙ CodeIq Settings & LLM Configuration", id="settings-title")

            with VerticalScroll(id="settings-scroll"):
                initial_provider = self.current_provider if self.current_provider in self.providers else (self.providers[0] if self.providers else "gemini")
                initial_models = self.provider_models.get(initial_provider, [])
                fallback_model = self.current_model if self.current_model else (initial_models[0] if initial_models else "")
                if fallback_model and fallback_model not in self.provider_models.get(initial_provider, []):
                    self.provider_models[initial_provider] = [fallback_model] + self.provider_models.get(initial_provider, [])

                with Horizontal(id="config-grid"):
                    with Vertical(classes="config-col"):
                        yield Static("1. Providers", classes="column-title")
                        yield Label("LLM Provider", classes="form-label")
                        with Horizontal(classes="form-row"):
                            yield Input(
                                placeholder="Search provider",
                                id="provider-search",
                                classes="form-input",
                            )
                            yield Button("+", id="btn-add-provider", classes="mini-btn")

                        yield Select(
                            options=self._provider_options(),
                            value=self.current_provider,
                            id="select-provider",
                        )

                    with Vertical(classes="config-col last"):
                        yield Static("2. Models", classes="column-title")
                        yield Label("Provider Model", classes="form-label")
                        with Horizontal(classes="form-row"):
                            yield Input(
                                placeholder="Search model",
                                id="model-search",
                                classes="form-input",
                            )
                            yield Button("+", id="btn-add-model", classes="mini-btn")

                        yield Select(
                            options=self._to_select_options(initial_provider, self.provider_models[initial_provider]),
                            value=fallback_model,
                            id="select-model",
                        )

                yield Static("3. Key", classes="column-title")
                yield Label("Provider API Key", classes="form-label")
                with Horizontal(classes="form-row"):
                    yield Input(
                        value="",
                        placeholder="API key",
                        id="input-provider-key",
                        classes="form-input",
                    )
                    yield Button("Eye", id="btn-toggle-api-visibility", classes="mini-btn")

                yield Label("Status", classes="form-label")
                yield Static("", id="providers-key-status", classes="form-input")

                yield Static("Tip: Use + to add a provider or model when it does not exist.", classes="helper-text")

            with Horizontal(id="settings-buttons"):
                yield Button("Cancel", id="btn-cancel", classes="btn-cancel")
                yield Button("Save", id="btn-save", classes="btn-save")

    def on_mount(self) -> None:
        selected = self.current_provider if self.current_provider in self.providers else (self.providers[0] if self.providers else "gemini")
        self._refresh_provider_select(selected_provider=selected)
        self._refresh_model_select(selected)
        self._refresh_api_key_input(selected)
        self._refresh_provider_key_summary()

        scroll = self.query_one("#settings-scroll", VerticalScroll)
        scroll.show_vertical_scrollbar = True

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "select-provider":
            self._store_current_provider_key_from_input()
            provider = str(event.value)
            self._refresh_model_select(provider, query=self.model_filter)
            self._refresh_api_key_input(provider)
            self._refresh_provider_key_summary()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "provider-search":
            current = self._current_provider()
            self._refresh_provider_select(selected_provider=current, query=event.value)
        elif event.input.id == "model-search":
            provider = self._current_provider()
            selected = str(self.query_one("#select-model", Select).value or "")
            self._refresh_model_select(provider, selected_model=selected, query=event.value)

    def on_input_focused(self, event: Input.Focused) -> None:
        if event.input.id == "input-provider-key" and not self.reveal_api_key and event.input.value == MASKED_API_KEY:
            event.input.value = ""

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
            return

        if event.button.id == "btn-add-provider":
            provider_name = self.query_one("#provider-search", Input).value.strip().lower()
            if not provider_name:
                return

            self.config.add_provider(provider_name)
            self.providers = self.config.get_all_providers()
            if provider_name not in self.provider_models:
                self.provider_models[provider_name] = self.config.get_models_for_provider(provider_name)
            if provider_name not in self.provider_api_keys:
                self.provider_api_keys[provider_name] = ""

            self.query_one("#provider-search", Input).value = ""
            self._refresh_provider_select(selected_provider=provider_name, query="")
            self._refresh_model_select(provider_name, query="")
            self._refresh_api_key_input(provider_name)
            self._refresh_provider_key_summary()
            return

        if event.button.id == "btn-add-model":
            provider = self._current_provider()
            model_name = self.query_one("#model-search", Input).value.strip()
            if not model_name:
                return

            models = self.provider_models.get(provider, [])
            if model_name not in models:
                models.insert(0, model_name)
            self.provider_models[provider] = models

            self.query_one("#model-search", Input).value = ""
            self._refresh_model_select(provider, selected_model=model_name, query="")
            return

        if event.button.id == "btn-toggle-api-visibility":
            self._store_current_provider_key_from_input()
            self.reveal_api_key = not self.reveal_api_key
            toggle_btn = self.query_one("#btn-toggle-api-visibility", Button)
            toggle_btn.label = "Hide" if self.reveal_api_key else "Eye"
            self._refresh_api_key_input(self._current_provider())
            return

        if event.button.id == "btn-save":
            self._store_current_provider_key_from_input()

            provider_val = str(self.query_one("#select-provider", Select).value)
            model_val = str(self.query_one("#select-model", Select).value)
            if not model_val:
                provider_models = self.provider_models.get(provider_val, [])
                model_val = provider_models[0] if provider_models else self.current_model

            result = {
                "provider": provider_val,
                "model": model_val,
                "providers": self.providers,
                "provider_models": self.provider_models,
                "provider_api_keys": self.provider_api_keys,
                "gemini_api_key": self.provider_api_keys.get("gemini", ""),
                "openai_api_key": self.provider_api_keys.get("openai", ""),
                "anthropic_api_key": self.provider_api_keys.get("anthropic", ""),
                "groq_api_key": self.provider_api_keys.get("groq", ""),
                "auto_approve": self.config.auto_approve,
            }
            self.dismiss(result)
