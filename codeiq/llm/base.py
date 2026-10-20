"""Abstract base interface for LLM providers."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..models import ChatMessage, ToolCall, TokenUsage


@dataclass
class StreamChunk:
    text_delta: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
    thought_delta: str = ""
    finish_reason: Optional[str] = None


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers in CodeIq."""

    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.extra_config = kwargs

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Streams AI responses, yielding text deltas and tool call proposals."""
        pass
