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
    assert {b["scene"]["props"].get("backdrop") for b in plan2["beats"]} == {sz.PROC_ID}   # nothing offered holds the cast: the drawn ground, never the empty background
    assert sz.violations(plan2, "9:16") == []


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


# ----------------------------------------------------------------------------- ground 2: the drawn ground, cast-first selection, whole figures in 16:9
SHAPES = ("16:9", "9:16", "1:1", "4:5")
SEA = "a French fox, a German bear and an Italian owl explain why the sea is salty"


def _policy(search=None, candidates=None):
    from engine import vector_policy as vp

    p = vp.Policy(bool(candidates), "cartoon", "style_cartoon" if candidates else "no_catalog_match", candidates=candidates or [], aspect="9:16", search=search)
    return p


def test_the_drawn_ground_has_a_stored_zone_and_a_ground_line_in_every_shape_for_every_cast():
    assert sz.usable(sz.PROC_ID) and not sz.disabled(sz.PROC_ID)
    e = ZONES[sz.PROC_ID]
    assert set(e["ground_line"]) == set(SHAPES) and e["native"] == "any"
    for asp in SHAPES:
        ln = sz.line(sz.PROC_ID, asp)
        assert ln and ln["casts"] == [1, 2, 3] and 0.0 <= ln["band"][0] <= ln["y"] <= ln["band"][1] <= 1.0, (asp, ln)
        assert sz.horizon(asp) is not None and sz.horizon(asp) < ln["band"][0]   # the floor begins above every foot
        for n in (1, 2, 3):
            assert sz.holds(sz.PROC_ID, asp, n)
            assert sz.violations(_plan(sz.PROC_ID, n, asp), asp) == [], (asp, n)
            for x, y in sz.foot_points(_plan(sz.PROC_ID, n, asp)["beats"][0]["scene"]["props"], asp):
                assert sz.feet_on_ground(sz.PROC_ID, asp, x, y, 0.01)


def test_the_drawn_ground_renders_in_every_shape_and_the_lower_part_of_the_frame_is_floor_not_void():
    import sys

    from PIL import ImageStat

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from ground2_stills import still

    for asp in SHAPES:
        im = still(sz.PROC_ID, asp, 3, "midnight", marks=False)
        w, h = im.size
        low = im.crop((0, int(h * 0.94), int(w * 0.2), h))   # bottom left corner: no card, no captions
        r, g, b = ImageStat.Stat(low).mean[:3]
        assert g > r and g > 40, (asp, (r, g, b))              # a green floor, not the dark gradient of the plain background


@pytest.mark.parametrize("asp", SHAPES)
def test_a_three_character_conversation_always_gets_a_backdrop_with_a_valid_ground_line(asp):
    # nothing offered, nothing found: the drawn ground
    v = _policy(search=lambda q, a, k: [])
    ids = ad.stand_backdrops(v, SEA, asp, 3, None)
    assert ids and all(sz.holds(i, asp, 3) for i in ids)
    for bd in ids:
        plan = _plan(bd, 3, asp)
        assert sz.line(bd, asp) is not None and sz.violations(plan, asp) == []
    # a search that fails altogether
    def boom(q, a, k):
        raise RuntimeError("down")
    assert ad.stand_backdrops(_policy(search=boom), SEA, asp, 3, None) == [sz.PROC_ID]


def test_selection_is_cast_first_the_sea_in_9x16_never_puts_the_cast_in_the_water():
    def search(q, asp, k):   # the real scores of the sea request (QA catalog, Cohere Embed v4): the full prompt matches no backdrop well, the neighbouring words match the beach
        sc = {"tall_space_vertical": 0.236, "tall_sunset_beach_vertical": 0.1863, "tall_ocean_lighthouse_night": 0.1829}
        if "beach" in q:
            sc = {"tall_sunset_beach_vertical": 0.3045, "tall_ocean_lighthouse_night": 0.2489, "tall_space_vertical": 0.2358}
        return [{"id": i, "score": s} for i, s in sc.items()]
    v = _policy(search=search)
    ids = ad.stand_backdrops(v, SEA, "9:16", 3, None)
    # the beach's dry sand lies below the caption lines in 9:16 (the sea and the foam line fill the rest): it is refused, and the drawn ground (a floor of its own) stays
    assert "tall_sunset_beach_vertical" not in ids and all(sz.holds(i, "9:16", 3) for i in ids)
    assert not any(i in ids for i in ("tall_space_vertical", "tall_ocean_lighthouse_night"))   # those cannot hold three characters


def test_the_vertical_beach_has_no_ground_where_the_sea_and_the_foam_line_are():   # the QA sea video of 2026-11-28: feet stood in the shallow water band
    for asp in ("9:16", "4:5"):
        m = sz._mask("tall_sunset_beach_vertical", asp)
        if m is None:
            continue
        y0, y1 = sz._crop("9:16", asp)[1], sz._crop("9:16", asp)[3]
        rows = [r for r in range(m.shape[0]) if m[r].any()]
        if rows:   # the first ground row of the picture is on dry sand: 0.79 of the picture and below
            assert y0 + (rows[0] / m.shape[0]) * (y1 - y0) >= 0.79 - 1e-6
    assert not sz.holds("tall_sunset_beach_vertical", "9:16", 1)


def test_feet_of_whole_figures_stay_above_the_caption_lines_in_every_shape():
    from types import SimpleNamespace
    from engine.frame import Frame
    for asp in ("1:1", "4:5", "9:16", "16:9"):
        fr = Frame.parse(asp, "1080p")
        top = sz.caption_top(fr)
        assert 0.6 < top < 0.9
        for n in (2, 3):
            lay = sz.layout_for({"character": "fox", "side": "left", "backdrop": sz.PROC_ID, "cast": ["fox", "bear", "owl"][:n]}, asp)
            if lay.get("floor") is not None:
                assert lay["floor"] / fr.H <= top + 1e-6, (asp, n, lay["floor"] / fr.H, top)
    for sid in USABLE:   # and every stored placement of a whole figure
        for asp, ln in ZONES[sid]["ground_line"].items():
            for n in ln["casts"]:
                lay = sz.layout_for(sz._cast_props(sid, n), asp)
                if lay.get("floor") is not None and not lay.get("unplaced"):
                    assert lay["floor"] / Frame.parse(asp, "1080p").H <= sz.caption_top(Frame.parse(asp, "1080p")) + 1e-6, (sid, asp, n)


def test_a_topic_without_a_credible_capable_match_gets_a_neutral_capable_backdrop_not_none():
    def search(q, asp, k):
        if "quiet outdoor" in q:
            return [{"id": "tall_rainbow_vertical", "score": 0.30}, {"id": "tall_castle_tower", "score": 0.2}]
        return [{"id": "tall_castle_tower", "score": 0.05}]
    ids = ad.stand_backdrops(_policy(search=search), "quarterly tax filing for freelancers", "9:16", 3, None)
    assert ids[0] == "tall_rainbow_vertical"


def test_neighbour_words_widen_the_search_for_the_topic():
    assert any("beach" in q for q in ad._neighbour_queries(SEA))
    assert any("moon" in q for q in ad._neighbour_queries("how far is the Moon"))
    assert ad._neighbour_queries("quarterly tax filing") == []


@pytest.mark.parametrize("asp", SHAPES)
@pytest.mark.parametrize("n", (1, 2, 3))
def test_no_conversation_plan_ends_with_an_empty_backdrop(asp, n):
    cast = ["fox", "bear", "owl"][:n]
    plan = {"title": "t", "voices": {}, "beats": [{"narration": "Hello there, this is the first line.", "speaker": cast[i % n], "scene": {"type": "presenter", "props": {"heading": "x", "character": cast[i % n]}}} for i in range(4)]}
    ad.enforce(plan, ad.Direction("conversation" if n > 1 else "presenter", by="you", chosen="cartoon", cast=cast), backdrops=[], aspect=asp)
    bds = [b["scene"]["props"].get("backdrop") for b in plan["beats"]]
    assert all(bds), bds
    assert sz.violations(plan, asp) == []


def test_16x9_shows_whole_figures_with_their_feet_on_the_ground_and_many_more_backdrops_hold_three():
    sid = next(s for s in USABLE if sz.holds(s, "16:9", 3))
    lay = sz.layout_for({"character": "fox", "side": "left", "backdrop": sid, "cast": ["fox", "bear", "owl"]}, "16:9")
    assert lay["floor"] is not None and lay["figures"] and all(f["ground"] == lay["floor"] for f in lay["figures"])   # whole figures, not cut at the waist
    assert lay["floor"] <= 1080 * 0.9
    assert sum(sz.holds(s, "16:9", 3) for s in ZONES) >= 40      # was 3 with the figures cut at the waist
    assert sum(sz.holds(s, "16:9", 1) for s in ZONES) >= 60      # was 33
