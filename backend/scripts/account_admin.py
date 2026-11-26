#!/usr/bin/env python3
"""Inspect, start, retry or complete an account deletion by hand (needs AWS admin credentials for the stage's account). Never exposed through the API. See docs/ACCOUNT_DELETION.md.

  AWS_PROFILE=qa python backend/scripts/account_admin.py show   you@example.com   # the job (status, finished steps, failures, last error) and what is still stored per store
  AWS_PROFILE=qa python backend/scripts/account_admin.py delete you@example.com   # start a deletion at the person's written request (email route): no recent-sign-in rule, staff are the authentication
  AWS_PROFILE=qa python backend/scripts/account_admin.py retry  <sub>             # a stuck or failing job gets fresh attempts and is queued again (the worker does the work)
  AWS_PROFILE=qa python backend/scripts/account_admin.py complete <sub> [--now]   # run the steps here, with your credentials, until done; --now skips the wait for old tokens to expire
Accounts are found by email in the stage's Cognito pool, or pass a user id (the token `sub`). Defaults to stage qa; prod asks you to type prod.
The script runs the same code as the worker (it copies the worker function's environment), so a step that fails here fails for the same reason it fails there, and prints the AWS error.
"""
import argparse
import json
import os
import sys
import time

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))


def setup(stage: str):
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))[stage]
    session = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    boto3.setup_default_session(profile_name=cfg["profile"], region_name=cfg["region"])
    out = {o["OutputKey"]: o["OutputValue"] for o in session.client("cloudformation").describe_stacks(StackName=f"videomk-{stage}")["Stacks"][0]["Outputs"]}
    # outputs of a nested construct are named <Construct><Id><hash> (AccountDeletionDeletionWorkerNameB9A3FDE3): match by the id
    for want in ("DeletionWorkerName", "DeletionTableName", "DeletionQueueUrl"):
        if want not in out:
            found = [v for k, v in out.items() if want in k]
            if found:
                out[want] = found[0]
    env = session.client("lambda").get_function_configuration(FunctionName=out["DeletionWorkerName"])["Environment"]["Variables"]
    os.environ.update(env)
    os.environ["AWS_DEFAULT_REGION"] = cfg["region"]
    return session, out


def find_user(session, pool_id: str, who: str) -> str:
    if "@" not in who:
        return who
    users = session.client("cognito-idp").list_users(UserPoolId=pool_id, Filter=f'email = "{who}"')["Users"]
    if len(users) != 1:
        sys.exit(f"expected one account with that email in the pool, found {len(users)}")
    return next(a["Value"] for a in users[0]["Attributes"] if a["Name"] == "sub")


def show(deletion, user: str) -> None:
    job = deletion.get_job(user)
    if not job:
        print("no deletion job for this account")
    else:
        t = lambda x: time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(int(x)))  # noqa: E731
        print(f"status={job['status']} requested={t(job['created_at'])} by={job.get('by')} settle_at={t(job['settle_at'])} fails={job.get('fails', 0)} apple_revoked={'yes' if job.get('apple_revoked_at') else 'no'}")
        for name in deletion.STEPS:
            s = (job.get("steps") or {}).get(name)
            print(f"  {name:<11} {'done ' + t(s['at']) + ' ' + json.dumps(s.get('n'), default=int) if s else '-'}")
        if job.get("last_error"):
            print(f"  last error: {json.dumps(job['last_error'], default=int)}")
    try:
        print("still stored:", json.dumps(deletion.inventory(user)))
    except Exception as e:  # noqa: BLE001
        print(f"could not count what is stored: {type(e).__name__}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["show", "delete", "retry", "complete"])
    ap.add_argument("who", help="email or user id (sub)")
    ap.add_argument("--stage", default="qa")
    ap.add_argument("--now", action="store_true", help="complete: do not wait for old tokens to expire")
    a = ap.parse_args()
    if a.action != "show" and a.stage == "prod" and input("This changes PRODUCTION accounts. Type 'prod': ") != "prod":
        sys.exit("cancelled")
    session, out = setup(a.stage)
    from common import deletion
    user = find_user(session, out["UserPoolId"], a.who)
    if a.action == "delete":
        if deletion.create_job(user, by="staff"):
            deletion.enqueue(user)
            print("deletion started; the worker takes it from here")
        else:
            print("a deletion job already exists for this account")
    elif a.action == "retry":
        if not deletion.get_job(user):
            sys.exit("no deletion job for this account (use `delete` to start one)")
        deletion.reopen(user)
        deletion.enqueue(user)
        print("queued again")
    elif a.action == "complete":
        if not deletion.get_job(user):
            sys.exit("no deletion job for this account (use `delete` to start one)")
        if deletion.get_job(user).get("status") == "stuck":
            deletion.reopen(user)
        while True:
            res = deletion.run(user, skip_settle=a.now)
            print(f"{res.status} {res.step}")
            if res.status == "done":
                break
            if res.status in ("stuck", "absent"):
                sys.exit(f"stopped: {res.status}; read the error below and fix it, then run again")
            if res.status in ("wait",):
                print(f"waiting {res.delay}s for earlier tokens to expire (use --now to skip)")
            if res.status != "continue":
                time.sleep(min(res.delay, 60) if res.status == "retry" else min(res.delay, 300))
    show(deletion, user)
    print(f"(sub={user})")


if __name__ == "__main__":
    main()
