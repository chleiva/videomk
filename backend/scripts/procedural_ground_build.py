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


def main() -> None:
    data = json.load(open(PATH))
    z = {
        "usable": True, "native": "any", "procedural": True, "horizon": HORIZON,
        "ground": [[[0.0, HORIZON["16:9"]], [1.0, HORIZON["16:9"]], [1.0, 1.0], [0.0, 1.0]]],
        "ground_by_aspect": {a: [[[0.0, h], [1.0, h], [1.0, 1.0], [0.0, 1.0]]] for a, h in HORIZON.items()},
        "hazards": [], "reason": "drawn floor: flat ground from the horizon to the bottom edge, in every shape", "model": "procedural",
    }
    data["zones"][sz.PROC_ID] = z
    json.dump(data, open(PATH, "w"), separators=(",", ":"))
    sz.reload()
    z["ground_line"] = sz.derive_lines(sz.PROC_ID)
    json.dump(data, open(PATH, "w"), separators=(",", ":"))
    sz.reload()
    for a in sz.ASPECT_RATIO:
        print(a, z["ground_line"].get(a), [n for n in (1, 2, 3) if sz.holds(sz.PROC_ID, a, n)])


if __name__ == "__main__":
    main()
