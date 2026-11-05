import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def get_available_models(provider: str = DEFAULT_PROVIDER) -> List[str]:
    """
    Retrieve available models from JSON configuration for a provider.

    Args:
        provider (str): Provider name. Defaults to DEFAULT_PROVIDER ("gemini").

    Returns:
        List[str]: List of model name identifiers.
    """
    try:
        config = load_config()
        models = config.get("providers", {}).get(provider, {}).get("models", [])
        return list(models) if isinstance(models, list) else []
    except Exception:
        return []


def add_model_to_config(model_name: str, provider: str = DEFAULT_PROVIDER) -> bool:
    """
    Add a new model to the provider in the JSON configuration.

    Args:
        model_name (str): The model name string to register.
        provider (str): The provider name. Defaults to DEFAULT_PROVIDER ("gemini").

    Returns:
        bool: True if model was added, False if it already existed or on error.
    """
    try:
        config = load_config()
        provider_data = config.setdefault("providers", {}).setdefault(provider, {})
        models = provider_data.setdefault("models", [])
        if model_name in models:
            return False
        models.append(model_name)
        save_config(config)
        return True
    except Exception:
        return False


def get_selected_model(provider: str = DEFAULT_PROVIDER) -> str:
    """
    Retrieve currently selected model ID based on environment or configuration priority.

    Args:
        provider (str): The provider name. Defaults to DEFAULT_PROVIDER ("gemini").

    Returns:
        str: Selected model identifier or empty string if none configured.
    """
    try:
        available_models = get_available_models(provider)

        # 1. Environment variable for the current terminal session
        env_model = os.getenv("MODEL")
        if env_model:
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
    except Exception:
        return ""


def set_selected_model(model_name: str, provider: str = DEFAULT_PROVIDER) -> None:
    """
    Save selected model to config file under Default_model outside providers.

    Args:
        model_name (str): Model name to designate as default.
        provider (str): Target provider name. Defaults to DEFAULT_PROVIDER ("gemini").

    Returns:
        None
    """
    try:
        config = load_config()
        config["Default_model"] = model_name
        # Remove deprecated "model" key if present
        config.pop("model", None)
        save_config(config)
    except Exception as e:
        print(f"Error setting selected model: {e}")
