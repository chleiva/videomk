#!/usr/bin/env python3
"""Build the search index of the cartoon vector scene catalog and (optionally) upload the packages to the QA catalog bucket.

  AWS_PROFILE=qa python backend/scripts/vector_catalog_index.py --store DIR [--upload qa]

Embeddings: Cohere Embed v4 through Bedrock (never Titan): the thumbnail as `search_document` (image) and a description text (title, tags, mood, topics) as `search_document` (text), 1024 d,
float16 base64 in backend/lambdas/common/vector_catalog_index.json. Cost: cents (two embeddings per scene; the spend is appended to docs/vector_catalog_spend.jsonl).
`--upload qa` copies each package to s3://videomk-qa-catalog-<account>/v/<id>/ (the QA catalog bucket; objects are immutable per id; no deploy).
"""
import argparse
import base64
import datetime
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("BEDROCK_REGION", "eu-west-1")

from common import library_search  # noqa: E402

OUT = os.path.join(HERE, "..", "lambdas", "common", "vector_catalog_index.json")
LEDGER = os.path.join(ROOT, "docs", "vector_catalog_spend.jsonl")
EMBED_USD_TEXT, EMBED_USD_IMAGE = 0.00002, 0.0006     # indicative (Cohere Embed v4 on Bedrock: per 1M tokens / per image), logged as an estimate


def enc(v):
    return base64.b64encode(struct.pack(f"<{len(v)}e", *v)).decode("ascii")


def describe(m):
    return f"{m['title']}. {m['description']}. Mood: {m['mood']}. Tags: {', '.join(m['tags'])}. Good for: {m['topics']}."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--upload", choices=["qa"])
    a = ap.parse_args()
    items, est = [], 0.0
    for sid in sorted(os.listdir(a.store)):
        mp = os.path.join(a.store, sid, "meta.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        if m["provenance"].get("review_status") != "approved":
            continue
        jpg = open(os.path.join(a.store, sid, "thumb.jpg"), "rb").read()
        vi = library_search._embed({"input_type": "search_document", "images": ["data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii")]})
        vt = library_search._embed({"input_type": "search_document", "texts": [describe(m)[:1800]]})
        est += EMBED_USD_TEXT + EMBED_USD_IMAGE
        items.append({k: m[k] for k in ("id", "title", "category", "mood", "tags", "topics", "aspects", "palette", "layers", "svg_kb")} | {"vi": enc(vi), "vt": enc(vt)})
        print("embedded", sid, flush=True)
    json.dump({"model": library_search.EMBED_MODEL, "dim": library_search.EMBED_DIM, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), "items": items}, open(OUT, "w"), separators=(",", ":"))
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "run": "vector-catalog-1", "item": "embeddings", "what": f"Cohere Embed v4 x{2 * len(items)} (estimate)", "usd": round(est, 5)}) + "\n")
    print(f"index: {len(items)} scenes, {os.path.getsize(OUT) // 1024} KB")
    if a.upload:
        import boto3
        sess = boto3.Session(profile_name="qa", region_name="eu-west-1")
        acct = sess.client("sts").get_caller_identity()["Account"]
        assert acct == "552357225438", "QA account only"
        bucket = f"videomk-qa-catalog-{acct}"
        s3 = sess.client("s3")
        n = 0
        for it in items:
            d = os.path.join(a.store, it["id"])
            for f in sorted(os.listdir(d)):
                if f.endswith(".svg") or f in ("manifest.json", "meta.json", "thumb.jpg"):
                    ct = {"svg": "image/svg+xml", "json": "application/json", "jpg": "image/jpeg"}[f.rsplit(".", 1)[1]]
                    s3.put_object(Bucket=bucket, Key=f"v/{it['id']}/{f}", Body=open(os.path.join(d, f), "rb").read(), ContentType=ct, ServerSideEncryption="AES256")
                    n += 1
        print(f"uploaded {n} objects to s3://{bucket}/v/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
