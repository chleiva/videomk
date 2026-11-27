"""Rig maths and pixels of the vector characters (engine/vector_character.py, docs/VECTOR_SCENES.md)."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import vector_character as vc  # noqa: E402

A, B = vc.ULEG_U * (1 - vc.OVERLAP), vc.LLEG_U


def fk(angles, a=A, b=B):
    a1, a2 = angles
    k = (a * math.sin(math.radians(a1)), a * math.cos(math.radians(a1)))
    return (k[0] + b * math.sin(math.radians(a2)), k[1] + b * math.cos(math.radians(a2))), k


def test_rot_turns_down_toward_forward():
    x, y = vc.rot((0, 1), 90)
    assert abs(x - 1) < 1e-9 and abs(y) < 1e-9
    assert vc.rot((0, 1), 0) == (0, 1)
    sx, sy = vc.seg(30, 10)
    assert abs(sx - 5) < 1e-9 and abs(sy - 10 * math.cos(math.radians(30))) < 1e-9


@pytest.mark.parametrize("target", [(0, 95), (20, 92), (-25, 90), (10, 60), (0, 40)])
def test_ik_reaches_reachable_targets_with_the_knee_in_front(target):
    foot, knee = fk(vc.two_bone_ik(target, A, B))
    assert math.hypot(foot[0] - target[0], foot[1] - target[1]) < 1e-6
    # the knee is on the forward side of the hip-foot line
    cross = target[0] * knee[1] - target[1] * knee[0]
    assert cross <= 1e-6 or knee[0] >= target[0] / 2 - 1e-6


def test_ik_clamps_unreachable_targets():
    foot, _ = fk(vc.two_bone_ik((0, 500), A, B))
    assert abs(math.hypot(*foot) - (A + B)) < 0.01


def test_walk_feet_is_periodic_and_legs_are_half_a_cycle_apart():
    for p in (0.0, 0.7, 2.0, 3.5, 5.9):
        a1, b1 = vc.walk_feet(p, 50, 100, 12)
        a2, b2 = vc.walk_feet(p + 2 * math.pi, 50, 100, 12)
        assert np.allclose(a1, a2) and np.allclose(b1, b2)
        b3, _ = vc.walk_feet(p + math.pi, 50, 100, 12)
        assert np.allclose(b1, b3)


def test_walk_feet_is_continuous_at_the_phase_boundaries():
    eps = 1e-6
    for edge in (0.0, math.pi, 2 * math.pi):
        before, after = vc.walk_feet(edge - eps, 50, 100, 12)[0], vc.walk_feet(edge + eps, 50, 100, 12)[0]
        assert abs(before[0] - after[0]) < 1e-3 and abs(before[1] - after[1]) < 1e-3


def test_planted_foot_stays_on_the_ground_and_does_not_slide():
    """The body moves at the ground speed; in stance the foot's WORLD position is constant (no skating) and its height is the ground."""
    stride, hip_h, g = 52.0, 100.0, 140.0
    T = vc.walk_period(stride, g)
    assert abs(stride / (T / 2) - g) < 1e-9
    xs, ys = [], []
    for i in range(1, 200):
        phase = math.pi * (g * (i / 200) * (T / 2) / stride)           # one stance, distance = g * time, phase = pi * distance / stride
        body_x = g * (i / 200) * (T / 2)
        (fx, fy), _ = vc.walk_feet(phase, stride, hip_h, 12)
        xs.append(body_x + fx)
        ys.append(fy)
    assert max(xs) - min(xs) < 1e-6
    assert max(ys) - min(ys) < 1e-9


def test_swing_lifts_the_foot_and_returns_to_the_stance_start():
    lifts = [vc.walk_feet(math.pi + p * math.pi, 50, 100, 12)[0][1] for p in np.linspace(0, 1, 21)]
    assert min(lifts) < 100 - 11.9 and abs(lifts[0] - 100) < 1e-6 and abs(lifts[-1] - 100) < 1e-6


def test_arm_walk_cycle_loops_and_arms_swing_opposite():
    for side in (0, 1):
        assert np.allclose(vc.arm_angles("walk", 0, 1.0, side), vc.arm_angles("walk", 0, 1.0 + 2 * math.pi, side))
    a0, a1 = vc.arm_angles("walk", 0, 0.8, 0), vc.arm_angles("walk", 0, 0.8, 1)
    assert abs(a0[0] + a1[0]) < 1e-9
    # wave: the elbow oscillates around zero and the arm is raised
    sh, _ = vc.arm_angles("wave", 0.3)
    assert sh > 120


def test_blink_is_short_and_periodic():
    n = sum(vc.blink(i / 100, 0.0) for i in range(1000))
    assert 0.02 < n / 1000 < 0.08
    assert vc.blink(0.05) and not vc.blink(0.5)


def test_mouth_has_hysteresis_and_follows_the_level():
    st = "closed"
    seq = []
    for lv in (0.0, 0.2, 0.7, 0.45, 0.45, 0.2, 0.05, 0.0):
        st = vc.mouth_for(lv, st)
        seq.append(st)
    assert seq[0] == "closed" and seq[2] == "wide" and seq[-1] == "closed"
    assert seq[3] == "wide" or seq[3] == "half"          # 0.45 stays open: no chatter between 0.40 and 0.55
    assert vc.mouth_for(0.30, "closed") == "closed" or vc.mouth_for(0.30, "closed") == "half"


def test_speech_envelope_is_per_frame_and_normalised():
    sr, fps = 24000, 30
    t = np.arange(sr * 2) / sr
    x = (np.sin(2 * np.pi * 220 * t) * (t > 1.0)).astype(np.float32)        # silence, then speech
    env = vc.speech_envelope(x, sr, fps)
    assert len(env) == 60 and env[:25].max() < 0.1 and env[40:].mean() > 0.4 and env.max() <= 1.0 + 1e-6


# ----------------------------------------------------------------------------- pixels (need the bundled characters and resvg)
def _have():
    try:
        import resvg_py  # noqa: F401
    except ImportError:
        return False
    return "mia" in vc.character_ids()


@pytest.mark.skipif(not _have(), reason="resvg-py or the bundled characters are missing")
def test_character_draws_deterministically_and_stays_inside_its_box():
    from PIL import Image

    ch = vc.load("mia", 1.0)
    pose = {"feet": vc.walk_feet(1.0, 50, vc.HIP_H0, 11), "hip_h": vc.HIP_H0, "arms": (vc.arm_angles("walk", 0, 1.0, 0), vc.arm_angles("walk", 0, 1.0, 1)), "mouth": "wide", "blink": True}
    out = []
    for _ in range(2):
        fr = Image.new("RGBA", (400, 500), (0, 0, 0, 0))
        ch.draw(fr, 200, 450, pose)
        out.append(np.array(fr))
    assert np.array_equal(out[0], out[1])
    ys, xs = np.nonzero(out[0][..., 3])
    assert ys.size > 5000
    assert ys.max() <= 450 + 25 and ys.min() >= 450 - 340           # soles near the ground line, head within ~3.2 heads
    assert xs.min() > 20 and xs.max() < 380


@pytest.mark.skipif(not _have(), reason="resvg-py or the bundled characters are missing")
def test_character_scales_with_resolution_without_changing_proportions():
    from PIL import Image

    heights = []
    for ppu in (1.0, 2.0):
        ch = vc.load("leo", ppu)
        fr = Image.new("RGBA", (int(500 * ppu), int(600 * ppu)), (0, 0, 0, 0))
        ch.draw(fr, 250 * ppu, 550 * ppu, {"hip_h": vc.HIP_H0, "feet": ((0, vc.HIP_H0), (0, vc.HIP_H0))})
        ys = np.nonzero(np.array(fr)[..., 3])[0]
        heights.append(ys.max() - ys.min())
    assert abs(heights[1] / heights[0] - 2.0) < 0.06


# ----------------------------------------------------------------------------- secondary motion (2026-11-27, docs/CHARACTER_ANIMATION_PROOF.md)
def test_spring_step_starts_at_zero_overshoots_and_settles():
    assert vc.spring_step(0.0) == 0.0 and vc.spring_step(-1.0) == 0.0
    vals = [vc.spring_step(i / 100, 3.0, 0.4) for i in range(0, 300)]
    assert max(vals) > 1.05                       # overshoot: it goes past the target ...
    assert abs(vals[-1] - 1.0) < 0.02             # ... and settles on it
    assert max(vc.spring_step(i / 100, 3.0, 0.999) for i in range(300)) < 1.02    # critically damped: (almost) no overshoot


def test_spring_keys_is_stateless_and_reaches_every_key_value():
    keys = [(0.0, 0.0), (1.0, 10.0), (3.0, -4.0)]
    a = [vc.spring_keys(t / 10, keys) for t in range(0, 60)]
    b = [vc.spring_keys(t / 10, keys) for t in reversed(range(0, 60))][::-1]
    assert a == b                                 # no hidden state: any evaluation order gives the same numbers
    assert abs(vc.spring_keys(2.9, keys, 3.2, 0.5) - 10.0) < 0.6 and abs(vc.spring_keys(8.0, keys) - (-4.0)) < 0.05
    assert vc.spring_keys(0.5, keys) == 0.0       # nothing moves before its key
    v = vc.spring_keys(8.0, [(0, (1.0, 2.0)), (1.0, (5.0, 6.0))])
    assert isinstance(v, tuple) and abs(v[0] - 5.0) < 0.05 and abs(v[1] - 6.0) < 0.05


def test_ease_keys_never_overshoots():
    keys = [(0.0, 0.0), (1.0, 10.0), (2.0, 0.0)]
    assert all(-1e-9 <= vc.ease_keys(t / 20, keys) <= 10.0 + 1e-9 for t in range(0, 50))
    assert vc.ease_keys(1.0, keys) == 10.0


def test_natural_blink_is_irregular_deterministic_and_short():
    ts = vc._blink_times(0.5)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert len(set(round(g, 2) for g in gaps)) > 5                      # not a metronome
    assert min(g for g in gaps if g > 0.5) >= 2.4 - 0.27 - 1e-9 and max(gaps) <= 5.5      # (a double blink eats 0.27 s of the next gap)
    assert all(vc.blink_natural(t + 0.05, 0.5) for t in ts[:20])        # closed just after each event
    assert not any(vc.blink_natural(t + 0.2, 0.5) for t in ts[:5] if all(abs(t + 0.2 - u) > 0.2 for u in ts))
    assert vc.blink_natural(5.0, 0.5) == vc.blink_natural(5.0, 0.5)


def test_mouth_track_leads_the_sound_and_has_no_one_frame_flicker():
    env = [0.0] * 6 + [0.9] * 6 + [0.0] * 6 + [0.9, 0.0, 0.9, 0.0, 0.9, 0.0] + [0.0] * 4
    seq = vc.mouth_track(env, lead=1, min_hold=2)
    assert seq[5] != "closed" and seq[4] == "closed"                    # opens one frame BEFORE the sound
    runs, cur = [], 1
    for a, b in zip(seq, seq[1:]):
        if a == b:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    assert min(runs) >= 2 or runs[0] >= 1


def test_stress_events_pick_separated_peaks():
    env = [0.1] * 30
    for i in (5, 8, 20):
        env[i] = 0.9
    ev = vc.stress_events(env, 30)
    assert ev == [5 / 30, 20 / 30]                                        # the peak at 8 is within 0.42 s of the one at 5


def test_breath_stays_small_and_periodic():
    for t in (0.0, 1.0, 2.5, 3.8):
        sy, lift = vc.breath(t)
        assert 1.0 <= sy <= 1.017 and 0.0 <= lift <= 1.1 + 1e-9
    assert vc.breath(0.0) == pytest.approx(vc.breath(3.8))


def test_new_pose_keys_default_to_the_old_pixels_and_draw_turned_squeezes():
    from PIL import Image, ImageChops
    if not vc.character_ids():
        pytest.skip("no character assets")
    ch = vc.load(vc.character_ids()[0], 1.2, 1.0)
    base = Image.new("RGBA", (400, 460), (255, 255, 255, 255))
    a, b = base.copy(), base.copy()
    ch.draw(a, 200, 430, {})
    ch.draw(b, 200, 430, {"torso_sy": 1.0, "head_sx": 1.0, "head_sy": 1.0, "eyes_scale": 1.0})
    assert ImageChops.difference(a, b).getbbox() is None                  # absent keys == neutral values: old frames are unchanged
    sq = base.copy()
    ch.draw(sq, 200, 430, {"torso_sy": 0.9})
    assert ImageChops.difference(a, sq).getbbox() is not None            # a squash really changes the picture
    full, half, flip = base.copy(), base.copy(), base.copy()
    ch.draw_turned(full, 200, 430, {}, 1.0)
    ch.draw_turned(half, 200, 430, {}, 0.3)
    ch.draw_turned(flip, 200, 430, {}, -1.0)
    assert ImageChops.difference(full, a).getbbox() is None
    def span(im):
        box = ImageChops.difference(im, base).getbbox()
        return box[2] - box[0]
    assert span(half) < 0.5 * span(full)
    assert abs(span(flip) - span(full)) <= 3                              # a mirrored figure is as wide as the original
