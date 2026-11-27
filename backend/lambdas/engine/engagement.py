"""The engagement brief: a short block of rules appended to the director's craft text so that ANY request (vague, tiny, dry, corporate) becomes a video
people keep watching. It is distilled in docs/QUALITY_REVIEW.md (rubric and sources). Flag: ENGAGEMENT_PROMPT (see `enabled`).
Pure text, no model calls, no side effects. It never asks for facts beyond the notes: accuracy rules stay in plan.py and quality.py."""
import os
import re
from typing import Optional

BANNED_EN = ("in this video", "welcome to", "let's dive in", "let's explore", "have you ever wondered", "in today's fast-paced world", "it's important to note", "in conclusion", "game-changer", "unlock", "delve", "thanks for watching")
BANNED_ES = ("en este video", "bienvenidos", "vamos a sumergirnos", "te has preguntado alguna vez", "en el mundo de hoy", "es importante destacar", "en conclusión", "gracias por ver")


def enabled() -> bool:
    return os.environ.get("ENGAGEMENT_PROMPT", "1").strip().lower() not in ("0", "off", "false", "no")


def is_vague(prompt: str) -> bool:
    """A request with no angle of its own: a few words, a bare topic, 'a video about my X'."""
    return len(re.findall(r"\w+", prompt or "")) <= 8


def hook_rule(minutes: Optional[float]) -> str:
    if minutes is not None and minutes < 1:
        return "HOOK: the first sentence is spoken in the first 2 seconds and is a concrete surprise, a stake or a question the video answers; the first scene is a big few-word statement or a number, never a title card with a subtitle."
    if minutes is not None and minutes >= 4:
        return ("HOOK: cold open. Beat 1 is the single most surprising concrete fact in the notes (a number, a name, a reversal) with a picture or number on screen, not a title card; the title and the agenda never come first. "
                "Open one question in the first minute and pay it off later; every 60-90 seconds open a smaller one or turn the story (\"but\", \"so\", \"which means\").")
    return ("HOOK: beat 1 (under 8 seconds) is the most surprising concrete fact in the notes or a question the video answers, with a picture or number on screen, not a title card. "
            "Open one question early and pay it off before the end.")


def banned_phrases(language: str = "en") -> str:
    """The filler lines the writer must avoid. Listed in English and Spanish; in any other language the English list stands for its equivalents."""
    if language == "es":
        return ", ".join('"%s"' % b for b in BANNED_ES)
    out = ", ".join('"%s"' % b for b in BANNED_EN)
    if language and language != "en":
        from . import voices
        out += f" (nor their equivalents in {voices.LANGUAGES.get(language, 'the language of the video')})"
    return out


def block(prompt: str, minutes: Optional[float], language: str = "en", photos: bool = False) -> str:
    """The rules to append to `craft`; empty when disabled or for a video made from the person's own photos (its own guide governs)."""
    if not enabled() or photos:
        return ""
    banned = banned_phrases(language)
    short = minutes is not None and minutes < 1
    cadence = ("a new picture or on-screen change at least every 4 seconds" if short else "a new picture or on-screen change at least every 8 seconds (a bullets or steps scene earns its place only if its items appear as they are spoken)")
    out = ["\n\nENGAGEMENT (the goal is a video people watch to the end, whatever the request; these refine the rules above):",
           "- " + hook_rule(minutes),
           "- THROUGH-LINE: choose ONE promise or question for the whole video and make every beat advance it (problem, stakes, turn, payoff). Cut anything that does not.",
           "- SPECIFIC BEFORE GENERAL: each beat carries one concrete thing taken from the notes (a number, name, date, example, comparison). Abstractions come after the example, never instead of it. Never invent a specific the notes do not contain; if the notes are thin, use one vivid, well-known, safe example instead.",
           f"- RHYTHM: {cadence}. Never the same scene type more than twice in a row. Do not open a section with a definition card: show the thing first, name it second. Sentences are short, active and mixed in length; one long sentence is allowed after two short ones.",
           "- FIRST ITEM FAST: in a beat that shows items one by one (bars, steps, nodes, bullets), the narration names the first item in its first sentence, so the screen is never an empty frame for seconds.",
           f"- VOICE: no filler openers or closers and none of these: {banned}. No \"there are N things\" announcements. Say the point, then the proof.",
           "- ENDING: the last beat pays off the opening question or fact and ends on one line the viewer can repeat. No recap of all sections, no thanks, no \"follow\" or \"subscribe\" unless the request asks for a call to action.",
           ]
    if is_vague(prompt):
        out.append("- VAGUE REQUEST: the request names a topic but no angle. Do not write a generic overview. Pick the angle a curious general viewer would find most surprising or useful, state it in beat 1, and keep to it (a business video: one customer problem, the change, the result).")
    return "\n".join(out)
