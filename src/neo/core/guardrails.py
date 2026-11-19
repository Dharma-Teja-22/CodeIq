import os
import re
from pathlib import Path
from typing import Any, Dict, List, Union


class EnvGuardrail:
    """
    Guardrail to ensure sensitive environment configuration (.env files),
    API keys, credentials, and secrets are NEVER provided to LLMs or rendered on screen.
    """

    # Block direct access to .env and common secret files
    BLOCKED_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.dev",
        ".env.development",
        ".env.test",
        ".env.stage",
        ".env.staging",
        "secrets.json",
        "credentials.json",
    }

    # Provider & generic regexes
    PROVIDER_REGEX = re.compile(
        r"(?i)\b(?:Bearer|Basic)\s+[a-zA-Z0-9\-\._~\+\/]+=*|"
        r"\bAQ\.[a-zA-Z0-9_\-\.]{20,}\b|"
        r"\bAIza[0-9A-Za-z\-_]{35,}\b|"
        r"\bsk-(?:proj-|svcacct-|ant-api\d+-)?[a-zA-Z0-9_\-]{20,}\b|"
        r"\bjina_[a-zA-Z0-9_\-]{20,}\b|"
        r"\bhf_[a-zA-Z0-9]{30,}\b|"
        r"\b(?:AKIA|ASIA|AROA|AIDA)[A-Z0-9]{16}\b|"
        r"\b[sr]k_(?:live|test)_[a-zA-Z0-9]{24,}\b|"
        r"\b(?:gh[pousr]_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b|"
        r"\bxox[baprs]-[0-9a-zA-Z\-]{10,}\b"
    )

    GENERIC_REGEX = re.compile(
        r"(['\"]?\b[a-zA-Z0-9_]*(?:api_key|apikey|secret|token|password|passwd|pwd|credential|auth|key|project_name|workspace)[a-zA-Z0-9_]*\b['\"]?\s*[:=]\s*)(['\"]?)([^\s'\",;\}]{3,})\2",
        flags=re.IGNORECASE,
    )

    # Common sensitive key patterns (case-insensitive)
    SENSITIVE_PATTERNS = [
        r"key",
        r"secret",
        r"token",
        r"password",
        r"passwd",
        r"pwd",
        r"auth",
        r"credential",
        r"private",
        r"api[_-]?key",
        r"opik[_-]?",
        r"gemini[_-]?",
        r"jina[_-]?",
        r"project[_-]?name",
        r"workspace",
    ]

    @classmethod
    def is_blocked_file(cls, filepath: Union[str, Path]) -> bool:
        """
        Check if a file path or filename is a blocked secret or env file.
        """
        try:
            path = Path(filepath)
            name_lower = path.name.lower()
            if name_lower in cls.BLOCKED_FILENAMES:
                return True
            if name_lower.startswith(".env.") or name_lower.endswith(".env"):
                return True
            if name_lower in {"secrets.json", "credentials.json", "service_account.json"}:
                return True
            return False
        except Exception:
            return False

    @classmethod
    def mask_text(cls, text: str) -> str:
        """
        Mask any detected provider API keys or generic secret key=value pairs in a text string.
        Also explicitly masks any active values found in the environment/.env.
        """
        if not text:
            return ""

        # First pass: provider and generic key/value patterns
        text = cls.PROVIDER_REGEX.sub("[MASKED_PROVIDER_KEY]", text)
        text = cls.GENERIC_REGEX.sub(r"\1\2[MASKED_SECRET]\2", text)

        # Second pass: dynamic masking of known sensitive environment variable values
        try:
            from dotenv import dotenv_values
            env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
            known_secrets = set()
            if env_file.exists():
                for k, v in dotenv_values(env_file).items():
                    if v and len(str(v).strip()) >= 3:
                        known_secrets.add(str(v).strip())

            for k in [
                "GEMINI_API_KEY",
                "JINA_API_KEY",
                "OPIK_API_KEY",
                "OPIK_PROJECT_NAME",
                "OPIK_WORKSPACE",
            ]:
                v = os.environ.get(k)
                if v and len(str(v).strip()) >= 3:
                    known_secrets.add(str(v).strip())

            for secret in known_secrets:
                if secret and secret in text:
                    text = text.replace(secret, "[MASKED_SECRET]")
        except Exception:
            pass

        return text

    @classmethod
    def safe_read_file(cls, filepath: Union[str, Path], allow_env_schema: bool = True) -> str:
        """
        Reads a file safely. If it's a .env file, either blocks it completely
        or returns ONLY the variable names (keys) with values masked.
        For all other files, scrubs any accidental hardcoded keys.
        """
        path = Path(filepath).resolve()

        if cls.is_blocked_file(path):
            if not allow_env_schema:
                raise PermissionError(f"Access denied: Reading '{path.name}' is blocked by security policy.")

            # Safe mode: Strip all values after '=' so scripts/agents only see available keys
            masked_lines = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        masked_lines.append(line.rstrip())
                    elif "=" in line:
                        key, _ = line.split("=", 1)
                        masked_lines.append(f"{key.strip()}=[MASKED_ENV_VALUE]")
            return "\n".join(masked_lines)

        # For all other files, read normally and scrub any accidental hardcoded keys
        with open(path, "r", encoding="utf-8") as f:
            return cls.mask_text(f.read())

    @classmethod
    def sanitize_messages(cls, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sanitize all messages before sending to the LLM. Recursively masks
        content, tool responses, and tool call arguments to guarantee no secret is leaked.
        """
        sanitized = []
        for msg in messages:
            new_msg = dict(msg)
            # Mask content
            if "content" in new_msg and isinstance(new_msg["content"], str):
                new_msg["content"] = cls.mask_text(new_msg["content"])

            # Mask tool calls arguments if present
            if "tool_calls" in new_msg and isinstance(new_msg["tool_calls"], list):
                sanitized_tool_calls = []
                for tc in new_msg["tool_calls"]:
                    tc_dict = dict(tc) if isinstance(tc, dict) else tc
                    if isinstance(tc_dict, dict) and "function" in tc_dict and isinstance(tc_dict["function"], dict):
                        fn_dict = dict(tc_dict["function"])
                        if "arguments" in fn_dict and isinstance(fn_dict["arguments"], str):
                            fn_dict["arguments"] = cls.mask_text(fn_dict["arguments"])
                        tc_dict["function"] = fn_dict
                    sanitized_tool_calls.append(tc_dict)
                new_msg["tool_calls"] = sanitized_tool_calls

            sanitized.append(new_msg)
        return sanitized

    @classmethod
    def sanitize_env_dict(cls, env_dict: Union[Dict[str, Any], os._Environ]) -> Dict[str, str]:
        """
        Take an environment dictionary (like os.environ) and return a fully sanitized
        dictionary where all sensitive keys are masked and protected.
        """
        sanitized = {}
        for k, v in env_dict.items():
            k_lower = str(k).lower()
            if any(re.search(pat, k_lower) for pat in cls.SENSITIVE_PATTERNS):
                sanitized[k] = "[PROTECTED: SECURE GUARDRAIL ACTIVE]"
            else:
                sanitized[k] = cls.mask_text(str(v))
        return sanitized

    @classmethod
    def sanitize_for_display(cls, text: str) -> str:
        """
        Scrub any secrets or env values before rendering output to terminal screens.
        """
        return cls.mask_text(text)


# Backwards-compatibility alias
SecurityGuardrail = EnvGuardrail
