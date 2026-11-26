"""Sign in with Google / Apple (docs/AUTH_SOCIAL.md): the pre sign-up linking trigger (mocked Cognito, no network) and the CDK template with the flags off and on."""
import json
import os
import re
import sys

import pytest
from botocore.exceptions import ClientError

import auth_presignup as ps

POOL = "eu-west-1_Pool"


class FakeIdp:
    def __init__(self, users=None, link_error=None):
        self.users, self.link_error, self.links, self.filters = users or [], link_error, [], []

    def list_users(self, UserPoolId, Filter, Limit):
        self.filters.append(Filter)
        m = re.match(r'email = "(.*)"', Filter)
        return {"Users": [u for u in self.users if any(a["Name"] == "email" and a["Value"] == m.group(1) for a in u["Attributes"])]}

    def admin_link_provider_for_user(self, **kw):
        if self.link_error:
            raise self.link_error
        self.links.append(kw)


def user(name, status="CONFIRMED", email="a@b.com", verified="true"):
    return {"Username": name, "UserStatus": status, "Attributes": [{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": verified}]}


def ev(name="Google_123", email="a@b.com", verified="true", source="PreSignUp_ExternalProvider"):
    attrs = {"email": email} if email else {}
    if verified is not None:
        attrs["email_verified"] = verified
    return {"triggerSource": source, "userPoolId": POOL, "userName": name, "request": {"userAttributes": attrs}, "response": {}}


def cerr(code, msg):
    return ClientError({"Error": {"Code": code, "Message": msg}}, "AdminLinkProviderForUser")


@pytest.fixture
def idp(monkeypatch):
    def install(**kw):
        f = FakeIdp(**kw)
        monkeypatch.setattr(ps, "client", lambda: f)
        return f
    return install


def test_native_signup_is_untouched(idp):
    f = idp()
    out = ps.handler(ev(source="PreSignUp_SignUp"))
    assert out["response"] == {} and not f.links and not f.filters


def test_verified_google_email_links_to_the_existing_confirmed_account(idp):
    f = idp(users=[user("native-uuid")])
    out = ps.handler(ev())
    assert f.links == [{"UserPoolId": POOL, "DestinationUser": {"ProviderName": "Cognito", "ProviderAttributeValue": "native-uuid"},
                        "SourceUser": {"ProviderName": "Google", "ProviderAttributeName": "Cognito_Subject", "ProviderAttributeValue": "123"}}]
    assert "autoConfirmUser" not in out["response"]   # linked: no new user is created


def test_apple_links_and_keeps_dots_in_the_subject(idp):
    f = idp(users=[user("n1")])
    ps.handler(ev(name="SignInWithApple_001.abc.0042", verified=None))   # Apple: no flag surfaced, still verified
    assert f.links[0]["SourceUser"]["ProviderName"] == "SignInWithApple" and f.links[0]["SourceUser"]["ProviderAttributeValue"] == "001.abc.0042"


def test_apple_explicit_false_is_not_verified(idp):
    f = idp(users=[user("n1")])
    out = ps.handler(ev(name="SignInWithApple_1", verified="false"))
    assert not f.links and out["response"] == {"autoConfirmUser": True}


@pytest.mark.parametrize("flag", ["false", None, "", "no"])
def test_unverified_google_email_never_links(idp, flag):
    f = idp(users=[user("native-uuid")])
    out = ps.handler(ev(verified=flag))
    assert not f.links and not f.filters   # does not even look the account up
    assert out["response"] == {"autoConfirmUser": True}   # created, but its email is NOT auto-verified


def test_no_existing_account_creates_confirmed_verified_user(idp):
    f = idp()
    out = ps.handler(ev())
    assert not f.links and out["response"] == {"autoConfirmUser": True, "autoVerifyEmail": True}


def test_apple_private_relay_is_a_separate_account(idp):
    f = idp(users=[user("n", email="x@privaterelay.appleid.com")])
    out = ps.handler(ev(name="SignInWithApple_9", email="X@PrivateRelay.AppleID.com", verified=None))
    assert not f.links and not f.filters and out["response"]["autoConfirmUser"] is True


def test_no_email_creates_unlinked(idp):
    f = idp(users=[user("n")])
    out = ps.handler(ev(email=""))
    assert not f.links and out["response"] == {"autoConfirmUser": True}


@pytest.mark.parametrize("status,verified", [("UNCONFIRMED", "false"), ("UNCONFIRMED", "true"), ("CONFIRMED", "false"), ("FORCE_CHANGE_PASSWORD", "true"), ("ARCHIVED", "true")])
def test_never_link_into_an_account_whose_email_was_not_proven(idp, status, verified):
    f = idp(users=[user("squatter", status=status, verified=verified)])
    out = ps.handler(ev())
    assert not f.links and out["response"]["autoConfirmUser"] is True


def test_email_case_is_matched(idp):
    f = idp(users=[user("n", email="a@b.com")])
    ps.handler(ev(email="A@B.com"))
    assert f.links and f.filters == ['email = "A@B.com"', 'email = "a@b.com"']


def test_filter_injection_is_refused(idp):
    f = idp(users=[user("n")])
    out = ps.handler(ev(email='a@b.com" or email = "x'))
    assert not f.links and out["response"]["autoConfirmUser"] is True


def test_two_confirmed_accounts_with_one_email_fails_closed(idp):
    f = idp(users=[user("n1"), user("n2")])
    with pytest.raises(RuntimeError):
        ps.handler(ev())
    assert not f.links


def test_federated_profile_is_ignored_when_a_native_account_exists(idp):
    f = idp(users=[user("Google_old", status="EXTERNAL_PROVIDER"), user("native")])
    ps.handler(ev(name="SignInWithApple_5", verified=None))
    assert f.links[0]["DestinationUser"] == {"ProviderName": "Cognito", "ProviderAttributeValue": "native"}


def test_cross_provider_links_to_the_first_federated_account(idp):
    f = idp(users=[user("Google_77", status="EXTERNAL_PROVIDER")])
    ps.handler(ev(name="SignInWithApple_5", verified=None))
    assert f.links[0]["DestinationUser"] == {"ProviderName": "Google", "ProviderAttributeName": "Cognito_Subject", "ProviderAttributeValue": "77"}


def test_cross_provider_refused_by_cognito_falls_back_to_a_separate_account(idp):
    idp(users=[user("Google_77", status="EXTERNAL_PROVIDER")], link_error=cerr("InvalidParameterException", "Destination user is not valid"))
    out = ps.handler(ev(name="SignInWithApple_5", verified=None))
    assert out["response"]["autoConfirmUser"] is True


def test_the_federated_user_itself_is_not_its_own_destination(idp):
    f = idp(users=[user("Google_123", status="EXTERNAL_PROVIDER")])
    out = ps.handler(ev())
    assert not f.links and out["response"]["autoConfirmUser"] is True


def test_race_already_linked_is_success_and_idempotent(idp):
    f = idp(users=[user("native")], link_error=cerr("InvalidParameterException", "SourceUser is already linked to another user."))
    out = ps.handler(ev())
    assert "autoConfirmUser" not in out["response"]
    assert ps.handler(ev())["response"] == out["response"]   # idempotent: the same event gives the same answer


@pytest.mark.parametrize("code,msg", [("TooManyRequestsException", "slow down"), ("InternalErrorException", "boom"), ("InvalidParameterException", "something else"), ("NotAuthorizedException", "no")])
def test_unexpected_errors_fail_closed(idp, code, msg):
    idp(users=[user("native")], link_error=cerr(code, msg))
    with pytest.raises(ClientError):
        ps.handler(ev())


def test_unknown_username_shape_creates_unlinked(idp):
    f = idp(users=[user("n")])
    out = ps.handler(ev(name="Facebook_1"))
    assert not f.links and out["response"] == {"autoConfirmUser": True}


def test_logs_never_contain_the_email(idp, caplog):
    idp(users=[user("native")])
    with caplog.at_level("INFO"):
        ps.handler(ev(email="a@b.com"))
        idp(users=[user("n", status="UNCONFIRMED")])
        ps.handler(ev(email="a@b.com"))
    assert caplog.records and "a@b.com" not in caplog.text and "b.com" not in caplog.text


# ---------- CDK template ----------
@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, root)
    cwd = os.getcwd()
    os.chdir(root)   # Code.from_asset("lambdas") is relative to backend/
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(**ctx):
            key = tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": "qa", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-social-{len(cache)}"))
                stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def _of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def test_flags_off_has_no_providers_no_trigger_and_clients_stay_cognito_only(synth):
    t = synth()
    assert not _of(t, "AWS::Cognito::UserPoolIdentityProvider")
    for c in _of(t, "AWS::Cognito::UserPoolClient").values():
        assert c["Properties"]["SupportedIdentityProviders"] == ["COGNITO"]
    pool = next(iter(_of(t, "AWS::Cognito::UserPool").values()))["Properties"]
    assert "LambdaConfig" not in pool
    assert not [k for k in t["Resources"] if "AuthPreSignUp" in k]
    assert t["Outputs"]["SocialProviders"]["Value"] == "none"


def test_flags_off_template_is_identical_to_an_unset_flag(synth):
    assert synth() == synth(socialGoogle="0", socialApple="false")


def test_flags_on_adds_providers_and_both_clients_list_them(synth):
    t = synth(socialGoogle="1", socialApple="1")
    idps = {v["Properties"]["ProviderName"]: v["Properties"] for v in _of(t, "AWS::Cognito::UserPoolIdentityProvider").values()}
    assert set(idps) == {"Google", "SignInWithApple"}
    assert idps["Google"]["AttributeMapping"]["email"] == "email" and idps["Google"]["AttributeMapping"]["email_verified"] == "email_verified"
    for c in _of(t, "AWS::Cognito::UserPoolClient").values():
        assert c["Properties"]["SupportedIdentityProviders"] == ["COGNITO", "Google", "SignInWithApple"]
        assert c["DependsOn"]
    assert "Google" in t["Outputs"]["SocialProviders"]["Value"] and "SignInWithApple" in t["Outputs"]["SocialProviders"]["Value"]
    assert "oauth2/idpresponse" in json.dumps(t["Outputs"]["SocialRedirectUri"])
    pool = next(iter(_of(t, "AWS::Cognito::UserPool").values()))["Properties"]
    assert "PreSignUp" in pool["LambdaConfig"]


def test_one_flag_only_adds_that_provider(synth):
    t = synth(socialApple="1")
    assert [v["Properties"]["ProviderName"] for v in _of(t, "AWS::Cognito::UserPoolIdentityProvider").values()] == ["SignInWithApple"]
    assert {tuple(c["Properties"]["SupportedIdentityProviders"]) for c in _of(t, "AWS::Cognito::UserPoolClient").values()} == {("COGNITO", "SignInWithApple")}


def test_secrets_are_dynamic_references_never_values(synth):
    text = json.dumps(synth(socialGoogle="1", socialApple="1")["Resources"])
    for n in ("google_oauth_client_secret", "apple_private_key"):
        assert f"{{{{resolve:secretsmanager:/videomk/{n}:SecretString" in text
    for n in ("google_oauth_client_id", "apple_services_id", "apple_team_id", "apple_key_id"):
        assert f"{{{{resolve:ssm:/videomk/{n}}}}}" in text
    assert "BEGIN PRIVATE KEY" not in text and "GOCSPX" not in text and "39ANXJNUTL" not in text


def test_trigger_is_least_privilege(synth):
    t = synth(socialGoogle="1", socialApple="1")
    pools = [k for k, v in t["Resources"].items() if v["Type"] == "AWS::Cognito::UserPool"]
    pol = t["Resources"][next(k for k in t["Resources"] if "PreSignUpPolicy" in k and t["Resources"][k]["Type"] == "AWS::IAM::Policy")]
    stmts = pol["Properties"]["PolicyDocument"]["Statement"]
    assert len(stmts) == 1 and sorted(stmts[0]["Action"]) == ["cognito-idp:AdminLinkProviderForUser", "cognito-idp:ListUsers"] and stmts[0]["Effect"] == "Allow"
    assert stmts[0]["Resource"] == {"Fn::GetAtt": [pools[0], "Arn"]}
    fn_role = pol["Properties"]["Roles"][0]["Ref"]
    # no other policy gives that role anything beyond logging
    for p in _of(t, "AWS::IAM::Policy").values():
        if {"Ref": fn_role} in p["Properties"].get("Roles", []) and p is not pol:
            assert False, "the trigger role has an extra policy"


def test_missing_values_check_names_what_is_absent():
    import social_auth

    class Boom(Exception):
        pass

    class C:
        def __init__(self, ok):
            self.ok = ok

        def get_parameter(self, Name):
            if Name in self.ok:
                return {"Parameter": {"Value": "x"}}
            raise Boom()

        def describe_secret(self, SecretId):
            if SecretId in self.ok:
                return {"Name": SecretId}
            raise Boom()

    class S:
        def client(self, n):
            return C({"/videomk/google_oauth_client_id"})
    m = social_auth.missing_values(S(), True, False)
    assert len(m) == 1 and "google_oauth_client_secret" in m[0]
    assert len(social_auth.missing_values(S(), True, True)) == 5
    assert social_auth.missing_values(S(), False, False) == []
