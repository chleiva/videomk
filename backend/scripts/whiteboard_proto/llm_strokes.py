#!/usr/bin/env python3
"""Method C (the research's fallback): a language model WRITES the drawing as ordered pen strokes, then looks at its own drawing and fixes it (the SketchAgent idea).

  AWS_PROFILE=qa AWS_REGION=eu-west-1 llm_strokes.py [--rounds 2]   -> WORK/llm_strokes/<name>.json (+ a picture of every round)

Uses the engine's own model call (engine/llm.py, Sonnet 5.5 on Bedrock). Every call's cost goes to the spend log.
"""
import argparse
import io
import json
import os
import re
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lambdas"))
sys.path.insert(0, HERE)

import wbcommon as common  # noqa: E402
import vectorize as vz  # noqa: E402

OUT = os.path.join(common.WORK, "llm_strokes")
SUBJECTS = {
    "sun": "a sun: a circle with short rays around it",
    "raincloud": "a rain cloud with short rain strokes falling from it",
    "plant": "a small plant growing from a little mound of soil: one stem with four leaves",
    "mountain": "a mountain with a zigzag snow cap on its peak",
    "waves": "a patch of sea: three rows of rolling waves",
    "person": "a simple standing person with a round head and no face, one arm raised in a wave",
}
SYSTEM = """You draw simple whiteboard marker doodles as pen strokes, the way a skilled teacher draws on a whiteboard: clear, friendly, few details, closed outlines.
The canvas is 100 wide and 100 high; x grows to the right, y grows DOWN. Keep the drawing inside 8..92.
Answer ONLY with JSON: {"strokes": [{"part": "<what this stroke is>", "smooth": true|false, "closed": true|false, "pts": [[x, y], ...]}]}
* Strokes are in the order a person would draw them (main outline first, details after), each in the direction a right-handed person draws it.
* "smooth": true means the pen passes through the points as one flowing curve (give 6 to 24 points along it); false means straight lines between the points (corners).
* "closed": true joins the last point back to the first.
* 3 to 16 strokes. One marker, one line weight, no shading, no text."""


def parse(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0))
    strokes = []
    for s in data["strokes"]:
        p = np.array(s["pts"], np.float32)
        if len(p) < 2:
            continue
        if s.get("closed"):
            p = np.concatenate([p, p[:1]])
        strokes.append({"part": s.get("part", ""), "smooth": bool(s.get("smooth")), "pts": p})
    return strokes


def to_curves(strokes, unit: float = 6.0):
    """Model points (0..100) -> smooth pen paths in a 600-unit box (Catmull-Rom through the points for smooth strokes)."""
    out = []
    for s in strokes:
        p = s["pts"].astype(np.float64) * unit
        if s["smooth"] and len(p) >= 3:
            closed = bool(np.allclose(p[0], p[-1]))
            q = np.concatenate([p[-2:-1], p, p[1:2]]) if closed else np.concatenate([p[:1], p, p[-1:]])
            seg = []
            for i in range(1, len(q) - 2):
                p0, p1, p2, p3 = q[i - 1], q[i], q[i + 1], q[i + 2]
                t = np.linspace(0, 1, 14, endpoint=False)[:, None]
                seg.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            p = np.concatenate(seg + [p[-1:]])
        out.append(p.astype(np.float32))
    return out


def picture(strokes) -> bytes:
    pkg = vz.from_strokes(to_curves(strokes), 14.0, 600, 600)
    a = vz.svg_alpha(pkg["ink"], 600, 600, 512 / 600)
    b = io.BytesIO()
    Image.fromarray((255 - a * 255).astype(np.uint8)).convert("RGB").save(b, "JPEG", quality=88)
    return b.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    from engine import llm

    os.makedirs(OUT, exist_ok=True)
    for name, subject in SUBJECTS.items():
        if a.only and name not in a.only.split(","):
            continue
        dst = os.path.join(OUT, name + ".json")
        if os.path.exists(dst):
            print(name, "exists")
            continue
        t0, cost = time.time(), 0.0
        common.reserve("llm strokes", 0.12)
        text, meta = llm.complete(SYSTEM, f"Draw {subject}.", max_tokens=6000, effort="medium")
        cost += meta["cost_usd"]
        strokes = parse(text)
        for r in range(a.rounds):
            jpg = picture(strokes)
            open(os.path.join(OUT, f"{name}_round{r}.jpg"), "wb").write(jpg)
            prev = json.dumps({"strokes": [{"part": s["part"], "smooth": s["smooth"], "closed": False, "pts": s["pts"].round(1).tolist()} for s in strokes]})
            text, meta = llm.complete(SYSTEM, f"Image 1 is your drawing of: {subject}. It was rendered from these strokes:\n{prev}\n"
                                      "Look at it critically: is it instantly recognisable, well proportioned, are shapes closed, do parts meet where they should, is anything crooked or misplaced? "
                                      "Return the complete corrected JSON (all strokes).", images=[jpg], max_tokens=6000, effort="medium")
            cost += meta["cost_usd"]
            try:
                strokes = parse(text)
            except Exception as e:
                print(name, "round", r, "unreadable answer, keeping the previous strokes:", type(e).__name__)
        open(os.path.join(OUT, f"{name}_final.jpg"), "wb").write(picture(strokes))
        json.dump({"subject": subject, "strokes": [{"part": s["part"], "smooth": s["smooth"], "pts": s["pts"].tolist()} for s in strokes], "cost_usd": cost, "seconds": time.time() - t0}, open(dst, "w"))
        common.charge(f"llm strokes {meta['model']} 1 draw + {a.rounds} look-and-fix", cost, item=name, seconds=round(time.time() - t0, 1))
    return 0


def load(name: str):
    d = json.load(open(os.path.join(OUT, name + ".json")))
    return to_curves([{"part": s["part"], "smooth": s["smooth"], "pts": np.array(s["pts"], np.float32)} for s in d["strokes"]]), d


if __name__ == "__main__":
    sys.exit(main())
