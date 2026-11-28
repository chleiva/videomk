"""Where characters STAND on a cartoon backdrop (docs/CARTOON_GROUND_2026-11-28.md).

A backdrop of the catalog is a picture; a character is only credible when its feet are on the ground of that picture. Each backdrop therefore carries a STAND ZONE (stored in
`common/vector_stand_zones.json`, and with the catalog item in the bucket's `meta.json`): the walkable ground and the hazards (water, sky, void behind an edge, stairs) as polygons in the
picture's own normalised coordinates (0..1, y down), found offline by backend/scripts/vector_stand_audit.py and checked by eye.

The engine turns a zone into a mask for the shape of the video (the scene is shown as a centre crop in the shapes it was not drawn for, exactly as engine/vector_scene.frame_for does),
shrinks it a little (the scene's slow push-in and parallax move the ground), and places every character FEET ON THE MASK:
  * a standing figure (9:16): the baseline row is searched upward from the nominal floor until every foot fits on the ground, smaller with distance when the ground has depth;
  * a figure cut at the waist (16:9, 1:1, 4:5): its feet are below the frame, so the ground must reach the bottom edge under the figure; the slots move sideways to ground that does;
  * nobody fits -> the backdrop is REFUSED for that cast and shape (`holds` is False): another backdrop is picked, and when none holds the cast the plain background stays.
A backdrop without a usable zone is not offered to characters (it stays for scenes without characters). `violations` is the hard check run on a plan and in the tests: no foot point
outside the ground, none on a hazard.
Pure functions of (zone data, shape, cast size); nothing is fetched at render time.
"""
import json
import math
import os
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ZONES_PATH = os.environ.get("STAND_ZONES_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common", "vector_stand_zones.json")
ASPECT_RATIO = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 0.8}
NATIVE_RATIO = {"16:9": 16 / 9, "9:16": 9 / 16}
PROC_ID = "ground_floor"     # the DRAWN ground (engine/procedural_ground.py): a backdrop type of its own whose zone is stored like any other (native "any": drawn for every shape)
SERVED = {"16:9": ("16:9", "1:1"), "9:16": ("9:16", "4:5"), "any": ("16:9", "9:16", "1:1", "4:5")}   # the video shapes a backdrop is offered for (engine/vector_policy.SCENE_SHAPE): a scene is never stretched to another shape
MASK_W = 192                  # the mask is drawn this wide (the other side follows the shape): 0.5 percent of the width per cell
SNAP_BOTTOM = 0.07           # the same at the bottom: outlines of a model end a little short of the picture edge
SNAP = 0.04                  # ground within this share of the picture edge is taken to reach the edge
ERODE = 0.022                 # the ground shrinks by this share of the frame height: the push-in and the parallax move the picture a little during the scene
HALF_FOOT = 30.0              # design units, at the figure's scale: half the span of the two feet (stance 13 + a shoe)
PITCH = 112.0                 # design units: the smallest distance between two characters' centres (arms and shoulders)
FAR_SCALE_K = 0.9             # a figure whose feet are 0.1 of the height higher in the picture is 9 percent smaller
LOWER = 0.03                  # feet may stand this much lower than the nominal floor (a share of the height): the caption lines begin below it
MIN_SCALE = 0.72
DEPTH_MIN = 0.12              # the ground must be this deep (share of the height) before characters get smaller with distance
MIN_CONTENT = 0.15            # share of the height a standing figure must leave for the card above it


@lru_cache(maxsize=1)
def _data() -> Dict[str, Any]:
    try:
        with open(ZONES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def reload() -> None:
    _data.cache_clear()
    _mask.cache_clear()
    holds.cache_clear()


def entry(scene_id: str) -> Optional[Dict[str, Any]]:
    """The stored zone record of a backdrop, or None when it has none."""
    zs = _data().get("zones")
    e = zs.get(scene_id) if isinstance(zs, dict) else None
    return e if isinstance(e, dict) else None


def disabled(scene_id: str) -> bool:
    e = entry(scene_id)
    return bool(e and e.get("disabled"))


def usable(scene_id: str) -> bool:
    e = entry(scene_id)
    return bool(e and e.get("usable") and not e.get("disabled") and e.get("ground"))


def horizon(aspect: str) -> Optional[float]:
    """Where the drawn ground (PROC_ID) begins in a frame of this shape, as a share of the height; None for a catalog backdrop."""
    e = entry(PROC_ID)
    h = (e or {}).get("horizon")
    return float(h[aspect]) if isinstance(h, dict) and aspect in h else None


def has_line(scene_id: str) -> bool:
    return any(line(scene_id, a) for a in ASPECT_RATIO)


DERIVING = False   # True while the ground lines are being derived from the ground (backend/scripts/vector_stand_build.py): placement then searches freely


def line(scene_id: str, aspect: str) -> Optional[Dict[str, Any]]:
    """The stored IDEAL GROUND LINE of a backdrop for a video shape: {"y": share of the height where the feet sit (1.0: the figure is cut at the waist and the ground must reach the
    bottom edge), "band": [lo, hi] the rows allowed for depth, "figure_h": the figure's height as a share of the frame height at the line, "max_cast": 1..3}. REQUIRED: a backdrop
    without a line for a shape is not eligible for characters in that shape."""
    e = entry(scene_id)
    gl = (e or {}).get("ground_line")
    ln = gl.get(aspect) if isinstance(gl, dict) else None
    if not isinstance(ln, dict) or not isinstance(ln.get("band"), (list, tuple)) or len(ln["band"]) != 2:
        return None
    try:
        return {"y": float(ln["y"]), "band": [float(ln["band"][0]), float(ln["band"][1])], "figure_h": float(ln.get("figure_h", 0.0)), "max_cast": int(ln.get("max_cast", 0)), "casts": [int(c) for c in ln.get("casts", [])]}
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- from the picture's coordinates to the frame's
def _crop(native: str, aspect: str) -> Tuple[float, float, float, float]:
    """The share of the picture a frame shows: (x0, y0, x1, y1), the centre crop that covers the frame."""
    if native == "any":
        return (0.0, 0.0, 1.0, 1.0)
    an, af = NATIVE_RATIO.get(native, 16 / 9), ASPECT_RATIO[aspect]
    if af < an:
        vw = af / an
        return ((1 - vw) / 2, 0.0, (1 + vw) / 2, 1.0)
    vh = an / af
    return (0.0, (1 - vh) / 2, 1.0, (1 + vh) / 2)


@lru_cache(maxsize=1024)
def _mask(scene_id: str, aspect: str) -> Optional[np.ndarray]:
    """Boolean ground mask of the frame (rows x cols), after the hazards are cut out and the edges pulled in. None without a usable zone."""
    e = entry(scene_id)
    if not usable(scene_id) or aspect not in ASPECT_RATIO:
        return None
    native = e.get("native") if e.get("native") in NATIVE_RATIO or e.get("native") == "any" else "16:9"
    x0, y0, x1, y1 = _crop(native, aspect)
    mw = MASK_W
    mh = max(8, int(round(mw / ASPECT_RATIO[aspect])))
    im = Image.new("L", (mw, mh), 0)
    dr = ImageDraw.Draw(im)

    def pts(poly: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:
        return [((float(p[0]) - x0) / (x1 - x0) * mw, (float(p[1]) - y0) / (y1 - y0) * mh) for p in poly]

    def snap(poly: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:   # ground that ends a hair short of the picture edge goes on to it (a model outline is never exact there)
        return [(0.0 if p[0] < SNAP else 1.0 if p[0] > 1 - SNAP else float(p[0]), 1.0 if p[1] > 1 - SNAP_BOTTOM else float(p[1])) for p in poly]

    for poly in (e.get("ground_by_aspect") or {}).get(aspect) or e.get("ground") or []:   # a drawn ground has its own outline per shape
        if len(poly) >= 3:
            dr.polygon(pts(snap(poly)), fill=255)
    for poly in e.get("hazards") or []:
        if len(poly) >= 3:
            dr.polygon(pts(poly), fill=0)
    k = max(1, int(round(ERODE * mh)))
    pad = k + 1
    big = Image.new("L", (mw + 2 * pad, mh + 2 * pad), 0)
    big.paste(im, (pad, pad))
    arr = np.array(big)
    arr[:pad, pad:pad + mw] = arr[pad:pad + 1, pad:pad + mw]          # the frame's edge is not a hazard: the ground carries on beyond it
    arr[pad + mh:, pad:pad + mw] = arr[pad + mh - 1:pad + mh, pad:pad + mw]
    arr[:, :pad] = arr[:, pad:pad + 1]
    arr[:, pad + mw:] = arr[:, pad + mw - 1:pad + mw]
    eroded = Image.fromarray(arr).filter(ImageFilter.MinFilter(2 * k + 1))
    out = np.array(eroded)[pad:pad + mh, pad:pad + mw] > 127
    return out


# ----------------------------------------------------------------------------- placing
def _runs(row: np.ndarray) -> List[Tuple[int, int]]:
    out, start = [], None
    for i, v in enumerate(row):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(row)))
    return out


def feet_on_ground(scene_id: str, aspect: str, x: float, y: float, half: float) -> bool:
    """Are the soles of a figure at (x, y) (frame shares; y >= 1: the feet are below the frame, so the ground must reach the bottom edge there) on the ground, +-half (share of the width)?"""
    m = _mask(scene_id, aspect)
    if m is None:
        return False
    mh, mw = m.shape
    row = min(mh - 1, max(0, int(y * mh))) if y < 1.0 else mh - 1
    a, b = int(math.floor((x - half) * mw)), int(math.ceil((x + half) * mw)) - 1
    if a < 0 or b >= mw:
        return False
    return bool(m[row, a:b + 1].all())


def _fit_row(m: np.ndarray, row: int, prefs: Sequence[float], half: float, pitch: float, max_shift: float) -> Optional[List[float]]:
    """x of every character (shares of the width) on the ground of one row, as near as possible to the preferred slots, kept in order and `pitch` apart; None when they do not fit."""
    mh, mw = m.shape
    half += 1.5 / mw   # the cells under the outer edge of a foot
    runs = [((a / mw) + half, (b / mw) - half) for a, b in _runs(m[row]) if (b - a) / mw > 2 * half]
    if not runs:
        return None
    n = len(prefs)
    xs: List[float] = []
    for p in prefs:
        lo = xs[-1] + pitch if xs else -1.0
        best: Optional[float] = None
        for a, b in runs:
            a2 = max(a, lo)
            if a2 > b + 1e-9:
                continue
            x = min(b, max(a2, p))
            if best is None or abs(x - p) < abs(best - p):
                best = x
        if best is None or abs(best - p) > max_shift + 1e-9:
            xs = []
            break
        xs.append(best)
    if len(xs) == n:
        return xs
    c = sum(prefs) / n   # the greedy order failed: one even row on the widest run that holds them all, centred on the middle of the preferred slots
    cands = []
    for a, b in runs:
        need = (n - 1) * pitch
        if b - a + 1e-9 >= need:
            mid = min(b - need / 2, max(a + need / 2, c))
            row_xs = [mid - need / 2 + i * pitch for i in range(n)]
            if all(abs(x - p) <= max_shift + 1e-9 for x, p in zip(row_xs, sorted(prefs))):
                cands.append((abs(mid - c), row_xs))
    return min(cands)[1] if cands else None


def depth_scale(scene_id: str, aspect: str, y: float, y_pref: float) -> float:
    """How large a figure is at the foot row y against the one at the nominal row: smaller higher up, only where the ground has depth."""
    m = _mask(scene_id, aspect)
    if m is None:
        return 1.0
    rows = np.where(m.any(axis=1))[0]
    if len(rows) == 0 or (rows[-1] - rows[0]) / m.shape[0] < DEPTH_MIN:
        return 1.0
    return max(MIN_SCALE, min(1.0, 1.0 + FAR_SCALE_K * (y - y_pref)))


class Placement:
    """Where the feet go: x shares of the width, `y` the foot row as a share of the height (above 1: below the frame), `scale` against the nominal figure."""

    def __init__(self, xs: List[float], y: float, scale: float):
        self.xs, self.y, self.scale = xs, y, scale

    def __repr__(self) -> str:
        return f"Placement(xs={[round(x, 3) for x in self.xs]}, y={self.y:.3f}, scale={self.scale:.2f})"


def place(scene_id: str, aspect: str, prefs: Sequence[float], *, foot_y: float, ppu: float, W: float, H: float, full: bool, max_shift: float = 0.5,
          accept: Optional[Callable[[float, float], bool]] = None) -> Optional[Placement]:
    """Feet on the ground of `scene_id` for characters whose preferred slots are `prefs` (shares of the width, in screen order).
    foot_y: the nominal foot row (share of the height; above 1 for a figure cut at the waist, whose feet are under the frame). ppu: the figure's scale at that row (design units per drawing unit).
    full: the whole figure is in the frame (its row may move up to find ground; smaller with distance). Otherwise the row stays and only the slots move sideways.
    accept(y, ppu): the layout's last word (room left for the card above the figure). -> None when the backdrop cannot hold them."""
    m = _mask(scene_id, aspect)
    if m is None or not prefs:
        return None
    mh = m.shape[0]
    ln = None if DERIVING else line(scene_id, aspect)
    if not DERIVING and ln is None:
        return None                      # no ground line: not eligible for characters
    if not full:
        half, pitch = HALF_FOOT * ppu / W, PITCH * ppu / W
        xs = _fit_row(m, mh - 1 if foot_y >= 1.0 else max(0, min(mh - 1, int(foot_y * mh))), prefs, half, pitch, max_shift)   # the foot row (below the frame: the bottom edge)
        return Placement(xs, foot_y, 1.0) if xs and (accept is None or accept(foot_y, ppu)) else None
    if ln is not None:   # the feet sit on the line; the band above and below it is the depth the figures may use (nearest to the line first)
        lo, hi = ln["band"]
        steps = sorted({round(lo + i / mh, 5) for i in range(int(round((hi - lo) * mh)) + 1)}, key=lambda v: abs(v - ln["y"]))
        cand = [ln["y"]] + [v for v in steps if abs(v - ln["y"]) > 1e-9]
        ref_y = ln["y"]
    else:
        cand = [foot_y + LOWER - dr / mh for dr in range(int(round((0.40 + LOWER) * mh)) + 1)]   # from a little below the nominal floor (the caption lines start a little lower) upward
        ref_y = foot_y
    for y in cand:
        row = min(mh - 1, max(0, int(y * mh)))
        if y * mh < 2:
            break
        for k in (1.0, 0.9, 0.8):
            s = k * depth_scale(scene_id, aspect, y, ref_y)
            p = ppu * s
            if accept is not None and not accept(y, p):
                continue
            half, pitch = HALF_FOOT * p / W, PITCH * p / W
            xs = _fit_row(m, row, prefs, half, pitch, max_shift)
            if xs:
                return Placement(xs, y, s)
    return None


# ----------------------------------------------------------------------------- the question the planner asks, and the hard check
def _cast_props(scene_id: str, n: int) -> Dict[str, Any]:
    ids = ("fox", "bear", "owl")[:max(1, n)]
    return {"character": ids[0], "side": "left", "backdrop": scene_id, **({"cast": list(ids)} if n >= 2 else {})}


def layout_for(props: Dict[str, Any], aspect: str, captions: bool = True) -> Dict[str, Any]:
    """The real presenter layout (the one the renderer uses) for these props, in a frame of this shape."""
    from types import SimpleNamespace

    from .frame import Frame
    from .scenes.elements import presenter as pe

    fr = Frame.parse(aspect, "1080p")
    ctx = SimpleNamespace(frame=fr, captions=captions, top=fr.margin_top, bottom=fr.content_bottom(captions), box=fr.box(captions))
    return pe.layout(props, ctx)


@lru_cache(maxsize=4096)
def holds(scene_id: str, aspect: str, n: int, captions: bool = True) -> bool:
    """May `n` characters (1 to 3) stand on this backdrop in a video of this shape? Uses the layout the renderer uses, so the answer cannot drift from what is drawn."""
    if not usable(scene_id) or aspect not in ASPECT_RATIO:
        return False
    ln = line(scene_id, aspect)
    if ln is None or n not in (ln.get("casts") or range(1, ln["max_cast"] + 1)):
        return False
    try:
        return not layout_for(_cast_props(scene_id, n), aspect, captions).get("unplaced")
    except Exception:  # noqa: BLE001 - a backdrop that cannot be tested is not offered
        return False


def derive_lines(scene_id: str) -> Dict[str, Dict[str, Any]]:
    """Derive the ground line of every shape from the ground mask with the engine's own placement (free search; the result is what `line` stores). A shape the ground cannot serve
    gets no entry."""
    global DERIVING
    out: Dict[str, Dict[str, Any]] = {}
    DERIVING = True
    try:
        native = (entry(scene_id) or {}).get("native", "16:9")
        for asp in SERVED[native]:
            m = _mask(scene_id, asp)
            if m is None:
                continue
            best, casts = None, []
            for n in (3, 2, 1):
                try:
                    lay = layout_for(_cast_props(scene_id, n), asp)
                except Exception:  # noqa: BLE001
                    continue
                if not lay.get("unplaced"):
                    best = best or (n, lay)
                    casts.append(n)
            if best is None:
                continue
            n, lay = best
            from .frame import Frame

            fr = Frame.parse(asp, "1080p")
            fig = (lay.get("figures") or [lay])[0]
            y = lay["ground"] / fr.H
            ppu = fig["ppu"]
            if lay.get("floor") is None:   # cut at the waist: the feet are under the frame or under the captions; the ground must be there, and carry on to the bottom edge
                mh = m.shape[0]
                xs = [(f["x"] / fr.W) for f in (lay.get("figures") or [lay])]
                yf = min(y, 1.0)
                row0 = mh - 1 if yf >= 1.0 else max(0, min(mh - 1, int(yf * mh)))

                def ok_row(r: int) -> bool:
                    return all(m[r, max(0, int((x - 0.03) * m.shape[1])):int((x + 0.03) * m.shape[1]) + 1].all() for x in xs)

                lo_row = row0
                while lo_row > 0 and ok_row(lo_row - 1):
                    lo_row -= 1
                hi_row = row0
                while hi_row < mh - 1 and ok_row(hi_row + 1):
                    hi_row += 1
                hi = 1.0 if hi_row >= mh - 1 else (hi_row + 1) / mh
                ys = [yf]   # a smaller cast stands on another row (the layouts differ): the band holds all of them
                for k in [c for c in casts if c != n]:
                    try:
                        lk = layout_for(_cast_props(scene_id, k), asp)
                    except Exception:  # noqa: BLE001
                        continue
                    if not lk.get("unplaced"):
                        ys.append(min(lk["ground"] / fr.H, 1.0))
                out[asp] = {"y": round(yf, 4), "band": [round(min(lo_row / mh, min(ys)), 4), round(max(hi, max(ys)), 4)], "figure_h": round(290.0 * ppu / fr.H, 4), "max_cast": n, "casts": sorted(casts)}
            else:
                mh = m.shape[0]
                half, pitch = HALF_FOOT * ppu / fr.W, PITCH * ppu / fr.W
                lo = hi = y
                while lo - 1 / mh >= y - 0.10 and _fit_row(m, int((lo - 1 / mh) * mh), [fig["x"] / fr.W], half, pitch, 1.0):
                    lo -= 1 / mh
                while hi + 1 / mh <= min(y + 0.02, 0.999) and _fit_row(m, int((hi + 1 / mh) * mh), [fig["x"] / fr.W], half, pitch, 1.0):
                    hi += 1 / mh
                out[asp] = {"y": round(y, 4), "band": [round(lo, 4), round(hi, 4)], "figure_h": round(290.0 * ppu / fr.H, 4), "max_cast": n, "casts": sorted(casts)}
    finally:
        DERIVING = False
    return out


def max_cast(scene_id: str, aspect: str) -> int:
    return max([n for n in (1, 2, 3) if holds(scene_id, aspect, n)] or [0])


def capable(aspect: str, n: int, ids: Optional[Sequence[str]] = None) -> List[str]:
    """Every catalog backdrop (or those of `ids`) that can hold a cast of `n` in this shape, sorted by id; the drawn ground is not among them (it is the last resort, never a pick)."""
    pool = list(ids) if ids is not None else sorted((_data().get("zones") or {}))
    return [s for s in pool if s != PROC_ID and holds(s, aspect, n)]


def eligible(scene_ids: Sequence[str], aspect: str, n: int) -> List[str]:
    """The backdrops among `scene_ids` (order kept) that can hold a cast of `n` in a video of this shape."""
    return [s for s in scene_ids if holds(s, aspect, n)]


def foot_points(props: Dict[str, Any], aspect: str, captions: bool = True) -> List[Tuple[float, float]]:
    """Where the soles of the characters of a presenter scene are, in shares of the frame (y above 1: below the frame)."""
    lay = layout_for(props, aspect, captions)
    from .frame import Frame

    fr = Frame.parse(aspect, "1080p")
    figs = lay.get("figures") or [{"x": lay["x"], "ground": lay["ground"]}]
    return [(f["x"] / fr.W, f["ground"] / fr.H) for f in figs]


def violations(plan: Dict[str, Any], aspect: str) -> List[Dict[str, Any]]:
    """The hard check: for every presenter scene of the plan with a backdrop, every foot point lies on the ground of that backdrop (and on no hazard); a backdrop that has no
    usable zone for characters, or cannot hold the cast, is a violation too. -> [{beat, backdrop, why}] (empty = fine)."""
    out: List[Dict[str, Any]] = []
    for i, b in enumerate(plan.get("beats") or []):
        sc = b.get("scene") or {}
        p = sc.get("props") or {}
        bd = p.get("backdrop")
        if sc.get("type") != "presenter" or not bd:
            continue
        if disabled(bd):
            out.append({"beat": i, "backdrop": bd, "why": "retired"})
            continue
        if not usable(bd):
            out.append({"beat": i, "backdrop": bd, "why": "no usable stand zone"})
            continue
        try:
            lay = layout_for(p, aspect)
        except Exception as e:  # noqa: BLE001
            out.append({"beat": i, "backdrop": bd, "why": f"layout failed {type(e).__name__}"})
            continue
        if lay.get("unplaced"):
            out.append({"beat": i, "backdrop": bd, "why": "the cast does not fit the ground"})
            continue
        from .frame import Frame

        fr = Frame.parse(aspect, "1080p")
        ppu = lay["ppu"] if not lay.get("figures") else lay["figures"][0]["ppu"]
        half = HALF_FOOT * ppu / fr.W
        for x, y in foot_points(p, aspect):
            if not feet_on_ground(bd, aspect, x, y, half):
                out.append({"beat": i, "backdrop": bd, "why": f"foot point ({x:.3f}, {y:.3f}) is not on the ground"})
            ln = line(bd, aspect)
            if ln is None or not (ln["band"][0] - 1e-3 <= min(y, 1.0) <= ln["band"][1] + 1e-3):
                out.append({"beat": i, "backdrop": bd, "why": f"foot Y {y:.3f} is outside the ground line band {ln['band'] if ln else None}"})
    return out


def strip_violations(plan: Dict[str, Any], aspect: str) -> List[Dict[str, Any]]:
    """Plan repair: a backdrop that fails the check is taken off that scene (the plain background stays); returns what was taken off."""
    bad = violations(plan, aspect)
    for v in bad:
        sc = plan["beats"][v["beat"]].get("scene") or {}
        (sc.get("props") or {}).pop("backdrop", None)
    return bad
