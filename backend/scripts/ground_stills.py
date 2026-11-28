#!/usr/bin/env python3
"""Local stills of a three-character cartoon conversation on the backdrops that have ground for it (no Lambda): the sea request of the owner's report.

  AWS_PROFILE=qa CATALOG_BUCKET=<qa catalog bucket> VECTOR_SCENES_DIR=/tmp/gnd/pkgs python backend/scripts/ground_stills.py OUTDIR [--backdrop ID]

Draws the presenter element the way the renderer does (engine.renderer.Renderer.frame_at) at a mid point of each of the three beats, for 9:16 and 16:9, and writes
`<shape>_<beat>.png` plus `<shape>_marks.png` with the foot points (yellow) and the ground line band (cyan) drawn over beat 1.
"""
import json
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
CAST = ["fox", "bear", "owl"]
LINES = [("fox", {"heading": "Why is the sea salty?"}), ("bear", {"heading": "The ocean", "chart": {"labels": ["Sea", "Land"], "values": [70.8, 29.2], "unit": "%"}}),
         ("owl", {"heading": "Salinity", "points": ["Salt dissolved in water", "Grams per litre"]})]
TEXT = "Exactly! The salt is dissolved in the water, like sugar in tea. It is called salinity, and it is measured in grams per litre."


def timeline(backdrop, aspect, speaker, content):
    fr = format_options.frame_dict(aspect, "720p", None)
    props = E.sanitize({**content, "character": speaker, "cast": CAST, "backdrop": backdrop})
    words = [list(w) for w in align.estimate_words(TEXT, 6.0, lead=0.4)]
    scenes = [{"id": "s1", "type": "presenter", "start": 0.0, "duration": 7.0, "props": props, "words": words}]
    pp.link(scenes)
    return {"fps": 30, "width": fr["width"], "height": fr["height"], "frame": fr, "theme": "midnight", "captions": True, "outro": False, "scenes": scenes}


def pick(aspect):
    from common import vector_catalog as vc
    shape = {"16:9": "16:9", "9:16": "9:16"}[aspect]
    try:
        found = vc.search("the sea is salty, ocean, beach, waves, water", aspect=shape, k=80, min_score=0.2)
    except Exception:  # noqa: BLE001
        found = []
    ids = [c["id"] for c in found] + sorted(sz._data()["zones"])
    return next((i for i in ids if sz.holds(i, aspect, 3)), None)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    only = sys.argv[sys.argv.index("--backdrop") + 1] if "--backdrop" in sys.argv else None
    for aspect in ("9:16", "16:9"):
        bd = only or pick(aspect)
        print(aspect, "backdrop", bd, sz.line(bd, aspect))
        for i, (who, content) in enumerate(LINES, 1):
            el.release()
            tl = timeline(bd, aspect, who, content)
            r = Renderer(tl)
            im = r.frame_at(3.2)
            tag = f"{aspect.replace(':', 'x')}_{bd}"
            im.save(os.path.join(out, f"{tag}_beat{i}.png"))
            if i == 1:
                m = im.copy()
                d = ImageDraw.Draw(m)
                k = m.width / r.frame.W
                for x, y in sz.foot_points(tl["scenes"][0]["props"], aspect):
                    X, Y = x * m.width, min(y, 0.999) * m.height
                    d.ellipse((X - 9, Y - 9, X + 9, Y + 9), fill=(255, 230, 0), outline=(0, 0, 0))
                ln = sz.line(bd, aspect)
                for yy in (ln["band"][0], ln["band"][1]):
                    d.line([(0, min(yy, 0.999) * m.height), (m.width, min(yy, 0.999) * m.height)], fill=(0, 230, 255), width=2)
                m.save(os.path.join(out, f"{tag}_marks.png"))


if __name__ == "__main__":
    main()
