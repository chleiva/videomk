"""Audio synthesis: narration track assembly, procedural music and SFX.

Music and SFX are generated with numpy, so they carry no licence, no Content ID risk and cost nothing
to store. (A curated CC0 pack can replace them per theme later; the interface is the same.)
"""
import wave
from typing import Dict, List, Sequence, Tuple

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


def _freq(name: str, octave: int) -> float:
    return 440.0 * 2 ** ((_NOTE[name] + 12 * (octave - 4) - 9) / 12)


MOODS = {
    "calm": dict(bpm=66, chords=[("A", "minor"), ("F", "major"), ("C", "major"), ("G", "major")], pluck=0.16),
    "bright": dict(bpm=84, chords=[("C", "major"), ("G", "major"), ("A", "minor"), ("F", "major")], pluck=0.22),
    "tense": dict(bpm=72, chords=[("A", "minor"), ("E", "minor"), ("F", "major"), ("E", "minor")], pluck=0.12),
}


def _triad(root: str, quality: str) -> List[float]:
    r = _freq(root, 3)
    third = 3 if quality == "minor" else 4
    return [r, r * 2 ** (third / 12), r * 2 ** (7 / 12)]


def generate_music(duration: float, mood: str = "calm", sr: int = MIX_SR, seed: int = 7) -> np.ndarray:
    """Soft ambient pad + sparse plucks. Returns stereo float32 shaped (n, 2), peak-normalised to 0.6."""
    cfg = MOODS.get(mood, MOODS["calm"])
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float32) / sr
    beat = 60.0 / cfg["bpm"]
    bar = beat * 4
    L = np.zeros(n, np.float32)
    R = np.zeros(n, np.float32)
    n_bars = int(duration / bar) + 2
    for b in range(n_bars):
        root, quality = cfg["chords"][b % len(cfg["chords"])]
        freqs = _triad(root, quality)
        t0 = b * bar
        i0, i1 = int(t0 * sr), min(n, int((t0 + bar + 1.2) * sr))  # overlap into next bar
        if i0 >= n:
            break
        tt = t[i0:i1] - t0
        env = np.minimum(1.0, tt / 1.0) * np.exp(-np.maximum(0.0, tt - bar) * 2.5)  # slow attack, long tail
        pad = np.zeros_like(tt)
        for k, f in enumerate(freqs + [freqs[0] / 2]):
            for det, amp in ((0.0, 1.0), (0.3, 0.6), (-0.4, 0.6)):
                ff = f * (1 + det * 0.004)
                pad += amp * (np.sin(2 * np.pi * ff * tt) + 0.35 * np.sin(2 * np.pi * 2 * ff * tt) + 0.12 * np.sin(2 * np.pi * 3 * ff * tt)) / (1 + 0.3 * k)
        pad *= env * 0.045
        L[i0:i1] += pad * 1.0
        R[i0:i1] += pad * 0.92
        # plucks on off-beats
        for q in range(8):
            if rng.random() > 0.55:
                continue
            f = freqs[int(rng.integers(0, 3))] * 4
            tp = t0 + q * beat / 2
            j0 = int(tp * sr)
            if j0 >= n:
                break
            j1 = min(n, j0 + int(1.1 * sr))
            tl = t[j0:j1] - tp
            pl = np.sin(2 * np.pi * f * tl) * np.exp(-tl * 5.5) * cfg["pluck"] * 0.06
            pan = rng.random()
            L[j0:j1] += pl * (1 - pan * 0.6)
            R[j0:j1] += pl * (0.4 + pan * 0.6)
    out = np.stack([L, R], axis=1)
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.6).astype(np.float32)


# ----------------------------------------------------------------------------- sfx
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


def build_sfx_track(events: Sequence[Tuple[float, str, float]], duration: float, sr: int = MIX_SR) -> np.ndarray:
    """events: (time_s, kind, gain). Returns stereo (n,2)."""
    n = int(duration * sr)
    out = np.zeros(n, np.float32)
    bank = {"whoosh": sfx_whoosh(sr), "pop": sfx_pop(sr), "tick": sfx_tick(sr)}
    for t, kind, gain in events:
        s = bank.get(kind)
        i = int(t * sr)
        if s is None or i < 0 or i >= n:
            continue
        j = min(n, i + s.size)
        out[i:j] += s[: j - i] * gain
    return np.stack([out, out], axis=1)
