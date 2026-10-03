import json
import uuid
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL, HOST, PORT
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

SYSTEM_PROMPT = """
You are Strata, a helpful and intelligent AI assistant.
You have access to real-time information through web search.

Behavior Guidelines:
- Be conversational, clear, and direct.
- Provide accurate, evidence-based responses.
- When information might be outdated, mention it and offer to search.
- Break down complex topics step-by-step.
- For code requests, provide clean, well-commented examples.
- Always cite sources when using web search results.
- Be concise but thorough.
- Adapt your tone to the user's style.

Tools Available:
- Google Search: Search for current information
- Web Retrieval: Extract content from webpages
- Conversation Memory: Maintain context across messages
"""


@app.get("/", response_class=HTMLResponse)
def home():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "api_key_configured": bool(GEMINI_API_KEY),
    }


@app.post("/api/chat")
async def chat(req: Request):
    if not GEMINI_API_KEY or not client:
        return JSONResponse(
            {
                "error": "GEMINI_API_KEY is not configured. Set it in the environment or Render dashboard."
            },
            status_code=500,
        )

    body = await req.json()
    message = str(body.get("message", "")).strip()
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
        thinking_steps = [
            ("🔍", "Analyzing your question..."),
            ("🌐", "Searching the web for latest information..."),
            ("📚", "Retrieving relevant knowledge..."),
            ("⚙️", "Processing and synthesizing response..."),
            ("✅", "Preparing final answer..."),
        ]

        for emoji, step in thinking_steps:
            yield "data: " + json.dumps({"type": "status", "message": step, "emoji": emoji}) + "\n\n"

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

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                max_output_tokens=2048,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )

            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
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
            error_message = f"An error occurred: {str(exc)[:100]}"
            logger.error(f"Chat error: {exc}")
            yield "data: " + json.dumps({"type": "error", "message": error_message}) + "\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, reload=False)
