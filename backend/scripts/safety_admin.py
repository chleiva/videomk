#!/usr/bin/env python3
"""Review and manage safety stops by hand (needs AWS admin credentials for the stage's account). Never exposed through the API.

  AWS_PROFILE=qa python backend/scripts/safety_admin.py show you@example.com     # recent stops (category, severity, source, time, excerpt) and the account state
  AWS_PROFILE=qa python backend/scripts/safety_admin.py clear you@example.com    # earlier stops no longer count and a hold is lifted (records stay until their 90 days)
  AWS_PROFILE=qa python backend/scripts/safety_admin.py hold you@example.com     # hold the account: creating videos answers 429 'paused' until `clear`
Accounts are found by email in the stage's Cognito pool, or pass a user id (the token `sub`). Defaults to stage qa; prod asks you to type prod.
The runtime Lambdas can only READ the flags table that `clear` and `hold` write (key 'safety:<sub>'), so an account can never clear itself.
"""
import argparse
import json
import os
import sys
import time

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from common import safety  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["show", "clear", "hold"])
    ap.add_argument("who", help="email or user id (sub)")
    ap.add_argument("--stage", default="qa")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))[a.stage]
    if a.action != "show" and a.stage == "prod" and input("This changes PRODUCTION accounts. Type 'prod': ") != "prod":
        sys.exit("cancelled")
    session = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    boto3.setup_default_session(profile_name=cfg["profile"], region_name=cfg["region"])
    cf = session.client("cloudformation").describe_stacks(StackName=f"videomk-{a.stage}")["Stacks"][0]
    out = {o["OutputKey"]: o["OutputValue"] for o in cf["Outputs"]}
    tables = [t for page in session.client("dynamodb").get_paginator("list_tables").paginate() for t in page["TableNames"]]
    for env, prefix in (("SAFETY_TABLE", f"videomk-{a.stage}-RequestIntakeSafetyTable"), ("FLAGS_TABLE", f"videomk-{a.stage}-AccountFlagsTable")):
        mine = [t for t in tables if t.startswith(prefix)]
        if len(mine) != 1:
            sys.exit(f"expected one table starting with {prefix}, found {mine}")
        os.environ[env] = mine[0]
    uid = a.who
    if "@" in a.who:
        users = session.client("cognito-idp").list_users(UserPoolId=out["UserPoolId"], Filter=f'email = "{a.who}"')["Users"]
        if not users:
            sys.exit(f"no account with email {a.who} in {a.stage}")
        uid = next(x["Value"] for x in users[0]["Attributes"] if x["Name"] == "sub")
    if a.action == "clear":
        safety.clear(uid)
    elif a.action == "hold":
        safety.set_hold(uid, True)
    flags = safety._flags(uid)
    print(f"{a.who} ({a.stage}) sub={uid}")
    print(f"flags: hold={bool(flags.get('safety_hold'))} cleared_at={flags.get('safety_cleared_at')}")
    cleared = int(flags.get("safety_cleared_at") or 0) * 1000
    for r in sorted(safety.records(uid), key=lambda r: r["ts"], reverse=True)[:30]:
        counted = "counts" if int(r["ts"]) > cleared else "cleared"
        print(f"  {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(int(r['ts']) / 1000))}  {r['category']:<24} {r['severity']:<14} {r['source']:<8} {counted:<8} {r.get('excerpt', '')!r}")
    st = safety.account_state(uid)
    print(f"state: {st.status}" + (f" ({st.reason}, retry_after={st.retry_after}s)" if st.stopped else ""))


if __name__ == "__main__":
    main()
