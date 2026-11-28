"""Paid dictation (speech to text), docs/SPEECH_TO_TEXT_2026-11-28.md: the provider interface and the OpenAI adapter.

  transcribe(audio, mime, languages, prompt) -> {text, language, seconds, cost_usd, model, provider}

The audio is never stored: it goes from the request to the provider and is dropped. A second provider (ElevenLabs Scribe v3) has a reserved slot in PROVIDERS and is NOT built.
Language hint (measured 2026-11-28 against the real API): ONE language goes in the plain `language` form field; two or more go in the `languages[]` field, repeated.
(`languages=["es"]` as a JSON string, single or not, is refused with invalid_value.)
Billing seconds = what the provider reports (`usage.seconds`, whole seconds), else the length the app claims, else an estimate from the size; never less than 1.
"""
import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger()

DEFAULT_MODEL = "gpt-transcribe"   # the only OpenAI transcription model without a shutdown date (the older ones end 2027-02-26)
RATE_PER_MINUTE_USD = {"gpt-transcribe": 0.0045}   # list price, pay as you go (OpenAI pricing page, read 2026-11-28); kept next to the code like tts.PER_CHAR
EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/aac": "m4a", "audio/mpeg": "mp3", "audio/mp3": "mp3",
       "audio/wav": "wav", "audio/x-wav": "wav", "audio/flac": "flac"}
BYTES_PER_SECOND_ESTIMATE = 3000   # 24 kbps Opus: only used when neither the provider nor the app says how long it is


class SttError(Exception):
    """`code`: bad_audio (the provider refused the file: 400), provider_unavailable (timeout, 5xx, no key: 502/503), provider_busy (429 from the provider)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


def rate_per_second(model: str) -> float:
    return RATE_PER_MINUTE_USD.get(model, RATE_PER_MINUTE_USD[DEFAULT_MODEL]) / 60.0


def cost_usd(seconds: float, model: str = DEFAULT_MODEL) -> float:
    return round(float(seconds) * rate_per_second(model), 6)


def mime_base(mime: str) -> str:
    return str(mime or "").split(";")[0].strip().lower()


def clean_languages(languages: Any) -> List[str]:
    """ISO 639-1 codes (two lower-case letters), at most 4, no repeats; anything else is dropped (a bad hint never stops a dictation)."""
    out: List[str] = []
    for x in (languages if isinstance(languages, (list, tuple)) else []):
        c = str(x or "").strip().lower().split("-")[0].split("_")[0]
        if len(c) == 2 and c.isalpha() and c not in out:
            out.append(c)
    return out[:4]


def multipart(fields: List[tuple], file_field: str, filename: str, content_type: str, data: bytes) -> tuple:
    boundary = uuid.uuid4().hex
    parts: List[bytes] = []
    for k, v in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def language_fields(languages: List[str]) -> List[tuple]:
    if len(languages) == 1:
        return [("language", languages[0])]
    return [("languages[]", c) for c in languages] if len(languages) >= 2 else []


class OpenAIProvider:
    name = "openai"
    URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 25.0, opener=None):
        self.model = model or os.environ.get("STT_MODEL") or DEFAULT_MODEL
        self._key, self.timeout, self._open = api_key, timeout, opener or urllib.request.urlopen

    def key(self) -> str:
        if not self._key:
            from common import secrets
            self._key = secrets.get_openai_api_key()
        if not self._key:
            raise SttError("provider_unavailable", "no key")
        return self._key

    def transcribe(self, audio: bytes, mime: str, languages: List[str], prompt: str = "", claimed_seconds: Optional[float] = None) -> Dict[str, Any]:
        fields: List[tuple] = [("model", self.model), ("response_format", "json")] + language_fields(languages)
        if prompt:
            fields.append(("prompt", prompt[:400]))
        body, ctype = multipart(fields, "file", f"audio.{EXT.get(mime_base(mime), 'webm')}", mime_base(mime) or "audio/webm", audio)
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={"Authorization": f"Bearer {self.key()}", "Content-Type": ctype})
        try:
            with self._open(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            status = e.code
            logger.warning("STT_PROVIDER_HTTP status=%s", status)   # never the body: it can echo the recognised words
            raise SttError("bad_audio" if status in (400, 413, 415, 422) else "provider_busy" if status == 429 else "provider_unavailable", f"http {status}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise SttError("provider_unavailable", type(e).__name__) from None
        text = str((data or {}).get("text") or "").strip()
        usage = (data or {}).get("usage") or {}
        secs = usage.get("seconds") if isinstance(usage.get("seconds"), (int, float)) and usage.get("seconds") > 0 else None
        if secs is None:
            secs = claimed_seconds if claimed_seconds and claimed_seconds > 0 else len(audio) / BYTES_PER_SECOND_ESTIMATE
        langs = (data or {}).get("languages")
        detected = langs[0].get("code") if isinstance(langs, list) and langs and isinstance(langs[0], dict) else (languages[0] if languages else None)
        secs = max(1.0, float(secs))
        return {"text": text, "language": detected, "seconds": secs, "cost_usd": cost_usd(secs, self.model), "model": self.model, "provider": self.name}


PROVIDERS = {"openai": OpenAIProvider}   # "elevenlabs": a Scribe v3 adapter with the same transcribe() signature goes here (reserved, not built)


def provider(name: Optional[str] = None):
    cls = PROVIDERS.get(name or os.environ.get("STT_PROVIDER") or "openai")
    if cls is None:
        raise SttError("provider_unavailable", "unknown provider")
    return cls()


def transcribe(audio: bytes, mime: str, languages: Any = None, prompt: str = "", *, claimed_seconds: Optional[float] = None, prov: Any = None) -> Dict[str, Any]:
    return (prov or provider()).transcribe(audio, mime, clean_languages(languages), prompt, claimed_seconds)
