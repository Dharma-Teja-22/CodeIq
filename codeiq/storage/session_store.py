"""Local JSON session persistence for CodeIq."""

from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
from typing import List, Optional
import uuid

from ..models import ChatMessage, Role, Session, TokenUsage


class SessionStore:
    """Manages saving, loading, listing, and resuming sessions in local JSON files."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        # Project-level sessions take priority; fallback to user home directory
        self.sessions_dir = self.cwd / ".codeiq" / "sessions"
        self.global_sessions_dir = Path.home() / ".codeiq" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.global_sessions_dir.mkdir(parents=True, exist_ok=True)

    def _generate_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rand_suffix = uuid.uuid4().hex[:6]
        return f"ses_{timestamp}_{rand_suffix}"

    def create_session(
        self,
        cwd: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        provider: str = "gemini",
        title: str = "New Coding Session",
    ) -> Session:
        session_id = self._generate_id()
        session = Session(
            id=session_id,
            cwd=str(self.cwd if cwd is None else Path(cwd).resolve()),
            title=title,
            model=model,
            provider=provider,
            messages=[],
            total_tokens=TokenUsage(),
        )
        self.save_session(session)
        return session

    def _get_path(self, session_id: str) -> Path:
        local_path = self.sessions_dir / f"{session_id}.json"
        if local_path.exists():
            return local_path
        global_path = self.global_sessions_dir / f"{session_id}.json"
        if global_path.exists():
            return global_path
        return local_path

    def save_session(self, session: Session) -> Path:
        session.updated_at = datetime.now().isoformat()
        path = self.sessions_dir / f"{session.id}.json"
        temp_path = self.sessions_dir / f"{session.id}.json.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        temp_path.replace(path)
        return path

    def load_session(self, session_id: str) -> Optional[Session]:
        path = self._get_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except Exception:
            return None

    def list_sessions(self) -> List[dict]:
        """Lists metadata for all stored sessions, sorted newest first."""
        sessions = []
        seen_ids = set()

        for sdir in (self.sessions_dir, self.global_sessions_dir):
            if not sdir.exists():
                continue
            for file_path in sdir.glob("*.json"):
                if file_path.stem in seen_ids:
                    continue
                seen_ids.add(file_path.stem)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sessions.append({
                        "id": data.get("id", file_path.stem),
                        "title": data.get("title", "Untitled Session"),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "model": data.get("model", ""),
                        "provider": data.get("provider", ""),
                        "cwd": data.get("cwd", ""),
                        "message_count": len(data.get("messages", [])),
                        "total_tokens": data.get("total_tokens", {}).get("total_tokens", 0),
                        "cost": data.get("total_tokens", {}).get("estimated_cost", 0.0),
                        "path": str(file_path),
                    })
                except Exception:
                    continue

        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        path = self._get_path(session_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False

    def export_markdown(self, session: Session, dest_path: Optional[Path] = None) -> Path:
        if dest_path is None:
            dest_path = self.cwd / f"session_{session.id}.md"

        lines = [
            f"# CodeIq Session: {session.title}",
            f"- **Session ID:** `{session.id}`",
            f"- **Created:** {session.created_at}",
            f"- **Model:** {session.model} ({session.provider})",
            f"- **Total Tokens:** {session.total_tokens.total_tokens} (${session.total_tokens.estimated_cost:.4f})",
            f"- **Workspace:** `{session.cwd}`",
            "",
            "---",
            "",
        ]

        for msg in session.messages:
            role_header = f"### {msg.role.value.capitalize()}"
            lines.append(role_header)
            lines.append(f"*{msg.timestamp}*\n")
            if msg.content:
                lines.append(msg.content)
                lines.append("")
            for tc in msg.tool_calls:
                lines.append(f"**Tool Call:** `{tc.name}`")
                lines.append(f"```json\n{json.dumps(tc.args, indent=2)}\n```")
                if tc.result:
                    lines.append(f"**Result:**\n```\n{tc.result}\n```")
                lines.append("")
            lines.append("---")
            lines.append("")

        dest_path.write_text("\n".join(lines), encoding="utf-8")
        return dest_path
