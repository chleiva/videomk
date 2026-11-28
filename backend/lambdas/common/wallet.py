"""Credits wallet. 1 credit = 1 started minute of video (a 10-second video costs 1, 61 seconds costs 2); a 4K video costs double (docs/FOUR_K.md).

Credits live in *buckets* so each kind can expire on its own and the soonest-expiring is spent first:
  daily   1 free credit a day, expire at the end of the user's local day (no hoarding)
  signup  5 welcome credits, expire after 30 days
  paid    bought through the stores, never expire (one bucket per user, increased per purchase)
  refund  a make-good when a refund finds its original bucket already expired (valid 24 h)
  plan    the monthly credits of a paid plan (docs/PLANS.md): granted once per monthly date, Pro's end at the next date, Max's live one month longer (balance capped at 240)
The amounts are server config (env), so they change without an app update. Where plans are on (common/plans.enabled()) the free amounts come from the owner's knobs
(common/plans.config()) and a free credit is granted only after the eligibility step (common/free_grants.py); off, everything below behaves as it always did.

Table (WALLET_TABLE): HASH user_id, RANGE sk.  META item `sk="META"`; bucket items `sk="B#<expiry>#<kind>#<id>"` so a query returns
them in spending order; `REF#<id>` items make purchase grants idempotent.
"""
import json
import math
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import entitlements, free_grants, plans

NEVER = 9_999_999_999
MAX_MINUTES = 12
UNLIMITED_DISPLAY = 999  # what an unlimited account's balance reads as, so older app builds still let it send


class InsufficientCredits(Exception):
    def __init__(self, balance: int, needed: int):
        super().__init__(f"{needed} credits needed, {balance} available")
        self.balance, self.needed = balance, needed


class FreeNotAvailable(InsufficientCredits):
    """The account has enough credits only by counting free ones, and free credits may not be spent on this request (`reason`: web, no_device, denied, no_context)."""

    def __init__(self, balance: int, needed: int, reason: str):
        super().__init__(balance, needed)
        self.reason = reason


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def rules() -> Dict[str, int]:
    if plans.enabled():   # the owner's knobs decide (docs/PLANS.md)
        cfg = plans.config()
        return {"credit_unit_seconds": 60, "max_minutes": MAX_MINUTES, "signup": int(cfg["welcome_credits"]), "daily": int(cfg["free_daily_credits"]),
                "signup_valid_days": int(cfg["welcome_valid_days"])}
    return {"credit_unit_seconds": 60, "max_minutes": MAX_MINUTES, "signup": _int("WALLET_SIGNUP_CREDITS", 5), "daily": _int("WALLET_DAILY_CREDITS", 1),
            "signup_valid_days": _int("WALLET_SIGNUP_VALID_DAYS", 30)}


def credits_for_minutes(minutes: float, resolution: Optional[str] = None) -> int:
    """THE price of a video, the one place it is worked out. Started minutes, at least 1: 0.2 -> 1, 1 -> 1, 1.01 -> 2, 12 -> 12; times the resolution's
    multiplier (`engine.format_options.RESOLUTIONS`: 1 for 720p and 1080p, 2 for 4K), so 3 minutes at 2160p -> 6. No or unknown resolution: times 1."""
    from engine.format_options import credits_multiplier   # the options table (plain data, no dependencies) is the only input

    return max(1, min(MAX_MINUTES, math.ceil(round(float(minutes), 6)))) * credits_multiplier(resolution)


def _table():
    return boto3.resource("dynamodb").Table(os.environ["WALLET_TABLE"])


def _tx(items: List[Dict[str, Any]]) -> None:
    _table().meta.client.transact_write_items(TransactItems=items)


def _cancelled(e: ClientError) -> bool:
    return e.response.get("Error", {}).get("Code") in ("TransactionCanceledException", "ConditionalCheckFailedException")


def local_day(now: float, tz: Optional[str]) -> Tuple[str, float]:
    """(YYYY-MM-DD in the user's timezone, epoch of the next local midnight). Unknown timezone names fall back to UTC."""
    zone: Any = timezone.utc
    if tz:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = timezone.utc
    dt = datetime.fromtimestamp(now, zone)
    return dt.strftime("%Y-%m-%d"), (dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _bucket(user_id: str, kind: str, amount: int, expires: int, now: float, name: Optional[str] = None) -> Dict[str, Any]:
    return {"user_id": user_id, "sk": f"B#{expires:010d}#{kind}#{name or uuid.uuid4().hex[:12]}", "kind": kind, "remaining": amount, "granted": amount,
            "expires_at": expires, "created_at": int(now), **({"ttl": expires + 7 * 86400} if expires < NEVER else {})}


def _signup_block(user_id: str, now: float) -> Optional[str]:
    if not os.environ.get("DELETION_TABLE"):
        return None
    from common import deletion

    return deletion.signup_block(user_id, now=now)


def _ensure_grants_plans(user_id: str, *, now: float, tz: Optional[str], ctx: Optional[Dict[str, Any]], ent: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Where plans are on: the wallet row (created without any credit), the plan's monthly credits, then the free grants behind their eligibility step.
    Returns (the META row, the effective entitlement); ({}, ent) for an account that is being deleted."""
    t = _table()
    unlimited = is_unlimited(user_id)
    ent = entitlements.effective(user_id, now=now, unlimited=unlimited) if ent is None else ent
    meta = t.get_item(Key={"user_id": user_id, "sk": "META"}, ConsistentRead=True).get("Item")
    if meta is None:
        block = _signup_block(user_id, now)
        if block == "deleting":
            return {}, ent
        day, _ = local_day(now, tz)
        meta = {"user_id": user_id, "sk": "META", "signup_at": int(now), "last_daily_key": day, "last_daily_utc_day": int(now // 86400),
                "welcome_state": "denied" if block else "pending", **({"signup_denied": block} if block else {})}
        try:
            t.put_item(Item=meta, ConditionExpression="attribute_not_exists(user_id)")
            if not unlimited:
                free_grants.note_first_seen(ctx, now)
        except ClientError as e:
            if not _cancelled(e):
                raise
            meta = t.get_item(Key={"user_id": user_id, "sk": "META"}, ConsistentRead=True).get("Item") or meta
    ensure_plan_grants(user_id, ent, now=now)
    meta = free_grants.ensure(user_id, meta, ctx=ctx, plan=ent["plan"], unlimited=unlimited, now=now, tz=tz)
    return meta, ent


def ensure_plan_grants(user_id: str, ent: Dict[str, Any], *, now: Optional[float] = None) -> int:
    """The monthly credits of a paid plan, once per monthly date counted from the subscription's anchor (so a yearly plan gets twelve grants, and a wallet that was not
    opened for a while catches up on what is still valid). Pro: 30 that end at the next date. Max: 120 that live one date longer; the plan balance never exceeds the plan's
    cap (240). A grant is keyed by plan, anchor and month (PLAN#...), so it happens once whatever the concurrency. No active paid plan: any plan credit left is removed
    (a plan that ended, was refunded or was downgraded to Free takes its credits with it). Returns the credits granted now."""
    now = time.time() if now is None else now
    if not ent.get("grants_credits"):
        if ent.get("record_plan"):   # there was a plan: its credits end with it
            revoke_plan_credits(user_id, now=now)
        return 0
    p, anchor, tn = plans.PLANS[ent["plan"]], int(ent["anchor"] or ent["period_start"] or now), _table().name
    if now < anchor:
        return 0
    weekly = bool(plans.config()["plan_weekly_release"])
    k_now = 0
    while entitlements.add_months(anchor, k_now + 1) <= now:
        k_now += 1
    base = f"PLAN#{p['id']}#{anchor}#"
    done = {x["sk"] for x in _table().query(KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with(base), ConsistentRead=True)["Items"]}
    granted = 0
    for k in range(max(0, k_now - int(p["rollover_months"])), k_now + 1):
        start, expires = entitlements.add_months(anchor, k), entitlements.add_months(anchor, k + 1 + int(p["rollover_months"]))
        if expires <= now or (ent.get("period_end") is not None and start >= int(ent["period_end"])):   # nothing to give: already over, or a month that was not paid for
            continue
        month_ref = f"{base}{k:04d}"
        if month_ref in done:   # the whole month was released at once (weekly release off, or before it existed)
            continue
        amounts = tranches(int(p["credits_per_month"]))
        todo = [j for j in range(TRANCHES) if f"{month_ref}#w{j}" not in done]
        if weekly:   # only the weeks that have begun (and that were paid for): a wallet first read mid-cycle gets the elapsed weeks at once, the rest follow weekly
            todo = [j for j in todo if tranche_start(anchor, k, j) <= now and not (ent.get("period_end") is not None and tranche_start(anchor, k, j) >= int(ent["period_end"]))]
            groups = [([j], f"{month_ref}#w{j}") for j in todo]
        else:       # switched back to the monthly bundle: what is left of this month, in one grant, and the month is marked done
            groups = [(todo, month_ref)] if todo else []
        for js, ref_sk in groups:
            have = sum(int(b["remaining"]) for b in _live_buckets(user_id, now) if b["kind"] == "plan")
            total = sum(amounts[j] for j in js)
            amount = max(0, min(total, int(p["credits_cap"]) - have))
            items: List[Dict[str, Any]] = [{"Put": {"TableName": tn, "Item": {"user_id": user_id, "sk": ref_sk, "credits": amount, "at": int(now)}, "ConditionExpression": "attribute_not_exists(user_id)"}}]
            if amount > 0:
                items.append({"Put": {"TableName": tn, "Item": {**_bucket(user_id, "plan", amount, expires, now, name=f"{p['id']}-{anchor}-{k:04d}-w{js[0]}"), "plan": p["id"]}}})
            try:
                _tx(items)
                granted += amount
            except ClientError as e:
                if not _cancelled(e):
                    raise
    return granted


TRANCHES = 4
WEEK_SECONDS = 7 * 86400


def tranches(total: int) -> List[int]:
    """A monthly bundle released in four weekly parts: floor(total / 4) in weeks 1 to 3 and the REST in week 4, so the parts always add up to the bundle (Pro 30 = 7 + 7 + 7 + 9, Max 120 = 4 x 30)."""
    q = total // TRANCHES
    return [q] * (TRANCHES - 1) + [total - q * (TRANCHES - 1)]


def tranche_start(anchor: int, k: int, j: int) -> int:
    """When part j (0 to 3) of cycle k is released: the cycle's start plus j x 7 days (UTC seconds, no daylight-saving shift). Part 3 starts on day 21, inside every month."""
    return entitlements.add_months(anchor, k) + j * WEEK_SECONDS


def next_plan_release(ent: Dict[str, Any], *, now: float) -> Dict[str, Any]:
    """What the apps show for a paid plan: when the next part of the bundle arrives and how many credits it holds ({} when there is nothing coming: a plan that ends, or release off)."""
    if not ent.get("grants_credits") or not plans.config()["plan_weekly_release"]:
        return {}
    p, anchor = plans.PLANS[ent["plan"]], int(ent["anchor"] or ent["period_start"] or now)
    amounts, k = tranches(int(p["credits_per_month"])), 0
    while entitlements.add_months(anchor, k + 1) <= now:
        k += 1
    for kk in (k, k + 1):
        for j in range(TRANCHES):
            at = tranche_start(anchor, kk, j)
            if at > now:
                if ent.get("period_end") is not None and at >= int(ent["period_end"]):
                    return {}
                return {"next_renewal_at": _iso(at), "renews_on": _iso(at)[:10], "next_release_credits": amounts[j], "release": "weekly"}
    return {}


def revoke_plan_credits(user_id: str, *, now: Optional[float] = None) -> int:
    """Remove the unused plan credits (a refund, or a plan that ended). Only what is still there is taken: a balance never goes below zero. Returns how many were removed."""
    now = time.time() if now is None else now
    removed = 0
    for b in _live_buckets(user_id, now):
        if b["kind"] != "plan":
            continue
        try:
            res = _table().update_item(Key={"user_id": user_id, "sk": b["sk"]}, UpdateExpression="SET remaining = :z, revoked = :n", ConditionExpression="remaining > :z",
                                       ExpressionAttributeValues={":z": 0, ":n": int(b["remaining"])}, ReturnValues="UPDATED_OLD")
            removed += int((res.get("Attributes") or {}).get("remaining") or 0)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    return removed


def ensure_grants(user_id: str, *, now: Optional[float] = None, tz: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None) -> None:
    """Welcome credits the first time we see a user; then the day's free credits once per local day. Race-safe (conditional writes).
    Where plans are on, see _ensure_grants_plans (`ctx` = free_grants.context(event): without it no free credit is granted)."""
    now = time.time() if now is None else now
    if plans.enabled():
        _ensure_grants_plans(user_id, now=now, tz=tz, ctx=ctx, ent=None)
        return
    r, t = rules(), _table()
    day, midnight = local_day(now, tz)
    meta = t.get_item(Key={"user_id": user_id, "sk": "META"}, ConsistentRead=True).get("Item")
    tn = t.name
    if meta is None:  # first sight: welcome credits now; the daily credits start with the next local day
        block = _signup_block(user_id, now)
        if block == "deleting":
            return  # this account is being deleted (docs/ACCOUNT_DELETION.md): no row, no grant
        meta_item = {"user_id": user_id, "sk": "META", "signup_at": int(now), "last_daily_key": day, "last_daily_utc_day": int(now // 86400), **({"signup_denied": block} if block else {})}
        items: List[Dict[str, Any]] = [{"Put": {"TableName": tn, "Item": meta_item, "ConditionExpression": "attribute_not_exists(user_id)"}}]
        if r["signup"] > 0 and not block:   # 'returning': the verified email or federated name of an account deleted recently (owner's switch, docs/ACCOUNT_DELETION.md): no second welcome credit
            items.append({"Put": {"TableName": tn, "Item": _bucket(user_id, "signup", r["signup"], int(now + r["signup_valid_days"] * 86400), now)}})
        try:
            _tx(items)
        except ClientError as e:
            if not _cancelled(e):
                raise
        return
    utc_day = int(now // 86400)
    # Claimable when the user's LOCAL day and the UTC day have both moved on: at most one claim per UTC day, so sending different
    # timezones cannot earn extra days, while an honest user still gets a fresh 2 each local day.
    if r["daily"] > 0 and meta.get("last_daily_key") != day and utc_day > int(meta.get("last_daily_utc_day", -1)):
        try:
            _tx([
                {"Update": {"TableName": tn, "Key": {"user_id": user_id, "sk": "META"}, "UpdateExpression": "SET last_daily_key = :d, last_daily_utc_day = :u",
                            "ConditionExpression": "attribute_not_exists(last_daily_key) OR (last_daily_key <> :d AND last_daily_utc_day < :u)",
                            "ExpressionAttributeValues": {":d": day, ":u": utc_day}}},
                {"Put": {"TableName": tn, "Item": _bucket(user_id, "daily", r["daily"], int(midnight), now, name=day)}},
            ])
        except ClientError as e:
            if not _cancelled(e):
                raise


def _flags():
    return boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"])


def unlimited_allowed() -> bool:
    """Off by default and set to 1 by the stack only for non-production stages: in production the flag is ignored even if someone writes it."""
    return os.environ.get("ALLOW_UNLIMITED_ACCOUNTS") == "1"


def is_unlimited(user_id: str) -> bool:
    """Test and staff accounts. The flag lives in its own table (FLAGS_TABLE) that the runtime Lambdas can only READ: it is written only
    with AWS admin credentials (`scripts/wallet_admin.py`), never through the API and never by a function that handles user input.
    Keyed by the immutable Cognito `sub`, never by email (users can change their email)."""
    if not unlimited_allowed() or not user_id or not os.environ.get("FLAGS_TABLE"):
        return False
    item = _flags().get_item(Key={"user_id": user_id}).get("Item") or {}
    return item.get("unlimited") is True


def set_unlimited(user_id: str, on: bool = True) -> None:
    """Admin only (needs write access to FLAGS_TABLE, which no Lambda role has)."""
    if on:
        _flags().put_item(Item={"user_id": user_id, "unlimited": True, "set_at": int(time.time())})
    else:
        _flags().delete_item(Key={"user_id": user_id})


def give_credits(user_id: str, credits: int, note: str = "admin") -> bool:
    """Add paid (never-expiring) credits by hand, once per call (a fresh reference each time)."""
    return grant_paid(user_id, credits, f"{note}-{uuid.uuid4().hex[:10]}")


def _live_buckets(user_id: str, now: float) -> List[Dict[str, Any]]:
    res = _table().query(KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with("B#"), ConsistentRead=True)
    return [b for b in sorted(res["Items"], key=lambda b: b["sk"]) if int(b["remaining"]) > 0 and int(b["expires_at"]) > now]


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_free_credit(user_id: str, *, now: Optional[float] = None, tz: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """When the next daily free credit can be claimed, by the same rule ensure_grants applies: the user's local day (X-Timezone) AND the UTC day must both have
    moved on since the last claim, so it is the later of the next local midnight and the next UTC midnight after the last claim. The credit is added the first
    time the wallet is read or a video is started after that moment (nothing is pushed). {} when daily credits are switched off.
    {"next_free_credit_at": ISO 8601 UTC, "next_free_credits": how many, "next_daily_at": the same moment as epoch seconds (the older field)}"""
    r = rules()
    if r["daily"] <= 0:
        return {"next_daily_at": None, "next_free_credit_at": None, "next_free_credits": 0}
    now = time.time() if now is None else now
    if meta is None:
        meta = _table().get_item(Key={"user_id": user_id, "sk": "META"}).get("Item") or {}
    _, midnight = local_day(now, tz)
    at = int(max(midnight, (int(meta.get("last_daily_utc_day", 0)) + 1) * 86400.0))
    return {"next_daily_at": at, "next_free_credit_at": _iso(at), "next_free_credits": r["daily"]}


def _bucket_view(b: Dict[str, Any]) -> Dict[str, Any]:
    return {"kind": b["kind"], "remaining": int(b["remaining"]), "expires_at": int(b["expires_at"]) if int(b["expires_at"]) < NEVER else None}


def _balance_plans(user_id: str, *, now: float, tz: Optional[str], ctx: Optional[Dict[str, Any]], grant: bool = True) -> Dict[str, Any]:
    """The wallet where plans are on: the same fields as before plus `plan` (which plan, its limits, what is locked and which plan unlocks it, whether upgrading can be
    bought yet) and `free` (what the Free plan offers and whether this account can make a free video now). `grant=False` only reads (GET capabilities)."""
    cfg = plans.config()
    if grant:
        meta, ent = _ensure_grants_plans(user_id, now=now, tz=tz, ctx=ctx, ent=None)
    else:
        ent = entitlements.effective(user_id, now=now)
        meta = _table().get_item(Key={"user_id": user_id, "sk": "META"}).get("Item") or {"welcome_state": "pending"}
    live = _live_buckets(user_id, now)
    unlimited = bool(ent["unlimited"])
    r = plans.rights(ent["plan"], cfg)
    if unlimited:   # the same ceiling the dictation service applies, so what is shown is what is allowed
        r["stt_seconds_per_day"] = plans.unlimited_stt_seconds()
    free = free_grants.summary(user_id, plan=ent["plan"], unlimited=unlimited, meta=meta, buckets=live, ctx=ctx, cfg=cfg, now=now)
    paid = ent["plan"] != "free"   # a paid plan (or a test account on Max's rights) has no weekly FREE window: only its own next release is shown
    allowance = {**free_grants.next_credit(meta, {**cfg, "weekly_allowance": False} if paid else cfg, now, tz), **(next_plan_release(ent, now=now) if paid else {})}
    spendable = [b for b in live if not (ent["plan"] == "free" and not unlimited and b["kind"] in free_grants.FREE_KINDS and free["reason"] in ("app_only", "not_available"))]
    return {"balance": UNLIMITED_DISPLAY if unlimited else sum(int(b["remaining"]) for b in spendable), "unlimited": unlimited, "buckets": [_bucket_view(b) for b in live],
            **allowance, "rules": rules(),
            "plan": {**entitlements.public(ent), "limits": plans.public_limits(r), "locked": plans.locked(ent["plan"], cfg), **({"allowance": allowance} if allowance.get("next_renewal_at") else {}),
                     "plan_credits": sum(int(b["remaining"]) for b in live if b["kind"] == "plan")},
            "free_creation": free["mode"], "free": free, "can_upgrade": plans.PURCHASES_LIVE}


def balance(user_id: str, *, now: Optional[float] = None, tz: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    if plans.enabled():
        return _balance_plans(user_id, now=now, tz=tz, ctx=ctx)
    ensure_grants(user_id, now=now, tz=tz)
    live = _live_buckets(user_id, now)
    meta = _table().get_item(Key={"user_id": user_id, "sk": "META"}).get("Item") or {}
    unlimited = is_unlimited(user_id)
    return {"balance": UNLIMITED_DISPLAY if unlimited else sum(int(b["remaining"]) for b in live), "unlimited": unlimited,
            "buckets": [_bucket_view(b) for b in live],
            **next_free_credit(user_id, now=now, tz=tz, meta=meta), "rules": rules()}


def charge(user_id: str, credits: int, *, now: Optional[float] = None, tz: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Take `credits`, soonest-expiring first. Returns the breakdown (needed to refund exactly what was taken).
    Raises InsufficientCredits. Concurrent requests can never overspend: every bucket update is conditional on what it still holds.
    Where plans are on, a Free account's free credits are only spendable when the request passes free_grants.spend_gate (FreeNotAvailable otherwise)."""
    now = time.time() if now is None else now
    gate = None
    if plans.enabled():
        meta, ent = _ensure_grants_plans(user_id, now=now, tz=tz, ctx=ctx, ent=None)
        if ent["unlimited"]:
            return []
        if ent["plan"] == "free":
            gate = free_grants.spend_gate(ctx, meta, plans.config(), now)
    else:
        ensure_grants(user_id, now=now, tz=tz)
        if is_unlimited(user_id):
            return []  # nothing taken, so a failed video has nothing to refund
    for _ in range(5):
        live = _live_buckets(user_id, now)
        if gate is not None:
            every = sum(int(b["remaining"]) for b in live)
            live = [b for b in live if b["kind"] not in free_grants.FREE_KINDS]
            if sum(int(b["remaining"]) for b in live) < credits <= every:
                raise FreeNotAvailable(sum(int(b["remaining"]) for b in live), credits, gate)
        have = sum(int(b["remaining"]) for b in live)
        if have < credits:
            raise InsufficientCredits(have, credits)
        need, takes = credits, []
        for b in live:
            take = min(need, int(b["remaining"]))
            takes.append({"sk": b["sk"], "n": take})
            need -= take
            if need == 0:
                break
        try:
            _tx([{"Update": {"TableName": _table().name, "Key": {"user_id": user_id, "sk": x["sk"]}, "UpdateExpression": "SET remaining = remaining - :n",
                             "ConditionExpression": "remaining >= :n AND expires_at > :now", "ExpressionAttributeValues": {":n": x["n"], ":now": int(now)}}} for x in takes])
            return takes
        except ClientError as e:
            if not _cancelled(e):
                raise  # a concurrent spend changed a bucket: read again and retry
    raise InsufficientCredits(0, credits)


def refund(user_id: str, breakdown: List[Dict[str, Any]], *, now: Optional[float] = None) -> int:
    """Put taken credits back where they came from; if that bucket has expired meanwhile, give a 24-hour make-good instead."""
    now = time.time() if now is None else now
    t, total = _table(), 0
    for x in breakdown:
        n = int(x["n"])
        try:
            t.update_item(Key={"user_id": user_id, "sk": x["sk"]}, UpdateExpression="SET remaining = remaining + :n",
                          ConditionExpression="attribute_exists(sk) AND expires_at > :now", ExpressionAttributeValues={":n": n, ":now": int(now)})
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            t.put_item(Item=_bucket(user_id, "refund", n, int(now + 86400), now))
        total += n
    return total


def refund_video(item: Dict[str, Any]) -> int:
    """Refund what a video was charged, exactly once (failed or rejected videos cost nothing). Safe to call twice."""
    charge_json, video_id, user_id = item.get("charge"), item.get("video_id"), str(item.get("user_id") or "")
    if not charge_json or not video_id or not user_id:
        return 0
    try:
        boto3.resource("dynamodb").Table(os.environ["VIDEOS_TABLE"]).update_item(
            Key={"video_id": video_id}, UpdateExpression="SET refunded = :t", ConditionExpression="attribute_not_exists(refunded)", ExpressionAttributeValues={":t": True})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return 0
        raise
    return refund(user_id, json.loads(charge_json))


def grant_paid(user_id: str, credits: int, ref: str, *, now: Optional[float] = None, tz: Optional[str] = None) -> bool:
    """Add purchased credits once per store transaction `ref` (False when this ref was already granted). Paid credits never expire."""
    now = time.time() if now is None else now
    ensure_grants(user_id, now=now, tz=tz)
    tn = _table().name
    try:
        _tx([{"Put": {"TableName": tn, "Item": {"user_id": user_id, "sk": f"REF#{ref}", "credits": credits, "at": int(now)}, "ConditionExpression": "attribute_not_exists(user_id)"}},
             {"Update": {"TableName": tn, "Key": {"user_id": user_id, "sk": f"B#{NEVER:010d}#paid#main"},
                         "UpdateExpression": "ADD remaining :n, granted :n SET kind = :k, expires_at = :e, created_at = if_not_exists(created_at, :now)",
                         "ExpressionAttributeValues": {":n": credits, ":k": "paid", ":e": NEVER, ":now": int(now)}}}])
        return True
    except ClientError as e:
        if _cancelled(e):
            return False
        raise
