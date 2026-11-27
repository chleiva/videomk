#!/usr/bin/env python3
"""Generate flat-cartoon pictures (the source art of a layered vector scene, docs/VECTOR_SCENES.md) with the OpenAI image model, QA account only.
About USD 0.037 per picture (2048x1152, medium). Every call is appended to docs/image_catalog/spend_log.jsonl; refuses to start above --cap (default 1.00) for the run name.

  AWS_PROFILE=qa python backend/scripts/vector_scene_art.py --run vector-scene-proto --out DIR --cap 1.0 NAME="description of the scene" ...
"""
import argparse
import base64
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")

import catalog_generate as cg  # noqa: E402

LEDGER = os.path.join(HERE, "..", "..", "docs", "image_catalog", "spend_log.jsonl")
STYLE = ("Flat 2D children's cartoon illustration, clean bold dark outlines, solid flat colours with only a little simple shading, vector-art style, no gradients, no textures, "
         "no text, no people, no logos. Wide 16:9 landscape composition with clear depth in 4 distinct planes: a plain sky with one or two simple clouds, distant shapes, a middle plane, "
         "and big simple foreground shapes at the bottom corners framing the scene. Bright friendly colours.")


def spent(run: str) -> float:
    tot = 0.0
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("run") == run:
                tot += float(j.get("usd", 0))
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="vector-scene-proto")
    ap.add_argument("--out", default=".")
    ap.add_argument("--cap", type=float, default=1.0)
    ap.add_argument("--quality", default="medium")
    ap.add_argument("scenes", nargs="+", help='NAME="what the scene shows"')
    a = ap.parse_args()
    api = cg.openai_api("qa")
    for item in a.scenes:
        name, _, what = item.partition("=")
        if spent(a.run) + 0.06 > a.cap:
            print("cap reached, stopping")
            return 1
        res = api({"model": cg.OPENAI_MODEL, "prompt": STYLE + " " + what, "size": cg.IMAGE_SIZE, "quality": a.quality, "output_format": "png", "n": 1})
        cost = cg.real_cost(res.get("usage") or {})
        path = os.path.join(a.out, f"{name}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": a.run, "item": name,
                                "what": f"{cg.OPENAI_MODEL} {cg.IMAGE_SIZE} {a.quality} flat-cartoon", "usd": round(cost, 4), "run_total": round(spent(a.run) + cost, 5)}) + "\n")
        print(f"{name}: {path} cost {cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
