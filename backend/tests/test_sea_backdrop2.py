"""A topical request never gets an off-theme backdrop (docs/SEA_BACKDROP_2_2026-11-28.md): the sea keeps sea and sand, in every shape; card titles keep a constant top margin."""
import os
import sys

import pytest

from engine import art_direction as ad
from engine import stand_zone as sz
from engine import watermark_spec as ws
from engine.frame import Frame

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

SHAPES = ("9:16", "4:5", "1:1", "16:9")
SEA = "a cartoon explaining why the sea is salty"
MEADOW = ("meadow_house_rainbow", "tall_meadow_cottage", "park_picnic_day", "farm_barn_morning")   # unrelated places that score high for a loose cartoon query


def _policy(search):
    from engine import vector_policy as vp
    return vp.Policy(False, "cartoon", "no_catalog_match", candidates=[], aspect="9:16", search=search)


def _search_prefers_meadows(q, asp, k):   # what QA saw: the unrelated meadow outscored every sea picture that could hold the cast
    import json
    from common import vector_catalog as vc
    ids = [i["id"] for i in vc.load_index()["items"]]
    sc = {i: 0.2 for i in ids}
    for i in ids:
        if any(w in i for w in ("meadow", "park", "farm", "garden", "cottage", "village")):
            sc[i] = 0.55
        if any(w in i for w in ("beach", "sea", "ocean", "coast", "lake", "harbour", "reef")):
            sc[i] = 0.12
    return [{"id": i, "score": s} for i, s in sc.items()]


def _plan(bd, n, asp):
    return {"beats": [{"scene": {"type": "presenter", "props": {"character": "fox", "side": "left", "backdrop": bd, **({"cast": ["fox", "bear", "owl"][:n]} if n > 1 else {})}}}]}


@pytest.mark.parametrize("asp", SHAPES)
@pytest.mark.parametrize("n", (1, 2, 3))
def test_a_sea_request_never_ends_with_an_off_theme_backdrop(asp, n):
    wet = ad._sea_ids()
    assert wet
    for search in (_search_prefers_meadows, lambda q, a, k: [], None):
        ids = ad.stand_backdrops(_policy(search), SEA, asp, n, None)
        assert ids
        for i in ids:
            assert i in wet or i == sz.BEACH_ID, (asp, n, i)
            assert sz.holds(i, asp, n)
            assert sz.violations(_plan(i, n, asp), asp) == [], (asp, n, i)   # feet on the ground, none in the water


def test_in_9x16_where_no_wet_backdrop_holds_a_cast_the_drawn_beach_is_used():
    assert ad.stand_backdrops(_policy(_search_prefers_meadows), SEA, "9:16", 3, None) == [sz.BEACH_ID]
    assert ad.stand_backdrops(_policy(_search_prefers_meadows), "why do seasons change", "9:16", 3, None)[0] != sz.BEACH_ID   # a non-sea topic is untouched


def test_sea_topic_words():
    for t in ("Why is the sea salty", "life at the beach", "how rivers form", "El océano y las mareas explicadas, la playa", "a lighthouse by the coast"):
        assert ad.sea_topic(t), t
    for t in ("why do seasons change", "how a search engine works", "the wavelength of light", "tidy rooms"):
        assert not ad.sea_topic(t), t


def test_the_enforce_fallback_for_a_sea_plan_is_the_beach_and_for_others_the_meadow_floor():
    sea = {"title": "Why is the sea salty?", "beats": [{"narration": "Rain washes salt into the sea.", "scene": {"type": "presenter", "props": {"heading": "Salt", "character": "fox"}}}], "voices": {}}
    d = ad.Direction("presenter", by="you", chosen="cartoon", cast=["fox"])
    for plan, want in ((sea, sz.BEACH_ID), ({**sea, "title": "Why is the sky blue?", "beats": [{"narration": "Light scatters.", "scene": {"type": "presenter", "props": {"heading": "Sky", "character": "fox"}}}]}, sz.PROC_ID)):
        ad.enforce(plan, d, backdrops=[], aspect="9:16")
        assert {b["scene"]["props"].get("backdrop") for b in plan["beats"]} == {want}


@pytest.mark.parametrize("asp", SHAPES)
def test_the_beach_floor_is_dry_and_its_sea_is_above_the_horizon(asp):
    from ground2_stills import still

    e = sz.entry(sz.BEACH_ID)
    assert e["usable"] and not e.get("hazards")
    for n in (1, 3):
        im = still(sz.BEACH_ID, asp, n, "paper", marks=False)
        w, h = im.size
        hz = sz.horizon(asp, sz.BEACH_ID)
        px = im.getpixel((int(w * 0.03), int(h * (hz + 0.03))))   # just under the foam line, left edge: no card there
        assert px[0] > px[2] + 25, (asp, px)                     # sand (warm), not water (blue)
        sea = im.getpixel((int(w * 0.03), int(h * (hz - 0.03))))
        assert sea[2] > sea[0], (asp, sea)                       # the sea above the horizon is blue
        for x, y in sz.foot_points(_plan(sz.BEACH_ID, n, asp)["beats"][0]["scene"]["props"], asp):
            assert y > hz + 0.02, (asp, y, hz)                   # no foot on the sea or on the foam line


@pytest.mark.parametrize("asp", ("9:16", "1:1", "4:5"))
def test_card_titles_keep_a_constant_top_margin_the_mark_never_reaches(asp):
    from types import SimpleNamespace
    from engine.scenes.elements import presenter as pe

    fr = Frame.parse(asp, "1080p")
    tops = set()
    for props in ({"heading": "T", "character": "fox"}, {"heading": "T", "points": ["a", "b"], "character": "fox"}, {"heading": "T", "character": "fox", "cast": ["fox", "bear"]}, {"heading": "T", "character": "fox", "backdrop": sz.PROC_ID}):
        for cap in (True, False):
            ctx = SimpleNamespace(frame=fr, captions=cap, top=fr.margin_top, bottom=fr.content_bottom(cap), box=fr.box(cap))
            lay = pe.layout(props, ctx)
            if lay.get("unplaced"):
                continue
            tops.add(round(lay["content"][1], 3))
    assert tops == {pe.CARD_TOP[asp]}, tops                        # one constant, no input but the shape
    lowest = 0.0
    for spec in ({"position": "auto", "mode": "videomk", "style": "lockup", "size": "medium"}, {"position": "tl", "mode": "custom", "size": "medium"}, {"position": "auto", "mode": "custom", "size": "medium"}):
        r = ws.layout(spec, fr, 1.0)["rect"]
        if r[1] < fr.H * 0.5 and r[0] < fr.W * 0.5:                # a top-left mark
            lowest = max(lowest, r[3])
    assert lowest < pe.CARD_TOP[asp]
