#!/usr/bin/env python3
"""The VideoMK logo, B1 "Action" (chosen by the owner, 27 Nov 2026): builds every brand file from one geometry.

  .venv/bin/python docs/brand/final/build_final.py            # masters (this folder) + store files + the apps', the site's and the sign-in page's copies
  .venv/bin/python docs/brand/final/build_final.py masters    # only this folder and ../store

One rounded play triangle and TWO four-point stars (the second 0.66 of the first), the same drawing at every size. White on the action
gradient #3B36C8 to #7A4BE6. Wordmark: "VideoMK" in Inter (OFL), Video 600 + MK 800, outlines in wordmark.json (made by
../2026-11-27-play-star/wordmarks.py). Needs resvg_py + Pillow (the repo's .venv). Every SVG written here is plain paths: no groups,
transforms, masks, clip paths or fonts, so Xcode, Android Studio, Cognito and browsers all read them the same way.
After this, the watermark art is rebuilt with backend/scripts/watermark_assets.py.
"""
import io, json, os, re, sys

import resvg_py
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
STORE = os.path.join(HERE, "..", "store")
FONTS = os.path.join(REPO, "backend", "lambdas", "engine", "assets", "fonts")
WM = json.load(open(os.path.join(HERE, "wordmark.json")))   # {"cap", "width", "segs": [{"d"}, {"d"}]}: "Video" (600) and "MK" (800), baseline at y = 0, y up is negative

# ---------- the one geometry (1024 grid) ----------
PLAY = "M242,417.9Q242,326 322.3,370.7L567.2,507.2Q662,560 567.2,612.8L322.3,749.3Q242,794 242,702.1Z"
STAR = "M630,190C640.2,274.5 673.5,307.8 758,318C673.5,328.2 640.2,361.5 630,446C619.8,361.5 586.5,328.2 502,318C586.5,307.8 619.8,274.5 630,190Z"
STAR2 = "M786,388C796.1,438.4 819.6,461.9 870,472C819.6,482.1 796.1,505.6 786,556C775.9,505.6 752.4,482.1 702,472C752.4,461.9 775.9,438.4 786,388Z"
BOX = (242.0, 190.0, 870.0, 764.0)     # the ink's bounding box: 628 x 574
PLAY_CY = 560.0                        # the play's centre line: the wordmark's cap band is centred on it
ICON_SCALE = 1.06                      # the mark in the app icon, about the tile's centre
FAV_SCALE = 1.06 * 1.09                # a little larger in the rounded tile (favicon, in-app mark)
ANDROID_SCALE = 1.06 * 0.80            # every point of ink inside the 66 dp safe circle of the 108 dp canvas
TILE_RX = 232                          # the rounded tile (favicon, in-app mark, lockup tile), on the 1024 grid

ACTION = ("#3B36C8", "#7A4BE6")        # the action gradient, top left to bottom right
INK_TILE = ("#151828", "#06070D")      # dark-appearance icon tile (Midnight)
DARK_PLAY = ("#6360FF", "#B56CFF")
DARK_STAR = ("#7CEBFA", "#22D3EE")
DARK_STAR2 = "#E9E8FF"
INK, PAPER_TEXT, WHITE = "#0B0C14", "#F4F5FA", "#FFFFFF"


def n(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


_TOK = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?")
_ARGS = {"M": 2, "L": 2, "T": 2, "Q": 4, "S": 4, "C": 6, "H": 1, "V": 1, "Z": 0}


def xf(d, s=1.0, tx=0.0, ty=0.0):
    """The path with x' = x * s + tx, y' = y * s + ty baked into its numbers (absolute commands only)."""
    out, toks, i, cmd = [], _TOK.findall(d), 0, None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            assert t in _ARGS, f"path command {t} is not handled"
            cmd = t
            i += 1
            if cmd == "Z":
                out.append("Z")
                continue
        k = _ARGS[cmd]
        vals = [float(v) for v in toks[i:i + k]]
        i += k
        if cmd == "H":
            vals = [vals[0] * s + tx]
        elif cmd == "V":
            vals = [vals[0] * s + ty]
        else:
            vals = [v * s + (tx if j % 2 == 0 else ty) for j, v in enumerate(vals)]
        out.append(cmd + " ".join(n(v) for v in vals))
        if cmd == "M":
            cmd = "L"   # further pairs after a moveto are linetos
    return "".join(out)


def about(s, c=512.0):
    """(s, tx, ty) of a scale about the centre of the 1024 grid."""
    return s, c - c * s, c - c * s


def lin(gid, c, box):
    return (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{n(box[0])}" y1="{n(box[1])}" x2="{n(box[2])}" y2="{n(box[3])}">'
            f'<stop offset="0" stop-color="{c[0]}"/><stop offset="1" stop-color="{c[1]}"/></linearGradient>')


def tbox(box, s, tx, ty):
    return (box[0] * s + tx, box[1] * s + ty, box[2] * s + tx, box[3] * s + ty)


def mark(fills, s=1.0, tx=0.0, ty=0.0, attr=""):
    """The three paths. fills: one colour, or (play, star, star2)."""
    f = (fills,) * 3 if isinstance(fills, str) else fills
    return "".join(f'<path d="{xf(d, s, tx, ty)}" fill="{c}"{attr}/>' for d, c in zip((PLAY, STAR, STAR2), f))


def svg(inner, vb, w=None, h=None, extra=""):
    size = f' width="{n(w)}" height="{n(h)}"' if w else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(n(v) for v in vb)}"{size}{extra}>{inner}</svg>\n'


def render(svg_str, w, h):
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg_str, width=int(w), height=int(h))))).convert("RGBA")


def flat(im):
    """RGB, no alpha channel at all (App Store, Play, favicon PNGs)."""
    bg = Image.new("RGB", im.size, (0, 0, 0))
    bg.paste(im, mask=im.getchannel("A"))
    return bg


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)


# ---------- icons ----------
def icon(mode="light", scale=ICON_SCALE, rx=0, size=None):
    """Full-bleed 1024 icon art (rx > 0: the rounded tile used on the web and inside the apps). mode: light | dark | tinted."""
    s, tx, ty = about(scale)
    r = f' rx="{rx}"' if rx else ""
    if mode == "light":
        defs = lin("bg", ACTION, (0, 0, 1024, 1024))
        body = mark(WHITE, s, tx, ty)
    elif mode == "dark":
        defs = lin("bg", INK_TILE, (0, 0, 1024, 1024)) + lin("p", DARK_PLAY, tbox((242, 190, 872, 794), s, tx, ty)) + lin("s", DARK_STAR, tbox((502, 190, 758, 446), s, tx, ty))
        body = mark(("url(#p)", "url(#s)", DARK_STAR2), s, tx, ty)
    else:   # tinted: grey values only, fully opaque; iOS lays the person's tint over it
        defs = lin("bg", ("#1E1E1E", "#000000"), (0, 0, 0, 1024)) + lin("p", ("#FFFFFF", "#C9C9C9"), (0, 190 * s + ty, 0, 764 * s + ty))
        body = mark("url(#p)", s, tx, ty)
    return svg(f'<defs>{defs}</defs><rect width="1024" height="1024"{r} fill="url(#bg)"/>{body}', (0, 0, 1024, 1024), size, size)


# ---------- lockups ----------
def word(fill, x, base, cap, fill_mk=None):
    s = cap / WM["cap"]
    return "".join(f'<path d="{xf(seg["d"], s, x, base)}" fill="{fill_mk if (fill_mk and i) else fill}"/>' for i, seg in enumerate(WM["segs"])), WM["width"] * s


def tile_at(x, y, T, uid="t"):
    """The rounded gradient tile with the white mark, T wide, at (x, y)."""
    k = T / 1024
    s, tx, ty = about(FAV_SCALE)
    return (f'<defs>{lin(uid, ACTION, (x, y, x + T, y + T))}</defs><rect x="{n(x)}" y="{n(y)}" width="{n(T)}" height="{n(T)}" rx="{n(TILE_RX * k)}" fill="url(#{uid})"/>'
            + mark(WHITE, s * k, tx * k + x, ty * k + y))


def bare_at(x, y, mh, kind):
    """The mark without a tile, mh tall, top left at (x, y). kind: light (gradient ink) | dark / white (white) | black (ink) | mono (currentColor)."""
    s = mh / (BOX[3] - BOX[1])
    tx, ty = x - BOX[0] * s, y - BOX[1] * s
    if kind == "light":
        return f'<defs>{lin("m", ACTION, tbox((242, 190, 872, 794), s, tx, ty))}</defs>' + mark("url(#m)", s, tx, ty), (BOX[2] - BOX[0]) * s, s, ty
    fill = {"dark": WHITE, "white": WHITE, "black": INK, "mono": "currentColor"}[kind]
    return mark(fill, s, tx, ty), (BOX[2] - BOX[0]) * s, s, ty


def word_colour(kind):
    return {"light": INK, "tile-light": INK, "black": INK, "dark": PAPER_TEXT, "tile-dark": PAPER_TEXT, "white": WHITE, "mono": "currentColor"}[kind]


def horizontal(kind, pad=0.0):
    """-> (svg, w, h). kind: tile-light | tile-dark (tile + word) or light | dark | white | black (bare mark + word)."""
    cap = 100.0
    if kind.startswith("tile"):
        T = 250.0
        gap = 0.30 * T
        w_svg, ww = word(word_colour(kind), T + gap, T / 2 + cap / 2, cap)
        W, H = T + gap + ww, T
        return svg(tile_at(0, 0, T) + w_svg, (0, -pad, W, H + 2 * pad), W, H + 2 * pad), W, H + 2 * pad
    mh = 1.95 * cap
    m, mw, s, ty = bare_at(0, 0, mh, kind)
    gap = 0.50 * cap
    cy = PLAY_CY * s + ty
    w_svg, ww = word(word_colour(kind), mw + gap, cy + cap / 2, cap)
    W = mw + gap + ww
    return svg(m + w_svg, (0, 0, W, mh), W, mh), W, mh


def stacked(kind):
    cap = 100.0
    _, ww = word(INK, 0, 0, cap)
    if kind.startswith("tile"):
        T, gap = 340.0, 0.85 * cap
        W, H = ww, T + gap + cap
        w_svg, _ = word(word_colour(kind), 0, H, cap)
        return svg(tile_at((W - T) / 2, 0, T) + w_svg, (0, 0, W, H + 2), W, H + 2), W, H + 2
    mh, gap = 3.0 * cap, 0.80 * cap
    mw = mh * (BOX[2] - BOX[0]) / (BOX[3] - BOX[1])
    W, H = ww, mh + gap + cap
    m, _, _, _ = bare_at((W - mw) / 2, 0, mh, kind)
    w_svg, _ = word(word_colour(kind), 0, H, cap)
    return svg(m + w_svg, (0, 0, W, H + 2), W, H + 2), W, H + 2


# ---------- Android ----------
def vector(paths, aapt=False):
    head = ('<?xml version="1.0" encoding="utf-8"?>\n<!-- Made by docs/brand/final/build_final.py: do not edit by hand. -->\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"' + (' xmlns:aapt="http://schemas.android.com/aapt"' if aapt else '') + '\n'
            '    android:width="108dp" android:height="108dp" android:viewportWidth="1024" android:viewportHeight="1024">\n')
    return head + paths + "</vector>\n"


def android_files():
    s, tx, ty = about(ANDROID_SCALE)
    fg = "".join(f'    <path android:fillColor="#FFFFFF" android:pathData="{xf(d, s, tx, ty)}" />\n' for d in (PLAY, STAR, STAR2))
    bg = ('    <path android:pathData="M0,0h1024v1024h-1024z">\n        <aapt:attr name="android:fillColor">\n'
          '            <gradient android:startX="0" android:startY="0" android:endX="1024" android:endY="1024" android:type="linear">\n'
          f'                <item android:offset="0" android:color="{ACTION[0]}" />\n                <item android:offset="1" android:color="{ACTION[1]}" />\n'
          '            </gradient>\n        </aapt:attr>\n    </path>\n')
    return {"ic_launcher_foreground.xml": vector(fg), "ic_launcher_monochrome.xml": vector(fg), "ic_launcher_background.xml": vector(bg, aapt=True)}


def android_svgs():
    s, tx, ty = about(ANDROID_SCALE)
    return {
        "android-adaptive-foreground.svg": svg(mark(WHITE, s, tx, ty), (0, 0, 1024, 1024)),
        "android-monochrome.svg": svg(mark(WHITE, s, tx, ty), (0, 0, 1024, 1024)),
        "android-adaptive-background.svg": svg(f'<defs>{lin("bg", ACTION, (0, 0, 1024, 1024))}</defs><rect width="1024" height="1024" fill="url(#bg)"/>', (0, 0, 1024, 1024)),
    }


# ---------- raster compositions ----------
def font(size, w="SemiBold"):
    return ImageFont.truetype(os.path.join(FONTS, f"Inter-{w}.ttf"), size)


def gradient(W, H):
    return render(svg(f'<defs>{lin("bg", ACTION, (0, 0, W, H))}</defs><rect width="{W}" height="{H}" fill="url(#bg)"/>', (0, 0, W, H)), W, H)


def lockup_png(kind, height):
    s, w, h = horizontal(kind)
    return render(s, round(height * w / h), height)


def feature_graphic():
    """Google Play feature graphic, 1024 x 500: the white lockup on the action gradient, and the product's line."""
    im = gradient(1024, 500)
    lk = lockup_png("white", 150)
    im.alpha_composite(lk, ((1024 - lk.width) // 2, 138))
    d = ImageDraw.Draw(im)
    d.text((512, 362), "Describe it. Get the video.", font=font(34, "SemiBold"), fill=(255, 255, 255, 235), anchor="mm")
    return flat(im)


def og_image():
    """The share image, 1200 x 630: lockup, the line, and a real frame of a VideoMK video."""
    im = gradient(1200, 630)
    lk = lockup_png("white", 92)
    im.alpha_composite(lk, (72, 70))
    d = ImageDraw.Draw(im)
    d.text((70, 240), "Describe it.", font=font(76, "Bold"), fill=(255, 255, 255))
    d.text((70, 334), "Get the video.", font=font(76, "Bold"), fill=(255, 255, 255))
    d.text((72, 466), "AI explainer videos from one sentence", font=font(28, "Regular"), fill=(255, 255, 255, 225))
    poster = os.path.join(REPO, "frontend", "public", "samples", "forest.webp")
    if os.path.exists(poster):
        fw, fh = 520, 292
        fr = Image.open(poster).convert("RGB").resize((fw, fh), Image.LANCZOS).convert("RGBA")
        m = Image.new("L", (fw * 2, fh * 2), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, fw * 2 - 1, fh * 2 - 1), 44, fill=255)
        fr.putalpha(m.resize((fw, fh), Image.LANCZOS))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.paste((10, 8, 50, 150), (630, 196 + 18), fr.getchannel("A"))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
        im.alpha_composite(fr, (630, 196))
    return flat(im)


def save_jpg(im, path, max_kb):
    for q in (90, 86, 82, 78, 74, 70):
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= max_kb * 1024:
            return


def save_ico(svg_str, path):
    ims = [render(svg_str, s, s) for s in (48, 32, 16)]   # each size drawn from the vector, not scaled down from a larger one
    ims[0].save(path, format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=ims[1:])


def preview():
    W, H = 1600, 900
    im = Image.new("RGBA", (W, H), (242, 243, 247, 255))
    im.paste((6, 7, 13, 255), (0, 520, W, H))
    x = 60
    for mode in ("light", "dark", "tinted"):
        ic = render(icon(mode, rx=TILE_RX), 300, 300)
        im.alpha_composite(ic, (x, 60))
        x += 340
    for S in (64, 32, 16):
        im.alpha_composite(render(icon("light", FAV_SCALE, TILE_RX), S, S), (x, 60))
        x += S + 24
    for i, kind in enumerate(("tile-light", "light", "black")):
        im.alpha_composite(lockup_png(kind, 90), (60 + i * 500, 400))
    for i, kind in enumerate(("tile-dark", "dark", "white")):
        im.alpha_composite(lockup_png(kind, 90), (60 + i * 500, 570))
    for i, kind in enumerate(("tile-dark", "dark")):
        s, w, h = stacked(kind)
        im.alpha_composite(render(s, round(170 * w / h), 170), (60 + i * 500, 700))
    return flat(im)


# ---------- outputs ----------
def masters():
    out = {
        "mark-gradient.svg": svg(bare_at(0, 0, 574, "light")[0], (0, 0, 628, 574)),
        "mark-white.svg": svg(bare_at(0, 0, 574, "white")[0], (0, 0, 628, 574)),
        "mark-black.svg": svg(bare_at(0, 0, 574, "black")[0], (0, 0, 628, 574)),
        "mark-mono.svg": svg(bare_at(0, 0, 574, "mono")[0], (0, 0, 628, 574)),
        "mark-tile.svg": icon("light", FAV_SCALE, TILE_RX),
        "favicon.svg": icon("light", FAV_SCALE, TILE_RX, 64),
        "icon-1024.svg": icon("light"),
        "icon-1024-dark.svg": icon("dark"),
        "icon-1024-tinted.svg": icon("tinted"),
        **android_svgs(),
    }
    for kind in ("tile-light", "tile-dark", "light", "dark", "white", "black"):
        out[f"lockup-horizontal-{kind}.svg"] = horizontal(kind)[0]
        out[f"lockup-stacked-{kind}.svg"] = stacked(kind)[0]
    for name, s in out.items():
        write(os.path.join(HERE, name), s)
    for mode, name in (("light", "icon-1024.png"), ("dark", "icon-1024-dark.png"), ("tinted", "icon-1024-tinted.png")):
        im = flat(render(icon(mode), 1024, 1024))
        (im.convert("L").convert("RGB") if mode == "tinted" else im).save(os.path.join(HERE, name), optimize=True)
    render(icon("light", FAV_SCALE, TILE_RX), 512, 512).save(os.path.join(HERE, "favicon-512.png"), optimize=True)   # the rounded tile keeps its transparent corners
    for kind in ("tile-light", "tile-dark", "white"):
        lockup_png(kind, 400).save(os.path.join(HERE, f"lockup-horizontal-{kind}.png"), optimize=True)
    preview().save(os.path.join(HERE, "preview.png"), optimize=True)
    # store files
    os.makedirs(STORE, exist_ok=True)
    full = icon("light")
    flat(render(full, 1024, 1024)).save(os.path.join(STORE, "videomk-app-store-icon-1024.png"), optimize=True)
    flat(render(full, 512, 512)).convert("RGBA").save(os.path.join(STORE, "videomk-play-store-icon-512.png"), optimize=True)   # Play asks for a 32-bit PNG: alpha channel present, every pixel opaque
    flat(render(full, 120, 120)).save(os.path.join(STORE, "videomk-google-consent-logo-120.png"), optimize=True)
    feature_graphic().save(os.path.join(STORE, "videomk-play-feature-graphic-1024x500.png"), optimize=True)
    save_jpg(og_image(), os.path.join(STORE, "videomk-og-1200x630.jpg"), 150)
    print("masters:", len(out), "svg files; store files written")
    return out


def apps():
    # iPhone
    ios = os.path.join(REPO, "mobile", "ios", "VideoMK", "Assets.xcassets")
    for mode, name in (("light", "icon-1024.png"), ("dark", "icon-1024-dark.png"), ("tinted", "icon-1024-tinted.png")):
        im = flat(render(icon(mode), 1024, 1024))
        (im.convert("L").convert("RGB") if mode == "tinted" else im).save(os.path.join(ios, "AppIcon.appiconset", name), optimize=True)
    write(os.path.join(ios, "BrandMark.imageset", "BrandMark.svg"), icon("light", FAV_SCALE, TILE_RX, 64))
    write(os.path.join(ios, "Lockup.imageset", "lockup-light.svg"), horizontal("tile-light")[0])
    write(os.path.join(ios, "Lockup.imageset", "lockup-dark.svg"), horizontal("tile-dark")[0])
    # Android
    res = os.path.join(REPO, "mobile", "android", "app", "src", "main", "res", "drawable")
    for name, text in android_files().items():
        write(os.path.join(res, name), text)
    # the site and the web app
    pub = os.path.join(REPO, "frontend", "public")
    fav = icon("light", FAV_SCALE, TILE_RX, 64)
    write(os.path.join(pub, "favicon.svg"), fav)
    save_ico(fav, os.path.join(pub, "favicon.ico"))
    full = icon("light")
    for S, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        flat(render(full, S, S)).save(os.path.join(pub, name), optimize=True)
    save_jpg(og_image(), os.path.join(pub, "og.jpg"), 150)
    # the Cognito sign-in page (backend/login_branding): logo 1:1 .. 4:1, SVG without scripts or images
    lb = os.path.join(REPO, "backend", "login_branding")
    write(os.path.join(lb, "logo-light.svg"), horizontal("tile-light", pad=40)[0])
    write(os.path.join(lb, "logo-dark.svg"), horizontal("tile-dark", pad=40)[0])
    write(os.path.join(lb, "favicon.svg"), fav)
    save_ico(fav, os.path.join(lb, "favicon.ico"))
    print("apps: iPhone, Android, web and sign-in page files written")


def checks():
    """The numbers the README quotes."""
    import math
    s, tx, ty = about(ANDROID_SCALE)
    a = render(svg(mark(WHITE, s, tx, ty), (0, 0, 1024, 1024)), 1024, 1024).getchannel("A")
    far = max(math.hypot(x - 511.5, y - 511.5) for y in range(0, 1024, 2) for x in range(0, 1024, 2) if a.getpixel((x, y)) > 8)
    print(f"android: farthest ink {far:.0f} px from the centre; safe circle radius {1024 * 33 / 108:.0f} px")
    assert far <= 1024 * 33 / 108
    for kind in ("tile-light", "light", "white"):
        _, w, h = horizontal(kind)
        print(f"lockup horizontal {kind}: {w:.1f} x {h:.1f} = {w / h:.2f}")
    for kind in ("tile-light", "light"):
        _, w, h = stacked(kind)
        print(f"lockup stacked {kind}: {w:.1f} x {h:.1f} = {w / h:.2f}")


if __name__ == "__main__":
    masters()
    if "masters" not in sys.argv[1:]:
        apps()
    checks()
