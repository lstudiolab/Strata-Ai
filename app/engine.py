"""Groq agent client helpers.

The existing GEMINI_API_KEY environment variable is intentionally retained
for deployment compatibility. Its value is treated as the Groq API key.
"""

import json
from typing import AsyncIterator

import aiohttp

from app.config import GEMINI_API_KEY

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def highest_priced_model(self) -> str:
        """Return Strata's current flagship Groq production model.

        Groq's model catalog does not expose OpenRouter-style per-model
        pricing metadata, so Strata uses Groq's featured flagship model.
        """
        return DEFAULT_MODEL

    async def run_agent(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        pasted_text: str = "",
        on_tool=None,
    ) -> str:
        working = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        tools = [
            {"type": "browser_search"},
            {"type": "code_interpreter"},
        ]
        if pasted_text.strip():
            tools.append({
                "type": "function",
                "function": {
                    "name": "get_pasted_text",
                    "description": (
                        "Read text the user explicitly pasted for this request. "
                        "Use it when the user wants the pasted text analyzed, "
                        "summarized, rewritten, extracted, compared, or explained."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            })

        timeout = aiohttp.ClientTimeout(total=180, sock_connect=30, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for round_number in range(6):
                payload = {
                    "model": model or DEFAULT_MODEL,
                    "messages": working,
                    "stream": False,
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "reasoning_effort": "medium",
                    "tool_choice": "auto",
                }
                if tools:
                    payload["tools"] = tools

                async with session.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status != 200:
                        detail = await response.text()
                        raise RuntimeError(
                            f"Groq returned HTTP {response.status}: {detail[:400]}"
                        )
                    data = await response.json()

                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                calls = message.get("tool_calls") or []

                if not calls:
                    return (message.get("content") or "").strip()

                working.append({
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": calls,
                })

                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name", "")
                    call_id = call.get("id", "")

                    if on_tool is not None:
                        await on_tool(name, round_number + 1)

                    if name == "get_pasted_text":
                        result = pasted_text
                    else:
                        result = "This tool is unavailable."

                    working.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": result,
                    })

            raise RuntimeError("Strata reached the maximum tool-use rounds.")


client = GroqClient(GEMINI_API_KEY) if GEMINI_API_KEY else None
