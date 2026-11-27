"""The MAKER of whiteboard sketch objects (docs/LIBRARY_ON_DEMAND.md, parts B and D): names -> one generated sheet -> cut -> traced -> gated -> packages.

    make([(id, english name), ...], timeout) -> (packages, stats)        or raises Refused

It is the library builder's own pipeline (scripts/whiteboard_proto: the house prompt, the cutter, the tracer, the gate that also names and colours), not a copy.
It needs scipy and vtracer, which do not fit the engine's Lambda layer, so it runs in two places only:
  * a laptop (tests, the proof, a nightly run), straight from engine/object_ondemand.py;
  * the small TRACER FUNCTION of its own stack (backend/object_tracer.py, handler backend/tracer/handler.py), which the plan step invokes.
Nothing here knows about accounts, budgets or videos: it gets plain English names that already passed the safety policy and returns drawings.

Safety (common/media_policy.py): the provider's own moderation model reads the exact prompt BEFORE the sheet is paid for and the sheet itself AFTER; either
refusing, or being unavailable, stops the call (fails closed). The policy's vision check of each finished drawing is done by the caller, on `stats["thumbs"]`.
"""
import base64
import io
import json
import logging
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from common import catalog_make as cm, media_policy

KEY_PARAM = "/videomk/openai_api_key"
IMAGES_URL = "https://api.openai.com/v1/images/generations"


class Refused(Exception):
    """The call made nothing. `billed`: could the image provider have charged for it? False = the caller gives the reservation back."""

    def __init__(self, kind: str, *, billed: bool):
        super().__init__(str(kind)[:120])
        self.kind, self.billed = str(kind)[:120], billed


def _proto_dir() -> str:
    return os.environ.get("WHITEBOARD_PROTO_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "whiteboard_proto")


def load() -> Optional[Tuple[Any, Any, Any]]:
    """(gen_art, lib_build, trace) of the library builder, or None where the tracing code or its libraries are not present (the engine's functions)."""
    try:
        proto = _proto_dir()
        if not os.path.isdir(proto):
            return None
        for p in (proto, os.path.join(proto, "..")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import gen_art
        import lib_build
        import trace as tr
        return gen_art, lib_build, tr
    except Exception as e:   # noqa: BLE001
        logging.info("whiteboard tracer unavailable (%s)", type(e).__name__)
        return None


def available() -> bool:
    return load() is not None


def read_key() -> str:
    """The image provider's key, read at every call (the environment on a laptop, SSM in a function), never kept or logged."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    try:
        import boto3
        return str(boto3.client("ssm").get_parameter(Name=os.environ.get("OPENAI_SSM_PARAM") or KEY_PARAM, WithDecryption=True)["Parameter"]["Value"] or "").strip()
    except Exception as e:   # noqa: BLE001
        logging.info("image provider key unavailable (%s)", type(e).__name__)
        return ""


def _jpeg(png: bytes) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(out, "JPEG", quality=88)
    return out.getvalue()


def sheet(prompt: str, size: str, timeout: float, *, key: Optional[str] = None, opener: Optional[Callable[..., Any]] = None,
          moderate: Optional[Callable[..., Optional[str]]] = None) -> Tuple[bytes, float]:
    """One sheet from the image provider, between the two moderation checks. -> (png, real cost by the provider's token counts). Raises Refused."""
    key = read_key() if key is None else key
    if not key:
        raise Refused("auth", billed=False)
    moderate = moderate or (lambda **kw: media_policy.moderation(key=key, opener=opener, **kw))
    why = moderate(text=prompt)
    if why:
        raise Refused(why, billed=False)
    body = {"model": cm.OPENAI_MODEL, "prompt": prompt, "size": size, "quality": "medium", "output_format": "png", "n": 1, "moderation": "auto"}
    req = urllib.request.Request(IMAGES_URL, json.dumps(body).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=max(5.0, timeout)) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Refused(f"provider HTTP {e.code}", billed=e.code >= 500) from None
    except (TimeoutError, OSError) as e:
        late = "timed out" in str(e).lower() or isinstance(e, TimeoutError)
        raise Refused("timeout" if late else f"provider {type(e).__name__}", billed=late) from None
    data = res.get("data") or []
    if not data or not data[0].get("b64_json"):
        raise Refused("no_image", billed=True)
    png = base64.b64decode(data[0]["b64_json"])
    why = moderate(image=png, mime="image/png")
    if why:
        raise Refused(why, billed=True)   # paid for and thrown away: nothing of this sheet is kept
    return png, cm.real_cost(res.get("usage") or {})


def make(objs: List[Tuple[str, str]], timeout: float, *, key: Optional[str] = None, opener: Optional[Callable[..., Any]] = None,
         moderate: Optional[Callable[..., Optional[str]]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """-> (accepted packages, stats). stats: sheet_s, sheet_usd, cut_s, object_s, total_s, rejected {id: why}, thumbs {id: JPEG of the finished drawing}."""
    mods = load()
    if mods is None:
        raise Refused("no_tracer", billed=False)
    gen_art, lib_build, tr = mods
    from concurrent.futures import ThreadPoolExecutor

    t0, n = time.time(), lib_build.COLS * lib_build.ROWS
    objs = list(objs)[:n]
    subjects = [name for _, name in objs] + ["a small plain circle"] * (n - len(objs))
    prompt = gen_art.HOUSE.format(n=n, cols=lib_build.COLS, rows=lib_build.ROWS, subjects="; ".join(f"({i + 1}) {s}" for i, s in enumerate(subjects)))
    png, usd = sheet(prompt, gen_art.SIZE, timeout, key=key, opener=opener, moderate=moderate)
    stats: Dict[str, Any] = {"sheet_s": round(time.time() - t0, 1), "sheet_usd": round(usd, 4), "rejected": {}, "thumbs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sheet.png")
        with open(path, "wb") as fh:
            fh.write(png)
        stats["sheet_png"] = png
        t1 = time.time()
        cells = lib_build.cut(tr.load_ink(path))
        stats["cut_s"] = round(time.time() - t1, 2)
        lib_build.LIB = tmp   # packages are written here and read back: nothing touches the builder's own library folder

        def one(job):
            (oid, name), cell = job
            t = time.time()
            try:
                row = lib_build.build_object(oid, "on-demand", name, cell, "on-demand", 1)
            except Exception as e:  # noqa: BLE001
                row = {"ok": False, "why": f"build failed: {type(e).__name__}"}
            row["s"] = round(time.time() - t, 1)
            return oid, row
        with ThreadPoolExecutor(max_workers=6) as ex:
            rows = list(ex.map(one, zip(objs, cells)))
        out = []
        for oid, row in rows:
            if row.get("ok"):
                with open(os.path.join(tmp, oid + ".json")) as fh:
                    out.append(json.load(fh))
                try:
                    with open(os.path.join(tmp, oid + ".png"), "rb") as fh:
                        stats["thumbs"][oid] = _jpeg(fh.read())
                except Exception:   # noqa: BLE001 - no picture = the caller's policy check refuses the drawing
                    logging.exception("no thumbnail of %s", oid)
            else:
                stats["rejected"][oid] = str(row.get("why"))[:80]
        stats["object_s"] = {oid: row["s"] for oid, row in rows}
    stats["total_s"] = round(time.time() - t0, 1)
    return out, stats
