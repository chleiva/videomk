#!/usr/bin/env python3
"""Usage: cdk deploy -c stage=qa  (or use scripts/deploy.sh). The stage selects account, region and names from stages.json."""
import json
import os

import aws_cdk as cdk

from backend_stack import BackendStack

app = cdk.App()
stage = app.node.try_get_context("stage")
with open(os.path.join(os.path.dirname(__file__), "stages.json")) as f:
    stages = json.load(f)
if stage not in stages:
    raise SystemExit(f"Pass -c stage=<{'|'.join(stages)}> (see stages.json)")
cfg = stages[stage]
cli_account = os.getenv("CDK_DEFAULT_ACCOUNT")
if cli_account and cli_account != cfg["account"]:
    raise SystemExit(f"Refusing: stage '{stage}' belongs to account {cfg['account']} but credentials are for {cli_account}.")

BackendStack(
    app, f"videomk-{stage}", stage=stage, stage_cfg=cfg,
    env=cdk.Environment(account=cfg["account"], region=cfg["region"]),
)
app.synth()
