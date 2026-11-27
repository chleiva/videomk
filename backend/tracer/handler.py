"""The whiteboard TRACER function (docs/LIBRARY_ON_DEMAND.md, part D): the maker of sketch objects, in a small function of its own stack because its two
libraries (scipy, vtracer) do not fit the engine's layer. The plan step calls it synchronously, once a video at most, and only for plain English names that
already passed the safety policy.

    {"action": "make", "objects": [["honeycomb", "honeycomb"], ...], "timeout": 30}
        -> {"packages": [...], "thumbs": {id: base64 JPEG}, "stats": {...}}          the accepted drawings (the caller checks them against the policy and stores them)
        -> {"refused": "<why>", "billed": true|false}                                nothing was made; billed=false means the image provider was never paid
    {"action": "ping"} -> {"ok": true, "tracer": true|false}                         are the tracing code and its libraries importable here

The function holds no state, writes nothing outside /tmp, and knows nothing of accounts, budgets or videos. It reads the image provider's key from SSM at every
call and asks Bedrock for the gate's verdict; those are its only two rights. The code is the library builder's own (common/object_maker.py), not a copy.
"""
import base64
import json
import logging
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lambdas"))
os.environ.setdefault("WB_OUT", "/tmp/wb")                                               # the builder's work folder (its spend log): /tmp is the only writable place
os.environ.setdefault("WHITEBOARD_PROTO_DIR", os.path.join(HERE, "scripts", "whiteboard_proto"))

from common import media_policy, object_maker   # noqa: E402

MAX_OBJECTS = 6
MAX_TIMEOUT_S = 45.0
MAX_ANSWER_BYTES = 5_500_000   # a synchronous answer may be 6 MB
ID_RE = re.compile(r"^[a-z0-9_]{3,48}$")
NAME_RE = re.compile(r"^[a-z][a-z \-]{1,40}$")

logging.getLogger().setLevel(logging.INFO)


def _objects(raw):
    """The request's objects as [(id, name)], or None when anything about them is not what the plan step sends."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_OBJECTS:
        return None
    out = []
    for it in raw:
        if not (isinstance(it, (list, tuple)) and len(it) == 2 and all(isinstance(x, str) for x in it)):
            return None
        oid, name = it
        if not ID_RE.match(oid) or not NAME_RE.match(name) or len(name.split()) > 4 or oid in [o for o, _ in out]:
            return None
        out.append((oid, name))
    return out


def lambda_handler(event, context=None):
    event = event if isinstance(event, dict) else {}
    if event.get("action") == "ping":
        return {"ok": True, "tracer": object_maker.available()}
    if event.get("action") != "make":
        return {"refused": "bad request", "billed": False}
    objs = _objects(event.get("objects"))
    if objs is None:
        return {"refused": "bad request", "billed": False}
    why = media_policy.text_reason(*[n for _, n in objs])   # the caller already checked; the function refuses on its own too, whoever calls it
    if why:
        return {"refused": why, "billed": False}
    try:
        timeout = max(5.0, min(MAX_TIMEOUT_S, float(event.get("timeout") or 30.0)))
    except (TypeError, ValueError):
        timeout = 30.0
    try:
        pkgs, stats = object_maker.make(objs, timeout)
    except object_maker.Refused as e:
        logging.warning("tracer refused: %s (billed=%s)", e.kind, e.billed)
        return {"refused": e.kind, "billed": e.billed}
    except Exception as e:   # noqa: BLE001 - the plan step keeps its labels
        logging.exception("tracer failed")
        return {"refused": f"tracer error ({type(e).__name__})", "billed": True}
    thumbs = {k: base64.b64encode(v).decode() for k, v in (stats.pop("thumbs", None) or {}).items()}
    stats.pop("sheet_png", None)
    out = {"packages": pkgs, "thumbs": thumbs, "stats": stats}
    if len(json.dumps(out)) > MAX_ANSWER_BYTES:
        return {"refused": "answer too large", "billed": True}
    logging.info("tracer made %d of %d in %.1f s", len(pkgs), len(objs), float(stats.get("total_s") or 0))
    return out
