#!/usr/bin/env python3
"""Write the stand record of the DRAWN ground (engine/stand_zone.PROC_ID, engine/procedural_ground.py) into common/vector_stand_zones.json, like vector_stand_build.py does for a catalog
backdrop: the ground outline per video shape (from the horizon down to the bottom edge, full width) and the ground lines derived with the engine's own placement.

  python backend/scripts/procedural_ground_build.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from engine import stand_zone as sz  # noqa: E402

PATH = os.path.join(HERE, "..", "lambdas", "common", "vector_stand_zones.json")
HORIZON = {"16:9": 0.60, "9:16": 0.60, "1:1": 0.58, "4:5": 0.58}   # a share of the frame height: the floor begins here and carries on to the bottom edge


def record(horizon, reason):
    return {
        "usable": True, "native": "any", "procedural": True, "horizon": horizon,
        "ground": [[[0.0, horizon["16:9"]], [1.0, horizon["16:9"]], [1.0, 1.0], [0.0, 1.0]]],
        "ground_by_aspect": {a: [[[0.0, h], [1.0, h], [1.0, 1.0], [0.0, 1.0]]] for a, h in horizon.items()},
        "hazards": [], "reason": reason, "model": "procedural",
    }


def main() -> None:
    data = json.load(open(PATH))
    zs = {sz.PROC_ID: record(HORIZON, "drawn floor: flat ground from the horizon to the bottom edge, in every shape"),
          sz.BEACH_ID: record(HORIZON, "drawn beach: sea above the horizon (never under a foot), a dry sand floor from the horizon to the bottom edge, in every shape")}
    data["zones"].update(zs)
    json.dump(data, open(PATH, "w"), separators=(",", ":"))
    sz.reload()
    for sid, z in zs.items():
        z["ground_line"] = sz.derive_lines(sid)
    json.dump(data, open(PATH, "w"), separators=(",", ":"))
    sz.reload()
    for sid, z in zs.items():
        for a in sz.ASPECT_RATIO:
            print(sid, a, z["ground_line"].get(a), [n for n in (1, 2, 3) if sz.holds(sid, a, n)])


if __name__ == "__main__":
    main()
