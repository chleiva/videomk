"""The web app at app.videomk.com (docs/WEB_REDESIGN_2026.md, work package 0): static files in a private bucket behind CloudFront.

Own stack in us-east-1 (CloudFront certificates must live there), prod account, next to the marketing stack (site_stack.py): the hosted zone for
videomk.com already exists (it belongs to that stack), so it is imported by id. The certificate validates through DNS in that zone.
  * the app's pages are folders (`/generations` -> `/generations/index.html`); unknown addresses fall back to `/index.html` (the app root sends people on);
  * `_astro/*` files carry a content hash: cached for a year; HTML is never cached by browsers (`no-cache`), so a deploy shows at once;
  * security headers include a Content-Security-Policy for the app (API, sign-in host and the S3 upload/playback hosts only), HSTS and `noindex`
    (the app is behind a sign-in; the public pages on videomk.com are what search engines should see);
  * /privacy, /terms and /support live on videomk.com: the footer links of the app's pages go there with a 301.
"""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as r53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

APP_HOST = "app.videomk.com"
MARKETING_HOST = "videomk.com"
ZONE_ID = "Z07620702J1XHOWB4O7NZ"   # videomk.com in the prod account (the marketing stack owns it)
API_HOST = "api.videomk.com"
AUTH_HOST = "login.videomk.com"

# ES5.1 (CloudFront Functions): the public pages go back to videomk.com, folders get their index.html, everything else is served as is.
APP_FUNCTION = (
    "function handler(e){var r=e.request;var u=r.uri;"
    "var m=/^(\\/es)?\\/(privacy|terms|support)(\\/(index\\.html)?)?$/.exec(u);"
    "if(m){return {statusCode:301,statusDescription:'Moved Permanently',headers:{location:{value:'https://" + MARKETING_HOST + "'+(m[1]||'')+'/'+m[2]+'/'}}};}"
    "if(u.endsWith('/')){r.uri=u+'index.html';}else if(u.indexOf('.')<0){r.uri=u+'/index.html';}return r;}"
)

# `'unsafe-inline'` for scripts and styles: Astro writes small inline scripts (theme, locale) and component styles into the pages. Everything else is
# locked down: no framing, no plugins, forms only to the sign-in host, connections only to our API, sign-in and the S3 upload hosts.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: https:",
    "font-src 'self' data:",
    f"connect-src 'self' https://{API_HOST} https://{AUTH_HOST} https://*.s3.amazonaws.com https://*.s3.us-west-2.amazonaws.com https://*.s3.eu-west-1.amazonaws.com",
    f"form-action 'self' https://{AUTH_HOST} https://*.s3.amazonaws.com https://*.s3.us-west-2.amazonaws.com https://*.s3.eu-west-1.amazonaws.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
])

NO_CACHE = "no-cache, max-age=0, must-revalidate"
IMMUTABLE = "public, max-age=31536000, immutable"
SHORT = "public, max-age=3600"


class AppSiteStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, app_dir: str, **kw) -> None:
        super().__init__(scope, cid, **kw)
        zone = r53.HostedZone.from_hosted_zone_attributes(self, "Zone", hosted_zone_id=ZONE_ID, zone_name=MARKETING_HOST)
        cert = acm.Certificate(self, "Cert", domain_name=APP_HOST, validation=acm.CertificateValidation.from_dns(zone))
        bucket = s3.Bucket(self, "Bucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True, removal_policy=RemovalPolicy.RETAIN)
        rewrite = cf.Function(self, "Rewrite", code=cf.FunctionCode.from_inline(APP_FUNCTION))
        headers = cf.ResponseHeadersPolicy(
            self, "Headers",
            security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
                strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(access_control_max_age=Duration.days(365), include_subdomains=True, override=True),
                content_type_options=cf.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cf.ResponseHeadersFrameOptions(frame_option=cf.HeadersFrameOption.DENY, override=True),
                referrer_policy=cf.ResponseHeadersReferrerPolicy(referrer_policy=cf.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN, override=True),
                content_security_policy=cf.ResponseHeadersContentSecurityPolicy(content_security_policy=CSP, override=True)),
            custom_headers_behavior=cf.ResponseCustomHeadersBehavior(custom_headers=[
                cf.ResponseCustomHeader(header="X-Robots-Tag", value="noindex, nofollow", override=True),
                cf.ResponseCustomHeader(header="Permissions-Policy", value="camera=(), geolocation=(), microphone=(self), payment=()", override=True),
            ]))
        dist = cf.Distribution(
            self, "Cdn", domain_names=[APP_HOST], certificate=cert, default_root_object="index.html", minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            http_version=cf.HttpVersion.HTTP2_AND_3,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket), viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                response_headers_policy=headers, compress=True,
                function_associations=[cf.FunctionAssociation(function=rewrite, event_type=cf.FunctionEventType.VIEWER_REQUEST)]),
            # An address with no file behind it answers the app's root page (it sends signed-in people to their videos, others to sign-in).
            error_responses=[cf.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html", ttl=Duration.seconds(10)),
                             cf.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html", ttl=Duration.seconds(10))])
        # Three deployments, none pruning (a page cached in a browser may still ask for last week's hashed file): hashed files, the rest, then the HTML
        # (last, with the cache invalidation, so a page never points at a file that is not there yet).
        hashed = s3deploy.BucketDeployment(self, "Hashed", sources=[s3deploy.Source.asset(app_dir)], destination_bucket=bucket, exclude=["*"], include=["_astro/*"], prune=False,
                                           cache_control=[s3deploy.CacheControl.from_string(IMMUTABLE)], memory_limit=512)
        other = s3deploy.BucketDeployment(self, "Other", sources=[s3deploy.Source.asset(app_dir)], destination_bucket=bucket, exclude=["*.html", "_astro/*"], prune=False,
                                          cache_control=[s3deploy.CacheControl.from_string(SHORT)], memory_limit=512)
        pages = s3deploy.BucketDeployment(self, "Pages", sources=[s3deploy.Source.asset(app_dir)], destination_bucket=bucket, exclude=["*"], include=["*.html"], prune=False,
                                          cache_control=[s3deploy.CacheControl.from_string(NO_CACHE)], distribution=dist, distribution_paths=["/*"], memory_limit=512)
        pages.node.add_dependency(hashed)
        pages.node.add_dependency(other)
        target = r53.RecordTarget.from_alias(targets.CloudFrontTarget(dist))
        r53.ARecord(self, "A", zone=zone, record_name=APP_HOST, target=target)
        r53.AaaaRecord(self, "AAAA", zone=zone, record_name=APP_HOST, target=target)
        CfnOutput(self, "Url", value=f"https://{APP_HOST}")
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=dist.distribution_id)
