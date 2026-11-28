"""The watermark is an independent layer applied at the very end (docs/WATERMARK_DECOUPLED_2026-11-28.md, owner requirement 2026-11-28): nothing that makes a video knows about it.

Proofs: scene frames and whiteboard scores are byte-identical whatever the watermark; segment cache keys, the plan and the timeline's scene times do not carry it; captions and content bands are the
pre-watermark ones in every shape; the final stage (engine/final_stage.py, real ffmpeg) draws the lockup over a finished master at 720p / 1080p / 2160p, appends the closing card as the only added
duration, and the same video without the watermark is the master itself, with no scene re-rendered."""
import json
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("WHITEBOARD_DIR", os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard"))

from common import watermark_store as store  # noqa: E402
from engine import final_stage as fs, media, pipeline, watermark_spec as ws  # noqa: E402
from engine.frame import ASPECTS, Frame  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.timeline import build_timeline, chunk_plan, chunk_timeline  # noqa: E402
from engine.whiteboard import score  # noqa: E402

WORDS = [["This", 0.2, 0.5], ["is", 0.5, 0.7], ["a", 0.7, 0.9], ["caption", 0.9, 1.4], ["line", 1.4, 1.8]]
LIST = {"heading": "Lighthouse facts", "items": ["Warn of rocks and reefs", "Guide ships into harbors", "Fewer shine today"]}
WB = ELEMENTS["whiteboard"].sanitize(ELEMENTS["whiteboard"].samples[0])
LOGO_SPEC = {"mode": "custom", "asset": "generation/v2/v/assets/watermark.png", "hash": "abc", "opacity": 1.0, "position": "br"}
MODES = {
    "absent": None,
    "none": {"mode": "none"},
    "forced": store.FORCED_SPEC,
    "test-account default": {"mode": "videomk", "style": "lockup", "presence": "always", "end_card": True, "position": "auto", "size": "small", "opacity": ws.DEFAULT_OPACITY},
    "custom": LOGO_SPEC,
    "moments": {"mode": "videomk", "style": "lockup", "presence": "moments", "windows": [[0.5, 5.7]], "size": "medium", "position": "tl", "opacity": 0.5},
}


def _png(w=300, h=120, color=(220, 30, 40, 255)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w - 40, h - 20), color), (20, 10))
    return im


def _photo(key):
    return Image.new("RGB", (800, 600), (200, 170, 120))


def _tl(aspect="16:9", resolution="1080p", theme="midnight", watermark=None, captions=True, scene="title", props=None, dur=6.0, words=None, outro=False):
    fr = Frame.parse(aspect, resolution)
    sc = {"id": "t", "type": scene, "start": 0.0, "duration": dur, "props": props or {"title": "A calm title", "subtitle": "with a subtitle"}, "words": WORDS if words is None else words, "transition": "none"}
    tl = {"scenes": [sc], "theme": theme, "captions": captions, "duration": dur, "width": fr.width, "height": fr.height, "fps": 30, "outro": outro, "frame": {"aspect": aspect, "resolution": resolution}}
    if watermark is not None:
        tl["watermark"] = watermark
    return tl


LOOKS = {   # scene, props, theme: a title, a list, a whiteboard board, a photo and a light theme
    "title-dark": ("title", None, "midnight"), "list-light": ("bullets", LIST, "paper"), "whiteboard": ("whiteboard", WB, "paper"), "photo": ("image", {"asset": "k", "alt": "A photo"}, "midnight"),
}


# ======================================================================== scenes know nothing of the watermark
@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("look", sorted(LOOKS))
def test_scene_frames_are_byte_identical_with_any_watermark(aspect, look):
    scene, props, theme = LOOKS[look]
    frames = {}
    for name, spec in MODES.items():
        tl = _tl(aspect, theme=theme, scene=scene, props=props, watermark=spec)
        r = Renderer(tl, image_loader=_photo, draft=True)
        assert not hasattr(r, "wm")
        frames[name] = [r.frame_at(t).tobytes() for t in (0.3, 2.5)] + [r._draw_spec(r.scenes[0], 2.5).tobytes()]
    base = frames["absent"]
    assert all(v == base for v in frames.values()), [k for k, v in frames.items() if v != base]


def test_a_full_size_frame_is_identical_too():
    a = Renderer(_tl("9:16", "720p", watermark=None), draft=False).frame_at(1.2).tobytes()
    b = Renderer(_tl("9:16", "720p", watermark=store.FORCED_SPEC), draft=False).frame_at(1.2).tobytes()
    assert a == b


def test_whiteboard_scores_and_plans_are_identical_with_and_without_a_watermark():
    from tests.test_whiteboard_score import FULL, SPARSE, beat
    out = {}
    for name, spec in MODES.items():
        plan = {"beats": [beat(FULL), beat(SPARSE)], **({"watermark": spec} if spec else {})}
        out[name] = json.dumps(score.score_plan(plan), sort_keys=True, default=str)
    assert len(set(out.values())) == 1, out.keys()


@pytest.mark.parametrize("aspect", ASPECTS)
def test_captions_and_content_bands_are_the_pre_watermark_ones_in_every_shape(aspect):
    f = Frame.parse(aspect)
    want_caption = {"16:9": 1010, "9:16": 1600, "1:1": 1020, "4:5": 1290}[aspect]
    want_top = {"16:9": 70, "9:16": 310, "1:1": 150, "4:5": 150}[aspect]   # a constant of the shape, just under the lowest the corner mark reaches; the same for every account, it does not follow the mark
    assert f.caption["bottom"] == want_caption and f.margin_top == want_top and f.box(True)[1] == want_top
    for spec in MODES.values():
        r = Renderer(_tl(aspect, watermark=spec), draft=True)
        assert r.frame == f and r.ctx.frame == f and r.ctx.top == want_top and r.frame.caption["bottom"] == want_caption


def test_nothing_in_the_engine_but_the_final_stage_reads_the_watermark():
    root = os.path.join(os.path.dirname(__file__), "..", "lambdas", "engine")
    allowed = {"final_stage.py", "watermark.py", "watermark_spec.py", "timeline.py", "cover.py"}   # the timeline only copies the spec (and its moments) through; cover pops it
    offenders = []
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py") and fn not in allowed and base.replace(root, "") in ("", "/handlers", "/scenes", "/scenes/elements"):
                src = open(os.path.join(base, fn), encoding="utf-8").read()
                if any(w in src for w in ("watermark_mod", "watermark_spec", "top_inset", "cap_lift", "wmv", "end_card")):
                    offenders.append(fn)
    assert offenders == ["plan_handler.py"], offenders   # the plan step only stores the option (finalize_handler calls the final stage by name)
    assert "final_stage.export" in open(os.path.join(root, "handlers", "finalize_handler.py"), encoding="utf-8").read()


# ======================================================================== plan, timeline and cache keys
def _plan(n=6, wm=None):
    beats = [{"id": f"b{i}", "narration": "one two three four five six seven eight", "scene": {"type": "title", "props": {"title": "Tides", "subtitle": ""}}} for i in range(n)]
    return {"title": "T", "language": "en", "theme": "midnight", "beats": beats, **({"watermark": wm} if wm else {})}


def test_segment_keys_scene_times_and_the_length_fit_do_not_depend_on_the_watermark():
    infos = [{"duration": 5.0}] * 6
    base = build_timeline(_plan(), infos, video_id="v", min_seconds=30, fit_seconds=30)
    for name, spec in MODES.items():
        wm = None if spec is None or spec["mode"] == "none" else spec
        tl = build_timeline(_plan(wm=wm), infos, video_id="v", min_seconds=30, fit_seconds=30)
        assert [(s["id"], s["start"], s["duration"], s["props"]) for s in tl["scenes"]] == [(s["id"], s["start"], s["duration"], s["props"]) for s in base["scenes"]], name
        assert tl["duration"] == base["duration"] and tl.get("pace") == base.get("pace"), name
        assert [c["hash"] for c in chunk_plan(tl, 10)] == [c["hash"] for c in chunk_plan(base, 10)], name
        assert [c["hash"] for c in chunk_plan(tl, 10, draft=True)] == [c["hash"] for c in chunk_plan(base, 10, draft=True)], name
        for c in chunk_plan(tl, 10):
            assert json.dumps(chunk_timeline(tl, c["lo"], c["hi"]), sort_keys=True) == json.dumps(chunk_timeline(base, c["lo"], c["hi"]), sort_keys=True), name


def test_the_director_and_the_plan_step_no_longer_hear_about_the_end_card():
    root = os.path.join(os.path.dirname(__file__), "..", "lambdas", "engine")
    assert "end_card" not in open(os.path.join(root, "director.py"), encoding="utf-8").read()
    src = open(os.path.join(root, "handlers", "plan_handler.py"), encoding="utf-8").read()
    assert '"end_card": bool(' not in src   # the option is stored on the plan and nothing else: the script is written and fitted without it


# ======================================================================== the final stage (real ffmpeg)
def _audio(path, seconds):
    subprocess.run([media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-c:a", "aac", path], check=True)


def _master(tl, tmp, draft=True, audio=True):
    n = int(round(tl["duration"] * tl["fps"]))
    seg = os.path.join(tmp, "seg.ts")
    pipeline.render_chunk(tl, 0, n, seg, None, draft=draft)
    aud = None
    if audio:
        aud = os.path.join(tmp, "mix.m4a")
        _audio(aud, tl["duration"])
    mst = os.path.join(tmp, "master.mp4")
    media.mux_final([seg], aud, mst, fps=tl["fps"])
    return mst, aud


def _frame(path, t, tmp, name):
    p = os.path.join(tmp, name)
    media.extract_frame(path, t, p)
    return np.asarray(Image.open(p).convert("RGB"), np.int16)


def _bbox(a, b, thr=50, win=None):
    """Bounding box of the clearly changed pixels (re-encoding noise is below `thr`), looked for inside `win` = (x0, y0, x1, y1) when given."""
    d = np.abs(a - b).max(axis=2) > thr
    if win is not None:
        m = np.zeros_like(d)
        m[max(0, int(win[1])):int(win[3]), max(0, int(win[0])):int(win[2])] = True
        d &= m
    ys, xs = np.where(d)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else None


def _win(spec, aspect, out_w, k=1.0):
    f = Frame.parse(aspect)
    scale = out_w / f.W
    x0, y0, x1, y1 = [v * scale for v in ws.layout(spec, f, None, True)["rect"]]
    h = y1 - y0
    return (x0 - k * h, y0 - k * h, x1 + k * h, y1 + k * h)


@pytest.mark.parametrize("aspect,resolution,draft", [("16:9", "720p", False), ("9:16", "1080p", True), ("1:1", "720p", True), ("4:5", "1080p", True)])
def test_the_final_stage_draws_the_lockup_where_the_layout_says_and_changes_nothing_else(tmp_path, aspect, resolution, draft):
    spec = {"mode": "videomk", "style": "lockup", "presence": "always", "opacity": 1.0}
    tl = _tl(aspect, resolution, theme="paper", watermark=spec, dur=4.0)
    mst, aud = _master(tl, str(tmp_path), draft=draft)
    out = str(tmp_path / "out.mp4")
    info = fs.export(tl, mst, aud, out, draft=draft, tmp=str(tmp_path))
    assert info["end_card"] is False and abs(media.ffprobe_duration(out) - media.ffprobe_duration(mst)) < 0.15   # no card asked: the same length
    a, b = _frame(mst, 2.0, str(tmp_path), "a.png"), _frame(out, 2.0, str(tmp_path), "b.png")
    r = Renderer(tl, draft=draft)
    scale = r.out_w / Frame.parse(aspect).W
    x0, y0, x1, y1 = [v * scale for v in ws.layout(spec, Frame.parse(aspect), None, True)["rect"]]
    box = _bbox(a, b, win=_win(spec, aspect, r.out_w))
    pad = 0.25 * (y1 - y0)
    assert box is not None and box[0] >= x0 - pad and box[1] >= y0 - pad and box[2] <= x1 + pad and box[3] <= y1 + pad
    assert (box[3] - box[1]) >= 0.75 * (y1 - y0) and (box[2] - box[0]) >= 0.75 * (x1 - x0)
    mask = np.ones(a.shape[:2], bool)
    mask[int(y0 - pad - 4):int(y1 + pad + 4), int(x0 - pad - 4):int(x1 + pad + 4)] = False
    assert float(np.abs(a - b).max(axis=2)[mask].mean()) < 4.0   # the rest of the picture is the master's (re-encoding noise only)
    ink = np.abs(a - b).max(axis=2) > 120
    ink[:int(y0 - 2 * pad), :] = False
    ink[int(y1 + 2 * pad):, :] = False
    assert ink.any() and b[ink].mean() < 90   # a light picture: the ink mark


def test_the_final_stage_at_4k(tmp_path):
    spec = {"mode": "videomk", "style": "lockup", "presence": "always", "opacity": 1.0}
    tl = _tl("16:9", "2160p", theme="midnight", watermark=spec, dur=2.0)
    mst, aud = _master(tl, str(tmp_path), draft=False, audio=False)
    out = str(tmp_path / "out.mp4")
    fs.export(tl, mst, None, out, draft=False, tmp=str(tmp_path))
    a, b = _frame(mst, 1.0, str(tmp_path), "a.png"), _frame(out, 1.0, str(tmp_path), "b.png")
    assert a.shape[:2] == (2160, 3840)
    box = _bbox(a, b, win=_win(spec, "16:9", 3840))
    x0, y0, x1, y1 = [v * 2 for v in ws.layout(spec, Frame.parse("16:9"), None, True)["rect"]]
    assert box is not None and (box[3] - box[1]) >= 0.75 * (y1 - y0) and box[2] <= x1 + 0.25 * (y1 - y0)
    assert b[np.abs(a - b).max(axis=2) > 120].mean() > 200   # a dark picture: the white mark


def test_the_end_card_is_the_only_added_duration_and_the_audio_keeps_its_length_plus_silence(tmp_path):
    spec = {**store.FORCED_SPEC}
    tl = _tl("16:9", "720p", theme="paper", watermark=spec, dur=3.0, outro=True)
    mst, aud = _master(tl, str(tmp_path), draft=True)
    out = str(tmp_path / "out.mp4")
    info = fs.export(tl, mst, aud, out, draft=True, tmp=str(tmp_path))
    d0, d1 = media.ffprobe_duration(mst), media.ffprobe_duration(out)
    assert info["end_card"] and abs((d1 - d0) - ws.END_CARD_S) < 0.2 and info["duration"] == 3.0
    last_content, card = _frame(out, d0 - 0.05, str(tmp_path), "l.png"), _frame(out, d0 + 1.4, str(tmp_path), "c.png")
    assert last_content.mean() < 40                      # the content ended on its own closing fade to black, untouched by the card
    assert card.mean() > 150 and np.abs(card - _frame(mst, 1.0, str(tmp_path), "m.png")).max() > 0   # then the card (paper theme: light)
    proc = subprocess.run([media.ffmpeg_bin(), "-i", out], capture_output=True, text=True)
    assert "Audio: aac" in proc.stderr
    # the audio ends with the card, silent over its last second
    pcm = subprocess.run([media.ffmpeg_bin(), "-v", "error", "-i", out, "-t", "30", "-f", "s16le", "-ac", "1", "-ar", "8000", "-"], capture_output=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(np.float32)
    assert abs(len(a) / 8000.0 - d1) < 0.3 and np.abs(a[int((d0 + 0.6) * 8000):]).max() < 200 and np.abs(a[int(1.0 * 8000):int(2.0 * 8000)]).max() > 2000


def test_the_same_video_without_the_watermark_is_the_master_and_no_scene_is_drawn_again(tmp_path, monkeypatch):
    tl = _tl("9:16", "720p", watermark=store.FORCED_SPEC, dur=3.0)
    base = {k: v for k, v in tl.items() if k != "watermark"}
    mst, aud = _master(tl, str(tmp_path), draft=True)   # the master was rendered from the timeline WITH a watermark: it has none
    (tmp_path / "x").mkdir()
    mst2, _ = _master(base, str(tmp_path / "x"), draft=True)   # ... and it is the master of the timeline without one: the same pictures, frame for frame
    assert all(np.array_equal(_frame(mst, t, str(tmp_path), "a.png"), _frame(mst2, t, str(tmp_path), "b.png")) for t in (0.5, 1.5, 2.5))
    monkeypatch.setattr(fs, "Renderer", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a scene was rendered")))
    for override in (None, {"mode": "none"}):
        out = str(tmp_path / "nomark.mp4")
        info = fs.export(tl, mst, aud, out, draft=True, spec_override=override, tmp=str(tmp_path))
        assert info["watermark"] is None and not info["end_card"] and open(out, "rb").read() == open(mst, "rb").read()
    out2 = str(tmp_path / "plain.mp4")
    fs.export(base, mst, aud, out2, draft=True, tmp=str(tmp_path))
    assert open(out2, "rb").read() == open(mst, "rb").read()


def test_a_video_made_without_a_watermark_can_get_one_later_from_the_same_master(tmp_path):
    tl = _tl("16:9", "720p", theme="midnight", dur=3.0, outro=True)
    mst, aud = _master(tl, str(tmp_path), draft=True)
    out = str(tmp_path / "later.mp4")
    info = fs.export(tl, mst, aud, out, draft=True, spec_override=store.FORCED_SPEC, tmp=str(tmp_path))
    assert info["end_card"] and abs(media.ffprobe_duration(out) - media.ffprobe_duration(mst) - ws.END_CARD_S) < 0.2
    assert _bbox(_frame(mst, 1.5, str(tmp_path), "a.png"), _frame(out, 1.5, str(tmp_path), "b.png"), win=_win(store.FORCED_SPEC, "16:9", 640)) is not None


def test_moments_show_the_mark_only_in_their_windows(tmp_path):
    spec = {"mode": "videomk", "style": "lockup", "presence": "moments", "windows": [[1.2, 6.4]], "opacity": 1.0}
    tl = _tl("16:9", "720p", theme="midnight", watermark=spec, dur=9.0, words=[])
    mst, aud = _master(tl, str(tmp_path), draft=True, audio=False)
    out = str(tmp_path / "out.mp4")
    fs.export(tl, mst, None, out, draft=True, tmp=str(tmp_path))
    w = _win(spec, "16:9", Renderer(tl, draft=True).out_w, 0.2)
    def strength(t):
        d = np.abs(_frame(mst, t, str(tmp_path), "a.png") - _frame(out, t, str(tmp_path), "b.png")).max(axis=2)[int(w[1]):int(w[3]), int(w[0]):int(w[2])]
        return float(d.mean())
    s = {t: strength(t) for t in (0.5, 1.5, 3.8, 6.1, 8.0)}
    assert s[0.5] < 1.0 and s[8.0] < 1.0 and s[3.8] > 8.0 and s[0.5] < s[1.5] < s[3.8] and s[6.1] < s[3.8]


def test_an_override_with_moments_works_out_its_windows_from_the_scenes():
    tl = {"scenes": [{"id": "a", "type": "title", "start": 0.0, "duration": 40.0}, {"id": "b", "type": "title", "start": 40.0, "duration": 30.0}], "duration": 70.0}
    spec = fs.spec_of(tl, {"mode": "videomk", "presence": "moments"})
    assert spec["windows"] and spec["windows"][0][0] == 1.2 and spec["windows"][-1][1] <= 70.0 - 1.0
    assert fs.spec_of(tl, {"mode": "none"}) is None and fs.spec_of(tl, None) is None and fs.spec_of({**tl, "watermark": {"mode": "videomk"}})["mode"] == "videomk"


def test_white_or_ink_follows_the_brightness_under_the_mark_per_scene_piece():
    scenes = [{"start": 0.0}, {"start": 10.0}, {"start": 20.0}]
    means = [0.2] * 40 + [0.9] * 40 + [0.2] * 40   # dark, light, dark (4 samples a second)
    start, flips = fs.ink_schedule(means, scenes, 30.0)
    assert start == 0 and flips == [(10.0, 1), (20.0, 0)] or (start == 0 and [f[1] for f in flips] == [1, 0])
    assert fs.ink_schedule([0.62] * 100, scenes, 30.0)[1] == []                      # inside the hysteresis band nothing flips
    s, f = fs.ink_schedule([0.2] * 120, scenes, 30.0)
    assert (s, f) == (0, [])
    expr = fs.ink_expr(0, [(10.0, 1), (20.0, 0)])
    assert expr.count("clip(") >= 6 and "T" in expr
    assert fs.pieces(scenes, 30.0)[0][0] == 0.0 and all(b - a <= fs.PIECE_S + 1e-6 for a, b in fs.pieces(scenes, 30.0))


def test_a_custom_logo_keeps_its_colours_and_an_unreadable_one_draws_nothing_and_no_card(tmp_path):
    tl = _tl("16:9", "720p", theme="midnight", dur=3.0, words=[], watermark=LOGO_SPEC)
    mst, aud = _master(tl, str(tmp_path), draft=True, audio=False)
    out = str(tmp_path / "out.mp4")
    fs.export(tl, mst, None, out, draft=True, image_loader=lambda k: _png(), tmp=str(tmp_path))
    a, b = _frame(mst, 1.5, str(tmp_path), "a.png"), _frame(out, 1.5, str(tmp_path), "b.png")
    box = _bbox(a, b, win=_win(LOGO_SPEC, "16:9", Renderer(tl, draft=True).out_w))
    assert box is not None
    px = b[box[1]:box[3], box[0]:box[2]].reshape(-1, 3)
    assert len(px[(px[:, 0] > 150) & (px[:, 1] < 90)]) > 0.3 * len(px)   # still red (yuv420 softens the edges a little)
    out2 = str(tmp_path / "out2.mp4")
    info = fs.export({**tl, "watermark": {**LOGO_SPEC}}, mst, None, out2, draft=True, image_loader=lambda k: None, tmp=str(tmp_path))
    assert not info["end_card"] and open(out2, "rb").read() == open(mst, "rb").read()


def test_the_overlay_expression_is_what_the_python_envelope_says():
    """The ffmpeg expression and the Python function describe one curve (checked at a few points by evaluating the expression with a tiny interpreter)."""
    def ev(expr, T):
        import re
        e = expr.replace("clip(", "_clip(").replace("min(", "_min(").replace("max(", "_max(")
        return eval(e, {"_clip": lambda x, lo, hi: max(lo, min(hi, x)), "_min": min, "_max": max, "T": T})
    for spec, d in (({"mode": "videomk"}, 20.0), ({"mode": "videomk", "presence": "moments", "windows": [[1.2, 6.4], [30.3, 35.5]]}, 60.0)):
        expr = fs.envelope_expr(spec, d)
        for t in (0.0, 0.3, 1.5, 3.0, 6.3, 19.5, 30.6, 33.0, 50.0):
            assert ev(expr, t) == pytest.approx(fs.envelope(spec, d, t), abs=1e-9)
