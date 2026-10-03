import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# API Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-8b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Database Configuration
DB_PATH = os.getenv("STRATA_MEMORY_DB", "data/strata.db")

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Validate
if not GEMINI_API_KEY:
    import warnings
    warnings.warn(
        "GEMINI_API_KEY is not set. Get one free at https://ai.google.dev/"
    )
