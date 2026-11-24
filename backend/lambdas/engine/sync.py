"""Make what appears on screen arrive when it is said.

The timeline used to reveal list items, diagram nodes, chart bars, timeline events and gallery photos on a fixed schedule spread over the scene, whatever the
narrator was saying. Now every revealable item is *anchored* to the narration word that introduces it:

  words (from the audio: engine/align.py)  +  the item's own text  ->  the moment it is first mentioned  ->  reveal just before it.

Items the narration never names fall back to even spacing between their neighbours (or across the spoken part of the beat), never to the old fixed schedule.
No model is called: matching is on normalised content words, so it costs nothing and runs in a few milliseconds.
`report()` measures the result on a finished timeline (which items were anchored, how far each reveal is from its mention), which is the cheap alignment check.
"""
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]

LEAD_IN_S = 0.15        # a reveal starts this long before the word that names it, so the picture is there when the word is heard
MIN_GAP_S = 0.30        # two reveals never start closer than this
GALLERY_AFTER_S = 0.15  # a gallery photo is fully in this long after its word
MIN_SHOT_S = 1.6        # no gallery photo is shown for less than this
MAX_ITEMS = 8

_STOP = set("""a an the and or but of to in on at for from by with without as is are was were be been being it its this that these those there here
which who whom what when where why how than then so if not no yes can could will would should may might do does did done have has had having into over under
about between through during before after above below up down out off again further once only own same such very just also more most other some any each both few
all my your our their his her him them us we you i me he she they one two three four five six seven eight nine ten
el la los las un una unos unas y o pero de del al en con sin por para como es son fue eran ser ha han he hemos tiene tienen que quien cual cuando donde
porque asi si no se su sus lo le les me te nos mi tu muy mas menos otro otra otros otras cada todo toda todos todas este esta estos estas ese esa eso""".split())


def norm(token: str) -> str:
    t = unicodedata.normalize("NFKD", token.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    if re.search(r"\d", t):                                     # "73%", "$4.2B", "1,200" and the spoken "73", "4.2", "1200" are the same token
        return re.sub(r"[^0-9.]", "", t.replace(",", "")).strip(".")
    t = re.sub(r"[^a-z]", "", t)
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t


def content_tokens(text: str) -> List[str]:
    out = []
    for raw in re.findall(r"[^\s/]+", text):
        n = norm(raw)
        if not n:
            continue
        if re.search(r"\d", n):
            out.append(n)
        elif n not in _STOP and len(n) >= 3:
            out.append(n)
    return out


def find_mentions(anchors: Sequence[str], words: Sequence[Word], min_share: float = 0.5) -> List[Optional[int]]:
    """For each anchor text, the index of the narration word where it is first mentioned (None if it never is). Anchors are matched in order: a later
    anchor is looked for after the previous one first, because narrators list things in the order the screen shows them."""
    narr = [norm(w[0]) for w in words]
    found: List[Optional[int]] = []
    prev = -1
    for text in anchors:
        toks = content_tokens(text)
        if not toks:
            found.append(None)
            continue
        need = max(1, math.ceil(len(toks) * min_share))
        best: Optional[Tuple[int, int, int]] = None   # (score, -span, index): most item words, then the tightest cluster, then the earliest
        for lo, hi in ((prev + 1, len(narr)), (0, prev + 1)):
            for p in range(lo, hi):
                if narr[p] not in toks:
                    continue
                window = narr[p: p + len(toks) + 4]
                hits = [k for k, w in enumerate(window) if w in toks]
                score = len({window[k] for k in hits})
                if score >= need:
                    cand = (score, -max(hits), p)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
            if best:
                break                                    # found after the previous anchor: never look earlier
        if best and best[2] > prev:
            found.append(best[2])
            prev = best[2]
        else:
            found.append(None)                           # only mentioned out of order, or not at all: it will be interpolated
    return found


def _spread(n: int, lo: float, hi: float) -> List[float]:
    if n <= 0:
        return []
    if n == 1:
        return [lo]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def anchor_times(anchors: Sequence[str], words: Sequence[Word], scene_dur: float, *, after: float = -LEAD_IN_S, min_share: float = 0.5) -> Tuple[List[float], List[Optional[int]]]:
    """Scene-local reveal time for each anchor: the mention (+`after`) when found, interpolated otherwise, monotonic with a minimum gap."""
    n = len(anchors)
    if not words:
        return _spread(n, scene_dur * 0.1, scene_dur * 0.72), [None] * n
    idx = find_mentions(anchors, words, min_share)
    first_w, last_w = words[0][1], words[-1][1]
    times: List[Optional[float]] = [None if i is None else max(0.1, words[i][1] + after) for i in idx]
    if all(t is None for t in times):                    # nothing is named: spread over the spoken part, not the whole scene
        return _spread(n, max(0.15, first_w), max(first_w, last_w * 0.92)), idx
    known = [i for i, t in enumerate(times) if t is not None]
    for i in range(n):                                   # interpolate the gaps between known neighbours; extrapolate at the ends
        if times[i] is not None:
            continue
        left = max((k for k in known if k < i), default=None)
        right = min((k for k in known if k > i), default=None)
        if left is not None and right is not None:
            times[i] = times[left] + (times[right] - times[left]) * (i - left) / (right - left)
        elif right is not None:
            times[i] = max(0.15, times[right] - 0.8 * (right - i))
        else:
            times[i] = min(scene_dur - 0.8, times[left] + 0.9 * (i - left))
    out: List[float] = []
    for t in times:                                      # monotonic, with a minimum gap
        t = float(t)
        if out and t < out[-1] + MIN_GAP_S:
            t = out[-1] + MIN_GAP_S
        out.append(round(min(t, max(0.2, scene_dur - 0.6)), 3))
    return out, idx


# ----------------------------------------------------------------------------- what each scene reveals, in the order it reveals it
def diagram_order(props: Dict[str, Any]) -> List[str]:
    """Node labels in the order draw_diagram reveals them (by layer, then in the order given)."""
    from .scenes.viz_scenes import MAX_NODES, layout_diagram

    nodes = [n for n in (props.get("nodes") or []) if isinstance(n, dict) and "id" in n][:MAX_NODES]
    edges = [e for e in (props.get("edges") or []) if isinstance(e, (list, tuple)) and len(e) >= 2]
    layer = layout_diagram(nodes, edges)
    n_layers = (max(layer.values()) + 1) if layer else 1
    return [str(n.get("label", n["id"])) for li in range(n_layers) for n in nodes if layer[str(n["id"])] == li]


def _element(stype: str):
    from .scenes.registry import ELEMENTS

    return ELEMENTS.get(stype)


def item_texts(stype: str, props: Dict[str, Any]) -> List[str]:
    if stype == "bullets":
        return [str(i) for i in (props.get("items") or [])][:6]
    if stype == "diagram":
        return diagram_order(props)
    if stype == "chart":
        labels = [str(x) for x in (props.get("labels") or [])]
        vals = [str(x) for x in (props.get("values") or [])]
        return [f"{labels[i] if i < len(labels) else ''}" for i in range(len(vals))] if vals else labels
    if stype == "timeline":
        return [f"{e.get('date', '')} {e.get('label', '')}" for e in (props.get("events") or []) if isinstance(e, dict)]
    if stype == "gallery":
        return [str(q) for q in (props.get("image_queries") or [])]
    el = _element(stype)
    if el is not None and el.anchors is not None:
        return [str(t) for t in el.anchors(props) if str(t).strip()]
    return []


def apply(stype: str, props: Dict[str, Any], words: Sequence[Word], scene_dur: float) -> Dict[str, Any]:
    """Writes the anchored reveal times into `props` (`cues` for list-like scenes, `cuts` for galleries, `cue` for a stat) and returns what it found."""
    if stype in ("bullets", "diagram", "chart", "timeline"):
        texts = item_texts(stype, props)
        if not texts:
            return {}
        cues, idx = anchor_times(texts, words, scene_dur)
        props["cues"] = cues
        return {"items": len(texts), "anchored": sum(i is not None for i in idx)}
    if stype == "gallery":
        texts = item_texts(stype, props)
        n = len(texts)
        if n < 2:
            return {}
        if not words:
            props["cuts"] = [round(scene_dur * k / n, 3) for k in range(n)]
            return {"items": n, "anchored": 0}
        # a photo's query describes the picture ("Colosseum interior arena"), the narrator names only its subject ("the Colosseum"): one shared word is enough, in order
        rest, idx = anchor_times(texts[1:], words, scene_dur, after=GALLERY_AFTER_S, min_share=0.0)   # photo 0 is there from the start
        cuts = [0.0]
        for k, t in enumerate(rest):
            cuts.append(round(max(t, cuts[-1] + MIN_SHOT_S), 3))
        for k in range(n - 1, 0, -1):                                                   # every photo needs a moment on screen: pull late cuts back, never reorder them
            cuts[k] = round(min(cuts[k], scene_dur - 0.6 - (n - 1 - k) * 1.0), 3)
        if any(b - a < 0.8 for a, b in zip(cuts, cuts[1:])) or cuts[1] < 0.8:           # no room even so: share the scene evenly instead
            cuts = [round(scene_dur * k / n, 3) for k in range(n)]
        props["cuts"] = cuts
        return {"items": n, "anchored": sum(i is not None for i in idx) + 1}
    el = _element(stype)
    if el is not None and el.anchors is not None:   # an element's own reveal list, anchored like bullets
        texts = item_texts(stype, props)
        if not texts:
            return {}
        cues, idx = anchor_times(texts, words, scene_dur)
        props["cues"] = cues
        return {"items": len(texts), "anchored": sum(i is not None for i in idx)}
    if stype == "stat":
        value = str(props.get("value", ""))
        toks = [t for t in content_tokens(value) if t not in ("%", "$")] or content_tokens(str(props.get("label", "")))
        if toks and words:
            idx = find_mentions([" ".join(toks)], words)[0]
            if idx is not None:
                props["cues"] = [round(max(0.15, words[idx][1] - 0.35), 3)]
                return {"items": 1, "anchored": 1}
        return {"items": 1, "anchored": 0}
    return {}


def coverage_problems(plan_beats: Sequence[Dict[str, Any]], min_items: int = 3, min_share: float = 0.6) -> List[str]:
    """Scenes with a list of items whose narration names too few of them: the screen would show things the narrator never says. Used once, before the plan is
    accepted, to ask the planner to rewrite those beats (no extra model call when everything is fine)."""
    out: List[str] = []
    for i, b in enumerate(plan_beats):
        sc = b.get("scene") or {}
        stype, props = sc.get("type"), sc.get("props") or {}
        if stype not in ("bullets", "diagram", "timeline", "chart", "gallery"):
            continue
        if stype == "gallery" and props.get("photos"):   # the user's own photos: their captions only time the cuts, the narrator need not say them
            continue
        texts = item_texts(stype, props)
        if len(texts) < min_items:
            continue
        toks = re.findall(r"\S+", b.get("narration", ""))
        found = find_mentions(texts, [(t, float(k), float(k) + 0.3) for k, t in enumerate(toks)])
        if sum(f is not None for f in found) < min_share * len(texts):
            missing = [t[:40] for t, f in zip(texts, found) if f is None][:4]
            out.append(f"beat {i + 1} ({stype}): its narration never says {missing}")
    return out


# ----------------------------------------------------------------------------- the cheap alignment check
_LEGACY_SPAN = {"bullets": (0.10, 0.72), "diagram": (0.12, 0.78), "chart": (0.15, 0.70), "timeline": (0.15, 0.75)}


def legacy_cues(stype: str, n: int, dur: float) -> List[float]:
    """When reveals were not anchored (videos made before this module) they followed this fixed schedule: what the audit measures them against."""
    if stype == "gallery":
        return [dur * k / n for k in range(n)]
    first, last = _LEGACY_SPAN.get(stype, (0.1, 0.72))
    return [dur * first] if n <= 1 else [dur * first + dur * (last - first) * k / (n - 1) for k in range(n)]


def report(timeline: Dict[str, Any]) -> Dict[str, Any]:
    """How well the finished timeline lines up: per scene, each item's reveal against the word that names it. `ok` is False when reveals precede their
    mention by more than 0.5 s (the 'appears way before it is said' fault) or follow it by more than 0.4 s."""
    rows: List[Dict[str, Any]] = []
    for sc in timeline.get("scenes") or []:
        stype, props, words = sc.get("type"), sc.get("props") or {}, [tuple(w) for w in sc.get("words") or []]
        texts = item_texts(stype, props)
        if not texts or not words:
            continue
        cues = props.get("cuts") if stype == "gallery" else props.get("cues")
        legacy = not cues
        if legacy:
            cues = legacy_cues(stype, len(texts), float(sc.get("duration") or 0))
        mentions = find_mentions(texts, words, 0.0 if stype == "gallery" else 0.5)
        for k, (text, m) in enumerate(zip(texts, mentions)):
            if k >= len(cues) or cues[k] is None:
                continue
            if stype == "gallery" and k == 0:
                continue
            if m is None:
                rows.append({"scene": sc.get("id"), "type": stype, "item": text[:40], "cue": round(cues[k], 2), "mention": None, "delta": None, "legacy": legacy})
            else:
                rows.append({"scene": sc.get("id"), "type": stype, "item": text[:40], "cue": round(cues[k], 2), "mention": round(words[m][1], 2), "delta": round(cues[k] - words[m][1], 2), "legacy": legacy})
    deltas = [r["delta"] for r in rows if r["delta"] is not None]
    early = [d for d in deltas if d < -0.5]
    late = [d for d in deltas if d > 0.4]
    return {"items": len(rows), "anchored": len(deltas), "early": len(early), "late": len(late), "mean_abs_delta": round(sum(abs(d) for d in deltas) / len(deltas), 3) if deltas else None,
            "ok": not early and not late, "rows": rows}
