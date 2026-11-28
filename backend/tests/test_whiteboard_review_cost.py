"""The whiteboard review's cost (docs/WHITEBOARD_REVIEW_COST_2026-11-28.md): model-free moves before the director (whiteboard/mend.py), the director's output budget, the
option to write key words for the count. Real plans of the QA run of 2026-11-28 as fixtures (tests/fixtures/whiteboard_plans/review_cost_qa_2026-11-28.json: the plan
as it stood just before the review, the director's recorded answer)."""
import copy
import io
import contextlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")

from engine import whiteboard_policy as wp  # noqa: E402
from engine.whiteboard import mend, score  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard_plans", "review_cost_qa_2026-11-28.json")


def qa(name):
    with open(FIX, encoding="utf-8") as f:
        d = json.load(f)[name]
    return copy.deepcopy(d["plan"]), d


def pol(d):
    return wp.Policy(True, "asked", aspect=d["aspect"])


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setenv("WHITEBOARD", "1")
    monkeypatch.delenv("WB_MEND", raising=False)
    monkeypatch.delenv("WB_MEND_COUNT", raising=False)


def repaired(p, d, mend_too):
    s = score.score_plan(p, d["aspect"])
    with contextlib.redirect_stdout(io.StringIO()):
        return wp._repair(p, pol(d), s, {}, [], mend_too=mend_too)


def shape(p):
    """What a move must never change: every item's id and kind, the order of the items, the narration."""
    return [(b.get("narration"), [(it.get("id"), it.get("draw") or it.get("write") or it.get("mark") or it.get("connect")) for it in (b["scene"]["props"].get("items") or [])])
            for b in p["beats"] if b["scene"]["type"] == "whiteboard"]


def test_mend_clears_blocked_arrows_without_touching_what_is_said():
    p, d = qa("p5_it_mutuo")
    before = repaired(copy.deepcopy(p), d, False)
    q = copy.deepcopy(p)
    after = repaired(q, d, True)
    assert sum(1 for s in before if "arrow" in s["kinds"]) == 2
    assert sum(1 for s in after if "arrow" in s["kinds"]) == 0
    assert mend._key(after)[0] < mend._key(before)[0]
    assert shape(q) == shape(p)                               # nothing added, taken off or reworded; the narration is the same


def test_mend_never_makes_a_video_worse_on_any_fixture():
    for name in ("p3_fr_sel", "p4_de_zins", "p5_it_mutuo", "p7_nl_batterij"):
        p, d = qa(name)
        a = mend._key(repaired(copy.deepcopy(p), d, False))
        b = mend._key(repaired(copy.deepcopy(p), d, True))
        assert b[0] <= a[0] and b[1] <= a[1], (name, a, b)


def test_the_setting_switches_mend_off(monkeypatch):
    monkeypatch.setenv("WB_MEND", "0")
    p, d = qa("p5_it_mutuo")
    q = copy.deepcopy(p)
    repaired(q, d, True)
    r = copy.deepcopy(p)
    repaired(r, d, False)
    assert q == r and not wp.mend_enabled()


def test_a_move_is_kept_only_for_a_strictly_better_video():
    ok = lambda kinds, ok_=False: {"ok": ok_, "kinds": kinds, "complaints": ["x"] * len(kinds)}  # noqa: E731
    old = [ok(["arrow", "late"]), ok([], True)]
    assert mend._improves(old, [ok(["late"]), ok([], True)])
    assert not mend._improves(old, old)                                           # the same: undone
    assert not mend._improves(old, [ok(["late"]), ok(["gap"])])                   # a passing board now fails
    assert not mend._improves(old, [ok(["gap"]), ok([], True)])                   # fewer complaints but a kind that was not there
    assert not mend._improves(old, [ok(["late"])])                                # a different number of boards


def test_a_late_item_is_tied_earlier_but_never_before_its_predecessor():
    items = [{"id": "a", "write": "uno", "zone": "left", "say": "alfa"}, {"id": "b", "write": "dos", "zone": "right", "say": "delta"}]
    plan = {"beats": [{"narration": "alfa beta gamma delta epsilon", "scene": {"type": "whiteboard", "props": {"items": items}}}]}
    moves = mend._late_moves(plan, {"beats": [1], "late": [["b", 1.0]]})
    assert [m[3] for m in moves] == ["gamma", "beta"]                         # "alfa" is taken by the item before: order stays the narration's
    assert all(m[1] == "say" and m[2] == "delta" for m in moves)


def test_director_budget_grows_with_the_boards_and_is_capped():
    assert wp.director_budget(1) == 9200 and wp.director_budget(5) == 22000
    assert wp.director_budget(0) == wp.director_budget(1) and wp.director_budget(99) == 32000


def test_a_cut_off_answer_is_asked_again_with_more_room():
    seen = []

    def ask(system, user, max_tokens=None):
        seen.append(max_tokens)
        return "" if len(seen) == 1 else '{"beats": []}'

    assert wp._ask_director(ask, "s", "u", budget=9000) == {"beats": []}
    assert seen == [9000, 13500]
    plain = []
    assert wp._ask_director(lambda s, u: plain.append(u) or '{"beats": []}', "s", "u", budget=9000) == {"beats": []}      # an ask without the argument still works


def test_review_passes_its_budget_to_the_director(monkeypatch):
    p, d = qa("p3_fr_sel")
    seen = []

    def ask(system, user, max_tokens=None):
        seen.append(max_tokens)
        return d["director_answer"]

    with contextlib.redirect_stdout(io.StringIO()):
        wp.review(p, pol(d), ask, d["language"])
    assert seen and seen[0] == wp.director_budget(2)


def test_review_with_mend_is_never_worse_than_without_on_the_recorded_answers(monkeypatch):
    for name in ("p3_fr_sel", "p4_de_zins", "p5_it_mutuo", "p7_nl_batterij"):
        res = {}
        for flag in ("0", "1"):
            monkeypatch.setenv("WB_MEND", flag)
            p, d = qa(name)
            with contextlib.redirect_stdout(io.StringIO()):
                wp.review(p, pol(d), lambda s, u, d=d: d["director_answer"], d["language"])
            res[flag] = mend._key(score.score_plan(p, d["aspect"]))
        assert res["1"][0] <= res["0"][0] and res["1"][1] <= res["0"][1], (name, res)


def test_the_count_option_is_off_by_default_and_when_on_only_helps(monkeypatch):
    p, d = qa("p3_fr_sel")
    base = repaired(copy.deepcopy(p), d, True)
    assert sum(1 for s in base if "count" in s["kinds"]) == 2
    monkeypatch.setenv("WB_MEND_COUNT", "1")
    q = copy.deepcopy(p)
    s = repaired(q, d, True)
    assert sum(1 for x in s if "count" in x["kinds"]) < 2 and mend._key(s) < mend._key(base)


def test_the_budget_setting_switches_the_budget_off(monkeypatch):
    monkeypatch.setenv("WB_REVIEW_BUDGET", "off")
    p, d = qa("p3_fr_sel")
    seen = []

    def ask(system, user, max_tokens=None):
        seen.append(max_tokens)
        return d["director_answer"]

    with contextlib.redirect_stdout(io.StringIO()):
        wp.review(p, pol(d), ask, d["language"])
    assert seen and seen[0] is None
