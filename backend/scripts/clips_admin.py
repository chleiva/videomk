#!/usr/bin/env python3
"""Library clips on demand: the owner's knobs, the library and the report (docs/CLIPS_ON_DEMAND.md). Needs AWS credentials for the stage's account; nothing here is
reachable through the API. A store is `qa`, `prod` or `local:<folder>`.

  python backend/scripts/clips_admin.py config show [--stage qa]            every knob: its value now, its default
  python backend/scripts/clips_admin.py config set enabled true             change one knob (checked before it is saved; live within a minute, no deploy). `enabled false` = the kill switch
  python backend/scripts/clips_admin.py config reset platform_day_usd       back to the default

  python backend/scripts/clips_admin.py list   --store qa                   the library: id, age, uses, distinct videos, brief
  python backend/scripts/clips_admin.py report --store qa [--days 30]       generated, rejected by reason, spend by day and account, cap hits, budget stops, latency, reuse rate, misses
  python backend/scripts/clips_admin.py sheet  --store qa --out sheet.jpg   a contact sheet of the posters (newest first) for a human look
  python backend/scripts/clips_admin.py retire <id> --store qa              take a clip out of search (the file stays); `restore <id>` brings it back
  python backend/scripts/clips_admin.py reindex --store qa                  rebuild missing index rows from the metadata documents in the bucket
  python backend/scripts/clips_admin.py promote --from qa --to prod [--ids a,b] [--no-dry-run] [--yes-prod]
                                                                            copy clips WITHOUT generating, checking or embedding again (never paid twice); dry run by default
Defaults to stage qa; prod asks you to type prod before it changes anything.
"""
import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from common import clip_config as cc, clip_store as cs   # noqa: E402


def _confirm_prod(what: str) -> None:
    if input(f"This changes PRODUCTION ({what}). Type prod to go on: ").strip() != "prod":
        sys.exit("stopped")


def _ssm(stage: str):
    import boto3
    cfg = cs.STAGES[stage]
    return boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"]).client("ssm"), f"/videomk/{stage}/clips/config"


def _raw(ssm, name: str) -> dict:
    try:
        return json.loads(ssm.get_parameter(Name=name)["Parameter"]["Value"] or "{}")
    except ssm.exceptions.ParameterNotFound:
        return {}


def cmd_config(a) -> None:
    ssm, name = _ssm(a.stage)
    raw = _raw(ssm, name)
    if a.action == "show":
        clean = cc.clean_config(raw)
        print(f"{name}  ({'set' if raw else 'not set: every default, generation off'})")
        for k, (default, kind, lo, hi) in cc.KNOBS.items():
            mark = "*" if k in raw and clean[k] != default else " "
            print(f" {mark} {k:<24} {json.dumps(clean[k]):<34} default {json.dumps(default)}")
        print("\n  monthly Max allowance now: $%.2f   yearly: $%.2f   one 8 s generation: $%.3f" % (cc.account_allowance_usd("month", 0, clean), cc.account_allowance_usd("year", 0, clean), cc.price_usd(clean["clip_seconds"], clean)))
        return
    if a.knob not in cc.KNOBS:
        sys.exit(f"unknown knob {a.knob!r}; one of: {', '.join(cc.KNOBS)}")
    if a.action == "set":
        try:
            raw[a.knob] = cc.coerce(a.knob, json.loads(a.value) if a.value[:1] in "[{" else a.value)
        except ValueError as e:
            sys.exit(str(e))
    else:
        raw.pop(a.knob, None)
    if a.stage == "prod":
        _confirm_prod(f"{a.action} {a.knob}")
    ssm.put_parameter(Name=name, Value=json.dumps(raw, sort_keys=True), Type="String", Overwrite=True)
    print(f"{a.knob} = {json.dumps(cc.clean_config(raw)[a.knob])}  (live within a minute)")


def _age_days(row: dict, now: float) -> float:
    return (now - float(row.get("created") or now)) / 86400


def cmd_list(a) -> None:
    store, now = cs.open_store(a.store), time.time()
    rows = sorted(store.query(cs.LIB), key=lambda r: -float(r.get("created") or 0))
    for r in rows:
        print(f"{r['sk'][:12]}  {_age_days(r, now):5.1f} d  uses {int(r.get('uses') or 0):3d}  videos {len(r.get('videos') or []):3d}  {r.get('aspect', ''):5} {float(r.get('seconds') or 0):4.1f} s  "
              f"{r.get('status', 'active'):8} {str(r.get('brief', ''))[:90]}")
    print(f"{len(rows)} clips in {store.label}")


def report(store: cs.Store, days: int = 30, now: float = None) -> dict:
    """Everything the owner asked to see, as one dictionary (the command prints it)."""
    now = time.time() if now is None else now
    months = sorted({cs.month(now - d * 86400) for d in range(days + 1)})
    since = now - days * 86400
    ledger = [r for m in months for r in store.query(cs.ledger_pk(m)) if float(r.get("at") or 0) >= since]
    made = [r for r in ledger if r.get("outcome") == "generated"]
    rejected = [r for r in ledger if r.get("outcome") == "gate_rejected"]
    reasons: dict = {}
    for r in ledger:
        if r.get("outcome") not in ("generated", "started"):
            key = f"{r.get('outcome')}:{r.get('reason')}"
            reasons[key] = reasons.get(key, 0) + 1
    lat = sorted(float(r["latency_s"]) for r in ledger if r.get("latency_s") is not None and r.get("outcome") in ("generated", "gate_rejected"))
    by_account: dict = {}
    for r in ledger:
        by_account[r.get("account", "?")] = round(by_account.get(r.get("account", "?"), 0.0) + float(r.get("charged_usd") or 0), 4)
    spend_day = {k: {r["sk"]: cs.usd(r.get("spent")) for r in store.query(cs.spend_pk(k, "day")) if r["sk"] >= cs.day(since)} for k in ("paid", "test")}
    spend_month = {k: {r["sk"]: cs.usd(r.get("spent")) for r in store.query(cs.spend_pk(k, "month")) if r["sk"] in months} for k in ("paid", "test")}
    stats: dict = {}
    for r in store.query(cs.STATS):
        if r["sk"] >= cs.day(since):
            for k, v in r.items():
                if k[:2] in ("d_", "g_") or k[:4] in ("cap_", "used"):
                    stats[k] = stats.get(k, 0) + int(v or 0)
    lib_rows = [r for r in store.query(cs.LIB)]
    active = [r for r in lib_rows if r.get("status", "active") == "active"]
    old = [r for r in active if _age_days(r, now) > 30]
    misses = [r for r in old if len(r.get("videos") or []) < 2]
    demand = sorted((r for r in store.query(cs.DEMAND)), key=lambda r: -len(r.get("videos") or []))
    have = {str(r.get("brief")) for r in active}
    return {
        "days": days, "generations": len([r for r in ledger if r.get("outcome") != "started"]), "unfinished": len([r for r in ledger if r.get("outcome") == "started"]),
        "kept": len(made), "rejected": len(rejected), "rejection_rate": round(len(rejected) / max(1, len(made) + len(rejected)), 3), "not_kept_by_reason": reasons,
        "spend_usd": round(sum(float(r.get("charged_usd") or 0) for r in ledger), 4), "cost_per_kept_clip_usd": round(sum(float(r.get("charged_usd") or 0) for r in ledger) / max(1, len(made)), 3),
        "spend_by_day": spend_day, "spend_by_month": spend_month, "spend_by_account": dict(sorted(by_account.items(), key=lambda t: -t[1])[:20]),
        "decisions": {k[2:]: v for k, v in stats.items() if k.startswith("d_")}, "cap_hits": {k[4:]: v for k, v in stats.items() if k.startswith("cap_")},
        "budget_stops": sum(v for k, v in stats.items() if k in ("cap_platform_day", "cap_platform_month", "cap_test_day", "cap_test_month")),
        "used": {k[5:]: v for k, v in stats.items() if k.startswith("used_")},
        "latency_s": {"p50": lat[len(lat) // 2] if lat else None, "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None, "max": lat[-1] if lat else None},
        "library": {"clips": len(active), "retired": len(lib_rows) - len(active), "uses": sum(int(r.get("uses") or 0) for r in active),
                    "invested_usd": round(sum(float(r.get("cost_usd") or 0) for r in lib_rows), 2)},
        "reuse": {"older_than_30_days": len(old), "misses": len(misses), "miss_rate": round(len(misses) / len(old), 3) if old else None,
                  "miss_list": [{"id": r["sk"][:12], "videos": len(r.get("videos") or []), "brief": r.get("brief")} for r in misses[:30]]},
        "top_clips": [{"id": r["sk"][:12], "videos": len(r.get("videos") or []), "uses": int(r.get("uses") or 0), "brief": r.get("brief")}
                      for r in sorted(active, key=lambda r: -len(r.get("videos") or []))[:10]],
        "asked_without_a_clip": [{"videos": len(r.get("videos") or []), "asks": int(r.get("asks") or 0), "brief": r.get("brief")} for r in demand if r.get("brief") not in have][:15],
    }


def cmd_report(a) -> None:
    rep = report(cs.open_store(a.store), a.days)
    if a.json:
        print(json.dumps(rep, indent=1, ensure_ascii=False))
        return
    print(f"Library clips on demand, last {rep['days']} days")
    print(f"  generations {rep['generations']} (kept {rep['kept']}, rejected by the gate {rep['rejected']}, rate {rep['rejection_rate']:.0%}; unfinished {rep['unfinished']})")
    print(f"  spend ${rep['spend_usd']:.2f}   per kept clip ${rep['cost_per_kept_clip_usd']:.2f}   latency p50 {rep['latency_s']['p50']} s, p95 {rep['latency_s']['p95']} s")
    print(f"  not kept: {rep['not_kept_by_reason'] or 'none'}")
    print(f"  decisions: {rep['decisions']}")
    print(f"  CAP HITS: {rep['cap_hits'] or 'none'}   BUDGET STOPS: {rep['budget_stops']}")
    for kind in ("paid", "test"):
        print(f"  spend by day ({kind}): {rep['spend_by_day'][kind] or 'none'}   by month: {rep['spend_by_month'][kind] or 'none'}")
    print(f"  spend by account (salted): {rep['spend_by_account'] or 'none'}")
    lib_ = rep["library"]
    print(f"  library: {lib_['clips']} clips ({lib_['retired']} retired), ${lib_['invested_usd']:.2f} invested, {lib_['uses']} uses; used in videos: {rep['used'] or 'none'}")
    r = rep["reuse"]
    print(f"  REUSE: {r['older_than_30_days']} clips older than 30 days, {r['misses']} used by fewer than 2 videos (miss rate {r['miss_rate'] if r['miss_rate'] is not None else 'n/a: no clip is 30 days old yet'}; target under 0.40)")
    for m in r["miss_list"]:
        print(f"     miss {m['id']}  videos {m['videos']}  {m['brief']}")
    for c in rep["top_clips"]:
        print(f"     top  {c['id']}  videos {c['videos']}  uses {c['uses']}  {c['brief']}")
    for d in rep["asked_without_a_clip"]:
        print(f"     asked by {d['videos']} videos, no clip: {d['brief']}")


def cmd_sheet(a) -> None:
    from PIL import Image, ImageDraw
    store = cs.open_store(a.store)
    rows = sorted((r for r in store.query(cs.LIB) if r.get("status", "active") == "active"), key=lambda r: -float(r.get("created") or 0))[:a.limit]
    cols, w, h = 4, 320, 180
    sheet = Image.new("RGB", (cols * w, max(1, -(-len(rows) // cols)) * (h + 34)), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        im = Image.open(io.BytesIO(store.get_object(f"p/{r['sk']}.jpg"))).convert("RGB")
        im.thumbnail((w, h))
        x, y = (i % cols) * w, (i // cols) * (h + 34)
        sheet.paste(im, (x + (w - im.width) // 2, y))
        d.text((x + 4, y + h + 2), f"{r['sk'][:10]}  v{len(r.get('videos') or [])}", fill=(255, 255, 255))
        d.text((x + 4, y + h + 16), str(r.get("brief", ""))[:52], fill=(190, 190, 190))
    sheet.save(a.out, quality=85)
    print(f"{len(rows)} clips -> {a.out}")


def _full_id(store: cs.Store, short: str) -> str:
    hits = [r["sk"] for r in store.query(cs.LIB) if r["sk"].startswith(short)]
    if len(hits) != 1:
        sys.exit(f"{len(hits)} clips start with {short!r}")
    return hits[0]


def cmd_status(a) -> None:
    from engine import clip_library as lib
    store = cs.open_store(a.store)
    if store.label == "prod":
        _confirm_prod(f"{a.cmd} {a.id}")
    lib.set_status(store, _full_id(store, a.id), "retired" if a.cmd == "retire" else "active")
    print("done")


def cmd_reindex(a) -> None:
    from engine import clip_library as lib
    print(f"{lib.reindex(cs.open_store(a.store))} index rows created")


def cmd_promote(a) -> None:
    from engine import clip_library as lib
    src, dst = cs.open_store(a.src), cs.open_store(a.dst)
    if dst.label == "prod" and not a.dry_run and not a.yes_prod:
        sys.exit("promotion to prod needs --yes-prod")
    out = lib.promote(src, dst, [i for i in (a.ids or "").split(",") if i] or None, dry_run=a.dry_run)
    for o in out:
        print(f"{o['id'][:12]}  {o['action']:<16} {o.get('brief', '')}")
    print(f"{sum(1 for o in out if o['action'] in ('copied', 'would copy'))} clips {'would be ' if a.dry_run else ''}copied from {src.label} to {dst.label}; nothing was generated or embedded")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("action", choices=["show", "set", "reset"])
    c.add_argument("knob", nargs="?")
    c.add_argument("value", nargs="?")
    c.add_argument("--stage", default="qa", choices=list(cs.STAGES))
    c.set_defaults(fn=cmd_config)
    for name, fn in (("list", cmd_list), ("report", cmd_report), ("sheet", cmd_sheet), ("retire", cmd_status), ("restore", cmd_status), ("reindex", cmd_reindex)):
        s = sub.add_parser(name)
        if name in ("retire", "restore"):
            s.add_argument("id")
        s.add_argument("--store", default="qa")
        if name == "report":
            s.add_argument("--days", type=int, default=30)
            s.add_argument("--json", action="store_true")
        if name == "sheet":
            s.add_argument("--out", required=True)
            s.add_argument("--limit", type=int, default=48)
        s.set_defaults(fn=fn)
    s = sub.add_parser("promote")
    s.add_argument("--from", dest="src", required=True)
    s.add_argument("--to", dest="dst", required=True)
    s.add_argument("--ids")
    s.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    s.add_argument("--yes-prod", action="store_true")
    s.set_defaults(fn=cmd_promote)
    a = p.parse_args()
    if a.cmd == "config" and a.action != "show" and (not a.knob or (a.action == "set" and a.value is None)):
        sys.exit("config set <knob> <value> | config reset <knob>")
    a.fn(a)


if __name__ == "__main__":
    main()
