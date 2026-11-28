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
if app.node.try_get_context("appSite"):  # the web app (app.videomk.com, docs/WEB_REDESIGN_2026.md): scripts/site.sh app
    from app_site_stack import AppSiteStack
    AppSiteStack(app, "videomk-app-site", app_dir=os.path.join(os.path.dirname(__file__), "build", "app"), env=cdk.Environment(account="464863885161", region="us-east-1"))
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
if app.node.try_get_context("clipsAlarms"):  # the two alarms of library clips on demand (docs/CLIPS_ON_DEMAND.md): a tiny stack of its own, because the main one is near 500 resources
    from clips_obs import ClipsObsStack
    _stage = str(app.node.try_get_context("stage") or "")
    with open(os.path.join(os.path.dirname(__file__), "stages.json")) as f:
        _cfg = json.load(f)[_stage]
    ClipsObsStack(app, f"videomk-{_stage}-clips-obs", day_budget_usd=float(app.node.try_get_context("clipsDayBudgetUsd") or 10), env=cdk.Environment(account=_cfg["account"], region=_cfg["region"]))
    app.synth()
    raise SystemExit(0)
if app.node.try_get_context("objectTracer"):  # the whiteboard tracer function (docs/LIBRARY_ON_DEMAND.md part D): a small stack of its own, for the same reason
    from object_tracer import ObjectTracerStack
    _stage = str(app.node.try_get_context("stage") or "")
    with open(os.path.join(os.path.dirname(__file__), "stages.json")) as f:
        _cfg = json.load(f)[_stage]
    _cli = os.getenv("CDK_DEFAULT_ACCOUNT")
    if _cli and _cli != _cfg["account"]:
        raise SystemExit(f"Refusing: stage '{_stage}' belongs to account {_cfg['account']} but credentials are for {_cli}.")
    ObjectTracerStack(app, f"videomk-{_stage}-wb-tracer", stage=_stage, plan_model_id=str(app.node.try_get_context("planModelId") or ""),
                      env=cdk.Environment(account=_cfg["account"], region=_cfg["region"]))
    app.synth()
    raise SystemExit(0)
if app.node.try_get_context("share"):  # share links for videos (docs/SHARE_PREVIEWS_2026-11-28.md): a small stack of its own, the main one is near 500 resources
    from share_stack import ShareStack
    _stage = str(app.node.try_get_context("stage") or "")
    with open(os.path.join(os.path.dirname(__file__), "stages.json")) as f:
        _cfg = json.load(f)[_stage]
    _cli = os.getenv("CDK_DEFAULT_ACCOUNT")
    if _cli and _cli != _cfg["account"]:
        raise SystemExit(f"Refusing: stage '{_stage}' belongs to account {_cfg['account']} but credentials are for {_cli}.")
    _pool, _clients = app.node.try_get_context("sharePoolId"), app.node.try_get_context("shareClientIds")
    if not _pool or not _clients or not app.node.try_get_context("shareVideosTable"):
        raise SystemExit("Pass -c sharePoolId=<Cognito user pool id> -c shareClientIds=<app client ids, comma separated> -c shareVideosTable=<the main stack's videos table name> (see the main stack's outputs and the doc).")
    ShareStack(app, f"videomk-{_stage}-share", stage=_stage, videos_table_name=str(app.node.try_get_context("shareVideosTable") or ""), assets_bucket=f"videomk-{_stage}-{_cfg['account']}",
               user_pool_id=str(_pool), client_ids=[c for c in str(_clients).split(",") if c], share_host=app.node.try_get_context("shareHost"), cert_arn=app.node.try_get_context("shareCertArn"),
               env=cdk.Environment(account=_cfg["account"], region=_cfg["region"]))
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

if app.node.try_get_context("admin"):  # the owner console (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md), its own stack per stage: scripts/admin_console.sh <stage> diff|deploy
    from admin_stack import DEFAULT_ALERT_EMAIL, AdminStack, main_stack_values
    _given = app.node.try_get_context("adminMainValues")   # the main stack's names as JSON (tests, or a machine without credentials); else read from the deployed launcher
    if _given:
        _main = json.loads(_given)
    else:
        import boto3
        _main = main_stack_values(boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"]))
    AdminStack(app, f"videomk-admin-{stage}", stage=stage, main=_main, host=app.node.try_get_context("adminHost") or cfg.get("adminHost"),
               alert_email=str(app.node.try_get_context("adminAlertEmail") or DEFAULT_ALERT_EMAIL), cli_profile=cfg["profile"], env=cdk.Environment(account=cfg["account"], region=cfg["region"]))
    app.synth()
    raise SystemExit(0)

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
