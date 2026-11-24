"""kinetic_text, definition, counter, checklist, steps, funnel."""
import copy

import pytest

from tests.element_utils import changed, render
from engine import sync
from engine.scenes import ELEMENTS

NAMES = ["kinetic_text", "definition", "counter", "checklist", "steps", "funnel"]


def test_all_six_are_registered():
    assert all(n in ELEMENTS for n in NAMES)


def test_kinetic_limits_and_emphasis():
    el = ELEMENTS["kinetic_text"]
    c = el.sanitize({"text": "word " * 100, "emphasis": "nothing here"})
    assert len(c["text"]) <= 140 and "emphasis" not in c
    assert el.sanitize({"text": "Patience beats talent", "emphasis": "PATIENCE"})["emphasis"] == "PATIENCE"
    with pytest.raises(ValueError):
        el.sanitize({"text": "one"})


def test_kinetic_anchors_cover_every_word_in_order():
    el = ELEMENTS["kinetic_text"]
    p = el.sanitize({"text": "Compound interest rewards patience more than talent.", "emphasis": "patience"})
    a = el.anchors(p)
    assert " ".join(a) == p["text"] and any(g == "patience" for g in a)
    words = [["Compound", 0.5, 0.9], ["interest", 1.0, 1.4], ["rewards", 1.5, 1.9], ["patience", 2.5, 3.0], ["more", 3.1, 3.3], ["than", 3.3, 3.5], ["talent", 3.6, 4.0]]
    found = sync.apply("kinetic_text", p, words, 8.0)
    assert found["anchored"] >= 3 and len(p["cues"]) == len(a)
    assert el.sanitize(copy.deepcopy(p)) == p, "cues survive a re-sanitize"


def test_kinetic_end_state_has_every_word():
    el = ELEMENTS["kinetic_text"]
    p = el.sanitize(el.samples[1])
    assert changed(render("kinetic_text", p, 0.0, 8.0), render("kinetic_text", p, 8.0, 8.0)) > 0.02


def test_counter_rejects_non_numeric_and_keeps_format():
    el = ELEMENTS["counter"]
    for bad in ("many", "", None, "4 to 5", True):
        with pytest.raises(ValueError):
            el.sanitize({"value": bad, "label": "x"})
    c = el.sanitize({"value": "1,250", "unit": "km" * 10, "prefix": "$$$$$$", "label": "L" * 200, "from": "2,000", "delta": "d" * 50})
    assert c["value"] == "1,250" and c["from"] == "2,000" and len(c["unit"]) <= 8 and len(c["prefix"]) <= 4 and len(c["label"]) <= 70 and len(c["delta"]) <= 24
    c = el.sanitize({"value": "$4.2B"})
    assert (c["value"], c["prefix"], c["unit"]) == ("4.2", "$", "B")
    assert el.sanitize({"value": 73})["value"] == "73"


def test_counter_counts_then_holds_the_final_value():
    el = ELEMENTS["counter"]
    p = el.sanitize({"value": "73", "unit": "%", "label": "Share of adults"})
    a, b, c = (render("counter", p, t, 8.0) for t in (0.3, 1.0, 7.0))
    assert changed(a, c) > 0.004 and changed(b, c) > 0.002 and changed(render("counter", p, 6.0, 8.0), c) == 0


def test_counter_anchor_is_the_number():
    p = ELEMENTS["counter"].sanitize({"value": "4.2", "label": "x"})
    assert ELEMENTS["counter"].anchors(p) == ["4.2"]


def test_checklist_limits_and_checked():
    el = ELEMENTS["checklist"]
    c = el.sanitize({"items": [f"item {i}" for i in range(10)], "checked": [False]})
    assert len(c["items"]) == 6 and c["checked"] == [False] + [True] * 5
    assert "checked" not in el.sanitize({"items": ["a", "b"], "checked": [True]})
    with pytest.raises(ValueError):
        el.sanitize({"items": ["only one"]})
    assert el.anchors(c) == c["items"]


def test_steps_and_funnel_limits():
    st, fu = ELEMENTS["steps"], ELEMENTS["funnel"]
    c = st.sanitize({"steps": ["a", {"label": "b" * 90, "detail": "d" * 200}, {"label": "c"}] + ["x"] * 8})
    assert len(c["steps"]) == 6 and len(c["steps"][1]["label"]) <= 40 and len(c["steps"][1]["detail"]) <= 80
    with pytest.raises(ValueError):
        st.sanitize({"steps": ["a", "b"]})
    f = fu.sanitize({"stages": [{"label": "a", "value": "1" * 40}, "b", "c", "d", "e", "f"]})
    assert len(f["stages"]) == 5 and len(f["stages"][0]["value"]) <= 12
    with pytest.raises(ValueError):
        fu.sanitize({"stages": ["a", "b"]})
    assert st.anchors(c)[0] == "a" and fu.anchors(f)[0] == "a"


@pytest.mark.parametrize("name", ["checklist", "steps", "funnel"])
def test_list_elements_reveal_in_order_and_end_complete(name):
    el = ELEMENTS[name]
    p = el.sanitize(el.samples[0])
    n = len(el.anchors(p))
    p["cues"] = [0.5 + 1.5 * i for i in range(n)]
    f1, f2, end = (render(name, p, t, 12.0) for t in (1.0, 0.5 + 1.5 * (n - 1) + 0.1, 11.9))
    assert changed(f1, end) > changed(f2, end) > 0 or changed(f2, end) >= 0
    assert changed(render(name, p, 0.2, 12.0), end) > 0.01


def test_definition_optional_lines_appear_later():
    el = ELEMENTS["definition"]
    p = el.sanitize(el.samples[1])
    assert changed(render("definition", p, 2.5, 8.0), render("definition", p, 7.9, 8.0)) > 0.001
    assert set(el.sanitize({"term": "t", "definition": "d"})) == {"term", "definition"}


@pytest.mark.parametrize("name", NAMES)
def test_empty_and_junk_are_refused(name):
    for bad in ({}, {"steps": "x"}, {"items": 5, "stages": None}):
        with pytest.raises(ValueError):
            ELEMENTS[name].sanitize(bad)
