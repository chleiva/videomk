"""Where is each labelled part in a photograph? Asked of the small vision model, and trusted only when two independent looks agree.

The director cannot see the picture, so `annotated_image.prepare` calls `locate` on the photograph it fetched. A pin is kept only if (1) the model said the part is
clearly visible in both looks (once on the plain picture, once on the picture with a numbered 10% grid drawn over it, which makes the coordinates sharper),
(2) the two pins are within AGREE of each other, (3) each pin lies inside its own box (the model contradicting itself is a guess), and (4) the box is a part,
not most of the picture. A label that fails any test is dropped; pins that would sit on top of each other are thinned. Nothing here guesses.
"""
import io
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from ._pm_text import ASSETS

AGREE = 0.15          # largest distance (fraction of the picture's width/height) between the two looks
MIN_GAP = 0.09        # pins closer than this are the same spot: keep the first
MAX_BOX_AREA = 0.55
THUMB = 768

SYSTEM = "You locate parts of a photograph precisely and honestly. You reply with JSON only. When a part is not clearly visible you say so; you never guess."


def thumbnail_jpeg(jpeg: bytes, grid: bool = False) -> bytes:
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    im.thumbnail((THUMB, THUMB))
    if grid:
        d = ImageDraw.Draw(im, "RGBA")
        font = ImageFont.truetype(os.path.join(ASSETS, "fonts", "Inter-Bold.ttf"), 14)
        w, h = im.size
        for k in range(1, 10):
            x, y = w * k / 10, h * k / 10
            d.line([(x, 0), (x, h)], fill=(255, 255, 255, 90), width=1)
            d.line([(0, y), (w, y)], fill=(255, 255, 255, 90), width=1)
            for pos, anchor in (((x, 2), "ma"), ((2, y), "lm")):
                d.text(pos, f"{k / 10:.1f}", font=font, fill=(255, 255, 0, 255), anchor=anchor, stroke_width=2, stroke_fill=(0, 0, 0, 255))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def _prompt(alt: str, labels: List[str], grid: bool) -> str:
    g = " The picture has a grid every 0.1 with the coordinate printed on its top and left edges; use it." if grid else ""
    return (f"The photograph shows: {alt or 'a scene'}.{g}\nFor each label below, find that part in the picture. x runs from 0 (left edge) to 1 (right edge), "
            "y from 0 (top edge) to 1 (bottom edge). Give pin = [x, y], the centre of the part, and box = [x0, y0, x1, y1], a tight box around it. "
            "If the part is not clearly visible, or you are unsure which thing it is, set visible to false.\n"
            f"Labels: {json.dumps(labels)}\n"
            'Reply with JSON only: {"parts": [{"label": "...", "visible": true, "pin": [0.0, 0.0], "box": [0.0, 0.0, 1.0, 1.0]}]} with one entry per label, in order.')


def parse(text: str, labels: List[str]) -> List[Optional[Dict[str, Any]]]:
    """One entry per label: {pin, box} or None. Tolerant of prose and code fences around the JSON; strict about the numbers."""
    m = re.search(r"\{.*\}", text or "", re.S)
    out: List[Optional[Dict[str, Any]]] = [None] * len(labels)
    if not m:
        return out
    try:
        parts = json.loads(m.group(0)).get("parts") or []
    except (ValueError, AttributeError):
        return out
    for i, lab in enumerate(labels):
        p = next((q for q in parts if isinstance(q, dict) and str(q.get("label", "")).strip().lower() == lab.lower()), parts[i] if i < len(parts) and isinstance(parts[i], dict) else None)
        try:
            if not p or p.get("visible") is False or p.get("pin") is None:
                continue
            x, y = (float(v) for v in p["pin"])
            x0, y0, x1, y1 = (float(v) for v in p["box"])
        except (TypeError, ValueError, KeyError):
            continue
        if not all(0.0 <= v <= 1.0 for v in (x, y, x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
            continue
        out[i] = {"pin": (x, y), "box": (x0, y0, x1, y1)}
    return out


def _consistent(r: Dict[str, Any]) -> bool:
    x, y = r["pin"]
    x0, y0, x1, y1 = r["box"]
    return x0 - 0.03 <= x <= x1 + 0.03 and y0 - 0.03 <= y <= y1 + 0.03 and (x1 - x0) * (y1 - y0) <= MAX_BOX_AREA


def locate(jpeg: bytes, labels: List[str], alt: str, complete: Callable[..., Tuple[str, Dict[str, Any]]], model: Optional[str] = None) -> Tuple[Dict[str, Tuple[float, float]], float]:
    """Returns ({label: (x, y)} for the labels that two looks agree on, cost in dollars). Raises if the model cannot be called at all."""
    looks, cost = [], 0.0
    for grid in (False, True):
        text, meta = complete(SYSTEM, _prompt(alt, labels, grid), images=[thumbnail_jpeg(jpeg, grid)], max_tokens=700, temperature=0.0, model=model, effort="low")
        cost += float(meta.get("cost_usd", 0.0))
        looks.append(parse(text, labels))
    found: Dict[str, Tuple[float, float]] = {}
    for i, lab in enumerate(labels):
        a, b = looks[0][i], looks[1][i]
        if not a or not b or not _consistent(a) or not _consistent(b):
            continue
        (ax, ay), (bx, by) = a["pin"], b["pin"]
        if abs(ax - bx) > AGREE or abs(ay - by) > AGREE:
            continue
        pin = ((ax + bx) / 2, (ay + by) / 2)
        if any(abs(pin[0] - q[0]) < MIN_GAP and abs(pin[1] - q[1]) < MIN_GAP for q in found.values()):
            continue
        found[lab] = (round(min(0.96, max(0.04, pin[0])), 3), round(min(0.96, max(0.04, pin[1])), 3))
    return found, cost
