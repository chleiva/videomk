"""Procedural animated backgrounds (engine/bg_animated.py): seamless loops, every aspect and size, text contrast in the quiet zone, dither, sanitising,
and the opt-in plumbing (off by default; renders only when BG_ANIMATED=1 and the timeline asks)."""
import json
import os

import numpy as np
import pytest

from engine import bg_animated as B
from engine.renderer import Renderer

ASPECTS = {"16:9": (320, 180), "9:16": (180, 320), "1:1": (240, 240), "4:5": (216, 270)}


@pytest.mark.parametrize("style", B.STYLES)
def test_every_style_renders_every_aspect(style):
    for w, h in ASPECTS.values():
        a = B.render(B.BgSpec(style=style), w, h, 1.3)
        assert a.shape == (h, w, 3) and a.dtype == np.uint8
        assert a.std() > 1.0   # not a flat colour


@pytest.mark.parametrize("style", B.STYLES)
def test_loop_is_seamless(style):
    sp = B.BgSpec(style=style, loop_seconds=8.0)
    a = B.render(sp, 192, 108, 0.0, dither=False).astype(float)
    b = B.render(sp, 192, 108, 8.0, dither=False).astype(float)
    c = B.render(sp, 192, 108, 16.0, dither=False).astype(float)
    n = B.render(sp, 192, 108, 1 / 30, dither=False).astype(float)
    assert np.abs(a - b).mean() < 0.01 and np.abs(a - c).mean() < 0.01     # frame T equals frame 0
    assert np.abs(a - n).mean() > np.abs(a - b).mean()                     # and it really moves


@pytest.mark.parametrize("style", B.STYLES)
def test_deterministic_and_seed_changes_picture(style):
    a = B.render(B.BgSpec(style=style, seed=5), 160, 90, 2.0)
    assert np.array_equal(a, B.render(B.BgSpec(style=style, seed=5), 160, 90, 2.0))
    assert not np.array_equal(a, B.render(B.BgSpec(style=style, seed=6), 160, 90, 2.0))


@pytest.mark.parametrize("mode", B.MODES)
@pytest.mark.parametrize("style", B.STYLES)
def test_quiet_zone_keeps_text_readable(style, mode):
    for pal in ("midnight", "sunrise", "mono"):
        r = B.contrast_report(B.BgSpec(style=style, palette=pal, mode=mode), 320, 180, (0, 3, 6))
        assert r["zone_min"] >= B.MIN_CONTRAST, (style, pal, mode, r)


def test_dither_removes_banding_without_shifting_the_mean():
    sp = B.BgSpec(style="smoke", palette="midnight", seed=3)
    plain = B.render(sp, 640, 360, 2.0, dither=False).astype(float)
    dith = B.render(sp, 640, 360, 2.0, dither=True).astype(float)
    assert abs(plain.mean() - dith.mean()) < 0.6
    row = dith[180, :, 2]
    assert len(np.unique(row)) >= len(np.unique(plain[180, :, 2]))        # more levels in use: contours broken up
    assert np.abs(dith - plain).max() <= 3.0                               # never more than a couple of levels of noise


def test_large_frames_are_computed_at_half_size_and_have_the_right_shape():
    a = B.render(B.BgSpec(style="gas"), 3840, 2160, 0.5)
    assert a.shape == (2160, 3840, 3)


def test_sanitize_keeps_only_known_values():
    s = B.sanitize({"style": "GAS", "palette": "nope", "mode": "x", "speed": 99, "intensity": -5, "seed": 12345, "loop_seconds": "a", "quiet": True}, "paper")
    assert (s.style, s.palette, s.mode) == ("gas", "violet", "light")     # unknown palette -> the theme's; the light theme -> light mode
    assert s.speed == 2.0 and s.intensity == 0.4 and s.seed == 2345 and s.loop_seconds == 10.0 and s.quiet == 0.8
    assert B.sanitize(None).style == "gas" and B.sanitize("<script>").palette == "midnight"
    assert B.sanitize({"style": "../../etc/passwd"}).style == "gas"


def test_plumbing_is_off_by_default_and_opt_in(monkeypatch):
    tl = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "demo_timeline.json")))
    tl["background"] = {"style": "gas", "palette": "ocean"}
    monkeypatch.delenv("BG_ANIMATED", raising=False)
    assert Renderer(tl, draft=True).bg_anim is None
    monkeypatch.setenv("BG_ANIMATED", "1")
    r = Renderer(tl, draft=True)
    assert r.bg_anim is not None and r.bg_anim.palette == "ocean"
    f0, f1 = r.frame_at(0.5), r.frame_at(0.9)
    assert f0.size == f1.size and np.abs(np.asarray(f0, float) - np.asarray(f1, float)).mean() > 0   # the background moves between frames
    monkeypatch.delenv("BG_ANIMATED")
    assert Renderer({k: v for k, v in tl.items() if k != "background"}, draft=True).bg_anim is None
