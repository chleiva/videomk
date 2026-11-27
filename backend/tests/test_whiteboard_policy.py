"""When a video is a whiteboard video (engine/whiteboard_policy.py): the flag, the request words, the automatic rule and its refusals, the plan gate, the text-to-board step."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402

YES = lambda s, u: '{"fit": true, "why": "explains a process"}'     # noqa: E731
NO = lambda s, u: '{"fit": false, "why": "needs real pictures"}'    # noqa: E731


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("WHITEBOARD", "1")


@pytest.mark.parametrize("text", ["Explain compound interest as a whiteboard video", "how planes fly, draw it on a whiteboard", "whiteboard style please", "a hand-drawn explainer about sleep",
                                  "explica el ciclo del agua estilo pizarra", "en pizarra blanca: cómo funciona una vacuna", "la fotosíntesis, dibujado a mano", "vídeo de pizarra sobre el ahorro"])
def test_the_person_can_ask_in_plain_words(text):
    assert wp.wish(None, text) == "whiteboard"


@pytest.mark.parametrize("text", ["the history of Rome", "how vaccines work", "a board game review", "el mercado de pizarras en España no"])
def test_ordinary_requests_do_not_ask(text):
    assert wp.wish(None, text) in ("auto",)


def test_other_wishes_win():
    assert wp.wish("cartoon", "as a whiteboard video") == "no"                 # the option is explicit
    assert wp.wish("real", "whiteboard style") == "no"
    assert wp.wish(None, "how vaccines work, with real footage, whiteboard") == "no"
    assert wp.wish(None, "no whiteboard please, explain taxes") == "no"
    assert wp.wish("whiteboard", "anything") == "whiteboard"


def test_flag_off_means_never(monkeypatch):
    monkeypatch.delenv("WHITEBOARD", raising=False)
    p = wp.decide("as a whiteboard video", options={"style": "whiteboard"})
    assert not p.allowed and p.reason == "flag_off" and p.prompt_block() == ""


def test_asked_is_allowed_without_a_model_call(on):
    p = wp.decide("how a battery works", options={"style": "whiteboard"}, skill_ids=["news-explainer"], research_mode="web")
    assert p.allowed and p.reason == "asked"


def test_never_with_the_persons_photos_or_a_deck(on):
    assert wp.decide("as a whiteboard video", photos=[{"id": 1}]).reason == "user_media"
    assert wp.decide("as a whiteboard video", options={"deck": True}).reason == "deck"


def test_auto_needs_the_right_kind_of_video_and_the_classifier(on):
    assert wp.decide("how compound interest works", skill_ids=["explainer-education"], ask=YES).allowed
    assert wp.decide("how compound interest works", skill_ids=["explainer-education"], ask=NO).reason == "not_suited"
    assert wp.decide("how compound interest works", skill_ids=["explainer-education"], ask=None).reason == "no_classifier"
    assert wp.decide("how compound interest works", skill_ids=["explainer-education"], ask=lambda s, u: "rubbish").reason == "not_suited"
    for skill in ("news-explainer", "biography-profile", "history-story", "travel-places", "product-marketing", "photo-memories"):
        assert wp.decide("x", skill_ids=[skill], ask=YES).reason == "kind_of_video"
    assert wp.decide("x", skill_ids=["explainer-education", "news-explainer"], ask=YES).reason == "kind_of_video"
    assert wp.decide("today's election results explained", skill_ids=["explainer-education"], research_mode="web", ask=YES).reason == "current_events"
    assert wp.decide("x", skill_ids=[], ask=YES).reason == "kind_of_video"


def test_prompt_block_teaches_the_scene_and_lists_the_library(on):
    b = wp.Policy(True, "asked").prompt_block()
    assert "whiteboard" in b and "EVERY beat" in b and "never coordinates" in b
    for oid in ("sun", "piggy_bank", "person_standing", "syringe"):
        assert oid in b
    assert len(b) < 12000


def test_the_plan_gate():
    assert not wp.allowed()
    with wp.scope(wp.Policy(True, "asked")):
        assert wp.allowed()
        with wp.scope(wp.Policy(False, "flag_off")):
            assert not wp.allowed()
        assert wp.allowed()
    assert not wp.allowed()


def test_plan_refuses_a_stray_board_and_keeps_it_when_the_look_is_on():
    from engine import plan as plan_mod

    beat = {"narration": "The sun warms the sea and the water rises as vapour.", "scene": {"type": "whiteboard", "props": ELEMENTS["whiteboard"].samples[0]}}
    raw = {"legit": True, "title": "t", "theme": "midnight", "beats": [dict(beat), dict(beat), dict(beat)]}
    plan, warnings = plan_mod.validate_plan(dict(raw, beats=[dict(b) for b in raw["beats"]]))
    assert all(b["scene"]["type"] != "whiteboard" for b in plan["beats"])
    with wp.scope(wp.Policy(True, "asked")):
        plan, warnings = plan_mod.validate_plan(dict(raw, beats=[dict(b) for b in raw["beats"]]))
    assert [b["scene"]["type"] for b in plan["beats"]] == ["whiteboard"] * 3


def test_enforce_writes_text_beats_on_the_board(on):
    plan = {"beats": [
        {"narration": "Three habits.", "scene": {"type": "title", "props": {"title": "Three habits", "subtitle": "that make money grow"}}},
        {"narration": "Start early, add a little, wait.", "scene": {"type": "bullets", "props": {"heading": "Habits", "items": ["Start early", "Add a little", "Wait"]}}},
        {"narration": "Seven percent.", "scene": {"type": "stat", "props": {"value": "7", "unit": "%", "label": "a year"}}},
        {"narration": "A photo.", "scene": {"type": "image", "props": {"image_query": "a bank"}}},
        {"narration": "A board.", "scene": {"type": "whiteboard", "props": ELEMENTS["whiteboard"].sanitize(ELEMENTS["whiteboard"].samples[1])}},
    ]}
    warnings = wp.enforce(plan, wp.Policy(True, "asked"))
    assert [b["scene"]["type"] for b in plan["beats"]] == ["whiteboard", "whiteboard", "whiteboard", "image", "whiteboard"]
    assert plan["whiteboard"]["boards"] == 4 and plan["whiteboard"]["other_scenes"] == 1
    assert "1. Start early" in plan["beats"][1]["scene"]["props"]["items"][1]["write"]
    assert any("kept another scene type" in w for w in warnings)
    off = {"beats": [{"narration": "x", "scene": {"type": "title", "props": {"title": "T"}}}]}
    assert wp.enforce(off, wp.Policy(False, "flag_off")) == [] and off["beats"][0]["scene"]["type"] == "title" and off["whiteboard"]["decision"] == "no"


# ----------------------------------------------------------------------------- the board follows the narration as it finally is
def _board(items):
    return ELEMENTS["whiteboard"].sanitize({"items": items})


def _mentions(props, narration):
    """What the engine's alignment will find (engine/sync.py), with every word one second apart."""
    from engine import sync

    words = [[w, float(i), float(i) + 0.9] for i, w in enumerate(narration.split())]
    return sync.find_mentions(ELEMENTS["whiteboard"].anchors(props), words)


def test_retie_draws_in_the_order_the_narrator_names_things():
    p = _board([{"id": "t", "write": "Compound interest", "zone": "top", "say": "compound"}, {"id": "p", "draw": "piggy_bank", "zone": "left", "say": "savings"},
                {"id": "s", "draw": "sun", "zone": "right", "say": "money"}, {"id": "a", "connect": "arrow", "from": "p", "to": "s", "say": "snowball"},
                {"id": "u", "mark": "underline", "on": "t", "say": "time"}])
    narration = "Your savings can earn money on money they already earned. That snowball is called compound interest, and time makes it grow."
    st = wp.retie(p, narration)
    assert [it["id"] for it in p["items"]] == ["p", "s", "a", "t", "u"] and st["moved"] > 0
    found = _mentions(p, narration)
    assert None not in found and found == sorted(found)


def test_retie_moves_a_lost_tie_to_a_word_that_is_said():
    p = _board([{"id": "h", "write": "Simple interest", "zone": "top", "say": "simple"}, {"id": "b", "draw": "piggy_bank", "zone": "left", "say": "deposit"},
                {"id": "n", "write": "$100", "zone": "centre", "say": "hundred"}, {"id": "c", "mark": "circle", "on": "n", "say": "year"}])
    narration = "Put in one hundred dollars, and every year you get the same small amount."        # the sentence that said "simple" and "deposit" was cut
    st = wp.retie(p, narration)
    assert st["retied"] + st["untied"] == 2
    found = _mentions(p, narration)
    assert None not in found and found == sorted(found) and len(set(found)) == len(found)
    assert wp.retie(p, narration) == {"moved": 0, "retied": 0, "untied": 0}                      # settled: a second pass changes nothing


def test_retie_never_puts_a_mark_or_an_arrow_before_its_target():
    p = _board([{"id": "a", "write": "Alpha", "zone": "left", "say": "last"}, {"id": "m", "mark": "circle", "on": "a", "say": "first"}])
    wp.retie(p, "First we wait and at last we see alpha.")
    assert [it["id"] for it in p["items"]] == ["a", "m"]


def test_keep_busy_adds_emphasis_where_the_pen_would_rest():
    p = _board([{"id": "t", "write": "Sleep", "zone": "top", "say": "sleep"}, {"id": "s", "draw": "sun", "zone": "left", "say": "morning"}])
    narration = "Sleep is when the brain files away what it learned during the whole long day and clears out waste so that by morning you think clearly again and feel rested and ready."
    n = wp.keep_busy(p, narration)
    marks = [it for it in p["items"] if it.get("mark")]
    assert n == len(marks) >= 1 and all(m["on"] in ("t", "s") and m.get("say") for m in marks)
    assert ELEMENTS["whiteboard"].sanitize(p)["items"] == p["items"]                             # what was added is valid
    found = _mentions(p, narration)
    assert None not in found and found == sorted(found)
    assert wp.keep_busy(_board([{"id": "t", "write": "Hi", "zone": "top", "say": "hi"}]), "Hi there.") == 0


def test_settle_runs_both_and_records_them(on):
    plan = {"beats": [{"narration": "Put in one hundred dollars, and every year you get the same small amount.",
                       "scene": {"type": "whiteboard", "props": _board([{"id": "h", "write": "Simple", "zone": "top", "say": "simple"}, {"id": "n", "write": "$100", "zone": "centre", "say": "hundred"}])}},
                      {"narration": "A photo.", "scene": {"type": "image", "props": {"image_query": "x"}}}]}
    w = wp.settle(plan, wp.Policy(True, "asked"))
    assert plan["whiteboard"]["retied"] + plan["whiteboard"]["untied"] == 1 and w
    assert wp.settle({"beats": []}, wp.Policy(False, "flag_off")) == []


def test_a_whiteboard_video_is_on_paper(on):
    plan = {"theme": "midnight", "beats": [{"narration": "x", "scene": {"type": "whiteboard", "props": _board([{"write": "Hi", "zone": "top"}])}}]}
    wp.enforce(plan, wp.Policy(True, "asked"))
    assert plan["theme"] == "paper"
