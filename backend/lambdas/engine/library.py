"""The curated background-music library: tracks made once with Lyria (see scripts/music_library.py), checked by a person, stored in S3, and chosen by the planner
from their descriptions. The planner says which track plays and where it changes; this module finds, decodes and fits the audio. If the catalogue or a track is
missing the engine falls back to the procedural synth (engine/music.py), so a video is never silent because of the library.

S3 layout (in the assets bucket): music/catalog.json and music/<id>.mp3
catalog.json: {"version": 1, "tracks": [{"id", "title", "description", "mood": [..], "energy": 1-5, "bpm", "key", "seconds", "file"}]}
"""
import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import media

SR = 44100
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
CATALOG_KEY = "music/catalog.json"
CATALOG_TTL_S = 300
TARGET_RMS = 0.09        # the loudness the synth tracks have: library tracks are levelled to it so the mix does not jump between sources
LOOP_XFADE_S = 3.0

_cache: Dict[str, Any] = {"at": 0.0, "tracks": []}


def track_key(track_id: str) -> str:
    if not ID_RE.match(track_id or ""):
        raise ValueError("bad track id")
    return f"music/{track_id}.mp3"


def clean_catalog(raw: Any) -> List[Dict[str, Any]]:
    """Only well-formed tracks with a usable id and description reach the planner."""
    out: List[Dict[str, Any]] = []
    for t in (raw or {}).get("tracks", []) if isinstance(raw, dict) else []:
        if not isinstance(t, dict) or not ID_RE.match(str(t.get("id", ""))) or not str(t.get("description", "")).strip():
            continue
        try:
            secs = float(t.get("seconds") or 0)
        except (TypeError, ValueError):
            secs = 0.0
        out.append({"id": t["id"], "title": str(t.get("title") or t["id"])[:60], "description": " ".join(str(t["description"]).split())[:400],
                    "mood": [str(m)[:20] for m in (t.get("mood") or [])][:5], "energy": min(5, max(1, int(t.get("energy") or 3))),
                    "bpm": int(t["bpm"]) if str(t.get("bpm", "")).isdigit() else None, "key": str(t.get("key") or "")[:12], "seconds": round(secs, 1)})
    return out


def load_catalog(get_json: Callable[[str], Any], now: Callable[[], float] = time.time) -> List[Dict[str, Any]]:
    """The catalogue from S3, cached for a few minutes; [] when there is none (then the planner is offered the synth styles instead)."""
    if now() - _cache["at"] < CATALOG_TTL_S:
        return _cache["tracks"]
    try:
        tracks = clean_catalog(get_json(CATALOG_KEY))
    except Exception:
        tracks = []
    _cache.update(at=now(), tracks=tracks)
    return tracks


def prompt_list(tracks: List[Dict[str, Any]]) -> str:
    return "\n".join(f"  {t['id']} ({t['seconds']:.0f} s, energy {t['energy']}{', ' + str(t['bpm']) + ' bpm' if t['bpm'] else ''}): {t['description']}" for t in tracks)


def decode(path: str) -> np.ndarray:
    """Any audio file -> float32 stereo (n, 2) at 44.1 kHz."""
    proc = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", path, "-vn", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, timeout=120)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("could not decode the track: " + proc.stderr[-200:].decode("utf8", "replace"))
    return np.frombuffer(proc.stdout, dtype="<f4").reshape(-1, 2).copy()


def level(samples: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(samples ** 2))) or 1.0
    out = samples * (TARGET_RMS / rms)
    peak = float(np.max(np.abs(out))) or 1.0
    return (out * min(1.0, 0.95 / peak)).astype(np.float32)


def fit(samples: np.ndarray, seconds: float, xfade: float = LOOP_XFADE_S) -> np.ndarray:
    """`seconds` of music from a track: a long one is cut from its start, a short one loops with equal-power crossfades (no click at the join)."""
    n = int(seconds * SR)
    if samples.shape[0] >= n:
        return samples[:n]
    x = min(int(xfade * SR), samples.shape[0] // 3)
    out = samples.copy()
    fade_in = np.sin(np.linspace(0, np.pi / 2, x, dtype=np.float32))[:, None]
    fade_out = np.cos(np.linspace(0, np.pi / 2, x, dtype=np.float32))[:, None]
    while out.shape[0] < n:
        head = samples[:x] * fade_in
        out[-x:] = out[-x:] * fade_out + head
        out = np.concatenate([out, samples[x:]], axis=0)
    return out[:n]


def segment_audio(track: np.ndarray, seconds: float) -> np.ndarray:
    return fit(level(track), seconds)
