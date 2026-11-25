#!/usr/bin/env python3
"""Contact sheets of the styled `bullets` and `diagram` scenes (docs/SCENE_STYLES.md): every style on three themes with different accents at the start, the middle of
the reveal and the end, plus an accent x theme grid.

  python scripts/scene_styles_preview.py [--out docs/scene_styles]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw  # noqa: E402

from engine.scenes import style_kit as sk  # noqa: E402
from tests.element_utils import render  # noqa: E402

BULLETS = {"heading": "What really matters", "items": ["Wealth is not everything", "Worry changes little", "Live well today", "Small habits compound"]}
KEYWORDS = {"heading": "Principles that last", "items": ["Clarity: say one thing at a time", "Pace: leave room to breathe", "Proof: show, then tell", "Care: respect the viewer"]}
FLOW = {"title": "How the golden rule spreads", "nodes": [{"id": "a", "label": "Choose my action"}, {"id": "b", "label": "Others feel respected"}, {"id": "c", "label": "Trust grows"}, {"id": "d", "label": "Community thrives"}],
        "edges": [["a", "b"], ["b", "c", "over time"], ["c", "d"]]}
LONG = {"title": "From idea to launch", "nodes": [{"id": k, "label": l} for k, l in zip("abcdefg", ["Spot a problem", "Sketch ideas", "Build a prototype", "Test with users", "Fix what breaks", "Launch it", "Keep improving"])],
        "edges": [[a, b] for a, b in zip("abcdef", "bcdefg")]}
CUES = {"bullets": [1.0, 2.6, 4.2, 5.8], "diagram": [1.0, 2.6, 4.2, 5.8]}
COMBOS = (("midnight", "indigo"), ("paper", "rose"), ("sunrise", "amber"))


def frame(stype, props, theme, lt, dur=8.0, w=640):
    return render(stype, props, lt, dur, theme, captions=True, draft=False).resize((w, w * 9 // 16), Image.LANCZOS)


def save(img, path):
    """Docs previews stay small: a 256-colour dithered palette keeps the gradients smooth enough for a preview."""
    img.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)


def sheet(rows, cols_labels, w=640, label_h=26):
    h = w * 9 // 16
    img = Image.new("RGB", (w * len(cols_labels), (h + label_h) * len(rows)), (24, 24, 28))
    d = ImageDraw.Draw(img)
    for r, (label, frames) in enumerate(rows):
        y = r * (h + label_h)
        d.text((10, y + 7), label, fill=(230, 230, 230))
        for c, f in enumerate(frames):
            img.paste(f, (c * w, y + label_h))
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "docs", "scene_styles"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    moments = (1.3, 3.6, 7.5)
    for stype, styles, base in (("bullets", sk.LIST_STYLES, BULLETS), ("diagram", sk.FLOW_STYLES, FLOW)):
        for style in styles:
            rows = []
            for theme, acc in COMBOS:
                props = dict(KEYWORDS if style == "keywords" else base, style=style, accent=acc, cues=CUES[stype])
                rows.append((f"{stype} / {style} / {theme} / {acc}   (start, mid-reveal, end)", [frame(stype, props, theme, t) for t in moments]))
            save(sheet(rows, moments), os.path.join(a.out, f"{stype}-{style}.png"))
        # accents x themes, end state, default style
        tiles = []
        for acc in sk.ACCENTS:
            row = []
            for theme in ("midnight", "paper", "sunrise"):
                props = dict(base, style=styles[2 if stype == "bullets" else 0], accent=acc)
                row.append(frame(stype, props, theme, 7.5, w=480))
            tiles.append((f"{stype} accent {acc}  (midnight, paper, sunrise)", row))
        save(sheet(tiles, [0, 1, 2], w=480), os.path.join(a.out, f"{stype}-accents.png"))
    # a long flow wraps into two rows
    rows = [(f"diagram / {st} / 7 nodes", [frame("diagram", dict(LONG, style=st, accent="teal", cues=[0.9 + 0.8 * i for i in range(7)]), "midnight", t, 9.0) for t in (1.5, 4.0, 8.5)]) for st in ("cards", "pills", "stack")]
    save(sheet(rows, (0, 1, 2)), os.path.join(a.out, "diagram-long.png"))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
