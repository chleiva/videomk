"""The standing presenter rig (engine/vector_presenter.py): straight legs on planted feet, arms that cannot detach or flip, hand shapes, framing presets."""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from PIL import Image  # noqa: E402

from engine import character_gestures as cg  # noqa: E402
from engine import vector_presenter as vp  # noqa: E402

CAST = ["ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle"]
TAILS = {"fox", "owl", "cat", "parrot", "turtle"}                      # the animals whose sheet has a tail piece


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_arm_ik_keeps_bone_lengths_and_reach():
    a, b = 34.0, 28.0
    s = (30.0, 150.0)
    for side in (-1, 1):
        for i in range(0, 360, 7):
            for r in (0.0, 5.0, 20.0, 45.0, 61.0, 62.0, 90.0, 400.0):
                t = (s[0] + r * math.cos(math.radians(i)), s[1] + r * math.sin(math.radians(i)))
                e, w = vp.arm_ik(s, t, a, b, side)
                assert abs(dist(s, e) - a) < 1e-6 and abs(dist(e, w) - b) < 1e-6          # the bones never stretch: no gap can open at the elbow or the wrist
                assert vp.REACH_MIN * (a + b) - 1e-6 <= dist(s, w) <= vp.REACH_MAX * (a + b) + 1e-6   # never locked straight, never folded flat
                if vp.REACH_MIN * (a + b) <= r <= vp.REACH_MAX * (a + b):
                    assert dist(w, t) < 1e-6


def test_arm_ik_elbow_never_flips():
    a, b = 34.0, 28.0
    s = (0.0, 0.0)
    for side in (-1, 1):
        prev = None
        for i in range(0, 1200):                                # the wrist goes round the shoulder twice while its distance breathes in and out
            ang = math.radians(i * 0.6)
            r = 40.0 + 18.0 * math.sin(i * 0.05)
            t = (r * math.cos(ang), r * math.sin(ang))
            e, w = vp.arm_ik(s, t, a, b, side)
            cross = (e[0] - s[0]) * (w[1] - e[1]) - (e[1] - s[1]) * (w[0] - e[0])
            assert cross * side > 0                             # always bent the same way
            if prev is not None:
                assert dist(e, prev) < 3.0                      # and the elbow moves a little when the wrist moves a little
            prev = e


def test_rest_pose_is_a_person_standing_straight():
    g = vp.Geom()
    sk = vp.solve(g)
    for (ang, k), side in zip(sk["leg"], (-1, 1)):
        assert abs(k - 1.0) < 1e-6                              # legs at their full length: no knee bend, no "sitting"
        assert 0 < ang * side < 6.0                             # feet a little wider than the hips
    assert sk["feet"][0][1] == 0.0 and sk["feet"][1][1] == 0.0
    assert 2 * g.stance < 2 * g.shoulder_x * 1.2                # about hip width, inside the shoulders
    for i, side in enumerate((-1, 1)):
        w, s = sk["wrists"][i], sk["shoulders"][i]
        assert w[1] < s[1] - 0.9 * g.arm and abs(w[0] - s[0]) < 0.2 * g.arm       # arms hang at the sides
    assert sk["shoulders"][0][1] == sk["shoulders"][1][1]


def test_weight_shift_keeps_the_feet_planted_and_the_legs_whole():
    g = vp.Geom()
    for dx in (-4.0, -2.0, 0.0, 2.5, 4.0):
        sk = vp.solve(g, {"dx": dx, "lean": -0.3 * dx})
        assert sk["feet"] == [(-g.stance, 0.0), (g.stance, 0.0)]
        for i, (ang, k) in enumerate(sk["leg"]):
            assert 0.985 < k < 1.015 and abs(ang) < 6.0
            hip = sk["hips"][i]
            foot = (hip[0] + k * g.leg_len * math.sin(math.radians(ang)), hip[1] - k * g.leg_len * math.cos(math.radians(ang)))
            assert dist(foot, sk["feet"][i]) < 1e-6             # the leg ends exactly on its planted foot


def test_shoulders_stay_on_the_torso_at_every_extreme():
    g = vp.Geom()
    A = g.arm
    base = vp.solve(g)
    for hx in (-0.5, 0.0, 0.5, 1.0, 2.0):
        for hy in (-1.5, -0.5, 0.0, 0.6, 1.5):
            sk = vp.solve(g, {"hands": ((hx * A, hy * A), (hx * A, hy * A)), "wrist": (40.0, -40.0)})
            assert sk["shoulders"] == base["shoulders"]         # the arm turns about the centre of the sleeve cap: the cap cannot leave the shoulder
            for i in range(2):
                assert abs(dist(sk["shoulders"][i], sk["elbows"][i]) - g.upper) < 1e-6
                assert abs(dist(sk["elbows"][i], sk["wrists"][i]) - g.fore) < 1e-6
                assert abs(math.hypot(*sk["hand_dir"][i]) - 1.0) < 1e-6
    sk = vp.solve(g, {"lean": 3.0, "shrug": 4.0, "torso_sy": 1.013})
    assert sk["shoulders"][0][1] > base["shoulders"][0][1] and sk["neck"][0] > base["neck"][0]


@pytest.mark.parametrize("cid", CAST)
def test_cast_has_the_presenter_pieces(cid):
    folder = os.path.join(vp.DIR, cid)
    cfg = json.load(open(os.path.join(folder, "presenter.json")))
    assert set(cfg["hands"]) == {"open", "one", "two", "three", "thumb"}
    for h in cfg["hands"].values():
        assert os.path.getsize(os.path.join(folder, h["file"])) > 500 and h["wrist_w"] > 10
    assert ("tail" in cfg) == (cid in TAILS)
    assert sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)) < 1_000_000
    ch = vp.load(cid, 1.2)
    assert ch.shapes == list(vp.HAND_SHAPES)
    g = ch.g
    assert 26 < g.upper < 42 and 16 < g.fore < 36 and 12 < g.hand < 34          # the forearm piece was cut at the wrist, the hand is its own piece
    assert 100 < g.leg_len < 112 and g.hip_x < g.stance < g.shoulder_x
    assert 270 < ch.height < 300
    leg = ch.pieces["leg_r"]
    assert abs((leg.end[1] - leg.pivot[1]) / ch.ppu - g.leg_len) < 0.5          # one fused piece from hip to sole


@pytest.mark.parametrize("cid", CAST)
def test_limbs_stay_attached_in_pixels(cid):
    """Draw extreme poses and look at the picture: the joints are covered by paint (no see-through gap at the shoulder, elbow, wrist or hip)."""
    ch = vp.load(cid, 2.0)
    A = ch.g.arm
    poses = [{}, {"hands": ((0.5 * A, 0.5 * A), (0.9 * A, -0.24 * A)), "hand_shape": ("open", "open"), "wrist": (-20.0, 20.0)},
             {"hands": ((0.64 * A, -0.4 * A), (0.47 * A, 0.13 * A)), "hand_shape": ("open", "three"), "shrug": 4.0, "lean": 2.0, "dx": 4.0},
             {"hands": ((0.3 * A, 0.9 * A), (1.2 * A, 0.0)), "hand_shape": ("thumb", "two"), "dx": -4.0, "feet": ((-ch.g.stance - 6, 2.5), (ch.g.stance, 0.0))}]
    for pose in poses:
        im = Image.new("RGBA", (760, 700), (0, 0, 0, 0))
        sk = ch.draw(im, 380, 660, pose)
        px = im.load()

        def solid(v):
            x, y = round(380 + v[0] * ch.ppu), round(660 - v[1] * ch.ppu)
            return any(px[x + i, y + j][3] > 200 for i in (-1, 0, 1) for j in (-1, 0, 1))

        for i in range(2):
            assert solid(sk["shoulders"][i]) and solid(sk["elbows"][i]) and solid(sk["wrists"][i]) and solid(sk["hips"][i])
            for k in (0.25, 0.5, 0.75):                         # and along the bones
                s, e, w = sk["shoulders"][i], sk["elbows"][i], sk["wrists"][i]
                assert solid((s[0] + (e[0] - s[0]) * k, s[1] + (e[1] - s[1]) * k)) and solid((e[0] + (w[0] - e[0]) * k, e[1] + (w[1] - e[1]) * k))
                h, f = sk["hips"][i], sk["feet"][i]
                assert solid((h[0] + (f[0] - h[0]) * k, h[1] + (f[1] + 3 - h[1]) * k))
        assert solid((sk["waist"][0], sk["waist"][1] + 8)) and solid((sk["neck"][0], sk["neck"][1] + 30))


@pytest.mark.parametrize("cid", CAST)
def test_every_hand_shape_draws_and_differs(cid):
    ch = vp.load(cid, 1.2)
    A = ch.g.arm
    seen = set()
    for shape in vp.HAND_SHAPES:
        im = Image.new("RGBA", (460, 420), (0, 0, 0, 0))
        ch.draw(im, 230, 400, {"hands": (None, (0.47 * A, 0.13 * A)), "hand_shape": ("relaxed", shape)})
        seen.add(im.tobytes())
    assert len(seen) == len(vp.HAND_SHAPES)
    off = Image.new("RGBA", (120, 90), (0, 0, 0, 0))            # a character partly or wholly outside the frame is not an error
    ch.draw(off, -200, 60, {})
    ch.draw(off, 60, 600, {})


@pytest.mark.parametrize("shape", [(1920, 1080), (1080, 1920), (1080, 1080), (1080, 1350)])
@pytest.mark.parametrize("preset", vp.FRAMINGS)
@pytest.mark.parametrize("side", ["left", "right"])
def test_framing_presets(shape, preset, side):
    W, H = shape
    fr = vp.framing(preset, side, W, H)
    g = vp.Geom()
    top = fr["ground"] - 290.0 * fr["ppu"]
    assert 0.02 * H < top < 0.62 * H                            # the head is inside the frame with air above it
    reach = (g.shoulder_x + 0.9 * 60.0 + 20.0) * fr["ppu"]
    assert 0 < fr["x"] < W and (fr["x"] - reach * 0.75 > 0 if side == "left" else fr["x"] + reach * 0.75 < W)    # the outside hand stays (nearly) in frame
    if preset == "full":
        assert fr["ground"] <= H                                # feet on screen
    else:
        assert fr["ground"] > H                                 # legs cut by the frame
        waist = fr["ground"] - (g.hip_h - vp.WAIST_UP) * fr["ppu"]
        assert waist < H                                        # and the waist, where the low gestures happen, is in frame
    x0, y0, x1, y1 = fr["content"]
    assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H and (x1 - x0) * (y1 - y0) > 0.12 * W * H
    if W > H:
        assert (x0 > fr["x"]) if side == "left" else (x1 < fr["x"])     # content beside the presenter
    else:
        assert y1 < fr["ground"] - 180.0 * fr["ppu"]                    # content above the presenter's shoulders
    assert (fr["lift"] > 0) == (preset == "waist_up")


def test_framing_rejects_unknown_preset():
    with pytest.raises(ValueError):
        vp.framing("close_up", "left", 1920, 1080)


def test_performance_poses_draw_on_the_real_rig():
    ch = vp.load("fox", 1.0)
    perf = cg.Performance(seed=0.5, content_side=1, tail=True)
    perf.gesture("wave", 1.0)
    perf.gesture("count", 4.0)
    for t in (0.0, 0.7, 1.2, 2.5, 4.1, 5.0):
        pose, _ = perf.pose(t, ch.g)
        im = Image.new("RGBA", (400, 340), (0, 0, 0, 0))
        ch.draw(im, 200, 330, pose)
        assert im.getbbox() is not None and "tail" in pose


# ----------------------------------------------------------------------------- the home pose must not be mirrored (owner's review: "the arms look swapped")
RELAXED_THUMB = {"ines": -1, "david": 1, "priya": 1, "mateo": -1, "fox": -1, "owl": -1, "bear": -1, "cat": -1, "parrot": 1, "turtle": -1}     # where the thumb is on each original forearm drawing, read by eye
SHEET_THUMB_RIGHT = {"fox"}                 # hand sheets drawn the other way round (thumb of the upright open hand on the right)


def _rest_checks(g):
    sk = vp.solve(g)
    for i, side in enumerate((-1, 1)):
        s, e, w = sk["shoulders"][i], sk["elbows"][i], sk["wrists"][i]
        assert (e[0] - s[0]) * side > 0.05 * g.upper            # the upper arm hangs a little OUT: the elbow is outside the shoulder
        assert (w[0] - e[0]) * side < -0.03 * g.fore            # the forearm comes back IN toward the thigh
        x_line = s[0] + (w[0] - s[0]) * (e[1] - s[1]) / (w[1] - s[1])
        assert (e[0] - x_line) * side > 0.02 * g.arm            # so the elbow is on the OUTER side of the line shoulder -> wrist (tucked in = the other arm's shape)
        assert (w[0] - s[0]) * side > -0.02 * g.arm and w[1] < e[1] < s[1]      # and the hand hangs beside the body, not across it
        assert abs(dist(s, e) - g.upper) < 1e-6 and abs(dist(e, w) - g.fore) < 1e-6
    assert sk["wrists"][0][0] == pytest.approx(-sk["wrists"][1][0]) and sk["elbows"][0][0] == pytest.approx(-sk["elbows"][1][0])   # the two arms mirror each other


def test_rest_pose_elbows_out_forearms_in():
    _rest_checks(vp.Geom())
    assert vp.REST_UPPER > 0 > vp.REST_FORE and cg.REST_WRIST < 0      # and the hand itself curls a little toward the leg


@pytest.mark.parametrize("cid", CAST)
def test_rest_pose_and_hand_sides_per_character(cid):
    ch = vp.load(cid, 2.0)
    _rest_checks(ch.g)
    cfg = json.load(open(os.path.join(vp.DIR, cid, "presenter.json")))
    assert cfg["relaxed_thumb"] == RELAXED_THUMB[cid] and cfg["sheet_thumb"] == ("right" if cid in SHEET_THUMB_RIGHT else "left")
    for s, side in (("l", -1), ("r", 1)):
        assert ch.thumb_x[("relaxed", s)] * side == -1          # at home the thumb is on the BODY side of the hand
        for shape in ("open", "one", "two", "three", "thumb"):
            assert ch.thumb_x[(shape, s)] * side == 1           # palm shapes: thumb on the outer side as stored = toward the head when raised, on top when presenting
    for name in ("fore", "hand_relaxed", "hand_open", "hand_two", "upper"):     # the left pieces are the right pieces mirrored, never the same drawing twice
        r, l = ch.pieces[name + "_r"], ch.pieces[name + "_l"]
        assert l.img.tobytes() == r.img.transpose(Image.FLIP_LEFT_RIGHT).tobytes() and l.pivot[0] == pytest.approx(r.img.width - r.pivot[0])
    # the open hand, measured on the paint: beside the palm the piece reaches further from the wrist line on the thumb side
    import numpy as np

    for s in ("l", "r"):
        pc = ch.pieces["hand_open_" + s]
        al = np.array(pc.img)[..., 3] > 96
        rows = [np.nonzero(al[y])[0] for y in range(int(pc.img.height * 0.15), int(pc.img.height * 0.55))]
        rows = [r for r in rows if r.size]
        left, right = max(pc.pivot[0] - r.min() for r in rows), max(r.max() - pc.pivot[0] for r in rows)
        assert (right - left) * ch.thumb_x[("open", s)] > 0.1 * pc.img.width


def test_presenting_hand_is_thumb_up_and_raised_hand_is_thumb_to_the_head():
    """Follow the thumb side of the stored piece through the pose: it must end up on top of a presenting hand and on the head side of a raised hand, on both arms."""
    ch = vp.load("david", 2.0)
    for i, (s, side) in enumerate((("l", -1), ("r", 1))):
        for kind, want in (("present", (0.0, 1.0)), ("count", (-side * 1.0, 0.0)), ("wave", (-side * 1.0, 0.0))):
            arms = [None, None]
            key, _ = cg.fit_key(kind, True, ch.g)
            arms[i] = (key[0], key[1])
            sk = vp.solve(ch.g, {"arms": tuple(arms)})
            d = sk["hand_dir"][i]                               # the fingers point along d; the piece's +x axis (as stored, hanging) is d turned a quarter turn
            thumb = (-d[1] * ch.thumb_x[("open", s)], d[0] * ch.thumb_x[("open", s)])
            assert thumb[0] * want[0] + thumb[1] * want[1] > 0.5, (s, kind, thumb)


def test_leaving_home_is_continuous_and_the_elbow_never_tucks_in():
    """The older wrist-target way to pose an arm: the elbow still glides (no jump), and whatever the target, the result is inside the joint limits."""
    g = vp.Geom()
    rt = vp.rest_target(g)
    for key in ((0.90 * g.arm, -0.24 * g.arm), (0.50 * g.arm, 0.50 * g.arm), (0.47 * g.arm, 0.13 * g.arm), (0.62 * g.arm, -0.50 * g.arm)):
        prev = None
        for n in range(0, 201):
            h = (rt[0] + (key[0] - rt[0]) * n / 200, rt[1] + (key[1] - rt[1]) * n / 200)
            sk = vp.solve(g, {"hands": (h, h)})
            if prev is not None:
                assert dist(sk["elbows"][1], prev) < 0.035 * g.arm
            prev = sk["elbows"][1]
            for i, side in enumerate((-1, 1)):
                s, e = sk["shoulders"][i], sk["elbows"][i]
                assert math.degrees(math.atan2(side * (e[0] - s[0]), -(e[1] - s[1]))) >= vp.UPPER_MIN - 1e-6      # the upper arm never crosses the chest
                assert abs(dist(s, e) - g.upper) < 1e-6 and abs(dist(e, sk["wrists"][i]) - g.fore) < 1e-6
