"""Word timings for captions/karaoke.

Per-beat synthesis already gives exact beat boundaries. Inside a beat we distribute words over the audio
duration in proportion to their length plus a pause weight for punctuation, which is accurate to roughly a
few hundred ms: good enough for karaoke highlighting. (Forced alignment with whisper.cpp / CTC can replace
this later without touching anything downstream: it produces the same [(word, start, end)] shape.)
"""
import re
from typing import List, Tuple

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
