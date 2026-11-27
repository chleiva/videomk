"""Handwriting as pen motion, engine runtime (docs/WHITEBOARD.md). The letters are the font's own outlines, each with its own slight size and slant, uncovered
along the letter's centre line in writing order. The centre lines come from tables built offline (scripts/whiteboard_proto/glyph_table.py): no SciPy here.

  HANDS   "neat" (Patrick Hand) and "casual" (Caveat), both SIL OFL 1.1 (licence files in engine/assets/whiteboard)
  TOOLS   "pen" (fine, quick), "marker" (thick, slower), "highlighter" (wide, goes under the ink)
  Markup  ^{2} superscript, _{2} subscript, \\frac{a}{b}, ->, <-, bullets "- " at a line start, "\\n" line break
"""
import json
import math
import os
import re
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import core

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "whiteboard")
HANDS: Dict[str, Dict[str, Any]] = {
    "neat": {"font": os.path.join(ASSETS, "PatrickHand-Regular.ttf"), "table": "glyphs_neat.json", "slant": 0.0, "slant_j": 1.6, "size_j": 0.03, "wander": 0.012, "space_j": 0.012, "track": 0.0, "line": 1.22, "speed": 1.0},
    "casual": {"font": os.path.join(ASSETS, "Caveat-Variable.ttf"), "table": "glyphs_casual.json", "slant": 3.0, "slant_j": 3.0, "size_j": 0.06, "wander": 0.028, "space_j": 0.03, "track": 0.01, "line": 1.02, "speed": 1.25,
               "scale": 1.22},
}
TOOLS: Dict[str, Dict[str, float]] = {
    "pen": {"width": 9.0, "max_frac": 0.075, "s_per_em": 0.028, "pressure": 0.10},
    "marker": {"width": 20.0, "max_frac": 0.125, "s_per_em": 0.036, "pressure": 0.06},
    "highlighter": {"width": 78.0, "max_frac": 0.9, "s_per_em": 0.05, "pressure": 0.03},
}
_TABLES: Dict[str, Dict[str, Any]] = {}


def _table(hand: str) -> Dict[str, Any]:
    if hand not in _TABLES:
        with open(os.path.join(ASSETS, HANDS[hand]["table"]), encoding="utf-8") as f:
            _TABLES[hand] = json.load(f)
    return _TABLES[hand]


_FALLBACK: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _fallback(ch: str, hand: str) -> Dict[str, Any]:
    """A letter the stroke table does not have (the tables hold all of Latin-1 and Latin Extended-A, so this is a rare sign or another script): never a gap.
    Its advance is the FONT's own, and its pen path is a hatch over the letter as the font draws it, left to right, so the pen passes over all of its ink and
    the word is drawn even when every letter of it is unknown. No SciPy: the centre line cannot be traced here, the ink can be read."""
    key = (ch, hand)
    if key in _FALLBACK:
        return _FALLBACK[key]
    from PIL import Image, ImageDraw, ImageFont

    em = 96
    f = ImageFont.truetype(HANDS[hand]["font"], em)
    adv = float(f.getlength(ch)) / em
    if adv <= 0.0:                                         # a combining or zero-width character: nothing to write, no room taken
        g = {"strokes": [], "adv": 0.0, "missing": True}
        _FALLBACK[key] = g
        return g
    pad = em // 2
    im = Image.new("L", (int(adv * em) + 2 * pad, int(em * 1.8) + pad), 0)
    ImageDraw.Draw(im).text((pad, pad // 2), ch, font=f, fill=255)           # same origin as the table's letters: the pen position on the line's top
    ink = np.asarray(im) > 127
    cols = np.flatnonzero(ink.any(axis=0))
    strokes: List[np.ndarray] = []
    if len(cols):
        step = max(2, int(round(0.07 * em)))
        pts, down = [], True
        for x in list(range(int(cols[0]), int(cols[-1]) + 1, step)) + [int(cols[-1])]:
            ys = np.flatnonzero(ink[:, max(0, x - step // 2):x + step // 2 + 1].any(axis=1))
            if not len(ys):
                continue
            y0, y1 = float(ys[0]), float(ys[-1])
            pts += [(x, y0), (x, y1)] if down else [(x, y1), (x, y0)]
            down = not down
        if len(pts) >= 2:
            strokes = [(np.asarray(pts, np.float64) - np.array([pad, pad // 2])) / em]
    g = {"strokes": strokes, "adv": adv, "missing": True}
    _FALLBACK[key] = g
    return g


def glyph(ch: str, hand: str) -> Dict[str, Any]:
    """-> {"strokes": [(n,2) arrays in em from the pen position on the line's top], "adv": advance in em}. A letter the table lacks comes from the font
    itself (`_fallback`: its real advance and a pen path over its ink), marked "missing"."""
    t = _table(hand)["glyphs"]
    g = t.get(ch)
    if g is None:
        return _fallback(ch, hand)
    if "np" not in g:
        g["np"] = [np.asarray(s, np.float64) for s in g["strokes"]]
    return {"strokes": g["np"], "adv": g["adv"]}


def baseline(hand: str) -> float:
    return float(_table(hand)["baseline"])


def natural_width(hand: str) -> float:
    return float(_table(hand)["width"])


def _rng(*parts) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(map(str, parts)).encode()))


def _instance(ch: str, hand_name: str, seed) -> Dict[str, Any]:
    """One written instance of a letter: its own size and slant (an affine change, so the font's outline and the pen path stay in step).
    Deterministic per seed; no two letters of a text share a seed, so the same letter never comes out twice the same."""
    hand = HANDS[hand_name]
    r = _rng(*seed)
    return {"ch": ch, "sc": 1.0 + r.uniform(-1, 1) * hand["size_j"], "slant": math.tan(math.radians(hand["slant"] + r.uniform(-1, 1) * hand["slant_j"])),
            "lift": r.uniform(-1, 1) * hand["size_j"] * 0.5}


def _apply(strokes: List[np.ndarray], inst: Dict[str, Any], base: float) -> List[np.ndarray]:
    out = []
    for s in strokes:
        yb = (s[:, 1] - base) * inst["sc"]
        out.append(np.stack([s[:, 0] * inst["sc"] - yb * inst["slant"], yb + base + inst["lift"]], 1))
    return out


# ----------------------------------------------------------------------------- markup -> runs
def _arrow_glyph(direction: int) -> Dict[str, Any]:
    y = 0.62
    shaft = np.array([[0.08, y], [0.78, y]]) if direction > 0 else np.array([[0.78, y], [0.08, y]])
    tip = shaft[-1]
    hd = np.array([[tip[0] - direction * 0.17, y - 0.11], tip, [tip[0] - direction * 0.17, y + 0.11]])
    return {"strokes": [np.linspace(shaft[0], shaft[1], 12), hd], "adv": 0.9}


def _special(tok: str) -> Optional[Dict[str, Any]]:
    if tok == "->":
        return _arrow_glyph(1)
    if tok == "<-":
        return _arrow_glyph(-1)
    if tok == "•":
        t = np.linspace(0, 2 * math.pi, 14)
        return {"strokes": [np.stack([0.2 + 0.035 * np.cos(t), 0.6 + 0.035 * np.sin(t)], 1)], "adv": 0.5}
    return None


def _tokens(word: str) -> List[Tuple[str, Any]]:
    """A word -> [("ch", c) | ("sup", str) | ("sub", str) | ("frac", (a, b)) | ("special", tok)]."""
    out, i = [], 0
    while i < len(word):
        m = re.match(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", word[i:])
        if m:
            out.append(("frac", (m.group(1), m.group(2))))
            i += m.end()
            continue
        m = re.match(r"([\^_])\{([^{}]*)\}", word[i:])
        if m:
            out.append(("sup" if m.group(1) == "^" else "sub", m.group(2)))
            i += m.end()
            continue
        if word[i:i + 2] in ("->", "<-"):
            out.append(("special", word[i:i + 2]))
            i += 2
            continue
        out.append(("special", word[i]) if word[i] == "•" else ("ch", word[i]))
        i += 1
    return out


def _run(text: str, hand_name: str, seed, r: float, x0: float, dy: float, out: Dict[str, list]) -> float:
    """Plain characters in a row at run scale `r`, starting at x0 (em), shifted down by dy (em). Appends to out["strokes"], out["glyphs"]. -> advance."""
    hand, base = HANDS[hand_name], baseline(hand_name)
    x = x0
    for i, ch in enumerate(text):
        if ch == " ":
            x += 0.3 * r
            continue
        g = glyph(ch, hand_name)
        inst = _instance(ch, hand_name, (*seed, i, ch))
        top = base * (1 - r) + dy                       # where the top of this (smaller) letter's line sits
        for s in _apply(g["strokes"], inst, base):
            out["strokes"].append(s * r + np.array([x, top]))
        out["glyphs"].append({"ch": ch, "x": x, "top": top, "r": r, "sc": inst["sc"], "slant": inst["slant"], "lift": inst["lift"]})
        sp = _rng(*seed, i, ch, "sp").uniform(-1, 1) * hand["space_j"]
        x += (g["adv"] * inst["sc"] + hand["track"] + sp) * r
    return x - x0


def word_strokes(word: str, hand_name: str, seed) -> Tuple[Dict[str, list], float]:
    """One word (with markup) -> ({"strokes": pen path in em from the word's left end on the line's top, "glyphs": letters to render from the font,
    "extra": strokes that ARE the art (arrows, fraction bars, bullets)}, advance in em)."""
    out: Dict[str, list] = {"strokes": [], "glyphs": [], "extra": []}
    x = 0.0
    buf = ""
    k0 = 0
    toks = _tokens(word)
    for k, (kind, val) in enumerate(toks + [("end", None)]):
        if kind == "ch":
            if not buf:
                k0 = k
            buf += val
            continue
        if buf:
            x += _run(buf, hand_name, (*seed, k0), 1.0, x, 0.0, out)
            buf = ""
        if kind == "special":
            g = _special(val)
            for s in g["strokes"]:
                out["strokes"].append(s + np.array([x, 0.0]))
                out["extra"].append(len(out["strokes"]) - 1)
            x += g["adv"]
        elif kind in ("sup", "sub"):
            x += _run(val, hand_name, (*seed, k, kind), 0.62, x + 0.02, -0.30 if kind == "sup" else 0.20, out) + 0.05
        elif kind == "frac":
            probe: Dict[str, list] = {"strokes": [], "glyphs": [], "extra": []}
            aa = _run(val[0], hand_name, (*seed, k, "n"), 0.66, 0.0, 0.0, probe)
            ab = _run(val[1], hand_name, (*seed, k, "d"), 0.66, 0.0, 0.0, probe)
            wd = max(aa, ab) + 0.12
            _run(val[0], hand_name, (*seed, k, "n"), 0.66, x + (wd - aa) / 2, -0.36, out)
            out["strokes"].append(np.linspace([x + 0.02, 0.60], [x + wd - 0.02, 0.585], 10))
            out["extra"].append(len(out["strokes"]) - 1)
            _run(val[1], hand_name, (*seed, k, "d"), 0.66, x + (wd - ab) / 2, 0.24, out)
            x += wd + 0.06
    return out, x


# ----------------------------------------------------------------------------- lines, wrapping, fitting
def layout(text: str, hand: str = "neat", size: float = 130.0, max_width: Optional[float] = None, max_height: Optional[float] = None, align: str = "left",
           seed: int = 0, min_size: float = 54.0) -> Dict[str, Any]:
    """Text -> a block of written words. Lines break at spaces to fit `max_width`; the size shrinks (down to min_size) until the block fits `max_height`.
    -> {"w", "h", "size", "lines": n, "words": [{"text", "line", "strokes": [arrays in block units], "glyphs": [...], "extra": [...], "box": (x0, y0, x1, y1)}]}"""
    H = HANDS[hand]
    size *= H.get("scale", 1.0)
    min_size *= H.get("scale", 1.0)
    space = 0.30
    paras = [re.sub(r"^\s*[-•]\s+", "• ", p) for p in text.split("\n")]
    cache: Dict[Tuple[int, int], Tuple[Dict[str, list], float]] = {}

    def ws(pi: int, wi: int, word: str):
        if (pi, wi) not in cache:
            cache[(pi, wi)] = word_strokes(word, hand, (seed, pi, wi))
        return cache[(pi, wi)]

    while True:
        lines: List[List[Tuple[int, int, str, float]]] = []
        for pi, para in enumerate(paras):
            cur, x = [], 0.0
            indent = 0.62 if para.startswith("• ") or re.match(r"^\d+[.)] ", para) else 0.0
            for wi, word in enumerate(para.split()):
                _, adv = ws(pi, wi, word)
                if cur and max_width and (x + adv) * size > max_width:
                    lines.append(cur)
                    cur, x = [], indent
                cur.append((pi, wi, word, x))
                x += adv + space
            lines.append(cur)
        lh = H["line"] * size
        h = lh * len(lines) + 0.25 * size
        w = max(((wd[3] + ws(wd[0], wd[1], wd[2])[1]) * size for ln in lines for wd in ln), default=0.0)
        if (not max_height or h <= max_height) and (not max_width or w <= max_width * 1.02) or size <= min_size:
            break
        size *= 0.93
    words = []
    for li, ln in enumerate(lines):
        if not ln:
            continue
        lw = (ln[-1][3] + ws(ln[-1][0], ln[-1][1], ln[-1][2])[1]) * size
        off = 0.0 if align == "left" else (w - lw) / (2.0 if align == "center" else 1.0)
        r = _rng(seed, li, "wander")
        ph, per, tilt = r.uniform(0, 6.28), r.uniform(5.0, 9.0), r.uniform(-0.006, 0.006)
        for pi, wi, word, x in ln:
            ws_, adv = ws(pi, wi, word)
            # the line's slow wander is taken once per WORD (a word is written in one go), so the letters' outlines and their pen paths stay together
            wy = (H["wander"] * math.sin((x + adv / 2) / per * 6.28 + ph) + tilt * x) * size + li * lh
            wx = x * size + off
            strokes = [np.stack([s[:, 0] * size + wx, s[:, 1] * size + wy], 1) for s in ws_["strokes"]]
            glyphs = [dict(g, x=g["x"] * size + wx, top=g["top"] * size + wy) for g in ws_["glyphs"]]
            words.append({"text": word, "line": li, "para": pi, "strokes": strokes, "glyphs": glyphs, "extra": list(ws_["extra"]),
                          "box": (wx, li * lh + 0.12 * size, wx + adv * size, li * lh + 1.02 * size)})
    return {"w": w, "h": h, "size": size, "lines": len(lines), "words": words, "hand": hand}


def raster_word(word: Dict[str, Any], origin: Tuple[float, float], hand: str, tool: str, size: float, scale: float, seed: int = 0) -> Optional[Dict[str, Any]]:
    """A written word at `scale` raster pixels per board unit -> {"alpha", "T", "strokes", "times", "x", "y" (board units of the raster's corner)}.
    The letters are drawn from the font (each with its own size and slant), grown or thinned to the tool's width, and uncovered along their centre lines."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    if not word["strokes"]:
        return None
    ox, oy = origin
    S = 2
    k = scale * S
    allp = np.concatenate(word["strokes"])
    m = size * 0.5
    bx0, by0 = float(allp[:, 0].min() - m), float(allp[:, 1].min() - m)
    W, Hh = int((allp[:, 0].max() + m - bx0) * k) + 2, int((allp[:, 1].max() + m - by0) * k) + 2
    canvas = Image.new("L", (W, Hh), 0)
    font_path = HANDS[hand]["font"]
    base = baseline(hand)
    want = tool_width(tool, size)
    delta = (want - natural_width(hand) * size) * k / 2.0       # raster pixels to grow (+) or thin (-) each side
    grow = int(round(delta)) if delta > 0.35 else 0
    for g in word["glyphs"]:
        px_size = size * g["r"] * g["sc"] * k
        f = ImageFont.truetype(font_path, max(4.0, px_size))
        gw, gh = int(f.getlength(g["ch"]) + px_size * 1.2) + 4 + 2 * grow, int(px_size * 2.0) + 4 + 2 * grow
        pad = px_size * 0.6
        im = Image.new("L", (gw, gh), 0)
        ImageDraw.Draw(im).text((pad - grow, pad * 0.5 - grow), g["ch"], font=f, fill=255, stroke_width=grow, stroke_fill=255)
        bpx = pad * 0.5 + base * px_size
        sl = g["slant"]
        im = im.transform((gw, gh), Image.AFFINE, (1, sl, -bpx * sl, 0, 1, 0), resample=Image.BICUBIC)
        gx = (g["x"] - bx0) * k - pad
        gy = (g["top"] - by0 + (base * (1 - g["sc"]) + g["lift"]) * size * g["r"]) * k - pad * 0.5
        canvas.paste(Image.new("L", im.size, 255), (int(round(gx)), int(round(gy))), im)
    if delta < -0.5:
        thin = min(int(round(-delta)), int(0.42 * natural_width(hand) * size * k))
        if thin >= 1:
            canvas = canvas.filter(ImageFilter.MinFilter(2 * thin + 1))
    a = np.asarray(canvas, np.float32) / 255.0
    if word["extra"]:
        ex = [(word["strokes"][i] - np.array([bx0, by0])) for i in word["extra"]]
        frag = "".join(core.stroke_svg(s, want, seed + i, TOOLS[tool]["pressure"]) for i, s in enumerate(ex))
        ea = core.svg_alpha(frag, W / k, Hh / k, k)
        hh, ww = min(a.shape[0], ea.shape[0]), min(a.shape[1], ea.shape[1])
        a = a.copy()
        a[:hh, :ww] = np.maximum(a[:hh, :ww], ea[:hh, :ww])
    small = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((max(1, W // S), max(1, Hh // S)), Image.LANCZOS), np.float32) / 255.0
    strokes = [(s - np.array([bx0, by0])) * scale for s in word["strokes"]]
    T, times, total = core.reveal_map(small, strokes, max(want, natural_width(hand) * size) * scale * 1.9, pace=1.3)
    return {"alpha": small, "T": T, "fills": [], "strokes": strokes, "times": times, "pen_len": total / scale, "x": bx0 + ox, "y": by0 + oy}


def tool_width(tool: str, size: float) -> float:
    t = TOOLS[tool]
    return min(t["width"], t["max_frac"] * size)


def write_time(strokes: Sequence[np.ndarray], tool: str, size: float, hand: str) -> float:
    """Natural seconds to write these strokes with this tool (pen travel in em, pen lifts included)."""
    L = sum(core.length_of(np.asarray(s)) for s in strokes) / size
    return (L * TOOLS[tool]["s_per_em"] + 0.012 * len(strokes)) / HANDS[hand]["speed"]


# ----------------------------------------------------------------------------- emphasis marks, by hand, around a box (x0, y0, x1, y1) in board units
def mark(kind: str, box: Tuple[float, float, float, float], seed: int = 0, frm: Optional[Tuple[float, float]] = None) -> List[np.ndarray]:
    from . import primitives as pr

    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    r = np.random.default_rng(seed)
    if kind == "underline":
        return pr.underline(x0, y1 + 0.10 * h, w, seed)
    if kind == "double_underline":
        return pr.underline(x0, y1 + 0.08 * h, w, seed) + pr.underline(x0 + 0.03 * w, y1 + 0.24 * h, w * 0.95, seed + 1)
    if kind == "cross_out":
        return [pr.path([(x0 - 0.03 * w, y0 + 0.62 * h + r.uniform(-4, 4)), (x0 + w / 2, y0 + 0.55 * h), (x1 + 0.03 * w, y0 + 0.50 * h + r.uniform(-4, 4))], seed, 2.5)]
    if kind == "circle":       # one loop, started top-left, a little open and overshooting like a real circled word
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2 + 0.04 * h, w / 2 * 1.12 + 12, h / 2 * 1.02 + 8
        a = np.radians(np.linspace(215, 215 + 395, 90))
        grow = np.linspace(1.0, 1.07, len(a))
        return [pr.wobble(np.stack([cx + rx * grow * np.cos(a), cy + ry * grow * np.sin(a)], 1), seed, 4.0)]
    if kind == "box":
        m = 0.12 * h + 8
        c = [(x0 - m, y0 - m), (x1 + m, y0 - m + r.uniform(-3, 3)), (x1 + m + r.uniform(-3, 3), y1 + m), (x0 - m + r.uniform(-3, 3), y1 + m + r.uniform(-3, 3)), (x0 - m + 2, y0 - m - 6)]
        return [pr.line(c[i], c[i + 1], seed + i, 2.5) for i in range(4)]
    if kind == "tick":
        s = h * 0.9
        return [np.array([(x0, y0 + 0.55 * s), (x0 + 0.3 * s, y0 + 0.95 * s), (x0 + 0.95 * s, y0 - 0.05 * s)], np.float64)]
    if kind == "cross":
        s = h * 0.8
        return [pr.line((x0, y0), (x0 + s, y0 + s), seed, 1.5), pr.line((x0 + s, y0), (x0, y0 + s), seed + 1, 1.5)]
    if kind == "arrow":        # from a point (default: lower left of the box) to the box's edge
        fx, fy = frm if frm else (x0 - 1.6 * h, y1 + 1.3 * h)
        tx, ty = (x0 - 0.15 * h, (y0 + y1) / 2 + 0.25 * h) if fx < x0 else (x1 + 0.15 * h, (y0 + y1) / 2)
        return pr.arrow([(fx, fy), ((fx + tx) / 2 + 0.15 * (ty - fy), (fy + ty) / 2 - 0.15 * (tx - fx)), (tx, ty)], seed, size=max(26.0, 0.42 * h))
    if kind == "highlight":
        return [pr.line((x0 - 6, (y0 + y1) / 2 + 0.06 * h + r.uniform(-3, 3)), (x1 + 8, (y0 + y1) / 2 + 0.02 * h + r.uniform(-3, 3)), seed, 2.0)]
    raise ValueError(kind)
