"""Text-to-speech behind one interface so the provider is a config choice, not a rewrite.

Every provider returns mono float32 samples at SR (24 kHz). Providers are synthesised per beat
(one or two sentences), which gives exact scene timing for free, parallel synthesis in Step Functions,
and cheap re-synthesis of a single edited beat.
"""
import base64
import io
import json
import os
import subprocess
import urllib.request
import wave
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .audio import SR, trim_silence

DEFAULT_PROVIDER = os.environ.get("TTS_PROVIDER", "polly")


class TTSError(RuntimeError):
    pass


def _pcm16_to_float(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def _wav_bytes_to_float(raw: bytes) -> Tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(raw), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = _pcm16_to_float(w.readframes(w.getnframes()))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def _resample(a: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or a.size == 0:
        return a
    n = int(round(a.size * dst / src))
    return np.interp(np.linspace(0, a.size - 1, n), np.arange(a.size), a).astype(np.float32)


def _post_json(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:  # surface status only: bodies can echo prompts
        raise TTSError(f"TTS HTTP {e.code}") from e
    except Exception as e:
        raise TTSError(f"TTS request failed: {type(e).__name__}") from e


class MockTTS:
    """Deterministic stand-in (tests, local demos, CI): speech-shaped tone bursts, ~165 wpm."""

    name = "mock"

    def __init__(self) -> None:
        self.speed = max(0.5, float(os.environ.get("MOCK_TTS_SPEED", "1")))  # >1 = faster speech (shorter test videos)

    def synth(self, text: str, voice: str = "", style: str = "") -> np.ndarray:
        words = text.split()
        out: List[np.ndarray] = []
        for i, w in enumerate(words):
            dur = (0.16 + 0.045 * len(w) + (0.22 if w[-1:] in ",;:" else 0.4 if w[-1:] in ".!?" else 0.0)) / self.speed
            n = int(dur * SR)
            t = np.arange(n, dtype=np.float32) / SR
            f0 = 110 + (sum(map(ord, w)) % 70)
            env = np.sin(np.pi * np.clip(t / max(dur - 0.12, 0.05), 0.0, 1.0))
            voiced = (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t) + 0.25 * np.sin(2 * np.pi * 3 * f0 * t)) * env * 0.25
            out.append(voiced.astype(np.float32))
        return np.concatenate(out) if out else np.zeros(int(0.2 * SR), np.float32)


def _decode(raw: bytes, sr: int) -> np.ndarray:
    """Compressed audio (MP3, OGG) -> mono float32 at `sr`, through the ffmpeg the render already ships."""
    from .media import ffmpeg_bin

    proc = subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "pipe:1"],
                          input=raw, capture_output=True, timeout=120)
    if proc.returncode != 0 or not proc.stdout:
        raise TTSError("could not decode the speech audio")
    return _pcm16_to_float(proc.stdout)


class PollyTTS:
    """Amazon Polly: no API key (the Lambda's IAM role is the credential), in-account, no data leaves AWS.

    Polly has no style prompt, so `style` is ignored. Voice defaults to Ruth (en-US).

    `rate` is the sample rate asked of Polly. The neural and generative engines make speech at 24 kHz, but Polly's raw PCM stops at 16 kHz: everything above
    8 kHz (the air of an s, an f, a breath) is cut, and the voice sounds duller than the one in Polly's console. Measured on 2026-11-27: PCM has nothing above
    8 kHz; the same request as MP3 at 24 kHz carries speech up to about 11 kHz and is otherwise the same waveform (docs/VOICE_QUALITY_IT_ES_2026-11-27.md).
    So at 24000 the audio is asked as MP3 and decoded (no resampling: 24 kHz is SR); at 16000, what plans made before `rate` was recorded keep, it is the
    raw PCM as always, resampled to SR.
    """

    name = "polly"
    PCM_RATE = 16000     # the most Polly gives as raw PCM
    FULL_RATE = 24000    # what the neural and generative engines really make; only as MP3 or OGG
    # $/character, list prices (verify): standard $4/M, neural $16/M, generative $30/M, long-form $100/M
    PER_CHAR = {"standard": 0.000004, "neural": 0.000016, "generative": 0.00003, "long-form": 0.0001}

    def __init__(self, client: Any = None, region: Optional[str] = None, engine: str = "neural", rate: int = PCM_RATE):
        self._client, self._region, self.engine = client, region, engine
        self.rate = self.FULL_RATE if int(rate or 0) >= self.FULL_RATE else self.PCM_RATE

    @property
    def cost_per_char(self) -> float:
        return self.PER_CHAR.get(self.engine, 0.00003)

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("polly", region_name=self._region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
        return self._client

    def _ask(self, text: str, voice: str, fmt: str, rate: int) -> bytes:
        try:
            resp = self.client.synthesize_speech(Text=text[:2900], OutputFormat=fmt, SampleRate=str(rate), VoiceId=voice or "Ruth", Engine=self.engine, TextType="text")
            raw = resp["AudioStream"].read()
        except Exception as e:  # botocore errors can echo request details: surface the type only
            raise TTSError(f"Polly request failed: {type(e).__name__}") from e
        if not raw:
            raise TTSError("Polly returned no audio")
        return raw

    def synth(self, text: str, voice: str = "", style: str = "") -> np.ndarray:
        if self.rate >= self.FULL_RATE:
            raw = self._ask(text, voice, "mp3", self.FULL_RATE)
            try:
                return _resample(_decode(raw, self.FULL_RATE), self.FULL_RATE, SR)
            except Exception as e:  # never lose a video to a decoder: say it loudly and take the narrow-band audio (engine_selftest checks decode_mp3)
                print(f"polly_fullband_fallback: {type(e).__name__}: narrow-band PCM used for this beat")
        return _resample(_pcm16_to_float(self._ask(text, voice, "pcm", self.PCM_RATE)), self.PCM_RATE, SR)


class OpenAITTS:
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-tts"):
        self.key, self.model = api_key, model

    def synth(self, text: str, voice: str = "", style: str = "") -> np.ndarray:
        body: Dict[str, Any] = {"model": self.model, "voice": voice or "alloy", "input": text, "response_format": "wav"}
        if style:
            body["instructions"] = style
        raw = _post_json("https://api.openai.com/v1/audio/speech", {"Authorization": f"Bearer {self.key}"}, body)
        a, sr = _wav_bytes_to_float(raw)
        return _resample(a, sr, SR)


class GeminiTTS:
    """Gemini TTS via generateContent: returns base64 raw PCM (s16le, 24 kHz, mono)."""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-preview-tts"):
        self.key, self.model = api_key, model

    def synth(self, text: str, voice: str = "", style: str = "") -> np.ndarray:
        prompt = f"{style}: {text}" if style else text
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or "Kore"}}},
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        raw = _post_json(url, {"x-goog-api-key": self.key}, body)  # header, not ?key=: keeps the key out of URLs/logs
        try:
            data = json.loads(raw)
            b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        except (KeyError, IndexError, ValueError) as e:
            raise TTSError("Gemini TTS returned no audio") from e
        return _pcm16_to_float(base64.b64decode(b64))


def get_provider(name: Optional[str] = None, api_key: str = "", cfg: Optional[Dict[str, Any]] = None) -> Any:
    name = (name or DEFAULT_PROVIDER).lower()
    if name == "mock":
        return MockTTS()
    if name == "polly":  # plans made before the engine (or the sample rate) was recorded keep the neural engine in the stack's own region (and 16 kHz PCM)
        cfg = cfg or {}
        return PollyTTS(region=cfg.get("region") or None, engine=cfg.get("engine") or "neural", rate=int(cfg.get("rate") or PollyTTS.PCM_RATE))
    if name == "openai":
        return OpenAITTS(api_key)
    if name == "gemini":
        return GeminiTTS(api_key)
    raise ValueError(f"unknown TTS provider: {name}")


def synth_beat(provider: Any, text: str, voice: str = "", style: str = "") -> np.ndarray:
    """Synthesize one beat and trim silence so scene timing hugs the speech."""
    samples = provider.synth(text, voice=voice, style=style)
    return trim_silence(samples.astype(np.float32), SR)
