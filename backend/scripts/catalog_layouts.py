"""Composition guides for the catalog generator: simple greyscale-ish drawings (made here, from nothing: no stock photo or third-party image is ever used) that the
image model keeps the STRUCTURE of. They enforce the house composition: subject in the middle third (so the 9:16 and 1:1 centre crops keep it) and a calm bottom quarter.
Each layout is `fn(seed) -> PIL.Image` of 1344x768 (16:9, the model's native size; one megapixel is also the largest the fast upscaler accepts)."""
import math
import random
from typing import Callable, Dict

from PIL import Image, ImageDraw, ImageFilter

W, H = 1344, 768


def _sky(top=(205, 215, 230), bottom=(235, 225, 215)) -> Image.Image:
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im


def _ridge(rng: random.Random, base: int, amp: int, peak_x: int, spread: int = 480) -> list:
    pts = [(0, H)]
    for x in range(0, W + 1, 24):
        bump = amp * math.exp(-((x - peak_x) / spread) ** 2)
        pts.append((x, int(base - bump + rng.uniform(-amp * 0.08, amp * 0.08))))
    pts.append((W, H))
    return pts


def mountains(seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = _sky()
    d = ImageDraw.Draw(im)
    d.polygon(_ridge(rng, 470, 230, 672), fill=(105, 115, 130))
    d.polygon(_ridge(rng, 500, 130, 300, 300), fill=(85, 95, 105))
    d.polygon(_ridge(rng, 505, 90, 1050, 300), fill=(75, 85, 95))
    d.rectangle([0, 560, W, H], fill=(60, 80, 100))   # a lake or valley floor: calm bottom
    return im.filter(ImageFilter.GaussianBlur(2))


def horizon(seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = _sky((190, 205, 225), (240, 215, 190))
    d = ImageDraw.Draw(im)
    y = int(H * rng.uniform(0.56, 0.64))
    sx = W // 2 + rng.randint(-120, 120)
    d.ellipse([sx - 60, y - 70, sx + 60, y + 50], fill=(250, 235, 200))
    d.rectangle([0, y, W, H], fill=(70, 95, 120))
    return im.filter(ImageFilter.GaussianBlur(3))


def layered_ridges(seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = _sky((210, 220, 235), (245, 230, 215))
    d = ImageDraw.Draw(im)
    for i, (base, amp, shade) in enumerate(((380, 120, 170), (440, 140, 135), (510, 130, 105), (590, 100, 80))):
        d.polygon(_ridge(rng, base, amp, rng.randint(250, 1100), 420), fill=(shade, shade + 8, shade + 16))
    d.rectangle([0, 640, W, H], fill=(60, 75, 85))
    return im.filter(ImageFilter.GaussianBlur(4))


def forest_path(seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = Image.new("RGB", (W, H), (190, 200, 175))
    d = ImageDraw.Draw(im)
    d.polygon([(W // 2 - 40, 330), (W // 2 + 40, 330), (W // 2 + 380, H), (W // 2 - 380, H)], fill=(140, 125, 100))
    for side in (-1, 1):
        for i in range(7):
            x = W // 2 + side * (200 + i * 95 + rng.randint(-20, 20))
            w = 28 - i * 2
            d.rectangle([x - w, 0, x + w, 600], fill=(45, 55, 40))
    d.rectangle([0, 0, W, 90], fill=(60, 80, 55))
    d.rectangle([0, 690, W, H], fill=(70, 70, 55))
    return im.filter(ImageFilter.GaussianBlur(5))


def dunes(seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = _sky((235, 200, 160), (250, 225, 190))
    d = ImageDraw.Draw(im)
    for base, shade in ((430, (200, 150, 100)), (520, (180, 125, 80)), (620, (150, 100, 65))):
        pts = [(0, H)] + [(x, int(base + 60 * math.sin(x / 190 + rng.uniform(0, 1)) + 30 * math.sin(x / 70))) for x in range(0, W + 1, 16)] + [(W, H)]
        d.polygon(pts, fill=shade)
    d.rectangle([0, 700, W, H], fill=(120, 80, 55))
    return im.filter(ImageFilter.GaussianBlur(3))


def center_object(seed: int) -> Image.Image:
    """A single subject in the middle third on a soft background; a calm lower band."""
    rng = random.Random(seed)
    im = Image.new("RGB", (W, H), (200, 195, 185))
    d = ImageDraw.Draw(im)
    for y in range(H):
        c = int(215 - 60 * (y / H))
        d.line([(0, y), (W, y)], fill=(c, c - 5, c - 12))
    cx, cy = W // 2 + rng.randint(-40, 40), int(H * 0.46)
    d.ellipse([cx - 190, cy - 170, cx + 190, cy + 170], fill=(120, 105, 90))
    d.rectangle([0, 600, W, H], fill=(95, 85, 75))
    return im.filter(ImageFilter.GaussianBlur(14))


def calm_band(im: Image.Image, share: float = 0.28) -> Image.Image:
    """Flatten the bottom `share` of a guide to its own average tone with a soft edge: a calm area for captions."""
    top = int(H * (1 - share))
    band = im.crop((0, top, W, H)).resize((1, 1), Image.BOX).getpixel((0, 0))
    out = im.copy()
    ImageDraw.Draw(out).rectangle([0, top, W, H], fill=tuple(int(c * 0.8) for c in band))
    return out.filter(ImageFilter.GaussianBlur(3))


LAYOUTS: Dict[str, Callable[[int], Image.Image]] = {"mountains": mountains, "horizon": horizon, "layered_ridges": layered_ridges, "forest_path": forest_path, "dunes": dunes, "center_object": center_object}
