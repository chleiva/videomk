"""Cartoon catalog: object-aware depth (no torn towers), the tear check, sprite cutting and the 'when to use' policy (docs/VECTOR_CATALOG.md)."""
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from common import vector_catalog as vc  # noqa: E402


# ---------------------------------------------------------------- policy
def test_suits_follows_use_for_and_avoid_for():
    s = {"use_for": "kids, education, explainer, tech", "avoid_for": "news, current events"}
    assert vc.suits(s, "kids") and vc.suits(s, "Education") and vc.suits(s, "tech")
    assert not vc.suits(s, "news")                 # avoided
    assert not vc.suits(s, "finance")              # not listed: the cartoon look is opt-in
    assert not vc.suits(s, "") and not vc.suits({}, "kids")
    both = {"use_for": "explainer", "avoid_for": "explainer"}
    assert not vc.suits(both, "explainer")         # avoid wins


def test_suits_matches_a_word_of_a_multiword_entry():
    s = {"use_for": "business-light, current explainer", "avoid_for": "current events"}
    assert vc.suits(s, "business-light")
    assert not vc.suits(s, "current")              # 'current' is part of the avoided phrase


# ---------------------------------------------------------------- object-aware depth
def test_merge_objects_keeps_one_depth_per_object_but_not_per_ground_plane():
    vo = pytest.importorskip("vector_objects")
    pytest.importorskip("scipy")
    # a 60x40 picture: a 'tower' made of three regions side by side whose depths ramp slowly (0.40, 0.46, 0.52), and a far hill (0.1) next to it
    comp = np.zeros((40, 60), np.int32)
    comp[:, 0:10] = 1      # hill
    comp[:, 10:20] = 2     # tower part A
    comp[:, 20:30] = 3     # tower part B
    comp[:, 30:40] = 4     # tower part C
    comp[:, 40:60] = 5     # near ground
    depth = np.array([0.0, 0.10, 0.40, 0.46, 0.52, 0.90], np.float32)
    sizes = np.array([0, 400, 400, 400, 400, 800], np.float32)
    lut = vo.merge_objects(comp, depth, sizes, np.zeros(comp.shape, bool))
    assert lut[2] == lut[3] == lut[4]              # the tower moves as one piece
    assert lut[1] != lut[2] and lut[5] != lut[4]   # a big depth jump is a real silhouette: still separate layers
    assert vo.RANGE_CAP < 0.4


def test_merge_objects_range_cap_stops_a_ramp_from_chaining():
    vo = pytest.importorskip("vector_objects")
    pytest.importorskip("scipy")
    n = 8
    comp = np.zeros((10, 10 * n), np.int32)
    for i in range(n):
        comp[:, i * 10:(i + 1) * 10] = i + 1
    depth = np.array([0.0] + [0.1 * i for i in range(n)], np.float32)     # a ground plane ramping 0 .. 0.7 in steps of 0.1
    lut = vo.merge_objects(comp, depth, np.array([0] + [100] * n, np.float32), np.zeros(comp.shape, bool))
    assert len(set(lut[1:].tolist())) >= 2         # not one single band


# ---------------------------------------------------------------- tear check
def _svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="576" viewBox="0 0 1024 576">{body}</svg>'


def _package(tmp_path, near_layer_covers_tower_top_only):
    """a white tower with a dark outline: either whole in the near layer (clean) or cut across by the layer boundary (torn)"""
    tower = '<rect x="480" y="100" width="64" height="400" fill="#f5f0e6" stroke="#223" stroke-width="8"/>'
    far = _svg('<rect width="1024" height="576" fill="#6bf"/>' + (tower if near_layer_covers_tower_top_only else ""))
    if near_layer_covers_tower_top_only:     # the lower half of the tower sits in the far layer, the upper half in the near one: the boundary runs across it at y = 300
        near = _svg('<clipPath id="c"><rect x="0" y="0" width="1024" height="300"/></clipPath><g clip-path="url(#c)">' + tower + "</g>")
    else:
        near = _svg(tower)
    (tmp_path / "0_sky.svg").write_text(far)
    (tmp_path / "1_layer1.svg").write_text(near)
    (tmp_path / "manifest.json").write_text(json.dumps({"layers": [{"file": "0_sky.svg", "name": "sky", "z": 0.0}, {"file": "1_layer1.svg", "name": "layer1", "z": 0.5}]}))
    return str(tmp_path)


def test_tear_check_flags_a_cut_through_an_object_and_passes_a_clean_silhouette(tmp_path):
    pytest.importorskip("resvg_py")
    pytest.importorskip("scipy")
    import vector_tear_check as tc
    clean, _ = tc.analyse(_package(tmp_path / "a", False) if (tmp_path / "a").mkdir() is None else "")
    torn, _ = tc.analyse(_package(tmp_path / "b", True) if (tmp_path / "b").mkdir() is None else "")
    assert clean["tears"] == 0
    assert torn["tears"] >= 1


# ---------------------------------------------------------------- sprites
def test_cut_region_takes_only_regions_closed_inside_the_box():
    vsp = pytest.importorskip("vector_sprites")
    pytest.importorskip("cv2")
    pytest.importorskip("scipy")
    H, W = 100, 200
    comp = np.zeros((H, W), np.int32)
    comp[:, :] = 1                                 # water: runs out of the box
    comp[40:60, 80:120] = 2                        # a boat hull: closed
    comp[30:40, 95:105] = 3                        # its cabin: closed
    outline = np.zeros((H, W), bool)
    m = vsp.cut_region(np.zeros((H, W, 3), np.uint8), comp, outline, [0.35, 0.25, 0.65, 0.7])
    assert m is not None and m[50, 100] and m[35, 100]
    assert not m[5, 5] and not m[90, 190]          # the water stays


def test_default_tags_are_valid_for_every_kind():
    vsp = pytest.importorskip("vector_sprites")
    from engine import vector_motion as vm
    sp = dict(i=1, facing="left", cx=0.5, cy=0.3, pivot=[0.5, 0.5], pivot_bottom=[0.5, 0.6], pivot_top=[0.5, 0.4])
    for kind, make in vsp.DEFAULT_TAGS.items():
        tags = make(sp)
        assert tags and len(vm.clean_tags(tags)) == len(tags), kind
