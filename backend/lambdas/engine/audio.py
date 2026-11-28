"""Audio synthesis: narration track assembly, procedural music and SFX.

Music and SFX are generated with numpy, so they carry no licence, no Content ID risk and cost nothing
to store. (A curated CC0 pack can replace them per theme later; the interface is the same.)
"""
import wave
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SR = 24000          # narration sample rate (TTS native)
MIX_SR = 44100


def read_wav(path: str) -> Tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("only 16-bit PCM wav supported")
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def write_wav(path: str, samples: np.ndarray, sr: int, channels: int = 1) -> None:
    a = np.clip(samples, -1.0, 1.0)
    pcm = (a * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def trim_silence(a: np.ndarray, sr: int, thresh: float = 0.012, keep: float = 0.06) -> np.ndarray:
    """Cut leading/trailing silence from TTS output so scene timing hugs the actual speech."""
    if a.size == 0:
        return a
    win = max(1, int(sr * 0.01))
    env = np.convolve(np.abs(a), np.ones(win) / win, mode="same")
    idx = np.where(env > thresh)[0]
    if idx.size == 0:
        return a
    k = int(keep * sr)
    return a[max(0, idx[0] - k): min(a.size, idx[-1] + k)]


# The level every beat of narration is brought to before the mix: Ruth's own (measured on QA stems, 2026-11-27), the voice the music bed and its ducking were
# tuned with. Polly's voices do not come at one level: Sergio -23.6 dB, Beatrice -22.9 (and -23.7 to -21.3 from one beat to the next), Ruth -21.7, Kiara
# -20.4, Tina -16.3. The music is ducked by how loud the voice is (media.mix_audio), so under a quieter voice it was both ducked less and nearer to it: 9.9 dB
# under Beatrice where it was 11.5 to 14.1 dB under the earlier voices.
SPEECH_LEVEL_DB = -21.7
MAX_LEVEL_GAIN_DB = 6.0


def speech_level_db(a: np.ndarray, sr: int) -> Optional[float]:
    """The level of the speech itself in dB (mean power of the 20 ms frames that carry speech: within 40 dB of the loudest, then within 10 dB of their mean,
    the gating loudness meters use). None for silence. Pauses do not count, so a slow reading and a fast one of the same voice measure alike."""
    h = max(1, int(0.02 * sr))
    n = a.size // h
    if n < 5:
        return None
    e = np.mean(a[: n * h].astype(np.float64).reshape(n, h) ** 2, axis=1)
    top = float(e.max())
    if top <= 1e-9:
        return None
    loud = e[e > top * 1e-4]
    act = loud[loud > float(loud.mean()) * 0.1]
    return float(10.0 * np.log10(float(act.mean()))) if act.size else None


def level_speech(a: np.ndarray, sr: int, target_db: float = SPEECH_LEVEL_DB) -> np.ndarray:
    """One beat of narration at the common speech level (at most MAX_LEVEL_GAIN_DB either way, and never past a peak of 0.97)."""
    lvl = speech_level_db(a, sr)
    if lvl is None:
        return a
    gain = 10.0 ** (max(-MAX_LEVEL_GAIN_DB, min(MAX_LEVEL_GAIN_DB, target_db - lvl)) / 20.0)
    peak = float(np.max(np.abs(a))) or 1.0
    gain = min(gain, 0.97 / peak) if gain > 1.0 else gain
    return (a * gain).astype(np.float32)


def build_narration(beats: Sequence[Dict], total_duration: float, sr: int = SR) -> np.ndarray:
    """beats: [{'offset': seconds, 'samples': float32 mono at `sr`}] placed on one silent track."""
    out = np.zeros(int(total_duration * sr) + sr, dtype=np.float32)
    for b in beats:
        s = b["samples"]
        o = int(b["offset"] * sr)
        if o >= out.size:
            continue
        end = min(out.size, o + s.size)
        out[o:end] += s[: end - o]
    return out[: int(total_duration * sr)]


# ----------------------------------------------------------------------------- music
_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _box(x: np.ndarray, w: int) -> np.ndarray:
    return np.convolve(x, np.ones(w) / w, mode="same")


def sfx_whoosh(sr: int = MIX_SR, dur: float = 0.55, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    noise = rng.standard_normal(n).astype(np.float32)
    band = _box(noise, 6) - _box(noise, 90)
    tt = np.linspace(0, 1, n, dtype=np.float32)
    env = np.clip(np.sin(np.pi * tt), 0.0, None) ** 2.2
    sweep = 0.6 + 0.4 * np.sin(np.pi * tt * 0.9)
    out = band * env * sweep
    return (out / (np.max(np.abs(out)) or 1.0) * 0.5).astype(np.float32)


def sfx_pop(sr: int = MIX_SR, dur: float = 0.18, f0: float = 720.0) -> np.ndarray:
    n = int(dur * sr)
    tt = np.arange(n, dtype=np.float32) / sr
    f = f0 * np.exp(-tt * 9.0)
    phase = 2 * np.pi * np.cumsum(f) / sr
    out = np.sin(phase) * np.exp(-tt * 26.0)
    return (out * 0.45).astype(np.float32)


def sfx_tick(sr: int = MIX_SR) -> np.ndarray:
    n = int(0.05 * sr)
    tt = np.arange(n, dtype=np.float32) / sr
    return (np.sin(2 * np.pi * 1800 * tt) * np.exp(-tt * 120.0) * 0.3).astype(np.float32)


def _tt(n: int, sr: int) -> np.ndarray:
    return np.arange(n, dtype=np.float32) / sr


def sfx_ding(sr: int = MIX_SR) -> np.ndarray:
    t = _tt(int(0.9 * sr), sr)
    out = np.sin(2 * np.pi * 1318.5 * t) * np.exp(-t * 6.5) + 0.4 * np.sin(2 * np.pi * 2637 * t) * np.exp(-t * 11) + 0.15 * np.sin(2 * np.pi * 3951 * t) * np.exp(-t * 18)
    return (out * np.minimum(1.0, t / 0.002) * 0.4).astype(np.float32)


def sfx_click(sr: int = MIX_SR) -> np.ndarray:
    rng = np.random.default_rng(3)
    t = _tt(int(0.05 * sr), sr)
    noise = _box(rng.standard_normal(t.size).astype(np.float32), 3)
    return ((noise * 0.6 + np.sin(2 * np.pi * 2300 * t) * 0.5) * np.exp(-t * 110) * 0.45).astype(np.float32)


def sfx_riser(sr: int = MIX_SR, dur: float = 1.3) -> np.ndarray:
    rng = np.random.default_rng(4)
    n = int(dur * sr)
    t = _tt(n, sr)
    noise = _box(rng.standard_normal(n).astype(np.float32), 5) - _box(rng.standard_normal(n).astype(np.float32), 70) * 0.3
    sweep = np.sin(2 * np.pi * np.cumsum(260 + 1500 * (t / dur) ** 2) / sr)
    env = (t / dur) ** 2.2 * np.minimum(1.0, (dur - t) / 0.03)
    return ((noise * 0.5 + sweep * 0.35) * env * 0.7).astype(np.float32)


def sfx_impact(sr: int = MIX_SR) -> np.ndarray:
    rng = np.random.default_rng(5)
    n = int(1.0 * sr)
    t = _tt(n, sr)
    thud = np.sin(2 * np.pi * np.cumsum(38 + 110 * np.exp(-t * 14)) / sr) * np.exp(-t * 4.5)
    body = np.sin(2 * np.pi * 120 * t) * np.exp(-t * 9) * 0.5
    burst = _box(rng.standard_normal(n).astype(np.float32), 9) * np.exp(-t * 18) * 0.5
    return ((thud + body + burst) * 0.42).astype(np.float32)


def sfx_shutter(sr: int = MIX_SR) -> np.ndarray:
    out = np.zeros(int(0.32 * sr), np.float32)
    for at, g in ((0.0, 1.0), (0.085, 0.75)):
        c = sfx_click(sr) * g
        i = int(at * sr)
        out[i:i + c.size] += c[: out.size - i]
    return (out * 1.1).astype(np.float32)


def sfx_sparkle(sr: int = MIX_SR) -> np.ndarray:
    rng = np.random.default_rng(6)
    out = np.zeros(int(1.2 * sr), np.float32)
    for k in range(7):
        f = float(rng.choice([2093, 2349, 2637, 3136, 3520, 3951]))
        t = _tt(int(0.5 * sr), sr)
        note = np.sin(2 * np.pi * f * t) * np.exp(-t * 9) * 0.22
        i = int((k * 0.11 + rng.random() * 0.04) * sr)
        out[i:i + note.size] += note[: out.size - i]
    return out


def sfx_typing(sr: int = MIX_SR) -> np.ndarray:
    rng = np.random.default_rng(7)
    out = np.zeros(int(1.4 * sr), np.float32)
    t_at = 0.0
    while t_at < 1.25:
        c = sfx_click(sr) * float(0.5 + 0.5 * rng.random())
        i = int(t_at * sr)
        out[i:i + c.size] += c[: out.size - i]
        t_at += float(0.07 + 0.08 * rng.random())
    return out


def sfx_swipe(sr: int = MIX_SR) -> np.ndarray:
    return (sfx_whoosh(sr, dur=0.28, seed=2) * 0.9).astype(np.float32)


def sfx_chime(sr: int = MIX_SR) -> np.ndarray:
    out = np.zeros(int(1.1 * sr), np.float32)
    for at, f in ((0.0, 880.0), (0.14, 1318.5)):
        t = _tt(int(0.9 * sr), sr)
        note = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t * 5.5) * 0.3
        i = int(at * sr)
        out[i:i + note.size] += note[: out.size - i]
    return out


# What the planner may put on a beat ("sfx"), with the effect's meaning for the prompt. `tick` stays internal.
# Only NON-TONAL effects remain (owner decision 2026-11-25: bells, dings, chimes and sparkles were annoying and made no sense). The tonal builders above (ding, chime, sparkle, pop,
# tick, riser) are kept as functions but are not registered: a plan that still names one gets no sound.
PLANNER_SFX = {
    "whoosh": "a transition", "click": "a step or a choice", "impact": "a big moment", "shutter": "a photo is shown", "typing": "writing or computing", "swipe": "a quick change",
}
_BANK_BUILDERS = {"whoosh": sfx_whoosh, "click": sfx_click, "impact": sfx_impact, "shutter": sfx_shutter, "typing": sfx_typing, "swipe": sfx_swipe}
SFX_KINDS = tuple(_BANK_BUILDERS)


def build_sfx_track(events: Sequence[Tuple[float, str, float]], duration: float, sr: int = MIX_SR) -> np.ndarray:
    """events: (time_s, kind, gain). Returns stereo (n,2)."""
    n = int(duration * sr)
    out = np.zeros(n, np.float32)
    bank = {k: _BANK_BUILDERS[k](sr) for k in {e[1] for e in events if e[1] in _BANK_BUILDERS}}
    for t, kind, gain in events:
        s = bank.get(kind)
        i = int(t * sr)
        if s is None or i < 0 or i >= n:
            continue
        j = min(n, i + s.size)
        out[i:j] += s[: j - i] * gain
    return np.stack([out, out], axis=1)


def build_clip_audio_track(items: Sequence[Tuple[float, float, np.ndarray]], duration: float, sr: int = MIX_SR) -> np.ndarray:
    """The person's own clips' sound placed on the timeline. items: (start_s, longest_s, mono samples at `sr`); each is cut to its scene and faded 30 ms at both ends. Returns stereo (n,2)."""
    n = int(duration * sr)
    out = np.zeros(n, np.float32)
    for start, longest, s in items:
        i = int(start * sr)
        if i < 0 or i >= n or s is None or s.size == 0:
            continue
        s = s[: int(longest * sr)].astype(np.float32).copy()
        f = min(s.size // 2, int(0.03 * sr))
        if f > 1:
            s[:f] *= np.linspace(0, 1, f, dtype=np.float32)
            s[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
        j = min(n, i + s.size)
        out[i:j] += s[: j - i]
    return np.stack([out, out], axis=1)
