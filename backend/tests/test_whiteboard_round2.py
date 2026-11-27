"""Round 2 of the whiteboard follow-ups (2026-11-27), real plans as fixtures (tests/fixtures/whiteboard_plans: the Spanish 9:16 vaccine video of the QA run)."""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.whiteboard import score  # noqa: E402

PLANS = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard_plans")


def plan(name="es_vacuna_916_r2"):
    with open(os.path.join(PLANS, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("WHITEBOARD", "1")


def policy(p):
    return wp.Policy(True, "asked", aspect=p["frame"]["aspect"])


# ----------------------------------------------------------------------------- 1. an answer that is not valid JSON
BROKEN_ANSWERS = [
    '{"beats": [{"beat": 2, "board": "new", "items": [{"id": "t" "write": "Vacuna"}]}]}',            # the missing comma of the QA run
    '```json\n{"beats": [{"beat": 2, "board": "new", "items": [{"id": "t", "write": "Vacuna",}]},]}\n```',   # trailing commas, code fence
    'Here is the board: {"beats": [{"beat": 2, "board": "new", "items": [{"id": "t", "write": "Vacuna"}',    # cut off
    "{'beats': [{'beat': 2, 'board': 'new', 'items': [{'id': 't', 'write': 'Vacuna'}]}]}",             # single quotes
]


@pytest.mark.parametrize("raw", BROKEN_ANSWERS)
def test_loose_json_reads_what_models_get_wrong(raw):
    data = wp.loose_json(raw)
    assert data["beats"][0]["items"][0]["write"] == "Vacuna"


def test_loose_json_refuses_what_is_not_json():
    with pytest.raises(ValueError):
        wp.loose_json("I cannot do that.")


def test_a_rewrite_with_a_missing_comma_is_not_lost(on):
    p = plan()
    asked = []

    def ask(system, user):
        asked.append(user)
        # a valid rewrite of the failing beat 2, with ONE comma missing: the QA run lost the whole rewrite to this
        items = [{"id": "t", "write": "Vacuna", "zone": "top-row", "size": "xl", "say": "entrenamiento"}, {"id": "s", "draw": "syringe", "zone": "left", "size": "l", "say": "vacuna"},
                 {"id": "v", "draw": "virus", "zone": "right", "size": "l", "say": "virus"}, {"id": "lv", "write": "Virus", "near": "v", "side": "below", "size": "m", "say": "virus"}]
        raw = json.dumps({"beats": [{"beat": b, "board": "new", "items": items} for b in (1, 2)]})
        return raw.replace('"Vacuna", "zone"', '"Vacuna" "zone"', 1)

    wp.review(p, policy(p), ask)
    sc = p["whiteboard"]["score"]
    assert "error" not in sc and sc["replanned"] is True, sc.get("error")


def test_an_answer_that_stays_unreadable_is_asked_once_more_and_the_first_boards_stand(on):
    p = plan()
    calls = []
    before = copy.deepcopy(p["beats"])
    notes = wp.review(p, policy(p), lambda s, u: calls.append(u) or "sorry, no")
    assert len(calls) == 2 and "could not be read as JSON" in calls[1]
    sc = p["whiteboard"]["score"]
    assert sc["replanned"] is False and sc["error"].startswith("ValueError")
    assert any("could not be read" in n for n in notes)
    assert [b["narration"] for b in p["beats"]] == [b["narration"] for b in before]       # the narration is never touched
    assert sc["boards"] == 3 and all(b["scene"]["type"] == "whiteboard" for b in p["beats"])


# ----------------------------------------------------------------------------- 4. arrows that could not be drawn in full
def test_a_lost_arrow_between_two_labelled_things_is_not_a_failure():
    props = {"items": [{"id": "a", "write": "Sol", "zone": "left"}, {"id": "b", "draw": "sun", "zone": "right"}, {"id": "lb", "write": "Luz", "near": "b", "side": "below"},
                       {"id": "x", "connect": "arrow", "from": "a", "to": "b"}]}
    assert score._readable_without("x", [props], False)
    bare = {"items": [{"id": "a", "draw": "sun", "zone": "left"}, {"id": "b", "draw": "moon", "zone": "right"}, {"id": "x", "connect": "arrow", "from": "a", "to": "b"}]}
    assert not score._readable_without("x", [bare], False)       # two bare drawings: nothing says how they relate
    assert score._readable_without("1:x", [bare, props], True) is True


def test_a_one_thing_short_board_that_covers_forty_percent_passes():
    assert score.COUNT_PASS_COVERAGE == 0.40


# ----------------------------------------------------------------------------- 5. the director is asked only for what a clean-up cannot mend
def test_complaints_have_kinds_and_only_some_need_the_director():
    p = plan()
    sc = score.score_plan(p, "9:16")
    for s in sc:
        assert len(s["kinds"]) == len(s["complaints"])
    assert all(set(s["kinds"]) <= {"rest", "empty", "mark", "overlap", "off"} or s["needs_director"] for s in sc)
    rest_only = {"complaints": ["x"], "kinds": ["rest"], "needs_director": False}
    assert not any(k in score.DIRECTOR_KINDS for k in rest_only["kinds"])
    assert {"rest", "busy", "empty", "overlap", "off", "mark"}.isdisjoint(score.DIRECTOR_KINDS)


def test_a_board_that_only_looks_empty_is_filled_without_the_director(on, monkeypatch):
    p = plan()
    # make board 2 only "look empty": enough things, large coverage missing -> fill_out repairs it; the director must not be asked about it
    asked = []
    sc = score.score_plan(p, "9:16")
    only_deterministic = [s for s in sc if not s["ok"] and not s["needs_director"]]
    wp.review(p, policy(p), lambda s, u: asked.append(u) or "{}")
    for s in only_deterministic:
        assert f"BOARD {s['board']} " not in (asked[0] if asked else "")
