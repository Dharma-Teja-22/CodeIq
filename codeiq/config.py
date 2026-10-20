"""Configuration manager for CodeIq."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Application configuration and environment management."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.global_dir = Path.home() / ".codeiq"
        self.project_dir = self.cwd / ".codeiq"
        self.global_config_path = self.global_dir / "config.json"
        self.project_config_path = self.project_dir / "config.json"

        # Load environment variables from .env files
        self._load_env_files()

        # Default settings
        self.provider: str = os.getenv("CODEIQ_PROVIDER", "gemini")
        self.model: str = os.getenv("CODEIQ_MODEL", "gemini-2.5-flash")
        self.auto_approve: bool = os.getenv("CODEIQ_AUTO_APPROVE", "0").lower() in ("1", "true", "yes")
        self.temperature: float = 0.2
        self.max_steps: int = 30
        self.theme: str = "tokyo-night"

        # API Keys & endpoints
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

        # Load file configs (project overrides global)
        self._load_file_configs()

    def _load_env_files(self) -> None:
        """Parse local and global .env files without requiring extra dependencies."""
        env_files = [
            self.global_dir / ".env",
            self.cwd / ".env",
            self.project_dir / ".env",
        ]
        for env_path in env_files:
            if env_path.exists() and env_path.is_file():
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip("'\"")
                            if key not in os.environ:
                                os.environ[key] = val
                except Exception:
                    pass

    def _load_file_configs(self) -> None:
        for path in (self.global_config_path, self.project_config_path):
            if path.exists() and path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.apply_dict(data)
                except Exception:
                    pass

    def apply_dict(self, data: Dict[str, Any]) -> None:
        if "provider" in data:
            self.provider = data["provider"]
        if "model" in data:
            self.model = data["model"]
        if "auto_approve" in data:
            self.auto_approve = bool(data["auto_approve"])
        if "temperature" in data:
            self.temperature = float(data["temperature"])
        if "max_steps" in data:
            self.max_steps = int(data["max_steps"])
        if "gemini_api_key" in data and data["gemini_api_key"]:
            self.gemini_api_key = data["gemini_api_key"]
        if "openai_api_key" in data and data["openai_api_key"]:
            self.openai_api_key = data["openai_api_key"]
        if "openai_base_url" in data and data["openai_base_url"]:
            self.openai_base_url = data["openai_base_url"]
        if "ollama_base_url" in data and data["ollama_base_url"]:
            self.ollama_base_url = data["ollama_base_url"]

    def save_project_config(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "provider": self.provider,
            "model": self.model,
            "auto_approve": self.auto_approve,
            "temperature": self.temperature,
            "max_steps": self.max_steps,
        }
        with open(self.project_config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_api_key(self, provider: Optional[str] = None) -> str:
        prov = (provider or self.provider).lower()
        if prov in ("gemini", "google"):
            return self.gemini_api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if prov == "openai":
            return self.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if prov == "groq":
            return self.groq_api_key or os.getenv("GROQ_API_KEY", "")
        if prov == "anthropic":
            return self.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        return ""
