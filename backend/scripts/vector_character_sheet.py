#!/usr/bin/env python3
"""Generate ONE rig-parts sheet per cartoon child with the OpenAI image model (QA account only), for the vector character prototype (docs/VECTOR_SCENES.md).
About USD 0.035 per sheet (1536x1024, medium). Every call is appended to docs/image_catalog/spend_log.jsonl; refuses to start above --cap for the run.

The sheet has a FIXED order (read left to right, top to bottom), which vector_character_build.py relies on to name the pieces:
  row 1: head (blank face), torso, upper arm, lower arm + hand
  row 2: upper leg, lower leg + shoe, eyes open, eyes closed
  row 3: mouth closed, mouth half open, mouth wide open

  AWS_PROFILE=qa python backend/scripts/vector_character_sheet.py --out DIR --cap 1.5 [--only NAME ...]
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
RUN = "vector-character-proto"

KIDS = {
    "mia": "a girl with warm brown skin, black curly shoulder-length hair, a bright yellow raincoat over a cream top, blue jeans, yellow sneakers",
    "leo": "a boy with pale freckled skin, short spiky ginger hair, a green hooded sweater, grey trousers, white sneakers with red soles",
    "nora": "a girl with light tan skin, long straight black hair in two pigtails with red bobbles and round glasses, a purple jumper, pink trousers, teal sneakers",
    "sam": "a boy with dark brown skin, a red baseball cap, a light blue t-shirt, beige trousers, orange sneakers",
}

LAYOUT = (
    "Character rig parts sheet for 2D cut-out animation of ONE friendly cartoon child: {who}. Flat children's cartoon style, bold dark outlines of equal weight, solid flat colours, "
    "no gradients, no shading, no text, no labels. Every part is drawn SEPARATE, straight, front-facing, un-rotated and fully visible, with wide white gaps between parts, on a plain flat white background. "
    "Strict layout, 4 columns, 3 rows, in this exact order. "
    "ROW 1: (1) the HEAD with hair (and the cap or glasses if any), with ears and a small nose but a BLANK FACE: no eyes, no mouth, no eyebrows, no neck; "
    "(2) the TORSO: top clothing only, front view, no head, no arms, no legs, ending at the waist; "
    "(3) one UPPER ARM: just the sleeve, hanging straight down; "
    "(4) one LOWER ARM with the bare hand, hanging straight down, open relaxed hand. "
    "ROW 2: (1) one UPPER LEG: a trouser leg only, straight down; "
    "(2) one LOWER LEG: trouser leg with the shoe, the shoe seen from the side pointing to the RIGHT; "
    "(3) a pair of OPEN EYES (two round eyes with highlights); "
    "(4) a pair of CLOSED EYES (two simple curved lashes lines). "
    "ROW 3: (1) a closed smiling MOUTH; (2) a half open MOUTH; (3) a wide open MOUTH with tongue; the 4th cell of row 3 stays empty."
)


def spent() -> float:
    tot = 0.0
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("run") == RUN:
                tot += float(j.get("usd", 0))
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--cap", type=float, default=1.5)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    api = cg.openai_api("qa")
    os.makedirs(a.out, exist_ok=True)
    for name, who in KIDS.items():
        if a.only and name not in a.only:
            continue
        if spent() + 0.06 > a.cap:
            print("cap reached, stopping")
            return 1
        res = api({"model": cg.OPENAI_MODEL, "prompt": LAYOUT.format(who=who), "size": "1536x1024", "quality": "medium", "output_format": "png", "n": 1})
        cost = cg.real_cost(res.get("usage") or {})
        path = os.path.join(a.out, f"sheet_{name}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": RUN, "item": f"sheet_{name}",
                                "what": f"{cg.OPENAI_MODEL} 1536x1024 medium rig parts sheet", "usd": round(cost, 4), "run_total": round(spent() + cost, 5)}) + "\n")
        print(f"{name}: {path} cost {cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
