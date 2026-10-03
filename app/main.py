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
    path = INSTRUCTIONS_DIR / "strata.md"
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


@app.get("/api/conversations")
async def get_conversations():
    return {"conversations": mem.list_sessions()}


@app.get("/api/conversations/{session_id}")
async def get_conversation(session_id: str):
    return {
        "session_id": session_id,
        "messages": [
            {"role": role, "content": content}
            for role, content in mem.conversation(session_id)
        ],
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
    pasted_text = str(body.get("pasted_text", "") or "").strip()

    if not message:
        return JSONResponse({"error": "Message is required."}, status_code=400)

    # Keep pasted context bounded so a browser paste cannot overwhelm the model.
    pasted_text = pasted_text[:120000]

    session_id = str(body.get("session_id") or uuid.uuid4())
    first_question = mem.first(session_id)
    if not first_question:
        first_question = message
        mem.start(session_id, first_question)

    history = mem.history(session_id)
    mem.add(session_id, "user", message)

    async def stream_response():
        yield f"data: {json.dumps({'type': 'status', 'message': 'Thinking...'})}\n\n"

        try:
            model_name = await client.highest_priced_model()
            system_prompt = load_instructions()

            await tool_events.put({"message": "Understanding your message..."})
            corrected_message = await client.correct_message(message)

            if pasted_text:
                system_prompt += (
                    "\n\nA pasted-text tool is available for this request. "
                    "Use get_pasted_text when the user's task depends on the "
                    "pasted material. Do not claim to have read it unless you "
                    "actually call the tool."
                )

            messages = make_messages(history, first_question, message)
            if corrected_message != message:
                messages.append({
                    "role": "user",
                    "content": (
                        "Message understanding correction (use this only to clarify the "
                        "previous user message; preserve the user's original intent): "
                        + corrected_message
                    ),
                })
            tool_events: asyncio.Queue = asyncio.Queue()

            async def on_tool(name: str, round_number: int):
                labels = {
                    "get_pasted_text": "Reading the pasted text...",
                    "calculator": "Calculating...",
                    "get_current_time": "Checking the current time...",
                    "format_json": "Formatting the JSON...",
                    "browser_search": "Searching the web...",
                    "code_interpreter": "Running code...",
                    "search_web": "Searching the web...",
                    "deep_research": "Doing deep research...",
                    "study": "Building a study session...",
                }
                await tool_events.put({
                    "message": labels.get(name, f"Using {name}...")
                })

            agent_task = asyncio.create_task(
                client.run_agent(
                    model_name,
                    system_prompt,
                    messages,
                    pasted_text=pasted_text,
                    on_tool=on_tool,
                )
            )

            while not agent_task.done():
                try:
                    event = await asyncio.wait_for(tool_events.get(), timeout=0.15)
                    yield f"data: {json.dumps({'type': 'status', 'message': event['message']})}\n\n"
                except asyncio.TimeoutError:
                    continue

            while not tool_events.empty():
                event = await tool_events.get()
                yield f"data: {json.dumps({'type': 'status', 'message': event['message']})}\n\n"

            answer = await agent_task
            if not answer:
                answer = "I couldn't generate a response. Please try again."

            # Keep the clean streaming feel in the UI after agent/tool work.
            chunk_size = 48
            for index in range(0, len(answer), chunk_size):
                yield f"data: {json.dumps({'type': 'delta', 'message': answer[index:index + chunk_size]})}\n\n"
                await asyncio.sleep(0.005)

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
