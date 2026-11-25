"""The private photo library: keys, quota, uploads, listing, collections, delete. See docs/MEDIA_LIBRARY.md.

Security rules this module keeps (tests enforce them):
  * The user id is only ever the verified Cognito `sub`, checked here against a strict pattern; every S3 key and DynamoDB key is built from it, never from client text.
  * Ids from the client (photo, collection, cursor) are looked up under the caller's own partition only: somebody else's id is simply "not found".
  * A paging cursor carries only a sort position; the partition key is rebuilt from the caller, never read from the cursor.
  * Presigned links are made only for photos found under the caller's partition.
"""
import base64
import datetime
import json
import logging
import os
import random
import re
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger()

GB = 1_000_000_000
FREE_BYTES = int(os.environ.get("LIBRARY_FREE_GB", "2")) * GB
PRO_BYTES = int(os.environ.get("LIBRARY_PRO_GB", "100")) * GB
ADDON_BYTES = GB          # an add-on is counted in whole GB (`storage_extra_gb`)
MAX_PHOTO_BYTES = 12_000_000          # the apps send at most ~2 MB (2048 px); this is only the hard ceiling of a slot
MAX_SLOTS_PER_CALL = 100
MAX_IDS = 100
DAILY_SLOTS = int(os.environ.get("LIBRARY_UPLOADS_PER_DAY", "2000"))
DAILY_SEARCHES = int(os.environ.get("LIBRARY_SEARCHES_PER_DAY", "400"))
SLOT_SECONDS = 900
THUMB_LINK_SECONDS = 3600
PHOTO_LINK_SECONDS = 600
PENDING_MAX_AGE_S = 45 * 60
MAX_COLLECTIONS = 1000   # automatic organising can make many (a place and month each)
MAX_PER_PHOTO_COLLECTIONS = 50
THUMB_PX = 480

USER_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
ID_RE = re.compile(r"^[0-9a-f]{16}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SRT_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d#[0-9a-f]{16}$")
DAY_RE = re.compile(r"^\d{4}-\d\d-\d\d$")
ORIG_RE = re.compile(r"^o/([A-Za-z0-9-]{8,64})/([0-9a-f]{16})\.jpg$")


class LibraryError(Exception):
    """A request problem with the HTTP status to answer with."""

    def __init__(self, status: int, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


# ----------------------------------------------------------------------------- clients (lazy, so tests can mock AWS)
_cache: Dict[str, Any] = {}


def reset_clients() -> None:
    _cache.clear()


def _get(name: str, make: Callable[[], Any]) -> Any:
    if name not in _cache:
        _cache[name] = make()
    return _cache[name]


def s3():
    return _get("s3", lambda: boto3.client("s3", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
                                          config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})))


def ddb():
    return _get("ddb", lambda: boto3.resource("dynamodb"))


def table():
    return ddb().Table(os.environ["MEDIA_TABLE"])


def vectors():
    return _get("vec", lambda: boto3.client("s3vectors"))


def set_vectors(client: Any) -> None:
    _cache["vec"] = client


def bucket() -> str:
    return os.environ["MEDIA_BUCKET"]


def vector_target() -> Dict[str, str]:
    return {"vectorBucketName": os.environ["VECTOR_BUCKET"], "indexName": os.environ.get("VECTOR_INDEX", "photos")}


# ----------------------------------------------------------------------------- identity and keys
def check_user(user: Any) -> str:
    if not isinstance(user, str) or not USER_RE.match(user):
        raise LibraryError(403, "Forbidden")
    return user


def check_id(mid: Any) -> str:
    if not isinstance(mid, str) or not ID_RE.match(mid):
        raise LibraryError(400, "invalid id")
    return mid


def orig_key(user: str, mid: str) -> str:
    return f"o/{check_user(user)}/{check_id(mid)}.jpg"


def thumb_key(user: str, mid: str) -> str:
    return f"t/{check_user(user)}/{check_id(mid)}.jpg"


def vec_key(user: str, mid: str) -> str:
    return f"{check_user(user)}:{check_id(mid)}"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _epoch(iso: str) -> float:
    return datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()


# ----------------------------------------------------------------------------- entitlement and quota
def limits(user: str, now: Optional[float] = None) -> Dict[str, Any]:
    """{plan, limit_bytes}. Read only: the flags table is written by an admin script alone (a lapsed plan falls back to free, nothing is deleted)."""
    now = time.time() if now is None else now
    item: Dict[str, Any] = {}
    if os.environ.get("FLAGS_TABLE"):
        item = ddb().Table(os.environ["FLAGS_TABLE"]).get_item(Key={"user_id": check_user(user)}).get("Item") or {}
    until = item.get("storage_until")
    active = until is None or float(until) > now
    plan = "pro" if item.get("storage_plan") == "pro" and active else "free"
    extra = int(item.get("storage_extra_gb") or 0) if active else 0
    base = PRO_BYTES if plan == "pro" else FREE_BYTES
    return {"plan": plan, "limit_bytes": base + max(0, extra) * ADDON_BYTES}


def set_storage(user: str, plan: str = "free", extra_gb: int = 0, until: Optional[int] = None) -> None:
    """Admin only (scripts/wallet_admin.py, needs write access to the flags table, which no Lambda role has). Keeps the other flags of the account."""
    if plan not in ("free", "pro") or extra_gb < 0 or extra_gb > 100_000:
        raise ValueError("plan must be free or pro and extra_gb a small whole number")
    sets, vals = ["storage_plan = :p", "storage_extra_gb = :e"], {":p": plan, ":e": int(extra_gb)}
    if until:
        sets.append("storage_until = :u")
        vals[":u"] = int(until)
    expr = "SET " + ", ".join(sets) + ("" if until else " REMOVE storage_until")
    ddb().Table(os.environ["FLAGS_TABLE"]).update_item(Key={"user_id": check_user(user)}, UpdateExpression=expr, ExpressionAttributeValues=vals)


def stats(user: str) -> Dict[str, int]:
    item = table().get_item(Key={"user_id": check_user(user), "sk": "stats"}).get("Item") or {}
    return {"used": int(item.get("used") or 0), "n": int(item.get("n") or 0)}


def _add_used(user: str, delta: int, n: int = 0) -> None:
    table().update_item(Key={"user_id": user, "sk": "stats"}, UpdateExpression="ADD used :d, n :n", ExpressionAttributeValues={":d": delta, ":n": n})


def reserve(user: str, sizes: List[int], limit: int) -> List[bool]:
    """Reserves the declared sizes in order, each one only if it still fits; no overspend under concurrency (conditional update, retried)."""
    for _ in range(4):
        room = limit - stats(user)["used"]
        ok, total = [], 0
        for s in sizes:
            fits = total + s <= room
            ok.append(fits)
            total += s if fits else 0
        if total == 0:
            return ok
        try:
            table().update_item(Key={"user_id": user, "sk": "stats"}, UpdateExpression="ADD used :t",
                                ConditionExpression="attribute_not_exists(used) OR used <= :mx", ExpressionAttributeValues={":t": total, ":mx": limit - total})
            return ok
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
    return [False] * len(sizes)


def release(user: str, size: int) -> None:
    if size > 0:
        _add_used(user, -int(size))


# ----------------------------------------------------------------------------- places (the coordinates are never stored)
def place_for(lat: Any, lon: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(display place, place key, country) from approximate coordinates, offline. The coordinates go no further than this function."""
    if lat is None or lon is None:
        return None, None, None
    try:
        from engine import geoname

        name = geoname.place_for(float(lat), float(lon))
    except Exception:
        name = None
    if not name:
        return None, None, None
    name = name[:80]
    key = name[5:] if name.startswith("near ") else name
    country = key.rsplit(",", 1)[1].strip() if "," in key else None
    return name, key, country


# ----------------------------------------------------------------------------- uploads
def valid_slot(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise LibraryError(400, "each item must be an object")
    size, sha = raw.get("size"), raw.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_PHOTO_BYTES:
        raise LibraryError(400, f"'size' must be a whole number of bytes from 1 to {MAX_PHOTO_BYTES}")
    if not isinstance(sha, str) or not HASH_RE.match(sha):
        raise LibraryError(400, "'sha256' must be 64 lowercase hex characters")
    out: Dict[str, Any] = {"size": size, "sha256": sha}
    from common.photo_ids import PhotoError, valid_media_meta

    try:
        meta = valid_media_meta({"0" * 16: {k: raw[k] for k in ("taken", "lat", "lon") if raw.get(k) is not None}}, ["0" * 16]).get("0" * 16, {})
    except PhotoError as e:
        raise LibraryError(400, str(e)) from e
    out.update(meta)
    return out


def create_slots(user: str, items: Any, *, consume: Callable[[str], None], now: Optional[str] = None) -> Dict[str, Any]:
    """Quota check, duplicate check, then one presigned POST per photo that fits. `consume(user)` applies the daily cap (raises usage.QuotaExceeded)."""
    check_user(user)
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SLOTS_PER_CALL:
        raise LibraryError(400, f"'items' must be a list of 1 to {MAX_SLOTS_PER_CALL}")
    slots = [valid_slot(i) for i in items]
    lim = limits(user)
    results: List[Optional[Dict[str, Any]]] = [None] * len(slots)
    seen: Dict[str, int] = {}
    todo: List[int] = []
    again: Dict[int, str] = {}   # retries: the photo's slot was granted earlier but its file never arrived: the same photo gets a fresh link (its space is already reserved)
    for i, s in enumerate(slots):   # duplicates: already in the library, or twice in this very batch
        found = table().get_item(Key={"user_id": user, "sk": f"h#{s['sha256']}"}).get("Item")
        if found:
            owner = table().get_item(Key={"user_id": user, "sk": f"m#{found['mid']}"}).get("Item")
            if owner and owner.get("st") == "pending" and int(owner["size_b"]) >= s["size"]:
                again[i], found = found["mid"], None
                seen[s["sha256"]] = i
                continue
            if not owner:   # a claim left behind by a photo that no longer exists
                table().delete_item(Key={"user_id": user, "sk": f"h#{s['sha256']}"})
                found = None
        if found or s["sha256"] in seen:
            results[i] = {"index": i, "status": "duplicate", "duplicate_of": found["mid"]} if found else {"index": i, "status": "duplicate", "_of": seen[s["sha256"]]}
            continue
        seen[s["sha256"]] = i
        todo.append(i)
    for i, mid in again.items():
        results[i] = {"index": i, **_slot(user, mid, int(table().get_item(Key={"user_id": user, "sk": f"m#{mid}"})["Item"]["size_b"]))}
    fits = reserve(user, [slots[i]["size"] for i in todo], lim["limit_bytes"])
    added = now or now_iso()
    for i, ok in zip(todo, fits):
        if not ok:
            results[i] = {"index": i, "status": "no_space"}
            continue
        s = slots[i]
        mid = uuid.uuid4().hex[:16]
        place, pkey, country = place_for(s.get("lat"), s.get("lon"))
        item = {"user_id": user, "sk": f"m#{mid}", "st": "pending", "size_b": s["size"], "hash": s["sha256"], "added": added, "created": added, "pend": "1"}
        for k, v in (("taken", s.get("taken")), ("pl", place), ("plk", pkey), ("cc", country)):
            if v:
                item[k] = v
        try:
            consume(user)
            created = transact([
                {"Put": {"TableName": table().name, "Item": _ser(item), "ConditionExpression": "attribute_not_exists(sk)"}},
                {"Put": {"TableName": table().name, "Item": _ser({"user_id": user, "sk": f"h#{s['sha256']}", "mid": mid}), "ConditionExpression": "attribute_not_exists(sk)"}},
            ])
        except Busy:
            release(user, s["size"])
            raise LibraryError(503, "Busy, please try again.") from None
        except Exception:
            release(user, s["size"])
            raise
        if not created:   # lost a race for the same content: it is a duplicate now
            release(user, s["size"])
            found = table().get_item(Key={"user_id": user, "sk": f"h#{s['sha256']}"}).get("Item")
            results[i] = {"index": i, "status": "duplicate", "duplicate_of": (found or {}).get("mid")}
            continue
        results[i] = {"index": i, **_slot(user, mid, s["size"])}
    for r in results:   # the same content twice in one batch: it points at the first copy, or shares its fate
        if r and "_of" in r:
            first = results[r.pop("_of")]
            if first["status"] == "upload":
                r["duplicate_of"] = first["id"]
            elif first["status"] == "duplicate":
                r["duplicate_of"] = first.get("duplicate_of")
            else:
                r["status"], r["duplicate_of"] = first["status"], None
                del r["duplicate_of"]
    st = stats(user)
    return {"uploads": results, "used_bytes": st["used"], "limit_bytes": lim["limit_bytes"], "expires_in": SLOT_SECONDS}


class Busy(Exception):
    """A transaction kept conflicting with others on the same rows (many photos of one person finishing at once). The caller should try again later."""


def transact(items: List[Dict[str, Any]], tries: int = 7) -> bool:
    """Runs a DynamoDB transaction. True when it was applied, False when a condition in it failed (the thing it expected is not there). Conflicts with other
    transactions on the same rows are retried with a short random backoff and, if they persist, raise Busy: a conflict is never mistaken for a failed condition."""
    for k in range(tries):
        try:
            table().meta.client.transact_write_items(TransactItems=items)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            reasons = [r.get("Code") for r in e.response.get("CancellationReasons") or []]
            if "ConditionalCheckFailed" in reasons:
                return False
            time.sleep(min(0.05 * 2 ** k, 0.8) * (0.5 + random.random()))
    raise Busy()


def _slot(user: str, mid: str, size: int) -> Dict[str, Any]:
    post = s3().generate_presigned_post(
        Bucket=bucket(), Key=orig_key(user, mid), Fields={"Content-Type": "image/jpeg", "x-amz-storage-class": "INTELLIGENT_TIERING"},
        Conditions=[{"Content-Type": "image/jpeg"}, {"x-amz-storage-class": "INTELLIGENT_TIERING"}, ["content-length-range", 1, size]], ExpiresIn=SLOT_SECONDS)
    return {"status": "upload", "id": mid, "url": post["url"], "fields": post["fields"]}


def _ser(item: Dict[str, Any]) -> Dict[str, Any]:
    """The resource's own client converts plain Python values for transactions too (sets become string sets), so this only documents the call sites."""
    return item


# ----------------------------------------------------------------------------- facets (counts per year, country and place, for chips and search vocabulary)
def _facet_names(item: Dict[str, Any]) -> List[str]:
    names = []
    base = item.get("taken") or item.get("added") or ""
    if base[:4].isdigit():
        names.append(f"y:{base[:4]}")
    if item.get("cc"):
        names.append(f"c:{item['cc']}")
    if item.get("plk"):
        names.append(f"p:{item['plk']}")
    return names


def _facet_update(names: List[str], delta: int) -> Dict[str, Any]:
    ph = {f"#f{i}": n for i, n in enumerate(names)}
    expr = "ADD " + ", ".join(f"#f{i} :d" for i in range(len(names)))
    return {"UpdateExpression": expr, "ExpressionAttributeNames": ph, "ExpressionAttributeValues": {":d": delta}}


def facets(user: str) -> Dict[str, Dict[str, int]]:
    item = table().get_item(Key={"user_id": check_user(user), "sk": "facets"}).get("Item") or {}
    out: Dict[str, Dict[str, int]] = {"y": {}, "c": {}, "p": {}}
    for k, v in item.items():
        if len(k) > 2 and k[1] == ":" and k[0] in out and int(v) > 0:
            out[k[0]][k[2:]] = int(v)
    return out


def sort_key(item: Dict[str, Any], mid: str) -> str:
    return f"{(item.get('taken') or item.get('added'))[:19]}#{mid}"


def finalize(user: str, mid: str, *, actual_bytes: int, w: int, h: int) -> bool:
    """pending -> ready, in one transaction with the counters. False when it was not pending any more (a repeated event)."""
    item = table().get_item(Key={"user_id": user, "sk": f"m#{mid}"}).get("Item")
    if not item or item.get("st") != "pending":
        return False
    srt = sort_key(item, mid)
    declared = int(item["size_b"])
    names = _facet_names(item)
    tx: List[Dict[str, Any]] = [
        {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"m#{mid}"}), "ConditionExpression": "st = :p",
                    "UpdateExpression": "SET st = :r, size_b = :b, w = :w, h = :h, srt = :s REMOVE pend",
                    "ExpressionAttributeValues": _ser({":p": "pending", ":r": "ready", ":b": actual_bytes, ":w": w, ":h": h, ":s": srt})}},
        {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": "stats"}), "UpdateExpression": "ADD used :d, n :one",
                    "ExpressionAttributeValues": _ser({":d": actual_bytes - declared, ":one": 1})}},
    ]
    if names:
        f = _facet_update(names, 1)
        tx.append({"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": "facets"}), "UpdateExpression": f["UpdateExpression"],
                              "ExpressionAttributeNames": f["ExpressionAttributeNames"], "ExpressionAttributeValues": _ser(f["ExpressionAttributeValues"])}})
    return transact(tx)   # False: it was not pending any more (a repeated event); Busy: other photos of this person are finishing at the same moment, try again


def reject(user: str, mid: str) -> None:
    """A pending photo that cannot become ready (bad file, nothing arrived): remove it and give the reserved bytes back."""
    item = table().get_item(Key={"user_id": user, "sk": f"m#{mid}"}).get("Item")
    if not item or item.get("st") != "pending":
        return
    for k in (orig_key(user, mid), thumb_key(user, mid)):
        try:
            s3().delete_object(Bucket=bucket(), Key=k)
        except ClientError:
            pass
    h = item.get("hash")
    if h:
        try:
            table().delete_item(Key={"user_id": user, "sk": f"h#{h}"}, ConditionExpression="mid = :m", ExpressionAttributeValues={":m": mid})
        except ClientError:
            pass
    table().delete_item(Key={"user_id": user, "sk": f"m#{mid}"})
    release(user, int(item["size_b"]))


# ----------------------------------------------------------------------------- reading
def get_item(user: str, mid: str, *, ready_only: bool = True) -> Optional[Dict[str, Any]]:
    it = table().get_item(Key={"user_id": check_user(user), "sk": f"m#{check_id(mid)}"}).get("Item")
    if not it or (ready_only and it.get("st") != "ready"):
        return None
    return it


def batch_get(user: str, ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Ready photos of THIS user among the ids (anything else is simply absent)."""
    check_user(user)
    keys = [{"user_id": user, "sk": f"m#{check_id(i)}"} for i in dict.fromkeys(ids)]
    out: Dict[str, Dict[str, Any]] = {}
    for n in range(0, len(keys), 100):
        req = {table().name: {"Keys": keys[n:n + 100]}}
        for _ in range(5):
            res = ddb().batch_get_item(RequestItems=req)
            for it in res["Responses"].get(table().name, []):
                if it.get("st") == "ready":
                    out[it["sk"][2:]] = it
            req = res.get("UnprocessedKeys") or {}
            if not req:
                break
    return out


def link(key: str, seconds: int) -> str:
    return s3().generate_presigned_url("get_object", Params={"Bucket": bucket(), "Key": key, "ResponseContentType": "image/jpeg"}, ExpiresIn=seconds)


def photo_json(user: str, it: Dict[str, Any], *, full: bool = False) -> Dict[str, Any]:
    mid = it["sk"][2:]
    out: Dict[str, Any] = {"id": mid, "added": (it.get("added") or "") + "Z" if it.get("added") else None, "w": int(it.get("w") or 0), "h": int(it.get("h") or 0), "bytes": int(it.get("size_b") or 0),
                           "thumb_url": link(thumb_key(user, mid), THUMB_LINK_SECONDS), "collections": sorted(it.get("cols") or [])}
    if it.get("taken"):
        out["taken"] = it["taken"]
    if it.get("pl"):
        out["place"] = it["pl"]
    if full:
        out["url"] = link(orig_key(user, mid), PHOTO_LINK_SECONDS)
    return out


def encode_cursor(**kw: str) -> str:
    return base64.urlsafe_b64encode(json.dumps(kw, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cur: Any) -> Dict[str, str]:
    if cur in (None, ""):
        return {}
    try:
        data = json.loads(base64.urlsafe_b64decode(str(cur) + "=" * (-len(str(cur)) % 4)))
        if not isinstance(data, dict) or not all(isinstance(v, str) and len(v) < 200 for v in data.values()):
            raise ValueError
        return data
    except Exception:
        raise LibraryError(400, "invalid cursor") from None


def day_bounds(date_from: Optional[str], date_to: Optional[str]) -> Tuple[str, str]:
    for d in (date_from, date_to):
        if d is not None and not (isinstance(d, str) and DAY_RE.match(d)):
            raise LibraryError(400, "dates must look like 2024-07-31")
    return (date_from or "0000-01-01") , ((date_to + "~") if date_to else "9999-12-31~")


def list_items(user: str, *, limit: int = 60, cursor: Any = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
               countries: Iterable[str] = (), places: Iterable[str] = ()) -> Dict[str, Any]:
    """Newest first from the Timeline index, with optional date range and place filters. Returns {"items": [raw rows], "cursor": str|None}."""
    check_user(user)
    limit = max(1, min(int(limit), 100))
    lo, hi = day_bounds(date_from, date_to)
    countries, places = list(countries), list(places)
    cur = decode_cursor(cursor)
    start = None
    if cur:
        if not (SRT_RE.match(cur.get("s", "")) and re.match(r"^m#[0-9a-f]{16}$", cur.get("k", ""))):
            raise LibraryError(400, "invalid cursor")
        start = {"user_id": user, "sk": cur["k"], "srt": cur["s"]}   # the partition key comes from the caller, never from the cursor
    filt = None
    if countries or places:
        parts = []
        if countries:
            parts.append(Attr("cc").is_in(countries))
        if places:
            parts.append(Attr("plk").is_in(places))
        filt = parts[0] if len(parts) == 1 else parts[0] | parts[1]
    rows: List[Dict[str, Any]] = []
    more = False
    for _ in range(15):
        kw: Dict[str, Any] = {"IndexName": "Timeline", "KeyConditionExpression": Key("user_id").eq(user) & Key("srt").between(lo, hi), "ScanIndexForward": False,
                              "Limit": limit if filt is None else 100}
        if filt is not None:
            kw["FilterExpression"] = filt
        if start:
            kw["ExclusiveStartKey"] = start
        res = table().query(**kw)
        rows += res.get("Items", [])
        start = res.get("LastEvaluatedKey")
        if len(rows) >= limit or not start:
            more = bool(start) or len(rows) > limit
            break
    rows = rows[:limit]
    nxt = encode_cursor(s=rows[-1]["srt"], k=rows[-1]["sk"]) if rows and more else None
    return {"items": rows, "cursor": nxt}


# ----------------------------------------------------------------------------- collections
def _name(raw: Any) -> str:
    name = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not 1 <= len(name) <= 40 or any(ord(c) < 32 for c in name):
        raise LibraryError(400, "the name must be 1 to 40 characters")
    return name


def _emoji(raw: Any) -> Optional[str]:
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or len(raw) > 8 or any(ord(c) < 32 for c in raw):
        raise LibraryError(400, "invalid emoji")
    return raw


def collection_json(c: Dict[str, Any]) -> Dict[str, Any]:
    out = {"id": c["sk"][2:], "name": c["nm"], "count": int(c.get("n") or 0)}
    if c.get("em"):
        out["emoji"] = c["em"]
    if c.get("auto"):
        out["auto"] = True   # made by "organize": matched by place and dates, never by name
    if c.get("cover"):
        out["cover_id"] = c["cover"]
        out["cover_thumb_url"] = link(thumb_key(c["user_id"], c["cover"]), THUMB_LINK_SECONDS)   # the row's own partition: the cover is always this user's photo
    return out


def collections(user: str) -> List[Dict[str, Any]]:
    res = table().query(KeyConditionExpression=Key("user_id").eq(check_user(user)) & Key("sk").begins_with("c#"))
    return sorted((collection_json(c) for c in res.get("Items", [])), key=lambda c: c["name"].lower())


def create_collection(user: str, name: Any, emoji: Any = None, auto: Optional[Dict[str, Any]] = None, *, count_hint: Optional[int] = None) -> Dict[str, Any]:
    """`auto` marks a collection made by the organiser: {"k": "m"|"t", "pk": place key or "", "ym": "YYYY-MM"} (a month) or {"k": "t", "pk": ..., "from": day, "to": day} (a trip)."""
    check_user(user)
    if (count_hint if count_hint is not None else len(collections(user))) >= MAX_COLLECTIONS:
        raise LibraryError(409, "too many collections")
    cid = uuid.uuid4().hex[:16]
    item = {"user_id": user, "sk": f"c#{cid}", "nm": _name(name), "n": 0, "created": now_iso()}
    if _emoji(emoji):
        item["em"] = emoji
    if auto:
        item["auto"] = auto
    table().put_item(Item=item)
    return collection_json(item)


def _collection(user: str, cid: str) -> Dict[str, Any]:
    c = table().get_item(Key={"user_id": check_user(user), "sk": f"c#{check_id(cid)}"}).get("Item")
    if not c:
        raise LibraryError(404, "not found")
    return c


def update_collection(user: str, cid: str, name: Any = None, emoji: Any = "__keep__") -> Dict[str, Any]:
    c = _collection(user, cid)
    sets, vals, names = [], {}, {}
    if name is not None:
        sets.append("nm = :n, ren = :r")   # a name the person chose is never rewritten by the automatic organiser
        vals[":n"] = _name(name)
        vals[":r"] = True
    if emoji != "__keep__":
        e = _emoji(emoji)
        sets.append("em = :e" if e else "REMOVE_EM")
        if e:
            vals[":e"] = e
    expr_set = [s for s in sets if s != "REMOVE_EM"]
    expr = ("SET " + ", ".join(expr_set) if expr_set else "") + (" REMOVE em" if "REMOVE_EM" in sets else "")
    if expr:
        kw: Dict[str, Any] = {"Key": {"user_id": user, "sk": c["sk"]}, "UpdateExpression": expr}
        if vals:
            kw["ExpressionAttributeValues"] = vals
        table().update_item(**kw)
    return collection_json(_collection(user, cid))


def collection_items(user: str, cid: str, limit: int = 60, cursor: Any = None) -> Dict[str, Any]:
    _collection(user, cid)
    limit = max(1, min(int(limit), 100))
    prefix = f"cm#{cid}#"
    cur = decode_cursor(cursor)
    kw: Dict[str, Any] = {"KeyConditionExpression": Key("user_id").eq(user) & Key("sk").begins_with(prefix), "ScanIndexForward": False, "Limit": limit}
    if cur:
        if not cur.get("k", "").startswith(prefix) or not SRT_RE.match(cur["k"][len(prefix):]):
            raise LibraryError(400, "invalid cursor")
        kw["ExclusiveStartKey"] = {"user_id": user, "sk": cur["k"]}
    res = table().query(**kw)
    rows = res.get("Items", [])
    got = batch_get(user, [r["mid"] for r in rows])
    items = [got[r["mid"]] for r in rows if r["mid"] in got]
    return {"items": items, "cursor": encode_cursor(k=rows[-1]["sk"]) if rows and res.get("LastEvaluatedKey") else None}


def change_collection(user: str, cid: str, add: Iterable[str] = (), remove: Iterable[str] = ()) -> Dict[str, Any]:
    c = _collection(user, cid)
    add, remove = list(dict.fromkeys(add)), list(dict.fromkeys(remove))
    if len(add) > MAX_IDS or len(remove) > MAX_IDS:
        raise LibraryError(400, f"at most {MAX_IDS} ids at a time")
    have = batch_get(user, add + remove)
    added = removed = 0
    for mid in add:
        it = have.get(mid)
        if not it or len(it.get("cols") or []) >= MAX_PER_PHOTO_COLLECTIONS:
            continue
        srt = it.get("srt") or sort_key(it, mid)
        try:
            if transact([
                {"Put": {"TableName": table().name, "Item": _ser({"user_id": user, "sk": f"cm#{cid}#{srt}", "mid": mid}), "ConditionExpression": "attribute_not_exists(sk)"}},
                {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"m#{mid}"}), "UpdateExpression": "ADD cols :c", "ExpressionAttributeValues": {":c": {cid}}}},
                {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"c#{cid}"}), "UpdateExpression": "ADD n :one SET cover = :m", "ExpressionAttributeValues": _ser({":one": 1, ":m": mid})}},
            ]):
                added += 1
        except Busy:
            raise LibraryError(503, "Busy, please try again.") from None
    for mid in remove:
        it = have.get(mid)
        if not it or cid not in (it.get("cols") or []):
            continue
        srt = it.get("srt") or sort_key(it, mid)
        try:
            transact([
                {"Delete": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"cm#{cid}#{srt}"})}},
                {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"m#{mid}"}), "UpdateExpression": "DELETE cols :c", "ExpressionAttributeValues": {":c": {cid}}}},
                {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"c#{cid}"}), "UpdateExpression": "ADD n :neg", "ExpressionAttributeValues": _ser({":neg": -1})}},
            ])
        except Busy:
            raise LibraryError(503, "Busy, please try again.") from None
        removed += 1
    if removed and c.get("cover") in remove:
        table().update_item(Key={"user_id": user, "sk": f"c#{cid}"}, UpdateExpression="REMOVE cover")
    return {"added": added, "removed": removed, "collection": collection_json(_collection(user, cid))}


def delete_collection(user: str, cid: str) -> None:
    _collection(user, cid)
    prefix = f"cm#{cid}#"
    res = table().query(KeyConditionExpression=Key("user_id").eq(user) & Key("sk").begins_with(prefix))
    while True:
        for r in res.get("Items", []):
            try:
                table().update_item(Key={"user_id": user, "sk": f"m#{r['mid']}"}, UpdateExpression="DELETE cols :c", ExpressionAttributeValues={":c": {cid}},
                                    ConditionExpression="attribute_exists(sk)")
            except ClientError:
                pass
            table().delete_item(Key={"user_id": user, "sk": r["sk"]})
        if not res.get("LastEvaluatedKey"):
            break
        res = table().query(KeyConditionExpression=Key("user_id").eq(user) & Key("sk").begins_with(prefix), ExclusiveStartKey=res["LastEvaluatedKey"])
    table().delete_item(Key={"user_id": user, "sk": f"c#{cid}"})


# ----------------------------------------------------------------------------- delete
def _delete_vectors(user: str, mids: List[str]) -> None:
    keys = [vec_key(user, m) for m in mids]
    for n in range(0, len(keys), 500):
        try:
            vectors().delete_vectors(**vector_target(), keys=keys[n:n + 500])
        except ClientError as e:
            logger.warning("vector delete failed: %s", e.response["Error"]["Code"])


def delete_items(user: str, ids: Any) -> Dict[str, int]:
    """Files and vectors first, then the rows: if a step fails the photo is still listed and can be deleted again, never an orphan file."""
    check_user(user)
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_IDS:
        raise LibraryError(400, f"'ids' must be a list of 1 to {MAX_IDS}")
    ids = [check_id(i) for i in dict.fromkeys(ids)]
    rows = {}
    for mid in ids:
        it = get_item(user, mid, ready_only=False)
        if it:
            rows[mid] = it
    if not rows:
        return {"deleted": 0, "used_bytes": stats(user)["used"]}
    s3().delete_objects(Bucket=bucket(), Delete={"Objects": [{"Key": k} for m in rows for k in (orig_key(user, m), thumb_key(user, m))], "Quiet": True})
    _delete_vectors(user, [m for m, it in rows.items() if it.get("st") == "ready"])
    for mid, it in rows.items():
        for cid in it.get("cols") or []:
            try:
                transact([
                    {"Delete": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"cm#{cid}#{it.get('srt') or sort_key(it, mid)}"})}},
                    {"Update": {"TableName": table().name, "Key": _ser({"user_id": user, "sk": f"c#{cid}"}), "UpdateExpression": "ADD n :neg", "ExpressionAttributeValues": _ser({":neg": -1}),
                                "ConditionExpression": "attribute_exists(sk)"}},
                ])
            except Busy:
                raise LibraryError(503, "Busy, please try again.") from None
        if it.get("hash"):
            try:
                table().delete_item(Key={"user_id": user, "sk": f"h#{it['hash']}"}, ConditionExpression="mid = :m", ExpressionAttributeValues={":m": mid})
            except ClientError:
                pass
        table().delete_item(Key={"user_id": user, "sk": f"m#{mid}"})
        if it.get("st") == "ready":
            _add_used(user, -int(it.get("size_b") or 0), -1)
            names = _facet_names(it)
            if names:
                table().update_item(Key={"user_id": user, "sk": "facets"}, **_facet_update(names, -1))
        else:
            release(user, int(it.get("size_b") or 0))
    return {"deleted": len(rows), "used_bytes": stats(user)["used"]}


def purge_user(user: str) -> Dict[str, int]:
    """Everything of one account: files, vectors, rows. For 'delete all my media' and for account deletion."""
    check_user(user)
    n_obj = 0
    for prefix in (f"o/{user}/", f"t/{user}/"):
        token = None
        while True:
            res = s3().list_objects_v2(Bucket=bucket(), Prefix=prefix, **({"ContinuationToken": token} if token else {}))
            objs = [{"Key": o["Key"]} for o in res.get("Contents", [])]
            if objs:
                s3().delete_objects(Bucket=bucket(), Delete={"Objects": objs, "Quiet": True})
                n_obj += len(objs)
            token = res.get("NextContinuationToken")
            if not token:
                break
    rows, mids, last = [], [], None
    while True:
        res = table().query(KeyConditionExpression=Key("user_id").eq(user), **({"ExclusiveStartKey": last} if last else {}))
        for r in res.get("Items", []):
            rows.append(r["sk"])
            if r["sk"].startswith("m#"):
                mids.append(r["sk"][2:])
        last = res.get("LastEvaluatedKey")
        if not last:
            break
    _delete_vectors(user, mids)
    with table().batch_writer() as bw:
        for sk in rows:
            bw.delete_item(Key={"user_id": user, "sk": sk})
    return {"objects": n_obj, "photos": len(mids), "rows": len(rows)}


ORGANIZE_CHOICES = ("ask", "always", "never")


def prefs(user: str) -> Dict[str, Any]:
    item = table().get_item(Key={"user_id": check_user(user), "sk": "prefs"}).get("Item") or {}
    return {"organize": item.get("organize") if item.get("organize") in ORGANIZE_CHOICES else "ask"}


def set_prefs(user: str, organize: Any) -> Dict[str, Any]:
    if organize not in ORGANIZE_CHOICES:
        raise LibraryError(400, "'organize' must be ask, always or never")
    table().put_item(Item={"user_id": check_user(user), "sk": "prefs", "organize": organize})
    return prefs(user)


def summary(user: str) -> Dict[str, Any]:
    lim, st, fa = limits(user), stats(user), facets(user)
    places = sorted(({"name": n, "country": n.rsplit(",", 1)[1].strip() if "," in n else n, "count": c} for n, c in fa["p"].items()), key=lambda p: -p["count"])[:30]
    return {"plan": lim["plan"], "limit_bytes": lim["limit_bytes"], "used_bytes": st["used"], "read_only": st["used"] > lim["limit_bytes"], "count": st["n"], "can_upgrade": os.environ.get("LIBRARY_CAN_UPGRADE") == "1",
            "years": [{"year": int(y), "count": c} for y, c in sorted(fa["y"].items(), reverse=True)], "places": places,
            "countries": [{"name": n, "count": c} for n, c in sorted(fa["c"].items(), key=lambda kv: -kv[1])[:30]], "collections": collections(user), "prefs": prefs(user)}
