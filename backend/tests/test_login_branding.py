"""Sign-in branding: settings are well formed and readable (WCAG), assets fit Cognito's rules, the stack creates one branding per app client."""
import base64
import os
import re
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambdas"))

import login_branding as lb  # noqa: E402


def lum(h):
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb_ = sorted((lum(a[:6]), lum(b[:6])), reverse=True)
    return (la + 0.05) / (lb_ + 0.05)


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}/{i}")
    else:
        yield path, o


def test_every_colour_is_rrggbbaa():
    for path, v in walk(lb.settings()):
        if path.lower().endswith("color") and isinstance(v, str):
            assert re.fullmatch(r"[0-9a-fA-F]{8}", v), (path, v)


def test_light_dark_scheme_default_is_dynamic_and_overridable():
    assert lb.settings()["categories"]["global"]["colorSchemeMode"] == "DYNAMIC"
    assert lb.settings("LIGHT")["categories"]["global"]["colorSchemeMode"] == "LIGHT"


@pytest.mark.parametrize("mode,pal", [("lightMode", lb.LIGHT), ("darkMode", lb.DARK)])
def test_text_contrast_meets_wcag_aa(mode, pal):
    s = lb.settings()
    c = s["components"]
    btn = c["primaryButton"][mode]
    assert contrast(btn["defaults"]["textColor"], btn["defaults"]["backgroundColor"]) >= 4.5
    assert contrast(btn["hover"]["textColor"], btn["hover"]["backgroundColor"]) >= 4.5
    page = c["pageBackground"][mode]["color"]
    form = c["form"][mode]["backgroundColor"]
    for key in ("headingColor", "bodyColor"):
        assert contrast(c["pageText"][mode][key], form) >= 4.5, (mode, key)
    cl = s["componentClasses"]
    assert contrast(cl["link"][mode]["defaults"]["textColor"], form) >= 4.5
    assert contrast(cl["inputLabel"][mode]["textColor"], form) >= 4.5
    assert contrast(cl["inputDescription"][mode]["textColor"], form) >= 4.5
    assert contrast(cl["input"][mode]["placeholderColor"], cl["input"][mode]["defaults"]["backgroundColor"]) >= 3.0
    assert contrast(cl["focusState"][mode]["borderColor"], form) >= 3.0   # focus ring is a UI component
    assert page and form


def test_no_clutter_and_social_first():
    s = lb.settings()
    assert s["categories"]["form"]["displayGraphics"] is False
    assert s["categories"]["global"]["pageHeader"]["enabled"] is False and s["categories"]["global"]["pageFooter"]["enabled"] is False
    order = s["categories"]["auth"]["authMethodOrder"][0]
    assert [o["type"] for o in order] == ["FEDERATED", "USERNAME_PASSWORD"]   # Google/Apple buttons above the email form when enabled
    assert s["components"]["form"]["logo"]["enabled"] is True


def test_assets_fit_cognito_rules():
    a = lb.assets()
    kinds = {(x["category"], x["color_mode"]) for x in a}
    for mode in ("LIGHT", "DARK"):
        assert {("FORM_LOGO", mode), ("PAGE_BACKGROUND", mode), ("FAVICON_SVG", mode), ("FAVICON_ICO", mode)} <= kinds
    for x in a:
        raw = base64.b64decode(x["bytes"])
        assert 0 < len(raw) <= 2 * 1024 * 1024
        if x["extension"] == "SVG":
            txt = raw.decode()
            assert txt.lstrip().startswith("<svg") and "<script" not in txt and "javascript:" not in txt and "<image" not in txt
        if x["category"] == "FORM_LOGO":   # Cognito: logo width:height between 1:1 and 4:1
            w, h = [float(v) for v in re.search(r'width="([\d.]+)" height="([\d.]+)"', raw.decode()).groups()]
            assert 1.0 <= w / h <= 4.0, (w, h)


def test_light_and_dark_logos_differ_in_ink():
    by = {(x["category"], x["color_mode"]): base64.b64decode(x["bytes"]).decode() for x in lb.assets() if x["extension"] == "SVG"}
    assert by[("FORM_LOGO", "LIGHT")] != by[("FORM_LOGO", "DARK")]
    assert "#11142b" in by[("FORM_LOGO", "LIGHT")] and "#f3f4fb" in by[("FORM_LOGO", "DARK")]


@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(stage="qa", **ctx):
            ctx.setdefault("engine", "v2")
            key = (stage,) + tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": stage, **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-lb-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                acct, region = ("464863885161", "us-west-2") if stage == "prod" else ("123456789012", "eu-west-1")
                stack = BackendStack(app, f"videomk-{stage}", stage=stage, stage_cfg={"account": acct, "region": region, "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account=acct, region=region))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def test_stack_has_one_branding_per_client_and_domain_on_managed_login(synth):
    t = synth("qa")
    brandings = of(t, "AWS::Cognito::ManagedLoginBranding")
    assert len(brandings) == 2
    clients = of(t, "AWS::Cognito::UserPoolClient")
    assert len(clients) == 2
    for b in brandings.values():
        p = b["Properties"]
        assert p["UseCognitoProvidedValues"] is False and p["Settings"] and len(p["Assets"]) == 8
        assert {a["Category"] for a in p["Assets"]} == {"FORM_LOGO", "PAGE_BACKGROUND", "FAVICON_SVG", "FAVICON_ICO"}
        assert any(d.startswith("UserPoolHostedUi") for d in b.get("DependsOn", []))
    (dom,) = of(t, "AWS::Cognito::UserPoolDomain").values()
    assert dom["Properties"]["ManagedLoginVersion"] == 2


def test_prod_with_custom_domain_also_switches(synth):
    t = synth("prod", authDomain="login.videomk.com", authCertArn="arn:aws:acm:us-east-1:464863885161:certificate/x", authZoneId="Z123")
    (dom,) = of(t, "AWS::Cognito::UserPoolDomain").values()
    assert dom["Properties"]["ManagedLoginVersion"] == 2 and dom["Properties"]["Domain"] == "login.videomk.com"
    assert len(of(t, "AWS::Cognito::ManagedLoginBranding")) == 2


def test_flag_off_keeps_the_classic_page(synth):
    t = synth("qa", loginBranding="0")
    assert not of(t, "AWS::Cognito::ManagedLoginBranding")
    (dom,) = of(t, "AWS::Cognito::UserPoolDomain").values()
    assert "ManagedLoginVersion" not in dom["Properties"]
