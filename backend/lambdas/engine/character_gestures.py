"""Automatic speaker gestures for the standing presenter rig (engine/vector_presenter.py). No model decides anything here: the narration's words and their timings do.

  plan_gestures(words)        text cues + word timings -> a short list of Gesture events (at most one meaningful gesture per sentence, and not on every sentence),
                              plus beat times on stressed words
  Performance(...).pose(t)    a pure function of time: the events, the idle life (breathing, blinks, weight shift, small head moves, eye darts), listening, entering and
                              leaving, turned into one pose dict for Presenter.draw. The same input and seed give the same pose on any machine, in any order of frames.

The rules follow what speaking coaches teach, what gesture research measured and what animators know about arms (sources in docs/PRESENTERS.md "Arms"):
  * rest = arms relaxed at the sides, elbows a little out, never two straight sticks and never the same on both sides for long; a listener may hold its hands
    loosely together in front. Rest is alive (breath, a slow sway, the weight shift) but never fidgets
  * gestures stay in the box between waist and shoulders (only the greeting wave goes higher), elbows near the body, with OPEN hands; nobody points with a finger
  * the stroke of a gesture lands on (a hair before) the word it belongs to, and is then HELD; the preparation starts as much earlier as the arm's way needs
    (Kendon's phases: preparation, stroke, hold, retraction)
  * arms are bone ANGLES (shoulder, elbow, wrist), never wrist targets: the elbow goes out when the forearm swings out, the upper arm leads on the way up and
    follows on the way down, the hand trails the forearm; slow in, slow out, a small overshoot that settles after the stroke
  * the way home is a RETURN: longer than the way up, slowest at the end, a hair past rest and back; never a drop
  * a gesture that follows closely goes straight from the pose the arm is in; the hands rest in between only when there is time to rest
  * two-handed gestures are never mirror images: one hand leads and they hold at different heights
  * where there is no room beside the body (a card, a neighbour) the same gesture is made in front of the chest

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
# Kendon's phases: preparation, stroke, hold, retraction. The times are per gesture because a hand that goes further takes longer: every one keeps the forearm
# under about 300 degrees a second at its fastest (engine/arm_check.py holds the animation to 400).
# PREP and RETRACT are the time the planner RESERVES (the longest an arm may need: a forearm folded right up beside a card). Each arm then takes only what its own
# way asks for (arm_times): it leaves later and is home sooner when the way is short, so the stroke still lands on the word.
PREP = {"wave": 0.94, "count": 0.90, "thumb": 0.90, "open": 0.90, "present": 0.78, "compare": 0.90, "shrug": 0.86, "beat": 0.60}
RETRACT = {"wave": 1.30, "count": 1.25, "thumb": 1.25, "open": 1.25, "present": 1.05, "compare": 1.25, "shrug": 1.20, "beat": 0.70}
PREP_S = 0.60               # the shortest preparation
RETRACT_S = 0.92            # the shortest retraction
LATE_MAX_S = 0.45           # the only late strokes: a gesture on the first word of a shot that fades in over another may land this much after its word
QUIET_MAX_S = 4.0           # a speaker who has not moved a hand for this long gives the most stressed word of the next sentence one open hand
RISE_DPS = 200.0            # degrees a second the forearm averages on the way up (its top speed is about 1.5 times that)
HOME_RAISED_S = 1.10        # the shortest way home of a hand that was up by the shoulder or the head
FALL_DPS = 132.0            # ... and on the way home
MIN_HOLD_S = 0.45
MAX_HOLD_S = 1.9
SEEN_S = 0.28               # a gesture has been seen this long after its stroke: only then may the next one take the arm over
GAP_S = 0.20                # two stretches of speech: the hands rest at least this long between their gestures
BRIDGE_S = 0.90             # the next gesture of the same arm starts sooner than this after the arm would be home: the arm holds and goes straight to it
STROKE_LEAD_S = 0.06        # the stroke lands this much BEFORE the word starts (never after)
MAX_PER_MINUTE = 13.0       # meaningful gestures (beats are counted separately): about one every four or five seconds at most, and not on every sentence
MAX_BUSY = 0.70             # share of the talk during which the hands are away from rest
BEAT_GAP_S = 1.6
TWIN_LAG_S = 0.13           # the second hand of a two-handed gesture follows three frames later (and lands on another pose): no mirror-image flapping
LEAD_S = 0.035              # the upper arm leads the forearm by a frame on the way up and follows it by a frame on the way down
DRAG_K, DRAG_MAX, DRAG_DT = 0.040, 13.0, 0.05     # the hand trails the forearm: degrees per (degree a second), its limit, and the look-back
WAVE_HZ = 2.0
REST_WRIST = -11.0          # at home the hand hangs a little toward the leg, not flared out
REST_CHANGE_S = 2.4         # an arm takes this long to settle from one relaxed pose into another
FOLD_S = 1.05               # hands coming together in front, or apart again
FOLD_MIN_S = 4.2            # a shot shorter than this is too short to bring the hands together and apart again
FOLD_DROP = 38.0            # units below the shoulder: where held hands meet (the navel)
FOLD_FLEX = -10.0

# Arm poses are bone ANGLES in degrees from straight down, positive away from the body: (upper arm, forearm, wrist turn). See vector_presenter.solve "arms".
Arm = Tuple[float, float, float]
# Rest: the arm relaxed at the side, never a straight stick and never the same on both sides for long. The first is the pinned home pose (elbow out, forearm in).
REST_POSES: Tuple[Arm, ...] = ((7.0, -4.0, REST_WRIST), (9.0, -12.0, -7.0), (6.0, -1.0, -12.0), (8.0, -8.0, -9.0))
# Characters that hold their hands loosely together in front while they LISTEN (the others keep them relaxed at the sides). By body: everyone whose hands meet
# over the belly; the fox's forearms are too short (they would cross like an X), so it keeps its arms at its sides.
FOLDERS = frozenset({"ines", "priya", "david", "mateo", "owl", "bear", "cat", "parrot", "turtle"})
# Gestures: the speaker's box between waist and shoulders, elbows near the body, open hands. (lead arm, the other arm of a two-handed gesture, hand shape).
# The two arms of a two-handed gesture are deliberately different.
KEY: Dict[str, Tuple[Arm, Optional[Arm], str]] = {
    "open": ((15.0, 116.0, 8.0), (12.0, 103.0, 5.0), "open"),
    "present": ((34.0, 99.0, 6.0), None, "open"),
    "count": ((24.0, 160.0, -4.0), None, "one"),
    "compare": ((15.0, 112.0, 10.0), (13.0, 123.0, 8.0), "open"),
    "shrug": ((9.0, 97.0, 22.0), (8.0, 104.0, 25.0), "open"),
    "wave": ((46.0, 176.0, 0.0), None, "open"),
    "thumb": ((21.0, 154.0, -6.0), None, "thumb"),
    "beat": ((9.0, 22.0, 4.0), None, "relaxed"),
}
TWO_HANDED = ("open", "shrug", "compare")
COUNT_SHAPES = ("one", "two", "three")
HAND_REACH = 1.15           # a gesture hand is drawn about this much longer than the relaxed one (the rig measures it: Geom.reach)


PALMS = ("open", "shrug", "compare", "present")
RAISED = ("wave", "count", "thumb")
PATH_NEED = 56.0            # units outward of the shoulder the middle of a hand sweeps through on its way up, when the character's sizes are not known (path_need)
SIDE_ROOM = 30.0            # with less room than this beside it a gesture folded up to fit would be "hands up": it is made in front of the body instead
# The same gestures made IN FRONT of the body, for an arm with no room beside it (a wide character between the frame's edge and the card, three in a row):
# the elbow stays at the side and the forearm comes up across the body, the hand in front of the chest. (forearm of the lead arm, of the other arm, wrist turn).
FRONT: Dict[str, Tuple[float, float, float]] = {
    "open": (-112.0, -97.0, -34.0), "shrug": (-104.0, -93.0, -40.0), "compare": (-112.0, -99.0, -34.0), "present": (-100.0, -100.0, -30.0),
    "count": (-124.0, -124.0, -42.0), "thumb": (-120.0, -120.0, -40.0), "wave": (-122.0, -122.0, -34.0),
}


def path_need(geom: Any) -> float:
    """Units outward of the shoulder the middle of the hand passes through on its way up beside the body (forearm level, elbow a little out, the hand trailing)."""
    return PATH_NEED if geom is None else 0.2 * geom.upper + geom.fore + 0.5 * geom.hand + 3.0


def outward(room: Optional[float], clear: Optional[float], geom: Any = None) -> bool:
    """Has this arm the room to gesture beside the body (to swing up there, and to hold a hand there)?"""
    return (clear is None or clear >= path_need(geom)) and (room is None or room >= SIDE_ROOM)


def fit_key(kind: str, lead: bool, geom: Any, room: Optional[float] = None, clear: Optional[float] = None) -> Tuple[List[float], str]:
    """The key pose of a gesture for one arm of one character -> ([upper, fore, flex], shape).
    room   units outward of the shoulder the HELD hand may reach (the card's text, the board, another figure, the frame's edge)
    clear  units the hand may SWEEP through on its way (the same without the frame's edge: a hand may leave the picture for a few frames)
    With room beside the body: the table's pose, the forearm folded up as far as `room` asks; a waving hand goes beside the head, not in front of the face.
    Without (`outward` is False): the same gesture in FRONT of the body: the hand never crosses the card or a neighbour, on its way or held."""
    a, b, shape = KEY[kind]
    up, fo, fl = a if (lead or b is None) else b
    U, F, H = geom.upper, geom.fore, getattr(geom, "reach", geom.hand * HAND_REACH)
    if kind in FRONT and not outward(room, clear, geom):
        f_lead, f_other, fl = FRONT[kind]
        fo = f_lead if lead else f_other
        reach_in = geom.shoulder_x - 3.0                      # the wrist stays on its own side of the body
        tight = min(x for x in (room, clear, 1e9) if x is not None)
        up = 2.0
        chin = getattr(geom, "neck_y", 85.6) - geom.shoulder_y - 8.0      # finger tips stay under the chin: a hand in front of the mouth hides the speaker
        for _ in range(16):                                   # a long forearm: the elbow moves out to keep the wrist on its side; no room for that, or the hand would
            need = F * math.sin(math.radians(-fo)) - reach_in  # reach the face: the forearm comes less far up
            up = 2.0 if need <= U * math.sin(math.radians(2.0)) else math.degrees(math.asin(min(0.95, need / U)))
            top = -U * math.cos(math.radians(up)) - F * math.cos(math.radians(fo)) - H * math.cos(math.radians(fo + fl))
            if U * math.sin(math.radians(up)) <= max(4.0, tight - 3.0) and up <= 24.0 and top <= chin:
                break
            fo += 4.0
        return [up, fo, fl], shape
    if kind == "wave":                                        # the waving hand goes beside the head, not in front of the face
        need = 0.5 * getattr(geom, "head_w", 92.0) + 0.55 * H - geom.shoulder_x
        rest = need - (F + 0.5 * H) * math.sin(math.radians(fo))
        if U * math.sin(math.radians(up)) < rest:
            up = max(up, min(70.0, math.degrees(math.asin(min(0.94, rest / U)))))
    if room is not None:
        def tip(u: float, f: float) -> float:
            return U * math.sin(math.radians(u)) + (F + H) * math.sin(math.radians(min(180.0, f + max(0.0, fl))))

        top = min(172.0, up + 126.0)                          # folded as far as an elbow folds
        if tip(up, fo) > room and fo < top:
            lo, hi = fo, top
            for _ in range(18):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if tip(up, mid) > room else (lo, mid)
            fo = hi
        if tip(up, fo) > room:
            lo, hi = 5.0, up
            for _ in range(18):
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if tip(mid, fo) > room else (mid, hi)
            up = lo
    return [up, fo, fl], shape


def arm_times(kind: str, key: Sequence[float]) -> Tuple[float, float]:
    """(preparation, retraction) seconds for an arm whose key pose is `key`: as long as its forearm's way from rest asks for, inside what the planner reserved."""
    sweep = abs(key[1] - REST_POSES[0][1]) + 10.0
    return (max(min(PREP_S, PREP[kind]), min(PREP[kind], sweep / RISE_DPS)), max(min(RETRACT_S, RETRACT[kind]), min(RETRACT[kind], sweep / FALL_DPS)))


# ----------------------------------------------------------------------------- text cues (EN + ES)
# English and Spanish first (the two languages the apps are in), then the commonest words of the other languages videos are made in (German, French, Portuguese,
# Italian, Dutch): a greeting, a goodbye, a contrast, "look", praise and emphasis. A language without words here still gets "?" and "!" and the stressed words.
_GREET = {"hello", "hi", "hey", "welcome", "hola", "bienvenido", "bienvenida", "bienvenidos", "bienvenidas", "buenas", "buenos",
          "hallo", "willkommen", "servus", "moin", "bonjour", "salut", "bienvenue", "olá", "ola", "oi", "ciao", "buongiorno", "benvenuti", "benvenuto", "hoi", "welkom"}
_BYE = {"bye", "goodbye", "thanks", "thank", "adios", "adiós", "gracias", "hasta", "chao",
        "tschüss", "tschüs", "danke", "wiedersehen", "merci", "revoir", "obrigado", "obrigada", "tchau", "adeus", "grazie", "arrivederci", "doei", "dag", "bedankt"}
_ORDINAL = {"first": 1, "firstly": 1, "second": 2, "secondly": 2, "third": 3, "thirdly": 3, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercero": 3, "tercera": 3,
            "erstens": 1, "zweitens": 2, "drittens": 3, "premièrement": 1, "deuxièmement": 2, "troisièmement": 3, "primeiro": 1, "terceiro": 3}
_NUMBER = {"one": 1, "two": 2, "three": 3, "1": 1, "2": 2, "3": 3, "dos": 2, "tres": 3, "zwei": 2, "drei": 3, "deux": 2, "trois": 3, "dois": 2, "três": 3, "due": 2, "tre": 3, "twee": 2, "drie": 3}
_CONTRAST = {"but", "however", "instead", "whereas", "versus", "vs", "yet", "pero", "sino", "aunque",
             "aber", "jedoch", "sondern", "mais", "cependant", "pourtant", "porém", "contudo", "però", "invece", "maar", "echter"}
_CONTRAST_PHRASE = (("on", "the", "other", "hand"), ("sin", "embargo"), ("en", "cambio"), ("por", "otro", "lado"), ("on", "the", "contrary"), ("auf", "der", "anderen", "seite"),
                    ("en", "revanche"), ("par", "contre"), ("por", "outro", "lado"))
_DEICTIC = {"this", "these", "here", "look", "see", "watch", "notice", "aquí", "aqui", "mira", "miren", "observa", "este", "esta", "estos", "estas", "fíjate",
            "hier", "schau", "schaut", "sieh", "seht", "voici", "regarde", "regardez", "ici", "olha", "olhem", "veja", "guarda", "guardate", "ecco", "qui", "kijk"}
_AFFIRM = {"great", "perfect", "exactly", "excellent", "awesome", "genial", "perfecto", "excelente", "exacto", "bravo",
           "genau", "super", "toll", "prima", "richtig", "perfekt", "klasse", "exactement", "parfait", "ótimo", "perfeito", "exatamente", "esatto", "perfetto", "precies", "goed"}
_STRONG = {"very", "really", "important", "key", "never", "always", "must", "every", "everything", "all", "huge", "best", "most", "essential", "remember",
           "muy", "importante", "clave", "nunca", "siempre", "todo", "todos", "mejor", "esencial", "recuerda",
           "sehr", "wichtig", "immer", "niemals", "très", "toujours", "jamais", "muito", "sempre", "molto", "mai", "heel", "altijd", "nooit", "belangrijk"}
_LIST_AND = {"and", "or", "y", "o", "e", "und", "oder", "et", "ou", "en", "of"}
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


def _last_beat(g: Gesture) -> float:
    """The last moment of a gesture that must be seen: its stroke, or its last step (the third finger of a count, the second hand of a comparison); the wave keeps a second."""
    return max([g.stroke + (1.0 if g.kind == "wave" else 0.0)] + [s[0] for s in g.steps])


def _fit(prev: Gesture, g: Gesture) -> bool:
    """May g follow prev? Yes when prev is home BRIDGE_S or more before g starts (the hands rest in between), and yes when g starts once prev has been seen
    (its last beat plus MIN_HOLD_S): the arm then holds prev and goes straight to g, never by way of rest (Performance._link). To get there g may prepare up to a
    quarter faster. False when even that is not enough (nothing is changed then)."""
    seen = _last_beat(prev) + MIN_HOLD_S
    if g.t0 >= seen:
        return True
    if g.stroke - seen < 0.75 * (g.stroke - g.t0):
        return False
    g.t0 = seen
    return True


def busy_share(gs: Sequence[Gesture], total: float) -> float:
    """The share of a talk during which the hands are away from rest: the usual way up and home of each gesture and its hold (not the time reserved for it)."""
    return sum(min(g.stroke - g.t0, PREP_S) + (g.hold_end - g.stroke) + RETRACT_S for g in gs) / max(total, 1e-6)


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


def _candidates(words: Sequence[Word], idx: List[int], first: bool, last: bool, level: Optional[Sequence[float]], latest: Optional[float] = None) -> List[Dict[str, Any]]:
    """Every gesture the sentence could carry: [{kind, i (the word the stroke lands on), ...}]. `latest`: a gesture that may choose its word (a question's shrug,
    emphasis) lands on a word that starts by then, when the sentence has one (the shot ends soon after: the hand must still come home)."""
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
    free = [j for j in range(n) if latest is None or words[idx[j]][1] <= latest] or list(range(n))
    if raw[-1].rstrip("\"')»”").endswith("?") and n >= 3:
        k = max(free, key=lambda j: _stress_score(words, idx[j], level) + (0.2 if j >= n - 2 else 0.0) + 0.15 * j / n)      # a question rises toward its end
        out.append({"kind": "shrug", "i": idx[k]})
    k_d = next((j for j, t in enumerate(toks) if t in _DEICTIC), None)
    if k_d is not None and n >= 3:
        out.append({"kind": "present", "i": idx[k_d]})
    k_a = next((j for j, t in enumerate(toks) if t in _AFFIRM), None)
    if k_a is not None:
        out.append({"kind": "thumb", "i": idx[k_a]})
    k_s = next((j for j, t in enumerate(toks) if t in _STRONG), None)
    if k_s is None and raw[-1].rstrip("\"')»”").endswith("!") and n >= 3:
        k_s = max(free, key=lambda j: _stress_score(words, idx[j], level))
    if k_s is not None and n >= 3:
        out.append({"kind": "open", "i": idx[k_s]})
    return out


def plan_gestures(words: Sequence[Word], seed: float = 0.0, content_side: int = 0, level: Optional[Sequence[float]] = None, end: Optional[float] = None,
                  max_per_minute: float = MAX_PER_MINUTE, max_busy: float = MAX_BUSY, home_by: Optional[float] = None) -> Tuple[List[Gesture], List[Tuple[float, str, float]]]:
    """-> (gestures, beats). words: [(word, start_s, end_s)] of ONE speaker, in order. content_side: -1 / +1 when there is content on the left / right of the speaker (0: none).
    level: optional loudness per word (word_levels). home_by: when the shot ends (hands are home by then: a gesture that may choose its word chooses an earlier one). beats: [(time, hand, strength)] small pulses on stressed words, layered on whatever the hands are doing.
    Deterministic: the same words, seed and options give the same plan."""
    if not words:
        return [], []
    sents = sentences(words)
    total = (end if end is not None else words[-1][2]) - words[0][1]
    picked: List[Gesture] = []
    last_kind = ""
    last_hand = "l" if _h01(seed, "hand") < 0.5 else "r"
    for si, idx in enumerate(sents):
        cands = _candidates(words, idx, si == 0, si == len(sents) - 1, level, None if home_by is None else home_by - RETRACT_S - 0.70)
        cands.sort(key=lambda c: PRIORITY[c["kind"]])
        s_end = words[idx[-1]][2]
        for c in cands:
            kind = c["kind"]
            if kind == last_kind and kind not in ("count",):      # never the same gesture twice in a row (a running count is one idea)
                continue
            if kind == "present" and content_side == 0 and _h01(seed, si, "p") < 0.35:
                continue
            ws = words[c["i"]][1]
            if kind == "open" and _h01(seed, si, "skip") < 0.30:    # emphasis is not underlined every time: a still speaker now and then is the stronger one
                continue
            prep = PREP[kind] * (0.96 + 0.12 * _h01(seed, si, "prep"))
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
                    steps = [(max(t2, stroke + 0.35 + PREP["compare"] * 0.5), "second")]
                    hold_end = min(max(steps[0][0] + 0.8, s_end - 0.1), steps[0][0] + 1.7)
            elif kind == "present":
                side = content_side or (1 if _h01(seed, si, "side") < 0.5 else -1)
                hand = "r" if side > 0 else "l"
            elif kind == "thumb":
                hand = "l" if content_side > 0 else "r"
                hold_end = min(hold_end, stroke + 1.1)
            elif kind in ("open", "shrug"):
                lead = "l" if last_hand == "r" else "r"
            g = Gesture(kind, t0, stroke, hold_end, hold_end + RETRACT[kind], hand, lead if hand == "both" else hand, steps, side, 0.92 + 0.16 * _h01(seed, si, "amp"), words[c["i"]][0])
            if picked and not _fit(picked[-1], g):
                if kind == "compare" and g.steps:                 # no room for the first half: keep the "other hand" on the contrast word
                    t2 = g.steps[0][0]
                    g = Gesture(kind, t2 - prep, t2, max(t2 + MIN_HOLD_S, min(s_end - 0.1, t2 + MAX_HOLD_S)), 0.0, lead, lead, (), 0, g.amp, words[c["second"]][0])
                    g.t1 = g.hold_end + RETRACT[kind]
                    hand = lead
                if not _fit(picked[-1], g):
                    if PRIORITY[kind] < PRIORITY[picked[-1].kind] and (len(picked) < 2 or _last_beat(picked[-2]) + MIN_HOLD_S <= g.t0):
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
        return busy_share(gs, total)

    if busy(picked) > max_busy:                                   # first let every hold go sooner, down to the shortest hold
        fixed = sum(min(g.stroke - g.t0, PREP_S) + (_last_beat(g) - g.stroke) + RETRACT_S for g in picked)
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
    # a speaker is not a statue: where no cue asked for a gesture for QUIET_MAX_S, the most stressed word of a sentence gets ONE open hand (hands in turn)
    hand = "l" if last_hand == "r" else "r"
    for si, idx in enumerate(sents):
        if len(idx) < 5 or len(picked) >= max(1, math.ceil(max_per_minute * total / 60.0)):
            continue
        s0, s1 = words[idx[0]][1], words[idx[-1]][2]
        if any(g.t0 < s1 and g.t1 > s0 for g in picked):
            continue
        head = [j for j in idx[: max(3, int(len(idx) * 0.7))] if home_by is None or words[j][1] <= home_by - RETRACT_S - 0.70] or idx[:3]
        i = max(head, key=lambda j: _stress_score(words, j, level))
        stroke = words[i][1] - STROKE_LEAD_S
        t0 = stroke - PREP["open"]
        hold_end = min(max(stroke + MIN_HOLD_S + 0.25, s1 - 0.15), stroke + 1.5)
        g = Gesture("open", t0, stroke, hold_end, hold_end + RETRACT["open"], hand, hand, (), 0, 0.9, words[i][0])
        before = [x for x in picked if x.stroke < stroke]
        after = [x for x in picked if x.stroke > stroke]
        if t0 < 0.0 or (before and stroke - before[-1].hold_end < QUIET_MAX_S) or (not before and stroke - words[0][1] < 0.5 * QUIET_MAX_S and si == 0 and len(sents) > 1):
            continue
        if after and after[0].t0 < g.t1 + GAP_S:
            continue
        if busy(picked + [g]) > max_busy:
            continue
        picked.append(g)
        picked.sort(key=lambda x: x.t0)
        hand = "l" if hand == "r" else "r"
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
                if g.t0 - 0.45 < tb < g.stroke + 0.4 or g.hold_end - 0.35 < tb < g.t1 + 0.45 or (g.kind in ("wave", "count", "thumb", "shrug") and g.t0 < tb < g.t1):
                    ok = False
                if any(abs(tb - s[0]) < 0.3 for s in g.steps):
                    ok = False
            if not ok:
                continue
            if _h01(seed, si, i, "beat") < 0.40:              # not every stress gets a beat
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


def _pulse(tau: float, rise: float = 0.18, fall: float = 0.40) -> float:
    """A beat: up, slower down, zero outside (smooth at both ends)."""
    if tau <= -rise or tau >= fall:
        return 0.0
    return _smooth((tau + rise) / rise) if tau < 0 else 1.0 - _smoother(tau / fall)


def _trap(u: float, a: float, d: float) -> float:
    """0..1 with a speed that grows evenly over the first `a` of the time, stays, and falls evenly over the last `d`: the lowest top speed for a given time
    (1 / (1 - a/2 - d/2) of the average), where an S-curve would be half as fast again in the middle."""
    u = min(1.0, max(0.0, u))
    v = 1.0 / (1.0 - 0.5 * a - 0.5 * d)
    if u < a:
        return 0.5 * v * u * u / a
    if u <= 1.0 - d:
        return v * (u - 0.5 * a)
    return 1.0 - 0.5 * v * (1.0 - u) ** 2 / d


def _rise(u: float) -> float:
    """Preparation into the stroke: a tiny wind-up the other way (anticipation), then slow in and slow out."""
    u = min(1.0, max(0.0, u))
    return _trap(u, 0.36, 0.34) - 0.03 * math.sin(math.pi * min(1.0, u * 3.0)) ** 2 * (1.0 - u)


def _fall(u: float) -> float:
    """Retraction: leaves gently, travels, and takes longest over the last part (the arm is put down, not let go)."""
    return _trap(u, 0.26, 0.48)


def _soft_max(v: float, lo: float, w: float = 3.0) -> float:
    """max(v, lo) without the corner."""
    x = lo - v
    return v + 0.5 * (x + math.sqrt(x * x + w * w))


def _lerp3(a: Sequence[float], b: Sequence[float], w: Sequence[float]) -> List[float]:
    return [a[i] + (b[i] - a[i]) * w[i] for i in range(3)]


class Performance:
    """Everything one character does in a shot, as a pure function of time.

      perf = Performance(seed=0.3, content_side=+1, who="fox")
      perf.speak(words, level=...)                 # one or more stretches of narration by THIS character (plans gestures and beats)
      perf.listen(t0, t1, toward=-1, nods=[...])   # another character speaks on that side
      perf.enter(t0, from_side=-1) / perf.leave(t0, to_side=+1) / perf.side_step(t0, dx_units)
      pose, extra = perf.pose(t, geom)             # extra: {"x": sideways offset in units, "alpha": 0..1}

    The arms (docs/PRESENTERS.md "Arms") are bone ANGLES, never wrist targets: rest pose -> gesture layers -> beats -> the elbow rule -> joint limits.
      who      the character: its idle life (breath, weight, sway, blinks, the rest pose it drifts between) runs on the VIDEO's clock with a seed of its own, so
               it goes on unbroken across a cut to the next scene; None = the scene's seed (a single clip)
      clock    the video time at which this shot starts
      limit    the shot's length: every gesture is back at rest by then (the next shot starts from the rest pose)
      room     (left, right) free space in units outward from each shoulder to the nearest thing a HELD hand must not cover (the card's text, the board, another
               figure, the frame's edge); None = unlimited. Gesture poses fold the forearm up to stay inside it
      clear    (left, right) the same for a hand on its WAY (without the frame's edge). An arm without the room to swing up beside the body makes its gestures
               in front of the body; a wave, a count or a thumb goes to the other hand when that one has the room (fit_key, _place)
      fold     (at the start, at the end): a listener that holds its hands together already when the shot starts / still when it ends
      quiet    seconds at the start of the shot during which no gesture begins (the crossfade from the shot before)
    """

    def __init__(self, seed: float = 0.0, content_side: int = 0, energy: float = 1.0, tail: bool = False, lift: float = 0.0, who: Optional[str] = None,
                 clock: float = 0.0, limit: Optional[float] = None, room: Optional[Tuple[Optional[float], Optional[float]]] = None,
                 clear: Optional[Tuple[Optional[float], Optional[float]]] = None, fold: Tuple[bool, bool] = (False, False), quiet: float = 0.0, geom: Any = None):
        self.seed, self.content_side, self.energy, self.tail = seed, content_side, energy, tail
        self.lift = lift                                     # waist-up framing: a beat at rest is made this much higher so that it shows above the frame's edge
        self.who, self.clock, self.limit, self.room, self.fold = who, float(clock), limit, room or (None, None), fold
        self.clear = clear or self.room
        self.geom = geom                                     # the character's sizes, when the caller knows them (how much room its arms need)
        self.quiet = quiet                                   # no gesture starts before this (the crossfade from the shot before: two pictures of one arm)
        self.life = _h01("life", who) if who else seed       # the seed of everything that must not change at a cut
        self.gestures: List[Gesture] = []
        self.beats: List[Tuple[float, str, float]] = []
        self.nods: List[Tuple[float, float]] = []            # (time, strength)
        self.talk: List[Tuple[float, float]] = []            # (start, end) of this character's speech
        self.listening: List[Tuple[float, float, float]] = []
        self.mouths: List[Tuple[float, float, Sequence[str]]] = []   # (start, fps, shapes per frame)
        self.moves: List[Tuple[str, float, float, float]] = []      # ("enter" | "leave" | "step", t0, amount in units, duration)
        self._shift: Optional[List[Tuple[float, float]]] = None
        self._gaze: Optional[List[Tuple[float, float, float]]] = None
        self._rest: Optional[List[List[Tuple[float, int]]]] = None
        self._falls: Optional[Dict[Tuple[int, str], Tuple[float, float]]] = None
        self._keys: Dict[Any, Any] = {}

    # --- script
    def speak(self, words: Sequence[Word], level: Optional[Sequence[float]] = None, end: Optional[float] = None) -> None:
        if not words:
            return
        gs, beats = plan_gestures(words, self.seed + 0.01 * len(self.talk), self.content_side, level, end, home_by=self.limit)
        if self.limit is not None:                           # the shot ends: hands are home by then, or the gesture is not made
            kept = []
            for g in gs:                                     # (the time RESERVED for the way home may run past the end: the shortest way home may not)
                over = g.hold_end + (RETRACT_S if g.kind in PALMS else HOME_RAISED_S) + (TWIN_LAG_S + 0.12 if g.hand == "both" else 0.0) - (self.limit - 0.04)
                if over > 0:
                    if g.hold_end - over < _last_beat(g) + 0.30:
                        continue
                    g.hold_end -= over
                g.t1 = min(g.t1, self.limit - 0.04)
                kept.append(g)
            gs = kept
            beats = [b for b in beats if b[0] < self.limit - 0.7]
        for g in gs:
            self._place(g)
        if self.quiet > 0.0:                                 # the shot fades in over the one before: an arm already on its way would show twice.
            kept: List[Gesture] = []                         # A gesture on the line's first word (a reaction: "Exactly!") is made a moment later instead
            for k, g in enumerate(gs):
                d = self.quiet - g.t0
                if d > 0.0:
                    nxt = gs[k + 1] if k + 1 < len(gs) else None
                    if d > LATE_MAX_S or (nxt is not None and nxt.t0 < _last_beat(g) + d + MIN_HOLD_S) or (self.limit is not None and g.t1 + d > self.limit - 0.04):
                        continue
                    g.t0, g.stroke, g.hold_end, g.t1 = g.t0 + d, g.stroke + d, g.hold_end + d, g.t1 + d
                    g.steps = tuple((ts + d, v) for ts, v in g.steps)
                kept.append(g)
            gs = kept
            beats = [b for b in beats if b[0] > self.quiet + 0.3]
        # a later stretch of speech never cuts into an earlier gesture
        gs = [g for g in gs if all(g.t0 >= o.t1 + GAP_S or g.t1 + GAP_S <= o.t0 for o in self.gestures)]
        self.gestures = sorted(self.gestures + gs, key=lambda g: g.t0)
        self._falls = None
        self.beats = sorted(self.beats + beats)
        self.talk.append((words[0][1], end if end is not None else words[-1][2]))
        # nods: on the stroke of most gestures and on about half of the other stressed words, never closer than 0.8 s
        cand = sorted([(g.stroke, 1.0) for g in gs if g.kind not in ("wave",)] + [(b[0], 0.7) for b in beats])
        for t, s in cand:
            if (not self.nods or t - self.nods[-1][0] > 0.8) and _h01(self.seed, round(t, 2), "nod") < 0.72:
                self.nods.append((t, s))
        self.nods.sort()

    def _place(self, g: Gesture) -> bool:
        """A raised one-handed gesture is given to the hand that has the room to go up beside the body (the other one when the planned hand has none)."""
        if g.kind not in RAISED or g.hand == "both":
            return True
        ok = {s: outward(self.room[i], self.clear[i], self.geom) for i, s in enumerate(("l", "r"))}
        if not ok[g.hand]:
            other = "r" if g.hand == "l" else "l"
            if ok[other]:
                g.hand = g.lead = other                      # (neither has: it is made in front of the chest, with the planned hand)
        return True

    def gesture(self, kind: str, stroke: float, hold: float = 1.2, hand: Optional[str] = None, side: int = 0) -> None:
        """A gesture asked for by the scene itself (everyone waves at the end). It may follow another closely or cut into its hold: the arm then goes from the
        pose it is in straight to the new one (never by way of rest). It only waits until the gesture before it has been seen (its stroke plus SEEN_S)."""
        if kind not in KEY:
            raise ValueError(f"unknown gesture {kind!r}")
        two = kind in TWO_HANDED
        h = hand or ("both" if two else ("l" if _h01(self.seed, kind, round(stroke, 2)) < 0.5 else "r"))
        if kind == "present" and side:
            h = "r" if side > 0 else "l"
        prep = PREP[kind]
        for o in self.gestures:                               # the one before must have landed and been seen
            if o.t0 <= stroke - prep < o.stroke + SEEN_S and (o.hand == "both" or h == "both" or o.hand == h):
                stroke = o.stroke + SEEN_S + prep
        t0 = max(0.0, stroke - prep)
        g = Gesture(kind, t0, stroke, stroke + hold, stroke + hold + RETRACT[kind], h, "r" if h == "both" else h, (), side)
        self._place(g)
        self.gestures = sorted([o for o in self.gestures if not (o.t0 >= g.t0 and o.t0 < g.t1)] + [g], key=lambda x: x.t0)
        self._falls = None

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

    # --- idle life (on the video's clock: T = clock + t)
    def _shifts(self) -> List[Tuple[float, float]]:
        if self._shift is None:
            sd = self.life
            out, t, i, cur = [(0.0, 1.6 * (_h01(sd, "s0") - 0.5))], 2.5 + 3.0 * _h01(sd, "st"), 1, 0.0
            while t < 900.0:
                cur = (2.2 + 1.6 * _h01(sd, i, "sa")) * (1 if cur <= 0 else -1)
                out.append((t, cur))
                t += 5.0 + 5.0 * _h01(sd, i, "sd")
                i += 1
            self._shift = out
        return self._shift

    def weight(self, T: float) -> float:
        """Sideways pelvis offset in units at video time T: the weight moves from one foot to the other every 5 to 10 s, in about a second."""
        s = self._shifts()
        i = bisect.bisect_right([a for a, _ in s], T) - 1
        if i <= 0:
            return s[0][1]
        return s[i - 1][1] + (s[i][1] - s[i - 1][1]) * _smoother((T - s[i][0]) / 1.1)

    def _gazes(self) -> List[Tuple[float, float, float]]:
        if self._gaze is None:
            sd = self.life
            out, t, i = [(0.0, 0.0, 0.0)], 1.0 + 1.5 * _h01(sd, "g0"), 1
            while t < 900.0:
                if _h01(sd, i, "gk") < 0.3:                       # a short glance away, then back to the viewer
                    out.append((t, 2.6 * (_h01(sd, i, "gx") - 0.5), 1.0 * (_h01(sd, i, "gy") - 0.6)))
                    out.append((t + 0.35 + 0.5 * _h01(sd, i, "gd"), 0.0, 0.0))
                t += 1.6 + 2.6 * _h01(sd, i, "gt")
                i += 1
            self._gaze = out
        return self._gaze

    def blink(self, t: float) -> bool:
        from engine.vector_character import blink_natural       # the same irregular blinks as the first rig

        if blink_natural(self.clock + t, self.life):
            return True
        return any(0.0 <= t - (g.t0 + 0.05) < 0.11 and _h01(self.seed, round(g.t0, 2), "gb") < 0.4 for g in self.gestures)   # people often blink as a gesture starts

    def speaking(self, t: float) -> bool:
        return any(a - 0.05 <= t < b + 0.1 for a, b in self.talk)

    # --- rest
    def _rests(self) -> List[List[Tuple[float, int]]]:
        """Per arm: [(video time, index into REST_POSES)]. Each arm settles into another relaxed pose every 8 to 16 s, the two arms at different moments."""
        if self._rest is None:
            out = []
            for s in ("l", "r"):
                seq, t, i = [(-1e9, int(_h01(self.life, s, "r0") * len(REST_POSES)))], 3.0 + 9.0 * _h01(self.life, s, "rt"), 1
                while t < 900.0:
                    nxt = int(_h01(self.life, s, i, "rk") * len(REST_POSES))
                    if nxt == seq[-1][1]:
                        nxt = (nxt + 1) % len(REST_POSES)
                    seq.append((t, nxt))
                    t += 8.0 + 8.0 * _h01(self.life, s, i, "rd")
                    i += 1
                out.append(seq)
            self._rest = out
        return self._rest

    def folded(self, t: float, i: int = 0) -> float:
        """0..1: how far this (listening) character has its hands together in front at shot time t (arm i moves a little after the other)."""
        if self.who not in FOLDERS or self.talk or self.gestures:
            return 0.0
        a0, a1 = self.fold
        if a0 and a1:
            return 1.0
        end = self.limit if self.limit is not None else (self.listening[-1][1] + 0.6 if self.listening else 0.0)
        if (not self.listening and not a0) or (end < FOLD_MIN_S and not a0):
            return 0.0
        lag = 0.22 * i if _h01(self.life, "fl") < 0.5 else 0.22 * (1 - i)
        t_in = (1.25 if any(m[0] == "enter" for m in self.moves) else 0.45) + 0.5 * _h01(self.seed, "fi")
        up = 1.0 if a0 else _smoother((t - t_in - lag) / FOLD_S)
        down = 1.0 if a1 else 1.0 - _smoother((t - (end - FOLD_S - 0.30) - lag) / FOLD_S)
        return up * down

    def _rest_arm(self, t: float, i: int, geom: Any) -> List[float]:
        """The arm's rest pose at shot time t: the relaxed pose of the moment, alive (breath, a slow sway, the weight shift), or the hands held together."""
        T = self.clock + t
        seq = self._rests()[i]
        j = bisect.bisect_right([a for a, _ in seq], T) - 1
        cur = REST_POSES[seq[j][1]]
        if j > 0:
            w = _smoother((T - seq[j][0]) / REST_CHANGE_S)
            cur = [a + (b - a) * w for a, b in zip(REST_POSES[seq[j - 1][1]], cur)]
        up, fo, fl = cur
        sd, side = self.life, (-1 if i == 0 else 1)
        k = 0.5 - 0.5 * math.cos(2 * math.pi * (T / (3.7 + 0.6 * _h01(sd, "bp")) + _h01(sd, "bo")))
        calm = 1.0
        f = self.folded(t, i)
        if f > 0.0:
            ku, kf = self._key_fold(geom, i)
            up, fo, fl = up + (ku - up) * f, fo + (kf - fo) * f, fl + (FOLD_FLEX - fl) * f
            calm = 1.0 - 0.30 * f                             # hands that hold each other move together, and little
        sway = 1.8 * math.sin(2 * math.pi * T / (5.3 + 1.1 * i) + 6.28 * _h01(sd, i, "sw")) + 0.5 * math.sin(2 * math.pi * T / (3.1 + 0.4 * i) + 6.28 * _h01(sd, i, "sx"))
        pend = 0.40 * side * self.weight(T - 0.28)            # the hanging arm swings a hair behind the weight shift
        fo += calm * (sway + pend) + 0.5 * k
        up += calm * (0.7 * math.sin(2 * math.pi * T / (6.7 + i) + 6.28 * _h01(sd, i, "su")) + 0.25 * pend) + 0.35 * k
        fl += 1.6 * math.sin(2 * math.pi * T / 4.1 + i)
        return [up, fo, fl]

    def _key_fold(self, geom: Any, i: int) -> Tuple[float, float]:
        """Hands loosely together in front of the navel (as far in as the arms reach): elbows out, forearms in, one hand a little above the other."""
        key = ("fold", id(geom), i)
        if key not in self._keys:
            from engine.vector_presenter import reach_angles

            top = i == (0 if _h01(self.life, "ft") < 0.5 else 1)
            x = -(geom.shoulder_x - (2.0 + 0.20 * geom.hand))
            up, fo = reach_angles(geom, (x, -(FOLD_DROP + (0.0 if top else 4.0))), -1)
            if up < 1.0:                                      # long arms: the elbow stays at the side and the hands meet lower
                up, fo = 1.0, math.degrees(math.asin(max(-1.0, min(0.0, (x - geom.upper * math.sin(math.radians(1.0))) / geom.fore)))) - (0.0 if top else 5.0)
            self._keys[key] = (up, fo)
        return self._keys[key]

    # --- gestures
    def _takes_part(self, g: Gesture, s: str) -> bool:
        """Does arm s make gesture g? A two-handed gesture needs room beside the body for both hands: where only one arm has it, that arm makes the gesture alone;
        where neither has, the leading hand makes it in front of the chest and the other stays at rest (two hands crossed on the chest say something else)."""
        if g.hand != "both":
            return g.hand == s
        i = 0 if s == "l" else 1
        mine, other = outward(self.room[i], self.clear[i], self.geom), outward(self.room[1 - i], self.clear[1 - i], self.geom)
        return mine or (not other and g.lead == s)

    def _arm_key(self, g: Gesture, s: str, geom: Any) -> Tuple[List[float], str, float, float]:
        """(key pose, hand shape, preparation, retraction) of arm s in gesture g for this character, in this place."""
        lead = g.hand != "both" or g.lead == s
        ck = (g.kind, lead, s, id(geom))
        if ck not in self._keys:
            i = 0 if s == "l" else 1
            key, shape = fit_key(g.kind, lead, self.geom or geom, self.room[i], self.clear[i])
            self._keys[ck] = (key, shape) + arm_times(g.kind, key)
        return self._keys[ck]

    @staticmethod
    def _arm_stroke(g: Gesture, s: str) -> float:
        if g.kind == "compare" and g.hand == "both" and s != g.lead and g.steps:       # the second hand comes up on the contrast word
            return g.steps[0][0]
        return g.stroke + (TWIN_LAG_S if (g.hand == "both" and g.lead != s) else 0.0)

    def _link(self) -> Dict[Tuple[int, str], Tuple[float, float]]:
        """When each arm of each gesture stops holding: (start, None) = at the end of its hold, the arm then goes home in its own time; (start, end) = the NEXT
        gesture of the same arm begins before this one would be home (or less than BRIDGE_S after): the arm holds until that one has taken over and this one
        lets go underneath it, so the arm never visits rest in between."""
        if self._falls is None:
            falls: Dict[Tuple[int, str], Tuple[float, float]] = {}
            gs = self.gestures
            for a, g in enumerate(gs):
                for s in ("l", "r"):
                    if not self._takes_part(g, s):
                        continue
                    lag = TWIN_LAG_S + 0.12 if (g.hand == "both" and g.lead != s) else 0.0      # the second hand also lets go later: the two do not come down as a pair
                    falls[(id(g), s)] = (g.hold_end + lag, None)
                    for h in gs[a + 1:]:
                        if self._takes_part(h, s):
                            st = self._arm_stroke(h, s)                        # when THIS arm of the next gesture lands (the second hand of a comparison comes later)
                            if st - PREP[h.kind] < g.t1 + BRIDGE_S:
                                falls[(id(g), s)] = (st + 0.02, st + 0.30)
                            break
            self._falls = falls
        return self._falls

    def _weight(self, g: Gesture, s: str, t: float, geom: Any) -> float:
        """How much of gesture g arm s shows at t: 0 at rest (or under the next gesture), 1 on the key pose, a little over 1 as it lands (overshoot, settles),
        a little under 0 as it comes home (the arm swings a hair past rest and back)."""
        lag = TWIN_LAG_S if (g.hand == "both" and g.lead != s) else 0.0
        _, _, prep, retract = self._arm_key(g, s, geom)
        st = self._arm_stroke(g, s)
        t0 = max(g.t0, st - prep)
        if t <= t0:
            return 0.0
        fs, fe = self._link()[(id(g), s)]
        if fe is None:
            fe = fs + min(retract, max(0.78, g.t1 - fs))
        if t < st:
            return _rise((t - t0) / max(st - t0, 1e-6))
        if t <= fs:
            tau = t - st
            return 1.0 + 0.045 * math.exp(-6.0 * tau) * (1.0 - math.cos(14.0 * tau))
        if t < fe:
            return 1.0 - _fall((t - fs) / max(fe - fs, 1e-6))
        tau = t - fe
        return -0.022 * math.exp(-5.0 * tau) * (1.0 - math.cos(10.0 * tau)) if tau < 1.4 else 0.0

    def _key(self, g: Gesture, s: str, t: float, geom: Any) -> Tuple[List[float], str]:
        """The key pose of gesture g for arm s at t (most are still; the wave waves, a count pumps, a comparison gives way) and its hand shape."""
        lead = g.hand != "both" or g.lead == s
        (up, fo, fl), shape, _, _ = self._arm_key(g, s, geom)
        tau = t - g.stroke
        if g.kind == "wave":
            on = _smooth((tau + 0.10) / 0.45) * _smooth((g.hold_end - t) / 0.45)        # the hand starts to wave as it arrives and stops before it leaves
            front = fo < 0.0                                                             # a wave in front of the chest is made with the hand, the forearm hardly moves
            fo += (4.0 if front else 10.0) * math.sin(2 * math.pi * WAVE_HZ * tau) * on
            fl += (11.0 if front else 9.0) * math.sin(2 * math.pi * WAVE_HZ * tau - 0.9) * on
        elif g.kind == "count":
            if g.steps:                                                                  # the hand comes up already showing its number ("second": two fingers, never one first)
                shape = COUNT_SHAPES[max(0, min(2, int(g.steps[0][1]) - 1))]
            for ts, v in g.steps:
                if t >= ts - 0.06:
                    shape = COUNT_SHAPES[max(0, min(2, int(v) - 1))]
                if ts != g.stroke:
                    fo -= 6.0 * _pulse(t - ts, 0.16, 0.36)                               # a small pump as each finger comes up
        elif g.kind == "compare" and g.hand == "both" and g.steps and lead:
            give = _smooth((t - g.steps[0][0] + 0.25) / 0.6)                              # the first hand gives way a little when the second one speaks
            fo -= 12.0 * give
            up -= 2.0 * give
        # a moving hold: the held hand is never frozen
        drift = _smooth(tau / 0.8)
        fo += drift * 1.4 * math.sin(2 * math.pi * (t / 2.3) + (0.0 if s == "l" else 1.9))
        fl += drift * 1.5 * math.sin(2 * math.pi * (t / 1.9) + (0.7 if s == "l" else 0.0))
        return [up, fo, fl], shape

    def _arm_raw(self, t: float, i: int, geom: Any) -> Tuple[List[float], str, float]:
        """-> ([upper, fore, flex], hand shape, how far from rest 0..1) before the wrist drag and the elbow rule."""
        s = "l" if i == 0 else "r"
        pose = self._rest_arm(t, i, geom)
        shape, away = "relaxed", 0.0
        for g in self.gestures:
            if t <= g.t0 or t > g.t1 + 2.0 or not self._takes_part(g, s):
                continue
            w = self._weight(g, s, t, geom)
            if w == 0.0:
                continue
            key, kshape = self._key(g, s, t, geom)
            fs = self._link()[(id(g), s)][0]
            wu = self._weight(g, s, t + LEAD_S * (1.0 - 2.0 * _smooth((t - g.stroke - 0.1) / max(0.25, fs - g.stroke - 0.2))), geom)     # the upper arm starts first on the way up and arrives last on the way down
            pose = _lerp3(pose, key, (wu, w, w))
            wc = min(1.0, max(0.0, w))
            late = g.kind in ("count", "thumb")                 # a finger or a thumb shows only when the hand is nearly up: half way it would read as pointing
            if wc > ((0.86 if late else 0.35) if t < g.stroke else (0.84 if late else 0.45)):
                shape = kshape
            elif wc > 0.5:
                shape = "relaxed"
            away = max(away * (1.0 - wc), wc)
        for tb, hb, sb in self.beats:
            if not (-0.25 < t - tb < 0.5):
                continue
            p = _pulse(t - tb) * sb * self.energy
            if away > 0.5:                                        # during a hold: the held hand dips and returns
                pose[1] -= 5.5 * p
                pose[2] -= 5.0 * p
            elif hb == s:                                         # at rest: the forearm lifts a little, elbow with it
                k = p * (1.0 - away)
                pose[0] += 3.5 * k
                pose[1] += (13.0 + 30.0 * self.lift) * k
                pose[2] += 6.0 * k
            else:                                                 # the other hand answers faintly, a little later
                p2 = _pulse(t - tb - 0.09) * sb * 0.3 * (1.0 - away)
                pose[1] += 5.0 * p2
        return pose, shape, away

    def arm(self, t: float, i: int, geom: Any) -> Tuple[float, float, float, str, float]:
        """-> (upper, fore, flex, hand shape, away) of arm i (0 = left of the picture) at shot time t. The hand drags behind the forearm while it travels and
        catches up after it stops; the elbow moves out when the forearm swings out (vector_presenter.elbow_need)."""
        from engine.vector_presenter import elbow_need

        (up, fo, fl), shape, away = self._arm_raw(t, i, geom)
        if away > 0.0 or self.gestures or self.beats:
            (_, fo0, _), _, _ = self._arm_raw(t - DRAG_DT, i, geom)
            v = (fo - fo0) / DRAG_DT
            fl -= DRAG_MAX * math.tanh(DRAG_K * v / DRAG_MAX)
        up = _soft_max(up, elbow_need(fo))
        return up, fo, fl, shape, away

    # --- everything
    def pose(self, t: float, geom: Any) -> Tuple[Dict[str, Any], Dict[str, float]]:
        sd = self.life
        T = self.clock + t
        k = 0.5 - 0.5 * math.cos(2 * math.pi * (T / (3.7 + 0.6 * _h01(sd, "bp")) + _h01(sd, "bo")))          # breath 0..1
        dx = self.weight(T)
        arms, wrists, shapes = [], [], []
        for i in (0, 1):
            up, fo, fl, sh, _aw = self.arm(t, i, geom)
            arms.append((up, fo))
            wrists.append(fl)
            shapes.append(sh)
        # gestures colour the body: lean toward the presenting side, shoulders up in a shrug, head tilts
        lean, shrug, tilt, look_x, look_y = -0.28 * dx, 0.0, 0.0, 0.0, 0.0
        for g in self.gestures:
            if not (g.t0 <= t < g.t1 + 0.4):
                continue
            ls = g.lead if g.hand == "both" else g.hand
            if not self._takes_part(g, ls):
                ls = "r" if ls == "l" else "l"
            e = min(1.0, max(0.0, self._weight(g, ls, t, geom))) if t < g.hold_end else 1.0 - _fall((t - g.hold_end) / max(g.t1 - g.hold_end, 1e-6))
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
                if g.hand != "both" or not g.steps:
                    first = -1.0 if ls == "l" else 1.0
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
        i = bisect.bisect_right([a for a, _, _ in gz], T) - 1
        if i >= 0 and abs(look_x) < 0.5:
            a, gx, gy = gz[i]
            px_, py_ = (gz[i - 1][1], gz[i - 1][2]) if i > 0 else (0.0, 0.0)
            w = _smooth((T - a) / 0.07)                                # a saccade takes two frames
            look_x += px_ + (gx - px_) * w
            look_y += py_ + (gy - py_) * w
        pose: Dict[str, Any] = {
            "dx": dx, "dy": 0.0, "lean": lean, "torso_sy": 1.0 + 0.013 * k, "shrug": shrug,
            "arms": tuple(arms), "wrist": tuple(wrists), "hand_shape": tuple(shapes),
            "head_tilt": tilt + 0.9 * math.sin(2 * math.pi * T / (4.9 + sd) + 6.0 * _h01(sd, "ht")) + 0.25 * dx,
            "head_dy": 1.0 * k - 1.7 * nod, "head_dx": 0.25 * look_x, "head_sy": 1.0 - 0.012 * nod,
            "look": (look_x, look_y - 0.5 * nod), "blink": self.blink(t), "mouth": self._mouth(t),
        }
        if self.tail:
            pose["tail"] = 5.0 * math.sin(2 * math.pi * T / 2.9 + sd) + 3.0 * math.sin(2 * math.pi * T / 1.3) * (1.0 if self.speaking(t) else 0.3) - 4.0 * nod
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
