"""Emphasis marks and arrows never touch anything (docs/WHITEBOARD.md, "Marks and arrows").

The fixtures in tests/fixtures/whiteboard_boards are the whiteboard scenes of real QA videos exactly as the renderer got them (2026-11-27): in five of
them (nl, fi, pt, fr, pl) circles swallowed the first letter of the next label, cut the phrase they surrounded, a word got an underline AND a box, and
arrows ran through a drawing, while the score said `overlaps 0`. `tidy=False` lays a board out as those videos were drawn (what the plan asks, whatever is
there); the default is what ships.
"""
import copy
import glob
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.frame import Frame  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.scenes.base import SceneCtx  # noqa: E402
from engine.scenes.elements import whiteboard as wbe  # noqa: E402
from engine.whiteboard import hand as wr  # noqa: E402
from engine.whiteboard import score, spec  # noqa: E402

BOARDS = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard_boards")
ALL = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(BOARDS, "*.json")))
LANGFIX = [n for n in ALL if n.startswith("langfix_")]
LOAD = score._stub_loader()


def _fx(name):
    with open(os.path.join(BOARDS, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _reports(fx, tidy=True, aspect=None):
    """One layout report per scene of a fixture, laid out as the renderer does."""
    ctx = SceneCtx(frame=Frame.parse(aspect or fx["aspect"], "1080p"), captions=fx["captions"])
    return [wbe.build(sc["props"], sc["duration"], ctx, 480, 270, load=LOAD, layout_only=True, tidy=tidy)[3] for sc in fx["scenes"]]


def _board(items, tidy=True, aspect="16:9"):
    props = ELEMENTS["whiteboard"].sanitize({"items": items})
    ctx = SceneCtx(frame=Frame.parse(aspect, "1080p"), captions=True)
    return wbe.build(props, 10.0, ctx, 480, 270, load=LOAD, layout_only=True, tidy=tidy)[3]


# ----------------------------------------------------------------------------- the real boards
def test_the_fixtures_are_there():
    assert len(LANGFIX) == 5 and len(ALL) >= 10


@pytest.mark.parametrize("name,pairs", [
    ("langfix_nl", [("1:m2", "1:l1"), ("1:em0_oog", "1:w4")]),          # the circle round the lightning swallowed the b of "bliksem", the one round the eye the m of "meteen"
    ("langfix_fi", [("1:m4", "1:k"), ("1:m5", "1:m4")]),                # the circle cut "Jokainen hiutale ainutlaatuinen"; the double underline ran into the circle
    ("langfix_pl", [("m2", "ray")]),                                    # the circle cut "jeden promień"
    ("langfix_pt", [("1:b2", "1:sun2"), ("1:b2", "1:em0_l2"), ("a3", "cal3")]),      # "Sol": underline AND box, the box cut by the sun; the arrow through the calendar
    ("langfix_fr", [("1:a2", "1:goutte"), ("+r0.0", "0:em1_montagne")]),             # the arrow through the water drop; the oval round "roches" into the one round the mountain
])
def test_the_measure_sees_what_the_videos_showed(name, pairs):
    """As those videos were drawn, the collision measure reports exactly the faults that were seen (the old score said overlaps 0 and nothing else)."""
    hits = {tuple(x) for rep in _reports(_fx(name), tidy=False) for x in rep["collisions"]}
    for pair in pairs:
        assert pair in hits, (pair, sorted(hits))


@pytest.mark.parametrize("name", ALL)
def test_no_board_ships_with_a_mark_or_arrow_touching_anything(name):
    fx = _fx(name)
    before = sum(len(rep["collisions"]) for rep in _reports(fx, tidy=False))
    assert before >= 3, before                                           # every one of these real boards had some
    for rep in _reports(fx):
        assert rep["collisions"] == [] and rep["crossed"] == [], (name, rep["collisions"])
        assert rep["overlaps"] == []
        kinds = rep["kinds"]
        gone = {x[0] for x in rep["marks"]["dropped"]} | {x[0] for x in rep["arrows"]["dropped"]}
        assert not gone & set(kinds)                                     # what was taken off is not on the board


@pytest.mark.parametrize("name", LANGFIX)
@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5"])
def test_nor_in_the_other_aspects(name, aspect):
    for rep in _reports(_fx(name), aspect=aspect):
        assert rep["collisions"] == [] and rep["crossed"] == []


@pytest.mark.parametrize("name", ALL)
def test_at_most_one_mark_per_thing_and_the_scenes_of_a_board_agree(name):
    fx = _fx(name)
    by_board = {}
    for sc, rep in zip(fx["scenes"], _reports(fx)):
        p = sc["props"]
        its = {it["id"]: it for it in (p.get("before") or []) + p["items"] + (p.get("after") or [])}
        moved = {m: to for m, _, to in rep["marks"]["moved"]}
        on = [moved.get(i, its[i].get("on")) for i, k in rep["kinds"].items() if k == "mark"]
        assert len(on) == len(set(on)), (name, on)
        key = tuple(sorted(its))                                          # the scenes of one board hold the same things: they must be drawn in the same places
        boxes = {i: b for i, b in rep["boxes"].items()}
        assert by_board.setdefault(key, boxes) == boxes


def test_marks_survive_where_there_is_room():
    """Across the ten real boards most marks are still drawn (as asked or as an underline), and most arrows still join their two things."""
    m = {"kept": 0, "degraded": 0, "dropped": 0}
    a = {"direct": 0, "rerouted": 0, "stub": 0, "dropped": 0}
    for name in ALL:
        fx = _fx(name)
        reps = _reports(fx)
        last = [k for k, sc in enumerate(fx["scenes"]) if k == len(fx["scenes"]) - 1 or fx["scenes"][k + 1]["props"].get("board") != "same"]
        for k in last:                                                    # one count per board
            for key in m:
                m[key] += len(reps[k]["marks"][key])
            for key in a:
                a[key] += len(reps[k]["arrows"][key])
    drawn, total = m["kept"] + m["degraded"], sum(m.values())
    assert total > 90 and drawn >= 0.8 * total and m["kept"] >= 0.45 * total, m
    assert a["direct"] + a["rerouted"] >= 0.65 * sum(a.values()) and a["rerouted"] >= 1 and a["stub"] >= 1, a


# ----------------------------------------------------------------------------- the real ink of writing
@pytest.mark.parametrize("text", ["Tęcza", "jeden promień", "Où reste le sel ?", "lämpötila + kosteus", "ĄŚĆ gjpqy Ñ", "bliksem", "¿Cómo?", "Jokainen hiutale"])
@pytest.mark.parametrize("tool", ["marker", "pen"])
def test_the_ink_box_of_a_word_holds_its_real_ink(text, tool):
    """Root cause 1: a mark was sized from the room a line of text was GIVEN (`box`), not from its ink: the tails of j, p, g, y, ę and ń hang 20 to 40
    units below that box and a leading j starts 19 units left of it. `word_inks` is measured here against the letters as they are really rasterised."""
    blk = wr.layout(text, "neat", 120.0, max_width=4000, seed=3, min_size=76)
    inks = spec.word_inks(blk, (0.0, 0.0), tool, "neat")
    below = 0.0
    for w, ink in zip(blk["words"], inks):
        r = wr.raster_word(w, (0.0, 0.0), "neat", tool, blk["size"], 1.0, seed=1)
        ys, xs = np.nonzero(r["alpha"] > 0.3)
        real = (r["x"] + xs.min(), r["y"] + ys.min(), r["x"] + xs.max() + 1, r["y"] + ys.max() + 1)
        assert ink[0] <= real[0] + 1 and ink[1] <= real[1] + 1 and ink[2] >= real[2] - 1 and ink[3] >= real[3] - 1, (w["text"], ink, real)     # nothing sticks out
        assert max(real[0] - ink[0], real[1] - ink[1], ink[2] - real[2], ink[3] - real[3]) <= 20, (w["text"], ink, real)                       # and it is not padded
        below = max(below, real[3] - w["box"][3])
    if any(c in text for c in "jpgyęą"):
        assert below > 15                                                # the box the old mark was sized from: the tails are outside it


def test_a_circle_holds_the_whole_phrase():
    rep = _board([{"id": "k", "write": "Jokainen hiutale\najattelee", "zone": "centre", "say": "x"}, {"id": "c", "mark": "circle", "on": "k"}])
    assert rep["marks"]["kept"] == ["c"] and rep["collisions"] == []
    old = _board([{"id": "k", "write": "Jokainen hiutale\najattelee", "zone": "centre", "say": "x"}, {"id": "c", "mark": "circle", "on": "k"}], tidy=False)
    assert ["c", "k"] in old["collisions"]                               # the ellipse through the middle of the sides cut the first and last letters


def test_one_mark_per_thing():
    rep = _board([{"id": "s", "write": "Sol", "zone": "centre", "say": "x"}, {"id": "u", "mark": "underline", "on": "s"}, {"id": "b", "mark": "box", "on": "s"}])
    assert rep["marks"]["kept"] == ["u"] and rep["marks"]["dropped"] == [["b", "one mark per thing"]] and "b" not in rep["kinds"]


def test_no_room_for_a_circle_is_an_underline_and_no_room_for_that_is_nothing():
    base = [{"id": "d", "draw": "sun", "zone": "centre", "say": "x"}, {"id": "l", "write": "bliksem", "near": "d", "side": "right"}]
    rep = _board(base + [{"id": "c", "mark": "circle", "on": "l"}])       # the label sits right beside the drawing: a loop round it would run over the drawing
    assert rep["marks"]["degraded"] == [["c", "circle", "underline"]] and rep["collisions"] == []
    crowded = [{"id": "d", "draw": "sun", "zone": "centre", "say": "x"}, {"id": "l", "write": "heet", "near": "d", "side": "below"},
               {"id": "c", "mark": "circle", "on": "d"}, {"id": "c2", "mark": "box", "on": "l"}, {"id": "t", "write": "een lange regel tekst", "zone": "bottom", "size": "l"},
               {"id": "t0", "write": "nog een lange regel", "zone": "top", "size": "l"}]
    rep = _board(crowded)
    assert rep["collisions"] == []
    assert {x[0] for x in rep["marks"]["dropped"]} | {x[0] for x in rep["marks"]["degraded"]} | set(rep["marks"]["kept"]) == {"c", "c2"}


def test_a_drawing_and_its_label_are_circled_together():
    rep = _board([{"id": "d", "draw": "sun", "zone": "centre", "size": "s", "say": "x"}, {"id": "l", "write": "Sol", "near": "d", "side": "below"}, {"id": "c", "mark": "circle", "on": "d"}])
    assert rep["marks"]["kept"] == ["c"] and rep["collisions"] == []
    c, l_ = rep["boxes"]["c"], rep["boxes"]["l"]
    assert c[0] < l_[0] and c[3] > l_[3]                                  # the loop goes round the label too


def test_an_engine_mark_moves_to_a_thing_with_room():
    """A mark the engine added for pacing (keep_busy: em<n>_<thing>) stresses "the latest thing": when that one has no room it goes to a free one."""
    items = [{"id": "t", "write": "Titel", "zone": "top", "say": "x"}, {"id": "d", "draw": "sun", "zone": "centre"}, {"id": "l", "write": "heet", "near": "d", "side": "below"},
             {"id": "u", "mark": "underline", "on": "l"}, {"id": "em0_l", "mark": "box", "on": "l"}]
    rep = _board(items)
    assert rep["marks"]["moved"] and rep["marks"]["moved"][0][0] == "em0_l" and rep["marks"]["moved"][0][2] in ("d", "t") and rep["collisions"] == []
    rep = _board([dict(it, id="mine") if it["id"] == "em0_l" else it for it in items])       # the director's own second mark does not move: it is left out
    assert rep["marks"]["dropped"] == [["mine", "one mark per thing"]]


# ----------------------------------------------------------------------------- arrows
ROW = [{"id": "a", "draw": "sun", "zone": "left", "say": "x"}, {"id": "m", "draw": "piggy_bank", "zone": "centre"}, {"id": "c", "draw": "plant_sprout", "zone": "right"}]


def test_an_arrow_goes_round_what_is_between_its_ends():
    old = _board(ROW + [{"id": "ar", "connect": "arrow", "from": "a", "to": "c"}], tidy=False)
    rep = _board(ROW + [{"id": "ar", "connect": "arrow", "from": "a", "to": "c"}])
    assert rep["arrows"]["direct"] + rep["arrows"]["rerouted"] == ["ar"] and rep["collisions"] == [] and rep["crossed"] == []
    b, m = rep["boxes"]["ar"], rep["boxes"]["m"]
    assert b[1] < m[1] - spec.PATH_CLEAR or b[3] > m[3] + spec.PATH_CLEAR  # over or under the thing in the middle
    assert old["crossed"] in ([], ["ar"])                                  # (the old gentle bend may or may not have cleared it)


def test_an_arrow_with_no_way_through_is_a_stub_or_nothing_and_the_board_complains():
    wall = [{"id": "a", "draw": "sun", "zone": "left", "say": "x"}, {"id": "c", "draw": "plant_sprout", "zone": "right"},
            {"id": "w1", "write": "een hele lange\nregel tekst\nin de weg\nvan boven\ntot onder", "zone": "centre-col", "size": "l"},
            {"id": "w0", "write": "nog een regel bovenaan", "zone": "top", "size": "m"}]
    rep = _board(wall + [{"id": "ar", "connect": "arrow", "from": "a", "to": "c"}])
    assert rep["collisions"] == [] and rep["crossed"] == []
    how = next(k for k, v in rep["arrows"].items() if "ar" in [x[0] if isinstance(x, list) else x for x in v])
    if how == "stub":
        b = rep["boxes"]["ar"]
        assert max(b[2] - b[0], b[3] - b[1]) <= spec.STUB[0] + 60
    elif how == "dropped":
        assert "ar" not in rep["kinds"]
    old = _board(wall + [{"id": "ar", "connect": "arrow", "from": "a", "to": "c"}], tidy=False)
    assert old["crossed"] == ["ar"]                                       # as it shipped: through the text


def test_an_arrow_wins_over_the_marks_on_its_ends():
    rep = _board([{"id": "a", "draw": "sun", "zone": "left", "say": "x"}, {"id": "c", "draw": "piggy_bank", "zone": "centre"}, {"id": "m1", "mark": "circle", "on": "a"},
                  {"id": "m2", "mark": "circle", "on": "c"}, {"id": "ar", "connect": "arrow", "from": "a", "to": "c"}])
    assert rep["arrows"]["direct"] == ["ar"] and rep["collisions"] == []


def test_what_is_placed_after_an_arrow_cannot_land_on_it():
    rep = _board([{"id": "a", "draw": "sun", "zone": "left", "say": "x"}, {"id": "c", "draw": "piggy_bank", "zone": "right"}, {"id": "ar", "connect": "arrow", "from": "a", "to": "c"},
                  {"id": "l", "write": "heats", "near": "ar", "side": "below"}, {"id": "u", "mark": "underline", "on": "l"}])
    assert rep["collisions"] == [] and rep["kinds"].get("l") == "write"


# ----------------------------------------------------------------------------- the score and the policy
@pytest.mark.parametrize("name", LANGFIX)
def test_the_score_counts_marks_and_arrows_on_every_board(name, monkeypatch):
    plan = copy.deepcopy(_fx(name)["plan"])
    scores = score.score_plan(plan)
    s = score.summary(scores)
    assert s["collisions"] == 0 and s["crossed"] == 0 and {"arrows_blocked", "marks_degraded", "marks_dropped"} <= set(s)
    assert all("collisions" in b and "marks" in b and "blocked" in b for b in scores)
    for g in score.boards_of(plan["beats"]):
        d = score.defects([plan["beats"][i]["scene"]["props"] for i in g])
        assert d["collisions"] == [] and d["overlaps"] == []
    real = wbe.build
    monkeypatch.setattr(wbe, "build", lambda *a, **k: real(*a, **{**k, "tidy": False}))       # the same plans, laid out as they were drawn
    assert score.summary(score.score_plan(copy.deepcopy(_fx(name)["plan"])))["collisions"] >= 4


def test_a_blocked_arrow_is_a_complaint():
    plan = copy.deepcopy(_fx("langfix_pl")["plan"])
    b = score.score_plan(plan)[1]
    assert b["blocked"] == ["a2"] and any("no clear way" in c for c in b["complaints"]) and not b["ok"]


def test_make_clean_takes_out_of_the_plan_what_the_layout_reports(monkeypatch):
    plan = copy.deepcopy(_fx("langfix_pl")["plan"])
    assert wp.make_clean(plan) == {"removed": [], "left": 0}            # the layout already guarantees it
    real, calls = score.defects, []

    def defects(props_list, aspect="16:9", captions=True):
        d = real(props_list, aspect, captions)
        ids = [it["id"] for it in props_list[0]["items"]]
        if "m1" in ids and not calls:                                    # as if the layout had let one through
            d = dict(d, collisions=[["m1", "t"]])
        elif "m1" not in ids:
            calls.append(1)
        return d

    monkeypatch.setattr(score, "defects", defects)
    out = wp.make_clean(plan)
    assert out == {"removed": ["m1"], "left": 0}
    items = plan["beats"][0]["scene"]["props"]["items"]
    assert "m1" not in [it["id"] for it in items] and any(it["id"] == "t" for it in items)       # the mark went, what it marked stayed


@pytest.mark.parametrize("name,beat", [("langfix_pl", 1), ("langfix_pt", 2)])
def test_a_board_that_looks_empty_is_filled_by_what_is_on_it(name, beat):
    """Point 3 of the 2026-11-27 runs: these two boards shipped at 28 % coverage after the one rewrite ("looks empty")."""
    plan = copy.deepcopy(_fx(name)["plan"])
    props = plan["beats"][beat]["scene"]["props"]
    said = plan["beats"][beat]["narration"]
    ids = [it["id"] for it in props["items"]]
    before = score.defects([props])
    assert before["coverage"] < score.MIN_COVERAGE
    out = wp.fill_out([props])
    after = score.defects([props])
    assert out["larger"] >= 1 and after["coverage"] >= score.MIN_COVERAGE and after["coverage"] == out["coverage"][1]
    assert not after["overlaps"] and not after["off_board"] and not after["collisions"] and after["lost"] <= before["lost"]
    assert [it["id"] for it in props["items"]] == ids and plan["beats"][beat]["narration"] == said
    assert not any("looks empty" in c for c in score.score_plan(plan)[[i for i, g in enumerate(score.boards_of(plan["beats"])) if beat in g][0]]["complaints"])
    assert wp.fill_out([props])["larger"] == 0                           # at the bar it stops


def test_review_ships_clean_boards_and_fills_the_empty_one():
    plan = copy.deepcopy(_fx("langfix_pt")["plan"])
    notes = wp.review(plan, wp.Policy(True, "asked"), None, "pt")
    sc = plan["whiteboard"]["score"]
    assert sc["collisions"] == 0 and sc["crossed"] == 0 and sc["overlaps"] == 0
    assert sc["filled_out"][0]["board"] == 2 and any("looked empty" in n for n in notes)
    assert not any("looks empty" in c for b in sc["boards_detail"] for c in b["complaints"])
