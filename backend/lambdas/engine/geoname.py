"""A place name from approximate coordinates, offline, from the bundled Natural Earth populated places (the same data the map element uses): no third party ever
sees a photo's location. Used on coordinates the phone already rounded to about 1 km."""
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

from .scenes.elements import _geo

NEAR_KM = 25.0      # a place this close counts as "in" it; among those the biggest city wins (a suburb is not what a visitor means)
FAR_KM = 90.0       # else the nearest place within this distance is named with "near"
IN_KM = 10.0


@lru_cache(maxsize=1)
def _arrays() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    pl = _geo.places()
    return (np.radians(np.array([p[_geo.P_LAT] for p in pl], np.float64)), np.radians(np.array([p[_geo.P_LON] for p in pl], np.float64)),
            np.array([float(p[_geo.P_POP] or 0) for p in pl], np.float64))


def place_for(lat: float, lon: float) -> Optional[str]:
    """"Paris, France", "near Versailles, France" or None when no known place is within FAR_KM."""
    la, lo, pop = _arrays()
    p1, l1 = np.radians(lat), np.radians(lon)
    a = np.sin((la - p1) / 2) ** 2 + np.cos(p1) * np.cos(la) * np.sin((lo - l1) / 2) ** 2
    d = 6371.0 * 2 * np.arcsin(np.sqrt(a))
    near = np.where(d <= NEAR_KM)[0]
    if len(near):
        i = int(near[np.argmax(pop[near])])
    else:
        i = int(np.argmin(d))
        if d[i] > FAR_KM:
            return None
    row = _geo.places()[i]
    name = f"{row[_geo.P_NAME]}, {row[_geo.P_COUNTRY]}" if row[_geo.P_COUNTRY] else str(row[_geo.P_NAME])
    return name if d[i] <= IN_KM else f"near {name}"
