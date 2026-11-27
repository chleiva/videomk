"""The web app's hosting (app.videomk.com, work package 0 of docs/WEB_REDESIGN_2026.md): private bucket + CloudFront, DNS in the imported zone, CSP, caching, redirects.

Plus: the old app addresses on videomk.com 301 to the app (the CloudFront Function is run through node here, as ES5 code), the prod sign-in URLs and the S3 upload origins."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
ZONE = "Z07620702J1XHOWB4O7NZ"


@pytest.fixture(scope="module")
def t(tmp_path_factory):
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    from app_site_stack import AppSiteStack
    d = tmp_path_factory.mktemp("appdir")
    (d / "index.html").write_text("x")
    app = cdk.App(outdir=str(tmp_path_factory.mktemp("app")))
    st = AppSiteStack(app, "videomk-app-site", app_dir=str(d), env=cdk.Environment(account="464863885161", region="us-east-1"))
    return Template.from_stack(st).to_json()


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def test_distribution_serves_only_the_app_host_over_https_with_oac(t):
    (d,) = of(t, "AWS::CloudFront::Distribution").values()
    c = d["Properties"]["DistributionConfig"]
    assert c["Aliases"] == ["app.videomk.com"] and c["DefaultRootObject"] == "index.html"
    assert c["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    assert c["ViewerCertificate"]["MinimumProtocolVersion"] == "TLSv1.2_2021"
    assert len(of(t, "AWS::CloudFront::OriginAccessControl")) == 1
    codes = {e["ErrorCode"]: e for e in c["CustomErrorResponses"]}
    assert codes[403]["ResponsePagePath"] == "/index.html" and codes[404]["ResponseCode"] == 200   # unknown address -> the app root


def test_certificate_validates_through_dns_in_the_existing_zone_and_no_zone_is_created(t):
    assert not of(t, "AWS::Route53::HostedZone")
    (c,) = of(t, "AWS::CertificateManager::Certificate").values()
    assert c["Properties"]["DomainName"] == "app.videomk.com" and c["Properties"]["ValidationMethod"] == "DNS"
    assert c["Properties"]["DomainValidationOptions"][0]["HostedZoneId"] == ZONE
    recs = [v["Properties"] for v in of(t, "AWS::Route53::RecordSet").values()]
    assert sorted(r["Type"] for r in recs) == ["A", "AAAA"] and all(r["HostedZoneId"] == ZONE and r["Name"] == "app.videomk.com." for r in recs)


def test_bucket_is_private_encrypted_tls_only_and_retained(t):
    (b,) = of(t, "AWS::S3::Bucket").values()
    p = b["Properties"]
    assert all(p["PublicAccessBlockConfiguration"].values()) and b["DeletionPolicy"] == "Retain"
    assert p["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    pol = json.dumps(of(t, "AWS::S3::BucketPolicy"))
    assert "aws:SecureTransport" in pol and "cloudfront.amazonaws.com" in pol


def test_security_headers_csp_and_noindex(t):
    (h,) = of(t, "AWS::CloudFront::ResponseHeadersPolicy").values()
    cfg = h["Properties"]["ResponseHeadersPolicyConfig"]
    sec = cfg["SecurityHeadersConfig"]
    assert sec["StrictTransportSecurity"]["AccessControlMaxAgeSec"] == 365 * 86400 and sec["FrameOptions"]["FrameOption"] == "DENY"
    csp = sec["ContentSecurityPolicy"]["ContentSecurityPolicy"]
    for part in ("frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "connect-src 'self' https://backend.videomk.com https://login.videomk.com", "form-action 'self' https://login.videomk.com"):
        assert part in csp
    assert "*" not in csp.replace("https://*.s3", "")   # no wildcard hosts except the S3 upload hosts
    custom = {x["Header"]: x["Value"] for x in cfg["CustomHeadersConfig"]["Items"]}
    assert custom["X-Robots-Tag"].startswith("noindex")


def test_cache_rules_hashed_files_immutable_html_never_cached(t):
    deployments = [v["Properties"] for v in of(t, "Custom::CDKBucketDeployment").values()]
    caches = sorted(d["SystemMetadata"]["cache-control"] for d in deployments)
    assert any("immutable" in c and "31536000" in c for c in caches) and any("no-cache" in c for c in caches) and any("max-age=3600" in c for c in caches)
    html = [d for d in deployments if "no-cache" in d["SystemMetadata"]["cache-control"]][0]
    assert html["Include"] == ["*.html"] and html["DistributionPaths"] == ["/*"]   # the HTML deploy goes last and invalidates
    assert all(d["Prune"] is False for d in deployments)


# ---- the CloudFront Functions, run with node (they are ES5.1, no template strings)
NODE = shutil.which("node")


def run_fn(code, uri, qs=None):
    js = code + "\nconsole.log(JSON.stringify(handler({request:{uri:%s,querystring:%s}})));" % (json.dumps(uri), json.dumps(qs or {}))
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not NODE, reason="node needed")
def test_old_app_addresses_on_the_marketing_site_redirect_to_the_app():
    from site_stack import MARKETING_FUNCTION as F
    r = run_fn(F, "/generations/index.html")
    assert r["statusCode"] == 301 and r["headers"]["location"]["value"] == "https://app.videomk.com/generations"
    assert run_fn(F, "/watch", {"id": {"value": "a%20b%26c"}})["headers"]["location"]["value"] == "https://app.videomk.com/watch?id=a%20b%26c"   # raw values stay raw
    assert run_fn(F, "/auth/callback/", {"code": {"value": "x"}, "state": {"value": "y"}})["headers"]["location"]["value"] == "https://app.videomk.com/auth/callback?code=x&state=y"
    assert run_fn(F, "/edit/index.html", {"id": {"value": "1"}})["headers"]["location"]["value"] == "https://app.videomk.com/edit?id=1"
    for p in ("/signin", "/wallet", "/feedback", "/questions", "/new", "/media", "/settings"):
        assert run_fn(F, p)["statusCode"] == 301


@pytest.mark.skipif(not NODE, reason="node needed")
def test_public_pages_stay_on_the_marketing_site_and_keep_their_rewrite():
    from site_stack import MARKETING_FUNCTION as F
    for p in ("/privacy", "/privacy/", "/terms", "/support", "/delete-account", "/es/privacy/", "/"):
        r = run_fn(F, p)
        assert "statusCode" not in r and r["uri"].endswith("index.html"), p
    assert run_fn(F, "/_astro/x.css")["uri"] == "/_astro/x.css" and run_fn(F, "/signin-help")["uri"] == "/signin-help/index.html"   # only the exact app addresses move


@pytest.mark.skipif(not NODE, reason="node needed")
def test_app_function_sends_public_pages_back_and_rewrites_folders():
    from app_site_stack import APP_FUNCTION as F
    assert run_fn(F, "/privacy")["headers"]["location"]["value"] == "https://videomk.com/privacy/"
    assert run_fn(F, "/es/terms/index.html")["headers"]["location"]["value"] == "https://videomk.com/es/terms/"
    assert run_fn(F, "/generations")["uri"] == "/generations/index.html" and run_fn(F, "/")["uri"] == "/index.html"
    assert run_fn(F, "/es")["headers"]["location"]["value"] == "https://videomk.com/es/" and run_fn(F, "/es/")["statusCode"] == 301   # the Spanish home is the marketing site's
    assert run_fn(F, "/es/delete-account")["uri"] == "/es/delete-account/index.html"
    assert run_fn(F, "/delete-account")["uri"] == "/delete-account/index.html"   # stays in the app (the Apple/Google web return address)


def test_prod_signin_urls_and_upload_origins():
    from backend_stack import _web_origins
    st = json.load(open(os.path.join(ROOT, "stages.json")))
    prod, qa = st["prod"], st["qa"]
    assert prod["callbackUrls"][0] == "https://app.videomk.com/auth/callback" and prod["logoutUrls"][0] == "https://app.videomk.com/"
    assert all(u.startswith("https://") for u in prod["callbackUrls"] + prod["logoutUrls"])   # no localhost in prod
    assert prod["domain"] == "videomk.com" and prod["apiHost"] == "backend.videomk.com"   # api.videomk.com is held by another AWS account
    assert "https://app.videomk.com" in _web_origins(prod) and "https://app.videomk.com" in _web_origins(qa)
