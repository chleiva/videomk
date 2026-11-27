"""Free versus paid usage for one UTC day (docs/PLANS.md, "Measurement"): the numbers behind the daily metric (lambdas/plans_daily.py) and the admin report
(scripts/plans_admin.py report). Read only.

A video row says which plan made it (`plan`: free | pro | max | test, written by the launcher) and how many of its credits were free ones (`free_credits`); the engine
adds `cost_usd` when it finishes (models, speech, searches: NOT the Lambda compute, about $0.07 a minute more). Two cost figures are therefore given for free usage:
`tracked_usd` (the sum of cost_usd) and `estimated_usd` (free credits x the knob cost_per_credit_usd, the measured all-in cost per credit).
"""
import os
from typing import Any, Dict, Iterable, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr

from common import plans


def videos_of_day(day: str, table: Any = None) -> List[Dict[str, Any]]:
    """Every video row started on `day` (the launcher's `usage_day`). A scan with a filter: fine at today's size; give the table an index by day when it is not."""
    table = table or boto3.resource("dynamodb").Table(os.environ["VIDEOS_TABLE"])
    rows, kwargs = [], {"FilterExpression": Attr("usage_day").eq(day), "ProjectionExpression": "video_id, user_id, #p, free_credits, credits_charged, cost_usd, #s, refunded",
                        "ExpressionAttributeNames": {"#p": "plan", "#s": "status"}}
    while True:
        res = table.scan(**kwargs)
        rows += res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            return rows
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def summarize(day: str, rows: Iterable[Dict[str, Any]], *, stats: Optional[Dict[str, Any]] = None, budget_spent: Optional[int] = None, cfg: Optional[Dict[str, Any]] = None, top: int = 10) -> Dict[str, Any]:
    cfg = plans.config() if cfg is None else cfg
    per = float(cfg["cost_per_credit_usd"])
    videos: Dict[str, int] = {"free": 0, "pro": 0, "max": 0, "test": 0, "unknown": 0}
    tracked: Dict[str, float] = {k: 0.0 for k in videos}
    credits = {"free": 0, "paid": 0}
    users: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        kind = r.get("plan") if r.get("plan") in videos else "unknown"
        cost = float(r.get("cost_usd") or 0)
        free_n = int(r.get("free_credits") or 0)
        charged = 0 if r.get("refunded") else int(r.get("credits_charged") or 0)
        videos[kind] += 1
        tracked[kind] += cost
        if kind == "free" or free_n:
            n = min(free_n, charged) if charged else 0
            credits["free"] += n
            credits["paid"] += max(0, charged - n)
            u = users.setdefault(str(r.get("user_id") or "?"), {"videos": 0, "free_credits": 0, "tracked_usd": 0.0})
            u["videos"] += 1
            u["free_credits"] += n
            u["tracked_usd"] += cost
        elif kind != "test":
            credits["paid"] += charged
    n_users = len(users)
    free_tracked, free_est = round(tracked["free"], 4), round(credits["free"] * per, 4)
    stats = {k: int(v) for k, v in (stats or {}).items() if k not in ("user_id", "day", "ttl")}
    out = {
        "day": day, "videos": videos, "paid_videos": videos["pro"] + videos["max"], "credits": credits,
        "free": {"videos": videos["free"], "users": n_users, "tracked_usd": free_tracked, "estimated_usd": free_est, "cost_per_credit_usd": per,
                 "tracked_usd_per_user": round(free_tracked / n_users, 4) if n_users else 0.0, "estimated_usd_per_user": round(free_est / n_users, 4) if n_users else 0.0},
        "paid_tracked_usd": round(tracked["pro"] + tracked["max"], 4),
        "top_free_users": [{"user": u, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}, "estimated_usd": round(d["free_credits"] * per, 4)}
                           for u, d in sorted(users.items(), key=lambda kv: (-kv[1]["free_credits"], -kv[1]["tracked_usd"]))[:top]],
        "budget": {"limit_credits": None if cfg["free_budget_unlimited"] else int(cfg["free_daily_budget_credits"]), "spent_credits": budget_spent,
                   "limit_usd": None if cfg["free_budget_unlimited"] else plans.usd(cfg["free_daily_budget_credits"], cfg)},
        "claims": {"granted": stats.get("granted", 0), "refused": {k[len("refused_"):]: v for k, v in sorted(stats.items()) if k.startswith("refused_")},
                   "budget_refused": stats.get("budget_refused", 0), "cap_refused": stats.get("cap_refused", 0),
                   "device_refused": {k[len("device_refused_"):]: v for k, v in sorted(stats.items()) if k.startswith("device_refused_")}},
    }
    return out


def day_counters(day: str, usage_table: Any = None) -> Dict[str, Any]:
    usage_table = usage_table or boto3.resource("dynamodb").Table(os.environ["USAGE_TABLE"])
    stats = usage_table.get_item(Key={"user_id": "fstat", "day": day}).get("Item") or {}
    budget = usage_table.get_item(Key={"user_id": "fbudget", "day": day}).get("Item") or {}
    return {"stats": stats, "budget_spent": int(budget.get("count") or 0)}


def ip_blocks(day: str, usage_table: Any, top: int = 10) -> List[Dict[str, Any]]:
    """The address blocks (/24, /48) that claimed the most free allowances on `day` (admin report only)."""
    rows, kwargs = [], {"FilterExpression": Attr("user_id").begins_with("fblk:") & Attr("day").eq(day)}
    while True:
        res = usage_table.scan(**kwargs)
        rows += res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            break
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]
    return [{"block": r.get("block") or "?", "claims": int(r.get("count") or 0)} for r in sorted(rows, key=lambda r: -int(r.get("count") or 0))[:top]]


def shared_identities(claims_table: Any, top: int = 10) -> Dict[str, Any]:
    """How many claimed identities exist, and the ones several accounts tried to use (n = 1 claim + refused attempts). Keys are salted hashes: shown shortened, never reversible."""
    rows, kwargs = [], {"ProjectionExpression": "pk, kind, n, #d", "ExpressionAttributeNames": {"#d": "day"}}
    while True:
        res = claims_table.scan(**kwargs)
        rows += res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            break
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]
    multi = sorted((r for r in rows if int(r.get("n") or 1) > 1), key=lambda r: -int(r.get("n") or 1))
    kinds = {"e": "email", "f": "sign-in identity", "d": "device"}
    return {"claims": len(rows), "by_kind": {v: sum(1 for r in rows if str(r.get("pk", ""))[:1] == k) for k, v in kinds.items()}, "shared": len(multi),
            "top": [{"identity": str(r["pk"])[:14] + "...", "kind": kinds.get(str(r["pk"])[:1], "?"), "accounts": int(r.get("n") or 1), "first_claim": r.get("day")} for r in multi[:top]]}
