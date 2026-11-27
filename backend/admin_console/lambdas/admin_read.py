"""GET /api/home : everything the console's one screen shows, in one answer. Read only.

API Gateway has checked the token before this code runs. This function may read: the rollup table (counts, no account ids, no text), the two switches
(one item), today's free-budget counter (one item), the plans parameter, the names and start times of the runs in progress, and the state of the alarms.
It cannot read a video record, a prompt, an account or an email address, and it cannot write anything."""
import logging
import os
import time
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key

import admin_common as c

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DAYS = 7
MAX_FAILURES = 50
DAY_FIELDS = ("day", "started", "complete", "failed", "cancelled", "rejected", "in_progress", "failure_rate", "cost_tracked", "compute_usd", "cost_all_in", "cost_per_video", "lost_usd",
              "cost_failed", "cost_cancelled", "make_p50_s", "make_p95_s", "make_n", "signups", "active_accounts", "credits_charged", "free_credits", "updated_at", "source", "partial")
FAIL_FIELDS = ("at", "status", "step", "cause", "code", "cost_usd", "plan", "length_s", "credits", "aspect", "resolution", "retries", "video_id")


def part(out: Dict[str, Any], name: str, fn: Any) -> None:
    """Each live part answers by itself: one that fails is reported as unavailable, the rest is still shown."""
    try:
        out[name] = fn()
    except Exception:   # noqa: BLE001
        logger.exception("ADMIN_READ_PART_FAILED %s", name)
        out[name] = {"error": True}


def days(now: float) -> List[Dict[str, Any]]:
    t = c.table("ROLLUP_TABLE")
    keys = [{"pk": "day#" + c.day_of(now - i * 86400), "sk": "all"} for i in range(DAYS - 1, -1, -1)]
    got = {i["day"]: i for i in (t.get_item(Key=k).get("Item") for k in keys) if i}
    return [{k: got[d].get(k) for k in DAY_FIELDS} if d in got else {"day": d, "missing": True} for d in (k["pk"][4:] for k in keys)]


def failures(now: float) -> List[Dict[str, Any]]:
    t, out = c.table("ROLLUP_TABLE"), []
    for i in range(DAYS):
        if len(out) >= MAX_FAILURES:
            break
        res = t.query(KeyConditionExpression=Key("pk").eq("fail#" + c.day_of(now - i * 86400)), ScanIndexForward=False, Limit=MAX_FAILURES - len(out))
        out += [{k: it.get(k) for k in FAIL_FIELDS} for it in res.get("Items", [])]
    return out


def running(now: float) -> Dict[str, Any]:
    res = c.client("stepfunctions").list_executions(stateMachineArn=os.environ["STATE_MACHINE_ARN"], statusFilter="RUNNING", maxResults=200)
    ages = [int((now - x["startDate"].timestamp()) // 60) for x in res.get("executions", [])]
    return {"count": len(ages), "more": bool(res.get("nextToken")), "oldest_minutes": max(ages) if ages else None}


def budget(now: float) -> Dict[str, Any]:
    k = c.budget_knobs()
    spent, limit, per = c.budget_spent(c.day_of(now)), int(k["free_daily_budget_credits"]), float(k["cost_per_credit_usd"])
    return {"spent": spent, "limit": limit, "unlimited": bool(k["free_budget_unlimited"]), "usd_per_credit": per, "spent_usd": round(spent * per, 2), "limit_usd": round(limit * per, 2)}


def alarms() -> Dict[str, Any]:
    """The alarms of VideoMK on this stage (the account may hold other projects' alarms: they are left out)."""
    cw, token, mine = c.client("cloudwatch"), None, []
    prefixes = tuple(p for p in os.environ.get("ALARM_PREFIXES", "").split(",") if p)
    for _ in range(10):
        res = cw.describe_alarms(AlarmTypes=["MetricAlarm"], MaxRecords=100, **({"NextToken": token} if token else {}))
        mine += [a for a in res.get("MetricAlarms", []) if a["AlarmName"].startswith(prefixes)]
        token = res.get("NextToken")
        if not token:
            break
    firing = [{"name": a["AlarmName"], "what": (a.get("AlarmDescription") or "")[:200], "since": c.iso(a["StateUpdatedTimestamp"].timestamp())} for a in mine if a["StateValue"] == "ALARM"]
    return {"total": len(mine), "firing": firing}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    who = c.claims(event)
    if not who.get("sub"):   # cannot happen behind the authorizer; refuse anyway
        return c.response(401, {"code": "unauthorized", "message": "Sign in first."})
    now = time.time()
    age = c.auth_age(event, now)
    out: Dict[str, Any] = {"stage": c.stage(), "now": c.iso(now), "session": {"signed_in_seconds_ago": int(age) if age is not None else None, "step_up_seconds": c.STEP_UP_SECONDS,
                                                                          "can_switch": age is not None and -60 <= age <= c.STEP_UP_SECONDS}}
    part(out, "days", lambda: days(now))
    part(out, "meta", lambda: c.plain(c.table("ROLLUP_TABLE").get_item(Key={"pk": "meta", "sk": "rollup"}).get("Item") or {"missing": True}))
    part(out, "failures", lambda: failures(now))
    part(out, "running", lambda: running(now))
    part(out, "budget", lambda: budget(now))
    part(out, "switches", c.switches)
    part(out, "alarms", alarms)
    return c.response(200, out)
