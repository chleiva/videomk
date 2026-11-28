#!/usr/bin/env python3
"""Local stills of every scene template in the three top-mark shapes (9:16, 1:1, 4:5) with the REAL watermark artwork composited at its real place (the layer final_stage overlays),
to look at whether any title or card meets the mark (docs/TITLES_AND_CLIP_NARRATION_2026-11-28.md). One PNG per template and shape, plus a contact sheet per shape.

  .venv/bin/python backend/scripts/titles_clear_stills.py --out ~/Downloads/videomk-looks/web/titles-clear
"""
import argparse
import copy
import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambdas")]
os.environ.setdefault("WHITEBOARD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "fixtures", "whiteboard"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from engine import watermark  # noqa: E402
from engine.frame import Frame  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from tests import format_samples as fs  # noqa: E402
from tests.element_utils import make_renderer  # noqa: E402

SPEC = {"mode": "videomk", "style": "lockup", "presence": "always", "position": "auto", "size": "medium", "opacity": 0.9}   # the largest videomk lockup


def cases():
    for n in sorted(fs.SAMPLES):
        yield n, fs.sample(n)
    for n in sorted(ELEMENTS):
        el = ELEMENTS[n]
        yield n, (n, el.sanitize(copy.deepcopy(el.samples[0])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--aspects", nargs="+", default=["9:16", "1:1", "4:5"])
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)
    font = ImageFont.load_default()
    for aspect in a.aspects:
        fr = Frame.parse(aspect, "720p")
        tiles = []
        for name, (stype, props) in cases():
            if a.only and name not in a.only:
                continue
            el = ELEMENTS.get(stype)
            dur = max(8.0, (el.min_seconds + 2) if el else 8.0)
            r, sc = make_renderer(stype, props, dur, "midnight", [], True, fs.image_loader, False, aspect, "720p", fs.clip_loader)
            im = r.frame_at(dur * 0.6).convert("RGBA")
            wm = watermark.build(SPEC, fr, im.size, True)
            if wm is not None:
                im.alpha_composite(wm.layer, wm.pos)
                d = ImageDraw.Draw(im)
                d.rectangle(wm.rect_px, outline=(255, 0, 0, 255))   # the mark's rectangle, for the eye
            im = im.convert("RGB")
            im.save(os.path.join(out, f"{name}_{aspect.replace(':', 'x')}.png"))
            tiles.append((name, im))
            print(aspect, name, flush=True)
        if not tiles:
            continue
        cell_h, cols = 360, 8
        th = [(n, i.resize((int(i.width * cell_h / i.height), cell_h), Image.LANCZOS)) for n, i in tiles]
        cw = max(t.width for _, t in th) + 6
        rows = (len(th) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * (cell_h + 16)), (50, 50, 54))
        d = ImageDraw.Draw(sheet)
        for k, (n, t) in enumerate(th):
            x, y = (k % cols) * cw, (k // cols) * (cell_h + 16)
            sheet.paste(t, (x + 3, y + 14))
            d.text((x + 4, y + 2), n[:24], fill=(255, 255, 255), font=font)
        sheet.save(os.path.join(out, f"sheet_{aspect.replace(':', 'x')}.jpg"), quality=88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
