#!/usr/bin/env python3
"""Round 2 (27 Nov 2026): the owner chose option B's SHAPE (one rounded play, two stars) but not its ink tile. Eight colour treatments, B1-B8.

  .venv/bin/python docs/brand/2026-11-27-play-star/round2/build_r2.py <svg_out_dir> <sheet_out_dir>

Reuses ../build.py (geometry helpers, renderers, cells). Proposal only: nothing here is used by the apps.
Small sizes: under 24 px of mark height (the 16 px favicon) the small star is dropped and the big one grows: `SMALL`.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build as b
from PIL import Image, ImageDraw

lin, tri, spark, n = b.lin, b.tri, b.spark, b.n
SMALL = [False]


def geometry(k):
    play = ("play", tri(262, 326, 468, 420, 54), None, None)
    if SMALL[0]:   # one bigger star, a touch closer: what a 16 px favicon can hold
        return [play, ("spark", spark(690, 330, 132), None, None)]
    return [play, ("spark", spark(662, 332, 108), None, None), ("spark2", spark(800, 468, 62), None, None)]


def rad(*stops, c=(760, 250, 900)):
    return ("rad", c, stops)


_lin_paint = b.paint


def paint(p):
    if isinstance(p, tuple) and p[0] == "rad":
        b._uid[0] += 1
        gid = f"r{b._uid[0]}"
        _, c, stops = p
        st = "".join(f'<stop offset="{n(i / (len(stops) - 1))}" stop-color="{col}"/>' for i, col in enumerate(stops))
        return f"url(#{gid})", f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="{c[0]}" cy="{c[1]}" r="{c[2]}">{st}</radialGradient>'
    return _lin_paint(p)


MB = (262, 228, 862, 794)                      # the mark's box, for gradients that run across play and stars
ACT = lin("#3B36C8", "#7A4BE6")
ACT_M = lin("#3B36C8", "#7A4BE6", v=MB)
LUM = lin("#3B5BFF", "#9B4DFF")
LUM_M = lin("#3B5BFF", "#9B4DFF", v=MB)
BRAND_M = lin("#2B2F9A", "#6A3FC4", v=MB)
WHITE_T = lin("#FFFFFF", "#F1F1F8")
DUSK = lin("#2E2B7A", "#4A3496")               # the dark-mode icon ground: a deep indigo, tinted, not black
DUSK2 = lin("#2A3A9E", "#5A34A8")
STAR = (554, 224, 770, 440)                    # the big star's box
WARM = lin("#F43F5E", "#F97316", v=STAR)
WARM_D = lin("#FF6B81", "#FFA24D", v=STAR)
MAG = lin("#8B4DFF", "#D946EF", v=STAR)
W = "#FFFFFF"

OPTS = {
    "B1": dict(name="Action", idea="B's shape in A's colours: white play and stars on the product's action gradient",
               palette="Tile #3B36C8 to #7A4BE6 (the Create button), white mark. Dark icon: the same gradient two steps deeper",
               icon=dict(tile=ACT, play=W, spark=W, spark2=W), icon_dark=dict(tile=lin("#2A2790", "#4F2FA6"), play=W, spark=W, spark2="#D9D4FF"),
               light=dict(play=ACT_M, spark=ACT_M, spark2=ACT_M), dark=dict(play=W, spark=W, spark2=W),
               near="Generic 'AI video' glyphs (CapCut AI, Canva Magic Media); the sparkles emoji beside a play. Ours: the play is about 80% of the ink, two stars in a fixed 2:1 rhythm, our own indigo-violet"),
    "B2": dict(name="Luminous", idea="The same idea, brighter: a livelier blue to violet",
               palette="Tile #3B5BFF to #9B4DFF, white mark. Dark icon: #2A3A9E to #5A34A8",
               icon=dict(tile=LUM, play=W, spark=W, spark2=W), icon_dark=dict(tile=DUSK2, play=W, spark=W, spark2="#D6DBFF"),
               light=dict(play=LUM_M, spark=LUM_M, spark2=LUM_M), dark=dict(play=W, spark=W, spark2=W),
               near="Blue-to-purple gradient tiles are common (Messenger, Twitch-ish violets, many AI apps); Gemini's blue-to-purple star. Ours never shows a star alone, and the play leads"),
    "B3": dict(name="Ember", idea="Gradient play with a warm big star on a white tile",
               palette="White tile, play #3B36C8 to #7A4BE6, big star #F43F5E to #F97316, small star #7A4BE6",
               icon=dict(tile=WHITE_T, play=ACT_M, spark=WARM, spark2="#7A4BE6"), icon_dark=dict(tile=DUSK, play=W, spark=WARM_D, spark2="#CFC8FF"),
               light=dict(play=ACT_M, spark=WARM, spark2="#7A4BE6"), dark=dict(play=W, spark=WARM_D, spark2="#CFC8FF"),
               near="Google Play (colour triangle on white), Plex's warm accent. Ours: one hue family for the play, one warm star, rounded, no colour facets"),
    "B4": dict(name="Tint", idea="White tile, play in the brand gradient, stars in lighter tints of it",
               palette="White tile, play #2B2F9A to #6A3FC4, big star #7C6CF0, small star #A99BF7",
               icon=dict(tile=WHITE_T, play=BRAND_M, spark="#7C6CF0", spark2="#A99BF7"), icon_dark=dict(tile=DUSK, play=W, spark="#C9C2FF", spark2="#A99BF7"),
               light=dict(play=BRAND_M, spark="#7C6CF0", spark2="#A99BF7"), dark=dict(play=W, spark="#C9C2FF", spark2="#A99BF7"),
               near="Google Play on white at a glance (a triangle on a white tile); Stripe-like indigo. Ours is one colour family and has the stars"),
    "B5": dict(name="Electric", idea="One flat vivid colour and white",
               palette="Flat electric indigo #4B3BFF, white mark (a blue, #2F6BFF, was tried: see B5-icon-1024-blue.svg). Dark icon: #33288F",
               icon=dict(tile="#4B3BFF", play=W, spark=W, spark2=W), icon_dark=dict(tile="#33288F", play=W, spark=W, spark2="#D6D1FF"),
               light=dict(play="#4B3BFF", spark="#4B3BFF", spark2="#4B3BFF"), dark=dict(play=W, spark=W, spark2=W),
               near="Flat-tile white glyphs (Zoom's blue, Discord's blurple #5865F2 is the nearest colour). Ours is more violet-blue and the glyph is a play, not a face or camera"),
    "B6": dict(name="Lavender", idea="A very pale lavender tile with a deep indigo play and violet stars",
               palette="Tile #F4F1FF to #E3DCFF, play #2B2F9A to #3B36C8, big star #7A4BE6, small star #9B7BF0",
               icon=dict(tile=lin("#F4F1FF", "#E3DCFF"), play=lin("#2B2F9A", "#3B36C8", v=MB), spark="#7A4BE6", spark2="#9B7BF0"),
               icon_dark=dict(tile=lin("#3A3690", "#5A45B5"), play=W, spark="#E3DCFF", spark2="#C3B6FF"),
               light=dict(play=lin("#2B2F9A", "#3B36C8", v=MB), spark="#7A4BE6", spark2="#9B7BF0"), dark=dict(play=W, spark="#C9BCFF", spark2="#A99BF7"),
               near="Pastel-tile icons (Notion Calendar, Craft); quiet beside saturated neighbours. Ours keeps a strong dark play for the 'video' read"),
    "B7": dict(name="Glow", idea="A two-tone tile (a soft glow behind the stars), white play, one tinted star",
               palette="Tile radial #8A64F6 over #5B45E6 to #3B36C8, white play and small star, big star pale cyan #C9F7FF. Dark icon: the same glow, deeper",
               icon=dict(tile=rad("#8A64F6", "#5B45E6", "#3B36C8"), play=W, spark="#C9F7FF", spark2=W),
               icon_dark=dict(tile=rad("#6F55D6", "#3F33A8", "#2A2790"), play=W, spark="#B8F3FF", spark2="#E6E2FF"),
               light=dict(play=ACT_M, spark="#7A4BE6", spark2="#3B36C8"), dark=dict(play=W, spark="#B8F3FF", spark2=W),
               near="Glow-gradient AI icons (Copilot, Arc, Gemini's glows). Ours: the glow is one family (indigo-violet), behind a plain white play"),
    "B8": dict(name="Spectrum", idea="My pick for freshness: a white tile with a faint lavender glow, play blue to violet, big star violet to magenta",
               palette="Tile #FFFFFF with a #EFEAFF glow, play #3B5BFF to #8B4DFF, big star #8B4DFF to #D946EF, small star #3B5BFF",
               icon=dict(tile=rad("#FFFFFF", "#FAF9FF", "#EFEAFF", c=(300, 250, 1000)), play=lin("#3B5BFF", "#8B4DFF", v=MB), spark=MAG, spark2="#3B5BFF"),
               icon_dark=dict(tile=DUSK, play=W, spark=lin("#C4A8FF", "#F0A6FF", v=STAR), spark2="#B9C6FF"),
               light=dict(play=lin("#3B5BFF", "#8B4DFF", v=MB), spark=MAG, spark2="#3B5BFF"), dark=dict(play=lin("#7088FF", "#A97BFF", v=MB), spark=lin("#B58CFF", "#EE7BFF", v=STAR), spark2="#8FA2FF"),
               near="Google Play and Gemini are both near: a colour-gradient triangle on white, plus a blue-violet-pink star. Ours has no colour facets and the star never stands alone, but this is the closest of the eight"),
}
b.OPTS, b.KEYS, b.geometry, b.paint = OPTS, list(OPTS), geometry, paint
b.ICON_SCALE = {k: 1.06 for k in OPTS}
b.play_cy = lambda k: 560
KEYS = b.KEYS


def fav(k, S):
    SMALL[0] = S <= 16
    try:
        return _fav(k, S)
    finally:
        SMALL[0] = False


_fav, b.fav = b.fav, fav


def cell_fav(k, W=600, H=360):
    im = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    im.paste((32, 33, 36, 255), (0, 250, W, H))
    d = ImageDraw.Draw(im)
    x = 30
    for S, lab in ((16, "16 px: one star"), (32, "32 px"), (64, "64 px")):
        im.alpha_composite(fav(k, S).resize((160, 160), Image.NEAREST), (x, 30))
        d.text((x, 198), lab, font=b.font(20), fill=(92, 97, 117))
        x += 190
    x = 30
    for S in (16, 32, 64):
        im.alpha_composite(fav(k, S), (x, 250 + (110 - S) // 2))
        x += S + 26
    d.text((x + 6, 292), "actual size", font=b.font(20), fill=(200, 203, 214))
    return im


b.cell_fav = cell_fav
VIEWS = [
    ("1-mark", "The mark alone: colour on light and dark, then one colour (white, black)", b.cell_mark),
    ("2-ios-icon", "iPhone app icon: the default (left) and the dark-mode variant (right, a tinted indigo, not black)", b.cell_ios),
    ("3-android-icon", "Android adaptive icon: circle and squircle masks", b.cell_android),
    ("4-favicon", "Favicon: at 16 px the small star is dropped and the big one grows; two stars from 32 px", cell_fav),
    ("5-lockup", "Lockup with the VideoMK wordmark (Inter): tile on light, bare mark on dark", b.cell_lockup),
    ("6-watermark", "Watermark in white with a soft shadow: dark frame and busy bright frame (3x inset; the same for all eight)", b.cell_watermark),
    ("7-end-card", "The 'Made with VideoMK' end card", b.cell_endcard),
]


def comparison(view, cols=4):
    slug, title, fn = view
    cells = [fn(k) for k in KEYS]
    cw, ch = cells[0].size
    G, top = 28, 110
    rows = (len(KEYS) + cols - 1) // cols
    sh = Image.new("RGBA", (cols * cw + (cols + 1) * G, top + rows * (ch + 64 + G) + 8), b.BG + (255,))
    d = ImageDraw.Draw(sh)
    d.text((G, 30), "VideoMK logo, round 2: the two-star shape in eight colour treatments", font=b.font(22), fill=(92, 97, 117))
    d.text((G, 58), title, font=b.font(30, "Bold"), fill=(11, 12, 20))
    for i, k in enumerate(KEYS):
        x, y = G + (i % cols) * (cw + G), top + (i // cols) * (ch + 64 + G)
        bar = Image.new("RGBA", (cw, 64), (255, 255, 255, 255))
        bd = ImageDraw.Draw(bar)
        bd.rounded_rectangle((14, 12, 66, 52), 10, fill=(11, 12, 20))
        bd.text((40, 32), k, font=b.font(24, "Bold"), fill=(255, 255, 255), anchor="mm")
        bd.text((80, 32), OPTS[k]["name"], font=b.font(26, "Bold"), fill=(11, 12, 20), anchor="lm")
        sh.alpha_composite(bar, (x, y))
        sh.alpha_composite(cells[i], (x, y + 64))
    return b.save_web(sh, f"r2-compare-{slug}")


def sources():
    b.write_sources()
    SMALL[0] = True
    try:
        for k in KEYS:
            bx = b.render(b.svg(b.mark(k, "#000")), 2048, 2048).getchannel("A").getbbox()
            vb = (bx[0] / 2, bx[1] / 2, (bx[2] - bx[0]) / 2, (bx[3] - bx[1]) / 2)
            for name, s in ((f"{k}-small-mark-white.svg", b.svg(b.mark(k, "#FFFFFF"), vb)), (f"{k}-small-mark-black.svg", b.svg(b.mark(k, b.INK), vb)),
                            (f"{k}-small-icon-1024.svg", b.svg(b.icon_inner(k, "icon", 1.09)))):
                open(os.path.join(b.SVG_OUT, name), "w").write(s + "\n")
    finally:
        SMALL[0] = False
    blue = dict(OPTS["B5"]["icon"], tile="#2F6BFF")
    OPTS["B5x"] = dict(OPTS["B5"], icon=blue)
    open(os.path.join(b.SVG_OUT, "B5-icon-1024-blue.svg"), "w").write(b.svg(b.icon_inner("B5x", "icon")) + "\n")
    del OPTS["B5x"]


if __name__ == "__main__":
    sources()
    only = os.environ.get("ONLY")
    for v in VIEWS:
        if not only or only in v[0]:
            print(comparison(v))
    for k in (os.environ.get("TOP") or "").split(","):
        if k:
            p = b.detail(k)
            q = os.path.join(os.path.dirname(p), "r2-" + os.path.basename(p))
            os.replace(p, q)
            print(q)
    for k in KEYS:
        print(k, "; ".join(b.contrast_lines(k)))
