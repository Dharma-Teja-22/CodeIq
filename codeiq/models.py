"""Core data models for CodeIq."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolState(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    state: ToolState = ToolState.PENDING_APPROVAL
    result: Optional[str] = None
    error: Optional[str] = None
    diff_preview: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "state": self.state.value,
            "result": self.result,
            "error": self.error,
            "diff_preview": self.diff_preview,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolCall:
        return cls(
            id=data.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            name=data["name"],
            args=data.get("args", {}),
            state=ToolState(data.get("state", "pending_approval")),
            result=data.get("result"),
            error=data.get("error"),
            diff_preview=data.get("diff_preview"),
        )


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0

    def add(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.estimated_cost += other.estimated_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TokenUsage:
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            estimated_cost=data.get("estimated_cost", 0.0),
        )


@dataclass
class ChatMessage:
    role: Role
    content: str
    id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tool_calls: List[ToolCall] = field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
    thought: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "token_usage": self.token_usage.to_dict() if self.token_usage else None,
            "thought": self.thought,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChatMessage:
        return cls(
            id=data.get("id", f"msg_{uuid.uuid4().hex[:8]}"),
            role=Role(data["role"]),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            tool_calls=[ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])],
            token_usage=TokenUsage.from_dict(data["token_usage"]) if data.get("token_usage") else None,
            thought=data.get("thought"),
        )


@dataclass
class DiffChunk:
    filename: str
    old_content: str
    new_content: str
    diff_text: str
    additions: int = 0
    deletions: int = 0


@dataclass
class Session:
    id: str
    cwd: str
    title: str = "New Session"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    model: str = "gemini-2.5-flash"
    provider: str = "gemini"
    messages: List[ChatMessage] = field(default_factory=list)
    total_tokens: TokenUsage = field(default_factory=TokenUsage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cwd": self.cwd,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "provider": self.provider,
            "messages": [msg.to_dict() for msg in self.messages],
            "total_tokens": self.total_tokens.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Session:
        session = cls(
            id=data["id"],
            cwd=data.get("cwd", "."),
            title=data.get("title", "Session"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            model=data.get("model", "gemini-2.5-flash"),
            provider=data.get("provider", "gemini"),
            messages=[ChatMessage.from_dict(m) for m in data.get("messages", [])],
            total_tokens=TokenUsage.from_dict(data.get("total_tokens", {})),
        )
        return session
