"""Whiteboard SKETCH OBJECTS on demand (docs/LIBRARY_ON_DEMAND.md, part B): the same framework as clips and images (engine/ondemand.py).

A whiteboard plan that asks for a drawing the library lacks gets its NAME written in a box (scenes/elements/whiteboard.py). With this step, in the plan step
and after the boards are settled: the plan's missing drawings (at most `object_max_per_call`, in ONE image call: a sheet in the house style) are generated,
cut, traced to a pen path, judged and named by the library's own gate (the part-naming call), stored in OUR library (package under w/<id>.json in the catalog
bucket, index row for search by name and by meaning in English and Spanish), and only then put into this video's boards in place of the written label.
Whatever is late, rejected or refused stays the written label: the plan is never delayed past `object_timeout_s`.

    fill(plan, video_id=..., ctx=...) -> {"made": [...ids], "asked": [...names], "reason": "..."}     never raises

The MAKER (names -> sheet -> packages, common/object_maker.py) needs the tracing code and two libraries (scipy, vtracer) that do not fit the engine's Lambda
layer. On Lambda it therefore runs in a small function of its own stack (backend/object_tracer.py) that the plan step calls when OBJECT_TRACER_FUNCTION names
it; on a laptop it runs in process. Where neither exists `fill` logs `no_tracer` and changes nothing; a function that is missing, slow or failing leaves the labels.
Safety (common/media_policy.py): the names are checked before anything is asked for, the provider's own moderation reads the prompt and the sheet, and every
finished drawing passes the policy's vision check before it is stored.
"""
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from common import clip_config, clip_store as cs, media_policy, takedown

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


def missing(plan: Dict[str, Any], limit: int, sure: float = 0.55, refused: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
    """(id, name) of the drawings the boards asked for and the library does not really have. In order, distinct, at most `limit`.
    A name that could never be a general library drawing (a brand, a flag, text, a person) is left as it is. `refused`, when given, collects name -> why for
    every name the free filters refuse (the policy's word lists first, then a brand or text word, then a personal wording): `fill` logs each as a decision."""
    from common import catalog_privacy

    out: List[Tuple[str, str]] = []
    for it in _items(plan):
        name = _wanted(it, sure)
        if not name:
            continue
        oid = object_id(name)
        if not NAME_RE.match(name) or len(oid) < 3 or len(name.split()) > 4:
            continue
        # the ONE safety policy's word lists: such a drawing is never made for the library; the label stays. A clearly benign compound ("queen bee", "water gun",
        # "baby elephant": media_policy.BENIGN) is read as a plain noun by the lists and by the privacy filter, which only knows single words
        personal = catalog_privacy.personal_reason(media_policy.cleared(name))
        why = media_policy.text_reason(name) or ("banned word" if _BANNED.search(name) else None) or (f"personal ({personal})" if personal not in (None, "address") else None)
        if why:
            if refused is not None:
                refused.setdefault(name, why)
            continue
        if oid not in [o for o, _ in out] and len(out) < limit:
            out.append((oid, name))
    return out


def descriptions(plan: Dict[str, Any], sure: float = 0.55) -> Dict[str, str]:
    """object id -> what the director said the object LOOKS like (`describe` on the item, 3 to 24 plain English words), for the drawings that are asked for. Only a
    description that the policy's word lists and the plain-English check let through is kept; a refused one is dropped and the drawing is made from its name alone."""
    out: Dict[str, str] = {}
    for it in _items(plan):
        name = _wanted(it, sure)
        d = " ".join(str(it.get("describe") or "").split()) if isinstance(it, dict) and name else ""
        if name and d and 3 <= len(d.split()) <= 24 and len(d) <= 160 and re.fullmatch(r"[A-Za-z ,\-]+", d) and not media_policy.text_reason(d) and media_policy.english_only(d):
            out.setdefault(object_id(name), d.lower())
    return out


def apply(plan: Dict[str, Any], made: Dict[str, str], sure: float = 0.55) -> int:
    """Put the new drawings where their written labels (or their approximate stand-ins) were. `made`: object id -> library id. -> how many items changed."""
    n = 0
    for it in _items(plan):
        name = _wanted(it, sure)
        if name and object_id(name) in made:
            for k in ("write", "boxed", "hand", "tool", "align", "asked", "match", "describe"):
                it.pop(k, None)
            it["draw"] = made[object_id(name)]
            n += 1
    return n


def offer(ctx: Optional[Dict[str, Any]], *, is_edit: bool = False) -> int:
    """How many drawings that the library lacks the director may NAME in this video's plan (engine/whiteboard_policy.allow_new_drawings): `object_max_per_call` when
    `fill` could make them for this account right now (the flag, both switches, an entitled plan, a store, a maker), else 0. Without it the director is told to draw
    only from the list, picks a stand-in itself, and `missing` never finds anything to make. Never raises; spends nothing (the limits are checked by `fill`)."""
    try:
        if not clip_config.flag() or is_edit or cs.current() is None:
            return 0
        cfg = clip_config.config()
        if not cfg["object_enabled"] or not cfg["master_enabled"] or ondemand.entitlement(ctx) is None or ondemand.plan_of(ctx) not in cfg["object_plans"]:
            return 0
        return int(cfg["object_max_per_call"]) if (_maker or default_maker()) is not None else 0
    except Exception:   # noqa: BLE001 - then the director draws from the list, as before
        logging.exception("objects on demand: offer failed")
        return 0


def settle(plan: Dict[str, Any], sure: Optional[float] = None) -> int:
    """After `fill`, for a plan whose director was allowed new names (`offer` > 0): a name that was NOT made and is still shown by an unsure match by meaning
    (a cheese for a honeycomb) becomes its written name in a box, which is what the director was promised ("drawn when it can be made, otherwise written").
    -> how many items changed."""
    try:
        sure = float(clip_config.config()["object_sure_score"]) if sure is None else float(sure)
    except Exception:   # noqa: BLE001
        sure = 0.55
    n = 0
    for it in _items(plan):
        if isinstance(it, dict) and it.get("draw") and it.get("asked") and float(it.get("match") or 1.0) < sure:
            name = str(it["asked"])
            for k in ("draw", "fill", "asked", "match"):
                it.pop(k, None)
            it["write"], it["boxed"], it["size"] = name, True, "m"
            n += 1
    return n


# ----------------------------------------------------------------------------- the maker: the library builder's own pipeline, here or in the tracer function
TRACER_ENV = "OBJECT_TRACER_FUNCTION"   # the name of the small tracer function of its own stack (backend/object_tracer.py). Unset = no function to call


class Refused(Exception):
    """The maker made nothing. `billed` False = the image provider was never paid, so the reservation goes back."""

    def __init__(self, kind: str, *, billed: bool):
        super().__init__(str(kind)[:120])
        self.kind, self.billed = str(kind)[:120], billed


_invoke: Optional[Callable[[str, bytes, float], bytes]] = None


def set_invoker(fn: Optional[Callable[[str, bytes, float], bytes]]) -> None:
    """Tests: how the tracer function is called (name, request JSON, seconds) -> response JSON."""
    global _invoke
    _invoke = fn


def _lambda_invoke(name: str, payload: bytes, timeout: float) -> bytes:
    import boto3
    from botocore.config import Config

    res = boto3.client("lambda", config=Config(read_timeout=max(5.0, timeout), connect_timeout=3, retries={"max_attempts": 0})).invoke(FunctionName=name, Payload=payload)
    body = res["Payload"].read()
    if res.get("FunctionError"):
        raise RuntimeError("tracer function error")
    return body


def tracer_maker(name: str) -> Maker:
    """The maker behind the tracer function: ONE synchronous call, no retry, bounded by the plan step's own limit. A function that is missing, throttled, slow or
    failing raises here and the boards keep what they had. Only plain English names go in; packages and their thumbnails come back."""
    import base64

    def make(objs: List[Tuple[str, str]], timeout: float, describe: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            body: Dict[str, Any] = {"action": "make", "objects": [[o, n] for o, n in objs], "timeout": timeout}
            if describe:
                body["describe"] = dict(describe)      # optional: a tracer that does not know the key ignores it
            raw = (_invoke or _lambda_invoke)(name, json.dumps(body).encode(), timeout + 2.0)
        except Exception as e:   # noqa: BLE001 - not there, not allowed, throttled, or no answer in time
            code = str(getattr(e, "response", {}).get("Error", {}).get("Code") or type(e).__name__)
            late = "timeout" in code.lower() or "timed out" in str(e).lower()
            raise Refused("timeout" if late else f"tracer unavailable ({code[:40]})", billed=late) from None   # no answer in time: the sheet may have been paid for
        res = json.loads(raw)
        if not isinstance(res, dict) or not isinstance(res.get("packages"), list):
            if isinstance(res, dict) and res.get("refused"):
                raise Refused(str(res["refused"]), billed=bool(res.get("billed", True)))
            raise Refused("tracer answer unreadable", billed=True)
        stats = dict(res.get("stats") or {})
        stats["thumbs"] = {str(k): base64.b64decode(v) for k, v in (res.get("thumbs") or {}).items()}
        return res["packages"], stats
    return make


def default_maker() -> Optional[Maker]:
    """Where the tracer function is configured (the plan step on Lambda): a call to it. On a laptop: the builder's pipeline itself (common/object_maker.py).
    None where neither exists (the engine's functions without the tracer stack): `fill` then answers `no_tracer` and spends nothing."""
    name = os.environ.get(TRACER_ENV, "").strip()
    if name:
        return tracer_maker(name)
    try:
        from common import object_maker

        if not object_maker.available():
            return None

        def make(objs: List[Tuple[str, str]], timeout: float, describe: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
            try:
                return object_maker.make(objs, timeout, describe=describe)
            except object_maker.Refused as e:
                raise Refused(e.kind, billed=e.billed) from None
        return make
    except Exception as e:   # noqa: BLE001
        logging.info("whiteboard tracer unavailable (%s)", type(e).__name__)
        return None


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


def unregister(ids: List[str]) -> int:
    """Drop drawings from THIS process's index (a takedown): they can no longer be found by id, by name or by meaning. -> how many were dropped."""
    from .whiteboard import library

    gone = set(ids)
    if not gone:
        return 0
    idx = library.index()
    before = len(idx["items"])
    idx["items"] = [it for it in idx["items"] if it["id"] not in gone]
    for fn in (library.by_name, library.search):
        for attr in ("_t", "_m"):
            if hasattr(fn, attr):
                delattr(fn, attr)
    return before - len(idx["items"])


def load_dynamic(store: Optional[cs.Store] = None) -> int:
    """Read the drawings made on demand so far into this process's index (the plan step calls it once before the director writes boards). -> how many."""
    try:
        store = store or cs.current()
        if store is None or not clip_config.flag():
            return 0
        rows = store.query(WOBJ)
        for r in rows:
            register(str(r["sk"]), r)
        unregister(takedown.denied(store, MEDIA))   # drawings taken out of the library (common/takedown.py), bundled ones included: never drawn again
        return len(rows)
    except Exception:
        logging.exception("dynamic whiteboard objects not loaded")
        return 0


def count_reuse(plan: Dict[str, Any], video_id: str, store: cs.Store) -> int:
    """How many drawings on this plan's boards the library got on demand EARLIER (rows under WOBJ). Each is counted like a library clip or image that a video
    reuses: the row's `uses` and distinct `videos`, the day's `used_library`, the metric. The report could not say whether a drawing we paid for was ever used
    again. Best effort: a counter never costs a plan."""
    try:
        ids = {str(it.get("draw")) for it in _items(plan) if isinstance(it, dict) and it.get("draw")}
        mine = sorted(str(r["sk"]) for r in store.query(WOBJ) if str(r["sk"]) in ids and r.get("status", "active") == "active") if ids else []
        for oid in mine:
            store.add(WOBJ, oid, {"uses": 1}, sets={"videos": [lib.video_ref(video_id)]}, fields={"last_used": int(time.time())})
        if mine:
            ondemand.emit("Used", len(mine), Source="library", Media=MEDIA)
            ondemand._stat(store, MEDIA, used_library=len(mine))
        return len(mine)
    except Exception:   # noqa: BLE001
        logging.exception("reuse of library drawings not counted")
        return 0


# ----------------------------------------------------------------------------- the safety policy on the finished drawings
def _policy_gate(pkgs: List[Dict[str, Any]], stats: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, str]]:
    """Every drawing the maker accepted is shown to the policy's vision check (common/media_policy.py), in parallel. -> (the drawings that passed, stats, {id: why} of
    the refused). A drawing without a picture to judge, or whose check fails or is unsure, is refused: it is never stored."""
    from concurrent.futures import ThreadPoolExecutor

    thumbs = stats.get("thumbs") or {}

    def one(pkg: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        oid = str(pkg.get("id"))
        name = str(pkg.get("what") or oid)
        why = media_policy.text_reason(name, (pkg.get("meta") or {}).get("title_en"), (pkg.get("meta") or {}).get("title_es"))   # what the gate named it, too
        if not why:
            ok, why, _v, _c = media_policy.vision_check([thumbs.get(oid) or b""], f"a simple whiteboard marker drawing of: {name}")
            why = None if ok else why
        return pkg, why
    if not pkgs:
        return [], stats, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, pkgs))
    return [p for p, why in rows if not why], stats, {str(p.get("id")): str(why) for p, why in rows if why}


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
        count_reuse(plan, video_id, store)   # drawings of our library that an earlier video had made: every plan reuses them, and the report counts it
        cfg = clip_config.config()
        free_refused: Dict[str, str] = {}
        want = missing(plan, int(cfg["object_max_per_call"]), float(cfg["object_sure_score"]), refused=free_refused)
        if not want and not free_refused:
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
        for name, why in free_refused.items():   # a name the free filters refused (the word lists, mostly) used to leave no trace: one decision each, like every other refusal
            ondemand.decision(store, f"filter:{why}", MEDIA, name=name)
        if not want:
            out["reason"] = "filter"
            return out
        maker = _maker or default_maker()
        if maker is None:
            out["reason"] = "no_tracer"
            ondemand.decision(store, "no_tracer", MEDIA, asked=out["asked"])
            return out
        # the ONE safety policy on the names (common/media_policy.py): word lists, then one small-model call that also gives the plain ENGLISH name, which is the
        # only wording the generator is sent. A refused name keeps its label; nothing is reserved for it.
        judged, _jcost = media_policy.judge_names([n for _, n in want])
        refused = {oid: j["reason"] for (oid, _), j in zip(want, judged) if not j["ok"]}
        asks: List[Tuple[str, str]] = []          # (id from the English name, English name): what the maker gets
        origin: Dict[str, str] = {}               # that id -> the id of the name the board wrote
        for (oid, _), j in zip(want, judged):
            en_id = object_id(j["english"]) if j["ok"] else ""
            if j["ok"] and len(en_id) >= 3 and en_id not in origin:
                asks.append((en_id, j["english"]))
                origin[en_id] = oid
        if not asks:
            out["reason"] = "policy_refused"
            ondemand.decision(store, "policy_refused", MEDIA, asked=out["asked"], refused=refused)
            return out
        t = time.time() if now is None else now
        price = round(float(cfg["object_call_usd"]) + float(cfg["object_gate_usd"]) * len(asks), 4)
        lines, why, allowance = ondemand.reserve(store, cfg, media=MEDIA, kind=kind, ctx=ctx, video_id=video_id, price=price, now=t)
        if lines is None:
            out["reason"] = why
            ondemand.decision(store, why, MEDIA, asked=out["asked"], price_usd=price, allowance_usd=allowance, kind=kind)
            return out
        ledger = (cs.ledger_pk(cs.month(t)), f"{int(t * 1000):013d}-{uuid.uuid4().hex[:6]}")
        store.put(ledger[0], ledger[1], {"at": int(t), "media": MEDIA, "outcome": "started", "brief": ", ".join(n for _, n in asks)[:200], "kind": kind, "reserved_usd": price, "charged_usd": price,
                                         "account": lib.account_ref(str(ctx["user_id"])), "video": lib.video_ref(video_id), "allowance_usd": allowance, "asked_n": len(asks), "ttl": int(t) + 500 * 86400})
        box: Dict[str, Any] = {}
        wrote = descriptions(plan, float(cfg["object_sure_score"]))
        described = {en_id: wrote[origin[en_id]] for en_id, _ in asks if origin.get(en_id) in wrote}      # id of the English name -> what it looks like (the generator is sent it with the name)
        out["described"] = sorted(described)

        def run() -> None:
            try:
                pkgs, stats = maker(asks, float(cfg["object_timeout_s"]), **({"describe": described} if described else {}))
                box["pkgs"], box["stats"], box["policy"] = _policy_gate(pkgs, stats or {})   # the same after-generation check as clips and images, on every drawing
            except Refused as e:
                box["error"], box["billed"] = e.kind, e.billed
            except Exception as e:  # noqa: BLE001
                box["error"] = type(e).__name__
        th = threading.Thread(target=run, name="objectgen", daemon=True)
        t0 = time.time()
        th.start()
        th.join(float(cfg["object_timeout_s"]))
        took = round(time.time() - t0, 1)
        ondemand.emit("GenerationSeconds", took, "Seconds", Media=MEDIA)
        if th.is_alive() or "error" in box:
            outcome = "timeout" if th.is_alive() or box.get("error") == "timeout" else "policy_refused" if str(box.get("error", "")).startswith("moderation:") else "provider_failed"
            out["reason"] = outcome
            charged = price
            if not th.is_alive() and box.get("billed") is False:   # refused before the provider was paid (no function, no key, the prompt refused by moderation): the reservation goes back
                ondemand.release(store, lines, media=MEDIA, kind=kind, price=price)
                charged = 0.0
            store.add(ledger[0], ledger[1], fields={"outcome": outcome, "reason": box.get("error", "not ready in time"), "latency_s": took, "charged_usd": charged})
            ondemand._stat(store, MEDIA, **{f"g_{outcome}": 1, "g_n": 1, "g_latency_ds": int(took * 10)})
            ondemand.decision(store, outcome, MEDIA, asked=out["asked"], waited=took, why=box.get("error"), charged_usd=charged)
            return out       # otherwise assumed billed: the reservation stays
        stats = box.get("stats") or {}
        made: Dict[str, str] = {}                 # the id of the name the board wrote -> the library id of its new drawing
        each = price / max(1, len(box["pkgs"]))
        for pkg in box["pkgs"]:
            try:
                en_id = object_id(str(pkg["id"]))
                made[origin.get(en_id, en_id)] = store_object(store, pkg, video_id=video_id, cost_usd=each)   # OUR library first
            except Exception:
                logging.exception("on-demand object not stored")
        n = apply(plan, made, float(cfg["object_sure_score"]))                                                                                 # only then the video
        out["made"] = sorted(made.values())
        rejected = {**refused, **dict(stats.get("rejected") or {}), **dict(box.get("policy") or {})}
        for _oid in rejected:
            ondemand.emit("Rejected", Reason="policy" if str(rejected[_oid]).startswith(("policy:", "moderation:")) else "gate", Media=MEDIA)
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
