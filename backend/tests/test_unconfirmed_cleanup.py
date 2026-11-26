"""Scheduled cleanup of abandoned UNCONFIRMED sign-ups: the Lambda with a fake Cognito client, and the CDK template."""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError

import unconfirmed_cleanup as uc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NOW = datetime.now(timezone.utc)


def u(name, status="UNCONFIRMED", age_h=48, identities=False):
    attrs = [{"Name": "email", "Value": f"{name}@secret-example.com"}]
    if identities:
        attrs.append({"Name": "identities", "Value": "[{}]"})
    return {"Username": name, "UserStatus": status, "UserCreateDate": NOW - timedelta(hours=age_h), "Attributes": attrs, "UserAttributes": attrs}


class FakeIdp:
    def __init__(self, users, page=60, change=None, throttle=0):
        self.users = {x["Username"]: dict(x) for x in users}
        self.order = [x["Username"] for x in users]
        self.page, self.change, self.throttle = page, change or {}, throttle
        self.deleted, self.filters, self.calls = [], [], 0

    def list_users(self, UserPoolId, Filter, Limit, PaginationToken=None):
        self.filters.append(Filter)
        if self.throttle > 0:
            self.throttle -= 1
            raise ClientError({"Error": {"Code": "TooManyRequestsException"}}, "ListUsers")
        start = int(PaginationToken or 0)
        names = self.order[start:start + self.page]
        out = {"Users": [self.users[n] for n in names]}
        if start + self.page < len(self.order):
            out["PaginationToken"] = str(start + self.page)
        return out

    def admin_get_user(self, UserPoolId, Username):
        if Username in self.change:
            self.users[Username]["UserStatus"] = self.change[Username]
        return self.users[Username]

    def admin_delete_user(self, UserPoolId, Username):
        self.deleted.append(Username)


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setenv("USER_POOL_ID", "eu-west-1_Pool")
    monkeypatch.setattr(uc, "_sleep", lambda s: None)

    def go(fake, **env):
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        monkeypatch.setattr(uc, "_idp", fake)
        return uc.handler({}, None)
    return go


def test_old_unconfirmed_deleted_others_kept(run):
    f = FakeIdp([u("old"), u("recent", age_h=2), u("conf", "CONFIRMED"), u("goog", "EXTERNAL_PROVIDER"), u("fed-unconf", identities=True)])
    assert run(f) == {"deleted": 1, "skipped": 0}
    assert f.deleted == ["old"]
    assert f.filters == ['cognito:user_status = "UNCONFIRMED"']


def test_max_age_env_and_minimum(run):
    f = FakeIdp([u("a", age_h=3)])
    run(f, UNCONFIRMED_MAX_AGE_HOURS=2)
    assert f.deleted == ["a"]
    f = FakeIdp([u("b", age_h=0.5)])
    run(f, UNCONFIRMED_MAX_AGE_HOURS=0)   # clamped to 1 hour
    assert f.deleted == []


def test_status_changed_between_list_and_delete_is_skipped(run):
    f = FakeIdp([u("a"), u("b")], change={"a": "CONFIRMED"})
    assert run(f) == {"deleted": 1, "skipped": 1}
    assert f.deleted == ["b"]


def test_pagination(run):
    f = FakeIdp([u(f"u{i}") for i in range(7)], page=2)
    assert run(f)["deleted"] == 7


def test_cap_and_log(run, caplog):
    f = FakeIdp([u(f"u{i}") for i in range(10)], page=3)
    with caplog.at_level(logging.INFO):
        assert run(f, MAX_DELETIONS_PER_RUN=4) == {"deleted": 4, "skipped": 0}
    assert "cap reached" in caplog.text and "UNCONFIRMED_CLEANUP deleted=4 skipped=0" in caplog.text


def test_throttle_backoff(run):
    f = FakeIdp([u("a")], throttle=2)
    assert run(f)["deleted"] == 1


def test_delete_error_counts_as_skipped(run):
    f = FakeIdp([u("a"), u("b")])
    orig = f.admin_delete_user

    def bad(UserPoolId, Username):
        if Username == "a":
            raise ClientError({"Error": {"Code": "InternalErrorException"}}, "AdminDeleteUser")
        orig(UserPoolId, Username)
    f.admin_delete_user = bad
    assert run(f) == {"deleted": 1, "skipped": 1}


def test_no_pii_in_logs(run, caplog):
    f = FakeIdp([u("alice-user"), u("bob-user")], change={"bob-user": "CONFIRMED"})
    with caplog.at_level(logging.DEBUG):
        run(f)
    assert "UNCONFIRMED_CLEANUP deleted=1 skipped=1" in caplog.text
    for secret in ("alice", "bob", "secret-example", "@", "Pool"):
        assert secret not in caplog.text


# ---- CDK ----
@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    sys.path.insert(0, ROOT)
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(**ctx):
            key = tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-unc-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def _fn(t):
    hits = {k: v for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("FunctionName") == "unconfirmed_cleanup"}
    return hits


def test_cdk_default_on(synth):
    t = synth()
    fns = _fn(t)
    assert len(fns) == 1
    (fid, fn), = fns.items()
    env = fn["Properties"]["Environment"]["Variables"]
    assert env["UNCONFIRMED_MAX_AGE_HOURS"] == "24" and env["MAX_DELETIONS_PER_RUN"] == "200"
    rules = [v for v in t["Resources"].values() if v["Type"] == "AWS::Events::Rule" and any(fid in str(x) for x in v["Properties"]["Targets"])]
    assert len(rules) == 1 and rules[0]["Properties"]["ScheduleExpression"] == "rate(6 hours)"
    role = fn["Properties"]["Role"]["Fn::GetAtt"][0]
    stmts = []
    for v in t["Resources"].values():
        if v["Type"] == "AWS::IAM::Policy" and any(r.get("Ref") == role for r in v["Properties"]["Roles"]):
            stmts += v["Properties"]["PolicyDocument"]["Statement"]
    cog = [s for s in stmts if any(a.startswith("cognito-idp:") for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"]))]
    assert len(cog) == 1
    assert sorted(cog[0]["Action"]) == ["cognito-idp:AdminDeleteUser", "cognito-idp:AdminGetUser", "cognito-idp:ListUsers"]
    assert cog[0]["Resource"] == {"Fn::GetAtt": [next(k for k, v in t["Resources"].items() if v["Type"] == "AWS::Cognito::UserPool"), "Arn"]}


def test_cdk_age_context_and_switch_off(synth):
    t = synth(unconfirmedMaxAgeHours="0")
    (fn,) = _fn(t).values()
    assert fn["Properties"]["Environment"]["Variables"]["UNCONFIRMED_MAX_AGE_HOURS"] == "1"
    assert _fn(synth(unconfirmedCleanup="0")) == {}
