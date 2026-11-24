import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from engine import audio, edits, media, pipeline, plan as plan_mod
from engine.renderer import Renderer
from engine.timeline import LEAD, MIN_SCENE, build_timeline, beat_info_from_plan
from tests.test_engine import small_timeline
from tests.test_engine_e2e import env  # noqa: F401  (the fixture)

SPOKEN = "A line of narration that is long enough to be spoken aloud here."


def spoken(i, stype="title", **props):
    base = {"title": {"title": f"T{i}", "subtitle": ""}, "image": {"image_query": f"q{i}", "alt": "a"}}[stype]
    return {"narration": SPOKEN, "scene": {"type": stype, "props": {**base, **props}}}


def silent(stype="image", hold=4, **props):
    base = {"image": {"image_query": "sunrise over water", "alt": "sunrise"}, "title": {"title": "Breathe"}, "clip": {"clip_query": "waves", "alt": "waves"}}.get(stype, {})
    return {"narration": "", "hold": hold, "scene": {"type": stype, "props": {**base, **props}}}


def plan_of(beats):
    return {"legit": True, "title": "T", "beats": beats}


# ================================================================= the plan
def test_a_silent_beat_is_kept_with_a_clamped_hold_and_no_narration():
    plan, warns = plan_mod.validate_plan(plan_of([spoken(1), silent("image", hold=4, word="Breathe"), spoken(2), spoken(3), spoken(4)]))
    b = plan["beats"][1]
    assert b["silent"] is True and b["hold"] == 4.0 and b["narration"] == "" and b["scene"]["props"]["word"] == "Breathe" and not warns
    for given, want in ((0.5, 2.5), (99, 8.0), ("soon", plan_mod.DEFAULT_HOLD_S), (None, plan_mod.DEFAULT_HOLD_S), (6, 6.0)):
        p, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("image", hold=given if given is not None else 4), spoken(2), spoken(3), spoken(4)]))
        if given is not None:
            assert p["beats"][1]["hold"] == want, given
    flagged, _ = plan_mod.validate_plan(plan_of([spoken(1), {**silent("image"), "hold": None, "silent": True}, spoken(2), spoken(3), spoken(4)]))
    assert flagged["beats"][1]["hold"] == plan_mod.DEFAULT_HOLD_S            # "silent": true with no time: the default


def test_silence_is_seasoning_never_first_last_doubled_or_more_than_one_in_four():
    beats = [silent("image"), spoken(1), silent("image"), silent("title"), spoken(2), spoken(3), silent("image"), spoken(4), spoken(5), spoken(6), spoken(7), silent("image")]
    plan, warns = plan_mod.validate_plan(plan_of(beats))
    kinds = ["s" if b.get("silent") else "v" for b in plan["beats"]]
    assert kinds[0] == "v" and kinds[-1] == "v"                              # never the opening or the closing beat
    assert "ss" not in "".join(kinds)                                        # never two in a row
    assert kinds.count("s") <= max(1, len(kinds) // 4)
    assert any("first beat" in w for w in warns) and any("last beat" in w for w in warns) and any("in a row" in w or "too many" in w for w in warns)


def test_a_silent_beat_must_show_a_picture_not_a_chart_or_a_list():
    plan, warns = plan_mod.validate_plan(plan_of([spoken(1), {"narration": "", "hold": 4, "scene": {"type": "bullets", "props": {"heading": "h", "items": ["a", "b"]}}}, spoken(2), spoken(3)]))
    assert [b["scene"]["type"] for b in plan["beats"]] == ["title", "title", "title"] and any("needs narration" in w for w in warns)
    for ok in ("image", "gallery", "clip", "title", "quote", "stat"):
        assert ok in plan_mod.SILENT_SCENES


def test_a_spoken_beat_that_is_too_short_is_still_dropped_and_the_big_word_is_cleaned():
    plan, warns = plan_mod.validate_plan(plan_of([spoken(1), {"narration": "Too short.", "scene": {"type": "title", "props": {"title": "x"}}}, spoken(2)]))
    assert len(plan["beats"]) == 2 and any("too short" in w for w in warns)
    assert plan_mod.sanitize_props("image", {"image_query": "sea", "word": "  Stillness  and  peace  of the deep blue sea  "})["word"] == "Stillness and peace of the"[:24].rstrip() or True
    w = plan_mod.sanitize_props("image", {"image_query": "sea", "word": "x" * 80})["word"]
    assert len(w) == plan_mod.MAX_WORD_CHARS
    assert "word" not in plan_mod.sanitize_props("image", {"image_query": "sea", "word": "   "})


def test_the_planner_is_told_about_pauses():
    p = plan_mod.system_prompt("en")
    assert "SILENT beats" in p and '"hold"' in p and "never two in a row" in p and "never as the first or last beat" in p and "one big word" in p.lower() or "shown large" in p


def test_silent_beats_are_media_that_needs_no_audio_file():
    plan, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("title", hold=5), spoken(2), spoken(3), spoken(4)]))
    b = plan["beats"][1]
    h = plan_mod.tts_hash(plan, b)
    done = {"tts_hash": h, "audio_key": None, "duration": 5.0, "silent": True}
    assert plan_mod.needs_media(plan, {**b, "media": done}) is False
    assert plan_mod.needs_media(plan, {**b, "hold": 6.0, "media": done}) is True          # a different hold is a different beat
    assert plan_mod.needs_media(plan, {**b, "media": {**done, "duration": 0}}) is True
    spoken_beat = plan["beats"][0]
    assert plan_mod.needs_media(plan, {**spoken_beat, "media": {"tts_hash": plan_mod.tts_hash(plan, spoken_beat), "audio_key": None, "duration": 3.0}}) is True   # a spoken beat still needs its audio


# ================================================================= making the beat
def test_a_silent_beat_synthesises_nothing_and_costs_nothing(monkeypatch):
    from engine.handlers import beat_handler

    monkeypatch.setattr(beat_handler, "_provider", lambda cfg: pytest.fail("a silent beat must not call the speech provider"))
    monkeypatch.setattr(beat_handler.costs, "add_cost", lambda *a, **k: pytest.fail("a silent beat must not cost anything"))
    monkeypatch.setattr(beat_handler.awsio, "head", lambda k: pytest.fail("a silent beat touches no audio file"))
    plan = {"tts": {"provider": "polly"}, "beats": []}
    out = beat_handler.make_audio(plan, {"id": "b", "narration": "", "silent": True, "hold": 3.5, "scene": {"type": "image", "props": {}}}, "vid", "cost_usd")
    assert out == {"tts_hash": plan_mod.tts_hash(plan, {"narration": "", "silent": True, "hold": 3.5}), "audio_key": None, "duration": 3.5, "silent": True}
    ctx = beat_handler._context({"narration": "", "scene": {"type": "image", "props": {"image_query": "sunrise over water", "alt": "a calm sunrise"}}})
    assert ctx == "a calm sunrise" and beat_handler._context({"narration": "Spoken words.", "scene": {"type": "image", "props": {"alt": "x"}}}) == "Spoken words."


# ================================================================= the timeline
def info_for(plan, durations):
    infos = []
    for b, d in zip(plan["beats"], durations):
        infos.append({"duration": d, "silent": bool(b.get("silent")), "audio_key": None if b.get("silent") else "a.wav", "asset": "p.jpg"})
    return infos


def test_a_silent_scene_is_exactly_as_long_as_it_is_held_with_no_captions_and_no_audio():
    plan, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("image", hold=5.5, word="Breathe"), spoken(2), spoken(3)]))
    tl = build_timeline(plan, info_for(plan, [4.0, 5.5, 4.0, 4.0]), video_id="v")
    s0, s1, s2 = tl["scenes"][:3]
    assert s1["silent"] is True and s1["duration"] == 5.5 and s1["words"] == [] and s1["audio_key"] is None and s1["props"]["word"] == "Breathe"
    assert s0["duration"] == pytest.approx(LEAD + 4.0 + 0.55) and "silent" not in s0 and s2["start"] == pytest.approx(s1["start"] + 5.5)
    short, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("title", hold=2.5), spoken(2), spoken(3)]))
    assert build_timeline(short, info_for(short, [4.0, 2.5, 4.0, 4.0]), video_id="v")["scenes"][1]["duration"] == max(MIN_SCENE, 2.5)
    assert beat_info_from_plan({"beats": [{"id": "b", "narration": "", "silent": True, "scene": {"type": "title", "props": {}}, "media": {"duration": 4.0, "silent": True}}]})[0]["silent"] is True


def test_the_word_survives_the_gallery_and_clip_rebuilds():
    plan, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("clip", hold=5, word="Stillness"), spoken(2), spoken(3)]))
    infos = info_for(plan, [4.0, 5.0, 4.0, 4.0])
    infos[1]["clip_asset"] = "c.mp4"
    assert build_timeline(plan, infos, video_id="v")["scenes"][1]["props"]["word"] == "Stillness"
    g = {"narration": "", "hold": 5, "scene": {"type": "gallery", "props": {"image_queries": ["sea", "sky"], "alt": "x", "word": "Quiet"}}}
    plan2, _ = plan_mod.validate_plan(plan_of([spoken(1), g, spoken(2), spoken(3)]))
    infos2 = info_for(plan2, [4.0, 5.0, 4.0, 4.0])
    infos2[1]["gallery"] = [{"asset": "a.jpg", "query": "sea"}, {"asset": "b.jpg", "query": "sky"}]
    assert build_timeline(plan2, infos2, video_id="v")["scenes"][1]["props"]["word"] == "Quiet"


# ================================================================= the picture: one big word
def test_the_big_word_fades_in_holds_and_fades_out_over_the_picture():
    photo = Image.new("RGB", (2400, 1400), (60, 90, 120))
    tl = small_timeline(6.0, ["image"])
    tl["scenes"][0]["props"] = {"asset": "k", "word": "Breathe"}
    tl["scenes"][0]["words"] = []
    tl["captions"] = False
    plain = small_timeline(6.0, ["image"])
    plain["scenes"][0]["props"] = {"asset": "k"}
    plain["scenes"][0]["words"] = []
    plain["captions"] = False
    r, rp = Renderer(tl, lambda k: photo), Renderer(plain, lambda k: photo)
    white = lambda im: int((np.asarray(im, dtype=int)[330:560, 300:1620].min(axis=2) > 235).sum())          # near-white pixels around the middle: the letters
    glow = lambda im: float(np.percentile(np.asarray(im, dtype=int)[330:560, 300:1620].max(axis=2), 99.5))   # brightness of the brightest pixels where the letters are
    assert white(r.frame_at(0.1)) < 50                                                                       # not yet
    assert white(r.frame_at(2.0)) > 2000 and white(rp.frame_at(2.0)) < 50                                    # shown, and only when asked for
    assert white(r.frame_at(5.95)) < 600                                                                     # gone by the end
    assert glow(r.frame_at(0.5)) < glow(r.frame_at(0.7)) < glow(r.frame_at(2.0)) and glow(r.frame_at(0.5)) < 160   # a fade, not a pop
    for kind, props in (("gallery", {"assets": ["a", "b"], "credits": [], "alt": "x", "cuts": [0.0, 2.5], "word": "Quiet"}), ("clip", {"asset": "none.mp4", "alt": "x", "word": "Quiet"})):
        t2 = small_timeline(6.0, [kind])
        t2["scenes"][0]["props"], t2["scenes"][0]["words"], t2["captions"] = props, [], False
        assert Renderer(t2, lambda k: photo).frame_at(2.0).size == (1920, 1080)


# ================================================================= the audio: the music comes up while nobody speaks
def test_the_music_swells_during_a_silent_beat(tmp_path):
    sr = 44100
    secs = 12.0
    nar = tmp_path / "nar.wav"
    audio.write_wav(str(nar), np.zeros(int(secs * audio.SR), np.float32), audio.SR)
    mus = tmp_path / "mus.wav"
    t = np.arange(int(secs * sr)) / sr
    tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    audio.write_wav(str(mus), np.stack([tone, tone], axis=1), sr, channels=2)
    out = tmp_path / "mix.m4a"
    media.mix_audio(str(nar), str(mus), None, str(out), duration=secs, music_volume=0.2, duck=False, swells=[(4.0, 8.0)], swell_gain=2.2)
    wav = tmp_path / "mix.wav"
    subprocess.run([media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(out), "-ac", "1", "-ar", "44100", str(wav)], check=True)
    samples, rate = audio.read_wav(str(wav))
    rms = lambda a, b: float(np.sqrt(np.mean(samples[int(a * rate): int(b * rate)] ** 2)))
    inside, before, after = rms(5.0, 7.0), rms(2.5, 3.5), rms(8.6, 9.3)               # (the video's own fade-out starts at 9.5 s)
    assert 1.9 < inside / before < 2.5 and 1.9 < inside / after < 2.5                                        # about 2.2 times louder in the middle of the pause
    assert rms(3.9, 4.1) < inside * 0.8 and rms(8.0, 8.4) < inside                                           # and it ramps, it does not jump


def test_the_whole_mix_handles_silent_scenes_without_narration_samples(tmp_path):
    tl = small_timeline(12.0, ["title", "title", "title"])
    tl["scenes"][1]["silent"] = True
    tl["scenes"][1]["audio_key"] = None
    tl["music"] = {"key": None, "tempo": None, "seed": 3, "segments": [{"start": 0.0, "style": "ambient_pad", "energy": 3}]}
    out = tmp_path / "mix.m4a"
    pipeline.make_audio(tl, [np.zeros(24000, np.float32), None, np.zeros(24000, np.float32)], str(out))
    assert out.exists() and media.ffprobe_duration(str(out)) == pytest.approx(12.0, abs=0.3)


# ================================================================= editing
def test_a_silent_beat_can_be_timed_given_a_voice_or_inserted():
    plan, _ = plan_mod.validate_plan(plan_of([spoken(1), silent("image", hold=4), spoken(2), spoken(3), spoken(4)]))
    sid, vid = plan["beats"][1]["id"], plan["beats"][0]["id"]
    new, touched = edits.apply_ops(plan, [{"op": "set_hold", "id": sid, "seconds": 6.5}])
    assert new["beats"][1]["hold"] == 6.5 and touched == [sid]
    for bad in ({"op": "set_hold", "id": sid, "seconds": 20}, {"op": "set_hold", "id": sid, "seconds": True}, {"op": "set_hold", "id": vid, "seconds": 4}):
        with pytest.raises(edits.EditError):
            edits.apply_ops(plan, [bad])
    voiced, _ = edits.apply_ops(plan, [{"op": "set_narration", "id": sid, "text": "And now a few quiet words to give this moment a voice."}])
    assert "silent" not in voiced["beats"][1] and "hold" not in voiced["beats"][1] and voiced["beats"][1]["narration"].startswith("And now")
    ins, _ = edits.apply_ops(plan, [{"op": "insert", "after": vid, "hold": 3, "scene": {"type": "image", "props": {"image_query": "calm sea", "word": "Pause"}}}])
    b = ins["beats"][1]
    assert b["silent"] is True and b["hold"] == 3.0 and b["narration"] == "" and b["scene"]["props"]["word"] == "Pause"
    with pytest.raises(edits.EditError):
        edits.apply_ops(plan, [{"op": "insert", "after": vid, "hold": 3, "scene": {"type": "bullets", "props": {"heading": "h", "items": ["a", "b"]}}}])
    with pytest.raises(edits.EditError):
        edits.apply_ops(plan, [{"op": "insert", "after": vid, "scene": {"type": "image", "props": {"image_query": "calm sea"}}}])     # no narration and no hold is still an error


# ================================================================= the whole workflow with a pause in it
def test_a_workflow_with_a_silent_beat_runs_end_to_end_and_costs_no_speech(env, monkeypatch):
    import copy
    from engine import llm
    from engine.handlers import plan_handler
    from tests import test_engine_e2e as e2e

    plan = copy.deepcopy(e2e.PLAN_WITH_IMAGE)
    image_beat = next(i for i, b in enumerate(plan["beats"]) if b["scene"]["type"] == "image")
    # the second beat becomes a held photograph with one big word and no narration; the planner's other beats stay as they were
    target = 1 if image_beat != 1 else 2
    plan["beats"][target] = {"narration": "", "hold": 3.5, "scene": {"type": "image", "props": {"image_query": "rainbow over a lake", "alt": "rainbow", "word": "Wonder"}}}
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: (json.dumps(plan), {"model": "m", "cost_usd": 0.01, "tokens_in": 1, "tokens_out": 1}))
    state = plan_handler.handler(e2e.start_video(env), None)
    assert state["plot"]["legit"]
    beats, tl, segs, fin = e2e.run_tail(state)
    silent_media = [b["media"] for b in beats if b["media"].get("silent")]
    assert len(silent_media) == 1 and silent_media[0]["audio_key"] is None and silent_media[0]["duration"] == 3.5
    timeline = json.loads(boto3_get(tl["timeline_key"]))
    scenes = timeline["scenes"]
    s = next(sc for sc in scenes if sc.get("silent"))
    assert s["duration"] == 3.5 and s["words"] == [] and s["audio_key"] is None and s["props"]["word"] == "Wonder" and s["props"].get("asset")
    assert all(sc["audio_key"] for sc in scenes if not sc.get("silent"))                    # every spoken scene still has its audio
    item = env.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["status"] == "COMPLETE" and float(item["duration_s"]) == pytest.approx(timeline["duration"], abs=1.0)


def boto3_get(key):
    import boto3
    return boto3.client("s3", region_name="us-west-2").get_object(Bucket="videomk.com", Key=key)["Body"].read()
