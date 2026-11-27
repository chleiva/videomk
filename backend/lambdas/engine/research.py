"""Ground the script in real text so numbers and claims aren't invented.

Wikipedia is free and keyless. Its text is CC BY-SA: we only use it as *notes* for the model (which
paraphrases) and record every page as a source for the video description. Swap in a web-search provider
behind the same `gather_notes` signature when you want broader coverage.
"""
import logging
import re
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from .netsafe import FetchError, fetch_json, quality_fixes, with_retry

API = "https://en.wikipedia.org/w/api.php"


def api_for(language: str) -> str:
    from . import voices   # every language a video can be made in has its own Wikipedia
    return f"https://{language if language in voices.LANGUAGES else 'en'}.wikipedia.org/w/api.php"
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


def _language_name(language: str) -> str:
    from . import voices
    return voices.LANGUAGES.get(language, "English")


def queries_for(topic: str, language: str, ask: Optional[Callable[[str, str], str]]) -> List[str]:
    """1-3 short encyclopedia queries for the brief. A whole sentence as a search query finds unrelated pages (which would then be
    cited as sources), so a small model writes proper queries; any failure falls back to the brief itself."""
    if ask is None:
        return [topic]
    try:
        text = ask(f"Write up to 3 short Wikipedia search queries (2 to 5 words each, in {_language_name(language)}) for the pages "
                   "needed to explain the user's request accurately. One query per line, no numbering, no quotes.", topic[:600])
    except Exception:
        return [topic]
    qs = [re.sub(r"^[\s\-*\d.)]+", "", ln).strip(" \"'") for ln in text.splitlines()]
    qs = [q for q in qs if 2 <= len(q) <= 80][:3]
    return qs or [topic]


WIKI_CONCURRENCY = 2   # Wikimedia answers 429 to bursts from one address: at most this many requests in flight (the whole process, all videos and sections)
_wiki_slots = threading.BoundedSemaphore(WIKI_CONCURRENCY)
WIKI_MIN_GAP_S = 0.3   # and no two requests start closer than this (a burst is what Wikimedia answers with a 429)
_cooldown_until = [0.0]   # a 429 with a long Retry-After: no request goes to Wikimedia until then (the whole process), the caller escalates or writes without notes
MAX_COOLDOWN_S = 120.0
_gap_lock = threading.Lock()
_last_start = [0.0]


def _spaced(clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
    with _gap_lock:
        wait = _last_start[0] + WIKI_MIN_GAP_S - clock()
        if wait > 0:
            sleep(wait)
        _last_start[0] = clock()
MIN_USEFUL_NOTES_CHARS = 1500   # under this the encyclopedia path counts as thin (the audit's threshold)


def _guarded(fetch: Callable[[str], Any], errors: Optional[List[Dict[str, Any]]], sleep: Callable[[float], None] = time.sleep) -> Callable[[str], Any]:
    """`fetch` with a bounded number of concurrent calls, retries with backoff on 429/5xx (Retry-After honoured, 3 tries, about 10 s at most), and every
    failure logged (url and status only, never any prompt text) and recorded in `errors`."""
    def get(url: str) -> Any:
        short_url = url.split("&", 1)[0][:160]
        if time.monotonic() < _cooldown_until[0]:
            if errors is not None:
                errors.append({"url": short_url, "status": 429, "attempt": 0, "error": "skipped: Wikimedia asked us to wait"})
            raise FetchError("skipped: rate limited", status=429)

        def failed(e: Exception, attempt: int) -> None:
            status = int(getattr(e, "status", 0) or 0)
            logging.warning("RESEARCH_FETCH_FAILED url=%s status=%s attempt=%s error=%s", url.split("&", 1)[0][:160], status, attempt, type(e).__name__)
            if errors is not None:
                errors.append({"url": url.split("&", 1)[0][:160], "status": status, "attempt": attempt, "retry_after": getattr(e, "retry_after", None), "error": str(e)[:80]})
        def spaced_fetch(u: str) -> Any:
            _spaced()
            return fetch(u)

        try:
            with _wiki_slots:
                return with_retry(spaced_fetch, url, on_fail=failed, sleep=sleep)
        except FetchError as e:
            if getattr(e, "status", 0) == 429:
                _cooldown_until[0] = max(_cooldown_until[0], time.monotonic() + min(MAX_COOLDOWN_S, getattr(e, "retry_after", None) or 5.0))
                logging.warning("RESEARCH_COOLDOWN seconds=%s", round(_cooldown_until[0] - time.monotonic()))
            raise
    return get


def gather_notes(topic: str, fetch: Callable[[str], Any] = fetch_json, language: str = "en",
                 ask: Optional[Callable[[str, str], str]] = None, errors: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, List[Dict[str, str]]]:
    """Returns (notes_text, sources). Never raises: a research failure must not fail the video. With QUALITY_FIXES (default) a fetch error is logged, retried
    with backoff and recorded in `errors`, and one bad page no longer ends the whole search; QUALITY_FIXES=0 is the old behaviour (errors swallowed)."""
    if not quality_fixes():
        return _gather_notes_legacy(topic, fetch, language, ask)
    fetch = _guarded(fetch, errors)
    notes: List[str] = []
    sources: List[Dict[str, str]] = []
    seen = set()
    try:
        api = api_for(language)
        titles: List[str] = []
        for q in queries_for(topic, language, ask):
            try:
                titles += [t for t in search_titles(q, limit=2, fetch=fetch, api=api) if t not in titles]
            except (FetchError, KeyError, ValueError, TypeError):
                continue   # logged and recorded by the guard; the other queries may still work
        for title in titles:
            if title in seen:
                continue
            seen.add(title)
            try:
                ex = fetch_extract(title, fetch=fetch, api=api)
            except (FetchError, KeyError, ValueError, TypeError):
                continue
            if len(ex["text"]) < 200:
                continue
            notes.append(f"## {ex['title']}\n{ex['text']}")
            sources.append({"title": ex["title"], "url": ex["url"], "publisher": "Wikipedia" if language == "en" else f"Wikipedia ({language})", "license": "CC BY-SA 4.0"})
            if sum(map(len, notes)) > MAX_NOTES_CHARS:
                break
    except Exception:   # never fail the video over research
        logging.exception("research failed")
    return "\n\n".join(notes)[:MAX_NOTES_CHARS], sources


def _gather_notes_legacy(topic: str, fetch: Callable[[str], Any], language: str, ask: Optional[Callable[[str, str], str]]) -> Tuple[str, List[Dict[str, str]]]:
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
