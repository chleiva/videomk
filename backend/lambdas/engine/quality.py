"""Post-write checks that keep the script honest (QUALITY_FIXES, docs/QUALITY_FIXES.md).

  ground_check   the checkable specifics in the narration (numbers with units, years, proper names, quotes) that appear nowhere in the research notes, the person's request
                 or the creator's brief are shown to the small model, once, which decides per candidate "notes" / "common" (well-known, safe to keep) / "unsupported" and rewrites
                 only the sentences that carry an unsupported specific. Never loops; any failure keeps the original script.
  repair_scenes  scenes that were replaced as invalid (a `versus` with one row) get ONE small-model call to correct them, instead of becoming a title card.

Both are pure of storage and billing (the caller passes `ask_small`) and cost a fraction of a cent: no model call at all when nothing is flagged.
"""
import json
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence

from .netsafe import quality_fixes

Ask = Callable[..., str]   # (system, user, max_tokens) -> text

MAX_BEATS_CHECKED = 14
MAX_NOTES_CHARS = 6000
STOP = set("""the a an and or but of to in on at for with by from as is are was were be been it its this that these those you your we our they their he she his her i
not no so if then than too very can will just also into over about more most how what why when where who which do does did has have had one all any some there here
el la los las un una unos unas y o pero de del al en con por para como es son era fue ser se su sus lo le les que qué cómo cuando donde quien cuál mi tu tus nos
más muy si ya también este esta estos estas eso esto hay han ha he hemos puede pueden""".split())
MONTHS = set("january february march april may june july august september october november december enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())
DAYS = set("monday tuesday wednesday thursday friday saturday sunday lunes martes miércoles miercoles jueves viernes sábado sabado domingo".split())
ORDINALS = set("""first second third fourth fifth sixth seventh eighth ninth tenth last next primero primera segundo segunda tercero tercera cuarto cuarta quinto quinta sexto sexta
séptimo septimo octavo noveno décimo decimo último ultimo""".split())
CAP_SKIP = MONTHS | DAYS | ORDINALS | {"i", "ok", "yes", "no", "sí", "hey", "wow", "imagine", "picture", "now", "today", "hoy", "ahora"}
UNITS = (r"%|percent|per cent|por ciento|mg|kg|g|km|cm|mm|ml|l|m|mph|kph|°|degrees?|grados?|minutes?|minutos?|mins?|hours?|horas?|days?|d[ií]as?|years?|a[ñn]os?|weeks?|semanas?|months?|meses|"
         r"seconds?|segundos?|dollars?|d[oó]lares?|euros?|usd|eur|calories|calor[ií]as|times|veces|people|personas|patients|pacientes|trials|studies|estudios")
FICTION = re.compile(r"\b(story|fable|tale|fairy|fiction|novel|poem|cuento|f[aá]bula|relato|ficci[oó]n|historia inventada|poema)\b", re.I)
LEAK = re.compile(r"\b(?:the|our|my) (?:grounding |research )?notes\b|\baccording to (?:the|our) (?:notes|research)\b|\b(?:seg[uú]n )?(?:las|nuestras|mis) notas\b|\bour (?:research|sources)\b|\bnuestras fuentes\b", re.I)
_NUM = re.compile(r"(?<![\w.])(\d[\d.,   ]*\d|\d)(\s?(?:" + UNITS + r")\b|\s?%)?(st|nd|rd|th|º|ª|\.º)?", re.I)


def norm(text: str) -> str:
    """Lowercase, accents stripped, thousands separators removed between digits: the form used to compare narration with notes."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"(?<=\d)[.,   ](?=\d{3}\b)", "", t)


def number_candidates(text: str) -> List[str]:
    """Numbers worth checking: not ordinals, not the small integers (0 to 10) people say idiomatically unless they carry a unit or a percent sign."""
    out: List[str] = []
    for m in _NUM.finditer(text or ""):
        raw, unit, ordinal = m.group(1), m.group(2), m.group(3)
        if ordinal:
            continue
        token = re.sub(r"(?<=\d)[.,   ](?=\d{3}\b)", "", raw).replace(" ", "")
        if re.fullmatch(r"\d+", token) and int(token) <= 10 and not unit:
            continue
        label = (token + (" " + unit.strip() if unit else "")).strip()
        if token not in [o.split(" ")[0] for o in out]:
            out.append(label)
    return out


def entity_candidates(text: str) -> List[str]:
    """Capitalised names that are not at the start of a sentence (runs of capitalised words kept together)."""
    ents: List[str] = []
    for sent in re.split(r"(?<=[.!?:¿¡\n])\s+|^", text or ""):
        toks = re.findall(r"[\w'’\-]+", sent, flags=re.U)
        run: List[str] = []
        for i, t in enumerate(toks):
            cap = (t[:1].isupper() and not t.isupper() or (t.isupper() and len(t) > 1 and t.isalpha())) and not t.isdigit()
            if cap and i > 0 and t.lower() not in CAP_SKIP and t.lower() not in STOP:
                run.append(t)
            else:
                if run:
                    ents.append(" ".join(run))
                run = []
        if run:
            ents.append(" ".join(run))
    seen: List[str] = []
    for e in ents:
        if e not in seen:
            seen.append(e)
    return seen


def quote_candidates(text: str) -> List[str]:
    return [q.strip() for q in re.findall(r"[\"“«]([^\"”»]{18,220})[\"”»]", text or "") if len(q.split()) >= 5]


def _in_corpus(item: str, corpus: str, kind: str) -> bool:
    n = norm(item)
    if kind == "number":
        tok = re.match(r"[\d.]+", n)
        digits = (tok.group(0) if tok else n).strip(".")
        return bool(re.search(r"(?<!\d)" + re.escape(digits) + r"(?!\d)", corpus))
    if n in corpus:
        return True
    return kind == "entity" and all(t in corpus for t in re.findall(r"\w+", n))


def candidates(narration: str, corpus: str, entities: bool = True) -> List[Dict[str, str]]:
    """The specifics in `narration` that the (normalised) corpus does not contain."""
    out: List[Dict[str, str]] = []
    for kind, items in (("number", number_candidates(narration)), ("entity", entity_candidates(narration) if entities else []), ("quote", quote_candidates(narration))):
        for it in items:
            if not _in_corpus(it, corpus, kind):
                out.append({"kind": kind, "text": it})
    return out


def _screen_text(scene: Dict[str, Any]) -> str:
    return norm(json.dumps((scene or {}).get("props") or {}, ensure_ascii=False))


SYSTEM = """You check the narration of a short explainer video against its research notes. Each candidate below is a number, date, name or quote that appears in a beat's narration but NOT literally in the notes, the request or the brief. Decide for each candidate:
- "notes": the notes support it (other wording, spelled out, rounded).
- "common": a well-known, reliable fact or a widely known name you are sure of (Newton, the 1969 Moon landing, water boils at 100 C), or a name of a character or place that the request itself asked to invent (a story, a fable).
- "unsupported": (for a candidate of kind [claim], a product feature, policy, price, guarantee or result that is stated as fact and that the notes, request and brief do not give) a specific number, date, name, quantity, feature, price, policy, study, statistic or quote that the notes and the request do not give and that is not certain common knowledge (including product features, results attributed to a study or institution, and details of the person's own business).
Bias: keep correct well-known facts ("common"); mark "unsupported" only what you cannot stand behind. When the notes are empty, specifics about the person's product or business are unsupported.
For each beat that has at least one unsupported candidate, return "text": that beat's narration with ONLY the sentences that carry an unsupported candidate changed: remove the specific or state it generally ("for a long time", "many people", "recently") without inventing anything else. Keep every other sentence word for word, the same language, tone and person, and about the same length. Also remove any reference to "the notes", "our notes", "the research" or "the sources" as the writer's own material (not as real-world things).
Return ONLY JSON: {"beats":[{"beat":<number>,"verdicts":["notes|common|unsupported", ...one per candidate in order],"text":"<only when some verdict is unsupported>"}]}"""


def relevant_notes(texts: Sequence[str], narrations: Sequence[str], limit: int = MAX_NOTES_CHARS) -> str:
    """The notes paragraphs that share the most words with the narration being checked, up to `limit` characters, in their original order (a staged video has far
    more notes than fit: the model must see the paragraph that could support a candidate, not just the first 6,000 characters)."""
    full = "\n".join(t for t in texts if t)
    if len(full) <= limit:
        return full
    want = {w for n in narrations for w in re.findall(r"\w{4,}", norm(n))}
    paras = [p for p in full.split("\n") if p.strip()]
    scored = sorted(range(len(paras)), key=lambda i: -len(want & set(re.findall(r"\w{4,}", norm(paras[i])))))
    keep, used = set(), 0
    for i in scored:
        if used + len(paras[i]) + 1 > limit:
            continue
        keep.add(i)
        used += len(paras[i]) + 1
    return "\n".join(paras[i] for i in sorted(keep))


def _json_obj(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _safe_rewrite(old: str, new: str, flagged: List[Dict[str, str]], corpus: str, entities: bool) -> bool:
    """A rewrite is used only when it is clearly a trimmed version of the original: close in length, free of the flagged specifics, with no new unsupported specific."""
    from .plan import MIN_BEAT_WORDS

    if not isinstance(new, str) or not new.strip():
        return False
    n_old, n_new = len(old.split()), len(new.split())
    if n_new < max(MIN_BEAT_WORDS, int(0.6 * n_old)) or n_new > int(1.15 * n_old) + 1:
        return False
    nn = norm(new)
    if any(norm(c["text"]) in nn for c in flagged if c["kind"] not in ("leak", "claim")):
        return False
    old_set = {norm(c["text"]) for c in candidates(old, corpus, entities)}
    if any(norm(c["text"]) not in old_set for c in candidates(new, corpus, entities)):
        return False
    return not LEAK.search(new)


def ground_check(plan: Dict[str, Any], texts: Sequence[str], ask_small: Ask, *, request: str = "", brief: str = "", max_beats: int = MAX_BEATS_CHECKED, review_claims: bool = False) -> Dict[str, Any]:
    """Checks and repairs `plan["beats"]` narration in place. Returns the counts {beats, candidates, checked, flagged, repaired, unsupported, common, supported, skipped_on_screen,
    calls}. At most ONE model call; never raises (a failure keeps the original narration). `review_claims` (product and marketing videos) also has every beat without a
    candidate reviewed for product features, policies, prices or results that neither the notes nor the request give: the rules cannot see those, the model can."""
    stats: Dict[str, Any] = {"beats": 0, "candidates": 0, "checked": 0, "flagged": 0, "repaired": 0, "unsupported": 0, "common": 0, "supported": 0, "skipped_on_screen": 0, "leaks": 0, "calls": 0}
    try:
        beats = plan.get("beats") or []
        stats["beats"] = len(beats)
        corpus = " ".join(norm(t) for t in [request, brief, *texts] if t)
        entities = not FICTION.search(request or "")   # a story's characters are the writer's own, not claims
        items: List[Dict[str, Any]] = []
        for i, b in enumerate(beats):
            narr = str(b.get("narration") or "")
            if not narr.strip() or b.get("silent"):
                continue
            screen = _screen_text(b.get("scene") or {})
            cands = []
            for c in candidates(narr, corpus, entities):
                if c["kind"] != "quote" and norm(c["text"].split(" ")[0] if c["kind"] == "number" else c["text"]) in screen:
                    stats["skipped_on_screen"] += 1   # the screen shows it too: cutting it from the narration alone would break the sync
                    continue
                cands.append(c)
            leak = LEAK.search(narr)
            if leak:
                cands.append({"kind": "leak", "text": leak.group(0)})
                stats["leaks"] += 1
            if review_claims and not cands and len(narr.split()) >= 8:
                cands.append({"kind": "claim", "text": "any product feature, policy, price, guarantee or result stated as fact in this beat"})
            if cands:
                items.append({"i": i, "narration": narr, "cands": cands})
        stats["candidates"] = sum(len(x["cands"]) for x in items)
        if not items:
            return stats
        items.sort(key=lambda x: -len(x["cands"]))
        items = sorted(items[:max_beats], key=lambda x: x["i"])
        stats["checked"] = len(items)
        lines = []
        for x in items:
            real = [c for c in x["cands"] if c["kind"] != "leak"]
            lines.append(f"Beat {x['i'] + 1}\nNarration: {x['narration']}\nCandidates: " + ("; ".join(f"{k + 1}) [{c['kind']}] {c['text']}" for k, c in enumerate(real)) or "(none: only remove the reference to the notes)")
                         + ("\nAlso remove this reference to the writer's own notes: " + next(c["text"] for c in x["cands"] if c["kind"] == "leak") if len(real) != len(x["cands"]) else ""))
        user = (f"REQUEST: {request[:1500]}\n" + (f"BRIEF: {brief[:600]}\n" if brief else "") + f"\nRESEARCH NOTES (may be empty):\n{relevant_notes(texts, [x['narration'] for x in items]) or '(none)'}\n\n"
                + "BEATS TO CHECK:\n\n" + "\n\n".join(lines) + "\n\nReturn the JSON now.")
        stats["calls"] = 1
        d = _json_obj(ask_small(SYSTEM, user, 2400))
        by_beat = {int(r["beat"]): r for r in (d.get("beats") or []) if isinstance(r, dict) and str(r.get("beat", "")).lstrip("-").isdigit()}
        for x in items:
            r = by_beat.get(x["i"] + 1)
            if not r:
                continue
            real = [c for c in x["cands"] if c["kind"] != "leak"]
            verdicts = [str(v).lower() for v in (r.get("verdicts") or [])][:len(real)]
            for v in verdicts:
                if v in ("notes", "common", "unsupported"):
                    stats[{"notes": "supported"}.get(v, v)] += 1
            bad = [c for c, v in zip(real, verdicts) if v == "unsupported"]
            has_leak = len(real) != len(x["cands"])
            if bad or has_leak:
                stats["flagged"] += 1
                new = r.get("text")
                if _safe_rewrite(x["narration"], new, bad + ([c for c in x["cands"] if c["kind"] == "leak"] if has_leak else []), corpus, entities):
                    beats[x["i"]]["narration"] = new.strip()
                    stats["repaired"] += 1
    except Exception:   # a check is an improvement, never a requirement: the original script stands
        logging.exception("grounding check failed")
    logging.warning("GROUNDING flagged=%s repaired=%s candidates=%s checked=%s", stats["flagged"], stats["repaired"], stats["candidates"], stats["checked"])
    return stats


REPAIR_SYSTEM = """You repair scenes of an animated video plan that were rejected as invalid. For each item you get the beat's narration, the scene the writer proposed and the validation error. Return a corrected scene of the SAME type when possible (follow the scene docs exactly: required fields, minimum and maximum counts), built only from what the narration says, or another valid type from the docs that shows the same idea. Never add facts that the narration does not say.
Return ONLY JSON: {"scenes":[{"beat":<number>,"type":"<type>","props":{...}}]}

"""


def repair_scenes(plan: Dict[str, Any], rejects: Sequence[Dict[str, Any]], ask_small: Ask, docs: str, max_items: int = 4) -> Dict[str, int]:
    """ONE small-model call for up to `max_items` rejected scenes; a corrected scene must pass the same sanitiser as any scene. Returns {"rejected", "repaired", "calls"}."""
    from .plan import sanitize_props
    from .scenes import SCENE_TYPES

    stats = {"rejected": len(rejects), "repaired": 0, "calls": 0}
    try:
        beats = plan.get("beats") or []
        todo = []
        for r in rejects:
            j = next((k for k, b in enumerate(beats) if b.get("narration") == r.get("narration") and (b.get("scene") or {}).get("type") == "title"), None)
            if j is not None:
                todo.append((j, r))
        todo = todo[:max_items]
        if not todo:
            return stats
        user = "\n\n".join(f"Beat {j + 1}\nNarration: {r['narration']}\nProposed scene: {json.dumps(r.get('scene'), ensure_ascii=False)[:900]}\nError: {r.get('error')}" for j, r in todo)
        stats["calls"] = 1
        d = _json_obj(ask_small(REPAIR_SYSTEM + docs, user, 1800))
        for s in d.get("scenes") or []:
            if not isinstance(s, dict) or not str(s.get("beat", "")).isdigit():
                continue
            j = int(s["beat"]) - 1
            if j not in {k for k, _ in todo} or s.get("type") not in SCENE_TYPES or not isinstance(s.get("props"), dict):
                continue
            try:
                props = sanitize_props(s["type"], s["props"])
            except (ValueError, TypeError, AttributeError):
                continue
            beats[j]["scene"] = {"type": s["type"], "props": props}
            stats["repaired"] += 1
    except Exception:
        logging.exception("scene repair failed")
    logging.warning("SCENE_REPAIR rejected=%s repaired=%s", stats["rejected"], stats["repaired"])
    return stats
