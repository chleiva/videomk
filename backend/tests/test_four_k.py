"""4K (2160p) output, docs/FOUR_K.md: sizes and scaling, the renderer's 4K path, encoder settings, chunk pieces, larger sources, the deploy flag, capabilities,
and the price (double credits, charged, shown and refunded)."""
import copy
import io
import json
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

from common import wallet
from engine import assets, awsio, clips, format_options as fo, media, pipeline, stock, usermedia
from engine.frame import FRAMES, RESOLUTIONS, Frame
from engine.handlers import beat_handler, render_chunk_handler, timeline_handler
from engine.renderer import Renderer
from engine.timeline import chunk_plan, chunk_timeline
from tests import format_samples as fs
from tests.element_utils import make_renderer
from tests.test_create_options import _plan, _run_timeline, cap_event, post, sent
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)

PIXELS_4K = {"16:9": (3840, 2160), "9:16": (2160, 3840), "1:1": (2160, 2160), "4:5": (2160, 2700)}
OLD_PIXELS = {("16:9", "720p"): (1280, 720), ("16:9", "1080p"): (1920, 1080), ("9:16", "720p"): (720, 1280), ("9:16", "1080p"): (1080, 1920),
              ("1:1", "720p"): (720, 720), ("1:1", "1080p"): (1080, 1080), ("4:5", "720p"): (720, 900), ("4:5", "1080p"): (1080, 1350)}


@pytest.fixture
def four_k(monkeypatch):
    monkeypatch.setenv("READY_RESOLUTIONS", "720p,1080p,2160p")


# ---------- sizes and scaling ----------
@pytest.mark.parametrize("aspect,size", PIXELS_4K.items())
def test_4k_pixel_table(aspect, size):
    f = Frame.parse(aspect, "2160p")
    assert (f.width, f.height) == size == fo.frame_size(aspect, "2160p") and min(size) == 2160 and all(x % 2 == 0 for x in size)
    assert f.scale_factor == 2.0 and f.scale(100) == 200 and (f.W, f.H) == (Frame.parse(aspect, "1080p").W, Frame.parse(aspect, "1080p").H)   # same design canvas: scenes do not know
    assert f.id == f"{aspect}@2160p" and Frame.from_size(*size) is FRAMES[(aspect, "2160p")]
    d = fo.frame_dict(aspect, "2160p", "youtube")
    assert (d["width"], d["height"], d["resolution"]) == (*size, "2160p") and fo.frame_of({"frame": d}) == d


def test_720p_and_1080p_sizes_are_what_they_were():
    assert RESOLUTIONS == ("720p", "1080p", "2160p") and fo.RESOLUTION_IDS == RESOLUTIONS
    for (aspect, res), size in OLD_PIXELS.items():
        f = Frame.parse(aspect, res)
        assert (f.width, f.height) == size == fo.frame_size(aspect, res) and Frame.from_size(*size) is f
    assert Frame.parse("16:9", "720p").scale_factor == 720 / 1080 and Frame.parse("16:9", "1080p").scale_factor == 1.0


def test_parse_accepts_4k_spellings_and_unknown_still_means_1080p():
    for r in ("2160p", "2160", 2160, "4k", "4K", "uhd"):
        assert Frame.parse("16:9", r).resolution == "2160p"
    assert Frame.parse("16:9", "8k").resolution == "1080p" and Frame.parse(None, None) == Frame("16:9", "1080p")
    assert Frame.from_size(3000, 1700).resolution == "2160p" and Frame.from_size(2000, 1100).resolution == "1080p" and Frame.from_size(1000, 600).resolution == "720p"


# ---------- the renderer ----------
def _tl(res, scenes=None, dur=1.0, aspect="16:9"):
    fr = Frame.parse(aspect, res)
    scenes = scenes or [{"id": "a", "start": 0, "duration": dur, "type": "title", "props": {"title": "Four K"}, "words": [["Four", 0.1, 0.4], ["K", 0.4, 0.8]], "transition": "none"}]
    return {"width": fr.width, "height": fr.height, "fps": 30, "theme": "midnight", "captions": True, "scenes": scenes, "duration": dur, "outro": False,
            "frame": {"aspect": aspect, "resolution": res}}


def test_supersampling_and_output_size_by_resolution():
    r4 = Renderer(_tl("2160p"))
    assert (r4.ss, r4.out_w, r4.out_h, r4.big) == (4, 3840, 2160, True)          # 4x canvas reduced 2x: the same 2x2 samples per output pixel as 1080p
    for res, size in (("1080p", (1920, 1080)), ("720p", (1280, 720))):
        r = Renderer(_tl(res))
        assert (r.ss, (r.out_w, r.out_h), r.big) == (2, size, False)
    d = Renderer(_tl("2160p"), draft=True)
    assert (d.ss, d.out_w, d.out_h) == (1, 960, 540)                             # a preview of a 4K video is the same small draft as a 1080p one
    assert (Renderer(_tl("2160p", aspect="4:5"), draft=True).out_w, Renderer(_tl("2160p", aspect="4:5"), draft=True).out_h) == (540, 674)
    assert Renderer(_tl("2160p", aspect="9:16")).frame_at(0.5).size == (2160, 3840)


def _crispness(im):
    """Mean second difference of the luminance: large for one-pixel edges, near zero for smooth or enlarged content."""
    a = np.asarray(im.convert("L"), np.float32)
    return float(np.abs(a[:, 2:] - 2 * a[:, 1:-1] + a[:, :-2]).mean() + np.abs(a[2:] - 2 * a[1:-1] + a[:-2]).mean())


def test_a_4k_frame_is_the_1080p_frame_with_more_pixels():
    """Same layout, drawn natively (never an enlarged 1080p bitmap): reduced 2x it matches the 1080p frame, and it holds detail the 1080p frame cannot."""
    words = [["Hello", 0.2, 0.6], ["there", 0.6, 1.0]]
    for name in ("bullets_cards", "chart_line", "image"):
        stype, props = fs.sample(name)
        ims = {}
        for res in ("1080p", "2160p"):
            r, sc = make_renderer(stype, copy.deepcopy(props), 6.0, "midnight", words, True, fs.image_loader, False, "16:9", res, fs.clip_loader)
            ims[res] = r.frame_at(5.5)
        assert ims["2160p"].size == (3840, 2160) and ims["1080p"].size == (1920, 1080)
        diff = float(np.abs(np.asarray(ims["2160p"].reduce(2), np.int16) - np.asarray(ims["1080p"], np.int16)).mean())
        assert diff < 1.5, (name, diff)
        if name != "image":   # text and shapes: crisper edges than the 1080p frame enlarged to 4K can have (the sample photo itself is small, so it gains nothing)
            sharp, soft = _crispness(ims["2160p"]), _crispness(ims["1080p"].resize((3840, 2160), Image.BICUBIC))
            assert sharp > soft * 1.25, (name, sharp, soft)


def test_4k_shape_edges_are_antialiased():
    """Pillow's shapes have no anti-aliasing of their own: at 4K too every frame must come from a supersampled canvas (edge pixels with in-between values)."""
    from engine import scenes

    scenes.SCENES["__disc__"] = (lambda cv, props, lt, dur, th, ctx: cv.ellipse(960, 540, 300, 300, fill=(255, 255, 255, 255)), lambda p, d: [])
    try:
        got = {}
        for res in ("1080p", "2160p"):
            r, sc = make_renderer("__disc__", {}, 2.0, "midnight", [], False, None, False, "16:9", res)
            a = np.asarray(r.frame_at(1.0).convert("L"), np.int16)
            k = a.shape[0] // 1080
            edge = a[(540 - 320) * k:(540 + 320) * k, (960 - 320) * k:(960 + 320) * k]
            got[res] = int(((edge > 120) & (edge < 235)).sum()) / k   # pixels between the background and the white disc, per unit of edge length
    finally:
        scenes.SCENES.pop("__disc__", None)
    assert got["2160p"] > 500 and got["2160p"] > got["1080p"] * 0.8, got   # as many in-between edge pixels per length as at 1080p (an unsmoothed disc has none)


def test_4k_photo_fill_equals_one_resample_to_the_output_size():
    from engine.scenes import viz_scenes

    src = fs.synth_image("photo#1")
    box = (10.5, 20.25, 1500.0, 858.0)
    out = viz_scenes._fill(src, 7680, 4320, box, 4)
    assert out.size == (7680, 4320) and out.reduce(2).tobytes() == src.resize((3840, 2160), Image.BILINEAR, box=box).tobytes()
    assert viz_scenes._fill(src, 3840, 2160, box, 2).tobytes() == src.resize((3840, 2160), Image.BILINEAR, box=box).tobytes()   # 1080p: exactly the old call


# ---------- encoding ----------
def test_encoder_settings_are_unchanged_up_to_1080p_and_4k_has_its_own():
    for (w, h) in OLD_PIXELS.values():
        assert media.encode_settings(w, h) == {"crf": 20, "preset": "veryfast", "extra": []}
        assert media.encode_settings(w, h, draft=True) == {"crf": 28, "preset": "ultrafast", "extra": []}
    for (w, h) in PIXELS_4K.values():
        e = media.encode_settings(w, h)
        assert e["crf"] == 21 and e["preset"] == "veryfast" and e["extra"][:4] == ["-profile:v", "high", "-level:v", "5.1"] and "-maxrate" in e["extra"] and "-bufsize" in e["extra"]
        assert w * h // 256 <= 36864   # macroblocks per frame allowed by H.264 level 5.1


def test_the_1080p_encode_command_is_exactly_the_old_one(monkeypatch):
    from tests.test_create_options import _Popen

    monkeypatch.setattr(media.subprocess, "Popen", _Popen)
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: "ffmpeg")
    _Popen.cmds.clear()
    media.encode_segment([b"x"], "/tmp/o.ts", width=1920, height=1080, fps=30, start_time=0.0, gop=60)
    assert _Popen.cmds[0] == ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "30", "-i", "-",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-bf", "2",
                              "-x264-params", "open-gop=0", "-threads", "0", "-output_ts_offset", "0.000000", "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "/tmp/o.ts"]
    seen = {}
    monkeypatch.setattr(media, "encode_segment", lambda frames, out, **kw: seen.update(kw) or 0)
    pipeline.render_chunk(_tl("1080p"), 0, 3, "/tmp/x.ts")
    assert (seen["crf"], seen["preset"], list(seen["extra"])) == (20, "veryfast", [])
    pipeline.render_chunk(_tl("2160p"), 0, 3, "/tmp/x.ts")
    assert (seen["width"], seen["height"], seen["crf"]) == (3840, 2160, 21) and "5.1" in seen["extra"]
    pipeline.render_chunk(_tl("2160p"), 0, 3, "/tmp/x.ts", draft=True)
    assert (seen["width"], seen["height"], seen["crf"], seen["preset"], list(seen["extra"])) == (960, 540, 28, "ultrafast", [])


def _probe(path):
    return subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True).stderr


def test_render_a_real_4k_mp4(tmp_path):
    """A few frames through the real pipeline: two pieces of one chunk, stitched into an MP4 that really is 3840x2160 H.264 High, yuv420p."""
    scenes = [{"id": "a", "start": 0, "duration": 0.2, "type": "title", "props": {"title": "Four K"}, "words": [["Four", 0.0, 0.1], ["K", 0.1, 0.2]], "transition": "none"},
              {"id": "b", "start": 0.2, "duration": 0.2, "type": "stat", "props": {"value": "3840", "label": "pixels across"}, "words": [], "transition": "fade"}]
    tl = _tl("2160p", scenes, dur=0.4)
    chunks = chunk_plan(tl, 6, max_frames=6)
    assert [(c.get("f0"), c["frames"]) for c in chunks] == [(0, 6), (6, 6)]
    paths = []
    for c in chunks:
        p = str(tmp_path / f"seg_{c['k']}.ts")
        assert pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), c["f0"], c["f0"] + c["frames"], p)["frames"] == c["frames"]
        paths.append(p)
    mp4 = str(tmp_path / "out.mp4")
    media.mux_final(paths, None, mp4, fps=30)
    info = _probe(mp4)
    assert "3840x2160" in info and "h264 (High)" in info and "yuv420p" in info, info
    assert abs(media.ffprobe_duration(mp4) - 0.4) < 0.1
    png = str(tmp_path / "f.png")
    media.extract_frame(mp4, 0.1, png)
    assert Image.open(png).size == (3840, 2160)


# ---------- chunks ----------
def _long_tl(res="2160p"):
    scenes, t = [], 0.0
    for i, d in enumerate((3.0, 22.0, 4.0, 2.5, 9.0)):
        scenes.append({"id": f"s{i}", "start": t, "duration": d, "type": "title", "props": {"title": f"Scene {i}"}, "words": [], "transition": "fade"})
        t += d
    return _tl(res, scenes, dur=t)


def test_chunk_plan_without_a_limit_is_exactly_the_old_plan():
    tl = _long_tl("1080p")
    assert chunk_plan(tl, 10) == chunk_plan(tl, 10, max_frames=0) == chunk_plan(tl, 10, False, 0)
    assert all("f0" not in c for c in chunk_plan(tl, 10)) and [c["k"] for c in chunk_plan(tl, 10)] == list(range(len(chunk_plan(tl, 10))))


def test_4k_chunks_are_cut_into_pieces_that_cover_every_frame_once():
    tl = _long_tl()
    whole, pieces = chunk_plan(tl, 6), chunk_plan(tl, 6, max_frames=180)
    assert sum(c["frames"] for c in pieces) == sum(c["frames"] for c in whole) == round(tl["duration"] * 30)
    assert max(c["frames"] for c in pieces) <= 180 < max(c["frames"] for c in whole)
    assert [c["k"] for c in pieces] == list(range(len(pieces))) and len({c["hash"] for c in pieces}) == len(pieces)
    for g in whole:   # the pieces of one group follow each other without a gap
        mine = [c for c in pieces if (c["lo"], c["hi"]) == (g["lo"], g["hi"])]
        assert sum(c["frames"] for c in mine) == g["frames"]
        if len(mine) > 1:
            pos = 0
            for c in mine:
                assert c["f0"] == pos and min(x["frames"] for x in mine) >= max(x["frames"] for x in mine) - 1   # even pieces
                pos += c["frames"]
        else:
            assert mine[0] == {**g, "k": mine[0]["k"]}
    assert chunk_plan(tl, 6, max_frames=180) == pieces   # stable: an edit that leaves a group alone reuses its pieces


def test_the_timeline_step_uses_short_chunks_for_4k_only(monkeypatch):
    plan4 = _plan(fo.frame_dict("16:9", "2160p"))
    tl, out = _run_timeline(monkeypatch, plan4)
    assert (tl["width"], tl["height"]) == (3840, 2160)
    assert [{k: c[k] for k in c if k not in ("video_id", "timeline_key")} for c in out["chunks"]] == chunk_plan(tl, timeline_handler.CHUNK_SECONDS_4K, max_frames=timeline_handler.CHUNK_MAX_FRAMES_4K)
    assert max(c["frames"] for c in out["chunks"]) <= timeline_handler.CHUNK_MAX_FRAMES_4K == 180 and timeline_handler.CHUNK_SECONDS_4K == 6
    tl2, prev = _run_timeline(monkeypatch, plan4, mode="preview")       # a preview of a 4K video: ordinary draft chunks
    assert all(c["draft"] and "f0" not in c for c in prev["chunks"]) and [c["hash"] for c in prev["chunks"]] == [c["hash"] for c in chunk_plan(tl2, timeline_handler.CHUNK_SECONDS, draft=True)]
    tl3, hd = _run_timeline(monkeypatch, _plan(fo.frame_dict("16:9", "1080p")))
    assert [{k: c[k] for k in c if k not in ("video_id", "timeline_key")} for c in hd["chunks"]] == chunk_plan(tl3, timeline_handler.CHUNK_SECONDS)   # 1080p: as always
    assert not {c["hash"] for c in out["chunks"]} & {c["hash"] for c in hd["chunks"]}


def test_the_render_function_renders_its_piece(monkeypatch):
    tl = _long_tl()
    seen = {}
    monkeypatch.setattr(awsio, "head", lambda k: None)
    monkeypatch.setattr(awsio, "get_json", lambda k: tl)
    monkeypatch.setattr(awsio, "upload", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "render_chunk", lambda ct, f0, f1, out, loader, **kw: seen.update(f0=f0, f1=f1, scenes=len(ct["scenes"])) or {"frames": f1 - f0})
    c = next(c for c in chunk_plan(tl, 6, max_frames=180) if c.get("f0"))
    out = render_chunk_handler.handler({**c, "video_id": "v1", "timeline_key": "generation/v2/v1/timeline_r1.json"}, None)
    assert (seen["f0"], seen["f1"]) == (c["f0"], c["f0"] + c["frames"]) and out["frames"] == c["frames"] and out["k"] == c["k"]
    whole = chunk_plan(_long_tl("1080p"), 10)[0]
    render_chunk_handler.handler({**whole, "video_id": "v1", "timeline_key": "generation/v2/v1/timeline_r1.json"}, None)
    assert (seen["f0"], seen["f1"]) == (0, whole["frames"])   # every other chunk: from its first frame, as before


def test_a_4k_chunk_starts_with_empty_picture_caches(monkeypatch):
    from engine import canvas, renderer
    from engine.scenes import style_kit

    r, sc = make_renderer(*fs.sample("bullets_cards"), 6.0, "midnight", [], False, None, True, "16:9", "1080p")
    r.frame_at(3.0)
    assert style_kit.rr_sprite.cache_info().currsize > 0 and canvas._BG_CACHE
    clips._CACHE["pixabay:kept"] = (0.0, {})
    assert renderer.release_caches() > 5
    assert style_kit.rr_sprite.cache_info().currsize == 0 and not canvas._BG_CACHE and "pixabay:kept" in clips._CACHE   # pictures gone, a provider's search results kept
    clips._CACHE.clear()
    calls = []
    monkeypatch.setattr(renderer, "release_caches", lambda: calls.append(1) or 0)
    monkeypatch.setattr(awsio, "head", lambda k: None)
    monkeypatch.setattr(awsio, "upload", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "render_chunk", lambda ct, f0, f1, out, loader, **kw: {"frames": f1 - f0})
    for res, draft, want in (("2160p", False, 1), ("2160p", True, 1), ("1080p", False, 1)):   # only a final 4K chunk empties them
        tl = _long_tl(res)
        monkeypatch.setattr(awsio, "get_json", lambda k, tl=tl: tl)
        c = chunk_plan(tl, 6, draft=draft)[0]
        render_chunk_handler.handler({**c, "video_id": "v1", "timeline_key": "generation/v2/v1/timeline_r1.json"}, None)
        assert len(calls) == want, (res, draft)


# ---------- sharp sources ----------
def _jpeg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 120, 150)).save(buf, "JPEG", quality=70)
    return buf.getvalue()


def test_photo_size_tiers():
    raw = _jpeg(6000, 4000)
    assert assets.to_jpeg(raw)[1] == (2800, 1866) and assets.max_side_for(False) == 2800           # 720p and 1080p videos: as always
    assert assets.to_jpeg(raw, max_side=assets.max_side_for(True))[1] == (4400, 2933)              # 4K: 3840 across plus the push-in, never enlarged in the frame
    assert assets.to_jpeg(_jpeg(3000, 2000), max_side=assets.max_side_for(True))[1] == (3000, 2000)   # a smaller original is kept as it is, not enlarged in storage
    assert usermedia.normalize(raw)[2]["w"] == 2048 and usermedia.normalize(raw, usermedia.MAX_SIDE_4K)[2]["w"] == 4096


def test_unsplash_is_asked_for_a_larger_picture_only_for_4k():
    row = {"id": "p1", "width": 6000, "height": 4000, "urls": {"raw": "https://images.unsplash.com/photo-1?ixid=abc", "small": "https://images.unsplash.com/s"},
           "user": {"name": "Ann", "username": "ann", "links": {"html": "https://unsplash.com/@ann"}}, "links": {"html": "https://unsplash.com/photos/p1", "download_location": "https://api.unsplash.com/dl"}}
    fetch = lambda url, **kw: {"results": [row]}   # noqa: E731
    assert "w=2400&" in stock.unsplash_search("sea", "k", fetch)[0]["full_url"]
    assert "w=4400&" in stock.unsplash_search("sea", "k", fetch, big=True)[0]["full_url"] and "ixid=abc" in stock.unsplash_search("sea", "k", fetch, big=True)[0]["full_url"]


def test_scouting_a_photo_keeps_the_larger_size_only_for_4k():
    cand = {"provider": "openverse", "id": "1", "thumb_url": "https://x/t.jpg", "full_url": "https://x/f.jpg", "width": 6000, "height": 4000, "creator": "A", "license": "CC0"}
    kw = dict(fetch_json_fn=lambda *a, **k: {"results": []}, fetch_bytes_fn=lambda url, **k: _jpeg(6000, 4000), review=None)
    orig = stock.gather
    try:
        seen = []
        stock.gather = lambda q, **k: seen.append(k) or [cand]
        small = stock.scout_reviewed("sea", "the sea", **kw)
        big = stock.scout_reviewed("sea", "the sea", big=True, **kw)
    finally:
        stock.gather = orig
    assert Image.open(io.BytesIO(small["jpeg"])).size == (2800, 1866) and Image.open(io.BytesIO(big["jpeg"])).size == (4400, 2933)
    assert "big" not in seen[0] and seen[1]["big"] is True   # the 1080p call is exactly the old call


def test_the_beat_step_asks_for_larger_sources_only_for_4k(monkeypatch):
    seen = {"clip": [], "photo": []}
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "")
    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda q, ctx, alt, **kw: seen["clip"].append(kw) or None)
    monkeypatch.setattr(beat_handler.stock, "scout_reviewed", lambda q, ctx, alt, **kw: seen["photo"].append(kw) or None)
    monkeypatch.setattr(awsio, "put_json", lambda *a, **k: None)
    beat = {"id": "b1", "narration": "Waves roll in.", "scene": {"type": "clip", "props": {"clip_query": "ocean waves", "alt": "ocean waves"}}}
    for res in ("1080p", "2160p"):
        beat_handler.make_clip({"frame": fo.frame_dict("16:9", res)}, beat, "v1", "cost_usd", 4.0)
    assert "hd" not in seen["clip"][0] and seen["clip"][1]["hd"] is True
    assert "big" not in seen["photo"][0] and seen["photo"][1]["big"] is True     # the still that stands in when no clip is found
    beat_handler.make_clip({"frame": fo.frame_dict("9:16", "2160p")}, beat, "v1", "cost_usd", 4.0)
    assert seen["clip"][2]["hd"] is True and seen["clip"][2]["orientation"] == "portrait"
    beat_handler.make_clip({}, beat, "v1", "cost_usd", 4.0)                        # an old plan without a frame
    assert "hd" not in seen["clip"][3] and "big" not in seen["photo"][3]


def test_clip_sizes_and_the_transcode_command(monkeypatch):
    assert clips.ORIENTATIONS == {"landscape": (1280, 720), "portrait": (720, 1280), "square": (720, 720)}   # unchanged
    assert [clips.clip_size(o, True) for o in ("landscape", "portrait", "square")] == [(1920, 1080), (1080, 1920), (1080, 1080)]
    assert clips.clip_size("landscape") == (1280, 720) and clips.clip_size("weird", True) == (1920, 1080)
    cmds = []

    def run(cmd, **kw):
        cmds.append(cmd)
        open(cmd[-1], "wb").write(b"x" * 2000)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(clips.subprocess, "run", run)
    monkeypatch.setattr(clips.media, "ffmpeg_bin", lambda: "ffmpeg")
    monkeypatch.setattr(clips, "probe_size", lambda path: (1920, 1080))   # a 1080p source (a smaller one stays 1280x720 in a 4K video: tests/test_clip_framed_4k.py)
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "fourk_clip_test.mp4")
    clips.transcode("in.mp4", out, start=1.0, seconds=5.0)
    clips.transcode("in.mp4", out, start=1.0, seconds=5.0, hd=True)
    clips.transcode("in.mp4", out, start=1.0, seconds=5.0, orientation="portrait", hd=True)
    os.unlink(out)
    vf = [c[c.index("-vf") + 1] for c in cmds]
    assert vf[0].startswith("scale=1280:720:") and "crop=1280:720" in vf[0] and cmds[0][cmds[0].index("-crf") + 1] == "26"
    assert vf[1].startswith("scale=1920:1080:") and "crop=1920:1080" in vf[1] and cmds[1][cmds[1].index("-crf") + 1] == "23"
    assert "crop=1080:1920" in vf[2]


def test_stock_libraries_are_asked_for_a_1080p_file_only_for_4k():
    files = [{"file_type": "video/mp4", "link": f"https://v.pexels.com/{w}.mp4", "width": w, "height": w * 9 // 16} for w in (960, 1280, 1920, 2560, 3840)]
    data = {"videos": [{"id": 1, "width": 3840, "height": 2160, "duration": 20, "image": "https://i.pexels.com/1.jpg", "url": "https://www.pexels.com/video/sea-1/", "user": {"name": "A"},
                        "video_files": files}]}
    fetch = lambda url, **kw: data   # noqa: E731
    assert clips.pexels_search("sea", "k", fetch)[0]["video_url"].endswith("/1920.mp4")
    assert clips.pexels_search("sea", "k", fetch, hd=True)[0]["video_url"].endswith("/1920.mp4")
    data["videos"][0]["video_files"] = [f for f in files if f["width"] != 1920]
    assert clips.pexels_search("sea", "k", fetch)[0]["video_url"].endswith("/1280.mp4")          # as before
    assert clips.pexels_search("sea", "k", fetch, hd=True)[0]["video_url"].endswith("/2560.mp4")  # 4K: at least 1080p
    hit = {"id": 7, "duration": 30, "user": "B", "user_id": 3, "pageURL": "https://pixabay.com/videos/id-7/", "tags": "sea",
           "videos": {n: {"url": f"https://cdn.pixabay.com/video/{n}.mp4", "width": w, "height": w * 9 // 16, "size": s, "thumbnail": f"https://cdn.pixabay.com/video/{n}.jpg"}
                      for n, w, s in (("large", 3840, 90_000_000), ("medium", 1920, 9_000_000), ("small", 1280, 4_000_000), ("tiny", 960, 2_000_000))}}
    clips._CACHE.clear()
    assert clips.pixabay_search("sea 4k test", "k", lambda url, **kw: {"hits": [hit]})[0]["video_url"].endswith("/medium.mp4")
    hit["videos"]["medium"].update(width=1280, height=720)
    hit["videos"]["large"].update(width=1920, height=1080, size=20_000_000)
    clips._CACHE.clear()
    assert clips.pixabay_search("sea 4k test", "k", lambda url, **kw: {"hits": [hit]})[0]["video_url"].endswith("/medium.mp4")            # 720p file, as before
    assert clips.pixabay_search("sea 4k test", "k", lambda url, **kw: {"hits": [hit]}, hd=True)[0]["video_url"].endswith("/large.mp4")  # 4K: the 1080p file
    clips._CACHE.clear()


def test_a_real_clip_is_normalised_to_1080p_for_4k(tmp_path):
    src, out = str(tmp_path / "src.mp4"), str(tmp_path / "hd.mp4")
    subprocess.run([media.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=3", "-pix_fmt", "yuv420p", src], check=True)
    clips.transcode(src, out, start=0.0, seconds=2.0, hd=True)
    frames = clips.ClipFrames(out)
    assert len(frames) == 60 and frames.frame(0).size == (1920, 1080) and frames.frame(999).size == (1920, 1080)
    assert sum(len(f) for f in frames.frames) < 60 * 1_500_000   # JPEG frames in memory stay far below raw size (6.2 MB each)


# ---------- the deploy flag, the API and the price ----------
def test_4k_is_off_by_default_and_refused_without_a_charge(launcher, monkeypatch):
    monkeypatch.delenv("READY_RESOLUTIONS", raising=False)
    assert fo.ready_resolutions() == ["720p", "1080p"]
    r = post(launcher, resolution="2160p")
    assert r["statusCode"] == 400 and json.loads(r["body"])["message"] == "This resolution is not available yet"
    assert launcher.fake.calls == [] and wallet.balance("u1")["balance"] == 5
    assert post(launcher, resolution="1080p")["statusCode"] == 202
    assert "'resolution' must be one of: 720p, 1080p, 2160p" in json.loads(post(launcher, resolution="4k")["body"])["message"]


def test_ready_resolutions_setting(monkeypatch):
    monkeypatch.setenv("READY_RESOLUTIONS", "1080p, 2160p, 8k")
    assert fo.ready_resolutions() == ["1080p", "2160p"]
    monkeypatch.setenv("READY_RESOLUTIONS", " ")
    assert fo.ready_resolutions() == ["720p", "1080p"]


def test_one_function_owns_the_price():
    assert [wallet.credits_for_minutes(m) for m in (0.2, 1, 1.01, 3, 12, 99)] == [1, 1, 2, 3, 12, 12]                       # unchanged
    assert [wallet.credits_for_minutes(m, "1080p") for m in (0.25, 3, 12)] == [wallet.credits_for_minutes(m, "720p") for m in (0.25, 3, 12)] == [1, 3, 12]
    assert [wallet.credits_for_minutes(m, "2160p") for m in (0.25, 1, 1.01, 3, 12)] == [2, 2, 4, 6, 24]                      # double, after rounding up to started minutes
    assert wallet.credits_for_minutes(3, "nonsense") == 3 and wallet.credits_for_minutes(3, None) == 3
    assert [fo.credits_multiplier(r) for r in ("720p", "1080p", "2160p", None, "x")] == [1, 1, 2, 1, 1] and fo.is_4k("2160p") and not fo.is_4k("1080p")


def test_a_4k_video_is_charged_double_and_recorded(launcher, aws, four_k):
    r = post(launcher, resolution="2160p", platform="youtube")
    assert r["statusCode"] == 202 and wallet.balance("u1")["balance"] == 3          # 1 minute at 4K: 2 of the 5 welcome credits
    s = sent(launcher)
    assert (s["resolution"], s["target_minutes"]) == ("2160p", 1)
    item = aws.Table("Videos").get_item(Key={"video_id": s["video_id"]})["Item"]
    assert int(item["credits_charged"]) == 2 and item["resolution"] == "2160p" and int(item["credits_multiplier"]) == 2
    assert sum(int(x["n"]) for x in json.loads(item["charge"])) == 2
    assert wallet.refund_video(item) == 2 and wallet.balance("u1")["balance"] == 5   # a failed 4K video gives back all of the doubled amount
    assert wallet.refund_video(aws.Table("Videos").get_item(Key={"video_id": s["video_id"]})["Item"]) == 0   # once


def test_a_1080p_video_is_recorded_exactly_as_before(launcher, aws, four_k):
    assert post(launcher, resolution="1080p")["statusCode"] == 202 and wallet.balance("u1")["balance"] == 4
    item = aws.Table("Videos").get_item(Key={"video_id": sent(launcher)["video_id"]})["Item"]
    assert int(item["credits_charged"]) == 1 and "credits_multiplier" not in item and "resolution" not in item


def test_not_enough_credits_for_4k_says_the_doubled_amount(launcher, four_k):
    r = launcher.handler(_event(body={"prompt": "A short explainer about how black holes form", "target_minutes": 3, "resolution": "2160p"}), None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 402 and body == {"message": "This video needs 6 credits and you have 5.", "code": "insufficient_credits", "balance": 5, "needed": 6,
                                               "resolution": "2160p", "credits_multiplier": 2}
    assert launcher.fake.calls == [] and wallet.balance("u1")["balance"] == 5
    r = launcher.handler(_event(body={"prompt": "A short explainer about how black holes form", "target_minutes": 6}), None)   # 1080p: the old body, no new keys
    assert json.loads(r["body"]) == {"message": "This video needs 6 credits and you have 5.", "code": "insufficient_credits", "balance": 5, "needed": 6}


def test_a_failed_start_refunds_the_doubled_amount(launcher, four_k, monkeypatch):
    def boom(**kw):
        raise RuntimeError("no workflow")

    monkeypatch.setattr(launcher.fake, "start_execution", boom)
    assert post(launcher, resolution="2160p")["statusCode"] == 500 and wallet.balance("u1")["balance"] == 5


def test_4k_is_accepted_for_any_platform_and_any_ready_aspect(launcher, four_k, monkeypatch):
    """The server only recommends (capabilities.supports_4k); it never refuses a platform. The aspect must be ready, like at every resolution."""
    wallet.give_credits("u1", 20)
    assert post(launcher, resolution="2160p", platform="tiktok")["statusCode"] == 202
    r = post(launcher, resolution="2160p", aspect="9:16")
    assert r["statusCode"] == 400 and json.loads(r["body"])["message"] == "This format is not available yet"
    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16")
    assert post(launcher, resolution="2160p", aspect="9:16", platform="shorts")["statusCode"] == 202 and sent(launcher)["resolution"] == "2160p"


def test_capabilities_without_4k_list_only_the_two_resolutions(monkeypatch):
    for k in ("READY_ASPECTS", "READY_RESOLUTIONS"):
        monkeypatch.delenv(k, raising=False)
    c = fo.capabilities()
    assert c["resolutions"] == [{"id": "720p", "label": "720p", "credits_multiplier": 1, "aspects": ["16:9"]}, {"id": "1080p", "label": "1080p", "credits_multiplier": 1, "aspects": ["16:9"]}]
    assert {p["id"] for p in c["platforms"] if p["supports_4k"]} == {"youtube", "other"}   # the platform facts are always there


def test_capabilities_with_4k(four_k, monkeypatch):
    import capabilities_api

    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16")
    body = json.loads(capabilities_api.handler(cap_event(), None)["body"])
    assert body["resolutions"][2] == {"id": "2160p", "label": "4K", "credits_multiplier": 2, "aspects": ["16:9", "9:16"],
                                      "note": "4K (2160p) costs twice the credits. Best for YouTube and large screens."}
    assert [r["id"] for r in body["resolutions"]] == ["720p", "1080p", "2160p"] and all(r["credits_multiplier"] == wallet.credits_for_minutes(1, r["id"]) for r in body["resolutions"])
    plat = {p["id"]: p for p in body["platforms"]}
    assert {k for k, p in plat.items() if p["supports_4k"]} == {"youtube", "other"} and plat["youtube"]["note_4k"] is None and plat["other"]["note_4k"] is None
    assert plat["tiktok"]["note_4k"] == "TikTok publishes at 1080p or lower; 4K would cost twice the credits for no visible gain."
    for pid in ("shorts", "tiktok", "reels", "instagram_feed", "linkedin", "x"):
        assert plat[pid]["supports_4k"] is False and plat[pid]["label"] in plat[pid]["note_4k"] and "twice the credits" in plat[pid]["note_4k"]
    assert all(p["resolution"] == "1080p" for p in plat.values())   # the recommendation stays 1080p everywhere: 4K is the person's own choice


def test_what_capabilities_lists_the_launcher_accepts(launcher, monkeypatch):
    wallet.give_credits("u1", 20)
    for setting in ("720p,1080p", "720p,1080p,2160p", "1080p"):
        monkeypatch.setenv("READY_RESOLUTIONS", setting)
        listed = [r["id"] for r in fo.capabilities()["resolutions"]]
        for res in fo.RESOLUTION_IDS:
            r = launcher.handler(_event(body={"prompt": f"A short explainer about black holes at {res} with {setting}", "target_minutes": 1, "resolution": res}), None)
            assert (r["statusCode"] == 202) == (res in listed), (setting, res)


def test_an_edit_keeps_4k_and_costs_no_credits(monkeypatch):
    from engine import edits

    plan = _plan(fo.frame_dict("16:9", "2160p", "youtube"))
    new, _ = edits.apply_ops(plan, [{"op": "set_meta", "theme": "paper"}])
    assert new["frame"] == plan["frame"]
    tl, out = _run_timeline(monkeypatch, new, rev=2)
    assert (tl["width"], tl["height"], tl["frame"]["resolution"]) == (3840, 2160, "2160p") and all(not c["draft"] for c in out["chunks"])
    import engine.handlers.editor_apply as editor_apply
    assert "wallet" not in vars(editor_apply)   # the edit route never touches credits: a re-render of a 4K video is free like any other edit
