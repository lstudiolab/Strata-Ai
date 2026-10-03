import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types

from app.config import (
    CORS_ORIGINS,
    DB_PATH,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    HOST,
    PORT,
)
from app.engine import client
from app.memory import Memory

logger = logging.getLogger("strata")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INSTRUCTIONS_DIR = BASE_DIR / "instructions"

app = FastAPI(title="Strata AI", version="1.0.0")

# No browser credentials are used by Strata, so wildcard CORS is safe for the
# default deployment. Specific origins can be supplied through CORS_ORIGINS.
allow_all_origins = CORS_ORIGINS == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
mem = Memory(DB_PATH)

AVAILABLE_MODELS = {
    "default": {"model_id": GEMINI_MODEL, "name": "Default"},
    "creative": {"model_id": GEMINI_MODEL, "name": "Creative"},
    "analytical": {"model_id": GEMINI_MODEL, "name": "Analytical"},
    "coding": {"model_id": GEMINI_MODEL, "name": "Coding"},
}


def get_default_instructions() -> str:
    return (
        "You are Strata, a capable general-purpose AI assistant. "
        "Be accurate, useful, direct, and transparent about uncertainty. "
        "Use the web-grounding tool when current or externally verifiable information "
        "would improve the answer. Never claim to have searched when you did not. "
        "Follow the user's request while keeping responses clear and practical."
    )


def load_instructions(model_type: str) -> str:
    safe_name = model_type if model_type in AVAILABLE_MODELS else "default"
    path = INSTRUCTIONS_DIR / f"{safe_name}.txt"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return get_default_instructions()


def make_contents(history, first_question: str, message: str):
    contents = []
    for role, text in history:
        contents.append(
            types.Content(
                role="user" if role == "user" else "model",
                parts=[types.Part.from_text(text=text)],
            )
        )

    # The first question is deliberately carried into the model context. This
    # gives Strata the persistent "first-question intelligence" requested by
    # the project without exposing an internal system prompt to the browser.
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=(
                        f"Conversation anchor (the user's first question): {first_question}\n\n"
                        f"User's current message: {message}"
                    )
                )
            ],
        )
    )
    return contents


def make_generation_config(system_prompt: str):
    # Google Search grounding is supported by current Gemini models and lets
    # the model retrieve current public web information itself. Older 1.5
    # models use a legacy tool name, so don't send the modern tool to them.
    tools = []
    if not GEMINI_MODEL.startswith("gemini-1.5"):
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        max_output_tokens=4096,
        tools=tools or None,
    )


@app.get("/", response_class=HTMLResponse)
async def home():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/models")
async def get_models():
    return {
        "models": [
            {"id": key, "name": value["name"], "model": value["model_id"]}
            for key, value in AVAILABLE_MODELS.items()
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "api_key_configured": bool(GEMINI_API_KEY),
        "web_grounding": not GEMINI_MODEL.startswith("gemini-1.5"),
    }


@app.post("/api/chat")
async def chat(req: Request):
    if not GEMINI_API_KEY or client is None:
        return JSONResponse(
            {"error": "GEMINI_API_KEY is not configured on the server."},
            status_code=503,
        )

    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON request."}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": "Request body must be a JSON object."}, status_code=400)

    message = str(body.get("message", "")).strip()
    model_type = str(body.get("model_type", "default")).strip() or "default"
    if model_type not in AVAILABLE_MODELS:
        model_type = "default"

    if not message:
        return JSONResponse({"error": "Message is required."}, status_code=400)

    session_id = str(body.get("session_id") or uuid.uuid4())
    first_question = mem.first(session_id)
    if not first_question:
        first_question = message
        mem.start(session_id, first_question)

    # Read previous turns before inserting the current user message, so the
    # current message is included exactly once in the generated contents.
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
            system_prompt = load_instructions(model_type)
            contents = make_contents(history, first_question, message)
            config = make_generation_config(system_prompt)
            model_name = AVAILABLE_MODELS[model_type]["model_id"]

            stream = await client.aio.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config,
            )

            answer_parts = []
            async for chunk in stream:
                text = getattr(chunk, "text", None)
                if not text:
                    continue
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
