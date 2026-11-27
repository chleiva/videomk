#!/usr/bin/env python3
"""Generate rig-parts sheets for the diverse adult/animal cast (docs/CHARACTER_LIBRARY.md), same fixed layout as vector_character_sheet.py. QA account only.
Every call is appended to docs/vector_character_spend.jsonl; the run refuses to start a call that could pass --cap (default USD 1.00).

  AWS_PROFILE=qa python backend/scripts/vector_character_sheet5.py --out DIR [--only ID ...] [--cap 1.0]
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

LEDGER = os.path.join(HERE, "..", "..", "docs", "vector_character_spend.jsonl")
RUN = "vector-character-cast5"

CAST = {
    "ines": "a friendly senior woman, a retired-teacher type mentor: warm light-tan skin, short wavy white-grey hair, round glasses, kind smile lines, a dusty-rose knitted cardigan over a cream blouse, dark teal trousers, comfortable brown flat shoes",
    "david": "a friendly young adult Black man, a software engineer: dark brown skin, short natural black hair with a neat fade, a mustard-yellow hoodie with the hood down and a pair of over-ear headphones resting around his neck (headphones are part of the TORSO piece), dark grey jeans, white sneakers",
    "priya": "a friendly middle-aged South Asian woman, a doctor-scientist: medium brown skin, long black hair tied back in a low ponytail close to the head, a white lab coat open over a teal shirt with a small stethoscope draped around the neck (part of the TORSO piece), navy trousers, black flat shoes",
    "mateo": "a friendly Latino man in his forties, a chef: medium olive-tan skin, short dark brown hair and a short neat dark beard, a white chef's shirt with a long dark-green apron over it, checked grey trousers, brown leather shoes",
    "fox": "a friendly cartoon FOX guide mascot walking upright like a person: orange-red fur, cream muzzle and chest, tall pointed ears with dark tips, a teal scarf and a small navy waistcoat, dark brown arms ending in cream paw-hands with simple fingers (no claws), legs in dark brown trousers-like fur with cream-and-brown boots. No tail piece",
}

LAYOUT = (
    "Character rig parts sheet for 2D cut-out animation of ONE friendly cartoon character: {who}. Flat cartoon explainer style, bold dark outlines of equal weight, solid flat colours, "
    "no gradients, no shading, no text, no labels. Adult proportions (not a child), simple friendly design. Every part is drawn SEPARATE, straight, front-facing, un-rotated and fully visible, with wide gaps between parts, on a plain flat background. "
    "Strict layout, 4 columns, 3 rows, in this exact order. "
    "ROW 1: (1) the HEAD with hair (and glasses or ears if any), with ears and a small nose but a BLANK FACE: no eyes, no mouth, no eyebrows, no neck; "
    "(2) the TORSO: top clothing only, front view, no head, no arms, no legs, ending at the waist; "
    "(3) one UPPER ARM: just the sleeve, hanging straight down; "
    "(4) one LOWER ARM with the bare hand, hanging straight down, open relaxed hand. "
    "ROW 2: (1) one UPPER LEG: a trouser leg only, straight down; "
    "(2) one LOWER LEG: trouser leg with the shoe, the shoe seen from the side pointing to the RIGHT; "
    "(3) a pair of OPEN EYES (two round eyes with highlights, with eyebrows above them); "
    "(4) a pair of CLOSED EYES (two simple curved lashes lines, with eyebrows above them). "
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
            tot += float(j.get("usd", 0))
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--cap", type=float, default=1.0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    api = cg.openai_api("qa")
    os.makedirs(a.out, exist_ok=True)
    for name, who in CAST.items():
        if a.only and name not in a.only:
            continue
        if spent() + 0.06 > a.cap:
            print("cap reached, stopping")
            return 1
        res = api({"model": cg.OPENAI_MODEL, "prompt": LAYOUT.format(who=who), "size": "1536x1024", "quality": "medium", "output_format": "png", "n": 1})
        cost = cg.real_cost(res.get("usage") or {})
        path = os.path.join(a.out, f"sheet_{name}{a.tag}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": RUN, "item": f"sheet_{name}{a.tag}",
                                "what": f"{cg.OPENAI_MODEL} 1536x1024 medium rig parts sheet", "usd": round(cost, 4), "run_total": round(spent() + cost, 5)}) + "\n")
        print(f"{name}: {path} cost {cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
