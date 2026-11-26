"""The deck converter Lambda (container image). Input: {"user_id", "deck_id", "ext": "pptx"|"pdf", "max_slides"?}.

Reads uploads/<user>/decks/<deck_id>/original.<ext> from the assets bucket, validates it as hostile input, renders every slide to a PNG and writes next to it
  slide_001.png ...  deck.json  ({format, slides:[{n,title,blocks,notes,tables,charts,alts,pictures,role,...}], images:[names], width, height})  and  status.json
  ({status: ready|failed, slides, roles | code}), which GET /users/{user}/decks/{id} reads. Deletes the original on success and on a refusal. Returns {"ok": true, "slides": n, "seconds": {...}} or {"ok": false, "code": "deck_..."}; never a stack trace, never slide text in a log.
Runs in a subnet with no route out (only the S3 gateway endpoint): see backend/deck.py.
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict

import boto3

import deck_extract
import deck_render
import deck_safe
from deck_safe import DeckError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
_ID = re.compile(r"^[0-9a-f]{16}$")
_USER = re.compile(r"^[A-Za-z0-9_.:-]{3,80}$")


def _s3():
    return boto3.client("s3")


def process(raw: bytes, ext: str, out_put, max_slides: int) -> Dict[str, Any]:
    """The whole job on bytes; `out_put(name, bytes, content_type)` stores a result. Testable without AWS."""
    t0 = time.time()
    kind = deck_safe.kind_of(raw[:16])
    if (ext == "pptx" and kind != "pptx") or (ext == "pdf" and kind != "pdf"):
        if kind == "ole":
            raise DeckError("deck_encrypted", "legacy or protected office file")
        raise DeckError("deck_unsupported", "content does not match the declared format")
    work = deck_render.make_workdir()
    sec: Dict[str, float] = {}
    try:
        if kind == "pptx":
            info = deck_safe.inspect_pptx(raw, max_slides)
            clean = deck_safe.sanitize_pptx(raw)
            logger.info("deck accepted: %s slides, %s entries, %s external references ignored", info["slides"], info["entries"], info["external_refs"])
            path = os.path.join(work, "deck.pptx")
            with open(path, "wb") as f:
                f.write(clean)
            t = time.time()
            data = deck_extract.extract_pptx(clean, max_slides)
            sec["extract"] = round(time.time() - t, 2)
            t = time.time()
            pdf = deck_render.pptx_to_pdf(path, work)
            sec["convert"] = round(time.time() - t, 2)
        else:
            deck_safe.inspect_pdf(raw)
            pdf = os.path.join(work, "deck.pdf")
            with open(pdf, "wb") as f:
                f.write(raw)
            data = None
        t = time.time()
        files = deck_render.rasterize(pdf, work, max_slides)
        sec["raster"] = round(time.time() - t, 2)
        if data is None:
            data = deck_extract.extract_pdf(deck_render.pdf_text(pdf, work, len(files)))
        n_text = len(data["slides"])
        if n_text != len(files):   # a mismatch (a slide the converter dropped or split): keep the pages we have; the text of the missing ones is empty
            logger.warning("deck slide count differs: %s extracted, %s rendered", n_text, len(files))
            while len(data["slides"]) < len(files):
                data["slides"].append({"n": len(data["slides"]) + 1, "title": "", "blocks": [], "notes": "", "tables": [], "charts": [], "alts": [], "pictures": 0, "layout": "", "role": "content"})
            data["slides"] = data["slides"][: len(files)]
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 60_000_000
        keys = []
        w = h = 0
        for i, fpath in enumerate(files, start=1):
            with open(fpath, "rb") as f:
                b = f.read()
            if i == 1:
                with Image.open(fpath) as im:
                    w, h = im.size
            keys.append(f"slide_{i:03d}.png")
            out_put(keys[-1], b, "image/png")
        data.update({"images": keys, "width": w, "height": h})
        out_put("deck.json", json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")
        sec["total"] = round(time.time() - t0, 2)
        return {"ok": True, "slides": len(files), "format": data["format"], "width": w, "height": h, "seconds": sec, "roles": [sl.get("role", "content") for sl in data["slides"]]}
    finally:
        deck_render.cleanup(work)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user, deck, ext = str(event.get("user_id", "")), str(event.get("deck_id", "")), str(event.get("ext", ""))
    max_slides = min(deck_safe.MAX_SLIDES, int(event.get("max_slides") or deck_safe.MAX_SLIDES))
    if not (_USER.match(user) and _ID.match(deck) and ext in ("pptx", "pdf")):
        return {"ok": False, "code": "deck_unsupported"}
    bucket = os.environ["ASSETS_BUCKET"]
    out_prefix = f"uploads/{user}/decks/{deck}/"
    key = f"{out_prefix}original.{ext}"
    s3 = _s3()

    def put(name: str, data: bytes, ctype: str) -> None:
        s3.put_object(Bucket=bucket, Key=out_prefix + name, Body=data, ContentType=ctype)

    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        if head["ContentLength"] > deck_safe.MAX_BYTES:
            raise DeckError("deck_too_large")
        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read(deck_safe.MAX_BYTES + 1)
        result = process(raw, ext, put, max_slides)
    except DeckError as e:
        logger.warning("deck refused: %s", e)   # code and a short English reason; never any slide text
        result = {"ok": False, "code": e.code}
    except Exception as e:   # a converter crash, a corrupt structure python-pptx cannot read: a plain failure, only the exception type in the log
        logger.error("deck failed: %s", type(e).__name__)
        result = {"ok": False, "code": "deck_corrupt"}
    status = {"status": "ready", "slides": result["slides"], "format": result["format"], "roles": result.get("roles", [])} if result.get("ok") else {"status": "failed", "code": result.get("code", "deck_corrupt")}
    try:
        put("status.json", json.dumps(status).encode(), "application/json")
        s3.delete_object(Bucket=bucket, Key=key)   # the original is not kept, whether or not it was usable
    except Exception:
        logger.error("could not write the deck status or delete the original")
    return result
