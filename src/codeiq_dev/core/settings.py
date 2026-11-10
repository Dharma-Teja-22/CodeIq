from codeiq_dev.core.config import load_config, DEFAULT_PROVIDER
import os
from pathlib import Path
from dotenv import load_dotenv

# Search and load .env file from the package directory or current working directory
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

config = load_config()
class Settings:
    # API Keys & URLs
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_BASE_URL = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    # Active Model Override from environment
    MODEL = os.getenv("MODEL") or config.get("default_model") or config.get("providers", {}).get(DEFAULT_PROVIDER, {}).get("default")
    JINA_API_KEY = os.getenv("JINA_API_KEY")
    
    # Small Model for title Gen
    SMALL_MODEL = config.get("small_model")

# Settings instance
settings = Settings()