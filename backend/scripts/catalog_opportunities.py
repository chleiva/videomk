#!/usr/bin/env python3
"""The demand loop of the image catalog (docs/IMAGE_CATALOG.md, section 4): what did the director search for that the catalog did not serve well, and which ONE new image would answer a whole group of those searches?
READ-ONLY against the demand table (and the catalog vectors); writes a report and a PLAN that catalog_generate.py consumes directly. Generates nothing; spends only a few cents of text embeddings and one small-model call per cluster.

  catalog_opportunities.py --stage qa --catalog local:/path --report out/report.json --plan out/next_plan.json [--window-days 90] [--last-n 200]
  catalog_opportunities.py --fixture docs/image_catalog/demand_queries.json --catalog local:/path --report r.json --plan p.json --no-model     # offline rows, no table

The rule (owner): when the director searches for the same thing (similar meaning, not the same words) in 3 or more completely different videos and the catalog did not serve it well, that is an opportunity
for one image. Steps:
 1. Rows are (phrase, video) pairs from the demand table: outcome catalog | rejected | none (| stock) and the best catalog score at that search. With --catalog, the score is recomputed against the CURRENT
    catalog vectors, so an image added since the search is credited; without it the logged score is used. A row is SERVED when the outcome is `catalog` (or, recomputed, the score reaches the serve threshold).
 2. Missed or weak rows (not served) are embedded with Cohere (search_query, the same helper as the catalog) and clustered (greedy leader, cosine >= CLUSTER_THRESHOLD).
 3. A cluster is an opportunity when it holds >= --min-videos DISTINCT videos with a missed row (one video asking 47 times counts once) and its best catalog match is below the serve threshold (or most of its
    misses were `rejected` by the verifier: a match existed but did not fit). A cluster that is mostly served is not an opportunity.
 4. Each opportunity gets a proposed generic subject (small model; a specific landmark, species, person or brand is refused), member phrases, distinct videos, miss rate, expected savings, a priority score.
"""
import argparse
import collections
import datetime
import json
import math
import os
import sys
from typing import Any, Callable, Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
sys.path.insert(0, HERE)

from catalog_plan import PER_IMAGE_USD, SUBJECT_SYSTEM  # noqa: E402

SERVE_THRESHOLD = 0.35      # = common.catalog.DEFAULT_MIN_SCORE (measured, docs section 7): the lowest score the director will even verify
NEAR_MISS_FLOOR = 0.25      # a miss whose best score is in [0.25, 0.35) is a near miss: measured "loosely right" matches were 0.33-0.40, wrong ones 0.29 and below
# Cosine between two Cohere search_query vectors. 0.62 is the value measured on the QA demand data (docs section 2.1): at 0.62 the five wordings of "honeycomb with honey" and the eight of the
# Eiffel Tower fall together while different scenes (a lake at dawn vs a sunrise at sea) stay apart; 393 phrases gave 268 clusters. Lower values start merging neighbouring scenes (one image could not
# serve both); higher values split wordings of the same scene so that no cluster reaches three videos. Leader clustering is deterministic: phrases are visited in order of distinct videos.
CLUSTER_THRESHOLD = 0.62
STOCK_COST_PER_SEARCH_USD = 0.003   # estimated: the stock path reviews about 6 candidates with the small vision model (about USD 0.0004 each, measured in the pilot); the stock APIs themselves are free
MISS_OUTCOMES = ("none", "rejected", "stock")


def prepare(rows: List[Dict[str, Any]], *, serve: float, phrase_scores: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Normalise demand rows: {phrase, video, searches, outcome, score, served}. With `phrase_scores` (recomputed against the current catalog) the score and the served flag come from it."""
    out = []
    for r in rows:
        ph = str(r["phrase"])
        n = int(r.get("searches", 1) or 1)
        logged = r.get("score", r.get("best_score"))
        score = phrase_scores[ph] if phrase_scores is not None and ph in phrase_scores else (float(logged) if logged is not None else 0.0)
        outcome = str(r.get("outcome") or "")
        served = (score >= serve and outcome != "rejected") if phrase_scores is not None else outcome == "catalog"
        if not outcome:
            outcome = "catalog" if served else "none"
        out.append({"phrase": ph, "video": str(r["video"]), "searches": n, "outcome": outcome, "score": score, "served": served, "last_seen": float(r.get("last_seen", 0) or 0)})
    return out


def health(rows: List[Dict[str, Any]], *, serve: float, last_n: int, recomputed: bool) -> Dict[str, Any]:
    """Hit rate, near-miss rate and 'how many of the last N searches the existing catalog would have served' (rows are phrase x video, weighted by their search counts)."""
    total = sum(r["searches"] for r in rows) or 0
    if not total:
        return {"searches": 0, "rows": 0}
    logged_hit = sum(r["searches"] for r in rows if r["outcome"] == "catalog")
    served = sum(r["searches"] for r in rows if r["served"])
    near = sum(r["searches"] for r in rows if not r["served"] and (r["outcome"] == "rejected" or NEAR_MISS_FLOOR <= r["score"] < serve))
    recent = sorted(rows, key=lambda r: -r["last_seen"])
    taken, got, n = 0, 0, 0
    for r in recent:
        if taken >= last_n:
            break
        take = min(r["searches"], last_n - taken)
        taken += take
        got += take if r["served"] else 0
    return {"searches": total, "rows": len(rows), "distinct_videos": len({r["video"] for r in rows}), "serve_threshold": serve, "scores": "recomputed against the current catalog" if recomputed else "as logged at search time",
            "hit_rate_logged": round(logged_hit / total, 4), "hit_rate": round(served / total, 4), "near_miss_rate": round(near / total, 4), "miss_rate": round(1 - served / total, 4),
            "last_n": taken, "last_n_served": got, "last_n_served_rate": round(got / taken, 4) if taken else 0.0}


def cluster_leaders(vecs: np.ndarray, thr: float) -> List[int]:
    """Greedy leader clustering by cosine (vectors are unit length): the first phrase of a group leads it; later phrases join the most similar leader at or above `thr`."""
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


def analyse(rows: List[Dict[str, Any]], *, embed_queries: Callable[[List[str]], np.ndarray], catalog_vectors: Optional[np.ndarray] = None, ask: Optional[Callable[[str, str], str]] = None,
            serve: float = SERVE_THRESHOLD, cluster_thr: float = CLUSTER_THRESHOLD, min_videos: int = 3, min_phrases: int = 1, last_n: int = 200, max_items: int = 25,
            stock_cost: float = STOCK_COST_PER_SEARCH_USD, per_image_usd: float = PER_IMAGE_USD, window_days: int = 90, plan_id: str = "") -> Dict[str, Any]:
    """-> {report, plan}. `embed_queries(phrases)` -> unit vectors (Cohere search_query); `catalog_vectors` (n x d, unit) are the CURRENT catalog image vectors (None: use the logged scores)."""
    phrases_all = sorted({str(r["phrase"]) for r in rows})
    qv_all = embed_queries(phrases_all) if phrases_all else np.zeros((0, 1))
    index = {p: i for i, p in enumerate(phrases_all)}
    scores = None
    if catalog_vectors is not None and len(catalog_vectors) and len(phrases_all):
        best = (qv_all @ catalog_vectors.T).max(axis=1)
        scores = {p: float(best[index[p]]) for p in phrases_all}
    elif catalog_vectors is not None and len(phrases_all):
        scores = {p: 0.0 for p in phrases_all}      # an empty catalog serves nothing
    prows = prepare(rows, serve=serve, phrase_scores=scores)
    rep: Dict[str, Any] = {"generated": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z", "window_days": window_days,
                           "thresholds": {"serve": serve, "near_miss_floor": NEAR_MISS_FLOOR, "cluster_cosine": cluster_thr, "min_distinct_videos": min_videos}}
    rep["health"] = health(prows, serve=serve, last_n=last_n, recomputed=scores is not None)
    missed = [r for r in prows if not r["served"]]
    by_phrase: Dict[str, Dict[str, Any]] = {}
    for r in prows:
        d = by_phrase.setdefault(r["phrase"], {"videos": set(), "miss_videos": set(), "searches": 0, "miss_searches": 0, "rejected": 0, "best": 0.0})
        d["videos"].add(r["video"])
        d["searches"] += r["searches"]
        if not r["served"]:
            d["miss_videos"].add(r["video"])
            d["miss_searches"] += r["searches"]
            d["rejected"] += r["searches"] if r["outcome"] == "rejected" else 0
            d["best"] = max(d["best"], r["score"])
    mp = sorted({r["phrase"] for r in missed}, key=lambda p: (-len(by_phrase[p]["miss_videos"]), -by_phrase[p]["miss_searches"], p))
    groups: Dict[int, List[str]] = collections.defaultdict(list)
    if mp:
        labels = cluster_leaders(np.array([qv_all[index[p]] for p in mp]), cluster_thr)
        for p, l in zip(mp, labels):
            groups[l].append(p)
    clusters = []
    for ps in groups.values():
        miss_vids = set().union(*(by_phrase[p]["miss_videos"] for p in ps))
        all_vids = set().union(*(by_phrase[p]["videos"] for p in ps))
        searches = sum(by_phrase[p]["searches"] for p in ps)
        miss_searches = sum(by_phrase[p]["miss_searches"] for p in ps)
        rejected = sum(by_phrase[p]["rejected"] for p in ps)
        best = max(by_phrase[p]["best"] for p in ps)
        # the cluster's rows that were served (in the same cluster, by phrases not in the missed list) are not counted here; the miss rate is over the rows of the member phrases
        miss_rate = len(miss_vids) / len(all_vids)
        reason = "below the serve threshold" if best < serve else ("most misses were rejected by the verifier" if rejected * 2 >= miss_searches and rejected else "")
        clusters.append({"phrases": sorted(ps, key=lambda p: (-len(by_phrase[p]["miss_videos"]), p)), "distinct_videos": len(miss_vids), "videos_asking": len(all_vids), "searches": searches, "miss_searches": miss_searches,
                         "miss_rate": round(miss_rate, 3), "best_catalog_score": round(best, 3), "qualifies": len(miss_vids) >= min_videos and len(ps) >= min_phrases and bool(reason), "reason": reason})
    for c in clusters:
        c["expected_savings_usd"] = round(c["miss_searches"] * stock_cost, 4)
        c["priority"] = round(c["distinct_videos"] * c["miss_rate"] * (1 + math.log10(max(1, c["miss_searches"]))), 3)
    clusters.sort(key=lambda c: (-c["priority"], -c["distinct_videos"], c["phrases"][0]))
    rep["top_uncovered_clusters"] = [{k: c[k] for k in ("phrases", "distinct_videos", "miss_rate", "best_catalog_score", "priority", "qualifies")} for c in clusters[:10]]
    ops = [c for c in clusters if c["qualifies"]]
    items: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    for c in ops:
        info: Dict[str, Any] = {}
        if ask:
            try:
                import re
                m = re.search(r"\{.*\}", ask(SUBJECT_SYSTEM, "Search phrases:\n- " + "\n- ".join(c["phrases"][:12])), flags=re.S)
                info = json.loads(m.group(0)) if m else {}
            except Exception:
                info = {}
            if info.get("generic") is not True:
                refused.append({"phrases": c["phrases"][:5], "distinct_videos": c["distinct_videos"], "why": "not generic (a specific landmark, species, person or brand), or unreadable"})
                continue
        if len(items) >= max_items:
            break
        items.append({"id": f"o{len(items) + 1:03d}", "title": info.get("title") or c["phrases"][0], "category": info.get("category") or "", "subject": info.get("subject") or c["phrases"][0], "people": bool(info.get("people")),
                      "serves": c["phrases"][:8], "distinct_videos": c["distinct_videos"], "miss_rate": c["miss_rate"], "priority": c["priority"], "expected_savings_usd": c["expected_savings_usd"],
                      "best_catalog_score": c["best_catalog_score"], "needs_review": not ask, "estimated_usd": round(per_image_usd, 4)})
    for it in items:
        it["payback_in_searches"] = round(it["estimated_usd"] / stock_cost) if stock_cost else None
    rep["opportunities"] = [{**it, "members": next(c["phrases"] for c in ops if c["phrases"][:8] == it["serves"])} for it in items]
    rep["refused_clusters"] = refused[:20]
    rep["notes"] = ("Savings are the stock-review cost avoided (about USD %.4f per search, estimated) over this window; the main value of a catalog image is a consistent, checked picture and a faster beat, "
                    "so payback is also given in searches." % stock_cost)
    plan = {"plan_id": plan_id or "opps-" + datetime.date.today().isoformat(), "approved_by": "", "created": rep["generated"], "estimated_total_usd": round(per_image_usd * len(items), 2), "items": items,
            "source": "catalog_opportunities.py: review, edit, then set approved_by"}
    return {"report": rep, "plan": plan}


def catalog_matrix(store) -> Optional[np.ndarray]:
    vecs = [store.get_vector(i)[0] for i in store.vector_ids() if store.get_vector(i)]
    if not vecs:
        return np.zeros((0, 1024), np.float32)
    m = np.array(vecs, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def load_rows(fixture: str, stage: str, window_days: int) -> List[Dict[str, Any]]:
    if fixture:
        return json.load(open(fixture))["rows"]
    from catalog_plan import demand_rows_from_table
    return demand_rows_from_table(stage, window_days)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="qa", help="qa | prod: the demand table to read (read-only)")
    ap.add_argument("--fixture", default="", help="a demand file ({rows:[{phrase, video, outcome?, score?}]}) instead of the table")
    ap.add_argument("--catalog", default="", help="qa | prod | local:<folder>: recompute scores against the current catalog images (else the logged scores are used)")
    ap.add_argument("--report", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--last-n", type=int, default=200)
    ap.add_argument("--min-videos", type=int, default=3)
    ap.add_argument("--min-phrases", type=int, default=1)
    ap.add_argument("--max-items", type=int, default=25)
    ap.add_argument("--serve-threshold", type=float, default=SERVE_THRESHOLD)
    ap.add_argument("--cluster-threshold", type=float, default=CLUSTER_THRESHOLD)
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--profile", default="qa")
    ap.add_argument("--cache", default="")
    a = ap.parse_args()
    os.environ["AWS_PROFILE"] = a.profile
    os.environ["BEDROCK_REGION"] = "eu-west-1"
    from catalog_demand import embed_texts

    rows = load_rows(a.fixture, a.stage, a.window_days)
    cv = None
    if a.catalog:
        from common.catalog_store import open_store
        cv = catalog_matrix(open_store(a.catalog))
    ask = None
    if not a.no_model:
        from engine import llm
        ask = lambda s, u: llm.complete(s, u, max_tokens=500, temperature=0.0, model=llm.REVIEW_MODEL, effort="low")[0]   # noqa: E731
    out = analyse(rows, embed_queries=lambda ps: embed_texts(ps, "search_query", a.profile, "eu-west-1", a.cache), catalog_vectors=cv, ask=ask, serve=a.serve_threshold, cluster_thr=a.cluster_threshold,
                  min_videos=a.min_videos, min_phrases=a.min_phrases, last_n=a.last_n, max_items=a.max_items, window_days=a.window_days)
    json.dump(out["report"], open(a.report, "w"), ensure_ascii=False, indent=1)
    json.dump(out["plan"], open(a.plan, "w"), ensure_ascii=False, indent=1)
    h = out["report"]["health"]
    print(json.dumps(h))
    print(f"{len(out['plan']['items'])} opportunities (about ${out['plan']['estimated_total_usd']} to generate). Review {a.plan}, set approved_by, then catalog_generate.py. Nothing was generated.")


if __name__ == "__main__":
    main()
