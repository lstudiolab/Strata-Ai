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

from app.config import GEMINI_API_KEY, HOST, PORT
from app.engine import client
from app.memory import Memory

logger = logging.getLogger(__name__)

app = FastAPI(title="Strata AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
mem = Memory("data/strata.db")


def load_available_models():
    instructions_dir = Path(__file__).parent / "instructions"
    models = {}

    if instructions_dir.exists():
        for file in sorted(instructions_dir.glob("*.txt")):
            model_name = file.stem
            models[model_name] = {
                "model_id": "gemini-1.5-flash",
                "name": model_name.replace("_", " ").title(),
            }

    if not models:
        models["default"] = {"model_id": "gemini-1.5-flash", "name": "Default"}

    return models


AVAILABLE_MODELS = load_available_models()


def get_default_instructions() -> str:
    return """
You are Strata, a helpful and intelligent AI assistant.

Behavior Guidelines:
- Be conversational, clear, and direct.
- Provide accurate, evidence-based responses.
- Break down complex topics step-by-step.
- For code requests, provide clean, well-commented examples.
- Be concise but thorough.
- Adapt your tone to the user's style.
- Always be respectful and helpful.
""".strip()


def load_instructions(model_type: str = "default") -> str:
    instructions_file = Path(__file__).parent / "instructions" / f"{model_type}.txt"
    if instructions_file.exists():
        return instructions_file.read_text(encoding="utf-8").strip()
    return get_default_instructions()


@app.get("/", response_class=HTMLResponse)
def home():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/models")
def get_models():
    return {"models": list(AVAILABLE_MODELS.keys())}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": "gemini-1.5-flash",
        "api_key_configured": bool(GEMINI_API_KEY),
    }


@app.post("/api/chat")
async def chat(req: Request):
    if not GEMINI_API_KEY or not client:
        return JSONResponse(
            {"error": "GEMINI_API_KEY is not configured."},
            status_code=500,
        )

    body = await req.json()
    message = str(body.get("message", "")).strip()
    model_type = str(body.get("model_type", "default")).strip() or "default"

    if not message:
        return JSONResponse({"error": "Message is required."}, status_code=400)

    session_id = str(body.get("session_id") or uuid.uuid4())
    first_question = mem.first(session_id)
    if not first_question:
        mem.start(session_id, message)
        first_question = message

    history = mem.history(session_id)
    mem.add(session_id, "user", message)

    async def stream_response():
        thinking_stages = [
            "Analyzing your question...",
            "Thinking about the best approach...",
            "Formulating response...",
            "Finalizing answer...",
        ]

        try:
            contents = []
            for role, text in history:
                contents.append(
                    types.Content(
                        role="user" if role == "user" else "model",
                        parts=[types.Part.from_text(text=text)],
                    )
                )

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=f"First question in conversation: {first_question}\n\nCurrent message: {message}"
                        )
                    ],
                )
            )

            system_prompt = load_instructions(model_type)

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                max_output_tokens=2048,
            )

            for stage in thinking_stages:
                yield "data: " + json.dumps({"type": "status", "message": stage}) + "\n\n"
                await asyncio.sleep(0.05)

            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=contents,
                config=config,
            )

            answer = (
                response.text.strip()
                if getattr(response, "text", None)
                else "I apologize, but I couldn't generate a response. Please try again."
            )
            mem.add(session_id, "model", answer)

            yield "data: " + json.dumps({"type": "answer", "message": answer}) + "\n\n"
        except Exception as exc:
            error_message = f"An error occurred: {str(exc)[:120]}"
            logger.error(f"Chat error: {exc}")
            yield "data: " + json.dumps({"type": "error", "message": error_message}) + "\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, reload=False)
