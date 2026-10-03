# Strata AI

Strata AI is a general-purpose AI assistant powered by a Gemini API key. It includes:
- FastAPI backend
- SQLite conversation memory
- streaming chat responses
- session-aware memory
- deploy-ready Render configuration

## Local development

1. Copy `.env.example` to `.env`
2. Add your Gemini API key
3. Install dependencies:
   pip install -r requirements.txt
4. Run the app:
   uvicorn app.main:app --host 0.0.0.0 --port 8000

## Environment variables

Required:
- `GEMINI_API_KEY`

Optional:
- `GEMINI_MODEL` (default: `gemini-2.5-flash`)
- `STRATA_MEMORY_DB` (default: `data/strata.db`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)

## Render deployment

Use the provided `render.yaml` and set the environment variables in the Render dashboard:
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `PORT=8000`

Important: never commit your real API key to Git. Use environment variables only.
