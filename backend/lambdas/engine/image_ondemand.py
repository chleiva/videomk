"""Library IMAGES on demand (docs/LIBRARY_ON_DEMAND.md, part A): the same framework as clips (engine/ondemand.py), on top of VideoMK's own image catalog
(docs/IMAGE_CATALOG.md). When the director's image search has no good catalog match and can be made general, ONE picture is generated with the catalog's own
model, tier and house style, judged by the catalog's own check, marked as ours (common/ownership.py), stored in the catalog, and only then used in the video,
read back from the catalog. A picture of our own library carries no on-screen credit.

    job = begin(...)      decide, reserve, generate in the background while the stock search runs. None = nothing will come. Never raises.
    result = use(id,...)  the catalog picture for this beat (checked against the narration, cut to the video's shape), or None.

Behind the deploy flag CLIPS_ON_DEMAND (the one flag of library media on demand), the knob `image_enabled`, and the catalog itself (`-c imageCatalog=1`).
"""
import base64
import datetime
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from common import catalog, catalog_make as cm, catalog_style, clip_config, clip_store as cs, ownership

from . import clip_brief, clip_library as lib, ondemand
from .clip_ondemand import Job

MEDIA = "image"
KEY_PARAM = "/videomk/openai_api_key"
WAIT_AFTER_S = 20.0
LOCK_S = 300


# ----------------------------------------------------------------------------- the provider (behind an interface, mocked in tests)
class ImageError(Exception):
    def __init__(self, kind: str, message: str = "", *, billed: bool = True):
        super().__init__(f"{kind}: {message}"[:300])
        self.kind, self.billed = kind, billed


class ImageProvider:
    name, model = "", ""

    def generate(self, prompt: str, *, timeout: float = 75.0) -> Dict[str, Any]:
        """-> {"jpeg": bytes, "usd": real cost from the provider's token counts, "model": str}"""
        raise NotImplementedError


class MockImages(ImageProvider):
    name = "mock"

    def __init__(self, jpeg: bytes = b"", *, error: Optional[Exception] = None, delay: float = 0.0, usd: float = 0.0442):
        self.jpeg, self.error, self.delay, self.usd, self.model, self.calls = jpeg, error, delay, usd, "mock-image-1", []

    def generate(self, prompt, *, timeout=75.0):
        self.calls.append({"prompt": prompt, "timeout": timeout})
        if self.delay:
            time.sleep(min(self.delay, timeout))
            if self.delay > timeout:
                raise ImageError("timeout", "mock")
        if self.error is not None:
            raise self.error
        return {"jpeg": self.jpeg, "usd": self.usd, "model": self.model}


class OpenAIImages(ImageProvider):
    """OpenAI Images API, the catalog's model and tier (common/catalog_make.py). The key is read at every call (SSM, or the environment on a laptop), never kept or logged."""
    name = "openai"

    def __init__(self, model: str = cm.OPENAI_MODEL, *, key: Optional[str] = None, opener: Optional[Callable[..., Any]] = None):
        self.model, self._key, self._open = model, key, opener or urllib.request.urlopen

    def _read_key(self) -> str:
        if self._key is not None:
            return self._key
        if os.environ.get("OPENAI_API_KEY"):
            return os.environ["OPENAI_API_KEY"]
        try:
            import boto3
            return str(boto3.client("ssm").get_parameter(Name=KEY_PARAM, WithDecryption=True)["Parameter"]["Value"] or "").strip()
        except Exception as e:
            logging.info("image provider key unavailable (%s)", type(e).__name__)
            return ""

    def generate(self, prompt, *, timeout=75.0):
        key = self._read_key()
        if not key:
            raise ImageError("auth", "no provider key configured", billed=False)
        body = {"model": self.model, "prompt": prompt[:30000], "size": cm.IMAGE_SIZE, "quality": cm.IMAGE_QUALITY, "output_format": "jpeg", "n": 1}
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", json.dumps(body).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with self._open(req, timeout=max(1.0, timeout)) as r:
                res = json.loads(r.read())
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = " ".join(e.read(600).decode("utf-8", "replace").split())[:200]
            except Exception:
                pass
            kind = "auth" if e.code in (401, 403) else "quota" if e.code == 429 else ("blocked" if "safety" in text.lower() or "policy" in text.lower() else "bad_request") if e.code == 400 else "provider"
            raise ImageError(kind, f"HTTP {e.code} {text}", billed=e.code >= 500) from None
        except (TimeoutError, OSError) as e:
            if "timed out" in str(e).lower() or isinstance(e, TimeoutError):
                raise ImageError("timeout", "no answer in time") from None
            raise ImageError("provider", type(e).__name__, billed=False) from None
        data = res.get("data") or []
        if not data or not data[0].get("b64_json"):
            raise ImageError("no_image", "the model returned no image")
        jpeg = base64.b64decode(data[0]["b64_json"])
        if jpeg[:2] != b"\xff\xd8":
            raise ImageError("no_image", "not a JPEG")
        return {"jpeg": jpeg, "usd": cm.real_cost(res.get("usage") or {}), "model": self.model}


_provider: Optional[ImageProvider] = None


def set_provider(p: Optional[ImageProvider]) -> None:
    global _provider
    _provider = p


def provider(model: str) -> ImageProvider:
    return _provider if _provider is not None else OpenAIImages(model)


# ----------------------------------------------------------------------------- the catalog, as this step needs it (a stage's, or a folder on a laptop)
class Cat:
    label = ""

    def search(self, text: str, k: int = 3, qvec: Optional[List[float]] = None) -> List[Dict[str, Any]]: raise NotImplementedError
    def nearest(self, vec: List[float]) -> Optional[Tuple[str, float]]: raise NotImplementedError
    def item(self, cid: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def read(self, key: str) -> bytes: raise NotImplementedError
    def add(self, cid: str, objects: Dict[str, bytes], vec: List[float], row: Dict[str, Any]) -> None: raise NotImplementedError


class AwsCat(Cat):
    label = "aws"

    def search(self, text, k=3, qvec=None):
        return catalog.search(text, k=k)

    def nearest(self, vec):
        r = catalog.vectors().query_vectors(**catalog.vector_target(), queryVector={"float32": [float(x) for x in vec]}, topK=1, returnDistance=True).get("vectors") or []
        return (str(r[0]["key"]), 1 - float(r[0]["distance"])) if r else None

    def item(self, cid):
        return catalog.get_item(cid)

    def read(self, key):
        return catalog.read_object(key)

    def add(self, cid, objects, vec, row):
        from decimal import Decimal

        def dec(v):
            return Decimal(str(round(v, 6))) if isinstance(v, float) else {k: dec(x) for k, x in v.items()} if isinstance(v, dict) else [dec(x) for x in v] if isinstance(v, list) else v
        for key, data in objects.items():
            catalog.s3().put_object(Bucket=os.environ["CATALOG_BUCKET"], Key=key, Body=data, ContentType="image/jpeg", CacheControl="private, max-age=31536000")
        catalog.vectors().put_vectors(**catalog.vector_target(), vectors=[{"key": cid, "data": {"float32": [float(x) for x in vec]}, "metadata": {"title": row.get("title", "")[:100], "category": row.get("category", "")}}])
        catalog.table().put_item(Item=dec(row))   # the row last: a row means a complete image


class LocalCat(Cat):
    def __init__(self, path: str) -> None:
        from common import catalog_store
        self.store, self.label = catalog_store.LocalStore(path), f"local:{path}"

    def search(self, text, k=3, qvec=None):
        q = qvec if qvec is not None else catalog._embed(text)
        return [{"id": cid, "score": round(s, 4)} for cid, s in self.store.query(list(q), k) if catalog.ID_RE.match(cid)]

    def nearest(self, vec):
        r = self.store.query(list(vec), 1)
        return r[0] if r else None

    def item(self, cid):
        return self.store.get_item(cid)

    def read(self, key):
        return self.store.get(key)

    def add(self, cid, objects, vec, row):
        for key, data in objects.items():
            self.store.put(key, data)
        self.store.put_vector(cid, [float(x) for x in vec], {"title": row.get("title", "")[:100], "category": row.get("category", "")})
        self.store.put_item(row)


_cat: Optional[Cat] = None


def set_catalog(c: Optional[Cat]) -> None:
    global _cat
    _cat = c


def current() -> Optional[Cat]:
    if _cat is not None:
        return _cat
    if os.environ.get("CATALOG_LOCAL_DIR"):
        return LocalCat(os.environ["CATALOG_LOCAL_DIR"])
    return AwsCat() if catalog.enabled() else None


def _embed_image(jpeg: bytes) -> List[float]:
    return [float(x) for x in lib.embed("image", jpeg)]


# ----------------------------------------------------------------------------- the flow
def _run(job: Job, *, store: cs.Store, cat: Cat, cfg: Dict[str, Any], lines: List[Dict[str, Any]], kind: str, brief: Dict[str, Any], prompt: str, price: float,
         ledger: Tuple[str, str], claim: Tuple[str, str], lock_key: str, video_id: str) -> None:
    t0 = time.time()
    outcome, reason, charged, cid, verdict, provider_usd = "provider_failed", "", price, None, {}, None
    try:
        try:
            made = provider(str(cfg["image_model"])).generate(prompt, timeout=float(cfg["image_timeout_s"]))
        except ImageError as e:
            outcome, reason = ("timeout" if e.kind == "timeout" else "provider_failed"), e.kind
            if not e.billed:
                ondemand.release(store, lines, media=MEDIA, kind=kind, price=price)
                charged = 0.0
            ondemand.emit("ProviderError", Kind=e.kind, Media=MEDIA)
            return
        ondemand.emit("GenerationSeconds", round(time.time() - t0, 1), "Seconds", Media=MEDIA)
        provider_usd = made.get("usd")
        ok, verdict, _gate_cost = cm.qa_check(made["jpeg"], {"subject": brief["brief"]})
        if not ok:
            bad = [k for k in ("text_visible", "logo_or_brand", "real_person_likeness", "anatomy_problem", "warped_objects", "unsafe") if verdict.get(k) is True] + \
                  [k for k in ("centre_subject", "calm_bottom", "style_ok") if verdict.get(k) is False]
            outcome, reason = "gate_rejected", (bad[0] if bad else "unreadable" if "unreadable" in verdict else "low score")
            ondemand.emit("Rejected", Reason=reason, Media=MEDIA)
            return   # never used, never stored
        asset = catalog.content_hash(made["jpeg"])            # the asset id: the hash of the picture as the provider made it
        thumb = cm._thumb(made["jpeg"], catalog.THUMB_PX)
        vec = _embed_image(thumb)
        near = cat.nearest(vec)
        if near is not None and near[1] >= cm.DUP_SIMILARITY and near[0] != asset:   # we already own this picture, near enough: use that one, store nothing
            outcome, reason, cid = "duplicate", f"of {near[0][:12]}", near[0]
            job.clip_id = cid
            return
        marked = ownership.mark_jpeg(made["jpeg"], asset_id=asset, title=brief["brief"])
        if not ownership.is_marked(marked, asset):
            raise RuntimeError("ownership metadata did not verify")
        from PIL import Image
        import io
        w, h = Image.open(io.BytesIO(made["jpeg"])).size
        full = catalog_style.full_prompt(brief["brief"], False)
        row = {"id": asset, "title": brief["brief"][:100], "category": "on-demand", "tags": [catalog_style.STYLE_VERSION, "on-demand"] + list(brief.get("tags") or []), "serves": [],
               "prompt": full, "negative_prompt": catalog_style.NEGATIVE, "subject": brief["brief"], "model": made.get("model"),
               "created": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "cost_usd": round(price, 4),
               "licence": "videomk-owned: output assigned to VideoMK by the provider's terms; see docs/IMAGE_CATALOG.md", "provenance": {"provider": "OpenAI Images API", "on_demand": True, "demand_video": lib.video_ref(video_id)},
               "review_status": "approved", "review": dict(verdict), "width": w, "height": h, "style_version": catalog_style.STYLE_VERSION, "promoted_from": "", "sha256": asset,
               "scope": "library", "owner_name": ownership.OWNER, "marked": True, "stored_sha256": catalog.content_hash(marked), "watermark": "pending"}
        cat.add(asset, {catalog.key_original(asset): marked, catalog.key_preview(asset): cm._thumb(made["jpeg"], catalog.PREVIEW_PX), catalog.key_thumb(asset): thumb}, vec, row)
        store.add(claim[0], claim[1], fields={"state": "done", "clip_id": asset})
        outcome, reason, cid = "generated", "ok", asset
        job.clip_id, job.generated = asset, True
        ondemand.emit("Generated", Media=MEDIA)
    except Exception as e:   # noqa: BLE001 - never reaches the video
        logging.exception("image generation failed")
        outcome, reason = "provider_failed", f"error {type(e).__name__}"
    finally:
        try:
            took = round(time.time() - t0, 1)
            store.add(ledger[0], ledger[1], fields={"outcome": outcome, "reason": reason[:120], "charged_usd": charged, "latency_s": took, "clip_id": cid, "provider_usd": provider_usd,
                                                    "gate_score": min(float(verdict.get("adherence") or 0), float(verdict.get("quality") or 0)) if verdict else None})
            if outcome != "generated":
                store.add(claim[0], claim[1], fields={"state": outcome, **({"clip_id": cid} if cid else {})})
            store.delete(cs.LOCK, lock_key)
            ondemand._stat(store, MEDIA, **{f"g_{outcome}": 1, "g_latency_ds": int(took * 10), "g_n": 1})
            ondemand.decision(store, outcome if outcome == "generated" else f"{outcome}:{reason}", MEDIA, brief=brief["brief"], charged_usd=charged, latency_s=took, image=cid, kind=kind)
        except Exception:
            logging.exception("image ledger not closed")


def begin(*, video_id: str, beat_id: str, query: str, alt: str, narration: str, plan: Optional[Dict[str, Any]] = None, ctx: Optional[Dict[str, Any]] = None, is_edit: bool = False,
          beat_started: Optional[float] = None, now: Optional[float] = None) -> Optional[Job]:
    """Decide and, when everything allows it, start. Never raises."""
    store = None
    try:
        if not clip_config.flag():
            return None
        store, cat = cs.current(), current()
        if store is None or cat is None:
            return None
        cfg = clip_config.config()
        kind = ondemand.entitlement(ctx)
        if kind is None:
            return None
        if not cfg["image_enabled"] or not cfg["master_enabled"]:
            ondemand.decision(store, "kill_switch", MEDIA)
            return None
        if is_edit:
            ondemand.decision(store, "edit", MEDIA)
            return None
        if (plan or {}).get("media_items") or (plan or {}).get("deck"):
            ondemand.decision(store, "own_photos", MEDIA)
            return None
        t = time.time() if now is None else now
        if beat_started is not None and t - beat_started > float(cfg["start_deadline_s"]):
            ondemand.decision(store, "too_late", MEDIA)
            return None
        claim = (cs.VIDEO + video_id, f"ibeat:{beat_id}")
        old = store.get(*claim)
        if old is not None:
            ondemand.decision(store, "retry", MEDIA, state=old.get("state"))
            return Job(store, clip_id=old.get("clip_id"), outcome="retry", media=MEDIA) if old.get("clip_id") else None
        brief, _c = clip_brief.generalise(query, alt, narration, media=MEDIA)
        if not brief["reusable"]:
            ondemand.decision(store, brief["reason"], MEDIA, query=query)
            return None
        hits = cat.search(brief["brief"], k=1)
        if hits and hits[0]["score"] >= float(cfg["image_reuse_min_score"]):
            ondemand.decision(store, "library_hit", MEDIA, brief=brief["brief"], image=hits[0]["id"], score=hits[0]["score"])
            return Job(store, clip_id=str(hits[0]["id"]), outcome="library_hit", media=MEDIA)
        lock_key = "i:" + clip_brief.brief_key(brief["brief"])
        if not store.put(cs.LOCK, lock_key, {"expires": int(t) + LOCK_S, "ttl": int(t) + LOCK_S}, only_if_absent=True, or_expired=int(t)):
            ondemand.decision(store, "in_flight", MEDIA, brief=brief["brief"])
            return None
        price = float(cfg["image_price_usd"])
        lines, why, allowance = ondemand.reserve(store, cfg, media=MEDIA, kind=kind, ctx=ctx, video_id=video_id, price=price, now=t)
        if lines is None:
            store.delete(cs.LOCK, lock_key)
            ondemand.decision(store, why, MEDIA, brief=brief["brief"], kind=kind, price_usd=price, allowance_usd=allowance)
            return None
        if not store.put(claim[0], claim[1], {"state": "started", "brief": brief["brief"], "at": int(t), "ttl": int(t) + 90 * 86400}, only_if_absent=True):
            ondemand.release(store, lines, media=MEDIA, kind=kind, price=price)
            store.delete(cs.LOCK, lock_key)
            return None
        prompt = catalog_style.full_prompt(brief["brief"], False) + " Avoid: " + catalog_style.NEGATIVE
        ledger = (cs.ledger_pk(cs.month(t)), f"{int(t * 1000):013d}-{uuid.uuid4().hex[:6]}")
        store.put(ledger[0], ledger[1], {"at": int(t), "media": MEDIA, "outcome": "started", "brief": brief["brief"], "query": " ".join(query.split())[:80], "kind": kind, "reserved_usd": price, "charged_usd": price,
                                         "account": lib.account_ref(str(ctx["user_id"])), "video": lib.video_ref(video_id), "allowance_usd": allowance, "ttl": int(t) + 500 * 86400})
        job = Job(store, outcome="generating", media=MEDIA)
        job.info = {"brief": brief["brief"], "t0": time.time()}
        job.deadline = time.time() + float(cfg["image_timeout_s"]) + WAIT_AFTER_S
        job.thread = threading.Thread(target=_run, name="imagegen", daemon=True, kwargs=dict(job=job, store=store, cat=cat, cfg=cfg, lines=lines, kind=kind, brief=brief, prompt=prompt,
                                                                                              price=price, ledger=ledger, claim=claim, lock_key=lock_key, video_id=video_id))
        job.thread.start()
        return job
    except Exception:   # noqa: BLE001
        logging.exception("images on demand: decision failed")
        try:
            ondemand.decision(store, "error", MEDIA)
        except Exception:
            pass
        return None


def use(cid: str, query: str, narration: str, alt: str, video_id: str, *, aspect: str = "16:9", big: bool = False, generated: bool = False,
        complete: Optional[Callable[..., Tuple[str, Dict[str, Any]]]] = None) -> Optional[Dict[str, Any]]:
    """The catalog picture `cid` for this beat, read back from the catalog: approved, checked against the narration by the catalog's own verifier, cut to the
    video's shape. The same result as catalog_pick.try_catalog: no credit line (it is ours). None = not suitable here (the stock photo stays)."""
    try:
        from . import assets, catalog_pick

        cat = current()
        item = cat.item(cid) if cat else None
        if not catalog.usable(item) or item.get("scope", "library") != "library":
            return None
        ok, cost = catalog_pick.verify(cat.read(catalog.key_preview(cid)), narration, alt, query, complete)
        if not ok:
            return None
        jpeg = catalog_pick.prepare_jpeg(cat.read(catalog.key_original(cid)), aspect, assets.max_side_for(big))
        store = cs.current()
        if store is not None:
            src = "generated" if generated else "library"
            ondemand.emit("Used", Source=src, Media=MEDIA)
            ondemand._stat(store, MEDIA, **{f"used_{src}": 1})
            store.add(cs.P + "iuse", cid, {"uses": 1}, sets={"videos": [lib.video_ref(video_id)]})
        return {"jpeg": jpeg, "entry": catalog.ledger_entry(item), "credit": "", "chosen": f"{catalog.SOURCE_NAME}:{cid}", "review": {"source": "catalog", "reason": "on demand", "cost_usd": cost}}
    except Exception:
        logging.exception("on-demand image could not be used")
        return None
