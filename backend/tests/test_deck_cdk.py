"""The deck-to-video infrastructure: nothing is created with the flag off; with it on, the converter is isolated and least-privilege, nothing is public, and the deck folder
is inside the area account deletion and the two-day lifecycle rule already cover."""
import json
import os
import re
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

        def build(**ctx):
            ctx.setdefault("engine", "v2")
            key = tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": "qa", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-deck-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"], "logoutUrls": ["https://qa.videomk.com/"]},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def fn(t, name):
    hits = [v for v in of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == name]
    return hits[0] if hits else None


def test_flag_off_creates_nothing(synth):
    t = synth()
    assert fn(t, "deck_prep") is None and fn(t, "decks_api") is None
    assert not of(t, "AWS::EC2::VPC") and not of(t, "AWS::EC2::VPCEndpoint")
    assert "decks" not in json.dumps([v["Properties"].get("PathPart") for v in of(t, "AWS::ApiGateway::Resource").values()])
    blob = json.dumps(t)
    assert "DECK_TO_VIDEO" not in blob and "DECKS_ENABLED" not in blob


def test_flag_on_converter_is_isolated_and_least_privilege(synth):
    t = synth(deckToVideo="1")
    prep = fn(t, "deck_prep")
    assert prep["Properties"]["PackageType"] == "Image" and prep["Properties"]["Architectures"] == ["arm64"]
    assert prep["Properties"]["VpcConfig"]["SubnetIds"]
    # no internet route anywhere in the deck VPC: no gateway, no NAT, no default route
    assert not of(t, "AWS::EC2::InternetGateway") and not of(t, "AWS::EC2::NatGateway")
    assert not [r for r in of(t, "AWS::EC2::Route").values() if r["Properties"].get("DestinationCidrBlock") == "0.0.0.0/0"]
    ep = list(of(t, "AWS::EC2::VPCEndpoint").values())
    assert len(ep) == 1 and ep[0]["Properties"]["VpcEndpointType"] == "Gateway" and "s3" in json.dumps(ep[0]["Properties"]["ServiceName"])
    # the converter's own role: S3 on the deck folders only, nothing else (no model, table, secret)
    role_name = prep["Properties"]["Role"]["Fn::GetAtt"][0]
    pol = [p for p in of(t, "AWS::IAM::Policy").values() if any(r.get("Ref") == role_name for r in p["Properties"]["Roles"])][0]
    for st in pol["Properties"]["PolicyDocument"]["Statement"]:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        res = json.dumps(st["Resource"])
        assert all(a.startswith("s3:") for a in acts), acts
        assert "uploads/*/decks/*" in res and "*\"" not in res.replace("uploads/*/decks/*", "")
    # public access stays blocked, the env flag reaches the three functions that need it
    for b in of(t, "AWS::S3::Bucket").values():
        pab = b["Properties"].get("PublicAccessBlockConfiguration")
        assert pab is None or all(pab.values())
    blob = json.dumps(t)
    assert blob.count('"DECKS_ENABLED"') >= 3 and '"DECK_TO_VIDEO"' in blob
    paths = {v["Properties"].get("PathPart") for v in of(t, "AWS::ApiGateway::Resource").values()}
    assert {"decks", "{deck_id}", "process"} <= paths


def test_decks_live_inside_the_area_account_deletion_covers():
    import account_deletion as ad
    from common import deck_limits as L

    assert "uploads/<user>/" in ad.COVERED_BUCKETS["AssetsBucket"]
    assert L.original_key("USER", "0123456789abcdef", "pptx").startswith("uploads/USER/")
    assert L.status_key("USER", "0123456789abcdef").startswith("uploads/USER/decks/")


def test_the_deck_quota_counters_are_removed_with_the_account():
    from common import deletion

    assert {"deck:", "deckproc:"} <= set(deletion.USAGE_PREFIXES)
