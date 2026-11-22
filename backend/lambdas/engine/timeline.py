"""Plan + measured audio durations -> timeline. Scene length comes from the narration, never from a guess."""
from typing import Any, Dict, List, Sequence

from .align import estimate_words
from .scenes import SCENES

LEAD = 0.40     # silence before the first word of a beat
TAIL = 0.55     # breathing room after the last word
MIN_SCENE = 2.8
END_HOLD = 1.4  # extra on the final scene for the outro fade
GOP_SECONDS = 2


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
                "id": f"s{i + 1}",
                "type": stype,
                "start": round(t, 4),
                "duration": round(dur, 4),
                "props": props,
                "words": [list(w) for w in estimate_words(beat["narration"], speech, lead=LEAD)],
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


def chunk_ranges(timeline: Dict[str, Any], chunk_seconds: int = 30) -> List[Dict[str, int]]:
    """Frame ranges [f0, f1) per chunk; every f0 is a multiple of the GOP so chunks concat with -c copy."""
    fps = int(timeline["fps"])
    gop = fps * GOP_SECONDS
    total = int(round(float(timeline["duration"]) * fps))
    per = max(gop, (chunk_seconds * fps // gop) * gop)
    out, f0, k = [], 0, 0
    while f0 < total:
        out.append({"k": k, "f0": f0, "f1": min(total, f0 + per)})
        f0 += per
        k += 1
    return out
