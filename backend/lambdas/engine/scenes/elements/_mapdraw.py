"""The map scene: model (everything that depends only on the props: projection, projected geometry, camera, label layout) and frame painting (camera, reveals).

`build_model` is cached on the props, so a frame only transforms already-projected geometry by the camera and paints the parts that are animating. Once the camera has settled the
base map (ocean, land, borders) is itself cached as an image per theme.
"""
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ...canvas import Canvas, load_font, partial_polyline, with_alpha
from ...easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress
from ...theme import Theme
from . import _geo, _project as P, _resolve as R

PANEL_X, PANEL_W = 110, 1700
PANEL_TOP = 84
CAM_SECONDS = 1.5
CAM_START = 0.80                 # the camera starts this fraction of the way in and eases to the fit
FIT_ALL = {"RUS", "FJI", "KIR"}  # countries whose far parts are part of the country picture (the Russian Far East crosses the antimeridian)
LABEL_PX_, SUB_PX_, TITLE_PX, CAPTION_PX, NOTE_PX = 40, 30, 52, 30, 24
LABEL_PX, SUB_PX = LABEL_PX_, SUB_PX_
_PIN_R = 12

Color = Tuple[int, ...]


# ----------------------------------------------------------------------------- palette
def _mix(a: Color, b: Color, t: float) -> Tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


@dataclass(frozen=True)
class Palette:
    void: Color        # outside the globe / the world's edge
    ocean: Color
    land: Color
    border: Color
    coast: Color
    grat: Color        # graticule (alpha applied at draw)
    grat_a: float


def palette(th: Theme) -> Palette:
    if th.name == "paper":
        return Palette((234, 228, 218), (214, 228, 242), (252, 249, 242), (186, 176, 160), (150, 160, 176), (31, 41, 55), 0.07)
    if th.name == "sunrise":
        return Palette((24, 12, 50), (44, 24, 92), (104, 58, 124), (176, 118, 168), (150, 102, 160), (255, 255, 255), 0.07)
    return Palette((7, 10, 24), (15, 27, 58), (43, 56, 98), (96, 111, 156), (74, 90, 138), (255, 255, 255), 0.06)


# ----------------------------------------------------------------------------- model
@dataclass
class Item:
    kind: str                                  # "region" | "pin"
    name: str
    sub: str = ""
    idx: int = 0                               # position in the reveal order (cue index)
    polys: List[Tuple[np.ndarray, bool]] = field(default_factory=list)   # plane polygons (ring, is_hole) for a region
    anchor: Optional[Tuple[float, float]] = None                         # plane position of the pin / the region's label point
    soft: bool = False                         # a focus highlight: calmer than a "regions" highlight
    label_off: Tuple[float, float] = (0.0, 0.0)  # top-left of the label block relative to the anchor (screen px at the final camera)
    label_wh: Tuple[float, float] = (0.0, 0.0)
    small: bool = False                        # route/arc endpoint pins are smaller


@dataclass
class Path:
    pts: np.ndarray                            # plane polyline
    a: int                                     # index of the item it starts at (in model.pins)
    b: int
    idx: int                                   # reveal index
    label: str = ""
    label_anchor: Optional[Tuple[float, float]] = None
    label_off: Tuple[float, float] = (0.0, 0.0)
    label_wh: Tuple[float, float] = (0.0, 0.0)


@dataclass
class Model:
    key: str
    mode: str
    pw: int
    ph: int
    proj: P.Proj
    level: str
    land: List[Tuple[np.ndarray, Tuple[float, float, float, float], bool]]
    borders: List[Tuple[np.ndarray, Tuple[float, float, float, float]]]
    adm1: List[Tuple[np.ndarray, Tuple[float, float, float, float]]]
    grat: List[np.ndarray]
    outline: np.ndarray
    regions: List[Item]
    pins: List[Item]
    paths: List[Path]
    n_cues: int
    cam_end: Tuple[float, float, float]        # plane centre x, y and scale (px per plane unit)
    centre_px: Tuple[float, float]             # where the camera centre sits in the panel
    title: str
    caption: str
    note: bool
    chip: Tuple[float, float, float, float]    # title chip rect (panel px) or zeros
    foot: Tuple[float, float, float, float]    # caption chip rect
    note_pos: Tuple[float, float]
    notes: List[str] = field(default_factory=list)
    k: float = 1.0                             # type scale of the frame (1.0 landscape): labels, pins and chips grow on narrower frames
    landscape: bool = True
    title_size: float = TITLE_PX
    title_lines: List[str] = field(default_factory=list)
    foot_size: float = CAPTION_PX
    foot_lines: List[str] = field(default_factory=list)
    note_size: float = NOTE_PX
    y_off: float = 0.0                         # vertical shift of a shortened panel inside the box (world maps on tall frames)
    ph_box: int = 0                            # the box height the model was asked for
    need_h: float = 0.0                        # panel height the fitted map needs


def _measure(text: str, weight: str, size: float) -> float:
    return load_font(weight, int(round(size * 2))).getlength(text) / 2.0


def _fit_lines(text: str, weight: str, size: float, max_w: float, min_size: float, max_lines: int = 2) -> Tuple[float, List[str]]:
    """The largest size (down to `min_size`) at which `text` fits `max_w` in at most `max_lines` lines (greedy word wrap); a single line is preferred to a smaller wrapped size."""
    words = text.split()
    sz = size
    while True:
        if _measure(text, weight, sz) <= max_w:
            return sz, [text]
        lines: List[str] = []
        cur = ""
        for w in words:
            t = (cur + " " + w).strip()
            if cur and _measure(t, weight, sz) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
        if len(lines) <= max_lines and all(_measure(l, weight, sz) <= max_w for l in lines):
            return sz, lines
        if sz <= min_size:
            return sz, lines[:max_lines]
        sz = max(min_size, sz - 2)


def _bbox(a: np.ndarray) -> Tuple[float, float, float, float]:
    return (float(a[:, 0].min()), float(a[:, 1].min()), float(a[:, 0].max()), float(a[:, 1].max()))


def role_of(mode: str, field_name: str) -> str:
    if field_name == "regions":
        return "shape"
    if field_name == "focus":
        return "any"
    return "point"


def entity_key(role: str, name: str) -> str:
    return f"{role}|{name}"


def _ents(spec: Dict[str, Any], role: str, name: str) -> Optional[R.Entity]:
    got = (spec.get("resolved") or {}).get(entity_key(role, name))
    if isinstance(got, dict) and got.get("t"):
        return got
    try:
        return R.resolve(name, role, allow_network=False)
    except R.ResolveError:
        return None


@lru_cache(maxsize=1)
def _id_index() -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for nm, col in (("adm0_50", _geo.A0_ID), ("adm0_110", _geo.A0_ID), ("adm1", _geo.A1_ID)):
        out[nm] = {m[col]: i for i, m in enumerate(_geo.layer(nm).meta)}
    return out


def _entity_rings(e: R.Entity) -> List[Tuple[np.ndarray, bool]]:
    name = "adm0_50" if e["t"] == "country" else "adm1"
    fi = _id_index()[name].get(e["id"])
    return [] if fi is None else _geo.layer(name).rings_of(fi)


def _label_point(e: R.Entity) -> Optional[Tuple[float, float]]:
    if e["t"] == "country":
        fi = _id_index()["adm0_50"].get(e["id"])
        if fi is not None:
            m = _geo.layer("adm0_50").meta[fi]
            return float(m[_geo.A0_LX]), float(m[_geo.A0_LY])
    if e["t"] == "admin1":
        fi = _id_index()["adm1"].get(e["id"])
        if fi is not None:
            m = _geo.layer("adm1").meta[fi]
            return float(m[_geo.A1_LX]), float(m[_geo.A1_LY])
    return None


def _main_rings(e: R.Entity, rings: List[Tuple[np.ndarray, bool]]) -> List[np.ndarray]:
    """The rings that count when framing a country: the biggest one and what lies near it (France without Guiana, the USA without Alaska), unless the whole country is the picture."""
    ext = [(r, _geo.ring_area_km2_like(r)) for r, h in rings if not h]
    if not ext:
        return []
    if e.get("id") in FIT_ALL:
        return [r for r, _ in ext]
    big = max(ext, key=lambda t: t[1])[0]
    box = lambda r: (float(r[:, 0].min()), float(r[:, 1].min()), float(r[:, 0].max()), float(r[:, 1].max()))  # noqa: E731
    boxes = {id(r): box(r) for r, _ in ext}

    def gap(a, b):
        dx = max(a[0] - b[2], b[0] - a[2], 0.0)
        dy = max(a[1] - b[3], b[1] - a[3], 0.0)
        return math.hypot(dx, dy)

    keep = [big]
    todo = [r for r, _ in ext if r is not big]
    grew = True
    while grew:                                   # single linkage: a ring joins when it lies within 5 degrees of one already in
        grew = False
        for r in list(todo):
            if any(gap(boxes[id(r)], boxes[id(k)]) < 5.0 for k in keep):
                keep.append(r)
                todo = [x for x in todo if x is not r]
                grew = True
    return keep


def _thin(a: np.ndarray, n: int = 400) -> np.ndarray:
    return a if len(a) <= n else a[:: max(1, len(a) // n)]


def _circ_extent(lons: np.ndarray) -> Tuple[float, float]:
    """(centre, span) of the shortest arc of longitudes that holds all of them."""
    u = np.unique(np.round(np.asarray(lons, np.float64) % 360.0, 1))
    if len(u) == 1:
        return float(u[0] if u[0] <= 180 else u[0] - 360), 0.0
    gaps = np.diff(np.concatenate([u, [u[0] + 360.0]]))
    k = int(np.argmax(gaps))
    start = u[(k + 1) % len(u)]
    span = 360.0 - float(gaps[k])
    c = start + span / 2.0
    return float((c + 180.0) % 360.0 - 180.0), float(span)


def choose_projection(lonlat: np.ndarray) -> Tuple[P.Proj, str, float]:
    """Projection by extent: Equal Earth for the whole world, an orthographic globe for continents, Albers conic (Mercator near the equator or for small areas) for countries."""
    c_lon, span_lon = _circ_extent(lonlat[:, 0])
    lat_lo, lat_hi = float(lonlat[:, 1].min()), float(lonlat[:, 1].max())
    c_lat = (lat_lo + lat_hi) / 2.0
    span_lat = lat_hi - lat_lo
    s = max(span_lat, span_lon * math.cos(math.radians(c_lat)))
    maxd = max(P.angular_distance_deg(c_lon, c_lat, lo, la) for lo, la in lonlat[:: max(1, len(lonlat) // 300)])
    if span_lon >= 200 or s >= 130 or maxd > 76:
        return P.Proj("equalearth", lon0=c_lon), "110", s
    if s > 52:
        return P.Proj("ortho", lon0=c_lon, lat0=max(-70.0, min(70.0, c_lat))), "50", s
    if abs(c_lat) < 14 or span_lat < 3.0:
        return P.Proj("mercator", lon0=c_lon), "50", s
    p1, p2 = lat_lo + span_lat / 6.0, lat_hi - span_lat / 6.0
    if abs(math.sin(math.radians(p1)) + math.sin(math.radians(p2))) < 0.25:
        return P.Proj("mercator", lon0=c_lon), "50", s
    return P.Proj("albers", lon0=c_lon, lat0=c_lat, phi1=p1, phi2=p2), "50", s


def _ring_in_window(bb: np.ndarray, proj: P.Proj, c_lat: float, half_lon: float, half_lat: float) -> bool:
    if proj.kind == "equalearth":
        return True
    cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    if proj.kind == "ortho":
        d = P.angular_distance_deg(proj.lon0, proj.lat0, cx, cy)
        return d - max(bb[2] - bb[0], bb[3] - bb[1]) * 0.75 < 100
    rel = abs(float(P.wrap_deg(cx - proj.lon0)))
    return (rel - (bb[2] - bb[0]) / 2.0 <= half_lon) and (cy - (bb[3] - bb[1]) / 2.0 <= c_lat + half_lat) and (cy + (bb[3] - bb[1]) / 2.0 >= c_lat - half_lat)


def _project_layer(layer: _geo.Layer, proj: P.Proj, c_lat: float, half_lon: float, half_lat: float, holes: bool = True, exterior_only: bool = False):
    out = []
    for r in range(layer.n_rings):
        hole = bool(layer.hole[r])
        if hole and not holes:
            continue
        if not _ring_in_window(layer.bbox[r], proj, c_lat, half_lon, half_lat):
            continue
        for piece in proj.ring_pieces(layer.ring(r)):
            if len(piece) >= 3:
                out.append((piece.astype(np.float32), _bbox(piece), hole))
    return out


def _arc_plane(proj: P.Proj, a: Tuple[float, float], b: Tuple[float, float]) -> np.ndarray:
    """A great-circle arc in plane coordinates, lifted a little so even a short hop reads as a curve."""
    gc = P.great_circle(a[0], a[1], b[0], b[1])
    pieces = proj.line_pieces(gc)
    if not pieces:
        return np.zeros((0, 2))
    pts = max(pieces, key=len)
    chord = pts[-1] - pts[0]
    L = float(np.hypot(*chord))
    if L < 1e-9:
        return pts
    n = np.array([-chord[1], chord[0]]) / L
    d = (pts - pts[0]) @ n
    sag = float(np.abs(d).max())
    t = np.linspace(0.0, 1.0, len(pts))
    lift = max(0.0, 0.13 * L - sag)
    sign = 1.0 if (d.mean() >= 0 and sag > 1e-6) or sag <= 1e-6 else -1.0
    return pts + (np.sin(np.pi * t) * lift * sign)[:, None] * n[None, :]


def _intersect(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _place_labels(m: Model, tf) -> None:
    PIN_R = _PIN_R * m.k
    """Choose, once, where each label sits relative to its pin or region (at the final camera), avoiding other labels, pins, the title and the footer."""
    safe = (16.0, 16.0, m.pw - 16.0, m.ph - 16.0)
    obstacles: List[Tuple[float, float, float, float]] = []
    for r in (m.chip, m.foot):
        if r[2] > r[0]:
            obstacles.append(r)
    pins_px = []
    for it in m.pins:
        if it.anchor is None:
            continue
        x, y = tf(it.anchor)
        rr = PIN_R * (0.7 if it.small else 1.0) + 6
        pins_px.append((x, y, rr))
        obstacles.append((x - rr, y - rr, x + rr, y + rr))

    def best(cands: List[Tuple[float, float, float, float]]) -> int:
        scores = []
        for k, c in enumerate(cands):
            sc = sum(_intersect(c, o) for o in obstacles) + k * 0.5
            out = (c[2] - c[0]) * (c[3] - c[1]) - _intersect(c, safe)
            scores.append(sc + out * 50)
        return int(np.argmin(scores))

    def box_for(it_w: float, it_h: float, ax: float, ay: float, pin: bool, r: float):
        if pin:
            g = r + 10
            offs = [(g, -it_h / 2), (-g - it_w, -it_h / 2), (-it_w / 2, -g - it_h), (-it_w / 2, g), (g * 0.6, -g * 0.6 - it_h), (-g * 0.6 - it_w, -g * 0.6 - it_h),
                    (g * 0.6, g * 0.6), (-g * 0.6 - it_w, g * 0.6)]
        else:
            offs = [(-it_w / 2, -it_h / 2), (-it_w / 2, -it_h * 1.5), (-it_w / 2, it_h * 0.5), (-it_w / 2 - it_w * 0.4, -it_h / 2), (-it_w / 2 + it_w * 0.4, -it_h / 2)]
        return offs

    # regions first (they sit on the shapes), then pins
    for it in m.regions:
        if it.anchor is None:
            continue
        ax, ay = tf(it.anchor)
        w, h = it.label_wh
        offs = box_for(w, h, ax, ay, False, 0)
        cands = [(ax + dx, ay + dy, ax + dx + w, ay + dy + h) for dx, dy in offs]
        k = best(cands)
        it.label_off = offs[k]
        obstacles.append(cands[k])
    for it in m.pins:
        if it.anchor is None:
            continue
        ax, ay = tf(it.anchor)
        w, h = it.label_wh
        r = PIN_R * (0.7 if it.small else 1.0)
        offs = box_for(w, h, ax, ay, True, r)
        cands = [(ax + dx, ay + dy, ax + dx + w, ay + dy + h) for dx, dy in offs]
        k = best(cands)
        it.label_off = offs[k]
        obstacles.append(cands[k])
    for pth in m.paths:
        if not pth.label or pth.label_anchor is None:
            continue
        ax, ay = tf(pth.label_anchor)
        w, h = pth.label_wh
        offs = [(-w / 2, -h - 8), (-w / 2, 8), (-w / 2 - w * 0.6, -h / 2), (-w / 2 + w * 0.6, -h / 2)]
        cands = [(ax + dx, ay + dy, ax + dx + w, ay + dy + h) for dx, dy in offs]
        k = best(cands)
        pth.label_off = offs[k]
        obstacles.append(cands[k])


@lru_cache(maxsize=6)
def build_model(key: str, pw: int, ph: int, ts: float = 1.0, wide: bool = True) -> Model:
    """The model for a panel of pw x ph. A world map (Equal Earth, 2:1) on a tall frame gets a panel only as tall as the map needs, centred in the box."""
    m = _build_model(key, pw, ph, ts, wide)
    m.ph_box = ph
    if not wide and m.proj.kind == "equalearth":
        ph2 = int(min(ph, max(m.need_h + 30, 0.5 * ph)))
        if ph2 < ph - 60:
            m = _build_model(key, pw, ph2, ts, wide)
            m.ph_box, m.y_off = ph, (ph - ph2) / 2.0
    return m


def _build_model(key: str, pw: int, ph: int, ts: float = 1.0, wide: bool = True) -> Model:
    LABEL_PX, SUB_PX = LABEL_PX_ * ts, SUB_PX_ * ts
    spec = json.loads(key)
    mode = spec["mode"]
    notes: List[str] = []
    fit: List[np.ndarray] = []          # lon/lat points that must be in view
    min_span_deg = 2.0

    # ---- entities
    regions_e: List[Tuple[int, str, R.Entity, bool]] = []
    pins_e: List[Tuple[int, str, str, R.Entity, bool]] = []
    route_e: List[int] = []
    arcs_e: List[Tuple[int, int, int, str]] = []

    def pin_entity(name: str, sub: str = "", idx: int = 0, small: bool = False) -> Optional[int]:
        e = _ents(spec, "point", name)
        if e is None or e["t"] != "point":
            notes.append(f"unresolved {name}")
            return None
        pins_e.append((idx, name, sub, e, small))
        fit.append(np.array([[e["lon"], e["lat"]]]))
        return len(pins_e) - 1

    if mode == "regions":
        for i, name in enumerate(spec.get("regions", [])):
            e = _ents(spec, "shape", name)
            if e is None or e["t"] not in ("country", "admin1"):
                notes.append(f"unresolved {name}")
                continue
            regions_e.append((i, name, e, False))
    elif mode == "focus":
        only = len(spec.get("focus", [])) == 1
        for i, name in enumerate(spec.get("focus", [])):
            e = _ents(spec, "any", name)
            if e is None:
                notes.append(f"unresolved {name}")
                continue
            if e["t"] in ("country", "admin1"):
                regions_e.append((0 if only else i, name, e, True))
            elif e["t"] == "point":
                pins_e.append((0 if only else i, name, "", e, False))
                fit.append(np.array([[e["lon"], e["lat"]]]))
            elif e["t"] == "frame":
                b = e["box"]
                fit.append(np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [(b[0] + b[2]) / 2, b[1]], [(b[0] + b[2]) / 2, b[3]], [b[0], (b[1] + b[3]) / 2], [b[2], (b[1] + b[3]) / 2]]))
    elif mode == "points":
        for i, (name, sub) in enumerate(spec.get("points", [])):
            pin_entity(name, sub, i)
    elif mode == "route":
        for i, name in enumerate(spec.get("stops", [])):
            k = pin_entity(name, "", i, small=False)
            if k is not None:
                route_e.append(k)
    elif mode == "arcs":
        seen: Dict[str, int] = {}
        for i, arc in enumerate(spec.get("arcs", [])):
            a, b, lab = arc[0], arc[1], (arc[2] if len(arc) > 2 else "")
            ids = []
            for nm in (a, b):
                if nm not in seen:
                    k = pin_entity(nm, "", i, small=True)
                    if k is None:
                        break
                    seen[nm] = k
                ids.append(seen[nm])
            if len(ids) == 2:
                arcs_e.append((i, ids[0], ids[1], lab))
    if mode != "focus":
        for name in spec.get("focus", []):
            e = _ents(spec, "any", name)
            if e is None:
                continue
            if e["t"] == "point":
                fit.append(np.array([[e["lon"], e["lat"]]]))
            elif e["t"] == "frame":
                b = e["box"]
                fit.append(np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [(b[0] + b[2]) / 2, b[1]], [(b[0] + b[2]) / 2, b[3]]]))
            else:
                for r in _main_rings(e, _entity_rings(e)):
                    fit.append(_thin(r))
    for _, _, e, _ in regions_e:
        for r in _main_rings(e, _entity_rings(e)):
            fit.append(_thin(r))
    pin_lonlat = [np.array([e["lon"], e["lat"]]) for _, _, _, e, _ in pins_e]
    arc_ll: List[np.ndarray] = []
    for _, a, b, _ in arcs_e:
        gc = P.great_circle(pin_lonlat[a][0], pin_lonlat[a][1], pin_lonlat[b][0], pin_lonlat[b][1], 4.0)
        arc_ll.append(gc)
        fit.append(gc[:: max(1, len(gc) // 6)])
    route_ll: List[np.ndarray] = []
    for a, b in zip(route_e, route_e[1:]):
        gc = P.great_circle(pin_lonlat[a][0], pin_lonlat[a][1], pin_lonlat[b][0], pin_lonlat[b][1], 4.0)
        route_ll.append(gc)
        fit.append(gc[:: max(1, len(gc) // 6)])
    if not fit:
        fit.append(np.array([[-170, -55], [170, -55], [170, 75], [-170, 75]]))
    allp = np.vstack(fit)
    pure_points = not regions_e and not any(spec.get("focus", [])) and bool(pins_e)
    if pure_points:
        min_span_deg = 12.0

    proj, level, s_deg = choose_projection(allp)
    c_lon, span_lon = _circ_extent(allp[:, 0])
    c_lat = float((allp[:, 1].min() + allp[:, 1].max()) / 2.0)
    half_lat = max(12.0, (allp[:, 1].max() - allp[:, 1].min()) * 1.2)
    half_lon = max(14.0, span_lon * 1.2) / max(0.35, math.cos(math.radians(min(70.0, abs(c_lat)))))
    if not wide:                         # a narrower panel shows more latitude (or less longitude) than the extent suggests: widen the culling window
        asp = ph / max(1.0, float(pw))
        half_lat *= max(1.0, asp / 0.55)
        half_lon *= max(1.0, 0.55 / asp)

    # ---- geometry in the plane
    land = _project_layer(_geo.layer(f"land_{level}"), proj, c_lat, half_lon, half_lat)
    a0 = _geo.layer(f"adm0_{level}")
    borders = [(p, bb) for p, bb, h in _project_layer(a0, proj, c_lat, half_lon, half_lat, holes=False)]
    grat_step = 30 if s_deg > 100 else 15 if s_deg > 55 else 10 if s_deg > 28 else 5 if s_deg > 12 else 2 if s_deg > 5 else 1
    grat = [g.astype(np.float32) for g in proj.graticule(grat_step, span=0 if proj.kind in ("equalearth", "ortho") else max(10.0, s_deg * 1.4))]
    outline = proj.sphere_outline().astype(np.float32)

    # admin-1 lines inside the countries in play, when the view is small enough to see them
    adm1_rows: List[Tuple[np.ndarray, Tuple[float, float, float, float]]] = []
    if s_deg <= 60:
        cids = set()
        for _, _, e, _ in regions_e:
            cids.add(e["id"] if e["t"] == "country" else e.get("c"))
        for _, _, _, e, _ in pins_e:
            pass
        l1 = _geo.layer("adm1")
        for fi, mm in enumerate(l1.meta):
            if mm[_geo.A1_ADM0] in cids:
                for rr, h in l1.rings_of(fi):
                    if not h:
                        for piece in proj.ring_pieces(rr):
                            if len(piece) >= 3:
                                adm1_rows.append((piece.astype(np.float32), _bbox(piece)))

    # ---- items in the plane
    regions: List[Item] = []
    for idx, name, e, soft in regions_e:
        it = Item("region", name, idx=idx, soft=soft)
        for ring, hole in _entity_rings(e):
            for piece in proj.ring_pieces(ring):
                if len(piece) >= 3:
                    it.polys.append((piece.astype(np.float32), hole))
        lp = _label_point(e)
        if lp is None and it.polys:
            big = max((p for p, h in it.polys if not h), key=len)
            it.anchor = (float(big[:, 0].mean()), float(big[:, 1].mean()))
        elif lp is not None:
            x, y, z = proj.forward(lp[0], lp[1])
            if float(z) >= 0:
                it.anchor = (float(x), float(y))
        if not it.polys:
            continue
        w = _measure(name, "semibold", LABEL_PX)
        it.label_wh = (w, LABEL_PX * 1.2)
        regions.append(it)
    pins: List[Item] = []
    for idx, name, sub, e, small in pins_e:
        x, y, z = proj.forward(e["lon"], e["lat"])
        it = Item("pin", name, sub=sub, idx=idx, small=small)
        it.anchor = (float(x), float(y)) if float(z) >= 0 else None
        w = _measure(name, "semibold", LABEL_PX)
        h = LABEL_PX * 1.2
        if sub:
            w = max(w, _measure(sub, "regular", SUB_PX))
            h += SUB_PX * 1.2
        it.label_wh = (w, h)
        pins.append(it)
    paths: List[Path] = []
    for k, ll in enumerate(route_ll):
        pcs = proj.line_pieces(ll)
        if pcs:
            paths.append(Path(max(pcs, key=len), route_e[k], route_e[k + 1], k + 1))
    for i, a, b, lab in arcs_e:
        pts = _arc_plane(proj, tuple(pin_lonlat[a]), tuple(pin_lonlat[b]))
        if len(pts) >= 2:
            p = Path(pts, a, b, i, label=lab)
            if lab:
                p.label_anchor = (float(pts[len(pts) // 2][0]), float(pts[len(pts) // 2][1]))
                p.label_wh = (_measure(lab, "semibold", 34 * ts), 34 * ts * 1.2)
            paths.append(p)

    # ---- the camera
    title, caption = spec.get("title", ""), spec.get("caption", "")
    note = bool(regions)
    note_size = NOTE_PX * ts
    note_w = _measure("Borders as of today", "regular", note_size) if note else 0.0
    t_size, t_lines = TITLE_PX, [title]
    f_size, f_lines = CAPTION_PX, [caption]
    if wide:
        left, right, top, bottom = 90.0, 90.0, 56.0, 56.0
        if title:
            top += 100
        if caption or note:
            bottom += 52
        while title and t_size > 34 and _measure(title, "semibold", t_size) > pw - 150:
            t_size -= 2
    else:
        left, right, top, bottom = 48.0, 48.0, 56.0, 56.0
        if title:
            t_size, t_lines = _fit_lines(title, "semibold", TITLE_PX * 0.9 * ts, pw - 112.0, 36.0, 2)
            top = 24.0 + len(t_lines) * t_size * 1.2 + 26 + 24
        if caption:
            f_size, f_lines = _fit_lines(caption, "regular", CAPTION_PX * 0.92 * ts, pw - 56.0 - 44 - (note_w + 20 if note else 0), 26.0, 2)
            bottom = max(bottom, len(f_lines) * f_size * 1.2 + 20 + 28 + 24)
        elif note:
            bottom = max(bottom, note_size * 1.2 + 40)
    rw, rh = pw - left - right, ph - top - bottom
    xy: List[np.ndarray] = []
    px, py, pz = proj.forward(allp[:, 0], allp[:, 1])
    ok = pz >= 0
    if ok.any():
        xy.append(np.stack([px[ok], py[ok]], axis=1))
    if not xy:
        xy.append(np.array([[0.0, 0.0], [0.1, 0.1]]))
    pts = np.vstack(xy)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    ls = proj.local_scale()
    bw, bh = max(hi[0] - lo[0], min_span_deg * ls), max(hi[1] - lo[1], min_span_deg * ls * rh / rw)
    pad = 1.16
    scale = min(rw / (bw * pad), rh / (bh * pad))
    if proj.kind == "ortho":
        scale = max(scale, 0.0)
    cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
    centre_px = (left + rw / 2, top + rh / 2)
    m = Model(key, mode, pw, ph, proj, level, land, borders, adm1_rows, grat, outline, regions, pins, paths, 0, (cx, cy, scale), centre_px, title, caption, note,
              (0, 0, 0, 0), (0, 0, 0, 0), (pw - 24.0, ph - 16.0), notes)
    # chips (title top-left, caption bottom-left)
    m.need_h = top + bottom + bh * scale * pad
    m.k, m.landscape, m.title_size, m.title_lines, m.foot_size, m.foot_lines, m.note_size = ts, wide, t_size, t_lines, f_size, f_lines, note_size
    m.note_pos = (pw - 24.0, ph - 16.0)
    if title:
        m.chip = (28.0, 24.0, 28.0 + max(_measure(l, "semibold", t_size) for l in t_lines) + 56, 24.0 + len(t_lines) * t_size * 1.2 + 26)
    if caption:
        w = max(_measure(l, "regular", f_size) for l in f_lines)
        m.foot = (28.0, ph - 28.0 - len(f_lines) * f_size * 1.2 - 20, 28.0 + w + 44, ph - 28.0)

    def tf(p):
        return centre_px[0] + (p[0] - cx) * scale, centre_px[1] - (p[1] - cy) * scale

    _place_labels(m, tf)
    m.n_cues = len(regions_e) if mode == "regions" else (len(spec.get("focus", [])) if mode == "focus" and len(spec.get("focus", [])) > 1 else 0)
    return m


# ----------------------------------------------------------------------------- painting
@lru_cache(maxsize=4)
def _panel_mask(w: int, h: int, r: int, ss: int) -> Image.Image:
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], r * ss, fill=255)
    return mask


def _camera(m: Model, lt: float) -> Tuple[float, float, float]:
    cx, cy, s1 = m.cam_end
    p = ease_in_out_cubic(progress(lt, 0.0, CAM_SECONDS))
    return cx, cy, s1 * (CAM_START + (1 - CAM_START) * p)


def _view(m: Model, cam) -> Tuple[float, float, float, float]:
    cx, cy, s = cam
    X0, Y0 = m.centre_px
    return cx - X0 / s, cy - (m.ph - Y0) / s, cx + (m.pw - X0) / s, cy + Y0 / s


def _flat(arr: np.ndarray, cam, m: Model, ss: int) -> List[float]:
    cx, cy, s = cam
    X0, Y0 = m.centre_px
    out = np.empty_like(arr, dtype=np.float64)
    out[:, 0] = (X0 + (arr[:, 0] - cx) * s) * ss
    out[:, 1] = (Y0 - (arr[:, 1] - cy) * s) * ss
    return out.ravel().tolist()


def _paint_base(m: Model, th: Theme, cam, ss: int) -> Canvas:
    pal = palette(th)
    mc = Canvas(m.pw, m.ph, ss=ss)
    d = mc.d
    W, H = m.pw * ss, m.ph * ss
    d.rectangle([0, 0, W, H], fill=pal.ocean if len(m.outline) == 0 else pal.void)
    vx0, vy0, vx1, vy1 = _view(m, cam)
    s = cam[2]
    if len(m.outline):
        d.polygon(_flat(m.outline, cam, m, ss), fill=pal.ocean)
    for g in m.grat:
        if len(g) >= 2:
            d.line(_flat(g, cam, m, ss), fill=with_alpha(pal.grat, pal.grat_a), width=max(1, ss))
    mpx = 0.6 / s

    def seen(bb) -> bool:
        return bb[2] >= vx0 and bb[0] <= vx1 and bb[3] >= vy0 and bb[1] <= vy1 and (bb[2] - bb[0] > mpx or bb[3] - bb[1] > mpx)

    for poly, bb, hole in m.land:
        if seen(bb):
            d.polygon(_flat(poly, cam, m, ss), fill=pal.ocean if hole else pal.land)
    bw = max(1, int(round(1.2 * ss)))
    for poly, bb in m.borders:
        if seen(bb):
            f = _flat(poly, cam, m, ss)
            d.line(f + f[:2], fill=with_alpha(pal.border, 0.9), width=bw, joint="curve")
    for poly, bb in m.adm1:
        if seen(bb):
            f = _flat(poly, cam, m, ss)
            d.line(f + f[:2], fill=with_alpha(pal.border, 0.45), width=max(1, ss), joint="curve")
    if len(m.outline):
        d.line(_flat(m.outline, cam, m, ss) + _flat(m.outline[:1], cam, m, ss), fill=with_alpha(pal.border, 0.7), width=max(1, ss * 2))
    return mc


@lru_cache(maxsize=3)
def _settled_base(key: str, pw: int, ph: int, theme_name: str, ss: int, k: float = 1.0, wide: bool = True) -> Image.Image:
    from ...theme import get_theme
    m = build_model(key, pw, ph, k, wide)
    return _paint_base(m, get_theme(theme_name), (m.cam_end[0], m.cam_end[1], m.cam_end[2]), ss).im


def _halo_text(mc: Canvas, x: float, y: float, s: str, weight: str, size: float, color, halo, alpha: float, anchor: str = "la") -> None:
    r = max(2.0, size * 0.09)
    ha = with_alpha(halo, min(1.0, alpha * 0.92))
    for k in range(10):
        a = 2 * math.pi * k / 10
        mc.text(x + math.cos(a) * r, y + math.sin(a) * r, s, weight, size, ha, anchor=anchor)
    mc.text(x, y, s, weight, size, with_alpha(color, alpha), anchor=anchor)


def _arrow(mc: Canvas, pts: List[Tuple[float, float]], color, size: float = 16) -> None:
    if len(pts) < 2:
        return
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ang = math.atan2(y1 - y0, x1 - x0)
    tip = (x1 + math.cos(ang) * size * 0.5, y1 + math.sin(ang) * size * 0.5)
    mc.polygon([tip, (tip[0] - size * math.cos(ang - 0.45), tip[1] - size * math.sin(ang - 0.45)), (tip[0] - size * math.cos(ang + 0.45), tip[1] - size * math.sin(ang + 0.45))], fill=color)


def reveal_schedule(m: Model, times: List[float], dur: float):
    """(region times, pin times, path (start, end) times) from the cue list."""
    cap = max(0.3, dur - 1.4)
    t = [min(max(0.0, float(x)), cap) for x in times]

    def at(i: int) -> float:
        return t[i] if i < len(t) else min(cap, 0.45 + 0.35 * i)

    reg = [at(it.idx) for it in m.regions]
    pins = [at(it.idx) for it in m.pins]
    paths: List[Tuple[float, float]] = []
    if m.mode == "route":
        route_pins = [k for k, it in enumerate(m.pins)]
        for p in m.paths:
            ta, tb = at(m.pins[p.a].idx), at(m.pins[p.b].idx)
            d = min(1.6, max(0.5, 0.9 * (tb - ta)))
            e = max(tb + 0.1, ta + 0.2 + 0.5)
            s0 = max(ta + 0.2, e - d)
            paths.append((s0, e))
            pins[p.b] = max(tb, e - 0.25)
        _ = route_pins
    elif m.mode == "arcs":
        first: Dict[int, float] = {}
        for p in m.paths:
            tb = at(p.idx)
            e = tb + 0.15
            s0 = max(0.05, e - 1.1)
            paths.append((s0, e))
            first[p.a] = min(first.get(p.a, 9e9), s0)
            first[p.b] = min(first.get(p.b, 9e9), e - 0.25)
        pins = [first.get(k, pins[k]) for k in range(len(m.pins))]
    return reg, pins, paths


def paint_frame(cv: Canvas, m: Model, th: Theme, times: List[float], lt: float, dur: float, bottom: int, origin: Tuple[float, float] = (PANEL_X, PANEL_TOP)) -> None:
    k, PIN_R = m.k, _PIN_R * m.k
    ss = cv.ss
    cam = _camera(m, lt)
    settled = lt >= CAM_SECONDS
    if settled:
        mc = Canvas(m.pw, m.ph, ss=ss)
        mc.im = _settled_base(m.key, m.pw, m.ph_box or m.ph, th.name, ss, m.k, m.landscape).copy()
        mc.d = ImageDraw.Draw(mc.im, "RGBA")
    else:
        mc = _paint_base(m, th, cam, ss)
    pal = palette(th)
    cx, cy, s = cam
    X0, Y0 = m.centre_px

    def tf(p):
        return X0 + (p[0] - cx) * s, Y0 - (p[1] - cy) * s

    reg_t, pin_t, path_t = reveal_schedule(m, times, dur)
    halo = th.bg_top

    # highlighted regions
    for it, t0 in zip(m.regions, reg_t):
        p = ease_out_cubic(progress(lt, t0, 0.6))
        if p <= 0:
            continue
        a_fill = (0.5 if it.soft else 0.78) * p
        for poly, hole in it.polys:
            f = _flat(poly, cam, m, ss)
            if len(f) < 6:
                continue
            mc.d.polygon(f, fill=pal.land if hole else with_alpha(th.accent, a_fill))
        for poly, hole in it.polys:
            if not hole:
                f = _flat(poly, cam, m, ss)
                mc.d.line(f + f[:2], fill=with_alpha(_mix(th.accent, (255, 255, 255), 0.35), 0.95 * p), width=max(1, int(round(2.6 * ss))), joint="curve")

    # routes and arcs
    line_col = th.accent2
    for pth, (t0, t1) in zip(m.paths, path_t):
        pr = ease_in_out_cubic(progress(lt, t0, t1 - t0))
        if pr <= 0:
            continue
        scr = [tf(q) for q in pth.pts]
        part = partial_polyline(scr, pr)
        mc.line(part, with_alpha(line_col, 0.20), 18, round_caps=True)
        mc.line(part, with_alpha(line_col, 1.0), 6.5)
        if pr < 0.999 and part:
            hx, hy = part[-1]
            mc.ellipse(hx, hy, 17, 17, fill=with_alpha(line_col, 0.28))
            mc.ellipse(hx, hy, 9.5, 9.5, fill=with_alpha(th.text, 1.0), outline=with_alpha(line_col, 1.0), width=3.5)
        elif m.mode == "arcs":
            _arrow(mc, scr, with_alpha(line_col, 1.0), 20)

    # pins
    for it, t0 in zip(m.pins, pin_t):
        if it.anchor is None:
            continue
        p = progress(lt, t0, 0.45)
        if p <= 0:
            continue
        x, y = tf(it.anchor)
        r = PIN_R * (0.72 if it.small else 1.0) * ease_out_back(p)
        age = lt - t0 - 0.35
        if age > 0:
            ph = (age % 2.0) / 2.0
            rr = r + 30 * ease_out_cubic(ph)
            mc.ellipse(x, y, rr, rr, outline=with_alpha(th.accent, 0.55 * (1 - ph)), width=3)
        mc.ellipse(x, y, r + 5, r + 5, fill=with_alpha(halo, 0.55))
        mc.ellipse(x, y, r, r, fill=with_alpha(th.accent, 1.0), outline=with_alpha(th.text, 1.0), width=3.2 if not it.small else 2.6)

    # labels (on top of everything)
    for it, t0 in zip(m.regions, reg_t):
        if it.anchor is None:
            continue
        p = ease_out_cubic(progress(lt, t0 + 0.12, 0.4))
        if p <= 0:
            continue
        x, y = tf(it.anchor)
        w, h = it.label_wh
        _halo_text(mc, x + it.label_off[0] + w / 2, y + it.label_off[1] + h / 2 + (1 - p) * 8, it.name, "semibold", LABEL_PX * k, th.text, halo, p, anchor="mm")
    for it, t0 in zip(m.pins, pin_t):
        if it.anchor is None:
            continue
        p = ease_out_cubic(progress(lt, t0 + 0.1, 0.4))
        if p <= 0:
            continue
        x, y = tf(it.anchor)
        bx, by = x + it.label_off[0], y + it.label_off[1] + (1 - p) * 8
        w, h = it.label_wh
        right = it.label_off[0] < -w / 2 - 1
        ax = bx + (w if right else 0)
        _halo_text(mc, ax, by, it.name, "semibold", LABEL_PX * k, th.text, halo, p, anchor="ra" if right else "la")
        if it.sub:
            _halo_text(mc, ax, by + LABEL_PX * k * 1.2, it.sub, "regular", SUB_PX * k, _mix(th.text, th.muted, 0.35), halo, p, anchor="ra" if right else "la")
    for pth, (t0, t1) in zip(m.paths, path_t):
        if not pth.label or pth.label_anchor is None:
            continue
        p = ease_out_cubic(progress(lt, t1 - 0.1, 0.4))
        if p <= 0:
            continue
        x, y = tf(pth.label_anchor)
        w, h = pth.label_wh
        _halo_text(mc, x + pth.label_off[0] + w / 2, y + pth.label_off[1] + h / 2, pth.label, "semibold", 34 * k, th.text, halo, p, anchor="mm")

    # title chip, caption, footnote
    if m.title:
        p = ease_out_cubic(progress(lt, 0.05, 0.5))
        x0, y0, x1, y1 = m.chip
        size = m.title_size
        mc.rrect(x0, y0, x1 - x0, y1 - y0, 18, fill=with_alpha(th.bg_top, 0.82 * p), outline=with_alpha(th.card_outline, p), width=1.5)
        mc.rrect(x0 + 16, y0 + 14, 7, y1 - y0 - 28, 3.5, fill=with_alpha(th.accent, p))
        for li, line in enumerate(m.title_lines):
            mc.text(x0 + 38, y0 + 13 + (1 - p) * 10 + li * size * 1.2, line, "semibold", size, with_alpha(th.text, p))
    if m.caption:
        p = ease_out_cubic(progress(lt, 0.4, 0.5))
        x0, y0, x1, y1 = m.foot
        mc.rrect(x0, y0, x1 - x0, y1 - y0, 16, fill=with_alpha(th.bg_top, 0.82 * p), outline=with_alpha(th.card_outline, p), width=1.5)
        for li, line in enumerate(m.foot_lines):
            mc.text(x0 + 22, y0 + 10 + li * m.foot_size * 1.2, line, "regular", m.foot_size, with_alpha(th.text, p))
    if m.note:
        p = ease_out_cubic(progress(lt, 0.6, 0.5))
        _halo_text(mc, m.note_pos[0], m.note_pos[1], "Borders as of today", "regular", m.note_size, th.muted if th.name != "paper" else (80, 88, 104), halo, 0.9 * p, anchor="rd")

    # onto the page: shadow, the clipped map, a thin frame
    x, y = origin[0], origin[1] + m.y_off
    cv.shadow(x, y, m.pw, m.ph, 36, blur=26, dy=14, alpha=th.shadow_alpha * 0.9)
    cv.im.paste(mc.im, (cv._s(x), cv._s(y)), _panel_mask(m.pw, m.ph, 36, ss))
    cv.rrect(x, y, m.pw, m.ph, 36, outline=th.card_outline, width=2)


def panel_size(bottom: int, frame=None, box=None) -> Tuple[int, int]:
    """Panel size in design units. Landscape keeps its panel; other frames use the whole content box (the map is the scene)."""
    if frame is None or frame.landscape or box is None:
        return PANEL_W, max(360, int(bottom - 14 - PANEL_TOP))
    return int(box[2] - box[0]), int(box[3] - box[1])


def panel_origin(frame=None, box=None) -> Tuple[float, float]:
    if frame is None or frame.landscape or box is None:
        return PANEL_X, PANEL_TOP
    return float(box[0]), float(box[1])
