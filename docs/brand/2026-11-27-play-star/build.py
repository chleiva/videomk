#!/usr/bin/env python3
"""VideoMK play + star logo options (27 Nov 2026): builds the SVG sources and the comparison / detail sheets.

  .venv/bin/python docs/brand/2026-11-27-play-star/build.py [svg_out_dir] [sheet_out_dir]

Needs resvg_py + Pillow (the repo's .venv), wordmarks.json next to this file (outlines of the wordmark, made by wordmarks.py
from Inter, OFL) and the engine's Inter files for the sheet labels. Proposal only: nothing here is used by the apps.
"""
import io, json, math, os, sys

import resvg_py
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("VIDEOMK_REPO", "/Users/chleiva/code/videomk")
SVG_OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "svg")
SHEETS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "sheets")
FONTS = os.path.join(REPO, "backend", "lambdas", "engine", "assets", "fonts")
WM = json.load(open(os.path.join(HERE, "wordmarks.json")))
os.makedirs(SVG_OUT, exist_ok=True)
os.makedirs(SHEETS, exist_ok=True)


# ---------- geometry (1024 grid) ----------
def n(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


def spark(cx, cy, R, a=0.08, b=0.34):
    p = [(0, -R), (a * R, -b * R), (b * R, -a * R), (R, 0), (b * R, a * R), (a * R, b * R), (0, R), (-a * R, b * R), (-b * R, a * R), (-R, 0), (-b * R, -a * R), (-a * R, -b * R), (0, -R)]
    q = [(cx + x, cy + y) for x, y in p]
    d = f"M{n(q[0][0])},{n(q[0][1])}"
    for i in range(1, 13, 3):
        d += "C" + " ".join(f"{n(x)},{n(y)}" for x, y in q[i:i + 3])
    return d + "Z"


def rpoly(pts, r):
    d = ""
    m = len(pts)
    for i in range(m):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % m]
        rr = r[i] if isinstance(r, (list, tuple)) else r

        def unit(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            return dx / L, dy / L
        u1, u2 = unit(p1, p0), unit(p1, p2)
        ang = math.acos(max(-1, min(1, u1[0] * u2[0] + u1[1] * u2[1])))
        t = rr / math.tan(ang / 2)
        s = (p1[0] + u1[0] * t, p1[1] + u1[1] * t)
        e = (p1[0] + u2[0] * t, p1[1] + u2[1] * t)
        d += ("M" if i == 0 else "L") + f"{n(s[0])},{n(s[1])}Q{n(p1[0])},{n(p1[1])} {n(e[0])},{n(e[1])}"
    return d + "Z"


def tri(L, T, h, w, r):
    """Play triangle pointing right. r is the rounding (distance kept on the short side); the tip gets a little more so the three corners look equally soft."""
    return rpoly([(L, T), (L + w, T + h / 2), (L, T + h)], [r, r * 1.12, r])


def rrect(x, y, w, h, r):
    return rpoly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], r)


def squircle(c, R, e=5.0, steps=180):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        pts.append((c + R * math.copysign(abs(ct) ** (2 / e), ct), c + R * math.copysign(abs(st) ** (2 / e), st)))
    return "M" + "L".join(f"{n(x)},{n(y)}" for x, y in pts) + "Z"


def geometry(k):
    """-> list of (role, d, cut_d or None, fill_rule)"""
    if k == "A":   # the Create button: one play, one star
        return [("play", tri(280, 318, 476, 428, 54), None, None), ("spark", spark(696, 340, 112), None, None)]
    if k == "B":   # one play, two stars (big + small, wrapping the tip)
        return [("play", tri(262, 326, 468, 420, 54), None, None), ("spark", spark(666, 336, 104), None, None), ("spark2", spark(792, 466, 52), None, None)]
    if k == "C":   # star cut out of the play
        L, T, h, w = 362, 262, 500, 450
        return [("play", tri(L, T, h, w, 58) + spark(L + 166, T + h / 2, 102, 0.1, 0.36), None, "evenodd")]
    if k == "D":   # play as negative space in a rounded tile, star on the corner
        b = rrect(236, 262, 540, 540, 132)
        p = tri(410, 378, 308, 276, 36)
        return [("badge", b + p, spark(760, 278, 168, 0.1, 0.36), "evenodd"), ("spark", spark(760, 278, 124), None, None)]
    if k == "E":   # star set into the play's upper edge (halo bite), tip left whole
        return [("play", tri(300, 288, 470, 422, 54), spark(546, 393, 166, 0.1, 0.36), None), ("spark", spark(546, 393, 126), None, None)]
    if k == "F":   # one play, two stars rising (small above-left of the big one)
        return [("play", tri(276, 344, 460, 414, 54), None, None), ("spark", spark(696, 344, 108), None, None), ("spark2", spark(576, 232, 48), None, None)]
    raise KeyError(k)


# ---------- colour ----------
def lin(*stops, v=(0, 0, 1024, 1024)):
    return ("lin", v, stops)


INK = "#0B0C14"
ACTION = lin("#3B36C8", "#7A4BE6")
BRAND = lin("#2B2F9A", "#6A3FC4")
INK_TILE = lin("#151828", "#06070D")
MARKBOX = (300, 170, 860, 790)
ACTION_M = lin("#3B36C8", "#7A4BE6", v=MARKBOX)
GLOW_M = lin("#7672FF", "#B78CFF", v=MARKBOX)
AMBER = lin("#FFD35C", "#FF9A1F", v=(420, 267, 672, 519))
AMBER_L = lin("#FFAE1F", "#F9731A", v=(420, 267, 672, 519))
AURORA = lin("#3B36C8", "#7A4BE6", "#EC4F9E", v=MARKBOX)
AURORA_D = lin("#6F6BFF", "#A87BFF", "#FF6FB2", v=MARKBOX)
CORAL = lin("#F2509B", "#FF8A5B", v=(588, 236, 804, 452))

OPTS = {
    "A": dict(name="Create", idea="One play, one star: the Create button as it is",
              palette="Action gradient tile #3B36C8 to #7A4BE6, white mark (the product's own tokens)",
              icon=dict(tile=ACTION, play="#FFFFFF", spark="#FFFFFF"),
              icon_dark=dict(tile=INK_TILE, play=GLOW_M, spark=GLOW_M),
              light=dict(play=ACTION_M, spark=ACTION_M), dark=dict(play="#FFFFFF", spark="#FFFFFF"),
              near="Generic 'AI video' glyphs (CapCut AI, Canva Magic Media): ours is a single fuller star in a fixed place above the tip, on our own indigo-violet; not YouTube (no red, no rectangle)"),
    "B": dict(name="Midnight", idea="One play, two stars, lit on a deep ink tile",
              palette="Ink tile #151828 to #06070D, play #6360FF to #B56CFF, big star cyan #22D3EE, small star #E9E8FF",
              icon=dict(tile=INK_TILE, play=lin("#6360FF", "#B56CFF", v=MARKBOX), spark=lin("#7CEBFA", "#22D3EE", v=(562, 232, 770, 440)), spark2="#E9E8FF"),
              icon_dark=dict(tile=INK_TILE, play=lin("#6360FF", "#B56CFF", v=MARKBOX), spark=lin("#7CEBFA", "#22D3EE", v=(562, 232, 770, 440)), spark2="#E9E8FF"),
              light=dict(play=ACTION_M, spark="#4B45E0", spark2="#7A4BE6"),
              dark=dict(play=lin("#6360FF", "#B56CFF", v=MARKBOX), spark=lin("#7CEBFA", "#22D3EE", v=(562, 232, 770, 440)), spark2="#E9E8FF"),
              near="The sparkles emoji / Gemini star cluster beside a play: ours keeps the play dominant (about 80% of the ink) and the stars in two colours; not Google Play (one hue family, rounded, no four colour facets)"),
    "C": dict(name="Flat", idea="A star cut out of the play: one shape, one flat colour",
              palette="One flat indigo #4B45E0 (the primary token) and white",
              icon=dict(tile="#4B45E0", play="#FFFFFF"), icon_dark=dict(tile=INK_TILE, play="#8F8BFF"),
              light=dict(play="#4B45E0"), dark=dict(play="#FFFFFF"),
              near="YouTube's white play on a colour tile, and Pictory's rounded play: ours is indigo, a full square tile, and carries the star inside the triangle"),
    "D": dict(name="Paper", idea="Play as negative space in a rounded tile, star on its corner; light icon",
              palette="Light tile #FFFFFF to #ECEDF5, badge in the action gradient, star #7A4BE6 (cyan on dark)",
              icon=dict(tile=lin("#FFFFFF", "#ECEDF5"), badge=lin("#3B36C8", "#7A4BE6", v=(236, 262, 776, 802)), spark="#7A4BE6"),
              icon_dark=dict(tile=INK_TILE, badge=lin("#5B57F0", "#9C6DF5", v=(236, 262, 776, 802)), spark="#22D3EE"),
              light=dict(badge=lin("#3B36C8", "#7A4BE6", v=(236, 262, 776, 802)), spark="#7A4BE6"),
              dark=dict(badge="#FFFFFF", spark="#FFFFFF"),
              near="YouTube / Google TV style 'play in a rounded rectangle', and notification-badge icons: ours is a square badge in indigo-violet with a star, never red"),
    "E": dict(name="Sunspark", idea="A warm star biting into a cool play",
              palette="Brand gradient tile #2B2F9A to #6A3FC4, white play, amber star #FFD35C to #FF9A1F",
              icon=dict(tile=BRAND, play="#FFFFFF", spark=AMBER), icon_dark=dict(tile=INK_TILE, play=lin("#A8A6FF", "#C9B4FF", v=MARKBOX), spark=AMBER),
              light=dict(play=ACTION_M, spark=AMBER_L), dark=dict(play="#FFFFFF", spark=AMBER),
              near="Plex (amber chevron on black) and 'favourite / premium' star badges: ours is a white play first, on indigo, the star is four-pointed and interlocked with the triangle"),
    "F": dict(name="Aurora", idea="One play, two rising stars in an indigo to pink gradient on white",
              palette="White tile, mark #3B36C8 to #7A4BE6 to #EC4F9E, stars coral #F2509B to #FF8A5B and violet",
              icon=dict(tile=lin("#FFFFFF", "#F1F1F8"), play=AURORA, spark=CORAL, spark2="#7A4BE6"),
              icon_dark=dict(tile=INK_TILE, play=AURORA_D, spark=CORAL, spark2="#B9A2FF"),
              light=dict(play=AURORA, spark=CORAL, spark2="#7A4BE6"), dark=dict(play=AURORA_D, spark=CORAL, spark2="#B9A2FF"),
              near="Google Play (multi-colour triangle on white) and Instagram's gradient: ours is one continuous gradient, rounded, with stars, no colour facets; still the closest of the six to Google Play at a glance"),
}
KEYS = list(OPTS)
ICON_SCALE = {"D": 1.0, "B": 1.06}   # how much larger the mark sits in the icon than on the 1024 drawing grid (default 1.1)
_uid = [0]


def paint(p):
    """-> (fill attribute value, defs string)"""
    if isinstance(p, str):
        return p, ""
    _uid[0] += 1
    gid = f"g{_uid[0]}"
    _, v, stops = p
    st = "".join(f'<stop offset="{n(i / (len(stops) - 1))}" stop-color="{c}"/>' for i, c in enumerate(stops))
    return f"url(#{gid})", f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{v[0]}" y1="{v[1]}" x2="{v[2]}" y2="{v[3]}">{st}</linearGradient>'


def mark(k, style):
    """Inner SVG (1024 grid). style: dict role->paint, or a single colour string (monochrome)."""
    defs, body = "", ""
    for role, d, cut, rule in geometry(k):
        fill, df = paint(style if isinstance(style, str) else style.get(role, style.get("play", "#fff")))
        defs += df
        attr = f' fill-rule="{rule}"' if rule else ""
        if cut:
            _uid[0] += 1
            mid = f"m{_uid[0]}"
            defs += f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024"><rect width="1024" height="1024" fill="#fff"/><path d="{cut}" fill="#000"/></mask>'
            attr += f' mask="url(#{mid})"'
        body += f'<path d="{d}" fill="{fill}"{attr}/>'
    return (f"<defs>{defs}</defs>" if defs else "") + body


def svg(inner, vb=(0, 0, 1024, 1024), w=None, h=None):
    size = f' width="{w}" height="{h}"' if w else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{n(vb[0])} {n(vb[1])} {n(vb[2])} {n(vb[3])}"{size}>{inner}</svg>'


def icon_inner(k, mode="icon", scale=1.0):
    scale *= ICON_SCALE.get(k, 1.1)
    st = OPTS[k][mode]
    fill, df = paint(st["tile"])
    g = mark(k, st)
    if scale != 1.0:
        g = f'<g transform="translate(512 512) scale({scale}) translate(-512 -512)">{g}</g>'
    return f'<defs>{df}</defs><rect width="1024" height="1024" fill="{fill}"/>{g}'


def render(svg_str, w, h):
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg_str, width=int(w), height=int(h))))).convert("RGBA")


_bbox = {}


def bbox(k):
    if k not in _bbox:
        b = render(svg(mark(k, "#000")), 2048, 2048).getchannel("A").getbbox()
        _bbox[k] = tuple(v / 2 for v in b)
    return _bbox[k]


def wordmark(key, fill, x, base, capsize, fill2=None):
    """Wordmark outlines scaled so the cap height is `capsize`; returns (svg, width)."""
    w = WM[key]
    s = capsize / w["cap"]
    out = ""
    for i, seg in enumerate(w["segs"]):
        out += f'<path d="{seg["d"]}" fill="{fill2 if (fill2 and i == len(w["segs"]) - 1) else fill}"/>'
    return f'<g transform="translate({n(x)} {n(base)}) scale({s:.5f})">{out}</g>', w["width"] * s


def lockup(k, kind, wm_key="inter_shift"):
    """kind: 'tile' (icon tile + ink word), 'light' / 'dark' (bare mark + word), 'white' / 'black' (one colour). -> (svg string, w, h)"""
    cap = 100.0
    if kind == "tile":
        T = 250.0   # tile side
        clip = f'<clipPath id="c"><path d="{rrect(0, 0, 1024, 1024, 300)}"/></clipPath>'
        m = f'<g transform="scale({T / 1024})">{clip}<g clip-path="url(#c)">{icon_inner(k)}</g></g>'
        if isinstance(OPTS[k]["icon"]["tile"], tuple) and OPTS[k]["icon"]["tile"][2][0] == "#FFFFFF":
            m += f'<g transform="scale({T / 1024})"><path d="{rrect(3, 3, 1018, 1018, 298)}" fill="none" stroke="#0B0C14" stroke-opacity="0.10" stroke-width="6"/></g>'
        gap = 0.30 * T
        word, ww = wordmark(wm_key, INK, T + gap, T / 2 + cap / 2, cap)
        return svg(m + word, (0, 0, T + gap + ww, T), None, None), T + gap + ww, T
    b = bbox(k)
    mh = 1.95 * cap
    s = mh / (b[3] - b[1])
    mw = (b[2] - b[0]) * s
    style = {"light": OPTS[k]["light"], "dark": OPTS[k]["dark"], "white": "#FFFFFF", "black": INK}[kind]
    m = f'<g transform="scale({s:.5f}) translate({-b[0]:.1f} {-b[1]:.1f})">{mark(k, style)}</g>'
    gap = 0.50 * cap
    col = {"light": INK, "dark": "#F4F5FA", "white": "#FFFFFF", "black": INK}[kind]
    # the word's cap-height band is centred on the play triangle's centre, not the bounding box (the star lifts the box)
    cy = (play_cy(k) - b[1]) * s
    word, ww = wordmark(wm_key, col, mw + gap, cy + cap / 2, cap)
    return svg(m + word, (0, 0, mw + gap + ww, mh), None, None), mw + gap + ww, mh


def play_cy(k):
    return {"A": 556, "B": 560, "C": 512, "D": 532, "E": 523, "F": 574}[k]


# ---------- contrast ----------
def lum(hexc):
    c = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def cols(p):
    return [p] if isinstance(p, str) else list(p[2])


def contrast_lines(k):
    out = []
    ic = OPTS[k]["icon"]
    back = "badge" if k == "D" else "tile"
    for role in ("play", "spark", "spark2", "badge"):
        if role in ic:
            against = ic["tile"] if role != "play" or k != "D" else ic["badge"]
            rs = [ratio(a, b) for a in cols(ic[role]) for b in cols(against)]
            out.append(f"{role} on tile {min(rs):.1f}:1")
    lt = OPTS[k]["light"]
    for role in lt:
        rs = [ratio(a, "#F7F7FA") for a in cols(lt[role])]
        out.append(f"{role} on light page {min(rs):.1f}:1")
    return out


# ---------- sheet helpers ----------
def font(size, w="SemiBold"):
    return ImageFont.truetype(os.path.join(FONTS, f"Inter-{w}.ttf"), size)


BG = (242, 243, 247)
DARKBG = (6, 7, 13)


def mask_img(kind, S):
    if kind == "ios":
        d = squircle(512, 512)
    elif kind == "circle":
        d = f"M512,0A512,512 0 1 1 511.9,0Z"
    else:
        d = squircle(512, 512, 4.0)
    return render(svg(f'<path d="{d}" fill="#fff"/>'), S, S).getchannel("A")


def masked_icon(k, mode, kind, S, scale=1.0):
    im = render(svg(icon_inner(k, mode, scale)), S, S)
    im.putalpha(mask_img(kind, S))
    return im


def with_shadow(im, blur, dy, alpha, pad=None):
    pad = pad or int(blur * 3)
    W, H = im.size
    canvas = Image.new("RGBA", (W + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: int(v * alpha))
    sh.paste((0, 0, 0, 255), (pad, pad + dy), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh)
    canvas.alpha_composite(im, (pad, pad))
    return canvas, pad


def paste_c(dst, im, cx, cy):
    dst.alpha_composite(im, (int(cx - im.size[0] / 2), int(cy - im.size[1] / 2)))


def frames():
    src = Image.open(os.path.join(REPO, "docs", "design_bar", "mockups", "phone_2_videos.jpg")).convert("RGB")
    busy = src.crop((116, 966, 442, 1150)).resize((960, 540), Image.LANCZOS)
    forest = src.crop((116, 562, 637, 855)).resize((960, 540), Image.LANCZOS)
    dark = Image.new("RGB", (960, 540), (10, 11, 20))
    g = render(svg('<defs><radialGradient id="r" cx="0.3" cy="0.35" r="0.9"><stop offset="0" stop-color="#232846"/><stop offset="1" stop-color="#07080F"/></radialGradient></defs><rect width="960" height="540" fill="url(#r)"/>', (0, 0, 960, 540)), 960, 540)
    dark.paste(g.convert("RGB"))
    return dark, busy, forest


_frames = None


def watermark_frame(k, which, zoom=True):
    global _frames
    _frames = _frames or frames()
    fr = _frames[which].copy().convert("RGBA")
    s, w, h = lockup(k, "white")
    H = 30   # about 5.5% of a 540 frame, the size the engine uses
    lk = render(s, round(w * H / h), H)
    lk.putalpha(lk.getchannel("A").point(lambda v: int(v * 0.92)))
    wsh, pad = with_shadow(lk, 3.0, 1, 0.55, 12)
    fr.alpha_composite(wsh, (960 - 28 - lk.size[0] - pad, 540 - 24 - H - pad))
    if zoom:
        Z = 3
        box = (960 - 28 - lk.size[0] - 14, 540 - 24 - H - 12, 960 - 14, 540 - 10)
        z = fr.crop(box).resize(((box[2] - box[0]) * Z, (box[3] - box[1]) * Z), Image.LANCZOS)
        d = ImageDraw.Draw(z)
        d.rectangle((0, 0, z.size[0] - 1, z.size[1] - 1), outline=(255, 255, 255, 200), width=2)
        fr.alpha_composite(z, (24, 24))
        ImageDraw.Draw(fr).text((28, 24 + z.size[1] + 6), "3x", font=font(18), fill=(255, 255, 255, 220))
    return fr


def end_card(k, es=False):
    W, H = 960, 540
    inner = '<defs><radialGradient id="r" cx="0.5" cy="0.42" r="0.8"><stop offset="0" stop-color="#1B1E3A"/><stop offset="1" stop-color="#06070D"/></radialGradient></defs><rect width="960" height="540" fill="url(#r)"/>'
    b = bbox(k)
    mh = 150.0
    s = mh / (b[3] - b[1])
    mw = (b[2] - b[0]) * s
    inner += f'<g transform="translate({(W - mw) / 2:.1f} 128) scale({s:.5f}) translate({-b[0]:.1f} {-b[1]:.1f})">{mark(k, OPTS[k]["dark"])}</g>'
    key = "hecho_con" if es else "made_with"
    cap = 30.0
    ww = WM[key]["width"] * cap / WM[key]["cap"]
    t, _ = wordmark(key, "#F4F5FA", (W - ww) / 2, 372, cap)
    inner += t
    cap2 = 15.0
    w2 = WM["url"]["width"] * cap2 / WM["url"]["cap"]
    t2, _ = wordmark("url", "#A2A8BC", (W - w2) / 2, 420, cap2)
    inner += t2
    return render(svg(inner, (0, 0, W, H)), W, H)


# ---------- cells (one per view) ----------
def cell_mark(k, W=600, H=560):
    im = Image.new("RGBA", (W, H), BG + (255,))
    half = W // 2
    im.paste((247, 247, 250, 255), (0, 0, half, 380))
    im.paste(DARKBG + (255,), (half, 0, W, 380))
    b = bbox(k)
    for i, st in enumerate(("light", "dark")):
        m = render(svg(mark(k, OPTS[k][st]), (b[0], b[1], b[2] - b[0], b[3] - b[1])), *fit(b, 220))
        paste_c(im, m, half * i + half / 2, 190)
    im.paste((17, 19, 29, 255), (0, 380, half, H))
    im.paste((255, 255, 255, 255), (half, 380, W, H))
    for i, c in enumerate(("#FFFFFF", INK)):
        m = render(svg(mark(k, c), (b[0], b[1], b[2] - b[0], b[3] - b[1])), *fit(b, 110))
        paste_c(im, m, half * i + half / 2, 470)
    return im


def fit(b, S):
    w, h = b[2] - b[0], b[3] - b[1]
    k = S / max(w, h)
    return round(w * k), round(h * k)


def cell_ios(k, W=600, H=360):
    im = Image.new("RGBA", (W, H), BG + (255,))
    im.paste((28, 30, 42, 255), (W // 2, 0, W, H))
    for i, mode in enumerate(("icon", "icon_dark")):
        ic = masked_icon(k, mode, "ios", 230)
        sh, pad = with_shadow(ic, 14, 10, 0.28)
        paste_c(im, sh, W / 4 + i * W / 2, H / 2)
    return im


def cell_android(k, W=600, H=360):
    im = Image.new("RGBA", (W, H), (232, 234, 240, 255))
    for i, kind in enumerate(("circle", "squircle")):
        ic = masked_icon(k, "icon", kind, 210, 0.80)
        sh, pad = with_shadow(ic, 10, 6, 0.25)
        paste_c(im, sh, W / 4 + i * W / 2, H / 2)
    return im


def fav(k, S):
    clip = f'<clipPath id="c"><path d="{rrect(0, 0, 1024, 1024, 230)}"/></clipPath>'
    inner = f'{clip}<g clip-path="url(#c)">{icon_inner(k, "icon", 1.09)}</g>'
    if isinstance(OPTS[k]["icon"]["tile"], tuple) and OPTS[k]["icon"]["tile"][2][0] == "#FFFFFF":
        inner += f'<path d="{rrect(16, 16, 992, 992, 215)}" fill="none" stroke="#0B0C14" stroke-opacity="0.14" stroke-width="32"/>'
    return render(svg(inner), S, S)


def cell_fav(k, W=600, H=360):
    im = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    im.paste((32, 33, 36, 255), (0, 250, W, H))
    d = ImageDraw.Draw(im)
    # enlarged, pixel for pixel
    x = 30
    for S, Z in ((16, 10), (32, 5), (64, 2.5)):
        f = fav(k, S)
        z = f.resize((160, 160), Image.NEAREST)
        im.alpha_composite(z, (x, 30))
        d.text((x, 198), f"{S} px", font=font(20), fill=(92, 97, 117))
        x += 190
    # actual size on a light and a dark tab strip
    x = 30
    for S in (16, 32, 64):
        f = fav(k, S)
        im.alpha_composite(f, (x, 250 + (110 - S) // 2))
        x += S + 26
    d.text((x + 6, 292), "actual size", font=font(20), fill=(200, 203, 214))
    return im


def cell_lockup(k, W=600, H=360):
    im = Image.new("RGBA", (W, H), (247, 247, 250, 255))
    im.paste(DARKBG + (255,), (0, H // 2, W, H))
    s, w, h = lockup(k, "tile")
    hh = 78
    paste_c(im, render(s, round(w * hh / h), hh), W / 2, H / 4)
    s, w, h = lockup(k, "dark")
    hh = 80
    paste_c(im, render(s, round(w * hh / h), hh), W / 2, 3 * H / 4)
    return im


def cell_watermark(k, W=600, H=690):
    im = Image.new("RGBA", (W, H), BG + (255,))
    for i, which in enumerate((0, 1)):
        fr = watermark_frame(k, which).resize((W, round(W * 540 / 960)), Image.LANCZOS)
        im.alpha_composite(fr, (0, i * (fr.size[1] + 14)))
    return im


def cell_endcard(k, W=600, H=338):
    return end_card(k).resize((W, H), Image.LANCZOS)


VIEWS = [
    ("1-mark", "The mark alone: colour on light and dark, then one colour (white, black)", cell_mark),
    ("2-ios-icon", "iPhone app icon: light and dark", cell_ios),
    ("3-android-icon", "Android adaptive icon: circle and squircle masks", cell_android),
    ("4-favicon", "Favicon at 16, 32 and 64 px: enlarged pixel for pixel, and at actual size", cell_fav),
    ("5-lockup", "Lockup with the VideoMK wordmark (Inter): tile on light, bare mark on dark", cell_lockup),
    ("6-watermark", "Watermark in white with a soft shadow: dark frame and busy bright frame (3x inset)", cell_watermark),
    ("7-end-card", "The 'Made with VideoMK' end card", cell_endcard),
]


def label_bar(k, W):
    bar = Image.new("RGBA", (W, 64), (255, 255, 255, 255))
    d = ImageDraw.Draw(bar)
    d.rounded_rectangle((14, 12, 54, 52), 10, fill=(11, 12, 20))
    d.text((34, 32), k, font=font(26, "Bold"), fill=(255, 255, 255), anchor="mm")
    d.text((68, 32), OPTS[k]["name"], font=font(26, "Bold"), fill=(11, 12, 20), anchor="lm")
    return bar


def save_web(im, name, max_kb=390):
    im = im.convert("RGB")
    path = os.path.join(SHEETS, name + ".jpg")
    for q in (90, 86, 82, 78, 72, 66, 60):
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= max_kb * 1024:
            break
    else:
        im = im.resize((im.size[0] * 3 // 4, im.size[1] * 3 // 4), Image.LANCZOS)
        im.save(path, "JPEG", quality=72, optimize=True)
    return path


def comparison(view):
    slug, title, fn = view
    cells = [fn(k) for k in KEYS]
    cw, ch = cells[0].size
    G = 28
    W = 3 * cw + 4 * G
    top = 110
    H = top + 2 * (ch + 64 + G) + 8
    sh = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(sh)
    d.text((G, 30), "VideoMK logo options", font=font(22, "SemiBold"), fill=(92, 97, 117))
    d.text((G, 58), title, font=font(30, "Bold"), fill=(11, 12, 20))
    for i, k in enumerate(KEYS):
        x = G + (i % 3) * (cw + G)
        y = top + (i // 3) * (ch + 64 + G)
        sh.alpha_composite(label_bar(k, cw), (x, y))
        sh.alpha_composite(cells[i], (x, y + 64))
    return save_web(sh, f"compare-{slug}")


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def detail(k):
    W, G = 1260, 30
    o = OPTS[k]
    parts = [cell_mark(k), cell_ios(k), cell_android(k), cell_fav(k), cell_lockup(k), cell_endcard(k)]
    wm = [watermark_frame(k, i).resize((600, 338), Image.LANCZOS) for i in (0, 1)]
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f_txt = font(24, "Regular")
    text = [("Idea", o["idea"]), ("Colour", o["palette"]), ("Contrast (WCAG)", "; ".join(contrast_lines(k))), ("Nearest look-alike", o["near"])]
    lines = []
    for h, t in text:
        lines.append((h, None))
        lines += [(None, ln) for ln in wrap(tmp, t, f_txt, W - 2 * G)]
    th = sum(40 if h else 32 for h, _ in lines) + 20
    rows = [(parts[0], None), (parts[1], parts[2]), (parts[3], parts[4]), (wm[0], wm[1]), (parts[5], "mono")]
    H = 120 + th + parts[0].size[1] + G + 3 * (360 + G) + 2 * 338 + 2 * G + 40
    im = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((G, 30, G + 64, 94), 14, fill=(11, 12, 20))
    d.text((G + 32, 62), k, font=font(40, "Bold"), fill=(255, 255, 255), anchor="mm")
    d.text((G + 84, 62), f"{o['name']}", font=font(44, "Bold"), fill=(11, 12, 20), anchor="lm")
    y = 120
    for h, t in lines:
        if h:
            d.text((G, y + 8), h.upper(), font=font(18, "Bold"), fill=(92, 97, 117))
            y += 40
        else:
            d.text((G, y), t, font=f_txt, fill=(11, 12, 20))
            y += 32
    y += 20
    # mark (left) + swatches (right)
    im.alpha_composite(parts[0], (G, y))
    sx = G + 600 + G
    sw = []
    for mode in ("icon", "icon_dark"):
        for role, p in o[mode].items():
            for c in cols(p):
                if c not in sw:
                    sw.append(c)
    for i, c in enumerate(sw[:10]):
        cx, cy = sx + (i % 2) * 290, y + (i // 2) * 108
        d.rounded_rectangle((cx, cy, cx + 84, cy + 84), 18, fill=c, outline=(200, 203, 214), width=2)
        d.text((cx + 98, cy + 42), c.upper(), font=font(24, "SemiBold"), fill=(11, 12, 20), anchor="lm")
    y += parts[0].size[1] + G
    for a, b in ((parts[1], parts[2]), (parts[3], parts[4]), (wm[0], wm[1])):
        im.alpha_composite(a, (G, y))
        im.alpha_composite(b, (G + 600 + G, y))
        y += a.size[1] + G
    im.alpha_composite(parts[5], (G, y))
    # one-colour lockups beside the end card
    box = Image.new("RGBA", (600, 338), (17, 19, 29, 255))
    box.paste((255, 255, 255, 255), (0, 169, 600, 338))
    for i, kind in enumerate(("white", "black")):
        s, w, h = lockup(k, kind)
        paste_c(box, render(s, round(w * 70 / h), 70), 300, 84 + i * 169)
    im.alpha_composite(box, (G + 600 + G, y))
    im = im.crop((0, 0, W, y + 338 + G))
    return save_web(im, f"detail-{k}-{o['name'].lower()}")


def typeface_sheet(k="A"):
    rows = [("inter_shift", "Inter Display: Video 600 + MK 800 (recommended)", None),
            ("inter_700", "Inter Display: one weight, 700", None),
            ("inter_shift", "Inter Display: weight shift + MK in the primary colour", "#4B45E0"),
            ("manrope_shift", "Manrope 600 / 800", None),
            ("jakarta_shift", "Plus Jakarta Sans 600 / 800", None),
            ("sora_600", "Sora 600", None)]
    W, rh = 1260, 190
    im = Image.new("RGBA", (W, 110 + rh * len(rows)), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((30, 30), "VideoMK logo options", font=font(22), fill=(92, 97, 117))
    d.text((30, 58), "The wordmark: typeface candidates (all OFL, free for logo use)", font=font(30, "Bold"), fill=(11, 12, 20))
    b = bbox(k)
    for i, (key, lab, c2) in enumerate(rows):
        y = 110 + i * rh
        if i % 2:
            im.paste((247, 247, 250, 255), (0, y, W, y + rh))
        cap = 100.0
        mh = 195.0
        s = mh / (b[3] - b[1])
        mw = (b[2] - b[0]) * s
        cy = (play_cy(k) - b[1]) * s
        word, ww = wordmark(key, INK, mw + 50, cy + cap / 2, cap, c2)
        sv = svg(f'<g transform="scale({s:.5f}) translate({-b[0]:.1f} {-b[1]:.1f})">{mark(k, OPTS[k]["light"])}</g>' + word, (0, 0, mw + 50 + ww, mh))
        r = render(sv, round((mw + 50 + ww) * 96 / mh), 96)
        im.alpha_composite(r, (40, y + 30))
        d.text((40, y + 144), lab, font=font(22, "Regular"), fill=(92, 97, 117))
    return save_web(im, "wordmark-typefaces")


def write_sources():
    for k in KEYS:
        o = OPTS[k]
        b = bbox(k)
        vb = (b[0], b[1], b[2] - b[0], b[3] - b[1])
        out = {
            f"{k}-mark-on-light.svg": svg(mark(k, o["light"]), vb),
            f"{k}-mark-on-dark.svg": svg(mark(k, o["dark"]), vb),
            f"{k}-mark-white.svg": svg(mark(k, "#FFFFFF"), vb),
            f"{k}-mark-black.svg": svg(mark(k, INK), vb),
            f"{k}-icon-1024.svg": svg(icon_inner(k, "icon")),
            f"{k}-icon-1024-dark.svg": svg(icon_inner(k, "icon_dark")),
        }
        for kind in ("tile", "light", "dark", "white", "black"):
            out[f"{k}-lockup-{kind}.svg"] = lockup(k, kind)[0]
        for name, s in out.items():
            open(os.path.join(SVG_OUT, name), "w").write(s + "\n")


if __name__ == "__main__":
    only = os.environ.get("ONLY")
    write_sources()
    for v in VIEWS:
        if not only or only in v[0]:
            print(comparison(v))
    if not only or only == "detail":
        for k in KEYS:
            print(detail(k))
    if not only or only == "type":
        print(typeface_sheet())
    for k in KEYS:
        print(k, bbox(k), "; ".join(contrast_lines(k)))
