"""Loader for the bundled Natural Earth geometry (public domain), see assets/geo/ and docs/MAPS.md. Lazy and cached: nothing is read until a map needs it.

A polygon layer is a set of rings (lon, lat in degrees) grouped by feature; a ring is an exterior (hole=False) or a hole. Features carry a small metadata list whose layout is
described by the META_* constants below (the format is written by scripts/build_geo.py).
"""
import gzip
import json
import os
from functools import lru_cache
from typing import Dict, List, Tuple

import numpy as np

GEO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "geo")
SCALE = 1000.0

# adm0 / adm1 metadata columns
A0_ID, A0_NAME, A0_NAMES, A0_ISO2, A0_ISO3, A0_POP, A0_CONT, A0_SOV, A0_LX, A0_LY = range(10)
A1_ID, A1_NAME, A1_NAMES, A1_ISO2, A1_ADM0, A1_COUNTRY, A1_TYPE, A1_LX, A1_LY, A1_POSTAL = range(10)
# place columns
P_NAME, P_ALTS, P_LON, P_LAT, P_ISO2, P_COUNTRY, P_ADM1, P_POP, P_CAP, P_CAP0 = range(10)


class Layer:
    def __init__(self, path: str):
        z = np.load(path)
        d = z["xy"].astype(np.int64)
        off = z["off"].astype(np.int64)
        self.off = off
        self.feat = z["feat"].astype(np.int64)
        self.hole = z["hole"].astype(bool)
        self.meta: List[list] = json.loads(bytes(z["meta"]).decode("utf-8"))
        ll = np.empty((len(d), 2), np.float64)
        for i in range(len(off) - 1):
            a, b = off[i], off[i + 1]
            ll[a:b] = np.cumsum(d[a:b], axis=0) / SCALE
        self.ll = ll
        self.bbox = np.array([[ll[off[i]:off[i + 1], 0].min(), ll[off[i]:off[i + 1], 1].min(), ll[off[i]:off[i + 1], 0].max(), ll[off[i]:off[i + 1], 1].max()]
                              for i in range(len(off) - 1)], np.float64)
        self.by_feat: Dict[int, List[int]] = {}
        for r, f in enumerate(self.feat):
            self.by_feat.setdefault(int(f), []).append(r)

    @property
    def n_rings(self) -> int:
        return len(self.off) - 1

    def ring(self, r: int) -> np.ndarray:
        return self.ll[self.off[r]:self.off[r + 1]]

    def rings_of(self, fi: int) -> List[Tuple[np.ndarray, bool]]:
        return [(self.ring(r), bool(self.hole[r])) for r in self.by_feat.get(fi, [])]


@lru_cache(maxsize=None)
def layer(name: str) -> Layer:
    """name: adm0_110, adm0_50, land_110, land_50, adm1."""
    return Layer(os.path.join(GEO_DIR, name + ".npz"))


@lru_cache(maxsize=1)
def places() -> List[list]:
    with gzip.open(os.path.join(GEO_DIR, "places.json.gz"), "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def ring_area_km2_like(r: np.ndarray) -> float:
    """Planar area in deg^2 scaled by cos(lat): enough to rank rings of one feature."""
    x, y = r[:, 0], r[:, 1]
    a = 0.5 * abs(float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])))
    return a * float(np.cos(np.radians(float(y.mean()))))
