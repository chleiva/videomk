"""No scene's text or card sits where the corner mark lands (docs/TITLES_AND_CLIP_NARRATION_2026-11-28.md).

Every built-in scene and every element sample is drawn in every aspect, every text run and every card-sized rounded rectangle is recorded (design units), and none may
intersect the mark's worst-case rectangle for that shape: the largest lockup, the largest mark and the widest custom logo, at the corner watermark_spec picks. Account-independent:
the margins are constants of the shape, the mark is a final layer (docs/WATERMARK_DECOUPLED_2026-11-28.md)."""
import copy

import pytest

from tests import format_samples as fs
from tests.element_utils import make_renderer
from engine import watermark_spec as ws
from engine.canvas import Canvas
from engine.frame import ASPECTS, Frame
from engine.scenes import ELEMENTS

FULL_BLEED = {"image", "clip", "gallery"}   # pictures fill the frame by design; their own text (credit, one word) is checked
SPECS = [{"mode": "videomk", "style": "lockup", "size": "medium"}, {"mode": "videomk", "style": "mark", "size": "medium"},
         {"mode": "custom", "size": "medium"}, {"mode": "videomk", "style": "lockup", "size": "small"}]


def mark_rects(aspect):
    """The mark's rectangle for each option set, where the shape's own corner holds it (a 16:9 custom logo as wide as 4.3 times its height does not fit the bottom right and is moved to
    the top left by the placement rules: a premium edge case, recorded in the doc, not a title question)."""
    fr = Frame.parse(aspect, "720p")
    rects = []
    for sp in SPECS:
        lay = ws.layout({**sp, "position": "auto"}, fr, logo_ratio=ws.MAX_LOGO_RATIO if sp["mode"] == "custom" else None)
        if not lay["moved"]:
            rects.append(lay["rect"])
    assert rects
    return rects


def _record(monkeypatch):
    out = []
    real_text, real_rrect = Canvas.text, Canvas.rrect

    def text(self, x, y, s, weight="regular", size=40, fill=(255, 255, 255, 255), anchor="la"):
        a = int(fill[3]) if len(fill) == 4 else 255
        if a > 0 and s:
            w = self.measure(s, weight, size)
            h = size
            x0 = x - (w / 2 if anchor[0] == "m" else w if anchor[0] == "r" else 0)
            y0 = y - (h * 0.8 if anchor[1] == "s" else h / 2 if anchor[1] == "m" else 0)
            out.append(("text", s[:30], (x0, y0, x0 + w, y0 + h * 0.8)))
        return real_text(self, x, y, s, weight, size, fill, anchor)

    def rrect(self, x, y, w, h, r, fill=None, outline=None, width=0):
        if w >= 120 and h >= 60 and fill is not None and (len(fill) < 4 or fill[3] > 40):
            out.append(("card", "", (x, y, x + w, y + h)))
        return real_rrect(self, x, y, w, h, r, fill, outline, width)

    monkeypatch.setattr(Canvas, "text", text)
    monkeypatch.setattr(Canvas, "rrect", rrect)
    return out


def _cases():
    for n in sorted(fs.SAMPLES):
        yield n, fs.sample(n)
    for n in sorted(ELEMENTS):
        el = ELEMENTS[n]
        yield n, (n, el.sanitize(copy.deepcopy(el.samples[0])))


CASES = list(_cases())


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name,case", CASES, ids=[c[0] for c in CASES])
def test_no_text_or_card_touches_the_mark(name, case, aspect, monkeypatch):
    stype, props = case
    el = ELEMENTS.get(stype)
    dur = max(8.0, (el.min_seconds + 2) if el else 8.0)
    boxes = mark_rects(aspect)
    rec = _record(monkeypatch)
    r, sc = make_renderer(stype, props, dur, "midnight", [], True, fs.image_loader, True, aspect, "720p", fs.clip_loader)
    for lt in (0.0, dur * 0.5, dur * 0.95):
        r._draw_spec(sc, lt)
    # the 1.5 design-unit slack covers rounding only
    if stype == "map":   # painted on its own panel (local coordinates): the whole panel, title chip inside it, must start below the mark
        from engine.scenes.elements import _mapdraw as MD
        fr = Frame.parse(aspect, "720p")
        if not fr.landscape:
            assert all(MD.panel_origin(fr, fr.box(True))[1] >= bx[3] - 1.5 for bx in boxes)
        return
    hits = [(k, s, b) for k, s, b in rec if any(ws.intersects(b, bx, -1.5) for bx in boxes) and not (stype in FULL_BLEED and k == "card")]
    assert not hits, f"{name} {aspect}: {hits[:3]} meets the mark {boxes}"
