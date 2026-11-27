"""Formats (docs/RESPONSIVE_LAYOUT.md): every built-in scene and element renders in every aspect without failing, is not blank, keeps its content where it belongs
(inside the frame, above the caption band; inside the content box for natively tagged scenes), captions respect the safe zones, and 16:9 output is unchanged."""
import hashlib
import json
import os

import numpy as np
import pytest

from tests import format_samples as fs
from tests.element_utils import blank, make_renderer, render  # noqa: F401
from engine.frame import ASPECTS, FRAMES, Frame
from engine.scenes import ELEMENTS, SCENES
from engine.scenes import formats as fm

WORDS = [("The", 0.5, 0.8), ("quick", 0.8, 1.2), ("brown", 1.2, 1.6), ("fox", 1.6, 2.0), ("jumps", 2.0, 2.4), ("over", 2.4, 2.8), ("the", 2.8, 3.0), ("lazy", 3.0, 3.4), ("dog.", 3.4, 3.9)]
FULL_BLEED = {"image", "clip", "gallery"}      # pictures fill the frame by design: only the background check applies
GOLDEN = os.path.join(os.path.dirname(__file__), "fixtures", "golden_16x9.json")


def _native_blank():
    SCENES["__blank__"] = (lambda *a, **k: None, lambda p, d: [])
    fm.BUILTIN_FORMATS["__blank__"] = fm.ALL_ASPECTS     # an empty scene that is native everywhere: just the background


def _drop_blank():
    SCENES.pop("__blank__", None)
    fm.BUILTIN_FORMATS.pop("__blank__", None)


def _bg(aspect, theme, lt, ambience=True, draft=False):
    """The background alone at the same moment (the scene id is 't', as in make_renderer, so the ambient phase matches)."""
    _native_blank()
    try:
        return render("__blank__", {}, lt, 6.0, theme, aspect=aspect, draft=draft, resolution="720p")
    finally:
        _drop_blank()


def _bbox(img, ref, thr=100):
    a = np.asarray(img.convert("RGB"), np.int16)
    b = np.asarray(ref.convert("RGB"), np.int16)
    m = np.abs(a - b).max(axis=2) > thr
    ys, xs = np.where(m)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, float(m.mean())


# ---------------------------------------------------------------------------------------------------------------- the frame table
def test_frame_pixel_table():
    table = {("16:9", "720p"): (1280, 720), ("16:9", "1080p"): (1920, 1080), ("9:16", "720p"): (720, 1280), ("9:16", "1080p"): (1080, 1920),
             ("1:1", "720p"): (720, 720), ("1:1", "1080p"): (1080, 1080), ("4:5", "720p"): (720, 900), ("4:5", "1080p"): (1080, 1350)}
    for (a, r), (w, h) in table.items():
        f = Frame.parse(a, r)
        assert (f.width, f.height) == (w, h), (a, r)
        assert Frame.from_size(w, h) == f
    assert Frame.parse(None, None) == Frame("16:9", "1080p") and Frame.parse("nonsense", "9999") == Frame("16:9", "1080p")
    assert Frame.parse("9:16").orientation == "portrait" and Frame.parse("1:1").orientation == "square" and Frame.parse("16:9").orientation == "landscape"


def test_content_box_is_above_the_caption_band():
    for f in FRAMES.values():
        x0, y0, x1, y1 = f.content_box
        cap = f.caption
        assert 0 <= x0 < x1 <= f.design_w and 0 <= y0 < y1 <= cap["bottom"] - cap["size"] * 2.3, f.id
        assert f.box(False)[3] >= y1
    v = Frame.parse("9:16")
    assert v.caption["bottom"] <= v.design_h - 250 and v.caption["x1"] <= v.design_w - 130    # clear of the platform UI zone


def test_director_hint_and_validation(monkeypatch):
    land, tall = Frame.parse("16:9"), Frame.parse("9:16")
    assert fm.format_scene_hint(land) == ""
    sf = fm.scenes_for(tall)
    assert "title" in sf["native"] and "bullets" in sf["native"] and "kinetic_text" in sf["native"] and "map" in sf["native"] and "table" in sf["native"]
    assert sf["framed"] == ["vector_scene"] and fm.check_scene_formats(tall, ["title", {"scene": {"type": "map"}}, {"type": "table"}]) == []     # every scene type is native in vertical now except the hidden vector_scene prototype (framed card until its vertical layout is built)
    real = fm.formats_of                                                                                                        # the framed path, with a scene pretending to be landscape only
    monkeypatch.setattr(fm, "formats_of", lambda s: ("16:9",) if s in ("map", "table") else real(s))
    sf = fm.scenes_for(tall)
    assert "map" in sf["framed"] and "map" in fm.format_scene_hint(tall) and len(fm.format_scene_hint(tall).splitlines()) == 1
    warn = fm.check_scene_formats(tall, ["title", {"scene": {"type": "map"}}, {"type": "table"}])
    assert len(warn) == 2 and "map" in warn[0] and fm.check_scene_formats(land, ["map"]) == []


# ---------------------------------------------------------------------------------------------------------------- 16:9 is unchanged
def test_landscape_pixel_identical_to_before():
    golden = json.load(open(GOLDEN))
    words = [(w, a, b) for w, a, b in WORDS] + [("and", 3.9, 4.2), ("runs", 4.2, 4.6), ("away", 4.6, 5.2)]
    from engine.renderer import Renderer
    # the order used to make the fixture: the same words as tests/format_samples-based gold run
    words = [("The", 0.5, 0.8), ("quick", 0.8, 1.2), ("brown", 1.2, 1.6), ("fox", 1.6, 2.0), ("jumps", 2.0, 2.4), ("over", 2.4, 2.8), ("the", 2.8, 3.0), ("lazy", 3.0, 3.4), ("dog.", 3.4, 3.9)]
    bad = []
    for key, want in golden.items():
        name, theme, lt = key.split("|")
        st, props = fs.sample(name)
        sc = {"id": name, "type": st, "start": 0.0, "duration": 6.0, "props": props, "words": words, "transition": "none"}
        tl = {"scenes": [sc], "theme": theme, "captions": True, "duration": 6.0, "width": 1920, "height": 1080, "fps": 30, "outro": False}
        img = Renderer(tl, image_loader=fs.image_loader, clip_loader=fs.clip_loader)._draw_spec(sc, float(lt))
        if hashlib.sha256(img.tobytes()).hexdigest()[:20] != want:
            bad.append(key)
    assert not bad, f"16:9 output changed: {bad}"


# ---------------------------------------------------------------------------------------------------------------- built-in scenes x aspects
@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name", sorted(fs.SAMPLES))
def test_builtin_scene_in_every_aspect(name, aspect):
    stype, props = fs.sample(name)
    fr = Frame.parse(aspect, "720p")
    assert fm.is_native(stype, fr)
    for theme in ("midnight", "paper"):
        for frac in (0.0, 0.5, 0.97):
            lt = 6.0 * frac
            img = render(stype, props, lt, 6.0, theme, aspect=aspect, resolution="720p", image_loader=fs.image_loader, clip_loader=fs.clip_loader, draft=False, captions=True)   # captions on, none spoken: the scene keeps the band free
            assert img.size == (fr.W, fr.H)    # _draw_spec returns design units; frame_at scales
            if frac < 0.9:
                continue
            ref = _bg(aspect, theme, lt, stype != "image")
            bb = _bbox(img, ref)
            assert bb is not None and bb[4] > 0.004, f"{name} {aspect} {theme}: blank at the end"
            if stype in FULL_BLEED or fr.landscape:     # 16:9 layouts are guarded by the golden test; pictures fill the frame by design
                continue
            x0, y0, x1, y1, _ = bb
            s = 1.0
            cx0, cy0, cx1, cy1 = fr.content_box
            tol = 40
            assert x0 >= (cx0 - tol) * s and x1 <= (cx1 + tol) * s, f"{name} {aspect} {theme}: content leaves the side margins {bb}"
            assert y1 <= (cy1 + tol) * s, f"{name} {aspect} {theme}: content reaches the caption band {bb}"
            assert y0 >= (fr.margin_top - 45) * s, f"{name} {aspect} {theme}: content above the top margin {bb}"


@pytest.mark.parametrize("aspect", ASPECTS)
def test_captions_stay_in_their_band(aspect):
    fr = Frame.parse(aspect, "720p")
    _native_blank()
    try:
        r, sc = make_renderer("__blank__", {}, 6.0, "midnight", WORDS, True, None, False, aspect, "720p")
        with_c = r._draw_spec(sc, 2.0)
        r2, sc2 = make_renderer("__blank__", {}, 6.0, "midnight", WORDS, False, None, False, aspect, "720p")
        without = r2._draw_spec(sc2, 2.0)
    finally:
        _drop_blank()
    bb = _bbox(with_c, without, thr=20)
    assert bb is not None, "no captions drawn"
    x0, y0, x1, y1, _ = bb
    s, cap = 1.0, fr.caption
    assert y1 <= (cap["bottom"] + 8) * s and y0 >= fr.content_bottom(True) * s - 12 * s, f"captions {bb} outside the band"
    assert x0 >= cap["x0"] * s and x1 <= (cap["x1"] + 2) * s - fr.right_reserve * 0 * s
    if aspect == "9:16":
        assert x1 <= (fr.design_w - fr.right_reserve) * s and y1 <= (fr.design_h - 250 + 8) * s     # clear of the platform UI zone
    # at most two lines
    assert (y1 - y0) <= (cap["size"] * 1.32 * 2 + 70) * s


# ---------------------------------------------------------------------------------------------------------------- elements x aspects (framed fallback or native)
_EL = sorted(ELEMENTS)


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name", _EL)
def test_element_in_every_aspect(name, aspect):
    import copy
    el = ELEMENTS[name]
    fr = Frame.parse(aspect, "720p")
    props = el.sanitize(copy.deepcopy(el.samples[0]))
    dur = max(8.0, el.min_seconds + 2)
    r, sc = make_renderer(name, props, dur, "midnight", [], True, None, True, aspect, "720p")   # captions on (none spoken): the card keeps the band free
    # a later state of the scene, and its first frame
    first = r._draw_spec(sc, 0.0)
    img = r._draw_spec(sc, dur * 0.95)
    assert img.size == first.size == (fr.W, fr.H)
    ref = _bg(aspect, "midnight", dur * 0.95, draft=True)
    bb = _bbox(img, ref, thr=40)
    assert bb is not None, f"{name} {aspect}: blank"
    if aspect in el.formats:
        return
    # framed: the card sits inside the content box
    x0, y0, x1, y1, _ = bb
    s = 1.0
    cx0, cy0, cx1, cy1 = fr.content_box
    assert y1 <= (cy1 + 40) * s and y0 >= (cy0 - 40) * s and x0 >= 0 and x1 <= fr.W, f"{name} {aspect}: framed card out of place {bb}"
    rep = r.fallbacks.get("t")
    assert rep and rep["scale"] > 0.3


# ---------------------------------------------------------------------------------------------------------------- stock footage orientation
def test_clip_search_asks_for_the_videos_orientation():
    from engine import clips

    seen = []

    def fetch(url, headers=None):
        seen.append(url)
        return {"videos": [], "hits": []}

    clips.pexels_search("ocean", "k", fetch, orientation="portrait")   # the true shape first, then landscape footage (cropped; owner decision 2026-11-26)
    clips.pexels_search("ocean", "k", fetch)
    assert "orientation=portrait" in seen[0] and "orientation=landscape" in seen[1] and "orientation=landscape" in seen[2] and len(seen) == 3
    hits = {"hits": [{"id": 1, "duration": 12, "tags": "a", "pageURL": "https://pixabay.com/x", "user": "u", "videos": {"medium": {"url": "https://v/a.mp4", "width": 720, "height": 1280, "size": 1000, "thumbnail": "https://t/a.jpg"}}},
                     {"id": 2, "duration": 12, "tags": "b", "pageURL": "https://pixabay.com/y", "user": "u", "videos": {"medium": {"url": "https://v/b.mp4", "width": 1920, "height": 1080, "size": 1000, "thumbnail": "https://t/b.jpg"}}}]}
    clips._CACHE.clear()
    assert [c["id"] for c in clips.pixabay_search("q1", "k", lambda u, **kw: hits, orientation="portrait")] == ["1", "2"]   # a vertical video takes landscape footage too, true portrait first
    clips._CACHE.clear()
    assert [c["id"] for c in clips.pixabay_search("q2", "k", lambda u, **kw: hits)] == ["2"]
    assert clips.ORIENTATIONS["portrait"] == (720, 1280)


def test_frame_at_scales_to_the_output_size():
    r, sc = make_renderer("title", {"title": "Hello"}, 6.0, "midnight", [], True, None, False, "9:16", "720p")
    assert r.frame_at(1.0).size == (720, 1280)
    r, sc = make_renderer("title", {"title": "Hello"}, 6.0, "midnight", [], True, None, True, "4:5", "1080p")
    assert r.frame_at(1.0).size == (540, 674)


def test_caches_keyed_by_size_do_not_collide():
    """Rendering the same scene in two shapes in one process gives each its own size (backgrounds, scrims, sprites are keyed by pixel size)."""
    a = render("title", {"title": "Hello"}, 1.0, 6.0, aspect="9:16", resolution="720p", draft=False)
    b = render("title", {"title": "Hello"}, 1.0, 6.0, aspect="1:1", resolution="720p", draft=False)
    c = render("title", {"title": "Hello"}, 1.0, 6.0, aspect="9:16", resolution="720p", draft=False)
    assert a.size == (1080, 1920) and b.size == (1080, 1080) and a.tobytes() == c.tobytes()
