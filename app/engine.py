"""Groq client helpers.

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

    async def stream_chat(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = {
            "model": model or DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "stream": True,
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status != 200:
                    detail = await response.text()
                    raise RuntimeError(
                        f"Groq returned HTTP {response.status}: {detail[:320]}"
                    )

                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if data == "[DONE]":
                        break

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = event.get("choices") or []
                    if not choices:
                        continue

                    delta = (choices[0].get("delta") or {}).get("content")
                    if isinstance(delta, str) and delta:
                        yield delta


client = GroqClient(GEMINI_API_KEY) if GEMINI_API_KEY else None
