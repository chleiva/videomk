#!/usr/bin/env python3
"""Contact sheets of the built-in scenes (and optionally every element) in a chosen aspect: one row per sample, three moments each.

  python scripts/format_preview.py --aspect 9:16 [--theme midnight|paper|sunrise] [--out docs/formats/9x16-midnight.png] [--only title,bullets_rail] [--elements] [--words]

The sheet prints a line for every scene that used the framed fallback (scale, smallest text in design px, readable or not).
Look at the sheet before calling a layout done: nothing may touch the caption band or the platform UI zone, text must be large enough, the end state must be complete.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw  # noqa: E402

from engine.frame import Frame  # noqa: E402
from tests import format_samples as fs  # noqa: E402
from tests.element_utils import make_renderer  # noqa: E402

WORDS = [("The", 0.5, 0.8), ("quick", 0.8, 1.2), ("brown", 1.2, 1.6), ("fox", 1.6, 2.0), ("jumps", 2.0, 2.4), ("over", 2.4, 2.8), ("the", 2.8, 3.0), ("lazy", 3.0, 3.4), ("dog", 3.4, 3.9),
         ("and", 3.9, 4.2), ("runs", 4.2, 4.6), ("away", 4.6, 5.2)]


def specs(elements: bool):
    out = [(name, t, p) for name, (t, p) in fs.SAMPLES.items()]
    if elements:
        import copy
        from engine.scenes import ELEMENTS
        for n in sorted(ELEMENTS):
            for i, smp in enumerate(ELEMENTS[n].samples[:2]):
                try:
                    out.append((f"{n}#{i + 1}", n, ELEMENTS[n].sanitize(copy.deepcopy(smp))))
                except Exception:   # noqa: BLE001
                    pass
    return out


def sheet(aspect: str, theme: str, only=None, elements=False, resolution="720p", fracs=(0.12, 0.45, 0.95), dur=6.0, words=True, tile_h=360):
    fr = Frame.parse(aspect, resolution)
    rows, notes = [], []
    for name, stype, props in specs(elements):
        if only and name not in only and stype not in only:
            continue
        r, sc = make_renderer(stype, props, dur, theme, WORDS if words else [], words, fs.image_loader, False, aspect, resolution, fs.clip_loader)
        frames = []
        for f in fracs:
            img = r._draw_spec(sc, dur * f)
            frames.append(img.resize((round(img.width * tile_h / img.height), tile_h), Image.LANCZOS))
        rep = r.fallbacks.get("t")
        if rep:
            notes.append(f"{name}: framed x{rep['scale']} min text {rep['min_text_px']}px {'OK' if rep['readable'] else 'TOO SMALL'}")
        rows.append((name + (f"  [framed x{rep['scale']}]" if rep else ""), frames))
    tw = max(f.width for _, fr_ in rows for f in fr_)
    cols = len(fracs)
    # lay rows out in as many sheet columns as keep the image wide but not huge
    per_col = max(1, min(len(rows), 5 if fr.vertical or fr.square else 8))
    groups = [rows[i:i + per_col] for i in range(0, len(rows), per_col)]
    gw = cols * (tw + 8) + 8
    gh = per_col * (tile_h + 26) + 8
    im = Image.new("RGB", (gw * len(groups), gh), (30, 30, 34))
    d = ImageDraw.Draw(im)
    for gi, g in enumerate(groups):
        for ri, (label, frames) in enumerate(g):
            y = 8 + ri * (tile_h + 26)
            d.text((gi * gw + 10, y + 3), label, fill=(230, 230, 230))
            for ci, f in enumerate(frames):
                im.paste(f, (gi * gw + 8 + ci * (tw + 8), y + 18))
    return im, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--theme", default="midnight")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--elements", action="store_true", help="also every registered element's samples")
    ap.add_argument("--resolution", default="720p")
    ap.add_argument("--no-words", action="store_true")
    ap.add_argument("--tile-h", type=int, default=360)
    ap.add_argument("--fracs", default="0.12,0.45,0.95", help="moments as fractions of the scene length")
    a = ap.parse_args()
    only = [x for x in a.only.split(",") if x]
    im, notes = sheet(a.aspect, a.theme, only, a.elements, a.resolution, words=not a.no_words, tile_h=a.tile_h, fracs=tuple(float(x) for x in a.fracs.split(',')))
    out = a.out or f"format-{a.aspect.replace(':', 'x')}-{a.theme}.png"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)   # a palette PNG: contact sheets stay small
    print(f"wrote {out} {im.size}")
    for n in notes:
        print("  " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
