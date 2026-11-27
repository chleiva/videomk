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
