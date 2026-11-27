"""One register for a speaker from the first scene to the last (2026-11-27, docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md).

Polly's lively voices (engine/voices.STEADY are the others) give a new take of a text every time, and now and then a take sits in another register: in the
first Italian video with Beatrice three beats had a median pitch of 175 to 200 Hz and the last one 271 Hz, 7.6 semitones higher, with no question or
exclamation in it. From one scene to the next that sounds like another person. Measured on the Italian and Spanish QA plans (three takes of every beat):
the spread between the beats of a video is 6.1 semitones on average for Beatrice and 2.8 for Lupe; steady voices stay within 0.8.

What does NOT fix it, measured: saying the whole narration in one request and cutting it at the beats (Beatrice 7.0 and 3.4 semitones in two takes, Lupe 2.7
and 2.9; and two cuts of fourteen landed 2.5 s inside the wrong beat), or saying the sentence before as a lead-in and cutting it off (6.6 and 3.3). The register
moves inside one request too.

What does: choosing among takes. Every beat is said once, as always. A beat whose median pitch is more than BAND_ST semitones from the speaker's register in
this video is said again, at most RETAKES times, and the take nearest the register is kept. The register is the median of the LOWER half of the first takes
of the speaker's beats: the excursions are upward (an excited mode), so the lower half is the speaker's normal voice even when half the beats went up.
A take is whole, so the liveliness inside a beat is untouched (pitch spread inside beats 5.0 semitones before and after) and the words are timed from the
audio that is kept. Cost: only the retakes, about 0.2 to 0.5 times the characters of a video with a lively voice; nothing for a steady voice.

Beats are made in parallel, one function each, so each one writes the median pitch of its first take next to its audio (`<hash>.f0.json`) and reads the
others': no shared state, no new permissions, and an edited beat finds the register of the beats that were not edited.
"""
import math
import os
from typing import Any, Dict, List, Optional

import numpy as np

from . import length, voices

BAND_ST = 2.0            # a beat this many semitones from the speaker's register is said again (the aim: under about 2.5 between any two beats)
QUESTION_BAND_ST = 4.0   # a beat that is all questions or exclamations may sit higher: that is what the text asks for
WAIT_S = 4.0             # how long a beat waits for the first takes of the others before it judges its own
PEERS = 3                # first takes of other beats that are enough to know the register


def retakes() -> int:
    """How many more takes a beat may ask for: server setting REGISTER_RETAKES (default 2; 0 turns the step off)."""
    try:
        return max(0, min(4, int(os.environ.get("REGISTER_RETAKES", "2"))))
    except ValueError:
        return 2


def median_pitch(samples: np.ndarray, sr: int, fmin: float = 65.0, fmax: float = 480.0) -> Optional[float]:
    """The median fundamental frequency of speech in Hz (None when too little of it is voiced). Normalised autocorrelation on 40 ms windows every 20 ms,
    numpy only: about 0.1 s of work for a beat. The same tracker the voices were measured with."""
    a = np.asarray(samples, dtype=np.float32)
    win, hop = int(0.040 * sr), int(0.020 * sr)
    if a.size < win * 4:
        return None
    lo, hi = int(sr / fmax), int(sr / fmin)
    nfft = 1 << int(np.ceil(np.log2(2 * win)))
    w = np.hanning(win).astype(np.float32)
    rw = np.fft.irfft(np.abs(np.fft.rfft(w, nfft)) ** 2)[: hi + 2]
    rw = rw / rw[0]
    peak = float(np.max(np.abs(a))) or 1.0
    f0: List[float] = []
    for i in range(0, a.size - win, hop):
        x = a[i: i + win]
        if float(np.sqrt(np.mean(x * x))) < 0.03 * peak:
            continue
        x = (x - x.mean()) * w
        r = np.fft.irfft(np.abs(np.fft.rfft(x, nfft)) ** 2)[: hi + 2]
        if r[0] <= 0:
            continue
        r = r / r[0] / np.maximum(rw, 1e-3)
        seg = r[lo: hi + 1]
        k = int(np.argmax(seg))
        if seg[k] < 0.5:
            continue
        cand = np.where((seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > 0.9 * seg[k]))[0] + 1   # the shortest lag near the best: no octave-down errors
        if cand.size:
            k = int(cand[0])
        f0.append(sr / float(k + lo))
    if len(f0) < 15:
        return None
    med = float(np.median(f0))
    kept = [f for f in f0 if med / 2.2 < f < med * 2.2]
    return round(float(np.median(kept)), 1)


def semitones(hz: float, ref: float) -> float:
    return 12.0 * math.log2(float(hz) / float(ref))


def reference(first_takes: List[float]) -> Optional[float]:
    """The speaker's register in this video, from the median pitch of the first take of each beat: the median of the lower half."""
    xs = sorted(float(x) for x in first_takes if x)
    if len(xs) < 2:
        return None
    low = xs[: (len(xs) + 1) // 2]
    return float(np.median(low))


def band(text: str) -> float:
    """How far from the register this text may be: more when every sentence of it is a question or an exclamation."""
    sents = length.sentences(text)
    return QUESTION_BAND_ST if sents and all(s.rstrip("\"'”’)»").endswith(("?", "!")) for s in sents) else BAND_ST


def off(hz: Optional[float], ref: Optional[float], text: str = "") -> float:
    """Semitones a take lies outside the band around the register (0.0: inside, or nothing to compare with)."""
    if not hz or not ref:
        return 0.0
    return max(0.0, abs(semitones(hz, ref)) - band(text))


def applies(plan: Dict[str, Any], beat: Dict[str, Any]) -> bool:
    """Only where takes differ: a lively Polly voice on the generative engine. Never a pause beat."""
    cfg = plan.get("tts") or {}
    if beat.get("silent") or not beat.get("narration") or retakes() <= 0:
        return False
    return (cfg.get("provider") or "polly") == "polly" and (cfg.get("engine") or "") == "generative" and voices.lively(voices.beat_voice(plan, beat))


def peers(plan: Dict[str, Any], beat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The other spoken beats of the same voice in this video."""
    voice = voices.beat_voice(plan, beat)
    return [b for b in plan.get("beats") or [] if b is not beat and b.get("id") != beat.get("id") and not b.get("silent") and b.get("narration")
            and voices.beat_voice(plan, b) == voice]


def choose(takes: List[Dict[str, Any]], ref: float) -> int:
    """The index of the take nearest the register. `takes`: [{"hz": median pitch or None}]; a take whose pitch could not be measured is never preferred."""
    scored = [(abs(semitones(t["hz"], ref)) if t.get("hz") else 99.0, i) for i, t in enumerate(takes)]
    return min(scored)[1]
