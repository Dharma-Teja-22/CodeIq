import json
from pathlib import Path
from typing import Any, Dict

CONFIG_FILE = Path(".codeiq_config.json")
DEFAULT_PROVIDER = "gemini"

def load_config() -> Dict[str, Any]:
    """
    Load configuration directly from .codeiq_config.json.

    Args:
        None

    Returns:
        Dict[str, Any]: Parsed configuration dictionary or default configuration structure.
    """
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"providers": {DEFAULT_PROVIDER: {"models": [], "default": None}}}

def save_config(data: Dict[str, Any]) -> None:
    """
    Save configuration dictionary to .codeiq_config.json.

    Args:
        data (Dict[str, Any]): Configuration dictionary to persist.

    Returns:
        None
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving config to {CONFIG_FILE}: {e}")
