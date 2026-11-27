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


def test_framed_rule_is_only_for_landscape_4k_and_small_footage():
    f4, f1 = Frame.parse("16:9", "2160p"), Frame.parse("16:9", "1080p")
    assert viz_scenes.clip_is_framed(f4, (1280, 720)) and viz_scenes.clip_is_framed(f4, (1600, 900))
    assert not viz_scenes.clip_is_framed(f4, (1920, 1080)) and not viz_scenes.clip_is_framed(f4, (3840, 2160))   # big enough: full bleed as before
    assert not viz_scenes.clip_is_framed(f1, (1280, 720)) and not viz_scenes.clip_is_framed(Frame.parse("16:9", "720p"), (1280, 720))
    assert not viz_scenes.clip_is_framed(Frame.parse("9:16", "2160p"), (720, 1280)) and not viz_scenes.clip_is_framed(None, (1280, 720))


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
    mp4, _ = clips.normalise(make_source(2, "640x360", tmp_path=tmp_path), need_seconds=2.0, source_seconds=2.0, suffix=".mp4", hd=True, orientation="portrait")
    assert frame_sizes(mp4, tmp_path)[1] == (1080, 1920)             # vertical 4K videos are unchanged


def test_a_montage_of_mixed_sizes_in_a_4k_video_uses_the_smaller_one(tmp_path):
    a, _ = clips.normalise(make_source(3, "1920x1080", tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True)
    b, _ = clips.normalise(make_source(3, "640x360", tmp_path=tmp_path), need_seconds=3.0, source_seconds=3.0, suffix=".mp4", hd=True)
    out = clips.assemble_montage([a, b], [2.0, 2.0], [3.0, 3.0], hd=True)
    assert frame_sizes(out, tmp_path)[1] == (1280, 720)
