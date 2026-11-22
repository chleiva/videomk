"""Plan + measured audio durations -> timeline. Scene length comes from the narration, never from a guess."""
import hashlib
import json
from typing import Any, Dict, List, Sequence

from .align import estimate_words
from .scenes import SCENES

LEAD = 0.40     # silence before the first word of a beat
TAIL = 0.55     # breathing room after the last word
MIN_SCENE = 2.8
END_HOLD = 1.4  # extra on the final scene for the outro fade
GOP_SECONDS = 2
RENDER_VERSION = "2"  # bump when scene/renderer code changes: invalidates every cached segment
MIN_TAIL_CHUNK_S = 8.0


def build_timeline(
    plan: Dict[str, Any],
    beat_info: Sequence[Dict[str, Any]],
    *,
    video_id: str,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> Dict[str, Any]:
    """beat_info[i] = {'duration': speech seconds, 'asset': optional key for image scenes}."""
    scenes: List[Dict[str, Any]] = []
    t = 0.0
    chapters: List[Dict[str, Any]] = []
    for i, beat in enumerate(plan["beats"]):
        info = beat_info[i]
        speech = float(info["duration"])
        dur = max(MIN_SCENE, LEAD + speech + TAIL)
        if i == len(plan["beats"]) - 1:
            dur += END_HOLD
        stype = beat["scene"]["type"]
        props = dict(beat["scene"]["props"])
        if stype == "image":
            if info.get("asset"):
                props["asset"] = info["asset"]
                if info.get("credit"):
                    props["credit"] = info["credit"]
            else:  # scout found nothing usable: degrade to a clean title card instead of a hole
                stype, props = "title", {"title": props.get("alt") or props.get("image_query", ""), "subtitle": ""}
        # reveal cues, as seconds from scene start, for sfx; scenes without cues get none
        cues = SCENES[stype][1](props, dur)
        scenes.append(
            {
                "id": beat.get("id") or f"s{i + 1}",
                "type": stype,
                "start": round(t, 4),
                "duration": round(dur, 4),
                "props": props,
                "words": [list(w) for w in estimate_words(beat["narration"], speech, lead=LEAD)],
                "audio_key": info.get("audio_key"),
                "narration_offset": LEAD,
                "cues": [round(c, 3) for c in cues[:8]],
                "transition": "fade",
            }
        )
        if beat.get("chapter"):
            chapters.append({"start": round(t, 3), "title": beat["chapter"]})
        t += dur
    # segment boundaries must be a multiple of the GOP so chunks start on an IDR frame
    return {
        "version": 2,
        "video_id": video_id,
        "fps": fps,
        "width": width,
        "height": height,
        "theme": plan.get("theme", "midnight"),
        "mood": plan.get("mood", "calm"),
        "captions": True,
        "duration": round(t, 4),
        "scenes": scenes,
        "chapters": chapters,
        "title": plan.get("title", ""),
    }


def beat_info_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-beat measured media (written into the plan by the timeline step) in the shape build_timeline expects."""
    out = []
    for b in plan["beats"]:
        m = b.get("media") or {}
        out.append({"duration": m["duration"], "asset": m.get("asset"), "credit": m.get("credit"), "audio_key": m.get("audio_key")})
    return out


def _scene_fingerprint(sc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: sc.get(k) for k in ("id", "type", "duration", "props", "words", "transition")}


def chunk_plan(timeline: Dict[str, Any], target_seconds: float = 30, draft: bool = False) -> List[Dict[str, Any]]:
    """Group whole scenes into ~target_seconds chunks. Each chunk is content-addressed:

    hash = f(renderer version, format, theme, draft, its scenes, the scene before it (crossfade), whether it ends the video).
    It deliberately excludes absolute time, so after an edit every chunk the edit didn't touch hashes the same and its cached
    segment is reused; a segment is rendered from t=0 and stitched purely by duration.
    """
    scenes = timeline["scenes"]
    fps = int(timeline["fps"])
    groups: List[List[int]] = []
    cur: List[int] = []
    acc = 0.0
    for i, sc in enumerate(scenes):
        cur.append(i)
        acc += float(sc["duration"])
        if acc >= target_seconds:
            groups.append(cur)
            cur, acc = [], 0.0
    if cur:
        if groups and acc < MIN_TAIL_CHUNK_S:
            groups[-1].extend(cur)  # don't leave a sliver chunk
        else:
            groups.append(cur)
    out: List[Dict[str, Any]] = []
    prev_f1 = 0  # cumulative rounding: frame counts always sum to round(total*fps), so video and audio can't drift apart
    for k, g in enumerate(groups):
        lo, hi = g[0], g[-1] + 1
        f0 = prev_f1
        f1 = int(round((float(scenes[hi - 1]["start"]) + float(scenes[hi - 1]["duration"])) * fps))
        prev_f1 = max(f1, f0 + 1)
        h = hashlib.sha256(json.dumps({
            "v": RENDER_VERSION, "fps": fps, "w": timeline["width"], "h": timeline["height"], "theme": timeline.get("theme"),
            "captions": timeline.get("captions", True), "draft": draft,
            "scenes": [_scene_fingerprint(x) for x in scenes[lo:hi]],
            "lead": _scene_fingerprint(scenes[lo - 1]) if lo > 0 else None, "outro": hi == len(scenes),
        }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        out.append({"k": k, "lo": lo, "hi": hi, "frames": max(1, f1 - f0), "hash": h, "draft": draft})
    return out


def chunk_timeline(timeline: Dict[str, Any], lo: int, hi: int) -> Dict[str, Any]:
    """Self-contained timeline for scenes [lo, hi): offsets relative to the chunk start, plus the lead scene for the crossfade."""
    scenes = timeline["scenes"]
    base = float(scenes[lo]["start"])
    sub = [{**sc, "start": round(float(sc["start"]) - base, 6)} for sc in scenes[lo:hi]]
    return {
        "fps": timeline["fps"], "width": timeline["width"], "height": timeline["height"], "theme": timeline.get("theme", "midnight"),
        "captions": timeline.get("captions", True), "scenes": sub, "lead": scenes[lo - 1] if lo > 0 else None,
        "outro": hi == len(scenes), "duration": round(sum(float(x["duration"]) for x in sub), 6),
    }
