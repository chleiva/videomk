import io
import json
import os
import subprocess
import tempfile
import urllib.parse

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
        "clip": {"asset": "k", "alt": "waves"},
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


def _flat_plan():
    beats = [
        {"narration": "The Eiffel Tower was finished in 1889 for the World's Fair and is the tallest structure in Paris today.",
         "scene": {"type": "image", "image_query": "Eiffel Tower golden hour", "alt": "The Eiffel Tower"}},
        {"narration": "Notre-Dame began in 1163 and the Louvre opened as a public museum during the French Revolution in 1793.",
         "scene": {"type": "bullets", "heading": "Landmarks", "items": ["Notre-Dame, 1163", "The Louvre, 1793"]}},
    ]
    return {"legit": True, "title": "Paris", "description": "d", "mood": "calm", "theme": "midnight", "beats": beats}


def test_validate_plan_accepts_props_flattened_onto_the_scene():
    clean, warns = plan_mod.validate_plan(_flat_plan())
    assert warns == []
    assert [b["scene"]["type"] for b in clean["beats"]] == ["image", "bullets"]
    assert clean["beats"][0]["scene"]["props"]["image_query"] == "Eiffel Tower golden hour"


def test_generate_plan_repairs_when_most_scenes_are_replaced():
    bad = _flat_plan()
    for b in bad["beats"]:
        b["scene"] = {"type": "bullets", "props": {"heading": "H", "items": "not a list"}}
    answers = iter([json.dumps(bad), json.dumps(_flat_plan())])
    seen = []

    def ask(s, u):
        seen.append(u)
        return next(answers)

    p, warns = plan_mod.generate_plan("paris", "", 1, ask)
    assert len(seen) == 2 and "most scenes were invalid" in seen[1]
    assert warns == [] and p["beats"][0]["scene"]["type"] == "image"


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


# ----------------------------------------------------------------------------- edit ops
def _plan_with_beats():
    plan, _ = plan_mod.validate_plan(GOOD_PLAN)
    return plan


def test_insert_refs_let_one_batch_edit_and_order_beats_it_just_created():
    from engine import edits as E

    plan = _plan_with_beats()
    first = plan["beats"][0]["id"]
    ops = [
        {"op": "insert", "ref": "a", "after": first, "narration": "A brand new first beat about the wonder of light in water.", "scene": {"type": "title", "props": {"title": "New"}}},
        {"op": "insert", "ref": "b", "after": "ref:a", "narration": "And a second new beat that follows the first new beat directly.", "scene": {"type": "stat", "props": {"value": "7", "label": "colors"}}},
        {"op": "set_narration", "id": "ref:a", "text": "A rewritten first beat about the wonder of light in water droplets."},
        {"op": "move", "id": "ref:b", "to": 0},
    ]
    new, touched = E.apply_ops(plan, ops)
    assert new["beats"][0]["scene"]["type"] == "stat"                       # ref:b, moved to the front
    assert new["beats"][1]["id"] == first                                     # the original first beat
    assert new["beats"][2]["narration"].startswith("A rewritten first beat")  # ref:a, edited after it was inserted
    assert len(touched) == 2 and len({b["id"] for b in new["beats"]}) == len(new["beats"])
    for bad in ([{"op": "set_narration", "id": "ref:nope", "text": "one two three four five six seven"}],
                [{"op": "insert", "ref": "x y", "narration": "word " * 8, "scene": {"type": "title", "props": {"title": "t"}}}],
                [{"op": "insert", "ref": "d", "narration": "word " * 8, "scene": {"type": "title", "props": {"title": "t"}}}, {"op": "insert", "ref": "d", "narration": "word " * 8, "scene": {"type": "title", "props": {"title": "t"}}}]):
        with pytest.raises(E.EditError):
            E.apply_ops(plan, bad)


def test_every_edit_op_is_validated_and_the_input_plan_is_never_mutated():
    from engine import edits as E
    import copy

    plan = _plan_with_beats()
    snapshot = copy.deepcopy(plan)
    ids = [b["id"] for b in plan["beats"]]
    good = [
        {"op": "set_scene", "id": ids[1], "type": "bullets", "props": {"heading": "H", "items": ["a", "b"]}},
        {"op": "set_chapter", "id": ids[2], "title": "Colors"}, {"op": "set_meta", "title": "New title", "theme": "paper", "mood": "bright"},
        {"op": "set_voice", "voice": "Matthew", "style": "Say it calmly"},
    ]
    new, _ = E.apply_ops(plan, good)
    assert new["theme"] == "paper" and new["tts"]["voice"] == "Matthew" and new["beats"][1]["scene"]["type"] == "bullets"
    assert plan == snapshot
    for bad in ([{"op": "set_meta", "theme": "neon"}], [{"op": "set_voice", "voice": "../x"}], [{"op": "move", "id": ids[0], "to": 99}], [{"op": "set_scene", "id": ids[0], "type": "bullets", "props": {"items": ["only one"]}}],
                [{"op": "set_narration", "id": ids[0], "text": "too short"}], [{"op": "set_narration", "id": ids[0], "text": "word " * 90}], [{"op": "pick_image", "id": ids[0], "candidate": "unsplash:x"}], [], "nope", [{"op": "set_meta", "title": "  "}]):
        with pytest.raises(E.EditError):
            E.apply_ops(plan, bad)
    with pytest.raises(E.EditError):
        E.apply_ops(plan, [{"op": "set_chapter", "id": ids[0], "title": "x"}] * 41)


def test_llm_request_shape_per_model_generation(monkeypatch):
    """Claude 5.x rejects `temperature` (400) and takes output_config.effort; older models still take temperature."""
    from engine import llm

    sent = []

    class FakeBody:
        def read(self):
            return json.dumps({"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()

    class FakeClient:
        def invoke_model(self, modelId, body):
            sent.append((modelId, json.loads(body)))
            return {"body": FakeBody()}

    monkeypatch.setattr(llm, "_bedrock", lambda: FakeClient())
    _, meta = llm.complete("s", "u", model="eu.anthropic.claude-sonnet-5-5", temperature=0.3, effort="low")
    _, _ = llm.complete("s", "u", model="eu.anthropic.claude-sonnet-4-6", temperature=0.3)
    new, old = sent[0][1], sent[1][1]
    assert "temperature" not in new and new["output_config"] == {"effort": "low"}
    assert old["temperature"] == 0.3 and "output_config" not in old
    assert meta["cost_usd"] == pytest.approx((10 * 2.0 + 5 * 10.0) / 1_000_000)  # Sonnet 5.5: $2 / $10 per 1M
    assert llm.estimate_cost("eu.anthropic.claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)


def test_polly_provider_requests_neural_pcm_and_resamples():
    import io as _io

    sent = {}
    pcm = (np.sin(np.linspace(0, 440, 16000)) * 12000).astype("<i2").tobytes()  # 1 s at 16 kHz

    class FakePolly:
        def synthesize_speech(self, **kw):
            sent.update(kw)
            return {"AudioStream": _io.BytesIO(pcm)}

    p = tts.get_provider("polly")
    p._client = FakePolly()
    a = p.synth("Hello there.", voice="Matthew", style="ignored")
    assert sent["Engine"] == "neural" and sent["OutputFormat"] == "pcm" and sent["SampleRate"] == "16000" and sent["VoiceId"] == "Matthew"
    assert abs(a.size - tts.SR) <= 2 and a.dtype == np.float32  # 1 s at 16 kHz -> 1 s at SR
    p._client = type("Empty", (), {"synthesize_speech": lambda self, **kw: {"AudioStream": _io.BytesIO(b"")}})()
    with pytest.raises(tts.TTSError):
        p.synth("x")
    assert tts.DEFAULT_PROVIDER == "polly" or os.environ.get("TTS_PROVIDER")


def test_photo_review_budget_leaves_room_for_the_whole_json():
    """A truncated review ('no JSON') silently degrades photo choice to the first search result: keep the cap generous."""
    from engine import stock

    seen = {}

    def fake_complete(system, user, **kw):
        seen.update(kw)
        return '{"choice": 2, "scores": [1, 9], "reason": "Clear view of the tower."}', {"cost_usd": 0.0}

    c = [{"thumb_url": "https://x/a", "provider": "unsplash", "id": str(i)} for i in range(2)]
    jpg = io.BytesIO()
    Image.new("RGB", (64, 36), (10, 20, 30)).save(jpg, "JPEG")
    idx, reason, _, _ = stock.llm_review(c, "n", "alt", "q", fetch_bytes_fn=lambda *a, **k: jpg.getvalue(), complete=fake_complete)
    assert idx == 1 and seen["max_tokens"] >= 800
    assert "at most 15 words" in stock.REVIEW_SYSTEM


def test_polly_engine_region_cost_and_cache_key():
    from engine import plan as plan_mod

    p = tts.get_provider("polly", "", {"engine": "generative", "region": "us-east-1"})
    assert p.engine == "generative" and p._region == "us-east-1" and p.cost_per_char == 0.00003
    old = tts.get_provider("polly", "", {})  # plans made before the engine was recorded
    assert old.engine == "neural" and old._region is None
    assert tts.get_provider("polly", "", {"engine": "long-form", "region": "us-east-1"}).cost_per_char == 0.0001

    beat = {"narration": "Same words."}
    legacy = {"tts": {"provider": "polly", "voice": "Ruth", "style": "s"}}
    gen = {"tts": {"provider": "polly", "voice": "Ruth", "style": "s", "engine": "generative", "region": "us-east-1"}}
    neural = {"tts": {"provider": "polly", "voice": "Ruth", "style": "s", "engine": "neural", "region": "eu-west-1"}}
    assert len({plan_mod.tts_hash(x, beat) for x in (legacy, gen, neural)}) == 3  # different engines never share cached audio
    assert plan_mod.tts_hash(legacy, beat) == plan_mod.tts_hash({"tts": {"provider": "polly", "voice": "Ruth", "style": "s"}}, beat)


# ---------------------------------------------------------------- casting: one narrator or a dialogue of up to 3 voices
def _plan_with(voices, speakers):
    beats = [{"narration": f"This is spoken line number {i} of the conversation.", "speaker": s, "scene": {"type": "title", "props": {"title": f"T{i}"}}}
             for i, s in enumerate(speakers)]
    return {"legit": True, "title": "T", "voices": voices, "beats": beats}


def test_voice_catalogue_covers_every_english_and_spanish_generative_voice():
    from engine import voices

    assert voices.canonical("matthew") == "Matthew" and voices.canonical(" RUTH ") == "Ruth" and voices.canonical("Zhiyu") is None
    assert len(voices.names("en")) == 21 and len(voices.names("es")) == 7
    assert voices.canonical("Lupe", "en") is None and voices.canonical("Lupe", "es") == "Lupe"  # a voice only works in its own language
    for lang in ("en", "es"):  # a woman and a man are always available for a dialogue
        assert {voices.CATALOG[n][2] for n in voices.names(lang)} == {"female", "male"}


def test_default_voice_follows_the_viewers_region_and_the_brief_can_override():
    from engine import voices

    d = voices.default_voice
    assert [d("en", r) for r in (None, "US", "us", "CA", "FR", "GB", "IN", "AU", "IE", "NZ", "ZA", "SG")] == \
        ["Ruth", "Ruth", "Ruth", "Ruth", "Ruth", "Amy", "Kajal", "Olivia", "Niamh", "Aria", "Ayanda", "Jasmine"]  # Canada: no Canadian voice, so American
    assert [d("es", r) for r in (None, "ES", "MX", "AR", "CO", "CL", "PE", "US", "FR")] == ["Lucia", "Lucia", "Mia", "Mia", "Mia", "Mia", "Mia", "Lupe", "Lucia"]
    assert voices.clean_region(" gb ") == "GB" and voices.clean_region("GBR") is None and voices.clean_region("1A") is None and voices.clean_region(None) is None
    assert voices.clean_cast(None, "en", "IN") == {"narrator": "Kajal"} and voices.clean_cast({"narrator": "Brian"}, "en", "IN") == {"narrator": "Brian"}
    p_in = plan_mod.system_prompt("en", "IN")
    assert "The viewer is in IN" in p_in and "default voice is Kajal (Indian)" in p_in and "The brief always wins" in p_in
    assert "The viewer is in" not in plan_mod.system_prompt("en") and "default voice is Ruth (American)" in plan_mod.system_prompt("en")
    assert "default voice is Lucia (Spanish (Spain))" in plan_mod.system_prompt("es") and "default voice is Mia (Mexican)" in plan_mod.system_prompt("es", "MX")
    assert "Ruth (American, female)" in plan_mod.system_prompt("en") and "Lupe" not in plan_mod.system_prompt("en") and "DIFFERENT voices" in plan_mod.system_prompt("en")


def test_spanish_plans_get_spanish_voices_only():
    from engine import voices

    plan, warns = plan_mod.validate_plan(_plan_with({"ana": "Lupe", "luis": "Matthew", "eva": "Mia"}, ["ana", "luis", "eva"]), language="es")
    assert plan["language"] == "es" and plan["voices"]["ana"] == "Lupe" and plan["voices"]["eva"] == "Mia"
    assert voices.language_of(plan["voices"]["luis"]) == "es" and plan["voices"]["luis"] not in ("Lupe", "Mia")  # Luis keeps his lines, with a Spanish voice
    assert voices.CATALOG[plan["voices"]["luis"]][2] == "male"  # and, being the one that had to be replaced, a different gender from the speaker before
    assert any("voices adjusted" in w for w in warns)
    assert plan_mod.validate_plan(_plan_with(None, [None]), language="es")[0]["voices"] == {"narrator": "Lucia"}
    assert plan_mod.validate_plan(_plan_with(None, [None]), language="es", region="MX")[0]["voices"] == {"narrator": "Mia"}
    assert plan_mod.validate_plan(_plan_with(None, [None]))[0]["voices"] == {"narrator": "Ruth"} and plan_mod.validate_plan(_plan_with(None, [None]))[0]["language"] == "en"


def test_language_detection_is_free_when_clear_and_declines_unsupported_languages():
    from engine import language

    asked = []

    def ask(system, user):
        asked.append(user)
        return {"Quelle est l'histoire de Paris et de sa tour ?": "fr", "???": "xx"}.get(user, "es")

    assert language.detect("Explica cómo funciona un volcán, para niños", ask) == "es"
    assert language.detect("A visual tour of the most famous landmarks of Paris", ask) == "en"
    assert language.detect("¿Por qué el cielo es azul?", ask) == "es"
    assert asked == []  # clear briefs never cost a model call
    assert language.detect("Historia de Roma", ask) == "es" and asked == ["Historia de Roma"]  # shared words ("de") never decide alone: ask
    assert language.detect("Napoleon Bonaparte", ask) == "es" and asked[-1] == "Napoleon Bonaparte"  # a name alone: the small model decides
    asked.clear()
    assert language.heuristic("Quelle est l'histoire de Paris et de sa tour ?") is None  # French is not mistaken for Spanish
    assert language.heuristic("Explique-moi pourquoi le ciel est bleu, dans le détail") is None
    assert language.heuristic("Cómo funciona la fotosíntesis") is None and language.heuristic("Explica cómo funciona la fotosíntesis, ¿por qué?") == "es"
    assert language.detect("Quelle est l'histoire de Paris et de sa tour ?", ask) == "other" and asked == ["Quelle est l'histoire de Paris et de sa tour ?"]
    assert language.detect("???", ask) == "en"  # cannot tell: English
    assert language.detect("Napoleon Bonaparte", lambda s, u: (_ for _ in ()).throw(RuntimeError("down"))) == "en"  # a failing model never fails the video
    assert "English and Spanish" in language.unsupported_message()


def test_research_reads_the_wikipedia_of_the_videos_language():
    from engine import research

    urls = []

    def fake(url, **kw):
        urls.append(url)
        if "list=search" in url:
            return {"query": {"search": [{"title": "Volcán"}]}}
        return {"query": {"pages": [{"title": "Volcán", "fullurl": "https://es.wikipedia.org/wiki/Volc%C3%A1n", "extract": "Un volcán es una estructura geológica. " * 12}]}}

    notes, sources = research.gather_notes("volcanes", fetch=fake, language="es")
    assert all(u.startswith("https://es.wikipedia.org/") for u in urls) and "volcán" in notes.lower()
    assert sources[0]["publisher"] == "Wikipedia (es)"
    urls.clear()
    research.gather_notes("volcanoes", fetch=fake)
    assert all(u.startswith("https://en.wikipedia.org/") for u in urls)


def test_a_dialogue_keeps_up_to_three_characters_and_a_narrator_with_distinct_real_voices():
    from engine import voices

    c = voices.clean_cast({"narrator": "Olivia", "Maya": "ruth", "Sam": "Matthew", "Lee": "Amy", "Extra": "Brian", "bad id!": "Nate"})
    assert list(c) == ["narrator", "maya", "sam", "lee"] and list(c.values()) == ["Olivia", "Ruth", "Matthew", "Amy"]  # 3 characters + narrator; the rest is dropped
    assert voices.clean_cast({"narrator": "Nonexistent"}) == {"narrator": voices.default_voice("en")}
    assert voices.clean_cast(None) == {"narrator": voices.default_voice("en")}
    dup = voices.clean_cast({"a": "Ruth", "b": "Ruth"})  # two speakers on one voice would be unintelligible
    assert dup["a"] == "Ruth" and dup["b"] != "Ruth" and voices.CATALOG[dup["b"]][2] != voices.CATALOG["Ruth"][2]


def test_validate_plan_casts_speakers_and_defaults_the_rest_to_the_narrator():
    plan, warns = plan_mod.validate_plan(_plan_with({"maya": "Ruth", "sam": "Matthew"}, ["maya", "sam", "ghost", None]))
    assert plan["voices"] == {"maya": "Ruth", "sam": "Matthew"}
    assert [b.get("speaker") for b in plan["beats"]] == ["maya", "sam", None, None]  # unknown or absent speaker -> narrator
    solo, _ = plan_mod.validate_plan(_plan_with(None, [None, None]))
    assert solo["voices"] == {"narrator": "Ruth"}


def test_each_beat_gets_its_speakers_voice_and_a_voice_change_remakes_only_that_audio():
    from engine import voices

    plan, _ = plan_mod.validate_plan(_plan_with({"maya": "Ruth", "sam": "Matthew"}, ["maya", "sam", "maya"]))
    plan["tts"] = {"provider": "polly", "style": "s", "engine": "generative", "region": "us-east-1"}
    b = plan["beats"]
    assert [voices.beat_voice(plan, x) for x in b] == ["Ruth", "Matthew", "Ruth"]
    hashes = [plan_mod.tts_hash(plan, x) for x in b]
    assert hashes[0] != hashes[1]  # same engine, different voice: different audio
    plan["voices"]["sam"] = "Stephen"
    assert plan_mod.tts_hash(plan, b[0]) == hashes[0] and plan_mod.tts_hash(plan, b[1]) != hashes[1]  # only Sam's lines are re-voiced
    other = dict(plan, tts={"provider": "gemini", "voice": "Puck", "style": "s"})
    assert voices.beat_voice(other, b[1]) == "Puck"  # the cast is Polly-only


def test_legacy_plans_without_a_cast_keep_their_audio_cache_keys():
    legacy = {"tts": {"provider": "polly", "voice": "Ruth", "style": "s"}, "beats": []}
    beat = {"narration": "Same words."}
    raw = json.dumps(["polly", "Ruth", "s", "Same words."], ensure_ascii=False)
    import hashlib

    assert plan_mod.tts_hash(legacy, beat) == hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def test_edits_can_recast_voices_and_reassign_speakers():
    from engine import edits

    plan, _ = plan_mod.validate_plan(_plan_with({"maya": "Ruth", "sam": "Matthew"}, ["maya", "sam"]))
    plan["tts"] = {"provider": "polly"}
    ids = [b["id"] for b in plan["beats"]]
    new, touched = edits.apply_ops(plan, [{"op": "set_speaker", "id": ids[0], "speaker": "sam"}])
    assert new["beats"][0]["speaker"] == "sam" and touched == [ids[0]]
    new, _ = edits.apply_ops(plan, [{"op": "set_voice", "speaker": "sam", "voice": "stephen"}])
    assert new["voices"]["sam"] == "Stephen"
    for bad in ({"op": "set_speaker", "id": ids[0], "speaker": "nobody"}, {"op": "set_voice", "speaker": "sam", "voice": "Ruth"},
                {"op": "set_voice", "speaker": "sam", "voice": "NotAVoice"}, {"op": "set_voice", "speaker": "ghost", "voice": "Amy"}):
        with pytest.raises(edits.EditError):
            edits.apply_ops(plan, [bad])


def test_narrator_gives_way_when_characters_run_out_of_voices_of_their_gender():
    from engine import voices

    # three women in Spanish (only 3 women's voices exist) and a narrator who also asked for a woman's voice
    c = voices.clean_cast({"narrator": "Lupe", "ana": "Mia", "lucia": "Lucia", "marta": "Lupe"}, "es")
    assert (c["ana"], c["lucia"], c["marta"]) == ("Mia", "Lucia", "Lupe")  # every character is a woman, as asked
    assert voices.CATALOG[c["narrator"]][2] == "male" and list(c) == ["narrator", "ana", "lucia", "marta"]
    assert "3 women's voices and 4 men's voices" in plan_mod.system_prompt("es") and "skip the narrator" in plan_mod.system_prompt("en")


def test_research_uses_short_queries_written_by_a_small_model_and_never_cites_unrelated_pages():
    from engine import research

    searched = []
    pages = {"Volcán": "Un volcán es una estructura geológica por la que emerge el magma. " * 6,
             "Magma": "El magma es roca fundida bajo la superficie de la Tierra. " * 6}

    def fake(url, **kw):
        if "list=search" in url:
            q = urllib.parse.unquote_plus(url.split("srsearch=")[1].split("&")[0])
            searched.append(q)
            return {"query": {"search": [{"title": {"volcán": "Volcán", "magma": "Magma"}.get(q.lower(), "Buscando a Nemo")}]}}
        title = urllib.parse.unquote_plus(url.split("titles=")[1].split("&")[0])
        return {"query": {"pages": [{"title": title, "fullurl": f"https://es.wikipedia.org/wiki/{title}", "extract": pages.get(title, "x" * 400)}]}}

    ask = lambda system, user: "1. Volcán\n- magma\n\n" + "z" * 200   # numbered, bulleted and an overlong line: all cleaned up
    notes, sources = research.gather_notes("Explica cómo se forman los volcanes, para niños curiosos.", fetch=fake, language="es", ask=ask)
    assert searched == ["Volcán", "magma"]  # never the whole sentence
    assert [s["title"] for s in sources] == ["Volcán", "Magma"]
    # a failing model falls back to the brief itself and never fails the video
    searched.clear()
    research.gather_notes("volcanes", fetch=fake, language="es", ask=lambda s, u: (_ for _ in ()).throw(RuntimeError("down")))
    assert searched == ["volcanes"]


def test_plan_keeps_the_sources_the_director_says_it_used():
    plan, _ = plan_mod.validate_plan({**_plan_with(None, [None]), "sources_used": ["Volcán", "  Magma ", 7, None]})
    assert plan["sources_used"] == ["Volcán", "Magma"]
    assert "sources_used" not in plan_mod.validate_plan(_plan_with(None, [None]))[0]  # absent stays absent: cite everything researched
    assert plan_mod.validate_plan({**_plan_with(None, [None]), "sources_used": []})[0]["sources_used"] == []  # used nothing: cite nothing



def test_description_labels_follow_the_videos_language_but_unsplash_attribution_keeps_its_wording():
    from engine import assets
    from engine.handlers import finalize_handler

    ledger = [{"attribution": "Photo by Ana (https://unsplash.com/@ana?utm_source=videomk&utm_medium=referral) on Unsplash", "landing_url": "https://unsplash.com/photos/x"}]
    sources = [{"title": "Volcán", "publisher": "Wikipedia (es)", "url": "https://es.wikipedia.org/wiki/Volc%C3%A1n"}]
    es, en = assets.credits_block(ledger, sources, "es"), assets.credits_block(ledger, sources)
    assert es.startswith("Créditos de las imágenes:") and "Fuentes:" in es and "Photo by Ana" in es  # attribution wording is Unsplash's
    assert en.startswith("Image credits:") and "Sources:" in en
    chapters = [{"start": 5.0, "title": "Uno"}, {"start": 30.0, "title": "Dos"}, {"start": 60.0, "title": "Tres"}]
    assert finalize_handler._chapters_text(chapters, "es").splitlines()[0] == "0:00 Introducción"
    assert finalize_handler._chapters_text(chapters).splitlines()[0] == "0:00 Intro"
