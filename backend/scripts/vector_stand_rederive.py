#!/usr/bin/env python3
"""Re-derive the ground lines and per-shape numbers of the stored stand zones, model-free (the polygons stay as they are).

  python backend/scripts/vector_stand_rederive.py [--zones common/vector_stand_zones.json]

Run after the engine's placement rules change (docs/SEA_DEFECTS_2026-11-28.md): the lines are a function of the polygons and the layout, so no vision model is involved.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("STAND_ZONES_PATH", os.path.join(HERE, "..", "lambdas", "common", "vector_stand_zones.json"))

import vector_stand_build as vb  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zones", default=os.environ["STAND_ZONES_PATH"])
    a = ap.parse_args()
    os.environ["STAND_ZONES_PATH"] = a.zones
    from engine import stand_zone as sz
    sz.ZONES_PATH = a.zones
    sz.reload()
    zones = json.load(open(a.zones))["zones"]
    vb.lines_and_shapes(zones, a.zones)
    print(sum(1 for z in zones.values() if z.get("usable")), "usable of", len(zones))


if __name__ == "__main__":
    main()
