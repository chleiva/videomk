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


# ----------------------------------------------------------------------------- responsive layouts (9:16, 1:1, 4:5)
ASPECTS = ("9:16", "1:1", "4:5")
STRESS = {
    "scale_compare": {"title": "A very long title that needs two lines to be shown", "unit": "km2", "items": [
        {"label": "Averyveryverylongname lab", "value": 17098242, "note": "largest country by area in the whole world ok"}, {"label": "Canada", "value": 9984670, "note": "second"},
        {"label": "Vatican City", "value": 0.49}, {"label": "Monaco", "value": 2.02, "note": "tiny"}, {"label": "Italy", "value": 301340}, {"label": "UK", "value": 243610}]},
    "pictogram": {"title": "Who is affected by this very long headline", "total": 100, "filled": 37, "icon": "person", "label": "of adults report this every single week of the year, a lot"},
    "bar_race": {"title": "Streaming giants over the years of the decade", "unit": "B", "periods": [str(2016 + i) for i in range(8)], "series": [
        {"label": "Alpha Records Intl", "values": [5, 6, 8, 9, 10, 11, 12, 13]}, {"label": "Beta Music", "values": [4, 7, 9, 12, 14, 15, 15, 16]}, {"label": "Gamma", "values": [6, 6, 7, 7, 8, 9, 14, 18]},
        {"label": "Delta", "values": [2, 3, 4, 6, 9, 13, 14, 15]}, {"label": "Epsilon", "values": [8, 8, 7, 7, 7, 6, 6, 5]}, {"label": "Zeta", "values": [1, 2, 3, 3, 4, 5, 7, 9]},
        {"label": "Eta Sound", "values": [3, 3, 3, 4, 4, 5, 5, 6]}, {"label": "Theta", "values": [2, 2, 2, 2, 3, 3, 3, 4]}]},
    "pie": {"title": "Budget donut six with a long title", "labels": ["Housing costs", "Food", "Transport", "Fun", "Savings", "Other stuff"], "values": [1200, 600, 400, 300, 250, 100], "unit": "$", "donut": True},
    "area": {"title": "Eight long labels", "labels": ["January", "February", "March", "April", "May", "June", "July", "August"], "values": [1200, 1500, 900, 3400, 2100, 2500, 2600, 3100], "unit": "$"},
    "stacked": {"title": "Sales by region", "labels": ["Quarter 1", "Quarter 2", "Q3 long", "Q4", "Q5", "Q6", "Q7", "Q8"], "unit": "$", "series": [
        {"name": "North region", "values": [10, 12, 14, 15, 17, 18, 20, 22]}, {"name": "South", "values": [8, 9, 9, 11, 12, 12, 13, 15]},
        {"name": "East side", "values": [5, 6, 8, 9, 9, 11, 12, 12]}, {"name": "West", "values": [3, 4, 4, 6, 7, 7, 9, 10]}]},
    "scatter": {"title": "Twelve labelled", "x_label": "X axis", "y_label": "Y axis", "points": [{"label": f"P{i} name", "x": 1 + i * 0.6, "y": 50 + (i * 37) % 40} for i in range(12)]},
}


def test_all_data_elements_are_tagged_native_in_every_aspect():
    for n in NAMES:
        assert set(ELEMENTS[n].formats) == {"16:9", "9:16", "1:1", "4:5"}


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name", NAMES)
def test_stress_props_render_inside_the_content_box_at_every_moment(name, aspect):
    import numpy as np
    from engine.frame import Frame
    from tests.test_formats import _bg
    fr = Frame.parse(aspect, "720p")
    x0, y0, x1, y1 = fr.content_box
    p = san(name, STRESS[name])
    for lt in (1.0, 4.0, 7.5):
        im = render(name, p, lt, 8.0, "midnight", captions=True, draft=False, aspect=aspect, resolution="720p")
        a = np.asarray(im.convert("RGB"), np.int16)
        b = np.asarray(_bg(aspect, "midnight", lt).convert("RGB"), np.int16)
        assert a.shape == b.shape
        sc = a.shape[1] / fr.W      # pixels per design unit of this render
        diff = np.abs(a - b).max(axis=2) > 60
        assert not diff[int((y1 + 6) * sc):].any(), (name, aspect, lt, "drawn below the content box")
        assert not diff[:, : int((x0 - 6) * sc)].any() and not diff[:, int((x1 + 6) * sc):].any(), (name, aspect, lt, "outside the side margins")
        assert not diff[: int((y0 - 4) * sc)].any(), (name, aspect, lt, "drawn above the content box")


@pytest.mark.parametrize("aspect", ASPECTS)
def test_narrow_layouts_keep_the_reveal_order(aspect):
    # the sixth bar of scale_compare and the last pie slice only exist after the first ones (cues unchanged)
    p = san("scale_compare", STRESS["scale_compare"])
    early = render("scale_compare", p, 0.3, 8.0, "midnight", aspect=aspect)
    late = render("scale_compare", p, 7.5, 8.0, "midnight", aspect=aspect)
    assert changed(early, late) > 0.01
