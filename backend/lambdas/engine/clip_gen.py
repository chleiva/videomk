"""The video provider behind library clips on demand (docs/CLIPS_ON_DEMAND.md). One small interface, so the provider is a choice, not a dependency:

    Provider.generate(prompt, seconds=8, aspect="16:9", timeout=150) -> {"mp4": bytes, "model": str, "seconds": float}     or raises GenError

`GeminiOmni` calls Google's Gemini API (`POST /v1beta/interactions`, model gemini-omni-1.2-flash, 720p: aistudio.google.com/docs/omni, read 2026-11-27) over plain HTTPS.
The key is never logged and never part of an error text. `Mock` is for tests and dry runs. Only the general brief's prompt is ever sent: nothing of the customer.
"""
import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

API = "https://generativelanguage.googleapis.com/v1beta"
KEY_PARAM = "/videomk/gemini_api_key"   # SecureString; the beat function may already read /videomk/*_api_key
MAX_BYTES = 60_000_000
USD_PER_M = {"video": 12.0, "text": 9.0, "input": 1.5}   # Google's price list for gemini-omni-1.2-flash, read 2026-11-27 (aistudio.google.com/docs/pricing)


def usage_usd(usage: Any) -> Optional[float]:
    """What the provider's own token counts come to at the list price: video output, the model's 'thought' tokens (counted as text output: measured about 1,100 a
    call, one cent) and the prompt. None when the answer carried no usage. For the ledger and the report; the budgets are charged the configured price."""
    try:
        if not isinstance(usage, dict):
            return None
        video = sum(int(m.get("tokens") or 0) for m in usage.get("output_tokens_by_modality") or [] if m.get("modality") == "video")
        other = max(0, int(usage.get("total_output_tokens") or 0) - video) + int(usage.get("total_thought_tokens") or 0)
        return round((video * USD_PER_M["video"] + other * USD_PER_M["text"] + int(usage.get("total_input_tokens") or 0) * USD_PER_M["input"]) / 1e6, 6)
    except Exception:
        return None
ASPECTS = ("16:9", "9:16")


class GenError(Exception):
    """`billed`: could the provider have charged for this call? (False only when it refused before making anything: bad request, blocked prompt, no key, quota.)
    `kind`: 'timeout' | 'blocked' | 'auth' | 'quota' | 'bad_request' | 'provider' | 'no_video'."""

    def __init__(self, kind: str, message: str = "", *, billed: bool = True):
        super().__init__(f"{kind}: {message}"[:300])
        self.kind, self.billed = kind, billed


class Provider:
    name = ""
    model = ""

    def generate(self, prompt: str, *, seconds: int = 8, aspect: str = "16:9", timeout: float = 150.0) -> Dict[str, Any]:
        raise NotImplementedError


class Mock(Provider):
    """Returns the bytes it was given (or raises what it was told to), and remembers every call."""
    name = "mock"

    def __init__(self, mp4: bytes = b"", *, error: Optional[Exception] = None, delay: float = 0.0, model: str = "mock-video-1"):
        self.mp4, self.error, self.delay, self.model, self.calls = mp4, error, delay, model, []

    def generate(self, prompt, *, seconds=8, aspect="16:9", timeout=150.0):
        self.calls.append({"prompt": prompt, "seconds": seconds, "aspect": aspect, "timeout": timeout})
        if self.delay:
            if self.delay > timeout:
                time.sleep(min(timeout, 0.2))
                raise GenError("timeout", "mock")
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return {"mp4": self.mp4, "model": self.model, "seconds": float(seconds)}


def _key() -> str:
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k:   # the function: the SecureString in SSM, read at EVERY call and never kept (common.secrets caches per container): the owner rotates the key and the next call uses the new one. A laptop: the environment
        try:
            import boto3
            k = str(boto3.client("ssm").get_parameter(Name=os.environ.get("CLIPS_KEY_PARAM") or KEY_PARAM, WithDecryption=True)["Parameter"]["Value"] or "").strip()
        except Exception as e:
            logging.info("clip provider key unavailable (%s)", type(e).__name__)
            k = ""
    return k


class GeminiOmni(Provider):
    name = "gemini"

    def __init__(self, model: str = "gemini-omni-1.2-flash", *, key: Optional[str] = None, opener: Optional[Callable[..., Any]] = None, resolution: str = "720p"):
        self.model, self._key, self._open, self.resolution = model, key, opener or urllib.request.urlopen, resolution

    def _call(self, method: str, url: str, body: Optional[Dict[str, Any]], timeout: float, key: str, raw: bool = False) -> Any:
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with self._open(req, timeout=max(1.0, timeout)) as res:
                data = res.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = e.read(2000).decode("utf-8", "replace")
            except Exception:
                pass
            msg = re.sub(r"\s+", " ", text)[:200]
            if e.code in (401, 403):
                raise GenError("auth", f"HTTP {e.code} {msg}", billed=False) from None
            if e.code == 429:
                raise GenError("quota", f"HTTP 429 {msg}", billed=False) from None
            if e.code == 400:
                low = msg.lower()
                raise GenError("blocked" if any(w in low for w in ("safety", "policy", "blocked", "prohibited")) else "bad_request", f"HTTP 400 {msg}", billed=False) from None
            raise GenError("provider", f"HTTP {e.code} {msg}", billed=e.code >= 500) from None
        except (TimeoutError, OSError) as e:   # urllib wraps socket timeouts in URLError (an OSError)
            if "timed out" in str(e).lower() or isinstance(e, TimeoutError):
                raise GenError("timeout", "no answer in time") from None
            raise GenError("provider", type(e).__name__, billed=False) from None
        if len(data) > MAX_BYTES:
            raise GenError("provider", "answer too large")
        return data if raw else json.loads(data)

    def generate(self, prompt, *, seconds=8, aspect="16:9", timeout=150.0):
        key = self._key if self._key is not None else _key()
        if not key:
            raise GenError("auth", "no provider key configured", billed=False)
        if aspect not in ASPECTS:
            raise GenError("bad_request", "aspect", billed=False)
        t_end = time.time() + timeout
        body = {"model": self.model, "input": prompt, "background": False, "store": True, "stream": False,   # the provider requires store=true for URI delivery (answered so on 2026-11-27)
                "response_format": {"type": "video", "aspect_ratio": aspect, "duration": f"{int(seconds)}s", "resolution": self.resolution, "delivery": "uri"}}
        res = self._call("POST", f"{API}/interactions", body, timeout, key)
        status = str(res.get("status") or "")
        video = None
        for step in res.get("steps") or []:
            if step.get("type") == "model_output":
                for part in step.get("content") or []:
                    if part.get("type") == "video":
                        video = part
        if video is None:
            blocked = status in ("blocked", "failed", "cancelled") or "safety" in json.dumps(res)[:4000].lower()
            raise GenError("blocked" if blocked else "no_video", f"status {status or 'unknown'}", billed=not blocked)
        if video.get("data"):
            mp4 = base64.b64decode(video["data"])
        else:
            uri = str(video.get("uri") or "")
            m = re.search(r"/files/([A-Za-z0-9_-]+)", uri)
            if not uri.startswith(API + "/") or not m:
                raise GenError("no_video", "unexpected file location")
            while True:   # the file is not guaranteed ready when the interaction returns
                state = self._call("GET", f"{API}/files/{m.group(1)}", None, max(1.0, t_end - time.time()), key).get("state")
                state = state.get("name") if isinstance(state, dict) else state
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise GenError("provider", "file failed")
                if time.time() + 2 > t_end:
                    raise GenError("timeout", "file not ready in time")
                time.sleep(2)
            mp4 = self._call("GET", f"{API}/files/{m.group(1)}:download?alt=media", None, max(5.0, t_end - time.time()), key, raw=True)
        if len(mp4) < 10_000 or mp4[4:8] != b"ftyp":
            raise GenError("no_video", "not an MP4")
        logging.info("clip provider %s made %d bytes", self.model, len(mp4))
        return {"mp4": mp4, "model": self.model, "seconds": float(seconds), "usage": res.get("usage")}


_override: Optional[Provider] = None


def set_provider(p: Optional[Provider]) -> None:
    global _override
    _override = p


def provider(model: str) -> Provider:
    return _override if _override is not None else GeminiOmni(model)
