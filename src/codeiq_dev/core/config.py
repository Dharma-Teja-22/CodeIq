import json
from pathlib import Path
from typing import Any, Dict

# The configuration file path is now user-specific based on the requirement.
# Target: C:\Users\<username>\.codeiq\models\.codeiq_config.json
CONFIG_DIR = Path.home() / ".codeiq" / "models"
CONFIG_FILE = CONFIG_DIR / ".codeiq_config.json"
DEFAULT_PROVIDER = "gemini"

def _ensure_config_dir() -> None:
    """Ensure the target configuration directory exists."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def load_config() -> Dict[str, Any]:
    """
    Load configuration from the user-specific .codeiq_config.json.

    Args:
        None

    Returns:
        Dict[str, Any]: Parsed configuration dictionary or default configuration structure.
    """
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {"providers": {DEFAULT_PROVIDER: {"models": [], "default": None}}}

def save_config(data: Dict[str, Any]) -> None:
    """
    Save configuration dictionary to the user-specific .codeiq_config.json.

    Args:
        data (Dict[str, Any]): Configuration dictionary to persist.

    Returns:
        None
    """
    _ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving config to {CONFIG_FILE}: {e}")
