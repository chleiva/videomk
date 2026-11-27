#!/usr/bin/env python3
"""Manage credits by hand (needs AWS credentials for the stage's account). Never exposed through the API.

  AWS_PROFILE=qa python backend/scripts/wallet_admin.py unlimited you@example.com        # no charges, ever (test/staff accounts)
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py limited you@example.com          # back to normal
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py give you@example.com 20          # add 20 paid credits
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py show you@example.com
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py watermark you@example.com [--off]   # premium watermark: the person's own logo as the watermark (works in production too; docs/WATERMARK.md)
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py watermark you@example.com --default moments   # premium watermark AND a saved default: videomk lockup that comes and goes + the closing card (--off undoes both)
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py storage you@example.com --plan pro [--extra-gb 100] [--until 2027-01-31]   # photo library size (free = 2 GB, pro = 100 GB, plus extra GB)
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py plan you@example.com --plan max [--until 2027-01-31] [--yearly]            # the account's PLAN (docs/PLANS.md): free | pro | max. Monthly credits start now;
                                                                                                                                    # --until = the plan ends at the end of that day (none: no end); --plan free ends it at once
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py plan you@example.com --refund                                              # a refund: back to Free, unused plan credits removed
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py plan you@example.com --grace [--until 2027-02-10]                          # payment is being retried: rights stay, no new credits
`show` prints the plan, its state and dates, the plan credits and the free plan's state next to the credits. The plan record is in a table no function can write.
The unlimited flag is only honoured outside production (ALLOW_UNLIMITED_ACCOUNTS is 0 there) and lives in a table the Lambdas cannot write.
Accounts are found by email in the stage's Cognito pool, or pass a user id (the token `sub`). Defaults to stage qa; prod asks you to type prod.
"""
import argparse
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from common import library as lib, wallet  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["unlimited", "limited", "give", "show", "storage", "watermark", "plan"])
    ap.add_argument("who", help="email or user id (sub)")
    ap.add_argument("amount", nargs="?", type=int)
    ap.add_argument("--off", action="store_true", help="with `watermark`: take premium watermark away again")
    ap.add_argument("--default", choices=["moments", "always"], help="with `watermark`: also save this account's default watermark (videomk lockup + closing card, with this presence); with --off it is removed")
    ap.add_argument("--stage", default="qa")
    ap.add_argument("--plan", choices=["free", "pro", "max"], default=None, help="`plan`: the account's plan; `storage`: free or pro (the older storage-only flag)")
    ap.add_argument("--yearly", action="store_true", help="with `plan`: a yearly plan (credits still arrive monthly)")
    ap.add_argument("--refund", action="store_true", help="with `plan`: refund (back to Free, unused plan credits removed)")
    ap.add_argument("--grace", action="store_true", help="with `plan`: billing grace (rights stay until --until, default 16 days; no new credits)")
    ap.add_argument("--extra-gb", type=int, default=0)
    ap.add_argument("--until", help="YYYY-MM-DD: the plan and add-ons lapse at the end of this day (nothing is deleted)")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))[a.stage]
    if a.stage == "prod" and input("This changes PRODUCTION credits. Type 'prod': ") != "prod":
        sys.exit("cancelled")
    session = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    boto3.setup_default_session(profile_name=cfg["profile"], region_name=cfg["region"])
    cf = session.client("cloudformation").describe_stacks(StackName=f"videomk-{a.stage}")["Stacks"][0]
    out = {o["OutputKey"]: o["OutputValue"] for o in cf["Outputs"]}
    tables = [t for page in session.client("dynamodb").get_paginator("list_tables").paginate() for t in page["TableNames"]]
    mine = [t for t in tables if t.startswith(f"videomk-{a.stage}-WalletTable")]
    if len(mine) != 1:
        sys.exit(f"expected one wallet table for stage {a.stage}, found {mine}")
    os.environ["WALLET_TABLE"] = mine[0]
    flags = [t for t in tables if t.startswith(f"videomk-{a.stage}-AccountFlagsTable")]
    if len(flags) != 1:
        sys.exit(f"expected one account-flags table for stage {a.stage}, found {flags}")
    os.environ["FLAGS_TABLE"] = flags[0]
    os.environ["ALLOW_UNLIMITED_ACCOUNTS"] = "0" if a.stage == "prod" else "1"  # `show` reports what the running system would do
    ent = [t for t in tables if t.startswith(f"videomk-{a.stage}-") and "EntitlementsTable" in t]
    claims = [t for t in tables if t.startswith(f"videomk-{a.stage}-") and "FreeClaimsTable" in t]
    plans_on = len(ent) == 1 and len(claims) == 1   # the stage has plans (docs/PLANS.md)
    if plans_on:
        usage = [t for t in tables if t.startswith(f"videomk-{a.stage}-UsageTable")]
        os.environ.update({"PLANS_ENABLED": "1", "ENTITLEMENTS_TABLE": ent[0], "FREE_CLAIMS_TABLE": claims[0], "PLANS_CONFIG_PARAM": f"/videomk/{a.stage}/plans/config",
                           "PLANS_REQUIRE_DEVICE_PROOF_DEFAULT": "1" if a.stage == "prod" else "0", **({"USAGE_TABLE": usage[0]} if len(usage) == 1 else {})})
    elif a.action == "plan":
        sys.exit(f"stage {a.stage} has no entitlements table yet (deploy the stack with plans on)")
    uid = a.who
    if "@" in a.who:
        users = session.client("cognito-idp").list_users(UserPoolId=out["UserPoolId"], Filter=f'email = "{a.who}"')["Users"]
        if not users:
            sys.exit(f"no account with email {a.who} in {a.stage}")
        uid = next(x["Value"] for x in users[0]["Attributes"] if x["Name"] == "sub")
    if a.action in ("unlimited", "limited"):
        wallet.set_unlimited(uid, a.action == "unlimited")
    elif a.action == "watermark":
        boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"]).update_item(Key={"user_id": uid}, UpdateExpression="SET watermark_custom = :v", ExpressionAttributeValues={":v": not a.off})   # keeps the other flags
        print(f"{a.who} ({a.stage}): premium watermark {'OFF' if a.off else 'ON'}")
        if a.default:   # also save (or, with --off, remove) the account's default watermark, as PUT /users/{user}/watermark would: watermark/<user>/profile.json in the assets bucket
            key = f"watermark/{uid}/profile.json"
            s3 = session.client("s3")
            if a.off:
                s3.delete_object(Bucket=out["AssetsBucketName"], Key=key)
                print(f"   saved default removed (s3://{out['AssetsBucketName']}/{key})")
            else:
                spec = {"mode": "videomk", "style": "lockup", "presence": a.default, "end_card": True, "position": "auto", "size": "small", "opacity": 0.65}
                s3.put_object(Bucket=out["AssetsBucketName"], Key=key, Body=json.dumps(spec).encode("utf-8"), ContentType="application/json")
                print(f"   saved default: {json.dumps(spec)} (s3://{out['AssetsBucketName']}/{key})")
        return
    elif a.action == "plan":
        import calendar, time as _t
        from common import entitlements
        until = calendar.timegm(_t.strptime(a.until, "%Y-%m-%d")) + 86400 if a.until else None
        if a.refund:
            if not entitlements.set_state(uid, "refunded"):
                sys.exit(f"{a.who} has no plan record")
            print(f"{a.who} ({a.stage}): refunded, back to Free; {wallet.revoke_plan_credits(uid)} unused plan credits removed")
        elif a.grace:
            if not entitlements.set_state(uid, "grace", grace_until=until):
                sys.exit(f"{a.who} has no plan record")
        else:
            if not a.plan:
                sys.exit("plan needs --plan free|pro|max (or --refund / --grace)")
            entitlements.set_plan(uid, a.plan, until=until, interval="year" if a.yearly else "month", source="admin")
    elif a.action == "storage":
        import calendar, time as _t
        until = calendar.timegm(_t.strptime(a.until, "%Y-%m-%d")) + 86400 if a.until else None
        if a.plan == "max":
            sys.exit("storage takes --plan free|pro; for a Max account use: plan <who> --plan max")
        lib.set_storage(uid, a.plan or "free", a.extra_gb, until)
        print(f"{a.who} ({a.stage}): library limit now {lib.limits(uid)}")
        return
    elif a.action == "give":
        if not a.amount or a.amount < 1:
            sys.exit("give needs a positive amount")
        wallet.give_credits(uid, a.amount)
    b = wallet.balance(uid)
    print(f"{a.who} ({a.stage}): unlimited={b['unlimited']} balance={b['balance']} buckets={[(x['kind'], x['remaining']) for x in b['buckets']]}")
    if plans_on:   # read without a request, so `free` here is the account's state, not what a given device would be told
        p, lim = b["plan"], b["plan"]["limits"]
        print(f"  plan={p['id']} state={p['state']} source={p['source']} interval={p['interval']} start={p['period_start']} end={p['period_end']} grace_until={p['grace_until']}"
              f" renews={p['renews']} previous={p['previous_plan']} test_account={p['test_account']}")
        print(f"  limits: longest {lim['max_seconds']} s, {'/'.join(lim['resolutions'])}, watermark {'/'.join(lim['watermark_modes'])}{' (forced)' if lim['watermark_forced'] else ''},"
              f" {lim['storage_bytes'] // 10**9} GB, {lim['photos_per_video']} photos per video, plan credits now {p['plan_credits']} (monthly {lim['credits_per_month']}, cap {lim['credits_cap']})")
        print(f"  free plan: offers={b['free_creation']} credits_left={b['free']['credits_left']} budget_paused={b['free']['budget_paused']} library={lib.limits(uid)}")


if __name__ == "__main__":
    main()
