"""Handwriting as real pen motion (docs/WHITEBOARD_WRITING.md). Any text: titles, sentences, lists, numbers, simple formulas; English and Spanish.

How: each letter of an open-licence handwriting font is reduced ONCE to its centre line (trace.py), the pieces are joined and ordered the way a hand writes
(top first, round letters anticlockwise, dots, accents and cross-bars last). Writing is then drawing those strokes with a round pen of the chosen width:
vector strokes, sharp at any size, and every letter instance can be bent a little (slant, size, baseline, a slow warp) so no two are identical.

  HANDS            "neat" (Patrick Hand) and "casual" (Caveat), both SIL OFL 1.1 (licence files in fonts/)
  TOOLS            "pen" (fine, quick), "marker" (thick, slower), "highlighter" (wide, translucent, goes UNDER the ink)
  layout(...)      text -> lines -> words -> strokes in block units, with line breaking and size fitting
  Markup           ^{2} superscript, _{2} subscript, \\frac{a}{b}, ->, <-, bullets "- " or "• " at a line start, "\\n" line break
"""
import math
import os
import pickle
import re
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import trace as tr
import vectorize as vz

HERE = os.path.dirname(os.path.abspath(__file__))
HANDS: Dict[str, Dict[str, Any]] = {
    # jitter values are fractions of the letter size (em) or degrees
    "neat": {"font": os.path.join(HERE, "fonts", "PatrickHand-Regular.ttf"), "slant": 0.0, "slant_j": 1.6, "size_j": 0.03, "warp": 0.011, "wander": 0.012, "space_j": 0.012, "track": 0.0, "line": 1.22, "speed": 1.0},
    "casual": {"font": os.path.join(HERE, "fonts", "Caveat-Variable.ttf"), "slant": 3.0, "slant_j": 3.0, "size_j": 0.06, "warp": 0.018, "wander": 0.028, "space_j": 0.03, "track": 0.01, "line": 1.02, "speed": 1.25, "scale": 1.22},
}
TOOLS: Dict[str, Dict[str, float]] = {
    # width in board units (capped at a fraction of the letter size so small text stays open), seconds per em of pen travel
    "pen": {"width": 9.0, "max_frac": 0.075, "s_per_em": 0.028, "pressure": 0.10},
    "marker": {"width": 20.0, "max_frac": 0.125, "s_per_em": 0.036, "pressure": 0.06},
    "highlighter": {"width": 78.0, "max_frac": 0.9, "s_per_em": 0.05, "pressure": 0.03},
}
EM = 360                    # pixels a glyph is rasterised at for tracing
_GLYPHS: Dict[Tuple[str, str], Dict[str, Any]] = {}
_FONTS: Dict[str, Any] = {}


def _font(path: str):
    from PIL import ImageFont

    if path not in _FONTS:
        _FONTS[path] = ImageFont.truetype(path, EM)
    return _FONTS[path]


def _orient(p: np.ndarray) -> np.ndarray:
    """Direction of one handwritten stroke: closed shapes from the top, ANTICLOCKWISE (o, 0, a, d); open strokes from their upper end, or from the left when flat."""
    if len(p) > 8 and float(np.hypot(*(p[0] - p[-1]))) < 4.0:
        q = p[:-1]
        q = np.roll(q, -int(np.argmin(q[:, 1] - 0.15 * q[:, 0])), axis=0)      # top, slightly to the right: where an "o" starts
        area = 0.5 * float(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]))
        if area > 0:          # clockwise on screen -> reverse
            q = np.concatenate([q[:1], q[1:][::-1]])
        return np.concatenate([q, q[:1]])
    dx, dy = p[-1] - p[0]
    if abs(dy) > 0.35 * abs(dx):
        return p if dy > 0 else p[::-1]
    return p if dx >= 0 else p[::-1]


def glyph(ch: str, hand: str) -> Dict[str, Any]:
    """-> {"strokes": [(n,2) arrays in em units, origin at the pen position on the line's top], "adv": advance in em}. Cached."""
    key = (ch, hand)
    if key in _GLYPHS:
        return _GLYPHS[key]
    from PIL import Image, ImageDraw

    f = _font(HANDS[hand]["font"])
    adv = f.getlength(ch) / EM
    pad = EM // 2
    im = Image.new("L", (int(f.getlength(ch)) + 2 * pad, int(EM * 1.8) + pad), 0)
    ImageDraw.Draw(im).text((pad, pad // 2), ch, font=f, fill=255)
    a = np.asarray(im, np.float32) / 255.0
    strokes: List[np.ndarray] = []
    if a.max() > 0.5:
        mask = a > 0.5
        sk = tr.skeleton(mask)
        w = tr.line_width(mask, sk)
        segs, _ = tr.segments(sk, w)
        raw = [vz.smooth_stroke(s, w, tol=0.05 * w) for s in tr.join_strokes(segs) if len(s) >= 2]
        raw = [_orient(np.asarray(s, np.float64)) for s in raw]
        big = max((tr.length_of(s) for s in raw), default=1.0)
        # main strokes left to right (then top to bottom); dots, accents and short bars last, as a hand does
        raw.sort(key=lambda s: (tr.length_of(s) < 0.28 * big, round(float(s[0][0]) / (0.22 * EM)), float(s[0][1])))
        strokes = [((s - np.array([pad, pad // 2])) / EM) for s in raw]
        # a filled dot (i, j, ., :, !, ?) thins to a single pixel and has no centre line: give every blob of ink without a stroke a tiny stroke at its middle
        from scipy import ndimage

        lab, nlab = ndimage.label(mask, structure=np.ones((3, 3)))
        hit = set()
        for s in raw:
            if tr.length_of(s) <= 0.02 * EM:
                continue
            q = np.clip(np.rint(s).astype(int), 0, [mask.shape[1] - 1, mask.shape[0] - 1])
            hit.update(np.unique(lab[q[:, 1], q[:, 0]]).tolist())
        dots = []
        for i in range(1, nlab + 1):
            if i not in hit and (lab == i).sum() > 12:
                cy, cx = ndimage.center_of_mass(lab == i)
                c = (np.array([cx, cy]) - np.array([pad, pad // 2])) / EM
                dots.append(np.stack([c + np.array([-0.012, -0.004]), c + np.array([0.012, 0.004])]))
        dots.sort(key=lambda d: (float(d[0][0]), float(d[0][1])))
        strokes = [s for s in strokes if tr.length_of(s) > 0.02] + dots
    g = {"strokes": strokes, "adv": adv}
    _GLYPHS[key] = g
    return g


def _rng(*parts) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(map(str, parts)).encode()))


def _instance(ch: str, hand_name: str, seed) -> Dict[str, Any]:
    """One written instance of a letter: its own size and slant (an affine change, so the font's outline and the pen path stay in step).
    Deterministic per seed; no two letters of a text share a seed, so the same letter never comes out twice the same."""
    hand = HANDS[hand_name]
    r = _rng(*seed)
    return {"ch": ch, "sc": 1.0 + r.uniform(-1, 1) * hand["size_j"], "slant": math.tan(math.radians(hand["slant"] + r.uniform(-1, 1) * hand["slant_j"])),
            "lift": r.uniform(-1, 1) * hand["size_j"] * 0.5}


def baseline(hand_name: str) -> float:
    return _font(HANDS[hand_name]["font"]).getmetrics()[0] / EM


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


def natural_width(hand: str) -> float:
    """The font's own stroke width, in em (measured once on a few letters)."""
    key = ("__width__", hand)
    if key not in _GLYPHS:
        from PIL import Image, ImageDraw

        f = _font(HANDS[hand]["font"])
        ws_ = []
        for ch in "nolhu":
            im = Image.new("L", (EM, int(EM * 1.6)), 0)
            ImageDraw.Draw(im).text((EM // 6, EM // 6), ch, font=f, fill=255)
            m = np.asarray(im) > 128
            ws_.append(tr.line_width(m, tr.skeleton(m)) / EM)
        _GLYPHS[key] = {"w": float(np.median(ws_))}
    return _GLYPHS[key]["w"]


def raster_word(word: Dict[str, Any], origin: Tuple[float, float], hand: str, tool: str, size: float, scale: float, seed: int = 0) -> Optional[Dict[str, Any]]:
    """A written word at `scale` raster pixels per board unit -> {"alpha", "T", "strokes", "times", "x", "y" (board units of the raster's corner)}.
    The letters are the FONT'S OWN OUTLINES (each with its own size and slant), grown or thinned to the tool's width; they are uncovered along the letters'
    centre lines in writing order, the pen slowing through bends. Arrows, bullets and fraction bars are drawn as strokes."""
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage

    if not word["strokes"]:
        return None
    ox, oy = origin
    S = 2                                               # supersampling for the width change and the shear
    k = scale * S
    allp = np.concatenate(word["strokes"])
    m = size * 0.5
    bx0, by0 = float(allp[:, 0].min() - m), float(allp[:, 1].min() - m)
    W, Hh = int((allp[:, 0].max() + m - bx0) * k) + 2, int((allp[:, 1].max() + m - by0) * k) + 2
    canvas = Image.new("L", (W, Hh), 0)
    font_path = HANDS[hand]["font"]
    base = baseline(hand)
    for g in word["glyphs"]:
        px_size = size * g["r"] * g["sc"] * k
        f = ImageFont.truetype(font_path, max(4.0, px_size))
        gw, gh = int(f.getlength(g["ch"]) + px_size * 1.2) + 4, int(px_size * 2.0) + 4
        pad = px_size * 0.6
        im = Image.new("L", (gw, gh), 0)
        ImageDraw.Draw(im).text((pad, pad * 0.5), g["ch"], font=f, fill=255)
        bpx = pad * 0.5 + base * px_size                # the baseline inside the glyph picture
        sl = g["slant"]
        im = im.transform((gw, gh), Image.AFFINE, (1, sl, -bpx * sl, 0, 1, 0), resample=Image.BICUBIC)
        # the letter's line-top sits at g["top"]; scaling about the baseline moved its own top down by base * (1 - sc)
        gx = (g["x"] - bx0) * k - pad
        gy = (g["top"] - by0 + (base * (1 - g["sc"]) + g["lift"]) * size * g["r"]) * k - pad * 0.5
        canvas.paste(Image.new("L", im.size, 255), (int(round(gx)), int(round(gy))), im)
    a = np.asarray(canvas, np.float32) / 255.0
    want = tool_width(tool, size)
    delta = (want - natural_width(hand) * size) * k / 2.0      # raster pixels to grow (+) or thin (-) each side
    if abs(delta) > 0.35 and a.max() > 0:
        inside = a > 0.5
        sd = ndimage.distance_transform_edt(~inside) - ndimage.distance_transform_edt(inside)      # < 0 inside the letter
        lim = -0.42 * natural_width(hand) * size * k                                               # never thin a stroke away
        a = np.clip(max(delta, lim) - sd + 0.5, 0.0, 1.0).astype(np.float32)
    if word["extra"]:
        import primitives as pr

        ex = [(word["strokes"][i] - np.array([bx0, by0])) for i in word["extra"]]
        frag = "".join(vz.stroke_polygon(s, want, seed + i, TOOLS[tool]["pressure"]) for i, s in enumerate(ex))
        ea = vz.svg_alpha(frag, W / k, Hh / k, k)
        a[:ea.shape[0], :ea.shape[1]] = np.maximum(a[:ea.shape[0], :ea.shape[1]], ea[:a.shape[0], :a.shape[1]])
        del pr
    small = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((max(1, W // S), max(1, Hh // S)), Image.LANCZOS), np.float32) / 255.0
    strokes = [(s - np.array([bx0, by0])) * scale for s in word["strokes"]]
    T, times, total = tr.time_map(small, strokes, max(want * scale * 0.6, 1.5), pace=1.3)
    return {"alpha": small, "T": T, "fills": [], "strokes": strokes, "times": times, "pen_len": total / scale, "x": bx0 + ox, "y": by0 + oy}


def tool_width(tool: str, size: float) -> float:
    t = TOOLS[tool]
    return min(t["width"], t["max_frac"] * size)


def write_time(strokes: Sequence[np.ndarray], tool: str, size: float, hand: str) -> float:
    """Natural seconds to write these strokes with this tool (pen travel in em, pen lifts included)."""
    L = sum(tr.length_of(np.asarray(s)) for s in strokes) / size
    return (L * TOOLS[tool]["s_per_em"] + 0.012 * len(strokes)) / HANDS[hand]["speed"]


# ----------------------------------------------------------------------------- emphasis marks, by hand, around a box (x0, y0, x1, y1) in board units
def mark(kind: str, box: Tuple[float, float, float, float], seed: int = 0, frm: Optional[Tuple[float, float]] = None) -> List[np.ndarray]:
    import primitives as pr

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
