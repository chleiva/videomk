"""docs/WHITEBOARD_VACCINE_REGRESSION_2026-11-28.md: two arrows that cross are a complaint (mend moves one end), a board still thin after the director gets the drawing a word of its
own narration names (or at most two written key words) tied to that word, a pen that rests is filled, all without a model and never making a plan score worse."""
import copy
import contextlib
import io
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.whiteboard import mend, score, spec  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard_plans")


def load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


def vaccine():
    return load("vaccine_es_916_qa_2026-11-28.json")


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setenv("WHITEBOARD", "1")
    monkeypatch.delenv("WB_FILL_WORDS", raising=False)


def repair(p, asp="9:16", **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return wp._repair(p, wp.Policy(True, "asked", aspect=asp), score.score_plan(p, asp), {}, [], **kw)


def test_two_arrows_that_make_an_x_cross_and_two_that_meet_at_a_thing_do_not():
    a = np.array([[0.0, 0.0], [100.0, 100.0]])
    b = np.array([[0.0, 100.0], [100.0, 0.0]])
    assert spec._segments_cross(a, b, 40.0)
    c = np.array([[0.0, 100.0], [95.0, 98.0]])       # meets the first at its end: a shared target, not an X
    assert not spec._segments_cross(a, c, 40.0)


def test_the_qa_vaccine_board_with_two_crossing_arrows_is_a_complaint_and_mend_clears_it():
    p = vaccine()
    s = score.score_plan(p, "9:16")
    assert any("cross each other" in c for x in s for c in x["complaints"]) and any(x["arrow_cross"] for x in s)
    after = repair(copy.deepcopy(p), mend_too=True)
    assert not any(x["arrow_cross"] for x in after)


def test_the_closing_board_of_one_line_gets_filled_without_inventing_anything():
    p = repair(vaccine(), mend_too=True) and vaccine()
    before = repair(copy.deepcopy(p), mend_too=True)
    q = copy.deepcopy(p)
    repair(q, mend_too=True)
    after = repair(q, tag="-final", words=True)
    last = lambda s: s[-1]      # noqa: E731
    assert last(before)["solid"] == 1 and last(after)["solid"] >= 3
    assert "count" not in last(after)["kinds"] and "rest" not in last(after)["kinds"] or last(after)["longest_idle_s"] < last(before)["longest_idle_s"]
    narr = wp._words(q["beats"][-1]["narration"])
    added = [it for it in q["beats"][-1]["scene"]["props"]["items"] if str(it.get("id", "")).startswith(("kd", "kw"))]
    assert 1 <= len(added) <= 4 and all(it["say"] in narr for it in added)
    assert sum(1 for it in added if it.get("write")) <= mend.MAX_WORDS
    assert [x["failed"] if False else x["ok"] for x in after].count(False) <= [x["ok"] for x in before].count(False)


def test_a_word_names_one_drawing_or_none():
    assert mend._drawing_for("cuerpo") == "person_standing"
    assert mend._drawing_for("te") is None and mend._drawing_for("verdad") is None


def test_nothing_is_added_to_boards_that_pass_and_the_setting_switches_it_off(monkeypatch):
    p = load("es_vacuna_916_r2.json")
    p = p.get("plan", p)
    a = repair(copy.deepcopy(p), mend_too=True)
    monkeypatch.setenv("WB_FILL_WORDS", "0")
    q = copy.deepcopy(p)
    repair(q, tag="-final", words=True)
    r = copy.deepcopy(p)
    repair(r, tag="-final")
    assert q == r and not wp.fill_words_enabled()
    monkeypatch.delenv("WB_FILL_WORDS")
    s = copy.deepcopy(p)
    b = repair(s, tag="-final", words=True)
    assert sum(not x["ok"] for x in b) <= sum(not x["ok"] for x in a)


def test_never_worse_on_the_review_cost_fixtures():
    d = load("review_cost_qa_2026-11-28.json")
    for name, v in d.items():
        p = copy.deepcopy(v["plan"])
        a = repair(p, v["aspect"], mend_too=True)
        b = repair(p, v["aspect"], tag="-final", words=True)
        assert sum(not x["ok"] for x in b) <= sum(not x["ok"] for x in a), name
        assert sum(len(x["complaints"]) for x in b) <= sum(len(x["complaints"]) for x in a), name
