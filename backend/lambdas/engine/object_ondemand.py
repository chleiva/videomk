"""Whiteboard SKETCH OBJECTS on demand (docs/LIBRARY_ON_DEMAND.md, part B): the same framework as clips and images (engine/ondemand.py).

A whiteboard plan that asks for a drawing the library lacks gets its NAME written in a box (scenes/elements/whiteboard.py). With this step, in the plan step
and after the boards are settled: the plan's missing drawings (at most `object_max_per_call`, in ONE image call: a sheet in the house style) are generated,
cut, traced to a pen path, judged and named by the library's own gate (the part-naming call), stored in OUR library (package under w/<id>.json in the catalog
bucket, index row for search by name and by meaning in English and Spanish), and only then put into this video's boards in place of the written label.
Whatever is late, rejected or refused stays the written label: the plan is never delayed past `object_timeout_s`.

    fill(plan, video_id=..., ctx=...) -> {"made": [...ids], "asked": [...names], "reason": "..."}     never raises

The MAKER (sheet -> packages) needs the tracing code and two libraries (scipy, vtracer) that are not in the engine's Lambda layer today; where they are
missing `fill` logs `no_tracer` and changes nothing. See the document for what going live on Lambda needs.
"""
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from common import clip_config, clip_store as cs

from . import clip_library as lib, ondemand

MEDIA = "object"
WOBJ = cs.P + "wobj"          # sort = object id: the dynamic part of the whiteboard index (titles, synonyms, vector)
NAME_RE = re.compile(r"^[a-z][a-z0-9 _-]{1,40}$")
_BANNED = re.compile(r"\b(logo|brand|flag of|map of|portrait|president|celebrity|text|word|letter|number|chart|graph|diagram)\b", re.I)

Maker = Callable[[List[Tuple[str, str]], float], Tuple[List[Dict[str, Any]], Dict[str, Any]]]
_maker: Optional[Maker] = None


def set_maker(m: Optional[Maker]) -> None:
    global _maker
    _maker = m


def object_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48]


def _wanted(it: Any, sure: float) -> Optional[str]:
    """The name of a drawing this item asked for and did not really get: written as a boxed label (nothing matched), or drawn from a match by meaning that is not
    a sure one (the board asked for a honeycomb and the library's closest thing was a cheese)."""
    if not isinstance(it, dict):
        return None
    if it.get("boxed") and it.get("write"):
        return " ".join(str(it["write"]).lower().split())
    if it.get("draw") and it.get("asked") and float(it.get("match") or 1.0) < sure:
        return " ".join(str(it["asked"]).lower().split())
    return None


def _items(plan: Dict[str, Any]):
    for b in plan.get("beats") or []:
        sc = b.get("scene") or {}
        if sc.get("type") == "whiteboard":
            yield from (sc.get("props") or {}).get("items") or []


def missing(plan: Dict[str, Any], limit: int, sure: float = 0.55) -> List[Tuple[str, str]]:
    """(id, name) of the drawings the boards asked for and the library does not really have. In order, distinct, at most `limit`.
    A name that could never be a general library drawing (a brand, a flag, text, a person) is left as it is."""
    from common import catalog_privacy

    out: List[Tuple[str, str]] = []
    for it in _items(plan):
        name = _wanted(it, sure)
        if not name:
            continue
        oid = object_id(name)
        if not NAME_RE.match(name) or len(oid) < 3 or len(name.split()) > 4 or _BANNED.search(name) or catalog_privacy.personal_reason(name) not in (None, "address"):
            continue
        if oid not in [o for o, _ in out] and len(out) < limit:
            out.append((oid, name))
    return out


def apply(plan: Dict[str, Any], made: Dict[str, str], sure: float = 0.55) -> int:
    """Put the new drawings where their written labels (or their approximate stand-ins) were. `made`: object id -> library id. -> how many items changed."""
    n = 0
    for it in _items(plan):
        name = _wanted(it, sure)
        if name and object_id(name) in made:
            for k in ("write", "boxed", "hand", "tool", "align", "asked", "match"):
                it.pop(k, None)
            it["draw"] = made[object_id(name)]
            n += 1
    return n


# ----------------------------------------------------------------------------- the default maker: the library builder's own pipeline (scripts/whiteboard_proto)
def default_maker() -> Optional[Maker]:
    """sheet of N names -> accepted packages, with the library's house prompt, cutter, tracer and gate (scripts/whiteboard_proto/lib_build.py). None where the
    tracing code or its libraries are not present (the engine's functions today)."""
    try:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        proto = os.environ.get("WHITEBOARD_PROTO_DIR") or os.path.join(here, "..", "..", "scripts", "whiteboard_proto")
        if not os.path.isdir(proto):
            return None
        for p in (proto, os.path.join(proto, "..")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import base64
        import tempfile
        from concurrent.futures import ThreadPoolExecutor

        import gen_art
        import lib_build
        import trace as tr

        from common import catalog_make as cm
        from .image_ondemand import OpenAIImages
    except Exception as e:   # noqa: BLE001
        logging.info("whiteboard tracer unavailable (%s)", type(e).__name__)
        return None

    def make(objs: List[Tuple[str, str]], timeout: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        t0, n = time.time(), lib_build.COLS * lib_build.ROWS
        subjects = [name for _, name in objs] + ["a small plain circle"] * (n - len(objs))
        prompt = gen_art.HOUSE.format(n=n, cols=lib_build.COLS, rows=lib_build.ROWS, subjects="; ".join(f"({i + 1}) {s}" for i, s in enumerate(subjects)))
        key = OpenAIImages()._read_key()
        import urllib.request
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", json.dumps({"model": cm.OPENAI_MODEL, "prompt": prompt, "size": gen_art.SIZE, "quality": "medium",
                                                                                                   "output_format": "png", "n": 1}).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=max(5.0, timeout)) as r:
            res = json.loads(r.read())
        stats: Dict[str, Any] = {"sheet_s": round(time.time() - t0, 1), "sheet_usd": round(cm.real_cost(res.get("usage") or {}), 4), "rejected": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sheet.png")
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(res["data"][0]["b64_json"]))
            stats["sheet_png"] = open(path, "rb").read()
            t1 = time.time()
            cells = lib_build.cut(tr.load_ink(path))
            stats["cut_s"] = round(time.time() - t1, 2)
            lib_build.LIB = tmp   # packages are written here and read back: nothing touches the builder's own library folder

            def one(job):
                (oid, name), cell = job
                t = time.time()
                try:
                    row = lib_build.build_object(oid, "on-demand", name, cell, "on-demand", 1)
                except Exception as e:  # noqa: BLE001
                    row = {"ok": False, "why": f"build failed: {type(e).__name__}"}
                row["s"] = round(time.time() - t, 1)
                return oid, row
            with ThreadPoolExecutor(max_workers=6) as ex:
                rows = list(ex.map(one, zip(objs, cells)))
            out = []
            for oid, row in rows:
                if row.get("ok"):
                    out.append(json.load(open(os.path.join(tmp, oid + ".json"))))
                else:
                    stats["rejected"][oid] = str(row.get("why"))[:80]
            stats["object_s"] = {oid: row["s"] for oid, row in rows}
        stats["total_s"] = round(time.time() - t0, 1)
        return out, stats
    return make


# ----------------------------------------------------------------------------- our library: the package, the index row, the search overlay
def store_object(store: cs.Store, pkg: Dict[str, Any], *, video_id: str, cost_usd: float, put_package: Optional[Callable[[str, bytes], None]] = None) -> str:
    """One accepted drawing into the library: the package (w/<id>.json in the catalog bucket, where the renderer reads every drawing) and its index row
    (names in English and Spanish, synonyms, tags, the text vector). An id that exists is never overwritten: the new drawing gets a numbered id."""
    meta = pkg.get("meta") or {}
    oid = base = object_id(str(pkg["id"]))
    k = 2
    while store.get(WOBJ, oid) is not None or _bundled(oid):
        oid, k = f"{base}_{k}", k + 1
    pkg = {**pkg, "id": oid, "provenance": {**(pkg.get("provenance") or {}), "on_demand": True, "demand_video": lib.video_ref(video_id), "owner": "Agilegency Ltd (VideoMK)", "scope": "library"}}
    data = json.dumps(pkg, separators=(",", ":"), ensure_ascii=False).encode()
    (put_package or _put_package)(oid, data)
    text = ". ".join(str(x) for x in [meta.get("title_en"), meta.get("title_es"), ", ".join(meta.get("synonyms_en") or []), ", ".join(meta.get("synonyms_es") or []),
                                      ", ".join(meta.get("tags") or []), meta.get("description")] if x)
    store.put(WOBJ, oid, {"title": meta.get("title_en") or oid, "title_es": meta.get("title_es") or "", "synonyms_en": list(meta.get("synonyms_en") or [])[:8],
                          "synonyms_es": list(meta.get("synonyms_es") or [])[:8], "tags": list(meta.get("tags") or [])[:8], "category": "on-demand", "v": lib.pack(lib.embed("doc", text)),
                          "w": pkg.get("w"), "h": pkg.get("h"), "pen_length": pkg.get("pen_length"), "score": meta.get("score"), "created": int(time.time()), "cost_usd": round(cost_usd, 4),
                          "scope": "library", "status": "active", "asked_as": str(pkg.get("what") or "")[:48]}, only_if_absent=True)
    register(oid, store.get(WOBJ, oid) or {})
    return oid


def _bundled(oid: str) -> bool:
    from .whiteboard import library
    return library.has(oid)


def _put_package(oid: str, data: bytes) -> None:
    local = os.environ.get("WHITEBOARD_DIR")
    if local:
        with open(os.path.join(local, oid + ".json"), "wb") as fh:
            fh.write(data)
        return
    import boto3
    boto3.client("s3").put_object(Bucket=os.environ["CATALOG_BUCKET"], Key=f"w/{oid}.json", Body=data, ContentType="application/json")


def register(oid: str, row: Dict[str, Any]) -> None:
    """Make a dynamic drawing findable in THIS process like a bundled one (by id, by name, by meaning)."""
    from .whiteboard import library

    idx = library.index()
    if any(it["id"] == oid for it in idx["items"]) or not row.get("v") or row.get("status", "active") != "active" or row.get("scope", "library") != "library":
        return
    idx["items"].append({"id": oid, "category": row.get("category", "on-demand"), "title": row.get("title"), "title_es": row.get("title_es"), "synonyms_en": row.get("synonyms_en") or [],
                         "synonyms_es": row.get("synonyms_es") or [], "tags": row.get("tags") or [], "v": row["v"], "w": row.get("w"), "h": row.get("h"), "pen_length": row.get("pen_length")})
    for fn in (library.by_name, library.search):   # their lookup tables are built once: drop them so the new drawing is in the next one
        for attr in ("_t", "_m"):
            if hasattr(fn, attr):
                delattr(fn, attr)


def load_dynamic(store: Optional[cs.Store] = None) -> int:
    """Read the drawings made on demand so far into this process's index (the plan step calls it once before the director writes boards). -> how many."""
    try:
        store = store or cs.current()
        if store is None or not clip_config.flag():
            return 0
        rows = store.query(WOBJ)
        for r in rows:
            register(str(r["sk"]), r)
        return len(rows)
    except Exception:
        logging.exception("dynamic whiteboard objects not loaded")
        return 0


# ----------------------------------------------------------------------------- the step
def fill(plan: Dict[str, Any], *, video_id: str, ctx: Optional[Dict[str, Any]], is_edit: bool = False, now: Optional[float] = None) -> Dict[str, Any]:
    """Make the plan's missing drawings (one call, bounded in time) and put them on its boards. Never raises; whatever fails stays a written label."""
    out: Dict[str, Any] = {"asked": [], "made": [], "reason": ""}
    store = None
    try:
        if not clip_config.flag():
            return out
        store = cs.current()
        if store is None:
            return out
        cfg = clip_config.config()
        want = missing(plan, int(cfg["object_max_per_call"]), float(cfg["object_sure_score"]))
        if not want:
            return out
        out["asked"] = [n for _, n in want]
        kind = ondemand.entitlement(ctx)
        if kind is None or ondemand.plan_of(ctx) not in cfg["object_plans"]:   # Max and test accounts; the allowance formula knows no other plan yet (see the document: opening it to Pro)
            out["reason"] = "not_entitled"
            return out
        for why, test in (("kill_switch", not cfg["object_enabled"] or not cfg["master_enabled"]), ("edit", is_edit), ("own_photos", bool(plan.get("media_items") or plan.get("deck")))):
            if test:
                out["reason"] = why
                ondemand.decision(store, why, MEDIA)
                return out
        maker = _maker or default_maker()
        if maker is None:
            out["reason"] = "no_tracer"
            ondemand.decision(store, "no_tracer", MEDIA, asked=out["asked"])
            return out
        t = time.time() if now is None else now
        price = round(float(cfg["object_call_usd"]) + float(cfg["object_gate_usd"]) * len(want), 4)
        lines, why, allowance = ondemand.reserve(store, cfg, media=MEDIA, kind=kind, ctx=ctx, video_id=video_id, price=price, now=t)
        if lines is None:
            out["reason"] = why
            ondemand.decision(store, why, MEDIA, asked=out["asked"], price_usd=price, allowance_usd=allowance, kind=kind)
            return out
        ledger = (cs.ledger_pk(cs.month(t)), f"{int(t * 1000):013d}-{uuid.uuid4().hex[:6]}")
        store.put(ledger[0], ledger[1], {"at": int(t), "media": MEDIA, "outcome": "started", "brief": ", ".join(out["asked"])[:200], "kind": kind, "reserved_usd": price, "charged_usd": price,
                                         "account": lib.account_ref(str(ctx["user_id"])), "video": lib.video_ref(video_id), "allowance_usd": allowance, "asked_n": len(want), "ttl": int(t) + 500 * 86400})
        box: Dict[str, Any] = {}

        def run() -> None:
            try:
                box["pkgs"], box["stats"] = maker(want, float(cfg["object_timeout_s"]))
            except Exception as e:  # noqa: BLE001
                box["error"] = type(e).__name__
        th = threading.Thread(target=run, name="objectgen", daemon=True)
        t0 = time.time()
        th.start()
        th.join(float(cfg["object_timeout_s"]))
        took = round(time.time() - t0, 1)
        ondemand.emit("GenerationSeconds", took, "Seconds", Media=MEDIA)
        if th.is_alive() or "error" in box:
            outcome = "timeout" if th.is_alive() else "provider_failed"
            out["reason"] = outcome
            store.add(ledger[0], ledger[1], fields={"outcome": outcome, "reason": box.get("error", "not ready in time"), "latency_s": took})
            ondemand._stat(store, MEDIA, **{f"g_{outcome}": 1, "g_n": 1, "g_latency_ds": int(took * 10)})
            ondemand.decision(store, outcome, MEDIA, asked=out["asked"], waited=took)
            return out       # assumed billed: the reservation stays
        stats = box.get("stats") or {}
        made: Dict[str, str] = {}
        each = price / max(1, len(box["pkgs"]))
        for pkg in box["pkgs"]:
            try:
                made[object_id(str(pkg["id"]))] = store_object(store, pkg, video_id=video_id, cost_usd=each)   # OUR library first
            except Exception:
                logging.exception("on-demand object not stored")
        n = apply(plan, made, float(cfg["object_sure_score"]))                                                                                 # only then the video
        out["made"] = sorted(made.values())
        rejected = dict(stats.get("rejected") or {})
        for _oid in rejected:
            ondemand.emit("Rejected", Reason="gate", Media=MEDIA)
        store.add(ledger[0], ledger[1], fields={"outcome": "generated" if made else "gate_rejected", "reason": json.dumps(rejected)[:200] if rejected else "ok", "latency_s": took,
                                                "made_n": len(made), "rejected_n": len(rejected), "provider_usd": stats.get("sheet_usd"), "clip_id": ",".join(out["made"])[:200]})
        ondemand._stat(store, MEDIA, g_n=1, g_latency_ds=int(took * 10), o_made=len(made), o_rejected=len(rejected), o_asked=len(want), used_generated=n, **{f"g_{'generated' if made else 'gate_rejected'}": 1})
        ondemand.emit("Generated", len(made), Media=MEDIA)
        ondemand.decision(store, "generated" if made else "gate_rejected", MEDIA, asked=out["asked"], made=out["made"], rejected=rejected, latency_s=took, charged_usd=price, kind=kind)
        out["reason"] = "generated" if made else "gate_rejected"
        return out
    except Exception:   # noqa: BLE001 - the plan goes on with its labels
        logging.exception("objects on demand failed")
        out["reason"] = "error"
        try:
            ondemand.decision(store, "error", MEDIA)
        except Exception:
            pass
        return out
