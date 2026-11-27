"""Whole sentences taken out of narration audio that already exists, at its own pauses. No synthesis, no model: numpy and the engine's aligner.

Why (2026-11-27): Polly's lively voices take a different time for the same text on every take, so a script estimated at 45 s can come back as 48 s of speech
and no silence is short enough to hide that (the first Italian video with Beatrice: 51.4 s for 45 asked). The length of a video is a promise (engine/length.py:
at least the length asked, at most 5 percent more), so when the measured speech breaks it the timeline step removes sentences from the audio itself, the ones
the lengthening step added first (`length.pick_cut`). A sentence ends in a pause and starts after one, so the cut is silence to silence and the voice's own
intonation closes what remains. A sentence whose pauses cannot be found in the audio is never cut.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import align, length

MIN_PAUSE_S = 0.12      # a sentence boundary is a silence at least this long ...
NEAR_S = 0.15           # ... that holds the place where the aligner puts the boundary, or ends no further than this from it (a comma's breath elsewhere in the sentence is not it)
MIN_CONFIDENCE = 0.6    # what remains must still be alignable with its text, or the cut is undone
PACE_GAP = 1.7          # a sentence said this many times faster or slower than the beat as a whole is not where the boundaries say it is: nothing is cut
KEEP_S = 0.06           # silence kept at an edge of what remains (audio.trim_silence keeps the same)
FADE_S = 0.005


def _silences(samples: np.ndarray, sr: int) -> List[Tuple[float, float]]:
    mask = align.voiced_mask(samples, sr)
    return [(a * align.HOP_S, b * align.HOP_S) for a, b in align._runs(mask, False) if (b - a) * align.HOP_S >= MIN_PAUSE_S]


def _pause_at(sil: Sequence[Tuple[float, float]], t: float) -> Optional[Tuple[float, float]]:
    near = [(abs(0.5 * (a + b) - t), a, b) for a, b in sil if a - NEAR_S <= t <= b + NEAR_S]
    if not near:
        return None
    _, a, b = min(near)
    return a, b


def sentence_cuts(samples: np.ndarray, sr: int, text: str, words: Optional[Sequence[Sequence[Any]]] = None) -> List[Optional[Tuple[float, float]]]:
    """For each sentence of `text` (length.sentences): the stretch of audio (start_s, end_s) to remove so that the others remain whole, or None when the
    sentence cannot be cut cleanly (its pauses are not in the audio, the words could not be placed, or it is the only sentence). `words`: the stored word
    times of this audio ([[word, start, end]]); measured here when missing."""
    sents = length.sentences(text)
    out: List[Optional[Tuple[float, float]]] = [None] * len(sents)
    tokens = str(text or "").split()
    if len(sents) < 2 or samples.size < sr * 0.5:
        return out
    if not words or len(words) != len(tokens):
        words, conf = align.align_words(samples, sr, " ".join(tokens))
        if not words or len(words) != len(tokens) or conf < 0.6:
            return out
    counts = [len(s.split()) for s in sents]
    if sum(counts) != len(tokens):
        return out
    sil = _silences(samples, sr)
    total = samples.size / float(sr)
    bounds: List[Optional[Tuple[float, float]]] = []     # the pause between sentence j and j+1
    n = 0
    for c in counts[:-1]:
        n += c
        bounds.append(_pause_at(sil, 0.5 * (float(words[n - 1][2]) + float(words[n][1]))))
    if all(b is not None for b in bounds):
        # the boundaries must be the sentences' own: a voice that makes no pause at a full stop leaves only its commas' breaths to find, and a sentence
        # "found" between two of those is spoken at an impossible pace (syllables per voiced second) against the beat as a whole
        mask = align.voiced_mask(samples, sr)
        edges = [0.0] + [0.5 * (b[0] + b[1]) for b in bounds] + [total]
        weight, voiced, n = [], [], 0
        for j, c in enumerate(counts):
            weight.append(sum(align.syllable_weight(t) for t in tokens[n: n + c]))
            voiced.append(float(mask[int(edges[j] / align.HOP_S): int(edges[j + 1] / align.HOP_S)].sum()) * align.HOP_S)
            n += c
        whole = sum(weight) / max(sum(voiced), 1e-6)
        if any(v <= 0 or not (whole / PACE_GAP <= w / v <= whole * PACE_GAP) for w, v in zip(weight, voiced)):
            return out
    for j in range(len(sents)):
        before = bounds[j - 1] if j > 0 else None
        after = bounds[j] if j < len(sents) - 1 else None
        if j > 0 and before is None or j < len(sents) - 1 and after is None:
            continue
        if j == 0:                       # the next sentence opens what remains
            start, end = 0.0, max(0.0, after[1] - KEEP_S)
        elif j == len(sents) - 1:        # the sentence before closes it
            start, end = min(total, before[0] + KEEP_S), total
        else:                            # the pause before the sentence stays, the sentence and the pause after it go
            start, end = before[1] - 0.02, after[1] - 0.02
        if end - start >= 0.3 and (j == 0 or j == len(sents) - 1 or before != after):
            out[j] = (round(start, 3), round(end, 3))
    return out


def remove(samples: np.ndarray, sr: int, span: Tuple[float, float]) -> np.ndarray:
    """The audio without `span` (seconds), the two edges faded for a few milliseconds (both lie in silence)."""
    a, b = max(0, int(span[0] * sr)), min(samples.size, int(span[1] * sr))
    left, right = samples[:a].astype(np.float32).copy(), samples[b:].astype(np.float32).copy()
    k = int(FADE_S * sr)
    if left.size > k:
        left[-k:] *= np.linspace(1.0, 0.0, k, dtype=np.float32)
    if right.size > k:
        right[:k] *= np.linspace(0.0, 1.0, k, dtype=np.float32)
    return np.concatenate([left, right])


def candidates(plan: Dict[str, Any], audio_of: Dict[int, np.ndarray], sr: int, words_of: Optional[Dict[int, Any]] = None, *, min_beat_words: int = 6) -> List[Dict[str, Any]]:
    """Every sentence that may be taken out of this video's speech, for `length.pick_cut`: [{"beat": index, "sentence": index, "seconds": saved, "added": bool,
    "span": (start, end), "text": the sentence}]. Never the opening line of the video nor its last line, never a sentence whose beat would be left with fewer
    than `min_beat_words`, never a pause beat (the rules of `length.fit_script`). `audio_of`: beat index -> its samples (beats without audio here are skipped)."""
    beats = plan.get("beats") or []
    out: List[Dict[str, Any]] = []
    for i, b in enumerate(beats):
        a = audio_of.get(i)
        if a is None or b.get("silent") or not b.get("narration"):
            continue
        sents = length.sentences(b["narration"])
        if len(sents) < 2:
            continue
        added = set(length.added_sentences(plan, i, b))
        cuts = sentence_cuts(a, sr, b["narration"], (words_of or {}).get(i))
        for j, span in enumerate(cuts):
            if span is None or (i == 0 and j == 0) or (i == len(beats) - 1 and j == len(sents) - 1):
                continue
            if len(" ".join(sents[:j] + sents[j + 1:]).split()) < min_beat_words:
                continue
            out.append({"beat": i, "sentence": j, "seconds": round(span[1] - span[0], 3), "added": sents[j] in added, "span": span, "text": sents[j]})
    return out


def fit(plan: Dict[str, Any], audio_of: Dict[int, np.ndarray], sr: int, total_at_floors: Any, target_seconds: float, words_of: Optional[Dict[int, Any]] = None,
        *, min_beat_words: int = 6, max_cuts: int = 12) -> List[Dict[str, Any]]:
    """Cuts sentences out of the speech until the video fits its window or nothing more can go. IN PLACE: `plan["beats"][i]["narration"]` loses the sentence,
    `audio_of[i]` becomes the shorter audio, `words_of[i]` is dropped (the caller measures the new audio). `total_at_floors(durations: {beat index: seconds})`
    -> the length of the video with the shortest silences given the speech lengths of the beats that changed (the timeline knows: timeline.shortest).
    -> the cuts made: [{"beat", "sentence", "seconds", "added", "text"}]."""
    done: List[Dict[str, Any]] = []
    durs: Dict[int, float] = {}
    refused: set = set()
    for _ in range(max_cuts * 2):
        total = float(total_at_floors(durs))
        if length.overrun(total, target_seconds) <= 0 or len(done) >= max_cuts:
            break
        cands = [c for c in candidates(plan, audio_of, sr, words_of, min_beat_words=min_beat_words) if (c["beat"], c["text"]) not in refused]
        pick = length.pick_cut(cands, total, target_seconds)
        if pick is None:
            break
        i = pick["beat"]
        b = plan["beats"][i]
        sents = length.sentences(b["narration"])
        text = " ".join(sents[:pick["sentence"]] + sents[pick["sentence"] + 1:])
        shorter = remove(audio_of[i], sr, pick["span"])
        words, conf = align.align_words(shorter, sr, text)
        if not words or len(words) != len(text.split()) or conf < MIN_CONFIDENCE:   # the audio that would remain does not match the text that would remain: not this sentence
            refused.add((i, pick["text"]))
            continue
        b["narration"], audio_of[i] = text, shorter
        durs[i] = audio_of[i].size / float(sr)
        if words_of is not None:
            words_of.pop(i, None)
        done.append({k: pick[k] for k in ("beat", "sentence", "seconds", "added", "text")})
    return done
