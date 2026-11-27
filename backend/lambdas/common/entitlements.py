"""The entitlements record: ONE item per account that says which plan it has (docs/PLANS.md).

  {user_id, plan: free|pro|max, state: active|grace|expired|refunded, source: admin|apple|google|web, interval: month|year,
   anchor (when this subscription began: the monthly credit dates count from it), period_start, period_end (None = no end), grace_until, renews, product_id, updated_at, log}

Who may touch it: the table (ENTITLEMENTS_TABLE) is READ-ONLY for every function that handles a request; the writers are a person with AWS admin credentials
(`scripts/wallet_admin.py plan ...`), the account-deletion worker (DeleteItem only) and, in phase 2, the purchase-verification and store-webhook functions. No route lets a
person change a plan, and the owner of a record reads it only through GET .../plan, .../wallet and .../capabilities (path user = token sub).

`effective()` is the one answer to "which plan applies now": the record's dates decide (an `active` record past its period end without grace IS expired, no job has to flip it),
`refunded` and `expired` are Free, and an unlimited test account (flags table, never in production) has the rights of Max without a record and without plan credits.
"""
import calendar
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3

from common import plans

STATES = ("active", "grace", "expired", "refunded")
SOURCES = ("admin", "apple", "google", "web")
INTERVALS = ("month", "year")
_ddb = None


def set_resource(resource: Any) -> None:   # tests
    global _ddb
    _ddb = resource


def table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb.Table(os.environ["ENTITLEMENTS_TABLE"])


def add_months(epoch: float, months: int) -> int:
    """The same day of the month `months` later (UTC), clamped to the month's last day: 31 Jan + 1 = 28 Feb. Always counted from the anchor, so the day never drifts."""
    d = datetime.fromtimestamp(int(epoch), timezone.utc)
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return int(d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1])).timestamp())


def get(user: str) -> Optional[Dict[str, Any]]:
    if not os.environ.get("ENTITLEMENTS_TABLE") or not user:
        return None
    return table().get_item(Key={"user_id": user}, ConsistentRead=True).get("Item")


def _num(v: Any) -> Optional[int]:
    return None if v is None else int(v)


def evaluate(item: Optional[Dict[str, Any]], *, now: Optional[float] = None, unlimited: bool = False) -> Dict[str, Any]:
    """Pure: the record (or None) -> what applies at `now`."""
    now = time.time() if now is None else now
    out: Dict[str, Any] = {"plan": "free", "state": "active", "source": None, "interval": None, "anchor": None, "period_start": None, "period_end": None, "grace_until": None,
                           "renews": False, "product_id": None, "record_plan": None, "unlimited": bool(unlimited), "grants_credits": False}
    if item and item.get("plan") in plans.PLANS and item.get("plan") != "free":
        state = item.get("state") if item.get("state") in STATES else "expired"
        end, grace = _num(item.get("period_end")), _num(item.get("grace_until"))
        if state in ("active", "grace"):
            if end is None or now < end:
                state = "active" if state == "active" else "grace"
            elif grace is not None and now < grace:
                state = "grace"
            else:
                state = "expired"
        out.update({"record_plan": item["plan"], "state": state, "source": item.get("source"), "interval": item.get("interval"), "anchor": _num(item.get("anchor")),
                    "period_start": _num(item.get("period_start")), "period_end": end, "grace_until": grace, "renews": bool(item.get("renews")), "product_id": item.get("product_id")})
        if state in ("active", "grace"):
            out["plan"], out["grants_credits"] = item["plan"], True
    if out["plan"] != "max" and unlimited:   # staff and test accounts: every right, no plan credits (they are never charged)
        out["plan"] = "max"
    return out


def effective(user: str, *, now: Optional[float] = None, unlimited: Optional[bool] = None) -> Dict[str, Any]:
    if not plans.enabled():
        return evaluate(None, now=now)
    if unlimited is None:
        from common import wallet
        unlimited = wallet.is_unlimited(user)
    return evaluate(get(user), now=now, unlimited=unlimited)


def plan_of(user: str, *, now: Optional[float] = None) -> str:
    return effective(user, now=now)["plan"]


# ----------------------------------------------------------------------------- the writers (admin now; store verification in phase 2). Never called by a request handler.
def _log(item: Optional[Dict[str, Any]], action: str, now: float, by: str) -> list:
    return (list((item or {}).get("log") or []) + [{"at": int(now), "action": action, "by": by}])[-20:]


def set_plan(user: str, plan: str, *, until: Optional[int] = None, interval: str = "month", source: str = "admin", renews: bool = False, anchor: Optional[int] = None,
             product_id: Optional[str] = None, now: Optional[float] = None, by: str = "admin") -> Dict[str, Any]:
    """Give the account `plan` from now (`until`: the end of the paid period, None = no end). `plan='free'` ends a plan at once (state expired). A new call starts a new subscription
    (a new anchor) unless `anchor` is given, which is how a renewal keeps its monthly dates. One record per account: whatever source wrote before is replaced."""
    now = time.time() if now is None else now
    if plan not in plans.PLANS or source not in SOURCES or interval not in INTERVALS:
        raise ValueError("unknown plan, source or interval")
    if until is not None and until <= now:
        raise ValueError("'until' must be in the future")
    old = get(user)
    if plan == "free":
        item = {**(old or {"user_id": user, "plan": "free"}), "state": "expired", "renews": False, "updated_at": int(now), "log": _log(old, "ended", now, by)}
    else:
        item = {"user_id": user, "plan": plan, "state": "active", "source": source, "interval": interval, "anchor": int(anchor if anchor is not None else now), "period_start": int(now),
                "renews": bool(renews), "updated_at": int(now), "log": _log(old, f"plan:{plan}", now, by)}
        if until is not None:
            item["period_end"] = int(until)
        if product_id:
            item["product_id"] = product_id
    table().put_item(Item=item)
    return item


def set_state(user: str, state: str, *, grace_until: Optional[int] = None, now: Optional[float] = None, by: str = "admin") -> Optional[Dict[str, Any]]:
    """grace (a renewal payment is being retried: rights stay until grace_until, no new credits), expired, refunded (back to Free; the caller also removes the unused
    plan credits: wallet.revoke_plan_credits) or active again."""
    now = time.time() if now is None else now
    if state not in STATES:
        raise ValueError("unknown state")
    old = get(user)
    if not old:
        return None
    item = {**old, "state": state, "updated_at": int(now), "log": _log(old, state, now, by)}
    if state == "grace":
        item["grace_until"] = int(grace_until if grace_until is not None else now + 16 * 86400)   # the stores' billing grace period (16 days, docs/PLANS.md)
    if state in ("expired", "refunded"):
        item["renews"] = False
    table().put_item(Item=item)
    return item


def delete(user: str) -> None:
    """Account deletion only."""
    table().delete_item(Key={"user_id": user})


def public(ent: Dict[str, Any]) -> Dict[str, Any]:
    """The part of the effective entitlement the owner of the account may see."""
    def iso(v: Optional[int]) -> Optional[str]:
        return None if v is None else datetime.fromtimestamp(int(v), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": ent["plan"], "name": plans.PLANS[ent["plan"]]["name"], "state": ent["state"], "source": ent["source"], "managed_by": ent["source"], "interval": ent["interval"],
            "period_start": iso(ent["period_start"]), "period_end": iso(ent["period_end"]), "grace_until": iso(ent["grace_until"]), "renews": ent["renews"],
            "previous_plan": ent["record_plan"] if ent["record_plan"] and ent["record_plan"] != ent["plan"] else None, "test_account": ent["unlimited"],
            "can_upgrade": plans.PURCHASES_LIVE}
