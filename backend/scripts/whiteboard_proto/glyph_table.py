#!/usr/bin/env python3
"""Offline: the centre-line pen paths of every letter of the two handwriting fonts, for the engine (which has no SciPy).

  glyph_table.py OUT_DIR   -> glyphs_neat.json, glyphs_casual.json: {"font", "baseline", "width", "glyphs": {char: {"adv", "strokes": [[[x, y], ...], ...]}}}

Units are em (the letter size), origin at the pen position on the top of the line. The fonts (SIL OFL 1.1) are copied next to the tables by the caller.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vectorize as vz  # noqa: E402
import writing as wr  # noqa: E402

CHARS = ("".join(chr(c) for c in range(33, 127)) + "áéíóúüñÁÉÍÓÚÜÑ¿¡àèìòùÀÈÌÒÙâêîôûÂÊÎÔÛäëïöÄËÏÖçÇãõÃÕåÅøØæÆœŒß°€£¥¢±×÷·•…–—‘’“”«»§©®™µ¼½¾²³¹ªº")


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for hand in ("neat", "casual"):
        table = {}
        for ch in CHARS:
            g = wr.glyph(ch, hand)
            if not g["strokes"] and ch.strip():
                continue
            table[ch] = {"adv": round(g["adv"], 4), "strokes": [[[round(float(x), 4), round(float(y), 4)] for x, y in vz._resample(s, 0.02)] for s in g["strokes"]]}
        path = os.path.join(out, f"glyphs_{hand}.json")
        json.dump({"font": os.path.basename(wr.HANDS[hand]["font"]), "baseline": round(wr.baseline(hand), 4), "width": round(wr.natural_width(hand), 4), "glyphs": table},
                  open(path, "w"), separators=(",", ":"), ensure_ascii=False)
        print(hand, len(table), "glyphs", os.path.getsize(path) // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
