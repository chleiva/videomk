"""The music director's instrument: parametric, procedural background music.

The planner (an LLM) picks a style from `STYLES`, optionally a key, a tempo, an energy (1-5) and up to two style changes at chapter shifts.
This module renders exactly that, with numpy only: no licence, no Content ID risk, no cost, instant, and different for every video
(the seed comes from the video id and varies the chord progression, the patterns, the tempo a little and the stereo placement).

An AI music model (ElevenLabs Music, Lyria, Stable Audio...) can later replace `render_segment` behind the same interface; see docs/MUSIC.md.
"""
import math
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

SR = 44100
XFADE_S = 2.6          # crossfade between two styles
MAX_SEGMENTS = 3       # the first style plus at most two changes
MIN_BPM, MAX_BPM = 50, 140

_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10]}


@dataclass(frozen=True)
class Style:
    label: str
    feel: str                                   # shown to the planner
    mode: str
    bpm: int
    progressions: Tuple[Tuple[int, ...], ...]   # scale degrees (1-7), one chord per bar, looped
    layers: Tuple[Dict[str, Any], ...]
    keys: Tuple[str, ...] = ("C", "D", "E", "F", "G", "A")


def _L(kind: str, **kw: Any) -> Dict[str, Any]:
    return {"kind": kind, **kw}


STYLES: Dict[str, Style] = {
    "ambient_pad": Style("Ambient pad", "slow, weightless pads with a few soft notes; calm, reflective, science, nature, long explanations", "minor", 62,
                         ((1, 6, 3, 7), (1, 4, 6, 5), (6, 4, 1, 5)),
                         (_L("pad", gain=1.0, attack=1.6, octave=4), _L("arp", inst="bell", rate=0.5, prob=0.35, octave=5, gain=0.5, pattern="random"))),
    "soft_piano": Style("Soft piano", "gentle felt-piano arpeggios over a warm pad; thoughtful, emotional, history, people, stories", "major", 72,
                        ((1, 5, 6, 4), (1, 6, 4, 5), (6, 4, 1, 5)),
                        (_L("pad", gain=0.55, attack=1.2), _L("arp", inst="piano", rate=2, prob=0.9, octave=4, gain=1.0, pattern="updown"), _L("bass", pattern="root", gain=0.5))),
    "lofi_chill": Style("Lo-fi chill", "mellow seventh chords, relaxed swung beat and soft bass; casual, modern, culture, everyday topics", "dorian", 78,
                        ((2, 5, 1, 6), (1, 4, 3, 6), (2, 5, 1, 1)),
                        (_L("pad", gain=0.45, attack=0.5, seventh=True), _L("arp", inst="piano", rate=1, prob=0.6, octave=4, gain=0.8, pattern="random", seventh=True),
                         _L("bass", pattern="root_fifth", gain=0.8), _L("drums", kick="x.....x...x.....", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", swing=0.22, gain=0.8, min_energy=2))),
    "bright_pluck": Style("Bright plucks", "upbeat major plucks with a light pulse; positive, learning, tips, kids, everyday science", "major", 100,
                          ((1, 5, 6, 4), (1, 4, 5, 4), (6, 4, 1, 5)),
                          (_L("pad", gain=0.35, attack=0.4), _L("arp", inst="bright", rate=2, prob=0.7, octave=5, gain=0.9, pattern="up"), _L("bass", pattern="root_fifth", gain=0.6),
                           _L("drums", kick="x.......x.......", snare="....x.......x...", hat="..x...x...x...x.", swing=0.0, gain=0.55, min_energy=3))),
    "cinematic_rise": Style("Cinematic", "deep drones, slow swells and sparse low hits that build; documentary, space, mystery, big ideas, danger", "minor", 60,
                            ((1, 6, 7, 1), (1, 7, 6, 5), (1, 3, 4, 5)),
                            (_L("drone", gain=1.0), _L("pad", gain=0.6, attack=2.2, octave=4), _L("swell", gain=0.9), _L("hit", gain=0.7, every=4, min_energy=2),
                             _L("arp", inst="bell", rate=0.25, prob=0.6, octave=5, gain=0.35, pattern="random"))),
    "tense_pulse": Style("Tense pulse", "a pulsing sub bass and ticking hats under dark chords; news, risk, finance, thrillers, problems", "minor", 96,
                         ((1, 1, 6, 7), (1, 4, 1, 5), (1, 7, 1, 6)),
                         (_L("pad", gain=0.55, attack=0.9, octave=4), _L("bass", pattern="pulse", gain=0.7), _L("drums", kick="x...x...x...x...", snare="................", hat="x.xxx.x.x.xxx.x.", swing=0.0, gain=0.5, min_energy=2),
                          _L("arp", inst="bright", rate=4, prob=0.35, octave=4, gain=0.35, pattern="random"))),
    "acoustic_warm": Style("Acoustic warm", "strummed guitar-like chords with a gentle groove; travel, food, family, nature, human stories", "major", 88,
                           ((1, 4, 5, 4), (1, 6, 4, 5), (1, 5, 6, 4)),
                           (_L("strum", gain=1.0), _L("bass", pattern="root", gain=0.5), _L("drums", kick="x.......x.......", snare="................", hat="..x...x...x...x.", swing=0.12, gain=0.35, min_energy=3))),
    "minimal_tech": Style("Minimal tech", "sparse bell-like arps and a soft steady kick, clean and modern; technology, software, data, engineering", "minor", 108,
                          ((1, 1, 4, 4), (1, 6, 1, 7), (1, 5, 4, 4)),
                          (_L("pad", gain=0.25, attack=0.7), _L("arp", inst="bell", rate=2, prob=0.5, octave=5, gain=0.7, pattern="random"), _L("bass", pattern="pulse", gain=0.55),
                           _L("drums", kick="x...x...x...x...", snare="................", hat="..x...x...x...x.", swing=0.0, gain=0.45, min_energy=2))),
    "uplifting_corporate": Style("Uplifting", "bright major chords, plucks and a steady beat; business, how-to, progress, achievements", "major", 104,
                                 ((1, 5, 6, 4), (1, 4, 6, 5), (4, 5, 1, 1)),
                                 (_L("pad", gain=0.6, attack=0.5), _L("arp", inst="bright", rate=2, prob=0.8, octave=5, gain=0.75, pattern="updown"), _L("bass", pattern="root_fifth", gain=0.7),
                                  _L("drums", kick="x...x...x...x...", snare="....x.......x...", hat="x.x.x.x.x.x.x.x.", swing=0.0, gain=0.6, min_energy=3))),
    "dreamy_bells": Style("Dreamy bells", "music-box bells over airy pads; wonder, space, childhood, magic, gentle stories", "major", 66,
                          ((1, 3, 4, 5), (1, 6, 2, 5), (1, 4, 1, 5)),
                          (_L("pad", gain=0.7, attack=1.8), _L("arp", inst="bell", rate=1, prob=0.75, octave=5, gain=0.9, pattern="up"), _L("bass", pattern="root", gain=0.35))),
}
DEFAULT_STYLE = "ambient_pad"
MOOD_STYLE = {"calm": "ambient_pad", "bright": "bright_pluck", "tense": "tense_pulse"}


def style_catalog() -> List[Dict[str, str]]:
    return [{"id": k, "label": s.label, "feel": s.feel} for k, s in STYLES.items()]


def prompt_list() -> str:
    return "\n".join(f"  {k}: {s.feel}" for k, s in STYLES.items())


def parse_key(key: Optional[str]) -> Optional[Tuple[int, Optional[str]]]:
    """'D minor' / 'F# major' / 'Bb' -> (semitone 0-11, mode or None)."""
    m = re.match(r"^\s*([A-Ga-g])\s*([#b♯♭]?)\s*(major|minor|maj|min|m)?\s*$", str(key or ""))
    if not m:
        return None
    semi = _NOTE[m.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1, "": 0}[m.group(2)]
    mode = {"major": "major", "maj": "major", "minor": "minor", "min": "minor", "m": "minor"}.get((m.group(3) or "").lower())
    return semi % 12, mode


# ----------------------------------------------------------------------------- instruments (all vectorised)
def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float32) / SR


def _midi_to_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def inst_piano(f: float, dur: float) -> np.ndarray:
    n = int(max(dur, 0.2) * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for k, a in enumerate((1.0, 0.55, 0.32, 0.2, 0.12, 0.07), start=1):
        fk = f * k * (1 + 0.0004 * k * k)
        out += a * np.sin(2 * np.pi * fk * t) * np.exp(-t * (1.6 + 1.1 * k) * (1.0 + 0.002 * f))
    out *= np.minimum(1.0, t / 0.006)
    return out * 0.5


def inst_pluck(f: float, dur: float) -> np.ndarray:
    n = int(max(dur, 0.2) * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for k in range(1, 7):
        out += (1.0 / k) * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (3.5 + 2.2 * k))
    return out * np.minimum(1.0, t / 0.003) * 0.55


def inst_bright(f: float, dur: float) -> np.ndarray:
    n = int(max(dur, 0.15) * SR)
    t = _t(n)
    out = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 3 * f * t) + 0.15 * np.sin(2 * np.pi * 5 * f * t)) * np.exp(-t * 6.0)
    return out * np.minimum(1.0, t / 0.004) * 0.5


def inst_guitar(f: float, dur: float) -> np.ndarray:
    n = int(max(dur, 0.3) * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for k in range(1, 11):
        out += (1.0 / k ** 1.1) * np.sin(2 * np.pi * f * k * t + 0.3 * k) * np.exp(-t * (1.3 + 0.9 * k ** 0.9))
    return out * np.minimum(1.0, t / 0.002) * 0.6


def inst_bell(f: float, dur: float) -> np.ndarray:
    n = int(max(dur, 0.5) * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for ratio, amp, tau in ((1.0, 1.0, 2.4), (2.76, 0.5, 1.5), (5.4, 0.2, 0.8), (8.93, 0.07, 0.4)):
        out += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t / tau)
    return out * np.minimum(1.0, t / 0.002) * 0.42


def inst_pad(f: float, dur: float, attack: float) -> np.ndarray:
    n = int(dur * SR)
    t = _t(n)
    out = np.zeros(n, np.float32)
    for det, amp in ((0.0, 1.0), (0.0035, 0.7), (-0.004, 0.7)):
        ff = f * (1 + det)
        out += amp * (np.sin(2 * np.pi * ff * t) + 0.3 * np.sin(2 * np.pi * 2 * ff * t) + 0.1 * np.sin(2 * np.pi * 3 * ff * t))
    env = np.minimum(1.0, t / max(attack, 0.05)) * np.minimum(1.0, (dur - t) / 0.9)
    return out * np.clip(env, 0, 1) * 0.12


def inst_bass(f: float, dur: float, sustain: bool) -> np.ndarray:
    n = int(max(dur, 0.1) * SR)
    t = _t(n)
    out = 0.7 * np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 2 * f * t) + 0.2 * np.sin(2 * np.pi * 3 * f * t)   # the upper partials carry the note on small speakers
    env = np.minimum(1.0, t / 0.008) * (np.minimum(1.0, (dur - t) / 0.06) if sustain else np.exp(-t * 3.2))
    return out * np.clip(env, 0, 1) * 0.3


def drum_kick() -> np.ndarray:
    t = _t(int(0.3 * SR))
    f = 46 + 90 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11) * 0.5


def drum_snare(rng: np.random.Generator) -> np.ndarray:
    t = _t(int(0.22 * SR))
    noise = rng.standard_normal(t.size).astype(np.float32)
    soft = np.convolve(noise, np.ones(5) / 5, mode="same")   # take the fizz off the noise: a soft brushed snare, not a hiss
    return (soft * np.exp(-t * 22) * 0.9 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28) * 0.35).astype(np.float32)


def drum_hat(rng: np.random.Generator) -> np.ndarray:
    n = int(0.06 * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    band = np.convolve(noise, np.ones(3) / 3, mode="same") - np.convolve(noise, np.ones(14) / 14, mode="same")   # a soft band of noise, not the top octave
    return band * np.exp(-_t(n) * 70) * 0.28


# ----------------------------------------------------------------------------- composition
class _Mix:
    def __init__(self, n: int):
        self.L = np.zeros(n, np.float32)
        self.R = np.zeros(n, np.float32)
        self.n = n

    def add(self, sig: np.ndarray, at: float, gain: float = 1.0, pan: float = 0.5) -> None:
        i = int(at * SR)
        if i >= self.n or i + sig.size <= 0:
            return
        a = max(0, -i)
        j = min(self.n, i + sig.size)
        seg = sig[a: a + (j - max(i, 0))] * gain
        i = max(i, 0)
        self.L[i:j] += seg * math.cos(pan * math.pi / 2)   # equal-power panning: 0 = left, 0.5 = centre, 1 = right
        self.R[i:j] += seg * math.sin(pan * math.pi / 2)


def _scale_note(root_semi: int, mode: str, degree: int, octave: int) -> float:
    """MIDI note of scale degree `degree` (1-based, may exceed 7 to climb) above the root, in the given octave (C4 = octave 4 -> midi 60)."""
    sc = _MODES[mode]
    d = degree - 1
    return 12 * (octave + 1) + root_semi + sc[d % 7] + 12 * (d // 7)


def _chord_degrees(degree: int, seventh: bool) -> List[int]:
    return [degree, degree + 2, degree + 4] + ([degree + 6] if seventh else [])


def render_segment(style_id: str, seconds: float, *, key: Optional[str], tempo: Optional[int], energy: int, seed: int) -> np.ndarray:
    """One style for `seconds`: stereo float32 (n, 2), peak-normalised to 0.6."""
    st = STYLES.get(style_id) or STYLES[DEFAULT_STYLE]
    rng = np.random.default_rng(seed)
    energy = int(min(5, max(1, energy)))
    parsed = parse_key(key)
    root = parsed[0] if parsed else _NOTE[st.keys[int(rng.integers(0, len(st.keys)))]]
    mode = parsed[1] if parsed and parsed[1] in _MODES else st.mode
    bpm = float(tempo) if tempo else st.bpm * (1 + (rng.random() - 0.5) * 0.12) * (0.92 + 0.04 * energy)
    bpm = float(min(MAX_BPM, max(MIN_BPM, bpm)))
    beat = 60.0 / bpm
    bar = beat * 4
    n = int(seconds * SR)
    mix = _Mix(n)
    prog = st.progressions[int(rng.integers(0, len(st.progressions)))]
    n_bars = int(seconds / bar) + 2
    for b in range(n_bars):
        deg = prog[b % len(prog)]
        t0 = b * bar
        for layer in st.layers:
            if energy < layer.get("min_energy", 1):
                continue
            kind, gain = layer["kind"], layer.get("gain", 1.0) * (0.75 + 0.1 * energy)
            seventh = bool(layer.get("seventh"))
            degs = _chord_degrees(deg, seventh)
            if kind == "pad":
                po = layer.get("octave", 3)
                for k, d in enumerate(degs + [deg - 7]):
                    f = _midi_to_hz(_scale_note(root, mode, d, po))
                    mix.add(inst_pad(f, bar + 1.3, layer.get("attack", 1.0)), t0 - 0.2, gain * (1.0 if k < len(degs) else 0.4), pan=0.5)
            elif kind == "drone":
                f = _midi_to_hz(_scale_note(root, mode, 1, 2))
                if b % 2 == 0:
                    tt = _t(int((bar * 2 + 1.5) * SR))
                    swellenv = np.sin(np.pi * np.minimum(1.0, tt / (bar * 2 + 1.5))) ** 1.5
                    sig = (np.sin(2 * np.pi * f * tt) + 0.7 * np.sin(2 * np.pi * f * 1.5 * tt) + 0.5 * np.sin(2 * np.pi * f * 2 * tt) + 0.3 * np.sin(2 * np.pi * f * 3 * tt)) * swellenv * 0.09
                    mix.add(sig.astype(np.float32), t0, gain, pan=0.5)
            elif kind == "arp":
                step = beat / layer["rate"]   # rate = notes per beat (0.25 = one note every four beats)
                inst = {"piano": inst_piano, "bell": inst_bell, "bright": inst_bright, "pluck": inst_pluck}[layer["inst"]]
                pool = [d + 7 * (layer["octave"] - 4) for d in degs] + [degs[0] + 7 * (layer["octave"] - 4) + 7]
                steps = max(1, int(round(bar / step)))
                for s in range(steps):
                    pat = layer.get("pattern", "up")
                    if pat == "up":
                        d = pool[s % len(pool)]
                    elif pat == "updown":
                        cyc = pool + pool[-2:0:-1]
                        d = cyc[s % len(cyc)]
                    else:
                        d = pool[int(rng.integers(0, len(pool)))]
                    if rng.random() > layer.get("prob", 1.0):
                        continue
                    f = _midi_to_hz(_scale_note(root, mode, d, 4))
                    mix.add(inst(f, min(2.4, step * 2.6)), t0 + s * step, gain * (0.8 + 0.4 * rng.random()), pan=float(rng.random()))
            elif kind == "strum":
                for hit, (off, down) in enumerate(((0.0, True), (beat * 1.5, False), (beat * 2.0, True), (beat * 3.0, False))):
                    if hit == 1 and rng.random() < 0.3:
                        continue
                    order = degs + [deg + 7]
                    order = order if down else order[::-1]
                    for k, d in enumerate(order):
                        f = _midi_to_hz(_scale_note(root, mode, d, 3 if d < deg + 7 else 4))
                        mix.add(inst_guitar(f, min(2.2, beat * 3)), t0 + off + k * 0.018, gain * (0.85 if hit % 2 else 1.0) * 0.8, pan=0.35 + 0.3 * (k / max(1, len(order) - 1)))
            elif kind == "bass":
                f = _midi_to_hz(_scale_note(root, mode, deg, 2))
                fifth = _midi_to_hz(_scale_note(root, mode, deg + 4, 2))
                pat = layer.get("pattern", "root")
                if pat == "root":
                    mix.add(inst_bass(f, beat * 3.6, True), t0, gain, 0.5)
                elif pat == "root_fifth":
                    for off, ff in ((0.0, f), (beat * 1.5, f), (beat * 2.0, fifth), (beat * 3.0, f)):
                        mix.add(inst_bass(ff, beat * 0.9, False), t0 + off, gain, 0.5)
                else:  # pulse: eighth notes
                    for s in range(8):
                        mix.add(inst_bass(f, beat * 0.45, False), t0 + s * beat / 2, gain * (1.0 if s % 2 == 0 else 0.6), 0.5)
            elif kind == "drums":
                step = bar / 16
                for s in range(16):
                    off = s * step + (layer.get("swing", 0.0) * step if s % 2 == 1 else 0.0)
                    if layer["kick"][s] == "x":
                        mix.add(drum_kick(), t0 + off, gain, 0.5)
                    if layer["snare"][s] == "x":
                        mix.add(drum_snare(rng), t0 + off, gain, 0.5)
                    if layer["hat"][s] == "x":
                        mix.add(drum_hat(rng), t0 + off, gain * (0.7 + 0.4 * rng.random()), 0.6)
            elif kind == "hit":
                if b % layer.get("every", 4) == 0:
                    f = _midi_to_hz(_scale_note(root, mode, 1, 1))
                    mix.add(inst_bass(f, 1.6, False) * 1.1, t0, gain, 0.5)
            elif kind == "swell":
                if b % 4 == 3:
                    nn = int(bar * SR)
                    noise = rng.standard_normal(nn + 200).astype(np.float32)
                    band = np.convolve(noise, np.ones(40) / 40, mode="same")[:nn]
                    env = (np.arange(nn, dtype=np.float32) / nn) ** 2.2
                    mix.add(band * env * 0.5, t0, gain, 0.5)
    out = np.stack([mix.L[:n], mix.R[:n]], axis=1)
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.6).astype(np.float32)


# ----------------------------------------------------------------------------- the whole track
def resolve(plan_music: Optional[Dict[str, Any]], mood: str, scene_starts: Sequence[float], duration: float, video_id: str = "") -> Dict[str, Any]:
    """Plan's music choice -> a concrete render spec with times: {key, tempo, seed, segments: [{start, style, energy}]}.
    Beat numbers (1-based) in `changes` become the start time of that beat's scene."""
    pm = plan_music if isinstance(plan_music, dict) else {}
    style = pm.get("style") if pm.get("style") in STYLES else MOOD_STYLE.get(mood, DEFAULT_STYLE)
    energy = int(pm.get("energy") or 3)
    segs = [{"start": 0.0, "style": style, "energy": min(5, max(1, energy))}]
    for ch in (pm.get("changes") or [])[: MAX_SEGMENTS - 1]:
        try:
            idx = int(ch["beat"]) - 1
            start = float(scene_starts[idx])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if ch.get("style") in STYLES and start > segs[-1]["start"] + 12.0 and start < duration - 12.0:  # a change needs room on both sides
            segs.append({"start": round(start, 3), "style": ch["style"], "energy": min(5, max(1, int(ch.get("energy") or energy)))})
    return {"key": pm.get("key"), "tempo": pm.get("tempo"), "seed": zlib.crc32(str(video_id).encode()) & 0x7FFFFFFF, "segments": segs}


def render(spec: Dict[str, Any], duration: float) -> np.ndarray:
    """The full background track for `duration` seconds, stereo float32 (n, 2); style changes crossfade."""
    segs = spec["segments"]
    n = int(duration * SR)
    out = np.zeros((n, 2), np.float32)
    ends = [s["start"] for s in segs[1:]] + [duration]
    for i, (s, end) in enumerate(zip(segs, ends)):
        lo = max(0.0, s["start"] - (XFADE_S / 2 if i > 0 else 0.0))
        hi = min(duration, end + (XFADE_S / 2 if i < len(segs) - 1 else 0.0))
        seg = render_segment(s["style"], hi - lo, key=spec.get("key"), tempo=spec.get("tempo"), energy=s["energy"], seed=(spec["seed"] + 7919 * i) & 0x7FFFFFFF)
        m = seg.shape[0]
        env = np.ones(m, np.float32)
        x = int(XFADE_S * SR)
        if i > 0:
            k = min(x, m)
            env[:k] = np.sin(np.linspace(0, np.pi / 2, k, dtype=np.float32))
        if i < len(segs) - 1:
            k = min(x, m)
            env[m - k:] *= np.cos(np.linspace(0, np.pi / 2, k, dtype=np.float32))
        a = int(lo * SR)
        b = min(n, a + m)
        out[a:b] += seg[: b - a] * env[: b - a, None]
    return np.clip(out, -1.0, 1.0)
