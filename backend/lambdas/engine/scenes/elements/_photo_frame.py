"""`photo_frame`: one of the user's photos presented as a designed piece (polaroid, matte, tilted with tape, a film frame, pinned on a cork board) over a blurred,
darkened enlargement of the same photo. Portrait and square photos are shown whole; a slow, gentle zoom; optional lower-third label and date chip."""
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ...canvas import Canvas, with_alpha
from ...easing import ease_in_out_cubic, ease_out_cubic, progress
from ...theme import Theme
from ..base import SceneCtx
from . import _photo_kit as K

STYLES = ("polaroid", "matte", "tilted", "film", "pinned")
AY0 = 62.0
ZOOM = 0.05                       # the photo grows by 5% over the scene
INK = (45, 48, 56)                # the dark ink of a polaroid's caption
# fractions of the photo's long side: border, bottom border, resting angle in degrees
SPEC = {"polaroid": (0.05, 0.23, -2.6), "matte": (0.105, 0.105, 0.0), "tilted": (0.032, 0.032, -3.6), "pinned": (0.036, 0.036, 1.8)}


def _fit(style: str, ratio: float, bw: float, bh: float) -> Tuple[float, float, float, float, float, float]:
    """(photo w, photo h, border, bottom border, angle, long side s) of the largest framed photo that fits bw x bh."""
    b, t, ang = SPEC[style]
    shrink = 1.0 - min(0.12, abs(ang) * 0.03)
    a, c = min(1.0, ratio), min(1.0, 1.0 / ratio)
    s = min(bw * shrink / (a + 2 * b), bh * shrink / (c + b + t))
    return s * a, s * c, b * s, t * s, ang, s


def _tape(ss: int, w: int, h: int) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    z = max(2, h // 8)
    pts = [(0, 0)]
    for k in range(1, 8):                                        # a torn, zig-zag left end
        pts.append((z if k % 2 else 0, k * h / 8))
    pts += [(0, h), (w, h)]
    for k in range(7, 0, -1):
        pts.append((w - (z if k % 2 else 0), k * h / 8))
    pts.append((w, 0))
    d.polygon(pts, fill=(250, 240, 196, 205))
    d.rectangle([0, h * 0.18, w, h * 0.26], fill=(255, 255, 255, 40))
    return im


def _pin(card: Image.Image, cx: float, cy: float, r: float, color) -> None:
    d = ImageDraw.Draw(card, "RGBA")
    d.ellipse([cx - r * 0.55, cy - r * 0.3, cx + r * 1.5, cy + r * 1.75], fill=(0, 0, 0, 80))        # its shadow on the photo
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(int(c * 0.72) for c in color) + (255,))
    d.ellipse([cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82], fill=tuple(color) + (255,))
    d.ellipse([cx - r * 0.5, cy - r * 0.55, cx - r * 0.05, cy - r * 0.1], fill=(255, 255, 255, 150))


def _sprite(cv: Canvas, style: str, src, pw: float, ph: float, bd: float, bt: float, ang: float, title: str, th: Theme) -> K.Sprite:
    ss = cv.ss
    w, h, b, t = int(round(pw * ss)), int(round(ph * ss)), int(round(bd * ss)), int(round(bt * ss))
    key = ("frame1", style, K.sid(src), w, h, b, t, round(ang, 1), title if style == "polaroid" else "", th.name if src is None else th.accent)

    def build() -> K.Sprite:
        photo = K.fit_photo(src, w, h, th, 0)
        if style == "matte":
            f = max(int(7 * ss), int(0.014 * max(w, h)))
            card = Image.new("RGB", (w + 2 * b, h + 2 * b), (36, 31, 29))
            d = ImageDraw.Draw(card, "RGBA")
            d.rectangle([f, f, card.width - f - 1, card.height - f - 1], fill=(246, 243, 236))
            d.rectangle([f, f, card.width - f - 1, card.height - f - 1], outline=(0, 0, 0, 50), width=max(1, ss))
            card.paste(photo, (b, b))
            d.rectangle([b - ss, b - ss, b + w, b + h], outline=(0, 0, 0, 90), width=max(1, ss))          # the bevel of the mat's window
            rgba = K.rounded(card, 2 * ss)
        elif style == "polaroid":
            card = Image.new("RGB", (w + 2 * b, h + b + t), (251, 250, 247))
            card.paste(photo, (b, b))
            d = ImageDraw.Draw(card, "RGBA")
            d.rectangle([b, b, b + w - 1, b + h - 1], outline=(0, 0, 0, 40), width=max(1, ss // 2))
            if title:
                size = t * 0.40
                font = cv.font("semibold", size / ss)
                while font.getlength(title) > card.width - 2 * b and size > t * 0.2:
                    size *= 0.93
                    font = cv.font("semibold", size / ss)
                d.text((card.width / 2, b + h + t * 0.5), title, font=font, fill=INK + (255,), anchor="mm")
            rgba = K.rounded(card, 3 * ss)
        else:                                                    # tilted, pinned: a thin white border
            card = Image.new("RGB", (w + 2 * b, h + 2 * b), (252, 251, 248))
            card.paste(photo, (b, b))
            ImageDraw.Draw(card, "RGBA").rectangle([b, b, b + w - 1, b + h - 1], outline=(0, 0, 0, 36), width=max(1, ss // 2))
            if style == "pinned":
                _pin(card, card.width / 2, b + 0.55 * min(w, h) * 0.06 + 14 * ss, max(10 * ss, 0.032 * max(w, h)), th.accent)
            rgba = K.rounded(card, 3 * ss)
            if style == "tilted":
                tw, tht = int(0.26 * max(w, h)), int(0.075 * max(w, h))
                tw, tht = max(tw, 90 * ss), max(tht, 30 * ss)
                tape = _tape(ss, tw, tht).rotate(-5, resample=Image.BICUBIC, expand=True)
                top = tape.height // 2 + ss
                big = Image.new("RGBA", (rgba.width, rgba.height + top), (0, 0, 0, 0))
                big.alpha_composite(rgba, (0, top))
                big.alpha_composite(tape, ((big.width - tape.width) // 2, 0))
                rgba = big
        rgba = K.rotated(rgba, ang)
        return K.sprite_of(K.shadowed(rgba, int(20 * ss), int(11 * ss), 0.5 if th.name != "paper" else 0.4))
    return K.cached(key, build, pin=src)


def _film_sprite(cv: Canvas, src, ratio: float, ih: float, th: Theme) -> K.Sprite:
    """A strip of film wider than the screen with the photo in the middle frame and empty (dark) frames either side, sprocket holes along both edges."""
    ss = cv.ss
    key = ("film1", K.sid(src), round(ih * ss), round(ratio, 3), th.name if src is None else "")

    def build() -> K.Sprite:
        band = int(46 * ss)
        W, H = int(2400 * ss), int(ih * ss) + 2 * band
        im = Image.new("RGB", (W, H), (17, 17, 21))
        d = ImageDraw.Draw(im, "RGBA")
        d.rectangle([0, band - 2 * ss, W, band - ss], fill=(255, 255, 255, 22))
        d.rectangle([0, H - band + ss, W, H - band + 2 * ss], fill=(255, 255, 255, 22))
        pitch, hw, hh = 52 * ss, 28 * ss, 19 * ss
        x = 8 * ss
        while x < W:
            for cy in (band / 2, H - band / 2):
                d.rounded_rectangle([x, cy - hh / 2, x + hw, cy + hh / 2], 5 * ss, fill=(233, 231, 224, 235))
            x += pitch
        pw, ph = int(round(ih * ss * ratio)), int(round(ih * ss))
        gap = int(24 * ss)
        fw = int(ph * 1.35)
        x0 = (W - pw) // 2
        for k in (-3, -2, -1, 1, 2, 3):                          # the neighbouring, unexposed frames (dark, a faint sheen)
            fx = x0 - gap - fw - (abs(k) - 1) * (fw + gap) if k < 0 else x0 + pw + gap + (k - 1) * (fw + gap)
            neg = Image.new("RGB", (fw, ph), (30, 30, 36))
            ImageDraw.Draw(neg, "RGBA").rectangle([0, 0, fw, ph // 2], fill=(255, 255, 255, 7))
            im.paste(K.rounded(neg, 4 * ss), (fx, band), K.rounded(neg, 4 * ss).getchannel("A"))
        photo = K.rounded(K.fit_photo(src, pw, ph, th, 0), 4 * ss)
        im.paste(photo, (x0, band), photo.getchannel("A"))
        return K.sprite_of(K.rounded(im, 0))
    return K.cached(key, build, pin=src)


def _cork(cv: Canvas, rect: Tuple[float, float, float, float]) -> K.Sprite:
    """A cork-board panel with a wooden rim: noise texture, built once."""
    ss = cv.ss
    x, y, w, h = rect
    pw, ph = int(w * ss), int(h * ss)

    def build() -> K.Sprite:
        rng = np.random.default_rng(11)
        lo = rng.normal(0, 1, (ph // 16 + 2, pw // 16 + 2)).astype(np.float32)
        mid = rng.normal(0, 1, (ph // 3 + 2, pw // 3 + 2)).astype(np.float32)
        fine = rng.normal(0, 1, (ph, pw)).astype(np.float32)
        up = lambda a, s: np.asarray(Image.fromarray(a).resize((pw, ph), Image.BICUBIC), np.float32)      # noqa: E731
        n = up(lo, 0) * 7 + up(mid, 0) * 6 + fine * 7
        base = np.array([176, 133, 92], np.float32)
        arr = np.clip(base[None, None, :] + n[:, :, None] * np.array([1.0, 0.85, 0.65], np.float32)[None, None, :], 0, 255).astype(np.uint8)
        im = Image.fromarray(arr, "RGB")
        d = ImageDraw.Draw(im, "RGBA")
        rim = int(16 * ss)
        d.rectangle([0, 0, pw - 1, ph - 1], outline=(104, 72, 46, 255), width=rim)
        d.rectangle([rim, rim, pw - rim - 1, ph - rim - 1], outline=(0, 0, 0, 70), width=max(2, 2 * ss))
        d.rectangle([0, 0, pw - 1, ph - 1], outline=(255, 255, 255, 28), width=max(1, ss))
        return K.sprite_of(K.shadowed(K.rounded(im, int(10 * ss)), int(18 * ss), int(10 * ss), 0.5))
    return K.cached(("cork", pw, ph), build)


def draw_frame(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    asset = str(props.get("asset") or "")
    src: Optional[Image.Image] = None
    if asset:
        try:
            src = ctx.resolve_image(asset)
        except Exception:
            src = None
    try:
        ratio = float(props.get("ratio") or 0)
    except (TypeError, ValueError):
        ratio = 0.0
    if not 0.2 <= ratio <= 5.0:
        ratio = src.width / src.height if src is not None else 1.5
    style = props.get("style") if props.get("style") in STYLES else "polaroid"
    title, subtitle, date = str(props.get("title") or ""), str(props.get("subtitle") or ""), str(props.get("date_label") or "")
    K.backdrop(cv, src, th)

    landscape = ratio >= 1.15
    in_frame_title = style == "polaroid" and bool(title)
    lab_title = "" if in_frame_title else title
    text = bool(lab_title or subtitle or date)
    bottom = ctx.bottom - 8
    ah = bottom - AY0
    lab = K.label_metrics(cv, lab_title, subtitle, 920 if landscape else 700)
    chip_h = K.chip_metrics(cv, date)[1] if date else 0.0
    strip = (max(lab["h"] if lab else 0.0, chip_h) + 24) if text and landscape else 0.0

    # where the photo goes: centred above the label strip, or (portrait/square with text) to the right of the label column
    if text and not landscape:
        cx, bw, bh, cy = 1230.0, 760.0, ah, AY0 + ah / 2
    else:
        cx, bw, bh, cy = 960.0, 1740.0, ah - strip, AY0 + (ah - strip) / 2
    if style == "pinned":
        bw, bh = bw - 70, bh - 60
        if text and not landscape:
            cx = 1250.0
    elif style == "tilted":
        bh -= 34
        cy += 14
    z = ease_in_out_cubic(progress(lt, 0.0, max(dur, 1.0)))
    k = (1.0 - ZOOM) + ZOOM * z
    a = ease_out_cubic(progress(lt, 0.0, 0.7))
    rise = (1 - a) * 36

    if style == "film":
        band_total = 92.0
        ih = max(120.0, min(bh - band_total, bw / ratio))
        sp = _film_sprite(cv, src, ratio, ih, th)
        K.blit(cv, sp, 960, cy + rise, scale=k, alpha=a)
    else:
        if style == "pinned":
            panel = (56.0, AY0 - 20, 1808.0, bottom - AY0 + 28)
            K.blit(cv, _cork(cv, panel), panel[0] + panel[2] / 2, panel[1] + panel[3] / 2, alpha=min(1.0, a * 1.6))
        pw, ph, bd, bt, ang, _ = _fit(style, ratio, bw, bh)
        sp = _sprite(cv, style, src, pw, ph, bd, bt, ang, title, th)
        K.blit(cv, sp, cx, cy + rise, scale=k, alpha=a)

    # the text: the lower-third at the bottom left, the date chip at the right of the strip (or above the label in the side layout)
    if lab:
        K.draw_label(cv, th, lab, lt, 90, bottom, t0=0.5)
    if date:
        if landscape:
            K.draw_chip(cv, th, date, lt, 1830, bottom, t0=0.7, anchor="r")
        else:
            K.draw_chip(cv, th, date, lt, 90, bottom - ((lab["h"] + 18) if lab else 0), t0=0.7)
