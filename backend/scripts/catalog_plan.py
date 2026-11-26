#!/usr/bin/env python3
"""The next batch of catalog images, from real demand (docs/IMAGE_CATALOG.md, "Feedback loop"). Writes a PLAN for the owner to approve; generates NOTHING and spends nothing but a few
cents of embeddings and one small-model call per candidate.

  catalog_plan.py --stage qa --out next_plan.json [--catalog qa|prod|local:<dir>] [--min-videos 3] [--max-items 25] [--since-days 90]
  catalog_plan.py --demand-json rows.json --catalog local:<dir> --out plan.json        # offline (rows: {phrase, video, searches})

Takes the demand table (generic phrases and salted video hashes, see common/catalog_privacy.py), drops the phrases the catalog already answers (best score of the phrase against the
catalog's vectors >= --covered), clusters the rest by meaning, and keeps clusters asked by at least --min-videos DIFFERENT videos with at least --min-phrases different wordings: one image
that serves three or more completely different prompts. A small model turns each cluster into a generic, reusable subject (or says the cluster is a specific landmark, species, person or brand,
which is not catalog material) and the plan says what each image would cost (measured USD 0.044 per generation, times 1.5 for the re-run of rejected pictures). The owner edits, then sets `approved_by` before catalog_generate.py will run it.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
sys.path.insert(0, HERE)

GENERATION_USD = 0.044     # measured: gpt-image-2.6-flare 2048x1152 high = 1413 output tokens + prompt (docs/IMAGE_CATALOG.md section 0)
CHECK_USD, EMBED_USD = 0.0005, 0.0005
RETRY_FACTOR = 1.5         # measured on the pilot: 10 generations for 6 kept items (rejected items are re-run once)
PER_IMAGE_USD = (GENERATION_USD + CHECK_USD + EMBED_USD) * RETRY_FACTOR   # expected cost of one KEPT image

SUBJECT_SYSTEM = """You turn a cluster of search phrases that a video director used into ONE reusable stock image for a library shared by many videos.
Answer ONLY with JSON: {"generic": true|false, "title": "<3-6 words>", "category": "<one of: nature, sky, work, city, food, people, animals, science, money, history, travel, mood>",
"subject": "<one sentence describing a single photograph: the scene, light and place type, no style words>", "people": true|false}
`generic` is false when the cluster is about a specific named landmark, building, species, person, brand, event or artwork (a library image of it would be wrong or risky), or when no single photograph
could serve all the phrases. The subject must not name a real person, brand or private place; any people are small, from behind or hands only; no text in the scene."""


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{phrase: {videos:set, searches:int, answered:int}} from demand rows (a row = one phrase of one video)."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = out.setdefault(r["phrase"], {"videos": set(), "searches": 0, "answered": 0})
        d["videos"].add(r["video"])
        d["searches"] += int(r.get("searches", 1))
        if r.get("outcome") == "catalog":
            d["answered"] += int(r.get("searches", 1))
    return out


def plan_from_rows(rows: List[Dict[str, Any]], *, embed_queries: Callable[[List[str]], np.ndarray], catalog_vectors: np.ndarray, ask: Optional[Callable[[str, str], str]],
                   covered: float = 0.40, cluster_thr: float = 0.62, min_videos: int = 3, min_phrases: int = 3, max_items: int = 25, plan_id: str = "") -> Dict[str, Any]:
    from catalog_demand import cluster

    agg = aggregate(rows)
    phrases = sorted(agg)
    report: Dict[str, Any] = {"phrases": len(phrases)}
    if not phrases:
        return {"plan_id": plan_id, "approved_by": "", "items": [], "report": report}
    qv = embed_queries(phrases)
    best = (qv @ catalog_vectors.T).max(axis=1) if len(catalog_vectors) else np.zeros(len(phrases))
    open_idx = [i for i in range(len(phrases)) if best[i] < covered]
    report.update({"already_covered": len(phrases) - len(open_idx), "open": len(open_idx)})
    labels = cluster(qv[open_idx], cluster_thr) if open_idx else []
    groups: Dict[int, List[str]] = collections.defaultdict(list)
    for i, l in zip(open_idx, labels):
        groups[l].append(phrases[i])
    cands = []
    for ps in groups.values():
        vids = set().union(*(agg[p]["videos"] for p in ps))
        if len(vids) >= min_videos and len(set(ps)) >= min_phrases:
            cands.append((len(vids), sum(agg[p]["searches"] for p in ps), ps))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    report["clusters_over_threshold"] = len(cands)
    items: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for nv, ns, ps in cands:
        top = sorted(ps, key=lambda p: -len(agg[p]["videos"]))
        info: Dict[str, Any] = {}
        if ask:
            try:
                m = re.search(r"\{.*\}", ask(SUBJECT_SYSTEM, "Search phrases:\n- " + "\n- ".join(top[:12])), flags=re.S)
                info = json.loads(m.group(0)) if m else {}
            except Exception:
                info = {}
        if ask and info.get("generic") is not True:
            rejected.append({"phrases": top[:5], "videos": nv, "why": "not generic (a specific landmark, species, person or brand) or unreadable"})
            continue
        if len(items) >= max_items:
            break
        items.append({"id": f"n{len(items) + 1:03d}", "title": info.get("title") or top[0], "category": info.get("category") or "", "subject": info.get("subject") or top[0], "people": bool(info.get("people")),
                      "serves": top[:8], "distinct_videos": nv, "searches": ns,
                      "needs_review": not ask, "estimated_usd": round(PER_IMAGE_USD, 4)})
    report["rejected_clusters"] = rejected[:20]
    return {"plan_id": plan_id or "plan-" + datetime.date.today().isoformat(), "approved_by": "", "created": datetime.datetime.utcnow().isoformat() + "Z", "min_videos": min_videos,
            "estimated_total_usd": round(PER_IMAGE_USD * len(items), 2), "items": items, "report": report}


def demand_rows_from_table(stage: str, since_days: int) -> List[Dict[str, Any]]:
    import boto3
    from common.catalog_store import names

    cfg = {"qa": ("qa", "eu-west-1"), "prod": ("default", "us-west-2")}[stage]
    sess = boto3.Session(profile_name=cfg[0], region_name=cfg[1])
    tbl_name = [t for t in sess.client("dynamodb").list_tables()["TableNames"] if "DemandTable" in t and f"videomk-{stage}" in t]
    if len(tbl_name) != 1:
        sys.exit(f"demand table not found in {stage} (is the image catalog deployed?)")
    t = sess.resource("dynamodb").Table(tbl_name[0])
    cutoff = datetime.datetime.utcnow().timestamp() - since_days * 86400
    out, kw = [], {}
    while True:
        r = t.scan(**kw)
        out += [{"phrase": i["phrase"], "video": i["video"], "searches": int(i.get("searches", 1)), "outcome": i.get("outcome", ""), "score": float(i.get("best_score", 0)), "last_seen": float(i.get("last_seen", 0))} for i in r["Items"] if float(i.get("last_seen", 0)) >= cutoff]
        if not r.get("LastEvaluatedKey"):
            return out
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="")
    ap.add_argument("--demand-json", default="")
    ap.add_argument("--catalog", default="qa", help="where the existing images are: qa, prod or local:<folder>")
    ap.add_argument("--out", required=True)
    ap.add_argument("--since-days", type=int, default=90)
    ap.add_argument("--min-videos", type=int, default=3)
    ap.add_argument("--min-phrases", type=int, default=3)
    ap.add_argument("--max-items", type=int, default=25)
    ap.add_argument("--covered", type=float, default=0.40, help="a phrase whose best catalog score is at least this is already served")
    ap.add_argument("--no-model", action="store_true", help="skip the small-model step (items are marked needs_review)")
    ap.add_argument("--profile", default="qa")
    ap.add_argument("--cache", default="")
    a = ap.parse_args()
    os.environ["AWS_PROFILE"] = a.profile
    os.environ["BEDROCK_REGION"] = "eu-west-1"
    from catalog_demand import embed_texts
    from common.catalog_store import open_store

    rows = json.load(open(a.demand_json))["rows"] if a.demand_json else demand_rows_from_table(a.stage or "qa", a.since_days)
    store = open_store(a.catalog)
    vecs = [store.get_vector(i)[0] for i in store.vector_ids() if store.get_vector(i)]
    cv = np.array(vecs, dtype=np.float32) if vecs else np.zeros((0, 1024), np.float32)
    if len(cv):
        cv /= np.linalg.norm(cv, axis=1, keepdims=True)
    ask = None
    if not a.no_model:
        from engine import llm
        ask = lambda s, u: llm.complete(s, u, max_tokens=500, temperature=0.0, model=llm.REVIEW_MODEL, effort="low")[0]   # noqa: E731
    plan = plan_from_rows(rows, embed_queries=lambda ps: embed_texts(ps, "search_query", a.profile, "eu-west-1", a.cache), catalog_vectors=cv, ask=ask,
                          covered=a.covered, min_videos=a.min_videos, min_phrases=a.min_phrases, max_items=a.max_items)
    json.dump(plan, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(plan['items'])} proposed images, about ${plan.get('estimated_total_usd', 0)} to generate; report: {json.dumps(plan['report'])[:300]}\nNothing was generated. Review {a.out}, then set approved_by and run catalog_generate.py.")


if __name__ == "__main__":
    main()
