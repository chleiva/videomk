"""The photo library bucket lets the web app upload straight from the browser: POST (and GET/HEAD) from the web origins only, never `*`, and no local dev server in prod."""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambdas"))


@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(stage):
            if stage not in cache:
                app = cdk.App(context={"stage": stage, "engine": "v2"}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-mcors-{stage}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                acct, region = ("464863885161", "us-west-2") if stage == "prod" else ("123456789012", "eu-west-1")
                cb = ["https://app.videomk.com/auth/callback", "https://videomk.com/auth/callback"] if stage == "prod" else ["http://localhost:4321/auth/callback"]
                stack = BackendStack(app, f"videomk-{stage}", stage=stage, stage_cfg={"account": acct, "region": region, "domain": None, "callbackUrls": cb}, env=cdk.Environment(account=acct, region=region))
                cache[stage] = Template.from_stack(stack).to_json()
            return cache[stage]
        yield build
    finally:
        os.chdir(cwd)


def media_bucket(t, stage):
    (b,) = [v for v in t["Resources"].values() if v["Type"] == "AWS::S3::Bucket" and "-media-" in str(v["Properties"].get("BucketName", ""))]
    return b["Properties"]


def test_prod_media_bucket_allows_only_the_web_origins(synth):
    rules = media_bucket(synth("prod"), "prod")["CorsConfiguration"]["CorsRules"]
    assert len(rules) == 1
    r = rules[0]
    assert "POST" in r["AllowedMethods"]
    assert sorted(r["AllowedOrigins"]) == ["https://app.videomk.com", "https://videomk.com", "https://www.videomk.com"]
    assert "*" not in r["AllowedOrigins"] and not any("localhost" in o for o in r["AllowedOrigins"])


def test_qa_media_bucket_also_allows_the_local_dev_server(synth):
    r = media_bucket(synth("qa"), "qa")["CorsConfiguration"]["CorsRules"][0]
    assert "http://localhost:4321" in r["AllowedOrigins"] and "POST" in r["AllowedMethods"] and "*" not in r["AllowedOrigins"]
