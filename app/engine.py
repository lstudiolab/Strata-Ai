"""Groq agent client helpers.

The existing GEMINI_API_KEY environment variable is intentionally retained
for deployment compatibility. Its value is treated as the Groq API key.
"""

import ast
import json
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp

from app.config import GEMINI_API_KEY

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"

TOOL_CATALOG = {
    "browser_search": "Search the live web for current information.",
    "code_interpreter": "Run Python code for calculations, data analysis, and verification.",
    "calculator": "Evaluate mathematical expressions safely.",
    "get_current_time": "Get the current UTC date and time.",
    "format_json": "Validate and pretty-print JSON.",
    "search_web": "Run a focused real-time web search.",
    "deep_research": "Research a complex topic across multiple sources.",
    "study": "Build a structured lesson, practice set, and self-test.",
    "get_pasted_text": "Read text explicitly supplied by the user.",
    "analyze_image": "Analyze an uploaded image, including OCR and visual understanding.",
    "get_navigation_links": "Create navigation links for Apple Maps, Google Maps, and Waze.",
    "open_webpage": "Read a public webpage for analysis.",
    "get_weather": "Get current weather and forecasts for a location.",
    "get_sports": "Get current sports scores, schedules, and standings.",
    "get_stock_quote": "Get current public market information for a stock symbol.",
}


class GroqClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limits = {
            "requests": {"remaining": None, "limit": None, "reset": None},
            "tokens": {"remaining": None, "limit": None, "reset": None},
        }

    def _record_rate_limits(self, response) -> None:
        def read_int(name):
            try:
                return int(response.headers.get(name))
            except (TypeError, ValueError):
                return None

        self.rate_limits["requests"] = {
            "remaining": read_int("x-ratelimit-remaining-requests"),
            "limit": read_int("x-ratelimit-limit-requests"),
            "reset": response.headers.get("x-ratelimit-reset-requests"),
        }
        self.rate_limits["tokens"] = {
            "remaining": read_int("x-ratelimit-remaining-tokens"),
            "limit": read_int("x-ratelimit-limit-tokens"),
            "reset": response.headers.get("x-ratelimit-reset-tokens"),
        }

    def credit_status(self):
        result = {"source": "Groq rate-limit headers"}
        for key, bucket in self.rate_limits.items():
            remaining = bucket["remaining"]
            limit = bucket["limit"]
            percent = None if remaining is None or not limit else round(max(0, min(100, remaining / limit * 100)), 1)
            result[key] = {**bucket, "remaining_percent": percent}
        return result

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

    async def _completion(self, messages: list[dict], tools=None, tool_choice="auto", max_tokens=2048, temperature=0.2, model=DEFAULT_MODEL) -> dict:
        payload = {
            "model": model,
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

    async def summarize_memory(self, existing_summary: str, messages: list[dict]) -> str:
        """Compress older conversation turns into durable context without deleting them."""
        transcript = "\n".join(
            f"{item.get('role', 'user').upper()}: {item.get('content', '')}"
            for item in messages
        )
        prompt = (
            "Create durable memory for a continuing conversation. Preserve facts, "
            "decisions, preferences, names, constraints, unresolved questions, important "
            "technical details, and commitments that may matter later. Remove repetition "
            "and small talk. Do not invent anything. Keep it compact but information-dense. "
            "This is memory, not a response to the user.\n\n"
            + ("Existing memory:\n" + existing_summary + "\n\n" if existing_summary else "")
            + "New conversation turns:\n" + transcript
        )
        data = await self._completion(
            [
                {"role": "system", "content": "You maintain Strata's long-term conversation memory."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=3000,
            temperature=0.1,
        )
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

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


    async def open_webpage(self, url: str) -> str:
        """Read a public webpage for analysis."""
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            return "A valid public http(s) URL is required."
        timeout = aiohttp.ClientTimeout(total=30, sock_connect=10, sock_read=20)
        headers = {"User-Agent": "Strata/1.0 (+https://strata-ai.app)"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status >= 400:
                        return f"Webpage returned HTTP {response.status}."
                    text = await response.text(errors="replace")
                    if len(text) > 30000:
                        text = text[:30000] + "\n[Page content truncated.]"
                    return text
        except Exception as exc:
            return f"Webpage read error: {exc}"

    async def get_weather(self, location: str) -> str:
        """Get current weather and forecast using Open-Meteo."""
        location = str(location).strip()
        if not location:
            return "A location is required."
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en", "format": "json"},
                ) as response:
                    geo = await response.json()
                results = geo.get("results") or []
                if not results:
                    return f"I could not find a location matching {location!r}."
                place = results[0]
                async with session.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                        "forecast_days": 3,
                        "timezone": "auto",
                    },
                ) as response:
                    weather = await response.json()
                return json.dumps({
                    "location": {
                        "name": place.get("name"),
                        "admin1": place.get("admin1"),
                        "country": place.get("country"),
                    },
                    "current": weather.get("current", {}),
                    "daily": weather.get("daily", {}),
                }, ensure_ascii=False)
        except Exception as exc:
            return f"Weather lookup error: {exc}"

    async def get_stock_quote(self, symbol: str) -> str:
        """Get a current-ish public market quote from Yahoo Finance's chart endpoint."""
        symbol = str(symbol).strip().upper()
        if not symbol:
            return "A stock symbol is required."
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
                    params={"range": "1d", "interval": "1m"},
                    headers={"User-Agent": "Strata/1.0"},
                ) as response:
                    if response.status >= 400:
                        return f"Market service returned HTTP {response.status}."
                    data = await response.json()
            result = (data.get("chart", {}).get("result") or [None])[0]
            if not result:
                return f"No market data was found for {symbol}."
            meta = result.get("meta", {})
            return json.dumps({
                "symbol": symbol,
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName"),
                "price": meta.get("regularMarketPrice"),
                "previous_close": meta.get("previousClose"),
                "market_time": meta.get("regularMarketTime"),
            }, ensure_ascii=False)
        except Exception as exc:
            return f"Stock lookup error: {exc}"

    async def get_sports(self, league: str, team: str = "") -> str:
        """Get public sports scores/schedules from ESPN's scoreboard endpoint."""
        league = str(league).strip().lower()
        team = str(team).strip()
        league_map = {
            "nfl": "football/nfl",
            "nba": "basketball/nba",
            "wnba": "basketball/wnba",
            "mlb": "baseball/mlb",
            "nhl": "hockey/nhl",
            "epl": "soccer/eng.1",
            "premier league": "soccer/eng.1",
            "ncaaf": "football/college-football",
            "ncaab": "basketball/mens-college-basketball",
        }
        path = league_map.get(league, league if "/" in league else "")
        if not path:
            return "Use a supported league such as NFL, NBA, WNBA, MLB, NHL, EPL, NCAAF, or NCAAB."
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard",
                    headers={"User-Agent": "Strata/1.0"},
                ) as response:
                    if response.status >= 400:
                        return f"Sports service returned HTTP {response.status}."
                    data = await response.json()
            events = []
            for event in (data.get("events") or [])[:20]:
                name = event.get("name", "")
                if team and team.lower() not in name.lower():
                    continue
                competitions = (event.get("competitions") or [{}])[0]
                competitors = []
                for item in competitions.get("competitors") or []:
                    competitors.append({
                        "team": (item.get("team") or {}).get("displayName"),
                        "score": item.get("score"),
                        "home_away": item.get("homeAway"),
                    })
                events.append({
                    "name": name,
                    "date": event.get("date"),
                    "status": (event.get("status") or {}).get("type", {}).get("detail"),
                    "competitors": competitors,
                })
            return json.dumps({"league": league, "events": events}, ensure_ascii=False)
        except Exception as exc:
            return f"Sports lookup error: {exc}"


    async def analyze_image(self, image_data: str, prompt: str = "Analyze this image carefully and answer the user's request. If there is text, transcribe the relevant text accurately.") -> str:
        if not image_data.startswith("data:image/"):
            return "The attached file is not a supported image."

        data = await self._completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Strata's private visual-analysis capability. Analyze the supplied "
                        "image accurately. Do not invent visual details. Read visible text when asked, "
                        "describe uncertainty, and follow the user's requested task."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.4,
            model=VISION_MODEL,
        )
        return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

    @staticmethod
    def discover_tools(query: str) -> str:
        words = {word.lower() for word in str(query).replace("-", " ").split() if len(word) > 2}
        ranked = []
        for name, description in TOOL_CATALOG.items():
            haystack = f"{name} {description}".lower()
            score = sum(1 for word in words if word in haystack)
            if score:
                ranked.append((score, name, description))
        ranked.sort(reverse=True)
        if not ranked:
            return json.dumps(
                [{"name": name, "description": description} for name, description in TOOL_CATALOG.items()],
                ensure_ascii=False,
            )
        return json.dumps(
            [{"name": name, "description": description} for _, name, description in ranked[:8]],
            ensure_ascii=False,
        )

    @staticmethod
    def get_navigation_links(destination: str, mode: str = "driving", source: str = "") -> str:
        destination = str(destination).strip()
        source = str(source).strip()
        mode = str(mode or "driving").strip().lower()
        mode = {"driving": "driving", "walking": "walking", "transit": "transit", "bicycling": "bicycling"}.get(mode, "driving")
        if not destination:
            return "A destination is required."

        apple = f"https://maps.apple.com/directions?destination={quote(destination)}&mode={mode}"
        google = f"https://www.google.com/maps/dir/?api=1&destination={quote(destination)}&travelmode={mode}"
        waze = f"https://www.waze.com/ul?q={quote(destination)}&navigate=yes"
        if source:
            apple += f"&source={quote(source)}"
            google += f"&origin={quote(source)}"
        return json.dumps(
            {
                "destination": destination,
                "mode": mode,
                "apple_maps": apple,
                "google_maps": google,
                "waze": waze,
            },
            ensure_ascii=False,
        )

    async def run_agent(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        pasted_text: str = "",
        image_data: str = "",
        on_tool=None,
    ) -> str:
        working = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "discover_tools",
                    "description": "Discover Strata's available capabilities based on what the user needs. Use this when the task may require a capability you have not yet selected.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
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
                    "name": "open_webpage",
                    "description": "Read a public webpage so Strata can analyze its contents.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather and a short forecast for a named location.",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_sports",
                    "description": "Get current scores and schedules for a supported sports league, optionally filtered by team.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "league": {"type": "string"},
                            "team": {"type": "string"},
                        },
                        "required": ["league"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stock_quote",
                    "description": "Get public market quote information for a stock symbol.",
                    "parameters": {
                        "type": "object",
                        "properties": {"symbol": {"type": "string"}},
                        "required": ["symbol"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_navigation_links",
                    "description": "Create direct navigation links for Apple Maps, Google Maps, and Waze for a destination.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "destination": {"type": "string"},
                            "mode": {"type": "string", "enum": ["driving", "walking", "transit", "bicycling"]},
                            "source": {"type": "string"},
                        },
                        "required": ["destination"],
                        "additionalProperties": False,
                    },
                },
            },
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

        if image_data.startswith("data:image/"):
            tools.append({
                "type": "function",
                "function": {
                    "name": "analyze_image",
                    "description": "Analyze the user's uploaded image. Use this for visual questions, OCR, screenshots, photos, charts, diagrams, or image-based tasks.",
                    "parameters": {
                        "type": "object",
                        "properties": {"prompt": {"type": "string"}},
                        "required": ["prompt"],
                        "additionalProperties": False,
                    },
                },
            })

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
            for round_number in range(10):
                payload = {
                    "model": model or DEFAULT_MODEL,
                    "messages": working,
                    "stream": False,
                    "max_tokens": 12000,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "reasoning_effort": "high",
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

                    if name == "open_webpage":
                        result = await self.open_webpage(str(arguments.get("url", "")))
                    elif name == "get_weather":
                        result = await self.get_weather(str(arguments.get("location", "")))
                    elif name == "get_sports":
                        result = await self.get_sports(
                            str(arguments.get("league", "")),
                            str(arguments.get("team", "")),
                        )
                    elif name == "get_stock_quote":
                        result = await self.get_stock_quote(str(arguments.get("symbol", "")))
                    elif name == "discover_tools":
                        result = self.discover_tools(str(arguments.get("query", "")))
                    elif name == "get_navigation_links":
                        result = self.get_navigation_links(
                            str(arguments.get("destination", "")),
                            str(arguments.get("mode", "driving")),
                            str(arguments.get("source", "")),
                        )
                    elif name == "analyze_image":
                        result = await self.analyze_image(
                            image_data,
                            str(arguments.get("prompt", "Analyze the image carefully.")),
                        )
                    elif name == "get_pasted_text":
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
