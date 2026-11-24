"""Craft guides ("skills") for the director: small, well-researched notes on how to make one KIND of video well (news, history, tutorial, coding, product, funny, ...).

A producer step picks one or two that fit the request with a single cheap model call; the always-on guide (publish quality) is added to every video. The chosen
text goes into the director's prompts (and the outline and section prompts of long videos). Skills are plain markdown files in engine/skills/:

    ---
    id: news-explainer
    name: News and current affairs
    pick: when to choose this guide (one line, read by the selector)
    ---
    - imperative bullets, at most ~1400 characters

`always: true` instead of `pick:` marks a guide that is added to every video. See docs/SKILLS.md for the research behind them.
"""
import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, List, Optional

SKILL_DIR = os.path.join(os.path.dirname(__file__), "skills")
MAX_PICKED = 2
DEFAULT_SKILL = "explainer-education"
MAX_BODY_CHARS = 1400

INTRO = ("Craft guides for this video (they refine the general rules above; follow them where they apply). "
         "A guide's visual suggestions name scene types: use one only if it appears in the scene list above.")

SELECT_SYSTEM = """You are the producer of an AI explainer-video studio. Given a viewer's request, choose which craft guides the director should follow. \
Choose the one or two guides that best match the KIND of video asked for (its subject and purpose), most important first; two only when the request clearly mixes two kinds \
(for example a history of a company is "history-story" and "product-marketing" only if it promotes it). Return ONLY JSON: {"types": ["<id>", "<id>"]}. Use only ids from the list."""


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    pick: str
    body: str
    always: bool = False


def _parse(path: str) -> Optional[Skill]:
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None
    head = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    head = {k.strip(): v.strip() for k, v in head.items()}
    sid = head.get("id", "")
    if not re.match(r"^[a-z][a-z0-9-]{2,40}$", sid):
        return None
    return Skill(id=sid, name=head.get("name", sid), pick=head.get("pick", ""), body=m.group(2).strip(), always=head.get("always", "").lower() == "true")


@lru_cache(maxsize=1)
def load() -> Dict[str, Skill]:
    out: Dict[str, Skill] = {}
    if os.path.isdir(SKILL_DIR):
        for fn in sorted(os.listdir(SKILL_DIR)):
            if fn.endswith(".md"):
                try:
                    s = _parse(os.path.join(SKILL_DIR, fn))
                except Exception:   # a broken guide must never take the director down
                    logging.exception("skill %s could not be read", fn)
                    continue
                if s:
                    out[s.id] = s
    return out


def catalog_text() -> str:
    return "\n".join(f"- {s.id}: {s.name}. Pick when: {s.pick}" for s in load().values() if not s.always)


def _ids_from(text: str) -> List[str]:
    dec, i = json.JSONDecoder(), (text or "").find("{")
    while i >= 0:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and isinstance(obj.get("types"), list):
                return [str(t).strip().lower() for t in obj["types"]]
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return []


def select(request: str, ask: Callable[[str, str], str], minutes: float = 3.0) -> List[str]:
    """Which type guides fit this request: at most MAX_PICKED ids (never the always-on ones), the default when the model fails or names nothing valid."""
    skills = load()
    choices = [s.id for s in skills.values() if not s.always]
    if not choices:
        return []
    try:
        raw = ask(SELECT_SYSTEM + "\n\nGuides:\n" + catalog_text(), f"Request: {request[:600]}\nTarget length: {minutes:g} minutes")
    except Exception:   # the producer is an improvement, never a requirement
        logging.exception("skill selection failed")
        raw = ""
    picked: List[str] = []
    for sid in _ids_from(raw):
        if sid in choices and sid not in picked:
            picked.append(sid)
    if not picked and DEFAULT_SKILL in choices:
        picked = [DEFAULT_SKILL]
    return picked[:MAX_PICKED]


def render(ids: List[str]) -> str:
    """The text added to the director's prompts: the always-on guides first, then the picked ones. Empty when there are none."""
    skills = load()
    parts = [s for s in skills.values() if s.always] + [skills[i] for i in ids if i in skills and not skills[i].always]
    if not parts:
        return ""
    return "\n\n" + INTRO + "\n\n" + "\n\n".join(f"### {s.name}\n{s.body}" for s in parts)
