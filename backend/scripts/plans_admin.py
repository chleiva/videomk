#!/usr/bin/env python3
"""Plans: the owner's knobs, the showcase gallery and the free-usage report (docs/PLANS.md). Needs AWS credentials for the stage's account; nothing here is reachable through the API.
(An account's plan is set with scripts/wallet_admin.py plan ...)

  python backend/scripts/plans_admin.py config show [--stage qa]                 every knob: its value now, its default, what it does
  python backend/scripts/plans_admin.py config set free_daily_budget_credits 30  change one knob (checked before it is saved; live within a minute, no deploy)
  python backend/scripts/plans_admin.py config set email_domain_deny "spam.example other.example"
  python backend/scripts/plans_admin.py config reset free_daily_budget_credits   back to the default
  python backend/scripts/plans_admin.py gallery-only on|off                      on: welcome_credits 0 and the daily credit off (Free accounts watch, a plan creates); off: the defaults

  python backend/scripts/plans_admin.py showcase list
  python backend/scripts/plans_admin.py showcase add <video id> --title-en "..." [--title-es "..."] [--desc-en "..."] [--desc-es "..."] [--show-prompt] [--poster poster.jpg] [--id forest]
  python backend/scripts/plans_admin.py showcase add --file cut.mp4 --id forest --title-en "..." --aspect 16:9 --seconds 28 [--width 1280 --height 720] [--prompt "..."] [--lang en]
  python backend/scripts/plans_admin.py showcase remove <id>
      `add <video id>` COPIES the finished video into showcase/<id>/ (its own folder: no expiry rule, not the customer area) and only takes a video whose owner is a staff account
      (the unlimited flag) unless you pass --made-by-us after checking yourself. Only what is in showcase/index.json is ever listed by GET /gallery.

  python backend/scripts/plans_admin.py report [--day 2026-11-27] [--days 7]     free against paid videos, what free usage cost per day and per user, the top free users, the
                                                                                 global budget, allowances granted and refused by reason, shared identities, top address blocks
  python backend/scripts/plans_admin.py disposable-refresh                       fetch the public CC0 list of disposable email domains again (then commit and deploy)
Defaults to stage qa; prod asks you to type prod before it changes anything.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from common import plan_report, plans  # noqa: E402

HERE = os.path.dirname(__file__)
LIST_URL = "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf"
COMMIT_URL = "https://api.github.com/repos/disposable-email-domains/disposable-email-domains/commits?per_page=1"
NOTES = {
    "enforce": "plan limits at the launcher (off: reported, not enforced)", "free_max_seconds": "longest Free video, seconds", "free_max_resolution": "highest Free resolution",
    "welcome_credits": "one-time welcome credits (0 = none)", "welcome_valid_days": "days the welcome credits last", "free_daily_credits": "recurring free credit (0 = off)",
    "free_credit_cadence": "daily, or weekly = at most free_credits_per_week claim days a week", "free_credits_per_week": "claim days a week when the cadence is weekly",
    "free_daily_budget_credits": "ALL free credits of ALL accounts per UTC day (0 = no free creation)", "free_budget_unlimited": "true = no global budget",
    "cost_per_credit_usd": "measured cost of one credit, to show dollars", "free_monthly_videos_cap": "free videos per account and month (0 = no cap)",
    "free_web": "may the web grant or spend free credits", "require_device_proof": "free creation needs a verified device proof (default: prod true, others false)",
    "device_proof_ios": "accept iOS App Attest", "device_check_ios": "use Apple DeviceCheck bits (needs the DeviceCheck key)", "device_proof_android": "accept Play Integrity (needs the service account)",
    "device_pass_minutes": "minutes a verified proof lasts", "block_disposable_email": "no allowance for disposable email domains", "email_domain_deny": "extra denied domains",
    "email_domain_allow": "domains taken out of the disposable list", "claims_per_ip_day": "allowances per IP address and day (0 = no limit)",
    "claims_per_ip_block_day": "allowances per /24 or /48 and day", "signups_per_ip_hour": "accounts first seen per IP address and hour", "claim_retention_days": "days a claim hash is kept",
}


def stage_session(stage: str, write: bool):
    cfg = json.load(open(os.path.join(HERE, "..", "stages.json")))[stage]
    if stage == "prod" and write and input("This changes PRODUCTION. Type 'prod': ") != "prod":
        sys.exit("cancelled")
    boto3.setup_default_session(profile_name=cfg["profile"], region_name=cfg["region"])
    return boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"]), cfg


def tables(session, stage: str) -> dict:
    names = [t for page in session.client("dynamodb").get_paginator("list_tables").paginate() for t in page["TableNames"] if t.startswith(f"videomk-{stage}-")]
    out = {}
    for key, part in (("videos", "VideosTable"), ("usage", "UsageTable"), ("flags", "AccountFlagsTable"), ("claims", "FreeClaimsTable"), ("entitlements", "EntitlementsTable")):
        got = [t for t in names if part in t]
        if len(got) != 1:
            sys.exit(f"expected one {part} for stage {stage}, found {got}")
        out[key] = got[0]
    return out


# ----------------------------------------------------------------------------- knobs
def read_raw(ssm, name: str) -> dict:
    try:
        return json.loads(ssm.get_parameter(Name=name)["Parameter"]["Value"] or "{}")
    except ssm.exceptions.ParameterNotFound:
        return {}   # never set: every default applies; the first `config set` creates it


def write_raw(ssm, name: str, raw: dict) -> None:
    ssm.put_parameter(Name=name, Value=json.dumps(raw, sort_keys=True), Type="String", Overwrite=True)


def config_cmd(a) -> None:
    session, _ = stage_session(a.stage, a.verb != "show")
    ssm, name = session.client("ssm"), f"/videomk/{a.stage}/plans/config"
    os.environ["PLANS_REQUIRE_DEVICE_PROOF_DEFAULT"] = "1" if a.stage == "prod" else "0"
    raw = read_raw(ssm, name)
    if a.verb == "set":
        if a.knob not in plans.KNOBS or a.value is None:
            sys.exit("usage: config set <knob> <value>   knobs: " + ", ".join(plans.KNOBS))
        value = a.value
        if plans.KNOBS[a.knob][1] in ("int", "float"):
            try:
                value = float(a.value) if plans.KNOBS[a.knob][1] == "float" else int(a.value)
            except ValueError:
                sys.exit(f"{a.knob} must be a number")
        try:
            raw[a.knob] = plans._coerce(a.knob, value)
        except ValueError as e:
            sys.exit(str(e))
        write_raw(ssm, name, raw)
        print(f"{a.knob} = {raw[a.knob]!r} on {a.stage} (live within a minute)")
    elif a.verb == "reset":
        if a.knob not in raw:
            sys.exit(f"{a.knob} is not set (the default applies)")
        raw.pop(a.knob)
        write_raw(ssm, name, raw)
        print(f"{a.knob} back to its default on {a.stage}")
    cfg = plans.clean_config(raw)
    print(f"\nKnobs of stage {a.stage} ({name}); * = changed from the default")
    for k, (default, _, _, _) in plans.KNOBS.items():
        d = plans.clean_config({})[k]
        print(f"  {'*' if k in raw and cfg[k] != d else ' '} {k:28s} {str(cfg[k]):22s} default {str(d):10s} {NOTES.get(k, '')}")
    if cfg["free_budget_unlimited"]:
        print("\nGlobal free budget: OFF (no ceiling on free spend)")
    else:
        day = plans.usd(cfg["free_daily_budget_credits"], cfg)
        print(f"\nGlobal free budget: {cfg['free_daily_budget_credits']} credits a day for all accounts = about ${day:.2f} a day, ${day * 31:.0f} a month at the very worst"
              f" (at ${cfg['cost_per_credit_usd']:.2f} per credit)")
    mode = "daily" if cfg["free_daily_credits"] else ("welcome" if cfg["welcome_credits"] else "none (gallery only)")
    print(f"Free plan offers: {mode}; device proof required: {cfg['require_device_proof']}; free on the web: {cfg['free_web']}")


def gallery_only_cmd(a) -> None:
    session, _ = stage_session(a.stage, True)
    ssm, name = session.client("ssm"), f"/videomk/{a.stage}/plans/config"
    raw = read_raw(ssm, name)
    if a.verb == "on":
        raw.update({"welcome_credits": 0, "free_daily_credits": 0})
    else:
        raw.pop("welcome_credits", None)
        raw.pop("free_daily_credits", None)
    write_raw(ssm, name, raw)
    print(f"gallery-only mode {a.verb.upper()} on {a.stage}: welcome_credits={plans.clean_config(raw)['welcome_credits']}, free_daily_credits={plans.clean_config(raw)['free_daily_credits']}")


# ----------------------------------------------------------------------------- showcase
INDEX_KEY = "showcase/index.json"


def read_index(s3, bucket: str) -> dict:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=INDEX_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"version": 1, "videos": []}


def showcase_cmd(a) -> None:
    session, cfg = stage_session(a.stage, a.verb != "list")
    s3 = session.client("s3")
    bucket = f"videomk-{a.stage}-{cfg['account']}"
    index = read_index(s3, bucket)
    if a.verb == "list":
        for v in index["videos"]:
            print(f"  {v['id']:20s} {v.get('aspect', '?'):5s} {v.get('seconds', 0):4d} s  {(v.get('title') or {}).get('en', '')}  [{v.get('source', '')}]")
        print(f"{len(index['videos'])} videos in the showcase of {a.stage}")
        return
    if a.verb == "remove":
        keep = [v for v in index["videos"] if v["id"] != a.target]
        if len(keep) == len(index["videos"]):
            sys.exit(f"no showcase video with id {a.target}")
        for obj in s3.list_objects_v2(Bucket=bucket, Prefix=f"showcase/{a.target}/").get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
        index["videos"] = keep
    else:
        if not a.title_en:
            sys.exit("add needs --title-en")
        entry = {"title": {"en": a.title_en, **({"es": a.title_es} if a.title_es else {})}, "description": {k: v for k, v in (("en", a.desc_en), ("es", a.desc_es)) if v},
                 "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if a.file:
            if not a.id or not a.aspect or not a.seconds:
                sys.exit("--file needs --id, --aspect and --seconds")
            sid = a.id
            s3.upload_file(a.file, bucket, f"showcase/{sid}/video.mp4", ExtraArgs={"ContentType": "video/mp4"})
            entry.update({"aspect": a.aspect, "seconds": int(a.seconds), "width": a.width, "height": a.height, "lang": a.lang or "en", "prompt": a.prompt, "source": "file"})
        else:
            t = tables(session, a.stage)
            ddb = session.resource("dynamodb")
            row = ddb.Table(t["videos"]).get_item(Key={"video_id": a.target}).get("Item")
            if not row or row.get("status") != "COMPLETE" or not str(row.get("video_uri", "")).startswith(f"s3://{bucket}/"):
                sys.exit(f"{a.target} is not a finished video of this stage")
            owner = ddb.Table(t["flags"]).get_item(Key={"user_id": row["user_id"]}).get("Item") or {}
            if owner.get("unlimited") is not True and not a.made_by_us:
                sys.exit("this video's owner is not a staff account. The showcase is for videos made by us: if it is one of ours, add --made-by-us")
            sid = a.id or str(a.target)[:12]
            src = str(row["video_uri"])[len(f"s3://{bucket}/"):]
            s3.copy_object(Bucket=bucket, Key=f"showcase/{sid}/video.mp4", CopySource={"Bucket": bucket, "Key": src}, ContentType="video/mp4", MetadataDirective="REPLACE",
                           TaggingDirective="REPLACE", Tagging="")   # its own copy with no tags: no expiry rule can reach it, and deleting the original changes nothing here
            entry.update({"aspect": row.get("aspect") or "16:9", "seconds": int(row.get("duration_s") or 0), "width": a.width, "height": a.height, "lang": a.lang or "en",
                          "prompt": (a.prompt or str(row.get("prompt") or "")) if (a.show_prompt or a.prompt) else None, "source": f"video:{a.target}"})
        if any(v["id"] == sid for v in index["videos"]):
            index["videos"] = [v for v in index["videos"] if v["id"] != sid]
        entry.update({"id": sid, "video_key": f"showcase/{sid}/video.mp4"})
        if a.poster:
            s3.upload_file(a.poster, bucket, f"showcase/{sid}/poster.jpg", ExtraArgs={"ContentType": "image/jpeg"})
            entry["poster_key"] = f"showcase/{sid}/poster.jpg"
        index["videos"].append(entry)
    index["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    s3.put_object(Bucket=bucket, Key=INDEX_KEY, Body=json.dumps(index, ensure_ascii=False, indent=1).encode("utf-8"), ContentType="application/json")
    print(f"showcase of {a.stage}: {len(index['videos'])} videos (GET /gallery shows the change within five minutes)")


# ----------------------------------------------------------------------------- report
def report_cmd(a) -> None:
    session, _ = stage_session(a.stage, False)
    t = tables(session, a.stage)
    ddb = session.resource("dynamodb")
    os.environ["PLANS_REQUIRE_DEVICE_PROOF_DEFAULT"] = "1" if a.stage == "prod" else "0"
    cfg = plans.clean_config(read_raw(session.client("ssm"), f"/videomk/{a.stage}/plans/config"))
    last = datetime.datetime.strptime(a.day, "%Y-%m-%d").date() if a.day else datetime.datetime.now(datetime.timezone.utc).date()
    usage, total_free, total_paid = ddb.Table(t["usage"]), 0.0, 0
    print(f"Free and paid usage, stage {a.stage} (cost per credit used for the estimate: ${cfg['cost_per_credit_usd']:.2f}; tracked = cost_usd on the video rows, without Lambda compute)")
    print(f"{'day':10s} {'free':>5s} {'paid':>5s} {'test':>5s} {'free users':>10s} {'free cr':>7s} {'budget':>9s} {'free $ est':>10s} {'free $ tracked':>14s} {'$ per free user':>15s} {'granted':>7s} {'refused':>7s}")
    for i in range(a.days - 1, -1, -1):
        day = (last - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        c = plan_report.day_counters(day, usage)
        r = plan_report.summarize(day, plan_report.videos_of_day(day, ddb.Table(t["videos"])), stats=c["stats"], budget_spent=c["budget_spent"], cfg=cfg)
        f = r["free"]
        total_free += f["estimated_usd"]
        total_paid += r["paid_videos"]
        budget = f"{c['budget_spent']}/{r['budget']['limit_credits'] if r['budget']['limit_credits'] is not None else '-'}"
        print(f"{day:10s} {f['videos']:5d} {r['paid_videos']:5d} {r['videos']['test']:5d} {f['users']:10d} {r['credits']['free']:7d} {budget:>9s} {f['estimated_usd']:10.2f} {f['tracked_usd']:14.2f}"
              f" {f['estimated_usd_per_user']:15.2f} {r['claims']['granted']:7d} {sum(r['claims']['refused'].values()):7d}")
        if i == 0:
            print(f"\n{day} in detail")
            print(f"  refused allowances by reason: {r['claims']['refused'] or 'none'}; turned away by the budget: {r['claims']['budget_refused']}, by the monthly cap: {r['claims']['cap_refused']};"
                  f" device proofs refused: {r['claims']['device_refused'] or 'none'}")
            print("  top free users (account id, videos, free credits, estimated $, tracked $):")
            for u in r["top_free_users"]:
                print(f"    {u['user']:38s} {u['videos']:3d} {u['free_credits']:4d} {u['estimated_usd']:7.2f} {u['tracked_usd']:7.2f}")
            print("  address blocks with the most allowances today:")
            for b in plan_report.ip_blocks(day, usage):
                print(f"    {b['block']:24s} {b['claims']}")
    ids = plan_report.shared_identities(ddb.Table(t["claims"]))
    print(f"\nAllowances claimed so far: {ids['claims']} ({ids['by_kind']}); identities that more than one account tried to use: {ids['shared']}")
    for x in ids["top"]:
        print(f"    {x['identity']:18s} {x['kind']:16s} {x['accounts']} accounts, first claim {x['first_claim']}")
    print(f"\n{a.days} days: free usage about ${total_free:.2f} (estimate), {total_paid} paid videos")


def refresh_cmd(a) -> None:
    path = os.path.join(HERE, "..", "lambdas", "common", "data", "disposable_email_domains.txt")
    body = urllib.request.urlopen(LIST_URL, timeout=30).read().decode("utf-8")   # noqa: S310
    commit = json.loads(urllib.request.urlopen(COMMIT_URL, timeout=30).read())[0]   # noqa: S310
    domains = [x.strip().lower() for x in body.splitlines() if x.strip() and not x.startswith("#")]
    if len(domains) < 3000 or {"gmail.com", "outlook.com", "icloud.com"} & set(domains):
        sys.exit("the downloaded list looks wrong: nothing written")
    head = (f"# Disposable email domains. Source: https://github.com/disposable-email-domains/disposable-email-domains (file disposable_email_blocklist.conf),\n"
            f"# commit {commit['sha']} of {commit['commit']['committer']['date'][:10]}, fetched {time.strftime('%Y-%m-%d')}. Licence: CC0 1.0 Universal (public domain dedication; no attribution needed).\n"
            "# Refresh: backend/scripts/plans_admin.py disposable-refresh. Local additions and exceptions go in the config knobs email_domain_deny / email_domain_allow, not here.\n")
    open(path, "w", encoding="utf-8").write(head + "\n".join(domains) + "\n")
    print(f"{len(domains)} domains written to {os.path.relpath(path)} (check the licence is still CC0, run the tests, commit, deploy)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["config", "gallery-only", "showcase", "report", "disposable-refresh"])
    ap.add_argument("verb", nargs="?", default="show")
    ap.add_argument("target", nargs="?")
    ap.add_argument("value", nargs="?")
    ap.add_argument("--stage", default="qa")
    for name in ("title-en", "title-es", "desc-en", "desc-es", "poster", "id", "file", "aspect", "prompt", "lang", "day"):
        ap.add_argument(f"--{name}")
    for name in ("seconds", "width", "height"):
        ap.add_argument(f"--{name}", type=int)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--show-prompt", action="store_true", help="showcase add: list the video's real prompt with it")
    ap.add_argument("--made-by-us", action="store_true", help="showcase add: you checked that this video was made by VideoMK, not by a customer")
    a = ap.parse_args()
    a.knob = a.target
    if a.command == "config":
        if a.verb not in ("show", "set", "reset"):
            sys.exit("config show | set <knob> <value> | reset <knob>")
        config_cmd(a)
    elif a.command == "gallery-only":
        if a.verb not in ("on", "off"):
            sys.exit("gallery-only on|off")
        gallery_only_cmd(a)
    elif a.command == "showcase":
        if a.verb not in ("list", "add", "remove") or (a.verb == "remove" and not a.target) or (a.verb == "add" and not (a.target or a.file)):
            sys.exit("showcase list | add <video id> --title-en ... | add --file cut.mp4 --id ... | remove <id>")
        showcase_cmd(a)
    elif a.command == "report":
        report_cmd(a)
    else:
        refresh_cmd(a)


if __name__ == "__main__":
    main()
