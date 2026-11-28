"""Share links for videos, in a stack of its own (docs/SHARE_PREVIEWS_2026-11-28.md): the main stack is near its 500-resource limit and has no part in this.

    cdk deploy videomk-<stage>-share -c stage=<stage> -c share=1 -c sharePoolId=... -c shareClientIds=a,b -c shareVideosTable=<name>

What it holds: a private bucket of shared copies (<token>/index.html, og.jpg, poster.jpg, video.mp4), a CloudFront distribution in front of it (the only reader; HTTPS only,
`noindex`, no framing of the page by others), and one function behind an HTTP API with the main API's Cognito sign-in (POST/GET/DELETE .../videos/{id}/share).
The main stack learns nothing: no cross-stack reference. The function reads the main stack's videos table by NAME and copies from its bucket by NAME (both follow the
naming of backend_stack.py); with this stack absent the apps simply have no share link to offer (they ask `capabilities`/config for the share API address and hide the button).

Address of a share: https://<share host>/<token>. The host is the distribution's own domain until a custom one is chosen (-c shareHost=share.videomk.com
-c shareCertArn=<ACM certificate in us-east-1>; the DNS record is then one alias to the distribution, made by hand or by the site stack).
"""
import os
import shutil
from typing import List, Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_cloudfront as cf, aws_cloudfront_origins as origins, aws_iam as iam, aws_lambda as _lambda, aws_logs as logs, aws_s3 as s3
from aws_cdk import aws_apigatewayv2 as apigw2, aws_apigatewayv2_authorizers as authorizers, aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_certificatemanager as acm
from constructs import Construct

HERE = os.path.dirname(os.path.abspath(__file__))

# the page is a folder: /<token> and /<token>/ are /<token>/index.html (ES5.1, CloudFront Functions)
PAGE_FUNCTION = ("function handler(e){var r=e.request;var u=r.uri;"
                 "if(/^\\/[A-Za-z0-9_-]{22}\\/?$/.test(u)){r.uri='/'+u.replace(/\\//g,'')+'/index.html';}return r;}")


def bundle(out_dir: Optional[str] = None) -> str:
    """The function's code folder: the handler and the page maker, flat."""
    out = out_dir or os.path.join(HERE, "build", "share_fn")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for name in ("share_api.py", "share_page.py"):
        shutil.copyfile(os.path.join(HERE, "lambdas", "share", name), os.path.join(out, name))
    return out


class ShareStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, stage: str, videos_table_name: str, assets_bucket: str, user_pool_id: str, client_ids: List[str], share_host: Optional[str] = None,
                 cert_arn: Optional[str] = None, bundle_dir: Optional[str] = None, **kw) -> None:
        super().__init__(scope, cid, **kw)
        keep = RemovalPolicy.RETAIN if stage == "prod" else RemovalPolicy.DESTROY
        bucket = s3.Bucket(self, "ShareBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
                           removal_policy=keep, auto_delete_objects=keep == RemovalPolicy.DESTROY)
        headers = cf.ResponseHeadersPolicy(self, "ShareHeaders", security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
            content_type_options=cf.ResponseHeadersContentTypeOptions(override=True),
            referrer_policy=cf.ResponseHeadersReferrerPolicy(referrer_policy=cf.HeadersReferrerPolicy.NO_REFERRER, override=True),
            strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(access_control_max_age=Duration.days(365), include_subdomains=True, override=True),
            content_security_policy=cf.ResponseHeadersContentSecurityPolicy(override=True, content_security_policy=(
                "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"))),
            custom_headers_behavior=cf.ResponseCustomHeadersBehavior(custom_headers=[cf.ResponseCustomHeader(header="X-Robots-Tag", value="noindex, nofollow", override=True)]))
        fn = cf.Function(self, "SharePageFunction", code=cf.FunctionCode.from_inline(PAGE_FUNCTION), runtime=cf.FunctionRuntime.JS_2_0)
        cert = acm.Certificate.from_certificate_arn(self, "Cert", cert_arn) if share_host and cert_arn else None
        dist = cf.Distribution(
            self, "ShareDistribution", comment=f"videomk {stage} share links", price_class=cf.PriceClass.PRICE_CLASS_100, http_version=cf.HttpVersion.HTTP2_AND_3,
            default_behavior=cf.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(bucket), viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD, cache_policy=cf.CachePolicy.CACHING_OPTIMIZED, response_headers_policy=headers,
                                                function_associations=[cf.FunctionAssociation(function=fn, event_type=cf.FunctionEventType.VIEWER_REQUEST)]),
            domain_names=[share_host] if cert else None, certificate=cert)
        host = share_host if cert else dist.distribution_domain_name

        name = f"videomk-{stage}-share"
        log_group = logs.LogGroup(self, "ShareLogs", log_group_name=f"/aws/lambda/{name}", retention=logs.RetentionDays.TWO_WEEKS, removal_policy=RemovalPolicy.DESTROY)
        func = _lambda.Function(
            self, "ShareFn", function_name=name, runtime=_lambda.Runtime.PYTHON_3_12, architecture=_lambda.Architecture.X86_64, handler="share_api.handler",
            code=_lambda.Code.from_asset(bundle(bundle_dir)), timeout=Duration.seconds(60), memory_size=512, log_group=log_group,
            environment={"VIDEOS_TABLE": videos_table_name, "ASSETS_BUCKET": assets_bucket, "SHARE_BUCKET": bucket.bucket_name, "SHARE_HOST": host, "DISTRIBUTION_ID": dist.distribution_id},
            description="Share a video by link and take it back (docs/SHARE_PREVIEWS_2026-11-28.md)")
        table_arn = f"arn:aws:dynamodb:{self.region}:{self.account}:table/{videos_table_name}"
        func.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:UpdateItem"], resources=[table_arn]))
        func.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"arn:aws:s3:::{assets_bucket}/videos/*"]))   # copy source: the finished MP4 and the covers only
        bucket.grant_put(func)
        bucket.grant_delete(func)
        func.add_to_role_policy(iam.PolicyStatement(actions=["cloudfront:CreateInvalidation"], resources=[f"arn:aws:cloudfront::{self.account}:distribution/{dist.distribution_id}"]))

        auth = authorizers.HttpJwtAuthorizer("ShareJwt", f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool_id}", jwt_audience=client_ids)
        api = apigw2.HttpApi(self, "ShareApi", api_name=name, cors_preflight=apigw2.CorsPreflightOptions(
            allow_origins=["*"], allow_headers=["Content-Type", "Authorization"], allow_methods=[apigw2.CorsHttpMethod.GET, apigw2.CorsHttpMethod.POST, apigw2.CorsHttpMethod.DELETE]))
        api.add_routes(path="/users/{user_id}/videos/{video_id}/share", methods=[apigw2.HttpMethod.GET, apigw2.HttpMethod.POST, apigw2.HttpMethod.DELETE],
                       integration=integrations.HttpLambdaIntegration("ShareInt", func), authorizer=auth)
        self.api_url = api.api_endpoint
        CfnOutput(self, "ShareApiUrl", value=api.api_endpoint)
        CfnOutput(self, "ShareBucketName", value=bucket.bucket_name, description="Pass to the main stack: -c shareBucket=<this> (account and video deletion take shared links back)")
        CfnOutput(self, "ShareHost", value=host)
        CfnOutput(self, "ShareDistributionId", value=dist.distribution_id)
