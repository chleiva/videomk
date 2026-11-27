"""The five-character cast (docs/CHARACTER_LIBRARY.md): assets are complete, metadata is well formed, every character draws in every pose family."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from PIL import Image  # noqa: E402

from engine import vector_character as vc  # noqa: E402

CAST = ["ines", "david", "priya", "mateo", "fox", "owl", "bear"]
PARTS = ["head", "torso", "upper_arm", "lower_arm", "upper_leg", "lower_leg", "eyes_open", "eyes_closed", "mouth_closed", "mouth_half", "mouth_wide"]
META_KEYS = {"id", "name", "role", "species", "age_group", "tags", "voice_hint", "suitable_topics", "provenance"}


def test_cast_is_listed():
    assert set(CAST) <= set(vc.character_ids())


@pytest.mark.parametrize("cid", CAST)
def test_assets_and_metadata(cid):
    folder = os.path.join(vc.DIR, cid)
    man = json.load(open(os.path.join(folder, "manifest.json")))
    assert list(man["parts"]) == PARTS
    for name, p in man["parts"].items():
        assert os.path.getsize(os.path.join(folder, p["file"])) > 500
        if name in ("upper_arm", "lower_arm", "upper_leg", "lower_leg"):
            assert "pivot" in p and "end" in p
    meta = json.load(open(os.path.join(folder, "meta.json")))
    assert META_KEYS <= set(meta) and meta["id"] == cid
    assert set(meta["voice_hint"]) == {"en", "es"} and all(meta["voice_hint"].values())
    assert sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)) < 1_000_000   # a character stays under 1 MB of vector pieces


@pytest.mark.parametrize("cid", CAST)
def test_draws_in_every_pose_family(cid):
    ch = vc.load(cid, 1.2, 1.0, back_tint=0.93)
    for pose in ({}, {"arms": ((10.0, 5.0), (150.0, 20.0))}, {"mouth": "wide", "blink": True, "torso_sy": 1.016, "head_sy": 0.97},
                 {"feet": vc.walk_feet(1.0, 40.0, vc.HIP_H0, 10.0)}):
        im = Image.new("RGBA", (400, 500), (200, 220, 240, 255))
        ch.draw(im, 200, 470, pose)
        assert im.getbbox() is not None
        # something was painted that is not the backdrop colour
        px = list(im.convert("RGB").getdata())
        assert any(p != (200, 220, 240) for p in px)
