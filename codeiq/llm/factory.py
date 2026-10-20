"""Factory for instantiating LLM providers."""

from __future__ import annotations
from typing import Optional

from ..config import Config
from .base import BaseLLMProvider
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .openai_provider import OpenAICompatibleProvider


def create_llm_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
    config: Optional[Config] = None,
) -> BaseLLMProvider:
    cfg = config or Config()
    provider = (provider_name or cfg.provider or "gemini").lower().strip()
    model = model_name or cfg.model or "gemini-2.5-flash"

    if provider in ("gemini", "google"):
        api_key = cfg.get_api_key("gemini")
        return GeminiProvider(api_key=api_key, model=model)

    elif provider == "openai":
        api_key = cfg.get_api_key("openai")
        return OpenAICompatibleProvider(
            api_key=api_key,
            model=model,
            base_url=cfg.openai_base_url or "https://api.openai.com/v1",
        )

    elif provider == "anthropic":
        api_key = cfg.get_api_key("anthropic")
        return AnthropicProvider(
            api_key=api_key,
            model=model,
        )

    elif provider == "groq":
        api_key = cfg.get_api_key("groq")
        return OpenAICompatibleProvider(
            api_key=api_key,
            model=model,
            base_url="https://api.groq.com/openai/v1",
        )

    elif provider in ("ollama", "local"):
        return OpenAICompatibleProvider(
            api_key="ollama",
            model=model,
            base_url=cfg.ollama_base_url or "http://localhost:11434/v1",
        )

    else:
        # Default fallback to Gemini
        api_key = cfg.get_api_key("gemini")
        return GeminiProvider(api_key=api_key, model=model)
