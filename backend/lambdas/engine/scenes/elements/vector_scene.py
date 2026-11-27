"""`vector_scene`: a flat-cartoon scene made of separate vector layers that drift at different speeds (parallax), with swaying leaves, drifting clouds and a slow push-in.
HIDDEN: the planner does not list it yet (prototype, docs/VECTOR_SCENES.md); a scene only appears when its props name one of the bundled scene folders."""
from typing import Any, Dict

from PIL import Image

from ... import vector_scene as vs
from ...canvas import Canvas
from ...theme import Theme
from ..base import SceneCtx
from ..registry import Element


def _sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    sid = str((props or {}).get("scene", "")).strip().lower()
    if sid not in vs.scene_ids():
        raise ValueError("vector_scene needs a known scene")
    return {"scene": sid}


def _draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, theme: Theme, ctx: SceneCtx) -> None:
    # The finished picture is the canvas at half its pixel size (the renderer reduces 2x): draw the vector scene at exactly that size, so a 4K video gets a
    # real 3840x2160 rasterisation of the SVG, and paste it doubled with NEAREST (the 2x reduce gives the very same pixels back).
    w, h = max(2, cv.im.width // 2), max(2, cv.im.height // 2)
    frame = vs.load(props["scene"], w, h).frame(max(0.0, lt), dur)
    cv.im.paste(frame.resize(cv.im.size, Image.NEAREST), (0, 0))


ELEMENTS = [
    Element(
        name="vector_scene", family="Media",
        doc="- vector_scene: {scene: id of a bundled cartoon scene}. NOT offered to the director yet.",
        sanitize=_sanitize, draw=_draw, cues=lambda props, dur: [],
        samples=[{"scene": "forest_path"}, {"scene": "seaside"}],
        hidden=True, min_seconds=4.0, max_per_video=2,
    )
]
