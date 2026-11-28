"""Video upload in the engine and launcher (docs/VIDEO_UPLOAD_2026-11-28.md sections 5 and 6): the planner's context, scene validation, placement, the three renderings,
the clip's sound under the narration, the launcher (ids, plan limit, copy, c_vidup charged once)."""
import json
import shutil
import subprocess
from decimal import Decimal

import boto3
import numpy as np
import pytest
from PIL import Image

from common import plans, vidup as V
from engine import audio, clips, media, pipeline, plan as plan_mod, timeline as timeline_mod
from engine.renderer import Renderer
from tests.test_engine import small_timeline

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

ASSETS = [{"id": "V1", "clip": "a" * 32, "w": 1080, "h": 1920, "duration": 4.0, "audio": True, "key": "generation/v2/v/assets/uclip_V1.mp4", "audio_key": "generation/v2/v/assets/uclip_V1.m4a",
           "lines": ["a dog runs", "it jumps"], "summary": "A dog plays in a park", "speech": "good boy"},
          {"id": "V2", "clip": "b" * 32, "w": 320, "h": 240, "duration": 3.0, "audio": False, "key": "generation/v2/v/assets/uclip_V2.mp4", "audio_key": None, "lines": [], "summary": "", "speech": ""}]


def _raw(*scenes):
    return {"legit": True, "title": "T", "beats": [{"narration": f"This is the spoken line number {i} of the video.", "scene": s} for i, s in enumerate(scenes)]}


def test_the_planner_prompt_carries_the_clip_description_and_the_scene_is_validated():
    seen = []
    good = _raw({"type": "clip", "props": {"user_clip": "v1", "fit": "FILL", "alt": "the dog"}}, {"type": "clip", "props": {"user_clip": "V2", "alt": "tiny"}})
    plan, warns = plan_mod.generate_plan("my dog", "", 1, lambda s, u: (seen.append(u), json.dumps(good))[1], video_assets=ASSETS, frame={"aspect": "16:9", "resolution": "1080p"})
    assert "<<<CLIP V1" in seen[0] and "second 1: a dog runs" in seen[0] and "speech in the clip (transcript): good boy" in seen[0] and "1080x1920, portrait" in seen[0] and "320x240" in seen[0]
    sc = [b["scene"] for b in plan["beats"] if b["scene"]["props"].get("user_clip")]
    assert [s["props"]["user_clip"] for s in sc] == ["V1", "V2"] and sc[0]["type"] == "clip" and "clip_query" not in sc[0]["props"]
    plan2, w = plan_mod.validate_plan(good), None
    assert plan2[0]["beats"][0]["scene"]["props"]["fit"] == "fill"


def test_ensure_video_clips_settles_fit_replaces_unknown_and_never_drops_a_clip():
    plan, _ = plan_mod.validate_plan(_raw({"type": "clip", "props": {"user_clip": "V1", "fit": "fill", "alt": "the dog"}}, {"type": "clip", "props": {"user_clip": "V9", "alt": "ghost clip"}},
                                          {"type": "bullets", "props": {"heading": "H", "items": ["a", "b"]}}))
    warns = plan_mod.ensure_video_clips(plan, ASSETS, "16:9", "1080p")
    b = plan["beats"]
    assert b[0]["scene"]["props"] == {"user_clip": "V1", "fit": "fit", "alt": "the dog"}                       # a vertical clip is never cropped to a landscape frame: the rule overrode "fill"
    assert b[1]["scene"] == {"type": "clip", "props": {"clip_query": "ghost clip", "alt": "ghost clip"}}       # an unknown id is ordinary stock footage
    added = [x for x in b if x["scene"]["props"].get("user_clip") == "V2"]
    assert len(added) == 1 and added[0]["scene"]["props"]["fit"] == "card" and len(added[0]["narration"].split()) >= 3 and any("unused video clips: V2" in w for w in warns)
    assert b[-1]["scene"]["type"] == "bullets" or added[0] is b[-2]                                          # inserted before the closing beat
    assert [a["id"] for a in plan["video_assets"]] == ["V1", "V2"] and plan["video_assets"][0]["audio_key"].endswith("V1.m4a")
    twice, _ = plan_mod.validate_plan(_raw({"type": "clip", "props": {"user_clip": "V1", "alt": "x"}}, {"type": "clip", "props": {"user_clip": "V1", "alt": "again"}}))
    plan_mod.ensure_video_clips(twice, ASSETS[:1], "9:16", "1080p")
    assert sum(1 for x in twice["beats"] if x["scene"]["props"].get("user_clip")) == 1                          # exactly once


def test_the_beat_uses_the_copied_clip_without_searching_or_paying(monkeypatch):
    from engine.handlers import beat_handler as bh
    plan = {"video_assets": ASSETS, "frame": {}}
    beat = {"id": "b1", "narration": "x", "scene": {"type": "clip", "props": {"user_clip": "V1", "fit": "fit", "alt": "dog"}}}
    monkeypatch.setattr(bh.clips, "scout_with_retry", lambda *a, **k: pytest.fail("no stock search for the person's own clip"))
    out = bh.make_clip(plan, beat, "v", "cost_usd", 3.0)
    assert out["clip_asset"] == ASSETS[0]["key"] and out["user_clip"] == {"fit": "fit", "audio_key": ASSETS[0]["audio_key"]}
    bad = {"video_assets": [{**ASSETS[0], "key": "generation/v2/other/assets/uclip_V1.mp4"}]}   # a key outside this video's folder is never read
    monkeypatch.setattr(bh.clips, "scout_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(bh.clips, "scout_own", lambda *a, **k: None)
    monkeypatch.setattr(bh, "make_photo", lambda *a, **k: {"asset": "stock.jpg"})
    out2 = bh.make_clip(bad, beat, "v", "cost_usd", 3.0)
    assert "user_clip" not in out2 and out2.get("asset") == "stock.jpg"


def test_the_timeline_carries_fit_and_the_clip_sound_for_the_renderer_and_the_mix():
    plan = {"title": "T", "language": "en", "frame": {}, "beats": [{"id": "b1", "narration": "A line of words about my dog playing.", "scene": {"type": "clip", "props": {"user_clip": "V1", "fit": "card", "alt": "dog"}}}]}
    info = [{"duration": 4.0, "clip_asset": "generation/v2/v/assets/uclip_V1.mp4", "user_clip": {"fit": "card", "audio_key": "generation/v2/v/assets/uclip_V1.m4a"}, "words": None, "silent": False, "audio_key": "a"}]
    tl = timeline_mod.build_timeline(plan, info, video_id="v")
    pr = tl["scenes"][0]["props"]
    assert tl["scenes"][0]["type"] == "clip" and pr["asset"].endswith("uclip_V1.mp4") and pr["fit"] == "card" and pr["clip_audio"].endswith("V1.m4a") and pr["user_clip"] is True
    sil = timeline_mod.build_timeline(plan, [{**info[0], "user_clip": {"fit": "fill"}}], video_id="v")["scenes"][0]["props"]
    assert "clip_audio" not in sil and sil["fit"] == "fill"


def _clip_file(tmp_path, size, seconds=2):
    p = tmp_path / f"c{size}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
    return clips.ClipFrames(str(p))


@pytest.mark.parametrize("fit,size", [("fill", "1920x1080"), ("fit", "1080x1920"), ("card", "320x240")])
def test_the_three_placements_render_and_differ(tmp_path, fit, size):
    frames = _clip_file(tmp_path, size)
    tl = small_timeline(4.0, ["clip", "title"])
    tl["scenes"][0]["props"] = {"asset": "u.mp4", "alt": "my clip", "fit": fit, "user_clip": True}
    r = Renderer(tl, clip_loader=lambda k: frames)
    a, b = r.frame_at(0.4), r.frame_at(1.4)
    assert a.size == (1920, 1080) and a.tobytes() != b.tobytes()                                              # it plays
    plain = {**tl["scenes"][0]["props"]}
    plain.pop("fit")
    tl2 = small_timeline(4.0, ["clip", "title"])
    tl2["scenes"][0]["props"] = {**plain, "fit": "fill"}
    other = Renderer(tl2, clip_loader=lambda k: frames).frame_at(0.4)
    assert (fit == "fill") == (a.tobytes() == other.tobytes())


def test_a_small_clip_in_a_card_is_never_enlarged_beyond_the_frame_scale(tmp_path):
    frames = _clip_file(tmp_path, "320x240")
    tl = small_timeline(4.0, ["clip", "title"])
    tl["scenes"][0]["props"] = {"asset": "u.mp4", "alt": "tiny", "fit": "card", "user_clip": True}
    im = Renderer(tl, clip_loader=lambda k: frames).frame_at(1.0).convert("RGB")
    cx = np.asarray(im)[540, :, :].astype(int)                                                                 # the middle row: dark glow outside, the bright test pattern inside the window
    bright = np.where(cx.max(axis=1) > 150)[0]
    assert bright.size and (bright.max() - bright.min()) < 1920 * 0.5


def test_the_clip_sound_is_placed_on_the_timeline_and_ducked_under_the_narration(tmp_path):
    sr = audio.MIX_SR
    tone = (0.5 * np.sin(2 * np.pi * 440 * np.arange(int(2 * sr)) / sr)).astype(np.float32)
    track = audio.build_clip_audio_track([(1.0, 1.0, tone)], 4.0)
    assert track.shape == (int(4 * sr), 2) and abs(track[: int(0.9 * sr)]).max() == 0 and abs(track[int(1.2 * sr): int(1.8 * sr)]).max() > 0.3 and abs(track[int(2.1 * sr):]).max() == 0   # cut to its scene
    nar = np.zeros(int(4 * 24000), np.float32)
    nar[int(2.0 * 24000): int(4 * 24000)] = 0.3 * np.sin(2 * np.pi * 200 * np.arange(int(2 * 24000)) / 24000)
    tl = {"duration": 4.0, "scenes": [{"id": "s", "type": "clip", "start": 0.0, "duration": 2.0, "props": {"asset": "k", "clip_audio": "ca"}, "audio_key": None, "silent": True, "narration_offset": 0.0},
                                      {"id": "t", "type": "title", "start": 2.0, "duration": 2.0, "props": {"title": "x"}, "audio_key": "n", "narration_offset": 0.0}], "music": None}
    with_clip, without = str(tmp_path / "a.m4a"), str(tmp_path / "b.m4a")
    pipeline.make_audio(tl, [None, nar], with_clip, clip_audio_loader=lambda k: tone)
    pipeline.make_audio(tl, [None, nar], without, clip_audio_loader=None)
    wav = lambda p: subprocess.run([media.ffmpeg_bin(), "-v", "error", "-i", p, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a, b = np.frombuffer(wav(with_clip), "<i2").astype(float), np.frombuffer(wav(without), "<i2").astype(float)
    assert abs(a[1600: 12000]).max() > 5 * max(1.0, abs(b[1600: 12000]).max())                                     # silent beat: the clip's own sound is heard
    assert abs(b[1600: 12000]).max() < 800


def test_the_audio_step_refuses_clip_sound_outside_this_videos_folder():
    from engine.handlers import audio_handler as ah
    tl = {"scenes": [{"audio_key": None, "silent": True, "props": {"clip_audio": "generation/v2/other/assets/uclip_V1.m4a"}}]}
    ah.awsio.get_json = lambda k: tl
    with pytest.raises(ValueError):
        ah.handler({"video_id": "v", "timeline_key": "x"}, None)


# ============================================================================ the launcher
@pytest.fixture
def launch_env(aws, monkeypatch):
    import sf_launcher as L
    s3 = boto3.client("s3", region_name="us-west-2")
    for b in ("assets-x", "vidup-x"):
        s3.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    monkeypatch.setenv("ASSETS_BUCKET", "assets-x")
    monkeypatch.setenv("VIDUP_BUCKET", "vidup-x")
    monkeypatch.setattr(L, "_s3", s3)
    return L, s3


def _ready(user, cid, usd=0.004, audio=False):
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.put_object(Bucket="vidup-x", Key=V.mezz_key(user, cid), Body=b"mp4")
    if audio:
        s3.put_object(Bucket="vidup-x", Key=V.audio_key(user, cid), Body=b"m4a")
    V.put_record(user, cid, {"status": V.READY, "w": 1280, "h": 720, "duration": 5.0, "audio_used": audio, "mezz_key": V.mezz_key(user, cid), "audio_key": V.audio_key(user, cid) if audio else None,
                             "lines": ["x"], "summary": "s", "transcript": "t", "c_vidup": usd})


def test_the_launcher_validates_ids_and_the_feature_flag(launch_env, monkeypatch):
    L, _ = launch_env
    ids = ["a" * 32, "b" * 32]
    assert L.validate_options({"video_assets": ids})["video_assets"] == ids
    for bad in ("x", ["short"], ["a" * 32, "a" * 32], ["a" * 32] * 7, [1]):
        with pytest.raises(L.BadRequest):
            L.validate_options({"video_assets": bad})
    monkeypatch.setenv("VIDUP_BUCKET", "")
    with pytest.raises(L.BadRequest):
        L.validate_options({"video_assets": ids})


def test_bringing_clips_copies_them_charges_each_cost_once_and_describes_them(launch_env):
    L, s3 = launch_env
    _ready("u1", "a" * 32, 0.004, audio=True)
    _ready("u1", "b" * 32, 0.003)
    opts = {"video_assets": ["a" * 32, "b" * 32]}
    err, extra = L.bring_video_clips("u1", "vid1", opts, "en")
    assert err is None and extra["c_vidup"] == Decimal("0.007") and extra["cost_usd"] == Decimal("0.007") and extra["vidup_ids"] == ["a" * 32, "b" * 32]
    keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket="assets-x", Prefix="generation/v2/vid1/").get("Contents", []))
    assert keys == ["generation/v2/vid1/assets/uclip_V1.m4a", "generation/v2/vid1/assets/uclip_V1.mp4", "generation/v2/vid1/assets/uclip_V2.mp4"]
    a = opts["video_assets"]
    assert [x["id"] for x in a] == ["V1", "V2"] and a[0]["audio"] is True and a[0]["audio_key"].endswith("V1.m4a") and a[1]["audio"] is False and a[0]["speech"] == "t" and a[1]["speech"] == ""
    err, extra2 = L.bring_video_clips("u1", "vid2", {"video_assets": ["a" * 32]}, "en")                          # a second video using the same clip carries none of its cost
    assert err is None and extra2["c_vidup"] == Decimal("0")
    err, again = L.bring_video_clips("u1", "vid1", {"video_assets": ["a" * 32]}, "en")                           # the same video again (a retry) is still charged to it, once
    assert again["c_vidup"] == Decimal("0.004")


@pytest.mark.parametrize("make", ["missing", "other_user", "not_ready"])
def test_clips_that_are_not_ready_or_not_yours_are_refused_and_nothing_is_copied(launch_env, make):
    L, s3 = launch_env
    _ready("u1", "a" * 32)
    if make == "other_user":
        user = "u2"
    else:
        user = "u1"
    if make == "not_ready":
        V.put_record("u1", "c" * 32, {"status": V.REJECTED, "code": "rejected"})
    cid = {"missing": "d" * 32, "other_user": "a" * 32, "not_ready": "c" * 32}[make]
    err, extra = L.bring_video_clips(user, "vid", {"video_assets": [cid]}, "en")
    assert err["statusCode"] == 400 and json.loads(err["body"])["code"] == "clip_not_ready" and extra == {}
    assert not s3.list_objects_v2(Bucket="assets-x").get("Contents")


def test_the_plan_limits_the_clips_per_video():
    cfg = plans.config()
    for plan, n, ok in (("free", 2, True), ("free", 3, False), ("pro", 4, True), ("pro", 5, False), ("max", 6, True)):
        opts = {"video_assets": ["a" * 32] * n, "target_minutes": 0.25}
        if ok:
            plans.check_create(opts, plan, cfg)
        else:
            with pytest.raises(plans.PlanError) as e:
                plans.check_create(opts, plan, cfg)
            assert e.value.code == "plan_video_clips" and e.value.requires_plan in ("pro", "max")
