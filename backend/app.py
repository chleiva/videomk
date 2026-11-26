#!/usr/bin/env python3
"""Usage: cdk deploy -c stage=qa  (or use scripts/deploy.sh). The stage selects account, region and names from stages.json."""
import json
import os

import aws_cdk as cdk

from backend_stack import BackendStack
from social_auth import flag as social_flag, missing_values

app = cdk.App()
if app.node.try_get_context("site"):  # the public website (videomk.com): scripts/site.sh
    from site_stack import SiteStack
    SiteStack(app, "videomk-site", domain="videomk.com", phase=app.node.try_get_context("sitePhase") or "zone",
              site_dir=os.path.join(os.path.dirname(__file__), "build", "site"), env=cdk.Environment(account="464863885161", region="us-east-1"))
    app.synth()
    raise SystemExit(0)
if app.node.try_get_context("mail"):  # email forwarding for videomk.com (docs/EMAIL_FORWARDING.md): prod account, us-east-1, like the site
    from mail_forward import MailForwardStack, PROD_ACCOUNT, REGION, DEFAULT_FROM, DEFAULT_TO, ZONE_ID, _ctx_email
    _cli = os.getenv("CDK_DEFAULT_ACCOUNT")
    if _cli and _cli != PROD_ACCOUNT:
        raise SystemExit(f"Refusing: the mail stack belongs to account {PROD_ACCOUNT} but credentials are for {_cli}.")
    _res = app.node.try_get_context("mailReservedConcurrency")
    MailForwardStack(app, "videomk-mail", forward_to=_ctx_email(app.node, "forwardTo", DEFAULT_TO), forward_from=_ctx_email(app.node, "forwardFrom", DEFAULT_FROM),
                     zone_id=str(app.node.try_get_context("mailZoneId") or ZONE_ID), reserved=int(_res) if _res else None, env=cdk.Environment(account=PROD_ACCOUNT, region=REGION))
    app.synth()
    raise SystemExit(0)
stage = app.node.try_get_context("stage")
with open(os.path.join(os.path.dirname(__file__), "stages.json")) as f:
    stages = json.load(f)
if stage not in stages:
    raise SystemExit(f"Pass -c stage=<{'|'.join(stages)}> (see stages.json)")
cfg = stages[stage]
cli_account = os.getenv("CDK_DEFAULT_ACCOUNT")
if cli_account and cli_account != cfg["account"]:
    raise SystemExit(f"Refusing: stage '{stage}' belongs to account {cfg['account']} but credentials are for {cli_account}.")

_google, _apple = social_flag(app.node, "socialGoogle"), social_flag(app.node, "socialApple")
if (_google or _apple) and not app.node.try_get_context("socialSkipCheck"):
    import boto3
    _missing = missing_values(boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"]), _google, _apple)
    if _missing:
        raise SystemExit("Social sign-in is switched on but these values are missing in account %s (%s):\n  - %s\nCreate them first (docs/AUTH_SOCIAL.md, section 'Owner steps'), or drop -c socialGoogle / -c socialApple." % (cfg["account"], cfg["region"], "\n  - ".join(_missing)))

BackendStack(
    app, f"videomk-{stage}", stage=stage, stage_cfg=cfg,
    env=cdk.Environment(account=cfg["account"], region=cfg["region"]),
)
app.synth()
