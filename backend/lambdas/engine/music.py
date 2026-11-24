"""Background music is a recording from the curated library (engine/library.py, made once with Lyria and checked by a person). The planner names the track and where it
changes; this module turns that into a timeline of segments and renders the full-length track with equal-power crossfades.

There is NO synthesised music: if the catalogue or a track is missing the video simply has no background music (narration and sound effects only). A synthesiser
was removed on 2026-11-24 because it sounded like a MIDI file.
"""
import logging
from typing import Any, Callable, Dict, Optional, Sequence

import numpy as np

from . import library

SR = 44100
XFADE_S = 2.6          # crossfade between two tracks
MAX_SEGMENTS = 3       # the first track plus at most two changes


def resolve(plan_music: Optional[Dict[str, Any]], scene_starts: Sequence[float], duration: float) -> Optional[Dict[str, Any]]:
    """Plan's music choice -> {"segments": [{"start", "track"}]} with times, or None when the plan chose no (valid) track.
    Beat numbers (1-based) in `changes` become the start time of that beat's scene."""
    pm = plan_music if isinstance(plan_music, dict) else {}
    track = str(pm.get("track") or "")
    if not library.ID_RE.match(track):
        return None
    segs = [{"start": 0.0, "track": track}]
    for ch in (pm.get("changes") or [])[: MAX_SEGMENTS - 1]:
        try:
            start = float(scene_starts[int(ch["beat"]) - 1])
            ct = str(ch.get("track") or "")
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            continue
        if library.ID_RE.match(ct) and start > segs[-1]["start"] + 12.0 and start < duration - 12.0:   # a change needs room on both sides
            segs.append({"start": round(start, 3), "track": ct})
    return {"segments": segs}


def render(spec: Optional[Dict[str, Any]], duration: float, track_loader: Optional[Callable[[str], Optional[np.ndarray]]] = None) -> Optional[np.ndarray]:
    """The full background track for `duration` seconds, stereo float32 (n, 2); changes crossfade. `track_loader(id)` -> stereo 44.1 kHz samples, or None when the
    recording is unavailable: that segment then plays another track of this video if there is one, else stays silent. Returns None when there is no music at all."""
    if not spec or not spec.get("segments") or track_loader is None:
        return None
    segs = spec["segments"]
    loaded: Dict[str, Optional[np.ndarray]] = {}
    for s in segs:
        if s["track"] not in loaded:
            try:
                got = track_loader(s["track"])
                loaded[s["track"]] = got if got is not None and got.shape[0] > SR else None
            except Exception:
                loaded[s["track"]] = None
    usable = [a for a in loaded.values() if a is not None]
    if not usable:
        logging.warning("none of the music tracks %s could be loaded: the video has no background music", sorted(loaded))
        return None
    n = int(duration * SR)
    out = np.zeros((n, 2), np.float32)
    ends = [s["start"] for s in segs[1:]] + [duration]
    for i, (s, end) in enumerate(zip(segs, ends)):
        lo = max(0.0, s["start"] - (XFADE_S / 2 if i > 0 else 0.0))
        hi = min(duration, end + (XFADE_S / 2 if i < len(segs) - 1 else 0.0))
        recorded = loaded.get(s["track"])
        if recorded is None:
            logging.warning("music track %s is unavailable: another track of this video stands in", s["track"])
            recorded = usable[0]
        seg = library.segment_audio(recorded, hi - lo)
        m = seg.shape[0]
        env = np.ones(m, np.float32)
        x = int(XFADE_S * SR)
        if i > 0:
            k = min(x, m)
            env[:k] = np.sin(np.linspace(0, np.pi / 2, k, dtype=np.float32))
        if i < len(segs) - 1:
            k = min(x, m)
            env[m - k:] *= np.cos(np.linspace(0, np.pi / 2, k, dtype=np.float32))
        a = int(lo * SR)
        b = min(n, a + m)
        out[a:b] += seg[: b - a] * env[: b - a, None]
    return np.clip(out, -1.0, 1.0)
