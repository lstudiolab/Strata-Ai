import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, DB_PATH, GEMINI_API_KEY, HOST, PORT
from app.engine import client
from app.memory import Memory

logger = logging.getLogger("strata")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INSTRUCTIONS_DIR = BASE_DIR / "instructions"

app = FastAPI(title="Strata AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
mem = Memory(DB_PATH)


def get_default_instructions() -> str:
    return (
        "You are Strata, a capable general-purpose AI assistant. "
        "Be accurate, useful, direct, and transparent about uncertainty. "
        "Use available information carefully and never claim to have searched "
        "the web unless a web tool was actually used. Follow the user's request "
        "while keeping responses clear and practical."
    )


def load_instructions() -> str:
    path = INSTRUCTIONS_DIR / "strata.txt"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return get_default_instructions()


def make_messages(history, first_question: str, message: str):
    messages = []
    for role, text in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": text,
        })

    messages.append({
        "role": "user",
        "content": (
            f"Conversation anchor (the user's first question): {first_question}\n\n"
            f"User's current message: {message}"
        ),
    })
    return messages


@app.get("/", response_class=HTMLResponse)
async def home():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/models")
async def get_models():
    model_name = None
    if client is not None:
        try:
            model_name = await client.highest_priced_model()
        except Exception:
            logger.exception("Unable to resolve the Strata model")

    return {
        "models": [
            {
                "id": "strata",
                "name": "Strata 1.0",
                "model": model_name,
            }
        ]
    }


@app.get("/health")
async def health():
    resolved_model = None
    if client is not None:
        try:
            resolved_model = await client.highest_priced_model()
        except Exception:
            logger.exception("Strata model discovery failed during health check")

    return {
        "status": "ok",
        "provider": "groq",
        "model": resolved_model,
        "api_key_configured": bool(GEMINI_API_KEY),
    }


@app.post("/api/chat")
async def chat(req: Request):
    if not GEMINI_API_KEY or client is None:
        return JSONResponse(
            {"error": "The Groq API key is not configured on the server."},
            status_code=503,
        )

    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON request."}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": "Request body must be a JSON object."}, status_code=400)

    message = str(body.get("message", "")).strip()
    if not message:
        return JSONResponse({"error": "Message is required."}, status_code=400)

    session_id = str(body.get("session_id") or uuid.uuid4())
    first_question = mem.first(session_id)
    if not first_question:
        first_question = message
        mem.start(session_id, first_question)

    history = mem.history(session_id)
    mem.add(session_id, "user", message)

    async def stream_response():
        stages = (
            "Analyzing your question...",
            "Checking relevant knowledge...",
            "Formulating the answer...",
        )
        for stage in stages:
            yield f"data: {json.dumps({'type': 'status', 'message': stage})}\n\n"
            await asyncio.sleep(0.02)

        try:
            model_name = await client.highest_priced_model()
            system_prompt = load_instructions()
            messages = make_messages(history, first_question, message)

            answer_parts = []
            async for text in client.stream_chat(model_name, system_prompt, messages):
                answer_parts.append(text)
                yield f"data: {json.dumps({'type': 'delta', 'message': text})}\n\n"

            answer = "".join(answer_parts).strip()
            if not answer:
                answer = "I couldn't generate a response. Please try again."

            mem.add(session_id, "model", answer)
            yield f"data: {json.dumps({'type': 'answer', 'message': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as exc:
            logger.exception("Chat generation failed")
            safe_error = str(exc).strip().replace("\n", " ")[:240]
            yield f"data: {json.dumps({'type': 'error', 'message': f'Strata could not complete the request: {safe_error}'})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
