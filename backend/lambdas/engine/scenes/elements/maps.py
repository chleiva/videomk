"""The `map` element: places on a map drawn from Natural Earth in the video's theme. One element, five modes (focus, regions, points, route, arcs).

The director gives names, never coordinates. `prepare` (beat stage, with network) resolves every name (offline from the bundled data, then Wikidata for landmarks and small
towns) and raises when a place cannot be resolved with confidence, so the beat becomes a title card; `draw` is pure and offline. See docs/MAPS.md.
"""
import json
import math
import re
import time
from typing import Any, Dict, List, Tuple

from ...easing import reveal_times
from ..registry import Element, PrepareCtx
from . import _mapdraw as MD
from . import _resolve as R

MODES = ("focus", "regions", "points", "route", "arcs")
MAX_NAME = 60
_LIMITS = {"focus": 4, "regions": 12, "points": 8, "stops": 8, "arcs": 8}
WD_BUDGET_S = 20.0           # all Wikidata lookups of one map together
WD_MAX_LOOKUPS = 8


def _s(v: Any, n: int) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f‪-‮⁦-⁩]", " ", str(v if v is not None else ""))).strip()[:n]


def _names(v: Any, hi: int, dedupe: bool = True) -> List[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    out: List[str] = []
    for x in v:
        if isinstance(x, dict):
            x = x.get("name") or x.get("place")
        n = _s(x, MAX_NAME)
        if n and not (dedupe and n.lower() in {o.lower() for o in out}):
            out.append(n)
    return out[:hi]


def _points(v: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(v, (list, tuple)):
        return out
    for x in v:
        name, label = "", ""
        if isinstance(x, dict):
            name, label = _s(x.get("name") or x.get("place"), MAX_NAME), _s(x.get("label"), 28)
        elif isinstance(x, (list, tuple)) and x:
            name, label = _s(x[0], MAX_NAME), _s(x[1], 28) if len(x) > 1 else ""
        else:
            name = _s(x, MAX_NAME)
        if name and name.lower() not in {p["name"].lower() for p in out}:
            out.append({"name": name, "label": label} if label else {"name": name})
    return out[:_LIMITS["points"]]


def _arcs(v: Any) -> List[List[str]]:
    out: List[List[str]] = []
    if not isinstance(v, (list, tuple)):
        return out
    for x in v:
        if isinstance(x, dict):
            a, b, lab = x.get("from"), x.get("to"), x.get("label")
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            a, b, lab = x[0], x[1], (x[2] if len(x) > 2 else "")
        else:
            continue
        a, b, lab = _s(a, MAX_NAME), _s(b, MAX_NAME), _s(lab, 22)
        if a and b and a.lower() != b.lower():
            out.append([a, b, lab] if lab else [a, b])
    return out[:_LIMITS["arcs"]]


def _resolved(v: Any) -> Dict[str, Dict[str, Any]]:
    """The patch `prepare` stored: only well-formed entities survive."""
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(v, dict):
        return out
    for k, e in list(v.items())[:100]:
        if not isinstance(k, str) or len(k) > 90 or not isinstance(e, dict):
            continue
        t = e.get("t")
        try:
            if t in ("country", "admin1") and isinstance(e.get("id"), str) and len(e["id"]) <= 24:
                out[k] = {"t": t, "id": e["id"], "n": _s(e.get("n"), 60)}
                if t == "admin1" and isinstance(e.get("c"), str):
                    out[k]["c"] = e["c"][:8]
            elif t == "point" and -90 <= float(e["lat"]) <= 90 and -180 <= float(e["lon"]) <= 180:
                out[k] = {"t": "point", "lon": round(float(e["lon"]), 5), "lat": round(float(e["lat"]), 5), "n": _s(e.get("n"), 60), "s": _s(e.get("s"), 10)}
            elif t == "frame" and isinstance(e.get("box"), (list, tuple)) and len(e["box"]) == 4:
                box = [round(float(b), 3) for b in e["box"]]
                if all(math.isfinite(b) for b in box):
                    out[k] = {"t": "frame", "box": box, "n": _s(e.get("n"), 60)}
        except (KeyError, TypeError, ValueError):
            continue
    return out


def sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(props, dict):
        raise ValueError("map props must be an object")
    mode = _s(props.get("mode"), 12).lower()
    if mode not in MODES:
        mode = next((m for m, key in (("route", "stops"), ("arcs", "arcs"), ("regions", "regions"), ("points", "points"), ("focus", "focus")) if props.get(key)), "")
    if mode not in MODES:
        raise ValueError("map needs a mode and places")
    out: Dict[str, Any] = {"mode": mode}
    title, caption = _s(props.get("title"), 50), _s(props.get("caption"), 60)
    if title:
        out["title"] = title
    if caption:
        out["caption"] = caption
    focus = _names(props.get("focus"), _LIMITS["focus"])
    if mode == "focus":
        if not focus:
            raise ValueError("focus needs 1-4 places")
        out["focus"] = focus
    else:
        if focus:
            out["focus"] = focus
        if mode == "regions":
            regions = _names(props.get("regions"), _LIMITS["regions"])
            if not regions:
                raise ValueError("regions needs at least one name")
            out["regions"] = regions
        elif mode == "points":
            pts = _points(props.get("points"))
            if not pts:
                raise ValueError("points needs at least one place")
            out["points"] = pts
        elif mode == "route":
            stops = _names(props.get("stops"), _LIMITS["stops"], dedupe=False)
            if len(stops) < 2:
                raise ValueError("route needs at least two stops")
            out["stops"] = stops
        else:
            arcs = _arcs(props.get("arcs"))
            if not arcs:
                raise ValueError("arcs needs at least one [from, to]")
            out["arcs"] = arcs
    cues = props.get("cues")
    if isinstance(cues, (list, tuple)):
        c = []
        for x in cues[:24]:
            try:
                f = float(x)
            except (TypeError, ValueError):
                continue
            if math.isfinite(f) and 0 <= f <= 3600:
                c.append(round(f, 3))
        if c:
            out["cues"] = c
    res = _resolved(props.get("resolved"))
    if res:
        out["resolved"] = res
    return out


# ----------------------------------------------------------------------------- names, roles, anchors
def needed(props: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(role, name) for every place the scene draws, in order, without repeats."""
    mode = props["mode"]
    out: List[Tuple[str, str]] = []
    if mode == "regions":
        out += [("shape", n) for n in props["regions"]]
    if mode == "points":
        out += [("point", p["name"]) for p in props["points"]]
    if mode == "route":
        out += [("point", n) for n in props["stops"]]
    if mode == "arcs":
        for a in props["arcs"]:
            out += [("point", a[0]), ("point", a[1])]
    out += [("any", n) for n in props.get("focus", [])]
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def anchors(props: Dict[str, Any]) -> List[str]:
    """Texts whose mention in the narration reveals each part, in order (the engine writes the times to props['cues'])."""
    mode = props.get("mode")
    if mode == "regions":
        return list(props.get("regions", []))
    if mode == "points":
        return [p["name"] for p in props.get("points", [])]
    if mode == "route":
        return list(props.get("stops", []))
    if mode == "arcs":
        return [a[1] for a in props.get("arcs", [])]
    if mode == "focus" and len(props.get("focus", [])) > 1:
        return list(props["focus"])
    return []


def _count(props: Dict[str, Any]) -> int:
    return max(1, len(anchors(props)))


def cues(props: Dict[str, Any], dur: float) -> List[float]:
    if not anchors(props):
        return [min(dur, 0.45)]
    return [min(dur, c) for c in reveal_times(_count(props), dur, props.get("cues"), first=0.14, last=0.70)]


def _spec_key(props: Dict[str, Any]) -> str:
    """What the drawing depends on, as a stable string (the cache key of the projected model)."""
    spec: Dict[str, Any] = {"mode": props["mode"], "title": props.get("title", ""), "caption": props.get("caption", ""), "focus": props.get("focus", [])}
    for k in ("regions", "stops", "arcs"):
        if k in props:
            spec[k] = props[k]
    if "points" in props:
        spec["points"] = [[p["name"], p.get("label", "")] for p in props["points"]]
    keys = {MD.entity_key(role, n) for role, n in needed(props)}
    spec["resolved"] = {k: v for k, v in (props.get("resolved") or {}).items() if k in keys}
    return json.dumps(spec, sort_keys=True, ensure_ascii=False)


def draw(cv, props, lt, dur, theme, ctx) -> None:
    pw, ph = MD.panel_size(ctx.bottom)
    m = MD.build_model(_spec_key(props), pw, ph)
    times = [min(dur, c) for c in (reveal_times(_count(props), dur, props.get("cues"), first=0.14, last=0.70) if anchors(props) else [0.45])]
    MD.paint_frame(cv, m, theme, times, lt, dur, ctx.bottom)


# ----------------------------------------------------------------------------- prepare / fallback
def prepare(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    """Resolve every named place (offline first, Wikidata for the rest). Raises when a place is unknown or ambiguous: the beat then shows `fallback`."""
    p = sanitize(props)
    resolved = dict(p.get("resolved") or {})
    t0, lookups = time.monotonic(), 0
    for role, name in needed(p):
        key = MD.entity_key(role, name)
        if key in resolved:
            continue
        try:
            e = R.resolve_offline(name, role)
        except R.Ambiguous:
            raise
        except R.NotFound:
            if role == "shape":
                raise
            lookups += 1
            if lookups > WD_MAX_LOOKUPS or time.monotonic() - t0 > WD_BUDGET_S:
                raise R.ResolveError("too many places to look up")
            e = R.wikidata_lookup(name)
        if role == "point" and e["t"] != "point":
            raise R.ResolveError(f"{name} is not a place that can be pinned")
        resolved[key] = e
    check = dict(p, resolved=resolved)
    clean = sanitize(check)
    if len(clean.get("resolved", {})) < len(needed(clean)):
        raise R.ResolveError("some places could not be resolved")
    return {"resolved": clean["resolved"]}


def fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    p = props or {}
    first = ""
    for k in ("regions", "stops", "focus"):
        v = p.get(k)
        if isinstance(v, list) and v:
            first = _s(v[0], 70)
            break
    if not first and isinstance(p.get("points"), list) and p["points"]:
        x = p["points"][0]
        first = _s(x.get("name") if isinstance(x, dict) else x, 70)
    if not first and isinstance(p.get("arcs"), list) and p["arcs"]:
        x = p["arcs"][0]
        first = _s(x[1] if isinstance(x, (list, tuple)) and len(x) > 1 else "", 70)
    return "title", {"title": _s(p.get("title"), 70) or first or "The map"}


DOC = (
    "- map: {mode: focus|regions|points|route|arcs, title (<=50), caption (<=60), focus: 1-4 names to frame, regions: <=12 countries/states, points: <=8 names or {name, label (<=28)}, "
    "stops: 2-8 names in order, arcs: <=8 [from, to, label?]}. Each mode takes its own list: {\"mode\":\"focus\",\"focus\":[\"Portugal\"]} {\"mode\":\"regions\",\"regions\":[\"France\",\"Spain\"]} "
    "{\"mode\":\"points\",\"points\":[\"Cairo\"]} {\"mode\":\"route\",\"stops\":[\"Paris\",\"Lyon\"]} {\"mode\":\"arcs\",\"arcs\":[[\"Shenzhen\",\"Rotterdam\"]]}. "
    "Use when the narration names places, a journey, a spread or connections, listed in spoken order. For a city or a tour use points or route with the landmarks, not focus (focus frames a country or region). Never when the place is vague; never give coordinates, only names."
)

SAMPLES = [
    {"mode": "focus", "title": "Where Portugal sits", "focus": ["Portugal"], "caption": "The westernmost country of mainland Europe"},
    {"mode": "regions", "title": "Four countries in the story", "regions": ["France", "Germany", "Italy", "Spain"]},
    {"mode": "regions", "regions": ["Texas", "California", "Florida", "New York"], "caption": "Four US states"},
    {"mode": "points", "title": "Capitals along the Nile region", "points": [{"name": "Cairo", "label": "Capital of Egypt"}, "Khartoum", {"name": "Nairobi", "label": "Capital of Kenya"}, "Addis Ababa"]},
    {"mode": "points", "points": ["Tokyo", "Delhi", "Sao Paulo", "Lagos", "London", "Sydney", "Mexico City", "Cairo"], "title": "Eight big cities"},
    {"mode": "route", "title": "A rail trip across France", "stops": ["Paris", "Lyon", "Marseille"]},
    {"mode": "route", "stops": ["Lisbon", "Madrid", "Paris", "Berlin", "Warsaw", "Kyiv"], "title": "Six capitals in a row", "caption": "Roughly west to east"},
    {"mode": "arcs", "title": "Where the goods go", "arcs": [["Shenzhen", "Rotterdam", "Containers"], ["Shenzhen", "Los Angeles"], ["Shanghai", "Santos"]]},
    {"mode": "arcs", "arcs": [["London", "New York"], ["Paris", "Dubai"], ["Singapore", "Sydney"], ["Johannesburg", "Mumbai"]], "title": "Flight links"},
]

ELEMENTS = [Element(
    name="map", family="Maps", doc=DOC, sanitize=sanitize, draw=draw, cues=cues, samples=SAMPLES, anchors=anchors, prepare=prepare, fallback=fallback, max_per_video=3, min_seconds=3.0,
)]
