"""4K clip scenes: footage under ~1080p wide plays in a native-size window instead of a 3x full-frame enlargement (docs/FOUR_K.md, docs/CLIPS.md).
720p and 1080p renders must not change by a single pixel."""
import hashlib

import pytest
from PIL import Image

from engine import clips
from engine.frame import Frame
from engine.renderer import Renderer
from engine.scenes import viz_scenes
from tests.test_clips import frame_sizes, make_source
from tests.test_engine import small_timeline


def _clip_frames(tmp_path, size="1280x720", hd=True):
    mp4, _ = clips.normalise(make_source(3, size, tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=hd)
    p = tmp_path / "c.mp4"
    p.write_bytes(mp4)
    return clips.ClipFrames(str(p))


def _timeline(res, props=None):
    f = Frame.parse("16:9", res)
    tl = small_timeline(4.0, ["clip"])
    tl.update({"width": f.width, "height": f.height, "frame": {"aspect": "16:9", "resolution": res}})
    tl["scenes"][0]["props"] = {"asset": "c", "alt": "sunbeams in a forest", "credit": "Video: Z / videomk", **(props or {})}
    return tl


def _digest(res, frames, t=1.5, **props):
    r = Renderer(_timeline(res, props), clip_loader=lambda k: frames)
    return hashlib.md5(r.frame_at(t).tobytes()).hexdigest(), r.frame_at(t)


def test_framed_rule_is_only_for_4k_and_small_footage():
    f4, f1 = Frame.parse("16:9", "2160p"), Frame.parse("16:9", "1080p")
    assert viz_scenes.clip_is_framed(f4, (1280, 720)) and viz_scenes.clip_is_framed(f4, (1600, 900))
    assert not viz_scenes.clip_is_framed(f4, (1920, 1080)) and not viz_scenes.clip_is_framed(f4, (3840, 2160))   # big enough: full bleed as before
    assert not viz_scenes.clip_is_framed(f1, (1280, 720)) and not viz_scenes.clip_is_framed(Frame.parse("16:9", "720p"), (1280, 720))
    assert not viz_scenes.clip_is_framed(None, (1280, 720))
    for aspect, small, big in (("9:16", (720, 1280), (1080, 1920)), ("1:1", (720, 720), (1080, 1080)), ("4:5", (720, 1280), (1080, 1920))):
        assert viz_scenes.clip_is_framed(Frame.parse(aspect, "2160p"), small) and not viz_scenes.clip_is_framed(Frame.parse(aspect, "2160p"), big)   # a 1080 copy fills a 2160-wide frame at 2x
        assert not viz_scenes.clip_is_framed(Frame.parse(aspect, "1080p"), small) and not viz_scenes.clip_is_framed(Frame.parse(aspect, "720p"), small)


def test_720p_and_1080p_renders_do_not_depend_on_the_framed_layout(tmp_path, monkeypatch):
    frames = _clip_frames(tmp_path, hd=False)
    before = {res: _digest(res, frames)[0] for res in ("720p", "1080p")}
    monkeypatch.setattr(viz_scenes, "_draw_clip_framed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("framed layout used below 4K")))
    monkeypatch.setattr(viz_scenes, "FRAMED_MIN_FULL_W", 99999)   # even if the threshold were absurd, only the 4K frame may use it
    monkeypatch.setattr(viz_scenes, "FRAMED_SCALE", 3.0)
    assert {res: _digest(res, frames)[0] for res in ("720p", "1080p")} == before


def test_4k_with_small_footage_shows_a_window_over_a_dark_glow_and_the_text_at_native_size(tmp_path):
    frames = _clip_frames(tmp_path)
    assert frames.frame(0).size == (1280, 720)                      # footage under 1080p is NOT enlarged to 1920x1080 for a 4K video
    _, im = _digest("2160p", frames)
    assert im.size == (3840, 2160)
    from PIL import ImageStat
    lum = im.convert("L")
    wd = 1280 * viz_scenes.FRAMED_SCALE                              # window width in output pixels
    left, right = 1920 - wd / 2, 1920 + wd / 2
    inside = ImageStat.Stat(lum.crop((int(left) + 100, 400, int(right) - 100, 900))).mean[0]
    outside = ImageStat.Stat(lum.crop((0, 0, int(left) - 60, 700))).mean[0]
    assert outside < 0.6 * inside                                    # the sides are the darkened glow, not footage
    assert ImageStat.Stat(lum.crop((int(left) - 30, 400, int(left) - 4, 900))).mean[0] < 0.6 * inside   # nothing leaks outside the window
    # the caption line under the window is drawn natively (text pixels are far brighter than the glow)
    band = im.crop((int(left), 1380, int(left) + 1000, 1450)).convert("L")
    assert band.getextrema()[1] > 200


def test_4k_with_1080p_footage_keeps_the_full_bleed_look(tmp_path, monkeypatch):
    frames = _clip_frames(tmp_path, size="1920x1080")
    assert frames.frame(0).size == (1920, 1080)
    monkeypatch.setattr(viz_scenes, "_draw_clip_framed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("window used for 1080p footage")))
    _, im = _digest("2160p", frames)
    assert max(im.getpixel((8, 8))) > 0 and im.size == (3840, 2160)


def test_hd_normalise_keeps_small_sources_native_and_big_ones_at_1080p(tmp_path):
    for size, want in (("640x360", (1280, 720)), ("1280x720", (1280, 720)), ("1600x900", (1280, 720)), ("1920x1080", (1920, 1080))):
        mp4, _ = clips.normalise(make_source(2, size, tmp_path=tmp_path), need_seconds=2.0, source_seconds=2.0, suffix=".mp4", hd=True)
        assert frame_sizes(mp4, tmp_path)[1] == want, size
    # vertical and square 4K videos: the 1080 copy only from a source that fills it without enlargement; anything else stays at the 720 copy (shown in a window)
    for size, orient, want in (("640x360", "portrait", (720, 1280)), ("1920x1080", "portrait", (720, 1280)), ("1080x1920", "portrait", (1080, 1920)), ("720x1280", "portrait", (720, 1280)),
                               ("1280x720", "square", (720, 720)), ("1920x1080", "square", (1080, 1080)), ("1080x1080", "square", (1080, 1080))):
        mp4, _ = clips.normalise(make_source(2, size, tmp_path=tmp_path), need_seconds=2.0, source_seconds=2.0, suffix=".mp4", hd=True, orientation=orient)
        assert frame_sizes(mp4, tmp_path)[1] == want, (size, orient)
        mp4, _ = clips.normalise(make_source(2, size, tmp_path=tmp_path), need_seconds=2.0, source_seconds=2.0, suffix=".mp4", orientation=orient)
        assert frame_sizes(mp4, tmp_path)[1] == clips.clip_size(orient), (size, orient)   # 720p and 1080p videos: exactly as before


def _tall_timeline(aspect, res, captions=True):
    f = Frame.parse(aspect, res)
    tl = small_timeline(4.0, ["clip"])
    tl.update({"width": f.width, "height": f.height, "frame": {"aspect": aspect, "resolution": res}, "captions": captions})
    tl["scenes"][0]["props"] = {"asset": "c", "alt": "sunbeams in a forest in the early morning light", "credit": "Video: Z / videomk"}
    return tl


@pytest.mark.parametrize("aspect,src,orient", [("9:16", "720x1280", "portrait"), ("1:1", "720x720", "square"), ("4:5", "720x1280", "portrait")])
def test_vertical_square_and_4_5_4k_show_small_footage_in_a_window_inside_the_content_box(tmp_path, aspect, src, orient):
    import numpy as np

    mp4, _ = clips.normalise(make_source(3, src, tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True, orientation=orient)
    p = tmp_path / "t.mp4"
    p.write_bytes(mp4)
    frames = clips.ClipFrames(str(p))
    fr = Frame.parse(aspect, "2160p")
    assert frames.frame(0).size[0] == 720 and viz_scenes.clip_is_framed(fr, frames.frame(0).size)
    im = Renderer(_tall_timeline(aspect, "2160p"), clip_loader=lambda k: frames).frame_at(1.5)
    assert im.size == (fr.width, fr.height)
    lum = np.asarray(im.convert("L"), np.float32)
    x0, y0, x1, y1 = [v * 2 for v in fr.box(True)]   # the content box in output pixels
    sw, sh = frames.frame(0).size
    k = min(1.0, (y1 - y0 - 160) / (sh * viz_scenes.FRAMED_SCALE))
    ww, wh = sw * viz_scenes.FRAMED_SCALE * k, sh * viz_scenes.FRAMED_SCALE * k
    assert ww <= sw * viz_scenes.FRAMED_SCALE + 1 and ww < 0.55 * fr.width          # never enlarged more than 1.5x: at most half the frame wide
    cx = fr.width // 2
    inside = lum[int(y0 + 0.2 * wh):int(y0 + 0.7 * wh), int(cx - 0.3 * ww):int(cx + 0.3 * ww)].mean()
    left = lum[int(y0):int(y1), 0:int(cx - ww / 2 - 60)].mean()
    assert left < 0.6 * inside                                                       # beside the window: the darkened glow, not footage
    assert lum[: max(1, int(y0) - 40)].mean() < 0.6 * inside                           # above the content box: only the glow
    under = lum[int(y0 + wh):int(y1) + 30, int(cx - ww / 2):int(cx + ww / 2)]
    assert under.max() > 200                                                         # the caption line and the credit are drawn under the window, natively


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5"])
def test_below_4k_the_other_shapes_never_use_the_window(tmp_path, monkeypatch, aspect):
    frames = _clip_frames(tmp_path, size="720x1280", hd=False)
    monkeypatch.setattr(viz_scenes, "_draw_clip_framed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("framed layout used below 4K")))
    for res in ("720p", "1080p"):
        f = Frame.parse(aspect, res)
        assert Renderer(_tall_timeline(aspect, res), clip_loader=lambda k: frames).frame_at(1.5).size == (f.width, f.height)


def test_a_vertical_4k_video_with_real_vertical_1080_footage_keeps_the_full_bleed_look(tmp_path, monkeypatch):
    mp4, _ = clips.normalise(make_source(3, "1080x1920", tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True, orientation="portrait")
    p = tmp_path / "v.mp4"
    p.write_bytes(mp4)
    frames = clips.ClipFrames(str(p))
    assert frames.frame(0).size == (1080, 1920)
    monkeypatch.setattr(viz_scenes, "_draw_clip_framed", lambda *a, **k: (_ for _ in ()).throw(AssertionError("window used for 1080-wide vertical footage")))
    im = Renderer(_tall_timeline("9:16", "2160p"), clip_loader=lambda k: frames).frame_at(1.5)
    assert im.size == (2160, 3840) and max(im.getpixel((8, 8))) > 0


def test_a_montage_of_mixed_sizes_in_a_4k_video_uses_the_smaller_one(tmp_path):
    a, _ = clips.normalise(make_source(3, "1920x1080", tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True)
    b, _ = clips.normalise(make_source(3, "640x360", tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True)
    out = clips.assemble_montage([a, b], [2.0, 2.0], [3.0, 3.0], hd=True)
    assert frame_sizes(out, tmp_path)[1] == (1280, 720)
