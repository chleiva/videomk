"""Helpers for testing scene elements: render one scene through the real Renderer and compare frames."""
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from engine.renderer import Renderer  # noqa: E402
from engine.theme import THEMES  # noqa: E402


def make_renderer(stype: str, props: Dict[str, Any], dur: float = 8.0, theme: str = "midnight", words: Optional[List[Any]] = None, captions: bool = False,
                  image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, draft: bool = True, aspect: str = "16:9", resolution: str = "1080p",
                  clip_loader: Optional[Callable[[str], Any]] = None):
    from engine.frame import Frame

    fr = Frame.parse(aspect, resolution)
    sc = {"id": "t", "type": stype, "start": 0.0, "duration": dur, "props": props, "words": words or [], "transition": "none"}
    tl = {"scenes": [sc], "theme": theme, "captions": captions, "duration": dur, "width": fr.width, "height": fr.height, "fps": 30, "outro": False,
          "frame": {"aspect": fr.aspect, "resolution": fr.resolution}}
    return Renderer(tl, image_loader=image_loader, draft=draft, clip_loader=clip_loader), sc


def render(stype: str, props: Dict[str, Any], lt: float, dur: float = 8.0, theme: str = "midnight", words: Optional[List[Any]] = None, captions: bool = False,
           image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, draft: bool = True, aspect: str = "16:9", resolution: str = "1080p",
           clip_loader: Optional[Callable[[str], Any]] = None) -> Image.Image:
    """One frame (RGB, half size when draft) of a scene `lt` seconds into a scene of length `dur`, exactly as the renderer draws it, in the given aspect."""
    r, sc = make_renderer(stype, props, dur, theme, words, captions, image_loader, draft, aspect, resolution, clip_loader)
    return r._draw_spec(sc, lt)


def changed(a: Image.Image, b: Image.Image, threshold: int = 24) -> float:
    """Share of pixels that differ clearly between two frames of the same size (0..1)."""
    x, y = np.asarray(a.convert("RGB"), np.int16), np.asarray(b.convert("RGB"), np.int16)
    return float((np.abs(x - y).max(axis=2) > threshold).mean())


def themes() -> List[str]:
    return list(THEMES)


def blank(theme: str = "midnight", lt: float = 1.0, dur: float = 8.0) -> Image.Image:
    """The background alone (what a scene shows when it has drawn nothing yet)."""
    from engine import scenes
    scenes.SCENES["__blank__"] = (lambda *a, **k: None, lambda p, d: [])
    try:
        return render("__blank__", {}, lt, dur, theme)
    finally:
        scenes.SCENES.pop("__blank__", None)
