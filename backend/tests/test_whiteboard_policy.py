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
    assert len(b) < 16000
    # the quality rules of 2026-11-27: full boards shared by beats, every key noun on the board, labels, pacing, large titles and numbers
    for rule in ('"board": "same"', "8 to 12 drawings and written phrases", "EVERY KEY NOUN", "label", "never more than 5 words", "4th to 6th word", "NEIGHBOURS", "size l or xl"):
        assert rule in b, rule
    assert "TALL" not in b and "left to right" in b
    tall = wp.decide("x as a whiteboard video", options={"aspect": "9:16"}).prompt_block("es")
    assert "THIS VIDEO IS TALL (9:16)" in tall and "top to bottom" in tall and "1 to 3 words per line" in tall


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


# ----------------------------------------------------------------------------- boards shared by beats, pacing with real times (docs/WHITEBOARD.md "Quality")
def _beat(narration, items, board=None):
    return {"narration": narration, "scene": {"type": "whiteboard", "props": ELEMENTS["whiteboard"].sanitize({"items": items, **({"board": board} if board else {})})}}


def _wb(n, zone, word):
    return [{"id": f"d{k}", "write": f"{word}{k}", "zone": z, "say": word} for k, z in zip(range(n), zone)]


def test_compose_keeps_beats_on_a_board_until_it_is_full():
    said = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"        # 20 words
    beats = [_beat(said, _wb(4, ("top", "left", "right", "centre"), "a")), _beat(said, _wb(4, ("bottom-left", "bottom", "bottom-right", "top-left"), "b")),      # the director forgot to say "same": the board is not full yet
             _beat(said, _wb(4, ("top", "left", "right", "centre"), "c"), "new"), _beat(said, _wb(2, ("bottom-left", "bottom"), "d"), "same"),      # 8 things and 40 words: full, a new board is right
             _beat(said + " " + said + " " + said, _wb(3, ("top", "left", "right"), "e"), "same"),                           # no room for 60 more words: a new board whatever it says
             _beat("the end", [{"id": "k", "write": "Key", "zone": "bottom", "say": "end"}])]                                           # the closing beat never opens a nearly empty board
    st = wp.compose(beats)
    flags = [b["scene"]["props"].get("board") for b in beats]
    assert flags == [None, "same", None, "same", None, "same"] and st["boards"] == 3 and st["shared"] == 3 and st["merged"] == 2
    assert wp.compose(beats)["boards"] == 3 and [b["scene"]["props"].get("board") for b in beats] == flags        # settled
    from engine.whiteboard import score

    assert score.boards_of(beats) == [[0, 1], [2, 3], [4, 5]]


def test_compose_gives_every_thing_its_own_zone_on_the_board():
    said = "one two three four five six seven eight"
    beats = [_beat(said, [{"id": "t", "write": "Title", "zone": "top-row", "say": "one"}, {"id": "a", "draw": "sun", "zone": "left", "say": "two"}]),
             _beat(said, [{"id": "x", "write": "Again", "zone": "top-row", "say": "one"}, {"id": "b", "draw": "piggy_bank", "zone": "left", "say": "two"},
                          {"id": "l", "write": "label", "near": "b", "say": "three"}], "same")]
    st = wp.compose(beats)
    items = beats[1]["scene"]["props"]["items"]
    assert st["rezoned"] == 2 and items[0]["zone"] in ("middle-row", "bottom-row") and items[1]["zone"] not in ("left", "top-left", "top", "top-right")
    assert "zone" not in items[2]                                                 # a label stays beside its drawing
    assert wp.free_zones([b["scene"]["props"] for b in beats])                    # ... and the zones still free can be named


def test_fill_rests_uses_the_real_word_times():
    before = [{"id": "0:t", "write": "Title", "zone": "top"}, {"id": "0:s", "draw": "sun", "zone": "left"}]
    props = {"before": list(before), "items": [{"id": "1:n", "write": "350", "zone": "right", "say": "350"}, {"id": "1:m", "mark": "underline", "on": "1:n", "say": "cases"}]}
    assert wp.fill_rests(props, [3.2, 7.5], end=10.0) == 2                     # the wait before the number, the gap before the mark; in the breath after the last word
    ids = [it["id"] for it in props["items"]]                                  # everything on the board has its ONE mark already: the pen rests
    assert ids[0].startswith("+r") and ids[1] == "1:n" and ids[2].startswith("+r") and ids[3] == "1:m" and len(ids) == 4
    lead, mid = props["items"][0], props["items"][2]
    assert lead["on"] == "0:s" and 0.4 <= lead["at"] < 2.0 and "say" not in lead    # something an earlier beat drew, at a fixed time inside the wait
    assert 3.5 < mid["at"] < 7.0 and mid["on"] == "0:t"
    on = [it["on"] for it in props["items"] if it.get("mark")]
    assert len(on) == len(set(on))                                             # never two marks on one thing
    assert ELEMENTS["whiteboard"].anchors(props) == ["350", "cases"]              # the scene's cue list is untouched
    assert wp.fill_rests(props, [3.2, 7.5], end=10.0) == 0                      # once
    calm = {"items": [{"id": "a", "draw": "sun", "zone": "left", "say": "sun"}, {"id": "b", "draw": "piggy_bank", "zone": "right", "say": "pig"}]}
    assert wp.fill_rests(calm, [1.9, 4.5], end=5.2) == 0                        # a drawing is drawn slowly through the wait: no rest, no mark; a NEW board does not wait at its start


def test_link_fills_rests_and_knows_the_breath_after_the_last_word():
    a = ELEMENTS["whiteboard"].sanitize({"items": [{"id": "t", "write": "Title", "zone": "top", "say": "title"}, {"id": "s", "draw": "sun", "zone": "left", "say": "sun"}]})
    b = ELEMENTS["whiteboard"].sanitize({"board": "same", "items": [{"id": "n", "write": "350", "zone": "right", "say": "number"}]})
    scenes = [{"id": "s0", "type": "whiteboard", "duration": 6.0, "transition": "fade", "props": dict(a, cues=[1.0, 3.0])},
              {"id": "s1", "type": "whiteboard", "duration": 9.0, "transition": "fade", "props": dict(b, cues=[4.0])}]
    wp.link(scenes)
    extra = [it for it in scenes[1]["props"]["items"] if "+r" in it["id"]]
    assert len(extra) >= 2 and all(isinstance(it["at"], float) and it["on"].startswith(("0:", "1:")) and it["id"].startswith("+r1.") for it in extra)
    assert [it["id"] for it in scenes[0]["props"]["after"]] == [it["id"] for it in scenes[1]["props"]["items"]]      # the first beat reserves the place of everything the second will draw
    again = [dict(s, props=dict(s["props"])) for s in scenes]
    wp.link(again)
    assert [s["props"] for s in again] == [s["props"] for s in scenes]            # an edit rebuilds the timeline: linking twice changes nothing


def test_keep_busy_fills_five_word_gaps_and_marks_a_thing_once():
    p = _board([{"id": "t", "write": "Sleep", "zone": "top", "say": "sleep"}])
    narration = "Sleep is when the brain files away what it learned during the whole long day and clears out waste so you think clearly."
    n = wp.keep_busy(p, narration)
    marks = [it for it in p["items"] if it.get("mark")]
    assert n == len(marks) == 1 and marks[0]["on"] == "t"     # one thing only: ONE mark (an underline and a box piled up on one word in the first Portuguese video)
    two = _board([{"id": "t", "write": "Sleep", "zone": "top", "say": "sleep"}, {"id": "b", "draw": "sun", "zone": "left", "say": "brain"}])
    wp.keep_busy(two, narration)
    on = [it["on"] for it in two["items"] if it.get("mark")]
    assert len(on) == len(set(on)) == 2                        # two things: one mark each
    assert wp.FILL_EVERY_WORDS == 5


def test_a_continued_board_keeps_its_first_word(on):
    from engine import sync

    words = [("Time", 0.4, 0.7), ("and", 0.8, 1.0), ("how", 1.0, 1.2), ("often", 1.3, 1.6), ("the", 1.8, 2.0), ("bank", 2.1, 2.4), ("pays", 2.6, 2.9), ("matter", 3.0, 3.4)]
    for board in ("same", None):
        p = ELEMENTS["whiteboard"].sanitize({"items": [{"id": "a", "write": "matter", "zone": "top", "say": "matter"}], **({"board": board} if board else {})})
        sync.apply("whiteboard", p, words, 6.0)
        if board:
            assert p["cues"][0] > sync.WHITEBOARD_FIRST_S                         # it goes on drawing on a board that is in the picture: every thing on its word
        else:
            assert p["cues"][0] == sync.WHITEBOARD_FIRST_S                        # an empty board does not wait for a late word


def test_auto_never_takes_a_video_whose_presenter_was_asked_for(on):
    kw = dict(skill_ids=["kids-family"], ask=YES)
    assert wp.decide("Why do leaves change colour? Explained by a fox", **kw).allowed                       # (the policy itself does not read presenter words)
    p = wp.decide("Why do leaves change colour? Explained by a fox", presenter_asked=True, **kw)
    assert not p.allowed and p.reason == "presenter_asked"
    assert wp.decide("Leaves, as a whiteboard video, explained by a fox", presenter_asked=True, **kw).reason == "asked"      # asked for the whiteboard in words: that still wins
