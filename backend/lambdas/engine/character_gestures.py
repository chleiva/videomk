"""Automatic speaker gestures for the standing presenter rig (engine/vector_presenter.py). No model decides anything here: the narration's words and their timings do.

  plan_gestures(words)        text cues + word timings -> a short list of Gesture events (at most one meaningful gesture per sentence, never overlapping, each one returns
                              to the home position), plus beat times on stressed words
  Performance(...).pose(t)    a pure function of time: the events, the idle life (breathing, blinks, weight shift, small head moves, eye darts), listening, entering and
                              leaving, turned into one pose dict for Presenter.draw. The same input and seed give the same pose on any machine, in any order of frames.

The rules follow what speaking coaches teach and what gesture research measured (sources in docs/CHARACTER_ANIMATION_PROOF.md):
  * home base = arms relaxed at the sides; the hands come back to it after every gesture
  * gestures stay in the box between waist and shoulders (only the greeting wave goes higher), with OPEN hands; nobody points with a finger
  * the stroke of a gesture lands on (a hair before) the word it belongs to; the preparation starts about 0.4 s earlier (Kendon's phases: preparation, stroke, hold, retraction)
  * the hand travels on an arc about the shoulder and the elbow follows (IK); slow in, slow out, a small settle after the stroke, the hand drags behind the forearm,
    and in two-handed gestures one hand leads by two or three frames (no twinning)
  * a character is never still: breathing, irregular blinks, a weight shift now and then, eye darts, nods on stressed words

Text cues (English and Spanish): greeting / goodbye -> wave; "first, second, third", a number up to three, or a list "a, b and c" -> count on the fingers;
"but / however / on the other hand" -> compare left and right; a question -> shrug with open palms; "this / here / look" -> present toward the content with the whole hand;
"great / exactly / perfecto" -> thumb up; strong words (very, important, never, every, "!") -> both palms open; otherwise a small beat on the most stressed word, or nothing.
"""
import bisect
import math
import re
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]
Vec = Tuple[float, float]

KINDS = ("wave", "count", "compare", "shrug", "present", "thumb", "open", "beat")      # in order of priority
PRIORITY = {k: i for i, k in enumerate(KINDS)}

# ----------------------------------------------------------------------------- limits (tests check them)
PREP_S = 0.42               # preparation: the hand leaves home this long before the stroke
RETRACT_S = 0.60            # back to home base
MIN_HOLD_S = 0.45
MAX_HOLD_S = 1.9
GAP_S = 0.20                # hands rest at least this long between two gestures
STROKE_LEAD_S = 0.06        # the stroke lands this much BEFORE the word starts (never after)
MAX_PER_MINUTE = 22.0       # meaningful gestures (beats are counted separately)
MAX_BUSY = 0.78             # share of the talk during which the hands are away from home base
BEAT_GAP_S = 1.1
TWIN_LAG_S = 0.075          # the second hand of a two-handed gesture follows this much later
REST_WRIST = -11.0         # at home the hand hangs a little toward the leg, not flared out
GESTURE_BOX_TOP = 0.18      # wrist height above the shoulder, as a share of the arm length, that no gesture but the wave may pass

# key poses: wrist target relative to the shoulder as a share of the arm length (x away from the body, y up), wrist turn in degrees, hand shape
KEY: Dict[str, Tuple[Vec, float, str]] = {
    "open": ((0.62, -0.50), 14.0, "open"),
    "present": ((0.90, -0.24), 8.0, "open"),
    "present_low": ((0.74, -0.42), 10.0, "open"),
    "count": ((0.47, 0.13), -4.0, "one"),
    "compare": ((0.70, -0.38), 16.0, "open"),
    "shrug": ((0.64, -0.40), 30.0, "open"),
    "wave": ((0.50, 0.50), -6.0, "open"),
    "thumb": ((0.50, 0.08), -4.0, "thumb"),
    "beat": ((0.19, -0.88), 10.0, "relaxed"),
}
COUNT_SHAPES = ("one", "two", "three")

# ----------------------------------------------------------------------------- text cues (EN + ES)
_GREET = {"hello", "hi", "hey", "welcome", "hola", "bienvenido", "bienvenida", "bienvenidos", "bienvenidas", "buenas", "buenos"}
_BYE = {"bye", "goodbye", "thanks", "thank", "adios", "adiós", "gracias", "hasta", "chao"}
_ORDINAL = {"first": 1, "firstly": 1, "second": 2, "secondly": 2, "third": 3, "thirdly": 3, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercera": 3}
_NUMBER = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3, "dos": 2, "tres": 3}
_CONTRAST = {"but", "however", "instead", "whereas", "versus", "vs", "yet", "pero", "sino", "aunque"}
_CONTRAST_PHRASE = (("on", "the", "other", "hand"), ("sin", "embargo"), ("en", "cambio"), ("por", "otro", "lado"), ("on", "the", "contrary"))
_DEICTIC = {"this", "these", "here", "look", "see", "watch", "notice", "aquí", "aqui", "mira", "miren", "observa", "este", "esta", "estos", "estas", "fíjate"}
_AFFIRM = {"great", "perfect", "exactly", "excellent", "awesome", "genial", "perfecto", "excelente", "exacto", "bravo"}
_STRONG = {"very", "really", "important", "key", "never", "always", "must", "every", "everything", "all", "huge", "best", "most", "essential", "remember",
           "muy", "importante", "clave", "nunca", "siempre", "todo", "todos", "mejor", "esencial", "recuerda"}
_LIST_AND = {"and", "or", "y", "o", "e"}
_FUNCTION = {"the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "it", "that", "for", "with", "as", "at", "by", "i", "im", "you", "we", "so", "be", "my", "your",
             "el", "la", "los", "las", "un", "una", "de", "en", "y", "o", "es", "son", "que", "por", "con", "para", "se", "lo", "al", "del", "mi", "tu", "su"}


def _norm(tok: str) -> str:
    return re.sub(r"[^\wáéíóúüñ]", "", tok.lower())


def _h01(*parts: Any) -> float:
    """Deterministic 0..1 from anything printable (never Python's own hash: that changes from run to run)."""
    return (zlib.crc32("|".join(str(p) for p in parts).encode("utf-8")) & 0xFFFFFF) / float(0x1000000)


class Gesture:
    """One planned gesture. Times in seconds: t0 the hands leave home, `stroke` the gesture lands, `hold_end` they start back, t1 they are home again.
    hand: "l", "r" (left / right of the picture) or "both"; lead: which hand moves first; steps: [(time, value)] changes during the hold (count: finger number, compare: the
    second hand); side: -1 / +1 where a presenting gesture aims."""
    __slots__ = ("kind", "t0", "stroke", "hold_end", "t1", "hand", "lead", "steps", "side", "amp", "word")

    def __init__(self, kind: str, t0: float, stroke: float, hold_end: float, t1: float, hand: str, lead: str = "r", steps: Sequence[Tuple[float, Any]] = (), side: int = 0,
                 amp: float = 1.0, word: str = ""):
        self.kind, self.t0, self.stroke, self.hold_end, self.t1, self.hand, self.lead = kind, t0, stroke, hold_end, t1, hand, lead
        self.steps, self.side, self.amp, self.word = tuple(steps), side, amp, word

    def as_tuple(self) -> tuple:
        return (self.kind, round(self.t0, 3), round(self.stroke, 3), round(self.hold_end, 3), round(self.t1, 3), self.hand, self.lead, self.steps, self.side, round(self.amp, 3))

    def __repr__(self) -> str:
        return f"Gesture({self.kind} {self.hand} {self.t0:.2f}>{self.stroke:.2f}>{self.hold_end:.2f}>{self.t1:.2f} '{self.word}')"


def _far(kind: str) -> float:
    """How much longer the way home is for the gestures that go high."""
    return 1.35 if kind == "wave" else 1.15 if kind in ("count", "thumb") else 1.0


def _last_beat(g: Gesture) -> float:
    """The last moment of a gesture that must be seen: its stroke, or its last step (the third finger of a count, the second hand of a comparison); the wave keeps a second."""
    return max([g.stroke + (1.0 if g.kind == "wave" else 0.0)] + [s[0] for s in g.steps])


def _fit(prev: Gesture, g: Gesture) -> bool:
    """Make room so that g starts after prev is back home: prev lets go sooner (never before its last beat has been seen for MIN_HOLD_S), prev returns a little faster,
    g prepares a little faster. False when that is not enough (nothing is changed then)."""
    need = prev.t1 + GAP_S - g.t0
    if need <= 0:
        return True
    room = max(0.0, prev.hold_end - (_last_beat(prev) + MIN_HOLD_S))
    quick = max(0.0, (prev.t1 - prev.hold_end) - 0.44 * _far(prev.kind))
    prep = max(0.0, (g.stroke - g.t0) - 0.30)
    if room + quick + prep < need:
        return False
    a = min(room, need)
    prev.hold_end -= a
    prev.t1 -= a
    need -= a
    a = min(quick, need)
    prev.t1 -= a
    need -= a
    g.t0 += need
    return True


def sentences(words: Sequence[Word]) -> List[List[int]]:
    """Indices of the words of each sentence (a sentence ends at . ! ? or at a pause longer than 0.7 s)."""
    out: List[List[int]] = []
    cur: List[int] = []
    for i, (w, a, b) in enumerate(words):
        cur.append(i)
        last = i == len(words) - 1
        if w.rstrip("\"')»”")[-1:] in ".!?…" or last or words[i + 1][1] - b > 0.7:
            out.append(cur)
            cur = []
    return out


def _stress_score(words: Sequence[Word], i: int, level: Optional[Sequence[float]]) -> float:
    """How strongly word i is stressed: its loudness when a per-word level is given, and always: content words over function words, longer words a little more."""
    n = _norm(words[i][0])
    s = 0.15 if n in _FUNCTION or len(n) <= 2 else 0.55 + min(0.25, 0.03 * len(n))
    if n in _STRONG or words[i][0].isupper() and len(n) > 2:
        s += 0.3
    if level is not None and i < len(level):
        s = 0.5 * s + 0.5 * float(level[i])
    return s


def word_levels(words: Sequence[Word], env: Sequence[float], fps: float, t0: float = 0.0) -> List[float]:
    """Loudness of each word (0..1) from a per-frame speech level track (engine.vector_character.speech_envelope) that starts at t0."""
    out = []
    for _, a, b in words:
        i0, i1 = max(0, int((a - t0) * fps)), min(len(env), max(int((a - t0) * fps) + 1, int((b - t0) * fps) + 1))
        out.append(float(max(env[i0:i1])) if i1 > i0 else 0.0)
    return out


def _candidates(words: Sequence[Word], idx: List[int], first: bool, last: bool, level: Optional[Sequence[float]]) -> List[Dict[str, Any]]:
    """Every gesture the sentence could carry: [{kind, i (the word the stroke lands on), ...}]."""
    toks = [_norm(words[i][0]) for i in idx]
    raw = [words[i][0] for i in idx]
    out: List[Dict[str, Any]] = []
    n = len(idx)
    if first and any(t in _GREET for t in toks[:3]):
        out.append({"kind": "wave", "i": idx[0]})
    if last and any(t in _BYE for t in toks):
        k = next(j for j, t in enumerate(toks) if t in _BYE)
        out.append({"kind": "wave", "i": idx[k]})
    # counting: an ordinal, a list "a, b and c", or a small number
    k_ord = 0 if toks[0] in _ORDINAL else (1 if n > 1 and toks[0] in ("and", "then", "y", "luego") and toks[1] in _ORDINAL else None)
    if k_ord is not None:
        out.append({"kind": "count", "i": idx[k_ord], "steps": [(idx[k_ord], _ORDINAL[toks[k_ord]])]})
    else:
        commas = [j for j in range(n - 1) if raw[j].endswith(",")]
        k_and = next((j for j in range(n - 1) if toks[j] in _LIST_AND and commas and commas[-1] < j <= commas[-1] + 4), None)
        ends: List[int] = []
        if k_and is not None:
            # the stroke of each count lands on the LAST word of an item (its head noun, in most lists); the last item on the word after "and"
            if len(commas) >= 2 and commas[-1] - commas[-2] <= 5:
                ends = [commas[-2], commas[-1], k_and + 1] if k_and == commas[-1] + 1 else [commas[-2], commas[-1], k_and - 1]
            elif len(commas) == 1 and 2 <= k_and - commas[0] <= 3:
                ends = [commas[0], k_and - 1, k_and + 1]
        if ends:
            steps = [(idx[e], m + 1) for m, e in enumerate(ends)]
            out.append({"kind": "count", "i": steps[0][0], "steps": steps})
        if not any(c["kind"] == "count" for c in out):
            k_num = next((j for j, t in enumerate(toks) if t in _NUMBER and _NUMBER[t] >= 2), None)
            if k_num is not None:
                out.append({"kind": "count", "i": idx[k_num], "steps": [(idx[k_num], _NUMBER[toks[k_num]])]})
    # contrast
    k_con = None
    for ph in _CONTRAST_PHRASE:
        for j in range(n - len(ph) + 1):
            if tuple(toks[j:j + len(ph)]) == ph:
                k_con = j
                break
        if k_con is not None:
            break
    if k_con is None:
        k_con = next((j for j, t in enumerate(toks) if t in _CONTRAST), None)
    if k_con is not None:
        if k_con >= 3:           # "A ..., but B ...": one hand for A, the other for B
            a = max(range(0, k_con), key=lambda j: _stress_score(words, idx[j], level))
            out.append({"kind": "compare", "i": idx[a], "second": idx[k_con]})
        else:                    # the sentence opens with the contrast: the "other hand" alone
            out.append({"kind": "compare", "i": idx[k_con], "second": None})
    if raw[-1].rstrip("\"')»”").endswith("?") and n >= 3:
        k = max(range(n), key=lambda j: _stress_score(words, idx[j], level) + (0.2 if j >= n - 2 else 0.0))
        out.append({"kind": "shrug", "i": idx[k]})
    k_d = next((j for j, t in enumerate(toks) if t in _DEICTIC), None)
    if k_d is not None and n >= 3:
        out.append({"kind": "present", "i": idx[k_d]})
    k_a = next((j for j, t in enumerate(toks) if t in _AFFIRM), None)
    if k_a is not None:
        out.append({"kind": "thumb", "i": idx[k_a]})
    k_s = next((j for j, t in enumerate(toks) if t in _STRONG), None)
    if k_s is None and raw[-1].rstrip("\"')»”").endswith("!") and n >= 3:
        k_s = max(range(n), key=lambda j: _stress_score(words, idx[j], level))
    if k_s is not None and n >= 3:
        out.append({"kind": "open", "i": idx[k_s]})
    return out


def plan_gestures(words: Sequence[Word], seed: float = 0.0, content_side: int = 0, level: Optional[Sequence[float]] = None, end: Optional[float] = None,
                  max_per_minute: float = MAX_PER_MINUTE, max_busy: float = MAX_BUSY) -> Tuple[List[Gesture], List[Tuple[float, str, float]]]:
    """-> (gestures, beats). words: [(word, start_s, end_s)] of ONE speaker, in order. content_side: -1 / +1 when there is content on the left / right of the speaker (0: none).
    level: optional loudness per word (word_levels). beats: [(time, hand, strength)] small pulses on stressed words, layered on whatever the hands are doing.
    Deterministic: the same words, seed and options give the same plan."""
    if not words:
        return [], []
    sents = sentences(words)
    total = (end if end is not None else words[-1][2]) - words[0][1]
    picked: List[Gesture] = []
    last_kind = ""
    last_hand = "l" if _h01(seed, "hand") < 0.5 else "r"
    for si, idx in enumerate(sents):
        cands = _candidates(words, idx, si == 0, si == len(sents) - 1, level)
        cands.sort(key=lambda c: PRIORITY[c["kind"]])
        s_end = words[idx[-1]][2]
        for c in cands:
            kind = c["kind"]
            if kind == last_kind and kind not in ("count",):      # never the same gesture twice in a row (a running count is one idea)
                continue
            if kind == "present" and content_side == 0 and _h01(seed, si, "p") < 0.35:
                continue
            ws = words[c["i"]][1]
            prep = PREP_S * (0.9 + 0.3 * _h01(seed, si, "prep")) * (1.6 if kind == "wave" else 1.35 if kind in ("count", "thumb") else 1.0)     # a longer way up takes longer
            stroke = max(ws - STROKE_LEAD_S, prep)                 # a talk that opens on its cue word: the hand still gets its full preparation (the only late stroke)
            t0 = max(0.0, stroke - prep)
            hand, lead, side, steps = "both", last_hand, 0, []
            hold_end = min(max(stroke + MIN_HOLD_S, s_end - 0.15), stroke + MAX_HOLD_S)
            if kind == "wave":
                hand = "r" if content_side <= 0 else "l"          # wave with the hand away from the content
                hold_end = max(stroke + 1.05, min(s_end, stroke + 1.6))
            elif kind == "count":
                hand = "l" if content_side > 0 else "r"
                steps = [(max(stroke, words[i][1] - STROKE_LEAD_S), v) for i, v in c["steps"]]
                steps[0] = (stroke, steps[0][1])
                hold_end = min(max(steps[-1][0] + 0.7, s_end - 0.1), steps[-1][0] + 1.6)
            elif kind == "compare":
                first_hand = "l" if last_hand == "r" else "r"
                if c.get("second") is None:
                    hand = first_hand
                else:
                    hand, lead = "both", first_hand
                    t2 = words[c["second"]][1] - STROKE_LEAD_S
                    steps = [(max(t2, stroke + 0.35), "second")]
                    hold_end = min(max(steps[0][0] + 0.8, s_end - 0.1), steps[0][0] + 1.7)
            elif kind == "present":
                side = content_side or (1 if _h01(seed, si, "side") < 0.5 else -1)
                hand = "r" if side > 0 else "l"
            elif kind == "thumb":
                hand = "l" if content_side > 0 else "r"
                hold_end = min(hold_end, stroke + 1.1)
            elif kind in ("open", "shrug"):
                lead = "l" if last_hand == "r" else "r"
            g = Gesture(kind, t0, stroke, hold_end, hold_end + RETRACT_S * _far(kind), hand, lead if hand == "both" else hand, steps, side, 0.92 + 0.16 * _h01(seed, si, "amp"), words[c["i"]][0])
            if picked and not _fit(picked[-1], g):
                if kind == "compare" and g.steps:                 # no room for the first half: keep the "other hand" on the contrast word
                    t2 = g.steps[0][0]
                    g = Gesture(kind, t2 - prep, t2, max(t2 + MIN_HOLD_S, min(s_end - 0.1, t2 + MAX_HOLD_S)), 0.0, lead, lead, (), 0, g.amp, words[c["second"]][0])
                    g.t1 = g.hold_end + RETRACT_S
                    hand = lead
                if not _fit(picked[-1], g):
                    if PRIORITY[kind] < PRIORITY[picked[-1].kind] and (len(picked) < 2 or picked[-2].t1 + GAP_S <= g.t0):
                        picked.pop()                              # the more telling gesture wins
                    else:
                        continue
            picked.append(g)
            last_kind = kind
            if hand != "both":
                last_hand = hand
            else:
                last_hand = lead
            break
    # limits: not too many, hands mostly at home
    def busy(gs: List[Gesture]) -> float:
        return sum(g.t1 - g.t0 for g in gs) / max(total, 1e-6)

    if busy(picked) > max_busy:                                   # first let every hold go sooner, down to the shortest hold
        fixed = sum((g.t1 - g.t0) - (g.hold_end - _last_beat(g)) for g in picked)
        holds = sum(g.hold_end - _last_beat(g) for g in picked)
        k = max(0.0, min(1.0, (max_busy * total - fixed) / max(holds, 1e-6)))
        for g in picked:
            cut = (g.hold_end - _last_beat(g)) - max(MIN_HOLD_S, k * (g.hold_end - _last_beat(g)))
            if cut > 0:
                g.hold_end -= cut
                g.t1 -= cut
    while len(picked) > 1 and (len(picked) > max(1, math.ceil(max_per_minute * total / 60.0)) or busy(picked) > max_busy + 0.06):     # holds cannot shrink below MIN_HOLD_S, so a small excess is let through
        j = max(range(len(picked)), key=lambda k: (PRIORITY[picked[k].kind], picked[k].t1 - picked[k].t0))
        picked.pop(j)
    # beats: the most stressed word of a phrase, where the hands are free or holding (never during a preparation, a stroke or a retraction)
    beats: List[Tuple[float, str, float]] = []
    hand = "l" if last_hand == "r" else "r"
    for si, idx in enumerate(sents):
        if len(idx) < 4:
            continue
        ranked = sorted(idx, key=lambda i: -_stress_score(words, i, level))
        took = 0
        for i in ranked:
            if took >= (2 if len(idx) >= 12 else 1):
                break
            tb = words[i][1] - STROKE_LEAD_S * 0.5
            sc = _stress_score(words, i, level)
            if sc < 0.5 or tb < 0.3:
                continue
            if any(abs(tb - b[0]) < BEAT_GAP_S for b in beats):
                continue
            ok = True
            for g in picked:
                if g.t0 - 0.35 < tb < g.stroke + 0.3 or g.hold_end - 0.25 < tb < g.t1 + 0.15 or (g.kind in ("wave", "count", "thumb", "shrug") and g.t0 < tb < g.t1):
                    ok = False
                if any(abs(tb - s[0]) < 0.3 for s in g.steps):
                    ok = False
            if not ok:
                continue
            if _h01(seed, si, i, "beat") < 0.22:              # not every stress gets a beat
                continue
            beats.append((tb, hand, 0.7 + 0.5 * _h01(seed, i, "bs")))
            hand = "l" if hand == "r" else "r"
            took += 1
    beats.sort()
    return picked, beats


# ----------------------------------------------------------------------------- motion (pure functions of time)
def _smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _smoother(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


def _pulse(tau: float, rise: float = 0.13, fall: float = 0.34) -> float:
    """A beat: quick up, slower down, zero outside."""
    if tau <= -rise or tau >= fall:
        return 0.0
    return _smooth((tau + rise) / rise) if tau < 0 else 1.0 - _smoother(tau / fall)


def _reach(g: Gesture, t: float, lag: float = 0.0) -> float:
    """0 at home, 1 on the key pose: slow in and out, a tiny wind-up before leaving, a small overshoot that settles after the stroke."""
    t -= lag
    if t <= g.t0 or t >= g.t1:
        return 0.0
    if t < g.stroke:
        u = (t - g.t0) / max(g.stroke - g.t0, 1e-6)
        return _smoother(u) - 0.04 * math.sin(math.pi * min(1.0, u * 2.6)) ** 2 * (1 - u)
    if t <= g.hold_end:
        tau = t - g.stroke
        return 1.0 + 0.05 * math.exp(-7.0 * tau) * math.sin(13.0 * tau)
    return 1.0 - _smoother((t - g.hold_end) / max(g.t1 - g.hold_end, 1e-6))


def _polar(v: Vec) -> Tuple[float, float]:
    """(angle from straight down, positive outward, in radians; radius)."""
    return math.atan2(v[0], -v[1]), math.hypot(v[0], v[1])


def _from_polar(a: float, r: float) -> Vec:
    return (r * math.sin(a), -r * math.cos(a))


def _arc(rest: Vec, key: Vec, e: float) -> Vec:
    """The wrist path between home and a key pose: an arc about the shoulder (angle and radius are blended, not x and y), pulled a little toward the body mid-way,
    the way a forearm folds while the arm lifts."""
    a0, r0 = _polar(rest)
    a1, r1 = _polar(key)
    a = a0 + (a1 - a0) * e
    tuck = 0.08 + 0.30 * min(1.0, abs(a1 - a0) / 2.4)             # the further round the hand goes, the more the arm folds on the way (a raised hand passes close to the body)
    r = (r0 + (r1 - r0) * e) * (1.0 - tuck * math.sin(math.pi * min(1.0, max(0.0, e))) ** 1.5)
    return _from_polar(a, r)


class Performance:
    """Everything one character does in a shot, as a pure function of time.

      perf = Performance(seed=0.3, content_side=+1)
      perf.speak(words, level=...)                 # one or more stretches of narration by THIS character (plans gestures and beats)
      perf.listen(t0, t1, toward=-1, nods=[...])   # another character speaks on that side
      perf.enter(t0, from_side=-1) / perf.leave(t0, to_side=+1) / perf.side_step(t0, dx_units)
      pose, extra = perf.pose(t, geom)             # extra: {"x": sideways offset in units, "alpha": 0..1}
    """

    def __init__(self, seed: float = 0.0, content_side: int = 0, energy: float = 1.0, tail: bool = False, lift: float = 0.0):
        self.seed, self.content_side, self.energy, self.tail = seed, content_side, energy, tail
        self.lift = lift                                     # low gestures are made this much higher (share of the arm length): for waist-up framing
        self.gestures: List[Gesture] = []
        self.beats: List[Tuple[float, str, float]] = []
        self.nods: List[Tuple[float, float]] = []            # (time, strength)
        self.talk: List[Tuple[float, float]] = []            # (start, end) of this character's speech
        self.listening: List[Tuple[float, float, float]] = []
        self.mouths: List[Tuple[float, float, Sequence[str]]] = []   # (start, fps, shapes per frame)
        self.moves: List[Tuple[str, float, float, float]] = []      # ("enter" | "leave" | "step", t0, amount in units, duration)
        self._shift: Optional[List[Tuple[float, float]]] = None
        self._gaze: Optional[List[Tuple[float, float, float]]] = None

    # --- script
    def speak(self, words: Sequence[Word], level: Optional[Sequence[float]] = None, end: Optional[float] = None) -> None:
        if not words:
            return
        gs, beats = plan_gestures(words, self.seed + 0.01 * len(self.talk), self.content_side, level, end)
        # a later stretch of speech never cuts into an earlier gesture
        gs = [g for g in gs if all(g.t0 >= o.t1 + GAP_S or g.t1 + GAP_S <= o.t0 for o in self.gestures)]
        self.gestures = sorted(self.gestures + gs, key=lambda g: g.t0)
        self.beats = sorted(self.beats + beats)
        self.talk.append((words[0][1], end if end is not None else words[-1][2]))
        # nods: on the stroke of most gestures and on about half of the other stressed words, never closer than 0.8 s
        cand = sorted([(g.stroke, 1.0) for g in gs if g.kind not in ("wave",)] + [(b[0], 0.7) for b in beats])
        for t, s in cand:
            if (not self.nods or t - self.nods[-1][0] > 0.8) and _h01(self.seed, round(t, 2), "nod") < 0.72:
                self.nods.append((t, s))
        self.nods.sort()

    def gesture(self, kind: str, stroke: float, hold: float = 1.2, hand: Optional[str] = None, side: int = 0) -> None:
        """A gesture asked for by the scene itself (everyone waves at the end): it replaces any planned gesture it would overlap."""
        if kind not in KEY:
            raise ValueError(f"unknown gesture {kind!r}")
        two = kind in ("open", "shrug")
        h = hand or ("both" if two else ("l" if _h01(self.seed, kind, round(stroke, 2)) < 0.5 else "r"))
        t0 = max(0.0, stroke - PREP_S * 1.2)
        g = Gesture(kind, t0, stroke, stroke + hold, stroke + hold + RETRACT_S * _far(kind), h, "r" if h == "both" else h, (), side)
        self.gestures = sorted([o for o in self.gestures if o.t1 + GAP_S <= g.t0 or o.t0 >= g.t1 + GAP_S] + [g], key=lambda x: x.t0)

    def mouth(self, t0: float, fps: float, shapes: Sequence[str]) -> None:
        self.mouths.append((t0, fps, shapes))

    def listen(self, t0: float, t1: float, toward: float, nods: Sequence[float] = ()) -> None:
        self.listening.append((t0, t1, max(-1.0, min(1.0, toward))))
        last = -9.0
        for t in nods:
            if t0 + 0.4 < t < t1 - 0.2 and t - last > 2.2 and _h01(self.seed, round(t, 2), "ln") < 0.6:
                self.nods.append((t + 0.18, 0.55))               # a listener nods a beat AFTER the word
                last = t
        self.nods.sort()

    def enter(self, t0: float, from_side: int = -1, distance: float = 70.0, dur: float = 0.75) -> None:
        self.moves.append(("enter", t0, from_side * distance, dur))

    def leave(self, t0: float, to_side: int = 1, distance: float = 70.0, dur: float = 0.65) -> None:
        self.moves.append(("leave", t0, to_side * distance, dur))  

    def side_step(self, t0: float, dx: float, dur: float = 0.8) -> None:
        self.moves.append(("step", t0, dx, dur))                   

    # --- idle life
    def _shifts(self) -> List[Tuple[float, float]]:
        if self._shift is None:
            out, t, i, cur = [(0.0, 1.6 * (_h01(self.seed, "s0") - 0.5))], 2.5 + 3.0 * _h01(self.seed, "st"), 1, 0.0
            while t < 600.0:
                cur = (2.2 + 1.6 * _h01(self.seed, i, "sa")) * (1 if cur <= 0 else -1)
                out.append((t, cur))
                t += 5.0 + 5.0 * _h01(self.seed, i, "sd")
                i += 1
            self._shift = out
        return self._shift

    def weight(self, t: float) -> float:
        """Sideways pelvis offset in units: the weight moves from one foot to the other every 5 to 10 s, in about a second."""
        s = self._shifts()
        i = bisect.bisect_right([a for a, _ in s], t) - 1
        if i <= 0:
            return s[0][1]
        return s[i - 1][1] + (s[i][1] - s[i - 1][1]) * _smoother((t - s[i][0]) / 1.1)

    def _gazes(self) -> List[Tuple[float, float, float]]:
        if self._gaze is None:
            out, t, i = [(0.0, 0.0, 0.0)], 1.0 + 1.5 * _h01(self.seed, "g0"), 1
            while t < 600.0:
                if _h01(self.seed, i, "gk") < 0.3:                       # a short glance away, then back to the viewer
                    out.append((t, 2.6 * (_h01(self.seed, i, "gx") - 0.5), 1.0 * (_h01(self.seed, i, "gy") - 0.6)))
                    out.append((t + 0.35 + 0.5 * _h01(self.seed, i, "gd"), 0.0, 0.0))
                t += 1.6 + 2.6 * _h01(self.seed, i, "gt")
                i += 1
            self._gaze = out
        return self._gaze

    def blink(self, t: float) -> bool:
        from engine.vector_character import blink_natural       # the same irregular blinks as the first rig

        if blink_natural(t, self.seed):
            return True
        return any(0.0 <= t - (g.t0 + 0.05) < 0.11 and _h01(self.seed, round(g.t0, 2), "gb") < 0.4 for g in self.gestures)   # people often blink as a gesture starts

    def speaking(self, t: float) -> bool:
        return any(a - 0.05 <= t < b + 0.1 for a, b in self.talk)

    # --- hands
    def _hand(self, t: float, s: str, A: float, rest: Vec) -> Tuple[Vec, float, str, float]:
        """-> (wrist target relative to the shoulder in units, wrist turn, shape, how far from home 0..1) for hand "l" or "r"."""
        tgt, wr, shape, away = rest, 0.0, "relaxed", 0.0
        for g in self.gestures:
            if not (g.t0 <= t < g.t1 + TWIN_LAG_S + 0.02):
                continue
            if g.hand != "both" and g.hand != s:
                continue
            lag = 0.0 if (g.hand != "both" or g.lead == s) else TWIN_LAG_S
            key, kw, kshape = KEY["present_low" if (g.kind == "present" and self.content_side == 0) else g.kind]
            amp = g.amp * (0.94 if lag else 1.0)
            e = _reach(g, t, lag)
            if g.kind == "compare" and g.hand == "both":
                t2 = g.steps[0][0]
                if s != g.lead:                                   # the second hand comes up on the contrast word and both leave together
                    g2 = Gesture("compare", t2 - PREP_S, t2, g.hold_end, g.t1, s)
                    e = _reach(g2, t, 0.03)
                else:
                    e *= 1.0 - 0.22 * _smooth((t - t2 + 0.2) / 0.4) # the first hand gives way a little when the second one speaks
            kx, ky = key[0] * A, (key[1] + (self.lift if key[1] < -0.1 else 0.0)) * A
            if g.kind == "wave":
                tau = t - g.stroke
                on = _smooth((tau + 0.15) / 0.3) * _smooth((g.hold_end - t) / 0.35)      # the hand starts to wave as it arrives and stops before it leaves
                kx += 0.085 * A * math.sin(2 * math.pi * 2.3 * tau) * on
                kw += 16.0 * math.sin(2 * math.pi * 2.3 * tau - 0.9) * on
            if g.kind == "count":
                for ts, v in g.steps:
                    if t >= ts - 0.06:
                        kshape = COUNT_SHAPES[max(0, min(2, int(v) - 1))]
                    ky += 0.045 * A * _pulse(t - ts, 0.10, 0.30) * (0.0 if ts == g.stroke else 1.0)    # a small pump as each finger comes up
            ee = min(1.06, e * (0.9 + 0.1 * amp))
            tgt = _arc(rest, (kx, ky), ee)
            wr = kw * min(1.0, max(0.0, e))
            # the hand drags behind the forearm while the arm travels and catches up after it stops
            dt = 0.045
            v = (_reach(g, t - 0.03, lag) - _reach(g, t - 0.03 - dt, lag)) / dt
            wr -= max(-20.0, min(20.0, 7.5 * v))
            late = g.kind in ("count", "thumb")                 # a finger or a thumb shows only when the hand is nearly up: half way it would read as pointing
            shape = kshape if e > ((0.80 if late else 0.30) if t < g.stroke else (0.70 if late else 0.42)) else "relaxed"
            away = min(1.0, max(0.0, e))
        # beats ride on top: at home a small lift of the forearm, during a hold a small drop-and-return of the held hand
        for tb, hb, sb in self.beats:
            if not (-0.2 < t - tb < 0.45):
                continue
            p = _pulse(t - tb) * sb * self.energy
            if away > 0.5:
                tgt = (tgt[0] + 0.012 * A * p, tgt[1] - 0.05 * A * p)
                wr -= 7.0 * p
            elif hb == s:
                b = _arc(rest, (KEY["beat"][0][0] * A, (KEY["beat"][0][1] + self.lift) * A), p * (1.0 - away))
                tgt = (tgt[0] + (b[0] - rest[0]), tgt[1] + (b[1] - rest[1]))
                wr += KEY["beat"][1] * p * (1.0 - away) - 9.0 * (_pulse(t - tb + 0.05) - _pulse(t - tb)) * sb
            else:                                                 # the other hand answers faintly, a little later
                p2 = _pulse(t - tb - 0.09) * sb * 0.3 * (1.0 - away)
                b = _arc(rest, (KEY["beat"][0][0] * A, KEY["beat"][0][1] * A), p2)
                tgt = (tgt[0] + (b[0] - rest[0]), tgt[1] + (b[1] - rest[1]))
        return tgt, wr, shape, away

    # --- everything
    def pose(self, t: float, geom: Any) -> Tuple[Dict[str, Any], Dict[str, float]]:
        from engine.vector_presenter import rest_target

        sd = self.seed
        A = geom.arm
        k = 0.5 - 0.5 * math.cos(2 * math.pi * (t / (3.7 + 0.6 * _h01(sd, "bp")) + _h01(sd, "bo")))          # breath 0..1
        dx = self.weight(t)
        # idle arm sway: the hanging arms swing a hair with the weight shift and the breath, each a little out of step
        rest0 = rest_target(geom)
        hands, wrists, shapes, away = [], [], [], []
        for i, s in enumerate(("l", "r")):
            side = -1 if i == 0 else 1
            sway = 0.010 * A * math.sin(2 * math.pi * t / (5.3 + i) + 3.0 * _h01(sd, s)) + 0.012 * A * side * (self.weight(t - 0.25) / 3.0) + 0.006 * A * k
            rest = (rest0[0] + sway, rest0[1] + 0.008 * A * k)
            tg, wr, sh, aw = self._hand(t, s, A, rest)
            hands.append(tg)
            wrists.append(wr + 2.0 * math.sin(2 * math.pi * t / 4.1 + i) + REST_WRIST * (1.0 - aw))
            shapes.append(sh)
            away.append(aw)
        # gestures colour the body: lean toward the presenting side, shoulders up in a shrug, head tilts
        lean, shrug, tilt, look_x, look_y = -0.28 * dx, 0.0, 0.0, 0.0, 0.0
        for g in self.gestures:
            if not (g.t0 <= t < g.t1):
                continue
            e = min(1.0, max(0.0, _reach(g, t)))
            if g.kind == "present":
                lean += 1.6 * g.side * e
                tilt += 3.0 * g.side * e
                gl = _smooth((t - g.t0) / 0.3) * (1.0 - _smooth((t - g.stroke - 0.55) / 0.35))             # a glance at the content, then back to the viewer
                look_x += 3.2 * g.side * gl
            elif g.kind == "shrug":
                shrug += 3.6 * e
                tilt += (5.0 if g.lead == "r" else -5.0) * e
            elif g.kind == "compare":
                first = -1.0 if g.lead == "l" else 1.0
                if g.hand != "both":
                    first = -1.0 if g.hand == "l" else 1.0
                    tilt += 3.0 * first * e
                else:
                    sw = _smooth((t - g.steps[0][0] + 0.25) / 0.45)
                    tilt += 3.2 * first * e * (1.0 - 2.0 * sw)
                    look_x += 1.6 * first * e * (1.0 - 2.0 * sw)
            elif g.kind == "wave":
                tilt += (4.0 if g.hand == "l" else -4.0) * e
            elif g.kind in ("count", "thumb"):
                tilt += (-2.0 if g.hand == "l" else 2.0) * e
            elif g.kind == "open":
                shrug += 0.8 * e
        nod = 0.0
        for tn, sn in self.nods:
            if -0.25 < t - tn < 0.6:
                nod += sn * _pulse(t - tn, 0.16, 0.42)
        # listening: face the speaker
        for a, b, toward in self.listening:
            w = _smooth((t - a) / 0.5) * (1.0 - _smooth((t - b + 0.1) / 0.5))
            if w > 0:
                tilt += 3.2 * toward * w
                look_x += 3.4 * toward * w
                lean += 0.7 * toward * w
        gz = self._gazes()
        i = bisect.bisect_right([a for a, _, _ in gz], t) - 1
        if i >= 0 and abs(look_x) < 0.5:
            a, gx, gy = gz[i]
            px_, py_ = (gz[i - 1][1], gz[i - 1][2]) if i > 0 else (0.0, 0.0)
            w = _smooth((t - a) / 0.07)                                # a saccade takes two frames
            look_x += px_ + (gx - px_) * w
            look_y += py_ + (gy - py_) * w
        pose: Dict[str, Any] = {
            "dx": dx, "dy": 0.0, "lean": lean, "torso_sy": 1.0 + 0.013 * k, "shrug": shrug,
            "hands": tuple(hands), "wrist": tuple(wrists), "hand_shape": tuple(shapes),
            "head_tilt": tilt + 0.9 * math.sin(2 * math.pi * t / (4.9 + sd) + 6.0 * _h01(sd, "ht")) + 0.25 * dx,
            "head_dy": 1.0 * k - 1.7 * nod, "head_dx": 0.25 * look_x, "head_sy": 1.0 - 0.012 * nod,
            "look": (look_x, look_y - 0.5 * nod), "blink": self.blink(t), "mouth": self._mouth(t),
        }
        if self.tail:
            pose["tail"] = 5.0 * math.sin(2 * math.pi * t / 2.9 + sd) + 3.0 * math.sin(2 * math.pi * t / 1.3) * (1.0 if self.speaking(t) else 0.3) - 4.0 * nod
        extra = {"x": 0.0, "alpha": 1.0}
        feet = [[-geom.stance, 0.0], [geom.stance, 0.0]]
        for kind, t0, amt, dur in self.moves:
            u = (t - t0) / dur
            if kind == "enter":
                if u < 1.0:
                    e = 1.0 - (1.0 - max(0.0, u)) ** 3                  # arrives fast, eases to a stop
                    extra["x"] += amt * (1.0 - e)
                    extra["alpha"] *= _smooth(max(0.0, u) / 0.45)
                    pose["lean"] += -0.055 * amt * (1.0 - max(0.0, u)) ** 2 * (0.0 if u < 0 else 1.0)       # leans into the move, straightens as it stops
                    if u < 0:
                        extra["alpha"] = 0.0
                tau = t - (t0 + dur * 0.8)
                if 0 < tau < 1.2:                                       # settle: a small dip and a counter-lean that die out
                    pose["dy"] += 1.6 * math.exp(-5.0 * tau) * math.sin(9.0 * tau)
                    pose["lean"] += 0.02 * amt * math.exp(-4.5 * tau) * math.sin(8.0 * tau)
            elif kind == "leave" and u > 0:
                e = min(1.0, u) ** 2.4
                extra["x"] += amt * e
                extra["alpha"] *= 1.0 - _smooth((u - 0.45) / 0.55)
                pose["lean"] += 0.05 * amt * min(1.0, u * 2.5) * (1.0 - 0.3 * min(1.0, u))
            elif kind == "step":
                # a side step with planted feet: the leading foot lifts and lands, the weight follows, the other foot closes
                if u <= 0:
                    continue
                lead = 1 if amt > 0 else 0
                a1 = _smoother(min(1.0, u / 0.45))
                a2 = _smoother(min(1.0, max(0.0, (u - 0.5) / 0.5)))
                feet[lead][0] += amt * a1
                feet[lead][1] += 2.6 * math.sin(math.pi * min(1.0, u / 0.45)) if u < 0.45 else 0.0
                feet[1 - lead][0] += amt * a2
                feet[1 - lead][1] += 2.6 * math.sin(math.pi * min(1.0, max(0.0, (u - 0.5) / 0.5))) if 0.5 < u < 1.0 else 0.0
                pose["dx"] += amt * _smoother(min(1.0, max(0.0, (u - 0.12) / 0.75)))
                pose["lean"] += 0.25 * amt * math.sin(math.pi * min(1.0, u)) * 0.5
        pose["feet"] = ((feet[0][0], feet[0][1]), (feet[1][0], feet[1][1]))
        return pose, extra

    def _mouth(self, t: float) -> str:
        for t0, fps, tr in self.mouths:
            i = int((t - t0) * fps)
            if 0 <= i < len(tr):
                return tr[i]
        return "closed"
