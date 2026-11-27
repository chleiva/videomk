#!/usr/bin/env python3
"""Render the vector-character prototype: four rigged cartoon kids walk through a seamless vector park, meet a butterfly and one of them explains a fact (docs/VECTOR_SCENES.md).

  AWS_PROFILE=qa python backend/scripts/vector_character_demo.py out.mp4 [--lang en|es] [--size 1920x1080] [--window 7.0,13.0] [--fps 30] [--no-audio]

* Narration: Polly (QA account, a few cents), one voice per child, cached as WAV in --cache so a re-run costs nothing. The speaking child's mouth follows the audio level.
* Scene: native SVG layers written here (sky, clouds, hills, trees, ground with the path, foreground tufts), tiled sideways, rasterised once at the output size with resvg.
* Feet: the background ground layer moves at the speed g; each child's walk cycle is derived from g (engine.vector_character.walk_period / walk_feet), so planted feet do not slide.
Needs ffmpeg on PATH, resvg-py, Pillow, numpy. Offline demo (not a planner scene yet).
"""
import argparse
import io
import math
import os
import random
import subprocess
import sys
import time
import wave
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")

from engine import vector_character as vc  # noqa: E402
from engine.audio import SR  # noqa: E402

FONT = os.path.join(HERE, "..", "lambdas", "engine", "assets", "fonts", "Inter-SemiBold.ttf")
MUSIC = os.path.join(HERE, "..", "music-draft", "playful-kids.mp3")
INK = "#2a2438"
KIDS = [  # id, x (share of the width), size, walk phase, voice EN, voice ES
    ("mia", 0.19, 1.00, 0.4, "Ruth", "Lupe"),
    ("leo", 0.39, 0.93, 2.3, "Matthew", "Pedro"),
    ("nora", 0.61, 0.97, 4.1, "Danielle", "Lucia"),
    ("sam", 0.81, 1.04, 5.6, "Stephen", "Sergio"),
]
LINES = {
    "en": [(0, "Four friends are walking home through the park."), (1, "Look! A monarch butterfly!"), (0, "It's beautiful!"),
           (2, "Did you know a monarch can fly four thousand kilometres every year?"), (3, "And it weighs less than one gram!"), (2, "They fly all the way to Mexico for the winter."), (1, "Wow! Bye, butterfly!")],
    "es": [(0, "Cuatro amigos caminan por el parque."), (1, "¡Mira! ¡Una mariposa monarca!"), (0, "¡Qué bonita!"),
           (2, "¿Sabías que una mariposa monarca puede volar cuatro mil kilómetros cada año?"), (3, "¡Y pesa menos de un gramo!"), (2, "¡Vuelan hasta México para pasar el invierno!"), (1, "¡Guau! ¡Adiós, mariposa!")],
}
CARD = {"en": ("Monarch butterfly", "4,000 km", "migration every year", "< 1 g", "weight"), "es": ("Mariposa monarca", "4.000 km", "de migración al año", "< 1 g", "de peso")}


# ----------------------------------------------------------------------------- narration
def synth_lines(lang: str, cache: str) -> List[Tuple[int, str, np.ndarray]]:
    from engine import tts

    os.makedirs(cache, exist_ok=True)
    prov = None
    out = []
    for i, (k, text) in enumerate(LINES[lang]):
        path = os.path.join(cache, f"{lang}_{i}.wav")
        if os.path.exists(path):
            with wave.open(path, "rb") as w:
                a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        else:
            prov = prov or tts.get_provider("polly", cfg={"region": os.environ.get("POLLY_REGION", "us-east-1"), "engine": "generative"})
            voice = KIDS[k][4 if lang == "en" else 5]
            a = tts.synth_beat(prov, text, voice=voice)
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
            print(f"polly {voice}: {len(text)} chars")
        out.append((k, text, a))
    return out


def timeline(lines: List[Tuple[int, str, np.ndarray]]) -> Dict[str, Any]:
    d = [len(a) / SR for _, _, a in lines]
    t = [1.6]
    gaps = [1.1, 0.45, 0.5, 0.35, 0.55, 0.7]
    for i in range(1, len(lines)):
        t.append(t[-1] + d[i - 1] + gaps[i - 1])
    stop_at = t[1] - 0.5                     # the children begin to slow just before "Look!"
    return {"start": t, "dur": d, "stop_at": stop_at, "stop_len": 1.0, "total": t[-1] + d[-1] + 1.6}


# ----------------------------------------------------------------------------- the park (native SVG, tiles of 1920 x 1080 that wrap sideways)
TW, TH = 1920, 1080


def _svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{TW}" height="{TH}" viewBox="0 0 {TW} {TH}">{body}</svg>'


def _wrap(items: List[Tuple[float, str]], span: float = 400.0) -> str:
    """Draw each item at x and x +- TW when it is near a tile edge so the layer tiles seamlessly."""
    out = []
    for x, frag in items:
        for off in (-TW, 0, TW):
            if -span < x + off < TW + span:
                out.append(f'<g transform="translate({x + off:.1f},0)">{frag}</g>')
    return "".join(out)


def cloud(cx: float, cy: float, s: float) -> str:
    c = [(0, 0, 60), (62, -18, 74), (128, 4, 56), (-58, 12, 46), (176, 24, 40)]
    circles = "".join(f'<circle cx="{cx + dx * s:.1f}" cy="{cy + dy * s:.1f}" r="{r * s:.1f}"' for dx, dy, r in c)
    parts = [f"<circle{k}" for k in circles.split("<circle")[1:]]
    strokes = "".join(p + f' fill="{INK}" stroke="{INK}" stroke-width="{10 * s:.1f}"/>' for p in parts)
    fills = "".join(p + ' fill="#ffffff"/>' for p in parts)
    bx, by, bw, bh = cx - 100 * s, cy + 14 * s, 300 * s, 46 * s
    base_s = f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{bh / 2:.1f}" fill="{INK}" stroke="{INK}" stroke-width="{10 * s:.1f}"/>'
    base_f = f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{bh / 2:.1f}" fill="#ffffff"/>'
    return base_s + strokes + base_f + fills


def layer_sky() -> str:
    return _svg(f'<rect width="{TW}" height="{TH}" fill="#7fcbf2"/><rect y="{TH * 0.30}" width="{TW}" height="{TH}" fill="#a3dbf6"/><rect y="{TH * 0.46}" width="{TW}" height="{TH}" fill="#c9ecfb"/>'
                f'<circle cx="1560" cy="190" r="86" fill="#ffe27a" stroke="{INK}" stroke-width="7"/>')


def layer_clouds() -> str:
    rnd = random.Random(7)
    items = [(x, cloud(0, y, s)) for x, y, s in [(150, 200, 1.0), (650, 120, 0.8), (1150, 260, 1.15), (1650, 140, 0.9)]]
    return _svg(_wrap(items, 500))


def hill_path(base: float, amp: float, cycles: Tuple[int, int], ph: float) -> str:
    pts = []
    for i in range(0, TW + 41, 40):
        a = 2 * math.pi * i / TW
        y = base - amp * (0.6 * math.sin(cycles[0] * a + ph) + 0.4 * math.sin(cycles[1] * a + ph * 1.7))
        pts.append(f"{i},{y:.1f}")
    return "M-30," + str(TH) + " L-30," + pts[0].split(",")[1] + " L" + " L".join(pts) + f" L{TW + 30},{pts[-1].split(chr(44))[1]} L{TW + 30},{TH} Z"


def layer_hills() -> str:
    return _svg(f'<path d="{hill_path(640, 70, (2, 5), 0.6)}" fill="#8fd18f" stroke="{INK}" stroke-width="6"/>'
                f'<path d="{hill_path(700, 55, (3, 7), 2.1)}" fill="#6dbf73" stroke="{INK}" stroke-width="6"/>')


def tree(cx: float, base: float, s: float, col: str, dark: str) -> str:
    trunk = f'<rect x="{-16 * s:.1f}" y="{base - 150 * s:.1f}" width="{32 * s:.1f}" height="{150 * s:.1f}" rx="6" fill="#a8683a" stroke="{INK}" stroke-width="6"/>'
    cs = [(0, base - 215 * s, 88 * s), (-62 * s, base - 168 * s, 62 * s), (64 * s, base - 172 * s, 64 * s), (0, base - 290 * s, 62 * s)]
    strokes = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{INK}" stroke="{INK}" stroke-width="12"/>' for x, y, r in cs)
    fills = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}"/>' for x, y, r in cs)
    shade = f'<circle cx="{26 * s:.1f}" cy="{base - 200 * s:.1f}" r="{44 * s:.1f}" fill="{dark}" opacity="0.55"/>'
    return trunk + strokes + fills + shade


def layer_trees() -> str:
    xs = [120, 420, 760, 1010, 1330, 1640]
    cols = [("#4fae63", "#3a8f4f"), ("#5cbf6f", "#46a05a"), ("#43a35a", "#2f8449")]
    items = [(x, tree(0, 800, 0.85 + 0.12 * ((i * 7) % 3), *cols[i % 3])) for i, x in enumerate(xs)]
    return _svg(_wrap(items, 300))


def layer_ground() -> str:
    rnd = random.Random(11)
    g = (f'<rect x="-30" y="{TH * 0.745}" width="{TW + 60}" height="{TH}" fill="#7bcf6a" stroke="{INK}" stroke-width="6"/>'
         f'<rect x="-30" y="{TH * 0.80}" width="{TW + 60}" height="{TH * 0.145}" fill="#f0d49a" stroke="{INK}" stroke-width="6"/>')
    # fence: pickets with a rail, periodic
    fence = []
    for x in range(30, TW, 128):
        fence.append(f'<rect x="{x}" y="{TH * 0.655}" width="46" height="{TH * 0.105}" rx="8" fill="#ffffff" stroke="{INK}" stroke-width="6"/>')
    rails = f'<rect x="-30" y="{TH * 0.69}" width="{TW + 60}" height="16" fill="#f3f3f3" stroke="{INK}" stroke-width="5"/><rect x="-30" y="{TH * 0.725}" width="{TW + 60}" height="16" fill="#f3f3f3" stroke="{INK}" stroke-width="5"/>'
    pebbles = "".join(f'<ellipse cx="{rnd.randint(0, TW)}" cy="{rnd.randint(int(TH * 0.83), int(TH * 0.93))}" rx="{rnd.randint(9, 20)}" ry="{rnd.randint(5, 9)}" fill="#d9b878" stroke="{INK}" stroke-width="3"/>' for _ in range(26))
    flowers = []
    for x, y, c in [(140, 0.775, "#ff6f91"), (520, 0.77, "#ffd24a"), (900, 0.78, "#ff9f43"), (1260, 0.772, "#ff6f91"), (1700, 0.776, "#b28dff")]:
        flowers.append(f'<g transform="translate({x},{TH * y})"><line x1="0" y1="0" x2="0" y2="40" stroke="{INK}" stroke-width="6"/><circle r="16" fill="{c}" stroke="{INK}" stroke-width="5"/><circle r="6" fill="#fff6c8"/></g>')
    return _svg(g + rails + "".join(fence) + pebbles + "".join(flowers))


def layer_fore() -> str:
    tufts = []
    for x in range(40, TW, 210):
        h = 60 + (x * 7 % 40)
        tufts.append(f'<path d="M{x},{TH} L{x + 14},{TH - h} L{x + 34},{TH - h * 0.45} L{x + 52},{TH - h * 1.1} L{x + 70},{TH - h * 0.4} L{x + 92},{TH - h * 0.9} L{x + 104},{TH} Z" fill="#5fbd5a" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>')
    return _svg("".join(tufts))


# (name, builder, speed share of the ground speed, extra drift px/s at 1080p)
LAYERS = [("sky", layer_sky, 0.0, 0.0), ("clouds", layer_clouds, 0.02, 6.0), ("hills", layer_hills, 0.08, 0.0), ("trees", layer_trees, 0.30, 0.0), ("ground", layer_ground, 1.0, 0.0), ("fore", layer_fore, 1.3, 0.0)]


class Park:
    def __init__(self, W: int, H: int):
        import resvg_py

        self.W, self.H = W, H
        self.strips: Dict[str, Image.Image] = {}
        for name, build, _, _ in LAYERS:
            png = resvg_py.svg_to_bytes(svg_string=build(), width=W, height=H)
            tile = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
            strip = Image.new("RGBA", (W * 2, H))
            strip.paste(tile, (0, 0))
            strip.paste(tile, (W, 0))
            self.strips[name] = strip

    def layer(self, name: str, dist: float, speed: float, drift: float, t: float) -> Image.Image:
        off = (dist * speed + drift * t) % self.W
        return self.strips[name].transform((self.W, self.H), Image.AFFINE, (1, 0, off, 0, 1, 0), Image.BILINEAR)


def butterfly_frame(size: int, flap: float) -> Image.Image:
    import resvg_py

    wing = abs(math.cos(flap)) * 0.88 + 0.12
    def w(sign: int) -> str:
        sx = sign * wing
        return (f'<g transform="translate(100,100) scale({sx:.3f},1)"><path d="M0,0 C10,-70 70,-90 86,-48 C96,-20 60,-4 0,0 Z" fill="#ff8a1f" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>'
                f'<path d="M0,2 C20,10 70,18 66,58 C60,88 18,70 0,2 Z" fill="#ff9d3d" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>'
                f'<circle cx="62" cy="-48" r="7" fill="#fff"/><circle cx="48" cy="46" r="6" fill="#fff"/></g>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">{w(-1)}{w(1)}'
           f'<ellipse cx="100" cy="100" rx="7" ry="30" fill="{INK}"/><path d="M98,72 Q88,50 80,46 M102,72 Q112,50 120,46" stroke="{INK}" stroke-width="4" fill="none" stroke-linecap="round"/></svg>')
    png = resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


# ----------------------------------------------------------------------------- overlays (captions, fact card)
def font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, px)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, maxw: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + [cur]


def caption(img: Image.Image, text: str, alpha: float) -> None:
    W, H = img.size
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = font(round(H * 0.037))
    lines = wrap_text(d, text, f, int(W * 0.78))
    lh = round(H * 0.052)
    w = max(d.textlength(l, font=f) for l in lines) + H * 0.05
    h = lh * len(lines) + H * 0.035
    x0, y0 = (W - w) / 2, H * 0.935 - h
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=H * 0.03, fill=(18, 16, 36, int(170 * alpha)))
    for i, l in enumerate(lines):
        d.text((W / 2, y0 + H * 0.017 + lh * i + lh / 2), l, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="mm")
    img.alpha_composite(ov)


def fact_card(img: Image.Image, lang: str, alpha: float) -> None:
    W, H = img.size
    t, n1, l1, n2, l2 = CARD[lang]
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    w, h = W * 0.25, H * 0.27
    x0, y0 = W * 0.715, H * 0.02 + (1 - alpha) * -H * 0.02
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=H * 0.035, fill=(255, 255, 255, int(235 * alpha)), outline=(42, 36, 56, int(255 * alpha)), width=max(3, H // 200))
    d.text((x0 + w * 0.07, y0 + h * 0.12), t, font=font(round(H * 0.034)), fill=(106, 63, 196, int(255 * alpha)), anchor="lm")
    d.text((x0 + w * 0.07, y0 + h * 0.35), n1, font=font(round(H * 0.075)), fill=(42, 36, 56, int(255 * alpha)), anchor="lm")
    d.text((x0 + w * 0.07, y0 + h * 0.53), l1, font=font(round(H * 0.026)), fill=(90, 86, 110, int(255 * alpha)), anchor="lm")
    d.text((x0 + w * 0.07, y0 + h * 0.70), n2, font=font(round(H * 0.075)), fill=(42, 36, 56, int(255 * alpha)), anchor="lm")
    d.text((x0 + w * 0.07 + 0, y0 + h * 0.87), l2, font=font(round(H * 0.026)), fill=(90, 86, 110, int(255 * alpha)), anchor="lm")
    img.alpha_composite(ov)


def ramp(t: float, a: float, b: float) -> float:
    return vc._smooth((t - a) / max(b - a, 1e-6))


# ----------------------------------------------------------------------------- the story
class Story:
    def __init__(self, lang: str, W: int, H: int, fps: int, cache: str):
        self.lang, self.W, self.H, self.fps = lang, W, H, fps
        self.S = W / 1920.0
        self.lines = synth_lines(lang, cache)
        self.tl = timeline(self.lines)
        self.park = Park(W, H)
        self.ppu = 2.15 * self.S
        self.chars = {k[0]: vc.load(k[0], self.ppu, k[2]) for k in KIDS}
        self.env = [vc.speech_envelope(a, SR, fps) for _, _, a in self.lines]
        # ground speed (px/s): 237 px/s at 1080p gives a 0.85 s cycle for a child of size 1.0
        self.g0 = 268.0 * self.S
        self.stride_u = 0.5 * (vc.ULEG_U * (1 - vc.OVERLAP) + vc.LLEG_U)
        self.mouth_prev = ["closed"] * 4
        self._dist_cache: Dict[int, float] = {}

    # ground speed profile and the distance travelled (closed form: smoothstep integral)
    def g(self, t: float) -> float:
        a, L = self.tl["stop_at"], self.tl["stop_len"]
        return self.g0 * (1 - vc._smooth((t - a) / L))

    def dist(self, t: float) -> float:
        a, L = self.tl["stop_at"], self.tl["stop_len"]
        if t <= a:
            return self.g0 * t
        u = min(1.0, (t - a) / L)
        # integral of 1 - smoothstep(u) over the ramp: u - (u^3 - u^4/2)
        return self.g0 * (a + L * (u - (u ** 3 - u ** 4 / 2))) + (self.g0 * (t - a - L) * 0 if t < a + L else 0.0)

    def speaker(self, t: float) -> Tuple[int, int, float]:
        """-> (line index, kid index, speech level) of whoever is talking at t, or (-1, -1, 0)."""
        for i, (k, _, a) in enumerate(self.lines):
            t0 = self.tl["start"][i]
            if t0 <= t < t0 + self.tl["dur"][i]:
                f = int((t - t0) * self.fps)
                e = self.env[i]
                return i, k, float(e[min(f, len(e) - 1)])
        return -1, -1, 0.0

    def butterfly(self, t: float) -> Tuple[float, float, float]:
        """-> (x, y, visibility) in shares of the frame."""
        t1 = self.tl["start"][1]
        tend = self.tl["start"][-1] + 1.3
        if t < t1 - 3.0:
            return (1.2, 0.3, 0.0)
        u = ramp(t, t1 - 3.0, t1 + 1.2)               # flies in from the right to hover above the group
        x = 1.15 + (0.58 - 1.15) * u + 0.05 * math.sin(t * 1.7)
        y = 0.24 + 0.05 * math.sin(t * 2.3) + 0.03 * math.sin(t * 5.1) - 0.0 * u
        if t > tend - 1.5:                             # leaves at the end
            v = ramp(t, tend - 1.5, tend + 1.8)
            x = x + (1.3 - x) * v
            y = y - 0.15 * v
        return (x, y, 1.0)

    def pose(self, ki: int, t: float) -> Dict[str, Any]:
        cid, _, size, ph0, _, _ = KIDS[ki]
        D = self.stride_u * 0.9 * size                       # stride of this child in units (smaller kids take smaller steps)
        hip_h0 = vc.HIP_H0
        walk_w = 1 - vc._smooth((t - self.tl["stop_at"] - 0.1) / (self.tl["stop_len"] * 0.8))     # 1 walking .. 0 standing
        dist_u = self.dist(t) / (self.ppu * size)             # distance in this child's own units
        phase = math.pi * dist_u / D + ph0
        bob = 1.6 * (1 - math.cos(2 * phase)) / 2
        hip_h = hip_h0 - bob * walk_w - 0.6 * math.sin(2 * math.pi * t / 3.1 + ki) * (1 - walk_w)
        fa, fb = vc.walk_feet(phase, D, hip_h, 11.0)
        stand = (0.0, hip_h)
        feet = (_lerp2(stand, fa, walk_w), _lerp2(stand, fb, walk_w))
        # arms: walking swing, then idle; Mia waves at the end, Nora points while she explains, everyone waves at the end
        arms = [vc.arm_angles("walk", t, phase, 0, walk_w), vc.arm_angles("walk", t, phase, 1, walk_w)]
        idle = [vc.arm_angles("idle", t, 0, 0), vc.arm_angles("idle", t, 0, 1)]
        arms = [_lerp2(idle[i], arms[i], walk_w) for i in range(2)]
        t3, t4 = self.tl["start"][3], self.tl["start"][-1]
        if cid == "nora":
            w = ramp(t, t3 - 0.1, t3 + 0.5) * (1 - ramp(t, t3 + self.tl["dur"][3] + 0.1, t3 + self.tl["dur"][3] + 0.6))
            arms[1] = _lerp2(arms[1], vc.arm_angles("point", t), w)
        wv = ramp(t, t4 - 0.1, t4 + 0.4) * (0.0 if t > self.tl["total"] else 1.0)
        if wv > 0:
            tt = t - t4 + ki * 0.35
            arms[1] = _lerp2(arms[1], vc.arm_angles("wave", tt), wv)
        # looking at the butterfly once it is near
        bx, by, vis = self.butterfly(t)
        look_w = ramp(t, self.tl["start"][1] - 0.6, self.tl["start"][1] + 0.4) * (1 - ramp(t, t4 - 0.3, t4 + 0.5))
        kx = KIDS[ki][1]
        dxl = max(-1.0, min(1.0, (bx - kx) * 3))
        pose: Dict[str, Any] = {"feet": feet, "hip_h": hip_h, "arms": tuple(arms),
                                "tilt": 1.2 * math.sin(2 * phase) * walk_w + 0.6 * math.sin(2 * math.pi * t / 3.1 + ki) * (1 - walk_w),
                                "head_tilt": -3.0 * math.sin(2 * phase - 0.8) * walk_w + look_w * (6.0 * dxl),
                                "head_dy": 1.2 * bob * 0.5 + look_w * 3.0,
                                "look": (look_w * 4.0 * dxl, -look_w * 5.5),
                                "blink": vc.blink(t, 0.7 * ki + 0.4, every=3.1 + 0.4 * ki)}
        li, sk, level = self.speaker(t)
        if sk == ki:
            self.mouth_prev[ki] = vc.mouth_for(level, self.mouth_prev[ki])
            pose["mouth"] = self.mouth_prev[ki]
        else:
            self.mouth_prev[ki] = "closed"
            pose["mouth"] = "closed"
        return pose

    def frame(self, t: float) -> Image.Image:
        W, H, S = self.W, self.H, self.S
        dist, g = self.dist(t), self.g(t)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        for name, _, speed, drift in LAYERS:
            if name == "fore":
                continue
            img.alpha_composite(self.park.layer(name, dist, speed, drift * S, t))
        ground_y = H * 0.835
        order = sorted(range(4), key=lambda i: KIDS[i][2])
        # butterfly sits behind the children's heads but in front of the trees
        bx, by, vis = self.butterfly(t)
        if vis > 0:
            bsz = round(210 * S)
            b = butterfly_frame(bsz, t * 2 * math.pi * 3.4)
            img.alpha_composite(b, (round(bx * W - bsz / 2), round(by * H - bsz / 2)))
        for ki in order:
            self.chars[KIDS[ki][0]].draw(img, KIDS[ki][1] * W, ground_y, self.pose(ki, t))
        img.alpha_composite(self.park.layer("fore", dist, 1.3, 0.0, t))
        # overlays
        i, _, _ = self.speaker(t)
        if i >= 0:
            t0, dur = self.tl["start"][i], self.tl["dur"][i]
            a = ramp(t, t0 - 0.05, t0 + 0.2) * (1 - ramp(t, t0 + dur - 0.1, t0 + dur + 0.2))
            if a > 0.01:
                caption(img, self.lines[i][1], a)
        t3, t4 = self.tl["start"][3], self.tl["start"][4]
        a = ramp(t, t3 + 0.2, t3 + 0.8) * (1 - ramp(t, t4 + self.tl["dur"][4] + 0.5, t4 + self.tl["dur"][4] + 1.1))
        if a > 0.01:
            fact_card(img, self.lang, a)
        fade = ramp(t, 0, 0.5) * (1 - ramp(t, self.tl["total"] - 0.7, self.tl["total"]))
        if fade < 1:
            black = Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade))))
            img.alpha_composite(black)
        return img.convert("RGB")

    def audio(self, total: float) -> np.ndarray:
        out = np.zeros(int(total * SR) + SR, dtype=np.float32)
        for i, (_, _, a) in enumerate(self.lines):
            s = int(self.tl["start"][i] * SR)
            out[s:s + len(a)] += a
        return out


def _lerp2(a: Tuple[float, float], b: Tuple[float, float], w: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)


def write_wav(path: str, a: np.ndarray) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--lang", default="en", choices=["en", "es"])
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--window", default="")
    ap.add_argument("--cache", default=os.path.join(HERE, "..", "..", ".vchar_cache"))
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--stills", default="", help="comma separated times: write PNGs next to the output instead of a video")
    a = ap.parse_args()
    W, H = (int(x) for x in a.size.lower().split("x"))
    t0 = time.time()
    st = Story(a.lang, W, H, a.fps, a.cache)
    print(f"load {time.time() - t0:.1f}s; total {st.tl['total']:.1f}s; starts {[round(x, 2) for x in st.tl['start']]}; stop at {st.tl['stop_at']:.2f}")
    if a.stills:
        for s in a.stills.split(","):
            st.frame(float(s)).save(f"{os.path.splitext(a.out)[0]}_{float(s):05.2f}.png")
        return 0
    ws, we = (0.0, st.tl["total"])
    if a.window:
        ws, we = (float(x) for x in a.window.split(","))
    tmp = a.out + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "17", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    n = int((we - ws) * a.fps)
    t1 = time.time()
    for i in range(n):
        p.stdin.write(st.frame(ws + i / a.fps).tobytes())
    p.stdin.close()
    p.wait()
    ms = (time.time() - t1) / n * 1000
    print(f"{n} frames, {ms:.0f} ms/frame")
    if a.no_audio:
        os.replace(tmp, a.out)
        return 0
    wav = a.out + ".voice.wav"
    write_wav(wav, st.audio(max(we, st.tl["total"])))
    ss = ["-ss", f"{ws:.3f}", "-t", f"{we - ws:.3f}"]
    fade_out = max(0.0, (we - ws) - 1.0)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", tmp, *ss, "-i", wav, "-stream_loop", "-1", "-i", MUSIC, "-filter_complex",
           f"[2:a]atrim=0:{we - ws:.3f},volume=0.13,afade=t=in:d=0.6,afade=t=out:st={fade_out:.2f}:d=1.0[m];[1:a]volume=1.0[v];[v][m]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out]
    subprocess.run(cmd, check=True)
    os.remove(tmp)
    os.remove(wav)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
