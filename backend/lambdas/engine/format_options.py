"""The creation options as plain data (docs/CREATE_API.md): what a person may choose, what is ready, and the exact picture size of each format.

Pure Python, no dependencies, safe to import from the API Lambdas as well as from the engine. The geometry itself lives in `engine/frame.py` (`Frame`);
this module is the options layer on top: ids, readiness settings, capabilities and what is stored in a plan or timeline (`frame_dict`).
"""
import os
from typing import Any, Dict, List, Optional, Tuple

from .frame import Frame

MAX_PHOTOS = 100   # keep equal to common.photo_ids.MAX_PHOTOS (a test checks)

DEFAULT_ASPECT = "16:9"
DEFAULT_RESOLUTION = "1080p"
DEFAULT_PLATFORM = "other"

ASPECTS: List[Dict[str, str]] = [
    {"id": "16:9", "label": "Landscape"},
    {"id": "9:16", "label": "Vertical"},
    {"id": "1:1", "label": "Square"},
    {"id": "4:5", "label": "Portrait"},
]
RESOLUTIONS: List[Dict[str, str]] = [{"id": "720p", "label": "720p"}, {"id": "1080p", "label": "1080p"}]
LANGUAGE_LABELS = {"en": "English", "es": "Español"}   # every language the engine can voice; READY_LANGUAGES picks which are offered

# aspect -> (width units, height units); the SHORT side is 720 or 1080 pixels
_RATIOS: Dict[str, Tuple[int, int]] = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
_SHORT = {"720p": 720, "1080p": 1080}

# What each platform is for. The note is shown under the chips; `aspect`/`resolution` are the recommendation, never a restriction.
PLATFORMS: List[Dict[str, str]] = [
    {"id": "youtube", "label": "YouTube", "aspect": "16:9", "resolution": "1080p", "note": "Landscape 16:9 · 1080p"},
    {"id": "shorts", "label": "YouTube Shorts", "aspect": "9:16", "resolution": "1080p", "note": "Vertical 9:16 · 1080p"},
    {"id": "tiktok", "label": "TikTok", "aspect": "9:16", "resolution": "1080p", "note": "Vertical 9:16 · 1080p"},
    {"id": "reels", "label": "Instagram Reels", "aspect": "9:16", "resolution": "1080p", "note": "Vertical 9:16 · 1080p"},
    {"id": "instagram_feed", "label": "Instagram feed", "aspect": "4:5", "resolution": "1080p", "note": "Portrait 4:5 · 1080p"},
    {"id": "linkedin", "label": "LinkedIn", "aspect": "16:9", "resolution": "1080p", "note": "Landscape 16:9 · 1080p (1:1 and 4:5 also work well)"},
    {"id": "x", "label": "X", "aspect": "16:9", "resolution": "1080p", "note": "Landscape 16:9 · 1080p"},
    {"id": "other", "label": "Just a video", "aspect": "16:9", "resolution": "1080p", "note": "Landscape 16:9 · 1080p"},
]
PLATFORM_IDS = tuple(p["id"] for p in PLATFORMS)
ASPECT_IDS = tuple(a["id"] for a in ASPECTS)
RESOLUTION_IDS = tuple(r["id"] for r in RESOLUTIONS)


def _csv(name: str, default: str) -> List[str]:
    raw = os.environ.get(name)
    raw = default if raw is None or not raw.strip() else raw
    return [x.strip() for x in raw.split(",") if x.strip()]


def ready_aspects() -> List[str]:
    """Server setting READY_ASPECTS (comma list, default 16:9): the formats the layouts are ready for. Unknown ids are ignored."""
    return [a for a in _csv("READY_ASPECTS", DEFAULT_ASPECT) if a in ASPECT_IDS]


def beta_aspects() -> List[str]:
    """Server setting BETA_ASPECTS: ready formats that still use a framed fallback for some scenes."""
    return [a for a in _csv("BETA_ASPECTS", "") if a in ASPECT_IDS]


def ready_languages() -> List[str]:
    """Server setting READY_LANGUAGES (comma list, default en,es). Unknown languages are ignored."""
    return [x for x in _csv("READY_LANGUAGES", "en,es") if x in LANGUAGE_LABELS]


def frame_size(aspect: Optional[str] = None, resolution: Optional[str] = None) -> Tuple[int, int]:
    """(width, height) in pixels. The short side is 720 or 1080; the long side follows the ratio. Unknown or absent values mean 16:9 1080p."""
    f = Frame.parse(aspect if aspect in _RATIOS else None, resolution if resolution in _SHORT else None)
    return f.width, f.height


def orientation(aspect: Optional[str]) -> str:
    return Frame.parse(aspect if aspect in _RATIOS else None).orientation


def frame_dict(aspect: Optional[str] = None, resolution: Optional[str] = None, platform: Optional[str] = None) -> Dict[str, Any]:
    """What is stored in the plan and the timeline (`frame`) so an edit re-renders the video at its own size."""
    aspect = aspect if aspect in _RATIOS else DEFAULT_ASPECT
    resolution = resolution if resolution in _SHORT else DEFAULT_RESOLUTION
    w, h = frame_size(aspect, resolution)
    return {"aspect": aspect, "resolution": resolution, "width": w, "height": h, "orientation": orientation(aspect), "platform": platform if platform in PLATFORM_IDS else DEFAULT_PLATFORM}


def frame_of(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The frame of a stored plan or timeline; documents made before formats existed have none and mean 16:9 1080p."""
    f = (doc or {}).get("frame")
    if isinstance(f, dict):
        return frame_dict(f.get("aspect"), f.get("resolution"), f.get("platform"))
    return frame_dict()


def capabilities() -> Dict[str, Any]:
    """The body of GET /users/{user}/capabilities."""
    ready, beta = set(ready_aspects()), set(beta_aspects())
    langs = ready_languages()
    return {
        "aspects": [{"id": a["id"], "label": a["label"], "ready": a["id"] in ready, "beta": a["id"] in ready and a["id"] in beta} for a in ASPECTS],
        "resolutions": [dict(r) for r in RESOLUTIONS],
        "platforms": [dict(p) for p in PLATFORMS],
        "languages": [{"id": x, "label": LANGUAGE_LABELS[x]} for x in langs],
        "lengths": {"min_minutes": 1, "max_minutes": 12},
        "max_photos": MAX_PHOTOS,
        "intake": os.environ.get("INTAKE_ENABLED") == "1",
    }
