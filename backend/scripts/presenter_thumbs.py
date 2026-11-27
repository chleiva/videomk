#!/usr/bin/env python3
"""The small face pictures of the presenter cast that capabilities returns (docs/PRESENTERS.md): one 112 px PNG per character, as data URIs in
lambdas/common/presenter_thumbs.json (a few KB each; no bucket, no new resource). Run again when a character's art changes or one is added:

  python backend/scripts/presenter_thumbs.py [--sheet /tmp/cast.png]
"""
import argparse
import base64
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from PIL import Image  # noqa: E402

from engine import presenter_policy, vector_presenter as vp  # noqa: E402
from engine.scenes.elements import presenter as el  # noqa: E402

SIZE = 112


def face(cid: str) -> Image.Image:
    ch = vp.load(cid, 3.0, el.CAST[cid]["size"])
    img = Image.new("RGBA", (900, 1000), (0, 0, 0, 0))
    sk = ch.draw(img, 450, 950, {"mouth": "half"})
    u = ch.ppu
    cx, top = 450 + sk["neck"][0] * u, 950 - (sk["neck"][1] + vp.HEAD_U * 1.05) * u
    half = vp.HEAD_U * u * 0.66
    crop = img.crop((int(cx - half), int(top - half * 0.12), int(cx + half), int(top + half * 1.88)))
    return crop.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet")
    a = ap.parse_args()
    out, faces = {}, []
    for cid in presenter_policy.ORDER:
        im = face(cid)
        faces.append(im)
        buf = io.BytesIO()
        im.quantize(96, method=Image.FASTOCTREE).save(buf, "PNG", optimize=True)
        out[cid] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        print(cid, len(buf.getvalue()), "bytes")
    path = os.path.join(os.path.dirname(__file__), "..", "lambdas", "common", "presenter_thumbs.json")
    json.dump(out, open(path, "w"), indent=0)
    print("wrote", os.path.normpath(path), os.path.getsize(path), "bytes")
    if a.sheet:
        sheet = Image.new("RGB", (SIZE * len(faces), SIZE), (245, 242, 236))
        for i, im in enumerate(faces):
            sheet.paste(im, (i * SIZE, 0), im)
        sheet.resize((sheet.width * 3, sheet.height * 3), Image.LANCZOS).save(a.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
