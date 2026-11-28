"""The automatic speaker gestures (engine/character_gestures.py): deterministic, one arm never asked for two things at once, always back to rest, inside the limits.
The arms themselves (bends, speeds, the way home, rest poses, the card) are measured in tests/test_presenter_arms.py."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import align  # noqa: E402
from engine import character_gestures as cg  # noqa: E402
from engine import vector_presenter as vp  # noqa: E402

TALKS = [
    "Hello, I'm David. A fast app comes down to three steps: measure, simplify and cache. Guessing is easy, but measuring is what works. Look at this chart: every second really matters. Thanks for watching!",
    "Hi! I'm Fox, your guide. Today we explore the forest together. On one side there are tall old trees, but on the other side, a quiet river. Ready? Great, follow me!",
    "Hello, I'm Priya. A good check-up starts with a simple conversation. First, we talk about how you feel. Second, we check your heart and lungs. And remember: small habits are the best medicine.",
    "Hola, soy Mateo. La buena comida empieza con ingredientes frescos. Mira estos tomates: maduros, rojos y llenos de sabor. ¿Necesitas una cocina cara? Para nada. Gracias por ver.",
    "The report is long. It has many pages and it was written over several months by a team that worked in three cities. Nobody expected the result. The numbers are in the table and the method is in the appendix.",
]


def words_for(text, rate=13.0):
    return align.estimate_words(text, len(text) / rate, lead=0.4)


def plan(text, seed=0.3, side=1):
    return cg.plan_gestures(words_for(text), seed, side)


@pytest.mark.parametrize("text", TALKS)
def test_plan_is_deterministic(text):
    a, ab = plan(text)
    b, bb = plan(text)
    assert [g.as_tuple() for g in a] == [g.as_tuple() for g in b] and ab == bb


@pytest.mark.parametrize("text", TALKS)
@pytest.mark.parametrize("seed", [0.0, 0.3, 0.71, 5.0])
def test_no_overlap_and_phases_in_order(text, seed):
    gs, beats = plan(text, seed)
    ws = words_for(text)
    for g in gs:
        assert 0.0 <= g.t0 < g.stroke <= g.hold_end < g.t1
        assert g.stroke - g.t0 >= 0.75 * cg.PREP_S or g.t0 == 0.0     # a preparation is never a jerk
        assert g.hold_end - max([g.stroke] + [s[0] for s in g.steps]) >= cg.MIN_HOLD_S - 1e-6
        assert g.t1 - g.hold_end >= cg.RETRACT_S - 1e-6          # a return is never a snap
        assert all(g.stroke <= s[0] <= g.hold_end for s in g.steps)
        starts = [a for w, a, b in ws if w == g.word]
        assert any(g.stroke <= a + 1e-6 for a in starts) or g.t0 == 0.0        # the stroke lands on or before its word, never after (except a talk that opens on the cue)
    for a, b in zip(gs, gs[1:]):                                # the next gesture starts only when this one has landed and been seen; then either the hands
        assert b.t0 >= max([a.stroke] + [s[0] for s in a.steps]) + cg.MIN_HOLD_S - 1e-6      # rest in between, or the arm goes straight on (test_presenter_arms)
    for (ta, _, _), (tb, _, _) in zip(beats, beats[1:]):
        assert tb - ta >= cg.BEAT_GAP_S - 1e-6
    for tb, _, _ in beats:                                      # no beat while a hand is on its way out or back
        assert not any(g.t0 - 0.45 < tb < g.stroke + 0.4 or g.hold_end - 0.35 < tb < g.t1 + 0.45 for g in gs)


@pytest.mark.parametrize("text", TALKS)
def test_limits(text):
    ws = words_for(text)
    gs, beats = cg.plan_gestures(ws, 0.3, 1)
    total = ws[-1][2] - ws[0][1]
    sents = cg.sentences(ws)
    assert len(gs) <= len(sents)                                # at most one meaningful gesture per sentence
    assert len(gs) <= max(1, math.ceil(cg.MAX_PER_MINUTE * total / 60.0))
    assert cg.busy_share(gs, total) <= cg.MAX_BUSY + 0.06
    for a, b in zip(gs, gs[1:]):
        assert a.kind != b.kind or a.kind == "count" or (a.kind == "wave" and b.t0 - a.t1 > 5.0)      # never the same gesture twice in a row (a running count is one idea; hello and goodbye are two moments)
    for idx in sents:                                           # and never two gestures inside one sentence
        a, b = ws[idx[0]][1], ws[idx[-1]][2]
        assert sum(1 for g in gs if a - cg.STROKE_LEAD_S - 1e-6 <= g.stroke < b) <= 1
    assert len(beats) <= len(sents) + 2


def test_a_plain_text_gets_few_gestures():
    gs, beats = plan(TALKS[4])
    assert len(gs) <= 1 and len(beats) >= 1                     # no cue, no show: only beats


def kinds(text, side=1, seed=0.3):
    return [g.kind for g in plan(text, seed, side)[0]]


def test_text_cues_pick_the_gesture():
    assert kinds("Hello everyone, welcome to the show.") == ["wave"]
    assert kinds("We sell apples every day. Why does that matter to you?")[-1] == "shrug"
    g = plan("We need three things today: flour, water and salt.")[0][0]
    assert g.kind == "count" and [s[1] for s in g.steps] == [1, 2, 3] and g.hand != "both"
    g = plan("The first plan was cheap and quick, but the second plan was safe.")[0][0]
    assert g.kind == "compare" and g.hand == "both" and g.steps[0][1] == "second" and g.steps[0][0] > g.stroke
    g = plan("Now look at this number on the screen.", side=-1)[0][0]
    assert g.kind == "present" and g.side == -1 and g.hand == "l"
    g = plan("Now look at this number on the screen.", side=1)[0][0]
    assert g.side == 1 and g.hand == "r"
    assert kinds("That was a long day. Great, you made it to the end.")[-1] == "thumb"
    assert "open" in kinds("We tried it once. This step is very important for everyone.", side=0, seed=0.8) or "present" in kinds("We tried it once. This step is very important for everyone.", side=0, seed=0.8)
    assert "count" not in kinds("We waited there. Because every second counts in a race.")      # "second" the unit of time is not "second" the ordinal
    assert kinds("Hola a todos, bienvenidos a la cocina de la escuela. Primero, lavamos muy bien las manos con agua y con jabón durante un minuto. Segundo, cortamos el pan en rebanadas finas con mucho cuidado. "
                 "Muchas gracias por venir y hasta pronto.") == ["wave", "count", "count", "wave"]


def test_nobody_points_with_a_finger():
    """A single finger appears only when counting, with the forearm upright; presenting uses the open hand."""
    assert cg.KEY["present"][2] == "open" and cg.KEY["compare"][2] == "open" and cg.KEY["open"][2] == "open"
    perf = cg.Performance(seed=0.3, content_side=1)
    perf.speak(words_for(TALKS[0]))
    g = vp.Geom()
    t = 0.0
    while t < 20.0:
        pose, _ = perf.pose(t, g)
        for i, s in enumerate(pose["hand_shape"]):
            if s in ("one", "two", "three", "thumb"):
                active = [x for x in perf.gestures if x.t0 <= t < x.t1 and x.kind in ("count", "thumb")]
                assert active
                sk = vp.solve(g, pose)
                assert sk["fore_dir"][i][1] > 0.6               # the forearm points up: a count beside the shoulder, not a finger aimed at somebody
        t += 1 / 30


def run(text, seed=0.3, side=1, dur=22.0, fps=30):
    perf = cg.Performance(seed=seed, content_side=side)
    perf.speak(words_for(text))
    g = vp.Geom()
    return perf, g, [perf.pose(i / fps, g)[0] for i in range(int(dur * fps))]


def at_rest(arm, wrist):
    """Is this arm in one of the relaxed poses, give or take the idle sway?"""
    return 3.0 < arm[0] < 13.0 and -18.0 < arm[1] < 6.0 and -20.0 < wrist < 0.0


@pytest.mark.parametrize("text", TALKS[:4])
def test_hands_return_to_home_base(text):
    perf, g, poses = run(text)
    assert perf.gestures
    busy = [(x.t0 - 0.05, x.t1 + cg.TWIN_LAG_S + 1.0) for x in perf.gestures] + [(b[0] - 0.3, b[0] + 0.6) for b in perf.beats]
    seen = 0
    for i, p in enumerate(poses):
        t = i / 30
        if any(a <= t <= b for a, b in busy):
            continue
        seen += 1
        for arm, wr, s in zip(p["arms"], p["wrist"], p["hand_shape"]):
            assert at_rest(arm, wr) and s == "relaxed", (t, arm, wr)
    assert seen > 30
    assert all(at_rest(arm, wr) for arm, wr in zip(poses[-1]["arms"], poses[-1]["wrist"]))


@pytest.mark.parametrize("text", TALKS[:4])
def test_gesture_box_and_smooth_motion(text):
    perf, g, poses = run(text)
    for i, p in enumerate(poses):
        t = i / 30
        gs = perf.gestures                                                       # a wave lasts until the hand is home, or until the next gesture has taken the arm over
        waving = any(x.kind == "wave" and x.t0 <= t <= max([x.t1] + [y.stroke for y in gs[k + 1:k + 2]]) + 0.3 for k, x in enumerate(gs))
        sk = vp.solve(g, p)
        for j, side in enumerate((-1, 1)):
            s, w = sk["shoulders"][j], sk["wrists"][j]
            if not waving:
                assert w[1] - s[1] <= 0.10 * g.arm                               # nothing but the greeting lifts a wrist above the shoulders
            assert (w[0] - s[0]) * side > -0.10 * g.arm                          # a speaker's hand never crosses the body
        assert abs(p["lean"]) < 4.0 and abs(p["head_tilt"]) < 12.0 and abs(p["dx"]) < 5.0
    for a, b in zip(poses, poses[1:]):                                           # nothing pops between two frames
        for (ua, fa), (ub, fb) in zip(a["arms"], b["arms"]):
            assert abs(ub - ua) < 13.4 and abs(fb - fa) < 13.4                   # 400 degrees a second
        assert abs(b["lean"] - a["lean"]) < 0.6 and abs(b["head_tilt"] - a["head_tilt"]) < 1.6 and abs(b["dx"] - a["dx"]) < 0.4
        assert all(abs(wb - wa) < 11.0 for wa, wb in zip(a["wrist"], b["wrist"]))


def test_pose_is_a_pure_function_of_time():
    perf, g, poses = run(TALKS[1], seed=0.9)
    for i in (400, 3, 250, 100, 250):
        assert perf.pose(i / 30, g)[0] == poses[i]
    other = cg.Performance(seed=0.9, content_side=1)
    other.speak(words_for(TALKS[1]))
    assert other.pose(8.3, g) == perf.pose(8.3, g)
    different = cg.Performance(seed=0.1, content_side=1)
    different.speak(words_for(TALKS[1]))
    assert different.pose(8.3, g) != perf.pose(8.3, g)          # another seed is another person: different blinks, sway and timing


def test_two_handed_gestures_are_not_twins():
    perf = cg.Performance(seed=0.3)
    perf.gesture("open", 2.0, hold=1.0)
    g = vp.Geom()
    t = perf.gestures[0].t0 + 0.45
    l, r = perf.pose(t, g)[0]["arms"]
    assert abs(l[1] - r[1]) > 6.0                               # one hand leads on the way up
    l, r = perf.pose(2.6, g)[0]["arms"]
    assert 6.0 < abs(l[1] - r[1]) < 25.0                        # and they hold at different heights: alike, never a mirror image


def test_idle_life_is_never_frozen_and_never_wild():
    perf = cg.Performance(seed=0.4)
    g = vp.Geom()
    poses = [perf.pose(i / 30, g)[0] for i in range(30 * 30)]
    assert len({round(p["torso_sy"], 4) for p in poses}) > 20   # breathing
    blinks = sum(1 for a, b in zip(poses, poses[1:]) if b["blink"] and not a["blink"])
    assert 4 <= blinks <= 16                                    # 8 to 32 a minute
    assert max(p["dx"] for p in poses) - min(p["dx"] for p in poses) > 2.0      # the weight moves from foot to foot
    assert all(p["feet"] == ((-g.stance, 0.0), (g.stance, 0.0)) for p in poses)  # on planted feet
    assert any(abs(p["look"][0]) > 0.5 for p in poses) and sum(1 for p in poses if abs(p["look"][0]) < 0.2) > 0.6 * len(poses)   # eye darts, but mostly at the viewer


def test_listening_looks_at_the_speaker_and_nods():
    perf = cg.Performance(seed=0.2)
    perf.listen(1.0, 6.0, toward=-1.0, nods=[1.6, 2.0, 2.4, 3.0, 3.6, 4.2, 4.9, 5.4])
    g = vp.Geom()
    p = perf.pose(3.0, g)[0]
    assert p["look"][0] < -2.0 and p["head_tilt"] < 0
    assert perf.pose(8.0, g)[0]["look"][0] > -1.5
    assert 1 <= len(perf.nods) <= 2 and not perf.gestures and all(1.0 < t < 6.0 for t, _ in perf.nods)       # a listener does not gesture
    assert all(at_rest(arm, wr) for arm, wr in zip(p["arms"], p["wrist"]))


def test_enter_leave_and_side_step_without_walking():
    perf = cg.Performance(seed=0.2)
    perf.enter(0.5, from_side=-1, distance=60.0)
    perf.side_step(4.0, 14.0)
    perf.leave(8.0, to_side=1)
    g = vp.Geom()
    assert perf.pose(0.2, g)[1]["alpha"] == 0.0
    p, ex = perf.pose(0.7, g)
    assert -60.0 < ex["x"] < 0 and 0 < ex["alpha"] <= 1 and p["lean"] > 0       # sliding in from the left, leaning into the move
    p, ex = perf.pose(3.0, g)
    assert ex == {"x": 0.0, "alpha": 1.0} and abs(p["dy"]) < 0.05               # settled
    mid = perf.pose(4.2, g)[0]["feet"]
    assert mid[1][0] > g.stance and mid[1][1] > 0 and mid[0] == (-g.stance, 0.0)   # the leading foot is in the air, the other one planted
    p = perf.pose(5.5, g)[0]
    assert p["feet"] == ((-g.stance + 14.0, 0.0), (g.stance + 14.0, 0.0)) and abs(p["dx"] - 14.0 - perf.weight(5.5)) < 1e-6
    for i in range(0, 300):                                                      # at no moment is a leg stretched or squashed visibly, or far from upright
        sk = vp.solve(g, perf.pose(i / 30, g)[0])
        for ang, k in sk["leg"]:
            assert 0.955 < k < 1.03 and abs(ang) < 9.0
    assert perf.pose(8.6, g)[1]["alpha"] < 0.2 and perf.pose(8.6, g)[1]["x"] > 30
