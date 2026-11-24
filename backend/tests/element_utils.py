"""Helpers for testing scene elements: render one scene through the real Renderer and compare frames."""
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from engine.renderer import Renderer  # noqa: E402
from engine.theme import THEMES  # noqa: E402


def render(stype: str, props: Dict[str, Any], lt: float, dur: float = 8.0, theme: str = "midnight", words: Optional[List[Any]] = None, captions: bool = False,
           image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, draft: bool = True) -> Image.Image:
    """One frame (RGB, 960x540 when draft) of a scene `lt` seconds into a scene of length `dur`, exactly as the renderer draws it."""
    sc = {"id": "t", "type": stype, "start": 0.0, "duration": dur, "props": props, "words": words or [], "transition": "none"}
    tl = {"scenes": [sc], "theme": theme, "captions": captions, "duration": dur, "width": 1920, "height": 1080, "fps": 30, "outro": False}
    return Renderer(tl, image_loader=image_loader, draft=draft)._draw_spec(sc, lt)


def changed(a: Image.Image, b: Image.Image, threshold: int = 24) -> float:
    """Share of pixels that differ clearly between two frames of the same size (0..1)."""
    x, y = np.asarray(a.convert("RGB"), np.int16), np.asarray(b.convert("RGB"), np.int16)
    return float((np.abs(x - y).max(axis=2) > threshold).mean())


def themes() -> List[str]:
    return list(THEMES)
