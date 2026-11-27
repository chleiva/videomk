#!/usr/bin/env python3
"""Hand shapes (and the fox's tail) for the standing presenter rig (engine/vector_presenter.py, docs/CHARACTER_LIBRARY.md "Second pass").

One sheet per character from the same image model as the parts sheet: five RIGHT hands in a row, upright, palm to the viewer, each with a short wrist stub
(open palm, one, two, three, thumb up); the fox sheet has a sixth piece, the tail. The pieces are cut, tinted to the exact skin colour of the character's own forearm piece,
vectorised with the same tracer as the body, and listed in <character>/presenter.json. Every call is appended to docs/vector_character_spend.jsonl (run "vector-character-hands").

  AWS_PROFILE=qa python backend/scripts/vector_character_hands.py generate --out DIR [--only ID ...] [--cap 3.0] [--tag _b]
  python backend/scripts/vector_character_hands.py build DIR [--only ID ...] [--tag _b]
"""
import argparse
import base64
import datetime
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")

LEDGER = os.path.join(HERE, "..", "..", "docs", "vector_character_spend.jsonl")
RUN = "vector-character-hands"
ASSETS = os.path.join(HERE, "..", "lambdas", "engine", "assets", "vector_characters")
NAMES = ["open", "one", "two", "three", "thumb"]
# Where the thumb is on each character's ORIGINAL forearm+hand drawing (lower_arm.svg, hanging down): +1 on the right of the drawing, -1 on the left. Read by eye from the
# pieces (the relaxed hands are too small and too symmetric to measure reliably); the rig mirrors the drawing so that the thumb ends up on the body side of each arm.
RELAXED_THUMB = {"ines": -1, "david": 1, "priya": 1, "mateo": -1, "fox": -1}
SHRINK = 0.42

WHO = {
    "ines": "an older woman with warm light-tan skin; each wrist stub ends in the knitted cuff of a dusty-rose cardigan",
    "david": "a young Black man with dark brown skin; each wrist stub ends in the cuff of a mustard-yellow hoodie",
    "priya": "a South Asian woman with medium brown skin; each wrist stub ends in the cuff of a white lab coat",
    "mateo": "a man with medium olive-tan skin; bare wrists",
    "fox": "a cartoon fox mascot: cream-coloured paw-hands with a thumb and three rounded fingers, no claws; each wrist stub is dark brown fur",
}
LAYOUT = (
    "Hand poses sheet for 2D cut-out animation, for ONE character: {who}. Flat cartoon explainer style, bold dark outlines of equal weight, solid flat colours, no gradients, "
    "no shading, no text, no labels, no numbers. The skin colour is exactly {skin}. {n} separate pieces in ONE horizontal row with wide empty gaps between them, on a plain flat white background. "
    "Every hand is a RIGHT hand drawn large, UPRIGHT (the wrist at the bottom, the fingers pointing straight up), seen from the PALM side, with a short straight wrist stub below it that is cut flat at the bottom. "
    "Correct anatomy, friendly rounded fingers. In this exact order, left to right: "
    "(1) an OPEN HAND, palm to the viewer, the four fingers straight and close together, the thumb out to the side: a relaxed presenting hand; "
    "(2) NUMBER ONE: only the index finger straight up, the other fingers folded into the palm, the thumb folded over them; "
    "(3) NUMBER TWO: the index and middle fingers straight up and slightly apart, the others folded; "
    "(4) NUMBER THREE: the index, middle and ring fingers straight up, the little finger folded and held by the thumb; "
    "(5) THUMBS UP: a closed fist with the thumb pointing straight up{tail}."
)
TAIL = "; (6) a big bushy FOX TAIL on its own: orange-red fur with a cream tip, a gentle S curve, the root (where it joins the body) at the bottom, the tip at the top"


def spent(run: str = RUN) -> float:
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


def skin_hex(cid: str) -> str:
    from engine import vector_presenter as vp

    r, g, b = vp.load(cid, 2.0).skin
    return f"#{r:02x}{g:02x}{b:02x}"


def generate(a) -> int:
    import catalog_generate as cg

    api = cg.openai_api("qa")
    os.makedirs(a.out, exist_ok=True)
    for cid, who in WHO.items():
        if a.only and cid not in a.only:
            continue
        if spent() + 0.06 > a.cap:
            print("cap reached, stopping")
            return 1
        prompt = LAYOUT.format(who=who, skin=skin_hex(cid), n="SIX" if cid == "fox" else "FIVE", tail=TAIL if cid == "fox" else "")
        res = api({"model": cg.OPENAI_MODEL, "prompt": prompt, "size": "1536x1024", "quality": "medium", "output_format": "png", "n": 1})
        cost = cg.real_cost(res.get("usage") or {})
        path = os.path.join(a.out, f"hands_{cid}{a.tag}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": RUN, "item": f"hands_{cid}{a.tag}",
                                "what": f"{cg.OPENAI_MODEL} 1536x1024 medium hand shapes sheet", "usd": round(cost, 4), "run_total": round(spent() + cost, 5)}) + "\n")
        print(f"{cid}: {path} cost {cost:.4f}")
    return 0


def to_rgba(im: Image.Image) -> np.ndarray:
    """The sheet with its plain background made transparent (flood from the border over near-background colours), unless it already has transparency."""
    arr = np.array(im.convert("RGBA"))
    if (arr[..., 3] < 200).mean() > 0.2:
        return arr
    bg = np.median(np.concatenate([arr[:6].reshape(-1, 4), arr[-6:].reshape(-1, 4)]), axis=0)[:3]
    close = np.abs(arr[..., :3].astype(np.int32) - bg).sum(axis=-1) < 36
    lab, _ = ndi.label(close)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    arr[np.isin(lab, list(border)), 3] = 0
    return arr


def pieces(arr: np.ndarray):
    solid = arr[..., 3] >= 200
    lab, _ = ndi.label(ndi.binary_dilation(solid, iterations=4))
    out = []
    for i, s in enumerate(ndi.find_objects(lab), 1):
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if (y1 - y0) * (x1 - x0) < 6000:
            continue
        part = arr[y0:y1, x0:x1].copy()
        part[~((lab[y0:y1, x0:x1] == i) & solid[y0:y1, x0:x1])] = (20, 18, 24, 0)
        part[part[..., 3] > 0, 3] = 255
        out.append((x0, Image.fromarray(part).crop(Image.fromarray(part).getbbox())))
    return [im for _, im in sorted(out, key=lambda t: t[0])]


def tint_to(im: Image.Image, skin, tol: int = 90) -> Image.Image:
    """Move the hand's main fill colour onto the character's skin colour (the model's colour is close, not exact). Outline and cuff colours stay."""
    arr = np.array(im).astype(np.float32)
    rgb = arr[..., :3]
    op = arr[..., 3] > 0
    fill = op & (rgb.sum(axis=-1) > 200)
    top = fill.copy()
    top[int(arr.shape[0] * 0.7):] = False                         # the upper part is hand, the bottom may be a cuff
    if not top.any():
        return im
    med = np.median(rgb[top], axis=0)
    sel = fill & (np.abs(rgb - med).sum(axis=-1) < tol)
    rgb[sel] = np.clip(rgb[sel] * (np.array(skin, dtype=np.float32) / np.maximum(med, 1.0)), 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def cut_cuff(im: Image.Image, skin) -> Image.Image:
    """Drop the sleeve cuff (or fur) below the wrist: the rig's own forearm piece has it, and the hand tucks under it. The cut is the lowest row that is mostly skin."""
    arr = np.array(im)
    rgb = arr[..., :3].astype(np.int32)
    fill = (arr[..., 3] > 0) & (rgb.sum(axis=-1) > 200)
    near = fill & (np.abs(rgb - np.array(skin)).sum(axis=-1) < 60)
    run = 0
    for y in range(im.height - 1, im.height // 2, -1):
        n = fill[y].sum()
        run = run + 1 if n and near[y].sum() / n > 0.8 else 0
        if run >= 4:
            return im.crop((0, 0, im.width, y + 4)).crop(im.crop((0, 0, im.width, y + 4)).getbbox())
    return im


def thumb_side(svg: str, meta) -> str:
    """Side of the open hand (upright, as on the sheet) where the thumb sticks out: the palm rows reach further from the wrist line on that side."""
    import io

    import resvg_py

    im = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_path=svg, width=meta["w"], height=meta["h"])))).convert("RGBA")
    al = np.array(im)[..., 3] > 96
    cx = meta["pivot"][0]
    rows = [np.nonzero(al[y])[0] for y in range(int(im.height * 0.45), int(im.height * 0.85))]
    rows = [r for r in rows if r.size]
    return "left" if max(cx - r.min() for r in rows) >= max(r.max() - cx for r in rows) else "right"


def build(a) -> int:
    import vector_character_build as vb
    from engine import vector_presenter as vp

    for cid in WHO:
        if a.only and cid not in a.only:
            continue
        sheet = os.path.join(a.sheets, f"hands_{cid}{a.tag}.png")
        if not os.path.exists(sheet):
            print(cid, "no sheet")
            continue
        ps = pieces(to_rgba(Image.open(sheet)))
        want = len(NAMES) + (1 if cid == "fox" else 0)
        if len(ps) != want:
            print(f"{cid}: found {len(ps)} pieces, expected {want}: regenerate the sheet")
            continue
        folder = os.path.join(ASSETS, cid)
        vp.load.cache_clear()
        skin = vp.Presenter(folder, 2.0).skin
        pj = os.path.join(folder, "presenter.json")
        cfg = json.load(open(pj)) if os.path.exists(pj) else {}
        hands = {}
        for name, im in zip(NAMES, ps):
            im = cut_cuff(tint_to(im, skin), skin)
            im = im.resize((round(im.width * SHRINK), round(im.height * SHRINK)), Image.LANCZOS)      # hands are small on screen: half the sheet's size keeps the SVG light
            size = vb.trace(im, os.path.join(folder, f"hand_{name}.svg"), os.path.join(folder, "_tmp.png"))
            al = np.array(im)[..., 3] > 0
            xs = np.nonzero(al[-max(3, im.height // 30):].any(axis=0))[0]
            hands[name] = {"file": f"hand_{name}.svg", "w": im.width, "h": im.height, "svg_bytes": size, "pivot": [float((xs.min() + xs.max()) / 2), float(im.height - im.height * 0.06)],
                           "wrist_w": float(xs.max() - xs.min() + 1), "scale": (cfg.get("hands", {}).get(name, {}) or {}).get("scale", 1.0)}
        cfg["hands"] = hands
        cfg["relaxed_thumb"] = RELAXED_THUMB[cid]
        cfg["sheet_thumb"] = thumb_side(os.path.join(folder, "hand_open.svg"), hands["open"])      # "left" for a right hand seen from the palm, upright
        if cid == "fox":
            im = ps[-1]
            im = im.resize((round(im.width * SHRINK), round(im.height * SHRINK)), Image.LANCZOS)
            size = vb.trace(im, os.path.join(folder, "tail.svg"), os.path.join(folder, "_tmp.png"))
            al = np.array(im)[..., 3] > 0
            xs = np.nonzero(al[-max(3, im.height // 25):].any(axis=0))[0]
            old = cfg.get("tail", {})
            cfg["tail"] = {"file": "tail.svg", "w": im.width, "h": im.height, "svg_bytes": size, "pivot": [float((xs.min() + xs.max()) / 2), float(im.height * 0.96)],
                           "height_u": old.get("height_u", 78.0), "x": old.get("x", 10.0), "y": old.get("y", 8.0), "angle": old.get("angle", -52.0)}
        tmp = os.path.join(folder, "_tmp.png")
        if os.path.exists(tmp):
            os.remove(tmp)
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        print(cid, "hands", {k: (v["w"], v["h"]) for k, v in hands.items()}, "tail" if cid == "fox" else "")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--out", required=True)
    g.add_argument("--cap", type=float, default=3.0)
    b = sub.add_parser("build")
    b.add_argument("sheets")
    for p in (g, b):
        p.add_argument("--only", nargs="*")
        p.add_argument("--tag", default="")
    a = ap.parse_args()
    return generate(a) if a.cmd == "generate" else build(a)


if __name__ == "__main__":
    sys.exit(main())
