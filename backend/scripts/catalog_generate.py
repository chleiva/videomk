#!/usr/bin/env python3
"""Generate the images of an APPROVED catalog plan (docs/IMAGE_CATALOG.md, section "Generation tool"). Costs money: nothing runs without --yes.

  catalog_generate.py plan.json --store local:/path/to/catalog --max-usd 5 --yes [--regen] [--only p01,p02] [--profile qa]

* The plan comes from catalog_plan.py (or by hand) and must carry `approved_by`; every item must say which >= 3 different prompts it serves.
* Generator: OpenAI Images API, model gpt-image-2.6-flare, 2048x1152 (16:9), quality high, JPEG. (Bedrock/Stability generation was removed: see docs/IMAGE_CATALOG.md.)
* Hard cost cap: before EVERY paid call a conservative price per call (PRICES below) is added to what the run has spent and the
  call is refused if the total would pass --max-usd; after the call the REAL cost from the response's token usage is charged. Every dollar goes to the spend log (JSON lines) whether the picture is kept or not.
* Each result is checked by a vision model (Claude): prompt adherence and artefacts (bad hands or faces, warped objects, text, logos, a recognisable real person, anything unsafe,
  captions area, crop safety). A rejected picture is dropped (never stored) and, with --regen, generated once more if the cap allows (the API has no seed).
* Duplicate check against the catalog: the Cohere embedding of the thumbnail is compared with the stored vectors (>= DUP_SIMILARITY: dropped).
* Kept pictures are stored immutably by content hash (original, 1280 preview, 384 thumbnail), with metadata and the vector. Idempotent by plan item id: an item with a marker row is skipped.
* Never writes to prod (promote with catalog_promote.py: copying, no second payment).
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
sys.path.insert(0, HERE)

# OpenAI gpt-image-2.6-flare, image output USD 30 per 1M tokens, text input USD 5 per 1M tokens (https://developers.openai.com/api/docs/pricing, read 2026-11-26).
# Measured 2026-11-26 at 2048x1152: high = 1413 output tokens (USD 0.0424), medium 1212 (0.0364); 1792x1008 medium 1056 (0.0317). The reserve is above the high-quality figure; the real cost
# from the response's `usage` is what is charged. The Anthropic check is measured from the real token usage. Cohere embedding of one thumbnail is a fraction of a cent.
from common.catalog_make import OPENAI_MODEL, IMAGE_SIZE, IMAGE_QUALITY, OUT_USD_PER_TOKEN, IN_USD_PER_TOKEN, QA_SYSTEM, real_cost, _thumb, qa_check, judge  # noqa: E402,F401 - shared with images on demand
PRICES = {"generate": 0.055, "embed": 0.0005, "check_reserve": 0.01}
MODELS = {"generate": OPENAI_MODEL}
SSM_KEY_NAME = "/videomk/openai_api_key"
from common.catalog_make import DUP_SIMILARITY, MIN_QA_SCORE  # noqa: E402,F401
ORIGINAL_MAX_SIDE = 3840

class BudgetExceeded(Exception):
    pass


class Spend:
    """The run's money. `reserve` is called BEFORE each paid call and raises when the call could pass the cap."""

    def __init__(self, cap: float, log_path: str, run: str) -> None:
        self.cap, self.log_path, self.run, self.total = cap, log_path, run, 0.0

    def reserve(self, what: str, usd: float) -> None:
        if self.total + usd > self.cap + 1e-9:
            raise BudgetExceeded(f"{what} (${usd:.4f}) would take the run to ${self.total + usd:.4f}, over the cap of ${self.cap:.2f}")

    def charge(self, what: str, usd: float, item: str = "") -> None:
        self.total += usd
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": self.run, "item": item, "what": what, "usd": round(usd, 6), "run_total": round(self.total, 6)}) + "\n")


# ----------------------------------------------------------------------------- the model calls
def _openai_key(profile: str) -> str:
    """The key is read from SSM (never printed, logged or stored). OPENAI_API_KEY in the environment wins (for a laptop)."""
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    import boto3

    return boto3.Session(profile_name=profile, region_name="eu-west-1").client("ssm").get_parameter(Name=SSM_KEY_NAME, WithDecryption=True)["Parameter"]["Value"]


def openai_api(profile: str):
    """-> a function body -> response dict for POST /v1/images/generations (plain HTTPS, no extra dependency). Errors never include the key."""
    import urllib.error
    import urllib.request

    key = _openai_key(profile)

    def call(body: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", json.dumps(body).encode(), {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=300))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OpenAI HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
    return call


def generate_image(api, item: Dict[str, Any]) -> Tuple[bytes, float]:
    """-> (jpeg, real cost USD). Free composition from the house prompt; the API has no seed, so a re-run gives a different picture."""
    from common import catalog_style

    prompt = catalog_style.full_prompt(item["subject"], bool(item.get("people")))
    prompt += " Avoid: " + catalog_style.NEGATIVE
    res = api({"model": OPENAI_MODEL, "prompt": prompt[:30000], "size": IMAGE_SIZE, "quality": IMAGE_QUALITY, "output_format": "jpeg", "n": 1})
    data = res.get("data") or []
    if not data or not data[0].get("b64_json"):
        raise RuntimeError("the model returned no image")
    return base64.b64decode(data[0]["b64_json"]), real_cost(res.get("usage") or {})


# ----------------------------------------------------------------------------- the run
def validate_plan(plan: Dict[str, Any]) -> List[str]:
    errs = []
    if not str(plan.get("approved_by") or "").strip():
        errs.append("the plan has no `approved_by`: the owner approves a plan before anything is generated")
    if not plan.get("plan_id"):
        errs.append("the plan has no `plan_id`")
    ids = set()
    for it in plan.get("items") or []:
        i = it.get("id", "?")
        if i in ids:
            errs.append(f"duplicate item id {i}")
        ids.add(i)
        if not it.get("subject"):
            errs.append(f"{i}: no subject")
        # one image for three or more different prompts; a demand-backed item (catalog_opportunities.py) may instead be asked by >= 3 distinct videos with fewer wordings
        if len({str(s).lower() for s in it.get("serves") or []}) < 3 and int(it.get("distinct_videos") or 0) < 3:
            errs.append(f"{i}: must list at least 3 different prompts it serves")
    if not plan.get("items"):
        errs.append("the plan has no items")
    return errs


def marker_id(plan_id: str, item_id: str) -> str:
    return f"plan#{plan_id}#{item_id}"


def store_image(store, jpeg: bytes, item: Dict[str, Any], plan: Dict[str, Any], cost: float, verdict: Dict[str, Any], vec: List[float], extra: Dict[str, Any]) -> str:
    from common import catalog, catalog_style

    cid = catalog.content_hash(jpeg)
    for key, data in ((catalog.key_original(cid), jpeg), (catalog.key_preview(cid), _thumb(jpeg, catalog.PREVIEW_PX)), (catalog.key_thumb(cid), _thumb(jpeg, catalog.THUMB_PX))):
        if not store.has(key):
            store.put(key, data)
    md = {"title": item.get("title", "")[:100], "category": item.get("category", "")}
    store.put_vector(cid, vec, md)
    store.put_item({
        "id": cid, "title": item.get("title", ""), "category": item.get("category", ""), "tags": [catalog_style.STYLE_VERSION, item.get("category", "")], "serves": list(item.get("serves") or [])[:12],
        "prompt": catalog_style.full_prompt(item["subject"], bool(item.get("people"))), "negative_prompt": catalog_style.NEGATIVE, "subject": item["subject"],
        "model": extra["model"], "created": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "cost_usd": round(cost, 4), "licence": "videomk-owned: output assigned to VideoMK by the provider's terms; see docs/IMAGE_CATALOG.md", "provenance": {"provider": "OpenAI Images API", "plan": plan["plan_id"], "plan_item": item["id"]},
        "review_status": "approved", "review": {k: v for k, v in verdict.items()}, "width": extra["size"][0], "height": extra["size"][1], "style_version": catalog_style.STYLE_VERSION,
        "promoted_from": "", "sha256": cid,
    })
    return cid


def run(plan: Dict[str, Any], store, spend: Spend, *, profile: str, regen: bool, only: Optional[List[str]], embed_image=None, api=None, complete=None, sleep=0.0) -> Dict[str, Any]:
    from PIL import Image
    from common import catalog

    if embed_image is None:
        from common import library_search
        embed_image = lambda j: library_search.embed_image(_thumb(j, catalog.THUMB_PX))   # noqa: E731
    api = api or openai_api(profile)
    summary: Dict[str, Any] = {"made": [], "skipped": [], "rejected": [], "duplicates": [], "stopped": ""}
    for item in plan["items"]:
        iid = item["id"]
        if only and iid not in only:
            continue
        mid = marker_id(plan["plan_id"], iid)
        if store.get_item(mid):
            summary["skipped"].append(iid)
            continue
        attempts = 2 if regen else 1
        done = False
        for attempt in range(attempts):
            try:
                spend.reserve("generate", PRICES["generate"] + PRICES["check_reserve"] + PRICES["embed"])
                final0, gen_cost = generate_image(api, item)
                spend.charge("generate", gen_cost, iid)
                jpeg = final0
                passed, verdict, qcost = qa_check(jpeg, item, complete)
                spend.charge("vision-check", qcost, iid)
                if not passed:
                    summary["rejected"].append({"item": iid, "attempt": attempt + 1, "verdict": verdict})
                    print(f"  {iid}: rejected ({verdict.get('reasons') or verdict.get('unreadable', 'unreadable verdict')})")
                    continue
                big = jpeg
                im = Image.open(io.BytesIO(big)).convert("RGB")
                if max(im.size) > ORIGINAL_MAX_SIDE:
                    s = ORIGINAL_MAX_SIDE / max(im.size)
                    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
                out = io.BytesIO()
                im.save(out, "JPEG", quality=92, optimize=True, subsampling=0)
                final = out.getvalue()
                vec = embed_image(final)
                spend.charge("embed", PRICES["embed"], iid)
                near = store.query(vec, 1)
                if near and near[0][1] >= DUP_SIMILARITY:
                    summary["duplicates"].append({"item": iid, "of": near[0][0], "similarity": round(near[0][1], 3)})
                    print(f"  {iid}: duplicate of an existing image ({near[0][1]:.2f}), dropped")
                    done = True
                    break
                cid = store_image(store, final, item, plan, gen_cost + PRICES["embed"] + qcost, verdict, vec, {"model": OPENAI_MODEL + " " + IMAGE_SIZE + " " + IMAGE_QUALITY, "size": im.size})
                summary["made"].append({"item": iid, "id": cid, "attempts": attempt + 1})
                print(f"  {iid}: kept {cid[:12]} ({im.size[0]}x{im.size[1]}) {verdict.get('reasons', '')}")
                done = True
                break
            except BudgetExceeded as e:
                summary["stopped"] = str(e)
                print("STOP:", e)
                return summary
            except Exception as e:   # a failed call is not retried silently: its cost (if any) is already logged, the item stays open
                print(f"  {iid}: failed ({type(e).__name__}: {str(e)[:200]})")
                break
        if done:
            store.put_item({"id": mid, "plan": plan["plan_id"], "item": iid, "done": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "image": (summary["made"][-1]["id"] if summary["made"] and summary["made"][-1]["item"] == iid else "")})
        if sleep:
            time.sleep(sleep)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--store", required=True, help="qa | local:<folder> (prod is refused: use catalog_promote.py)")
    ap.add_argument("--max-usd", type=float, default=5.0)
    ap.add_argument("--yes", action="store_true", help="really spend money")
    ap.add_argument("--regen", action="store_true", help="regenerate a rejected picture once")
    ap.add_argument("--only", default="")
    ap.add_argument("--profile", default="qa")
    ap.add_argument("--spend-log", default=os.path.join(HERE, "..", "..", "docs", "image_catalog", "spend_log.jsonl"))
    args = ap.parse_args()
    if args.store.strip() == "prod":
        sys.exit("Refusing: nothing is generated into prod. Generate in qa (or locally) and promote with catalog_promote.py --from qa --to prod.")
    plan = json.load(open(args.plan))
    errs = validate_plan(plan)
    if errs:
        sys.exit("Plan refused:\n  - " + "\n  - ".join(errs))
    est = sum(PRICES["generate"] + PRICES["embed"] + PRICES["check_reserve"] for _ in plan["items"])
    print(f"{len(plan['items'])} items, about ${est:.2f} without regeneration (cap ${args.max_usd:.2f})")
    if not args.yes:
        sys.exit("Dry run: nothing was generated. Add --yes to spend.")
    if args.profile == "default":
        sys.exit("Refusing: the `default` profile is the production account.")
    os.environ["AWS_PROFILE"] = args.profile   # before anything imports boto3 clients: the model calls, the embeddings and the checks all use this account
    os.environ["BEDROCK_REGION"] = "eu-west-1"
    from common.catalog_store import open_store

    store = open_store(args.store)
    os.makedirs(os.path.dirname(os.path.abspath(args.spend_log)), exist_ok=True)
    spend = Spend(args.max_usd, args.spend_log, f"{plan['plan_id']}-{int(time.time())}")
    summary = run(plan, store, spend, profile=args.profile, regen=args.regen, only=[x for x in args.only.split(",") if x] or None)
    print(json.dumps({k: (v if k == "stopped" else len(v)) for k, v in summary.items()}), f"spent this run: ${spend.total:.4f} of ${args.max_usd:.2f}")


if __name__ == "__main__":
    main()
