"""Library media on demand (docs/LIBRARY_ON_DEMAND.md): what clips, images and whiteboard objects share. ONE framework, three media types:

    generalise the search -> check OUR library -> generate -> quality gate -> into OUR library -> only then into the video

This module is the common part: who may generate and which budget pays (`entitlement`), the account's allowance (ONE invariant for all three types),
the reservation of money (`reserve`: ONE transaction over the video's count, the account's total, the account's share for this type, and the day and month
budgets of this type), and the observability (`decision`, `emit`, the counters the report reads). The type-specific parts live in clip_ondemand.py,
image_ondemand.py and object_ondemand.py.
"""
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from common import clip_config, clip_store as cs

MEDIA = ("clip", "image", "object")

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


def stats_sk(media: str = "clip", now: Optional[float] = None) -> str:
    return cs.day(now) if media == "clip" else f"{cs.day(now)}:{media}"


def _stat(store: cs.Store, media: str = "clip", **counters: int) -> None:
    try:
        store.add(cs.STATS, stats_sk(media), {k: int(v) for k, v in counters.items()}, fields={"ttl": int(time.time()) + 400 * 86400})
    except Exception:
        logging.exception("clip stat not written")


def decision(store: Optional[cs.Store], outcome: str, media: str = "clip", **info: Any) -> None:
    """Every decision, with its reason: a log line, a metric by reason code, and a counter of the day (per media type)."""
    code = outcome.split(":", 1)[0]
    logging.warning("%s_DECISION %s", media.upper(), json.dumps({"outcome": outcome, **{k: v for k, v in info.items() if v is not None}}, ensure_ascii=False, default=str)[:900])
    emit("Decisions", Outcome=code, **({} if media == "clip" else {"Media": media}))
    if store is not None:
        _stat(store, media, **{f"d_{code}": 1})


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
    """The account's TOTAL allowance of the month for all media types together: the invariant's number."""
    if kind == "test":
        return float(cfg["test_account_cap_usd"])
    return clip_config.account_allowance_usd(str(ctx.get("plan_interval") or "month"), credits_used(str(ctx["user_id"]), now), cfg)


def reserve(store: cs.Store, cfg: Dict[str, Any], *, media: str, kind: str, ctx: Dict[str, Any], video_id: str, price: float, now: Optional[float] = None,
            count: int = 1) -> Tuple[Optional[List[Dict[str, Any]]], str, float]:
    """Reserve `price` dollars for one generation of `media` in ONE transaction, or nothing at all. -> (lines to release later | None, reason code, the account's allowance).
    Five counters, each with its own limit: this video's generations of this type; the account's TOTAL of the month (the invariant: all three media types share it);
    the account's share for this type; this type's day budget; this type's month budget (the paying ones, or the test ones for accounts that bring no revenue).
    Reason codes: '' (reserved), cap_video, cap_account, cap_account_type, budget_day, budget_month, busy."""
    t = time.time() if now is None else now
    lim = clip_config.limits(cfg, media, kind)
    allowance = allowance_usd(kind, ctx, cfg, t)
    keep, user, m = int(t) + 400 * 86400, str(ctx["user_id"]), cs.micro(price)
    lines = [cs.line(cs.VIDEO + video_id, "n" if media == "clip" else f"n:{media}", count, int(lim["video_cap"]), field="n", extra={"spent": m}, ttl=int(t) + 90 * 86400),
             cs.line(cs.ACCT + user, cs.month(t), m, cs.micro(allowance), extra={"n": 1}, ttl=keep),
             cs.line(cs.ACCT + user, f"{cs.month(t)}:{media}", m, cs.micro(lim["account_cap"]), extra={"n": 1}, ttl=keep),
             cs.line(cs.spend_pk(kind, "day", media), cs.day(t), m, cs.micro(lim["day"]), extra={"n": 1}, ttl=keep),
             cs.line(cs.spend_pk(kind, "month", media), cs.month(t), m, cs.micro(lim["month"]), extra={"n": 1}, ttl=keep)]
    failed = store.reserve(lines)
    if failed is None:
        emit("SpendUsd", price, "None", Kind=kind, **({} if media == "clip" else {"Media": media}))
        return lines, "", allowance
    scope = "platform" if kind == "paid" else "test"
    cap = ("video", "account", "account_type", f"{scope}_day", f"{scope}_month")[failed] if failed >= 0 else "busy"
    emit("CapHit", Cap=cap, **({} if media == "clip" else {"Media": media}))
    _stat(store, media, **{f"cap_{cap}": 1})
    if failed >= 3:
        emit("BudgetStop", Kind=kind, **({} if media == "clip" else {"Media": media}))
    reason = {"video": "cap_video", "account": "cap_account", "account_type": "cap_account_type", "busy": "busy"}.get(cap, "budget_day" if cap.endswith("day") else "budget_month")
    return None, reason, allowance


def release(store: cs.Store, lines: List[Dict[str, Any]], *, media: str, kind: str, price: float) -> None:
    """Give a reservation back (the provider refused before making anything)."""
    store.release(lines)
    emit("SpendUsd", -price, "None", Kind=kind, **({} if media == "clip" else {"Media": media}))


def spent_today(store: cs.Store, kind: str, media: str, now: Optional[float] = None) -> float:
    return cs.usd((store.get(cs.spend_pk(kind, "day", media), cs.day(now)) or {}).get("spent"))


