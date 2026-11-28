"""Paid dictation: who may, how much is left today, and the record of every dictation (docs/SPEECH_TO_TEXT_2026-11-28.md). The audio is never kept; only counters.

All in the existing usage table (no new table), UTC days, TTL on every item:
  {user_id: 'stt:<user>',    day: 'YYYY-MM-DD'}  seconds        what this account has used today (the daily cap, atomic ADD with a condition)
  {user_id: 'stt:global',    day: 'YYYY-MM-DD'}  seconds        what ALL accounts have used today (the global ceiling)
  {user_id: 'sttrec:<user>', day: <dictation id>} seconds, cost_usd, model, language, created   one record per dictation; a video that names it in `dictation_ids` is charged `c_stt`

Plan right: `stt_premium` (Pro and Max; unlimited test accounts have Max's rights, they follow common/entitlements). Free keeps the phone's engine.
Kill switches: the knob `stt_enabled` and the ops item `stop_dictation` (true = stopped; set by hand like the other switches, fails open).
"""
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from common import entitlements, ops_switches, plans

logger = logging.getLogger()
STOP_SWITCH = "stop_dictation"
ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_IDS_PER_VIDEO = 20
TTL_S = 40 * 86400


class Refused(Exception):
    """`code` (stable, for the apps), HTTP `status`, the plans.PlanError that carries the localized answer."""

    def __init__(self, error: plans.PlanError):
        super().__init__(error.code)
        self.error = error


class Paused(Exception):
    pass


def _table():
    return boto3.resource("dynamodb").Table(os.environ["USAGE_TABLE"])


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _int(v: Any) -> int:
    return int(v) if v is not None else 0


def used_today(user: str, day: Optional[str] = None) -> int:
    return _int((_table().get_item(Key={"user_id": f"stt:{user}", "day": day or today()}).get("Item") or {}).get("seconds"))


def plan_rights(user: str, cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    cfg = plans.config() if cfg is None else cfg
    ent = entitlements.effective(user)
    r = plans.rights(ent["plan"], cfg)
    if ent["unlimited"]:   # staff and test accounts (never in production): Max's rights, no plan cap, but a ceiling and a trail in case the token is ever stolen (like UNLIMITED_DAILY_VIDEOS)
        r["stt_seconds_per_day"] = int(os.environ.get("UNLIMITED_DAILY_STT_SECONDS", "7200"))
    return ent["plan"], r


def paused(cfg: Dict[str, Any]) -> bool:
    return (not cfg["stt_enabled"]) or ops_switches.stopped(STOP_SWITCH)


def check(user: str, cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """The plan and its rights, or raises Paused / Refused (plan lacks the right, or today's seconds are used)."""
    cfg = plans.config() if cfg is None else cfg
    if paused(cfg):
        raise Paused()
    plan, r = plan_rights(user, cfg)
    if not r["stt_premium"] or int(r["stt_seconds_per_day"]) <= 0:
        raise Refused(plans.PlanError("dictation_plan", "plan.dictation", plan=plan, requires_plan=plans.lowest_plan(lambda x: x["stt_premium"]), feature="dictation",
                                      limit={"stt_seconds_per_day": int(r["stt_seconds_per_day"])}))
    return plan, r


def _quota_error(plan: str, r: Dict[str, Any], cfg: Dict[str, Any], scope: str) -> plans.PlanError:
    nxt = plans.lowest_plan(lambda x: x["stt_seconds_per_day"] > r["stt_seconds_per_day"], cfg) if scope == "user" else None
    return plans.PlanError("dictation_quota" if scope == "user" else "dictation_paused", "dictation.quota" if scope == "user" else "dictation.paused", status=429 if scope == "user" else 503,
                           plan=plan, requires_plan=nxt, feature="dictation", limit={"stt_seconds_per_day": int(r["stt_seconds_per_day"])})


def _add(key: str, day: str, n: float, cap: Optional[int]) -> None:
    kw: Dict[str, Any] = {}
    vals = {":n": Decimal(str(round(n, 3))), ":ttl": int(time.time()) + 3 * 86400}
    if cap is not None:
        kw["ConditionExpression"] = "attribute_not_exists(seconds) OR seconds <= :room"
        vals[":room"] = Decimal(str(round(cap - n, 3)))
    _table().update_item(Key={"user_id": key, "day": day}, UpdateExpression="ADD seconds :n SET #t = :ttl", ExpressionAttributeNames={"#t": "ttl"}, ExpressionAttributeValues=vals, **kw)


def reserve(user: str, seconds: float, plan: str, r: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    """Take `seconds` from today's account allowance and from the global ceiling (atomic). Returns the day (the settle/refund must use the same one).
    Raises Refused: 429 `dictation_quota` (the account's seconds are used) or 503 `dictation_paused` (the global ceiling)."""
    day, cap = today(), int(r["stt_seconds_per_day"])
    try:
        _add(f"stt:{user}", day, seconds, cap)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise Refused(_quota_error(plan, r, cfg, "user")) from e
        raise
    try:
        _add("stt:global", day, seconds, int(cfg["stt_global_daily_seconds"]))
    except ClientError as e:
        _add(f"stt:{user}", day, -seconds, None)
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise Refused(_quota_error(plan, r, cfg, "global")) from e
        raise
    return day


def settle(user: str, day: str, reserved: float, actual: float) -> None:
    """The provider told us the real length: correct both counters by the difference (no condition: at most one clip over the cap, the next one is refused)."""
    delta = round(float(actual) - float(reserved), 3)
    if delta:
        for key in (f"stt:{user}", "stt:global"):
            _add(key, day, delta, None)


def release(user: str, day: str, seconds: float) -> None:
    """The provider failed: give the whole reservation back (best effort)."""
    try:
        for key in (f"stt:{user}", "stt:global"):
            _add(key, day, -seconds, None)
    except Exception:   # noqa: BLE001
        logger.exception("DICTATION_RELEASE_FAILED user=%s", user)


def record(user: str, dictation_id: str, result: Dict[str, Any]) -> None:
    _table().put_item(Item={"user_id": f"sttrec:{user}", "day": dictation_id, "seconds": Decimal(str(round(result["seconds"], 3))), "cost_usd": Decimal(str(result["cost_usd"])),
                            "model": result["model"], "language": result.get("language") or "", "created": int(time.time()), "ttl": int(time.time()) + TTL_S})


def totals(user: str, ids: Iterable[str]) -> Tuple[float, float, List[str]]:
    """(seconds, cost_usd, the ids used) of the dictations a video names. Each must be this account's own record; a repeated id counts once. Raises ValueError for a bad id
    shape, too many ids, or an id that is not this account's (or has expired): the launcher answers 400."""
    ids = list(dict.fromkeys(ids))
    if len(ids) > MAX_IDS_PER_VIDEO or not all(isinstance(i, str) and ID_RE.match(i) for i in ids):
        raise ValueError("'dictation_ids' must be a list of at most %d dictation ids" % MAX_IDS_PER_VIDEO)
    sec, usd = Decimal(0), Decimal(0)
    for i in ids:
        it = _table().get_item(Key={"user_id": f"sttrec:{user}", "day": i}).get("Item")
        if not it:
            raise ValueError("unknown dictation id")
        sec += Decimal(str(it.get("seconds", 0)))
        usd += Decimal(str(it.get("cost_usd", 0)))
    return float(sec), float(usd), ids


def capabilities(user: str, plan_limits: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the apps need to show or hide 'Better dictation' (GET .../capabilities, field `dictation`). Reading usage must never stop the answer."""
    cfg = plans.config() if cfg is None else cfg
    has, cap = bool(plan_limits.get("stt_premium")), int(plan_limits.get("stt_seconds_per_day") or 0)
    is_paused = paused(cfg)
    left = None
    if has and cap:
        try:
            left = max(0, cap - used_today(user))
        except Exception:   # noqa: BLE001
            logger.exception("DICTATION_USAGE_READ_FAILED")
    return {"premium": has, "available": bool(has and cap and not is_paused and (left is None or left > 0)), "paused": bool(is_paused), "seconds_per_day": cap, "seconds_left_today": left,
            "max_clip_seconds": int(cfg["stt_max_clip_seconds"]), "max_clip_bytes": MAX_AUDIO_BYTES, "requires_plan": None if has else plans.lowest_plan(lambda x: x["stt_premium"], cfg),
            "provider": "openai"}


MAX_AUDIO_BYTES = 3 * 1024 * 1024
