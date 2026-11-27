"""Library clips on demand (docs/CLIPS_ON_DEMAND.md): when a Max customer's video asks for footage the library does not have, make ONE general clip for the library,
and let this video use it from there. Everything is behind the deploy flag CLIPS_ON_DEMAND and the live kill switch `enabled`; both off by default.

    job = begin(...)        decide (entitled? reusable? already there? asked enough? caps and budgets?), reserve the money in ONE transaction, start the generation
                            in the background. None = nothing is made (the reason is logged). Never raises.
    clip_id = job.wait()    the id of a clip that is IN THE LIBRARY (made now, or found there), or None (slow, failed, rejected). The caller then selects it through
                            the normal own-library path (clips.scout_own), which checks it against the narration like any other clip.

The customer's video never depends on this: every failure is a None and the beat goes on with its stock clip or photo.
Money: a generation is charged its configured price to four counters at once (video, account-month, day, month); a counter over its limit refuses all four.
"""
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from common import clip_config, clip_store as cs

from . import clip_brief, clip_gate, clip_gen, clip_library as lib

NAMESPACE = "videomk/Clips"
PAYING_SOURCES = ("apple", "google", "web")
NO_CREDIT_STATUSES = ("FAILED", "CANCELLED", "REJECTED")   # their credits were given back
LOCK_S = 600
WAIT_AFTER_S = 40.0                # after the provider's own limit: the gate, the embeddings and the writes
MIN_FILL = 0.75                    # clips.MIN_FILL: footage shorter than this share of the scene is never used

_readers: Dict[str, Callable[..., Any]] = {}


def set_readers(*, video: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None, credits: Optional[Callable[[str, float], int]] = None) -> None:
    """Tests: how the video row and the account's credits of the month are read."""
    for k, v in (("video", video), ("credits", credits)):
        if v is not None:
            _readers[k] = v


def reset() -> None:
    _readers.clear()


# ----------------------------------------------------------------------------- observability
def emit(name: str, value: float = 1, unit: str = "Count", **dims: str) -> None:
    """One CloudWatch metric through the function's log (embedded metric format: no API call, no permission)."""
    print(json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [{"Namespace": NAMESPACE, "Dimensions": [sorted(dims)], "Metrics": [{"Name": name, "Unit": unit}]}]},
                      name: value, **dims}))


def _stat(store: cs.Store, **counters: int) -> None:
    try:
        store.add(cs.STATS, cs.day(), {k: int(v) for k, v in counters.items()}, fields={"ttl": int(time.time()) + 400 * 86400})
    except Exception:
        logging.exception("clip stat not written")


def decision(store: Optional[cs.Store], outcome: str, **info: Any) -> None:
    """Every decision, with its reason: a log line, a metric by reason code, and a counter of the day."""
    code = outcome.split(":", 1)[0]
    logging.warning("CLIP_DECISION %s", json.dumps({"outcome": outcome, **{k: v for k, v in info.items() if v is not None}}, ensure_ascii=False, default=str)[:900])
    emit("Decisions", Outcome=code)
    if store is not None:
        _stat(store, **{f"d_{code}": 1})


# ----------------------------------------------------------------------------- who is asking
def context(video_id: str) -> Optional[Dict[str, Any]]:
    """What the video row says about who made the video: {user_id, plan, plan_interval, plan_source, plan_state}. None when it cannot be read (then nobody is entitled)."""
    try:
        if "video" in _readers:
            return _readers["video"](video_id)
        import boto3
        it = boto3.resource("dynamodb").Table(os.environ.get("VIDEOS_TABLE", "Videos")).get_item(
            Key={"video_id": video_id}, ProjectionExpression="user_id, #p, plan_interval, plan_source, plan_state", ExpressionAttributeNames={"#p": "plan"}).get("Item")
        return dict(it) if it else None
    except Exception:
        logging.exception("clip context unreadable")
        return None


def plan_of(ctx: Optional[Dict[str, Any]]) -> str:
    p = str((ctx or {}).get("plan") or "free")
    return p if p in clip_config.PLANS_ALL else "free"


def entitlement(ctx: Optional[Dict[str, Any]]) -> Optional[str]:
    """'paid' (an active Max plan bought in a store or on the web: the paying budget and the margin formula), 'test' (an unlimited test account, or a Max plan an admin
    granted: no revenue, so the separate test budget), or None (Free, Pro, a plan in its grace period, unknown: never generates)."""
    plan = plan_of(ctx)
    if plan == "test":
        return "test"
    if plan != "max" or plan not in clip_config.GENERATE_PLANS:
        return None
    if str(ctx.get("plan_state") or "active") != "active":
        return None
    return "paid" if ctx.get("plan_source") in PAYING_SOURCES else "test"


def credits_used(user_id: str, now: Optional[float] = None) -> int:
    """Credits charged to the account's videos created this calendar month (UTC) and not given back."""
    if "credits" in _readers:
        return int(_readers["credits"](user_id, now or time.time()))
    import boto3
    from boto3.dynamodb.conditions import Key

    tbl = boto3.resource("dynamodb").Table(os.environ.get("VIDEOS_TABLE", "Videos"))
    start = time.strftime("%Y-%m-01T00:00:00Z", time.gmtime(now))
    total, kw = 0, {}
    while True:
        r = tbl.query(IndexName=os.environ.get("GSI_USER_VIDEOS", "GSI_UserVideos"), KeyConditionExpression=Key("user_id").eq(user_id) & Key("created_at").gte(start),
                      ProjectionExpression="credits_charged, #s", ExpressionAttributeNames={"#s": "status"}, **kw)
        total += sum(int(i.get("credits_charged") or 0) for i in r.get("Items", []) if i.get("status") not in NO_CREDIT_STATUSES)
        if not r.get("LastEvaluatedKey"):
            return total
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def allowance_usd(kind: str, ctx: Dict[str, Any], cfg: Dict[str, Any], now: Optional[float] = None) -> float:
    if kind == "test":
        return float(cfg["test_account_cap_usd"])
    return clip_config.account_allowance_usd(str(ctx.get("plan_interval") or "month"), credits_used(str(ctx["user_id"]), now), cfg)


# ----------------------------------------------------------------------------- the demand log
def log_demand(store: cs.Store, brief: str, bvec: Any, video_id: str, cfg: Dict[str, Any]) -> int:
    """Count this video as asking for this general scene; a brief close enough to an earlier one joins its line. -> distinct videos that asked (this one included)."""
    now = int(time.time())
    key, best = clip_brief.brief_key(brief), -1.0
    for r in store.query(cs.DEMAND):
        if int(r.get("expires") or 0) < now or not r.get("vec"):
            continue
        s = float(bvec @ lib.unpack(r["vec"]))
        if s >= float(cfg["demand_join_score"]) and s > best:
            key, best = str(r["sk"]), s
    ref = lib.video_ref(video_id)
    store.add(cs.DEMAND, key, {"asks": 1}, sets={"videos": [ref]}, fields={"last": now, "expires": now + 180 * 86400, "ttl": now + 180 * 86400,
                                                                           **({"brief": brief, "vec": lib.pack(bvec), "first": now} if best < 0 else {})})
    row = store.get(cs.DEMAND, key) or {}
    return len(row.get("videos") or [ref])


# ----------------------------------------------------------------------------- the job
def _silent(mp4: bytes) -> bytes:
    """The provider's file without its audio track (the library is silent footage). The original bytes when ffmpeg cannot do it."""
    from . import media
    try:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a.mp4"), os.path.join(tmp, "b.mp4")
            with open(a, "wb") as fh:
                fh.write(mp4)
            p = subprocess.run([media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", a, "-an", "-c:v", "copy", "-movflags", "+faststart", b], capture_output=True, timeout=60)
            if p.returncode == 0 and os.path.getsize(b) > 10_000:
                with open(b, "rb") as fh:
                    return fh.read()
    except Exception:
        logging.exception("could not strip the audio of a generated clip")
    return mp4


class Job:
    """One decision that ended in 'a library clip may come': either already known (`clip_id` set), or a generation running in the background."""

    def __init__(self, store: cs.Store, *, clip_id: Optional[str] = None, outcome: str = "") -> None:
        self.store, self.clip_id, self.outcome = store, clip_id, outcome
        self.thread: Optional[threading.Thread] = None
        self.deadline = 0.0
        self.generated = False
        self.info: Dict[str, Any] = {}

    def wait(self) -> Optional[str]:
        """The clip id once it is in the library, or None when the generation is not ready by its deadline (the beat goes on without it)."""
        if self.thread is not None:
            self.thread.join(timeout=max(0.0, self.deadline - time.time()))
            if self.thread.is_alive():
                decision(self.store, "timeout", brief=self.info.get("brief"), waited=round(time.time() - self.info.get("t0", time.time()), 1))
                emit("Timeout")
                return None
        return self.clip_id


def _run(job: Job, *, store: cs.Store, cfg: Dict[str, Any], lines: List[Dict[str, Any]], kind: str, brief: Dict[str, Any], prompt: str, seconds: int, aspect: str,
         price: float, ledger: Tuple[str, str], claim: Tuple[str, str], lock_key: str, video_id: str) -> None:
    t0 = time.time()
    outcome, reason, charged, cid, gate = "provider_failed", "", price, None, {}
    try:
        try:
            made = clip_gen.provider(str(cfg["model"])).generate(prompt, seconds=seconds, aspect=aspect, timeout=float(cfg["gen_timeout_s"]))
        except clip_gen.GenError as e:
            outcome, reason = ("timeout" if e.kind == "timeout" else "provider_failed"), e.kind
            if not e.billed:   # refused before anything was made: the reservation goes back
                store.release(lines)
                charged = 0.0
                emit("SpendUsd", -price, "None", Kind=kind)
            emit("ProviderError", Kind=e.kind)
            return
        emit("GenerationSeconds", round(time.time() - t0, 1), "Seconds")
        gate = clip_gate.check(made["mp4"], brief["brief"], asked_seconds=seconds, aspect=aspect, min_score=float(cfg["gate_min_score"]))
        if not gate["ok"]:
            outcome, reason = "gate_rejected", str(gate["reason"])
            emit("Rejected", Reason=reason.split(":")[0][:40])
            return   # never used, never stored: only the ledger keeps its cost and why
        mp4 = _silent(made["mp4"])
        text = brief["brief"] + (". " + ", ".join(brief.get("tags") or []) if brief.get("tags") else "")
        cid = lib.add_clip(store, mp4=mp4, poster=gate["poster"], tvec=lib.embed("doc", text), ivec=lib.embed("image", gate["poster"]), meta={
            "brief": brief["brief"], "tags": brief.get("tags") or [], "people": brief.get("people"), "prompt": prompt, "provider": clip_gen.provider(str(cfg["model"])).name,
            "model": made.get("model"), "cost_usd": price, "seconds": gate["seconds"], "width": gate["width"], "height": gate["height"], "aspect": aspect,
            "center_safe": bool(gate["center_safe"]), "gate_score": gate["score"], "gate": gate.get("verdict"), "demand_video": lib.video_ref(video_id),
            "origin": store.label, "paid_by": kind})
        store.add(claim[0], claim[1], fields={"state": "done", "clip_id": cid})
        outcome, reason = "generated", "ok"
        job.clip_id, job.generated = cid, True
        emit("Generated")
    except Exception as e:   # noqa: BLE001 - a failure here must never reach the video
        logging.exception("clip generation failed")
        outcome, reason = "provider_failed", f"error {type(e).__name__}"
    finally:
        try:
            took = round(time.time() - t0, 1)
            store.add(ledger[0], ledger[1], fields={"outcome": outcome, "reason": reason[:120], "charged_usd": charged, "latency_s": took, "clip_id": cid,
                                                    "gate_score": gate.get("score"), "gate_usd": gate.get("cost_usd")})
            if outcome != "generated":
                store.add(claim[0], claim[1], fields={"state": outcome})
            store.delete(cs.LOCK, lock_key)
            _stat(store, **{f"g_{outcome}": 1, "g_latency_ds": int(took * 10), "g_n": 1})
            decision(store, outcome if outcome == "generated" else f"{outcome}:{reason}", brief=brief["brief"], seconds=seconds, charged_usd=charged, latency_s=took, clip=cid, kind=kind)
        except Exception:
            logging.exception("clip ledger not closed")


def begin(*, video_id: str, beat_id: str, query: str, alt: str, narration: str, need_seconds: float, orientation: str = "landscape", plan: Optional[Dict[str, Any]] = None,
          ctx: Optional[Dict[str, Any]] = None, is_edit: bool = False, beat_started: Optional[float] = None, now: Optional[float] = None,
          complete: Optional[Callable[..., Tuple[str, Dict[str, Any]]]] = None) -> Optional[Job]:
    """Decide and, when everything allows it, start. Never raises; None means 'nothing will come, carry on'."""
    store = None
    try:
        if not clip_config.flag():
            return None
        store = cs.current()
        if store is None:
            return None
        cfg = clip_config.config()
        kind = entitlement(ctx)
        if kind is None:
            return None   # Free, Pro, grace, unknown: not even a decision line (it would be every video)
        if not cfg["enabled"]:
            decision(store, "kill_switch")
            return None
        if is_edit:
            decision(store, "edit")
            return None
        if (plan or {}).get("media_items") or (plan or {}).get("deck"):
            decision(store, "own_photos")
            return None
        t = time.time() if now is None else now
        if beat_started is not None and t - beat_started > float(cfg["start_deadline_s"]):
            decision(store, "too_late", after=round(t - beat_started, 1))
            return None
        seconds = int(cfg["clip_seconds"]) if need_seconds <= cfg["clip_seconds"] + 0.5 else int(cfg["clip_seconds_long"])
        if MIN_FILL * need_seconds > seconds:
            decision(store, "too_long", need=round(need_seconds, 1))
            return None
        claim = (cs.VIDEO + video_id, f"beat:{beat_id}")
        old = store.get(*claim)
        if old is not None:   # this beat already asked (a retried beat): never pay twice
            decision(store, "retry", state=old.get("state"))
            return Job(store, clip_id=old.get("clip_id"), outcome="retry") if old.get("clip_id") else None

        brief, _cost = clip_brief.generalise(query, alt, narration, complete=complete)
        if not brief["reusable"]:
            decision(store, brief["reason"], query=query)
            return None
        aspect = "9:16" if orientation == "portrait" else "16:9"
        bvec = lib.embed("query", brief["brief"])
        near = lib.nearest_brief(bvec, orientation, store)
        if near is not None and near[0] >= float(cfg["reuse_min_score"]):
            decision(store, "library_hit", brief=brief["brief"], clip=near[1]["sk"], score=near[0])
            return Job(store, clip_id=str(near[1]["sk"]), outcome="library_hit")
        asked = log_demand(store, brief["brief"], bvec, video_id, cfg)
        budget_kind = "paid" if kind == "paid" else "test"
        day_limit, month_limit = float(cfg[f"{'platform' if kind == 'paid' else 'test'}_day_usd"]), float(cfg[f"{'platform' if kind == 'paid' else 'test'}_month_usd"])
        spent_today = cs.usd((store.get(cs.spend_pk(budget_kind, "day"), cs.day(t)) or {}).get("spent"))
        need_asks = max(int(cfg["min_demand"]), int(cfg["min_demand_tight"]) if day_limit > 0 and spent_today >= float(cfg["tight_share"]) * day_limit else 0)
        if asked < need_asks:
            decision(store, "low_demand", brief=brief["brief"], asked=asked, needed=need_asks)
            return None
        lock_key = clip_brief.brief_key(brief["brief"])
        if not store.put(cs.LOCK, lock_key, {"expires": int(t) + LOCK_S, "ttl": int(t) + LOCK_S, "video": lib.video_ref(video_id)}, only_if_absent=True, or_expired=int(t)):
            decision(store, "in_flight", brief=brief["brief"])
            return None

        price = clip_config.price_usd(seconds, cfg)
        allowance = allowance_usd(kind, ctx, cfg, t)
        keep = int(t) + 400 * 86400
        lines = [cs.line(cs.VIDEO + video_id, "n", 1, int(cfg["video_cap_clips"]), field="n", extra={"spent": cs.micro(price)}, ttl=int(t) + 90 * 86400),
                 cs.line(cs.ACCT + str(ctx["user_id"]), cs.month(t), cs.micro(price), cs.micro(allowance), extra={"n": 1}, ttl=keep),
                 cs.line(cs.spend_pk(budget_kind, "day"), cs.day(t), cs.micro(price), cs.micro(day_limit), extra={"n": 1}, ttl=keep),
                 cs.line(cs.spend_pk(budget_kind, "month"), cs.month(t), cs.micro(price), cs.micro(month_limit), extra={"n": 1}, ttl=keep)]
        failed = store.reserve(lines)
        if failed is not None:
            cap = ("video", "account", f"{'platform' if kind == 'paid' else 'test'}_day", f"{'platform' if kind == 'paid' else 'test'}_month")[failed] if failed >= 0 else "busy"
            store.delete(cs.LOCK, lock_key)
            emit("CapHit", Cap=cap)
            _stat(store, **{f"cap_{cap}": 1})
            if failed >= 2:
                emit("BudgetStop", Kind=budget_kind)
            decision(store, {"video": "cap_video", "account": "cap_account", "busy": "busy"}.get(cap, "budget_day" if cap.endswith("day") else "budget_month"),
                     brief=brief["brief"], kind=kind, price_usd=price, allowance_usd=allowance)
            return None
        emit("SpendUsd", price, "None", Kind=budget_kind)
        if not store.put(claim[0], claim[1], {"state": "started", "brief": brief["brief"], "at": int(t), "ttl": int(t) + 90 * 86400}, only_if_absent=True):
            store.release(lines)   # another attempt of the same beat got here first
            store.delete(cs.LOCK, lock_key)
            emit("SpendUsd", -price, "None", Kind=budget_kind)
            decision(store, "retry", state="raced")
            return None
        prompt = clip_brief.build_prompt(brief["brief"], people=str(brief.get("people") or "none"), aspect=aspect)
        ledger = (cs.ledger_pk(cs.month(t)), f"{int(t * 1000):013d}-{uuid.uuid4().hex[:6]}")
        store.put(ledger[0], ledger[1], {"at": int(t), "outcome": "started", "brief": brief["brief"], "query": clip_brief_safe(query), "seconds": seconds, "aspect": aspect, "kind": budget_kind,
                                         "reserved_usd": price, "charged_usd": price, "account": lib.account_ref(str(ctx["user_id"])), "video": lib.video_ref(video_id),
                                         "asked": asked, "allowance_usd": allowance, "ttl": int(t) + 500 * 86400})
        job = Job(store, outcome="generating")
        job.info = {"brief": brief["brief"], "t0": time.time(), "price": price, "kind": budget_kind}
        job.deadline = time.time() + float(cfg["gen_timeout_s"]) + WAIT_AFTER_S
        job.thread = threading.Thread(target=_run, name="clipgen", daemon=True, kwargs=dict(
            job=job, store=store, cfg=cfg, lines=lines, kind=budget_kind, brief=brief, prompt=prompt, seconds=seconds, aspect=aspect, price=price, ledger=ledger, claim=claim,
            lock_key=lock_key, video_id=video_id))
        job.thread.start()
        return job
    except Exception:   # noqa: BLE001 - the video goes on without the feature
        logging.exception("clips on demand: decision failed")
        try:
            decision(store, "error")
        except Exception:
            pass
        return None


def clip_brief_safe(query: str) -> str:
    """The director's wording as the ledger may keep it: only when the privacy filter calls it generic (it passed pre_filter to get here), cut short."""
    return " ".join(str(query or "").split())[:80]


def used(video_id: str, chosen: Any, *, generated_id: Optional[str] = None) -> None:
    """The video really shows library clip(s): count the use (per clip and per distinct video) and say whether it was made for this video or reused."""
    try:
        store = cs.current()
        if store is None:
            return
        for key in ([chosen] if isinstance(chosen, str) else list(chosen or [])):
            for part in str(key).split(","):
                if part.startswith(lib.PROVIDER + ":"):
                    cid = part.split(":", 1)[1]
                    lib.record_use(cid, video_id, store)
                    src = "generated" if cid == generated_id else "library"
                    emit("Used", Source=src)
                    _stat(store, **{f"used_{src}": 1})
    except Exception:
        logging.exception("clip use not recorded")
