import aiohttp
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class SearchEngine:
    """Web search interface for retrieving real-time information."""

    SEARCH_API = "https://api.search.brave.com/res/v1/web/search"
    GOOGLE_SEARCH_API = "https://www.google.com/search"

    @staticmethod
    async def search(query: str, limit: int = 5) -> List[Dict]:
        """
        Search the web using Google search.
        Returns list of results with title, link, and snippet.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            params = {
                "q": query,
                "num": limit,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    SearchEngine.GOOGLE_SEARCH_API,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        results = SearchEngine._parse_google_results(html)
                        return results
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            return []

        return []

    @staticmethod
    def _parse_google_results(html: str) -> List[Dict]:
        """Parse Google search HTML results."""
        results = []
        try:
            import re

            # Simple regex pattern to extract search results
            pattern = r'<a href="([^"]+)" ping="[^"]*"><h3[^>]*>([^<]+)</h3>'
            matches = re.findall(pattern, html)

            for url, title in matches[:5]:
                if url.startswith("/url?q="):
                    url = url.split("/url?q=")[1].split("&")[0]
                results.append({"title": title, "link": url, "snippet": ""})
        except Exception as e:
            logger.warning(f"Parsing search results failed: {e}")

        return results

    @staticmethod
    async def get_page_content(url: str) -> Optional[str]:
        """
        Fetch and extract text content from a webpage.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        # Simple text extraction
                        import re

                        text = re.sub(r"<[^>]+>", " ", html)
                        text = re.sub(r"\s+", " ", text).strip()
                        return text[:2000]  # Return first 2000 chars
        except Exception as e:
            logger.warning(f"Failed to fetch page content: {e}")

        return None
