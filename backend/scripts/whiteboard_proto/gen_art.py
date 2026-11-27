#!/usr/bin/env python3
"""Generate marker line-art sheets in ONE house style with the image model the catalogs use (scripts/catalog_generate.py).

  gen_art.py sheet1 [sheet2 ...] [--quality medium|high] [--force]

A sheet is one picture holding several objects on a grid; trace.py cuts it apart. Every call is reserved against the
USD 3 cap before it is made and its real cost (from the response's token usage) is logged afterwards.
"""
import argparse
import base64
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lambdas"))
sys.path.insert(0, HERE)

import wbcommon as common  # noqa: E402

# The house style: one paragraph, never changed between sheets. The subject list is the only thing that varies.
HOUSE = (
    "A sheet of simple hand-drawn whiteboard doodles for an explainer video. Black marker line drawings on a pure white background. "
    "One thick, even, confident black marker line of the SAME weight for every drawing, as if drawn with one chisel-free round-tip whiteboard marker. "
    "Outlines only: no shading, no hatching, no grey, no colour, no solid black areas, no gradients, no shadows, no background, no frame, no grid lines. "
    "Friendly, clear, slightly loose hand-drawn shapes with closed outlines and few details, like a skilled teacher draws on a whiteboard. "
    "No text, no letters, no numbers, no labels, no faces. "
    "Exactly {n} separate drawings arranged on an invisible {cols} by {rows} grid, each centred in its own cell, all about the same size, with wide empty white space between them; no drawing touches another. "
    "In reading order (left to right, top row first): {subjects}."
)

SHEETS = {
    "sheet1": (3, 2, [
        "a sun: a circle with short straight rays around it",
        "a fluffy cumulus cloud",
        "a mountain with a zigzag snow cap on its peak",
        "a small plant growing from a little mound of soil, one stem with four leaves",
        "a six-armed snowflake",
        "a patch of sea: three rows of rolling ocean waves",
    ]),
    "sheet2": (3, 2, [
        "a leafy tree with a round crown and a trunk",
        "a single water drop",
        "a rain cloud with short rain strokes falling from it",
        "a winding river between two banks",
        "a little house with a pitched roof, a door and a window",
        "a thermometer",
    ]),
    "sheet3": (3, 2, [
        "a simple standing person: round head with no face, simple body, arms and legs, one arm raised in a wave",
        "a simple person walking, round head with no face",
        "a light bulb",
        "a bicycle",
        "a fish",
        "an open book",
    ]),
}

SIZE = "2048x1152"
RESERVE = {"medium": 0.045, "high": 0.06}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheets", nargs="+")
    ap.add_argument("--quality", default="medium")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    import catalog_generate as cg

    api = cg.openai_api("qa")
    for name in a.sheets:
        cols, rows, subjects = SHEETS[name]
        out = os.path.join(common.ART, f"{name}{a.suffix}.png")
        if os.path.exists(out) and not a.force:
            print(f"{out} exists (use --force to pay again)")
            continue
        prompt = HOUSE.format(n=len(subjects), cols=cols, rows=rows, subjects="; ".join(f"({i + 1}) {s}" for i, s in enumerate(subjects)))
        common.reserve(f"image {name}", RESERVE[a.quality])
        t0 = time.time()
        res = api({"model": cg.OPENAI_MODEL, "prompt": prompt, "size": SIZE, "quality": a.quality, "output_format": "png", "n": 1})
        dt = time.time() - t0
        cost = cg.real_cost(res.get("usage") or {}) or RESERVE[a.quality]
        common.charge(f"image {cg.OPENAI_MODEL} {SIZE} {a.quality}", cost, item=name + a.suffix, seconds=round(dt, 1), objects=len(subjects))
        with open(out, "wb") as f:
            f.write(base64.b64decode(res["data"][0]["b64_json"]))
        print(f"{name}: {out} in {dt:.0f} s, ${cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
