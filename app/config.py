import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
DB_PATH = os.getenv("STRATA_MEMORY_DB", str(ROOT_DIR / "data" / "strata.db"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Comma-separated origins. Keep * for the default single-site deployment.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

if not GEMINI_API_KEY:
    import warnings

    warnings.warn(
        "GEMINI_API_KEY is not set. Configure it in the environment or Render dashboard.",
        RuntimeWarning,
        stacklevel=2,
    )
