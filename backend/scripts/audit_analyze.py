#!/usr/bin/env python3
"""Aggregates the saved audit runs into markdown tables and statistics (no network, no cost).
  python backend/scripts/audit_analyze.py  ->  docs/audit/2026-11-25/tables.md and stats.json
"""
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "docs", "audit", "2026-11-25")
sys.path.insert(0, HERE)
import quality_audit as qa  # noqa: E402

DIMS = [k for k, _ in qa.DIMS]


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


def jscore(r, d):
    return ((r.get("judge") or {}).get("scores") or {}).get(d, {}).get("score")


def main():
    global OUT
    if len(sys.argv) > 1:   # python audit_analyze.py <folder with runs/>: tables.md is written next to it
        OUT = os.path.abspath(sys.argv[1])
        qa.RUNS_DIR = os.path.join(OUT, "runs")
    runs = qa.load_runs()
    ok = [r for r in runs if r.get("plan")]
    bad = [r for r in runs if not r.get("plan")]
    L = []
    w = L.append
    w(f"Runs: {len(runs)}; with a plan: {len(ok)}; failed or declined: {len(bad)}")
    for r in bad:
        w(f"- {r['id']}: {r.get('error') or r.get('reason')}")
    w("")
    w("## Per prompt")
    w("| id | cat | lang | min | words/exp | beats | scene types | ungrounded % | sources | mode (searches/reads) | notes chars | flags | judge mean | acc | cov | struct | hook | tone | vis | orig | instr | lang | publish | cost $ | sec |")
    w("|" + "---|" * 25)
    for r in sorted(ok, key=lambda r: (r["category"], r["id"])):
        ru, j = r["rules"], r.get("judge") or {}
        res = r["research"]
        w(f"| {r['id']} | {r['category'].split(' (')[0]} | {r['language']} | {r['minutes']:g} | {ru['length']['words']}/{ru['length']['expected_words']} | {ru['length']['beats']} | {ru['variety']['distinct']} | "
          f"{round(ru['grounding']['ungrounded_share'] * 100)} | {ru['sources']['cited']}/{res.get('n_fetched')} | {res.get('mode')} ({res.get('searches') or 0}/{res.get('reads') or 0}) | {res.get('notes_len')} | "
          f"{', '.join(ru['flags']) or '-'} | {j.get('mean', '-')} | " + " | ".join(str(jscore(r, d) or "-") for d in DIMS) + f" | {'Y' if j.get('would_publish') else 'N'} | {r['cost']['total']:.3f} | {r['timings']['total_s']:.0f} |")
    w("")
    w("## Per category (mean judge score per dimension, rule metrics)")
    w("| category | n | judge mean | " + " | ".join(DIMS) + " | ungrounded % | median words ratio | flags per video | publish (judge) |")
    w("|" + "---|" * (len(DIMS) + 7))
    bycat = defaultdict(list)
    for r in ok:
        bycat[r["category"]].append(r)
    for c, rs in sorted(bycat.items(), key=lambda kv: mean([(r.get("judge") or {}).get("mean") for r in kv[1]]) or 0):
        w(f"| {c} | {len(rs)} | {mean([(r.get('judge') or {}).get('mean') for r in rs])} | " + " | ".join(str(mean([jscore(r, d) for r in rs])) for d in DIMS) +
          f" | {round(100 * mean([r['rules']['grounding']['ungrounded_share'] for r in rs]))} | {round(st.median([r['rules']['length']['ratio'] for r in rs]), 2)} | {mean([len(r['rules']['flags']) for r in rs])} | "
          f"{sum(1 for r in rs if (r.get('judge') or {}).get('would_publish'))}/{len(rs)} |")
    w("")
    w("## Judge means by dimension (all / en / es) and by length")
    for name, sel in [("all", ok), ("en", [r for r in ok if r["language"] == "en"]), ("es", [r for r in ok if r["language"] == "es"]),
                      ("1-2 min", [r for r in ok if r["minutes"] <= 2]), ("3 min", [r for r in ok if r["minutes"] == 3]), ("4-5 min (staged)", [r for r in ok if r["minutes"] >= 4]),
                      ("web research", [r for r in ok if r["research"].get("mode") == "web"]), ("encyclopedia", [r for r in ok if r["research"].get("mode") != "web"])]:
        w(f"- {name} (n={len(sel)}): mean {mean([(r.get('judge') or {}).get('mean') for r in sel])}; " + ", ".join(f"{d} {mean([jscore(r, d) for r in sel])}" for d in DIMS) +
          f"; ungrounded {round(100 * (mean([r['rules']['grounding']['ungrounded_share'] for r in sel]) or 0))}%; publish {sum(1 for r in sel if (r.get('judge') or {}).get('would_publish'))}/{len(sel)}")
    w("")
    flags = Counter(f for r in ok for f in r["rules"]["flags"])
    w("## Rule flags (frequency over videos)")
    for f, n in flags.most_common():
        ids = [r["id"] for r in ok if f in r["rules"]["flags"]]
        w(f"- {f}: {n}/{len(ok)} ({', '.join(ids[:12])}{'...' if len(ids) > 12 else ''})")
    w("")
    w("## Judge defects by dimension and severity")
    dc = Counter()
    for r in ok:
        for d in (r.get("judge") or {}).get("defects") or []:
            dc[(d.get("dimension"), d.get("severity"))] += 1
    bydim = defaultdict(Counter)
    for (d, s), n in dc.items():
        bydim[d][s] += n
    for d, c in sorted(bydim.items(), key=lambda kv: -sum(kv[1].values())):
        w(f"- {d}: {sum(c.values())} (critical {c['critical']}, major {c['major']}, minor {c['minor']})")
    w("")
    costs = [r["cost"]["total"] for r in ok]
    secs = [r["timings"]["total_s"] for r in ok]
    jc = [(r.get("judge") or {}).get("cost_usd", 0) for r in ok]
    w("## Cost and latency")
    w(f"- plan cost per video: median ${st.median(costs):.3f}, p90 ${pct(costs, .9):.3f}, max ${max(costs):.3f}, total ${sum(costs):.2f}; judge total ${sum(jc):.2f}")
    w(f"- latency per video: median {st.median(secs):.0f}s, p90 {pct(secs, .9):.0f}s, max {max(secs):.0f}s")
    for name, sel in [("1-2 min", [r for r in ok if r["minutes"] <= 2]), ("3 min", [r for r in ok if r["minutes"] == 3]), ("4-5 min (staged)", [r for r in ok if r["minutes"] >= 4]),
                      ("web", [r for r in ok if r["research"].get("mode") == "web"]), ("encyclopedia", [r for r in ok if r["research"].get("mode") != "web"])]:
        if sel:
            c, s = [r["cost"]["total"] for r in sel], [r["timings"]["total_s"] for r in sel]
            w(f"- {name} (n={len(sel)}): cost median ${st.median(c):.3f} p90 ${pct(c, .9):.3f}; latency median {st.median(s):.0f}s p90 {pct(s, .9):.0f}s")
    parts = Counter()
    for r in ok:
        for k, v in r["cost"].items():
            if k != "total":
                parts[k] += v
    w("- cost by part: " + ", ".join(f"{k} ${v:.2f}" for k, v in parts.most_common()))
    w("")
    w("## Research")
    modes = Counter(r["research"].get("mode") for r in ok)
    w(f"- modes: {dict(modes)}; fallbacks: {[r['id'] for r in ok if r['research'].get('fallback')]}; research errors: {[(r['id'], r['research'].get('error')) for r in ok if r['research'].get('error')]}")
    w(f"- notes length: median {st.median([r['research']['notes_len'] for r in ok]):.0f} chars; under 1500 chars: {[r['id'] for r in ok if r['research']['notes_len'] < 1500]}")
    ts = [r for r in ok if r.get("time_sensitive")]
    w("- time-sensitive prompts: " + "; ".join(f"{r['id']} mode={r['research'].get('mode')} searches={r['research'].get('searches')} sources={r['rules']['sources']['cited']} acc={jscore(r, 'accuracy')}" for r in ts))
    w("- decided=web for non-time-sensitive prompts: " + str([r['id'] for r in ok if r['research'].get('mode') == 'web' and not r.get('time_sensitive')]))
    w("- encyclopedia sources (Wikipedia titles) per video: median " + str(st.median([r['research']['n_sources'] for r in ok if r['research'].get('mode') != 'web'] or [0])))
    sk = Counter(s for r in ok for s in (r["research"].get("skills") or []))
    w(f"- skills chosen: {dict(sk.most_common())}")
    w("")
    w("## Scene types used (all beats)")
    sc = Counter(t for r in ok for t, n in r["rules"]["variety"]["counts"].items() for _ in range(n))
    tot = sum(sc.values())
    w(", ".join(f"{t} {n} ({round(100 * n / tot)}%)" for t, n in sc.most_common()))
    w("")
    w("## Judge vs rules (correlation of judge accuracy with ungrounded share)")
    xs = [(r["rules"]["grounding"]["ungrounded_share"], jscore(r, "accuracy")) for r in ok if jscore(r, "accuracy")]
    if len(xs) > 3:
        try:
            w(f"- Pearson r (ungrounded share vs judge accuracy) = {st.correlation([a for a, _ in xs], [b for _, b in xs]):.2f} over {len(xs)} videos")
        except Exception:
            pass
    with open(os.path.join(OUT, "tables.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
