import os
from pathlib import Path
from dotenv import load_dotenv

# Search and load .env file from the package directory or current working directory
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

# API Keys & URLs
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)

# Active Model Override from environment
MODEL_ENV = os.getenv("MODEL")
JINA_API_KEY = os.getenv("JINA_API_KEY")
