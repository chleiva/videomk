import numpy as np
import pytest

from engine import library, music, plan as plan_mod

SR = library.SR


def tone(seconds, hz=220.0, amp=0.5):
    t = np.arange(int(seconds * SR)) / SR
    x = (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


CATALOG = {"version": 1, "tracks": [
    {"id": "calm-pad-dawn", "title": "Calm pad", "description": "Slow  weightless pads.\nNo drums.", "mood": ["calm"], "energy": 1, "bpm": 62, "key": "A minor", "seconds": 120.4},
    {"id": "Bad ID", "description": "x"}, {"id": "no-description", "description": "  "}, {"id": "ok-track-2", "description": "Upbeat plucks", "energy": 9, "bpm": "fast"}, "junk"]}


def test_only_well_formed_tracks_reach_the_planner_and_text_is_tidied():
    tracks = library.clean_catalog(CATALOG)
    assert [t["id"] for t in tracks] == ["calm-pad-dawn", "ok-track-2"]
    assert tracks[0]["description"] == "Slow weightless pads. No drums." and tracks[1]["energy"] == 5 and tracks[1]["bpm"] is None
    assert library.clean_catalog(None) == [] and library.clean_catalog({"tracks": "x"}) == []


def test_the_catalogue_is_cached_and_a_missing_one_means_no_library():
    calls = []
    clock = {"t": 1000.0}
    def get(key):
        calls.append(key)
        return CATALOG
    library._cache.update(at=0.0, tracks=[])
    assert len(library.load_catalog(get, now=lambda: clock["t"])) == 2 and library.load_catalog(get, now=lambda: clock["t"] + 10) and calls == [library.CATALOG_KEY]
    clock["t"] += library.CATALOG_TTL_S + 1
    library.load_catalog(get, now=lambda: clock["t"])
    assert len(calls) == 2
    library._cache.update(at=0.0, tracks=[])
    assert library.load_catalog(lambda k: (_ for _ in ()).throw(KeyError("NoSuchKey"))) == []


def test_track_keys_are_safe():
    assert library.track_key("calm-pad-dawn") == "music/calm-pad-dawn.mp3"
    for bad in ("../x", "A", "a/b", "", "UPPER-case", "x" * 50):
        with pytest.raises(ValueError):
            library.track_key(bad)


def test_a_track_is_levelled_to_the_synth_loudness_and_cut_or_looped_to_the_scene_without_a_click():
    quiet, loud = library.level(tone(5, amp=0.02)), library.level(tone(5, amp=0.9))
    rms = lambda a: float(np.sqrt(np.mean(a ** 2)))
    assert rms(quiet) == pytest.approx(library.TARGET_RMS, rel=0.05) and rms(loud) == pytest.approx(library.TARGET_RMS, rel=0.05) and float(np.abs(loud).max()) <= 0.951
    long_cut = library.fit(tone(20), 8.0)
    assert long_cut.shape == (8 * SR, 2)
    looped = library.fit(tone(10, 220.0), 35.0)
    assert looped.shape == (35 * SR, 2)
    join = 10 * SR - int(library.LOOP_XFADE_S * SR)                                  # where the first loop's tail meets the head again
    seg = looped[join - 400: join + int(library.LOOP_XFADE_S * SR) + 400, 0]
    assert float(np.max(np.abs(np.diff(seg)))) < 0.12                               # a continuous tone through the crossfade: no jump
    assert library.fit(tone(1.0), 5.0).shape == (5 * SR, 2)                          # even a very short track fills the scene


def test_decode_reads_real_audio_files(tmp_path):
    from engine import audio
    path = tmp_path / "t.wav"
    audio.write_wav(str(path), tone(2.0)[:, 0], SR)
    out = library.decode(str(path))
    assert out.shape[1] == 2 and abs(out.shape[0] - 2 * SR) < 2000
    (tmp_path / "bad.mp3").write_bytes(b"not audio")
    with pytest.raises(RuntimeError):
        library.decode(str(tmp_path / "bad.mp3"))


def test_the_prompt_offers_the_library_when_there_is_one_and_the_synth_when_not():
    tracks = library.clean_catalog(CATALOG)
    p = plan_mod.system_prompt("en", None, 10, True, tracks)
    assert "curated library" in p and "calm-pad-dawn (120 s, energy 1, 62 bpm): Slow weightless pads. No drums." in p and '"track"' in p and "ambient_pad" not in p
    assert "sfx" in p.lower() and "silent beat" in p
    synth = plan_mod.system_prompt("en")
    assert "ambient_pad" in synth and "curated library" not in synth


def test_the_planner_can_name_tracks_and_changes_and_nonsense_ids_are_ignored():
    m = plan_mod.sanitize_music({"track": "Calm-Pad-Dawn", "changes": [{"beat": 4, "track": "ok-track-2"}, {"beat": 5, "track": "../etc"}, {"beat": 6, "style": "polka"}]}, 8)
    assert m["track"] == "calm-pad-dawn" and m["changes"] == [{"beat": 4, "energy": 3, "track": "ok-track-2"}]
    assert plan_mod.sanitize_music({"track": "bad id!"}, 8) is None and plan_mod.sanitize_music({"track": "x"}, 8) is None


def test_resolve_and_render_play_the_recording_change_with_a_crossfade_and_fall_back_to_the_synth():
    starts = [0, 10, 25, 40, 55]
    spec = music.resolve({"track": "calm-pad-dawn", "changes": [{"beat": 3, "track": "ok-track-2"}]}, "calm", starts, 70.0, "vid")
    assert [(s["start"], s.get("track")) for s in spec["segments"]] == [(0.0, "calm-pad-dawn"), (25.0, "ok-track-2")]
    marks = {"calm-pad-dawn": tone(60, 220.0), "ok-track-2": tone(60, 880.0)}
    out = music.render(spec, 40.0, marks.get)
    assert out.shape == (40 * SR, 2)
    freq = lambda a, b: float(np.argmax(np.abs(np.fft.rfft(out[int(a * SR): int(b * SR), 0]))) * SR / (int(b * SR) - int(a * SR)))
    assert freq(5, 15) == pytest.approx(220, abs=3) and freq(33, 39) == pytest.approx(880, abs=3)            # each segment plays its own recording
    jump = float(np.max(np.abs(np.diff(out[25 * SR - 300: 25 * SR + 300, 0]))))
    assert jump < 0.12
    fallback = music.render(spec, 40.0, lambda tid: None)                                                     # tracks unavailable: the synth stands in, still a full track
    assert fallback.shape == (40 * SR, 2) and float(np.abs(fallback).max()) > 0.3
    assert music.render(spec, 40.0).shape == (40 * SR, 2)                                                     # and with no loader at all
    boom = music.render(spec, 40.0, lambda tid: (_ for _ in ()).throw(RuntimeError("s3 down")))
    assert boom.shape == (40 * SR, 2)
