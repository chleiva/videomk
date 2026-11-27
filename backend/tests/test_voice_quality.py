"""Speech quality (docs/VOICE_QUALITY_IT_ES_2026-11-27.md): the full band of the generative voices reaches the video, and old plans keep their audio."""
import io
import math
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import length, media, plan as plan_mod, tts, voice_data, voices  # noqa: E402


def _mp3(freqs, seconds=1.0, sr=24000) -> bytes:
    """A real MP3 at `sr` holding the given tones (made with the ffmpeg the engine ships)."""
    expr = "+".join(f"0.2*sin(2*PI*{f}*t)" for f in freqs)
    out = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"aevalsrc={expr}:s={sr}:d={seconds}", "-ac", "1",
                          "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1"], capture_output=True)
    if out.returncode != 0 or not out.stdout:
        pytest.skip("this ffmpeg cannot encode MP3 (the engine only needs to decode it)")
    return out.stdout


def _share_above(a: np.ndarray, hz: float, sr: int = tts.SR) -> float:
    spec = np.abs(np.fft.rfft(a)) ** 2
    return float(spec[np.fft.rfftfreq(a.size, 1 / sr) > hz].sum() / spec.sum())


class _Polly:
    def __init__(self, mp3: bytes = b"", fail_mp3: bool = False):
        self.calls, self.mp3, self.fail_mp3 = [], mp3, fail_mp3

    def synthesize_speech(self, **kw):
        self.calls.append(kw)
        if kw["OutputFormat"] == "mp3":
            return {"AudioStream": io.BytesIO(b"not an mp3" if self.fail_mp3 else self.mp3)}
        pcm = (np.sin(2 * math.pi * 440 * np.arange(16000) / 16000) * 12000).astype("<i2").tobytes()
        return {"AudioStream": io.BytesIO(pcm)}


def test_new_plans_ask_polly_for_its_full_band_and_what_is_above_8_khz_survives():
    """Polly's raw PCM stops at 16 kHz, so nothing above 8 kHz ever reached a video. A plan that records rate 24000 gets the engine's own 24 kHz (as MP3)."""
    fake = _Polly(_mp3([440, 10000]))
    p = tts.get_provider("polly", "", {"engine": "generative", "region": "us-east-1", "rate": 24000})
    p._client = fake
    a = p.synth("Hola.", voice="Lupe")
    sent = fake.calls[0]
    assert (sent["Engine"], sent["OutputFormat"], sent["SampleRate"], sent["VoiceId"], sent["TextType"]) == ("generative", "mp3", "24000", "Lupe", "text")
    assert len(fake.calls) == 1 and a.dtype == np.float32 and abs(a.size - tts.SR) < tts.SR * 0.1     # one second, at the narration's own rate: no resampling
    assert _share_above(a, 8000) > 0.2                                                               # the 10 kHz tone is there


def test_plans_made_before_the_rate_was_recorded_keep_their_sound_and_their_cache_keys():
    old_cfg = {"provider": "polly", "voice": "", "style": "s", "engine": "generative", "region": "us-east-1"}
    fake = _Polly()
    p = tts.get_provider("polly", "", old_cfg)
    p._client = fake
    a = p.synth("Hola.", voice="Lucia")
    assert (fake.calls[0]["OutputFormat"], fake.calls[0]["SampleRate"]) == ("pcm", "16000") and abs(a.size - tts.SR) <= 2
    assert _share_above(a, 8000) < 1e-3
    beat = {"narration": "Las mismas palabras."}
    import hashlib
    import json

    legacy = hashlib.sha1(json.dumps(["polly", "", "s", "Las mismas palabras.", "generative", "us-east-1"], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    assert plan_mod.tts_hash({"tts": old_cfg}, beat) == legacy                                     # byte for byte the key the stored audio was saved under
    assert plan_mod.tts_hash({"tts": old_cfg}, beat) != plan_mod.tts_hash({"tts": {**old_cfg, "rate": 24000}}, beat)   # full band is another sound: never served from the old cache
    assert tts.get_provider("polly", "", {"engine": "generative", "rate": 22050}).rate == 16000    # only the two rates that were measured


def test_a_decoder_failure_costs_the_band_not_the_video(capsys):
    fake = _Polly(fail_mp3=True)
    p = tts.get_provider("polly", "", {"engine": "generative", "region": "us-east-1", "rate": 24000})
    p._client = fake
    a = p.synth("Ciao.", voice="Beatrice")
    assert [c["OutputFormat"] for c in fake.calls] == ["mp3", "pcm"] and abs(a.size - tts.SR) <= 2
    assert "polly_fullband_fallback" in capsys.readouterr().out      # and it says so: a quiet fallback is how a quality loss goes unnoticed


def test_the_plan_records_the_full_band_rate():
    import inspect

    from engine.handlers import plan_handler

    src = inspect.getsource(plan_handler)
    assert '"rate": int(os.environ.get("POLLY_SAMPLE_RATE", "24000"))' in src


def test_no_default_voice_is_a_steady_one_where_its_accent_has_a_lively_one():
    """Polly's generative voices are two families (voices.STEADY): the steady 18 read like the neural engine. Italian and Latin American Spanish have lively
    voices, so their defaults are lively; Spain has none, so Lucia stays until another provider or voice exists."""
    ids = {v["id"] for v in voice_data.VOICES}
    assert voices.STEADY <= ids and len(voices.STEADY) == 18
    assert voices.STEADY == set(voice_data.PARTIAL_REGIONS["eu-west-2"])        # the same split Polly makes by region: a new voice there is a lively one
    assert voices.default_voice("it") == "Beatrice" and voices.default_voice("it", "IT") not in voices.STEADY
    for region in ("MX", "AR", "CO", "CL", "PE", "US"):
        assert voices.default_voice("es", region) == "Lupe"
    assert voices.default_voice("de") == "Vicki" and "Vicki" not in voices.STEADY and voices.default_voice("en") not in voices.STEADY
    assert voices.default_voice("es", "ES") == "Lucia" and {v["id"] for v in voice_data.VOICES if v["locale"] == "es-ES"} <= voices.STEADY   # nothing better in Polly
    assert voices.resolve({"accent": "mexicana"}, "es", "ES")[0] in ("Mia", "Andres")            # a Mexican accent asked by name is still Mexican
    assert length.rate_for("it", "Beatrice") == length.RATES["Beatrice"] and length.rate_for("it", "Bianca") == length.RATES["Bianca"]
