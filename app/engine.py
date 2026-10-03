import logging
from google import genai
from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized successfully")
    except Exception as exc:
        logger.warning(f"Gemini initialization failed: {exc}")
else:
    logger.warning("GEMINI_API_KEY is not set. The app will reject chat requests until it is configured.")
