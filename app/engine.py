"""Groq agent client helpers.

The existing GEMINI_API_KEY environment variable is intentionally retained
for deployment compatibility. Its value is treated as the Groq API key.
"""

import ast
import json
from datetime import datetime, timezone

import aiohttp

from app.config import GEMINI_API_KEY

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limits = {
            "requests": {"remaining": None, "limit": None, "reset": None},
            "tokens": {"remaining": None, "limit": None, "reset": None},
        }

    def _record_rate_limits(self, response) -> None:
        def number(name: str):
            value = response.headers.get(name)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        self.rate_limits["requests"] = {
            "remaining": number("x-ratelimit-remaining-requests"),
            "limit": number("x-ratelimit-limit-requests"),
            "reset": response.headers.get("x-ratelimit-reset-requests"),
        }
        self.rate_limits["tokens"] = {
            "remaining": number("x-ratelimit-remaining-tokens"),
            "limit": number("x-ratelimit-limit-tokens"),
            "reset": response.headers.get("x-ratelimit-reset-tokens"),
        }

    def credit_status(self) -> dict:
        def percentage(bucket):
            remaining = bucket["remaining"]
            limit = bucket["limit"]
            if remaining is None or limit is None or limit <= 0:
                return None
            return round(max(0.0, min(100.0, remaining / limit * 100.0)), 1)

        return {
            "requests": {
                **self.rate_limits["requests"],
                "remaining_percent": percentage(self.rate_limits["requests"]),
            },
            "tokens": {
                **self.rate_limits["tokens"],
                "remaining_percent": percentage(self.rate_limits["tokens"]),
            },
            "source": "Groq rate-limit headers",
        }

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

    @staticmethod
    def _calculate(expression: str) -> str:
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp,
            ast.Add, ast.Sub, ast.Mult, ast.Div,
            ast.FloorDiv, ast.Mod, ast.Pow,
            ast.USub, ast.UAdd, ast.Constant,
        )
        try:
            tree = ast.parse(expression, mode="eval")
            if any(not isinstance(node, allowed) for node in ast.walk(tree)):
                return "Unsupported expression."
            value = eval(compile(tree, "<calculator>", "eval"), {"__builtins__": {}}, {})
            return str(value)
        except Exception as exc:
            return f"Calculation error: {exc}"

    async def _completion(self, messages: list[dict], tools=None, tool_choice="auto", max_tokens=2048, temperature=0.2) -> dict:
        payload = {
            "model": DEFAULT_MODEL,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "reasoning_effort": "low",
            "tool_choice": tool_choice,
        }
        if tools:
            payload["tools"] = tools

        timeout = aiohttp.ClientTimeout(total=180, sock_connect=30, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                self._record_rate_limits(response)
                if response.status != 200:
                    detail = await response.text()
                    raise RuntimeError(f"Groq returned HTTP {response.status}: {detail[:400]}")
                return await response.json()

    async def correct_message(self, message: str) -> str:
        """Normalize unclear user wording without changing its intended request."""
        if len(message.strip()) < 4:
            return message.strip()

        data = await self._completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Strata's message-understanding layer. Rewrite the user's "
                        "message into one clear, concise request while preserving the exact "
                        "intent, constraints, names, numbers, code, and requested outcome. "
                        "Fix obvious spelling, grammar, fragmented wording, and speech-to-text "
                        "errors. Do not answer the request. Do not add requirements. If the "
                        "message is already clear, return it unchanged. Return only the "
                        "normalized request."
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=768,
            temperature=0.1,
        )
        normalized = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return normalized or message

    async def search_web(self, query: str) -> str:
        """Run a focused real-time browser search through Groq's built-in search."""
        data = await self._completion(
            [
                {
                    "role": "system",
                    "content": "Search the web for the user's query. Prefer current authoritative sources. Return a concise research result with source names and useful URLs when available.",
                },
                {"role": "user", "content": query},
            ],
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            max_tokens=3000,
            temperature=0.2,
        )
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

    async def deep_research(self, topic: str, focus: str = "") -> str:
        """Perform a deeper multi-source research pass using browser search."""
        request = topic if not focus else f"Topic: {topic}\nResearch focus: {focus}"
        data = await self._completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Strata's deep-research specialist. Conduct a thorough web "
                        "research pass using browser search. Search multiple relevant sources, "
                        "prefer primary sources, compare conflicting information, check dates, "
                        "and synthesize the findings. Return a structured research brief with "
                        "key findings, important caveats, and source names/URLs. Do not invent sources."
                    ),
                },
                {"role": "user", "content": request},
            ],
            tools=[{"type": "browser_search"}],
            tool_choice="required",
            max_tokens=6000,
            temperature=0.2,
        )
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

    async def study(self, topic: str, material: str = "") -> str:
        """Create an active study guide or analyze supplied study material."""
        prompt = (
            f"Topic: {topic}\n\nStudy material:\n{material}"
            if material.strip()
            else f"Topic: {topic}"
        )
        data = await self._completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Strata's study specialist. Teach rather than merely summarize. "
                        "Build a structured study session with core concepts, simple explanations, "
                        "examples, misconceptions, practice questions, and a short self-test. "
                        "If study material is supplied, ground the lesson in it and clearly "
                        "separate supplied facts from added explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=5000,
            temperature=0.35,
        )
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

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
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Safely evaluate a mathematical expression.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string", "description": "Mathematical expression."}
                        },
                        "required": ["expression"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current UTC date and time in ISO 8601 format.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "format_json",
                    "description": "Validate and pretty-print JSON.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string", "description": "JSON text."}
                        },
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Run a focused real-time web search for current or source-dependent information.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "deep_research",
                    "description": "Conduct a deeper multi-source web research pass. Use for complex research questions, comparisons, or topics requiring several sources.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "focus": {"type": "string"},
                        },
                        "required": ["topic"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "study",
                    "description": "Create an active study session with explanations, examples, practice questions, and a self-test.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "material": {"type": "string"},
                        },
                        "required": ["topic"],
                        "additionalProperties": False,
                    },
                },
            },
        ])

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
                    self._record_rate_limits(response)
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

                    arguments = {}
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except (TypeError, json.JSONDecodeError):
                        arguments = {}

                    if name == "get_pasted_text":
                        result = pasted_text
                    elif name == "get_current_time":
                        result = datetime.now(timezone.utc).isoformat()
                    elif name == "format_json":
                        try:
                            parsed = json.loads(str(arguments.get("value", "")))
                            result = json.dumps(parsed, indent=2, ensure_ascii=False)
                        except (TypeError, json.JSONDecodeError) as exc:
                            result = f"Invalid JSON: {exc}"
                    elif name == "calculator":
                        result = self._calculate(str(arguments.get("expression", "")))
                    elif name == "search_web":
                        result = await self.search_web(str(arguments.get("query", "")))
                    elif name == "deep_research":
                        result = await self.deep_research(
                            str(arguments.get("topic", "")),
                            str(arguments.get("focus", "")),
                        )
                    elif name == "study":
                        result = await self.study(
                            str(arguments.get("topic", "")),
                            str(arguments.get("material", "")),
                        )
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
