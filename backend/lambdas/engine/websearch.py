"""Web search and page reading for the research agent.

Search goes through a provider interface (Tavily today; another can sit behind the same `search` signature). Page reading uses the same
SSRF-safe fetcher as everything else (https only, public addresses only, every redirect hop checked) and only returns plain text.
Everything fetched from the web is UNTRUSTED DATA: callers wrap it and never treat it as instructions.
"""
import html
import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from .netsafe import FetchError, fetch_bytes, quality_fixes, user_agent

TAVILY_URL = "https://api.tavily.com/search"
TOPICS = ("general", "news", "finance")
TIME_RANGES = ("day", "week", "month", "year")
MAX_RESULTS = 6


class WebSearchError(RuntimeError):
    pass


def _clean(s: Any, n: int) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip()[:n]


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key: str, post: Optional[Callable[..., bytes]] = None):
        self._key = api_key
        self._post = post or self._http_post

    @staticmethod
    def _http_post(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> bytes:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **({"User-Agent": user_agent()} if quality_fixes() else {}), **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(1_000_000)
        except urllib.error.HTTPError as e:  # status only: error bodies can echo the request
            raise WebSearchError(f"search provider HTTP {e.code}") from e
        except Exception as e:
            raise WebSearchError(f"search provider request failed: {type(e).__name__}") from e

    def search(self, query: str, *, topic: str = "general", time_range: Optional[str] = None, max_results: int = MAX_RESULTS,
               include_domains: Optional[List[str]] = None, timeout: float = 12.0) -> List[Dict[str, str]]:
        body: Dict[str, Any] = {"query": _clean(query, 200), "topic": topic if topic in TOPICS else "general", "max_results": max(1, min(int(max_results), 10)),
                                "search_depth": "basic", "include_answer": False, "include_images": False, "include_raw_content": False}
        if time_range in TIME_RANGES:
            body["time_range"] = time_range
        if include_domains:
            body["include_domains"] = [d for d in include_domains if re.fullmatch(r"[a-z0-9.-]{3,80}", d)][:20]
        raw = self._post(TAVILY_URL, {"Authorization": f"Bearer {self._key}"}, body, timeout)
        try:
            data = json.loads(raw)
        except ValueError as e:
            raise WebSearchError("search provider returned invalid JSON") from e
        out: List[Dict[str, str]] = []
        for r in data.get("results") or []:
            url = str(r.get("url") or "")
            if urlparse(url).scheme != "https" or not domain_of(url):
                continue  # only https pages are ever offered to the agent
            out.append({"title": _clean(r.get("title"), 160) or domain_of(url), "url": url[:500], "content": _clean(r.get("content"), 900),
                        "date": _clean(r.get("published_date") or r.get("publishedDate"), 40)})
        return out


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in ("p", "br", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data)


def page_text(url: str, *, max_chars: int = 5000, fetch: Callable[..., bytes] = fetch_bytes) -> str:
    """Readable text of a page (HTML or plain text). Raises WebSearchError for anything unfetchable, unsafe or not text."""
    try:
        raw = fetch(url, max_bytes=500_000, timeout=12, headers={"Accept": "text/html,text/plain;q=0.9"})
    except FetchError as e:
        raise WebSearchError(f"could not read the page ({e})") from e
    head = raw[:512].lstrip().lower()
    if head.startswith(b"%pdf") or b"\x00" in raw[:1024]:
        raise WebSearchError("the page is not readable text")
    text = raw.decode("utf-8", errors="replace")
    p = _Text()
    try:
        p.feed(text)
    except Exception:
        pass
    out = re.sub(r"[ \t]+", " ", "".join(p.parts))
    out = re.sub(r"\n\s*\n+", "\n", out).strip()
    if len(out) < 80:
        raise WebSearchError("the page has no readable text")
    return out[:max_chars]
