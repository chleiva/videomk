"""Data elements: scale_compare, pictogram, bar_race, pie, area, stacked, scatter (the generic contract is checked in test_elements_framework)."""
import copy

import pytest

from tests.element_utils import changed, render
from engine.scenes import ELEMENTS

NAMES = ["scale_compare", "pictogram", "bar_race", "pie", "area", "stacked", "scatter"]


def san(name, props):
    return ELEMENTS[name].sanitize(copy.deepcopy(props))


def test_all_are_registered_in_the_data_family_with_the_never_invent_rule():
    for n in NAMES:
        assert ELEMENTS[n].family == "Data" and "never invent" in ELEMENTS[n].doc.lower()


def test_empty_and_sparse_props_are_refused():
    bad = {"scale_compare": {"items": [{"label": "a", "value": 1}]}, "pictogram": {"filled": 3}, "bar_race": {"periods": ["a", "b"], "series": []},
           "pie": {"labels": ["a"], "values": [1]}, "area": {"labels": ["a", "b"], "values": [1, 2]},
           "stacked": {"labels": ["a", "b", "c"], "series": [{"name": "x", "values": [1, 2, 3]}]}, "scatter": {"points": [{"x": 1, "y": 2}]}}
    for n, p in bad.items():
        with pytest.raises(ValueError):
            san(n, p)


def test_limits_are_enforced():
    p = san("scale_compare", {"title": "t" * 99, "unit": "u" * 30, "items": [{"label": "L" * 60, "value": 5, "note": "n" * 90}] * 9})
    assert len(p["title"]) <= 50 and len(p["unit"]) <= 10 and len(p["items"]) == 6 and len(p["items"][0]["label"]) <= 24 and len(p["items"][0]["note"]) <= 40
    p = san("pictogram", {"total": 500, "filled": 900, "icon": "star", "label": "x" * 200})
    assert p["total"] == 100 and p["filled"] == 100 and p["icon"] == "person" and len(p["label"]) == 70
    assert san("pictogram", {"total": 3, "filled": 1, "label": "x"})["total"] == 10
    p = san("pie", {"labels": list("abcdefgh"), "values": [1] * 8})
    assert len(p["labels"]) == 6
    p = san("scatter", {"points": [{"x": i, "y": i * i, "label": "z" * 40} for i in range(30)]})
    assert len(p["points"]) == 12 and len(p["points"][0]["label"]) == 18
    p = san("bar_race", {"periods": [str(2000 + i) for i in range(20)], "series": [{"label": str(i), "values": list(range(20))} for i in range(12)]})
    assert len(p["periods"]) == 10 and len(p["series"]) == 8 and all(len(s["values"]) == 10 for s in p["series"])


def test_non_numbers_and_series_with_missing_values_are_dropped_not_invented():
    p = san("bar_race", {"periods": ["a", "b", "c"], "series": [{"label": "ok1", "values": [1, 2, 3]}, {"label": "short", "values": [1, 2]}, {"label": "ok2", "values": [3, 2, 1]},
                                                                {"label": "neg", "values": [1, -2, 3]}, {"label": "ok3", "values": ["4", "5", "6"]}]})
    assert [s["label"] for s in p["series"]] == ["ok1", "ok2", "ok3"]
    p = san("pie", {"labels": ["a", "b", "c"], "values": [5, "x", 3]})
    assert p["labels"] == ["a", "c"]


def test_anchors_follow_the_items():
    assert ELEMENTS["pie"].anchors(san("pie", ELEMENTS["pie"].samples[0])) == ["Gas", "Wind", "Nuclear", "Solar", "Other"]
    assert ELEMENTS["scale_compare"].anchors(san("scale_compare", ELEMENTS["scale_compare"].samples[0]))[0] == "Statue of Liberty"
    unnamed = san("scatter", ELEMENTS["scatter"].samples[1])
    assert ELEMENTS["scatter"].anchors(unnamed) == []          # points without names cannot be tied to words
    named = san("scatter", ELEMENTS["scatter"].samples[0])
    assert ELEMENTS["scatter"].anchors(named) == ["Chad", "India", "Brazil", "Japan", "Norway"]


def test_cues_honour_narration_times():
    p = san("pie", ELEMENTS["pie"].samples[0])
    p["cues"] = [0.5, 1.0, 2.0, 3.0, 4.0]
    assert ELEMENTS["pie"].cues(p, 8.0) == p["cues"]


def test_scale_break_only_when_values_differ_a_lot():
    from engine.scenes.elements.data import _sc_cap
    assert _sc_cap([10, 20, 400]) is None
    assert _sc_cap([1.8, 25, 93, 330, 828]) == 25


def test_pictogram_fraction_text():
    from engine.scenes.elements.data import _pg_text
    assert _pg_text(20, 100) == ("1 in 5", "20%")
    assert _pg_text(37, 100) == ("37%", "")
    assert _pg_text(7, 30) == ("23.3%", "7 of 30")
    assert _pg_text(0, 100)[0] == "0%"


def test_end_state_is_complete_and_differs_from_the_start():
    for n in NAMES:
        for s in ELEMENTS[n].samples:
            p = san(n, s)
            assert changed(render(n, p, 0.0, 8.0), render(n, p, 8.0, 8.0)) > 0.004


def test_bar_race_reranks_and_holds_the_last_period():
    p = san("bar_race", ELEMENTS["bar_race"].samples[1])
    a, b, c = (render("bar_race", p, t, 8.0) for t in (0.5, 4.0, 7.0))
    assert changed(a, c) > 0.01
    assert changed(render("bar_race", p, 7.0, 8.0), render("bar_race", p, 7.9, 8.0)) < 0.002     # the last period holds still


def test_pie_with_one_dominant_slice_and_stacked_with_empty_segments_render():
    render("pie", san("pie", {"labels": ["a", "b"], "values": [999, 1]}), 8.0, 8.0)
    render("stacked", san("stacked", {"labels": ["a", "b", "c"], "series": [{"name": "x", "values": [1, 0, 3]}, {"name": "y", "values": [0, 2, 0]}]}), 8.0, 8.0)
    render("area", san("area", {"labels": ["a", "b", "c"], "values": [-3, 2, -1]}), 8.0, 8.0)
    render("scatter", san("scatter", {"points": [{"x": 1, "y": 1}, {"x": 1, "y": 1}, {"x": 1, "y": 1}]}), 8.0, 8.0)
