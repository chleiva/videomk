"""Map projections in plain numpy (no pyproj): orthographic, Equal Earth, Albers conic, Mercator, plus the geometry that makes them drawable: horizon clipping for the globe,
the antimeridian seam for flat maps, great-circle sampling, graticules.

All projections work on the unit sphere and return "plane" coordinates (x to the right, y up); the map scene turns plane units into pixels with one camera (scale and centre).
Rings are returned as polygons ready to fill, lines as polylines that are broken wherever the line leaves the visible area.
"""
import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

PI = math.pi
_EE = (1.340264, -0.081106, 0.000893, 0.003796)
SQ3 = math.sqrt(3.0)


def wrap_deg(d):
    """Longitude difference wrapped to [-180, 180)."""
    return (np.asarray(d, dtype=np.float64) + 180.0) % 360.0 - 180.0


def circular_mean_lon(lons, weights=None) -> float:
    lons = np.radians(np.asarray(lons, np.float64))
    w = np.ones_like(lons) if weights is None else np.asarray(weights, np.float64)
    return math.degrees(math.atan2(float((np.sin(lons) * w).sum()), float((np.cos(lons) * w).sum())))


def to_vec(lon, lat) -> np.ndarray:
    lo, la = np.radians(lon), np.radians(lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)


def angular_distance_deg(lon1, lat1, lon2, lat2) -> float:
    a, b = to_vec(lon1, lat1), to_vec(lon2, lat2)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a, b))))))


def great_circle(lon1: float, lat1: float, lon2: float, lat2: float, step_deg: float = 1.5) -> np.ndarray:
    """Points (lon, lat) along the shorter great circle from 1 to 2, including both ends; about one point per `step_deg`."""
    a, b = to_vec(lon1, lat1), to_vec(lon2, lat2)
    d = math.acos(max(-1.0, min(1.0, float(np.dot(a, b)))))
    n = max(2, int(math.degrees(d) / step_deg) + 2)
    if d < 1e-9:
        return np.array([[lon1, lat1], [lon2, lat2]], np.float64)
    t = np.linspace(0.0, 1.0, n)[:, None]
    p = (np.sin((1 - t) * d) * a + np.sin(t * d) * b) / math.sin(d)
    lat = np.degrees(np.arcsin(np.clip(p[:, 2], -1, 1)))
    lon = np.degrees(np.arctan2(p[:, 1], p[:, 0]))
    lon = lon1 + wrap_deg(lon - lon1)           # continuous with the start, so a path over the antimeridian does not jump
    lon[-1] = lon1 + float(wrap_deg(lon2 - lon1))
    return np.stack([lon, lat], axis=1)


@dataclass(frozen=True)
class Proj:
    kind: str                    # "ortho" | "equalearth" | "albers" | "mercator"
    lon0: float = 0.0            # degrees: the central meridian / the view centre
    lat0: float = 0.0
    phi1: float = 0.0            # standard parallels (albers)
    phi2: float = 0.0

    # ---------------------------------------------------------------- forward
    def forward(self, lon, lat):
        """-> (x, y, z). z is the visibility measure (cos of the angular distance from the centre) for the globe, 1 elsewhere."""
        lon = np.asarray(lon, np.float64)
        lat = np.asarray(lat, np.float64)
        return self._fwd(np.radians(wrap_deg(lon - self.lon0)), np.radians(np.clip(lat, -90, 90)))

    def _fwd(self, dl, ph):
        """dl: longitude relative to the centre (radians, not wrapped); ph: latitude (radians)."""
        if self.kind == "ortho":
            p0 = math.radians(self.lat0)
            x = np.cos(ph) * np.sin(dl)
            y = math.cos(p0) * np.sin(ph) - math.sin(p0) * np.cos(ph) * np.cos(dl)
            z = math.sin(p0) * np.sin(ph) + math.cos(p0) * np.cos(ph) * np.cos(dl)
            return x, y, z
        if self.kind == "equalearth":
            th = np.arcsin(SQ3 / 2 * np.sin(ph))
            t2, t6 = th * th, th ** 6
            a1, a2, a3, a4 = _EE
            x = (2 * SQ3 / 3) * dl * np.cos(th) / (a1 + 3 * a2 * t2 + t6 * (7 * a3 + 9 * a4 * t2))
            y = th * (a1 + a2 * t2 + t6 * (a3 + a4 * t2))
            return x, y, np.ones_like(x)
        if self.kind == "albers":
            p1, p2, p0 = math.radians(self.phi1), math.radians(self.phi2), math.radians(self.lat0)
            n = (math.sin(p1) + math.sin(p2)) / 2
            c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
            rho = np.sqrt(np.maximum(c - 2 * n * np.sin(ph), 0.0)) / n
            rho0 = math.sqrt(max(c - 2 * n * math.sin(p0), 0.0)) / n
            th = n * dl
            return rho * np.sin(th), rho0 - rho * np.cos(th), np.ones_like(rho)
        # mercator
        ph = np.clip(ph, math.radians(-82), math.radians(82))
        return dl, np.log(np.tan(PI / 4 + ph / 2)), np.ones_like(dl)

    def xy(self, lon, lat) -> np.ndarray:
        x, y, _ = self.forward(lon, lat)
        return np.stack([x, y], axis=-1)

    def local_scale(self) -> float:
        """Plane units per degree at the centre of the view."""
        a = self.xy(self.lon0, self.lat0)
        b = self.xy(self.lon0 + 1.0, self.lat0)
        c = self.xy(self.lon0, self.lat0 + 1.0)
        return float(max(np.hypot(*(b - a)), np.hypot(*(c - a)), 1e-6))

    # ---------------------------------------------------------------- shapes
    def sphere_outline(self) -> np.ndarray:
        """The edge of the world in plane coordinates (a circle for the globe, the Equal Earth outline), or an empty array for maps that have no edge in view."""
        if self.kind == "ortho":
            t = np.linspace(0, 2 * PI, 181)
            return np.stack([np.cos(t), np.sin(t)], axis=1)
        if self.kind == "equalearth":
            lat = np.linspace(-90, 90, 91)
            right = self.xy(np.full_like(lat, self.lon0 + 179.999), lat)
            left = self.xy(np.full_like(lat, self.lon0 - 179.999), lat)
            return np.vstack([right, left[::-1]])
        return np.zeros((0, 2))

    def graticule(self, step: float, span: float = 0.0) -> List[np.ndarray]:
        """Polylines of meridians and parallels every `step` degrees (limited to `span` degrees around the centre when given)."""
        lines: List[np.ndarray] = []
        lat_lo, lat_hi = -80.0, 80.0
        lon_half = 180.0
        if span:
            lat_lo, lat_hi = max(-85.0, self.lat0 - span), min(85.0, self.lat0 + span)
            lon_half = min(180.0, span * 1.6 / max(math.cos(math.radians(self.lat0)), 0.2))
        lon_lo = math.floor((self.lon0 - lon_half) / step) * step
        lon_hi = math.ceil((self.lon0 + lon_half) / step) * step
        lons = np.arange(lon_lo, lon_hi + 0.01, step)
        lats = np.arange(math.ceil(lat_lo / step) * step, lat_hi + 0.01, step)
        for lo in lons:
            lines += self.line_pieces(np.stack([np.full(81, lo), np.linspace(lat_lo, lat_hi, 81)], axis=1))
        for la in lats:
            lines += self.line_pieces(np.stack([np.linspace(lon_lo, lon_hi, max(2, int((lon_hi - lon_lo) / 2) + 1)), np.full(max(2, int((lon_hi - lon_lo) / 2) + 1), la)], axis=1))
        return lines

    # ---------------------------------------------------------------- rings and lines
    def ring_pieces(self, ll: np.ndarray) -> List[np.ndarray]:
        """A closed ring (lon, lat) -> polygons in plane coordinates (several when the ring crosses the seam of a flat map; none when it is hidden on the globe)."""
        if len(ll) < 3:
            return []
        if self.kind == "ortho":
            return self._ortho_ring(ll)
        return self._flat_ring(ll)

    def line_pieces(self, ll: np.ndarray) -> List[np.ndarray]:
        """A polyline (lon, lat) -> polylines in plane coordinates, broken where it goes over the horizon (globe) or across the seam (flat maps)."""
        ll = np.asarray(ll, np.float64)
        if len(ll) < 2:
            return []
        if self.kind == "ortho":
            x, y, z = self.forward(ll[:, 0], ll[:, 1])
            vis = z >= 0
            out, start = [], None
            for i in range(len(ll) + 1):
                v = bool(vis[i]) if i < len(ll) else False
                if v and start is None:
                    start = i
                elif not v and start is not None:
                    seg = np.stack([x[start:i], y[start:i]], axis=1)
                    if len(seg) >= 2:
                        out.append(seg)
                    start = None
            return out
        dl = wrap_deg(ll[:, 0] - self.lon0)
        jump = np.abs(np.diff(dl)) > 180.0
        xy = self.xy(ll[:, 0], ll[:, 1])
        cuts = [0] + [int(i) + 1 for i in np.nonzero(jump)[0]] + [len(ll)]
        return [xy[a:b] for a, b in zip(cuts, cuts[1:]) if b - a >= 2]

    # -- globe
    def _ortho_ring(self, ll: np.ndarray) -> List[np.ndarray]:
        x, y, z = self.forward(ll[:, 0], ll[:, 1])
        vis = z >= 0
        n = len(ll)
        if vis.all():
            return [np.stack([x, y], axis=1)]
        if not vis.any():
            return []
        # start at the first visible vertex that follows a hidden one, so every visible run is bounded by hidden vertices on both sides
        starts = [i for i in range(n) if vis[i] and not vis[i - 1]]
        s0 = starts[0]
        order = np.roll(np.arange(n), -s0)
        x, y, z, vis = x[order], y[order], z[order], vis[order]

        def crossing(i: int, j: int) -> Tuple[float, float]:
            t = z[i] / (z[i] - z[j])
            px, py, pz = x[i] + t * (x[j] - x[i]), y[i] + t * (y[j] - y[i]), 0.0
            r = math.hypot(px, py) or 1.0
            return px / r, py / r

        runs = []
        i = 0
        while i < n:
            if vis[i]:
                j = i
                while j + 1 < n and vis[j + 1]:
                    j += 1
                runs.append((i, j))
                i = j + 1
            else:
                i += 1
        pts: List[Tuple[float, float]] = []
        for k, (a, b) in enumerate(runs):
            entry = crossing(a - 1, a)
            exit_ = crossing(b, (b + 1) % n)
            pts.append(entry)
            pts += list(zip(x[a:b + 1], y[a:b + 1]))
            pts.append(exit_)
            nxt = crossing(runs[(k + 1) % len(runs)][0] - 1, runs[(k + 1) % len(runs)][0])
            pts += _horizon_arc(exit_, nxt)
        return [np.array(pts, np.float64)]

    # -- flat maps
    def _flat_ring(self, ll: np.ndarray) -> List[np.ndarray]:
        lam = np.unwrap(np.radians(wrap_deg(ll[:, 0] - self.lon0)))
        phi = ll[:, 1]
        pieces: List[Tuple[np.ndarray, np.ndarray]] = []
        if lam.min() >= -PI and lam.max() <= PI:
            pieces.append((lam, phi))
        else:
            for k in (-2 * PI, 0.0, 2 * PI):
                s = lam + k
                if s.max() < -PI or s.min() > PI:
                    continue
                poly = _clip_x(list(zip(s, phi)), -PI, PI)
                if len(poly) >= 3:
                    a = np.array(poly)
                    pieces.append((a[:, 0], a[:, 1]))
        out = []
        for l, p in pieces:
            l, p = _densify_seam(l, p)
            x, y, _ = self._fwd(l, np.radians(np.clip(p, -90, 90)))
            out.append(np.stack([x, y], axis=1))
        return out


def _horizon_arc(a: Tuple[float, float], b: Tuple[float, float]) -> List[Tuple[float, float]]:
    ta, tb = math.atan2(a[1], a[0]), math.atan2(b[1], b[0])
    d = (tb - ta + PI) % (2 * PI) - PI            # the shorter way round the limb
    k = max(1, int(abs(d) / math.radians(3)))
    return [(math.cos(ta + d * i / (k + 1)), math.sin(ta + d * i / (k + 1))) for i in range(1, k + 1)]


def _clip_x(poly: List[Tuple[float, float]], lo: float, hi: float) -> List[Tuple[float, float]]:
    """Sutherland-Hodgman against the vertical lines x=lo and x=hi."""
    def clip(pts, inside, inter):
        out = []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            pi_, qi = inside(p), inside(q)
            if pi_:
                if not qi:
                    out.append(inter(q, p))
                out.append(p)
            elif qi:
                out.append(inter(q, p))
        return out

    def at(xv):
        return lambda q, p: (xv, q[1] + (p[1] - q[1]) * (xv - q[0]) / (p[0] - q[0]))

    poly = clip(poly, lambda p: p[0] >= lo, at(lo))
    if len(poly) < 3:
        return []
    return clip(poly, lambda p: p[0] <= hi, at(hi))


def _densify_seam(lam: np.ndarray, phi: np.ndarray, step_deg: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """Edges that run along the seam (x = +-pi) get intermediate points, so they follow the curved edge of the projection."""
    ol, op = [lam[0]], [phi[0]]
    for i in range(1, len(lam) + 1):
        a, b = i - 1, i % len(lam)
        if abs(abs(lam[a]) - PI) < 1e-9 and abs(abs(lam[b]) - PI) < 1e-9 and abs(lam[a] - lam[b]) < 1e-9 and abs(phi[a] - phi[b]) > step_deg:
            k = int(abs(phi[a] - phi[b]) / step_deg)
            for j in range(1, k + 1):
                ol.append(lam[a])
                op.append(phi[a] + (phi[b] - phi[a]) * j / (k + 1))
        if i < len(lam):
            ol.append(lam[i])
            op.append(phi[i])
    return np.array(ol), np.array(op)
