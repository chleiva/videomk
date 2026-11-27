"""Where a catalog lives, for the OFFLINE tools (generate, promote, plan): the same four operations over a stage's AWS resources or over a local folder.

  Store.has / put / get          objects (o/ p/ t/ keys, see common/catalog.py)
  Store.get_item / put_item / items     metadata rows (DynamoDB item shape, plain dicts)
  Store.get_vector / put_vector / vectors / query   the 1024-d vectors with their metadata

`AwsStore(stage)` uses the stage's profile and the names the CDK construct gives (backend/catalog.py); `LocalStore(path)` is a folder: a catalog can be made on a laptop and later
copied (not regenerated, not re-embedded) to QA and then to prod with scripts/catalog_promote.py. The runtime (engine) never uses this module: it reads through common/catalog.py.
"""
import json
import os
import threading
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np

from common import catalog

_STAGES = {"qa": {"profile": "qa", "region": "eu-west-1", "account": "552357225438"}, "prod": {"profile": "default", "region": "us-west-2", "account": "464863885161"}}


def names(stage: str) -> Dict[str, str]:
    acct = _STAGES[stage]["account"]
    return {"bucket": f"videomk-{stage}-catalog-{acct}", "table": f"videomk-{stage}-catalog-items", "vector_bucket": f"videomk-{stage}-catalog-vec-{acct}", "index": catalog.INDEX_NAME}


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    return v


def _dec(v: Any) -> Any:
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return {k: _dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_dec(x) for x in v]
    return v


class Store:
    label = ""

    def has(self, key: str) -> bool: raise NotImplementedError
    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None: raise NotImplementedError
    def get(self, key: str) -> bytes: raise NotImplementedError
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def put_item(self, item: Dict[str, Any]) -> None: raise NotImplementedError
    def items(self) -> List[Dict[str, Any]]: raise NotImplementedError
    def get_vector(self, vid: str) -> Optional[Tuple[List[float], Dict[str, Any]]]: raise NotImplementedError
    def put_vector(self, vid: str, vec: List[float], metadata: Dict[str, Any]) -> None: raise NotImplementedError
    def vector_ids(self) -> List[str]: raise NotImplementedError
    def delete(self, key: str) -> None: raise NotImplementedError            # only the takedown uses these two (common/takedown.py), after the copy to quarantine/
    def delete_vector(self, vid: str) -> None: raise NotImplementedError

    def query(self, vec: List[float], k: int = 3) -> List[Tuple[str, float]]:
        """(id, cosine similarity) best first. Over the whole index: the catalog is small (hundreds), so the offline tools just compare."""
        q = np.array(vec, dtype=np.float32)
        q /= (np.linalg.norm(q) or 1.0)
        out = []
        for vid in self.vector_ids():
            got = self.get_vector(vid)
            if got:
                v = np.array(got[0], dtype=np.float32)
                out.append((vid, float(q @ (v / (np.linalg.norm(v) or 1.0)))))
        return sorted(out, key=lambda t: -t[1])[:k]

    def images(self) -> List[Dict[str, Any]]:
        """Catalog images (their ids are SHA-256 hashes), not bookkeeping rows."""
        return [i for i in self.items() if catalog.ID_RE.match(str(i.get("id", "")))]


class LocalStore(Store):
    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        self.label = f"local:{self.path}"
        self._lock = threading.Lock()
        os.makedirs(os.path.join(self.path, "objects"), exist_ok=True)

    def _obj(self, key: str) -> str:
        p = os.path.normpath(os.path.join(self.path, "objects", key))
        if not p.startswith(os.path.join(self.path, "objects") + os.sep):
            raise ValueError("bad key")
        return p

    def _json(self, name: str) -> Dict[str, Any]:
        p = os.path.join(self.path, name)
        return json.load(open(p)) if os.path.exists(p) else {}

    def _save(self, name: str, data: Dict[str, Any]) -> None:
        tmp = os.path.join(self.path, name + ".tmp")
        json.dump(data, open(tmp, "w"), ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, os.path.join(self.path, name))

    def has(self, key: str) -> bool: return os.path.exists(self._obj(key))

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        p = self._obj(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)

    def get(self, key: str) -> bytes: return open(self._obj(key), "rb").read()
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]: return self._json("items.json").get(item_id)

    def put_item(self, item: Dict[str, Any]) -> None:
        with self._lock:
            d = self._json("items.json")
            d[item["id"]] = _plain(item)
            self._save("items.json", d)

    def items(self) -> List[Dict[str, Any]]: return list(self._json("items.json").values())

    def get_vector(self, vid: str) -> Optional[Tuple[List[float], Dict[str, Any]]]:
        v = self._json("vectors.json").get(vid)
        return (v["vector"], v["metadata"]) if v else None

    def put_vector(self, vid: str, vec: List[float], metadata: Dict[str, Any]) -> None:
        with self._lock:
            d = self._json("vectors.json")
            d[vid] = {"vector": [float(x) for x in vec], "metadata": _plain(metadata)}
            self._save("vectors.json", d)

    def vector_ids(self) -> List[str]: return list(self._json("vectors.json").keys())

    def delete(self, key: str) -> None:
        if os.path.exists(self._obj(key)):
            os.remove(self._obj(key))

    def delete_vector(self, vid: str) -> None:
        with self._lock:
            d = self._json("vectors.json")
            if d.pop(vid, None) is not None:
                self._save("vectors.json", d)


class AwsStore(Store):
    def __init__(self, stage: str, session: Any = None) -> None:
        import boto3

        cfg = _STAGES[stage]
        self.stage, self.n = stage, names(stage)
        self.label = stage
        sess = session or boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
        self.s3, self.vec = sess.client("s3"), sess.client("s3vectors")
        self.tbl = sess.resource("dynamodb").Table(self.n["table"])

    def has(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.s3.head_object(Bucket=self.n["bucket"], Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        self.s3.put_object(Bucket=self.n["bucket"], Key=key, Body=data, ContentType=content_type, CacheControl="private, max-age=31536000, immutable")

    def get(self, key: str) -> bytes: return self.s3.get_object(Bucket=self.n["bucket"], Key=key)["Body"].read()
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        it = self.tbl.get_item(Key={"id": item_id}).get("Item")
        return _plain(it) if it else None
    def put_item(self, item: Dict[str, Any]) -> None: self.tbl.put_item(Item=_dec(item))

    def items(self) -> List[Dict[str, Any]]:
        out, kw = [], {}
        while True:
            r = self.tbl.scan(**kw)
            out += [_plain(i) for i in r.get("Items", [])]
            if not r.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def _target(self) -> Dict[str, str]: return {"vectorBucketName": self.n["vector_bucket"], "indexName": self.n["index"]}

    def get_vector(self, vid: str) -> Optional[Tuple[List[float], Dict[str, Any]]]:
        r = self.vec.get_vectors(**self._target(), keys=[vid], returnData=True, returnMetadata=True).get("vectors") or []
        return (r[0]["data"]["float32"], r[0].get("metadata") or {}) if r else None

    def put_vector(self, vid: str, vec: List[float], metadata: Dict[str, Any]) -> None:
        self.vec.put_vectors(**self._target(), vectors=[{"key": vid, "data": {"float32": [float(x) for x in vec]}, "metadata": metadata}])

    def vector_ids(self) -> List[str]:
        out, tok = [], None
        while True:
            r = self.vec.list_vectors(**self._target(), **({"nextToken": tok} if tok else {}))
            out += [v["key"] for v in r.get("vectors", [])]
            tok = r.get("nextToken")
            if not tok:
                return out

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.n["bucket"], Key=key)   # the bucket is versioned: this adds a delete marker, the bytes stay recoverable

    def delete_vector(self, vid: str) -> None:
        self.vec.delete_vectors(**self._target(), keys=[vid])

    def query(self, vec: List[float], k: int = 3) -> List[Tuple[str, float]]:
        r = self.vec.query_vectors(**self._target(), queryVector={"float32": [float(x) for x in vec]}, topK=k, returnDistance=True)
        return [(v["key"], 1 - float(v["distance"])) for v in r.get("vectors", [])]


def open_store(spec: str) -> Store:
    """'qa', 'prod' or 'local:<folder>'."""
    if spec.startswith("local:"):
        return LocalStore(spec[6:])
    if spec in _STAGES:
        return AwsStore(spec)
    raise ValueError(f"unknown store {spec!r} (qa, prod or local:<folder>)")
