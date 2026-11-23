"""Ground the script in real text so numbers and claims aren't invented.

Wikipedia is free and keyless. Its text is CC BY-SA: we only use it as *notes* for the model (which
paraphrases) and record every page as a source for the video description. Swap in a web-search provider
behind the same `gather_notes` signature when you want broader coverage.
"""
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from .netsafe import FetchError, fetch_json

API = "https://en.wikipedia.org/w/api.php"


def api_for(language: str) -> str:
    return f"https://{language if language in ('en', 'es') else 'en'}.wikipedia.org/w/api.php"
MAX_NOTES_CHARS = 7000


def search_titles(query: str, limit: int = 3, fetch: Callable[[str], Any] = fetch_json, api: str = API) -> List[str]:
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query[:150], "srlimit": limit, "format": "json", "formatversion": 2})
    data = fetch(f"{api}?{q}")
    return [h["title"] for h in (data.get("query", {}).get("search") or []) if h.get("title")]


def fetch_extract(title: str, chars: int = 2600, fetch: Callable[[str], Any] = fetch_json, api: str = API) -> Dict[str, str]:
    q = urllib.parse.urlencode({
        "action": "query", "prop": "extracts|info", "titles": title, "explaintext": 1, "exintro": 0,
        "exchars": chars, "inprop": "url", "redirects": 1, "format": "json", "formatversion": 2,
    })
    page = (fetch(f"{api}?{q}").get("query", {}).get("pages") or [{}])[0]
    text = re.sub(r"\n{2,}", "\n", str(page.get("extract") or "")).strip()
    return {"title": str(page.get("title") or title), "url": str(page.get("fullurl") or ""), "text": text}


def queries_for(topic: str, language: str, ask: Optional[Callable[[str, str], str]]) -> List[str]:
    """1-3 short encyclopedia queries for the brief. A whole sentence as a search query finds unrelated pages (which would then be
    cited as sources), so a small model writes proper queries; any failure falls back to the brief itself."""
    if ask is None:
        return [topic]
    try:
        text = ask(f"Write up to 3 short Wikipedia search queries (2 to 5 words each, in {'Spanish' if language == 'es' else 'English'}) for the pages "
                   "needed to explain the user's request accurately. One query per line, no numbering, no quotes.", topic[:600])
    except Exception:
        return [topic]
    qs = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip(" \"'") for ln in text.splitlines()]
    qs = [q for q in qs if 2 <= len(q) <= 80][:3]
    return qs or [topic]


def gather_notes(topic: str, fetch: Callable[[str], Any] = fetch_json, language: str = "en",
                 ask: Optional[Callable[[str, str], str]] = None) -> Tuple[str, List[Dict[str, str]]]:
    """Returns (notes_text, sources). Never raises: a research failure must not fail the video."""
    notes: List[str] = []
    sources: List[Dict[str, str]] = []
    seen = set()
    try:
        api = api_for(language)
        titles: List[str] = []
        for q in queries_for(topic, language, ask):
            titles += [t for t in search_titles(q, limit=2, fetch=fetch, api=api) if t not in titles]
        for title in titles:
            if title in seen:
                continue
            seen.add(title)
            ex = fetch_extract(title, fetch=fetch, api=api)
            if len(ex["text"]) < 200:
                continue
            notes.append(f"## {ex['title']}\n{ex['text']}")
            sources.append({"title": ex["title"], "url": ex["url"], "publisher": "Wikipedia" if language == "en" else f"Wikipedia ({language})", "license": "CC BY-SA 4.0"})
            if sum(map(len, notes)) > MAX_NOTES_CHARS:
                break
    except (FetchError, KeyError, ValueError, TypeError):
        pass
    return "\n\n".join(notes)[:MAX_NOTES_CHARS], sources
