import json
import os

import numpy as np
import pytest
from PIL import Image

from engine import audio, edits, music, pipeline, plan as plan_mod
from engine.renderer import Renderer
from engine.timeline import build_timeline
from tests.test_engine import small_timeline
from tests.test_hardening import launcher  # noqa: F401  (the fixture)


# ================================================================= image density
def beat(i, stype="title", **props):
    base = {"title": {"title": "T", "subtitle": ""}, "image": {"image_query": f"q{i}", "alt": "a", "ken_burns": "in"},
            "gallery": {"image_queries": [f"g{i}a", f"g{i}b", f"g{i}c"], "alt": "a"}}[stype]
    return {"id": f"{i:08x}", "narration": "A line of narration that is long enough to count.", "scene": {"type": stype, "props": {**base, **props}}}


def test_the_budget_is_a_ceiling_per_minute_with_zero_allowed():
    assert [plan_mod.image_budget(m, 10) for m in (1, 1.5, 3, 12)] == [10, 15, 30, 120]
    assert plan_mod.image_budget(1, 0) == 0 and plan_mod.image_budget(2, 2.5) == 5 and plan_mod.image_budget(1, 0.4) == 0


def test_galleries_count_each_photo_and_the_users_own_photos_never_count():
    assert plan_mod.count_images(beat(1, "image")) == 1 and plan_mod.count_images(beat(2, "gallery")) == 3 and plan_mod.count_images(beat(3)) == 0
    assert plan_mod.count_images(beat(4, "image", photo="P1")) == 0


def test_beyond_the_budget_galleries_shrink_then_images_become_plain_cards():
    beats = [beat(1, "gallery"), beat(2, "image"), beat(3, "gallery"), beat(4, "image"), beat(5, "image", photo="P1")]
    warns = plan_mod.enforce_image_budget(beats, 5)       # 3 + 1 used, 1 left: the second gallery is reduced to its first photograph, the next image is out of budget
    assert [b["scene"]["type"] for b in beats] == ["gallery", "image", "image", "title", "image"]
    assert beats[2]["scene"]["props"]["image_query"] == "g3a"
    assert len(warns) == 2 and any("reduced to one photograph" in w for w in warns) and any("budget of 5" in w for w in warns)
    beats = [beat(1, "gallery"), beat(2, "gallery")]
    plan_mod.enforce_image_budget(beats, 5)               # 3 used, 2 left: the second gallery keeps its first two photographs
    assert beats[1]["scene"]["type"] == "gallery" and beats[1]["scene"]["props"]["image_queries"] == ["g2a", "g2b"]
    beats = [beat(1, "gallery"), beat(2, "gallery")]
    plan_mod.enforce_image_budget(beats, 4)               # 3 + 1 left: reduced to a single photograph
    assert beats[1]["scene"]["type"] == "image"
    beats = [beat(1, "image"), beat(2, "gallery")]
    plan_mod.enforce_image_budget(beats, 0)
    assert [b["scene"]["type"] for b in beats] == ["title", "title"]


def test_an_exact_fit_is_untouched_and_the_first_photographs_win():
    beats = [beat(1, "gallery"), beat(2, "image")]
    assert plan_mod.enforce_image_budget(beats, 4) == [] and beats[0]["scene"]["type"] == "gallery"
    beats = [beat(1, "image"), beat(2, "image"), beat(3, "image")]
    plan_mod.enforce_image_budget(beats, 2)
    assert [b["scene"]["type"] for b in beats] == ["image", "image", "title"]


def test_gallery_props_are_sanitised():
    ok = plan_mod.sanitize_props("gallery", {"image_queries": ["Rome forum", "rome FORUM", " Colosseum ", "", 5, "Pantheon", "Trevi", "Spanish steps"], "alt": ""})
    assert ok == {"image_queries": ["Rome forum", "Colosseum", "Pantheon", "Trevi", "Spanish steps"], "alt": "Rome forum"}   # up to six, duplicates and junk dropped
    for bad in ({"image_queries": ["one"]}, {"image_queries": "a,b"}, {"image_queries": ["a", "A"]}, {}):
        with pytest.raises(ValueError):
            plan_mod.sanitize_props("gallery", bad)


def test_the_prompt_states_the_ceiling_and_documents_galleries(monkeypatch):
    p = plan_mod.system_prompt("en", "US", 10)
    assert "at most 10 per minute" in p and "use most of it" in p and "VISUAL topics" in p and "- gallery:" in p and "- image:" in p and "use few or none" in p and "2-6 different photographs" in p
    assert "at most 2.5 per minute" in plan_mod.system_prompt("en", None, 2.5)
    none = plan_mod.system_prompt("en", None, 0)
    assert "Do NOT use image or gallery scenes" in none and "- gallery:" not in none and "- image:" not in none and "- chart:" in none


def llm_plan(beats):
    return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [{"narration": b["narration"], "scene": b["scene"]} for b in beats]})


def test_generate_plan_passes_the_rate_to_the_model_and_enforces_it_on_the_answer():
    seen = []
    greedy = [beat(i, "gallery") for i in range(1, 7)]                # 18 photographs asked for in a 1-minute video
    plan, warns = plan_mod.generate_plan("holiday in Rome", "", 1, lambda s, u: (seen.append(s), llm_plan(greedy))[1], max_images_per_minute=10)
    assert "at most 10 per minute" in seen[0]
    imgs = sum(plan_mod.count_images(b) for b in plan["beats"])
    assert imgs == 10 and any("image budget" in w for w in warns)
    plan, _ = plan_mod.generate_plan("holiday in Rome", "", 1, lambda s, u: llm_plan(greedy), max_images_per_minute=3)
    assert sum(plan_mod.count_images(b) for b in plan["beats"]) == 3
    plan, _ = plan_mod.generate_plan("holiday in Rome", "", 2, lambda s, u: llm_plan(greedy), max_images_per_minute=0)
    assert sum(plan_mod.count_images(b) for b in plan["beats"]) == 0
    plan, _ = plan_mod.generate_plan("holiday in Rome", "", 1, lambda s, u: llm_plan(greedy[:2]), max_images_per_minute=99)    # a silly rate is clamped to the maximum of 10
    assert sum(plan_mod.count_images(b) for b in plan["beats"]) == 6


def test_gallery_media_is_remade_only_when_its_queries_change():
    b = beat(1, "gallery")
    plan = {"beats": [b]}
    done = {"tts_hash": plan_mod.tts_hash(plan, b), "audio_key": "a", "duration": 5.0, "query": "g1a|g1b|g1c", "gallery": [{"asset": "k1"}, {"asset": "k2"}, {"asset": "k3"}]}
    assert plan_mod.needs_media(plan, {**b, "media": done}) is False
    assert plan_mod.needs_media(plan, {**b, "media": {**done, "query": "g1a|other|g1c"}}) is True
    assert plan_mod.needs_media(plan, {**b, "media": {k: v for k, v in done.items() if k != "gallery"}}) is True
    assert plan_mod.needs_media(plan, {**b, "media": {**{k: v for k, v in done.items() if k != "gallery"}, "no_photo": True}}) is False


def test_the_beat_step_fetches_each_gallery_photo_in_parallel_and_drops_the_ones_it_cannot_find(monkeypatch):
    from engine.handlers import beat_handler

    seen = []
    def fake_photo(plan, still, video_id, cost_field):
        seen.append(still["id"])
        q = still["scene"]["props"]["image_query"]
        if q == "g1b":
            return {"query": q, "pick": None, "no_photo": True}
        if q == "g1c":
            raise RuntimeError("provider exploded")
        return {"query": q, "pick": None, "asset": f"assets/{q}.jpg", "credit": f"Photo: {q}", "ledger": {"source": "unsplash"}, "chosen": f"unsplash:{q}"}
    monkeypatch.setattr(beat_handler, "make_photo", fake_photo)
    out = beat_handler.make_gallery({"beats": []}, beat(1, "gallery"), "vid", "cost_usd")
    assert out["query"] == "g1a|g1b|g1c" and [g["asset"] for g in out["gallery"]] == ["assets/g1a.jpg"] and sorted(seen) == ["00000001g0", "00000001g1", "00000001g2"]
    assert "no_photo" not in out
    monkeypatch.setattr(beat_handler, "make_photo", lambda *a, **k: {"no_photo": True})
    assert beat_handler.make_gallery({"beats": []}, beat(1, "gallery"), "vid", "cost_usd")["no_photo"] is True


def test_the_timeline_makes_a_gallery_a_single_image_or_a_card_when_photos_are_missing():
    b = beat(1, "gallery")
    plan = {"beats": [b], "theme": "midnight"}
    def sc(info):
        return build_timeline(plan, [{"duration": 6.0, **info}], video_id="v")["scenes"][0]
    full = sc({"gallery": [{"asset": "a.jpg", "credit": "Photo: A"}, {"asset": "b.jpg", "credit": ""}, {"asset": "c.jpg", "credit": "Photo: C"}]})
    assert full["type"] == "gallery" and {k: full["props"][k] for k in ("assets", "credits", "alt", "image_queries")} == {"assets": ["a.jpg", "b.jpg", "c.jpg"], "credits": ["Photo: A", "", "Photo: C"], "alt": "a", "image_queries": ["g1a", "g1b", "g1c"]}
    assert full["props"]["cuts"][0] == 0.0 and len(full["props"]["cuts"]) == 3
    one = sc({"gallery": [{"asset": "a.jpg", "credit": "Photo: A"}]})
    assert one["type"] == "image" and one["props"]["asset"] == "a.jpg" and one["props"]["credit"] == "Photo: A"
    assert sc({"gallery": []})["type"] == "title" and sc({})["type"] == "title"


def test_a_gallery_scene_shows_each_photo_in_turn_with_a_crossfade_and_never_crashes_on_a_missing_one():
    colors = {"a": (200, 30, 30), "b": (30, 200, 30), "c": (30, 30, 200)}
    loader = lambda key: Image.new("RGB", (2400, 1400), colors[key]) if key in colors else None
    tl = small_timeline(9.0, ["gallery"])
    tl["scenes"][0]["props"] = {"assets": ["a", "b", "c"], "credits": ["Photo: A / Unsplash", "", "Photo: C"], "alt": "three"}
    tl["scenes"][0]["words"] = []
    r = Renderer(tl, loader)
    centre = lambda t: r.frame_at(t).getpixel((960, 400))
    first, second, third = centre(1.0), centre(4.0), centre(7.5)
    assert first[0] > 150 and second[1] > 150 and third[2] > 150                 # red, then green, then blue, each for a third of the beat
    mid = centre(2.85)                                                           # inside the fade from the first to the second photograph
    assert 30 < mid[0] < 200 and 30 < mid[1] < 200
    tl2 = small_timeline(6.0, ["gallery"])
    tl2["scenes"][0]["props"] = {"assets": ["a", "missing", "c"], "credits": [], "alt": "x"}
    tl2["scenes"][0]["words"] = []
    r2 = Renderer(tl2, loader)
    assert all(r2.frame_at(t).size == (1920, 1080) for t in (0.2, 2.5, 3.2, 5.9, 20.0))
    tl3 = small_timeline(4.0, ["gallery"])
    tl3["scenes"][0]["props"] = {"assets": ["x", "y"], "alt": "nothing found"}
    assert Renderer(tl3, loader).frame_at(1.0).size == (1920, 1080)              # all missing: the placeholder card


def event(body):
    return {"pathParameters": {"user_id": "u1"}, "headers": {}, "body": json.dumps({"prompt": "Our week at the beach with the family", "target_minutes": 1, "client_request_id": "dens-" + str(abs(hash(json.dumps(body)))), **body}),
            "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}


def test_the_launcher_accepts_a_density_from_0_to_10_and_forwards_it(launcher):
    for ok in (0, 3, 7.5, 10):
        out = launcher.handler(event({"max_images_per_minute": ok}), None)
        assert out["statusCode"] == 202, ok
        assert json.loads(launcher.fake.calls[-1]["input"])["max_images_per_minute"] == float(ok)
    n = len(launcher.fake.calls)
    for bad in (-1, 10.5, 11, "5", True, [3]):
        assert launcher.handler(event({"max_images_per_minute": bad}), None)["statusCode"] == 400, bad
    assert len(launcher.fake.calls) == n
    assert launcher.handler(event({}), None)["statusCode"] == 202 and "max_images_per_minute" not in json.loads(launcher.fake.calls[-1]["input"])


# ================================================================= music (library recordings only: nothing is synthesised)
def _tone(seconds, f):
    t = np.arange(int(seconds * music.SR)) / music.SR
    x = (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


def test_music_choices_are_sanitised_to_well_formed_library_tracks_and_styles_are_gone():
    ok = plan_mod.sanitize_music({"track": "Soft-Piano-Memory", "style": "soft_piano", "energy": 9, "key": "e minor", "tempo": 90, "changes": [
        {"beat": 5, "track": "tense-pulse"}, {"beat": 1, "track": "lofi-evening"}, {"beat": 7, "style": "polka"}, {"beat": 20, "track": "lofi-evening"}, {"beat": 3, "track": "bad id!"}, {"beat": "x", "track": "a-b-c"}]}, 8)
    assert ok == {"track": "soft-piano-memory", "changes": [{"beat": 5, "track": "tense-pulse"}]}        # no style, energy, key or tempo; no change at beat 1, beyond the end or with a bad id
    assert plan_mod.sanitize_music({"style": "soft_piano", "energy": 3}, 8) is None and plan_mod.sanitize_music("loud", 8) is None and plan_mod.sanitize_music(None, 8) is None


def test_validate_plan_keeps_a_track_and_sfx_and_drops_nonsense():
    raw = {"legit": True, "title": "T", "music": {"track": "cinematic-rise"}, "beats": [
        {"narration": "A line of narration that is long enough to count.", "scene": {"type": "title", "props": {"title": "x"}}, "sfx": "RISER"},
        {"narration": "Another line of narration that is long enough.", "scene": {"type": "title", "props": {"title": "y"}}, "sfx": "airhorn"},
        {"narration": "A third line of narration that is long enough.", "scene": {"type": "title", "props": {"title": "z"}}, "sfx": "none"}]}
    plan, _ = plan_mod.validate_plan(raw)
    assert plan["music"] == {"track": "cinematic-rise"} and [b.get("sfx") for b in plan["beats"]] == [None, None, "none"]      # "riser" is a removed tonal effect: dropped like an unknown one
    raw["music"] = {"style": "kazoo"}
    assert "music" not in plan_mod.validate_plan(raw)[0]


def test_music_changes_become_times_and_need_room_on_both_sides():
    starts = [0, 10, 25, 40, 55, 70]
    spec = music.resolve({"track": "soft-piano-memory", "changes": [{"beat": 3, "track": "tense-pulse"}, {"beat": 5, "track": "dreamy-bells"}, {"beat": 6, "track": "lofi-evening"}]}, starts, 85.0)
    assert [(s["start"], s["track"]) for s in spec["segments"]] == [(0.0, "soft-piano-memory"), (25.0, "tense-pulse"), (55.0, "dreamy-bells")]   # a third change is dropped
    early = music.resolve({"track": "soft-piano-memory", "changes": [{"beat": 2, "track": "tense-pulse"}]}, starts, 85.0)
    assert len(early["segments"]) == 1                                     # a change 10 s in leaves no room for the first track
    assert music.resolve(None, starts, 85.0) is None and music.resolve({"style": "soft_piano"}, starts, 85.0) is None and music.resolve({"track": "bad id!"}, starts, 85.0) is None   # no track, no music


def test_a_track_change_crossfades_without_a_click():
    spec = {"segments": [{"start": 0.0, "track": "a-low"}, {"start": 20.0, "track": "b-high"}]}
    out = music.render(spec, 40.0, {"a-low": _tone(60, 220.0), "b-high": _tone(60, 330.0)}.get)
    assert out.shape == (40 * music.SR, 2) and float(np.abs(out).max()) <= 1.0 and not np.isnan(out).any()
    b = 20 * music.SR
    jump = float(np.max(np.abs(np.diff(out[b - 200: b + 200, 0]))))
    typical = float(np.max(np.abs(np.diff(out[5 * music.SR: 6 * music.SR, 0]))))
    assert jump < typical * 2.5                                            # no discontinuity at the boundary
    rms = lambda a, b_: float(np.sqrt((out[int(a * music.SR): int(b_ * music.SR)] ** 2).mean()))
    assert rms(19, 21) > 0.5 * min(rms(5, 15), rms(25, 35))                # no hole in the middle of the fade


def test_the_synthesiser_is_gone_for_good():
    assert not any(hasattr(music, n) for n in ("render_segment", "STYLES", "MOOD_STYLE", "inst_piano", "drum_kick", "style_catalog"))
    assert not hasattr(audio, "generate_music")


# ================================================================= sound effects
def test_the_director_chooses_effects_and_the_default_transition_whoosh_steps_aside():
    tl = {"scenes": [{"type": "title", "start": 0.0, "sfx": "swipe"}, {"type": "title", "start": 10.0, "sfx": "chime"}, {"type": "title", "start": 20.0, "sfx": "none"},
                     {"type": "title", "start": 30.0}, {"type": "title", "start": 40.0, "sfx": "impact"}, {"type": "bullets", "start": 50.0, "cues": [1.0, 2.0]}]}
    ev = pipeline.sfx_events(tl)
    assert (0.12, "swipe", 0.34) in ev and (40.0, "impact", 0.34) in ev
    assert not any(k in ("chime", "ding", "sparkle", "pop", "riser", "tick") for _, k, _ in ev)       # no bells or musical sounds, even when an old plan still names one
    assert (29.88, "whoosh", 0.28) in ev                                    # an unremarkable beat keeps the transition whoosh
    assert not any(abs(t - 19.88) < 1e-6 for t, _, _ in ev) and not any(k == "whoosh" and abs(t - 9.88) < 1e-6 for t, k, _ in ev)   # "none" is silent, and a chosen effect replaces the whoosh
    assert not any(abs(t - 9.88) < 1e-6 or abs(t - 10.12) < 1e-6 for t, _, _ in ev)                      # an old plan's removed effect is silence, not a whoosh and not a bell


def test_every_effect_is_short_audible_and_quiet_enough_to_mix():
    for kind in audio.SFX_KINDS:
        s = audio._BANK_BUILDERS[kind](audio.MIX_SR)
        assert 0.03 < s.size / audio.MIX_SR < 1.6 and not np.isnan(s).any() and 0.1 < float(np.abs(s).max()) <= 1.0, kind
    assert set(audio.PLANNER_SFX) <= set(audio.SFX_KINDS) and set(audio.SFX_KINDS) == {"whoosh", "click", "impact", "shutter", "typing", "swipe"}
    for gone in ("ding", "chime", "sparkle", "pop", "riser", "tick"):
        assert gone not in audio.SFX_KINDS and gone not in audio.PLANNER_SFX and not audio.build_sfx_track([(1.0, gone, 0.3)], 4.0).any()
    track = audio.build_sfx_track([(1.0, "click", 0.3), (2.0, "nonsense", 0.3), (99.0, "ding", 0.3)], 4.0)
    assert track.shape == (4 * audio.MIX_SR, 2) and float(np.abs(track[int(1.0 * audio.MIX_SR): int(2.0 * audio.MIX_SR)]).max()) > 0.05 and float(np.abs(track[int(2.5 * audio.MIX_SR):]).max()) == 0.0


def test_the_whole_audio_mix_uses_the_chosen_music_and_effects(tmp_path):
    tl = small_timeline(12.0, ["title", "bullets"])
    tl["music"] = music.resolve({"track": "dreamy-bells"}, [0, 6], 12.0)
    tl["scenes"][1]["sfx"] = "impact"
    out = tmp_path / "mix.m4a"
    pipeline.make_audio(tl, [np.zeros(24000, np.float32)] * 2, str(out), track_loader={"dreamy-bells": _tone(30, 261.6)}.get)
    assert out.exists() and out.stat().st_size > 20_000
    from engine import media
    assert media.ffprobe_duration(str(out)) == pytest.approx(12.0, abs=0.3)
    quiet = tmp_path / "nomusic.m4a"                                          # no track chosen (or none loadable): narration and effects only, still a valid file
    tl["music"] = None
    pipeline.make_audio(tl, [np.zeros(24000, np.float32)] * 2, str(quiet))
    assert quiet.exists() and media.ffprobe_duration(str(quiet)) == pytest.approx(12.0, abs=0.3)
    tl["music"] = music.resolve({"track": "dreamy-bells"}, [0, 6], 12.0)
    none_loaded = tmp_path / "missing.m4a"
    pipeline.make_audio(tl, [np.zeros(24000, np.float32)] * 2, str(none_loaded), track_loader=lambda tid: None)
    assert none_loaded.exists()


# ================================================================= editing
def test_a_person_can_change_the_music_and_an_effect_and_cannot_choose_nonsense():
    plan = {"title": "T", "mood": "calm", "beats": [{"id": "aaaaaaa1", "narration": "x " * 10, "scene": {"type": "title", "props": {"title": "t"}}}, {"id": "aaaaaaa2", "narration": "y " * 10, "scene": {"type": "title", "props": {"title": "u"}}}]}
    new, touched = edits.apply_ops(plan, [{"op": "set_music", "music": {"track": "lofi-evening"}}, {"op": "set_sfx", "id": "aaaaaaa2", "sfx": "typing"}])
    assert new["music"] == {"track": "lofi-evening"} and new["beats"][1]["sfx"] == "typing" and touched == []
    new2, _ = edits.apply_ops(new, [{"op": "set_music", "music": None}, {"op": "set_sfx", "id": "aaaaaaa2", "sfx": ""}])
    assert "music" not in new2 and "sfx" not in new2["beats"][1]
    for bad in ({"op": "set_music", "music": {"style": "polka"}}, {"op": "set_music", "music": {"track": "x"}}, {"op": "set_sfx", "id": "aaaaaaa1", "sfx": "airhorn"}, {"op": "set_sfx", "id": "zzzzzzzz", "sfx": "ding"}):
        with pytest.raises(edits.EditError):
            edits.apply_ops(plan, [bad])
    g, _ = edits.apply_ops(plan, [{"op": "set_scene", "id": "aaaaaaa1", "type": "gallery", "props": {"image_queries": ["a b", "c d"]}}])
    assert g["beats"][0]["scene"]["type"] == "gallery"


def test_a_short_video_gets_a_real_photo_budget_and_a_fallback_card_is_a_complete_thought():
    assert [plan_mod.image_budget(m, 10) for m in (0.25, 0.5, 0.75, 1)] == [10, 10, 10, 10]     # 15 s: up to 10 photos, not 2
    assert plan_mod.image_budget(0.25, 3) == 3 and plan_mod.image_budget(0.25, 0) == 0 and plan_mod.image_budget(0.5, 0.4) == 0   # never above a minute's allowance; "no photos" stays none
    c = plan_mod.card_text
    assert c("Wander Montmartre and Le Marais. Paris is best when you leave room to wander.") == "Wander Montmartre and Le Marais"
    assert c("One city, endless postcards. The Eiffel Tower.") == "One city, endless postcards"
    assert c("When the river froze in that long winter, the whole town walked across it to the market") == "When the river froze in that long winter"
    long = c("The quick brown fox jumps over the lazy dog again and again and again without ever stopping")
    assert long.endswith("…") and len(long.split()) <= 10
    assert c("") == "" and c("¿Por qué el cielo es azul? Porque la luz se dispersa.") == "¿Por qué el cielo es azul?"
