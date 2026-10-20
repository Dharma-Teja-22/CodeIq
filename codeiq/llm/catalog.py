"""Provider and model catalog used by the TUI and config manager."""

from __future__ import annotations

SUPPORTED_PROVIDERS = ("gemini", "openai", "anthropic", "groq", "ollama")

POPULAR_MODELS = {
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
        "o1",
    ],
    "anthropic": [
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
    ],
    "ollama": [
        "qwen2.5-coder:latest",
        "deepseek-coder-v2:latest",
        "llama3.1:latest",
        "mistral:latest",
    ],
}

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI GPT",
    "anthropic": "Anthropic Claude",
    "groq": "Groq",
    "ollama": "Ollama",
}
