"""The free allowance and what keeps it from being farmed (docs/PLANS.md, "Abuse controls"). Only used where plans are on (common/plans.enabled()).

One free allowance per PERSON signal, not per account. Before a free credit is GRANTED the account passes `evaluate()`:
  web             the request did not come from a mobile app (X-Platform ios|android) and the knob free_web is off
  identity        no verified email in the token
  disposable      the email domain is in the shipped public list (CC0, common/data/disposable_email_domains.txt) or in email_domain_deny (email_domain_allow takes one out)
  no_device       require_device_proof is on and the account has no fresh device proof (lambdas/device_api.py records one)
  signup_velocity too many accounts first seen from this IP address in the last hour
  ip / ip_block   too many allowances claimed today from this address, or from its /24 (IPv4) or /48 (IPv6)
  duplicate_*     the normalised email, the Google/Apple identity or the attested device already claimed an allowance (this one is final for the account)
and before a free credit is SPENT by a Free account `spend_gate()` checks the platform and the device proof again, then the launcher takes the credits out of the
global daily budget and the account's monthly cap. Paid plans and unlimited test accounts skip all of it.

What is stored about a claim (FREE_CLAIMS_TABLE): the key `e#|f#|d#` + HMAC-SHA256 of the normalised email / federated id / device key under the per-stage secret, the day,
an attempt counter and an expiry. No account id, no address, nothing else: it survives account deletion on purpose and cannot be turned back into a person.
Velocity counters live in the usage table for a few days, keyed by the HMAC of the address (the /24 block itself is kept on the block counter so the report can name it).
The client is never told which rule refused: it sees `free.reason = "not_available"`; the reason goes to the log (FREE_CLAIM ...) and to the metric FreeClaimRefused{Reason}.
"""
import ipaddress
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from common import plans

logger = logging.getLogger()
FREE_KINDS = ("daily", "signup")
PERMANENT = ("duplicate_email", "duplicate_identity", "duplicate_device")
NAMESPACE = "videomk/Plans"
_ddb = None
_disposable: Optional[frozenset] = None


def ddb():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def set_resource(resource: Any) -> None:   # tests
    global _ddb
    _ddb = resource


def claims_table():
    return ddb().Table(os.environ["FREE_CLAIMS_TABLE"])


def usage_table():
    return ddb().Table(os.environ["USAGE_TABLE"])


def emit(name: str, value: float = 1, unit: str = "Count", **dims: str) -> None:
    """One CloudWatch metric through the function's log (embedded metric format: no API call, no extra permission)."""
    print(json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [{"Namespace": NAMESPACE, "Dimensions": [sorted(dims)], "Metrics": [{"Name": name, "Unit": unit}]}]},
                      name: value, **dims}))


def mac(domain: str, value: str) -> str:
    from common import deletion
    return deletion.mac(f"free:{domain}", value)


# ----------------------------------------------------------------------------- who is asking
def context(event: Any) -> Dict[str, Any]:
    """What the eligibility rules may look at, taken from the verified token and the connection: never from the body."""
    rc = (event or {}).get("requestContext") or {}
    authz = rc.get("authorizer") or {}
    claims = authz.get("claims") if isinstance(authz.get("claims"), dict) else ((authz.get("jwt") or {}).get("claims") or {})
    headers = {str(k).lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
    platform = str(headers.get("x-platform") or "").strip().lower()
    username, sub = str(claims.get("cognito:username") or ""), str(claims.get("sub") or "")
    federated = None
    if username and username != sub and username.lower().startswith(("google_", "signinwithapple_")):
        federated = username.lower()
    else:
        try:
            ids = claims.get("identities")
            ids = json.loads(ids) if isinstance(ids, str) else ids
            for i in ([ids] if isinstance(ids, dict) else ids or []):
                if i.get("userId") and i.get("providerName"):
                    federated = f"{str(i['providerName']).lower()}_{i['userId']}"
        except (ValueError, TypeError, AttributeError):
            federated = None
    return {"platform": platform if platform in ("ios", "android") else "web", "ip": str((rc.get("identity") or {}).get("sourceIp") or ""),
            "email": str(claims.get("email") or ""), "email_verified": str(claims.get("email_verified", "")).lower() == "true", "federated": federated}


def normalise_email(email: str) -> str:
    """One mailbox, one spelling: lower case, no '+tag', and for Gmail no dots and googlemail.com = gmail.com (the same rule the deletion tombstone uses)."""
    from common import deletion
    return deletion.normalise_email(email)


def disposable_domains() -> frozenset:
    global _disposable
    if _disposable is None:
        path = os.path.join(os.path.dirname(__file__), "data", "disposable_email_domains.txt")
        with open(path, encoding="utf-8") as f:
            _disposable = frozenset(x.strip().lower() for x in f if x.strip() and not x.startswith("#"))
    return _disposable


def is_disposable(email: str, cfg: Dict[str, Any]) -> bool:
    domain = email.rsplit("@", 1)[-1].strip().lower()
    parts = domain.split(".")
    names = {".".join(parts[i:]) for i in range(len(parts) - 1)}   # the domain and its parents: sub.mailinator.com is mailinator.com
    if names & set(cfg["email_domain_allow"]):
        return False
    if names & set(cfg["email_domain_deny"]):
        return True
    return bool(cfg["block_disposable_email"]) and bool(names & disposable_domains())


def ip_block(ip: str) -> Optional[str]:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return str(ipaddress.ip_network(f"{addr}/{24 if addr.version == 4 else 48}", strict=False))


def claim_keys(ctx: Dict[str, Any], meta: Dict[str, Any]) -> List[Tuple[str, str]]:
    """[(claim key, the refusal reason if it is taken)]"""
    keys = []
    if ctx.get("email"):
        keys.append(("e#" + mac("email", normalise_email(ctx["email"])), "duplicate_email"))
    if ctx.get("federated"):
        keys.append(("f#" + mac("federated", ctx["federated"]), "duplicate_identity"))
    if meta.get("device_ref"):
        keys.append(("d#" + str(meta["device_ref"]), "duplicate_device"))
    return keys


# ----------------------------------------------------------------------------- counters (usage table)
def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


def _count(key: str, sort: str, now: float, *, limit: int = 0, n: int = 1, keep_days: int = 8, extra: Optional[Dict[str, Any]] = None) -> bool:
    """Add n to a counter; with a limit, only while the total stays within it (False: over the limit, nothing added). Atomic."""
    names, vals = {"#c": "count", "#t": "ttl"}, {":n": n, ":t": int(now) + keep_days * 86400}
    sets = ["#t = :t"]
    for i, (k, v) in enumerate((extra or {}).items()):
        names[f"#x{i}"], vals[f":x{i}"] = k, v
        sets.append(f"#x{i} = :x{i}")
    kwargs: Dict[str, Any] = {}
    if limit > 0:
        if n > limit:
            return False
        kwargs["ConditionExpression"] = "attribute_not_exists(#c) OR #c <= :room"
        vals[":room"] = limit - n
    try:
        usage_table().update_item(Key={"user_id": key, "day": sort}, UpdateExpression="ADD #c :n SET " + ", ".join(sets), ExpressionAttributeNames=names, ExpressionAttributeValues=vals, **kwargs)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _read(key: str, sort: str) -> int:
    return int((usage_table().get_item(Key={"user_id": key, "day": sort}).get("Item") or {}).get("count") or 0)


def stat(field: str, now: float, n: int = 1) -> None:
    """The day's totals for the admin report (usage table, item `fstat` / day): granted, refused_<reason>, budget_refused, cap_refused."""
    try:
        usage_table().update_item(Key={"user_id": "fstat", "day": _day(now)}, UpdateExpression="ADD #f :n SET #t = :t", ExpressionAttributeNames={"#f": field, "#t": "ttl"},
                                  ExpressionAttributeValues={":n": n, ":t": int(now) + 400 * 86400})
    except Exception:   # noqa: BLE001 - a statistic never stops a request
        logger.exception("FREE_STAT_FAILED")


def note_first_seen(ctx: Optional[Dict[str, Any]], now: float) -> None:
    """Called once when an account's wallet is created: the sign-up velocity counter of its address."""
    if ctx and ctx.get("ip"):
        try:
            _count("fsu:" + mac("ip", ctx["ip"]), time.strftime("%Y-%m-%dT%H", time.gmtime(now)), now, keep_days=2)
        except Exception:   # noqa: BLE001
            logger.exception("FREE_FIRST_SEEN_FAILED")


# ----------------------------------------------------------------------------- the global daily budget and the per-account monthly cap
def budget_state(cfg: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    limit = int(cfg["free_daily_budget_credits"])
    resumes = (int(now // 86400) + 1) * 86400
    out = {"limit_credits": limit, "limit_usd": plans.usd(limit, cfg), "resumes_at": datetime.fromtimestamp(resumes, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if cfg["free_budget_unlimited"]:
        return {**out, "limit_credits": None, "limit_usd": None, "spent_credits": _read("fbudget", _day(now)), "paused": False}
    spent = _read("fbudget", _day(now)) if limit > 0 else 0
    return {**out, "spent_credits": spent, "paused": spent >= limit}


def budget_take(n: int, cfg: Dict[str, Any], now: Optional[float] = None) -> bool:
    """Take n free credits out of today's budget for ALL accounts (UTC day). False: the budget cannot cover them, nothing is taken."""
    now = time.time() if now is None else now
    if n <= 0:
        return True
    if cfg["free_budget_unlimited"]:
        return _count("fbudget", _day(now), now, n=n, keep_days=400)
    limit = int(cfg["free_daily_budget_credits"])
    return limit > 0 and _count("fbudget", _day(now), now, limit=limit, n=n, keep_days=400)


def budget_return(n: int, now: Optional[float] = None) -> None:
    """A video that never started gives its share back (best effort, never below zero)."""
    now = time.time() if now is None else now
    if n <= 0:
        return
    try:
        usage_table().update_item(Key={"user_id": "fbudget", "day": _day(now)}, UpdateExpression="ADD #c :neg", ConditionExpression="#c >= :n", ExpressionAttributeNames={"#c": "count"},
                                  ExpressionAttributeValues={":neg": -n, ":n": n})
    except ClientError:
        pass


def _month(now: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(now))


def monthly_take(user: str, cfg: Dict[str, Any], now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return _count(f"freemonth:{user}", _month(now), now, limit=int(cfg["free_monthly_videos_cap"]), keep_days=70)


def monthly_return(user: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    try:
        usage_table().update_item(Key={"user_id": f"freemonth:{user}", "day": _month(now)}, UpdateExpression="ADD #c :neg", ConditionExpression="#c >= :one", ExpressionAttributeNames={"#c": "count"},
                                  ExpressionAttributeValues={":neg": -1, ":one": 1})
    except ClientError:
        pass


def monthly_used(user: str, now: Optional[float] = None) -> int:
    return _read(f"freemonth:{user}", _month(time.time() if now is None else now))


def free_credits_in(takes: List[Dict[str, Any]]) -> int:
    """How many of the credits a charge took came from free buckets (bucket keys are B#<expiry>#<kind>#<id>)."""
    return sum(int(x["n"]) for x in takes if str(x.get("sk", "")).split("#")[2:3] and str(x["sk"]).split("#")[2] in FREE_KINDS)


# ----------------------------------------------------------------------------- eligibility
def device_ok(meta: Dict[str, Any], cfg: Dict[str, Any], now: float) -> bool:
    return (not cfg["require_device_proof"]) or int(meta.get("device_pass_until") or 0) > now


def spend_gate(ctx: Optional[Dict[str, Any]], meta: Dict[str, Any], cfg: Dict[str, Any], now: float) -> Optional[str]:
    """May this Free account SPEND free credits on this request? None, or the reason it may not (web, no_device, denied)."""
    if ctx is None:
        return "no_context"
    if ctx["platform"] == "web" and not cfg["free_web"]:
        return "web"
    if str(meta.get("welcome_state") or "").startswith("denied"):
        return "denied"
    if not device_ok(meta, cfg, now):
        return "no_device"
    return None


def evaluate(ctx: Optional[Dict[str, Any]], meta: Dict[str, Any], cfg: Dict[str, Any], now: float) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """(None, claim keys) when this account may be granted its free allowance now; else (reason, []). Reads only; the velocity counters are taken in `claim()`."""
    if ctx is None:
        return "no_context", []
    if ctx["platform"] == "web" and not cfg["free_web"]:
        return "web", []
    if not ctx.get("email") or not ctx.get("email_verified"):
        if not ctx.get("federated"):
            return "identity", []
    if ctx.get("email") and is_disposable(ctx["email"], cfg):
        return "disposable", []
    if not device_ok(meta, cfg, now):
        return "no_device", []
    if meta.get("device_claimed"):   # Apple's DeviceCheck bit or Google's device recall says this DEVICE already had an allowance
        return "duplicate_device", []
    try:
        keys = claim_keys(ctx, meta)
        for key, reason in keys:
            item = claims_table().get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
            if item and int(item.get("ttl") or 0) > now:
                try:   # how many accounts tried to use this identity (the report's "accounts per identity")
                    claims_table().update_item(Key={"pk": key}, UpdateExpression="ADD #n :one", ConditionExpression="attribute_exists(pk)", ExpressionAttributeNames={"#n": "n"}, ExpressionAttributeValues={":one": 1})
                except ClientError:
                    pass
                return reason, []
    except Exception:   # noqa: BLE001 - no key, no table: no free allowance (fail closed), the account still works
        logger.exception("FREE_CLAIM_CHECK_FAILED")
        return "internal", []
    ip = ctx.get("ip") or ""
    if ip and int(cfg["signups_per_ip_hour"]) > 0 and _read("fsu:" + mac("ip", ip), time.strftime("%Y-%m-%dT%H", time.gmtime(now))) > int(cfg["signups_per_ip_hour"]):
        return "signup_velocity", []
    return None, keys


def take_velocity(ctx: Dict[str, Any], cfg: Dict[str, Any], now: float) -> Optional[str]:
    ip = ctx.get("ip") or ""
    block = ip_block(ip) if ip else None
    if not ip or not block:
        return None
    if not _count("fip:" + mac("ip", ip), _day(now), now, limit=int(cfg["claims_per_ip_day"])):
        return "ip"
    if not _count("fblk:" + mac("block", block), _day(now), now, limit=int(cfg["claims_per_ip_block_day"]), extra={"block": block}):
        return "ip_block"
    return None


def _refused(user: str, meta: Dict[str, Any], reason: str, now: float, table: Any) -> None:
    """Record a refusal once per (account, reason): the log line, the metric and the day's statistic; a final one closes the account's allowance."""
    if meta.get("free_refusal") == reason:
        return
    final = reason in PERMANENT
    logger.warning("FREE_CLAIM result=refused reason=%s final=%s user=%s", reason, final, user)
    emit("FreeClaimRefused", Reason=reason)
    stat(f"refused_{reason}", now)
    try:
        table.update_item(Key={"user_id": user, "sk": "META"}, UpdateExpression="SET free_refusal = :r" + (", welcome_state = :d" if final else ""),
                          ConditionExpression="attribute_exists(user_id) AND (attribute_not_exists(welcome_state) OR welcome_state = :p)",
                          ExpressionAttributeValues={":r": reason, ":p": "pending", **({":d": "denied"} if final else {})})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
    meta["free_refusal"] = reason
    if final:
        meta["welcome_state"] = "denied"


def ensure(user: str, meta: Dict[str, Any], *, ctx: Optional[Dict[str, Any]], plan: str, unlimited: bool, now: float, tz: Optional[str], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The free grants of one account, where plans are on: the one-time welcome allowance (after the eligibility step) and, if the knob is on, the recurring free credit.
    `meta` is the wallet's META row; the (possibly updated) row is returned. A row without `welcome_state` is an account from before plans: its welcome credits were granted then."""
    from common import wallet
    cfg = plans.config() if cfg is None else cfg
    t, tn = wallet._table(), wallet._table().name
    if meta.get("welcome_state") == "pending" and int(cfg["welcome_credits"]) > 0 and (unlimited or ctx is not None):   # no request (an admin read, a refund): nothing is tried, nothing is recorded
        expires = int(now + int(cfg["welcome_valid_days"]) * 86400)
        grant = [{"Update": {"TableName": tn, "Key": {"user_id": user, "sk": "META"}, "UpdateExpression": "SET welcome_state = :g, welcome_at = :now REMOVE free_refusal",
                             "ConditionExpression": "welcome_state = :p", "ExpressionAttributeValues": {":g": "granted", ":p": "pending", ":now": int(now)}}},
                 {"Put": {"TableName": tn, "Item": wallet._bucket(user, "signup", int(cfg["welcome_credits"]), expires, now)}}]
        if unlimited:   # staff and test accounts: no eligibility step, no claim
            reason, keys = None, []
        else:
            reason, keys = evaluate(ctx, meta, cfg, now)
            if reason is None:
                reason = take_velocity(ctx or {}, cfg, now)
        if reason is not None:
            _refused(user, meta, reason, now, t)
        else:
            ttl = int(now + int(cfg["claim_retention_days"]) * 86400)
            puts = [{"Put": {"TableName": os.environ["FREE_CLAIMS_TABLE"], "Item": {"pk": k, "kind": k[0], "day": _day(now), "n": 1, "ttl": ttl},
                             "ConditionExpression": "attribute_not_exists(pk) OR #t < :now", "ExpressionAttributeNames": {"#t": "ttl"}, "ExpressionAttributeValues": {":now": int(now)}}} for k, _ in keys]
            try:
                wallet._tx(grant + puts)
                meta = {**meta, "welcome_state": "granted", "welcome_at": int(now)}
                meta.pop("free_refusal", None)
                if not unlimited:
                    logger.info("FREE_CLAIM result=granted user=%s credits=%s", user, cfg["welcome_credits"])
                    emit("FreeClaimGranted")
                    stat("granted", now)
            except ClientError as e:
                if not wallet._cancelled(e):
                    raise   # lost a race (a second request, or the same identity claiming at this instant): the next read settles it
    if int(cfg["free_daily_credits"]) > 0 and plan == "free" and meta.get("welcome_state", "granted") == "granted" and (unlimited or spend_gate(ctx, meta, cfg, now) is None):
        meta = _daily(user, meta, cfg, now, tz, t, tn)
    return meta


def _week(day: str) -> str:
    y, w, _ = datetime.strptime(day, "%Y-%m-%d").isocalendar()
    return f"{y}-W{w:02d}"


def _daily(user: str, meta: Dict[str, Any], cfg: Dict[str, Any], now: float, tz: Optional[str], t: Any, tn: str) -> Dict[str, Any]:
    from common import wallet
    day, midnight = wallet.local_day(now, tz)
    utc_day = int(now // 86400)
    if meta.get("last_daily_key") == day or utc_day <= int(meta.get("last_daily_utc_day", -1)):
        return meta
    week = _week(day)
    claimed = int(meta.get("week_claims") or 0) if meta.get("week_key") == week else 0
    if cfg["free_credit_cadence"] == "weekly" and claimed >= int(cfg["free_credits_per_week"]):
        return meta
    try:
        wallet._tx([
            {"Update": {"TableName": tn, "Key": {"user_id": user, "sk": "META"}, "UpdateExpression": "SET last_daily_key = :d, last_daily_utc_day = :u, week_key = :w, week_claims = :c",
                        "ConditionExpression": "attribute_not_exists(last_daily_key) OR (last_daily_key <> :d AND last_daily_utc_day < :u)",
                        "ExpressionAttributeValues": {":d": day, ":u": utc_day, ":w": week, ":c": claimed + 1}}},
            {"Put": {"TableName": tn, "Item": wallet._bucket(user, "daily", int(cfg["free_daily_credits"]), int(midnight), now, name=day)}},
        ])
        return {**meta, "last_daily_key": day, "last_daily_utc_day": utc_day, "week_key": week, "week_claims": claimed + 1}
    except ClientError as e:
        if not wallet._cancelled(e):
            raise
        return meta


def next_credit(meta: Dict[str, Any], cfg: Dict[str, Any], now: float, tz: Optional[str]) -> Dict[str, Any]:
    """When the next recurring free credit can be claimed (the wallet's next_free_credit_at), by the same rules `_daily` applies."""
    from common import wallet
    if int(cfg["free_daily_credits"]) <= 0:
        return {"next_daily_at": None, "next_free_credit_at": None, "next_free_credits": 0}
    day, midnight = wallet.local_day(now, tz)
    at = max(midnight, (int(meta.get("last_daily_utc_day", 0)) + 1) * 86400.0)
    if meta.get("last_daily_key") != day and int(now // 86400) > int(meta.get("last_daily_utc_day", -1)):
        at = now   # claimable now (it was not, for a reason `free` explains)
    if cfg["free_credit_cadence"] == "weekly" and meta.get("week_key") == _week(day) and int(meta.get("week_claims") or 0) >= int(cfg["free_credits_per_week"]):
        d = datetime.strptime(day, "%Y-%m-%d")
        at = max(at, midnight + (7 - d.isoweekday()) * 86400.0)   # the first midnight of next week (Monday), in the person's own day
    return {"next_daily_at": int(at), "next_free_credit_at": wallet._iso(at), "next_free_credits": int(cfg["free_daily_credits"])}


def summary(user: str, *, plan: str, unlimited: bool, meta: Dict[str, Any], buckets: List[Dict[str, Any]], ctx: Optional[Dict[str, Any]], cfg: Dict[str, Any], now: float) -> Dict[str, Any]:
    """The `free` block of the wallet and of capabilities: can THIS account make a free video now, and if not, what the app should show. The reason is one of the public ones only:
    off (no free creation is offered: gallery and paywall), app_only (free videos are made in the mobile apps), not_available (not for this account), paused (today's free
    videos are used up for everyone), used (this account has no free credit left), monthly_cap. `mode` says what the Free plan offers at all: none | welcome | daily.
    `pending: true` = the welcome allowance has not been tried yet for this account (a read-only call such as capabilities came first): the wallet read settles it."""
    mode = "daily" if int(cfg["free_daily_credits"]) > 0 else ("welcome" if int(cfg["welcome_credits"]) > 0 else "none")
    left = sum(int(b["remaining"]) for b in buckets if b["kind"] in FREE_KINDS)
    budget = budget_state(cfg, now)
    out = {"mode": mode, "credits_left": left, "max_seconds": int(cfg["free_max_seconds"]), "budget_paused": bool(budget["paused"]), "resumes_at": budget["resumes_at"] if budget["paused"] else None,
           "available": True, "reason": None, "pending": False}
    if plan != "free" or unlimited:
        return out
    gate = spend_gate(ctx, meta, cfg, now) if ctx is not None else None
    pending = meta.get("welcome_state") == "pending"
    cap = int(cfg["free_monthly_videos_cap"])
    untried = pending and left == 0 and int(cfg["welcome_credits"]) > 0 and gate is None and not meta.get("free_refusal")
    if untried and not budget["paused"]:
        return {**out, "pending": True}
    if mode == "none" and left == 0:
        reason = "off"
    elif gate == "web":
        reason = "app_only"
    elif gate is not None or (pending and mode != "none" and left == 0 and meta.get("free_refusal") not in (None, "web")):
        reason = "not_available"
    elif pending and left == 0 and meta.get("free_refusal") == "web":
        reason = "app_only"
    elif left == 0:
        reason = "used"
    elif budget["paused"]:
        reason = "paused"
    elif cap > 0 and monthly_used(user, now) >= cap:
        reason = "monthly_cap"
    else:
        reason = None
    return {**out, "available": reason is None, "reason": reason}
