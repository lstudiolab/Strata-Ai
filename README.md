# Strata AI

Gemini-powered AI assistant with an internal intelligence layer, first-question session context, SQLite conversation memory, Google Search grounding, and a ChatGPT-style web interface.

Set GEMINI_API_KEY in the deployment environment. Never commit the API key.

Run: `pip install -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000`.
