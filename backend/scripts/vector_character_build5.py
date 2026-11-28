#!/usr/bin/env python3
"""Build the five-character cast (docs/CHARACTER_LIBRARY.md) from the rig-parts sheets with the same cutter as vector_character_build.py.

  python backend/scripts/vector_character_build5.py SHEETS_DIR [--only ID ...] [--cut ID=0.2 ...] [--tag _b]

The animal cast (owl, bear, cat, parrot, turtle) is built only when named in --only; it also gets its face layout and meta.json (ANIMAL_FACE, ANIMAL_META).
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

import vector_character_build as vb  # noqa: E402


def find_pieces(rgba):
    """vb.find_pieces plus: the eye sets of these sheets carry eyebrows ABOVE the eyes (separate shapes): stacked small shapes are merged into one piece."""
    solid = rgba[..., 3] >= 200
    lab, n = ndi.label(ndi.binary_dilation(solid, iterations=5))
    boxes = []
    for i, s in enumerate(ndi.find_objects(lab), 1):
        if s is None:
            continue
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if (y1 - y0) * (x1 - x0) < 900:
            continue
        boxes.append([x0, y0, x1, y1, i])

    def merge_pass(test):
        merged = True
        while merged:
            merged = False
            for a in range(len(boxes)):
                for b in range(a + 1, len(boxes)):
                    A, B = boxes[a], boxes[b]
                    if test(A, B):
                        boxes[a] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3]), A[4]]
                        lab[lab == B[4]] = A[4]
                        del boxes[b]
                        merged = True
                        break
                if merged:
                    break

    def side(A, B):
        small = max(A[2] - A[0], A[3] - A[1], B[2] - B[0], B[3] - B[1]) < 220
        gap = max(A[0], B[0]) - min(A[2], B[2])
        cy = abs((A[1] + A[3]) / 2 - (B[1] + B[3]) / 2)
        return small and gap < 110 and cy < 50

    def stacked(A, B):
        for X in (A, B):
            if X[3] - X[1] > 230 or X[2] - X[0] > 420:
                return False
        ov = min(A[2], B[2]) - max(A[0], B[0])
        vgap = max(A[1], B[1]) - min(A[3], B[3])
        return ov > 0.5 * min(A[2] - A[0], B[2] - B[0]) and vgap < 110

    merge_pass(side)      # eyebrows pair, eye pair
    merge_pass(stacked)   # brows over eyes
    rows = []
    for bx in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        for r in rows:
            if abs((r[0][1] + r[0][3]) / 2 - (bx[1] + bx[3]) / 2) < 140:
                r.append(bx)
                break
        else:
            rows.append([bx])
    ordered = [b for r in rows for b in sorted(r, key=lambda b: b[0])]
    return [((x0, y0, x1, y1), lab[y0:y1, x0:x1] == i) for x0, y0, x1, y1, i in ordered]


vb.find_pieces = find_pieces

# fraction of the torso width cut away at each side (the torso art has its own hanging sleeves, the rig has separate arms): set by eye per character
CUT = {"ines": 0.17, "david": 0.16, "priya": 0.17, "mateo": 0.17, "fox": 0.2}
# the animal cast (vector_character_sheet5.py --animals): 0 = the torso was drawn without sleeves, nothing is cut. `--only` is needed to build one of them.
ANIMAL_CUT = {"owl": 0.0, "bear": 0.0, "cat": 0.17, "parrot": 0.0, "turtle": 0.0}
# Where the eyes and the mouth sit on each animal's head, set by eye (manifest "face", read by engine/vector_presenter.py): eyes_y / mouth_y = share of the head's height from
# the top, eyes_w / mouth_w = width as a share of the head's width, mouth_anchor "top" = a beak, which hangs from its top edge and opens downward.
ANIMAL_FACE = {
    "owl": {"eyes_y": 0.50, "eyes_w": 0.52, "mouth_y": 0.62, "mouth_w": 0.20, "mouth_anchor": "top"},      # the eyes sit in the glasses, the beak just under them
    "bear": {"eyes_y": 0.43, "eyes_w": 0.46, "mouth_y": 0.84, "mouth_w": 0.24},                             # the eyes above the nose, the mouth on the muzzle under it
    "parrot": {"eyes_y": 0.50, "eyes_w": 0.44, "mouth_y": 0.60, "mouth_w": 0.30, "mouth_anchor": "top"},   # a big hooked beak in the middle of the white face patch
    "turtle": {"eyes_y": 0.55, "eyes_w": 0.46, "mouth_y": 0.78},
}


def fill_notch(im, rgba, pieces):
    """A waistcoat whose two fronts end in points leaves an open V at the bottom centre; on the rig the backdrop would show through it between the legs. The notch is
    filled with the trousers' colour (read from the sheet's upper-leg piece) down to the hem line of the points, so it reads as the top of the trousers."""
    from PIL import Image

    (x0, y0, x1, y1), mask = pieces[4]
    leg = rgba[y0:y1, x0:x1][mask & (rgba[y0:y1, x0:x1, 3] >= 200)]
    leg = leg[leg[:, :3].astype(np.int32).sum(axis=1) > 120]                    # not the outline
    colour = tuple(int(v) for v in np.median(leg[:, :3], axis=0)) + (255,)
    a = np.array(im)
    h, w = a.shape[:2]
    solid = a[..., 3] > 0
    for x in range(int(w * 0.25), int(w * 0.75)):
        ys = np.nonzero(solid[:, x])[0]
        if ys.size and ys.max() < h - 4:
            a[ys.max():h - 3, x] = colour
    return Image.fromarray(a)


def one_colour(im, rgba, pieces):
    """The parrot's upper arm was drawn red, yellow and blue, and so was its forearm: on the rig the bands would repeat down the arm. The upper arm becomes plain red
    (the colour of its own top), so the arm reads red at the shoulder, then the yellow band, then blue to the hand."""
    from PIL import Image

    a = np.array(im)
    rgb = a[..., :3].astype(np.int32)
    fill = (a[..., 3] > 0) & (rgb.sum(axis=-1) > 200)
    top = fill.copy()
    top[int(a.shape[0] * 0.3):] = False
    a[fill, :3] = np.median(a[top][:, :3], axis=0).astype(np.uint8)
    return Image.fromarray(a)


def plain_face(im, rgba, pieces):
    """The turtle's head was drawn with two nostrils low on the face, where the mouth piece goes: they are painted over with the head's own colour."""
    from PIL import Image

    a = np.array(im)
    rgb = a[..., :3].astype(np.int32)
    solid = a[..., 3] > 0
    ink = solid & (rgb.sum(axis=-1) < 330)
    lab, n = ndi.label(ink)
    border = set(np.unique(lab[ndi.binary_dilation(~solid, iterations=3) & ink])) - {0}       # the outline touches the outside; marks inside the face do not
    inner = ink & ~np.isin(lab, list(border))
    a[ndi.binary_dilation(inner, iterations=3) & solid & ~np.isin(lab, list(border)), :3] = np.median(a[solid & ~ink][:, :3], axis=0).astype(np.uint8)
    return Image.fromarray(a)


vb.PIECE_POST[("owl", "torso")] = fill_notch
vb.PIECE_POST[("turtle", "head")] = plain_face
vb.PIECE_POST[("parrot", "upper_arm")] = one_colour
_RIG = "biped front-facing cut-out (head, torso, upper/lower arm, upper/lower leg, 2 eye sets, 3 mouths)"
ANIMAL_META = {
    "owl": {"name": "Otto", "role": "professor", "species": "owl (bipedal mascot)", "age_group": "ageless", "tags": ["mascot", "animal", "professor", "calm", "learning", "kids", "explainer"],
            "voice_hint": {"en": ["Brian", "Matthew"], "es": ["Sergio", "Pedro"]}, "personality": "calm, wise, patient", "suitable_topics": ["learning", "science", "history", "how it works"],
            "outfit": "round gold glasses, olive tweed waistcoat, dark-red bow tie, brown trousers, tan shoes", "skin": "chestnut-brown feathers, cream face and hands", "hair": "n/a"},
    "bear": {"name": "Bruno", "role": "wellbeing friend", "species": "bear (bipedal mascot)", "age_group": "ageless", "tags": ["mascot", "animal", "warm", "gentle", "health", "feelings", "kids", "bedtime"],
             "voice_hint": {"en": ["Stephen", "Matthew"], "es": ["Andres", "Pedro"]}, "personality": "warm, gentle, reassuring", "suitable_topics": ["health", "feelings", "bedtime", "wellbeing", "kids"],
             "outfit": "teal knitted jumper with a cream zigzag, blue trousers, brown boots", "skin": "honey-brown fur", "hair": "n/a"},
    "cat": {"name": "Mika", "role": "tech explorer", "species": "cat (bipedal mascot)", "age_group": "ageless", "tags": ["mascot", "animal", "curious", "clever", "technology", "kids", "explainer"],
            "voice_hint": {"en": ["Olivia", "Salli"], "es": ["Mia", "Lucia"]}, "personality": "curious, clever, quick", "suitable_topics": ["technology", "how things work", "gadgets", "coding"],
            "outfit": "orange hoodie, navy trousers, white-and-red sneakers", "skin": "grey tabby fur, white paws", "hair": "n/a"},
    "parrot": {"name": "Paco", "role": "language and travel guide", "species": "parrot, scarlet macaw (bipedal mascot)", "age_group": "ageless",
               "tags": ["mascot", "animal", "bright", "cheerful", "languages", "travel", "fun facts", "spanish", "kids"],
               "voice_hint": {"en": ["Nate", "Matthew"], "es": ["Pedro", "Sergio"]}, "personality": "bright, cheerful, talkative", "suitable_topics": ["languages", "travel", "fun facts", "kids (Spanish)"],
               "outfit": "yellow neckerchief, grey boots", "skin": "scarlet feathers, blue feathered hands", "hair": "n/a"},
    "turtle": {"name": "Tula", "role": "nature guide", "species": "turtle (bipedal mascot)", "age_group": "ageless", "tags": ["mascot", "animal", "slow", "wise", "nature", "sea", "step by step", "kids"],
               "voice_hint": {"en": ["Amy", "Ruth"], "es": ["Lupe", "Lucia"]}, "personality": "slow, wise, kind", "suitable_topics": ["nature", "the sea", "step-by-step tutorials", "patience"],
               "outfit": "small backpack with orange straps, sand trousers, brown hiking boots", "skin": "soft green, olive shell", "hair": "n/a"},
}


def finish_animal(cid: str, out: str) -> None:
    """The settings a sheet cannot give: the face layout into manifest.json and the character's meta.json."""
    folder = os.path.join(out, cid)
    mp = os.path.join(folder, "manifest.json")
    man = json.load(open(mp, encoding="utf-8"))
    if cid in ANIMAL_FACE:
        man["face"] = ANIMAL_FACE[cid]
        json.dump(man, open(mp, "w", encoding="utf-8"), indent=1)
    meta = {**ANIMAL_META[cid], "id": cid, "rig": _RIG, "provenance": {"model": "gpt-image-2.6-flare", "sheet": "1536x1024 medium rig parts sheet",
                                                                       "generated": datetime.date.today().isoformat(), "script": "backend/scripts/vector_character_sheet5.py --animals"}}
    old = os.path.join(folder, "meta.json")
    if os.path.exists(old):
        meta["provenance"]["generated"] = json.load(open(old, encoding="utf-8")).get("provenance", {}).get("generated", meta["provenance"]["generated"])
    json.dump(meta, open(old, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheets")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--cut", nargs="*", default=[])
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "lambdas", "engine", "assets", "vector_characters"))
    a = ap.parse_args()
    for c in a.cut:
        k, v = c.split("=")
        CUT[k] = float(v)
    CUT.update({k: v for k, v in ANIMAL_CUT.items() if k not in CUT and k in (a.only or [])})
    vb.TORSO_CUT.update(CUT)
    for cid in CUT:
        if a.only and cid not in a.only:
            continue
        man = vb.build(os.path.join(a.sheets, f"sheet_{cid}{a.tag}.png"), cid, a.out)
        if cid in ANIMAL_CUT:
            finish_animal(cid, a.out)
        tot = sum(p["svg_bytes"] for p in man["parts"].values())
        print(cid, f"svg total {tot / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
