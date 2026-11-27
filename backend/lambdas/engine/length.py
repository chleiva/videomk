"""The length of a video is kept by arithmetic, not by hoping the writer counts words (owner rule: a video is AT LEAST as long as asked and may run a few
seconds over, never short; measured on QA 2026-11-27: a 60 s request came out at 69 s, a 30 s one at 38 s).

Three deterministic steps, in the order they run:
  1. `fit_script` (before any voice is made, in the director): the speaking time of the script is ESTIMATED from its text with the measured rate of the voice
     (characters, punctuation and digits predict Polly's speech to about 5 percent per video; words alone to about 8). A script that would run past the length
     asked is cut: whole sentences first (never the opening line or the last line, never a beat left with too few words), then a whole middle beat when the
     writer delivered more beats than the length has room for. Nothing is ever added here.
  2. `tighten` (in the timeline, with the MEASURED audio): if the video would still run past the window, the silences around every spoken beat (0.40 s before,
     0.55 s after) are shortened evenly, down to a floor. The pace found is stored in the plan (`plan["pace"]`) so an edit keeps it.
  3. `timeline.stretch_to` (already there): if the video would be shorter than asked, scenes are held a little longer: every spoken scene by the same amount,
     never one long freeze on the last scene.
  0. `extend_script` (before step 1, since 2026-11-27): a script estimated so short that step 3 would have to hold every scene longer than a moment is sent back
     to the writer once to be lengthened, its existing sentences kept. The one step with a model call; it exists because a video is never shorter than asked,
     and a video that reaches its length by standing still is not what was asked for either.
The window is [asked, asked + 5 percent]: steps 1 and 2 aim inside it, step 3 guarantees its lower edge.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

# seconds of generative Polly speech per character, per punctuation mark (a pause) and per digit (a number is spoken long): least-squares fits on the beats of
# 174 finished QA videos (Amy 1032 beats, Ruth 293, Lucia 414, Lupe 18). Mean error of the estimate per video: +1 percent, standard deviation 3 to 5 percent.
RATES: Dict[str, Tuple[float, float, float]] = {
    "Amy": (0.0558, 0.309, 0.23), "Ruth": (0.0547, 0.351, 0.16), "Lucia": (0.0495, 0.378, 0.14), "Lupe": (0.0570, 0.311, 0.14),
    # The default voice of each newer language (2026-11-27): the English shape scaled to what the voice really took for an explainer passage of about 70 words
    # and, where a QA video exists, its four finished beats (fr, de, it, pt, pl: 51 to 58 s of speech each; nl, fi: the passage alone, 23 and 24 s). Before, one
    # sentence a voice: the estimate was 4 percent long for Léa and 6 to 8 percent short for Vicki, Camila and Laura.
    "Lea": (0.0482, 0.287, 0.17), "Vicki": (0.0548, 0.326, 0.20), "Bianca": (0.0584, 0.347, 0.21), "Camila": (0.0546, 0.325, 0.20),
    "Laura": (0.0548, 0.326, 0.20), "Ola": (0.0559, 0.333, 0.20), "Suvi": (0.0578, 0.344, 0.21),
    # Beatrice (the Italian default since 2026-11-27) took 0.88 of what Bianca's fit predicts for two passages of 60 and 65 words (45.0 s against 51.1 s)
    "Beatrice": (0.0514, 0.305, 0.18),
}
# WORDS a second of speech, per language (the default voice; the same passage and videos as above; English: the median of 174 QA videos). Characters predict
# the time, words do not: French says 3.0 words a second and Finnish 1.9, so a budget counted in words must follow the language (engine/plan.words_per_s).
WORDS_PER_S: Dict[str, float] = {"en": 2.63, "fr": 3.03, "de": 2.66, "it": 2.85, "pt": 3.09, "nl": 2.79, "pl": 2.37, "fi": 1.95}
LANG_RATES: Dict[str, Tuple[float, float, float]] = {"en": (0.0555, 0.33, 0.20), "es": (0.0530, 0.345, 0.14)}   # a voice without its own fit
# The four fitted voices say the catalogue's sentence 4 to 10 percent faster than their fits predict (Ruth 11.6 s against 12.3, Amy 12.0 / 12.5, Lucia 10.7 / 11.2,
# Lupe 11.2 / 12.3: finished beats carry a little more silence than one clean sentence), so a rate derived from that sentence is raised by the median of the four.
SAMPLE_CALIBRATION = 1.05

OVER = 0.05              # the window above the asked length: asked .. asked * 1.05
CUT_ABOVE = 1.03         # a script estimated past this share of the asked length is cut ...
CUT_AIM = 1.00           # ... to as near this as whole sentences allow (the estimate is off by up to about 13 percent either way; the pauses and the stretch absorb that)
TIGHTEN_AIM = 1.03       # with the measured audio: a video past this share of the asked length gives up pause time, down to the floors below
LEAD_FLOOR, TAIL_FLOOR = 0.22, 0.25   # the shortest silence before the first word and after the last word of a beat (normally 0.40 and 0.55)
MIN_SENTENCE_WORDS = 3   # a piece shorter than this is not a sentence on its own ("Dr.", "No.") and stays with its neighbour

_PUNCT = re.compile(r"[.!?;:,—–…]")
_DIGIT = re.compile(r"\d")
_NEXT = r"(?=[\"'“‘„«(¿¡]*[A-ZÀ-ÜĄ-Ž0-9])"   # the next sentence opens with a capital (Latin Extended-A too: Polish Ł, Ś, Ż) or a digit
_SPLIT = re.compile(r"(?:(?<=[.!?\u2026])|(?<=[.!?\u2026][\"'\u201d\u2019)]))\s+" + _NEXT)


def _measured(voice: str, lang: str) -> Optional[Tuple[float, float, float]]:
    """A voice with no fit of its own: the language rate scaled by how long the voice took to say the catalogue's fixed sentence (engine/voice_data.py, one
    measurement per voice) against what the language rate predicts for that sentence. For the languages without a fit (French, German, ...) the English shape
    (seconds per character, pause and digit) is scaled the same way, so the estimate is right for that one sentence and approximately right elsewhere."""
    from . import voice_data
    v = next((x for x in voice_data.VOICES if x["id"] == voice), None)
    text = voice_data.SAMPLE.get(v["language"]) if v else None
    if not v or not text or not v.get("sample_s"):
        return None
    if v["language"] not in LANG_RATES:   # a newer language: its default voice has a fit; another voice of it is that fit, as much faster or slower as it said the catalogue's sentence
        from . import voices
        base = next((x for x in voice_data.VOICES if x["id"] == voices.default_voice(v["language"])), None)
        if base and base["id"] in RATES and base.get("sample_s") and base["id"] != voice:
            k = float(v["sample_s"]) / float(base["sample_s"])
            return tuple(round(x * k, 5) for x in RATES[base["id"]])   # type: ignore[return-value]
    c, p, d = LANG_RATES.get(v["language"], LANG_RATES["en"])
    predicted = len(text) * c + len(_PUNCT.findall(text)) * p + len(_DIGIT.findall(text)) * d
    k = SAMPLE_CALIBRATION * float(v["sample_s"]) / predicted
    return (round(c * k, 5), round(p * k, 4), round(d * k, 4))


_MEASURED: Dict[str, Optional[Tuple[float, float, float]]] = {}


def rate_for(language: str = "en", voice: Optional[str] = None) -> Tuple[float, float, float]:
    """(seconds per character, per punctuation mark, per digit): the voice's own fit, else its one measured sentence, else the language's rate."""
    name, lang = str(voice or ""), str(language or "en").lower()[:2]
    if name in RATES:
        return RATES[name]
    if name and name not in _MEASURED:
        _MEASURED[name] = _measured(name, lang)
    if _MEASURED.get(name):
        return _MEASURED[name]
    if lang not in LANG_RATES:   # no voice known: the language's default voice stands for it
        from . import voices
        return rate_for(lang, voices.default_voice(lang)) if lang in voices.LANGUAGES and voices.default_voice(lang) != name else LANG_RATES["en"]
    return LANG_RATES[lang]


def estimate_speech(text: str, language: str = "en", voice: Optional[str] = None) -> float:
    """Seconds the voice needs for this text (an estimate: the real length is only known once the audio exists)."""
    text = " ".join(str(text or "").split())
    if not text:
        return 0.0
    c, p, d = rate_for(language, voice)
    return len(text) * c + len(_PUNCT.findall(text)) * p + len(_DIGIT.findall(text)) * d


def sentences(text: str) -> List[str]:
    """The text as whole sentences; a piece too short to stand alone is joined to the one after it (or before it, at the end)."""
    parts = [s for s in _SPLIT.split(" ".join(str(text or "").split())) if s]
    out: List[str] = []
    carry = ""
    for s in parts:
        s = (carry + " " + s).strip() if carry else s
        if len(s.split()) < MIN_SENTENCE_WORDS:
            carry = s
            continue
        carry = ""
        out.append(s)
    if carry:
        if out:
            out[-1] = out[-1] + " " + carry
        else:
            out.append(carry)
    return out


def _voice_of(plan: Dict[str, Any], beat: Dict[str, Any]) -> Optional[str]:
    voices = plan.get("voices") if isinstance(plan.get("voices"), dict) else {}
    v = voices.get(beat.get("speaker") or "narrator") or voices.get("narrator")
    if isinstance(v, dict):
        v = v.get("voice")
    return v if isinstance(v, str) else None


def _pauses() -> Tuple[float, float, float, float]:
    from . import timeline   # here, not at the top: the timeline imports this module

    return timeline.LEAD, timeline.TAIL, timeline.MIN_SCENE, timeline.END_HOLD


def beat_seconds(plan: Dict[str, Any], beat: Dict[str, Any], text: Optional[str] = None) -> float:
    """The estimated length of one beat's scene: a pause as long as it is held, a spoken beat its speech plus the silences around it."""
    lead, tail, min_scene, _ = _pauses()
    if beat.get("silent"):
        try:
            return max(min_scene, float(beat.get("hold") or 0.0))
        except (TypeError, ValueError):
            return min_scene
    return max(min_scene, lead + estimate_speech(beat.get("narration", "") if text is None else text, plan.get("language", "en"), _voice_of(plan, beat)) + tail)


def estimate_total(plan: Dict[str, Any]) -> float:
    """The estimated length of the whole video as the timeline will build it (before any stretching or tightening)."""
    _, _, _, end_hold = _pauses()
    beats = [b for b in (plan.get("beats") or []) if isinstance(b, dict)]
    if not beats:
        return 0.0
    intro = max(0.0, min(6.0, float(plan.get("intro_s") or 0.0)))
    outro = max(end_hold, min(8.0, float(plan.get("outro_s") or end_hold)))
    return sum(beat_seconds(plan, b) for b in beats) + (intro if not beats[0].get("silent") else 0.0) + outro


def fit_script(plan: Dict[str, Any], target_seconds: float, *, min_beat_words: int = 6, min_beats: int = 2, drop_beats: bool = True) -> Dict[str, Any]:
    """Cuts the script IN PLACE when its estimated length is past the asked one (see the module text). Returns a report:
    {"target", "before", "after", "cut_sentences", "cut_beats", "cut_words", "fits"}; `fits` is False when nothing more could be cut and the estimate is still
    past the window the pauses can recover. Never raises, never adds, never touches a script that fits."""
    target = float(target_seconds or 0.0)
    beats: List[Dict[str, Any]] = plan.get("beats") or []
    before = estimate_total(plan)
    rep = {"target": round(target, 1), "before": round(before, 1), "after": round(before, 1), "cut_sentences": 0, "cut_beats": 0, "cut_words": 0, "fits": True}
    if target <= 0 or not beats or before <= target * CUT_ABOVE:
        return rep
    limit, aim = target * CUT_ABOVE, target * CUT_AIM
    est = before
    while est > limit:
        # every sentence that may go: not the opening line, not the closing line, and the beat keeps enough words to be a beat
        best = None
        for i, b in enumerate(beats):
            if b.get("silent") or not b.get("narration"):
                continue
            ss = sentences(b["narration"])
            if len(ss) < 2:
                continue
            now = beat_seconds(plan, b)
            for j, s in enumerate(ss):
                if (i == 0 and j == 0) or (i == len(beats) - 1 and j == len(ss) - 1):
                    continue
                rest = " ".join(ss[:j] + ss[j + 1:])
                if len(rest.split()) < min_beat_words:
                    continue
                after = est - (now - beat_seconds(plan, b, rest))
                # the cut that lands nearest the aim; among equals a sentence from the middle of the video and the middle of its beat goes first
                key = (round(abs(after - aim), 2), 0 if 0 < i < len(beats) - 1 else 1, 0 if 0 < j < len(ss) - 1 else 1, i, j)
                if best is None or key < best[0]:
                    best = (key, i, rest, after, len(s.split()))
        if best is None or abs(best[3] - aim) >= abs(est - aim):
            break
        _, i, rest, est, n = best
        beats[i]["narration"] = rest
        rep["cut_sentences"] += 1
        rep["cut_words"] += n
    # more beats than the length has room for (a 30 s video written in 4 beats): a whole middle beat goes, the shortest that brings the estimate nearest the aim
    while drop_beats and est > limit and len(beats) > max(2, int(min_beats)):
        best = None
        for i in range(1, len(beats) - 1):
            b = beats[i]
            if b.get("silent") or b.get("speaker"):   # a pause is the director's choice, and a dialogue line is somebody's turn
                continue
            after = est - beat_seconds(plan, b)
            key = (round(abs(after - aim), 2), i)
            if best is None or key < best[0]:
                best = (key, i, after)
        if best is None or abs(best[2] - aim) >= abs(est - aim):
            break
        _, i, est = best
        gone = beats.pop(i)
        if gone.get("chapter") and i < len(beats) and not beats[i].get("chapter"):   # the chapter starts one beat later
            beats[i]["chapter"] = gone["chapter"]
        rep["cut_beats"] += 1
        rep["cut_words"] += len(str(gone.get("narration") or "").split())
    spoken = sum(1 for b in beats if not b.get("silent"))
    lead, tail, _, _ = _pauses()
    room = spoken * ((lead - LEAD_FLOOR) + (tail - TAIL_FLOOR))   # what the pauses can still give back once the real audio is known
    rep["after"] = round(est, 1)
    rep["fits"] = est <= target * (1.0 + OVER) + room
    return rep


EXTEND_SYSTEM = (
    "You lengthen the narration of a short explainer video that came out too short for the length its viewer asked for. You are given some of its beats, each with "
    "the number of words to ADD. For each, return the narration with its existing sentences word for word, in the same order, and new sentences between or after "
    "them (never before the first sentence of beat 1): an explanation, an example, a consequence or a comparison that follows from what the script already says. "
    "No new numbers, names, dates or claims that the script does not already support; no filler, no recap, no greeting, no 'in this video'. Same language, same "
    'tone, same reading level. Answer ONLY JSON: {"beats": [{"beat": <the number given>, "narration": "<the longer narration>"}]} with exactly the beats given.')
EXTEND_FITTED = ("en", "es")   # not lengthened: their word budget and its repair in the plan step are fitted on 174 finished videos and they come out a little short by design (held 1 to 1.6 s a scene)
EXTEND_AIM = 0.97        # a script lengthened by the model aims at this share of the length asked (the writer lands over what it is asked; `fit_script` cuts what is too much)


def absorbable(plan: Dict[str, Any]) -> float:
    """Seconds the timeline makes up by holding every spoken scene a little longer (timeline.MAX_SPOKEN_STRETCH each): a video short by no more than this
    never shows a freeze. What is short beyond it was held on the last scene: the dead tail of the first French and Portuguese videos."""
    from . import timeline

    return timeline.MAX_SPOKEN_STRETCH * sum(1 for b in (plan.get("beats") or []) if isinstance(b, dict) and not b.get("silent"))


def extend_script(plan: Dict[str, Any], target_seconds: float, ask: Any, *, max_beat_words: int = 70) -> Dict[str, Any]:
    """The counterpart of `fit_script`, for every language whose word budget is not fitted on finished videos (all but EXTEND_FITTED): when the script is estimated so short that holding every scene a little longer cannot
    reach the length asked (`absorbable`), the writer is asked ONCE to lengthen the beats, each by its share of the missing words; the existing sentences
    stay word for word (what is tied to them, a board's items, stays tied). A beat's answer is taken only if it keeps every existing sentence, is longer and
    within the beat's limit. IN PLACE. -> {"target", "before", "after", "short_by", "asked": beats sent, "extended": beats taken, "added_words"}; `asked` 0
    when the script was long enough. Never raises: a failed call leaves the script as it was (the timeline then spreads the wait over the scenes)."""
    import json

    target = float(target_seconds or 0.0)
    beats: List[Dict[str, Any]] = [b for b in (plan.get("beats") or []) if isinstance(b, dict)]
    before = estimate_total(plan)
    rep: Dict[str, Any] = {"target": round(target, 1), "before": round(before, 1), "after": round(before, 1), "short_by": round(max(0.0, target - before), 1), "asked": 0, "extended": 0, "added_words": 0}
    spoken = [(i, b) for i, b in enumerate(beats) if not b.get("silent") and str(b.get("narration") or "").strip()]
    lang = plan.get("language", "en")
    if target <= 0 or not spoken or ask is None or target - before <= absorbable(plan) or str(lang or "en").lower()[:2] in EXTEND_FITTED:
        return rep
    need_s = target * EXTEND_AIM - before
    total_s = sum(estimate_speech(b["narration"], lang, _voice_of(plan, b)) for _, b in spoken) or 1.0
    rows, want = [], {}
    for i, b in spoken:
        words = len(b["narration"].split())
        secs = estimate_speech(b["narration"], lang, _voice_of(plan, b))
        add = min(int(round(need_s * (secs / total_s) * words / max(secs, 0.1))), max(0, max_beat_words - words))     # its share of the time, at its own words a second
        if add >= 3:
            want[i] = add
            rows.append(f"Beat {i + 1}: add about {add} words (now {words}). Narration: {json.dumps(b['narration'], ensure_ascii=False)}")
    if not rows:
        return rep
    rep["asked"] = len(rows)
    try:
        from . import voices

        raw = ask(EXTEND_SYSTEM + f" The language is {voices.LANGUAGES.get(str(lang)[:2], 'English')}.",
                  f"The video is asked to be {target:.0f} s long and its narration is about {target - before:.0f} s short.\n\n" + "\n\n".join(rows))
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        norm = lambda t: " ".join(str(t).split())      # noqa: E731
        for row in data.get("beats") or []:
            i = int(row.get("beat", 0)) - 1
            new = norm(row.get("narration") or "")
            if i not in want:
                continue
            old = norm(beats[i]["narration"])
            pos, kept = 0, True
            for sent in sentences(old):                 # every existing sentence, word for word, in order
                at = new.find(sent, pos)
                if at < 0:
                    kept = False
                    break
                pos = at + len(sent)
            n_old, n_new = len(old.split()), len(new.split())
            if not kept or n_new <= n_old or n_new > max(max_beat_words, n_old) or n_new > n_old + int(1.5 * want[i]) + 4 or (i == 0 and not new.startswith(sentences(old)[0])):
                continue
            beats[i]["narration"] = new
            rep["extended"] += 1
            rep["added_words"] += n_new - n_old
    except Exception as e:  # noqa: BLE001 - the script stands as it was
        rep["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    rep["after"] = round(estimate_total(plan), 1)
    return rep


def tighten(n_spoken: int, total: float, target_seconds: float, lead: float, tail: float) -> Tuple[float, float]:
    """The (lead, tail) silences that bring a video of `total` seconds (built with the normal silences) back to the window above `target_seconds`: unchanged
    when it already fits, otherwise both shortened by the same share, no further than their floors. A video that is still too long then stays too long: the
    words are never cut once they are spoken."""
    target = float(target_seconds or 0.0)
    if target <= 0 or n_spoken <= 0 or total <= target * TIGHTEN_AIM:
        return lead, tail
    room = n_spoken * ((lead - LEAD_FLOOR) + (tail - TAIL_FLOOR))
    if room <= 0:
        return lead, tail
    k = min(1.0, (total - target * TIGHTEN_AIM) / room)
    return round(lead - k * (lead - LEAD_FLOOR), 3), round(tail - k * (tail - TAIL_FLOOR), 3)


def clean_pace(raw: Any, lead: float, tail: float) -> Tuple[float, float]:
    """A plan's stored pace -> (lead, tail), only ever between the floors and the normal values."""
    if not isinstance(raw, dict):
        return lead, tail
    try:
        lo, ta = float(raw.get("lead", lead)), float(raw.get("tail", tail))
    except (TypeError, ValueError):
        return lead, tail
    return min(lead, max(LEAD_FLOOR, lo)), min(tail, max(TAIL_FLOOR, ta))
