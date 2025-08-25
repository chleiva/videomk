#!/usr/bin/env python3
import os
import json
import aws_cdk as cdk

from backend_stack import BackendStack


app = cdk.App()

# Try to load account/region from config.json, fallback to env vars
account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")
try:
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            cfg = json.load(f)
            account = cfg.get("awsAccount") or account
            region = cfg.get("awsRegion") or region
except Exception:
    pass

env = cdk.Environment(account=account, region=region)

BackendStack(app, "BackendStack", env=env)

app.synth()


