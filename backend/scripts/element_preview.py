#!/usr/bin/env python3
"""Contact sheet of scene elements: every sample of every registered element (or the ones named) at several moments, on a chosen theme.

  python scripts/element_preview.py [name ...] [--theme midnight|paper|sunrise] [--out preview.png] [--times 0.15,0.5,0.9] [--aspect 9:16|1:1|4:5|16:9]

Look at the sheet before calling an element done (text must fit, nothing may overlap the caption band at the bottom, the end state must be complete).
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw  # noqa: E402

from engine.scenes import ELEMENTS  # noqa: E402
from tests.element_utils import render  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--theme", default="midnight")
    ap.add_argument("--out", default="element-preview.png")
    ap.add_argument("--times", default="0.15,0.5,0.95", help="fractions of the scene length")
    ap.add_argument("--dur", type=float, default=8.0)
    ap.add_argument("--aspect", default="16:9", help="frame shape; an element not tagged for it is shown in the framed fallback (the row label says so, with its smallest text size)")
    a = ap.parse_args()
    names = a.names or sorted(ELEMENTS)
    fracs = [float(x) for x in a.times.split(",")]
    from engine.frame import Frame
    fr = Frame.parse(a.aspect, "720p")
    th = 270 if fr.landscape else 400
    tw = round(th * fr.width / fr.height)
    rows = []
    for n in names:
        el = ELEMENTS[n]
        for si, sample in enumerate(el.samples):
            props = el.sanitize(copy.deepcopy(sample))
            dur = max(a.dur, el.min_seconds + 2)
            frames = [render(n, props, dur * f, dur, a.theme, captions=True, aspect=a.aspect, resolution="720p", draft=False).resize((tw, th)) for f in fracs]
            tag = "" if a.aspect in el.formats else "  [framed fallback]"
            rows.append((f"{n} #{si + 1}{tag}", frames))
    sheet = Image.new("RGB", (len(fracs) * tw + 10 * (len(fracs) + 1), len(rows) * (th + 34) + 10), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for r, (label, frames) in enumerate(rows):
        y = 10 + r * (th + 34)
        d.text((12, y + 4), label, fill=(230, 230, 230))
        for c, f in enumerate(frames):
            sheet.paste(f, (10 + c * (tw + 10), y + 22))
    sheet.save(a.out)
    print(f"wrote {a.out}: {len(rows)} rows x {len(fracs)} moments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
