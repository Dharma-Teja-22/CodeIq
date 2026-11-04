import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_FILE = Path(".codeiq_config.json")
DEFAULT_PROVIDER = "gemini"


def load_config() -> Dict[str, Any]:
    """Load configuration directly from .codeiq_config.json."""
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
    """Save configuration dictionary to .codeiq_config.json."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_available_models(provider: str = DEFAULT_PROVIDER) -> List[str]:
    """Retrieve available models from JSON configuration for a provider."""
    config = load_config()
    models = config.get("providers", {}).get(provider, {}).get("models", [])
    return list(models) if isinstance(models, list) else []


def add_model_to_config(model_name: str, provider: str = DEFAULT_PROVIDER) -> bool:
    """Add a new model to the provider in the JSON configuration."""
    config = load_config()
    provider_data = config.setdefault("providers", {}).setdefault(provider, {})
    models = provider_data.setdefault("models", [])
    if model_name in models:
        return False
    models.append(model_name)
    save_config(config)
    return True


def get_selected_model(provider: str = DEFAULT_PROVIDER) -> str:
    """
    Retrieve currently selected model ID.
    Priority:
    1. Session environment variable `MODEL` (e.g. set MODEL=... or $env:MODEL=...)
    2. Active `Default_model` outside providers in config file (`.codeiq_config.json`)
    3. Provider's own default (`providers.<provider>.default`)
    4. Fallback to first available model from JSON config
    """
    available_models = get_available_models(provider)

    # 1. Environment variable for the current terminal session
    env_model = os.getenv("MODEL")
    if env_model:
        # Strip potential surrounding quotes from shells (e.g. 'model' or "model")
        cleaned_env_model = env_model.strip().strip("'").strip('"')
        if cleaned_env_model in available_models:
            return cleaned_env_model

    # 2. Persisted active model (Default_model / model) outside of providers
    config = load_config()
    active_model = config.get("Default_model") or config.get("model")
    if active_model and active_model in available_models:
        return active_model

    # 3. Provider default model
    provider_default = config.get("providers", {}).get(provider, {}).get("default")
    if provider_default and provider_default in available_models:
        return provider_default

    # 4. Fallback to first available model from JSON config
    if available_models:
        return available_models[0]
    return ""


def set_selected_model(model_name: str, provider: str = DEFAULT_PROVIDER) -> None:
    """Save selected model to config file under Default_model outside providers."""
    config = load_config()
    config["Default_model"] = model_name
    # Remove deprecated "model" key if present
    config.pop("model", None)
    save_config(config)
