#!/usr/bin/env python3
"""Builds the bundled geometry in lambdas/engine/assets/geo/ from Natural Earth GeoJSON (public domain). Dev-time only: needs numpy, nothing else.

  python scripts/build_geo.py <dir with the Natural Earth .geojson files> [--out lambdas/engine/assets/geo]

Inputs (https://github.com/nvkelso/natural-earth-vector/tree/master/geojson):
  ne_110m_admin_0_countries, ne_50m_admin_0_countries, ne_110m_land, ne_50m_land, ne_10m_admin_1_states_provinces, ne_10m_populated_places_simple

Output format (one .npz per polygon layer): `xy` int32 (N,2) the rings' points in 1/1000 degree, delta coded inside a ring (the first point is absolute); `off` int32 (R+1) ring
boundaries in `xy`; `feat` int32 (R) the feature of each ring; `hole` uint8 (R); `meta` uint8 the JSON bytes of one list per feature. Places are one gzip'd JSON.
"""
import argparse
import gzip
import json
import os
import sys
from typing import Any, Dict, List

import numpy as np

SCALE = 1000


def rdp(pts: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker on an (N,2) array (open polyline); keeps the ends."""
    n = len(pts)
    if n < 3 or tol <= 0:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        seg = pts[a + 1:b]
        d = q - p
        L = float(np.hypot(d[0], d[1]))
        if L == 0:
            dist = np.hypot(seg[:, 0] - p[0], seg[:, 1] - p[1])
        else:
            dist = np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / L
        i = int(np.argmax(dist))
        if dist[i] > tol:
            m = a + 1 + i
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return pts[keep]


def ring_area(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def simplify_ring(r: np.ndarray, tol: float) -> np.ndarray:
    r = np.asarray(r, np.float64)
    if len(r) > 1 and (r[0] == r[-1]).all():
        r = r[:-1]
    if len(r) > 8 and tol > 0:
        # a closed ring: split at the farthest point so both halves are simplified against a sensible chord
        far = int(np.argmax(np.hypot(r[:, 0] - r[0, 0], r[:, 1] - r[0, 1])))
        a = rdp(r[:far + 1], tol)
        b = rdp(np.vstack([r[far:], r[:1]]), tol)
        r = np.vstack([a[:-1], b[:-1]])
    return r


def polys(geom: Dict[str, Any]) -> List[List[Any]]:
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def build_layer(features: List[Dict[str, Any]], metas: List[Any], tol: float, min_area: float, path: str) -> int:
    xy: List[np.ndarray] = []
    off = [0]
    feat: List[int] = []
    hole: List[int] = []
    for fi, f in enumerate(features):
        rings = []
        for poly in polys(f["geometry"]):
            for k, ring in enumerate(poly):
                r = simplify_ring(ring, tol)
                a = abs(ring_area(r)) if len(r) >= 3 else 0.0
                rings.append((a, k > 0, r))
        if not rings:
            continue
        biggest = max(a for a, h, r in rings if not h)
        for a, h, r in rings:
            if len(r) < 3 or (a < min_area and not (a == biggest and not h)):
                continue
            q = np.rint(r * SCALE).astype(np.int64)
            d = np.vstack([q[:1], np.diff(q, axis=0)])
            xy.append(d.astype(np.int32))
            off.append(off[-1] + len(q))
            feat.append(fi)
            hole.append(1 if h else 0)
    meta = json.dumps(metas, ensure_ascii=False, separators=(",", ":")).encode()
    np.savez_compressed(path, xy=np.vstack(xy), off=np.array(off, np.int32), feat=np.array(feat, np.int32), hole=np.array(hole, np.uint8), meta=np.frombuffer(meta, np.uint8))
    return os.path.getsize(path)


def uniq(seq):
    seen, out = set(), []
    for s in seq:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def load(d: str, name: str) -> List[Dict[str, Any]]:
    with open(os.path.join(d, name + ".geojson"), encoding="utf-8") as fh:
        return json.load(fh)["features"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "lambdas", "engine", "assets", "geo"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    total = 0

    # ---- countries (admin 0)
    for res, tol, min_area in (("110m", 0.0, 0.0), ("50m", 0.003, 0.0001)):
        feats = [f for f in load(a.src, f"ne_{res}_admin_0_countries")]
        metas = []
        for f in feats:
            p = f["properties"]
            names = uniq([p.get("NAME"), p.get("NAME_LONG"), p.get("ADMIN"), p.get("NAME_EN"), p.get("FORMAL_EN"), p.get("ABBREV"), p.get("NAME_CIAWF"), p.get("BRK_NAME"), p.get("GEOUNIT"), p.get("SUBUNIT")]
                         + [p.get(f"NAME_{c}") for c in ("ES", "FR", "DE", "IT", "PT", "NL", "SV", "PL", "TR", "ID")] + (p.get("NAME_ALT") or "").split("|"))
            metas.append([p.get("ADM0_A3"), p.get("NAME_EN") or p.get("NAME"), names, p.get("ISO_A2_EH") if p.get("ISO_A2_EH") not in (None, "-99") else p.get("ISO_A2"),
                          p.get("ISO_A3_EH") if p.get("ISO_A3_EH") not in (None, "-99") else p.get("ISO_A3"), int(p.get("POP_EST") or 0), p.get("CONTINENT"), p.get("SOVEREIGNT"),
                          round(float(p.get("LABEL_X") or 0), 3), round(float(p.get("LABEL_Y") or 0), 3)])
        size = build_layer(feats, metas, tol, min_area, os.path.join(a.out, f"adm0_{res[:-1]}.npz"))
        print(f"adm0_{res}: {len(feats)} countries, {size / 1024:.0f} KB")
        total += size

    # ---- land
    for res, tol, min_area in (("110m", 0.0, 0.0), ("50m", 0.003, 0.0001)):
        feats = load(a.src, f"ne_{res}_land")
        size = build_layer(feats, [[]] * len(feats), tol, min_area, os.path.join(a.out, f"land_{res[:-1]}.npz"))
        print(f"land_{res}: {size / 1024:.0f} KB")
        total += size

    # ---- first-level areas (10m), simplified hard: they are drawn as thin lines inside a country or as a highlighted region
    feats = [f for f in load(a.src, "ne_10m_admin_1_states_provinces") if f["geometry"]]
    metas = []
    for f in feats:
        p = f["properties"]
        names = uniq([p.get("name"), p.get("name_en"), p.get("name_alt"), p.get("name_local"), p.get("woe_name"), p.get("gn_name")] + [p.get(f"name_{c}") for c in ("es", "fr", "de", "it", "pt")]
                     + (p.get("name_alt") or "").split("|"))
        metas.append([p.get("adm1_code"), p.get("name_en") or p.get("name"), names, p.get("iso_a2"), p.get("adm0_a3"), p.get("admin"), p.get("type_en") or p.get("type"),
                      round(float(p.get("longitude") or 0), 3), round(float(p.get("latitude") or 0), 3), p.get("postal")])
    size = build_layer(feats, metas, 0.008, 0.001, os.path.join(a.out, "adm1.npz"))
    print(f"adm1: {len(feats)} areas, {size / 1024:.0f} KB")
    total += size

    # ---- populated places
    rows = []
    for f in load(a.src, "ne_10m_populated_places_simple"):
        p = f["properties"]
        alts = uniq([p.get("nameascii"), p.get("namepar"), p.get("meganame"), p.get("ls_name")] + (p.get("namealt") or "").split("|"))
        alts = [x for x in alts if x != p.get("name")]
        rows.append([p.get("name"), alts, round(float(p["longitude"]), 4), round(float(p["latitude"]), 4), p.get("iso_a2"), p.get("adm0name"), p.get("adm1name"), int(p.get("pop_max") or 0),
                     1 if p.get("adm0cap") else 0, 1 if "capital" in (p.get("featurecla") or "").lower() and "Admin-0" in (p.get("featurecla") or "") else 0])
    path = os.path.join(a.out, "places.json.gz")
    with gzip.open(path, "wb", 9) as fh:
        fh.write(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode())
    print(f"places: {len(rows)}, {os.path.getsize(path) / 1024:.0f} KB")
    total += os.path.getsize(path)
    print(f"total {total / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
