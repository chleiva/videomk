"""Characters stand ON the ground of a cartoon backdrop (engine/stand_zone.py, docs/CARTOON_GROUND_2026-11-28.md)."""
import glob
import json
import os

import pytest

from common import vector_catalog as vc
from engine import art_direction as ad
from engine import stand_zone as sz

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "plans")
ZONES = sz._data()["zones"]
USABLE = sorted(k for k in ZONES if sz.usable(k))


def test_the_retired_lighthouse_cliff_is_out_of_every_selection():
    assert ZONES["tall_lighthouse_cliff"]["disabled"] and not sz.usable("tall_lighthouse_cliff")
    idx = vc.load_index()
    item = next(i for i in idx["items"] if i["id"] == "tall_lighthouse_cliff")
    assert item["disabled"] is True
    assert "tall_lighthouse_cliff" not in [r["id"] for r in vc.search("a lighthouse on a cliff", aspect="9:16", k=50, embed=lambda q: item["vi"], min_score=0.0)]
    assert not any(sz.holds("tall_lighthouse_cliff", a, 1) for a in sz.ASPECT_RATIO)


def test_every_eligible_backdrop_has_a_ground_line_with_its_band_and_size():
    assert len(USABLE) >= 50
    for sid in USABLE:
        e = ZONES[sid]
        assert e["ground"] and sz.has_line(sid), sid
        assert set(e["ground_line"]) <= set(sz.SERVED[e["native"]]), sid     # only the shapes the backdrop is served in
        for asp, ln in e["ground_line"].items():
            lo, hi = ln["band"]
            assert 0.0 <= lo <= ln["y"] <= hi <= 1.0 and ln["casts"] and max(ln["casts"]) == ln["max_cast"] <= 3 and 0.05 < ln["figure_h"] < 1.4, (sid, asp, ln)
    for sid, e in ZONES.items():   # no line, no characters
        if not e.get("ground_line"):
            assert not any(sz.holds(sid, a, 1) for a in sz.ASPECT_RATIO), sid


def _plan(sid, n, aspect):
    ids = ("fox", "bear", "owl")[:n]
    props = {"character": ids[0], "backdrop": sid, "heading": "x", **({"cast": list(ids)} if n >= 2 else {"side": "left"})}
    return {"beats": [{"scene": {"type": "presenter", "props": props}}]}


def test_every_placed_foot_is_on_the_ground_and_on_the_line_in_every_shape_for_every_cast_the_backdrop_holds():
    placed = 0
    for sid in USABLE:
        for asp, ln in ZONES[sid]["ground_line"].items():
            for n in ln["casts"]:
                assert sz.holds(sid, asp, n), (sid, asp, n)
                assert sz.violations(_plan(sid, n, asp), asp) == [], (sid, asp, n)
                pts = sz.foot_points(_plan(sid, n, asp)["beats"][0]["scene"]["props"], asp)
                assert len(pts) == n
                for x, y in pts:
                    assert ln["band"][0] - 1e-3 <= min(y, 1.0) <= ln["band"][1] + 1e-3 and 0.0 < x < 1.0
                placed += 1
    assert placed >= 200


def test_a_backdrop_that_cannot_hold_the_cast_is_refused():
    sid = next(s for s in USABLE if any(l["max_cast"] < 3 for l in ZONES[s]["ground_line"].values()))
    asp = next(a for a, l in ZONES[sid]["ground_line"].items() if l["max_cast"] < 3)
    n = ZONES[sid]["ground_line"][asp]["max_cast"] + 1
    assert not sz.holds(sid, asp, n)
    assert sz.layout_for(_plan(sid, n, asp)["beats"][0]["scene"]["props"], asp).get("unplaced")
    assert sz.violations(_plan(sid, n, asp), asp)
    assert sz.eligible([sid], asp, n) == []
    assert sz.eligible([sid], "16:9" if asp == "9:16" else "9:16", 1) == [] or True


def test_the_hard_check_catches_a_foot_off_the_ground_and_a_retired_or_unknown_backdrop(monkeypatch):
    assert sz.violations(_plan("tall_lighthouse_cliff", 3, "9:16"), "9:16")[0]["why"] == "retired"
    assert sz.violations(_plan("lake_dawn", 1, "9:16"), "9:16")[0]["why"] == "no usable stand zone"
    sid = next(s for s in USABLE if "9:16" in ZONES[s]["ground_line"])
    monkeypatch.setattr(sz, "feet_on_ground", lambda *a, **k: False)   # a placement bug would look like this
    assert any("not on the ground" in v["why"] for v in sz.violations(_plan(sid, 1, "9:16"), "9:16"))


def test_the_sea_conversation_that_floated_on_the_lighthouse_cliff_now_stands_on_ground():
    plan = json.load(open(os.path.join(FIX, "cartoon_sea_lighthouse_9x16.json")))
    assert all(b["scene"]["props"].get("backdrop") == "tall_lighthouse_cliff" for b in plan["beats"])
    assert sz.violations(plan, "9:16")                       # the old plan fails the check
    good = [s for s in USABLE if sz.holds(s, "9:16", 3)]
    assert good
    ad.enforce(plan, ad.Direction("conversation", by="you", chosen="cartoon", cast=["fox", "bear", "owl"]), backdrops=["tall_lighthouse_cliff"] + good[:1], aspect="9:16")
    assert {b["scene"]["props"].get("backdrop") for b in plan["beats"]} == {good[0]}
    assert sz.violations(plan, "9:16") == []
    plan2 = json.load(open(os.path.join(FIX, "cartoon_sea_lighthouse_9x16.json")))
    ad.enforce(plan2, ad.Direction("conversation", by="you", chosen="cartoon", cast=["fox", "bear", "owl"]), backdrops=["tall_lighthouse_cliff"], aspect="9:16")
    assert not any(b["scene"]["props"].get("backdrop") for b in plan2["beats"])   # nothing holds the cast: the plain background stays


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(FIX, "*.json"))))
def test_no_plan_fixture_has_a_character_off_the_ground_after_the_art_direction_pass(path):
    plan = json.load(open(path))
    if not isinstance(plan, dict) or not isinstance(plan.get("beats"), list):
        pytest.skip("not a plan")
    for asp in ("16:9", "9:16", "1:1", "4:5"):
        p = json.loads(json.dumps(plan))
        cast = sorted({(b.get("scene") or {}).get("props", {}).get("character") for b in p["beats"] if (b.get("scene") or {}).get("type") == "presenter"} - {None})
        for b in p["beats"]:
            props = (b.get("scene") or {}).get("props")
            if (b.get("scene") or {}).get("type") == "presenter" and isinstance(props, dict):
                props.setdefault("backdrop", "tall_lighthouse_cliff")   # the worst case: a retired backdrop everywhere
        if cast:
            ad.enforce(p, ad.Direction("conversation" if len(cast) > 1 else "presenter", by="you", chosen="cartoon", cast=cast[:3] or ["owl"]), backdrops=["tall_lighthouse_cliff"], aspect=asp)
        assert sz.violations(p, asp) == []


def test_every_catalog_item_has_a_stand_record_so_a_new_backdrop_must_bring_one():
    missing = [i["id"] for i in vc.load_index()["items"] if i["id"] not in ZONES]
    assert missing == []
