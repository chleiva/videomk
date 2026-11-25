"""The Photos elements: photo_collage, photo_frame, chapter_card."""
import copy

import pytest
from PIL import Image

from tests.element_utils import blank, changed, render
from engine.scenes import ELEMENTS
from engine.scenes.registry import PrepareCtx

NAMES = ("photo_collage", "photo_frame", "chapter_card")
STYLES = ("mosaic", "polaroids", "grid", "filmstrip", "stack")
FRAME_STYLES = ("polaroid", "matte", "tilted", "film", "pinned")
SHAPES = {1: (900, 1200, (200, 80, 60)), 2: (1200, 800, (60, 120, 200)), 3: (1000, 1000, (60, 180, 90)), 4: (1280, 720, (220, 180, 40)),
          5: (900, 1200, (150, 60, 160)), 6: (1200, 900, (30, 160, 170)), 7: (1200, 800, (210, 110, 50)), 8: (700, 1200, (90, 90, 200)), 9: (1280, 720, (120, 200, 120))}


def _img(i):
    w, h, c = SHAPES[(i - 1) % 9 + 1]
    im = Image.new("RGB", (w, h), c)
    for x in range(0, w, 40):                       # something to see, not a flat colour
        im.paste((255 - c[0], 255 - c[1], 255 - c[2]), (x, 0, x + 12, h))
    return im


def loader(key):
    return _img(int(key.split("_P")[1].split(".")[0]))


def ctx(n=9):
    items = [{"id": f"P{i}", "key": f"v/assets/user_P{i}.jpg", "w": SHAPES[(i - 1) % 9 + 1][0], "h": SHAPES[(i - 1) % 9 + 1][1], "orientation": "landscape", "caption": f"photo {i}"} for i in range(1, n + 1)]
    return PrepareCtx(video_id="v", beat_id="b", narration="x", duration=8.0, media_items=items)


def test_the_elements_are_registered_in_the_photos_family():
    for n in NAMES:
        assert ELEMENTS[n].family == "Photos" and len(ELEMENTS[n].doc) <= 800
    assert ELEMENTS["chapter_card"].min_seconds == 3.0


# --------------------------------------------------------------------------------------------------------- sanitize
def test_collage_sanitize_limits_and_refusals():
    el = ELEMENTS["photo_collage"]
    p = el.sanitize({"photos": ["p1", "P2", "P2", "bad", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"], "style": "nope", "title": "t" * 90, "subtitle": "s" * 200, "alt": "a" * 200, "junk": 1})
    assert p["photos"] == ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"] and "style" not in p and len(p["title"]) <= 50 and len(p["subtitle"]) <= 80 and len(p["alt"]) <= 70 and "junk" not in p
    assert el.sanitize({"photos": "P1, P2 P3", "style": "grid"})["photos"] == ["P1", "P2", "P3"]
    for bad in ({}, {"photos": ["P1"]}, {"photos": ["x", "y"]}, {"photos": "P1,P1"}):
        with pytest.raises(ValueError):
            el.sanitize(bad)


def test_frame_and_chapter_sanitize():
    f, c = ELEMENTS["photo_frame"], ELEMENTS["chapter_card"]
    p = f.sanitize({"photo": "p7", "style": "film", "title": "t" * 99, "subtitle": "s" * 99, "date_label": "d" * 99})
    assert p["photo"] == "P7" and p["style"] == "film" and len(p["title"]) <= 50 and len(p["subtitle"]) <= 80 and len(p["date_label"]) <= 30
    for bad in ({}, {"photo": "7"}, {"photo": "P1234"}):
        with pytest.raises(ValueError):
            f.sanitize(bad)
    q = c.sanitize({"title": "T" * 100, "subtitle": "s" * 300, "kicker": "k" * 99, "photo": "nope"})
    assert len(q["title"]) <= 60 and len(q["subtitle"]) <= 100 and len(q["kicker"]) <= 40 and "photo" not in q
    with pytest.raises(ValueError):
        c.sanitize({"subtitle": "x"})


def test_patches_survive_a_second_sanitize():
    el = ELEMENTS["photo_collage"]
    p = el.sanitize({"photos": ["P1", "P2", "P3"]})
    p.update(el.prepare(p, ctx()))
    assert el.sanitize(copy.deepcopy(p)) == p and len(p["assets"]) == 3


# --------------------------------------------------------------------------------------------------------- prepare
def test_collage_prepare_resolves_ids_ratios_and_drops_unknown_ones():
    el = ELEMENTS["photo_collage"]
    patch = el.prepare({"photos": ["P2", "P99", "P1", "P3"], "captions": ["a", "b", "c", "d"]}, ctx(3))
    assert patch["photos"] == ["P2", "P1", "P3"] and patch["assets"] == ["v/assets/user_P2.jpg", "v/assets/user_P1.jpg", "v/assets/user_P3.jpg"]
    assert patch["ratios"][0] == pytest.approx(1.5) and patch["ratios"][1] == pytest.approx(0.75) and patch["orientations"] == ["landscape", "portrait", "square"]
    assert patch["captions"] == ["a", "c", "d"]
    with pytest.raises(ValueError):
        el.prepare({"photos": ["P1", "P50", "P51"]}, ctx(3))
    assert el.fallback({"photos": ["P1", "P2"], "title": "Paris"})[0] == "title"


def test_frame_prepare():
    el = ELEMENTS["photo_frame"]
    assert el.prepare({"photo": "P1"}, ctx(2)) == {"asset": "v/assets/user_P1.jpg", "ratio": pytest.approx(0.75, abs=1e-3)}
    with pytest.raises(ValueError):
        el.prepare({"photo": "P9"}, ctx(2))


def test_chapter_prepare_never_raises():
    el = ELEMENTS["chapter_card"]
    assert el.prepare({"title": "T", "photo": "P2"}, ctx(3)) == {"asset": "v/assets/user_P2.jpg"}
    assert el.prepare({"title": "T", "photo": "P40"}, ctx(3)) == {}
    assert el.prepare({"title": "T"}, ctx(3)) == {}
    assert el.prepare({"title": "T", "photo": ["x"]}, PrepareCtx("v", "b", "", 1.0)) == {}


# --------------------------------------------------------------------------------------------------------- anchors and cues
def test_collage_anchors_follow_the_captions_and_cues_are_honoured():
    el = ELEMENTS["photo_collage"]
    p = el.sanitize({"photos": ["P1", "P2", "P3"], "captions": ["the tower", "", "a lunch"]})
    assert el.anchors(p) == ["the tower", "photo 2", "a lunch"]
    assert el.anchors(el.sanitize({"photos": ["P1", "P2"]})) == ["photo 1", "photo 2"]
    p["cues"] = [0.3, 2.0, 4.0]
    assert el.cues(p, 8.0) == [0.3, 2.0, 4.0]
    early, late = render("photo_collage", p, 1.0, 8.0), render("photo_collage", p, 3.0, 8.0)
    assert changed(early, late) > 0.01                              # the second photo arrives at 2.0 s, not before


# --------------------------------------------------------------------------------------------------------- drawing
def _props(style, n=6, **kw):
    p = {"photos": [f"P{i}" for i in range(1, n + 1)], "style": style, "alt": "x"}
    p.update(kw)
    p.update(ELEMENTS["photo_collage"].prepare(p, ctx(9)))
    return p


@pytest.mark.parametrize("style", STYLES)
def test_every_collage_style_draws_with_real_photos_and_without(style):
    for n in (2, 3, 5, 9):
        p = _props(style, n, title="Saturday in Paris", subtitle="a long lunch")
        end = render("photo_collage", p, 8.0, 8.0, image_loader=loader)
        none = render("photo_collage", p, 8.0, 8.0, image_loader=lambda k: None)     # photos unreadable: placeholders in the same layout
        bare = {k: v for k, v in p.items() if k not in ("assets", "ratios", "orientations")}
        before_prepare = render("photo_collage", bare, 8.0, 8.0)
        for im in (end, none, before_prepare):
            assert changed(im, blank(lt=8.0, dur=8.0)) > 0.05, (style, n)
        assert changed(render("photo_collage", p, 0.0, 8.0, image_loader=loader), end) > 0.02


@pytest.mark.parametrize("style", STYLES)
def test_the_caption_band_stays_free(style):
    p = _props(style, 9, title="Saturday in Paris", subtitle="a long lunch")
    a = render("photo_collage", p, 8.0, 8.0, image_loader=None, captions=True)
    band = (0, 800, a.width, a.height)                                   # the caption band starts at 800
    b = blank(lt=8.0, dur=8.0)
    assert changed(a.crop(band), b.crop(band)) < 0.002


@pytest.mark.parametrize("style", FRAME_STYLES)
def test_every_frame_style_draws_for_portrait_square_and_landscape(style):
    for i in (1, 3, 2):
        p = {"photo": f"P{i}", "style": style, "title": "Golden hour", "subtitle": "From the Trocadero", "date_label": "Sunday 12 April"}
        p.update(ELEMENTS["photo_frame"].prepare(p, ctx(3)))
        assert changed(render("photo_frame", p, 6.0, 6.0, image_loader=loader), blank(lt=6.0, dur=6.0)) > 0.1
        assert changed(render("photo_frame", {k: v for k, v in p.items() if k not in ("asset", "ratio")}, 6.0, 6.0), blank(lt=6.0, dur=6.0)) > 0.02


def test_a_photo_in_a_frame_is_never_cropped():
    p = {"photo": "P1", "style": "matte", "asset": "v/assets/user_P1.jpg", "ratio": 0.75}
    im = render("photo_frame", p, 6.0, 6.0, image_loader=lambda k: Image.new("RGB", (900, 1200), (255, 0, 0)))
    xs = [x for x in range(im.width) if im.getpixel((x, im.height // 2))[0] > 200 and im.getpixel((x, im.height // 2))[1] < 60]
    ys = [y for y in range(im.height) if im.getpixel((im.width // 2, y))[0] > 200 and im.getpixel((im.width // 2, y))[1] < 60]
    assert xs and ys and (max(xs) - min(xs)) / (max(ys) - min(ys)) == pytest.approx(0.75, abs=0.03)


def test_chapter_card_with_and_without_a_hero():
    p = {"title": "A day in the city", "kicker": "Day 2", "subtitle": "Markets and museums"}
    plain = render("chapter_card", p, 4.0, 5.0)
    hero = render("chapter_card", dict(p, asset="v/assets/user_P1.jpg"), 4.0, 5.0, image_loader=loader)
    assert changed(plain, hero) > 0.05 and changed(plain, blank(lt=4.0, dur=5.0)) > 0.01
    assert changed(render("chapter_card", p, 0.0, 5.0), plain) > 0.005
    render("chapter_card", dict(p, asset="missing.jpg"), 4.0, 5.0, image_loader=lambda k: None)       # a missing hero: just no background


@pytest.mark.parametrize("name", NAMES)
def test_the_samples_draw_on_every_theme_with_photos(name):
    el = ELEMENTS[name]
    for s in el.samples:
        p = el.sanitize(copy.deepcopy(s))
        p.update(el.prepare(p, ctx(9)))
        for th in ("midnight", "paper", "sunrise"):
            render(name, p, 3.0, 7.0, th, image_loader=loader, captions=True)


# --------------------------------------------------------------------------------------------------------- responsive (9:16, 1:1, 4:5)
ASPECTS = ("9:16", "1:1", "4:5")


def _bbox(a, b, thr=30):
    import numpy as np
    d = np.abs(np.asarray(a.convert("RGB"), np.int16) - np.asarray(b.convert("RGB"), np.int16)).max(axis=2) > thr
    ys, xs = np.where(d)
    return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None


def _blank_for(aspect, lt, dur):
    from engine import scenes
    scenes.SCENES["__blank__"] = (lambda *a, **k: None, lambda p, d: [])
    try:
        return render("__blank__", {}, lt, dur, "midnight", aspect=aspect, resolution="720p", draft=False, captions=True)
    finally:
        scenes.SCENES.pop("__blank__", None)


def test_the_photo_elements_are_tagged_for_every_aspect():
    for n in NAMES:
        assert set(ELEMENTS[n].formats) == {"16:9", "9:16", "1:1", "4:5"}


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("style", STYLES)
def test_collage_stays_in_the_content_box_in_every_aspect(style, aspect):
    from engine.frame import Frame
    fr = Frame.parse(aspect, "720p")
    x0, y0, x1, y1 = fr.content_box
    for n in (2, 3, 6, 9):
        p = _props(style, n, title="Saturday in Paris", subtitle="a long lunch")
        for ld in (None, loader):
            im = render("photo_collage", p, 8.0, 8.0, aspect=aspect, resolution="720p", draft=False, captions=True, image_loader=ld)
            assert im.size == (fr.W, fr.H)
            if ld is None:
                bb = _bbox(im, _blank_for(aspect, 8.0, 8.0))
                tol = 70                                   # soft shadows
                assert bb and bb[0] >= x0 - tol and bb[2] <= x1 + tol and bb[3] <= y1 + tol and bb[1] >= y0 - tol, (style, n, aspect, bb)
        assert changed(render("photo_collage", p, 0.0, 8.0, aspect=aspect, resolution="720p", image_loader=loader), im) > 0.02


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("style", FRAME_STYLES)
def test_frame_and_chapter_in_every_aspect(style, aspect):
    from engine.frame import Frame
    fr = Frame.parse(aspect, "720p")
    x0, y0, x1, y1 = fr.content_box
    for i in (1, 2, 3):
        p = {"photo": f"P{i}", "style": style, "title": "Golden hour", "subtitle": "From the Trocadero", "date_label": "Sunday 12 April"}
        p.update(ELEMENTS["photo_frame"].prepare(p, ctx(3)))
        bare = {k: v for k, v in p.items() if k not in ("asset", "ratio")}
        im = render("photo_frame", bare, 6.0, 6.0, aspect=aspect, resolution="720p", draft=False, captions=True)
        bb = _bbox(im, _blank_for(aspect, 6.0, 6.0))
        assert bb and bb[3] <= y1 + 70 and bb[1] >= y0 - 70, (style, aspect, bb)
        if style != "film":                                # a film strip bleeds off both sides by design
            assert bb[0] >= x0 - 70 and bb[2] <= x1 + 70, (style, aspect, bb)
        render("photo_frame", p, 6.0, 6.0, aspect=aspect, resolution="720p", image_loader=loader)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_chapter_card_is_centred_and_inside_the_box(aspect):
    from engine.frame import Frame
    fr = Frame.parse(aspect, "720p")
    x0, y0, x1, y1 = fr.content_box
    for title in ("Paris", "The long way round the old harbour and back again to the town square", "Extraordinarilylongwordthatcannotbreakanywhereatall"):
        im = render("chapter_card", {"title": title, "kicker": "Day 2", "subtitle": "Markets, museums and a long walk home"}, 4.0, 5.0, aspect=aspect, resolution="720p", draft=False, captions=True)
        bb = _bbox(im, _blank_for(aspect, 4.0, 5.0), thr=140)   # the text, not the faint rings
        assert bb and bb[0] >= x0 - 20 and bb[2] <= x1 + 20 and bb[1] >= y0 - 20 and bb[3] <= y1 + 20, (aspect, title[:12], bb)


def test_vertical_film_strips_keep_their_cues():
    p = _props("filmstrip", 6)
    p["cues"] = [0.3, 2.0, 3.0, 4.0, 5.0, 6.0]
    early = render("photo_collage", p, 1.0, 8.0, aspect="9:16", resolution="720p", image_loader=loader)
    late = render("photo_collage", p, 2.5, 8.0, aspect="9:16", resolution="720p", image_loader=loader)
    assert changed(early, late) > 0.005
