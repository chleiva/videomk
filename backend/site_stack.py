"""The public website at videomk.com: privacy, terms, support, delete-account and a landing page, as static files.

Own stack in us-east-1 (CloudFront certificates must live there), prod account. Two phases because a certificate validates through DNS, and DNS only
works once the domain's name servers point at the new zone:
  1. `-c sitePhase=zone`  creates the hosted zone only; copy its name servers into the domain registration (scripts/site.sh does it).
  2. `-c sitePhase=full`  adds the certificate, the private bucket, CloudFront, the DNS records and uploads the files.
"""
from aws_cdk import CfnOutput, Duration, Fn, RemovalPolicy, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as r53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


APP_HOST = "app.videomk.com"
APP_PATHS = "signin|generations|wallet|feedback|watch|edit|questions|auth\\/callback"   # the app screens that used to live on videomk.com
# CloudFront Functions run ES5.1: no template strings, no arrow functions. The query values in the event are the raw (still percent-encoded) text of the request: copied as they are (encoding them again would turn %20 into %2520).
MARKETING_FUNCTION = (
    "function handler(e){var r=e.request;var u=r.uri;"
    "var m=/^\\/(" + APP_PATHS + ")(\\/(index\\.html)?)?$/.exec(u);"
    "if(m){var q=[];var qs=r.querystring||{};for(var k in qs){var o=qs[k];"
    "if(o.multiValue){for(var i=0;i<o.multiValue.length;i++){q.push(k+'='+o.multiValue[i].value);}}"
    "else{q.push(k+'='+o.value);}}"
    "return {statusCode:301,statusDescription:'Moved Permanently',headers:{location:{value:'https://" + APP_HOST + "/'+m[1]+(q.length?'?'+q.join('&'):'')}}};}"
    "if(u.endsWith('/')){r.uri=u+'index.html';}else if(u.indexOf('.')<0){r.uri=u+'/index.html';}return r;}"
)


class SiteStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, domain: str, phase: str, site_dir: str, **kw) -> None:
        super().__init__(scope, cid, **kw)
        zone = r53.PublicHostedZone(self, "Zone", zone_name=domain)
        zone.apply_removal_policy(RemovalPolicy.RETAIN)
        CfnOutput(self, "NameServers", value=Fn.join(" ", zone.hosted_zone_name_servers or []))
        if phase != "full":
            return
        names = [domain, f"www.{domain}"]
        cert = acm.Certificate(self, "Cert", domain_name=domain, subject_alternative_names=[names[1]], validation=acm.CertificateValidation.from_dns(zone))
        bucket = s3.Bucket(self, "Bucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True, removal_policy=RemovalPolicy.RETAIN)
        # /privacy -> /privacy/index.html (the pages are folders). The web app moved to app.videomk.com (docs/WEB_REDESIGN_2026.md): its old addresses 301 there,
        # keeping the path and the query string. The public pages (privacy, terms, support, delete-account) stay here.
        rewrite = cf.Function(self, "Rewrite", code=cf.FunctionCode.from_inline(MARKETING_FUNCTION))
        headers = cf.ResponseHeadersPolicy(self, "Headers", security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
            strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(access_control_max_age=Duration.days(365), include_subdomains=True, override=True),
            content_type_options=cf.ResponseHeadersContentTypeOptions(override=True),
            frame_options=cf.ResponseHeadersFrameOptions(frame_option=cf.HeadersFrameOption.DENY, override=True),
            referrer_policy=cf.ResponseHeadersReferrerPolicy(referrer_policy=cf.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN, override=True)))
        dist = cf.Distribution(
            self, "Cdn", domain_names=names, certificate=cert, default_root_object="index.html", minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket), viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                response_headers_policy=headers, function_associations=[cf.FunctionAssociation(function=rewrite, event_type=cf.FunctionEventType.VIEWER_REQUEST)]),
            error_responses=[cf.ErrorResponse(http_status=403, response_http_status=404, response_page_path="/404.html", ttl=Duration.minutes(5)),
                             cf.ErrorResponse(http_status=404, response_http_status=404, response_page_path="/404.html", ttl=Duration.minutes(5))])
        s3deploy.BucketDeployment(self, "Files", sources=[s3deploy.Source.asset(site_dir)], destination_bucket=bucket, distribution=dist, distribution_paths=["/*"])
        for i, n in enumerate(names):
            target = r53.RecordTarget.from_alias(targets.CloudFrontTarget(dist))
            r53.ARecord(self, f"A{i}", zone=zone, record_name=n, target=target)
            r53.AaaaRecord(self, f"AAAA{i}", zone=zone, record_name=n, target=target)
        CfnOutput(self, "Url", value=f"https://{domain}")
