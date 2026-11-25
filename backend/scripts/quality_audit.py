#!/usr/bin/env python3
"""Quality audit of the CURRENT plan stage (docs/PIPELINE_V3.md section 5).

Runs the SAME code as production up to the saved plan (`engine.director.direct` with the web provider and ask_tools wired exactly as
`handlers/plan_handler.py` wires them: Haiku for the small calls and the research agent, Sonnet for the script; Tavily key from SSM). No TTS,
no images, no rendering. For each prompt of docs/audit/prompts.json it saves a JSON result under docs/audit/2026-11-25/runs/, then scores it
with deterministic rules (free) and an LLM judge (Claude Sonnet through the same Bedrock helpers).

  AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/quality_audit.py [--limit N] [--only ID ...] [--judge-only] [--rejudge]
                                                                            [--workers 3] [--max-cost 12] [--no-judge]
Resumable: a prompt with a finished result file is skipped (judging is resumable too). Stops starting work when the cap would be exceeded.
Only the QA account is allowed (the script refuses to run against another profile).
"""
import argparse
import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
AUDIT_DIR = os.path.join(ROOT, "docs", "audit")
PROMPTS_PATH = os.path.join(AUDIT_DIR, "prompts.json")
RUNS_DIR = os.environ.get("AUDIT_RUNS_DIR") or os.path.join(AUDIT_DIR, "2026-11-25", "runs")   # --runs-dir / AUDIT_RUNS_DIR: where results are saved and read
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

WEB_SEARCH_COST_USD = 0.008   # same constant as plan_handler (Tavily basic search)
WORDS_PER_S = 2.4             # plan.SPOKEN_WORDS_PER_S
BEAT_OVERHEAD_S = 0.95

# ============================================================================== rules (pure, deterministic, unit-tested)
STOP = set("""the a an and or but of to in on at for with by from as is are was were be been it its this that these those you your we our they their he she his her i
not no so if then than too very can will just also into over about more most how what why when where who which do does did has have had one all any some there here
el la los las un una unos unas y o pero de del al en con por para como es son era fue ser se su sus lo le les que qué cómo por qué cuando donde quien cuál mi tu tus nos
más muy no si ya también este esta estos estas eso esto hay han ha he hemos puede pueden""".split())
ES_WORDS = set("el la los las de que y en un una es por con para se su al lo como más pero sus le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante".split())
EN_WORDS = set("the of and to in is that it for as with was on are by this be at or from an have not but they which you we one all their has been more his her can will".split())
MONTHS = set("january february march april may june july august september october november december enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())
DAYS = set("monday tuesday wednesday thursday friday saturday sunday lunes martes miércoles miercoles jueves viernes sábado sabado domingo".split())
CAP_SKIP = MONTHS | DAYS | {"i", "ok", "yes", "no", "sí"}
GREETING = re.compile(r"^\W*(hello|hi|hey|welcome|good (morning|evening|afternoon)|hola|bienvenid|buenas|saludos)\b", re.I)
CLOSE_GENERIC = re.compile(r"(thanks? for watching|thank you for watching|see you (next|in|soon)|don'?t forget to (like|subscribe)|like and subscribe|gracias por (ver|vernos|acompañarnos|mirar)|hasta la próxima|nos vemos|suscr[ií]be)", re.I)


def words(text: str) -> List[str]:
    return re.findall(r"[\w'’]+", text or "", flags=re.U)


def norm(text: str) -> str:
    """Lowercase, accents stripped, thousands separators removed between digits: the form used to compare narration with notes."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"(?<=\d)[.,   ](?=\d{3}\b)", "", t)
    return t


def narration_of(beats: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(str(b.get("narration") or "") for b in beats)


def detect_lang(text: str) -> str:
    ws = [w.lower() for w in words(text)]
    es, en = sum(w in ES_WORDS for w in ws), sum(w in EN_WORDS for w in ws)
    if re.search(r"[¿¡ñáéíóú]", text or "") and es >= en * 0.6:
        return "es"
    return "es" if es > en else "en"


def length_fit(beats: Sequence[Dict[str, Any]], expected_words: int, expected_beats: int) -> Dict[str, Any]:
    n_words = sum(len(words(b.get("narration") or "")) for b in beats)
    ratio = n_words / expected_words if expected_words else 0.0
    return {"words": n_words, "expected_words": expected_words, "ratio": round(ratio, 3), "beats": len(beats), "expected_beats": expected_beats,
            "est_speech_s": round(n_words / WORDS_PER_S + BEAT_OVERHEAD_S * len(beats), 1),
            "flag_short": ratio < 0.9, "flag_long": ratio > 1.15, "flag_few_beats": len(beats) < max(3, expected_beats * 0.6)}


def hook_and_close(beats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    first = str((beats[0].get("narration") if beats else "") or "")
    last = str((beats[-1].get("narration") if beats else "") or "")
    # the first spoken beat (a title card can come first and be silent)
    spoken = [str(b.get("narration") or "") for b in beats if (b.get("narration") or "").strip()]
    first = spoken[0] if spoken else first
    last = spoken[-1] if spoken else last
    first_sentence = re.split(r"(?<=[.!?])\s+", first.strip())[0] if first.strip() else ""
    return {"hook_words": len(words(first)), "hook_greeting": bool(GREETING.search(first)), "hook_question": bool("?" in first_sentence or first.strip().startswith("¿")),
            "hook_long": len(words(first)) > 40, "close_words": len(words(last)), "close_generic": bool(CLOSE_GENERIC.search(last)), "close_short": len(words(last)) < 8,
            "hook_text": first[:200], "close_text": last[:200]}


def scene_variety(beats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    types = [str((b.get("scene") or {}).get("type") or "?") for b in beats]
    c = Counter(types)
    run = best = 0
    prev = None
    for t in types:
        run = run + 1 if t == prev else 1
        best, prev = max(best, run), t
    n = len(types) or 1
    entropy = -sum((v / n) * math.log2(v / n) for v in c.values()) if types else 0.0
    top, top_n = (c.most_common(1) or [("", 0)])[0]
    return {"distinct": len(c), "counts": dict(c), "max_run": best, "entropy": round(entropy, 2), "top_type": top, "top_share": round(top_n / n, 2),
            "flag_low_variety": len(types) >= 6 and (len(c) < 3 or top_n / n > 0.5), "flag_run": best >= 3}


def extract_numbers(text: str) -> List[str]:
    """Numbers worth checking: not tiny integers (0 to 10) unless a percentage; thousands separators removed."""
    out = []
    for m in re.finditer(r"(?<![\w.])(\d[\d.,   ]*\d|\d)(\s?%)?", text or ""):
        raw = m.group(1)
        token = re.sub(r"(?<=\d)[.,   ](?=\d{3}\b)", "", raw)
        if re.fullmatch(r"\d+", token) and int(token) <= 10 and not m.group(2):
            continue
        out.append(token.replace(" ", ""))
    return out


def extract_entities(text: str) -> List[str]:
    """Capitalised names that are not at the start of a sentence (runs of capitalised words kept together)."""
    ents = []
    for sent in re.split(r"(?<=[.!?:¿¡\n])\s+|^", text or ""):
        toks = re.findall(r"[\w'’\-]+", sent, flags=re.U)
        run: List[str] = []
        for i, t in enumerate(toks):
            cap = t[:1].isupper() and not t.isupper() or (t.isupper() and len(t) > 1 and t.isalpha())
            if cap and i > 0 and t.lower() not in CAP_SKIP and t.lower() not in STOP:
                run.append(t)
            else:
                if run:
                    ents.append(" ".join(run))
                run = []
        if run:
            ents.append(" ".join(run))
    return ents


def grounding(narr: str, notes: str, prompt: str = "") -> Dict[str, Any]:
    """Numbers and names in the narration that appear nowhere in the research notes or the user's own words. An UPPER bound of invention: a
    well-known fact the model knows by heart (Newton, 1969) also counts as ungrounded here; the judge and the human decide which are errors."""
    corpus = norm(notes) + " " + norm(prompt)
    nums = sorted(set(extract_numbers(narr)))
    ents = sorted(set(extract_entities(narr)), key=str.lower)
    bad_nums = [n for n in nums if not re.search(r"(?<!\d)" + re.escape(norm(n)) + r"(?!\d)", corpus)]
    bad_ents = []
    for e in ents:
        ne = norm(e)
        if ne in corpus:
            continue
        if all(t in corpus for t in re.findall(r"\w+", ne)):
            continue
        bad_ents.append(e)
    total = len(nums) + len(ents)
    return {"numbers": len(nums), "ungrounded_numbers": bad_nums, "entities": len(ents), "ungrounded_entities": bad_ents,
            "ungrounded_share": round((len(bad_nums) + len(bad_ents)) / total, 3) if total else 0.0,
            "ungrounded_number_share": round(len(bad_nums) / len(nums), 3) if nums else 0.0, "no_notes": not notes.strip()}


def repeated_phrases(narr: str, n: int = 4, min_count: int = 2) -> List[Dict[str, Any]]:
    ws = [norm(w) for w in words(narr)]
    grams = Counter()
    for i in range(len(ws) - n + 1):
        g = ws[i:i + n]
        if sum(w in STOP or w.isdigit() for w in g) >= n - 1:
            continue
        grams[" ".join(g)] += 1
    out = [(g, c) for g, c in grams.most_common() if c >= min_count]
    kept: List[Any] = []
    for g, c in out:   # drop grams that are a sub-gram of a kept longer repeat of the same count
        if not any(g in k and c <= kc for k, kc in kept):
            kept.append((g, c))
    return [{"phrase": g, "count": c} for g, c in kept[:6]]


def silent_beats(beats: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    s = [b.get("id") for b in beats if not (b.get("narration") or "").strip()]
    return {"silent": len(s), "silent_share": round(len(s) / len(beats), 2) if beats else 0.0}


def warning_kinds(warnings: Sequence[str]) -> Dict[str, int]:
    kinds = Counter()
    for w in warnings:
        lw = w.lower()
        kind = ("length" if lw.startswith("length") else "scene_replaced" if "scene replaced" in lw else "coverage" if ("never mention" in lw or "narration" in lw and "item" in lw)
                else "image_budget" if "image" in lw else "silence" if "silen" in lw else "section" if lw.startswith("section") else "other")
        kinds[kind] += 1
    return dict(kinds)


def source_use(research: Dict[str, Any], cited: int, notes_len: int) -> Dict[str, Any]:
    fetched = int(research.get("n_fetched") or 0)
    return {"cited": cited, "fetched": fetched, "notes_len": notes_len, "flag_thin_notes": notes_len < 1500,
            "flag_no_sources": cited == 0, "flag_web_no_sources": research.get("mode") == "web" and cited == 0}


def time_sensitivity(prompt: str, tagged: bool, mode: str, cue_regex: Any = None) -> Dict[str, Any]:
    cue = bool(cue_regex.search(prompt)) if cue_regex else False
    needs = tagged or cue
    return {"tagged": tagged, "cue": cue, "needs_web": needs, "flag_no_web": needs and mode != "web"}


def apply_rules(run: Dict[str, Any], expected_words: int, expected_beats: int, cue_regex: Any = None) -> Dict[str, Any]:
    plan = run.get("plan") or {}
    beats = plan.get("beats") or []
    narr = narration_of(beats)
    notes = run.get("notes") or ""
    res = run.get("research") or {}
    r: Dict[str, Any] = {"length": length_fit(beats, expected_words, expected_beats), **{"hook_close": hook_and_close(beats)}, "variety": scene_variety(beats),
                         "grounding": grounding(narr, notes, run.get("prompt", "")), "repeats": repeated_phrases(narr), "silent": silent_beats(beats),
                         "warnings": warning_kinds(run.get("warnings") or []),
                         "sources": source_use(res, len(plan.get("sources") or []), len(notes)),
                         "time": time_sensitivity(run.get("prompt", ""), bool(run.get("time_sensitive")), res.get("mode", ""), cue_regex)}
    got, want = detect_lang(narr), run.get("language") or "en"
    r["language"] = {"expected": want, "detected": got, "flag_wrong": got != want}
    r["question_beats"] = round(sum(1 for b in beats if str(b.get("narration") or "").strip().endswith("?")) / len(beats), 2) if beats else 0.0
    flags = []
    L, H, V, G, S, T = r["length"], r["hook_close"], r["variety"], r["grounding"], r["sources"], r["time"]
    for cond, name in [(L["flag_short"], "too_short"), (L["flag_long"], "too_long"), (L["flag_few_beats"], "few_beats"), (H["hook_greeting"], "hook_greeting"),
                       (H["hook_long"], "hook_long"), (H["close_generic"], "close_generic"), (H["close_short"], "close_short"), (V["flag_low_variety"], "low_scene_variety"),
                       (V["flag_run"], "scene_run_3plus"), (G["ungrounded_share"] > 0.5 and not G["no_notes"], "ungrounded_over_half"), (G["ungrounded_number_share"] > 0.5 and G["numbers"] >= 3, "numbers_mostly_ungrounded"),
                       (S["flag_thin_notes"], "thin_notes"), (S["flag_no_sources"], "no_sources_cited"), (T["flag_no_web"], "time_sensitive_without_web"),
                       (bool(r["repeats"]), "repeated_phrase"), (r["silent"]["silent_share"] > 0.3, "many_silent_beats"), (r["language"]["flag_wrong"], "wrong_language"),
                       (r["warnings"].get("coverage", 0) > 0, "narration_screen_mismatch"), (r["warnings"].get("scene_replaced", 0) > 0, "scenes_replaced")]:
        if cond:
            flags.append(name)
    r["flags"] = flags
    return r


# ============================================================================== judge
DIMS = [("accuracy", "Factual accuracy and grounding"), ("coverage", "Coverage and depth for the stated length"), ("structure", "Structure and narrative arc"),
        ("hook_ending", "Hook and ending"), ("tone", "Tone and audience fit"), ("visuals", "Visual plan variety and relevance"), ("originality", "Originality (not generic filler)"),
        ("instructions", "Instruction following"), ("language", "Language quality")]

JUDGE_SYSTEM = """You are a strict, experienced editor reviewing the SCRIPT of a narrated explainer video made by an AI. You read the viewer's request, the research notes the writer was given, and the finished script beat by beat (each beat = narration plus the scene shown on screen). Judge the script only; you cannot see the rendered video.

Score each dimension from 1 to 5. Be harsh: LLM judges are usually too generous, and a score of 4 or 5 must be earned. Anchors:
 5 = publishable by a professional channel as is; nothing a careful editor would change. Rare (about 1 script in 10).
 4 = good; one or two small weaknesses a viewer would hardly notice.
 3 = acceptable but generic or uneven; a viewer would finish it and learn little that they could not guess, or notice clear flaws.
 2 = weak: shallow, repetitive, partly wrong or off-brief; most viewers would be disappointed.
 1 = unusable: wrong, off-topic, wrong language, or mostly filler.
Default to 3 when unsure, not 4.

Dimensions:
- accuracy: every number, date, name and claim is correct (use your own knowledge as well as the notes) and traceable to the notes or common knowledge; penalise invented specifics, wrong facts, and confident claims on shaky ground, especially for time-sensitive topics (the notes carry the dates; the script must not rely on stale memory). 1 wrong key fact caps this at 3.
- coverage: for the stated length, are the points a good answer must contain present, with depth and at least one non-obvious fact or example per section? Compare with the 'what a great video contains' note.
- structure: clear order, sections that build, transitions, one takeaway, no repetition, pacing suitable for the length.
- hook_ending: does the first spoken line create curiosity or tension (not a greeting, not a bland definition), and does the ending land (a takeaway or image, not 'thanks for watching' or a bare summary)?
- tone: right voice and register for the audience and topic (kids, beginners, professionals, a story needs literary voice, a news piece a neutral one).
- visuals: do the scene types vary sensibly and does each scene show what the narration says (charts only for real numbers, lists matching what is spoken, images matching the content)? Judge from the scene props given.
- originality: concrete, surprising, specific vs generic filler and cliches ('in today's fast-paced world', 'it is important to note').
- instructions: does it do everything the request asked (length, audience, requested points, format, language, number of items) and nothing contrary?
- language: grammar, fluency, natural phrasing in the script's language.

Notes on what you see: scenes of type 'title', 'kinetic_text', 'stat', 'quote' and similar show text on screen; 'image' and 'gallery' show stock photos found with the given image_queries (you cannot see them, so judge only whether the queries fit the narration). Your own knowledge may be older than the notes for events after 2025: for recent events trust the notes over memory. A claim that is absent from the notes but that you KNOW to be true is not an error (mention it in wrong_facts only as 'unverified, but true' if it matters); a claim that contradicts the notes or that you know is false is an error.

Rules for evidence: for EVERY defect you list you must quote the exact narration words (or the scene title) that show it, in the field "quote". If you cannot quote it, do not list it. List at most 8 concrete defects, most severe first; list none if there are none. Do not praise in the defects list. For each score give a one-line reason that cites something concrete.

Return ONLY this JSON (no markdown):
{"scores": {"accuracy": {"score": 1-5, "reason": "..."}, "coverage": {...}, "structure": {...}, "hook_ending": {...}, "tone": {...}, "visuals": {...}, "originality": {...}, "instructions": {...}, "language": {...}},
 "defects": [{"dimension": "...", "severity": "minor|major|critical", "quote": "exact words", "issue": "what is wrong and why", "beat": <1-based beat number or null>}],
 "missing": ["important points a great video on this request would contain that this script lacks"],
 "wrong_facts": ["each factual error or doubtful claim, with the corrected fact if you know it"],
 "would_publish": true|false,
 "summary": "two sentences"}"""

JUDGE_ES_ADDENDUM = """

THIS SCRIPT IS IN SPANISH. Also judge its naturalness as spoken Spanish, as a native speaker would: calques from English ('es importante notar que', 'en el final del día'), literal translations of idioms, anglicisms, unnatural word order, overly formal or stiff register for narration, repeated connectors, mixed 'tú/usted', regional words that only suit one country when a neutral choice exists (the request tells the region), awkward numbers or units, and punctuation (¿ ¡). Put this in the 'language' score, and add to the JSON an extra key "spanish": {"naturalness": 1-5, "issues": [{"quote": "exact words", "problem": "...", "better": "a natural rewrite"}]} with at most 6 issues. Natural, idiomatic Spanish that a native speaker would not notice is a 4; a 5 is rare."""


def judge_user(run: Dict[str, Any]) -> str:
    plan = run.get("plan") or {}
    lines = []
    for i, b in enumerate(plan.get("beats") or [], 1):
        sc = b.get("scene") or {}
        props = sc.get("props") or {}
        keep = {k: v for k, v in props.items() if k not in ("ken_burns", "accent", "style", "icons", "emphasis", "hold")}   # what is on screen; look-and-feel props omitted
        ch = f" [chapter: {b['chapter']}]" if b.get("chapter") else ""
        lines.append(f"Beat {i}{ch}\n  scene: {sc.get('type')} {json.dumps(keep, ensure_ascii=False)[:600]}\n  narration: {b.get('narration', '')}")
    srcs = "\n".join(f"- {s.get('title')} ({s.get('publisher', '')}) {s.get('url', '')}" for s in (plan.get("sources") or [])) or "(none cited)"
    res = run.get("research") or {}
    notes = (run.get("notes") or "")[:9000]
    return (f"REQUEST: {run['prompt']}\nRequested language: {'Spanish' if run['language'] == 'es' else 'English'}. Target length: {run['minutes']} minute(s) "
            f"(about {run['rules']['length']['expected_words']} words). Viewer region: {run['options'].get('region')}. Today: 2026-11-25.\n"
            f"What a great video on this request contains (reviewer's note): {run['great']}\n"
            f"Research mode used: {res.get('mode')} ({res.get('searches', 0)} searches, {res.get('reads', 0)} page reads). Notes length: {len(run.get('notes') or '')} chars.\n\n"
            f"RESEARCH NOTES GIVEN TO THE WRITER (may be empty or truncated):\n{notes or '(none)'}\n\nSOURCES CITED BY THE SCRIPT:\n{srcs}\n\n"
            f"SCRIPT. Title: {plan.get('title')}\n" + "\n".join(lines) + "\n\nReturn the JSON now.")


def parse_json(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        raise ValueError("no JSON in judge answer")
    return json.loads(m.group(0))


def judge_run(run: Dict[str, Any], complete) -> Dict[str, Any]:
    system = JUDGE_SYSTEM + (JUDGE_ES_ADDENDUM if run["language"] == "es" else "")
    last = None
    for _ in range(2):
        text, meta = complete(system, judge_user(run))
        try:
            j = parse_json(text)
            scores = {k: int(j["scores"][k]["score"]) for k, _ in DIMS}
            j["mean"] = round(sum(scores.values()) / len(scores), 2)
            j["cost_usd"] = meta["cost_usd"]
            j["tokens"] = [meta["tokens_in"], meta["tokens_out"]]
            return j
        except (ValueError, KeyError, TypeError) as e:
            last = e
    raise ValueError(f"judge answer unusable: {last}")


# ============================================================================== running the plan stage
class Spend:
    def __init__(self, cap: float):
        self.cap, self.lock, self.total, self.inflight = cap, threading.Lock(), 0.0, 0

    def add(self, usd: float):
        with self.lock:
            self.total += usd

    def try_start(self, reserve: float) -> bool:
        with self.lock:
            if self.total + reserve * (self.inflight + 1) > self.cap:
                return False
            self.inflight += 1
            return True

    def done(self):
        with self.lock:
            self.inflight -= 1


NOTE_MARKERS = ("Grounding notes (may be empty):\n", "Background notes on the topic (may be empty):\n", "Research notes for this section (may be empty; use them for facts and numbers):\n")


def extract_notes(users: Sequence[str]) -> str:
    """The research text the writer saw, recovered from the prompts it was sent (director.direct does not return it)."""
    seen, parts = set(), []
    for u in users:
        for mk in NOTE_MARKERS:
            if mk in u:
                body = u.split(mk, 1)[1]
                body = re.split(r"\n\nReturn the JSON", body)[0].strip()
                if body and not body.startswith("(none"):   # "(none)" and the "(none) No sources were found..." note of QUALITY_FIXES are not notes
                    # section prompts put their own research first, then the shared notes: keep each paragraph block once
                    for chunk in re.split(r"\n\n(?=## |\[S\d+\]|Source|SOURCE)", body):
                        key = chunk[:200]
                        if key not in seen:
                            seen.add(key)
                            parts.append(chunk)
    return "\n\n".join(parts)


def web_tools(spent_cb):
    from common.secrets import get_secret_param
    from engine import llm, websearch
    key = get_secret_param("/videomk/tavily_api_key", quiet=True)
    if not key:
        return None, None

    def ask_tools(system, messages, tools, **kw):
        blocks, stop, meta = llm.complete_tools(system, messages, tools, model=llm.REVIEW_MODEL, **kw)   # as in plan_handler._web_tools
        spent_cb("research", meta["cost_usd"], meta)
        return blocks, stop, meta

    return websearch.TavilyProvider(key), ask_tools


def run_prompt(item: Dict[str, Any], spend: Spend) -> Dict[str, Any]:
    from engine import director, llm, plan as plan_mod, researcher
    minutes = float(item["minutes"])
    region = "ES" if item["language"] == "es" else "US"
    cost: Dict[str, float] = {}
    calls = Counter()
    tokens = Counter()
    users: List[str] = []
    marks: Dict[str, float] = {}
    lock = threading.Lock()

    def add(part: str, usd: float, meta: Optional[Dict[str, Any]] = None):
        with lock:
            cost[part] = cost.get(part, 0.0) + usd
            if meta:
                tokens["in"] += meta.get("tokens_in", 0)
                tokens["out"] += meta.get("tokens_out", 0)
        spend.add(usd)

    def ask_small(system, user, max_tokens=120):
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        calls["small"] += 1
        add("script_small", meta["cost_usd"], meta)
        return text

    def ask_big(system, user):
        with lock:
            marks.setdefault("first_big", time.time())
            users.append(user)
        text, meta = llm.complete(system, user, max_tokens=plan_mod_max_tokens(minutes))
        calls["big"] += 1
        if meta.get("stop_reason") == "max_tokens":
            calls["big_cut_off"] += 1
        add("script_big", meta["cost_usd"], meta)
        return text

    def plan_mod_max_tokens(m):   # same formula as plan_handler.plan_max_tokens
        return int(min(32000, 6000 + 2600 * float(m)))

    provider, ask_tools = web_tools(lambda part, usd, meta: (calls.update(["tools"]), add(part, usd, meta)))
    t0 = time.time()
    out: Dict[str, Any] = {k: item[k] for k in ("id", "category", "language", "difficulty", "prompt", "great")}
    out.update({"minutes": minutes, "time_sensitive": item.get("time_sensitive", False), "options": {"target_minutes": minutes, "language_passed": None, "region": region, "theme": None,
                "max_images_per_minute": 10.0, "web_research": bool(provider)}, "started": time.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        r = director.direct(item["prompt"], minutes=minutes, ask_small=ask_small, ask_big=ask_big, language=None, region=region, web_provider=provider, ask_tools=ask_tools,
                            max_images_per_minute=10.0, music_tracks=None)
    except Exception as e:   # a crash is a finding, not a reason to stop the audit
        out.update({"error": f"{type(e).__name__}: {str(e)[:300]}", "plan": None, "research": {}, "warnings": [], "notes": "",
                    "cost": {**cost, "total": round(sum(cost.values()), 5)}, "timings": {"total_s": round(time.time() - t0, 1)}, "calls": dict(calls)})
        return out
    info = r.get("research") or {}
    api = float(info.get("searches", 0)) * WEB_SEARCH_COST_USD
    add("search_api", api)
    total_s = time.time() - t0
    plan = r.get("plan") or {}
    notes = extract_notes(users)
    research = {k: info.get(k) for k in ("mode", "decided", "reason", "queries", "searches", "reads", "iterations", "seconds", "error", "fallback", "section_searches", "skills", "staged", "escalated", "fetch_errors", "fetch_errors_n", "grounding", "scene_repair")}
    research.update({"notes_len": len(notes), "n_sources": len(plan.get("sources") or []), "n_fetched": len(r.get("fetched") or []), "fetched": r.get("fetched"),
                     "research_agent_cost_usd": info.get("cost_usd")})
    first_big = marks.get("first_big", t0 + total_s)
    out.update({"legit": r.get("legit"), "reason": r.get("reason"), "research": research, "warnings": r.get("warnings") or [], "notes": notes,
                "plan": {k: plan.get(k) for k in ("title", "description", "language", "mood", "theme", "voices", "beats", "sources", "skills", "region")} if plan else None,
                "timings": {"total_s": round(total_s, 1), "before_first_script_call_s": round(first_big - t0, 1), "script_s": round(t0 + total_s - first_big, 1)},
                "cost": {**{k: round(v, 5) for k, v in cost.items()}, "total": round(sum(cost.values()), 5)}, "calls": dict(calls), "tokens": dict(tokens)})
    return out


def score_run(run: Dict[str, Any]) -> None:
    from engine import plan as plan_mod, researcher
    if not run.get("plan"):
        return
    exp_w = plan_mod.expected_words(run["minutes"])
    exp_b = plan_mod.expected_beats(run["minutes"])
    run["rules"] = apply_rules(run, exp_w, exp_b, researcher._RECENT)
    # coverage problems straight from sync (the same function production uses to flag screen/narration mismatch)
    try:
        from engine import sync as sync_mod
        run["rules"]["mismatch_scenes"] = sync_mod.coverage_problems(run["plan"]["beats"])
    except Exception:
        run["rules"]["mismatch_scenes"] = []


def load_runs(ids: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    out = []
    if os.path.isdir(RUNS_DIR):
        for fn in sorted(os.listdir(RUNS_DIR)):
            if fn.endswith(".json") and (not ids or fn[:-5] in ids):
                with open(os.path.join(RUNS_DIR, fn), encoding="utf-8") as f:
                    out.append(json.load(f))
    return out


def save_run(run: Dict[str, Any]) -> None:
    os.makedirs(RUNS_DIR, exist_ok=True)
    tmp = os.path.join(RUNS_DIR, f".{run['id']}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(RUNS_DIR, f"{run['id']}.json"))


def spent_so_far() -> float:
    t = 0.0
    for r in load_runs():
        t += float((r.get("cost") or {}).get("total", 0)) + float((r.get("judge") or {}).get("cost_usd", 0))
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", action="append")
    ap.add_argument("--judge-only", action="store_true", help="only judge saved runs that have no judgement yet")
    ap.add_argument("--rejudge", action="store_true", help="judge again even if a judgement exists (with --judge-only)")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--runs-dir", help="folder for the results (default docs/audit/2026-11-25/runs); a new folder starts a new audit with its own spend count")
    ap.add_argument("--max-cost", type=float, default=12.0, help="hard cap in USD for the whole audit (existing results count)")
    ap.add_argument("--reserve", type=float, default=0.60, help="cost reserved per prompt in flight before starting another")
    args = ap.parse_args()

    if args.runs_dir:
        global RUNS_DIR
        RUNS_DIR = os.path.abspath(args.runs_dir)
    profile = os.environ.setdefault("AWS_PROFILE", "qa")
    if profile != "qa":
        sys.exit(f"refusing to run with AWS_PROFILE={profile}: the audit may only use the QA account (profile qa)")
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])
    os.environ.setdefault("BEDROCK_REGION", "eu-west-1")
    from engine import llm

    with open(PROMPTS_PATH, encoding="utf-8") as f:
        prompts = json.load(f)
    if args.only:
        prompts = [p for p in prompts if p["id"] in args.only]
    spend = Spend(args.max_cost)
    spend.total = spent_so_far()
    print(f"already spent in saved results: ${spend.total:.3f} (cap ${args.max_cost})")
    t_start = time.time()

    def judge_it(run):
        def complete(system, user):
            text, meta = llm.complete(system, user, model=llm.PRIMARY_MODEL, effort="medium", max_tokens=5000)
            spend.add(meta["cost_usd"])
            return text, meta
        run["judge"] = judge_run(run, complete)

    def work(item):
        path = os.path.join(RUNS_DIR, f"{item['id']}.json")
        if args.judge_only:
            run = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
            if not run or not run.get("plan") or (run.get("judge") and not args.rejudge):
                return item["id"], "skip", 0.0
            for k in ("great", "category", "language", "prompt"):
                run[k] = item[k]
            score_run(run)
        elif os.path.exists(path):
            run = json.load(open(path, encoding="utf-8"))
            if run.get("judge") or args.no_judge or not run.get("plan"):
                return item["id"], "skip", 0.0
        else:
            run = run_prompt(item, spend)
            score_run(run)
            save_run(run)
        if not args.no_judge and run.get("plan"):
            try:
                judge_it(run)
            except Exception as e:
                run["judge_error"] = str(e)[:300]
        save_run(run)
        return item["id"], run.get("error") or "ok", float(run["cost"]["total"]) if run.get("cost") else 0.0

    todo = prompts[:args.limit] if args.limit else prompts
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {}
        pending = list(todo)
        done_n = 0
        while pending or futs:
            while pending and len(futs) < args.workers:
                item = pending[0]
                if not spend.try_start(args.reserve):
                    print(f"COST CAP: ${spend.total:.2f} spent, cannot start another prompt within ${args.max_cost}. Stopping.")
                    pending = []
                    break
                pending.pop(0)
                futs[ex.submit(work, item)] = item
            if not futs:
                break
            for fut in as_completed(list(futs)):
                item = futs.pop(fut)
                spend.done()
                done_n += 1
                try:
                    pid, status, cost = fut.result()
                except Exception as e:
                    pid, status, cost = item["id"], f"CRASH {type(e).__name__}: {e}", 0.0
                print(f"[{done_n}/{len(todo)}] {pid:8s} {status:10s} run ${cost:.3f}   running total ${spend.total:.3f}   {time.time() - t_start:.0f}s", flush=True)
                break
    print(f"\nDONE. total spent ${spend.total:.3f} of ${args.max_cost}")


if __name__ == "__main__":
    main()
