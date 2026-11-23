"""Human edits as small, validated operations on the plan. Pure functions: the editor API and the tests both use them.

Anything a person can type is untrusted exactly like LLM output: every changed field goes back through the same
sanitisers, ids must match the strict 8-hex shape, and a human can never choose a file path or an S3 key.
"""
import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from . import plan as plan_mod
from . import voices as voice_mod
from .scenes import SCENE_TYPES
from .theme import THEMES

MAX_OPS = 40
_CAND_RE = re.compile(r"^(unsplash|openverse):[A-Za-z0-9_\-]{1,40}$")
_VOICE_RE = re.compile(r"^[A-Za-z0-9_\- ]{0,40}$")
_REF_RE = re.compile(r"^ref:[A-Za-z0-9_]{1,20}$")


class EditError(ValueError):
    pass


def _find(beats: List[Dict[str, Any]], bid: Any, refs: Optional[Dict[str, str]] = None) -> int:
    """Index of a beat by id, or by "ref:<name>" for a beat inserted earlier in the same batch (clients can't know new ids)."""
    if isinstance(bid, str) and _REF_RE.match(bid):
        bid = (refs or {}).get(bid)
    for i, b in enumerate(beats):
        if b["id"] == bid:
            return i
    raise EditError(f"unknown beat id {bid!r}")


def _narration(text: Any) -> str:
    t = plan_mod._s(text, 700)
    n = len(t.split())
    if n < plan_mod.MIN_BEAT_WORDS:
        raise EditError(f"narration needs at least {plan_mod.MIN_BEAT_WORDS} words")
    if n > plan_mod.MAX_BEAT_WORDS:
        raise EditError(f"narration is limited to {plan_mod.MAX_BEAT_WORDS} words per beat; split it into two beats")
    return t


def _scene(stype: Any, props: Any) -> Dict[str, Any]:
    if stype not in SCENE_TYPES:
        raise EditError(f"unknown scene type {stype!r}")
    try:
        return {"type": stype, "props": plan_mod.sanitize_props(stype, props if isinstance(props, dict) else {})}
    except (ValueError, TypeError, AttributeError) as e:
        raise EditError(f"invalid {stype} scene: {e}") from e


def apply_ops(plan: Dict[str, Any], ops: Any, *, max_beats: int = plan_mod.MAX_BEATS) -> Tuple[Dict[str, Any], List[str]]:
    """Returns (new_plan, touched_beat_ids). Raises EditError on the first invalid op: all-or-nothing."""
    if not isinstance(ops, list) or not ops:
        raise EditError("ops must be a non-empty list")
    if len(ops) > MAX_OPS:
        raise EditError(f"at most {MAX_OPS} operations per edit")
    new = copy.deepcopy(plan)
    beats: List[Dict[str, Any]] = new["beats"]
    touched: List[str] = []
    refs: Dict[str, str] = {}

    def touch(bid: str) -> None:
        if bid not in touched:
            touched.append(bid)

    def F(bid: Any) -> int:
        return _find(beats, bid, refs)

    for op in ops:
        if not isinstance(op, dict):
            raise EditError("each op must be an object")
        kind = op.get("op")
        if kind == "set_narration":
            i = F(op.get("id"))
            beats[i]["narration"] = _narration(op.get("text"))
            touch(beats[i]["id"])
        elif kind == "set_scene":
            i = F(op.get("id"))
            beats[i]["scene"] = _scene(op.get("type"), op.get("props"))
            beats[i].pop("pick", None)  # a new scene invalidates a previously picked photo
            touch(beats[i]["id"])
        elif kind == "pick_image":
            i = F(op.get("id"))
            if beats[i]["scene"]["type"] != "image":
                raise EditError("pick_image applies to image scenes")
            cand = op.get("candidate")
            if not isinstance(cand, str) or not _CAND_RE.match(cand):
                raise EditError("bad candidate id")
            beats[i]["pick"] = cand
            touch(beats[i]["id"])
        elif kind == "insert":
            if len(beats) >= max_beats:
                raise EditError(f"a video can have at most {max_beats} beats")
            after = op.get("after")
            at = 0 if after in (None, "") else F(after) + 1
            sc = op.get("scene") or {}
            beat = {"id": plan_mod.new_beat_id(None, {b["id"] for b in beats}), "narration": _narration(op.get("narration")), "scene": _scene(sc.get("type"), sc.get("props"))}
            if plan_mod._s(op.get("chapter"), 60):
                beat["chapter"] = plan_mod._s(op.get("chapter"), 60)
            beats.insert(at, beat)
            ref = op.get("ref")
            if ref is not None:
                if not isinstance(ref, str) or not _REF_RE.match("ref:" + ref) or "ref:" + ref in refs:
                    raise EditError("bad or duplicate ref")
                refs["ref:" + ref] = beat["id"]
            touch(beat["id"])
        elif kind == "delete":
            if len(beats) <= 1:
                raise EditError("a video needs at least one beat")
            beats.pop(F(op.get("id")))
        elif kind == "move":
            i = F(op.get("id"))
            to = op.get("to")
            if isinstance(to, bool) or not isinstance(to, int) or not 0 <= to < len(beats):
                raise EditError("'to' is out of range")
            beats.insert(to, beats.pop(i))
        elif kind == "set_chapter":
            i = F(op.get("id"))
            title = plan_mod._s(op.get("title"), 60)
            beats[i].pop("chapter", None)
            if title:
                beats[i]["chapter"] = title
        elif kind == "set_meta":
            if "title" in op:
                t = plan_mod._s(op["title"], 60)
                if not t:
                    raise EditError("title cannot be empty")
                new["title"] = t
            if "description" in op:
                new["description"] = plan_mod._s(op["description"], 400)
            if "theme" in op:
                if op["theme"] not in THEMES:
                    raise EditError("unknown theme")
                new["theme"] = op["theme"]
            if "mood" in op:
                if op["mood"] not in ("calm", "bright", "tense"):
                    raise EditError("unknown mood")
                new["mood"] = op["mood"]
        elif kind == "set_speaker":
            i = F(op.get("id"))
            sp = voice_mod.speaker_id(op.get("speaker"))
            if sp and sp not in (new.get("voices") or {}):
                raise EditError(f"unknown speaker {sp!r}")
            beats[i].pop("speaker", None)
            if sp:
                beats[i]["speaker"] = sp
            touch(beats[i]["id"])
        elif kind == "set_voice":
            voice = str(op.get("voice", ""))
            if not _VOICE_RE.match(voice):
                raise EditError("bad voice name")
            if (new.get("tts") or {}).get("provider", "polly") == "polly":
                voice = voice_mod.canonical(voice) or ""
                if not voice:
                    raise EditError("unknown voice: choose one of " + ", ".join(voice_mod.CATALOG))
            cast = new.setdefault("voices", {})
            speaker = voice_mod.speaker_id(op.get("speaker")) if op.get("speaker") else ("narrator" if "narrator" in cast or not cast else next(iter(cast)))
            if cast and speaker not in cast:
                raise EditError(f"unknown speaker {speaker!r}")
            if speaker == "narrator" or not cast:
                new.setdefault("tts", {})["voice"] = voice
            cast[speaker] = voice
            if len(set(cast.values())) < len(cast):
                raise EditError("two speakers can't share a voice")
            if "style" in op:
                new["tts"]["style"] = plan_mod._s(op["style"], 160)
        else:
            raise EditError(f"unknown op {kind!r}")
    if not beats:
        raise EditError("a video needs at least one beat")
    return new, touched
