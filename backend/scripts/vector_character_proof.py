#!/usr/bin/env python3
"""Animation PROOF REEL for the rigged vector characters (docs/CHARACTER_ANIMATION_PROOF.md). Zero spend: CPU only, cached Polly lines, no model calls.

  python backend/scripts/vector_character_proof.py out.mp4 --cache <dir with en_0..6.wav> [--fps 30] [--only idle,wave] [--stills 1.0,2.0]

One clip per action, a plain neutral background so the character is judged alone, a label burned in (label only for the proof). Actions that the rig can do better with secondary
motion are shown BEFORE (original rig: smoothstep keyframes, metronome blink, static body) next to AFTER (spring follow-through, breathing, weight shift, natural blinks,
stress-driven nods and hand beats, mouth leading the sound). Actions that cannot be done say so on a card instead of faking it.
"""
import argparse
import math
import os
import subprocess
import sys
import wave
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
sys.path.insert(0, HERE)

from engine import vector_character as vc  # noqa: E402
from engine.audio import SR  # noqa: E402

FONT = os.path.join(HERE, "..", "lambdas", "engine", "assets", "fonts", "Inter-SemiBold.ttf")
W, H = 1920, 1080
BG_TOP, BG_BOT = (238, 240, 247), (219, 224, 238)
INK = (42, 36, 56)
REACH = vc.ULEG_U * (1 - vc.OVERLAP) + vc.LLEG_U
STRIDE_U = 0.5 * REACH
G_UNITS = 125.0                          # ground speed in units/s: one cycle = 2 * D / G = 0.74 s for size 1.0
LINES = {0: ("mia", "Four friends are walking home through the park."), 1: ("leo", "Look! A monarch butterfly!"), 2: ("mia", "It's beautiful!"),
         3: ("nora", "Did you know a monarch can fly four thousand kilometres every year?"), 4: ("sam", "And it weighs less than one gram!"),
         5: ("nora", "They fly all the way to Mexico for the winter."), 6: ("leo", "Wow! Bye, butterfly!")}


def font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, px)


# ----------------------------------------------------------------------------- audio
class Voice:
    def __init__(self, cache: str, idx: int, fps: int):
        with wave.open(os.path.join(cache, f"en_{idx}.wav"), "rb") as w:
            assert w.getframerate() == SR, w.getframerate()
            self.a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        self.dur = len(self.a) / SR
        self.env = vc.speech_envelope(self.a, SR, fps)
        self.fps = fps
        self.kid = LINES[idx][0]
        self.text = LINES[idx][1]
        # the original rig's mouth: stateful hysteresis, computed up front so the clip stays a pure function of t
        prev, seq = "closed", []
        for lv in self.env:
            prev = vc.mouth_for(float(lv), prev)
            seq.append(prev)
        self.mouth_before = seq
        self.mouth_after = vc.mouth_track(self.env, lead=1, min_hold=2)
        self.stress = vc.stress_events(self.env, fps)

    def level(self, t: float) -> float:
        i = int(t * self.fps)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0

    def mouth(self, mode: str, t: float) -> str:
        seq = self.mouth_before if mode == "before" else self.mouth_after
        i = int(t * self.fps)
        return seq[i] if 0 <= i < len(seq) else "closed"


# ----------------------------------------------------------------------------- pose helpers
def kf(mode: str, t: float, keys: Sequence[Tuple[float, Any]], freq: float = 3.4, damp: float = 0.5) -> Any:
    return vc.ease_keys(t, keys) if mode == "before" else vc.spring_keys(t, keys, freq, damp)


def stand_h(mode: str) -> float:
    return vc.HIP_H0 if mode == "before" else 0.99 * REACH       # a nearly straight leg: the knee step shows less than in the crouch of the original stance


def lerp2(a: Tuple[float, float], b: Tuple[float, float], w: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)


def idle_arms(t: float, seed: float = 0.0) -> List[Tuple[float, float]]:
    return [vc.arm_angles("idle", t, 0, 0), vc.arm_angles("idle", t, 0, 1)]


def idle(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    """Standing at rest. BEFORE: what the story demo did (a sine bob, metronome blink). AFTER: breathing, weight shift with the feet staying planted, arms and head that trail the body."""
    if mode == "before":
        return {"hip_h": vc.HIP_H0 - 0.6 * math.sin(2 * math.pi * t / 3.1 + seed), "tilt": 0.6 * math.sin(2 * math.pi * t / 3.1 + seed), "arms": tuple(idle_arms(t)),
                "blink": vc.blink(t, 0.7 * seed + 0.4, every=3.1 + 0.4 * seed)}
    tsy, lift = vc.breath(t, seed=0.13 * seed)
    sway = math.sin(2 * math.pi * (t / 6.4 + 0.2 * seed))
    lag = math.sin(2 * math.pi * ((t - 0.35) / 6.4 + 0.2 * seed))
    dx = 1.7 * sway
    h = stand_h(mode) - 0.35 * (1 - math.cos(2 * math.pi * t / 3.8)) / 2
    a = idle_arms(t)
    arms = ((a[0][0] + 2.4 * lag, a[0][1] + 1.2 * lag), (a[1][0] + 2.4 * lag, a[1][1] - 1.2 * lag))
    return {"hip_h": h, "dx": dx, "feet": ((-dx, h), (-dx, h)), "tilt": 0.55 * sway, "torso_sy": tsy, "head_dy": lift,
            "head_tilt": 1.2 * lag + 0.8 * math.sin(2 * math.pi * t / 9.1 + seed), "arms": arms,
            "look": (1.4 * math.sin(2 * math.pi * t / 7.3 + seed), 0.7 * math.sin(2 * math.pi * t / 5.1)), "blink": vc.blink_natural(t, 0.37 * seed + 0.5)}


def with_idle(mode: str, t: float, seed: int, **over: Any) -> Dict[str, Any]:
    p = idle(mode, t, seed)
    p.update({k: v for k, v in over.items() if v is not None})
    return p


def nod_tilt(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    """Two nods (yes), then a curious head tilt."""
    dy = kf(mode, t, [(0, 0.0), (0.45, -2.6), (0.85, 0.4), (1.2, -2.6), (1.6, 0.0)], 3.8, 0.55)
    tilt = kf(mode, t, [(0, 0.0), (2.0, 9.0), (3.1, 0.0)], 3.0, 0.5)
    p = with_idle(mode, t, seed)
    p["head_dy"] = p.get("head_dy", 0.0) + dy
    p["head_tilt"] = p.get("head_tilt", 0.0) + tilt
    if mode == "after":
        p["head_sy"] = 1.0 - 0.03 * max(0.0, -dy) / 2.6
        p["tilt"] = p.get("tilt", 0.0) + 0.3 * dy + 0.22 * tilt            # the torso follows a beat later (secondary motion)
        p["look"] = (0.4 * tilt, 0.5 * dy)
    return p


def talking(mode: str, t: float, v: Voice, seed: int = 0, t0: float = 0.0) -> Dict[str, Any]:
    """Speaking. BEFORE: the mouth only. AFTER: the mouth leads the sound, the head nods on stressed syllables, a hand beats with them, the head drifts as people do."""
    lt = t - t0
    p = with_idle(mode, t, seed)
    p["mouth"] = v.mouth(mode, lt) if 0 <= lt < v.dur else "closed"
    if mode == "after" and 0 <= lt < v.dur + 0.6:
        dy_keys, arm_keys, hr = [(-9.0, 0.0)], [(-9.0, (4.0, 6.0))], 0
        for k, e in enumerate(v.stress):
            dy_keys += [(e - 0.06, -1.8), (e + 0.28, 0.0)]
            amp = 1.0 if k % 2 == 0 else 0.7
            arm_keys += [(e - 0.16, (4.0 + 20 * amp, 6.0 + 62 * amp)), (e + 0.55, (4.0, 6.0))]      # the forearm comes UP into a presenting gesture, then rests
        dy = vc.spring_keys(lt, dy_keys, 4.2, 0.55)
        a1 = vc.spring_keys(lt, arm_keys, 3.0, 0.55)
        p["head_dy"] = p.get("head_dy", 0.0) + dy
        p["head_tilt"] = p.get("head_tilt", 0.0) + 2.0 * math.sin(2 * math.pi * lt / 2.4 + seed) * min(1.0, v.level(lt) * 2)
        arms = list(p["arms"])
        arms[1] = (a1[0], a1[1])
        p["arms"] = tuple(arms)
        p["head_sy"] = 1.0 - 0.02 * max(0.0, -dy) / 1.8
    return p


def wave_pose(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    p = with_idle(mode, t, seed)
    up, down = (152.0, 0.0), (4.0, 6.0)
    sh = kf(mode, t, [(0, down[0]), (0.35, 152.0), (2.85, 152.0), (3.25, 4.0)], 2.6, 0.45)
    w_in, w_out = vc._smooth((t - 0.5) / 0.35), 1 - vc._smooth((t - 2.7) / 0.4)
    if mode == "before":
        s, e = vc.arm_angles("wave", t - 0.4)
        arm = lerp2(down, (s, e), vc._smooth((t - 0.2) / 0.4) * (1 - vc._smooth((t - 2.9) / 0.4)))
    else:
        amp = 30.0 * w_in * w_out
        env = 1.0 + 0.0
        arm = (sh + 5.0 * math.sin(2 * math.pi * 0.9 * t) * w_in * w_out, 6.0 + 24.0 * w_in * w_out + amp * math.sin(2 * math.pi * 3.2 * (t - 0.6)))
        p["tilt"] = p.get("tilt", 0.0) - 1.6 * vc._smooth((t - 0.3) / 0.5) * w_out
        p["head_tilt"] = p.get("head_tilt", 0.0) + 5.0 * vc._smooth((t - 0.3) / 0.5) * w_out
        p["dx"] = -1.4 * vc._smooth((t - 0.3) / 0.5) * w_out
        h = p["hip_h"]
        p["feet"] = ((-p["dx"], h), (-p["dx"], h))
    arms = list(p["arms"])
    arms[1] = arm
    p["arms"] = tuple(arms)
    return p


def point(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    p = with_idle(mode, t, seed)
    sh = kf(mode, t, [(0, 4.0), (0.4, 128.0), (2.5, 128.0), (2.95, 4.0)], 2.8, 0.5)
    bend = kf(mode, t, [(0, 6.0), (0.4, 4.0), (2.5, 4.0), (2.95, 6.0)], 2.8, 0.5)
    arms = list(p["arms"])
    arms[1] = (sh, bend)
    p["arms"] = tuple(arms)
    if mode == "after":
        lean = vc._smooth((t - 0.3) / 0.5) * (1 - vc._smooth((t - 2.5) / 0.5))
        p["tilt"] = p.get("tilt", 0.0) + 2.4 * lean
        p["head_tilt"] = p.get("head_tilt", 0.0) + 3.0 * lean
        p["look"] = (4.5 * lean, -0.5 * lean)
    return p


def shrug(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    p = with_idle(mode, t, seed)
    r = kf(mode, t, [(0, (4.0, 6.0)), (0.4, (40.0, 84.0)), (1.9, (40.0, 84.0)), (2.35, (4.0, 6.0))], 3.2, 0.5)
    k = kf(mode, t, [(0, 0.0), (0.4, 1.0), (1.9, 1.0), (2.35, 0.0)], 3.2, 0.5)
    p["arms"] = ((-r[0], -r[1]), (r[0], r[1]))
    p["head_dy"] = p.get("head_dy", 0.0) - 2.4 * k
    p["head_tilt"] = p.get("head_tilt", 0.0) + 7.0 * k
    if mode == "after":
        p["head_sy"] = 1.0 - 0.025 * max(0.0, k)
        p["torso_sy"] = p.get("torso_sy", 1.0) - 0.028 * max(0.0, k)       # shoulders rise: the torso is squashed a little (no shoulder bone in the art)
        p["look"] = (0.0, 1.2 * k)
    return p


def surprise(mode: str, t: float, seed: int = 0) -> Dict[str, Any]:
    p = with_idle(mode, t, seed)
    r = kf(mode, t, [(0, (4.0, 6.0)), (0.5, (112.0, 26.0)), (2.2, (112.0, 26.0)), (2.7, (4.0, 6.0))], 3.4, 0.4)
    k = kf(mode, t, [(0, 0.0), (0.5, 1.0), (2.2, 1.0), (2.7, 0.0)], 3.4, 0.45)
    hop = kf(mode, t, [(0, 0.0), (0.45, 3.2), (0.8, 0.0)], 4.5, 0.4)
    h = stand_h(mode)
    p["arms"] = ((-r[0], -r[1]), (r[0], r[1]))
    p["hip_h"] = h + hop
    p["feet"] = ((0.0, h + hop - 1.3 * max(0.0, hop)), (0.0, h + hop - 1.3 * max(0.0, hop)))
    p["dx"] = 0.0
    p["head_dy"] = 2.4 * k
    p["head_tilt"] = -5.0 * k
    p["mouth"] = "wide" if k > 0.35 else "closed"
    if mode == "after":
        p["eyes_scale"] = 1.0 + 0.16 * max(0.0, min(1.2, k))
        p["blink"] = False
        p["torso_sy"] = 1.0 + 0.02 * max(0.0, hop) / 3.2
        p["look"] = (0.0, -1.5 * k)
    else:
        p["blink"] = False
    return p


def walk_pose(mode: str, t: float, phase: float, w: float = 1.0, size: float = 1.0, seed: int = 0) -> Dict[str, Any]:
    """Walking (w = 1) blended into standing (w = 0). The feet are planted: the ground (or the body) must move at G_UNITS."""
    D = STRIDE_U * 0.9 * size
    h0 = vc.HIP_H0 + (stand_h(mode) - vc.HIP_H0) * (1 - w)        # a straighter stance when standing, the original height when walking (the stride must stay within the leg's reach)
    bob = 1.6 * (1 - math.cos(2 * phase)) / 2
    h = h0 - bob * w
    fa, fb = vc.walk_feet(phase, D, h, 11.0)
    dx = 0.0 if mode == "before" else 1.1 * math.sin(phase) * w
    stand = (0.0, h)
    feet = (lerp2(stand, (fa[0] - dx, fa[1]), w), lerp2(stand, (fb[0] - dx, fb[1]), w))
    if mode == "before":
        walk = [vc.arm_angles("walk", t, phase, 0, w), vc.arm_angles("walk", t, phase, 1, w)]
    else:
        def arm(side: int) -> Tuple[float, float]:
            pp = phase + math.pi * side
            return (w * 24.0 * math.sin(pp), w * (8.0 + 12.0 * (1 + math.sin(pp - 0.9)) / 2))     # the forearm trails the upper arm: follow-through
        walk = [arm(0), arm(1)]
    idl = idle_arms(t)
    arms = [lerp2(idl[i], walk[i], w) for i in range(2)]
    p = {"feet": feet, "hip_h": h, "arms": tuple(arms), "dx": dx,
         "tilt": 1.2 * math.sin(2 * phase) * w + 0.5 * math.sin(2 * math.pi * t / 3.1 + seed) * (1 - w),
         "head_tilt": -3.0 * math.sin(2 * phase - 0.8) * w, "head_dy": 0.6 * bob,
         "blink": vc.blink(t, 0.4 + seed, every=3.1) if mode == "before" else vc.blink_natural(t, 0.5 + 0.37 * seed)}
    if mode == "after":
        p["torso_sy"] = 1.0 - 0.012 * (1 + math.cos(2 * phase)) / 2 * w
    return p


# ----------------------------------------------------------------------------- stages and overlays
def stage(floor_off: float = 0.0, ticks: bool = True, ground_y: float = H * 0.86) -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(round(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * k) for i in range(3)))
    d.rectangle([0, ground_y, W, H], fill=(205, 211, 228))
    d.line([(0, ground_y), (W, ground_y)], fill=(150, 156, 180), width=3)
    if ticks:
        off = floor_off % 150
        for k in range(-2, W // 150 + 3):
            xx = k * 150 - off
            d.line([(xx, ground_y + 6), (xx - 22, ground_y + 40)], fill=(150, 156, 180), width=4)
    return img


def label(img: Image.Image, text: str, sub: str = "") -> None:
    d = ImageDraw.Draw(img, "RGBA")
    f, g = font(34), font(24)
    w = max(d.textlength(text, font=f), d.textlength(sub, font=g)) + 44
    h = 62 + (36 if sub else 0)
    d.rounded_rectangle([28, 24, 28 + w, 24 + h], radius=18, fill=(20, 18, 36, 215))
    d.text((50, 46), text, font=f, fill=(255, 255, 255))
    if sub:
        d.text((50, 92), sub, font=g, fill=(190, 196, 230))


def tag(img: Image.Image, x: int, text: str, good: bool) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    f = font(30)
    w = d.textlength(text, font=f) + 40
    col = (46, 125, 82, 235) if good else (150, 60, 60, 235)
    d.rounded_rectangle([x - w / 2, 175, x + w / 2, 175 + 50], radius=14, fill=col)
    d.text((x, 200), text, font=f, fill=(255, 255, 255), anchor="mm")


def card(text: str, sub: str) -> Image.Image:
    img = stage(ticks=False)
    d = ImageDraw.Draw(img)
    d.text((W / 2, H * 0.42), text, font=font(78), fill=INK, anchor="mm")
    d.text((W / 2, H * 0.55), sub, font=font(36), fill=(90, 86, 110), anchor="mm")
    return img


# ----------------------------------------------------------------------------- clips
class Clip:
    def __init__(self, name: str, title: str, sub: str, dur: float, render: Callable[[float, str], Image.Image], both: bool = True, audio: Optional[List[Tuple[float, np.ndarray]]] = None):
        self.name, self.title, self.sub, self.dur, self.render, self.both, self.audio = name, title, sub, dur, render, both, audio or []


PPU = 2.45
GROUND = H * 0.86
TINT = {"before": vc.BACK_TINT, "after": 0.93}     # the far arm is drawn darker for depth; at 0.80 its sleeve shows as a dark box beside the torso


def ld(cid: str, ppu: float, size: float = 1.0, mode: str = "after") -> vc.Character:
    return vc.load(cid, ppu, size, TINT[mode])


def split_clip(single: Callable[[str, float, float], Image.Image]) -> Callable[[float, str], Image.Image]:
    """single(mode, t, cx) -> frame with ONE character centred at cx. BEFORE left, AFTER right."""
    def fn(t: float, which: str) -> Image.Image:
        if which == "after":
            return single("after", t, W / 2)
        a = single("before", t, W * 0.25)
        b = single("after", t, W * 0.75)
        # take the left half of A and right half of B (each stage was drawn with its own character at its own x)
        out = Image.new("RGB", (W, H))
        out.paste(a.crop((0, 0, W // 2, H)), (0, 0))
        out.paste(b.crop((W // 2, 0, W, H)), (W // 2, 0))
        d = ImageDraw.Draw(out)
        d.line([(W // 2, 0), (W // 2, H)], fill=(120, 126, 150), width=3)
        tag(out, W // 4, "BEFORE: original rig", False)
        tag(out, 3 * W // 4, "AFTER: spring + secondary motion", True)
        return out
    return fn


def one_char(cid: str, pose_fn: Callable[[str, float], Dict[str, Any]], ppu: float = PPU, bg: Optional[Callable[[float], Image.Image]] = None, size: float = 1.0
             ) -> Callable[[str, float, float], Image.Image]:
    chars: Dict[Any, vc.Character] = {}

    def fn(mode: str, t: float, cx: float) -> Image.Image:
        if (cid, mode) not in chars:
            chars[(cid, mode)] = ld(cid, ppu, size, mode)
        img = (bg(t) if bg else stage()).convert("RGBA")
        chars[(cid, mode)].draw(img, cx, GROUND, pose_fn(mode, t))
        return img.convert("RGB")
    return fn


def build_clips(cache: str, fps: int) -> List[Clip]:
    V = [Voice(cache, i, fps) for i in range(7)]
    clips: List[Clip] = []

    def add(c: Clip) -> None:
        clips.append(c)

    add(Clip("idle", "1 · Idle: breathing and blink", "no one is ever perfectly still", 3.2, split_clip(one_char("mia", lambda m, t: idle(m, t, 1)))))
    add(Clip("nod", "2 · Head nod and tilt", "same keyframes, linear ease vs spring follow-through", 3.4, split_clip(one_char("leo", lambda m, t: nod_tilt(m, t, 2)))))
    v3 = V[3]
    add(Clip("talk", "3 · Talking with natural pauses", "Polly line, mouth driven by the audio level; AFTER: nods and hand beats on stressed syllables", v3.dur + 0.9,
             split_clip(one_char("nora", lambda m, t: talking(m, t, v3, 3, 0.5))), audio=[(0.5, v3.a)]))
    add(Clip("wave", "4 · Wave", "", 3.4, split_clip(one_char("mia", lambda m, t: wave_pose(m, t, 1)))))
    add(Clip("point", "5 · Point", "the hand is an open hand: 'presenting', not a pointing finger", 3.0, split_clip(one_char("nora", lambda m, t: point(m, t, 3)))))
    add(Clip("shrug", "6 · Shrug", "no shoulder bone in the art: arms out, head sinks, torso squashed", 2.7, split_clip(one_char("leo", lambda m, t: shrug(m, t, 2)))))
    add(Clip("surprise", "7 · Surprise", "no eyebrows in the art: wide eyes, open mouth, head back, arms up, small hop", 2.9, split_clip(one_char("sam", lambda m, t: surprise(m, t, 4)))))
    add(Clip("walkin", "8 · Walk in place (treadmill)", "ground ticks scroll at the foot speed: feet must not skate", 3.0, split_clip(walk_in_place())))
    add(Clip("walkacross", "9 · Walk across", "ticks stay still: planted feet must stay still on them", 4.4, walk_across()))
    add(Clip("turn", "10 · Stop, turn, walk back (paper-doll flip)", "there is no 3/4 view in this art: the turn is a flip", 6.0, stop_turn()))
    add(Clip("sit", "11 · Sit", "NOT SUPPORTED: legs are one front-facing IK pair", 1.6, lambda t, w: card("Sit: not supported", "front-facing cut-out, no side view of torso or thighs; behind a desk is the practical option"), both=False))
    v4, v5 = V[3], V[4]
    add(Clip("two", "12 · Two characters talking in turn", "listener looks, nods, blinks; right one is mirrored to face left", 7.9, two_talk(V), both=False,
             audio=[(0.6, V[3].a), (0.6 + V[3].dur + 0.5, V[4].a)]))
    add(Clip("joints", "13 · Close-up on the joints (magnified)", "defects show here: sleeve edges, knee step, hand", 5.0, joints(), both=False))
    add(Clip("presenter", "14 · Presenter mode (lower third)", "torso static from the hips up: gestures + talking + a text card", 7.0, presenter(V), both=False,
             audio=[(0.4, V[3].a), (0.4 + V[3].dur + 0.55, V[5].a)]))
    add(Clip("scene", "15 · In a scene (vector park)", "two kids walk, one talks, they stop, wave", 8.0, scene(V), both=False,
             audio=[(1.0, V[1].a), (4.6, V[2].a)]))
    return clips


# ----- walking clips
def walk_in_place() -> Callable[[str, float, float], Image.Image]:
    ppu = PPU
    cache: Dict[str, vc.Character] = {}

    def fn(mode: str, t: float, cx: float) -> Image.Image:
        ch = cache.setdefault("mia" + mode, ld("mia", ppu, 1.0, mode))
        D = STRIDE_U * 0.9
        dist_u = G_UNITS * t
        phase = math.pi * dist_u / D + 0.4
        img = stage(floor_off=dist_u * ppu).convert("RGBA")
        ch.draw(img, cx, GROUND, walk_pose(mode, t, phase, 1.0, 1.0, 1))
        return img.convert("RGB")
    return fn


def walk_across() -> Callable[[float, str], Image.Image]:
    ppu = PPU
    cache: Dict[str, vc.Character] = {}

    def fn(t: float, which: str) -> Image.Image:
        ch = cache.setdefault("leo", ld("leo", ppu, 0.93))
        D = STRIDE_U * 0.9 * 0.93
        dist_u = G_UNITS * 0.93 * t
        phase = math.pi * dist_u / D + 2.3
        x = W * 0.12 + dist_u * ppu * 0.93 * 1.0
        img = stage(floor_off=0.0).convert("RGBA")
        ch.draw(img, x, GROUND, walk_pose("after", t, phase, 1.0, 0.93, 2))
        return img.convert("RGB")
    return fn


def stop_turn() -> Callable[[float, str], Image.Image]:
    ppu = PPU
    cache: Dict[str, vc.Character] = {}
    size = 0.97

    def spd(tt: float) -> float:
        """Walking speed share: right until 2.0 s, ramp to a stop by 2.7 s, stand, flip 3.3-3.9 s, stand to 4.3 s, ramp up (leftwards) to full by 4.9 s."""
        if tt < 2.0:
            return 1.0
        if tt < 2.7:
            return 1 - vc._smooth((tt - 2.0) / 0.7)
        if tt < 4.3:
            return 0.0
        return vc._smooth((tt - 4.3) / 0.6)

    def integ(t: float) -> Tuple[float, float]:
        """(signed distance in units, absolute distance in units): right is positive before the flip, left after it."""
        n = max(1, int(t * 200))
        signed = absd = 0.0
        for i in range(n):
            ta = (i + 0.5) * t / n
            v = spd(ta) * G_UNITS * size * (t / n)
            absd += v
            signed += v if ta < 3.6 else -v
        return signed, absd

    def fn(t: float, which: str) -> Image.Image:
        ch = cache.setdefault("nora", ld("nora", ppu, size))
        D = STRIDE_U * 0.9 * size
        signed, absd = integ(t)
        x = W * 0.14 + signed * ppu
        phase = math.pi * absd / D + 4.1
        facing = 1.0 if t < 3.3 else (1.0 - 2 * vc._smooth((t - 3.3) / 0.6) if t < 3.9 else -1.0)
        pose = walk_pose("after", t, phase, spd(t), size, 3)
        img = stage().convert("RGBA")
        ch.draw_turned(img, x, GROUND, pose, facing)
        return img.convert("RGB")
    return fn


def two_talk(V: List[Voice]) -> Callable[[float, str], Image.Image]:
    ppu = PPU * 0.94
    starts = [0.6, 0.6 + V[3].dur + 0.5]
    seq = [(V[3], 0, starts[0]), (V[4], 1, starts[1])]
    cache: Dict[str, vc.Character] = {}

    def fn(t: float, which: str) -> Image.Image:
        a = cache.setdefault("nora", ld("nora", ppu, 0.97))
        b = cache.setdefault("sam", ld("sam", ppu, 1.04))
        img = stage(ticks=False).convert("RGBA")
        poses = [with_idle("after", t, 3), with_idle("after", t, 4)]
        for v, who, t0 in seq:
            lt = t - t0
            if -0.1 <= lt < v.dur + 0.9:
                sp = talking("after", t, v, 3 if who == 0 else 4, t0)
                li = 1 - who
                # listener: looks at the speaker, nods a little after each stress, keeps the idle otherwise
                ls = poses[li]
                dy = vc.spring_keys(lt, [(-9.0, 0.0)] + [k for e in v.stress for k in ((e + 0.18, -1.5), (e + 0.5, 0.0))], 4.0, 0.55)
                ls["head_dy"] = ls.get("head_dy", 0.0) + dy
                ls["look"] = (5.5 if li == 0 else -5.5, 0.0)
                ls["head_tilt"] = ls.get("head_tilt", 0.0) + (3.5 if li == 0 else -3.5) * vc._smooth((lt + 0.1) / 0.4)
                poses[who] = sp
        a.draw(img, W * 0.33, GROUND, poses[0])
        b.draw_turned(img, W * 0.67, GROUND, poses[1], -1.0)
        return img.convert("RGB")
    return fn


def joints() -> Callable[[float, str], Image.Image]:
    big = 6.0
    cache: Dict[str, vc.Character] = {}

    def fn(t: float, which: str) -> Image.Image:
        ch = cache.setdefault("mia", ld("mia", big, 1.0))
        img = Image.new("RGBA", (W, H), (238, 240, 247, 255))
        if t < 2.5:
            pose = wave_pose("after", t + 0.1, 1)
            # centre on the shoulder / elbow / hand of the raised arm
            gy = H / 2 + 175 * big
            ch.draw(img, W * 0.40, gy, pose)
        else:
            tt = t - 2.5
            D = STRIDE_U * 0.9
            phase = math.pi * G_UNITS * tt / D + 0.4
            pose = walk_pose("after", tt, phase, 1.0, 1.0, 1)
            gy = H / 2 + 62 * big
            ch.draw(img, W * 0.5, gy, pose)
        return img.convert("RGB")
    return fn


def presenter(V: List[Voice]) -> Callable[[float, str], Image.Image]:
    ppu = 3.0
    cache: Dict[str, vc.Character] = {}
    starts = [0.4, 0.4 + V[3].dur + 0.55]
    bullets = ["a monarch flies 4,000 km", "every single year", "to Mexico for the winter"]

    def fn(t: float, which: str) -> Image.Image:
        ch = cache.setdefault("nora", ld("nora", ppu, 0.97))
        img = stage(ticks=False).convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([0, 0, W, H], fill=(236, 238, 248, 255))
        d.rectangle([W * 0.46, 0, W, H], fill=(106, 63, 196, 255))
        v = V[3] if t < starts[1] - 0.2 else V[5]
        t0 = starts[0] if v is V[3] else starts[1]
        pose = talking("after", t, v, 3, t0)
        pose["feet"] = ((0.0, pose["hip_h"]),) * 2
        ch.draw(img, W * 0.25, H * 0.92 + 70 * ppu, pose)        # the frame ends just below the waist (hands stay in shot): a presenter behind the lower third
        d.rectangle([0, H * 0.92, W * 0.46, H], fill=(20, 18, 36, 235))
        d.text((W * 0.03, H * 0.96), "Nora · science guide", font=font(40), fill=(255, 255, 255), anchor="lm")
        for i, b in enumerate(bullets):
            a = vc._smooth((t - (0.8 + 1.7 * i)) / 0.4)
            if a > 0.01:
                d.rounded_rectangle([W * 0.52, H * (0.22 + 0.2 * i), W * 0.95, H * (0.22 + 0.2 * i + 0.14)], radius=26, fill=(255, 255, 255, int(235 * a)))
                d.text((W * 0.55, H * (0.22 + 0.2 * i + 0.07)), b, font=font(48), fill=(42, 36, 56, int(255 * a)), anchor="lm")
        return img.convert("RGB")
    return fn


def scene(V: List[Voice]) -> Callable[[float, str], Image.Image]:
    import vector_character_demo as demo

    park = demo.Park(W, H)
    ppu = 2.15
    chars = {"mia": ld("mia", ppu, 1.0), "leo": ld("leo", ppu, 0.93)}
    g_px = G_UNITS * ppu

    def spd(t: float) -> float:
        return 1.0 if t < 3.6 else 1 - vc._smooth((t - 3.6) / 0.8)

    def dist(t: float) -> float:
        n = 400
        return sum(spd(t * i / n) for i in range(n)) * (t / n) * g_px

    def fn(t: float, which: str) -> Image.Image:
        dd = dist(t)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        for name, _, speed, drift in demo.LAYERS:
            if name == "fore":
                continue
            img.alpha_composite(park.layer(name, dd, speed, drift, t))
        ground = H * 0.835
        for cid, cx, size, ph in (("leo", 0.52 * W, 0.93, 2.3), ("mia", 0.30 * W, 1.0, 0.4)):
            D = STRIDE_U * 0.9 * size
            phase = math.pi * (dd / (ppu * size)) / D + ph
            w = min(1.0, spd(t) * 1.0)
            pose = walk_pose("after", t, phase, w, size, 1 if cid == "mia" else 2)
            if cid == "leo":
                lt = t - 1.0
                if 0 <= lt < V[1].dur:
                    pose["mouth"] = V[1].mouth("after", lt)
                    pose["head_dy"] = pose.get("head_dy", 0.0) + vc.spring_keys(lt, [(-9.0, 0.0)] + [k for e in V[1].stress for k in ((e - 0.06, -1.8), (e + 0.28, 0.0))], 4.2, 0.55)
            else:
                lt = t - 4.6
                if 0 <= lt < V[2].dur:
                    pose["mouth"] = V[2].mouth("after", lt)
                wv = vc._smooth((t - 6.0) / 0.4)
                if wv > 0:
                    wp = wave_pose("after", t - 5.9, 1)
                    pose["arms"] = (pose["arms"][0], lerp2(pose["arms"][1], wp["arms"][1], wv))
            chars[cid].draw(img, cx, ground, pose)
        img.alpha_composite(park.layer("fore", dd, 1.3, 0.0, t))
        return img.convert("RGB")
    return fn


def measure(cache: str, fps: int) -> Dict[str, Any]:
    """Numbers behind the verdicts: mouth flicker and lead, planted-foot drift, joint speeds (popping)."""
    out: Dict[str, Any] = {"mouth": {}, "foot": {}, "pop": {}}
    for i in (1, 3, 4, 5):
        v = Voice(cache, i, fps)
        for mode, seq in (("before", v.mouth_before), ("after", v.mouth_after)):
            ch = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
            runs, cur = [], 1
            for a, b in zip(seq, seq[1:]):
                if a == b:
                    cur += 1
                else:
                    runs.append(cur)
                    cur = 1
            runs.append(cur)
            openness = np.array([{"closed": 0.0, "half": 0.5, "wide": 1.0}[m] for m in seq])
            best = max(range(-4, 5), key=lambda L: float(np.corrcoef(np.roll(openness, -L), v.env[:len(openness)])[0, 1]))
            out["mouth"][f"line{i}_{mode}"] = {"changes_per_s": round(ch / v.dur, 2), "one_frame_shapes": sum(1 for r in runs if r == 1), "best_lag_frames": best,
                                              "corr_at_zero": round(float(np.corrcoef(openness, v.env[:len(openness)])[0, 1]), 3)}
    # planted foot drift over a stance (walk across, px at the reel scale): the world x of the planted foot must not move
    ppu, size = PPU, 0.93
    D = STRIDE_U * 0.9 * size
    ch = vc.load("leo", ppu, size)
    u = ch.ppu                                     # px per unit of this character (ppu * size)
    hx = ch.hip_x()
    for mode in ("before", "after"):
        worst, reach_err = 0.0, 0.0
        for k in range(8):                       # 8 stances of leg A (feet[0], the left hip)
            xs = []
            for j in range(41):
                phase = (k * 2 * math.pi) + math.pi * j / 40.0
                dist_u = phase * D / math.pi            # walk_across: phase = pi * dist_u / D
                t = dist_u / (G_UNITS * size)
                x_c = 100.0 + dist_u * u
                pose = walk_pose(mode, t, phase, 1.0, size, 2)
                tgt = pose["feet"][0]
                a1, a2 = vc.two_bone_ik(tgt, vc.ULEG_U * (1 - vc.OVERLAP), vc.LLEG_U)      # forward kinematics of what the IK really reaches
                ax = vc.ULEG_U * (1 - vc.OVERLAP) * math.sin(math.radians(a1)) + vc.LLEG_U * math.sin(math.radians(a2))
                ay = vc.ULEG_U * (1 - vc.OVERLAP) * math.cos(math.radians(a1)) + vc.LLEG_U * math.cos(math.radians(a2))
                reach_err = max(reach_err, math.hypot(ax - tgt[0], ay - tgt[1]))
                xs.append(x_c + (pose.get("dx", 0.0) - hx + ax) * u)
            worst = max(worst, max(xs) - min(xs))
        out["foot"][mode] = {"max_planted_drift_px": round(worst, 3), "max_ik_miss_units": round(reach_err, 3)}
    return out


def joint_strip(path: str) -> None:
    """A strip of 100% crops (1 px = 1 px of the 1080p reel) of the places where this kind of rig shows its seams, each with a 3x enlargement underneath."""
    ppu, size = PPU, 1.0
    ch = ld("mia", ppu, size, "after")
    u = ch.ppu
    cx = W / 2

    def frame(pose: Dict[str, Any]) -> Image.Image:
        img = stage(ticks=False).convert("RGBA")
        ch.draw(img, cx, GROUND, pose)
        return img.convert("RGB")

    stand = frame(idle("after", 1.0, 1))
    wavef = frame(wave_pose("after", 1.5, 1))
    D = STRIDE_U * 0.9
    phase = math.pi * 0.62                         # leg A mid-stance, leg B in mid-swing
    walkf = frame(walk_pose("after", 0.3, phase, 1.0, size, 1))
    h = stand_h("after")
    hip_y = GROUND - h * u
    wy = hip_y + 8 * u
    sh_y = wy - vc.TORSO_U * 0.83 * u
    neck_y = wy - vc.TORSO_U * 0.93 * u
    tw = ch.tw
    crops = [("neck + hair edge", stand, cx, neck_y), ("near shoulder + sleeve cap", stand, cx + 0.40 * tw * u, sh_y + 10 * u),
             ("torso hem + far sleeve", stand, cx - 0.30 * tw * u, wy - 14 * u), ("raised elbow + hand (wave)", wavef, cx + 28 * u, sh_y - 45 * u),
             ("knee, leg in swing (walk)", walkf, cx, hip_y + 44 * u), ("knee, planted leg (walk)", walkf, cx - ch.hip_x() * u - 10 * u, hip_y + 52 * u)]
    cw, chh = 300, 240
    tiles = []
    for name, img, x, y in crops:
        box = (int(x - cw / 2), int(y - chh / 2), int(x + cw / 2), int(y + chh / 2))
        c = img.crop(box)
        t = Image.new("RGB", (cw, chh + 3 * chh + 40), (255, 255, 255))
        t.paste(c, (0, 40))
        big = c.resize((cw * 3, chh * 3), Image.NEAREST).crop((0, 0, cw, chh * 3))      # the top-left of the enlargement is not the point: show the centre at 3x
        c3 = c.crop((cw // 2 - cw // 6, chh // 2 - chh // 6, cw // 2 + cw // 6, chh // 2 + chh // 6)).resize((cw, chh), Image.NEAREST)
        t.paste(c3, (0, 40 + chh))
        d = ImageDraw.Draw(t)
        d.text((6, 8), name, font=font(20), fill=(20, 20, 40))
        d.text((6, 40 + chh * 2 + 8), "3x on the centre of the crop (nearest neighbour)", font=font(14), fill=(90, 90, 110))
        tiles.append(t.crop((0, 0, cw, 40 + 2 * chh)))
    sheet = Image.new("RGB", (cw * 3, (40 + 2 * chh) * 2), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * cw, (i // 3) * (40 + 2 * chh)))
    sheet.save(path)


# ----------------------------------------------------------------------------- main
def mix(clips: List[Clip], fps: int) -> np.ndarray:
    total = sum(c.dur for c in clips)
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    t0 = 0.0
    for c in clips:
        for st, a in c.audio:
            s = int((t0 + st) * SR)
            out[s:s + len(a)] += a
        t0 += c.dur
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--only", default="")
    ap.add_argument("--stills", default="", help="name:t,name:t ... write PNGs (stage of a clip at t seconds) instead of a video")
    ap.add_argument("--which", default="before", help="'before' = split view where the clip has one")
    ap.add_argument("--joint-strip", default="", help="write the 100% joint crops PNG and exit")
    ap.add_argument("--measure", action="store_true", help="print the numbers behind the verdicts and exit")
    a = ap.parse_args()
    if a.joint_strip:
        joint_strip(a.joint_strip)
        return 0
    if a.measure:
        import json
        print(json.dumps(measure(a.cache, a.fps), indent=1))
        return 0
    clips = build_clips(a.cache, a.fps)
    if a.only:
        keep = set(a.only.split(","))
        clips = [c for c in clips if c.name in keep]
    by = {c.name: c for c in clips}
    if a.stills:
        for item in a.stills.split(","):
            n, ts = item.split(":")
            c = by[n]
            img = c.render(float(ts), "before" if c.both else "after")
            label(img, c.title, c.sub)
            img.save(f"{os.path.splitext(a.out)[0]}_{n}_{float(ts):04.1f}.png")
        return 0
    tmp = a.out + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "17", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for c in clips:
        n = int(round(c.dur * a.fps))
        print(c.name, n, "frames", flush=True)
        for i in range(n):
            t = i / a.fps
            img = c.render(t, "before" if c.both else "after")
            label(img, c.title, c.sub)
            p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()
    wav = a.out + ".voice.wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix(clips, a.fps), -1, 1) * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out], check=True)
    os.remove(tmp)
    os.remove(wav)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
