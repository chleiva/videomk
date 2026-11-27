#!/usr/bin/env python3
"""Generate rig-parts sheets for the diverse adult/animal cast (docs/CHARACTER_LIBRARY.md), same fixed layout as vector_character_sheet.py. QA account only.
Every call is appended to docs/vector_character_spend.jsonl; the run refuses to start a call that could pass --cap (default USD 1.00).

  AWS_PROFILE=qa python backend/scripts/vector_character_sheet5.py --out DIR [--only ID ...] [--cap 1.0]
  AWS_PROFILE=qa python backend/scripts/vector_character_sheet5.py --out DIR --animals [--only owl bear ...] [--tag _b]     the animal cast (run "vector-character-animals")
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


# The animal cast (docs/PRESENTERS.md "Animal presenters"): same house style and rig as the fox. The rig scales every limb piece to a fixed length, so the limbs must be drawn
# as long as a person's; wings are drawn as arms ending in feathered hands; a bird's beak is the MOUTH piece (the head stays blank); a shell is part of the torso.
RUN_ANIMALS = "vector-character-animals"
_BODY = " Walking upright like a person, with the body proportions of a person: arms and legs as long and as slim as a person's arms and legs."
ANIMALS = {
    "owl": {"who": "a friendly cartoon OWL professor mascot, calm and wise: warm chestnut-brown feathers, a cream heart-shaped face disc and cream chest, two small ear tufts, round gold glasses, "
                   "an olive-green tweed waistcoat with a small dark-red bow tie, the WINGS drawn as ARMS: chestnut-brown feathered arms that end in cream feathered HANDS (a feather thumb and three "
                   "broad rounded feather fingers, like a mitten glove made of feathers), legs in dark brown trousers with tan leather shoes." + _BODY,
            "head": "the HEAD with the two ear tufts and the round gold glasses (empty lenses), but a BLANK FACE: no eyes, no beak, no mouth, no eyebrows, no neck",
            "mouths": "(1) a small closed orange BEAK seen from the front, pointing down; (2) the same BEAK half open; (3) the same BEAK wide open with a pink tongue"},
    "bear": {"who": "a big friendly cartoon BEAR mascot, warm and gentle: honey-brown fur, a light tan muzzle with a dark brown nose, small round ears, a chunky knitted jumper in soft teal with a cream "
                    "zigzag band across the chest, the jumper's long sleeves on the arms, honey-brown paw-hands with a thumb and three rounded fingers (no claws), legs in dark blue trousers with "
                    "brown boots. A broad, soft, huggable build." + _BODY,
             "head": "the HEAD with the round ears, the tan muzzle and the nose, but a BLANK FACE: no eyes, no mouth, no eyebrows, no neck",
             "mouths": "(1) a closed smiling MOUTH; (2) a half open MOUTH; (3) a wide open MOUTH with tongue"},
    "cat": {"who": "a friendly cartoon CAT mascot, curious and clever: grey fur with darker grey tabby stripes on the forehead, a white muzzle with a small pink nose, tall pointed ears with pink insides, "
                   "a bright orange hoodie with the hood down and a white drawstring, the hoodie's long sleeves on the arms, white paw-hands with a thumb and three rounded fingers (no claws), "
                   "legs in dark navy trousers with white-and-red sneakers. No tail piece." + _BODY,
            "head": "the HEAD with the pointed ears, the white muzzle, the small pink nose and three short whiskers on each cheek, but a BLANK FACE: no eyes, no mouth, no eyebrows, no neck",
            "mouths": "(1) a closed smiling MOUTH; (2) a half open MOUTH; (3) a wide open MOUTH with tongue"},
    "parrot": {"who": "a friendly cartoon PARROT mascot (a scarlet macaw), bright and cheerful: scarlet-red feathers, a white face patch, a small crest of three red feathers on top of the head, "
                      "a small sunny-yellow neckerchief tied at the neck, a red feathered chest, the WINGS drawn as ARMS: the upper arm red, the lower arm with a yellow band and then blue feathers, "
                      "ending in bright blue feathered HANDS (a feather thumb and three broad rounded feather fingers, like a mitten glove made of feathers), legs covered in red feathers like "
                      "trousers, ending in dark grey boots. No tail piece." + _BODY,
               "head": "the HEAD with the crest and the white face patch, but a BLANK FACE: no eyes, no beak, no mouth, no eyebrows, no neck",
               "mouths": "(1) a closed curved parrot BEAK seen from the front, pale yellow upper beak with a dark tip, hooked, pointing down; (2) the same BEAK half open; (3) the same BEAK wide open with a pink tongue"},
    "turtle": {"who": "a friendly cartoon TURTLE mascot, slow, wise and kind: soft green skin, a round smooth bald head, a domed olive-brown shell on the back whose rim shows behind the body, "
                      "a cream-yellow belly plate on the front, the two orange shoulder straps of a small backpack over the chest, bare green arms ending in green hands with a thumb and three rounded "
                      "fingers, legs in sand-coloured shorts-like trousers down to the ankle with sturdy brown hiking boots. No tail piece." + _BODY,
               "head": "the HEAD: round, bald and green with two tiny nostrils, but a BLANK FACE: no eyes, no mouth, no eyebrows, no neck",
               "mouths": "(1) a closed smiling MOUTH; (2) a half open MOUTH; (3) a wide open MOUTH with tongue"},
}
LAYOUT_ANIMAL = (
    "Character rig parts sheet for 2D cut-out animation of ONE friendly cartoon character: {who} Flat cartoon explainer style, bold dark outlines of equal weight, solid flat colours, "
    "no gradients, no shading, no text, no labels. Simple friendly appealing design. Every part is drawn SEPARATE, straight, front-facing, un-rotated and fully visible, with wide gaps between parts, "
    "on a plain flat white background. Strict layout, 4 columns, 3 rows, in this exact order. "
    "ROW 1: (1) {head}; "
    "(2) the TORSO: the body with its clothing only, front view, no head, no arms, no legs, no tail, ending at the waist; "
    "(3) one UPPER ARM: shoulder to elbow only, a long straight piece with a round top, hanging straight down; "
    "(4) one LOWER ARM with the hand: elbow to finger tips, a long straight piece hanging straight down, ending in an open relaxed hand in a clearly different colour from the forearm. "
    "ROW 2: (1) one UPPER LEG: hip to knee only, a long straight trouser leg, straight down; "
    "(2) one LOWER LEG: knee to foot, a long straight leg with the shoe, the shoe seen from the side pointing to the RIGHT; "
    "(3) a pair of OPEN EYES (two round eyes with highlights, with eyebrows above them); "
    "(4) a pair of CLOSED EYES (two simple curved lashes lines, with eyebrows above them). "
    "ROW 3: {mouths}; the 4th cell of row 3 stays empty."
)


def spent(run: str = "") -> float:
    tot = 0.0
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if not run or j.get("run") == run:
                tot += float(j.get("usd", 0))
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--cap", type=float, default=1.0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--tag", default="")
    ap.add_argument("--animals", action="store_true", help="the animal cast instead of the first five; --cap then counts the animal sheets only")
    a = ap.parse_args()
    api = cg.openai_api("qa")
    os.makedirs(a.out, exist_ok=True)
    run = RUN_ANIMALS if a.animals else RUN
    for name, who in (ANIMALS if a.animals else CAST).items():
        if a.only and name not in a.only:
            continue
        if spent(run if a.animals else "") + 0.06 > a.cap:
            print("cap reached, stopping")
            return 1
        prompt = LAYOUT_ANIMAL.format(**who) if a.animals else LAYOUT.format(who=who)
        res = api({"model": cg.OPENAI_MODEL, "prompt": prompt, "size": "1536x1024", "quality": "medium", "output_format": "png", "n": 1})
        cost = cg.real_cost(res.get("usage") or {})
        path = os.path.join(a.out, f"sheet_{name}{a.tag}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": run, "item": f"sheet_{name}{a.tag}",
                                "what": f"{cg.OPENAI_MODEL} 1536x1024 medium rig parts sheet", "usd": round(cost, 4), "run_total": round(spent(run if a.animals else "") + cost, 5)}) + "\n")
        print(f"{name}: {path} cost {cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
