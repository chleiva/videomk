"""The watermark (docs/WATERMARK.md): the options and placement rules, frames of the real renderer (corner, size, opacity, fades, light and dark pictures, never on the captions or the
credit line), the timeline and chunk hashes, the launcher's policy (premium, forced, saved default), the settings and logo API with moto, the logo upload checks, the plan step's copy of a
custom logo and the account deletion."""
import base64
import io
import json

import boto3
import numpy as np
import pytest
from moto import mock_aws
from PIL import Image

import watermark_api
from common import deletion, usage, wallet, watermark_store as store
from engine import awsio, watermark as wm, watermark_spec as ws
from engine.frame import ASPECTS, Frame
from engine.handlers import plan_handler
from engine.renderer import Renderer
from engine.timeline import build_timeline, chunk_plan, chunk_timeline
from tests.test_create_options import _plan, _run_timeline, post, sent
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)

USER = "11111111-aaaa-bbbb-cccc-222222222222"
OTHER = "99999999-aaaa-bbbb-cccc-222222222222"
WORDS = [["This", 0.2, 0.5], ["is", 0.5, 0.7], ["a", 0.7, 0.9], ["caption", 0.9, 1.4], ["line", 1.4, 1.8]]


# ======================================================================== options
def test_parse_defaults_and_none():
    assert ws.parse(None) is None
    assert ws.parse({"mode": "none"}) == {"mode": "none"}
    d = ws.parse({"mode": "videomk"})
    assert d == {"mode": "videomk", "position": "auto", "opacity": 0.65, "size": "small", "style": "mark", "end_card": False}
    assert ws.parse({"mode": "custom", "position": "tl", "opacity": 0.5, "size": "medium"}) == {"mode": "custom", "position": "tl", "opacity": 0.5, "size": "medium"}   # no style or end card for a custom logo


@pytest.mark.parametrize("raw", [{"mode": "red"}, {"mode": "videomk", "position": "middle"}, {"mode": "videomk", "opacity": 0.1}, {"mode": "videomk", "opacity": 1.5}, {"mode": "videomk", "opacity": True},
                                 {"mode": "videomk", "opacity": "0.5"}, {"mode": "videomk", "size": "huge"}, {"mode": "videomk", "style": "big"}, {"mode": "videomk", "end_card": "yes"},
                                 {"mode": "videomk", "asset": "x"}, {"mode": "custom", "hash": "x"}, "videomk", 5, ["videomk"]])
def test_strict_parse_refuses_anything_invalid(raw):
    with pytest.raises(ws.WatermarkError):
        ws.parse(raw)


def test_lenient_parse_falls_back_instead_of_failing():
    out = ws.parse({"mode": "videomk", "position": "x", "opacity": 9, "size": "huge", "style": "z", "end_card": 3}, strict=False)
    assert out == {"mode": "videomk", "position": "auto", "opacity": 0.65, "size": "small", "style": "mark", "end_card": False}
    assert ws.parse({"mode": "custom", "asset": "generation/v2/v/assets/watermark.png", "hash": "ab" * 8}, strict=False)["asset"].endswith("watermark.png")
    assert ws.parse({"mode": "videomk", "asset": "x"}, strict=False).get("asset") is None   # only a custom logo has a file


# ======================================================================== placement
def _tall_ui_free(rect):   # 9:16 auto: clear of the platform header, the right buttons column and the bottom band
    return rect[1] >= 162 and rect[0] >= 0 and rect[2] <= 950 and rect[3] <= 1600


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("resolution", ["720p", "1080p", "2160p"])
@pytest.mark.parametrize("captions", [True, False])
def test_every_option_stays_in_the_frame_and_off_the_captions_and_the_credit(aspect, resolution, captions):
    f = Frame.parse(aspect, resolution)
    for mode, ratio in (("videomk", None), ("custom", 1.0), ("custom", 2.2), ("custom", 6.0), ("custom", 0.4)):
        for pos in ws.POSITIONS:
            for size in ws.SIZES:
                for style in ws.STYLES:
                    spec = {"mode": mode, "position": pos, "size": size, "style": style}
                    lay = ws.layout(spec, f, ratio, captions)
                    x0, y0, x1, y1 = lay["rect"]
                    assert not lay.get("overlaps"), (aspect, spec, ratio, lay)
                    assert 0 <= x0 < x1 <= f.W and 0 <= y0 < y1 <= f.H, (aspect, spec, lay)
                    if captions:
                        assert not ws.intersects(lay["rect"], ws.caption_rect(f)), (aspect, spec, ratio, lay)
                    if lay["position"] == "tr":
                        assert not ws.intersects(lay["rect"], ws.credit_rect(f)), (aspect, spec, ratio, lay)
                    if pos == "auto" and aspect == "9:16":
                        assert _tall_ui_free(lay["rect"]), (spec, lay)
                    assert 0.6 <= lay["scale"] <= 1.0


def test_the_default_corner_per_shape_and_the_size():
    for aspect, corner in {"16:9": "br", "9:16": "tl", "1:1": "tl", "4:5": "tl"}.items():
        f = Frame.parse(aspect)
        lay = ws.layout({"mode": "videomk"}, f, None, True)
        assert lay["position"] == corner and lay["scale"] == 1.0 and not lay["moved"]
        x0, y0, x1, y1 = lay["rect"]
        assert abs((y1 - y0) - 0.05 * 1080) < 0.01 and abs((x1 - x0) / (y1 - y0) - ws.MARK_RATIO) < 0.01   # small = 5 % of the short side
        assert abs((ws.layout({"mode": "videomk", "size": "medium"}, f, None, True)["rect"][3] - ws.layout({"mode": "videomk", "size": "medium"}, f, None, True)["rect"][1]) - 0.07 * 1080) < 0.01


def test_an_explicit_corner_is_kept_when_nothing_is_in_the_way():
    f = Frame.parse("16:9")
    for pos in ("tl", "bl", "br"):
        assert ws.layout({"mode": "videomk", "position": pos}, f, None, True)["position"] == pos
    assert ws.layout({"mode": "videomk", "position": "tr"}, f, None, True)["position"] == "br"   # the clip credit line owns the top right: the mark takes the corner below it
    assert ws.layout({"mode": "videomk", "position": "tr"}, f, None, False)["position"] == "br"   # (still: a credit can be there with captions off)


def test_a_wide_logo_is_limited_to_the_lockup_width():
    f = Frame.parse("16:9")
    x0, y0, x1, y1 = ws.layout({"mode": "custom", "position": "tl", "size": "small"}, f, 20.0, False)["rect"]
    assert abs((x1 - x0) - ws.MAX_LOGO_RATIO * 0.05 * 1080) < 0.5 and abs((x1 - x0) / (y1 - y0) - 20.0) < 0.05   # the width is capped at 6.3 x the mark height, the shape kept


# ======================================================================== frames of the real renderer
def _tl(aspect="16:9", resolution="1080p", theme="midnight", watermark=None, captions=True, scene="title", props=None, dur=6.0, words=None, outro=False, lead=None):
    fr = Frame.parse(aspect, resolution)
    sc = {"id": "t", "type": scene, "start": 0.0, "duration": dur, "props": props or {"title": "A calm title", "subtitle": "with a subtitle"}, "words": WORDS if words is None else words, "transition": "none"}
    tl = {"scenes": [sc], "theme": theme, "captions": captions, "duration": dur, "width": fr.width, "height": fr.height, "fps": 30, "outro": outro, "frame": {"aspect": aspect, "resolution": resolution}}
    if watermark is not None:
        tl["watermark"] = watermark
    return tl


def _frame(tl, t=1.2, draft=True, loader=None, first=False, band=0):
    r = Renderer(tl, image_loader=loader, draft=draft)
    if band:   # a frame WITHOUT the mark but with the band a top-corner mark reserves, so the only difference to the marked frame is the mark itself
        r.frame = r.frame.with_top_inset(band)
        r.ctx.frame = r.frame
    if not first:
        r.lead = object()   # a chunk that is not the first: the mark is already fully in
    return r, r.frame_at(t).convert("RGB")


def _bbox(a, b, thr=6):
    d = np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).max(axis=2) > thr
    ys, xs = np.where(d)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else None


@pytest.mark.parametrize("aspect", ASPECTS)
def test_the_mark_is_where_the_layout_says_and_as_big(aspect):
    r, marked = _frame(_tl(aspect, watermark={"mode": "videomk"}))
    _, plain = _frame(_tl(aspect), band=r.wm.inset)
    box = _bbox(plain, marked)
    assert box is not None
    scale = r.out_w / r.frame.W
    x0, y0, x1, y1 = [v * scale for v in ws.layout({"mode": "videomk"}, r.frame, None, True)["rect"]]
    pad = 0.2 * (y1 - y0)   # the soft shadow reaches a little past the mark
    assert box[0] >= x0 - pad and box[1] >= y0 - pad and box[2] <= x1 + pad and box[3] <= y1 + pad
    assert (box[3] - box[1]) >= 0.8 * (y1 - y0) and (box[2] - box[0]) >= 0.8 * (x1 - x0)


@pytest.mark.parametrize("aspect,resolution,draft", [("16:9", "720p", False), ("9:16", "1080p", True), ("1:1", "720p", True), ("4:5", "1080p", True), ("16:9", "2160p", False)])
def test_the_mark_is_drawn_at_the_output_size_in_every_resolution(aspect, resolution, draft):
    r, marked = _frame(_tl(aspect, resolution, watermark={"mode": "videomk"}), draft=draft)
    _, plain = _frame(_tl(aspect, resolution), draft=draft, band=r.wm.inset)
    box = _bbox(plain, marked)
    expect_h = 0.05 * min(r.out_w, r.out_h)   # 5 % of the short side of what is really output
    assert marked.size == (r.out_w, r.out_h) and box and 0.8 * expect_h <= (box[3] - box[1]) <= 1.45 * expect_h


def test_without_a_watermark_or_with_none_the_frame_is_exactly_what_it_was():
    for wmk in (None, {"mode": "none"}):
        _, a = _frame(_tl(watermark=wmk))
        _, b = _frame(_tl())
        assert _bbox(a, b, thr=0) is None


def test_the_same_frame_twice_is_identical():
    t = _tl(watermark={"mode": "videomk", "style": "lockup"})
    _, a = _frame(t)
    _, b = _frame(t)
    assert _bbox(a, b, thr=0) is None


def test_opacity_changes_how_strong_the_mark_is():
    def strength(op):
        _, plain = _frame(_tl())
        _, marked = _frame(_tl(watermark={"mode": "videomk", "opacity": op}))
        return int(np.abs(np.asarray(plain, np.int16) - np.asarray(marked, np.int16)).sum())
    lo, mid, hi = strength(0.2), strength(0.65), strength(1.0)
    assert lo < mid < hi and hi > 2.5 * lo


def test_the_mark_fades_in_on_the_first_chunk_only_and_goes_with_the_closing_fade():
    t = _tl(watermark={"mode": "videomk"}, outro=True)
    _, plain0 = _frame(_tl(outro=True), t=0.0, first=True)
    _, m0 = _frame(t, t=0.0, first=True)
    _, m_mid = _frame(t, t=0.3, first=True)
    _, m_full = _frame(t, t=1.2, first=True)
    _, p_mid = _frame(_tl(outro=True), t=0.3, first=True)
    _, p_full = _frame(_tl(outro=True), t=1.2, first=True)
    assert _bbox(plain0, m0, thr=1) is None                                        # frame 0 of the video: nothing yet
    s_mid, s_full = [int(np.abs(np.asarray(p, np.int16) - np.asarray(m, np.int16)).sum()) for p, m in ((p_mid, m_mid), (p_full, m_full))]
    assert 0 < s_mid < s_full
    _, mid_chunk = _frame(t, t=0.0, first=False)                                    # a later chunk starts with the mark fully in
    assert _bbox(plain0, mid_chunk) is not None
    _, plain_end = _frame(_tl(outro=True), t=5.99)
    _, wm_end = _frame(t, t=5.99)
    assert _bbox(plain_end, wm_end, thr=1) is None or int(np.abs(np.asarray(plain_end, np.int16) - np.asarray(wm_end, np.int16)).max()) <= 2   # gone with the picture


def test_a_light_picture_gets_the_ink_mark_and_a_dark_one_the_white_mark():
    def core(theme):
        r, marked = _frame(_tl(theme=theme, watermark={"mode": "videomk", "opacity": 1.0}))
        _, plain = _frame(_tl(theme=theme))
        d = np.abs(np.asarray(plain, np.int16) - np.asarray(marked, np.int16)).max(axis=2)
        px = np.asarray(marked, np.float32)[d > 120]
        return px.mean() if len(px) else None
    dark, light = core("midnight"), core("paper")
    assert dark is not None and dark > 200      # white on the dark theme
    assert light is not None and light < 90     # ink on the light theme


def test_the_mark_never_lands_on_the_captions():
    for aspect in ASPECTS:
        for pos in ws.POSITIONS:
            for style in ws.STYLES:
                spec = {"mode": "videomk", "position": pos, "style": style, "size": "medium"}
                r, with_all = _frame(_tl(aspect, watermark=spec, words=WORDS))
                _, no_caps = _frame(_tl(aspect, watermark=spec, captions=False))
                _, only_caps = _frame(_tl(aspect), t=1.2, band=r.wm.inset)
                _, nothing = _frame(_tl(aspect, captions=False), band=r.wm.inset)
                cap_box = _bbox(nothing, only_caps)
                wm_box = _bbox(only_caps, with_all)
                assert cap_box is not None and wm_box is not None
                inter = not (wm_box[2] <= cap_box[0] or wm_box[0] >= cap_box[2] or wm_box[3] <= cap_box[1] or wm_box[1] >= cap_box[3])
                assert not inter, (aspect, pos, style, cap_box, wm_box)


# ======================================================================== a top-corner mark has a band of its own (QA 2026-11-27: a 9:16 logo sat on a list heading)
LIST = {"heading": "Lighthouse facts", "items": ["Warn of rocks and reefs", "Guide ships into harbors", "Fewer shine today"]}


@pytest.mark.parametrize("aspect", ["9:16", "1:1", "4:5"])
@pytest.mark.parametrize("spec", [{"mode": "videomk"}, {"mode": "videomk", "style": "lockup", "size": "medium"}, {"mode": "videomk", "position": "tl", "style": "lockup"}])   # (a lockup asked for top right now fits bottom right in 1:1 and 4:5 since it is drawn smaller: watermark_spec.LOCKUP_SCALE)
def test_a_top_corner_mark_gets_its_own_band_above_the_content(aspect, spec):
    f = Frame.parse(aspect)
    lay = ws.layout(spec, f, None, True)
    inset = ws.content_inset(lay, f)
    assert lay["position"] in ("tl", "tr") and 0 <= inset <= f.design_h // 10
    assert (inset > 0) == (lay["rect"][3] + ws.CONTENT_GAP > f.margin_top)   # a chosen corner of 9:16 sits in the platform header, above the content: nothing to move
    assert f.with_top_inset(inset).margin_top >= lay["rect"][3] + ws.CONTENT_GAP - 0.5   # the content box starts below the mark
    assert f.with_top_inset(inset).base_margin_top == f.margin_top and f.with_top_inset(0) is f   # the shape's own margin (credit line, mark placement) does not move
    r, marked = _frame(_tl(aspect, watermark=spec, scene="bullets", props=LIST, words=[]), t=5.0)
    assert r.frame.top_inset == inset and r.ctx.frame.top_inset == inset and r.ctx.top == f.margin_top + inset
    # the heading is drawn below the mark: with the band, nothing of the scene differs from the bare background inside the mark's rectangle
    _, scene = _frame(_tl(aspect, scene="bullets", props=LIST, words=[]), t=5.0, band=inset)
    _, bare = _frame(_tl(aspect, scene="bullets", props={"heading": "", "items": [""]}, words=[]), t=5.0, band=inset)
    k = r.out_w / f.W
    x0, y0, x1, y1 = [int(round(v * k)) for v in lay["rect"]]
    a, b = np.asarray(scene, np.int16)[y0:y1, x0:x1], np.asarray(bare, np.int16)[y0:y1, x0:x1]
    assert np.abs(a - b).max() <= 6, (aspect, spec)
    _, old = _frame(_tl(aspect, scene="bullets", props=LIST, words=[]), t=5.0)   # the frame as it was without the band, for the default corner: the heading ran under a wide mark
    if spec.get("size") == "medium":
        assert np.abs(np.asarray(old, np.int16)[y0:y1, x0:x1] - b).max() > 40


def test_no_band_for_a_bottom_corner_for_landscape_or_without_a_watermark():
    for aspect in ASPECTS:
        f = Frame.parse(aspect)
        assert Renderer(_tl(aspect)).frame.top_inset == 0 and Renderer(_tl(aspect, watermark={"mode": "none"})).frame is f
    land = Frame.parse("16:9")
    for pos in ws.POSITIONS:
        assert ws.content_inset(ws.layout({"mode": "videomk", "position": pos, "style": "lockup"}, land, None, True), land) == 0
    tall = Frame.parse("9:16")
    lay = ws.layout({"mode": "videomk", "position": "br"}, tall, None, False)   # captions off: the chosen bottom corner is free
    assert lay["position"] == "br" and ws.content_inset(lay, tall) == 0
    assert Frame.parse("9:16").with_top_inset(10_000).top_inset == 192 and Frame.parse("9:16").with_top_inset(-5).top_inset == 0   # a band, never a layout change


def test_the_band_is_part_of_the_segment_hash_so_old_segments_are_not_reused():
    tl = _tl("9:16", watermark={"mode": "videomk"})
    plain = _tl("9:16")
    assert chunk_plan(tl)[0]["hash"] != chunk_plan(plain)[0]["hash"]
    import hashlib, json as _json  # noqa: E401
    assert '"wmv"' not in _json.dumps(chunk_plan(plain)) and hashlib   # nothing new in a video without a mark (its hash is covered by the existing test)


def _png(w=300, h=120, color=(220, 30, 40, 255)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w - 40, h - 20), color), (20, 10))
    return im


def test_a_custom_logo_is_drawn_in_its_own_colours_and_an_unreadable_one_draws_nothing():
    spec = {"mode": "custom", "asset": "generation/v2/v/assets/watermark.png", "hash": "abc", "opacity": 1.0, "position": "br"}
    r, marked = _frame(_tl(watermark=spec), loader=lambda k: _png())
    _, plain = _frame(_tl())
    box = _bbox(plain, marked)
    assert box is not None
    px = np.asarray(marked, np.float32)[box[1]:box[3], box[0]:box[2]].reshape(-1, 3)
    red = px[(px[:, 0] > 180) & (px[:, 1] < 80)]
    assert len(red) > 0.4 * len(px)                                               # still red: the person's colours are not tinted
    for loader in (lambda k: None, lambda k: (_ for _ in ()).throw(OSError("gone"))):
        r2, none = _frame(_tl(watermark=spec), loader=loader)
        assert r2.wm is None and _bbox(plain, none, thr=0) is None


# ======================================================================== timeline and chunks
def test_the_timeline_carries_the_watermark_and_the_chunk_hashes_follow_it(monkeypatch):
    plain, _ = _run_timeline(monkeypatch, _plan())
    assert "watermark" not in plain
    p = _plan()
    p["watermark"] = {"mode": "videomk", "size": "medium"}
    tl, out = _run_timeline(monkeypatch, p)
    assert tl["watermark"]["mode"] == "videomk" and tl["watermark"]["size"] == "medium"
    a, b = chunk_plan(plain, 10), chunk_plan(tl, 10)
    assert [c["hash"] for c in a] != [c["hash"] for c in b]
    assert chunk_timeline(tl, 0, 1)["watermark"] == tl["watermark"] and "watermark" not in chunk_timeline(plain, 0, 1)
    p2 = _plan()
    p2["watermark"] = {"mode": "none"}
    tl2, _ = _run_timeline(monkeypatch, p2)
    assert "watermark" not in tl2 and [c["hash"] for c in chunk_plan(tl2, 10)] == [c["hash"] for c in a]   # 'none' changes nothing, caches included


def test_a_changed_logo_or_option_makes_new_segments():
    base = _tl(watermark={"mode": "custom", "asset": "k", "hash": "aa"})
    other = _tl(watermark={"mode": "custom", "asset": "k", "hash": "bb"})
    base["scenes"][0]["start"] = other["scenes"][0]["start"] = 0.0
    assert chunk_plan(base, 10)[0]["hash"] != chunk_plan(other, 10)[0]["hash"]


def test_the_optional_end_card_is_one_silent_scene_after_the_last():
    plan = _plan()
    infos = [{"duration": 3.0}] * len(plan["beats"])
    plain = build_timeline(plan, infos, video_id="v")
    plan["watermark"] = {"mode": "videomk", "end_card": True}
    tl = build_timeline(plan, infos, video_id="v")
    assert len(tl["scenes"]) == len(plain["scenes"]) + 1
    last = tl["scenes"][-1]
    assert last["type"] == "title" and last["silent"] and last["words"] == [] and last["audio_key"] is None and last["props"]["title"] == "Made with VideoMK"
    assert abs(tl["duration"] - plain["duration"] - ws.END_CARD_S) < 1e-6 and abs(last["start"] - plain["duration"]) < 1e-6
    plan["language"] = "es"
    assert build_timeline(plan, infos, video_id="v")["scenes"][-1]["props"]["title"] == "Hecho con VideoMK"
    plan["watermark"] = {"mode": "videomk", "end_card": False}
    assert len(build_timeline(plan, infos, video_id="v")["scenes"]) == len(plain["scenes"])
    plan["watermark"] = {"mode": "custom", "end_card": True, "asset": "k"}
    assert len(build_timeline(plan, infos, video_id="v")["scenes"]) == len(plain["scenes"])   # a custom logo has no 'Made with VideoMK' card


# ======================================================================== the policy
def test_resolve_matrix():
    R = store.resolve
    free = dict(premium=False, forced=False, has_logo=False)
    assert R(None, None, **free) == {"mode": "none"}
    assert R({"mode": "videomk", "position": "tl"}, None, **free)["position"] == "tl"
    assert R(None, {"mode": "videomk", "size": "medium"}, **free)["size"] == "medium"                    # the saved default
    assert R({"mode": "none"}, {"mode": "videomk"}, **free) == {"mode": "none"}                         # a request beats the saved default
    with pytest.raises(store.WatermarkError) as e:
        R({"mode": "custom"}, None, premium=False, forced=False, has_logo=True)
    assert e.value.status == 403 and e.value.code == "watermark_premium"
    with pytest.raises(store.WatermarkError) as e:
        R({"mode": "custom"}, None, premium=True, forced=False, has_logo=False)
    assert e.value.status == 400 and e.value.code == "watermark_logo_missing"
    assert R({"mode": "custom"}, None, premium=True, forced=False, has_logo=True)["mode"] == "custom"
    assert R(None, {"mode": "custom"}, premium=False, forced=False, has_logo=True) == {"mode": "none"}   # a saved custom whose plan lapsed quietly falls back
    assert R(None, {"mode": "custom"}, premium=True, forced=False, has_logo=False) == {"mode": "none"}   # ... and so does one whose logo is gone
    # the owner's switch: a free account's video always carries the mark; premium may still choose none
    f = dict(premium=False, forced=True, has_logo=False)
    assert R(None, None, **f)["mode"] == "videomk" and R({"mode": "none"}, None, **f)["mode"] == "videomk" and R(None, {"mode": "custom"}, premium=False, forced=True, has_logo=True)["mode"] == "videomk"
    assert R({"mode": "none"}, None, premium=True, forced=False, has_logo=False) == {"mode": "none"}


@pytest.fixture
def wm_on(monkeypatch, aws):
    monkeypatch.setenv("WATERMARK_ENABLED", "1")
    monkeypatch.setenv("ASSETS_BUCKET", "assets-wm")
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket="assets-wm", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    store.set_clients(s3, aws)
    monkeypatch.setenv("DAILY_VIDEO_LIMIT", "100")
    for u in (USER, OTHER):
        wallet.give_credits(u, 200)
    yield type("W", (), {"s3": s3, "ddb": aws})()
    store.set_clients(None, None)


def _flags(w, user, **kw):
    w.ddb.Table("Flags").put_item(Item={"user_id": user, **kw})


def _launch(launcher, user=USER, **extra):
    return launcher.handler(_event(user=user, body={"prompt": "A short explainer about how black holes form", "target_minutes": 1, **extra}), None)


def test_the_launcher_sends_nothing_new_when_the_feature_is_off(launcher):
    assert _launch(launcher, watermark={"mode": "videomk"})["statusCode"] == 202
    assert "watermark" not in sent(launcher)


def test_the_launcher_validates_the_option(launcher, wm_on):
    r = _launch(launcher, watermark={"mode": "red"})
    assert r["statusCode"] == 400 and launcher.fake.calls == []
    assert _launch(launcher, watermark="videomk")["statusCode"] == 400
    assert _launch(launcher, watermark={"mode": "videomk", "opacity": 3})["statusCode"] == 400


def test_a_request_gets_its_watermark_and_nothing_when_none(launcher, wm_on):
    assert _launch(launcher)["statusCode"] == 202 and "watermark" not in sent(launcher)
    assert _launch(launcher, watermark={"mode": "none"}, target_minutes=2)["statusCode"] == 202 and "watermark" not in sent(launcher)
    assert _launch(launcher, watermark={"mode": "videomk", "position": "tl", "end_card": True}, target_minutes=3)["statusCode"] == 202
    assert sent(launcher)["watermark"] == {"mode": "videomk", "position": "tl", "opacity": 0.65, "size": "small", "style": "mark", "end_card": True}


def test_custom_needs_premium_and_a_logo_and_costs_nothing_when_refused(launcher, wm_on):
    r = _launch(launcher, watermark={"mode": "custom"})
    assert r["statusCode"] == 403 and json.loads(r["body"])["code"] == "watermark_premium" and launcher.fake.calls == []
    _flags(wm_on, USER, watermark_custom=True)
    r = _launch(launcher, watermark={"mode": "custom"})
    assert r["statusCode"] == 400 and json.loads(r["body"])["code"] == "watermark_logo_missing" and launcher.fake.calls == []
    wm_on.s3.put_object(Bucket="assets-wm", Key=store.logo_key(USER), Body=b"x")
    assert _launch(launcher, watermark={"mode": "custom", "size": "medium"})["statusCode"] == 202
    assert sent(launcher)["watermark"]["mode"] == "custom" and sent(launcher)["watermark"]["size"] == "medium" and "asset" not in sent(launcher)["watermark"]


def test_a_pro_plan_and_an_unlimited_test_account_are_premium_but_a_lapsed_plan_is_not(wm_on, monkeypatch):
    assert not store.is_premium(USER) and not store.is_premium(USER, {})
    assert store.is_premium(USER, {"storage_plan": "pro"}) and store.is_premium(USER, {"storage_plan": "pro", "storage_until": 4_000_000_000})
    assert not store.is_premium(USER, {"storage_plan": "pro", "storage_until": 1_000})
    assert not store.is_premium(USER, {"storage_plan": "free"}) and not store.is_premium(USER, {"watermark_custom": False})
    assert store.is_premium(USER, {"unlimited": True})
    monkeypatch.setenv("ALLOW_UNLIMITED_ACCOUNTS", "0")                          # production ignores the unlimited flag
    assert not store.is_premium(USER, {"unlimited": True}) and store.is_premium(USER, {"watermark_custom": True})


def test_an_unlimited_test_account_carries_the_name_by_default_and_can_remove_it(launcher, wm_on, monkeypatch):
    """Owner decision 2026-11-27: every video made by a test account has the brand (lockup, always, end card) unless the account says otherwise; customers are untouched."""
    _flags(wm_on, USER, unlimited=True)
    assert _launch(launcher)["statusCode"] == 202
    wm = sent(launcher)["watermark"]
    assert wm["mode"] == "videomk" and wm["style"] == "lockup" and wm.get("presence") == "always" and wm["end_card"] is True
    assert _launch(launcher, watermark={"mode": "none"}, target_minutes=2)["statusCode"] == 202 and "watermark" not in sent(launcher)     # the setting removes it
    assert _launch(launcher, watermark={"mode": "videomk", "presence": "moments"}, target_minutes=3)["statusCode"] == 202
    assert sent(launcher)["watermark"]["presence"] == "moments"                                                                        # and can soften it
    store.put_profile(USER, {"mode": "none"})                                                                                          # a saved choice is honoured
    assert _launch(launcher, target_minutes=1)["statusCode"] == 202 and "watermark" not in sent(launcher)
    store.put_profile(USER, {"mode": "videomk"})                                                                                       # saved mark without a stated presence: always, not moments
    assert _launch(launcher, target_minutes=2)["statusCode"] == 202 and sent(launcher)["watermark"].get("presence") == "always"
    assert store.capabilities(USER)["default_presence"] == "always"


def test_the_test_account_default_never_reaches_a_customer_or_production(launcher, wm_on, monkeypatch):
    assert _launch(launcher)["statusCode"] == 202 and "watermark" not in sent(launcher)                                               # an ordinary account: nothing changed
    assert store.rights(USER, {})["test"] is False
    monkeypatch.setenv("ALLOW_UNLIMITED_ACCOUNTS", "0")                                                                                # production ignores the unlimited flag
    assert store.rights(USER, {"unlimited": True})["test"] is False and not store.is_test_account(USER, {"unlimited": True})


def test_the_saved_default_is_used_when_the_request_says_nothing(launcher, wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    store.put_profile(USER, {"mode": "videomk", "position": "bl", "opacity": 0.5, "size": "medium", "style": "lockup", "end_card": True})
    assert _launch(launcher)["statusCode"] == 202
    assert sent(launcher)["watermark"] == {"mode": "videomk", "position": "bl", "opacity": 0.5, "size": "medium", "style": "lockup", "end_card": True, "presence": "moments"}   # a premium account's videomk mark comes and goes unless it says 'always' (tests/test_watermark_presence.py)
    assert _launch(launcher, watermark={"mode": "none"}, target_minutes=2)["statusCode"] == 202 and "watermark" not in sent(launcher)   # the request wins


def test_force_policy_marks_free_accounts_only(launcher, wm_on, monkeypatch):
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    assert _launch(launcher)["statusCode"] == 202 and sent(launcher)["watermark"]["mode"] == "videomk"
    assert _launch(launcher, watermark={"mode": "none"}, target_minutes=2)["statusCode"] == 202 and sent(launcher)["watermark"]["mode"] == "videomk"
    _flags(wm_on, OTHER, watermark_custom=True)
    assert _launch(launcher, user=OTHER, target_minutes=3)["statusCode"] == 202 and "watermark" not in sent(launcher)
    assert _launch(launcher, user=OTHER, watermark={"mode": "none"}, target_minutes=4)["statusCode"] == 202 and "watermark" not in sent(launcher)
    monkeypatch.setenv("FORCE_WATERMARK", "0")
    assert _launch(launcher, target_minutes=5)["statusCode"] == 202 and "watermark" not in sent(launcher)


def test_a_lookup_failure_never_stops_a_video(launcher, wm_on, monkeypatch):
    monkeypatch.setattr(store, "is_premium", lambda u, *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert _launch(launcher)["statusCode"] == 202 and "watermark" not in sent(launcher)
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    assert _launch(launcher, target_minutes=2)["statusCode"] == 202 and sent(launcher)["watermark"]["mode"] == "videomk"


# ======================================================================== the plan step's copy of a logo
def test_the_plan_step_copies_a_custom_logo_into_the_videos_own_folder(monkeypatch):
    puts, data = {}, {"watermark/" + USER + "/logo.png": b"PNGDATA"}
    monkeypatch.setattr(awsio, "get_bytes", lambda k: data[k])
    monkeypatch.setattr(awsio, "put_bytes", lambda k, b, ct="x", *a, **kw: puts.__setitem__(k, b))
    out = plan_handler._watermark({"watermark": {"mode": "custom", "size": "medium"}}, "vid12345", USER)
    assert out["mode"] == "custom" and out["asset"] == "generation/v2/vid12345/assets/watermark.png" and len(out["hash"]) == 16 and puts[out["asset"]] == b"PNGDATA"
    assert plan_handler._watermark({"watermark": {"mode": "videomk"}}, "vid12345", USER) == {"mode": "videomk", "position": "auto", "opacity": 0.65, "size": "small", "style": "mark", "end_card": False}
    assert plan_handler._watermark({}, "vid12345", USER) is None and plan_handler._watermark({"watermark": {"mode": "none"}}, "vid12345", USER) is None
    data.clear()   # the logo vanished between the request and the plan step
    assert plan_handler._watermark({"watermark": {"mode": "custom"}}, "vid12345", USER) is None
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    assert plan_handler._watermark({"watermark": {"mode": "custom"}}, "vid12345", USER) == {"mode": "videomk"}


# ======================================================================== the settings and logo API
def call(method, resource, body=None, user=USER, path_user=None, raw=None, locale=None):
    ev = {"httpMethod": method, "resource": "/users/{user_id}/watermark" + resource, "pathParameters": {"user_id": path_user or user}, "headers": {"X-Locale": locale} if locale else {},
          "body": raw if raw is not None else (json.dumps(body) if body is not None else None), "requestContext": {"authorizer": {"claims": {"sub": user}}}}
    r = watermark_api.handler(ev, None)
    return r["statusCode"], json.loads(r["body"])


def logo_body(data):
    return {"data": base64.b64encode(data).decode()}


def png_bytes(w=400, h=160, color=(10, 120, 240, 255), pad=30):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w - 2 * pad, h - 2 * pad), color), (pad, pad))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def test_get_before_anything_is_saved(wm_on):
    st, b = call("GET", "")
    assert st == 200 and b["watermark"] == {"mode": "none", "position": "auto", "opacity": 0.65, "size": "small", "style": "mark", "end_card": False, "has_logo": False}
    c = b["capabilities"]
    assert [m["id"] for m in c["modes"]] == ["none", "videomk", "custom"] and c["premium"] is False and c["forced"] is False
    assert {m["id"]: m["available"] for m in c["modes"]} == {"none": True, "videomk": True, "custom": False}
    assert c["positions"] == ["auto", "tl", "tr", "bl", "br"] and c["sizes"] == ["small", "medium"] and c["opacity"] == {"min": 0.2, "max": 1.0, "default": 0.65}


def test_the_api_needs_the_signed_in_user_and_the_feature(wm_on, monkeypatch):
    assert watermark_api.handler({"httpMethod": "GET", "resource": "/users/{user_id}/watermark", "pathParameters": {"user_id": USER}, "requestContext": {}}, None)["statusCode"] == 401
    assert call("GET", "", user=USER, path_user=OTHER)[0] == 403
    monkeypatch.setenv("WATERMARK_ENABLED", "0")
    assert call("GET", "")[0] == 404


def test_save_and_read_the_default_settings(wm_on):
    st, b = call("PUT", "", {"mode": "videomk", "position": "bl", "opacity": 0.4, "size": "medium", "style": "lockup", "end_card": True})
    assert st == 200 and b["watermark"]["position"] == "bl" and b["watermark"]["style"] == "lockup" and b["watermark"]["end_card"] is True
    assert call("GET", "")[1]["watermark"]["opacity"] == 0.4
    assert call("PUT", "", {"mode": "none"})[1]["watermark"]["mode"] == "none"
    for bad in ({"mode": "red"}, {"mode": "videomk", "opacity": 7}, {"mode": "videomk", "junk": 1}, {}, []):
        assert call("PUT", "", bad)[0] == 400
    assert call("PUT", "", raw="{nope")[0] == 400


def test_custom_is_premium_only_and_the_logo_must_exist_first(wm_on):
    assert call("PUT", "", {"mode": "custom"})[0] == 403
    assert call("PUT", "/logo", logo_body(png_bytes())) [0] == 403
    _flags(wm_on, USER, watermark_custom=True)
    st, b = call("PUT", "", {"mode": "custom"})
    assert st == 400 and b["code"] == "watermark_logo_missing"
    st, b = call("PUT", "/logo", logo_body(png_bytes()))
    assert st == 200 and b["watermark"]["has_logo"] is True and b["watermark"]["logo_url"].startswith("https://")
    assert call("PUT", "", {"mode": "custom", "position": "tr"})[1]["watermark"]["mode"] == "custom"
    st, b = call("DELETE", "/logo")
    assert st == 200 and b["watermark"]["has_logo"] is False and b["watermark"]["mode"] == "videomk"   # a saved 'custom' without a logo would be dead: it falls back
    st, b = call("DELETE", "")
    assert st == 200 and b["watermark"]["mode"] == "none"
    keys = [o["Key"] for o in wm_on.s3.list_objects_v2(Bucket="assets-wm").get("Contents", [])]
    assert keys == []


def test_the_forced_policy_refuses_none_to_a_free_account(wm_on, monkeypatch):
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    st, b = call("PUT", "", {"mode": "none"})
    assert st == 403 and b["code"] == "watermark_required"
    assert call("PUT", "", {"mode": "videomk"})[0] == 200
    c = call("GET", "")[1]["capabilities"]
    assert c["forced"] is True and {m["id"]: m["available"] for m in c["modes"]}["none"] is False
    _flags(wm_on, USER, watermark_custom=True)
    assert call("PUT", "", {"mode": "none"})[0] == 200


def test_the_logo_is_re_encoded_trimmed_and_scaled(wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    big = Image.new("RGBA", (1900, 700), (0, 0, 0, 0))
    big.paste(Image.new("RGBA", (1500, 400), (200, 20, 20, 255)), (200, 150))
    buf = io.BytesIO()
    big.save(buf, "PNG", pnginfo=None)
    st, _ = call("PUT", "/logo", logo_body(buf.getvalue()))
    assert st == 200
    stored = wm_on.s3.get_object(Bucket="assets-wm", Key=store.logo_key(USER))
    assert stored["ContentType"] == "image/png"
    img = Image.open(io.BytesIO(stored["Body"].read()))
    assert img.format == "PNG" and img.mode == "RGBA" and max(img.size) == store.STORE_PX and abs(img.width / img.height - 1500 / 400) < 0.02   # margins trimmed, at most 1024
    assert not img.info.get("exif") and "Comment" not in img.info


def test_checking_a_logo_leaves_pillows_pixel_limit_as_it_was():
    """The limit is process-wide: left lowered, a 4K canvas drawn later in the same process was refused as a decompression bomb (the hidden state behind a 4K test that failed only after this file)."""
    before = Image.MAX_IMAGE_PIXELS
    buf = io.BytesIO()
    _png().save(buf, "PNG")
    store.normalise_logo(buf.getvalue())
    assert Image.MAX_IMAGE_PIXELS == before
    with pytest.raises(store.WatermarkError):
        store.normalise_logo(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    assert Image.MAX_IMAGE_PIXELS == before
    Image.new("RGB", (7680, 4400)).crop((0, 0, 7680, 4320))   # a 4K canvas at 4x: no error


def test_a_jpeg_with_metadata_comes_back_clean(wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    im = Image.new("RGB", (300, 200), (30, 90, 200))
    exif = Image.Exif()
    exif[0x010E] = "SECRET DESCRIPTION"
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    assert call("PUT", "/logo", logo_body(buf.getvalue()))[0] == 200
    out = wm_on.s3.get_object(Bucket="assets-wm", Key=store.logo_key(USER))["Body"].read()
    assert b"SECRET" not in out and b"Exif" not in out and out.startswith(b"\x89PNG")


GOOD_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40" width="100" height="40"><rect x="5" y="5" width="90" height="30" rx="6" fill="#e11"/></svg>'


@pytest.mark.parametrize("name,data,code", [
    ("not an image", b"hello this is just text", "logo_type"),
    ("an executable called png", b"MZ\x90\x00" + b"\x00" * 600, "logo_type"),
    ("empty", b"", "logo_too_big"),
    ("truncated png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "logo_type"),
    ("svg with a script", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect width="9" height="9"/></svg>', "logo_svg"),
    ("svg with an external image", b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="http://169.254.169.254/latest/meta-data/" width="9" height="9"/></svg>', "logo_svg"),
    ("svg with a file reference", b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd" width="9" height="9"/></svg>', "logo_svg"),
    ("svg with an entity", b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>', "logo_svg"),
    ("svg with an import", b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(http://evil/x.css);</style><rect width="9" height="9"/></svg>', "logo_svg"),
    ("fully transparent png", png_bytes(color=(0, 0, 0, 0)), "logo_empty"),
])
def test_unsafe_or_unusable_logos_are_refused(wm_on, name, data, code):
    _flags(wm_on, USER, watermark_custom=True)
    st, b = call("PUT", "/logo", logo_body(data))
    assert st == 400 and b["code"] == code, name
    assert wm_on.s3.list_objects_v2(Bucket="assets-wm").get("KeyCount", 0) == 0


def test_size_and_dimension_limits(wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    st, b = call("PUT", "/logo", logo_body(b"\x89PNG\r\n\x1a\n" + b"\x00" * (store.MAX_LOGO_BYTES + 10)))
    assert st == 400 and b["code"] == "logo_too_big"
    st, b = call("PUT", "/logo", raw=json.dumps({"data": "A" * (4 * 1024 * 1024)}))
    assert st == 400 and b["code"] == "logo_too_big"
    big = io.BytesIO()
    Image.new("RGBA", (2100, 100), (255, 0, 0, 255)).save(big, "PNG")
    st, b = call("PUT", "/logo", logo_body(big.getvalue()))
    assert st == 400 and b["code"] == "logo_px"
    assert call("PUT", "/logo", {"data": 5})[0] == 400 and call("PUT", "/logo", {"data": "!!!notbase64!!!"})[0] == 400 and call("PUT", "/logo", {})[0] == 400
    assert wm_on.s3.list_objects_v2(Bucket="assets-wm").get("KeyCount", 0) == 0


def test_a_good_svg_is_drawn_once_and_only_a_png_is_kept(wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    assert call("PUT", "/logo", logo_body(GOOD_SVG))[0] == 200
    out = wm_on.s3.get_object(Bucket="assets-wm", Key=store.logo_key(USER))["Body"].read()
    img = Image.open(io.BytesIO(out))
    assert out.startswith(b"\x89PNG") and abs(img.width / img.height - 90 / 30) < 0.05


def test_logo_uploads_are_rate_limited_per_day(wm_on, monkeypatch):
    _flags(wm_on, USER, watermark_custom=True)
    monkeypatch.setattr(watermark_api, "LOGO_UPLOADS_PER_DAY", 2)
    assert call("PUT", "/logo", logo_body(png_bytes()))[0] == 200 and call("PUT", "/logo", logo_body(png_bytes()))[0] == 200
    st, b = call("PUT", "/logo", logo_body(png_bytes()))
    assert st == 429 and b["code"] == "rate_limited"


def test_one_person_cannot_touch_anothers_settings(wm_on):
    _flags(wm_on, USER, watermark_custom=True)
    call("PUT", "/logo", logo_body(png_bytes()))
    assert call("GET", "", user=OTHER)[1]["watermark"]["has_logo"] is False
    assert call("DELETE", "/logo", user=OTHER)[0] == 200
    assert call("GET", "")[1]["watermark"]["has_logo"] is True
    for bad_user in ("../" + USER, "a" * 3, USER + "/x"):
        assert call("GET", "", user=bad_user)[0] == 403


def test_messages_follow_the_locale(wm_on):
    st, b = call("PUT", "/logo", logo_body(png_bytes()), locale="es")
    assert st == 403 and "plan Pro" in b["message"]
    assert "Pro plan" in call("PUT", "/logo", logo_body(png_bytes()), locale="en")[1]["message"]


def test_capabilities_lists_the_watermark_for_the_signed_in_account(wm_on):
    import capabilities_api
    ev = {"pathParameters": {"user_id": USER}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": USER}}}}
    body = json.loads(capabilities_api.handler(ev, None)["body"])
    assert body["watermark"]["premium"] is False and body["aspects"] and "watermark" in body
    _flags(wm_on, USER, watermark_custom=True)
    assert json.loads(capabilities_api.handler(ev, None)["body"])["watermark"]["premium"] is True


def test_capabilities_is_unchanged_when_the_feature_is_off(aws):
    import capabilities_api
    ev = {"pathParameters": {"user_id": USER}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": USER}}}}
    assert "watermark" not in json.loads(capabilities_api.handler(ev, None)["body"])


# ======================================================================== account deletion and the stack
def test_the_account_deletion_covers_the_watermark_folder_and_the_logo_counter():
    assert "watermark/{u}/" in deletion.ASSET_USER_PREFIXES and "wmlogo:" in deletion.USAGE_PREFIXES


@pytest.fixture(scope="module")
def synth():
    import os as _os
    import sys
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
    sys.path.insert(0, root)
    cwd = _os.getcwd()
    _os.chdir(root)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(stage="qa", **ctx):
            ctx.setdefault("engine", "v2")
            key = (stage,) + tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": stage, **ctx}, outdir=_os.path.join(_os.environ.get("TMPDIR", "/tmp"), f"vmk-wm-{len(cache)}"))
                _os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                acct, region = ("464863885161", "us-west-2") if stage == "prod" else ("123456789012", "eu-west-1")
                stack = BackendStack(app, f"videomk-{stage}", stage=stage, stage_cfg={"account": acct, "region": region, "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account=acct, region=region))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        _os.chdir(cwd)


def _of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def _fn(t, name):
    found = [v["Properties"] for v in _of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == name]
    return found[0] if found else None


def test_the_stack_adds_the_routes_and_the_rights_and_can_switch_it_off(synth):
    t = synth()
    res = {k: v["Properties"]["PathPart"] for k, v in _of(t, "AWS::ApiGateway::Resource").items()}
    wm = [k for k, p in res.items() if p == "watermark"]
    logo = [k for k, p in res.items() if p == "logo"]
    assert len(wm) == 1 and len(logo) == 1
    methods = lambda rid: {v["Properties"]["HttpMethod"] for v in _of(t, "AWS::ApiGateway::Method").values() if v["Properties"].get("ResourceId") == {"Ref": rid}}   # noqa: E731
    assert methods(wm[0]) == {"GET", "PUT", "DELETE", "OPTIONS"} and methods(logo[0]) == {"PUT", "DELETE", "OPTIONS"}
    for v in _of(t, "AWS::ApiGateway::Method").values():   # every real method is behind the Cognito authoriser
        if v["Properties"].get("ResourceId") in ({"Ref": wm[0]}, {"Ref": logo[0]}) and v["Properties"]["HttpMethod"] != "OPTIONS":
            assert v["Properties"]["AuthorizationType"] == "COGNITO_USER_POOLS"
    api = _fn(t, "watermark_api")
    assert api and api["Environment"]["Variables"]["WATERMARK_ENABLED"] == "1" and api["Environment"]["Variables"]["FORCE_WATERMARK"] == "0" and len(api["Layers"]) == 1
    assert _fn(t, "VideoGenerationSFLauncher")["Environment"]["Variables"]["WATERMARK_ENABLED"] == "1" and _fn(t, "capabilities_api")["Environment"]["Variables"]["WATERMARK_ENABLED"] == "1"
    assert _fn(t, "v2_plan")["Environment"]["Variables"]["FORCE_WATERMARK"] == "0"
    # the API function may touch only the watermark folder of the bucket, and can only READ the flags table (nothing at runtime can grant itself premium)
    pol = json.dumps([v["Properties"]["PolicyDocument"] for k, v in _of(t, "AWS::IAM::Policy").items() if "WatermarkApiFunction" in k])
    assert "watermark/*" in pol
    flags_stmts = [st for k, v in _of(t, "AWS::IAM::Policy").items() if "WatermarkApiFunction" in k for st in v["Properties"]["PolicyDocument"]["Statement"] if "AccountFlagsTable" in json.dumps(st.get("Resource"))]
    assert flags_stmts and all(set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]]) <= {"dynamodb:BatchGetItem", "dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:Scan", "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable"} for st in flags_stmts)


def test_it_can_be_switched_off_and_the_policy_switched_on(synth):
    assert _fn(synth(watermark="0"), "watermark_api") is None
    assert "WATERMARK_ENABLED" not in _fn(synth(watermark="0"), "VideoGenerationSFLauncher")["Environment"]["Variables"]
    assert _fn(synth(forceWatermark="1"), "watermark_api")["Environment"]["Variables"]["FORCE_WATERMARK"] == "1"
    assert _fn(synth(forceWatermark="1"), "v2_plan")["Environment"]["Variables"]["FORCE_WATERMARK"] == "1"
