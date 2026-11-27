"""Motion tags for the layered vector scenes (docs/VECTOR_SCENES.md, docs/VECTOR_CATALOG.md): things that look like they should move DO move.

A scene layer may carry `tags`, a list of dicts `{"type": ..., ...}`. This module turns the tags of one layer into ONE transform for a time `t`, as pure
functions of (t, dur, params), so a chunk rendered anywhere is identical. Everything cycles an INTEGER number of times over the scene (`dur`), so the last frame
meets the first one and a replayed or cross-faded scene never jumps.

Tag types and their parameters (`period` is the wanted seconds per cycle, rounded to a whole number of cycles over `dur`; `phase` is in turns, 0..1;
`pivot` is [u, v] in PICTURE coordinates, 0..1, the point the layer turns around):
  rotate   {pivot, period, dir=1}                        turbine blades, fans, wheels, gears: constant turn
  wiggle   {pivot, deg, period, phase}                   fish tails, flags, laundry, antennas: swing +-deg around the pivot
  bob      {amp, period, phase}                          boats, floating things: vertical sine, `amp` is a share of the frame height
  drift    {vx, vy=0, mode="pingpong"|"linear"|"wrap"}   boats, fish, birds, trains, cars, planes: travel across, shares of the frame width/height over the scene;
                                                         pingpong returns to the start (loop-safe), linear keeps going, wrap re-enters (needs a margin)
  flicker  {min=0.55, period, phase}                     flames, lamps, neon: opacity wobbles (sum of two sines)
  twinkle  {min=0.3, period, phase}                      stars, window lights: opacity pulses
  rise     {amp, period, phase, grow=0.15}               smoke, steam, rising balloons: climbs a share `amp` of the height, grows, fades in and out (zero opacity at the wrap)
Unknown tags and bad values are ignored (a layer without valid tags is drawn exactly as before).
"""
import math
from typing import Any, Dict, List, Optional

TAU = 2 * math.pi
KINDS = ("rotate", "wiggle", "bob", "drift", "flicker", "twinkle", "rise")


def cycles(period: float, dur: float) -> int:
    """whole cycles over the scene: at least 1, nearest to dur/period, so the motion closes on itself."""
    try:
        return max(1, int(round(dur / max(float(period), 1e-3))))
    except (TypeError, ValueError):
        return 1


def _num(x: Any, default: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return min(hi, max(lo, v))


def clean_tag(tag: Any) -> Optional[Dict[str, Any]]:
    """validated copy of a tag, or None. Used when a manifest is read, so a bad catalog file never reaches the renderer."""
    if not isinstance(tag, dict) or tag.get("type") not in KINDS:
        return None
    k = tag["type"]
    out: Dict[str, Any] = {"type": k}
    out["period"] = _num(tag.get("period"), 6.0, 0.2, 600.0)
    out["phase"] = _num(tag.get("phase"), 0.0, 0.0, 1.0)
    if k in ("rotate", "wiggle"):
        pv = tag.get("pivot")
        if not (isinstance(pv, (list, tuple)) and len(pv) == 2):
            return None
        out["pivot"] = [_num(pv[0], 0.5, 0.0, 1.0), _num(pv[1], 0.5, 0.0, 1.0)]
    if k == "rotate":
        out["dir"] = -1 if _num(tag.get("dir"), 1, -1, 1) < 0 else 1
    elif k == "wiggle":
        out["deg"] = _num(tag.get("deg"), 6.0, 0.0, 45.0)
    elif k == "bob":
        out["amp"] = _num(tag.get("amp"), 0.004, 0.0, 0.1)
    elif k == "drift":
        out["vx"] = _num(tag.get("vx"), 0.05, -2.0, 2.0)
        out["vy"] = _num(tag.get("vy"), 0.0, -2.0, 2.0)
        out["mode"] = tag.get("mode") if tag.get("mode") in ("pingpong", "linear", "wrap") else "pingpong"
    elif k in ("flicker", "twinkle"):
        out["min"] = _num(tag.get("min"), 0.55 if k == "flicker" else 0.3, 0.0, 1.0)
    elif k == "rise":
        pv = tag.get("pivot")
        if isinstance(pv, (list, tuple)) and len(pv) == 2:
            out["pivot"] = [_num(pv[0], 0.5, 0.0, 1.0), _num(pv[1], 0.5, 0.0, 1.0)]
        out["amp"] = _num(tag.get("amp"), 0.12, 0.0, 1.0)
        out["grow"] = _num(tag.get("grow"), 0.15, 0.0, 1.0)
    return out


def clean_tags(tags: Any) -> List[Dict[str, Any]]:
    return [t for t in (clean_tag(x) for x in (tags if isinstance(tags, list) else [])) if t]


def _tri(x: float) -> float:
    """triangle wave 0 -> 1 -> 0 over x in [0, 1]"""
    x = x % 1.0
    return 1.0 - abs(2 * x - 1)


def layer_transform(tags: List[Dict[str, Any]], t: float, dur: float) -> Optional[Dict[str, float]]:
    """Combine the tags of one layer for time t. Returns None when there is nothing to do, else
    dict(dx, dy (shares of frame width/height), rot (radians, about pivot), pivot (u, v) or None, alpha (0..1), scale)."""
    tags = clean_tags(tags)
    if not tags:
        return None
    d = max(float(dur), 1e-6)
    x = min(1.0, max(0.0, t / d))        # progress over the scene: 0..1
    out = dict(dx=0.0, dy=0.0, rot=0.0, pivot=None, alpha=1.0, scale=1.0)
    for tg in tags:
        k = tg["type"]
        n = cycles(tg["period"], d)
        ang = TAU * (n * x + tg["phase"])
        if k == "rotate":
            out["rot"] += tg["dir"] * TAU * (n * x + tg["phase"])
            out["pivot"] = tuple(tg["pivot"])
        elif k == "wiggle":
            out["rot"] += math.radians(tg["deg"]) * math.sin(ang)
            out["pivot"] = tuple(tg["pivot"])
        elif k == "bob":
            out["dy"] += tg["amp"] * math.sin(ang)
        elif k == "drift":
            mode = tg["mode"]
            if mode == "pingpong":
                f = _tri(x) - 0.5
            elif mode == "wrap":
                f = (x * (n if n > 1 else 1)) % 1.0 - 0.5
            else:
                f = x - 0.5
            out["dx"] += tg["vx"] * f * (2 if mode == "pingpong" else 1)
            out["dy"] += tg["vy"] * f * (2 if mode == "pingpong" else 1)
        elif k == "flicker":
            w = 0.5 + 0.5 * (0.6 * math.sin(ang) + 0.4 * math.sin(3 * ang + 1.3))
            out["alpha"] *= tg["min"] + (1 - tg["min"]) * w
        elif k == "twinkle":
            w = 0.5 + 0.5 * math.sin(ang)
            out["alpha"] *= tg["min"] + (1 - tg["min"]) * w * w
        elif k == "rise":
            f = (n * x + tg["phase"]) % 1.0
            out["dy"] -= tg["amp"] * f
            out["scale"] *= 1.0 + tg["grow"] * f
            out["alpha"] *= math.sin(math.pi * f) ** 1.5      # zero at both ends: the wrap is invisible
            if isinstance(tg.get("pivot"), list) and len(tg["pivot"]) == 2 and out["pivot"] is None:
                out["pivot"] = (tg["pivot"][0], tg["pivot"][1])     # a plume grows from its base
    return out


def affine(tr: Dict[str, float], *, W: int, H: int, cw: int, ch: int, rs: float, margin: float, s: float, tx: float, ty: float) -> tuple:
    """PIL AFFINE coefficients (output pixel -> raster pixel) for one layer: the parallax/push map used by vector_scene.frame (scale s, translation tx, ty in frame px)
    plus the tag transform (rotation about the pivot, extra translation, scale about the pivot or the frame centre).
    The picture fills the raster (cw x ch); the frame shows its middle 1/margin, so picture (u, v) sits at frame W/2 + (u - .5) W margin, H/2 + (v - .5) H margin."""
    cxf, cyf = W / 2.0, H / 2.0
    tx = tx + tr["dx"] * W
    ty = ty + tr["dy"] * H
    th = tr["rot"]
    c, sn = math.cos(-th), math.sin(-th)
    piv = tr.get("pivot")
    if piv:
        px, py = cxf + (piv[0] - 0.5) * W * margin, cyf + (piv[1] - 0.5) * H * margin
    else:
        px, py = cxf, cyf
    sig = tr.get("scale", 1.0) or 1.0
    k = rs / (s * sig)
    A = ((k * c, -k * sn), (k * sn, k * c))          # (RS / s) * R(-theta)
    # raster = R0 + RS (p - C) + RS R(-theta)(C - p) + A (o - C - t)
    r0x, r0y = cw / 2.0, ch / 2.0
    cpx, cpy = cxf - px, cyf - py
    kx = r0x + rs * (px - cxf) + (rs / sig) * (c * cpx - sn * cpy) - (A[0][0] * (cxf + tx) + A[0][1] * (cyf + ty))
    ky = r0y + rs * (py - cyf) + (rs / sig) * (sn * cpx + c * cpy) - (A[1][0] * (cxf + tx) + A[1][1] * (cyf + ty))
    return (A[0][0], A[0][1], kx, A[1][0], A[1][1], ky)
