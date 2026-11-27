"""The hourly rollup job of the owner console (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md sections 2.3, 2.4, 5.2).

Every run RECOMPUTES today and yesterday (UTC) from the video records and overwrites their rollups, so a run that fails or runs twice does no harm.
Days older than that are never touched again: they stay as they were, also after accounts are deleted (they hold counts only, no account ids, no text).

Reads (read only): the videos of a day through the day index (small fields, never the prompt), the list of workflow runs (times only), the step where a
failed run broke (run history WITHOUT its data), the free-budget counter, the plans parameter, the customer pool's user list (creation dates only), the
Lambda metrics of the engine functions. Writes: the rollup table. Sends: the alerts of section 5.2 that it can judge itself (videos failing, a stuck
run, the free budget at 80 % and 100 %). A heartbeat metric is written at the end of each run; an alarm fires when it stops.
"""
import datetime
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

import admin_common as c

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INDEX = "GSI_UsageDay"
# exactly what the day index carries (backend_stack.USAGE_DAY_FIELDS + the keys); the fallback scan may read these attributes and no others (its policy says so)
FIELDS = ("video_id", "usage_day", "created_at", "status", "plan", "user_id", "cost_usd", "c_speech", "c_script", "c_research", "c_photos", "c_stock", "c_deck", "duration_s",
          "aspect", "resolution", "failure_code", "credits_charged", "credits_multiplier", "free_credits", "last_rendered_at", "retries", "deck")
PARTS = ("speech", "script", "research", "photos", "stock", "deck")
DONE = ("COMPLETE", "FAILED", "CANCELLED", "REJECTED")
LAMBDA_GBS_PRICE, LAMBDA_REQ_PRICE = 0.0000166667, 0.0000002   # x86, per GB-second and per request (list price; the same figures as scripts/cost_report.py)
DAY_TTL_DAYS, FAIL_TTL_DAYS = 3 * 365, 90
NAMESPACE = "videomk/Admin"

# alert thresholds (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md section 5.2); each can be changed with a function variable, no code change
FAIL_MIN = int(os.environ.get("ALERT_FAIL_MIN", "3"))                # at least this many failures among the videos started in the last hour ...
FAIL_SHARE = float(os.environ.get("ALERT_FAIL_SHARE", "0.20"))       # ... and more than this share of that hour's finished videos
STUCK_MINUTES = int(os.environ.get("ALERT_STUCK_MINUTES", "30"))     # a run still going after this long
BUDGET_LEVELS = (80, 100)                                            # per cent of the day's free credits

CAUSES = (   # (pattern on the error name, plain words)
    (r"timeout|timedout", "timeout (a model or the network was too slow)"),
    (r"accessdenied|unauthorized|forbidden|notauthorized", "permission (the function was not allowed to do something)"),
    (r"throttl|toomanyrequests|ratelimit|limitexceeded", "throttled (too many requests at once)"),
    (r"costcap", "cost cap (the video passed its spending limit)"),
    (r"valueerror|keyerror|typeerror|indexerror|jsondecode|assertion|attributeerror", "bad plan or data (the script or a file was not as expected)"),
    (r"memory|runtime\.exit|sigkill|lambda\.|states\.taskfailed|states\.runtime", "function crashed"),
    (r"modelerror|validationexception|modelstream|servicequota|internalserver|serviceunavailable", "model error"),
)
STEPS = (("plan", "plan"), ("beat", "scenes"), ("timeline", "timeline"), ("chunk", "render"), ("render", "render"), ("audio", "audio"), ("finalize", "finalize"),
         ("intent", "plan"), ("asset", "scenes"), ("storyboard", "render"))


# ----------------------------------------------------------------------------- maths (pure: tests/test_admin_console.py)
def f(x: Any) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def percentile(values: List[float], p: float) -> Optional[float]:
    """Nearest rank. None for no values."""
    if not values:
        return None
    v = sorted(values)
    k = max(1, int(-(-p * len(v) // 100)))   # ceil(p/100 * n)
    return v[min(len(v), k) - 1]


def clean_code(code: Any) -> str:
    """The error NAME only: the leading run of letters, digits, dots and underscores, at most 60. If a record ever carried a message after the name, it is not copied."""
    m = re.match(r"[A-Za-z_][A-Za-z0-9_.]{0,59}", str(code or "").strip())   # the leading name; anything after it (a colon, a space, a message) is dropped
    return m.group(0).rstrip(".") if m else "UNKNOWN"


def cause_of(code: str) -> str:
    low = code.lower()
    if low in ("", "unknown"):
        return "unknown"
    for pattern, words in CAUSES:
        if re.search(pattern, low):
            return words
    return code


def step_of(state_name: Optional[str]) -> str:
    low = str(state_name or "").lower()
    for needle, words in STEPS:
        if needle in low:
            return words
    return re.sub(r"[^A-Za-z0-9_ ]", "", str(state_name or ""))[:30]


def is_test(r: Dict[str, Any]) -> bool:
    return str(r.get("plan") or "") == "test" or str(r.get("user_id") or "").startswith("qa-selft")


def summarize(records: List[Dict[str, Any]], *, exclude_test: bool) -> Dict[str, Any]:
    """The counts and costs of one day's video records. No account ids and no text in the result."""
    rows = [r for r in records if not (exclude_test and is_test(r))]
    by = lambda s: [r for r in rows if r.get("status") == s]   # noqa: E731
    complete, failed, cancelled, rejected = by("COMPLETE"), by("FAILED"), by("CANCELLED"), by("REJECTED")
    cost = lambda rs: round(sum(f(r.get("cost_usd")) for r in rs), 6)   # noqa: E731
    finished = len(complete) + len(failed)
    out = {
        "started": len(rows), "complete": len(complete), "failed": len(failed), "cancelled": len(cancelled), "rejected": len(rejected),
        "in_progress": len([r for r in rows if r.get("status") not in DONE]),
        "failure_rate": round(len(failed) / finished, 4) if finished else None,      # failed / (complete + failed); cancelled and rejected are beside it, not inside
        "cost_tracked": cost(rows), "cost_failed": cost(failed), "cost_cancelled": cost(cancelled), "cost_rejected": cost(rejected),
        "cost_parts": {p: round(sum(f(r.get(f"c_{p}")) for r in rows), 6) for p in PARTS},
        "credits_charged": int(sum(f(r.get("credits_charged")) for r in complete)),   # failed, cancelled and rejected videos are refunded
        "free_credits": int(sum(f(r.get("free_credits")) for r in complete)),
        "active_accounts": len({r.get("user_id") for r in rows if r.get("user_id")}),
        "excluded_test": len(records) - len(rows),
    }
    plans: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        p = plans.setdefault(str(r.get("plan") or "unknown"), {"started": 0, "complete": 0, "failed": 0, "cancelled": 0, "cost_tracked": 0.0})
        p["started"] += 1
        p["cost_tracked"] = round(p["cost_tracked"] + f(r.get("cost_usd")), 6)
        for status, key in (("COMPLETE", "complete"), ("FAILED", "failed"), ("CANCELLED", "cancelled")):
            if r.get("status") == status:
                p[key] += 1
    out["plans"] = plans
    return out


def money(summary: Dict[str, Any], compute_usd: Optional[float]) -> Dict[str, Any]:
    """All-in cost = tracked (models, speech, searches: on each record) + Lambda compute (known per day only, shared out evenly between the videos started).
    Lost = what failed and cancelled videos cost: their tracked cost plus their share of the compute. Estimates until the engine records compute per video."""
    comp = round(f(compute_usd), 6) if compute_usd is not None else None
    all_in = round(summary["cost_tracked"] + (comp or 0.0), 6)
    share = (summary["failed"] + summary["cancelled"]) / summary["started"] if summary["started"] else 0.0
    return {"compute_usd": comp, "cost_all_in": all_in, "cost_per_video": round(all_in / summary["complete"], 6) if summary["complete"] else None,
            "lost_usd": round(summary["cost_failed"] + summary["cost_cancelled"] + (comp or 0.0) * share, 6)}


def make_times(records: List[Dict[str, Any]], runs: Dict[str, float], *, exclude_test: bool) -> Dict[str, Any]:
    """Time to make a video: run end minus run start of COMPLETE videos' FIRST run (the run is named after the video; a retry or an edit has another name)."""
    secs = [runs[r["video_id"]] for r in records if r.get("status") == "COMPLETE" and r.get("video_id") in runs and not (exclude_test and is_test(r))]
    return {"make_p50_s": percentile(secs, 50), "make_p95_s": percentile(secs, 95), "make_n": len(secs)}


def failure_items(records: List[Dict[str, Any]], *, exclude_test: bool) -> List[Dict[str, Any]]:
    """One small record per failed or cancelled video: time, cause, cost, plan, length. No prompt, no title, no account id."""
    out = []
    for r in records:
        if r.get("status") not in ("FAILED", "CANCELLED") or (exclude_test and is_test(r)):
            continue
        code = clean_code(r.get("failure_code")) if r.get("status") == "FAILED" else ""
        out.append({"video_id": str(r.get("video_id") or ""), "at": str(r.get("created_at") or ""), "status": r["status"], "code": code,
                    "cause": cause_of(code) if r["status"] == "FAILED" else "cancelled by the person", "cost_usd": round(f(r.get("cost_usd")), 6),
                    "plan": str(r.get("plan") or "unknown"), "length_s": int(f(r.get("duration_s"))) or None, "credits": int(f(r.get("credits_charged"))),
                    "aspect": r.get("aspect"), "resolution": r.get("resolution"), "retries": int(f(r.get("retries")))})
    return out


def last_hour(records: List[Dict[str, Any]], now: float, *, exclude_test: bool) -> Dict[str, int]:
    """The videos STARTED in the last 60 minutes (a record keeps when it started, not when it ended; a video takes a few minutes)."""
    since = c.iso(now - 3600)
    rows = [r for r in records if str(r.get("created_at") or "") >= since and not (exclude_test and is_test(r))]
    return {"failed": len([r for r in rows if r.get("status") == "FAILED"]), "complete": len([r for r in rows if r.get("status") == "COMPLETE"])}


def evaluate_alerts(snap: Dict[str, Any], prev: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], Dict[str, Any]]:
    """(emails to send as (subject, text), the state to remember). Each alert is sent when it STARTS, not every hour while it lasts."""
    out: List[Tuple[str, str]] = []
    state = {"failing": False, "stuck": [], "budget_day": snap["today"], "budget_levels": []}
    h = snap.get("hour") or {"failed": 0, "complete": 0}
    finished = h["failed"] + h["complete"]
    failing = h["failed"] >= FAIL_MIN and finished > 0 and h["failed"] / finished > FAIL_SHARE
    state["failing"] = failing
    if failing and not prev.get("failing"):
        out.append(("videos are failing", "%d of the %d videos started in the last hour failed (%d %%).\n\nOpen the console to see the step and the cause. If it keeps going, "
                    "\"Stop all new videos\" stops the spending while you look (videos being made finish)." % (h["failed"], finished, round(100 * h["failed"] / finished))))
    stuck = sorted(x["name"] for x in (snap.get("stuck") or []))
    state["stuck"] = stuck
    fresh = [n for n in stuck if n not in (prev.get("stuck") or [])]
    if fresh:
        longest = max(x["minutes"] for x in snap["stuck"])
        out.append(("a video is stuck", "%d video run%s still going after %d minutes (the longest: %d minutes).\n\nRuns: %s\n\nA run is stopped by AWS after 45 minutes; the person gets "
                    "the credits back when it fails." % (len(stuck), " is" if len(stuck) == 1 else "s are", STUCK_MINUTES, longest, ", ".join(stuck[:10]))))
    b = snap.get("budget") or {}
    sent = list(prev.get("budget_levels") or []) if prev.get("budget_day") == snap["today"] else []
    if b.get("limit") and not b.get("unlimited"):
        pct = 100.0 * b["spent"] / b["limit"]
        for level in BUDGET_LEVELS:
            if pct >= level and level not in sent:
                sent.append(level)
                if level == max(l for l in BUDGET_LEVELS if pct >= l):   # one email for the highest level reached, not two at once
                    out.append(("free budget at %d %%" % level, "%d of today's %d free credits are used (about $%.2f of $%.2f).\n\n%s"
                                % (b["spent"], b["limit"], b["spent"] * b["usd_per_credit"], b["limit"] * b["usd_per_credit"],
                                   "Free videos are paused until 00:00 UTC. That is the budget doing its job; nothing to do." if level >= 100
                                   else "At 100 %% free videos pause until 00:00 UTC. To stop them now: \"Stop free videos\" in the console.")))
    state["budget_levels"] = sorted(sent)
    return out, state


# ----------------------------------------------------------------------------- reads
def read_day(day: str) -> Tuple[List[Dict[str, Any]], str]:
    """The video records of one UTC day: through the day index; while the index does not exist yet (the main stack is deployed separately), a scan of
    exactly the same small fields. -> (records, 'index' | 'scan')"""
    t = c.table("VIDEOS_TABLE")
    try:
        items, kw = [], {"IndexName": INDEX, "KeyConditionExpression": Key("usage_day").eq(day)}
        while True:
            res = t.query(**kw)
            items += res.get("Items", [])
            if not res.get("LastEvaluatedKey"):
                return items, "index"
            kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") not in ("ValidationException", "ResourceNotFoundException"):
            raise
        logger.warning("ROLLUP_INDEX_MISSING falling back to a scan of the small fields (deploy the main stack to add %s)", INDEX)
    names = {f"#a{i}": n for i, n in enumerate(FIELDS)}
    items, kw = [], {"FilterExpression": Attr("usage_day").eq(day), "ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names, "Select": "SPECIFIC_ATTRIBUTES"}
    while True:
        res = t.scan(**kw)
        items += res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            return items, "scan"
        kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def succeeded_runs(since: float) -> Dict[str, float]:
    """{run name: seconds} of the runs that ended well and started at or after `since` (names and times only: the list holds no request data)."""
    sfn, out, token = c.client("stepfunctions"), {}, None
    for _ in range(200):
        kw = {"stateMachineArn": os.environ["STATE_MACHINE_ARN"], "statusFilter": "SUCCEEDED", "maxResults": 1000, **({"nextToken": token} if token else {})}
        res = sfn.list_executions(**kw)
        old = False
        for x in res.get("executions", []):
            if x["startDate"].timestamp() < since:
                old = True
                continue
            if x.get("stopDate"):
                out[x["name"]] = round((x["stopDate"] - x["startDate"]).total_seconds(), 1)
        token = res.get("nextToken")
        if old or not token:
            break
    return out


def running_runs(now: float) -> List[Dict[str, Any]]:
    sfn, out, token = c.client("stepfunctions"), [], None
    for _ in range(20):
        res = sfn.list_executions(stateMachineArn=os.environ["STATE_MACHINE_ARN"], statusFilter="RUNNING", maxResults=1000, **({"nextToken": token} if token else {}))
        out += [{"name": x["name"], "minutes": int((now - x["startDate"].timestamp()) // 60)} for x in res.get("executions", [])]
        token = res.get("nextToken")
        if not token:
            break
    return out


def failed_step(video_id: str, retries: int) -> str:
    """Where a failed run broke: the last step it entered before the failure handling. Read WITHOUT the run's data (the request text stays unread)."""
    machine = os.environ["STATE_MACHINE_ARN"]
    arn = machine.replace(":stateMachine:", ":execution:") + ":" + (video_id if not retries else f"{video_id}-r{retries}")
    try:
        res = c.client("stepfunctions").get_execution_history(executionArn=arn, reverseOrder=True, includeExecutionData=False, maxResults=100)
    except ClientError:
        return ""
    for ev in res.get("events", []):
        name = (ev.get("stateEnteredEventDetails") or {}).get("name")
        if name and not re.search(r"failed|markfailed", name, re.I):
            return step_of(name)
    return ""


def compute_cost(day: str, now: float) -> float:
    """Lambda compute of the engine functions on that UTC day: seconds x memory x price + requests. Renders, edits and failed runs included."""
    fns = json.loads(os.environ.get("ENGINE_FUNCTIONS") or "{}")   # {function name: memory in MB}, fixed when the console is deployed
    if not fns:
        return 0.0
    start = datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    end = min(start + datetime.timedelta(days=1), datetime.datetime.fromtimestamp((int(now) // 60 + 1) * 60, datetime.timezone.utc))
    queries = []
    for i, name in enumerate(sorted(fns)):
        for metric, tag in (("Duration", "d"), ("Invocations", "n")):
            queries.append({"Id": f"{tag}{i}", "ReturnData": True, "MetricStat": {"Stat": "Sum", "Period": 86400,
                            "Metric": {"Namespace": "AWS/Lambda", "MetricName": metric, "Dimensions": [{"Name": "FunctionName", "Value": name}]}}})
    res = c.client("cloudwatch").get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=end)
    got = {r["Id"]: sum(r.get("Values") or []) for r in res.get("MetricDataResults", [])}
    usd = 0.0
    for i, name in enumerate(sorted(fns)):
        usd += got.get(f"d{i}", 0.0) / 1000.0 * float(fns[name]) / 1024.0 * LAMBDA_GBS_PRICE + got.get(f"n{i}", 0.0) * LAMBDA_REQ_PRICE
    return round(usd, 6)


def signups(days: List[str]) -> Dict[str, int]:
    """New confirmed accounts per UTC day, from the customer pool's user list. Only the creation date and the status are looked at (no attribute but the id is asked for)."""
    idp, out, token = c.client("cognito-idp"), {d: 0 for d in days}, None
    for _ in range(500):
        res = idp.list_users(UserPoolId=os.environ["CUSTOMER_POOL_ID"], AttributesToGet=["sub"], Limit=60, **({"PaginationToken": token} if token else {}))
        for u in res.get("Users", []):
            d = c.day_of(u["UserCreateDate"].timestamp())
            if d in out and u.get("UserStatus") in ("CONFIRMED", "EXTERNAL_PROVIDER") and u.get("Enabled", True):
                out[d] += 1
        token = res.get("PaginationToken")
        if not token:
            return out
    raise RuntimeError("too many accounts to list every hour: move sign-ups to a daily read (slice two)")


# ----------------------------------------------------------------------------- the run
def collect(now: float) -> Dict[str, Any]:
    exclude = os.environ.get("EXCLUDE_TEST_ACCOUNTS", "0") == "1"
    today, yesterday = c.day_of(now), c.day_of(now - 86400)
    snap: Dict[str, Any] = {"now": now, "today": today, "days": {}, "partial": [], "includes_test_accounts": not exclude}
    records: Dict[str, List[Dict[str, Any]]] = {}
    for day in (yesterday, today):
        records[day], source = read_day(day)   # the core: a failure here fails the run (alarm)
        snap["days"][day] = {**summarize(records[day], exclude_test=exclude), "source": source}

    def part(name: str, fn: Any) -> Any:   # the rest: a failure is recorded and the number is shown as "not available", never guessed
        try:
            return fn()
        except Exception:   # noqa: BLE001
            logger.exception("ROLLUP_PART_FAILED %s", name)
            snap["partial"].append(name)
            return None

    runs = part("make_time", lambda: succeeded_runs(datetime.datetime.strptime(yesterday, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp()))
    new_accounts = part("signups", lambda: signups([yesterday, today]))
    for day in (yesterday, today):
        d = snap["days"][day]
        d.update(make_times(records[day], runs, exclude_test=exclude) if runs is not None else {"make_p50_s": None, "make_p95_s": None, "make_n": 0})
        d.update(money(d, part("compute", lambda day=day: compute_cost(day, now))))
        d["signups"] = new_accounts[day] if new_accounts is not None else None
        d["failures"] = failure_items(records[day], exclude_test=exclude)
    running = part("running", lambda: running_runs(now))
    snap["running"] = len(running) if running is not None else None
    snap["stuck"] = [x for x in (running or []) if x["minutes"] >= STUCK_MINUTES]
    snap["hour"] = last_hour(records[yesterday] + records[today], now, exclude_test=exclude)

    def budget() -> Dict[str, Any]:
        k = c.budget_knobs()
        return {"spent": c.budget_spent(today), "limit": int(k["free_daily_budget_credits"]), "unlimited": bool(k["free_budget_unlimited"]), "usd_per_credit": float(k["cost_per_credit_usd"])}
    snap["budget"] = part("budget", budget)
    return snap


def write(snap: Dict[str, Any]) -> None:
    t, now = c.table("ROLLUP_TABLE"), snap["now"]
    for day, d in snap["days"].items():
        failures, plans = d.pop("failures"), d.pop("plans")
        known = {i["sk"]: i for i in _query(t, f"fail#{day}")}
        t.put_item(Item=c.dec({"pk": f"day#{day}", "sk": "all", "day": day, **d, "updated_at": c.iso(now), "partial": snap["partial"], "includes_test_accounts": snap["includes_test_accounts"],
                               "ttl": int(now) + DAY_TTL_DAYS * 86400}))
        for plan, p in plans.items():
            t.put_item(Item=c.dec({"pk": f"day#{day}", "sk": "plan#" + re.sub(r"[^a-z0-9_]", "", plan.lower())[:20], "day": day, **p, "updated_at": c.iso(now), "ttl": int(now) + DAY_TTL_DAYS * 86400}))
        for fl in failures:
            sk = f"{fl['at']}#{fl['video_id']}"
            old = known.get(sk) or {}
            if fl["status"] == "FAILED":   # the step is read once per failed run (one small call), then kept
                fl["step"] = old.get("step") if old.get("step") and old.get("status") == "FAILED" else failed_step(fl["video_id"], fl["retries"])
            t.put_item(Item=c.dec({"pk": f"fail#{day}", "sk": sk, **fl, "ttl": int(now) + FAIL_TTL_DAYS * 86400}))
        gone = set(known) - {f"{fl['at']}#{fl['video_id']}" for fl in failures}   # retried and now running or complete, or deleted with its account
        for sk in gone:
            t.delete_item(Key={"pk": f"fail#{day}", "sk": sk})
    t.put_item(Item=c.dec({"pk": "meta", "sk": "rollup", "updated_at": c.iso(now), "partial": snap["partial"], "hour": snap["hour"], "stuck": snap["stuck"], "running": snap["running"],
                           "source": snap["days"][snap["today"]]["source"], "includes_test_accounts": snap["includes_test_accounts"]}))


def _query(t: Any, pk: str) -> List[Dict[str, Any]]:
    items, kw = [], {"KeyConditionExpression": Key("pk").eq(pk)}
    while True:
        res = t.query(**kw)
        items += res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            return items
        kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def alert(snap: Dict[str, Any]) -> List[str]:
    t = c.table("ROLLUP_TABLE")
    prev = c.plain(t.get_item(Key={"pk": "meta", "sk": "alerts"}).get("Item") or {})
    emails, state = evaluate_alerts(snap, prev)
    for subject, text in emails:
        c.notify(subject, text + "\n\n(VideoMK console, %s, %s)" % (c.stage(), c.hhmm(snap["now"])))
    t.put_item(Item=c.dec({"pk": "meta", "sk": "alerts", **state, "updated_at": c.iso(snap["now"])}))   # after the emails: a failed send is tried again next hour
    return [s for s, _ in emails]


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    now = time.time()
    if isinstance(event, dict) and event.get("test_alert"):   # `aws lambda invoke ... --payload '{"test_alert": true}'`: one test email through the same path as every alert
        c.notify("test alert", "This is a test of the VideoMK console alerts, sent at %s. Nothing is wrong." % c.hhmm(now))
        return {"sent": "test alert"}
    snap = collect(now)
    write(snap)
    sent = alert(snap)
    # the heartbeat (CloudWatch embedded metric format: a log line becomes a metric, no extra permission); the alarm fires when two hours pass without one
    print(json.dumps({"_aws": {"Timestamp": int(now * 1000), "CloudWatchMetrics": [{"Namespace": NAMESPACE, "Dimensions": [["Stage"]], "Metrics": [{"Name": "RollupHeartbeat", "Unit": "Count"}]}]},
                      "Stage": c.stage(), "RollupHeartbeat": 1}))
    t = snap["days"][snap["today"]]
    logger.info("ROLLUP_DONE day=%s started=%s complete=%s failed=%s partial=%s alerts=%s", snap["today"], t["started"], t["complete"], t["failed"], snap["partial"], sent)
    return {"day": snap["today"], "started": t["started"], "complete": t["complete"], "failed": t["failed"], "partial": snap["partial"], "alerts": sent}
