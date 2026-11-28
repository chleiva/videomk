"""Account deletion (docs/ACCOUNT_DELETION.md): the steps, the job record, the tombstone and the safety-record rule. Pure Python on boto3, no network but AWS.

How it runs: `POST /users/{user}/account/delete` (account_api.py) writes a JOB item and sends one SQS message. The worker (account_deleter.py) calls `run(user)`, which does the
steps in order, each one idempotent, and records every finished step on the job. A failing step is logged (`ACCOUNT_DELETION_FAILED`), counted and retried later; nothing is ever
skipped. The Cognito user is deleted LAST, so a stuck run can always be resumed with the same identity (scripts/account_admin.py).

Order (STEPS): begin (disable sign-in, revoke refresh tokens) -> executions (stop running video workflows) -> media -> videos -> wallet -> usage -> flags -> safety -> tombstone ->
settle (wait until every token issued before `begin` has expired: a still-valid token could otherwise recreate a row) -> recheck (all data steps again) -> cognito -> finish.

What belongs to a person (one place; tests/test_account_deletion.py checks it against the CDK stack and against the keys the code writes):
  VIDEOS table (GSI_UserVideos by user_id; primary key video_id)          -> items; S3 assets bucket generation/v2/<video>/ and generation/assets/<video>/ first
  S3 assets bucket   videos/<user>/  uploads/<user>/                      -> every object
  MEDIA table (user_id, sk: m# h# c# cm# prefs facets stats)              -> every row of the partition
  S3 media bucket    o/<user>/  t/<user>/ ; S3 Vectors index photos, key <user>:<photo>
  WALLET table (user_id: META, B#..., REF#...)                            -> every row
  USAGE table  user_id = <user> | upload: libup: libsearch: brief: unlimited: dup: edit: + <user> -> every row
  FLAGS table  user_id = <user> | safety:<user>                           -> deleted (the worker may only DeleteItem there)
  SAFETY table user_id = <user>                                           -> re-keyed to deleted:<hashed ref>, only what the privacy policy discloses, original expiry
  Cognito user                                                            -> AdminDeleteUser (drops linked Google and Apple identities)
Kept on purpose: the re-keyed safety records (90 days from the stop), the job record (30 days after completion: user id and step times only), and, only when the owner switches
it on (TOMBSTONE_ENABLED=1), a salted hash of the verified email and of the federated username for TOMBSTONE_DAYS so that a welcome credit cannot be collected twice.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import i18n

logger = logging.getLogger()

USER_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
VIDEO_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")

STEPS = ["begin", "executions", "media", "videos", "wallet", "usage", "flags", "safety", "feedback", "tombstone", "settle", "recheck", "cognito", "finish"]
DATA_STEPS = ["media", "videos", "wallet", "usage", "flags", "safety", "feedback"]

# every usage-table partition a person can have (code: usage.consume(f"<prefix>:{user}") and the plain `user` of the daily video quota)
USAGE_PREFIXES = ("", "upload:", "libup:", "libsearch:", "brief:", "unlimited:", "dup:", "edit:", "deck:", "deckproc:", "feedback:", "feedbackh:", "wmlogo:", "freemonth:", "devch:", "clipgen:acct:")
FLAG_KEYS = ("{u}", "safety:{u}")
ASSET_USER_PREFIXES = ("videos/{u}/", "uploads/{u}/", "watermark/{u}/")   # watermark/: the saved watermark settings and logo (docs/WATERMARK.md)
ASSET_VIDEO_PREFIXES = ("generation/v2/{v}/", "generation/assets/{v}/")
MEDIA_PREFIXES = ("o/{u}/", "t/{u}/")
SHARED_PREFIXES = ("music/",)   # the shared music catalogue: belongs to nobody

SAFETY_KEEP_DAYS = 90      # privacy policy: stops are kept 90 days
JOB_KEEP_DAYS = 30         # how long a finished job record stays (then DynamoDB TTL removes it)
MAX_FAILS = 30             # consecutive failures of one step before the job is marked stuck (about 7 hours with the backoff below)
RECENT_AUTH_SECONDS = 600  # the sign-in must be at most this old


class DeletionError(Exception):
    """A request problem with the HTTP status to answer with (API) or a bad input (worker)."""

    def __init__(self, status: int, message: Any, **extra: Any):
        """`message` is the English text, or an `i18n.Localized` (then `text(locale)` gives the person's language; `message` stays English)."""
        self.localized = message if isinstance(message, i18n.Localized) else None
        super().__init__(str(message))
        self.status, self.message, self.extra = status, str(message), extra

    def text(self, locale: Any = None) -> str:
        return self.localized.message(locale) if self.localized else self.message


class TimeUp(Exception):
    """The invocation is nearly out of time: stop, keep what is done, continue in the next message."""


class Budget:
    def __init__(self, seconds: float = 1e9, clock: Callable[[], float] = time.monotonic):
        self.clock, self.deadline = clock, clock() + seconds

    def check(self) -> None:
        if self.clock() > self.deadline:
            raise TimeUp()


# ----------------------------------------------------------------------------- clients (lazy, so tests can mock AWS)
_cache: Dict[str, Any] = {}


def reset_clients() -> None:
    _cache.clear()


def _get(name: str, make: Callable[[], Any]) -> Any:
    if name not in _cache:
        _cache[name] = make()
    return _cache[name]


def ddb():
    return _get("ddb", lambda: boto3.resource("dynamodb"))


def s3():
    return _get("s3", lambda: boto3.client("s3"))


def idp():
    return _get("idp", lambda: boto3.client("cognito-idp"))


def sfn():
    return _get("sfn", lambda: boto3.client("stepfunctions"))


def sqs():
    return _get("sqs", lambda: boto3.client("sqs"))


def vectors():
    return _get("vec", lambda: boto3.client("s3vectors"))


def set_client(name: str, client: Any) -> None:
    _cache[name] = client


def _env(name: str) -> str:
    v = os.environ.get(name, "")
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def check_user(user: Any) -> str:
    if not isinstance(user, str) or not USER_RE.match(user):
        raise DeletionError(403, i18n.Localized("err.forbidden"))
    return user


# ----------------------------------------------------------------------------- hashing (HMAC with a per-stage secret: salted, and not computable by anyone without it)
_KEY: Optional[bytes] = None


def set_key(key: Optional[bytes]) -> None:
    global _KEY
    _KEY = key


def _key() -> bytes:
    global _KEY
    if _KEY is None:
        sm = _get("sm", lambda: boto3.client("secretsmanager"))
        _KEY = sm.get_secret_value(SecretId=_env("DELETION_KEY_SECRET"))["SecretString"].encode("utf-8")
        if len(_KEY) < 16:
            raise RuntimeError("the deletion key is too short")
    return _KEY


def mac(domain: str, value: str) -> str:
    """Domain-separated HMAC-SHA256 hex digest: the same value hashes differently for each purpose."""
    return hmac.new(_key(), f"{domain}\0{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def account_ref(user: str) -> str:
    """The hashed account reference kept on safety records after deletion."""
    return mac("acct", user)[:32]


def normalise_email(email: str) -> str:
    """Lower case, no +tag, no dots for gmail: the spellings of one mailbox are one value (so a +tag cannot dodge the tombstone)."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return e
    local, domain = e.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def tombstone_enabled() -> bool:
    return os.environ.get("TOMBSTONE_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def tombstone_days() -> int:
    try:
        return max(1, min(365, int(os.environ.get("TOMBSTONE_DAYS", "90"))))
    except ValueError:
        return 90


def tombstone_keys(attrs: Dict[str, str], username: str, user: str) -> List[str]:
    """The tombstone keys of one pool user: verified email, and the username when it comes from a federated provider (a native username is just the `sub`)."""
    keys: List[str] = []
    if attrs.get("email") and str(attrs.get("email_verified", "")).lower() == "true":
        keys.append("tomb#e#" + mac("email", normalise_email(attrs["email"])))
    if username and username != user and "_" in username:   # Cognito names a federated user <Provider>_<provider id>
        keys.append("tomb#u#" + mac("username", username))
    return keys


# ----------------------------------------------------------------------------- Cognito
def _attrs(user_obj: Dict[str, Any]) -> Dict[str, str]:
    return {a["Name"]: a["Value"] for a in user_obj.get("UserAttributes") or user_obj.get("Attributes") or []}


def find_pool_user(user: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """{'username', 'attrs'} of the pool user whose `sub` is `user`, or None. Never returns somebody else: the sub is compared."""
    pool = _env("USER_POOL_ID")
    if username:
        try:
            u = idp().admin_get_user(UserPoolId=pool, Username=username)
            if _attrs(u).get("sub") == user:
                return {"username": u["Username"], "attrs": _attrs(u)}
        except ClientError as e:
            if e.response["Error"]["Code"] != "UserNotFoundException":
                raise
    res = idp().list_users(UserPoolId=pool, Filter=f'sub = "{check_user(user)}"', Limit=2)
    users = [u for u in res.get("Users", []) if _attrs(u).get("sub") == user]
    if len(users) != 1:
        return None
    return {"username": users[0]["Username"], "attrs": _attrs(users[0])}


def apple_identity(attrs: Dict[str, str]) -> Optional[str]:
    """Apple's own id of the person (the `sub` Apple puts in its id token), from the pool user's `identities` attribute, or None."""
    try:
        for i in json.loads(attrs.get("identities") or "[]"):
            if i.get("providerName") == "SignInWithApple" and i.get("userId"):
                return str(i["userId"])
    except (ValueError, TypeError, AttributeError):
        pass
    return None


# ----------------------------------------------------------------------------- the job record (DELETION table: pk = job#<user> | tomb#...)
def deletion_table():
    return ddb().Table(_env("DELETION_TABLE"))


def job_key(user: str) -> Dict[str, str]:
    return {"pk": f"job#{check_user(user)}"}


def get_job(user: str) -> Optional[Dict[str, Any]]:
    return deletion_table().get_item(Key=job_key(user), ConsistentRead=True).get("Item")


def create_job(user: str, username: Optional[str] = None, *, now: Optional[float] = None, settle_seconds: Optional[int] = None, by: str = "user") -> bool:
    """True when this call created the job, False when one already exists (the request is idempotent)."""
    now = int(time.time() if now is None else now)
    settle = int(os.environ.get("DELETION_SETTLE_SECONDS", "3900") if settle_seconds is None else settle_seconds)
    item = {**job_key(user), "user_id": user, "status": "queued", "created_at": now, "settle_at": now + settle, "steps": {}, "fails": 0, "by": by}
    if username:
        item["username"] = username
    try:
        deletion_table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _update(user: str, expr: str, names: Optional[Dict[str, str]] = None, values: Optional[Dict[str, Any]] = None) -> None:
    kw: Dict[str, Any] = {"Key": job_key(user), "UpdateExpression": expr, "ConditionExpression": "attribute_exists(pk)"}
    if names:
        kw["ExpressionAttributeNames"] = names
    if values:
        kw["ExpressionAttributeValues"] = values
    deletion_table().update_item(**kw)


def enqueue(user: str, delay: int = 0) -> None:
    sqs().send_message(QueueUrl=_env("DELETION_QUEUE_URL"), MessageBody=json.dumps({"user_id": check_user(user)}), DelaySeconds=max(0, min(900, int(delay))))


def reopen(user: str) -> None:
    """A stuck (or failed) job is given a fresh set of attempts (the app calling again, or staff)."""
    _update(user, "SET #s = :q, fails = :z REMOVE last_error", {"#s": "status"}, {":q": "queued", ":z": 0})


def mark_apple_revoked(user: str, now: Optional[float] = None) -> None:
    _update(user, "SET apple_revoked_at = :t", None, {":t": int(time.time() if now is None else now)})


# ----------------------------------------------------------------------------- generic AWS helpers
def _query_all(table: Any, budget: Budget, **kw: Any) -> Iterator[Dict[str, Any]]:
    last = None
    while True:
        budget.check()
        res = table.query(**kw, **({"ExclusiveStartKey": last} if last else {}))
        yield from res.get("Items", [])
        last = res.get("LastEvaluatedKey")
        if not last:
            return


def _delete_keys(table: Any, keys: Iterable[Dict[str, Any]], budget: Budget) -> int:
    n = 0
    with table.batch_writer() as bw:
        for k in keys:
            if n % 200 == 0:
                budget.check()
            bw.delete_item(Key=k)
            n += 1
    return n


def _partition_delete(table_env: str, partition: str, budget: Budget, hash_name: str = "user_id", range_name: str = "sk") -> int:
    """Every row of one partition, for tables keyed (user_id, <range>)."""
    table = ddb().Table(_env(table_env))
    rows = list(_query_all(table, budget, KeyConditionExpression=Key(hash_name).eq(partition), ProjectionExpression="#h, #r", ExpressionAttributeNames={"#h": hash_name, "#r": range_name}))
    return _delete_keys(table, ({hash_name: r[hash_name], range_name: r[range_name]} for r in rows), budget)


def _s3_keys(bucket: str, prefix: str, budget: Budget) -> Iterator[str]:
    token = None
    while True:
        budget.check()
        res = s3().list_objects_v2(Bucket=bucket, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
        for o in res.get("Contents", []):
            yield o["Key"]
        token = res.get("NextContinuationToken")
        if not token:
            return


def _s3_delete_prefix(bucket: str, prefix: str, budget: Budget) -> int:
    """Deletes every object under `prefix`; raises when S3 reports a failed key (so the step is retried, not skipped)."""
    n, batch = 0, []

    def flush() -> int:
        if not batch:
            return 0
        res = s3().delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
        if res.get("Errors"):
            raise RuntimeError(f"S3 could not delete {len(res['Errors'])} objects ({res['Errors'][0].get('Code')})")
        done = len(batch)
        batch.clear()
        return done

    for k in _s3_keys(bucket, prefix, budget):
        batch.append(k)
        if len(batch) >= 1000:
            n += flush()
    return n + flush()


# ----------------------------------------------------------------------------- the data steps (each idempotent; each returns counts)
def _video_rows(user: str, budget: Budget) -> List[Dict[str, Any]]:
    t = ddb().Table(_env("VIDEOS_TABLE"))
    return list(_query_all(t, budget, IndexName="GSI_UserVideos", KeyConditionExpression=Key("user_id").eq(user)))


def _video_ids(user: str, rows: List[Dict[str, Any]], budget: Budget) -> List[str]:
    """Video ids from the rows AND from the final files (videos/<user>/<id>...), so a video whose row was lost still has its working files removed."""
    ids = {str(r["video_id"]) for r in rows if r.get("video_id")}
    base = f"videos/{user}/"
    for k in _s3_keys(_env("ASSETS_BUCKET"), base, budget):
        first = k[len(base):].split("/", 1)[0]
        first = first.rsplit(".", 1)[0] if "." in first else first
        if VIDEO_RE.match(first):
            ids.add(first)
    return sorted(i for i in ids if VIDEO_RE.match(i))


def step_executions(user: str, budget: Budget) -> Dict[str, int]:
    """Stop the user's running workflows first, so nothing new is written while the rest is deleted. A stopped execution can never refund; the wallet is deleted anyway."""
    rows = _video_rows(user, budget)
    vids = _video_ids(user, rows, budget)
    recent = {str(r["video_id"]) for r in rows if str(r.get("created_at", "")) >= time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 86400))}
    stopped = 0

    def stop(arn: str) -> None:
        nonlocal stopped
        try:
            sfn().stop_execution(executionArn=arn, cause="account deleted")
            stopped += 1
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("ExecutionDoesNotExist", "ExecutionAlreadyStopped"):
                raise

    for machine in [m for m in os.environ.get("GENERATE_STATE_MACHINE_ARNS", "").split(",") if m]:
        base = machine.replace(":stateMachine:", ":execution:")
        for v in sorted(recent):
            budget.check()
            if VIDEO_RE.match(v):
                stop(f"{base}:{v}")   # the launcher names the execution after the video id
                for n in range(1, 4):   # a retried video runs as <video id>-r<n> (lambdas/video_retry.py, at most 3 retries)
                    stop(f"{base}:{v}-r{n}")
    edit = os.environ.get("EDIT_STATE_MACHINE_ARN", "")
    if edit and vids:
        prefixes = tuple(f"{v}-r" for v in vids)
        token = None
        while True:
            budget.check()
            res = sfn().list_executions(stateMachineArn=edit, statusFilter="RUNNING", maxResults=100, **({"nextToken": token} if token else {}))
            for e in res.get("executions", []):
                if e["name"].startswith(prefixes):   # edits are named <video id>-r<rev>-...
                    stop(e["executionArn"])
            token = res.get("nextToken")
            if not token:
                break
    return {"stopped": stopped}


def step_media(user: str, budget: Budget) -> Dict[str, int]:
    """The photo library, strictly: a vector or file that cannot be deleted raises (the library's own purge only logs it)."""
    if not os.environ.get("MEDIA_TABLE"):
        return {"skipped": 1}   # this stage has no media library (engine v1)
    table, bucket = ddb().Table(_env("MEDIA_TABLE")), _env("MEDIA_BUCKET")
    rows = list(_query_all(table, budget, KeyConditionExpression=Key("user_id").eq(user), ProjectionExpression="user_id, sk"))
    mids = {r["sk"][2:] for r in rows if r["sk"].startswith("m#")}
    for p in MEDIA_PREFIXES:   # photos whose row is already gone (an upload that finished late) still have a vector to remove
        for k in _s3_keys(bucket, p.format(u=user), budget):
            m = k.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if re.match(r"^[0-9a-f]{16}$", m):
                mids.add(m)
    keys = sorted(f"{user}:{m}" for m in mids)
    for i in range(0, len(keys), 500):
        budget.check()
        vectors().delete_vectors(vectorBucketName=_env("VECTOR_BUCKET"), indexName=os.environ.get("VECTOR_INDEX", "photos"), keys=keys[i:i + 500])
    files = sum(_s3_delete_prefix(bucket, p.format(u=user), budget) for p in MEDIA_PREFIXES)
    n = _delete_keys(table, ({"user_id": r["user_id"], "sk": r["sk"]} for r in rows), budget)
    return {"rows": n, "files": files, "vectors": len(keys)}


def step_videos(user: str, budget: Budget) -> Dict[str, int]:
    """Working files of each video first, then the user's final videos and uploads, then the rows: until the last row is gone the next run can still find every video."""
    bucket = _env("ASSETS_BUCKET")
    rows = _video_rows(user, budget)
    vids = _video_ids(user, rows, budget)
    files = 0
    from common import share_revoke
    for r in rows:   # shared links first: the token lives on the row, which goes last
        if r.get("user_id") == user and r.get("share_token"):
            share_revoke.revoke_item(r)
    for v in vids:
        for p in ASSET_VIDEO_PREFIXES:
            files += _s3_delete_prefix(bucket, p.format(v=v), budget)
    for p in ASSET_USER_PREFIXES:
        files += _s3_delete_prefix(bucket, p.format(u=user), budget)
    table = ddb().Table(_env("VIDEOS_TABLE"))
    n = _delete_keys(table, ({"video_id": r["video_id"]} for r in rows if r.get("user_id") == user), budget)
    return {"videos": n, "files": files}


def step_wallet(user: str, budget: Budget) -> Dict[str, int]:
    return {"rows": _partition_delete("WALLET_TABLE", user, budget)}


def step_usage(user: str, budget: Budget) -> Dict[str, int]:
    return {"rows": sum(_partition_delete("USAGE_TABLE", f"{p}{user}", budget, range_name="day") for p in USAGE_PREFIXES)}


def step_flags(user: str, budget: Budget) -> Dict[str, int]:
    table, n = ddb().Table(_env("FLAGS_TABLE")), 0
    for k in FLAG_KEYS:
        table.delete_item(Key={"user_id": k.format(u=user)})   # an absent item is not an error
        n += 1
    if os.environ.get("ENTITLEMENTS_TABLE"):   # the plan record (docs/PLANS.md). The free-allowance claim (a salted hash with no account id) is NOT deleted: that is its purpose
        ddb().Table(os.environ["ENTITLEMENTS_TABLE"]).delete_item(Key={"user_id": user})
        n += 1
    return {"keys": n}


def step_safety(user: str, budget: Budget, now: Optional[float] = None) -> Dict[str, int]:
    """Keep exactly what the privacy policy says (category, time, a short excerpt, the request fingerprint, 90 days) under a hashed account reference; delete the rest."""
    if not os.environ.get("SAFETY_TABLE"):
        return {"skipped": 1}
    now = time.time() if now is None else now
    table = ddb().Table(_env("SAFETY_TABLE"))
    ref = f"deleted:{account_ref(user)}"
    n = 0
    for r in list(_query_all(table, budget, KeyConditionExpression=Key("user_id").eq(user), ConsistentRead=True)):
        ts = int(r["ts"])
        ttl = int(r.get("ttl") or (ts // 1000 + SAFETY_KEEP_DAYS * 86400))
        if ttl > now:   # an already expired record is simply dropped
            table.put_item(Item={"user_id": ref, "ts": ts, "category": r.get("category"), "severity": r.get("severity"), "excerpt": str(r.get("excerpt") or "")[:160],
                                 "prompt_hash": r.get("prompt_hash"), "ttl": ttl})
        table.delete_item(Key={"user_id": user, "ts": ts})
        n += 1
    return {"records": n}


def step_feedback(user: str, budget: Budget) -> Dict[str, int]:
    """Keep the person's feedback text (owner value, privacy page) but cut the link: userId becomes a one-way keyed hash. Idempotent; skipped where the feature is off."""
    if not os.environ.get("FEEDBACK_TABLE"):
        return {"skipped": 1}
    table = ddb().Table(_env("FEEDBACK_TABLE"))
    ref = f"deleted:{account_ref(user)}"
    n = 0
    for r in list(_query_all(table, budget, IndexName="GSI_User", KeyConditionExpression=Key("userId").eq(user))):
        table.update_item(Key={"feedbackId": r["feedbackId"]}, UpdateExpression="SET userId = :r", ExpressionAttributeValues={":r": ref})
        n += 1
    return {"rows": n}


def step_tombstone(user: str, username: Optional[str], now: Optional[float] = None) -> Dict[str, int]:
    if not tombstone_enabled():
        return {"skipped": 1}
    now = int(time.time() if now is None else now)
    pu = find_pool_user(user, username)
    if pu is None:
        return {"keys": 0}
    exp = now + tombstone_days() * 86400
    keys = tombstone_keys(pu["attrs"], pu["username"], user)
    for k in keys:
        deletion_table().put_item(Item={"pk": k, "at": now, "expires_at": exp, "ttl": exp})
    return {"keys": len(keys)}


def signup_block(user: str, *, now: Optional[float] = None) -> Optional[str]:
    """Asked by the wallet the first time it sees a `sub`: 'deleting' (this very account is being deleted: no grant, no rows) or 'returning' (the verified email or federated
    username of a recently deleted account: no welcome credit) or None. The second needs TOMBSTONE_ENABLED and fails closed (an error means the wallet call is retried)."""
    if not os.environ.get("DELETION_TABLE") or not isinstance(user, str) or not USER_RE.match(user):
        return None
    if get_job(user):
        return "deleting"
    if not tombstone_enabled():
        return None
    now = int(time.time() if now is None else now)
    pu = find_pool_user(user)
    if pu is None:
        return None
    for k in tombstone_keys(pu["attrs"], pu["username"], user):
        item = deletion_table().get_item(Key={"pk": k}).get("Item")
        if item and int(item.get("expires_at", 0)) > now:
            return "returning"
    return None


# ----------------------------------------------------------------------------- the run
@dataclass
class Outcome:
    status: str          # done | wait | retry | continue | stuck | absent
    delay: int = 0       # seconds until the next message
    step: str = ""


def backoff(fails: int) -> int:
    return min(900, 30 * 2 ** max(0, fails - 1))


def _step_fn(name: str, user: str, username: Optional[str], budget: Budget, now: float, job: Dict[str, Any]) -> Dict[str, Any]:
    if name == "begin":
        pu = find_pool_user(user, username)
        if pu is None:
            _update(user, "SET settle_at = :s", None, {":s": int(now)})   # no pool user: no token can still be issued
            return {"user": "absent"}
        idp().admin_disable_user(UserPoolId=_env("USER_POOL_ID"), Username=pu["username"])
        idp().admin_user_global_sign_out(UserPoolId=_env("USER_POOL_ID"), Username=pu["username"])
        # the wait for old tokens to expire starts NOW (after the last token could be issued), not at the request: a delayed first step must not shorten it
        _update(user, "SET username = :u, settle_at = :s", None, {":u": pu["username"], ":s": int(now) + int(os.environ.get("DELETION_SETTLE_SECONDS", "3900"))})
        return {"user": "disabled"}
    if name == "executions":
        return step_executions(user, budget)
    if name in DATA_STEPS:
        return {"media": step_media, "videos": step_videos, "wallet": step_wallet, "usage": step_usage, "flags": step_flags, "safety": lambda u, b: step_safety(u, b, now), "feedback": step_feedback}[name](user, budget)
    if name == "tombstone":
        return step_tombstone(user, username, now)
    if name == "recheck":
        return {s: _step_fn(s, user, username, budget, now, job) for s in DATA_STEPS}
    if name == "cognito":
        pu = find_pool_user(user, username)
        if pu is None:
            return {"user": "absent"}
        idp().admin_delete_user(UserPoolId=_env("USER_POOL_ID"), Username=pu["username"])
        return {"user": "deleted"}
    if name == "finish":
        return {}
    raise RuntimeError(f"unknown step {name}")


def run(user: str, *, now: Optional[float] = None, budget: Optional[Budget] = None, skip_settle: bool = False) -> Outcome:
    """Do every step that is not done yet, in order. Returns what the caller should do next (see Outcome)."""
    check_user(user)
    budget = budget or Budget()
    job = get_job(user)
    if job is None:
        return Outcome("absent")
    if job.get("status") == "done":
        return Outcome("done")
    if job.get("status") == "stuck":
        return Outcome("stuck")
    _update(user, "SET #s = :r", {"#s": "status"}, {":r": "running"})
    for name in STEPS:
        job = get_job(user) or job
        if name in (job.get("steps") or {}):
            continue
        t = int(time.time() if now is None else now)
        if name == "settle":
            if not skip_settle and t < int(job["settle_at"]):
                _update(user, "SET #s = :w", {"#s": "status"}, {":w": "waiting"})
                return Outcome("wait", min(900, int(job["settle_at"]) - t + 1), name)
            counts: Dict[str, Any] = {}
        elif name == "finish":
            exp = t + JOB_KEEP_DAYS * 86400
            _update(user, "SET #s = :d, steps.#n = :v, finished_at = :t, #ttl = :e", {"#s": "status", "#n": name, "#ttl": "ttl"}, {":d": "done", ":v": {"at": t, "n": {}}, ":t": t, ":e": exp})
            logger.info("ACCOUNT_DELETION_DONE user=%s", user)
            return Outcome("done", 0, name)
        else:
            try:
                counts = _step_fn(name, user, job.get("username"), budget, t, job)
            except TimeUp:
                _update(user, "SET #s = :q", {"#s": "status"}, {":q": "queued"})
                return Outcome("continue", 0, name)
            except Exception as e:   # noqa: BLE001 - every failure is recorded and retried; the log line carries the step, the error class and AWS code, never a message that could hold personal data
                code = e.response.get("Error", {}).get("Code", "") if isinstance(e, ClientError) else ""
                fails = int(job.get("fails") or 0) + 1
                stuck = fails >= MAX_FAILS
                _update(user, "SET fails = :f, #s = :s, last_error = :e", {"#s": "status"},
                        {":f": fails, ":s": "stuck" if stuck else "retrying", ":e": {"step": name, "type": type(e).__name__, "code": code, "at": t}})
                logger.error("ACCOUNT_DELETION_FAILED user=%s step=%s error=%s%s attempt=%d", user, name, type(e).__name__, f"/{code}" if code else "", fails)
                if stuck:
                    logger.error("ACCOUNT_DELETION_STUCK user=%s step=%s after=%d", user, name, fails)
                    return Outcome("stuck", 0, name)
                return Outcome("retry", backoff(fails), name)
        _update(user, "SET steps.#n = :v, fails = :z", {"#n": name}, {":v": {"at": t, "n": json.loads(json.dumps(counts))}, ":z": 0})
    return Outcome("done")


def inventory(user: str, budget: Optional[Budget] = None) -> Dict[str, int]:
    """What is still stored for this person, per store (read only; used by scripts/account_admin.py and the tests). All zeros means the data steps have nothing left to do."""
    budget = budget or Budget()
    out: Dict[str, int] = {}
    rows = _video_rows(user, budget)
    out["videos_rows"] = len(rows)
    bucket = _env("ASSETS_BUCKET")
    n = sum(1 for p in ASSET_USER_PREFIXES for _ in _s3_keys(bucket, p.format(u=user), budget))
    for v in _video_ids(user, rows, budget):
        n += sum(1 for p in ASSET_VIDEO_PREFIXES for _ in _s3_keys(bucket, p.format(v=v), budget))
    out["assets_files"] = n
    for env, name in (("WALLET_TABLE", "wallet_rows"),):
        out[name] = sum(1 for _ in _query_all(ddb().Table(_env(env)), budget, KeyConditionExpression=Key("user_id").eq(user)))
    out["usage_rows"] = sum(1 for p in USAGE_PREFIXES for _ in _query_all(ddb().Table(_env("USAGE_TABLE")), budget, KeyConditionExpression=Key("user_id").eq(f"{p}{user}")))
    out["flags_rows"] = sum(1 for k in FLAG_KEYS if ddb().Table(_env("FLAGS_TABLE")).get_item(Key={"user_id": k.format(u=user)}).get("Item"))
    if os.environ.get("ENTITLEMENTS_TABLE"):
        out["entitlement_rows"] = 1 if ddb().Table(os.environ["ENTITLEMENTS_TABLE"]).get_item(Key={"user_id": user}).get("Item") else 0
    if os.environ.get("SAFETY_TABLE"):
        out["safety_rows"] = sum(1 for _ in _query_all(ddb().Table(_env("SAFETY_TABLE")), budget, KeyConditionExpression=Key("user_id").eq(user)))
    if os.environ.get("MEDIA_TABLE"):
        out["media_rows"] = sum(1 for _ in _query_all(ddb().Table(_env("MEDIA_TABLE")), budget, KeyConditionExpression=Key("user_id").eq(user)))
        out["media_files"] = sum(1 for p in MEDIA_PREFIXES for _ in _s3_keys(_env("MEDIA_BUCKET"), p.format(u=user), budget))
    return out


# ----------------------------------------------------------------------------- the API side
def recent_auth(claims_auth_time: Any, *, now: Optional[float] = None, max_age: int = RECENT_AUTH_SECONDS) -> bool:
    """True when the token's `auth_time` (when the person last typed a password or used a provider) is at most `max_age` seconds old. Missing, odd or future values are 'not recent'."""
    try:
        t = int(float(claims_auth_time))
    except (TypeError, ValueError):
        return False
    now = time.time() if now is None else now
    return now - max_age <= t <= now + 60
