"""Motion tags of the layered vector scenes (engine/vector_motion.py) and their hook in engine/vector_scene.py."""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import vector_motion as vm  # noqa: E402


def test_cycles_are_whole_and_at_least_one():
    assert vm.cycles(3.0, 9.0) == 3
    assert vm.cycles(10.0, 4.0) == 1
    assert vm.cycles("bad", 6.0) >= 1


def test_clean_tag_rejects_unknown_and_bad_values():
    assert vm.clean_tag({"type": "teleport"}) is None
    assert vm.clean_tag("rotate") is None
    assert vm.clean_tag({"type": "rotate", "period": 4}) is None          # needs a pivot
    t = vm.clean_tag({"type": "rotate", "pivot": [2, -1], "period": "x", "dir": -3})
    assert t["pivot"] == [1.0, 0.0] and t["period"] == 6.0 and t["dir"] == -1
    w = vm.clean_tag({"type": "wiggle", "pivot": [0.5, 0.5], "deg": 999})
    assert w["deg"] == 45.0
    assert vm.clean_tags("nope") == [] and vm.clean_tags([None, {"type": "bob"}])[0]["type"] == "bob"
    nan = vm.clean_tag({"type": "bob", "amp": float("nan")})
    assert nan["amp"] == 0.004


@pytest.mark.parametrize("tag", [
    {"type": "rotate", "pivot": [0.5, 0.5], "period": 3},
    {"type": "wiggle", "pivot": [0.4, 0.6], "deg": 8, "period": 1.5},
    {"type": "bob", "amp": 0.01, "period": 2},
    {"type": "drift", "vx": 0.2, "mode": "pingpong"},
    {"type": "flicker", "period": 0.7},
    {"type": "twinkle", "period": 1.1, "phase": 0.3},
    {"type": "rise", "amp": 0.1, "period": 4},
])
def test_every_motion_closes_its_loop(tag):
    """the last frame of the scene meets the first: rotation modulo a turn, everything else equal."""
    a = vm.layer_transform([tag], 0.0, 8.0)
    b = vm.layer_transform([tag], 8.0, 8.0)
    assert a is not None and b is not None
    for k in ("dx", "dy", "alpha", "scale"):
        assert a[k] == pytest.approx(b[k], abs=1e-9), k
    assert math.sin(a["rot"]) == pytest.approx(math.sin(b["rot"]), abs=1e-9)
    assert math.cos(a["rot"]) == pytest.approx(math.cos(b["rot"]), abs=1e-9)


def test_rotate_is_constant_speed_and_direction():
    tag = {"type": "rotate", "pivot": [0.5, 0.5], "period": 4, "dir": 1}
    steps = [vm.layer_transform([tag], t / 10, 8.0)["rot"] for t in range(0, 81, 10)]
    d = [b - a for a, b in zip(steps, steps[1:])]
    assert all(x == pytest.approx(d[0]) for x in d) and d[0] > 0
    rev = vm.layer_transform([dict(tag, dir=-1)], 1.0, 8.0)["rot"]
    assert rev < 0


def test_rise_fades_to_nothing_at_the_wrap():
    tag = {"type": "rise", "amp": 0.2, "period": 4}
    assert vm.layer_transform([tag], 0.0, 8.0)["alpha"] == pytest.approx(0.0, abs=1e-9)
    mid = vm.layer_transform([tag], 2.0, 8.0)
    assert mid["alpha"] > 0.9 and mid["dy"] < 0 and mid["scale"] > 1.0


def test_flicker_stays_inside_its_range():
    tag = {"type": "flicker", "min": 0.5, "period": 0.5}
    vals = [vm.layer_transform([tag], t / 40, 6.0)["alpha"] for t in range(0, 241)]
    assert min(vals) >= 0.5 - 1e-9 and max(vals) <= 1.0 + 1e-9 and max(vals) - min(vals) > 0.2


def test_no_tags_means_no_transform():
    assert vm.layer_transform([], 1.0, 5.0) is None
    assert vm.layer_transform([{"type": "nope"}], 1.0, 5.0) is None


def test_affine_identity_matches_the_plain_parallax_map():
    """with no rotation and no shift the tag map equals the (a, 0, c, 0, a, f) map vector_scene.frame uses without tags"""
    W, H, M, RS = 640, 360, 1.12, 1.08
    cw, ch = round(W * M * RS), round(H * M * RS)
    tr = dict(dx=0.0, dy=0.0, rot=0.0, pivot=None, alpha=1.0, scale=1.0)
    s, tx, ty = 1.03, 5.0, -2.0
    coef = vm.affine(tr, W=W, H=H, cw=cw, ch=ch, rs=RS, margin=M, s=s, tx=tx, ty=ty)
    a = RS / s
    cx, cy = cw / 2, ch / 2
    ref = (a, 0, cx - (W / 2 + tx) * a, 0, a, cy - (H / 2 + ty) * a)
    for x, y in zip(coef, ref):
        assert x == pytest.approx(y, abs=1e-9)


def test_affine_rotation_keeps_the_pivot_fixed():
    """a point at the pivot lands on the same raster pixel whatever the angle"""
    W, H, M, RS = 640, 360, 1.12, 1.08
    cw, ch = W * M * RS, H * M * RS      # exact (the engine rounds to whole pixels)
    u, v = 0.3, 0.4
    px, py = W / 2 + (u - 0.5) * W * M, H / 2 + (v - 0.5) * H * M      # the pivot in frame pixels at rest

    def raster_of(th):
        tr = dict(dx=0.0, dy=0.0, rot=th, pivot=(u, v), alpha=1.0, scale=1.0)
        a, b, c, d, e, f = vm.affine(tr, W=W, H=H, cw=cw, ch=ch, rs=RS, margin=M, s=1.0, tx=0.0, ty=0.0)
        return (a * px + b * py + c, d * px + e * py + f)

    r0, r1, r2 = raster_of(0.0), raster_of(0.9), raster_of(-2.0)
    assert r0 == pytest.approx(r1, abs=1e-6) and r0 == pytest.approx(r2, abs=1e-6)
    assert r0 == pytest.approx((u * cw, v * ch), abs=1e-6)             # and it is where the picture says it is


def test_scene_hook_draws_a_tagged_layer(tmp_path):
    """a manifest with tags renders; invalid tags are dropped on load; a layer without tags is unchanged"""
    resvg = pytest.importorskip("resvg_py")      # noqa: F841
    from engine.vector_scene import VectorScene

    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90" viewBox="0 0 160 90"><rect width="160" height="90" fill="#7ac"/></svg>'
    spr = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90" viewBox="0 0 160 90"><rect x="70" y="10" width="20" height="35" fill="#fff"/><rect x="40" y="40" width="80" height="10" fill="#fff"/></svg>'
    (tmp_path / "0.svg").write_text(svg)
    (tmp_path / "1.svg").write_text(spr)
    man = {"layers": [{"file": "0.svg", "z": 0.0}, {"file": "1.svg", "z": 0.5, "tags": [{"type": "rotate", "pivot": [0.5, 0.5], "period": 2}, {"type": "bogus"}]}], "motion": {"push": 0.0, "pan": 0.0}}
    (tmp_path / "manifest.json").write_text(json.dumps(man))
    vs = VectorScene(str(tmp_path), 160, 90)
    assert vs.layers[1]["tags"] == vm.clean_tags([{"type": "rotate", "pivot": [0.5, 0.5], "period": 2}])
    a, b = vs.frame(0.0, 4.0), vs.frame(0.5, 4.0)
    assert a.size == (160, 90) and a.tobytes() != b.tobytes()           # the sprite turned
    c, d = vs.frame(0.0, 4.0), vs.frame(4.0, 4.0)
    assert c.tobytes() == d.tobytes() or sum(abs(x - y) for x, y in zip(c.tobytes(), d.tobytes())) < 160 * 90 * 3 * 0.02    # loop closes
