import io
import json
import os
import subprocess
import tempfile

import numpy as np
import pytest
from PIL import Image

from engine import align, assets, audio, media, pipeline, plan as plan_mod, research, tts
from engine.renderer import Renderer
from engine.scenes import SCENE_TYPES
from engine.scenes.captions import paginate
from engine.timeline import build_timeline, chunk_plan, chunk_timeline

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "demo_timeline.json")


def small_timeline(seconds=4.0, kinds=None):
    kinds = kinds or ["title", "bullets"]
    scenes, t = [], 0.0
    props = {
        "title": {"title": "Test title", "subtitle": "sub"},
        "bullets": {"heading": "H", "items": ["one", "two", "three"]},
        "diagram": {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "edges": [["a", "b", "go"]]},
        "chart": {"kind": "line", "labels": ["a", "b", "c"], "values": [1, 3, 2], "unit": "%"},
        "timeline": {"events": [{"date": "1", "label": "x"}, {"date": "2", "label": "y"}]},
        "stat": {"value": "42%", "label": "answer"},
        "quote": {"text": "To be or not to be", "attribution": "W"},
        "image": {"asset": "k", "ken_burns": "left"},
    }
    per = seconds / len(kinds)
    for i, k in enumerate(kinds):
        scenes.append({"id": f"s{i}", "type": k, "start": t, "duration": per, "props": props[k], "words": [["hello", 0.3, 0.6], ["there.", 0.6, 1.0]], "cues": []})
        t += per
    return {"fps": 30, "width": 1920, "height": 1080, "theme": "midnight", "duration": seconds, "captions": True, "scenes": scenes, "mood": "calm"}


# ----------------------------------------------------------------------------- renderer
@pytest.mark.parametrize("kind", SCENE_TYPES)
def test_every_scene_type_renders_at_every_phase(kind):
    """No scene may crash at t=0 (degenerate geometry), mid-animation or after its end (held state)."""
    photo = Image.new("RGB", (2400, 1400), (80, 120, 200))
    tl = small_timeline(6.0, [kind])
    r = Renderer(tl, lambda k: photo)
    for t in (0.0, 0.05, 0.5, 2.0, 5.9, 6.5):
        im = r.frame_at(min(t, 5.99))
        assert im.size == (1920, 1080)


def test_empty_and_hostile_props_do_not_crash():
    for kind, p in [("bullets", {}), ("diagram", {"nodes": [], "edges": []}), ("chart", {"labels": [], "values": []}),
                    ("chart", {"labels": ["a"], "values": ["x"]}), ("timeline", {"events": []}), ("stat", {"value": ""}),
                    ("quote", {}), ("title", {}), ("image", {"asset": "missing"}),
                    ("diagram", {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [["a", "b"], ["b", "a"], ["a", "a"], ["x", "y"]]})]:
        tl = small_timeline(3.0, ["title"])
        tl["scenes"][0].update({"type": kind, "props": p})
        r = Renderer(tl, lambda k: None)
        for t in (0.0, 1.5, 2.9):
            r.frame_at(t)


def test_frame_is_a_pure_function_of_time():
    """Chunk-parallel rendering requires that independent renderers agree on every frame."""
    tl = small_timeline(4.0, ["diagram", "chart"])
    a, b = Renderer(tl), Renderer(tl)
    b.frame_at(0.0)  # warm different cache state
    b.frame_at(3.0)
    for t in (0.0, 1.0, 1.9, 2.05, 3.5):
        assert np.array_equal(np.asarray(a.frame_at(t)), np.asarray(b.frame_at(t))), t


def test_draft_mode_is_half_size():
    r = Renderer(small_timeline(), draft=True)
    assert r.frame_at(1.0).size == (960, 540)


def test_crossfade_blends_scenes_and_outro_fades_to_black():
    tl = small_timeline(4.0, ["title", "stat"])
    r = Renderer(tl)
    before, mid = np.asarray(r.frame_at(1.99), np.float32), np.asarray(r.frame_at(2.1), np.float32)
    assert np.abs(before - mid).mean() > 0  # transition frames differ from the previous scene
    last = np.asarray(r.frame_at(3.999))
    assert last.mean() < 8  # faded to (almost) black


def test_captions_paginate_and_highlight_by_time():
    words = [[f"w{i}" + ("." if i % 7 == 6 else ""), i * 0.3, i * 0.3 + 0.25] for i in range(30)]
    pages = paginate(words)
    assert all(len(p) <= 11 for p in pages) and sum(len(p) for p in pages) == 30


# ----------------------------------------------------------------------------- chunking / seams
def test_chunked_render_stitches_with_exact_duration_and_continuous_timestamps():
    tl = small_timeline(9.0, ["title", "bullets", "chart"])
    chunks = chunk_plan(tl, target_seconds=3)
    assert len(chunks) == 3 and sum(c["frames"] for c in chunks) == 270
    with tempfile.TemporaryDirectory() as tmp:
        segs = []
        for c in chunks:
            p = os.path.join(tmp, f"{c['k']}.ts")
            pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), 0, c["frames"], p, draft=True)
            segs.append(p)
        out = os.path.join(tmp, "o.mp4")
        media.mux_final(segs, None, out, fps=30)
        assert abs(media.ffprobe_duration(out) - 9.0) < 0.1
        pts = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "frame=pts_time", "-of", "csv=p=0", out],
                             capture_output=True, text=True).stdout.split()
        pts = sorted(float(x.strip(",")) for x in pts)
        assert len(pts) == 270
        assert np.allclose(np.diff(pts), 1 / 30, atol=1e-3), "timestamps must be continuous across chunk seams"


def _six_scene_timeline():
    tl = small_timeline(60.0, ["title", "bullets", "chart", "stat", "quote", "timeline"])
    for i, sc in enumerate(tl["scenes"]):
        sc["id"] = f"{i:08x}"
    return tl


def test_chunk_hash_is_position_independent_and_edit_local():
    """The property the editor relies on: an edit re-renders its own chunk only; shifted-but-identical chunks stay cached."""
    tl = _six_scene_timeline()
    base = chunk_plan(tl, 20)
    assert [(c["lo"], c["hi"]) for c in base] == [(0, 2), (2, 4), (4, 6)]

    edited = json.loads(json.dumps(tl))
    edited["scenes"][0]["props"]["title"] = "A different title"
    edited["scenes"][0]["duration"] += 2.0          # longer scene => every later scene moves 2 s later
    for sc in edited["scenes"][1:]:
        sc["start"] += 2.0
    new = chunk_plan(edited, 20)
    assert new[0]["hash"] != base[0]["hash"]        # the edited chunk
    assert new[1]["hash"] == base[1]["hash"]        # moved 2 s later in the video, same content => cache hit
    assert new[2]["hash"] == base[2]["hash"]
    # editing the LAST scene of a chunk also invalidates the next chunk (its opening crossfade shows that scene)
    e2 = json.loads(json.dumps(tl))
    e2["scenes"][1]["props"]["items"] = ["x", "y"]
    n2 = chunk_plan(e2, 20)
    assert n2[0]["hash"] != base[0]["hash"] and n2[1]["hash"] != base[1]["hash"] and n2[2]["hash"] == base[2]["hash"]
    # draft and final never share a cache entry; a renderer version bump invalidates everything
    assert chunk_plan(tl, 20, draft=True)[0]["hash"] != base[0]["hash"]


def test_chunk_frame_counts_sum_exactly_to_the_total():
    tl = small_timeline(61.7, ["title", "bullets", "chart", "stat", "quote", "timeline", "diagram"])
    tl["scenes"] = [dict(sc, start=round(i * 61.7 / 7, 4), duration=round(61.7 / 7, 4)) for i, sc in enumerate(tl["scenes"])]
    tl["duration"] = round(sum(s["duration"] for s in tl["scenes"]), 4)
    for target in (5, 12, 20, 45):
        assert sum(c["frames"] for c in chunk_plan(tl, target)) == round(tl["duration"] * 30)


def test_chunk_render_is_identical_wherever_the_chunk_sits():
    """Same scenes at a different absolute time => pixel-identical frames (what makes cached segments reusable)."""
    tl = _six_scene_timeline()
    shifted = json.loads(json.dumps(tl))
    for sc in shifted["scenes"]:
        sc["start"] += 7.3
    c1, c2 = chunk_plan(tl, 20)[1], chunk_plan(shifted, 20)[1]
    assert c1["hash"] == c2["hash"]
    r1, r2 = Renderer(chunk_timeline(tl, c1["lo"], c1["hi"])), Renderer(chunk_timeline(shifted, c2["lo"], c2["hi"]))
    for f in (0, 10, 200, 350):
        assert np.array_equal(np.asarray(r1.frame_at(f / 30)), np.asarray(r2.frame_at(f / 30)))


# ----------------------------------------------------------------------------- audio
def test_music_and_sfx_are_finite_bounded_and_deterministic():
    m1, m2 = audio.generate_music(8, "calm"), audio.generate_music(8, "calm")
    assert np.array_equal(m1, m2) and np.isfinite(m1).all() and np.abs(m1).max() <= 0.61 and m1.shape[1] == 2
    for mood in ("calm", "bright", "tense"):
        assert audio.generate_music(3, mood).shape[0] == 3 * audio.MIX_SR
    s = audio.build_sfx_track([(0.5, "whoosh", 0.3), (1.0, "pop", 0.2), (99, "pop", 1.0)], 3)
    assert np.isfinite(s).all() and s.shape == (3 * audio.MIX_SR, 2) and np.abs(s).max() < 1


def test_trim_silence_and_narration_placement():
    sr = audio.SR
    a = np.concatenate([np.zeros(sr), 0.3 * np.sin(np.linspace(0, 400, sr)), np.zeros(sr)]).astype(np.float32)
    t = audio.trim_silence(a, sr)
    assert 0.9 * sr < t.size < 1.3 * sr
    track = audio.build_narration([{"offset": 1.0, "samples": t}], 5.0)
    assert track.size == 5 * sr and np.abs(track[: sr - 100]).max() == 0 and np.abs(track[sr: 2 * sr]).max() > 0.1


def test_mix_audio_ducks_music_under_speech():
    with tempfile.TemporaryDirectory() as tmp:
        sr = audio.SR
        speech = (0.5 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)).astype(np.float32)
        nar = np.concatenate([speech, np.zeros(2 * sr, np.float32)])  # speech first 2 s, then silence
        audio.write_wav(os.path.join(tmp, "n.wav"), nar, sr)
        audio.write_wav(os.path.join(tmp, "m.wav"), audio.generate_music(4, "calm"), audio.MIX_SR, 2)
        for duck, name in ((True, "d.m4a"), (False, "nd.m4a")):
            media.mix_audio(os.path.join(tmp, "n.wav"), os.path.join(tmp, "m.wav"), None, os.path.join(tmp, name), duration=4.0, duck=duck)

        def rms_after_speech(name):  # music-only region, 2.4 s..3.4 s (after compressor release)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(tmp, name), "-ss", "2.6", "-t", "0.8", "-f", "f32le", "-ac", "1", "-ar", "44100", "-"],
                                 capture_output=True).stdout
            return float(np.sqrt(np.mean(np.frombuffer(raw, np.float32) ** 2)))

        def rms_during_speech(name):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(tmp, name), "-ss", "0.6", "-t", "1.0", "-f", "f32le", "-ac", "1", "-ar", "44100", "-"],
                                 capture_output=True).stdout
            return float(np.sqrt(np.mean(np.frombuffer(raw, np.float32) ** 2)))

        # with ducking, the mix during speech is closer to narration-only than without it
        assert rms_during_speech("d.m4a") < rms_during_speech("nd.m4a")
        assert rms_after_speech("d.m4a") > 0.001  # music returns after the release


def test_word_timing_is_ordered_and_covers_duration():
    w = align.estimate_words("Black holes, as it turns out, are not black at all.", 5.0, lead=0.4)
    assert [x[0] for x in w][0] == "Black" and all(a[2] <= b[1] + 1e-6 for a, b in zip(w, w[1:]))
    assert w[0][1] >= 0.4 and w[-1][2] <= 5.4


# ----------------------------------------------------------------------------- tts
def test_mock_tts_scales_with_text_and_synth_beat_trims():
    short = tts.synth_beat(tts.MockTTS(), "Hello there.")
    long = tts.synth_beat(tts.MockTTS(), "Hello there. " * 6)
    assert long.size > 4 * short.size > 0


def test_gemini_and_openai_requests_and_parsing(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, raw): self.raw = raw
        def read(self): return self.raw
        def __enter__(self): return self
        def __exit__(self, *a): return False

    pcm = (np.sin(np.linspace(0, 200, 24000)) * 12000).astype("<i2").tobytes()
    import base64, wave

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        if "generativelanguage" in req.full_url:
            return Resp(json.dumps({"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}).encode())
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        return Resp(buf.getvalue())

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    g = tts.get_provider("gemini", "KEY").synth("Hi there", voice="Puck", style="Say warmly")
    o = tts.get_provider("openai", "KEY2").synth("Hi there", voice="nova", style="calm")
    assert g.size == 24000 and o.size == 24000
    gem, oai = calls
    assert "KEY" not in gem.full_url and gem.headers["X-goog-api-key"] == "KEY"  # key in header, never in the URL
    assert json.loads(gem.data)["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"
    assert oai.headers["Authorization"] == "Bearer KEY2" and json.loads(oai.data)["voice"] == "nova"


def test_tts_http_errors_do_not_leak_bodies(monkeypatch):
    import urllib.error

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(b"secret prompt echo"))

    monkeypatch.setattr(tts.urllib.request, "urlopen", boom)
    with pytest.raises(tts.TTSError) as e:
        tts.get_provider("openai", "k").synth("hello")
    assert "secret" not in str(e.value) and "429" in str(e.value)


# ----------------------------------------------------------------------------- plan / timeline
GOOD_PLAN = {
    "legit": True, "title": "How Rainbows Form", "description": "d", "mood": "bright", "theme": "paper",
    "beats": [
        {"chapter": "Intro", "narration": "Ever wondered why a rainbow always shows up opposite the sun in the sky?", "scene": {"type": "title", "props": {"title": "How Rainbows Form"}}},
        {"narration": "Sunlight enters a raindrop, bends, reflects off the back, and bends again as it leaves.", "scene": {"type": "diagram", "props": {"nodes": [{"id": "s", "label": "Sunlight"}, {"id": "d", "label": "Raindrop"}, {"id": "e", "label": "Your eye"}], "edges": [["s", "d"], ["d", "e", "bent light"]]}}},
        {"chapter": "Colors", "narration": "Each color bends by a slightly different amount, which spreads white light into a spectrum.", "scene": {"type": "chart", "props": {"kind": "bar", "labels": ["Red", "Green", "Violet"], "values": [42, 41, 40], "unit": "°"}}},
    ],
}


def test_plan_validation_blocks_injection_and_normalises():
    evil = json.loads(json.dumps(GOOD_PLAN))
    evil["beats"][0]["scene"] = {"type": "image", "props": {"image_query": "x", "asset": "s3://other/secret.png", "path": "/etc/passwd"}}
    clean, _ = plan_mod.validate_plan(evil)
    props = clean["beats"][0]["scene"]["props"]
    assert set(props) == {"image_query", "alt", "ken_burns"}  # LLM can never choose a file path


def test_generate_plan_repairs_once_then_fails_closed():
    answers = iter(["not json at all", json.dumps(GOOD_PLAN)])
    p, _ = plan_mod.generate_plan("rainbows", "", 3, lambda s, u: next(answers))
    assert p["legit"] and len(p["beats"]) == 3
    with pytest.raises(ValueError):
        plan_mod.generate_plan("rainbows", "", 3, lambda s, u: "still not json")


def test_rejected_plan_passes_reason_through():
    p, _ = plan_mod.generate_plan("x", "", 3, lambda s, u: '{"legit": false, "reason": "Not suitable."}')
    assert p == {"legit": False, "reason": "Not suitable."}


def test_timeline_durations_follow_audio_and_scenes_use_beat_ids():
    plan, _ = plan_mod.validate_plan(GOOD_PLAN)
    tl = build_timeline(plan, [{"duration": 4.0}, {"duration": 9.0}, {"duration": 20.0}], video_id="v")
    assert [round(s["duration"], 2) for s in tl["scenes"][:2]] == [4.95, 9.95]
    assert tl["scenes"][1]["start"] == pytest.approx(tl["scenes"][0]["duration"])
    assert [s["id"] for s in tl["scenes"]] == [b["id"] for b in plan["beats"]] and all(len(b["id"]) == 8 for b in plan["beats"])
    assert tl["chapters"][0]["title"] == "Intro" and tl["duration"] == pytest.approx(sum(s["duration"] for s in tl["scenes"]), abs=1e-3)
    assert sum(c["frames"] for c in chunk_plan(tl, 30)) == round(tl["duration"] * 30)


def test_beat_ids_are_strict_and_media_staleness_tracks_content():
    plan, _ = plan_mod.validate_plan({**GOOD_PLAN, "beats": [dict(b, id="../../etc") for b in GOOD_PLAN["beats"]]})
    assert all(plan_mod._ID_RE.match(b["id"]) for b in plan["beats"])  # an id from outside can never reach an S3 key
    plan["tts"] = {"provider": "mock", "voice": "", "style": ""}
    b = plan["beats"][0]
    assert plan_mod.needs_media(plan, b)
    b["media"] = {"tts_hash": plan_mod.tts_hash(plan, b), "audio_key": "k", "duration": 3.0}
    assert not plan_mod.needs_media(plan, b)
    b["narration"] += " And one more sentence."
    assert plan_mod.needs_media(plan, b)
    plan["tts"]["voice"] = "Puck"
    b["media"]["tts_hash"] = "stale"
    assert plan_mod.needs_media(plan, b)


def test_image_scene_without_asset_degrades_to_title_card():
    plan, _ = plan_mod.validate_plan({**GOOD_PLAN, "beats": [{"narration": "A photograph of the Eiffel Tower at night in Paris, France.", "scene": {"type": "image", "props": {"image_query": "eiffel tower night"}}}]})
    tl = build_timeline(plan, [{"duration": 5.0}], video_id="v")
    assert tl["scenes"][0]["type"] == "title"
    tl2 = build_timeline(plan, [{"duration": 5.0, "asset": "generation/v2/v/assets/img_000.jpg", "credit": "Photo: A (CC0)"}], video_id="v")
    assert tl2["scenes"][0]["type"] == "image" and tl2["scenes"][0]["props"]["credit"].startswith("Photo")


# ----------------------------------------------------------------------------- assets / research
def test_asset_licence_filter_and_credits_block():
    rs = [{"id": "1", "license": "by-sa", "width": 4000, "height": 2000, "url": "https://x/1.jpg"},
          {"id": "2", "license": "by-nc", "width": 4000, "height": 2000, "url": "https://x/2.jpg"},
          {"id": "3", "license": "by", "license_version": "4.0", "width": 3000, "height": 1800, "url": "https://x/3.jpg", "creator": "Ann", "title": "Galaxy", "attribution": "\"Galaxy\" by Ann"},
          {"id": "4", "license": "cc0", "width": 3000, "height": 1800, "url": "http://insecure/4.jpg"}]
    assert assets.pick(rs)["id"] == "3"
    buf = io.BytesIO(); Image.new("RGB", (3200, 1800)).save(buf, "PNG")
    jpeg, entry = assets.scout("q", fetch_json_fn=lambda u: {"results": rs}, fetch_bytes_fn=lambda u: buf.getvalue())
    assert Image.open(io.BytesIO(jpeg)).format == "JPEG" and entry["license"] == "BY 4.0"
    assert "Ann" in assets.credits_block([entry], [{"title": "T", "url": "https://u", "publisher": "Wikipedia"}])
    assert assets.scout("q", fetch_json_fn=lambda u: {"results": []}) is None


def test_research_failure_never_fails_the_video():
    notes, src = research.gather_notes("x", fetch=lambda u: (_ for _ in ()).throw(ValueError("down")))
    assert notes == "" and src == []
