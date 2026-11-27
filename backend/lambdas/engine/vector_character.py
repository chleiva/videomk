"""Cut-out vector characters with a small bone rig (docs/VECTOR_SCENES.md, "Characters").

A character folder (engine/assets/vector_characters/<id>/) holds one SVG per body piece (head, torso, upper/lower arm, upper/lower leg, two eye states, three mouths) and a
manifest with each piece's size and joints, made offline by backend/scripts/vector_character_build.py. At run time every piece is rasterised ONCE at the size it is shown (so it is
sharp at any resolution, like VectorScene), then each frame turns the pieces about their joints (forward kinematics) and pastes them: about a few ms per character at 1080p.

Everything here is a pure function of the time/phase, so a chunk rendered anywhere is identical. The maths is separate from the pixels so it can be tested:
  two_bone_ik       a leg that reaches a foot target (law of cosines; the knee points forward)
  walk_feet         planted-foot walk cycle: during stance the foot is STILL on the ground (constant speed backwards relative to the body), so the feet do not skate when
                    the body (or the background) moves at the matching ground speed
  walk_period       the cycle length that matches a ground speed
  arm_angles / blink / mouth_for  idle, walking, waving, pointing arms; eyes; lip flap from an audio level

Angles are degrees; alpha = 0 hangs straight down, positive swings the end toward +x (forward = right).
"""
import io
import json
import math
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

DIR = os.path.join(os.path.dirname(__file__), "assets", "vector_characters")

# ----------------------------------------------------------------------------- proportions (units; the head is 100 units tall)
HEAD_U, TORSO_U, UARM_U, LARM_U, ULEG_U, LLEG_U = 100.0, 92.0, 46.0, 54.0, 50.0, 56.0
OVERLAP = 0.07                               # a limb piece starts this share of the piece above it inside it: no gap at knees and elbows
HIP_H0 = 0.955 * (ULEG_U * (1 - OVERLAP) + LLEG_U)          # hip height above the ground when standing (a slightly bent knee, never a locked one)
BACK_TINT = 0.80                             # the far arm and leg are drawn a little darker: depth for free


def character_ids() -> List[str]:
    try:
        return sorted(d for d in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, d, "manifest.json")))
    except OSError:
        return []


# ----------------------------------------------------------------------------- rig maths (pure)
def rot(v: Tuple[float, float], a_deg: float) -> Tuple[float, float]:
    """Rotate a vector by the segment angle: (0, 1) (straight down) goes to (sin a, cos a)."""
    a = math.radians(a_deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[1] * s, -v[0] * s + v[1] * c)


def seg(a_deg: float, length: float) -> Tuple[float, float]:
    a = math.radians(a_deg)
    return (length * math.sin(a), length * math.cos(a))


def two_bone_ik(target: Tuple[float, float], a: float, b: float) -> Tuple[float, float]:
    """Hip at the origin, target (x forward, y DOWN) -> (thigh angle, shin angle) in degrees; the knee is in front of the line hip-foot. The target is clamped to the reach."""
    x, y = target
    d = max(abs(a - b) + 1e-3, min(a + b - 1e-3, math.hypot(x, y)))
    g = math.atan2(x, y)
    cos_hip = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2 * a * d)))
    a1 = g + math.acos(cos_hip)
    kx, ky = a * math.sin(a1), a * math.cos(a1)
    a2 = math.atan2(x - kx, y - ky)
    return math.degrees(a1), math.degrees(a2)


def _smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def walk_feet(phase: float, stride: float, hip_h: float, lift: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Foot targets (relative to the hip: x forward, y down) of the two legs, `phase` in radians (leg A at phase, leg B half a cycle later).
    Stance (phase 0..pi): the foot slides back from +stride/2 to -stride/2 at CONSTANT speed on the ground line. Swing: it lifts and returns."""
    def one(p: float) -> Tuple[float, float]:
        p = p % (2 * math.pi)
        if p < math.pi:
            return (stride / 2 - stride * (p / math.pi), hip_h)
        u = (p - math.pi) / math.pi
        e = 0.35 * u + 0.65 * _smooth(u)
        return (-stride / 2 + stride * e, hip_h - lift * math.sin(math.pi * u))
    return one(phase), one(phase + math.pi)


def walk_period(stride: float, ground_speed: float) -> float:
    """Seconds per cycle so that the planted foot moves back exactly as fast as the ground moves under the character: stance lasts half a cycle and covers `stride`."""
    return 2.0 * stride / max(ground_speed, 1e-6)


def arm_angles(kind: str, t: float, phase: float = 0.0, side: int = 0, amount: float = 1.0) -> Tuple[float, float]:
    """(shoulder angle, elbow bend) of one arm. kind: idle | walk | wave | point. side 0/1 are the two arms (they swing opposite)."""
    if kind == "walk":
        p = phase + math.pi * side
        return (amount * 24.0 * math.sin(p), amount * (8.0 + 12.0 * (1 + math.sin(p)) / 2))
    if kind == "wave":
        return (152.0 + 6.0 * math.sin(2 * math.pi * 0.7 * t), 30.0 * math.sin(2 * math.pi * 3.2 * t))
    if kind == "point":
        return (128.0, 4.0)
    return ((-4.0 if side else 4.0) + 1.5 * math.sin(2 * math.pi * t / 3.2 + side), 6.0)


def blink(t: float, seed: float = 0.0, every: float = 3.4, length: float = 0.13) -> bool:
    return ((t + seed) % every) < length


def mouth_for(level: float, prev: str = "closed") -> str:
    """Lip flap from a 0..1 speech level, with a little hysteresis so the mouth does not chatter."""
    up = {"closed": 0.16, "half": 0.55, "wide": 9.9}
    down = {"closed": -1.0, "half": 0.10, "wide": 0.40}
    state = prev
    if level > up.get(state, 9.9):
        state = "half" if state == "closed" else "wide"
        if state == "half" and level > 0.55:
            state = "wide"
    elif level < down.get(state, -1.0):
        state = "closed" if state == "half" else "half"
    return state


def speech_envelope(samples: np.ndarray, sr: int, fps: int, smooth: float = 0.06) -> np.ndarray:
    """Per-video-frame speech level in 0..1 (RMS per frame, normalised to the 95th percentile, light smoothing)."""
    n = max(1, int(round(len(samples) / sr * fps)))
    hop = sr / fps
    env = np.array([float(np.sqrt(np.mean(np.square(samples[int(i * hop):int((i + 1) * hop) + 1])) + 1e-12)) for i in range(n)])
    ref = np.percentile(env, 95) if env.size else 1.0
    env = np.clip(env / max(ref, 1e-6), 0, 1.3) / 1.3 * 1.0
    k = max(1, int(round(smooth * fps)))
    return np.convolve(env, np.ones(k) / k, mode="same")


# ----------------------------------------------------------------------------- secondary motion (pure functions of time: a chunk rendered anywhere is identical)
def spring_step(t: float, freq: float = 3.2, damp: float = 0.5) -> float:
    """Step response of a damped spring: 0 for t <= 0, then rises to 1 with a little overshoot and settles. `freq` in Hz, `damp` 0..1 (lower = bouncier)."""
    if t <= 0.0:
        return 0.0
    w = 2.0 * math.pi * freq
    z = min(0.999, max(0.0, damp))
    wd = w * math.sqrt(1.0 - z * z)
    return 1.0 - math.exp(-z * w * t) * (math.cos(wd * t) + (z * w / wd) * math.sin(wd * t))


def spring_keys(t: float, keys: Sequence[Tuple[float, Any]], freq: float = 3.2, damp: float = 0.5) -> Any:
    """Keyframes (time, value) where each key is REACHED through a spring (overshoot, follow-through, settle) instead of an eased line. Values are floats or tuples of floats.
    It is a sum of step responses, so it needs no state: value(t) is the same whenever and wherever it is evaluated."""
    v0 = keys[0][1]
    if isinstance(v0, (tuple, list)):
        out = list(v0)
        for (_, a), (tk, b) in zip(keys, keys[1:]):
            k = spring_step(t - tk, freq, damp)
            for i in range(len(out)):
                out[i] += (b[i] - a[i]) * k
        return tuple(out)
    out = float(v0)
    for (_, a), (tk, b) in zip(keys, keys[1:]):
        out += (b - a) * spring_step(t - tk, freq, damp)
    return out


def ease_keys(t: float, keys: Sequence[Tuple[float, Any]]) -> Any:
    """The plain alternative to spring_keys: smoothstep between keyframes (no overshoot, no follow-through)."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            k = _smooth((t - t0) / max(t1 - t0, 1e-6))
            if isinstance(a, (tuple, list)):
                return tuple(a[i] + (b[i] - a[i]) * k for i in range(len(a)))
            return a + (b - a) * k
    return keys[-1][1]


def _hash01(i: int, seed: float) -> float:
    return (math.sin(i * 12.9898 + seed * 78.233) * 43758.5453) % 1.0


@lru_cache(maxsize=64)
def _blink_times(seed: float, horizon: float = 900.0) -> Tuple[float, ...]:
    out, t, i = [], 1.2 + 2.0 * _hash01(0, seed), 1
    while t < horizon:
        out.append(t)
        if _hash01(i, seed + 1.0) < 0.22:       # now and then a quick double blink
            out.append(t + 0.27)
        t += 2.4 + 3.0 * _hash01(i, seed + 2.0)    # irregular: 2.4 to 5.4 s
        i += 1
    return tuple(out)


def blink_natural(t: float, seed: float = 0.0, length: float = 0.12) -> bool:
    """Irregular blinks (2.4 to 5.4 s apart, sometimes a double blink); a metronome blink every 3.4 s is the clearest 'robot' tell."""
    import bisect
    ts = _blink_times(round(seed, 3))
    i = bisect.bisect_right(ts, t) - 1
    return i >= 0 and (t - ts[i]) < length


def breath(t: float, period: float = 3.8, seed: float = 0.0) -> Tuple[float, float]:
    """(torso vertical scale, head lift in units): the chest rises a little on the in-breath and the head rides on it."""
    k = 0.5 - 0.5 * math.cos(2 * math.pi * (t / period + seed))
    return 1.0 + 0.016 * k, 1.1 * k


def stress_events(env: Sequence[float], fps: int, thr: float = 0.62, min_gap: float = 0.42) -> List[float]:
    """Times (s) of the stressed syllables in a speech-level track (local maxima above `thr`, at least `min_gap` apart): where a head nod or a hand beat belongs."""
    out: List[float] = []
    for i in range(1, len(env) - 1):
        if env[i] >= thr and env[i] >= env[i - 1] and env[i] > env[i + 1]:
            t = i / fps
            if not out or t - out[-1] >= min_gap:
                out.append(t)
    return out


def mouth_track(env: Sequence[float], lead: int = 1, min_hold: int = 2) -> List[str]:
    """Mouth shape per frame from a speech-level track, computed up front: the mouth LEADS the sound by `lead` frames (animators open the mouth just before the sound) and a shape
    is held at least `min_hold` frames (no one-frame flicker)."""
    n = len(env)
    shifted = [env[min(n - 1, i + lead)] if n else 0.0 for i in range(n)]
    out: List[str] = []
    state, held = "closed", 99
    for lv in shifted:
        new = mouth_for(lv, state)
        if new != state and held < min_hold:
            new = state
        held = 0 if new != state else held + 1
        state = new
        out.append(state)
    return out


# ----------------------------------------------------------------------------- pixels
def _shade(im: Image.Image, f: float) -> Image.Image:
    a = np.array(im).astype(np.float32)
    a[..., :3] *= f
    return Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA")


class Piece:
    def __init__(self, img: Image.Image, pivot: Tuple[float, float], end: Optional[Tuple[float, float]] = None):
        self.img, self.pivot, self.end = img, pivot, end


class Character:
    """Rasterised pieces of one character at `ppu` pixels per unit (the head is 100 units tall)."""

    def __init__(self, folder: str, ppu: float, size: float = 1.0, back_tint: float = BACK_TINT):
        import resvg_py

        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            self.man = json.load(f)
        self.ppu = ppu * size
        P = self.man["parts"]
        hw = P["head"]["w"] * HEAD_U / P["head"]["h"]
        sc = {"head": HEAD_U / P["head"]["h"], "torso": TORSO_U / P["torso"]["h"], "upper_arm": UARM_U / P["upper_arm"]["h"], "lower_arm": LARM_U / P["lower_arm"]["h"],
              "upper_leg": ULEG_U / P["upper_leg"]["h"], "lower_leg": LLEG_U / P["lower_leg"]["h"]}
        es = 0.50 * hw / P["eyes_open"]["w"]
        ms = 0.27 * hw / P["mouth_wide"]["w"]
        for k in ("eyes_open", "eyes_closed"):
            sc[k] = es
        for k in ("mouth_closed", "mouth_half", "mouth_wide"):
            sc[k] = ms
        self.unit: Dict[str, float] = sc
        self.pieces: Dict[str, Piece] = {}
        for name, p in P.items():
            s = sc[name] * self.ppu
            w, h = max(1, round(p["w"] * s)), max(1, round(p["h"] * s))
            png = resvg_py.svg_to_bytes(svg_path=os.path.join(folder, p["file"]), width=w, height=h)
            im = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
            if im.size != (w, h):
                im = im.resize((w, h), Image.BILINEAR)
            piv = (p["pivot"][0] * w / p["w"], p["pivot"][1] * h / p["h"])
            end = (p["end"][0] * w / p["w"], p["end"][1] * h / p["h"]) if "end" in p else None
            self.pieces[name] = Piece(im, piv, end)
        for name in ("upper_arm", "lower_arm", "upper_leg", "lower_leg"):   # darker, mirrored copies for the far side
            pc = self.pieces[name]
            flipped = pc.img.transpose(Image.FLIP_LEFT_RIGHT) if "arm" in name else pc.img
            pv = (pc.img.width - pc.pivot[0], pc.pivot[1]) if "arm" in name else pc.pivot
            en = ((pc.img.width - pc.end[0], pc.end[1]) if "arm" in name else pc.end) if pc.end else None
            self.pieces[name + "_back"] = Piece(_shade(flipped, back_tint), pv, en)
        # sizes in units (for the joints)
        self.hw = hw
        self.tw = P["torso"]["w"] * sc["torso"]
        face = self.man.get("face", {})
        self.eyes_y = face.get("eyes_y", 0.60)      # fraction of the head height, from the top
        self.mouth_y = face.get("mouth_y", 0.80)
        self.eyes_x = face.get("eyes_x", 0.5)

    # --- geometry in units
    def hip_x(self) -> float:
        return 0.16 * self.tw

    def shoulder(self) -> Tuple[float, float]:
        return (0.40 * self.tw, -TORSO_U * 0.83)      # relative to the waist (bottom centre of the torso), y up is negative

    def draw(self, frame: Image.Image, x: float, ground: float, pose: Dict[str, Any]) -> None:
        """Paste the character on `frame` (RGB or RGBA). x: horizontal centre (px), ground: y of the soles (px)."""
        u = self.ppu
        hip_h = pose.get("hip_h", HIP_H0)
        hip_y = ground - hip_h * u                                    # the legs reach the ground by IK, so the bob is just hip_h changing
        wx, wy = x + pose.get("dx", 0.0) * u, hip_y + 8.0 * u        # waist: the torso hem hides the tops of the legs
        def put(piece: Piece, pos: Tuple[float, float], angle: float, sx: float = 1.0, sy: float = 1.0) -> None:
            """Rotate about the piece's pivot, which sits at `pos` (px); optional squash and stretch (sx, sy) about the same pivot."""
            if sx != 1.0 or sy != 1.0:
                im0 = piece.img
                im1 = im0.resize((max(1, round(im0.width * sx)), max(1, round(im0.height * sy))), Image.BILINEAR)
                piece = Piece(im1, (piece.pivot[0] * im1.width / im0.width, piece.pivot[1] * im1.height / im0.height))
            im = piece.img
            if abs(angle) < 0.05:
                frame.paste(im, (round(pos[0] - piece.pivot[0]), round(pos[1] - piece.pivot[1])), im)
                return
            cx, cy = im.width / 2, im.height / 2
            off = rot((cx - piece.pivot[0], cy - piece.pivot[1]), angle)
            r = im.rotate(angle, resample=Image.BICUBIC, expand=True)
            frame.paste(r, (round(pos[0] + off[0] - r.width / 2), round(pos[1] + off[1] - r.height / 2)), r)

        hx = self.hip_x()
        feet = pose.get("feet", ((0.0, hip_h), (0.0, hip_h)))     # (back leg, front leg) targets relative to each hip, in units
        legs = []
        for i, side in enumerate((-1, 1)):
            a1, a2 = two_bone_ik(feet[i], ULEG_U * (1 - OVERLAP), LLEG_U)
            hip = (x + pose.get("dx", 0.0) * u + side * hx * u, hip_y)
            legs.append((hip, a1, a2, "_back" if i == 0 else ""))
        # far arm, legs, torso, head, face, near arm
        sh_x, sh_y = self.shoulder()
        tsy = pose.get("torso_sy", 1.0)             # breathing / squash: the torso is scaled about the waist, the shoulders and neck ride with it
        sh_y *= tsy
        tilt = pose.get("tilt", 0.0)

        def torso_pt(px_u: float, py_u: float) -> Tuple[float, float]:
            r = rot((px_u * u, py_u * u), tilt)
            return (wx + r[0], wy + r[1])

        arms = pose.get("arms", ((4.0, 6.0), (-4.0, 6.0)))   # (far arm, near arm): (shoulder, elbow bend)
        def arm(i: int, suffix: str) -> None:
            s_ang, e_bend = arms[i]
            side = -1 if i == 0 else 1
            sp = torso_pt(side * sh_x, sh_y)
            ua, la = self.pieces["upper_arm" + suffix], self.pieces["lower_arm" + suffix]
            elbow = _joint(ua, sp, s_ang)
            put(la, elbow, s_ang + e_bend)
            put(ua, sp, s_ang)

        arm(0, "_back")
        for hip, a1, a2, suffix in legs:
            ul, ll = self.pieces["upper_leg" + suffix], self.pieces["lower_leg" + suffix]
            knee = _joint(ul, hip, a1)
            put(ll, knee, a2)
            put(ul, hip, a1)
        put(self.pieces["torso"], (wx, wy), tilt, 1.0, tsy)
        neck = torso_pt(0.0, -TORSO_U * 0.93 * tsy)
        head_tilt = tilt + pose.get("head_tilt", 0.0)
        hd = self.pieces["head"]
        hp = (neck[0], neck[1] - pose.get("head_dy", 0.0) * u)
        hsx, hsy = pose.get("head_sx", 1.0), pose.get("head_sy", 1.0)
        put(hd, hp, head_tilt, hsx, hsy)
        hh, hw_px = hd.img.height, hd.img.width

        def face_pt(fx: float, fy: float) -> Tuple[float, float]:
            v = rot(((fx - hd.pivot[0]) * hsx, (fy - hd.pivot[1]) * hsy), head_tilt)
            return (hp[0] + v[0], hp[1] + v[1])

        eyes = self.pieces["eyes_closed" if pose.get("blink") else "eyes_open"]
        ex, ey = face_pt(hw_px * self.eyes_x + pose.get("look", (0.0, 0.0))[0] * u, hh * self.eyes_y + pose.get("look", (0.0, 0.0))[1] * u)
        es = pose.get("eyes_scale", 1.0)             # wide eyes for surprise
        put(Piece(eyes.img, (eyes.img.width / 2, eyes.img.height / 2)), (ex, ey), head_tilt, es, es)
        mouth = self.pieces["mouth_" + pose.get("mouth", "closed")]
        mx, my = face_pt(hw_px * self.eyes_x, hh * self.mouth_y)
        put(Piece(mouth.img, (mouth.img.width / 2, mouth.img.height / 2)), (mx, my), head_tilt)
        arm(1, "")

    def draw_turned(self, frame: Image.Image, x: float, ground: float, pose: Dict[str, Any], turn: float) -> None:
        """Facing control by a paper-doll flip: the whole figure is drawn, then squeezed sideways by |turn| (1 = full width) and mirrored when turn < 0, so a mid-turn frame is a
        narrow slab. There is no 3/4 view in this rig (the art is front-facing): this is a flip, not a turn of the body. turn = 1 faces right (the shoes point right), -1 faces left."""
        if turn >= 0.999:
            return self.draw(frame, x, ground, pose)
        u = self.ppu
        wl, hl = int(400 * u), max(8, int(ground + 12 * u))
        layer = Image.new("RGBA", (wl, hl), (0, 0, 0, 0))
        self.draw(layer, wl / 2, ground, pose)
        nw = max(2, round(wl * abs(turn)))
        out = layer.resize((nw, hl), Image.BILINEAR)
        if turn < 0:
            out = out.transpose(Image.FLIP_LEFT_RIGHT)
        frame.paste(out, (round(x - nw / 2), 0), out)


def _add(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Tuple[float, float], k: float) -> Tuple[float, float]:
    return (a[0] * k, a[1] * k)


def _joint(p: Piece, pos: Tuple[float, float], angle: float) -> Tuple[float, float]:
    """World position of the end joint of a piece hanging from `pos` and turned by `angle`."""
    v = rot((p.end[0] - p.pivot[0], (p.end[1] - p.pivot[1]) * (1 - OVERLAP)), angle)
    return (pos[0] + v[0], pos[1] + v[1])


@lru_cache(maxsize=16)
def load(cid: str, ppu: float, size: float = 1.0, back_tint: float = BACK_TINT) -> Character:
    if cid not in character_ids():
        raise ValueError(f"unknown vector character {cid!r}")
    return Character(os.path.join(DIR, cid), ppu, size, back_tint)
