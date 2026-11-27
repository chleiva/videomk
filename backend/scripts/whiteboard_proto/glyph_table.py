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

# Every letter a video language writes (docs/LANGUAGES.md: en, es, fr, de, it, pt, nl, pl, fi, and whatever Latin language comes next): printable ASCII, the whole of
# Latin-1 and Latin Extended-A (ą ć ę ł ń ś ź ż, š ž, ÿ Ÿ, ĳ, ...), and the punctuation and signs texts carry. A character the font has no glyph for is left out
# (the engine then falls back, engine/whiteboard/hand.py); tests/test_languages.py walks every language's letters against the tables.
CHARS = ("".join(chr(c) for c in range(33, 127)) + "".join(chr(c) for c in range(0xA1, 0x180) if c != 0xAD)
         + "•…–—‘’‚“”„«»‹›€™")


def _has(font, ch: str) -> bool:
    """Does the font draw this character itself (not its "missing glyph" box)?"""
    box = font.getmask("\U0010fffd")
    m = font.getmask(ch)
    return (bytes(m), m.size) != (bytes(box), box.size)


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for hand in ("neat", "casual"):
        table = {}
        font = wr._font(wr.HANDS[hand]["font"])
        for ch in CHARS:
            if not _has(font, ch):
                continue
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
