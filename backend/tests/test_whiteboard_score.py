"""The self-check of a whiteboard plan (engine/whiteboard/score.py and whiteboard_policy.review): every board is scored as the renderer will lay it out and time
it; a board that fails is written again once with its complaint; the scores are logged and kept in the plan."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.whiteboard import library, score  # noqa: E402

SAID = "The sun warms the pond and the water rises as vapour into the cold sky where it gathers in clouds and falls again as rain on the hills"


def beat(items, narration=SAID, board=None):
    return {"narration": narration, "scene": {"type": "whiteboard", "props": ELEMENTS["whiteboard"].sanitize({"items": items, **({"board": board} if board else {})})}}


FULL = [{"id": "t", "write": "The water cycle", "zone": "top-row", "size": "l", "say": "warms"}, {"id": "s", "draw": "sun", "zone": "left", "say": "pond"},
        {"id": "sl", "write": "heat", "near": "s", "side": "below", "tool": "pen", "size": "s", "say": "water"}, {"id": "v", "write": "vapour", "zone": "centre", "say": "vapour"},
        {"id": "a", "connect": "arrow", "from": "s", "to": "v", "say": "cold"}, {"id": "p", "draw": "plant_sprout", "zone": "bottom-left", "say": "gathers"},
        {"id": "c", "write": "clouds", "zone": "right", "say": "clouds"}, {"id": "a2", "connect": "arrow", "from": "v", "to": "c", "say": "falls"},
        {"id": "r", "write": "rain", "zone": "bottom-right", "size": "xl", "say": "rain"}, {"id": "u", "mark": "underline", "on": "r", "say": "hills"},
        {"id": "pig", "draw": "piggy_bank", "zone": "bottom"}]
SPARSE = [{"id": "t", "write": "Rain", "zone": "top", "size": "s", "say": "rain"}]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("WHITEBOARD", "1")


def test_needs_no_drawing_package(monkeypatch):
    monkeypatch.setattr(library, "load", lambda oid: (_ for _ in ()).throw(AssertionError("the planner has no right to read the catalog bucket")))
    s = score.score_plan({"beats": [beat(FULL)]})
    assert len(s) == 1 and s[0]["solid"] == 8 and s[0]["items"] >= 11 and 0.2 < s[0]["coverage"] < 0.9 and s[0]["min_text"] >= score.MIN_TEXT


def test_a_full_board_passes_and_a_sparse_one_is_told_why():
    wp.retie(beat(FULL)["scene"]["props"], SAID)
    good = score.score_plan({"beats": [beat(FULL)]})[0]
    assert good["ok"], good["complaints"]
    assert good["pen_busy"] >= score.MIN_BUSY and good["longest_idle_s"] <= score.MAX_IDLE_S and not good["overlaps"] and not good["crossed"]
    bad = score.score_plan({"beats": [beat(SPARSE)]})[0]
    assert not bad["ok"] and any("only 1 drawings and written phrases" in c and "free zones" in c for c in bad["complaints"])
    assert any("pen" in c for c in bad["complaints"])                              # ... and the pen rests through most of it


def test_overlaps_and_long_texts_are_named():
    clash = [{"id": "one", "write": "A long phrase here", "zone": "centre", "size": "xl", "say": "sun"},
             {"id": "two", "write": "Another long phrase", "zone": "centre", "size": "xl", "say": "pond"}]
    s = score.score_plan({"beats": [beat(clash)]}, "9:16")[0]
    assert not s["ok"] and any("overlap" in c or "does not fit" in c for c in s["complaints"])


def test_boards_are_scored_whole_and_in_every_aspect():
    plan = {"beats": [beat(FULL[:5]), beat([FULL[5], FULL[6], FULL[8], FULL[9], FULL[10]], board="same"), beat(SPARSE, "A last word about rain.")]}
    for aspect in ("16:9", "9:16", "1:1", "4:5"):
        s = score.score_plan(plan, aspect)
        assert [x["beats"] for x in s] == [[1, 2], [3]] and s[0]["solid"] == 8 and s[0]["seconds"] > 20
    tot = score.summary(score.score_plan(plan))
    assert tot["boards"] == 2 and tot["failed"] >= 1 and tot["solid_per_board"] == 4.5 and 0 < tot["pen_busy"] <= 1


def test_review_writes_a_failing_board_again_once_and_keeps_the_better(on, capsys):
    policy = wp.Policy(True, "asked")
    plan = {"beats": [beat(SPARSE), beat(FULL)]}
    asked = []

    def ask(system, user):
        asked.append((system, user))
        return json.dumps({"beats": [{"beat": 1, "board": "new", "items": FULL}]})

    notes = wp.review(plan, policy, ask)
    assert len(asked) == 1 and "only 1 drawings" in asked[0][1] and "Narration (final)" in asked[0][1] and "WHITEBOARD VIDEO" in asked[0][0]
    assert "Beat 2." not in asked[0][1]                                            # only the beats of the failing board are sent
    assert len(plan["beats"][0]["scene"]["props"]["items"]) >= 10 and plan["beats"][0]["narration"] == SAID       # the board is new, the narration untouched
    sc = plan["whiteboard"]["score"]
    assert sc["replanned"] and sc["kept"] == "new" and sc["first"]["failed"] == 1 and sc["failed"] == 0 and len(sc["boards_detail"]) == 2
    assert any("written again once" in n for n in notes)
    logged = [json.loads(line.split(" ", 1)[1]) for line in capsys.readouterr().out.splitlines() if line.startswith("WHITEBOARD_SCORE ")]
    assert [x["pass"] for x in logged] == [1, 2] and logged[0]["failed"] == 1 and logged[1]["kept"] == "new"


def test_review_keeps_the_first_boards_when_the_repair_is_worse_or_broken(on):
    policy = wp.Policy(True, "asked")
    for answer in ('{"beats": [{"beat": 1, "items": []}]}', "sorry, no", json.dumps({"beats": [{"beat": 2, "items": SPARSE}]})):
        plan = {"beats": [beat(SPARSE), beat(FULL)]}
        before = json.dumps(plan["beats"], sort_keys=True)
        wp.review(plan, policy, lambda s, u: answer)
        assert json.dumps(plan["beats"], sort_keys=True) == before and plan["whiteboard"]["score"]["failed"] == 1
    plan = {"beats": [beat(FULL)]}
    assert wp.review(plan, policy, lambda s, u: (_ for _ in ()).throw(AssertionError("a passing plan asks nothing"))) == [] and plan["whiteboard"]["score"]["failed"] == 0
    assert wp.review({"beats": [beat(SPARSE)]}, wp.Policy(False, "flag_off"), None) == []
    assert wp.review({"beats": [beat(SPARSE)]}, policy, None)                     # no model: scored, logged, nothing changed


# ================================================================= shared boards never overlap (the first Polish video, 2026-11-27)
PL = os.path.join(os.path.dirname(__file__), "fixtures", "plans", "pl_rainbow_wb_plan.json")


def _pl():
    with open(PL, encoding="utf-8") as f:
        return json.load(f)


def _geometry(plan):
    """Overlaps and things off the board on every board of the plan, as the renderer will lay them out."""
    out = []
    for g in score.boards_of(plan["beats"]):
        d = score.defects([plan["beats"][i]["scene"]["props"] for i in g], "16:9")
        out += [tuple(x) for x in d["overlaps"]] + d["off_board"]
    return out


def test_the_polish_plan_as_shipped_overlaps_and_the_score_says_so():
    plan = _pl()
    s = score.score_plan(plan)
    assert [x["beats"] for x in s] == [[1], [2, 3], [4]] and len(s[1]["overlaps"]) == 3            # beat 3 on beat 2's board, in beat 2's zones
    assert score.summary(s)["overlaps"] == 3 and not s[1]["ok"]                                    # counted although that board fails


def test_review_takes_the_whole_board_it_scored_not_only_its_flag(on):
    """What happened: beats 2 and 4 were written again; `compose` then put beat 3 on beat 2's new board, in free zones, in the TRIAL; the plan took the
    rewritten beats and only the FLAG of beat 3, whose things stayed in the zones of a board of its own: three overlaps shipped, zero reported."""
    shipped = _pl()
    plan = _pl()
    plan["beats"][2]["scene"]["props"].pop("board")                                                # before the review: four boards, one per beat
    plan["beats"][1]["scene"]["props"]["items"] = [dict(it) for it in SPARSE]                      # board 2 fails, so it is written again ...
    plan["beats"][1]["scene"]["props"]["items"][0]["say"] = "kropli"
    answer = json.dumps({"beats": [{"beat": 2, "board": "new", "items": shipped["beats"][1]["scene"]["props"]["items"]}]}, ensure_ascii=False)   # ... as the director did
    asked = []
    wp.review(plan, wp.Policy(True, "asked"), lambda s, u: asked.append(u) or answer, "pl")
    assert len(asked) == 1 and plan["whiteboard"]["score"]["replanned"]
    assert _geometry(plan) == []                                                                   # nothing overlaps, nothing leaves a board
    sc = plan["whiteboard"]["score"]
    again = score.summary(score.score_plan(plan))
    assert sc["overlaps"] == again["overlaps"] == 0 and sc["off_board"] == again["off_board"] == 0  # and the record is the score of what ships
    assert [b["narration"] for b in plan["beats"]] == [b["narration"] for b in shipped["beats"]]


def test_a_beat_shares_a_board_only_when_its_things_really_fit():
    """Free ZONES are not room: the list of colours fits no single corner. With the aspect known the beat gets its own board and its author's zones back."""
    plan = _pl()
    plan["beats"][2]["scene"]["props"].pop("board")
    zones = [it.get("zone") for it in plan["beats"][2]["scene"]["props"]["items"]]
    blind = _pl()
    blind["beats"][2]["scene"]["props"].pop("board")
    assert wp.compose(blind["beats"])["shared"] == 1 and _geometry(blind) != []                    # by zones alone: shared, and 'cols' leaves the board
    st = wp.compose(plan["beats"], "16:9")
    assert st["split"] == 1 and st["shared"] == 0 and st["boards"] == 4
    assert [it.get("zone") for it in plan["beats"][2]["scene"]["props"]["items"]] == zones and _geometry(plan) == []
    easy = {"beats": [beat(FULL[:5]), beat([FULL[5], FULL[6], FULL[8], FULL[9], FULL[10]])]}          # things that do fit still share (boards stay full)
    assert wp.compose(easy["beats"], "16:9")["shared"] == 1 and _geometry(easy) == []


def test_a_board_that_still_overlaps_is_never_shipped_as_it_is(on, capsys):
    """No model, a repair refused, or a repair that broke: the shipped Polish board goes through the last resort and comes out without an overlap."""
    for ask in (None, lambda s, u: "sorry, no", lambda s, u: (_ for _ in ()).throw(RuntimeError("model down"))):
        plan = _pl()
        notes = wp.review(plan, wp.Policy(True, "asked"), ask, "pl")
        sc = plan["whiteboard"]["score"]
        assert _geometry(plan) == [] and sc["overlaps"] == 0 and sc["off_board"] == 0 and sc["made_safe"]["left"] == 0 and sc["made_safe"]["boards"] == [2]
        assert any("overlapping or off the board" in n for n in notes)
        assert sc["made_safe"]["split"] == 1 and sc["made_safe"]["dropped"] == 0 and sc["boards"] == 4                 # a fresh board was the room: nothing was lost
        assert "board" not in plan["beats"][2]["scene"]["props"] and any(it["id"] == "cols" for it in plan["beats"][2]["scene"]["props"]["items"])
        assert all(sum(1 for it in b["scene"]["props"]["items"] if it.get("draw") or it.get("write")) >= 1 for b in plan["beats"])     # no beat lost its board
    logged = [json.loads(line.split(" ", 1)[1]) for line in capsys.readouterr().out.splitlines() if line.startswith("WHITEBOARD_SCORE ")]
    assert logged[0]["overlaps"] == 3 and [x for x in logged if x["pass"] == "safe"][0]["overlaps"] == 0
    # a pile of long texts in one zone: moved apart, made smaller, or taken off, until the layout is clean; it always ends
    pile = {"beats": [beat([{"id": f"w{k}", "write": "a rather long line of handwriting", "zone": "centre", "size": "xl", "say": "sun"} for k in range(6)])]}
    r = wp.untangle([pile["beats"][0]["scene"]["props"]])
    assert r["left"] == 0 and _geometry(pile) == [] and r["moved"] + r["smaller"] + r["dropped"] > 0 and pile["beats"][0]["scene"]["props"]["items"]
