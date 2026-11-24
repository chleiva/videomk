"""Word timings for captions/karaoke.

Per-beat synthesis already gives exact beat boundaries. Inside a beat we distribute words over the audio
duration in proportion to their length plus a pause weight for punctuation, which is accurate to roughly a
few hundred ms: good enough for karaoke highlighting. (Forced alignment with whisper.cpp / CTC can replace
this later without touching anything downstream: it produces the same [(word, start, end)] shape.)
"""
import re
from typing import Dict, List, Tuple

Word = Tuple[str, float, float]

_PAUSE = {",": 2.5, ";": 3.5, ":": 3.0, "—": 3.0, ".": 5.0, "!": 5.0, "?": 5.0}


def estimate_words(text: str, duration: float, lead: float = 0.0) -> List[Word]:
    tokens = re.findall(r"\S+", text)
    if not tokens or duration <= 0:
        return []
    weights = [len(re.sub(r"\W", "", t)) + 1.5 + _PAUSE.get(t[-1], 0.0) for t in tokens]
    total = sum(weights)
    out: List[Word] = []
    t = lead
    span = max(0.1, duration)
    for tok, w in zip(tokens, weights):
        d = span * w / total
        pause = span * _PAUSE.get(tok[-1], 0.0) / total  # silence after the word, not part of it
        out.append((tok, round(t, 3), round(t + max(0.05, d - pause), 3)))
        t += d
    return out


# ============================================================================= alignment from the audio itself
# The generative voices we use have no speech marks, and a second synthesis request would not be the audio we actually play. So the timing
# comes from the waveform, for free: pauses in the audio are matched to the punctuation in the text (a period or comma is almost always an audible
# pause), and inside each phrase the words are placed by syllable weight along the *voiced* time axis. It is accurate to a small fraction of a second
# against exact speech marks (see tests/test_align.py and scripts/check_sync.py), which is what reveals and captions need.
import numpy as np

HOP_S = 0.01
MIN_PAUSE_S = 0.10
_VOWELS = re.compile(r"[aeiouyáéíóúüàèìòùâêîôûäëïöå]+", re.I)
_BOUNDARY = {",": 0.5, ";": 0.7, ":": 0.6, "—": 0.6, "–": 0.5, ".": 1.0, "!": 1.0, "?": 1.0, "…": 0.8}


def syllable_weight(token: str) -> float:
    """How long a token takes to say, in rough syllables: vowel groups for words, spoken length for digits and symbols."""
    core = re.sub(r"[^\w%$€£&+]", "", token)
    if not core:
        return 0.3
    digits = re.sub(r"\D", "", core)
    letters = re.sub(r"[\d%$€£&+_]", "", core)
    w = 0.0
    if digits:
        w += max(2.0, 1.7 * len(digits))                      # "73" is "seventy-three"
    if "%" in core:
        w += 2.0                                               # "percent"
    if re.search(r"[$€£]", core):
        w += 1.8                                               # "dollars"
    if "&" in core or "+" in core:
        w += 1.0
    if letters:
        low = letters.lower()
        groups = len(_VOWELS.findall(low))
        if re.search(r"[^aeiouy]e$", low) and not re.search(r"[^aeiouy]le$", low) and groups > 1:   # a silent final e ("there", "are", "make"), but not "table"
            groups -= 1
        if re.search(r"[^aeiouytd]ed$|[^aeiouy]es$", low) and groups > 1:                              # "walked", "makes"
            groups -= 1
        w += max(1, groups) + 0.03 * len(letters)
    return max(0.6, w)


def _frame_db(samples: np.ndarray, sr: int) -> np.ndarray:
    hop = max(1, int(sr * HOP_S))
    win = hop * 3
    x = samples.astype(np.float32)
    n = max(1, (x.size - win) // hop + 1) if x.size >= win else 1
    if x.size < win:
        x = np.pad(x, (0, win - x.size))
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(x[idx] ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def voiced_mask(samples: np.ndarray, sr: int) -> np.ndarray:
    db = _frame_db(samples, sr)
    peak = float(np.percentile(db, 97))
    floor = float(np.percentile(db, 5))
    thr = max(peak - 34.0, floor + 8.0)
    return db > thr


def _runs(mask: np.ndarray, value: bool) -> List[Tuple[int, int]]:
    out, start = [], None
    for i, m in enumerate(mask):
        if m == value and start is None:
            start = i
        elif m != value and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def align_words(samples: np.ndarray, sr: int, text: str) -> Tuple[List[Word], float]:
    """-> ([(word, start_s, end_s)], confidence 0-1) with times from the first sample of `samples`. Confidence is low when the audio's pauses and the text's
    punctuation do not agree; callers then keep the plain estimate."""
    tokens = re.findall(r"\S+", text)
    if not tokens or samples.size < sr * 0.2:
        return [], 0.0
    mask = voiced_mask(samples, sr)
    voiced = _runs(mask, True)
    if not voiced:
        return [], 0.0
    first, last = voiced[0][0], voiced[-1][1]
    pauses = [(a, b) for a, b in _runs(mask[first:last], False) if (b - a) * HOP_S >= MIN_PAUSE_S]
    pauses = [(a + first, b + first) for a, b in pauses]
    # voiced-time axis: cumulative voiced frames, so words are never placed inside a silence
    cum = np.concatenate([[0], np.cumsum(mask[first:last].astype(np.float64))])      # cum[i] = voiced frames in [first, first+i)
    total_voiced = float(cum[-1]) or 1.0
    weights = [syllable_weight(t) for t in tokens]
    wsum = float(sum(weights))
    before = np.concatenate([[0.0], np.cumsum(weights)])                              # syllable weight before token i
    bounds = [(i, _BOUNDARY[t[-1]]) for i, t in enumerate(tokens[:-1]) if t[-1] in _BOUNDARY]   # a pause is expected after token i
    f = [float(before[i + 1] / wsum) for i, _ in bounds]                              # where on the speech axis each boundary should fall
    g = [float(cum[a - first] / total_voiced) for a, _ in pauses]                     # where each detected pause actually falls
    plen = [(b - a) * HOP_S for a, b in pauses]

    # Match boundaries to pauses, in order, each pause at most once. TTS honours punctuation, so the COUNT and ORDER of pauses is the strong evidence (a list spoken
    # slowly puts every boundary far from where syllable counts predict); position on the speech axis is only a weak tiebreaker. A boundary left unmatched
    # costs more than any plausible position error, an unused pause is free.
    NB, NP = len(bounds), len(pauses)
    INF = 1e9
    dp = [[INF] * (NP + 1) for _ in range(NB + 1)]       # dp[i][j]: first i boundaries decided, pauses before index j consumed
    choice: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
    for j in range(NP + 1):
        dp[0][j] = 0.0
    for i in range(1, NB + 1):
        for j in range(NP + 1):
            best, how = dp[i - 1][j] + 0.30 * bounds[i - 1][1], (i - 1, j, -1)   # boundary i-1 unmatched
            for k in range(j):                                           # matched to pause k (k < j), previous state could be any j' <= k
                cost = dp[i - 1][k] + abs(f[i - 1] - g[k]) * 0.25 - min(plen[k], 0.5) * 0.10 * bounds[i - 1][1]
                if cost < best:
                    best, how = cost, (i - 1, k, k)
            dp[i][j] = best
            choice[(i, j)] = how
    matches: Dict[int, int] = {}
    i, j = NB, NP
    while i > 0:
        pi, pj, k = choice[(i, j)]
        if k >= 0:
            matches[i - 1] = k
            j = k
        else:
            j = pj
        i = pi

    # anchors: (token index after which the phrase ends, pause) -> segment boundaries in frames
    segs: List[Tuple[int, int, int, int]] = []        # (token_lo, token_hi_exclusive, frame_lo, frame_hi)
    tok_lo, fr_lo = 0, first
    for bi in sorted(matches):
        tok_idx = bounds[bi][0]
        a, b = pauses[matches[bi]]
        segs.append((tok_lo, tok_idx + 1, fr_lo, a))
        tok_lo, fr_lo = tok_idx + 1, b
    segs.append((tok_lo, len(tokens), fr_lo, last))

    def frame_at_voiced(v: float) -> float:
        """Inverse of the cumulative voiced axis (v in voiced frames from `first`) -> frame index."""
        return first + float(np.searchsorted(cum, v, side="left"))

    db = _frame_db(samples, sr)
    smooth = np.convolve(db, np.ones(3) / 3, mode="same")

    def snap(frame: float, lo_limit: float, hi_limit: float) -> float:
        """Word boundaries sit in small energy dips: move a boundary to the deepest dip within +-80 ms when there is a real one."""
        c = int(round(frame))
        a, b = max(int(lo_limit) + 2, c - 8), min(int(hi_limit) - 2, c + 8)
        if b <= a or a < 0 or b >= len(smooth):
            return frame
        win = smooth[a:b + 1]
        k = int(np.argmin(win))
        return float(a + k) if float(np.median(win)) - float(win[k]) >= 2.5 else frame

    out: List[Word] = []
    for tlo, thi, flo, fhi in segs:
        if thi <= tlo:
            continue
        v0, v1 = float(cum[max(0, flo - first)]), float(cum[max(0, min(fhi, last) - first)])
        w = weights[tlo:thi]
        tot = float(sum(w)) or 1.0
        acc = 0.0
        edges = [float(flo)]
        for k in range(thi - tlo):
            acc += w[k]
            edges.append(frame_at_voiced(v0 + (v1 - v0) * acc / tot))
        edges[-1] = float(fhi)
        for k in range(1, len(edges) - 1):        # inner boundaries only: the phrase edges are anchored by pauses
            edges[k] = snap(edges[k], edges[k - 1] + 3, edges[k + 1] - 3)
        for k, tok in enumerate(tokens[tlo:thi]):
            s, e = edges[k], edges[k + 1]
            out.append((tok, round(s * HOP_S, 3), round(max(e * HOP_S, s * HOP_S + 0.05), 3)))
    # quality: how well the audio's pauses explain the text's punctuation, and is the speaking rate plausible
    strong = [bi for bi, (_, st) in enumerate(bounds) if st >= 0.9]
    matched_strong = sum(1 for bi in strong if bi in matches)
    pause_score = (matched_strong / len(strong)) if strong else 1.0
    rate = wsum / max(0.5, (last - first) * HOP_S)                                     # weighted syllables per second
    rate_score = 1.0 if 2.0 <= rate <= 8.5 else (0.4 if 1.4 <= rate <= 11 else 0.0)
    conf = round(min(1.0, 0.2 + 0.45 * pause_score + 0.35 * rate_score), 3)
    return out, conf
