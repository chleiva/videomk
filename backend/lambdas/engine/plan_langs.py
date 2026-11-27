"""The language of every spoken line of a plan, and the checks that keep it true (docs/MULTILINGUAL_CONVERSATIONS_DESIGN_2026-11-27.md sections 2.3, 2.4, 2.11).

`plan.language` is the video's MAIN language (the viewer's: title, description, end card, sources, translation line). With `plan.polyglot` each speaker has its own
language (`polyglot.speakers`: {character id: language}) and every line is written in, and spoken with a voice of, its speaker's language. Without `polyglot` nothing
here changes anything: `beat_lang` answers the plan's language.

  * `beat_lang`, `speaker_lang`, `is_polyglot`   who speaks what
  * `check_lines`    language of every line: the word-count heuristic first (free), one batched small-model call for the lines it cannot judge
  * `repair_lines`   a line in the wrong language is rewritten ONCE (one batched call, neighbours as context); still wrong: kept, a warning recorded, never dropped
  * `recast`         each speaker gets a voice of ITS language (the resolver, `presenter_policy.voice_for`; no voice name is written here)
  * `audit`          voice language equals line language for every spoken beat, translation present, speaker known: a mismatch is a bug, not a note
  * `translation_for`   the text of the translation row of a beat (or None), by the `translation` switch
  * `plan_seconds`   the estimated length of the video in seconds (per-voice measured rates, engine/length.py)
Pure except the two small-model calls, which take the caller's `ask(system, user) -> text`.
"""
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import language as lang_mod
from . import voices

Ask = Callable[[str, str], str]
MAX_LANGS = 3


# ----------------------------------------------------------------------------- who speaks what
def polyglot_of(plan: Dict[str, Any]) -> Dict[str, Any]:
    p = plan.get("polyglot")
    return p if isinstance(p, dict) and isinstance(p.get("speakers"), dict) else {}


def main_language(plan: Dict[str, Any]) -> str:
    return str(plan.get("language") or "en").lower()[:2]


def speaker_lang(plan: Dict[str, Any], speaker: Optional[str]) -> str:
    lang = polyglot_of(plan).get("speakers", {}).get(speaker or "")
    return str(lang).lower()[:2] if lang else main_language(plan)


def beat_lang(plan: Dict[str, Any], beat: Dict[str, Any]) -> str:
    """The language this beat is written in and spoken in: its own `lang`, else its speaker's, else the plan's."""
    own = beat.get("lang")
    return str(own).lower()[:2] if isinstance(own, str) and own else speaker_lang(plan, beat.get("speaker"))


def languages_of(plan: Dict[str, Any]) -> List[str]:
    """The languages spoken in the plan, the main one first when it is among them, each once."""
    seen: List[str] = []
    for b in plan.get("beats") or []:
        if not b.get("silent") and str(b.get("narration") or "").strip():
            lang = beat_lang(plan, b)
            if lang not in seen:
                seen.append(lang)
    main = main_language(plan)
    return ([main] if main in seen else []) + [x for x in seen if x != main]


def is_polyglot(plan: Dict[str, Any]) -> bool:
    """More than one language is spoken, or the one spoken is not the main language (a French video for an English viewer still needs its translation row)."""
    if not polyglot_of(plan):
        return False
    langs = languages_of(plan)
    return len(langs) > 1 or (bool(langs) and langs[0] != main_language(plan))


def spoken(plan: Dict[str, Any]) -> List[Tuple[int, Dict[str, Any]]]:
    return [(i, b) for i, b in enumerate(plan.get("beats") or []) if not b.get("silent") and str(b.get("narration") or "").strip()]


# ----------------------------------------------------------------------------- is every line in its speaker's language
IDENTIFY = ("You identify languages. You get numbered lines of a children's video script. For EACH line reply with the ISO 639-1 code of the language it is written in "
            '(en es fr de it pt nl pl fi, or "xx" when it cannot be told: a name, a sound, a single interjection). A line may quote a word of another language; judge the language of '
            'the sentence itself. Return ONLY a JSON object {"1": "fr", "2": "de", ...} with one entry per line.')


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


def heuristic_lang(text: str) -> Optional[str]:
    """A language code when the word counts are sure (engine/language.heuristic), else None. Only languages the app has voices for count."""
    code = lang_mod.heuristic(_norm(text))
    return code if code in voices.READY else None


def check_lines(plan: Dict[str, Any], ask: Optional[Ask] = None) -> Dict[str, Any]:
    """Language of every spoken line against its speaker's language.
    -> {"wrong": [{"beat", "expected", "found"}], "unsure": [beat index], "asked": n lines sent to the model, "ok": n lines right}
    The heuristic judges what it is sure of; the rest goes to ONE small-model call (no call when nothing is unsure or `ask` is None: those lines are given the benefit of the doubt)."""
    rows = spoken(plan)
    verdict: Dict[int, Optional[str]] = {i: heuristic_lang(b["narration"]) for i, b in rows}
    unsure = [i for i, _ in rows if verdict[i] is None]
    asked = 0
    if unsure and ask is not None:
        lines = [(i, plan["beats"][i]["narration"]) for i in unsure]
        asked = len(lines)
        try:
            raw = ask(IDENTIFY, "\n".join(f"{k + 1}. {_norm(t)[:300]}" for k, (_, t) in enumerate(lines)))
            obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            for k, (i, _) in enumerate(lines):
                code = str(obj.get(str(k + 1)) or "").strip().lower()[:2]
                verdict[i] = code if code in voices.READY else None
        except Exception:   # noqa: BLE001 - a failed check never fails a video: the lines stay unjudged
            pass
    wrong = [{"beat": i, "expected": beat_lang(plan, b), "found": verdict[i]} for i, b in rows if verdict[i] and verdict[i] != beat_lang(plan, b)]
    return {"wrong": wrong, "unsure": [i for i, _ in rows if verdict[i] is None], "asked": asked, "ok": len(rows) - len(wrong) - sum(verdict[i] is None for i, _ in rows)}


REWRITE = ("You fix a children's video script written for characters that each speak their OWN language. Some lines are in the wrong language. Rewrite EACH numbered line "
           "ONLY in the language named for it, keeping its meaning, its tone, its length (about the same number of words) and its first-person voice, and so that it still "
           "answers the line before it and leads into the line after it. Do not mix languages (a name or a word the line is about may stay). Return ONLY a JSON object "
           '{"<number>": "<the rewritten line>", ...} with one entry per numbered line.')


def repair_lines(plan: Dict[str, Any], wrong: List[Dict[str, Any]], ask: Ask, check_again: bool = True) -> Dict[str, Any]:
    """Rewrites the wrong lines ONCE, in place (and their translation is kept: the meaning does not change). Returns {"rewritten": n, "still_wrong": [..], "warnings": [..]}.
    A line that is still wrong after the rewrite is kept as the rewrite (the second try is never made) and named in the warnings."""
    beats = plan.get("beats") or []
    if not wrong:
        return {"rewritten": 0, "still_wrong": [], "warnings": []}
    names = voices.LANGUAGES
    parts = []
    for k, w in enumerate(wrong):
        i = w["beat"]
        before = beats[i - 1]["narration"] if i > 0 else ""
        after = beats[i + 1]["narration"] if i + 1 < len(beats) else ""
        parts.append(f"{k + 1}. Language: {names.get(w['expected'], w['expected'])}. Speaker: {beats[i].get('speaker') or 'narrator'}.\n"
                     f"   Line before (context): {_norm(before)[:200]}\n   WRONG LINE: {_norm(beats[i]['narration'])}\n   Line after (context): {_norm(after)[:200]}"
                     + (f"\n   Meaning: {_norm(beats[i].get('translation'))[:240]}" if beats[i].get("translation") else ""))
    out: Dict[str, Any] = {"rewritten": 0, "still_wrong": [], "warnings": []}
    try:
        raw = ask(REWRITE, "\n\n".join(parts))
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:   # noqa: BLE001
        out["warnings"] = [f"language: beat {w['beat']} is in {w['found']}, not {w['expected']}; the rewrite failed, the line was kept" for w in wrong]
        out["still_wrong"] = [w["beat"] for w in wrong]
        return out
    for k, w in enumerate(wrong):
        text = _norm(obj.get(str(k + 1)))
        if not text or len(text.split()) < 2:
            out["still_wrong"].append(w["beat"])
            out["warnings"].append(f"language: beat {w['beat']} is in {w['found']}, not {w['expected']}; no usable rewrite, the line was kept")
            continue
        beats[w["beat"]]["narration"] = text
        out["rewritten"] += 1
        found = heuristic_lang(text)
        if check_again and found and found != w["expected"]:
            out["still_wrong"].append(w["beat"])
            out["warnings"].append(f"language: beat {w['beat']} is still in {found}, not {w['expected']} after one rewrite; kept")
    return out


def settle(plan: Dict[str, Any], ask: Optional[Ask]) -> Dict[str, Any]:
    """check, rewrite the wrong lines once, record `plan.polyglot.language_check`. -> {"warnings": [...], "wrong": n, "rewritten": n, "asked": n}"""
    first = check_lines(plan, ask)
    warnings: List[str] = []
    rewritten, still = 0, []
    if first["wrong"] and ask is not None:
        r = repair_lines(plan, first["wrong"], ask)
        rewritten, still, warnings = r["rewritten"], r["still_wrong"], r["warnings"]
    elif first["wrong"]:
        warnings = [f"language: beat {w['beat']} is in {w['found']}, not {w['expected']}" for w in first["wrong"]]
        still = [w["beat"] for w in first["wrong"]]
    rec = {"wrong": len(first["wrong"]), "rewritten": rewritten, "still_wrong": still, "asked": first["asked"], "unsure": len(first["unsure"])}
    if isinstance(plan.get("polyglot"), dict):
        plan["polyglot"]["language_check"] = rec
    return {"warnings": warnings, **rec}


# ----------------------------------------------------------------------------- voices
def recast(plan: Dict[str, Any], pick: Optional[Callable[[str, str, List[str]], str]] = None) -> Dict[str, str]:
    """Gives every speaker of `polyglot.speakers` a voice of its OWN language, in place (`plan.voices`), and returns {speaker: voice}. The voice is the resolver's:
    `pick(character, language, taken)`, by default `presenter_policy.voice_for` (hand-picked where the cast table has it, else the closest voice of that language to
    the character's gender). Two speakers of one language get two voices where the language has them."""
    from . import presenter_policy

    pick = pick or presenter_policy.voice_for
    out: Dict[str, str] = {}
    taken_by_lang: Dict[str, List[str]] = {}
    speakers = polyglot_of(plan).get("speakers", {})
    for sid, lang in speakers.items():
        lang = str(lang).lower()[:2]
        taken = taken_by_lang.setdefault(lang, [])
        out[sid] = pick(sid, lang, taken) if sid in presenter_policy.CAST else voices.resolve({}, lang, None, taken)[0]
        taken.append(out[sid])
    if out:
        plan["voices"] = {**{k: v for k, v in (plan.get("voices") or {}).items() if k not in out and k != "narrator"}, **out}
        if isinstance(plan.get("presenter"), dict):
            plan["presenter"]["voices"] = {k: v for k, v in plan["voices"].items()}
    return out


def audit(plan: Dict[str, Any]) -> Dict[str, Any]:
    """The plan audit for a polyglot plan: -> {"ok": bool, "problems": [text]}.
    * every spoken beat has a speaker in `polyglot.speakers`
    * the voice that speaks the beat is a voice OF the line's language (a Spanish voice never reads French text: the owner's case)
    * the translation is there for every line when `polyglot.translate`
    A plan without `polyglot` audits clean (one language, nothing to compare)."""
    p = polyglot_of(plan)
    if not p:
        return {"ok": True, "problems": []}
    problems: List[str] = []
    speakers = p["speakers"]
    for i, b in spoken(plan):
        sp = b.get("speaker")
        lang = beat_lang(plan, b)
        if sp not in speakers:
            problems.append(f"beat {i}: speaker {sp!r} has no language in polyglot.speakers")
        voice = voices.beat_voice(plan, b)
        vlang = voices.language_of(voice) if voice else None
        if vlang != lang:
            problems.append(f"beat {i}: spoken by {voice} ({vlang}) but written in {lang}")
        if p.get("translate") and not str(b.get("translation") or "").strip() and lang != main_language(plan):
            problems.append(f"beat {i}: no translation into {main_language(plan)}")
    return {"ok": not problems, "problems": problems}


# ----------------------------------------------------------------------------- the translation row
def translation_mode(plan: Dict[str, Any]) -> str:
    m = polyglot_of(plan).get("translation")
    return m if m in ("auto", "on", "off") else "auto"


def translation_for(plan: Dict[str, Any], beat: Dict[str, Any]) -> Optional[str]:
    """The text of this beat's translation row, or None: `translation` off shows nothing; `auto` shows it under lines that are not in the main language; `on` under every
    line that has one (a line already in the main language is not translated into itself)."""
    if not polyglot_of(plan) or beat.get("silent"):
        return None
    mode = translation_mode(plan)
    text = _norm(beat.get("translation"))
    if mode == "off" or not text or text.lower() == _norm(beat.get("narration")).lower():
        return None
    if mode == "auto" and beat_lang(plan, beat) == main_language(plan):
        return None
    return text[:300]


def shows_translation(plan: Dict[str, Any]) -> bool:
    """True when any line of the plan has a translation row (the renderer then reserves the band even with captions off)."""
    return any(translation_for(plan, b) for b in plan.get("beats") or [])


def scene_extras(plan: Dict[str, Any], beat: Dict[str, Any]) -> Dict[str, Any]:
    """What the timeline adds to a scene of a polyglot plan: {"translation": text, "lang": code}. {} for every other plan (a plan of today is byte-identical)."""
    if not polyglot_of(plan) or beat.get("silent"):
        return {}
    out: Dict[str, Any] = {}
    tr = translation_for(plan, beat)
    if tr:
        out["translation"] = tr
    lang = beat_lang(plan, beat)
    if lang != main_language(plan):
        out["lang"] = lang
    return out


# ----------------------------------------------------------------------------- length
def plan_seconds(plan: Dict[str, Any]) -> float:
    """Estimated length of the video in seconds as the timeline will build it. The speech rate is the VOICE's own (engine/length.py: a fit per voice, or the voice's
    measured sentence), and every speaker of a polyglot plan has a voice of its language, so a Finnish line and a French line of the same words come out different."""
    from . import length

    return float(length.estimate_total(plan))


def words_per_line(language: str, seconds: float) -> int:
    """How many words a line of `seconds` is in this language (the writer is told per character: French 3.0 words a second, Finnish 1.9; engine/length.WORDS_PER_S)."""
    from . import plan as plan_mod

    return max(5, int(round(seconds * plan_mod.words_per_s(language))))

