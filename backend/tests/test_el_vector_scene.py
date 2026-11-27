"""The vector_scene element (prototype, hidden from the director): sanitize, layered parallax motion, resolution independence, determinism, the registry contract."""
import numpy as np
import pytest

from tests.element_utils import changed, render, themes
from engine import vector_scene as vs
from engine.scenes import ELEMENTS

EL = ELEMENTS["vector_scene"]


def test_registered_and_hidden_from_the_director():
    from engine.scenes import registry
    assert EL.hidden is True
    assert "vector_scene" not in registry.docs_by_family()


def test_bundled_scenes_are_there_and_small():
    import os
    ids = vs.scene_ids()
    assert {"forest_path", "seaside", "mountain_cabin"} <= set(ids)
    for sid in ids:
        folder = os.path.join(vs.DIR, sid)
        man = vs.json.load(open(os.path.join(folder, "manifest.json")))
        assert len(man["layers"]) >= 4 and man["layers"][0]["z"] == 0.0
        total = sum(os.path.getsize(os.path.join(folder, l["file"])) for l in man["layers"])
        assert total < 1.5 * 1024 * 1024        # the vector art of a whole scene stays about a megabyte
        zs = [l["z"] for l in man["layers"]]
        assert zs == sorted(zs)                # back to front


def test_sanitize():
    assert EL.sanitize({"scene": " Forest_Path ", "junk": 1}) == {"scene": "forest_path"}
    assert EL.sanitize(EL.sanitize({"scene": "seaside"})) == {"scene": "seaside"}
    for bad in ({}, {"scene": ""}, {"scene": "../etc"}, {"scene": "nope"}, None):
        with pytest.raises(ValueError):
            EL.sanitize(bad)


@pytest.mark.parametrize("scene", ["forest_path", "seaside", "mountain_cabin"])
def test_parallax_moves_the_layers_and_nothing_pops(scene):
    s = vs.load(scene, 480, 270)
    a, b, c = (np.asarray(s.frame(t, 8.0), np.int16) for t in (0.0, 4.0, 8.0))
    assert np.abs(a - c).mean() > 2.0                         # the picture really changes over the scene
    d1 = np.abs(np.asarray(s.frame(2.00, 8.0), np.int16) - np.asarray(s.frame(2.0 + 1 / 30, 8.0), np.int16)).mean()
    assert d1 < 3.0                                           # one frame later it is nearly the same: smooth, no popping
    assert (np.asarray(s.frame(8.0, 8.0)).max(axis=2) > 0).all()   # no black gaps behind the layers even at the end of the push


def test_deterministic():
    s = vs.load("seaside", 320, 180)
    assert np.array_equal(np.asarray(s.frame(3.3, 8.0)), np.asarray(s.frame(3.3, 8.0)))


def test_resolution_independent():
    """Rasterised from the SVG at the size it is shown: the big frame, reduced, matches the small one (no blur from upscaling)."""
    small, big = vs.load("forest_path", 480, 270).frame(3.0, 8.0), vs.load("forest_path", 960, 540).frame(3.0, 8.0)
    ref = big.resize((480, 270))
    assert np.abs(np.asarray(small, np.int16) - np.asarray(ref, np.int16)).mean() < 6.0
    # and the big one has more real detail than an upscaled small one
    up = small.resize((960, 540))
    g = lambda im: np.abs(np.diff(np.asarray(im.convert("L"), np.float32), axis=1)).mean()
    assert g(big) > g(up)


@pytest.mark.parametrize("theme", themes())
def test_element_draws_on_every_theme_and_moves(theme):
    f0 = render("vector_scene", {"scene": "forest_path"}, 0.0, 6.0, theme)
    f1 = render("vector_scene", {"scene": "forest_path"}, 6.0, 6.0, theme)
    assert changed(f0, f1, 12) > 0.3
    assert np.asarray(f0).std() > 20                           # a full picture, not a blank


def test_other_shapes_are_framed_not_broken():
    f = render("vector_scene", {"scene": "seaside"}, 3.0, 6.0, "midnight", aspect="9:16")
    assert f.size[0] < f.size[1] and np.asarray(f).std() > 15
