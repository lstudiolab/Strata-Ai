# Strata AI

A Gemini-powered AI assistant with a persistent intelligence layer, web-aware retrieval, session memory, and a ChatGPT-style web interface.

## Run

Set `GEMINI_API_KEY` in the environment. Never commit API keys.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.
