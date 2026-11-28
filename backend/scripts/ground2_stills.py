#!/usr/bin/env python3
"""Local stills (no Lambda) of cartoon conversations on a backdrop or on the DRAWN ground, for docs/CARTOON_GROUND_2026-11-28.md.

  VECTOR_SCENES_DIR=/tmp/gnd/pkgs python backend/scripts/ground2_stills.py OUTDIR  [--only proc|catalog] [--theme midnight|paper|sunrise]

Writes `<name>.png` for each case and `index.html`. Foot points are drawn small (yellow) so the eye can check them.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambdas"))
os.environ.setdefault("PRESENTERS", "1")

from PIL import ImageDraw  # noqa: E402

from engine import align, format_options, presenter_policy as pp, stand_zone as sz  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.scenes.elements import presenter as el  # noqa: E402

E = ELEMENTS["presenter"]
TEXT = "Exactly! The salt is dissolved in the water, like sugar in tea. It is called salinity, and it is measured in grams per litre."
CONTENT = {"heading": "Why is the sea salty?", "points": ["Rain washes salt from rocks", "Rivers carry it to the sea"]}


def still(backdrop, aspect, n, theme="midnight", marks=True):
    cast = ["fox", "bear", "owl"][:n]
    fr = format_options.frame_dict(aspect, "720p", None)
    props = E.sanitize({**CONTENT, "character": cast[-1] if n > 1 else cast[0], **({"cast": cast} if n > 1 else {}), "backdrop": backdrop})
    words = [list(w) for w in align.estimate_words(TEXT, 6.0, lead=0.4)]
    scenes = [{"id": "s1", "type": "presenter", "start": 0.0, "duration": 7.0, "props": props, "words": words}]
    pp.link(scenes)
    tl = {"fps": 30, "width": fr["width"], "height": fr["height"], "frame": fr, "theme": theme, "captions": True, "outro": False, "scenes": scenes}
    el.release()
    im = Renderer(tl).frame_at(3.2)
    if marks:
        d = ImageDraw.Draw(im)
        for x, y in sz.foot_points(props, aspect):
            X, Y = x * im.width, min(y, 0.999) * im.height
            d.ellipse((X - 5, Y - 5, X + 5, Y + 5), fill=(255, 230, 0), outline=(0, 0, 0))
    return im


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    themes = [sys.argv[sys.argv.index("--theme") + 1]] if "--theme" in sys.argv else ["midnight", "paper"]
    cases = []
    if only in (None, "proc"):
        for th in themes:
            for asp in ("9:16", "16:9", "1:1", "4:5"):
                for n in (1, 2, 3):
                    cases.append((sz.PROC_ID, asp, n, th))
    if only in (None, "catalog"):
        cases += [("tall_sunset_beach_vertical", "9:16", 3, "midnight"), ("camping_lake_night", "16:9", 3, "midnight")]
    rows = []
    for bd, asp, n, th in cases:
        name = f"{bd}_{asp.replace(':', 'x')}_{n}c_{th}.png"
        try:
            still(bd, asp, n, th).save(os.path.join(out, name))
            rows.append((name, f"{bd} {asp} {n} character(s) theme {th}"))
        except Exception as e:  # noqa: BLE001
            print("FAILED", name, type(e).__name__, e)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write("<meta charset=utf-8><title>ground 2</title><body style='background:#222;color:#eee;font:14px sans-serif'><h1>Ground 2: drawn ground and 16:9 whole figures</h1>")
        for name, cap in rows:
            f.write(f"<figure style='display:inline-block;margin:8px;vertical-align:top'><img src='{name}' style='max-height:420px;max-width:700px'><figcaption>{cap}</figcaption></figure>")
    print(len(rows), "stills in", out)


if __name__ == "__main__":
    main()
