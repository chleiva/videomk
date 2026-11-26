#!/usr/bin/env python3
"""Measure how much stock-video supply each source gives for realistic scene queries (docs/CLIPS.md, "Measured supply").

Read-only and cheap: search calls to the free APIs (Pixabay needs its key from SSM `/videomk/pixabay_api_key`, QA account), no downloads in
the supply phase. Per source it reports: candidates returned (after the provider's own licence/orientation/size filters, exactly what `clips.gather`
sees), how many are >= 5 s and >= 1080p, the median duration, orientation, and the share of queries with at least one usable candidate.
With --pass-sample N it then runs the real review (poster frames) and verify (3 frames) on N queries and reports what share finally passes
(a few cents of model calls on the QA account, plus ~10 MB of downloads per sampled clip).

  AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/clip_supply.py [--pass-sample 12] [--max-cost 0.60] [--json out.json]
Only the QA account is allowed.
"""
import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Callable, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

# (query as the planner writes it, alt wording, narration for the review/verify sample). Mixed topics, English and Spanish.
QUERIES = [
    ("waves crashing on rocky coast", "ocean surf on cliffs", "The sea has shaped this coastline for millions of years, one wave at a time."),
    ("aerial view of a forest", "drone over green trees", "Forests cover almost a third of the land on Earth."),
    ("city traffic at night", "cars on a busy street, lights", "Every evening the streets fill with light and movement."),
    ("hands typing on laptop", "person working at a computer", "Most of us spend our days working at a keyboard."),
    ("bees on flowers", "honey bee pollinating", "Bees move pollen from flower to flower, and crops depend on it."),
    ("chef cooking in a kitchen", "pan cooking vegetables", "The best dishes start with simple ingredients and a hot pan."),
    ("lava flowing from volcano", "volcano eruption", "When pressure builds up, magma finds a way out."),
    ("ancient ruins at sunset", "old stone temple", "The ruins still stand where a great city once did."),
    ("storm clouds timelapse", "dark clouds moving over fields", "Storms form when warm, moist air rises quickly."),
    ("microscope laboratory research", "scientist pipetting samples", "Scientists test a hypothesis by repeating the experiment."),
    ("busy market street", "people shopping at a market", "Markets are where a city's daily life becomes visible."),
    ("solar panels on a roof", "wind turbines and solar farm", "Renewable energy is now the cheapest in many places."),
    ("elephants walking in savanna", "african wildlife herd", "Elephants travel in family herds led by the oldest female."),
    ("earth from space", "planet rotating satellite view", "From orbit the Earth looks calm, but its systems never stop."),
    ("coffee beans harvest", "farmer picking coffee cherries", "Every cup of coffee starts on a farm thousands of miles away."),
    ("train passing through mountains", "railway in the alps", "The railway connected two valleys that had been isolated for centuries."),
    ("meeting in an office", "team discussing around a table", "Good teams spend time talking before they build."),
    ("old books in a library", "pages turning historical documents", "For centuries, knowledge lived in handwritten books."),
    ("rocket launch", "space shuttle liftoff", "A rocket burns tons of fuel in the first minutes of flight."),
    ("rain falling on a window", "raindrops on leaves", "Rain is part of the water cycle that never stops."),
    ("olas rompiendo en la playa", "mar y espuma en la orilla", "El mar nunca se detiene: sube y baja con cada marea."),
    ("mercado de frutas y verduras", "puesto de fruta en un mercado", "En los mercados se compra lo que la tierra da cada temporada."),
    ("bosque con niebla", "árboles entre la niebla en la mañana", "El bosque despierta lento cuando la niebla se levanta."),
    ("ciudad al atardecer", "vista aérea de una ciudad al anochecer", "Cuando cae la tarde, la ciudad cambia de ritmo."),
    ("agricultor cosechando trigo", "tractor en un campo de cultivo", "El trigo se cosecha a finales del verano, cuando el grano está seco."),
]


def _orientation(c: Dict[str, Any]) -> str:
    r = c["width"] / max(1, c["height"])
    return "landscape" if r >= 1.3 else "portrait" if r <= 0.85 else "square"


def internet_archive_eval(query: str, fetch: Callable[..., Any], limit: int = 8) -> List[Dict[str, Any]]:
    """EVALUATION ONLY (not a provider in clips.py): Internet Archive movies with a CC0 / Public Domain Mark licence URL, <= 70 MB MP4, >= 1280 px, >= 3 s."""
    import urllib.parse
    lic = '(licenseurl:"http://creativecommons.org/publicdomain/zero/1.0/" OR licenseurl:"http://creativecommons.org/publicdomain/mark/1.0/")'
    q = urllib.parse.urlencode([("q", f"mediatype:movies AND {lic} AND ({query})"), ("fl[]", "identifier"), ("fl[]", "title"), ("rows", limit), ("output", "json")])
    docs = (fetch(f"https://archive.org/advancedsearch.php?{q}").get("response") or {}).get("docs") or []
    out = []
    for d in docs:
        try:
            files = fetch(f"https://archive.org/metadata/{d['identifier']}").get("files") or []
        except Exception:
            continue
        for f in files:
            try:
                if f.get("format") in ("MPEG4", "h.264", "h.264 HD") and int(f.get("width") or 0) >= 1280 and float(f.get("length") or 0) >= 3 and int(f.get("size") or 0) <= 70_000_000:
                    out.append({"id": d["identifier"], "width": int(f["width"]), "height": int(f["height"]), "duration": float(f["length"]), "title": d.get("title")})
                    break
            except (ValueError, TypeError):
                continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass-sample", type=int, default=0, help="run the real review + verify on this many queries (model calls on QA)")
    ap.add_argument("--max-cost", type=float, default=0.60)
    ap.add_argument("--json", default="")
    ap.add_argument("--queries", type=int, default=len(QUERIES))
    args = ap.parse_args()
    profile = os.environ.setdefault("AWS_PROFILE", "qa")
    if profile != "qa":
        sys.exit(f"refusing to run with AWS_PROFILE={profile}: only the QA account (profile qa) may be used")
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    os.environ["CLIPS_COMMONS"] = "1"   # search works without contact details in the User-Agent; only downloads are throttled
    import boto3
    from engine import clips
    from engine.netsafe import fetch_json

    key = boto3.Session(profile_name="qa", region_name="eu-west-1").client("ssm").get_parameter(Name="/videomk/pixabay_api_key", WithDecryption=True)["Parameter"]["Value"]
    providers: Dict[str, Callable[..., List[Dict[str, Any]]]] = {
        "pixabay": lambda q, **o: clips.pixabay_search(q, key, fetch_json, **o),
        "commons": lambda q, **o: clips.commons_search(q, fetch_json),
    }
    if hasattr(clips, "nasa_search"):
        providers["nasa"] = lambda q, **o: clips.nasa_search(q, fetch_json, **o)
    if hasattr(clips, "pexels_search"):
        providers["pexels"] = lambda q, **o: clips.pexels_search(q, "", fetch_json, **o)   # no key exists: always 0 until /videomk/pexels_api_key is stored
    stats: Dict[str, Dict[str, Any]] = {n: {"cands": [], "hd5": [], "queries_with": 0, "errors": 0} for n in providers}
    ia: List[int] = []
    qs = QUERIES[: args.queries]
    for q, alt, _ in qs:
        for name, fn in providers.items():
            try:
                got = fn(q)
                hd = fn(q, hd=True) if name in ("pixabay", "nasa", "pexels") else got   # the 1080p rendition is only picked for hd=True; Commons returns the original
            except Exception as e:
                stats[name]["errors"] += 1
                print(f"  {name} failed for {q!r}: {type(e).__name__}", file=sys.stderr)
                continue
            got = [c for c in got if c["duration"] >= clips.MIN_SOURCE_SECONDS]
            s = stats[name]
            s["cands"] += got
            s["hd5"] += [c for c in hd if c["duration"] >= 5 and max(c["width"], c["height"]) >= 1920]
            s["queries_with"] += 1 if [c for c in hd if c["duration"] >= 5 and max(c["width"], c["height"]) >= 1920] else 0
        try:
            ia.append(len(internet_archive_eval(q, fetch_json)))
        except Exception:
            ia.append(0)
        time.sleep(0.3)
    print(f"\nSUPPLY for {len(qs)} queries (English and Spanish; 'usable' = >= 5 s and >= 1080p long side)\n")
    print(f"{'source':9} {'cands/query':>11} {'usable/query':>13} {'queries with usable':>20} {'median s':>9} {'orientation':>22} {'errors':>6}")
    report: Dict[str, Any] = {}
    for name, s in stats.items():
        n = len(qs)
        orient: Dict[str, int] = {}
        for c in s["cands"]:
            orient[_orientation(c)] = orient.get(_orientation(c), 0) + 1
        med = statistics.median([c["duration"] for c in s["cands"]]) if s["cands"] else 0
        report[name] = {"cands_per_query": round(len(s["cands"]) / n, 2), "usable_per_query": round(len(s["hd5"]) / n, 2), "queries_with_usable": f"{s['queries_with']}/{n}", "median_s": med, "orientation": orient, "errors": s["errors"]}
        print(f"{name:9} {len(s['cands']) / n:11.1f} {len(s['hd5']) / n:13.1f} {s['queries_with']:>17}/{n} {med:9.1f} {json.dumps(orient):>22} {s['errors']:6d}")
    print(f"internet-archive (CC0/PDM only, <=70 MB mp4, >=1280 px, evaluation only): {sum(ia) / len(ia):.1f} per query, {sum(1 for x in ia if x)}/{len(ia)} queries with any")
    report["internet_archive_eval"] = {"per_query": round(sum(ia) / len(ia), 2), "queries_with_any": sum(1 for x in ia if x)}

    if args.pass_sample:
        from engine import llm
        usage = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}
        real_complete = llm.complete

        def counting_complete(*a, **k):   # every review and verify call, including the ones whose clip was then thrown away
            text, meta = real_complete(*a, **k)
            usage["calls"] += 1
            usage["in"] += int(meta.get("tokens_in", 0))
            usage["out"] += int(meta.get("tokens_out", 0))
            usage["cost"] += float(meta.get("cost_usd", 0.0))
            return text, meta
        llm.complete = counting_complete
        tally = {"queries": 0, "gathered": 0, "no_candidates": 0, "too_short": 0, "rejected_by_review": 0, "verified_fail": 0, "passed": 0, "cost": 0.0, "verify_calls": 0, "review_calls": 0}
        per_source: Dict[str, Dict[str, int]] = {}
        step = max(1, len(qs) // args.pass_sample)
        for q, alt, narr in qs[::step][: args.pass_sample]:
            if tally["cost"] > args.max_cost:
                print("cost cap reached, stopping the sample")
                break
            tally["queries"] += 1
            counts = {"review": 0, "verify": 0}
            real_review, real_verify = clips._review, clips.verify

            def rv(*a, **k):
                counts["review"] += 1
                return real_review(*a, **k)

            def vf(*a, **k):
                counts["verify"] += 1
                return real_verify(*a, **k)

            os.environ["CLIPS_PASS_SAMPLE"] = "1"
            res = clips.scout_clip(q, narr, alt, need_seconds=5.0, pixabay_key=key, review=rv, verify_fn=vf)
            if res is None:
                tally["no_candidates"] += 1
                outcome, src = "none", "-"
            elif not res.get("mp4"):
                tally["rejected_by_review"] += 1
                outcome, src = "review-rejected", "-"
            else:
                tally["passed"] += 1
                outcome, src = "PASS", res["chosen"].split(":")[0]
                per_source[src] = {"passed": per_source.get(src, {}).get("passed", 0) + 1}
            cost = float((res or {}).get("review", {}).get("cost_usd", 0.0))
            tally["cost"] += cost
            tally["review_calls"] += counts["review"]
            tally["verify_calls"] += counts["verify"]
            print(f"  {q!r}: {outcome} {src}  candidates={len((res or {}).get('candidates', []))} review_calls={counts['review']} verify_calls={counts['verify']} cost=${cost:.4f}")
        t = tally["queries"] or 1
        print(f"\nPASS RATE: {tally['passed']}/{tally['queries']} queries end with a verified clip ({100 * tally['passed'] / t:.0f}%); review rejected all: {tally['rejected_by_review']}, nothing found/too short: {tally['no_candidates']}; passed by source {per_source}")
        print(f"model cost (measured from token counts, all calls): ${usage['cost']:.4f} for {usage['calls']} calls = {usage['in']} input / {usage['out']} output tokens; "
              f"${usage['cost'] / t:.4f} and {usage['calls'] / t:.1f} calls per scene")
        report["pass_sample"] = {**tally, "per_source": per_source, "usage": usage}
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
