"""Where VideoMK's own clip library and the on-demand ledger live (docs/CLIPS_ON_DEMAND.md section 8). No resource of its own:

  objects  the assets bucket under `cliplib/`:  v/<id>.mp4 the clip, p/<id>.jpg its poster, m/<id>.json all metadata and both vectors (the source of truth)
  rows     the usage table (partition `user_id`, sort `day`) under partitions that start with `clipgen:` (the free-plan budget rows live in that table the same way)

Two stores with the same few operations: `AwsStore` (a stage) and `LocalStore` (a folder: tests, a laptop, and a source or target of `clips_admin.py promote`).
`reserve()` is the one operation money depends on: several counters move together or not at all, each only while it stays within its limit.
"""
import base64
import fcntl
import json
import os
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

PREFIX = "cliplib/"
P = "clipgen:"                    # every partition of this feature in the usage table
LIB = P + "lib"                   # sort = clip id: the search index (brief, tags, shape, vectors, uses)
DEMAND = P + "demand"             # sort = brief key: who asked for which general scene
LOCK = P + "lock"                 # sort = brief key: a generation of this scene is in flight
STATS = P + "stats"               # sort = UTC day: counters of decisions and outcomes (what the report reads without CloudWatch)
ACCT = P + "acct:"                # + user id; sort = YYYY-MM: the account's clip spend of the month (removed with the account: common/deletion.USAGE_PREFIXES)
TAKEDOWN = P + "takedown"         # sort = "<media>:<id>": every asset taken out of the library, when and why (common/takedown.py)
VIDEO = P + "video:"              # + video id; sort = "n" (generations of the video) or "beat:<id>" (the claim that stops a retried beat paying twice)
STAGES = {"qa": {"profile": "qa", "region": "eu-west-1", "account": "552357225438"}, "prod": {"profile": "default", "region": "us-west-2", "account": "464863885161"}}


def spend_pk(kind: str, span: str, media: str = "clip") -> str:
    """kind: 'paid' | 'test'; span: 'day' | 'month'; media: 'clip' | 'image' | 'object' (each type has its own budgets). Sort key = the UTC day or month."""
    return f"{P}spend:{kind}:{span}" + ("" if media == "clip" else f":{media}")


def ledger_pk(month: str) -> str:
    return f"{P}ledger:{month}"


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return sorted(_plain(x) for x in v)
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _dec(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return Decimal(str(round(v, 6)))
    if isinstance(v, dict):
        return {k: _dec(x) for k, x in v.items() if x is not None}
    if isinstance(v, (list, tuple)):
        return [_dec(x) for x in v]
    return v


def line(pk: str, sk: str, add: int, limit: int, *, field: str = "spent", extra: Optional[Dict[str, int]] = None, ttl: Optional[int] = None) -> Dict[str, Any]:
    """One counter of a reservation: `field` grows by `add` only while field + add <= limit. `extra` counters grow with it (no limit)."""
    return {"pk": pk, "sk": sk, "field": field, "add": int(add), "limit": int(limit), "extra": dict(extra or {}), "ttl": ttl}


class Store:
    label = ""

    # ---- rows
    def get(self, pk: str, sk: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def query(self, pk: str) -> List[Dict[str, Any]]: raise NotImplementedError
    def put(self, pk: str, sk: str, item: Dict[str, Any], *, only_if_absent: bool = False, or_expired: Optional[int] = None) -> bool: raise NotImplementedError
    def add(self, pk: str, sk: str, counters: Optional[Dict[str, int]] = None, *, sets: Optional[Dict[str, List[str]]] = None, fields: Optional[Dict[str, Any]] = None) -> None: raise NotImplementedError
    def delete(self, pk: str, sk: str) -> None: raise NotImplementedError
    def reserve(self, lines: List[Dict[str, Any]]) -> Optional[int]: raise NotImplementedError
    def release(self, lines: List[Dict[str, Any]]) -> None:
        for ln in lines:
            self.add(ln["pk"], ln["sk"], {ln["field"]: -ln["add"], **{k: -v for k, v in ln["extra"].items()}})

    # ---- objects (keys are relative to the library: 'v/<id>.mp4')
    def put_object(self, key: str, data: bytes, content_type: str) -> None: raise NotImplementedError
    def get_object(self, key: str) -> bytes: raise NotImplementedError
    def has_object(self, key: str) -> bool: raise NotImplementedError
    def list_objects(self, prefix: str) -> List[str]: raise NotImplementedError
    def delete_object(self, key: str) -> None: raise NotImplementedError   # only the takedown uses it (common/takedown.py), after the copy to quarantine/


def _check_key(key: str) -> str:
    if not isinstance(key, str) or ".." in key or key.startswith("/") or not (key[:2] in ("v/", "p/", "m/") or key[:4] in ("q/v/", "q/p/")):   # q/ = quarantine (common/takedown.py)
        raise ValueError("bad library key")
    return key


class LocalStore(Store):
    """A folder: `objects/` and `rows.json`. Safe across threads and processes (one lock file); meant for tests, a laptop and promotion, not for load."""

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        self.label = f"local:{self.path}"
        os.makedirs(os.path.join(self.path, "objects"), exist_ok=True)
        self._lock = threading.RLock()

    class _Guard:
        def __init__(self, store: "LocalStore") -> None:
            self.s = store

        def __enter__(self) -> Dict[str, Any]:
            self.s._lock.acquire()
            self.fh = open(os.path.join(self.s.path, ".lock"), "a+")
            fcntl.flock(self.fh, fcntl.LOCK_EX)
            p = os.path.join(self.s.path, "rows.json")
            self.rows = json.load(open(p)) if os.path.exists(p) else {}
            return self.rows

        def __exit__(self, et, ev, tb) -> None:
            try:
                if et is None:
                    tmp = os.path.join(self.s.path, "rows.json.tmp")
                    with open(tmp, "w") as fh:
                        json.dump(self.rows, fh, ensure_ascii=False, sort_keys=True)
                    os.replace(tmp, os.path.join(self.s.path, "rows.json"))
            finally:
                fcntl.flock(self.fh, fcntl.LOCK_UN)
                self.fh.close()
                self.s._lock.release()

    @staticmethod
    def _k(pk: str, sk: str) -> str:
        return f"{pk}\x1f{sk}"

    def get(self, pk, sk):
        with self._Guard(self) as rows:
            r = rows.get(self._k(pk, sk))
            return dict(r) if r else None

    def query(self, pk):
        with self._Guard(self) as rows:
            return [dict(r) for k, r in sorted(rows.items()) if k.startswith(pk + "\x1f")]

    def put(self, pk, sk, item, *, only_if_absent=False, or_expired=None):
        with self._Guard(self) as rows:
            old = rows.get(self._k(pk, sk))
            if only_if_absent and old is not None and not (or_expired is not None and int(old.get("expires") or 0) < or_expired):
                return False
            rows[self._k(pk, sk)] = {**json.loads(json.dumps(_plain(item))), "pk": pk, "sk": sk}
            return True

    def add(self, pk, sk, counters=None, *, sets=None, fields=None):
        with self._Guard(self) as rows:
            r = rows.setdefault(self._k(pk, sk), {"pk": pk, "sk": sk})
            for f, n in (counters or {}).items():
                r[f] = (r.get(f) or 0) + n
            for f, vals in (sets or {}).items():
                r[f] = sorted(set(r.get(f) or []) | set(vals))
            r.update(json.loads(json.dumps(_plain(fields or {}))))

    def delete(self, pk, sk):
        with self._Guard(self) as rows:
            rows.pop(self._k(pk, sk), None)

    def reserve(self, lines):
        with self._Guard(self) as rows:
            for i, ln in enumerate(lines):
                if int((rows.get(self._k(ln["pk"], ln["sk"])) or {}).get(ln["field"]) or 0) + ln["add"] > ln["limit"]:
                    return i
            for ln in lines:
                r = rows.setdefault(self._k(ln["pk"], ln["sk"]), {"pk": ln["pk"], "sk": ln["sk"]})
                for f, n in {ln["field"]: ln["add"], **ln["extra"]}.items():
                    r[f] = (r.get(f) or 0) + n
                if ln.get("ttl"):
                    r["ttl"] = ln["ttl"]
            return None

    def _obj(self, key: str) -> str:
        return os.path.join(self.path, "objects", _check_key(key))

    def put_object(self, key, data, content_type):
        p = self._obj(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)

    def get_object(self, key):
        with open(self._obj(key), "rb") as fh:
            return fh.read()

    def has_object(self, key):
        return os.path.isfile(self._obj(key))

    def list_objects(self, prefix):
        d = os.path.join(self.path, "objects", prefix.rstrip("/"))
        return sorted(f"{prefix.rstrip('/')}/{n}" for n in (os.listdir(d) if os.path.isdir(d) else []) if not n.endswith(".tmp"))

    def delete_object(self, key):
        if os.path.isfile(self._obj(key)):
            os.remove(self._obj(key))


class AwsStore(Store):
    def __init__(self, table_name: str, bucket: str, *, session: Any = None, label: str = "aws") -> None:
        import boto3

        sess = session or boto3
        self.table_name, self.bucket, self.label = table_name, bucket, label
        self.tbl = sess.resource("dynamodb").Table(table_name)
        self.s3 = sess.client("s3")

    def _key(self, pk: str, sk: str) -> Dict[str, str]:
        return {"user_id": pk, "day": sk}

    @staticmethod
    def _row(item: Dict[str, Any]) -> Dict[str, Any]:
        r = _plain(item)
        r["pk"], r["sk"] = r.pop("user_id"), r.pop("day")
        return r

    def get(self, pk, sk):
        it = self.tbl.get_item(Key=self._key(pk, sk), ConsistentRead=True).get("Item")
        return self._row(it) if it else None

    def query(self, pk):
        from boto3.dynamodb.conditions import Key

        out, kw = [], {}
        while True:
            r = self.tbl.query(KeyConditionExpression=Key("user_id").eq(pk), **kw)
            out += [self._row(i) for i in r.get("Items", [])]
            if not r.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def put(self, pk, sk, item, *, only_if_absent=False, or_expired=None):
        from botocore.exceptions import ClientError

        kw: Dict[str, Any] = {"Item": {**_dec(item), **self._key(pk, sk)}}
        if only_if_absent:
            kw["ConditionExpression"] = "attribute_not_exists(user_id)" + (" OR expires < :now" if or_expired is not None else "")
            if or_expired is not None:
                kw["ExpressionAttributeValues"] = {":now": int(or_expired)}
        try:
            self.tbl.put_item(**kw)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def add(self, pk, sk, counters=None, *, sets=None, fields=None):
        names, vals, adds, sets_ = {}, {}, [], []
        for i, (f, n) in enumerate((counters or {}).items()):
            names[f"#c{i}"], vals[f":c{i}"] = f, int(n)
            adds.append(f"#c{i} :c{i}")
        for i, (f, v) in enumerate((sets or {}).items()):
            if v:
                names[f"#s{i}"], vals[f":s{i}"] = f, set(v)
                adds.append(f"#s{i} :s{i}")
        for i, (f, v) in enumerate((fields or {}).items()):
            names[f"#f{i}"], vals[f":f{i}"] = f, _dec(v)
            sets_.append(f"#f{i} = :f{i}")
        if not adds and not sets_:
            return
        self.tbl.update_item(Key=self._key(pk, sk), UpdateExpression=" ".join(x for x in (("ADD " + ", ".join(adds)) if adds else "", ("SET " + ", ".join(sets_)) if sets_ else "") if x),
                             ExpressionAttributeNames=names, ExpressionAttributeValues=vals)

    def delete(self, pk, sk):
        self.tbl.delete_item(Key=self._key(pk, sk))

    def reserve(self, lines):
        """All counters move in ONE transaction, each on the condition that it stays within its limit. -> None when reserved, else the index of the first counter that
        refused (-1: the transaction could not be made, treated as refused). Two requests racing for the last dollar: exactly one gets it."""
        from botocore.exceptions import ClientError

        for i, ln in enumerate(lines):
            if ln["add"] > ln["limit"]:
                return i
        items = []
        for ln in lines:
            names, vals, expr = {"#f": ln["field"]}, {":a": ln["add"], ":room": ln["limit"] - ln["add"]}, "ADD #f :a"
            for j, (f, n) in enumerate(ln["extra"].items()):
                names[f"#e{j}"], vals[f":e{j}"] = f, int(n)
                expr += f", #e{j} :e{j}"
            if ln.get("ttl"):
                names["#t"], vals[":t"] = "ttl", int(ln["ttl"])
                expr += " SET #t = :t"
            items.append({"Update": {"TableName": self.table_name, "Key": self._key(ln["pk"], ln["sk"]), "UpdateExpression": expr,
                                     "ConditionExpression": "attribute_not_exists(#f) OR #f <= :room", "ExpressionAttributeNames": names, "ExpressionAttributeValues": vals}})
        for attempt in range(5):
            try:
                self.tbl.meta.client.transact_write_items(TransactItems=items)
                return None
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                    raise
                for i, r in enumerate(e.response.get("CancellationReasons") or []):
                    if r.get("Code") == "ConditionalCheckFailed":
                        return i
                time.sleep(0.05 * (attempt + 1))   # a conflict with a concurrent transaction on the same counters: try again
        return -1

    def put_object(self, key, data, content_type):
        self.s3.put_object(Bucket=self.bucket, Key=PREFIX + _check_key(key), Body=data, ContentType=content_type)

    def get_object(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=PREFIX + _check_key(key))["Body"].read()

    def has_object(self, key):
        from botocore.exceptions import ClientError
        try:
            self.s3.head_object(Bucket=self.bucket, Key=PREFIX + _check_key(key))
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "403", "NoSuchKey", "NotFound"):   # 403: a missing key without the right to list
                return False
            raise

    def delete_object(self, key):
        self.s3.delete_object(Bucket=self.bucket, Key=PREFIX + _check_key(key))   # the assets bucket is NOT versioned (checked on QA, 2026-11-27): the takedown copies to q/ first, and that copy is the one that stays

    def list_objects(self, prefix):
        out, kw = [], {}
        while True:
            r = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=PREFIX + prefix, **kw)
            out += [o["Key"][len(PREFIX):] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return sorted(out)
            kw["ContinuationToken"] = r["NextContinuationToken"]


# ----------------------------------------------------------------------------- which store
_current: Optional[Store] = None
_explicit = False


def set_store(store: Optional[Store]) -> None:
    """Tests and scripts."""
    global _current, _explicit
    _current, _explicit = store, store is not None


def current() -> Optional[Store]:
    """The runtime's store: a folder when CLIPS_LIB_DIR is set (a laptop), else the stage's bucket and usage table when the deploy flag is on, else None (the feature is absent)."""
    global _current
    if _explicit or _current is not None:
        return _current
    if os.environ.get("CLIPS_LIB_DIR"):
        _current = LocalStore(os.environ["CLIPS_LIB_DIR"])
    elif os.environ.get("CLIPS_ON_DEMAND") == "1" and os.environ.get("USAGE_TABLE") and os.environ.get("ASSETS_BUCKET"):
        _current = AwsStore(os.environ["USAGE_TABLE"], os.environ["ASSETS_BUCKET"])
    return _current


def open_store(spec: str) -> Store:
    """Scripts: 'qa', 'prod' (the stage's usage table and assets bucket, found from the stack) or 'local:<folder>'."""
    if spec.startswith("local:"):
        return LocalStore(spec[6:])
    if spec not in STAGES:
        raise ValueError(f"unknown store {spec!r} (qa, prod or local:<folder>)")
    import boto3

    cfg = STAGES[spec]
    sess = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    if sess.client("sts").get_caller_identity()["Account"] != cfg["account"]:
        raise SystemExit(f"profile {cfg['profile']} is not account {cfg['account']}")
    table = ""
    for page in sess.client("cloudformation").get_paginator("list_stack_resources").paginate(StackName=f"videomk-{spec}"):
        for r in page["StackResourceSummaries"]:
            if r["ResourceType"] == "AWS::DynamoDB::Table" and r["LogicalResourceId"].startswith("UsageTable"):
                table = r["PhysicalResourceId"]
    if not table:
        raise SystemExit("usage table not found in the stack")
    return AwsStore(table, f"videomk-{spec}-{cfg['account']}", session=sess, label=spec)


# ----------------------------------------------------------------------------- small shared helpers
def month(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m", time.gmtime(now))


def day(now: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


def micro(usd: float) -> int:
    return int(round(float(usd) * 1_000_000))


def usd(micro_usd: Any) -> float:
    return round(int(micro_usd or 0) / 1_000_000, 6)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))
