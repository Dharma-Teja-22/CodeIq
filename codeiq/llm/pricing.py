"""Token pricing registry and real-time cost calculator."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ModelRate:
    prompt_rate_per_million: float
    completion_rate_per_million: float


# Current pricing per 1,000,000 tokens (USD)
MODEL_PRICING: Dict[str, ModelRate] = {
    # Google Gemini Models (Primary)
    "gemini-2.5-flash": ModelRate(0.075, 0.30),
    "gemini-2.5-pro": ModelRate(1.25, 5.00),
    "gemini-2.0-flash": ModelRate(0.10, 0.40),
    "gemini-2.0-pro": ModelRate(1.25, 5.00),
    "gemini-1.5-flash": ModelRate(0.075, 0.30),
    "gemini-1.5-pro": ModelRate(1.25, 5.00),

    # OpenAI Models
    "gpt-4o": ModelRate(2.50, 10.00),
    "gpt-4o-mini": ModelRate(0.15, 0.60),
    "o1": ModelRate(15.00, 60.00),
    "o3-mini": ModelRate(1.10, 4.40),

    # Anthropic Models
    "claude-3-7-sonnet": ModelRate(3.00, 15.00),
    "claude-3-5-sonnet": ModelRate(3.00, 15.00),
    "claude-3-5-haiku": ModelRate(0.80, 4.00),

    # Groq / OpenRouter / DeepSeek
    "deepseek-chat": ModelRate(0.14, 0.28),
    "deepseek-coder": ModelRate(0.14, 0.28),
    "llama-3.3-70b": ModelRate(0.59, 0.79),

    # Ollama / Local Models
    "ollama": ModelRate(0.0, 0.0),
    "local": ModelRate(0.0, 0.0),
}


def get_model_rate(model_name: str) -> ModelRate:
    norm_name = model_name.lower().strip()
    if "ollama" in norm_name or "local" in norm_name:
        return ModelRate(0.0, 0.0)

    for key, rate in MODEL_PRICING.items():
        if key in norm_name or norm_name in key:
            return rate

    # Default fallback
    return ModelRate(1.00, 3.00)


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate = get_model_rate(model_name)
    prompt_cost = (prompt_tokens / 1_000_000.0) * rate.prompt_rate_per_million
    completion_cost = (completion_tokens / 1_000_000.0) * rate.completion_rate_per_million
    return round(prompt_cost + completion_cost, 6)


def estimate_tokens(text: str) -> int:
    """Fast approximation of token count (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
