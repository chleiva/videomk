#!/usr/bin/env python3
"""Manage credits by hand (needs AWS credentials for the stage's account). Never exposed through the API.

  AWS_PROFILE=qa python backend/scripts/wallet_admin.py unlimited you@example.com        # no charges, ever (test/staff accounts)
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py limited you@example.com          # back to normal
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py give you@example.com 20          # add 20 paid credits
  AWS_PROFILE=qa python backend/scripts/wallet_admin.py show you@example.com
The unlimited flag is only honoured outside production (ALLOW_UNLIMITED_ACCOUNTS is 0 there) and lives in a table the Lambdas cannot write.
Accounts are found by email in the stage's Cognito pool, or pass a user id (the token `sub`). Defaults to stage qa; prod asks you to type prod.
"""
import argparse
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from common import wallet  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["unlimited", "limited", "give", "show"])
    ap.add_argument("who", help="email or user id (sub)")
    ap.add_argument("amount", nargs="?", type=int)
    ap.add_argument("--stage", default="qa")
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
    uid = a.who
    if "@" in a.who:
        users = session.client("cognito-idp").list_users(UserPoolId=out["UserPoolId"], Filter=f'email = "{a.who}"')["Users"]
        if not users:
            sys.exit(f"no account with email {a.who} in {a.stage}")
        uid = next(x["Value"] for x in users[0]["Attributes"] if x["Name"] == "sub")
    if a.action in ("unlimited", "limited"):
        wallet.set_unlimited(uid, a.action == "unlimited")
    elif a.action == "give":
        if not a.amount or a.amount < 1:
            sys.exit("give needs a positive amount")
        wallet.give_credits(uid, a.amount)
    b = wallet.balance(uid)
    print(f"{a.who} ({a.stage}): unlimited={b['unlimited']} balance={b['balance']} buckets={[(x['kind'], x['remaining']) for x in b['buckets']]}")


if __name__ == "__main__":
    main()
