"""The presenters' arms (docs/PRESENTERS.md "Arms"). The owner's review, third time arms came up: "when the characters are bending their arms ... sometimes they are
bending it in the opposite way, almost like breaking the arms ... the arms just drop immediately ... the still needs to look more natural".

Two kinds of test:
  * the INSTRUMENT (engine/arm_check.py) over the whole matrix: every character x every gesture (each hand, each side of the content, low and raised framing) x every
    ordered pair of gestures (one after the other, and the second cutting into the first) x spoken lines x a listener, and whole conversations through the element
    in every frame shape. Every defect class must count ZERO.
  * PINS: the particular things that were wrong, each stated on its own so that it cannot come back unnoticed.
The code before this work fails nearly all of them (numbers in the doc)."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

pytest.importorskip("resvg_py")

from engine import arm_check as ac  # noqa: E402
from engine import character_gestures as cg  # noqa: E402
from engine import vector_presenter as vp  # noqa: E402

CAST = ("ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle")
TAILS = {"fox", "owl", "cat", "parrot", "turtle"}
KINDS = tuple(cg.KINDS)
GESTURES = tuple(k for k in KINDS if k != "beat")          # (the old rig had no table of two-handed gestures: TWO_HANDED is read where it is used)


def maker(cid):
    def make(seed, content_side, lift):
        try:
            return cg.Performance(seed=seed, content_side=content_side, tail=cid in TAILS, lift=lift, who=cid)
        except TypeError:                          # the rig before this work (to run this file against it)
            return cg.Performance(seed=seed, content_side=content_side, tail=cid in TAILS, lift=lift)
    return make


def geom(cid):
    return vp.load(cid, ac.GEOM_PPU).g


def tracked(perf, g, t0, t1):
    def pose_at(t):
        pose, _ = perf.pose(t, g)
        return vp.solve(g, pose), pose
    return ac.track(pose_at, t0, t1)


def active(perf):
    def f(t):
        if any(x.t0 - 0.1 <= t <= x.t1 + 0.6 for x in perf.gestures) or any(abs(t - b[0]) < 0.7 for b in perf.beats):
            return True
        return hasattr(perf, "folded") and (0.001 < perf.folded(t, 0) < 0.999 or 0.001 < perf.folded(t, 1) < 0.999)
    return f


# ----------------------------------------------------------------------------- the instrument over the whole matrix
@pytest.mark.parametrize("cid", CAST)
def test_instrument_counts_zero_over_the_whole_matrix(cid):
    ch = vp.load(cid, ac.GEOM_PPU)
    g = ch.g
    total, cases = {}, 0
    for group, name, perf, t0, t1 in ac.scenarios(KINDS, maker(cid), overlap=True):
        res = ac.check(tracked(perf, g, t0, t1), g, active=active(perf), head_w=ch.hw)
        bad = {k: res[k] for k in ac.CLASSES if res[k]}
        assert not bad, (cid, name, bad, {k: v[:5] for k, v in res["detail"].items() if v}, res["peak"])
        ac.add(total, res)
        cases += 1
    assert cases > 300 and total["frames"] > 60000
    pk = total["peak"]
    assert pk["speed"] <= ac.SPEED_MAX and pk["accel"] <= ac.ACCEL_MAX and pk["drop"] <= ac.DROP_MAX
    assert pk["upper_min"] >= ac.TUCK_MIN and ac.BEND_MIN <= pk["bend_min"] and pk["bend_max"] <= ac.BEND_MAX + 0.01


@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1", "4:5"])
@pytest.mark.parametrize("cast", [["fox", "bear"], ["bear", "fox"], ["owl"], ["ines"], ["cat", "parrot", "turtle"], ["david", "priya"], ["mateo", "ines", "priya"]], ids="+".join)
def test_instrument_counts_zero_in_whole_scenes(cast, aspect, monkeypatch):
    """Through the element: the layout's room beside each figure (the card's text, the board, the neighbours), speaker and listener on either side, and the CUTS
    between the scenes of a conversation (a pose that differs across a cut is a discontinuity)."""
    monkeypatch.setenv("PRESENTERS", "1")
    from engine.scenes.elements import presenter as el

    el.release()
    rows = ac.scene_tracks(ac.conversation(cast), aspect)
    assert set(rows) == set(cast)
    for cid, rec in rows.items():
        res = rec["result"]
        bad = {k: res[k] for k in ac.CLASSES if res[k]}
        assert not bad, (cid, bad, {k: v[:5] for k, v in res["detail"].items() if v}, res["peak"])
        assert res["peak"]["cut_jump"] < 2.0 and len(rec["cuts"]) == 4
    el.release()


def test_the_instrument_sees_each_defect():
    """The instrument is only worth its zeros if it counts the defects when they are there: one made-up arm track per class."""
    g = vp.Geom()

    def run(arm_at, n=60, **kw):
        def pose_at(t):
            pose = {"arms": (arm_at(t, 0), arm_at(t, 1)), "wrist": (0.0, 0.0)}
            return vp.solve(g, pose), pose
        return ac.check(ac.track(pose_at, 0.0, n / 30.0), g, **kw)

    still = run(lambda t, i: (7.0, -4.0), n=120, active=lambda t: False)
    assert still["dead"] > 0 and still["wrong_way"] == 0 and still["discontinuity"] == 0
    assert run(lambda t, i: (2.0, 70.0))["detail"]["wiper"]                       # forearm out sideways from a hanging upper arm
    assert not run(lambda t, i: (20.0, 70.0))["detail"]["wiper"]                  # the same forearm with the elbow out: an arm
    assert run(lambda t, i: (60.0, 30.0 + 200.0 * t))["detail"]["flip"]           # through straight while raised
    assert run(lambda t, i: (10.0, 20.0 + (150.0 if t > 1.0 else 0.0)))["detail"]["speed"]     # a pop
    assert run(lambda t, i: (40.0, 150.0 - 500.0 * max(0.0, t - 1.0) ** 2 * 3))["detail"]["drop"]      # let go
    assert run(lambda t, i: (10.0, 20.0 + 100.0 * t))["twin"] > 0                 # both arms the same, moving
    assert run(lambda t, i: (10.0, 20.0 + 100.0 * t + 8.0 * i))["twin"] == 0
    assert run(lambda t, i: (2.0, -85.0), n=10)["detail"]["midline"]              # a hand across the body's centre line
    assert not run(lambda t, i: (2.0, -60.0), n=10)["detail"]["midline"]
    assert run(lambda t, i: (10.0, 20.0), n=10, keep_out=lambda p: p[1] < 130.0)["detail"]["keep_out"]
    assert run(lambda t, i: (120.0, 230.0), n=10)["detail"]["face"]                # a hand over the face
    # a rig that tucks the elbow in or stretches a bone is seen too (skeletons given directly)
    sk = vp.solve(g, {"arms": ((10.0, 20.0), (10.0, 20.0))})
    bad = dict(sk, elbows=[(sk["shoulders"][0][0] + 12.0, sk["shoulders"][0][1] - 30.0), sk["elbows"][1]])
    res = ac.check(ac.track(lambda t: (bad, {}), 0.0, 0.2), g)
    assert res["detail"]["tucked"] and res["stretch"] > 0


def test_the_rig_and_the_instrument_state_the_same_elbow_rule():
    for f in range(-120, 181, 3):
        assert ac.elbow_out(float(f)) - ac.WIPER_TOL + 0.5 <= vp.elbow_need(float(f)) <= ac.elbow_out(float(f)) + 6.0, f     # the rig asks at least what the instrument checks
    assert (vp.UPPER_MIN, vp.BEND_MIN, vp.BEND_MAX) == (ac.TUCK_MIN, ac.BEND_MIN, ac.BEND_MAX) and vp.FLEX_MAX <= ac.FLEX_MAX


# ----------------------------------------------------------------------------- pins: the rig
def test_the_rig_cannot_draw_a_wrong_arm():
    """Whatever angles or wrist target it is given: the upper arm never crosses the chest, the elbow stays inside its range, the bones keep their length."""
    g = vp.Geom()
    for up in range(-90, 181, 15):
        for fo in range(-270, 361, 15):
            for i, side in enumerate((-1, 1)):
                arms = [None, None]
                arms[i] = (float(up), float(fo))
                sk = vp.solve(g, {"arms": tuple(arms), "wrist": (90.0, -90.0)})
                a = ac.arm_state(sk, i)
                assert vp.UPPER_MIN - 1e-6 <= a["upper"] <= vp.UPPER_MAX + 1e-6 and vp.BEND_MIN - 1e-6 <= a["bend"] <= vp.BEND_MAX + 1e-6, (up, fo, a)
                assert abs(a["len_u"] - g.upper) < 1e-9 and abs(a["len_f"] - g.fore) < 1e-9 and abs(a["flex"]) <= vp.FLEX_MAX + 1e-6
    for x in range(-60, 91, 10):
        for y in range(-80, 81, 10):
            sk = vp.solve(g, {"hands": ((float(x), float(y)), (float(x), float(y)))})
            for i in (0, 1):
                a = ac.arm_state(sk, i)
                assert a["upper"] >= vp.UPPER_MIN - 1e-6 and vp.BEND_MIN - 1e-6 <= a["bend"] <= vp.BEND_MAX + 1e-6 and abs(a["len_f"] - g.fore) < 1e-9


def test_both_arms_are_mirror_images_of_one_rule():
    """The same angles on the left and on the right arm give mirrored skeletons: no arm is the other side's arm."""
    g = geom("bear")
    for up, fo in ((7.0, -4.0), (15.0, 116.0), (46.0, 176.0), (5.0, -80.0)):
        sk = vp.solve(g, {"arms": ((up, fo), (up, fo))})
        for key in ("elbows", "wrists"):
            assert sk[key][0][0] == pytest.approx(-sk[key][1][0]) and sk[key][0][1] == pytest.approx(sk[key][1][1])
        assert sk["elbows"][1][0] > sk["shoulders"][1][0] and sk["elbows"][0][0] < sk["shoulders"][0][0]      # each elbow outside its own shoulder


def test_forearm_is_drawn_over_the_upper_arm_and_hands_over_the_body():
    """Draw order, on the paint: a hand held in front of the belly is visible (not behind the torso), and the forearm covers the upper arm at the elbow."""
    from PIL import Image

    ch = vp.load("bear", 1.0)
    order = []
    orig = ch._put

    def spy(frame, piece, pos, angle, sx=1.0, sy=1.0):
        order.append(next(k for k, v in ch.pieces.items() if v is piece))
        return orig(frame, piece, pos, angle, sx, sy)

    ch._put = spy
    try:
        ch.draw(Image.new("RGBA", (400, 400), (0, 0, 0, 0)), 200, 380, {"arms": ((3.0, -70.0), (3.0, -70.0))})
    finally:
        ch._put = orig
    for s in ("l", "r"):
        assert order.index("torso") < order.index("upper_" + s) < order.index("fore_" + s) and order.index("head") < order.index("hand_relaxed_" + s)


# ----------------------------------------------------------------------------- pins: the way up, the hold, the way home
@pytest.mark.parametrize("cid", ["ines", "fox", "bear", "turtle"])
@pytest.mark.parametrize("kind", GESTURES)
def test_the_elbow_goes_out_with_the_forearm_and_never_into_the_body(cid, kind):
    """What read as a broken arm: on its way up the forearm swung out sideways from an elbow pressed into the ribs (the upper arm reached 35 degrees INTO the chest)."""
    g = geom(cid)
    perf = maker(cid)(0.37, 1, 0.14)
    perf.gesture(kind, 1.3, 1.0)
    for f in tracked(perf, g, 0.0, 4.8):
        for a in f["arms"]:
            assert a["upper"] >= 0.0, (f["t"], a["upper"])                                    # never tucked in
            assert a["upper"] >= ac.elbow_out(a["fore"]) - ac.WIPER_TOL, (f["t"], a)         # and out as far as the forearm asks


@pytest.mark.parametrize("kind", GESTURES)
def test_the_way_home_is_a_return_not_a_drop(kind):
    """ "It feels like the arms just drop immediately": the return took 0.6 s and the wrist fell at 5 arm lengths a second (a limp arm does 7)."""
    g = geom("ines")
    perf = maker("ines")(0.37, 1, 0.14)
    perf.gesture(kind, 1.3, 1.0)
    x = perf.gestures[0]
    fr = tracked(perf, g, 0.0, x.t1 + 2.0)
    away = [f["t"] for f in fr if f["t"] > x.hold_end and max(abs(a["fore"] - (-4.0)) for a in f["arms"]) > 14.0]
    assert away and away[-1] - x.hold_end >= 0.50                                             # the arm is still well on its way half a second after it let go
    falls = [-(b["arms"][i]["wy"] - a["arms"][i]["wy"]) * 30 / g.arm for a, b in zip(fr, fr[1:]) for i in (0, 1)]
    assert max(falls) <= ac.DROP_MAX
    # it slows into rest: the last third of the way down is slower than the middle third
    i = 0 if (x.hand == "l" or (x.hand == "both" and x.lead == "l")) else 1
    down = [f["arms"][i]["fore"] for f in fr if x.hold_end <= f["t"] <= x.t1 + 0.3]
    hi, lo = down[0], min(down)
    t_mid = sum(1 for v in down if lo + (hi - lo) / 3 < v <= lo + 2 * (hi - lo) / 3)
    t_end = sum(1 for v in down[: down.index(lo) + 1] if v <= lo + (hi - lo) / 3)
    assert t_end > t_mid
    # and settles: a hair past rest and back, never a bounce
    after = [f["arms"][i]["fore"] for f in fr if f["t"] >= x.t1]
    assert max(after) - min(after) < 9.0


def test_the_stroke_lands_on_the_word_then_holds():
    w = ac.fake_words("We tried it once. Now look at this number on the screen, please.")
    g = geom("david")
    perf = maker("david")(0.2, 1, 0.14)
    perf.speak(w, None, w[-1][2])
    x = next(q for q in perf.gestures if q.kind == "present")
    word = next(a for (t, a, b) in w if t.strip(".,").lower() == "look")
    assert 0.0 <= word - x.stroke <= 0.12                                                     # on the word, a hair before, never after
    i = 1 if x.hand == "r" else 0
    key = perf._arm_key(x, x.hand, g)[0]
    at = lambda t: perf.arm(t, i, g)                                                          # noqa: E731
    assert abs(at(x.stroke)[1] - key[1]) < 4.0                                               # there on the stroke
    assert all(abs(at(x.stroke + k / 30)[1] - key[1]) < 9.0 for k in range(int((x.hold_end - x.stroke) * 30)))     # and held (a moving hold, a small overshoot)
    assert len({round(at(x.stroke + 0.3 + k / 30)[1], 2) for k in range(8)}) > 4              # the hold is alive


@pytest.mark.parametrize("a,b", [("open", "count"), ("count", "present"), ("wave", "open"), ("present", "thumb"), ("shrug", "wave")])
def test_an_interrupted_gesture_blends_from_where_it_is_never_by_way_of_rest(a, b):
    g = geom("priya")
    perf = maker("priya")(0.61, 1, 0.14)
    perf.gesture(a, 1.3, 0.9, "r" if a not in cg.TWO_HANDED else None)
    ga = perf.gestures[0]
    perf.gesture(b, ga.stroke + 0.55, 0.9, "r" if b not in cg.TWO_HANDED else None, 1 if b == "present" else 0)
    gb = perf.gestures[1]
    assert gb.t0 < ga.t1                                                                      # the second one starts while the first is still up
    ka, kb = perf._arm_key(ga, "r", g)[0][1], perf._arm_key(gb, "r", g)[0][1]
    lo = min(ka, kb)
    path = [perf.arm(ga.stroke + k / 30, 1, g)[1] for k in range(int((gb.stroke - ga.stroke) * 30) + 1)]
    assert min(path) > lo - 16.0, (min(path), ka, kb)                                         # the forearm stays between the two poses: it does not dip toward rest
    res = ac.check(tracked(perf, g, 0.0, gb.t1 + 1.5), g)
    assert res["wrong_way"] == 0 and res["discontinuity"] == 0


def test_gestures_close_together_go_straight_on_and_far_apart_rest_between():
    g = geom("ines")
    near = maker("ines")(0.2, 1, 0.0)
    near.gesture("open", 1.3, 0.8)
    near.gesture("compare", near.gestures[0].t1 + 0.5, 0.8)                                   # the next would start half a second after the hands are home
    far = maker("ines")(0.2, 1, 0.0)
    far.gesture("open", 1.3, 0.8)
    far.gesture("compare", far.gestures[0].t1 + 2.5, 0.8)
    for perf, rests in ((near, False), (far, True)):
        a, b = perf.gestures
        low = min(perf.arm(a.stroke + k / 30, 1, g)[1] for k in range(int((b.stroke - a.stroke) * 30)))
        assert (low < 10.0) == rests


def test_two_handed_gestures_are_never_mirror_images():
    for cid in ("ines", "bear", "fox"):
        g = geom(cid)
        for kind in cg.TWO_HANDED:
            perf = maker(cid)(0.37, 1, 0.14)
            perf.gesture(kind, 1.3, 1.6)
            x = perf.gestures[0]
            l, r = perf.arm(x.stroke + 1.3, 0, g), perf.arm(x.stroke + 1.3, 1, g)
            assert abs(l[1] - r[1]) > 6.0                                                     # held at different heights
            starts = []
            for i in (0, 1):
                starts.append(next(k for k in range(200) if abs(perf.arm(k / 30, i, g)[1] - perf.arm(0.0, i, g)[1]) > 6.0))
            assert starts[0] != starts[1]                                                     # and one hand leads


# ----------------------------------------------------------------------------- pins: rest
def test_rest_is_alive_asymmetric_and_calm():
    """ "The still needs to look more natural": at rest the arms were two straight sticks, the same on both sides, that did not move (0.2 degrees in a minute)."""
    for cid in CAST:
        g = geom(cid)
        perf = maker(cid)(0.3, 1, 0.14)
        fr = tracked(perf, g, 0.0, 60.0)
        res = ac.check(fr, g, active=lambda t: False)
        assert res["dead"] == 0 and res["discontinuity"] == 0 and res["wrong_way"] == 0, (cid, res["detail"], res["peak"])
        lo, hi = res["peak"]["rest_move"]
        assert lo >= ac.DEAD_DEG and hi <= ac.FIDGET_DEG
        apart = sum(1 for f in fr if abs(f["arms"][0]["fore"] - f["arms"][1]["fore"]) > 2.0)
        assert apart > 0.6 * len(fr), cid                                                     # the two arms are not the same most of the time
        for f in fr:
            for a in f["arms"]:
                assert 3.0 < a["upper"] < 13.0 and -19.0 < a["fore"] < 7.0                    # relaxed at the sides, elbows a little out, never a raised or flared arm
        speeds = [abs(b["arms"][i]["fore"] - a["arms"][i]["fore"]) * 30 for a, b in zip(fr, fr[1:]) for i in (0, 1)]
        assert max(speeds) < 16.0                                                             # degrees a second: a settle, not a fidget


def test_the_home_pose_is_still_the_pinned_one():
    assert cg.REST_POSES[0] == (vp.REST_UPPER, vp.REST_FORE, cg.REST_WRIST) and all(u > 0 and abs(f - u) < 22 for u, f, _ in cg.REST_POSES)


@pytest.mark.parametrize("cid", sorted(getattr(cg, "FOLDERS", CAST)))
def test_a_listener_brings_its_hands_together_and_apart_again(cid):
    g = geom(cid)
    perf = maker(cid)(0.3, -1, 0.14)
    perf.limit = 9.0
    perf.listen(0.2, 8.4, 1.0, [2.0, 5.0])
    fr = tracked(perf, g, 0.0, 9.0)
    mid = fr[150]
    gap = abs(mid["arms"][0]["wx"] - mid["arms"][1]["wx"])
    assert gap < 2.0 * g.hand + 0.3 * g.shoulder_x and all(a["fore"] < -40.0 for a in mid["arms"])      # the hands meet (finger tips at least) in front of the belly
    assert all(a["wy"] - a["sy"] < -0.35 * g.arm for a in mid["arms"])                        # at navel height, not on the chest
    for f in (fr[0], fr[-1]):
        assert all(-19.0 < a["fore"] < 7.0 for a in f["arms"])                                # the shot starts and ends at the sides: the next shot starts there too
    res = ac.check(fr, g, active=active(perf))
    assert not any(res[k] for k in ac.CLASSES), (res["detail"], res["peak"])
    kept = maker(cid)(0.3, -1, 0.14)
    kept.limit, kept.fold = 9.0, (True, True)                                                 # listened before and listens after: never lets go
    kept.listen(0.2, 8.4, 1.0, [])
    assert all(kept.folded(t, i) == 1.0 for t in (0.0, 4.0, 9.0, 9.3) for i in (0, 1))


def test_the_fox_keeps_its_hands_at_its_sides():
    assert "fox" not in cg.FOLDERS
    perf = maker("fox")(0.3, -1, 0.14)
    perf.limit = 9.0
    perf.listen(0.2, 8.4, 1.0, [])
    assert perf.folded(4.0, 0) == 0.0


# ----------------------------------------------------------------------------- pins: across a cut, and beside the card
def test_nothing_jumps_at_a_cut_and_the_outgoing_scene_matches_under_the_crossfade(monkeypatch):
    monkeypatch.setenv("PRESENTERS", "1")
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx
    from engine.scenes.elements import presenter as el

    el.release()
    scenes = ac.conversation(["owl", "bear"])
    ctx = SceneCtx(frame=Frame.parse("16:9", "720p"), captions=True)
    for a, b in zip(scenes, scenes[1:]):
        assert b["props"]["at"] == pytest.approx(a["props"]["at"] + a["duration"], abs=1e-3)
        assert b["props"]["prev_speaker"] == a["props"]["character"] and a["props"]["next_speaker"] == b["props"]["character"]
        la, lb = el.layout(a["props"], ctx), el.layout(b["props"], ctx)
        for fa, fb in zip(la["figures"], lb["figures"]):
            g = geom(fa["character"])
            pa = el.performance(a["props"], a["duration"], fa["lift"], "left", fa["character"], fa["slot"], fa["toward"], fa["content_side"])
            pb = el.performance(b["props"], b["duration"], fb["lift"], "left", fb["character"], fb["slot"], fb["toward"], fb["content_side"])
            for k in range(0, 13):                              # the 0.4 s crossfade: the outgoing scene runs on past its end while the new one fades in
                qa, qb = pa.pose(a["duration"] + k / 30, g)[0], pb.pose(k / 30, g)[0]
                for (ua, fa_), (ub, fb_) in zip(qa["arms"], qb["arms"]):
                    assert abs(ua - ub) < 1.5 and abs(fa_ - fb_) < 2.5, (fa["character"], k, qa["arms"], qb["arms"])
                assert abs(qa["dx"] - qb["dx"]) < 0.05 and abs(qa["torso_sy"] - qb["torso_sy"]) < 1e-4      # the weight and the breath go on
    el.release()


def test_every_gesture_is_home_before_the_scene_ends():
    w = ac.fake_words("This is very important for everyone! Thanks, goodbye!")
    end = w[-1][2] + 0.55
    g = geom("ines")
    perf = cg.Performance(seed=0.4, content_side=1, who="ines", limit=end)
    perf.speak(w, None, w[-1][2])
    assert all(x.t1 <= end for x in perf.gestures)
    for i in (0, 1):
        up, fo, fl, shape, away = perf.arm(end, i, g)
        assert -19.0 < fo < 7.0 and shape == "relaxed"


def test_hands_fold_up_beside_a_card_and_come_in_front_of_the_body_where_there_is_no_room():
    g = geom("ines")
    reach = lambda key: g.upper * math.sin(math.radians(key[0])) + (g.fore + g.reach) * math.sin(math.radians(min(180.0, key[1] + max(0.0, key[2]))))     # noqa: E731
    free, _ = cg.fit_key("present", True, g)
    for room in (80.0, 66.0, 50.0, 36.0):
        key, _ = cg.fit_key("present", True, g, room, 90.0)
        assert reach(key) <= room + 0.5 and key[1] >= free[1]                                 # the forearm folds up until the whole hand fits
    assert 35.0 < cg.path_need(g) < 70.0 and cg.outward(40.0, 90.0, g) and not cg.outward(40.0, 30.0, g) and not cg.outward(20.0, 90.0, g)
    for cid in CAST:                                                                          # no room beside the body: the same gesture in front of it
        gg = geom(cid)
        for kind in GESTURES:
            (up, fo, fl), shape = cg.fit_key(kind, True, gg, 20.0, 20.0)
            assert fo < -60.0 and 0.0 < up <= 24.0 and vp.BEND_MIN < fo - up, (cid, kind)     # elbow at the side, forearm up across the body
            sk = vp.solve(gg, {"arms": ((7.0, -4.0), (up, fo)), "wrist": (0.0, fl)})
            w, hd = sk["wrists"][1], sk["hand_dir"][1]
            tip = (w[0] + hd[0] * gg.reach, w[1] + hd[1] * gg.reach)
            assert w[0] > 2.0 and tip[1] < sk["neck"][1] - 4.0, (cid, kind, w, tip)           # the wrist on its own side of the body, the finger tips under the chin
            assert sk["elbows"][1][0] - sk["shoulders"][1][0] <= 18.0                         # and the elbow inside the little room there is
    # a two-handed gesture without room for both hands is made by one: two hands crossed on the chest say something else
    both = cg.Performance(seed=0.3, content_side=1, who="ines", room=(20.0, 20.0), clear=(20.0, 20.0), geom=g)
    both.gesture("open", 1.5, 1.0)
    x = both.gestures[0]
    lead, other = (0, 1) if x.lead == "l" else (1, 0)
    assert both.arm(x.stroke + 0.3, lead, g)[1] < -60.0 and -19.0 < both.arm(x.stroke + 0.3, other, g)[1] < 7.0
    half = cg.Performance(seed=0.3, content_side=1, who="ines", room=(80.0, 20.0), clear=(90.0, 20.0), geom=g)
    half.gesture("open", 1.5, 1.0)
    assert half.arm(half.gestures[0].stroke + 0.3, 0, g)[1] > 90.0 and -19.0 < half.arm(half.gestures[0].stroke + 0.3, 1, g)[1] < 7.0     # the arm with room makes it alone
    half.gesture("count", 6.0, 1.0, "r")
    assert half.gestures[-1].hand == "l"                                                      # and a count goes to the hand that has the room


def test_gestures_are_not_on_every_sentence_and_the_plan_is_deterministic():
    text = " ".join(ac.LINES[k] for k in ("en_greet", "en_plain"))
    w = ac.fake_words(text)
    plans = []
    for _ in range(2):
        perf = cg.Performance(seed=0.42, content_side=1, who="owl")
        perf.speak(w, None, w[-1][2])
        plans.append([x.as_tuple() for x in perf.gestures])
    assert plans[0] == plans[1]
    n_sent = len(cg.sentences(w))
    total = w[-1][2] - w[0][1]
    assert 2 <= len(plans[0]) < n_sent and len(plans[0]) <= math.ceil(cg.MAX_PER_MINUTE * total / 60.0)
    assert len({p[0] for p in plans[0]}) >= 2                                                 # variety
