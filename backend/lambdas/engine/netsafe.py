"""Small, defensive HTTP helpers for fetching third-party content (images, search APIs)."""
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

# Wikimedia and Openverse ask automated clients to identify themselves; set HTTP_USER_AGENT per deployment (the context key `httpUserAgent`: a
# descriptive agent WITH a contact, for example "videomk/1.0 (https://example.com; contact@example.com)"; the owner supplies it).
# Without it the default is "videomk/1.0" (identifying, no invented contact). QUALITY_FIXES=0 restores the old default.


def quality_fixes() -> bool:
    return os.environ.get("QUALITY_FIXES", "1").strip().lower() not in ("0", "off", "false", "no")


def user_agent() -> str:
    """The User-Agent of EVERY outbound research and stock request: HTTP_USER_AGENT when set, else an identifying default."""
    return os.environ.get("HTTP_USER_AGENT") or ("videomk/1.0" if quality_fixes() else "explainer-engine/2.0")


USER_AGENT = user_agent()


class FetchError(RuntimeError):
    """`status` is the HTTP status when the server answered (0 for a network failure or a refused URL); `retry_after` the server's Retry-After seconds."""

    def __init__(self, msg: str = "", status: int = 0, retry_after: Optional[float] = None):
        super().__init__(msg)
        self.status = status
        self.retry_after = retry_after


def _check_public_https(url: str) -> None:
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise FetchError("only https URLs are allowed")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError("dns failure") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("refusing non-public address")


class _NoCrossSchemeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_https(newurl)  # every hop must also be public https
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_NoCrossSchemeRedirect)


def fetch_bytes(url: str, *, max_bytes: int = 15_000_000, timeout: int = 20, headers: Optional[Dict[str, str]] = None) -> bytes:
    _check_public_https(url)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), **(headers or {})})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
    except FetchError:
        raise
    except urllib.error.HTTPError as e:   # status only: the status is what a caller needs to decide to retry
        ra = None
        try:
            ra = float(e.headers.get("Retry-After")) if e.headers and e.headers.get("Retry-After") else None
        except (TypeError, ValueError):
            ra = None
        raise FetchError(f"fetch failed: HTTPError {e.code}", status=int(e.code), retry_after=ra) from e
    except Exception as e:
        raise FetchError(f"fetch failed: {type(e).__name__}") from e
    if len(data) > max_bytes:
        raise FetchError("response too large")
    return data


def fetch_json(url: str, *, timeout: int = 15, headers: Optional[Dict[str, str]] = None) -> Any:
    return json.loads(fetch_bytes(url, max_bytes=2_000_000, timeout=timeout, headers={"Accept": "application/json", **(headers or {})}))


# ----------------------------------------------------------------------------- retries (QUALITY_FIXES)
def retryable(e: Exception) -> bool:
    """429 and 5xx (and a network failure with no status) are worth another try; a 404, a refused URL or an oversized body are not."""
    if not isinstance(e, FetchError):
        return False
    st = int(getattr(e, "status", 0) or 0)
    if st:
        return st == 429 or st >= 500
    return str(e).startswith("fetch failed") or str(e) == "dns failure"


def with_retry(fn: Callable[..., Any], *args: Any, max_tries: int = 3, base_delay: float = 0.5, max_wait: float = 4.0, max_total_s: float = 10.0,
               sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic, on_fail: Optional[Callable[[Exception, int], None]] = None,
               **kwargs: Any) -> Any:
    """fn(*args, **kwargs), at most `max_tries` times with exponential backoff, honouring Retry-After (capped at `max_wait`), and never past `max_total_s`.
    `on_fail(error, attempt)` sees every failure (for the log); the last error is raised."""
    t0 = clock()
    for attempt in range(1, max_tries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if on_fail:
                on_fail(e, attempt)
            if attempt >= max_tries or not retryable(e):
                raise
            ra = getattr(e, "retry_after", None)
            wait = min(max_wait, ra if ra is not None else base_delay * (2 ** (attempt - 1)))
            if clock() - t0 + wait > max_total_s:
                raise
            sleep(max(0.0, wait))
