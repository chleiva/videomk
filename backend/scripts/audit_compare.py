#!/usr/bin/env python3
"""Before/after table of two audit runs folders (no network, no cost).
  python backend/scripts/audit_compare.py docs/audit/2026-11-25 docs/audit/2026-11-25-after  ->  markdown on stdout
Each folder holds `runs/*.json` written by quality_audit.py. The screen/narration mismatch is recomputed on BOTH sets with the strict (QUALITY_FIXES=0) rule, so the
comparison does not reward the looser checker.
"""
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
import quality_audit as qa  # noqa: E402

DIMS = [k for k, _ in qa.DIMS]


def load(folder):
    qa.RUNS_DIR = os.path.join(folder, "runs")
    return qa.load_runs()


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def js(r, d):
    return ((r.get("judge") or {}).get("scores") or {}).get(d, {}).get("score")


def strict_mismatch(r):
    from engine import sync
    old = os.environ.get("QUALITY_FIXES")
    os.environ["QUALITY_FIXES"] = "0"
    try:
        return len(sync.coverage_problems(r["plan"]["beats"]))
    finally:
        if old is None:
            os.environ.pop("QUALITY_FIXES", None)
        else:
            os.environ["QUALITY_FIXES"] = old


def metrics(runs):
    ok = [r for r in runs if r.get("plan")]
    m = {"runs": len(runs), "with a plan": len(ok), "failures (no plan)": len(runs) - len(ok)}
    nl = [r["research"].get("notes_len") or 0 for r in ok]
    m["notes chars, median"] = round(st.median(nl))
    m["notes chars, mean"] = round(sum(nl) / len(nl))
    m["videos with no notes (0 chars)"] = sum(1 for x in nl if x == 0)
    m["videos with thin notes (< 1,500 chars)"] = sum(1 for x in nl if x < 1500)
    m["videos citing no source"] = sum(1 for r in ok if not (r["plan"].get("sources") or []))
    m["sources cited, median"] = st.median([len(r["plan"].get("sources") or []) for r in ok])
    for name, sel in (("all", ok), ("en", [r for r in ok if r["language"] == "en"]), ("es", [r for r in ok if r["language"] == "es"])):
        m[f"ungrounded numbers and names, mean share ({name})"] = f"{round(100 * (mean([r['rules']['grounding']['ungrounded_share'] for r in sel]) or 0))}%"
    m["judge accuracy defects (all / major)"] = "%d / %d" % (sum(len([d for d in (r.get('judge') or {}).get('defects') or [] if d.get('dimension') == 'accuracy']) for r in ok),
                                                          sum(len([d for d in (r.get('judge') or {}).get('defects') or [] if d.get('dimension') == 'accuracy' and d.get('severity') in ('major', 'critical')]) for r in ok))
    m["videos reading 'the notes' aloud"] = sum(1 for r in ok if any(__import__("re").search(r"\b(the|our) notes\b|\blas notas\b", b.get("narration") or "", __import__("re").I) for b in r["plan"]["beats"]))
    for d in DIMS:
        m[f"judge {d}, mean (all)"] = mean([js(r, d) for r in ok])
    m["judge mean of means (all)"] = mean([(r.get("judge") or {}).get("mean") for r in ok])
    es = [r for r in ok if r["language"] == "es"]
    m["judge mean of means (es)"] = mean([(r.get("judge") or {}).get("mean") for r in es])
    m["judge accuracy (es)"] = mean([js(r, "accuracy") for r in es])
    m["judge language (es)"] = mean([js(r, "language") for r in es])
    m["judge naturalness es"] = mean([((r.get("judge") or {}).get("spanish") or {}).get("naturalness") for r in es])
    for mins in (1, 2):
        sel = [r for r in ok if r["minutes"] == mins]
        if sel:
            m[f"est. speech time / target, {mins} min (median, max; n={len(sel)})"] = "%.2f, %.2f" % (st.median([r["rules"]["length"]["est_speech_s"] / (mins * 60) for r in sel]), max(r["rules"]["length"]["est_speech_s"] / (mins * 60) for r in sel))
            m[f"narration words / expected, {mins} min (median)"] = round(st.median([r["rules"]["length"]["ratio"] for r in sel]), 2)
    m["all lengths: est. speech / target (median, p90)"] = "%.2f, %.2f" % (st.median([r["rules"]["length"]["est_speech_s"] / (r["minutes"] * 60) for r in ok]), pct([r["rules"]["length"]["est_speech_s"] / (r["minutes"] * 60) for r in ok], 0.9))
    m["flag too_long"] = sum(1 for r in ok if r["rules"]["length"]["flag_long"])
    m["flag too_short"] = sum(1 for r in ok if r["rules"]["length"]["flag_short"])
    m["within +/-7% of expected words"] = sum(1 for r in ok if abs(r["rules"]["length"]["ratio"] - 1) <= 0.07)
    m["videos with screen/narration mismatch (looser checker, as warned)"] = sum(1 for r in ok if r["rules"]["warnings"].get("coverage", 0))
    m["videos with screen/narration mismatch (strict rule on the final plan)"] = sum(1 for r in ok if strict_mismatch(r))
    m["videos with scenes replaced as invalid"] = sum(1 for r in ok if r["rules"]["warnings"].get("scene_replaced", 0))
    cost, secs = [r["cost"]["total"] for r in ok], [r["timings"]["total_s"] for r in ok]
    m["plan cost per video, median / p90 / total (USD)"] = "%.3f / %.3f / %.2f" % (st.median(cost), pct(cost, .9), sum(cost))
    m["plan latency, median / p90 (s)"] = "%.0f / %.0f" % (st.median(secs), pct(secs, .9))
    m["judge cost total (USD)"] = round(sum((r.get("judge") or {}).get("cost_usd", 0) for r in ok), 2)
    m["web research used (videos)"] = sum(1 for r in ok if r["research"].get("mode") == "web")
    m["escalations from thin encyclopedia notes"] = sum(1 for r in ok if r["research"].get("escalated"))
    m["videos with Wikipedia fetch errors (logged)"] = sum(1 for r in ok if r["research"].get("fetch_errors_n"))
    g = [r["research"].get("grounding") for r in ok if r["research"].get("grounding")]
    if g:
        m["grounding check: beats flagged / repaired (total)"] = "%d / %d (videos with a model call: %d)" % (sum(x["flagged"] for x in g), sum(x["repaired"] for x in g), sum(1 for x in g if x["calls"]))
    m["hook_greeting / close_generic flags"] = "%d / %d" % (sum(1 for r in ok if "hook_greeting" in r["rules"]["flags"]), sum(1 for r in ok if "close_generic" in r["rules"]["flags"]))
    m["wrong language"] = sum(1 for r in ok if r["rules"]["language"]["flag_wrong"])
    return m


def main():
    a, b = sys.argv[1], sys.argv[2]
    ra, rb = load(a), load(b)
    ids = {r["id"] for r in rb}
    ra_same = [r for r in ra if r["id"] in ids]   # the same prompts only
    ma, mb = metrics(ra_same), metrics(rb)
    print("| metric | before | after |\n|---|---|---|")
    for k in mb:
        print(f"| {k} | {ma.get(k, '-')} | {mb[k]} |")
    print("\n## Per prompt (judge mean before -> after; est. speech / target; notes chars)")
    print("| id | min | judge before | judge after | speech/target before | after | notes before | after | flags after |")
    print("|---|---|---|---|---|---|---|---|---|")
    ia = {r["id"]: r for r in ra}
    for r in sorted(rb, key=lambda r: r["id"]):
        o = ia.get(r["id"])
        if not r.get("plan"):
            print(f"| {r['id']} | {r['minutes']:g} | - | FAILED: {str(r.get('error') or r.get('reason'))[:60]} | | | | | |")
            continue
        sp = lambda x: round(x["rules"]["length"]["est_speech_s"] / (x["minutes"] * 60), 2)
        print(f"| {r['id']} | {r['minutes']:g} | {(o.get('judge') or {}).get('mean', '-') if o else '-'} | {(r.get('judge') or {}).get('mean', '-')} | {sp(o) if o and o.get('plan') else '-'} | {sp(r)} | "
              f"{(o or {}).get('research', {}).get('notes_len', '-')} | {r['research'].get('notes_len')} | {', '.join(r['rules']['flags']) or '-'} |")


if __name__ == "__main__":
    main()
