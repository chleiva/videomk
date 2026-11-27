"""Standing presenter rig for the cut-out vector characters (docs/CHARACTER_ANIMATION_PROOF.md, "Second pass: the speaker").

The first rig (engine/vector_character.py) was built for walking: side-view legs on a two-bone IK with a knee that is never straight, arms that hang from the top edge of the sleeve.
Standing still it reads as a person half sitting, and a raised sleeve leaves the shoulder. This rig uses the SAME art for a different job: a speaker who stands and talks.

  legs      one straight piece per leg (thigh and shin fused once at load: widths matched at the knee, the inner outline removed), feet planted, toes turned out;
            the hips may shift a little over planted feet (weight shift) and a foot may take a small side step. There is no knee and no walk.
  arms      shoulder pivot in the CENTRE of the round sleeve cap (the cap stays on the shoulder at any angle), elbow pivot inside both pieces, a two-bone IK from a wrist
            target, with the elbow always on the same side of the shoulder-wrist line, so it cannot flip (see arm_ik), and the reach clamped so the arm never locks straight;
            at home the arm hangs by its own angles (elbow out, forearm in: solve_arm), blended into the IK as the hand leaves
  hands     the forearm piece is cut at the wrist: the hand is its own piece that turns at the wrist and can be swapped (relaxed, open palm, one, two, three, thumb up)
  tail      optional piece behind the legs (the fox)

All geometry is in UNITS (the head is 100 units tall), x to the right, y UP, origin on the ground under the character. `solve` is pure maths (tested without pixels);
`Presenter.draw` rasterises. Pose keys are listed at `solve`. The gestures that drive it live in engine/character_gestures.py. Nothing here is wired into the planner.
"""
import io
import json
import math
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

DIR = os.path.join(os.path.dirname(__file__), "assets", "vector_characters")

HEAD_U, TORSO_U, UARM_U, LARM_U, ULEG_U, LLEG_U = 100.0, 92.0, 46.0, 54.0, 56.0, 60.0
KNEE_OV = 0.12            # the shin starts this share of the thigh above its lower end (hides the thigh's hem)
WAIST_UP = 8.0            # the torso hem hangs this far below the hip joints
REACH_MAX = 0.985         # the wrist never goes further than this share of the full arm: the elbow keeps a soft bend and never snaps
REACH_MIN = 0.30
HAND_SCALE = 1.22          # the swapped hand shapes are drawn a little larger than anatomy: hands must read at video size
HAND_SHAPES = ("relaxed", "open", "one", "two", "three", "thumb")
Vec = Tuple[float, float]


# ----------------------------------------------------------------------------- pure maths
def arm_ik(shoulder: Vec, target: Vec, a: float, b: float, side: int) -> Tuple[Vec, Vec]:
    """-> (elbow, wrist) for a wrist target. `side` is +1 for the arm on the right of the picture, -1 for the left one.
    The wrist is the target clamped to [REACH_MIN, REACH_MAX] of the arm length. The elbow is always on the same side of the line shoulder -> wrist (seen along that line: on the
    right for the right arm), which gives: arm hanging = elbow a touch inward and the forearm slightly out; forearm raised to the side = elbow low by the ribs; hand up by the
    head = elbow out. Because the side never changes, the elbow moves continuously for any continuous wrist path."""
    dx, dy = target[0] - shoulder[0], target[1] - shoulder[1]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        dx, dy, d = 0.0, -1.0, 1.0
    full = a + b
    dc = max(max(REACH_MIN * full, abs(a - b) + 1e-3), min(REACH_MAX * full, d))
    ux, uy = dx / d, dy / d
    wrist = (shoulder[0] + ux * dc, shoulder[1] + uy * dc)
    cos_s = max(-1.0, min(1.0, (a * a + dc * dc - b * b) / (2 * a * dc)))
    sin_s = math.sqrt(max(0.0, 1.0 - cos_s * cos_s))
    nx, ny = (uy, -ux) if side > 0 else (-uy, ux)
    elbow = (shoulder[0] + a * (ux * cos_s + nx * sin_s), shoulder[1] + a * (uy * cos_s + ny * sin_s))
    return elbow, wrist


def _rot_up(v: Vec, deg: float) -> Vec:
    """Rotate counter-clockwise in the y-up frame."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


class Geom:
    """Sizes of one character in units (see Presenter.__init__ for how they are measured from the art)."""

    def __init__(self, **kw: float):
        self.hip_x = 10.0            # half the distance between the hip joints
        self.stance = 13.0           # half the distance between the feet (ankles) when standing: about hip width, a touch wider
        self.leg_len = ULEG_U * (1 - KNEE_OV) + LLEG_U
        self.shoulder_x = 26.0
        self.shoulder_y = 70.0       # above the waist
        self.neck_y = TORSO_U * 0.93
        self.upper = 38.0            # shoulder -> elbow
        self.fore = 34.0             # elbow -> wrist
        self.hand = 18.0             # wrist -> finger tips (for bounds only)
        self.__dict__.update(kw)

    @property
    def hip_h(self) -> float:
        return math.sqrt(max(1.0, self.leg_len ** 2 - (self.stance - self.hip_x) ** 2))

    @property
    def arm(self) -> float:
        return self.upper + self.fore


REST_UPPER, REST_FORE = 7.0, -4.0     # home base, degrees from straight down, positive = away from the body: the upper arm hangs a little OUT (the elbow is the widest point),
#                                       the forearm comes back IN toward the thigh. (The first cut had it the other way round: elbows tucked in, forearms flaring out,
#                                       which made each arm look like the arm of the other side.)
REST_ZONE = 0.30                      # within this share of the arm length of home, the arm blends from the home angles to the IK solution


def _dir(deg: float, side: int) -> Vec:
    r = math.radians(deg)
    return (side * math.sin(r), -math.cos(r))


def rest_target(g: Geom) -> Vec:
    """Wrist at home, relative to the shoulder (x away from the body, y up)."""
    u, f = _dir(REST_UPPER, 1), _dir(REST_FORE, 1)
    return (g.upper * u[0] + g.fore * f[0], g.upper * u[1] + g.fore * f[1])


def solve_arm(g: Geom, shoulder: Vec, hand: Vec, side: int) -> Tuple[Vec, Vec]:
    """-> (elbow, wrist). Far from home: the IK solution for the wrist target. At home: the home angles (elbow out, forearm in). In between the two bone ANGLES are blended, so the
    bones keep their length and the arm passes through straight on its way from one bend to the other; nothing flips."""
    rt = rest_target(g)
    e, w = arm_ik(shoulder, (shoulder[0] + side * hand[0], shoulder[1] + hand[1]), g.upper, g.fore, side)
    k = min(1.0, math.hypot(hand[0] - rt[0], hand[1] - rt[1]) / (REST_ZONE * g.arm))
    home = 1.0 - k * k * (3 - 2 * k)
    if home <= 0.0:
        return e, w
    au = math.degrees(math.atan2(side * (e[0] - shoulder[0]), -(e[1] - shoulder[1])))
    af = math.degrees(math.atan2(side * (w[0] - e[0]), -(w[1] - e[1])))
    du, df = _dir(au + (REST_UPPER - au) * home, side), _dir(af + (REST_FORE - af) * home, side)
    e = (shoulder[0] + g.upper * du[0], shoulder[1] + g.upper * du[1])
    return e, (e[0] + g.fore * df[0], e[1] + g.fore * df[1])


def solve(g: Geom, pose: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Skeleton for a pose, in units (x right, y up, origin on the ground under the character). Pose keys (all optional):
      dx, dy        pelvis shift sideways / drop (weight shift over planted feet, settle)
      feet          ((x, lift), (x, lift)) left and right foot relative to the character's x; default (-stance, 0), (+stance, 0)
      lean          torso tilt about the waist, degrees, positive = toward the right of the picture
      torso_sy      breathing / squash of the torso (1 = none);  shrug: the shoulders rise by this many units
      hands         ((x, y), (x, y)) wrist targets of the left and right arm RELATIVE TO THEIR SHOULDER, x positive = away from the body, y up; default: hanging
      wrist         (deg, deg) hand turn relative to the forearm, positive = the same way the elbow bends (outward / up)
      hand_shape    (name, name) from HAND_SHAPES
      head_tilt, head_dx, head_dy, head_sx, head_sy, look (x, y), blink, mouth, eyes_scale, tail (deg)     drawn by Presenter.draw, passed through here
    Returns joints: hips, feet, leg (angle from vertical in degrees, positive = foot toward +x; length scale), waist, shoulders, elbows, wrists, hand_dir (unit vectors), neck."""
    p = pose or {}
    dx, dy = p.get("dx", 0.0), p.get("dy", 0.0)
    feet = p.get("feet") or ((-g.stance, 0.0), (g.stance, 0.0))
    hip_y = g.hip_h - dy
    hips, legs = [], []
    for i, side in enumerate((-1, 1)):
        hip = (dx + side * g.hip_x, hip_y)
        fx, fl = feet[i]
        vx, vy = fx - hip[0], fl - hip[1]
        legs.append((math.degrees(math.atan2(vx, -vy)), math.hypot(vx, vy) / g.leg_len))
        hips.append(hip)
    waist = (dx, hip_y - WAIST_UP)
    lean = p.get("lean", 0.0)
    tsy = p.get("torso_sy", 1.0)
    shrug = p.get("shrug", 0.0)

    def torso_pt(x: float, y: float) -> Vec:
        v = _rot_up((x, y), -lean)
        return (waist[0] + v[0], waist[1] + v[1])

    rt = rest_target(g)
    hands = p.get("hands") or (rt, rt)
    wr = p.get("wrist") or (0.0, 0.0)
    shoulders, elbows, wrists, hdirs, fdirs = [], [], [], [], []
    for i, side in enumerate((-1, 1)):
        s = torso_pt(side * g.shoulder_x, g.shoulder_y * tsy + shrug)
        hx, hy = hands[i] if hands[i] is not None else rt
        e, w = solve_arm(g, s, (hx, hy), side)
        f = ((w[0] - e[0]) / g.fore, (w[1] - e[1]) / g.fore)
        shoulders.append(s)
        elbows.append(e)
        wrists.append(w)
        fdirs.append(f)
        hdirs.append(_rot_up(f, side * wr[i]))
    return {"hips": hips, "feet": [(feet[0][0], feet[0][1]), (feet[1][0], feet[1][1])], "leg": legs, "waist": waist, "lean": lean, "torso_sy": tsy,
            "shoulders": shoulders, "elbows": elbows, "wrists": wrists, "fore_dir": fdirs, "hand_dir": hdirs, "neck": torso_pt(0.0, g.neck_y * tsy + 0.5 * shrug)}


# ----------------------------------------------------------------------------- pixels
def _alpha(im: Image.Image) -> np.ndarray:
    return np.array(im)[..., 3] > 96


def _span(a: np.ndarray, y: int) -> Tuple[float, float]:
    y = max(0, min(a.shape[0] - 1, int(y)))
    xs = np.nonzero(a[y])[0]
    if not xs.size:
        return (a.shape[1] / 2, a.shape[1] / 2)
    return float(xs.min()), float(xs.max() + 1)


def _is_ink(rgb: np.ndarray) -> np.ndarray:
    return rgb.astype(np.int32).sum(axis=-1) < 200


def find_wrist(im: Image.Image) -> Tuple[int, Tuple[int, int, int]]:
    """Row where the hand begins on a forearm+hand piece hanging down, and the skin colour. Rule: the skin is the commonest fill colour of the lowest fifth; going up, the skin
    region ends at the cuff (long sleeves); when the forearm is bare the wrist is the narrowest row above the palm."""
    arr = np.array(im)
    h, w = arr.shape[:2]
    op = arr[..., 3] > 96
    fill = op & ~_is_ink(arr[..., :3])
    low = arr[int(h * 0.8):][fill[int(h * 0.8):]][:, :3]
    skin = tuple(int(v) for v in np.median(low, axis=0)) if low.size else (200, 160, 130)
    near = fill & (np.abs(arr[..., :3].astype(np.int32) - np.array(skin)).sum(axis=-1) < 70)
    top, miss = int(h * 0.88), 0
    for y in range(int(h * 0.88), int(h * 0.15), -1):
        n = fill[y].sum()
        if n and near[y].sum() / n < 0.5:
            miss += 1
            if miss >= 3:
                break
        else:
            miss, top = 0, y
    widths = op.sum(axis=1)
    palm = int(h * 0.62) + int(np.argmax(widths[int(h * 0.62):int(h * 0.9)]))
    wrist = top
    if palm - top > 0.22 * h:                    # a bare forearm above the hand: cut at its narrowest row
        lo = top + int(0.35 * (palm - top))
        wrist = lo + int(np.argmin(widths[lo:palm]))
    return int(wrist), skin


class Piece:
    def __init__(self, img: Image.Image, pivot: Vec, end: Optional[Vec] = None):
        self.img, self.pivot, self.end = img, pivot, end
        # the drawn bone (pivot -> end) is rarely exactly vertical in the art: `bias` is the turn that puts it on the rig's bone, so the far joint lands where the maths says
        self.bias = -math.degrees(math.atan2(end[0] - pivot[0], end[1] - pivot[1])) if end else 0.0

    def flipped(self) -> "Piece":
        w = self.img.width
        return Piece(self.img.transpose(Image.FLIP_LEFT_RIGHT), (w - self.pivot[0], self.pivot[1]), (w - self.end[0], self.end[1]) if self.end else None)


def _raster(folder: str, file: str, w: int, h: int) -> Image.Image:
    import resvg_py

    png = resvg_py.svg_to_bytes(svg_path=os.path.join(folder, file), width=max(1, w), height=max(1, h))
    im = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
    return im if im.size == (w, h) else im.resize((max(1, w), max(1, h)), Image.BILINEAR)


def fuse_leg(ul: Image.Image, ll: Image.Image, ll_pivot_x: float, sole_x: float) -> Piece:
    """One straight leg from the thigh and the shin+shoe pieces (both at their final pixel size): the thigh is scaled sideways so its lower width equals the shin's upper width,
    the shin's top outline is removed and the shin is pasted over the lower KNEE_OV of the thigh. Pivot = the hip (top centre), end = the sole under the ankle."""
    a_ul, a_ll = _alpha(ul), _alpha(ll)
    u0, u1 = _span(a_ul, int(ul.height * 0.86))
    l0, l1 = _span(a_ll, int(ll.height * 0.10))
    k = max(0.7, min(1.4, (l1 - l0) / max(1.0, u1 - u0)))
    if abs(k - 1) > 0.02:
        ul = ul.resize((max(1, round(ul.width * k)), ul.height), Image.BILINEAR)
        a_ul = _alpha(ul)
        u0, u1 = _span(a_ul, int(ul.height * 0.86))
    arr = np.array(ll)
    cx = int((l0 + l1) / 2)
    ink = _is_ink(arr[..., :3]) | (arr[..., 3] < 96)
    m = max(2, int((l1 - l0) * 0.2))
    del cx
    y = 0
    while y < ll.height * 0.12 and ink[y, int(l0) + m:int(l1) - m].mean() > 0.25:      # rows of the top outline
        y += 1
    if y < ll.height * 0.12:
        arr[:y + 1, :, 3] = 0
        ll = Image.fromarray(arr, "RGBA")
    ov = round(ul.height * KNEE_OV)
    ucx, lcx = (u0 + u1) / 2, (l0 + l1) / 2
    left = round(max(0.0, lcx - ucx))               # x of the thigh's left edge on the canvas
    lx = round(left + ucx - lcx)
    W = max(left + ul.width, lx + ll.width)
    H = ul.height - ov + ll.height
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(ul, (left, 0))
    out.alpha_composite(ll, (lx, ul.height - ov))
    t0, t1 = _span(a_ul, int(ul.height * 0.06))
    return Piece(out, (left + (t0 + t1) / 2, ul.height * 0.05), (lx + sole_x, float(H)))


class TurnCache:
    """Turned (and scaled) pieces kept between frames, for the real renders (engine/scenes/elements/presenter.py; docs/PRESENTERS.md "Render cost").

    Turning a piece is 85 % of a frame's drawing time, and a speaker's pieces come back to the same angles all the time (home base, the same gestures). With a cache the
    angle is snapped to `STEP` degrees and the scale to `SCALE_STEP`, so a frame depends only on the snapped values: the picture is the same whether the piece came from the
    cache or was turned again, i.e. the same in every render chunk and on every machine. Memory is bounded: least recently used pieces are dropped beyond `max_bytes`."""

    STEP = 0.5          # degrees: half a degree at the wrist of a 54-unit forearm is under half a pixel at 1080p
    SCALE_STEP = 0.004  # breathing and head squash change the size by a few thousandths

    def __init__(self, max_bytes: int = 48 << 20):
        from collections import OrderedDict
        self.max_bytes, self.bytes, self.hits, self.misses = max_bytes, 0, 0, 0
        self.d: "OrderedDict[tuple, Tuple[Image.Image, Vec]]" = OrderedDict()

    def get(self, key: tuple) -> Optional[Tuple[Image.Image, Vec]]:
        v = self.d.get(key)
        if v is None:
            self.misses += 1
            return None
        self.d.move_to_end(key)
        self.hits += 1
        return v

    def put(self, key: tuple, im: Image.Image, off: Vec) -> None:
        self.d[key] = (im, off)
        self.bytes += im.width * im.height * 4
        while self.bytes > self.max_bytes and len(self.d) > 1:
            _, (old, _o) = self.d.popitem(last=False)
            self.bytes -= old.width * old.height * 4

    def clear(self) -> None:
        self.d.clear()
        self.bytes = 0


class Presenter:
    """Rasterised pieces of one character at `ppu` pixels per unit, ready to draw standing poses."""

    cache: Optional[TurnCache] = None    # set by `load_cached`: turned pieces are kept and angles snapped (see TurnCache); None = exact angles, nothing kept (the demos and pin tests)

    def __init__(self, folder: str, ppu: float, size: float = 1.0):
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            self.man = json.load(f)
        cfg: Dict[str, Any] = {}
        pj = os.path.join(folder, "presenter.json")
        if os.path.exists(pj):
            with open(pj, encoding="utf-8") as f:
                cfg = json.load(f)
        self.cfg = cfg
        self.folder = folder
        self.ppu = u = ppu * size
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
        raw: Dict[str, Image.Image] = {}
        for name, p in P.items():
            s = sc[name] * u
            raw[name] = _raster(folder, p["file"], round(p["w"] * s), round(p["h"] * s))
        self.pieces: Dict[str, Piece] = {}
        # head and face
        hd = raw["head"]
        self.pieces["head"] = Piece(hd, (P["head"]["pivot"][0] * hd.width / P["head"]["w"], P["head"]["pivot"][1] * hd.height / P["head"]["h"]))
        for k in ("eyes_open", "eyes_closed", "mouth_closed", "mouth_half", "mouth_wide"):
            self.pieces[k] = Piece(raw[k], (raw[k].width / 2, raw[k].height / 2))
        face = self.man.get("face", {})
        self.eyes_y, self.mouth_y, self.eyes_x = face.get("eyes_y", 0.60), face.get("mouth_y", 0.80), face.get("eyes_x", 0.5)
        # torso
        to = raw["torso"]
        self.pieces["torso"] = Piece(to, (to.width / 2, float(to.height)))
        a_to = _alpha(to)
        b0, b1 = _span(a_to, int(to.height * 0.55))                       # the body below the shoulders (the builder cut the drawn sleeves away)
        body_half = (b1 - b0) / 2 / u
        tw = to.width / u
        # legs
        ll_p = P["lower_leg"]
        k_ll = raw["lower_leg"].width / ll_p["w"]
        leg = fuse_leg(raw["upper_leg"], raw["lower_leg"], ll_p["pivot"][0] * k_ll, ll_p["pivot"][0] * k_ll)
        self.pieces["leg_r"] = leg
        self.pieces["leg_l"] = leg.flipped()
        # arms
        ua = raw["upper_arm"]
        a_ua = _alpha(ua)
        c0, c1 = _span(a_ua, int(ua.height * 0.16))
        r_cap = (c1 - c0) / 2
        e0, e1 = _span(a_ua, int(ua.height * 0.86))
        r_el = (e1 - e0) / 2
        up = Piece(ua, ((c0 + c1) / 2, r_cap * 0.92), ((e0 + e1) / 2, ua.height - r_el * 0.95))
        la = raw["lower_arm"]
        wrist_y, self.skin = find_wrist(la)
        if "wrist" in cfg:
            wrist_y = round(cfg["wrist"] * la.height)
        a_la = _alpha(la)
        f0, f1 = _span(a_la, int(la.height * 0.08))
        r_f = (f1 - f0) / 2
        w0, w1 = _span(a_la, wrist_y)
        tuck = max(2, round(0.035 * la.height))                            # the hand goes this far under the cuff
        fore = Piece(la.crop((0, 0, la.width, wrist_y + 1)), ((f0 + f1) / 2, r_f * 0.95), ((w0 + w1) / 2, float(wrist_y - tuck * 0.3)))
        hand = Piece(la.crop((0, max(0, wrist_y - tuck), la.width, la.height)), ((w0 + w1) / 2, float(tuck)))
        self.wrist_w = (w1 - w0) / u
        self.pieces["upper_r"], self.pieces["upper_l"] = up, up.flipped()
        # Which way round the forearm+hand drawing goes. At home the thumb is on the BODY side of the hand (it points forward, the fingers curl toward the thigh). The sheets
        # draw the thumb on either side, so presenter.json says where it is ("relaxed_thumb": +1 = on the right of the drawing) and the drawing is mirrored where needed.
        t = int(cfg.get("relaxed_thumb", 1))
        fr, hr = (fore, hand) if t < 0 else (fore.flipped(), hand.flipped())          # right arm of the picture: the body is on its left, so the thumb must be on the left
        self.pieces["fore_r"], self.pieces["fore_l"] = fr, fr.flipped()
        self.pieces["hand_relaxed_r"], self.pieces["hand_relaxed_l"] = hr, hr.flipped()
        self.thumb_x: Dict[Tuple[str, str], int] = {("relaxed", "r"): -1, ("relaxed", "l"): 1}    # where the thumb is on each piece as stored (hanging down): -1 left, +1 right
        # extra hand shapes (drawn fingers UP with a wrist stub at the bottom; turned half a turn here so that, like the relaxed hand, the fingers continue the forearm)
        self.shapes: List[str] = ["relaxed"]
        for name, hp in (cfg.get("hands") or {}).items():
            path = os.path.join(folder, hp["file"])
            if name not in HAND_SHAPES or not os.path.exists(path):
                continue
            k = hp.get("scale", 1.0) * HAND_SCALE * (w1 - w0) / max(1.0, hp["wrist_w"])     # the stub is as wide as the forearm's wrist
            im = _raster(folder, hp["file"], round(hp["w"] * k), round(hp["h"] * k)).transpose(Image.ROTATE_180)
            pv = (im.width - hp["pivot"][0] * k, im.height - hp["pivot"][1] * k)
            pc = Piece(im, pv)
            if cfg.get("sheet_thumb", "left") == "right":                      # a sheet drawn the other way round (the fox's)
                pc = pc.flipped()
            # Gesture hands show the PALM. A raised palm has its thumb toward the head, a presenting palm has its thumb on top: both mean the thumb is on the OUTER side of the
            # piece as stored (hanging down, before the forearm turns it up). Upright on the sheet the thumb is on the left; turned half a turn it is on the right = outer for the
            # right arm of the picture. (The first cut gave this piece to the left arm: thumbs away from the head, presenting hands thumb down.)
            self.pieces[f"hand_{name}_r"], self.pieces[f"hand_{name}_l"] = pc, pc.flipped()
            self.thumb_x[(name, "r")], self.thumb_x[(name, "l")] = 1, -1
            self.shapes.append(name)
        # tail
        tp = cfg.get("tail")
        if tp and os.path.exists(os.path.join(folder, tp["file"])):
            k = tp["height_u"] * u / tp["h"]
            im = _raster(folder, tp["file"], round(tp["w"] * k), round(tp["h"] * k))
            self.pieces["tail"] = Piece(im, (tp["pivot"][0] * k, tp["pivot"][1] * k))
        # geometry in units
        arm_w = ua.width / u
        g = Geom()
        g.hip_x = cfg.get("hip_x", 0.17 * tw)
        g.stance = g.hip_x + cfg.get("stance_out", 3.0)
        g.shoulder_x = cfg.get("shoulder_x", body_half + 0.30 * arm_w)
        g.shoulder_y = cfg.get("shoulder_y", 0.775 * TORSO_U)
        g.upper = (up.end[1] - up.pivot[1]) / u
        g.fore = (fore.end[1] - fore.pivot[1]) / u
        g.hand = (hand.img.height - hand.pivot[1]) / u
        g.leg_len = (leg.end[1] - leg.pivot[1]) / u
        self.g = g
        self.hw, self.tw = hw, tw
        self.height = g.hip_h - WAIST_UP + g.neck_y + HEAD_U     # ground to the top of the head, units

    # --- drawing
    def _put(self, frame: Image.Image, piece: Piece, pos: Vec, angle: float, sx: float = 1.0, sy: float = 1.0) -> None:
        """Paste `piece` with its pivot at `pos` (px), turned by `angle` degrees counter-clockwise on screen; optional scale about the pivot."""
        if self.cache is not None:
            self._put_cached(frame, piece, pos, angle, sx, sy)
            return
        im, pv = piece.img, piece.pivot
        if sx != 1.0 or sy != 1.0:
            im1 = im.resize((max(1, round(im.width * sx)), max(1, round(im.height * sy))), Image.BILINEAR)
            pv = (pv[0] * im1.width / im.width, pv[1] * im1.height / im.height)
            im = im1
        angle += piece.bias
        if abs(angle) < 0.05:
            _paste_clip(frame, im, (round(pos[0] - pv[0]), round(pos[1] - pv[1])))
            return
        a = math.radians(angle)
        c, s = math.cos(a), math.sin(a)
        vx, vy = im.width / 2 - pv[0], im.height / 2 - pv[1]
        off = (vx * c + vy * s, -vx * s + vy * c)
        r = im.rotate(angle, resample=Image.BICUBIC, expand=True)
        _paste_clip(frame, r, (round(pos[0] + off[0] - r.width / 2), round(pos[1] + off[1] - r.height / 2)))

    def _put_cached(self, frame: Image.Image, piece: Piece, pos: Vec, angle: float, sx: float, sy: float) -> None:
        """`_put` with the angle and scale snapped and the turned piece kept (TurnCache). The piece is stored with the offset of its top-left corner from the pivot."""
        c = self.cache
        qa = round((angle + piece.bias) / c.STEP)
        qx, qy = round(sx / c.SCALE_STEP), round(sy / c.SCALE_STEP)
        key = (id(piece), qa, qx, qy)
        got = c.get(key)
        if got is None:
            im, pv = piece.img, piece.pivot
            fx, fy = qx * c.SCALE_STEP, qy * c.SCALE_STEP
            if qx != round(1.0 / c.SCALE_STEP) or qy != round(1.0 / c.SCALE_STEP):
                im1 = im.resize((max(1, round(im.width * fx)), max(1, round(im.height * fy))), Image.BILINEAR)
                pv = (pv[0] * im1.width / im.width, pv[1] * im1.height / im.height)
                im = im1
            a_deg = qa * c.STEP
            if qa == 0:
                got = (im, (-pv[0], -pv[1]))
            else:
                a = math.radians(a_deg)
                cs, sn = math.cos(a), math.sin(a)
                vx, vy = im.width / 2 - pv[0], im.height / 2 - pv[1]
                r = im.rotate(a_deg, resample=Image.BICUBIC, expand=True)
                got = (r, (vx * cs + vy * sn - r.width / 2, -vx * sn + vy * cs - r.height / 2))
            c.put(key, got[0], got[1])
        im, off = got
        _paste_clip(frame, im, (round(pos[0] + off[0]), round(pos[1] + off[1])))

    def draw(self, frame: Image.Image, x: float, ground: float, pose: Optional[Dict[str, Any]] = None, sk: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Draw on an RGBA `frame`: x = horizontal centre (px), ground = y of the soles (px). Returns the solved skeleton."""
        p = pose or {}
        u = self.ppu
        sk = sk or solve(self.g, p)

        def px(v: Vec) -> Vec:
            return (x + v[0] * u, ground - v[1] * u)

        def ang(d: Vec) -> float:               # screen rotation that turns "down" onto the direction d (y up)
            return math.degrees(math.atan2(d[0], -d[1]))

        if "tail" in self.pieces:
            tp = self.cfg["tail"]
            self._put(frame, self.pieces["tail"], px((sk["waist"][0] + tp.get("x", 0.0), sk["waist"][1] + tp.get("y", 10.0))), tp.get("angle", 0.0) + p.get("tail", 0.0))
        for i, name in enumerate(("leg_l", "leg_r")):
            a, k = sk["leg"][i]
            self._put(frame, self.pieces[name], px(sk["hips"][i]), a, 1.0, k)
        lean = sk["lean"]
        self._put(frame, self.pieces["torso"], px(sk["waist"]), -lean, 1.0, sk["torso_sy"])
        for i, s in enumerate(("l", "r")):
            e, sh = sk["elbows"][i], sk["shoulders"][i]
            self._put(frame, self.pieces["upper_" + s], px(sh), ang((e[0] - sh[0], e[1] - sh[1])))
        # head and face
        hd = self.pieces["head"]
        head_tilt = -lean * 0.6 + p.get("head_tilt", 0.0)
        hp0 = px(sk["neck"])
        hp = (hp0[0] + p.get("head_dx", 0.0) * u, hp0[1] - p.get("head_dy", 0.0) * u)
        hsx, hsy = p.get("head_sx", 1.0), p.get("head_sy", 1.0)
        self._put(frame, hd, hp, head_tilt, hsx, hsy)
        hh, hw_px = hd.img.height, hd.img.width
        ta = math.radians(head_tilt)
        tc, ts = math.cos(ta), math.sin(ta)

        def face_pt(fx: float, fy: float) -> Vec:
            vx, vy = (fx - hd.pivot[0]) * hsx, (fy - hd.pivot[1]) * hsy
            return (hp[0] + vx * tc + vy * ts, hp[1] - vx * ts + vy * tc)

        look = p.get("look", (0.0, 0.0))
        eyes = self.pieces["eyes_closed" if p.get("blink") else "eyes_open"]
        es = p.get("eyes_scale", 1.0)
        self._put(frame, eyes, face_pt(hw_px * self.eyes_x + look[0] * u, hh * self.eyes_y - look[1] * u), head_tilt, es, es)
        mouth = self.pieces["mouth_" + p.get("mouth", "closed")]
        self._put(frame, mouth, face_pt(hw_px * self.eyes_x + 0.4 * look[0] * u, hh * self.mouth_y), head_tilt)
        shapes = p.get("hand_shape") or ("relaxed", "relaxed")
        for i, s in enumerate(("l", "r")):
            name = f"hand_{shapes[i]}_{s}"
            if name not in self.pieces:
                name = f"hand_relaxed_{s}"
            self._put(frame, self.pieces[name], px(sk["wrists"][i]), ang(sk["hand_dir"][i]))
            self._put(frame, self.pieces["fore_" + s], px(sk["elbows"][i]), ang(sk["fore_dir"][i]))
        return sk


def _paste_clip(frame: Image.Image, im: Image.Image, at: Tuple[int, int]) -> None:
    """alpha_composite that tolerates a piece partly (or wholly) outside the frame."""
    x, y = at
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.width, x + im.width), min(frame.height, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    frame.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


@lru_cache(maxsize=16)
def load(cid: str, ppu: float, size: float = 1.0) -> Presenter:
    folder = os.path.join(DIR, cid)
    if not os.path.isfile(os.path.join(folder, "manifest.json")):
        raise ValueError(f"unknown vector character {cid!r}")
    return Presenter(folder, ppu, size)


@lru_cache(maxsize=4)
def load_cached(cid: str, ppu: float, size: float = 1.0, max_mb: int = 48) -> Presenter:
    """A presenter of its own (not the shared one of `load`) that keeps its turned pieces: for rendering real videos. At most 4 are kept (a video has one presenter,
    a dialogue two), each with at most `max_mb` of turned pieces."""
    folder = os.path.join(DIR, cid)
    if not os.path.isfile(os.path.join(folder, "manifest.json")):
        raise ValueError(f"unknown vector character {cid!r}")
    p = Presenter(folder, ppu, size)
    p.cache = TurnCache(max_mb << 20)
    return p


# ----------------------------------------------------------------------------- framing presets
FRAMINGS = ("full", "three_quarter", "waist_up")


def framing(preset: str, side: str, W: int, H: int, height_u: float = 290.0) -> Dict[str, Any]:
    """Where a presenter stands beside content, for any frame shape. -> {ppu, x, ground, content: (x0, y0, x1, y1)} in pixels, and `lift`: how much higher the low gestures should be
    made (Performance(lift=...)) so that the hands stay in a tight frame.
      full           the whole figure, feet on a floor line
      three_quarter  cut at mid thigh (the classic presenter shot)
      waist_up       cut just under the waist, the largest face and hands
    side: "left" | "right" | "center". In wide frames (16:9) the content sits beside the presenter; in tall and square frames (9:16, 4:5, 1:1) the content takes the upper part
    and the presenter stands in the lower part, to one side."""
    if preset not in FRAMINGS:
        raise ValueError(f"unknown framing {preset!r}")
    ar = W / H
    wide = ar >= 1.3
    cut = {"full": 0.0, "three_quarter": 0.27, "waist_up": 0.31}[preset]          # share of the figure's height below the bottom edge of its box
    if wide:
        box_h = H * {"full": 0.80, "three_quarter": 0.84, "waist_up": 0.80}[preset]
        bottom = H * 0.93 if preset == "full" else H
        cx = {"left": 0.21, "right": 0.79, "center": 0.5}[side] * W
        if preset == "waist_up":
            cx = {"left": 0.235, "right": 0.765, "center": 0.5}[side] * W
        col = (0.45 if preset == "waist_up" else 0.40) * W
        content = (col, 0.10 * H, 0.94 * W, 0.84 * H) if side == "left" else (0.06 * W, 0.10 * H, W - col, 0.84 * H) if side == "right" else (0.0, 0.0, 0.0, 0.0)
    else:
        share = (0.44 if ar < 0.7 else 0.50 if ar < 0.9 else 0.56) * {"full": 1.0, "three_quarter": 1.0, "waist_up": 0.92}[preset]
        box_h = H * share
        bottom = H * (0.95 if ar < 0.7 else 0.96) if preset == "full" else H
        cx = {"left": 0.30, "right": 0.70, "center": 0.5}[side] * W
        content = (0.06 * W, 0.07 * H, 0.94 * W, H - box_h - 0.02 * H) if side != "center" else (0.0, 0.0, 0.0, 0.0)
    ppu = box_h / (height_u * (1.0 - cut))
    ground = bottom + cut * height_u * ppu
    return {"ppu": ppu, "x": cx, "ground": ground, "content": content, "preset": preset, "side": side, "lift": 0.14 if preset == "waist_up" else 0.0}
