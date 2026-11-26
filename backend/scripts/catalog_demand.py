#!/usr/bin/env python3
"""Demand analysis for the image catalog (docs/IMAGE_CATALOG.md, section 2). READ-ONLY on QA.

  catalog_demand.py extract  --out docs/image_catalog/demand_queries.json     # every image search phrase in the QA plans (generic phrases only)
  catalog_demand.py analyze  --queries docs/image_catalog/demand_queries.json --candidates docs/image_catalog/candidates.json --out docs/image_catalog/demand_report.json

`extract` reads generation/v2/*/plan_r*.json from the assets bucket with the `qa` profile (list + get only), keeps ONLY the image search phrases (never the
narration, titles or user photos), drops the personal ones with common/catalog_privacy.py, and stores {phrase, video(hashed), kind}. `analyze` embeds the phrases
(Cohere Embed v4 through Bedrock, text), clusters them, and measures how many past searches the proposed catalog images would have satisfied.
"""
import argparse
import collections
import hashlib
import json
import os
import sys
from typing import Any, Dict, List

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from common import catalog_privacy as priv  # noqa: E402

BUCKET = "videomk-qa-552357225438"
SALT = "catalog-demand-analysis-v1"   # analysis-only salt: the report names videos by an opaque short hash


def extract(out: str, profile: str = "qa", region: str = "eu-west-1") -> None:
    import boto3

    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")
    keys: List[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="generation/v2/"):
        keys += [o["Key"] for o in page.get("Contents", []) if "/plan_r" in o["Key"] and o["Key"].endswith(".json")]
    # one plan per video: the latest revision (earlier ones repeat the same searches)
    latest: Dict[str, str] = {}
    for k in sorted(keys, key=lambda k: (k.split("/")[2], int(k.rsplit("plan_r", 1)[1].split(".")[0]))):
        latest[k.split("/")[2]] = k
    rows: List[Dict[str, Any]] = []
    dropped: collections.Counter = collections.Counter()
    for vid, key in sorted(latest.items()):
        plan = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
        ref = priv.video_ref(vid, SALT)
        for b in plan.get("beats", []):
            sc = b.get("scene") or {}
            p = sc.get("props") or {}
            found: List[tuple] = []
            if sc.get("type") in ("image", "annotated_image") and not p.get("photo") and p.get("image_query"):
                found.append((p["image_query"], "image"))
            if sc.get("type") == "gallery" and not p.get("photos"):
                found += [(q, "gallery") for q in p.get("image_queries") or []]
            for q, kind in found:
                g = priv.generic_phrase(str(q))
                if g is None:
                    dropped[priv.personal_reason(str(q)) or "?"] += 1
                else:
                    rows.append({"phrase": g, "video": ref, "kind": kind})
    doc = {"source": f"qa {BUCKET} generation/v2 latest plan per video", "videos": len(latest), "searches": len(rows), "dropped_personal": dict(dropped), "rows": rows}
    with open(out, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=0)
    print(f"{len(latest)} videos, {len(rows)} generic searches kept, dropped {sum(dropped.values())}: {dict(dropped)} -> {out}")


# ----------------------------------------------------------------------------- embeddings
def _client(profile: str, region: str):
    import boto3

    return boto3.Session(profile_name=profile, region_name=region).client("bedrock-runtime")


def embed_texts(texts: List[str], input_type: str, profile: str = "qa", region: str = "eu-west-1", cache: str = "") -> np.ndarray:
    model = os.environ.get("EMBED_MODEL_ID", "eu.cohere.embed-v4:0" if region.startswith("eu-") else "us.cohere.embed-v4:0")
    store: Dict[str, List[float]] = {}
    if cache and os.path.exists(cache):
        store = json.load(open(cache))
    def k(t: str) -> str:
        return hashlib.sha1((input_type + "|" + t).encode()).hexdigest()
    todo = [t for t in dict.fromkeys(texts) if k(t) not in store]
    br = _client(profile, region) if todo else None
    for i in range(0, len(todo), 64):
        chunk = todo[i:i + 64]
        res = json.loads(br.invoke_model(modelId=model, body=json.dumps({"input_type": input_type, "texts": [t[:512] for t in chunk], "embedding_types": ["float"], "output_dimension": 1024}))["body"].read())
        for t, v in zip(chunk, res["embeddings"]["float"]):
            store[k(t)] = v
    if cache and todo:
        json.dump(store, open(cache, "w"))
    m = np.array([store[k(t)] for t in texts], dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def cluster(vecs: np.ndarray, thr: float) -> List[int]:
    """Greedy leader clustering by cosine similarity: deterministic, no dependencies."""
    leaders: List[int] = []
    labels: List[int] = []
    for i, v in enumerate(vecs):
        if leaders:
            sims = vecs[leaders] @ v
            j = int(np.argmax(sims))
            if sims[j] >= thr:
                labels.append(j)
                continue
        leaders.append(i)
        labels.append(len(leaders) - 1)
    return labels


def analyze(queries: str, candidates: str, out: str, profile: str, region: str, cache: str, threshold: float, cluster_thr: float) -> None:
    data = json.load(open(queries))
    rows = data["rows"]
    phrases = sorted({r["phrase"] for r in rows})
    qv = embed_texts(phrases, "search_query", profile, region, cache)
    idx = {p: i for i, p in enumerate(phrases)}
    vids_of: Dict[str, set] = collections.defaultdict(set)
    count: collections.Counter = collections.Counter()
    for r in rows:
        vids_of[r["phrase"]].add(r["video"])
        count[r["phrase"]] += 1
    labels = cluster(qv, cluster_thr)
    groups: Dict[int, List[str]] = collections.defaultdict(list)
    for p, l in zip(phrases, labels):
        groups[l].append(p)
    clusters = []
    for l, ps in groups.items():
        vs = set().union(*(vids_of[p] for p in ps))
        clusters.append({"example": max(ps, key=lambda p: count[p]), "phrases": len(ps), "searches": sum(count[p] for p in ps), "videos": len(vs), "sample": ps[:6]})
    clusters.sort(key=lambda c: (-c["videos"], -c["searches"]))
    report: Dict[str, Any] = {"searches": len(rows), "distinct_phrases": len(phrases), "videos": len({r["video"] for r in rows}), "cluster_threshold": cluster_thr,
                              "clusters": len(clusters), "top_clusters": clusters[:40], "clusters_serving_3plus_videos": sum(1 for c in clusters if c["videos"] >= 3)}
    if candidates:
        cands = json.load(open(candidates))["images"]
        dv = embed_texts([c["description"] for c in cands], "search_document", profile, region, cache)
        sims = qv @ dv.T   # phrases x images
        per = []
        for j, c in enumerate(cands):
            hit = [p for p in phrases if sims[idx[p], j] >= threshold]
            vs = set().union(*(vids_of[p] for p in hit)) if hit else set()
            per.append({"id": c["id"], "title": c["title"], "phrases": len(hit), "searches": sum(count[p] for p in hit), "videos": len(vs), "examples": sorted(hit, key=lambda p: -sims[idx[p], j])[:6]})
        report["candidates"] = sorted(per, key=lambda c: (-c["videos"], -c["searches"]))
        report["coverage"] = {}
        order = sorted(range(len(cands)), key=lambda j: -len({v for p in phrases if sims[idx[p], j] >= threshold for v in vids_of[p]}))
        for thr in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55):
            best = sims.max(axis=1)
            sat = sum(count[p] for p in phrases if best[idx[p]] >= thr)
            report["coverage"][f"{thr:.2f}"] = {"searches_satisfied": sat, "percent": round(100 * sat / len(rows), 1), "phrases_satisfied": int((best >= thr).sum())}
        # the distribution of the best score per phrase (to pick the threshold knowingly)
        best = sims.max(axis=1)
        report["best_score_percentiles"] = {str(q): round(float(np.percentile(best, q)), 3) for q in (10, 25, 50, 75, 90)}
        report["images_ranked_by_videos"] = [cands[j]["id"] for j in order[:20]]
        report["unserved_examples"] = [p for p in sorted(phrases, key=lambda p: -len(vids_of[p])) if best[idx[p]] < threshold][:40]
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("top_clusters", "candidates", "unserved_examples")}, indent=1))


def against_images(queries: str, store_spec: str, out: str, profile: str, region: str, cache: str) -> None:
    """Cross-modal measurement: the director's real phrases (search_query) against the REAL image vectors (search_document) of a catalog store. This is the score the engine will see."""
    os.environ["AWS_PROFILE"] = profile
    from common.catalog_store import open_store

    store = open_store(store_spec)
    imgs = store.images()
    mat = np.array([store.get_vector(i["id"])[0] for i in imgs], dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    rows = json.load(open(queries))["rows"]
    phrases = sorted({r["phrase"] for r in rows})
    qv = embed_texts(phrases, "search_query", profile, region, cache)
    sims = qv @ mat.T
    best = sims.max(axis=1)
    cnt = collections.Counter(r["phrase"] for r in rows)
    total = sum(cnt.values())
    rep: Dict[str, Any] = {"images": len(imgs), "phrases": len(phrases), "searches": total, "best_score_percentiles": {str(q): round(float(np.percentile(best, q)), 3) for q in (10, 25, 50, 75, 90, 99)},
                           "coverage_by_threshold": {f"{t:.2f}": round(100 * sum(cnt[p] for p, b in zip(phrases, best) if b >= t) / total, 1) for t in (0.15, 0.20, 0.25, 0.30, 0.35, 0.40)}, "per_image": []}
    for j, im in enumerate(imgs):
        order = np.argsort(-sims[:, j])[:8]
        rep["per_image"].append({"id": im["id"][:12], "title": im.get("title"), "top": [(phrases[i], round(float(sims[i, j]), 3)) for i in order]})
    json.dump(rep, open(out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "per_image"}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--out", required=True)
    e.add_argument("--profile", default="qa")
    e.add_argument("--region", default="eu-west-1")
    a = sub.add_parser("analyze")
    a.add_argument("--queries", required=True)
    a.add_argument("--candidates", default="")
    a.add_argument("--out", required=True)
    a.add_argument("--profile", default="qa")
    a.add_argument("--region", default="eu-west-1")
    a.add_argument("--cache", default="")
    a.add_argument("--threshold", type=float, default=0.40)
    a.add_argument("--cluster-threshold", type=float, default=0.62)
    i = sub.add_parser("images")
    i.add_argument("--queries", required=True)
    i.add_argument("--store", required=True)
    i.add_argument("--out", required=True)
    i.add_argument("--profile", default="qa")
    i.add_argument("--region", default="eu-west-1")
    i.add_argument("--cache", default="")
    args = ap.parse_args()
    if args.cmd == "images":
        against_images(args.queries, args.store, args.out, args.profile, args.region, args.cache)
    elif args.cmd == "extract":
        extract(args.out, args.profile, args.region)
    else:
        analyze(args.queries, args.candidates, args.out, args.profile, args.region, args.cache, args.threshold, args.cluster_threshold)


if __name__ == "__main__":
    main()
