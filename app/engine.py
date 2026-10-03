"""OpenRouter client helpers.

The existing GEMINI_API_KEY environment variable is intentionally retained
for deployment compatibility. Its value is treated as the OpenRouter API key.
"""

import json
import time
from typing import AsyncIterator

import aiohttp

from app.config import GEMINI_API_KEY

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_CACHE_SECONDS = 300


class OpenRouterClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._cached_model: str | None = None
        self._cached_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://strata-ai.onrender.com",
            "X-Title": "Strata AI",
        }

    async def highest_priced_model(self) -> str:
        now = time.monotonic()
        if self._cached_model and now - self._cached_at < MODEL_CACHE_SECONDS:
            return self._cached_model

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{OPENROUTER_BASE_URL}/models",
                headers=self._headers(),
            ) as response:
                if response.status != 200:
                    detail = await response.text()
                    raise RuntimeError(
                        f"OpenRouter model catalog returned HTTP {response.status}: {detail[:240]}"
                    )
                payload = await response.json()

        candidates = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            pricing = item.get("pricing") or {}
            try:
                prompt_price = float(pricing.get("prompt") or 0)
                completion_price = float(pricing.get("completion") or 0)
            except (TypeError, ValueError):
                continue

            architecture = item.get("architecture") or {}
            output_modalities = architecture.get("output_modalities") or []
            if output_modalities and "text" not in output_modalities:
                continue

            if model_id and (prompt_price > 0 or completion_price > 0):
                candidates.append(
                    (prompt_price + completion_price, completion_price, prompt_price, model_id)
                )

        if not candidates:
            raise RuntimeError("OpenRouter did not return a priced text-generation model.")

        candidates.sort(reverse=True)
        self._cached_model = candidates[0][3]
        self._cached_at = now
        return self._cached_model

    async def stream_chat(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
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
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status != 200:
                    detail = await response.text()
                    raise RuntimeError(
                        f"OpenRouter returned HTTP {response.status}: {detail[:320]}"
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


client = OpenRouterClient(GEMINI_API_KEY) if GEMINI_API_KEY else None
