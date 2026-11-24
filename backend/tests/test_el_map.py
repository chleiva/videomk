"""The map element: resolver, projections, sanitize, anchors, prepare (with a fake Wikidata, never the network), every mode on every theme, end state, speed."""
import copy
import math
import time

import numpy as np
import pytest

from tests.element_utils import changed, render, themes
from engine import sync
from engine.scenes import ELEMENTS
from engine.scenes.elements import _geo, _mapdraw as MD, _project as P, _resolve as R, maps
from engine.scenes.registry import PrepareCtx

EL = ELEMENTS["map"]
CTX = PrepareCtx(video_id="v", beat_id="b", narration="", duration=8.0)


# ----------------------------------------------------------------------------- data
def test_the_bundled_data_is_small_and_loads_lazily():
    import os
    total = sum(os.path.getsize(os.path.join(_geo.GEO_DIR, f)) for f in os.listdir(_geo.GEO_DIR))
    assert total < 8 * 1024 * 1024
    assert len(_geo.layer("adm0_50").meta) > 200 and len(_geo.layer("adm1").meta) > 3000 and len(_geo.places()) > 7000
    assert _geo.layer("adm0_50") is _geo.layer("adm0_50")


# ----------------------------------------------------------------------------- resolver
@pytest.mark.parametrize("name,role,kind,ident", [
    ("USA", "shape", "country", "USA"), ("UK", "shape", "country", "GBR"), ("Czechia", "shape", "country", "CZE"), ("Côte d'Ivoire", "shape", "country", "CIV"),
    ("Cote d'Ivoire", "shape", "country", "CIV"), ("Burma", "shape", "country", "MMR"), ("Holland", "shape", "country", "NLD"), ("texas", "shape", "admin1", None),
    ("São Paulo", "point", "point", None), ("Sao Paulo", "point", "point", None), ("Saint Petersburg", "point", "point", None), ("St. Petersburg", "point", "point", None),
    ("Zürich", "point", "point", None), ("Paris, France", "point", "point", None), ("NYC", "point", "point", None), ("Washington DC", "point", "point", None),
    ("Brazil", "point", "point", None), ("Europe", "any", "frame", None),
])
def test_names_resolve_with_aliases_and_accents(name, role, kind, ident):
    e = R.resolve_offline(name, role)
    assert e["t"] == kind and (ident is None or e["id"] == ident)


def test_known_places_land_in_the_right_spot():
    for name, lon, lat in (("Paris", 2.33, 48.87), ("Tokyo", 139.7, 35.7), ("Saint Petersburg", 30.3, 59.9), ("Sao Paulo", -46.6, -23.6)):
        e = R.resolve_offline(name, "point")
        assert abs(e["lon"] - lon) < 0.5 and abs(e["lat"] - lat) < 0.5, e


@pytest.mark.parametrize("name,role", [("Springfield", "point"), ("Birmingham", "point"), ("Georgia", "shape"), ("Georgia", "any"), ("Washington", "point")])
def test_ambiguous_names_raise(name, role):
    with pytest.raises(R.Ambiguous):
        R.resolve_offline(name, role)


def test_an_unknown_name_raises_and_a_qualifier_that_matches_nothing_is_not_guessed():
    for n, role in (("Atlantis", "point"), ("Paris, Texas", "point"), ("Eiffel Tower", "shape"), ("", "point")):
        with pytest.raises(R.ResolveError):
            R.resolve_offline(n, role)


def test_a_city_is_not_a_region_to_highlight():
    with pytest.raises(R.NotFound):
        R.resolve_offline("Lyon", "shape")


# ----------------------------------------------------------------------------- Wikidata (fake)
def fake_wikidata(entities, search=None):
    def http(url, timeout=4.0):
        assert timeout <= 4.0 and url.startswith("https://www.wikidata.org/")
        if "wbsearchentities" in url:
            return {"search": search or [{"id": k, "label": v["label"], "match": {"text": v["label"]}, "description": v.get("desc", "")} for k, v in entities.items()]}
        return {"entities": {k: {"labels": {"en": {"value": v["label"]}}, "claims": {"P625": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {
            "latitude": v["lat"], "longitude": v["lon"], "globe": "http://www.wikidata.org/entity/Q2"}}}}]}} for k, v in entities.items()}}
    return http


def test_a_landmark_is_looked_up_on_wikidata_and_cached():
    R._WD_CACHE.clear()
    calls = []
    inner = fake_wikidata({"Q243": {"label": "Eiffel Tower", "lat": 48.8584, "lon": 2.2945}})

    def http(url, timeout=4.0):
        calls.append(url)
        return inner(url, timeout)
    e = R.wikidata_lookup("Eiffel Tower", http)
    assert e["t"] == "point" and abs(e["lat"] - 48.8584) < 1e-4 and e["s"] == "wd"
    n = len(calls)
    R.wikidata_lookup("eiffel tower", http)
    assert len(calls) == n


def test_wikidata_needs_an_exact_label_and_refuses_several_far_matches():
    R._WD_CACHE.clear()
    with pytest.raises(R.NotFound):
        R.wikidata_lookup("Eiffel Tower", fake_wikidata({"Q1": {"label": "Eiffel Tower Restaurant", "lat": 36.1, "lon": -115.1}}))
    with pytest.raises(R.Ambiguous):
        R.wikidata_lookup("Springfield Hill", fake_wikidata({"Q1": {"label": "Springfield Hill", "lat": 40.0, "lon": -80.0}, "Q2": {"label": "Springfield Hill", "lat": 10.0, "lon": 20.0}}))
    R._WD_CACHE.clear()
    e = R.wikidata_lookup("Twin Hill", fake_wikidata({"Q1": {"label": "Twin Hill", "lat": 40.0, "lon": -80.0}, "Q2": {"label": "Twin Hill", "lat": 40.01, "lon": -80.01}}))
    assert abs(e["lat"] - 40.0) < 0.05


def test_wikidata_ignores_other_worlds_and_network_errors_become_resolve_errors():
    R._WD_CACHE.clear()

    def moon(url, timeout=4.0):
        d = fake_wikidata({"Q9": {"label": "Tycho", "lat": -43.3, "lon": -11.2}})(url, timeout)
        for ent in d.get("entities", {}).values():
            ent["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]["globe"] = "http://www.wikidata.org/entity/Q405"
        return d
    with pytest.raises(R.NotFound):
        R.wikidata_lookup("Tycho", moon)

    def boom(url, timeout=4.0):
        raise TimeoutError("slow")
    with pytest.raises(R.ResolveError):
        R.wikidata_lookup("Some Landmark", boom)


def test_prepare_resolves_offline_names_and_falls_back_to_wikidata_for_landmarks(monkeypatch):
    R._WD_CACHE.clear()
    monkeypatch.setattr(R, "_http_json", fake_wikidata({"Q243": {"label": "Eiffel Tower", "lat": 48.8584, "lon": 2.2945}}))
    patch = maps.prepare({"mode": "points", "points": ["Eiffel Tower", "Rome"]}, CTX)
    res = patch["resolved"]
    assert res["point|Eiffel Tower"]["s"] == "wd" and res["point|Rome"]["s"] == "ne"
    props = EL.sanitize({"mode": "points", "points": ["Eiffel Tower", "Rome"], **patch})
    render("map", props, 6.0, 8.0)                                  # draws from the patch alone


def test_prepare_raises_when_a_place_is_unknown_or_ambiguous_or_the_network_is_down(monkeypatch):
    R._WD_CACHE.clear()
    monkeypatch.setattr(R, "_http_json", fake_wikidata({}, search=[]))
    with pytest.raises(R.ResolveError):
        maps.prepare({"mode": "route", "stops": ["Paris", "Nowhereville Castle"]}, CTX)
    with pytest.raises(R.ResolveError):
        maps.prepare({"mode": "points", "points": ["Springfield"]}, CTX)
    with pytest.raises(R.ResolveError):
        maps.prepare({"mode": "regions", "regions": ["France", "Eiffel Tower"]}, CTX)

    def boom(url, timeout=4.0):
        raise OSError("offline")
    monkeypatch.setattr(R, "_http_json", boom)
    with pytest.raises(R.ResolveError):
        maps.prepare({"mode": "points", "points": ["Some Landmark Far Away"]}, CTX)
    assert maps.prepare({"mode": "route", "stops": ["Paris", "Lyon"]}, CTX)["resolved"]    # offline names never need the network


def test_the_fallback_is_a_title_card_with_the_title_or_the_main_place():
    assert maps.fallback({"mode": "route", "stops": ["Paris", "Lyon"], "title": "A trip"}) == ("title", {"title": "A trip"})
    assert maps.fallback({"mode": "arcs", "arcs": [["A", "B"]]})[1]["title"] == "B"
    assert maps.fallback({"mode": "regions", "regions": ["France"]})[1]["title"] == "France"


# ----------------------------------------------------------------------------- projections
def test_projections_put_known_coordinates_where_expected():
    ee = P.Proj("equalearth")
    assert np.allclose(ee.xy(0, 0), [0, 0]) and abs(ee.xy(-179.99, 0)[0] + 2.7066) < 1e-3 and abs(ee.xy(0, 90)[1] - 1.3174) < 1e-3
    o = P.Proj("ortho", lon0=10, lat0=50)
    x, y, z = o.forward(10, 50)
    assert abs(x) < 1e-9 and abs(y) < 1e-9 and abs(z - 1) < 1e-9
    assert o.forward(190, -50)[2] < -0.99                              # the antipode is hidden
    x, y, _ = o.forward(100, 0)
    assert x > 0.9                                                     # east of the centre is to the right
    m = P.Proj("mercator")
    assert abs(m.xy(0, 0)[1]) < 1e-9 and m.xy(0, 60)[1] > m.xy(0, 30)[1] > 0
    a = P.Proj("albers", lon0=-96, lat0=37.5, phi1=29.5, phi2=45.5)
    ny, la = a.xy(-74, 40.7), a.xy(-118, 34)
    assert ny[0] > 0 > la[0] and abs(ny[1] - la[1]) < 0.2 and np.allclose(a.xy(-96, 37.5), [0, 0], atol=1e-9)


def test_the_projection_follows_the_extent():
    def pick(*ll):
        return MD.choose_projection(np.array(ll, float))[0].kind
    assert pick((-9, 37), (-6, 42)) == "albers"                                        # Portugal-sized
    assert pick((-125, 25), (-67, 49)) == "albers"                                      # the USA
    assert pick((-18, -35), (52, 37)) == "ortho"                                        # Africa
    assert pick((-170, -50), (170, 70), (0, 0), (90, 0), (-90, 0)) == "equalearth"                                 # the world
    assert pick((100, -3), (110, 3)) == "mercator"                                      # near the equator


def test_globe_rings_are_clipped_at_the_horizon_and_flat_rings_split_at_the_seam():
    o = P.Proj("ortho", lon0=0, lat0=0)
    ring = np.array([[-60, -30], [60, -30], [60, 30], [-60, 30], [-60, -30]], float)
    out = o.ring_pieces(ring)
    assert len(out) == 1 and np.hypot(out[0][:, 0], out[0][:, 1]).max() <= 1.0 + 1e-9
    assert o.ring_pieces(np.array([[170, 10], [178, 10], [178, 20], [170, 20]], float)) == []   # far side
    far = P.Proj("mercator", lon0=170)
    across = np.array([[160, 0], [-170, 0], [-170, 10], [160, 10]], float)                      # crosses 180 but not the seam at lon0+180=-10
    p = far.ring_pieces(across)
    assert len(p) == 1 and (p[0][:, 0].max() - p[0][:, 0].min()) < 1.0
    seam = P.Proj("equalearth", lon0=0)
    cut = seam.ring_pieces(np.array([[170, 0], [-170, 0], [-170, 10], [170, 10]], float))
    assert len(cut) >= 1 and all(abs(q[:, 0]).max() <= 2.71 for q in cut)


def test_great_circle_goes_the_short_way():
    gc = P.great_circle(-74, 40.7, 2.35, 48.85)
    assert gc[:, 1].max() > 48.0 and abs(gc[0, 0] + 74) < 1e-6
    over = P.great_circle(170, 0, -170, 0)
    assert abs(over[-1, 0] - 190) < 1e-6 and len(over) >= 3             # continuous over the antimeridian


# ----------------------------------------------------------------------------- sanitize
def test_sanitize_limits_and_idempotence():
    p = EL.sanitize({"mode": "regions", "regions": [f"Country {i}" for i in range(30)], "title": "T" * 99, "caption": "c" * 99, "lat": 5, "coords": [1, 2]})
    assert len(p["regions"]) == 12 and len(p["title"]) == 50 and len(p["caption"]) == 60 and "coords" not in p and "lat" not in p
    assert EL.sanitize(p) == p
    assert EL.sanitize({"stops": ["A", "B", "A"]})["mode"] == "route"                      # mode inferred; a stop may repeat
    pts = EL.sanitize({"mode": "points", "points": ["Cairo", {"name": "Nairobi", "label": "x" * 80}, ["Lima", "Capital"], "cairo"]})["points"]
    assert [x["name"] for x in pts] == ["Cairo", "Nairobi", "Lima"] and len(pts[1]["label"]) == 28
    arcs = EL.sanitize({"mode": "arcs", "arcs": [["A", "B", "l" * 50], {"from": "C", "to": "D"}, ["E", "E"], ["F"]]})["arcs"]
    assert arcs == [["A", "B", "l" * 22], ["C", "D"]]
    for bad in ({}, {"mode": "route", "stops": ["Paris"]}, {"mode": "focus"}, {"mode": "arcs", "arcs": [["A"]]}, {"mode": "points", "points": []}, {"mode": "regions", "regions": [None, ""]}):
        with pytest.raises(ValueError):
            EL.sanitize(bad)


def test_sanitize_keeps_cues_and_prepared_places_but_drops_junk():
    p = EL.sanitize({"mode": "route", "stops": ["Paris", "Lyon"], "cues": [0.5, "x", 1.5, -3, None],
                     "resolved": {"point|Paris": {"t": "point", "lon": 2.3, "lat": 48.8, "n": "Paris"}, "point|Bad": {"t": "point", "lon": 999, "lat": 0}, "x": 5}})
    assert p["cues"] == [0.5, 1.5] and list(p["resolved"]) == ["point|Paris"]
    assert EL.sanitize(p) == p


# ----------------------------------------------------------------------------- anchors and cues
def test_anchors_follow_the_mode_and_tie_reveals_to_the_words():
    assert EL.anchors(EL.sanitize({"mode": "route", "stops": ["Paris", "Lyon", "Marseille"]})) == ["Paris", "Lyon", "Marseille"]
    assert EL.anchors(EL.sanitize({"mode": "arcs", "arcs": [["A", "B"], ["A", "C"]]})) == ["B", "C"]
    assert EL.anchors(EL.sanitize({"mode": "focus", "focus": ["France"]})) == []
    props = EL.sanitize({"mode": "route", "stops": ["Paris", "Lyon", "Marseille"]})
    words = [["We", 0.2, 0.3], ["leave", 0.4, 0.8], ["Paris", 1.0, 1.4], ["then", 1.5, 1.7], ["Lyon", 3.0, 3.4], ["and", 3.5, 3.6], ["Marseille", 5.5, 6.0]]
    found = sync.apply("map", props, words, 8.0)
    assert found["items"] == 3 and found["anchored"] == 3 and props["cues"][1] > props["cues"][0] + 1.5 and props["cues"][2] > props["cues"][1] + 1.5
    assert EL.cues(props, 8.0) == [min(8.0, c) for c in props["cues"]]


def _lit(props, lt, dur=8.0, th="midnight"):
    return render("map", props, lt, dur, th, draft=True)


def test_each_item_appears_when_its_word_is_said():
    props = EL.sanitize({"mode": "points", "points": ["Cairo", "Tokyo"], "cues": [1.0, 4.0]})
    before, between, after = _lit(props, 0.9), _lit(props, 3.0), _lit(props, 6.5)
    assert changed(before, between) > 0.0003 and changed(between, after) > 0.0003


# ----------------------------------------------------------------------------- drawing
@pytest.mark.parametrize("i", range(len(EL.samples)))
def test_every_sample_shows_every_named_item_at_the_end(i):
    sample = EL.sanitize(copy.deepcopy(EL.samples[i]))
    pw, ph = MD.panel_size(800)
    m = MD.build_model(maps._spec_key(sample), pw, ph)
    assert m.notes == [], m.notes
    mode = sample["mode"]
    if mode == "regions":
        assert len(m.regions) == len(sample["regions"])
    if mode == "points":
        assert len(m.pins) == len(sample["points"])
    if mode == "route":
        assert len(m.pins) == len(sample["stops"]) and len(m.paths) == len(sample["stops"]) - 1
    if mode == "arcs":
        assert len(m.paths) == len(sample["arcs"])
    # every pin and region label ends inside the panel
    cx, cy, s = m.cam_end
    for it in m.pins:
        x, y = m.centre_px[0] + (it.anchor[0] - cx) * s, m.centre_px[1] - (it.anchor[1] - cy) * s
        assert 0 < x < m.pw and 0 < y < m.ph
        assert x + it.label_off[0] > 0 and x + it.label_off[0] + it.label_wh[0] < m.pw and y + it.label_off[1] > 0 and y + it.label_off[1] + it.label_wh[1] < m.ph


@pytest.mark.parametrize("th", ["midnight", "paper", "sunrise"])
def test_every_mode_draws_on_every_theme_and_the_end_differs_from_the_start(th):
    for sample in EL.samples:
        props = EL.sanitize(copy.deepcopy(sample))
        early, end = _lit(props, 0.0, 8.0, th), _lit(props, 8.0, 8.0, th)
        assert changed(early, end) > 0.004, (sample["mode"], th)


def test_map_without_title_or_caption_and_with_a_prepared_patch_still_draws():
    props = EL.sanitize({"mode": "focus", "focus": ["Europe"]})
    assert changed(_lit(props, 0.0), _lit(props, 0.0, 8.0, "paper")) > 0.1
    assert EL.max_per_video == 3 and EL.family == "Maps" and EL.doc.startswith("- map:")


def test_a_frame_renders_well_under_the_budget():
    from engine.canvas import Canvas
    from engine.scenes.base import SceneCtx
    from engine.theme import THEMES
    worst = 0.0
    for sample in EL.samples:
        props = EL.sanitize(copy.deepcopy(sample))
        for lt in (0.0, 0.8, 5.0, 5.2):                              # first frame builds the model; 0.8 is mid-camera; the rest are settled
            cv = Canvas(1920, 1080, ss=2)
            cv.background(THEMES["midnight"], lt, ambience=False)
            t = time.perf_counter()
            EL.draw(cv, props, lt, 8.0, THEMES["midnight"], SceneCtx())
            dt = time.perf_counter() - t
            if lt > 0.0:
                worst = max(worst, dt)
    assert worst < 0.3, worst


def test_a_region_alias_shared_by_several_areas_is_not_a_guess():
    with pytest.raises(R.NotFound):
        R.resolve_offline("Tuscany", "shape")             # Natural Earth has provinces there, not the region
    assert R.resolve_offline("Florida", "shape")["id"].startswith("USA")
