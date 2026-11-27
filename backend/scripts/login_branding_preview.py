#!/usr/bin/env python3
"""Push the sign-in branding (login_branding/) straight to a QA app client, to iterate on the look without a CloudFormation deploy.

  AWS_PROFILE=qa python scripts/login_branding_preview.py --client <client id> [--user-pool <id>] [--domain-version 2]

Only the QA profile is accepted. The deployed stack (backend_stack.py, login_branding) is the source of truth: before a deploy that creates the same
branding, delete the preview one (`--delete`), because a client can have only one branding.
"""
import argparse
import base64
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import login_branding as lb  # noqa: E402


def aws_assets():
    return [{"Category": a["category"], "ColorMode": a["color_mode"], "Extension": a["extension"], "Bytes": base64.b64decode(a["bytes"])} for a in lb.assets()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--user-pool", default="eu-west-1_NiWZ6eHoo")
    ap.add_argument("--region", default="eu-west-1")
    ap.add_argument("--domain")
    ap.add_argument("--scheme", default="DYNAMIC", choices=["DYNAMIC", "LIGHT", "DARK"])
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args()
    if os.environ.get("AWS_PROFILE") != "qa":
        sys.exit("only the qa profile (AWS_PROFILE=qa)")
    c = boto3.client("cognito-idp", region_name=a.region)
    try:
        cur = c.describe_managed_login_branding_by_client(UserPoolId=a.user_pool, ClientId=a.client)["ManagedLoginBranding"]["ManagedLoginBrandingId"]
    except c.exceptions.ResourceNotFoundException:
        cur = None
    if a.delete:
        if cur:
            c.delete_managed_login_branding(UserPoolId=a.user_pool, ManagedLoginBrandingId=cur)
            print("deleted", cur)
        return
    if a.domain:
        c.update_user_pool_domain(Domain=a.domain, UserPoolId=a.user_pool, ManagedLoginVersion=2)
        print("domain on managed login v2")
    if cur:
        c.update_managed_login_branding(UserPoolId=a.user_pool, ManagedLoginBrandingId=cur, UseCognitoProvidedValues=False, Settings=lb.settings(a.scheme), Assets=aws_assets())
    else:
        cur = c.create_managed_login_branding(UserPoolId=a.user_pool, ClientId=a.client, UseCognitoProvidedValues=False, Settings=lb.settings(a.scheme), Assets=aws_assets())["ManagedLoginBranding"]["ManagedLoginBrandingId"]
    print("branding", cur)


if __name__ == "__main__":
    main()
