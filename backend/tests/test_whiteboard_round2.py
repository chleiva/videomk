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


# ----------------------------------------------------------------------------- layout: the measures and the fixes (2, 3 and the tall frame)
from engine.frame import Frame  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.scenes.base import SceneCtx  # noqa: E402
from engine.scenes.elements import whiteboard as wbe  # noqa: E402
from engine.whiteboard import spec  # noqa: E402


def _board(items, aspect="16:9"):
    props = ELEMENTS["whiteboard"].sanitize({"items": items})
    ctx = SceneCtx(frame=Frame.parse(aspect, "1080p"), captions=True)
    return wbe.build(props, 10.0, ctx, 480, 270, load=score._stub_loader(), layout_only=True)[3]


def test_two_texts_never_read_as_one_word():
    """The French sea-salt video: "sel" and "soleil" touched ("selsoleil"). The ink of different texts keeps TEXT_GAP apart, the score counts it."""
    p = plan("fr_sea_salt_r2")
    sc = score.score_plan(p, "16:9")
    assert [s["close_texts"] for s in sc] == [[], []]
    # the measure itself sees the old layout: put the label back where it was (9 units under the text) and the pair is reported
    items = [{"id": "sw", "write": "sel", "zone": "left", "size": "l"}, {"id": "sol", "write": "soleil", "near": "sw", "side": "right", "size": "s"}]
    assert _board(items)["close_texts"] == []
    real = spec._apart_texts
    spec._apart_texts = lambda blk, x, y, *a, **k: (x, y)
    old_gap = spec.TEXT_GAP
    try:
        orig_free = spec._free_side
        spec._free_side = lambda tb, w, h, side, gap, by_id, L: orig_free(tb, w, h, side, 9.4, by_id, L)
        close = _board(items)["close_texts"]
    finally:
        spec._apart_texts, spec._free_side, spec.TEXT_GAP = real, orig_free, old_gap
    assert close and close[0][2] < spec.TEXT_GAP
    assert any(c[0] == "sw" for c in close)


def test_a_close_pair_is_a_complaint_for_the_director_not_a_failure_to_hide():
    assert "gap" in score.DIRECTOR_KINDS


def test_an_arrow_aims_at_the_words_and_the_underline_yields():
    """An arrow coming from below a underlined word stopped at the underline tip (74 units under the writing) and pointed at the underline."""
    r = _board([{"id": "b", "write": "Hielo", "zone": "top", "size": "l"}, {"id": "a", "write": "Calor", "zone": "bottom", "size": "l"},
                {"id": "x", "connect": "arrow", "from": "a", "to": "b"}, {"id": "u", "mark": "underline", "on": "b"}])
    tip_y = r["arrow_ends"]["x"][1][1]
    assert r["boxes"]["b"][3] < tip_y < r["boxes"]["b"][3] + 40, tip_y            # was about 74 below the writing
    assert ["u", "an arrow needed the room"] in r["marks"]["dropped"] and r["collisions"] == []


def test_underlines_are_capped_and_never_end_to_end():
    """Six circles degraded into two rows of underlines end to end (QA, vaccine video): over the real boards no board has more than the cap, and no two underlines
    of one board at about the same height end less than UNDER_END_GAP apart."""
    import glob

    seen = 0
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard_boards", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            fx = json.load(fh)
        ctx = SceneCtx(frame=Frame.parse(fx["aspect"], "1080p"), captions=fx["captions"])
        for sc_ in fx["scenes"]:
            r = wbe.build(sc_["props"], sc_["duration"], ctx, 480, 270, load=score._stub_loader(), layout_only=True)[3]
            under = [i for i, k in r["kinds"].items() if k == "mark" and any(it["id"] == i.split(":")[-1] and it.get("mark", "").endswith("underline") or
                                                                                 [d for d in r["marks"]["degraded"] if d[0] == i.split(":")[-1] and d[2] == "underline"]
                                                                                 for it in sc_["props"]["items"])]
            degraded = [x for x in r["marks"]["degraded"] if x[2] == "underline"]
            assert len(degraded) <= spec.UNDERLINES_DEGRADED, f
            seen += len(under)
            boxes = sorted((r["boxes"][i] for i in under), key=lambda b: b[0])
            for a_, b_ in zip(boxes, boxes[1:]):
                same_row = abs((a_[1] + a_[3]) / 2 - (b_[1] + b_[3]) / 2) < 45
                assert not same_row or b_[0] - a_[2] >= spec.UNDER_END_GAP, (f, a_, b_)
    assert seen > 10


def test_a_loop_keeps_a_wider_clear_margin_to_the_next_item():
    assert spec.LOOP_CLEAR >= 30.0 and spec.LOOP_CLEAR > spec.MARK_CLEAR


def test_a_lonely_column_is_centred_and_a_tall_board_gives_empty_rows_nothing():
    items = [{"id": "t", "write": "ARN\nmensajero", "zone": "top-left"}, {"id": "c", "draw": "cell", "zone": "left"}, {"id": "l", "write": "Pieza", "near": "c"}]
    out = spec.centred(items)
    assert [i.get("zone") for i in out] == ["top", "centre", None]
    two = items + [{"id": "r", "draw": "sun", "zone": "right"}]
    assert spec.centred(two) is two                                    # two columns used: nothing moves
    assert spec.weights(items, tall=True)[0][2] < spec.weights(items)[0][2] and spec.weights(items, tall=True)[1][2] < spec.weights(items)[1][2]


def test_a_block_of_several_lines_stands_centred_in_its_zone():
    r = _board([{"id": "t", "write": "ARN\nmensajero", "zone": "top-row", "size": "m"}], "9:16")
    x0, _, x1, _ = r["boxes"]["t"]
    W = r["view"][2]
    assert abs((x0 + x1) / 2 - (r["view"][0] + W / 2)) < 0.15 * W, (x0, x1, r["view"])      # was flush against the left edge of the zone
