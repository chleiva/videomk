"""Video upload in a stack of its own (docs/VIDEO_UPLOAD_2026-11-28.md section 8):

    backend/layers/build_layer.sh vidup_deps
    cdk deploy videomk-<stage>-vidup -c stage=<stage> -c vidupStack=1 [-c vidupMainValues='{...}']

Why its own stack: the main stack is near the 500-resource limit. Nothing here is a cross-stack reference: the names of the main stack's tables, plans parameter and customer pool are
read from the DEPLOYED launcher's settings at synth time (like the admin console; `-c vidupMainValues` gives them as JSON on a machine without credentials). The main stack only
learns this stack's bucket NAME (`-c videoUpload=1` on it, QA/prod flag: one variable and one read statement on the launcher, no resource), so either stack deploys or is deleted without the other.

What it creates: one private bucket (originals live under in/ for at most a day and are deleted by the worker at once; the kept copies under clips/ expire after 14 days); one HTTP API
whose every route needs a token of the customer pool; the API function (small, 15 s) and the analysis function (2 GB, 2 minutes, reserved concurrency 5, invoked once per clip);
their roles; one alarm. No table: records, counters and the money ceiling live in the main usage table under their own key prefixes (common/vidup.py), reachable only through
a LeadingKeys condition.
"""
import os
import shutil
from typing import Any, Dict, List, Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigw2
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

HERE = os.path.dirname(os.path.abspath(__file__))
OPENAI_SSM_PARAM = "/videomk/openai_api_key"
MAIN_KEYS = ("usage_table", "flags_table", "entitlements_table", "safety_table", "plans_param", "customer_pool_id", "client_ids")
LAUNCHER_FUNCTION = "VideoGenerationSFLauncher"
ORIGINAL_DAYS, KEPT_DAYS = 1, 14
FILES = (("lambdas/vidup_api.py", "vidup_api.py"), ("lambdas/vidup_analyse.py", "vidup_analyse.py"), ("lambdas/engine/llm.py", "engine/llm.py"))


def bucket_name(stage: str, account: str) -> str:
    """The one thing the two stacks share: this stack creates the bucket with this name, the main stack's launcher reads from it."""
    return f"videomk-{stage}-vidup-{account}"


def main_stack_values(session: Any) -> Dict[str, Any]:
    """The main stack's names this stack needs, from the deployed launcher's settings (and the customer pool's app clients, for the token audience)."""
    env = session.client("lambda").get_function_configuration(FunctionName=LAUNCHER_FUNCTION)["Environment"]["Variables"]
    pool = env["USER_POOL_ID"]
    idp = session.client("cognito-idp")
    clients = [c["ClientId"] for c in idp.list_user_pool_clients(UserPoolId=pool, MaxResults=20)["UserPoolClients"]]
    return {"usage_table": env["USAGE_TABLE"], "flags_table": env["FLAGS_TABLE"], "entitlements_table": env["ENTITLEMENTS_TABLE"], "safety_table": env["SAFETY_TABLE"],
            "plans_param": env["PLANS_CONFIG_PARAM"], "customer_pool_id": pool, "client_ids": clients}


def bundle(out_dir: Optional[str] = None) -> str:
    """The code folder: the two handlers, the shared `common` package, and the model client. Rebuilt from scratch every time, so it always matches the working tree."""
    out = out_dir or os.path.join(HERE, "build", "vidup")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(os.path.join(HERE, "lambdas", "common"), os.path.join(out, "common"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for src, dst in FILES:
        target = os.path.join(out, dst)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(HERE, src), target)
    with open(os.path.join(out, "engine", "__init__.py"), "w") as f:
        f.write('"""The model client of the engine (llm.py), bundled for the video-upload functions."""\n')
    return out


class VideoUploadStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, stage: str, main: Dict[str, Any], web_origins: List[str], is_prod: bool = False, plan_model_id: str = "", review_model_id: str = "",
                 analyse_concurrency: int = 5, bundle_dir: Optional[str] = None, **kw: Any) -> None:
        super().__init__(scope, cid, description=f"VideoMK video upload ({stage}): private bucket, API, analysis worker. Owns no customer account data.", **kw)
        missing = [k for k in MAIN_KEYS if not main.get(k)]
        if missing:
            raise ValueError(f"video upload needs these names of the main stack: {', '.join(missing)}")
        layer_dir = os.path.join(HERE, "layers", "vidup_deps")
        if not os.path.isdir(os.path.join(layer_dir, "python")) and not os.environ.get("CDK_SKIP_LAYER_CHECK"):
            raise ValueError("Video upload layer not built. Run `backend/layers/build_layer.sh vidup_deps` first (or set CDK_SKIP_LAYER_CHECK=1 for a synth-only check).")
        arn = lambda service, rest: f"arn:aws:{service}:{self.region}:{self.account}:{rest}"   # noqa: E731
        usage_arn, flags_arn, ent_arn, safety_arn = (arn("dynamodb", "table/" + main[k]) for k in ("usage_table", "flags_table", "entitlements_table", "safety_table"))

        bucket = s3.Bucket(
            self, "Clips", bucket_name=bucket_name(stage, self.account), block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY, auto_delete_objects=not is_prod,
            lifecycle_rules=[s3.LifecycleRule(id="abort-partial-uploads", abort_incomplete_multipart_upload_after=Duration.days(1)),
                             s3.LifecycleRule(id="originals-never-stay", prefix="in/", expiration=Duration.days(ORIGINAL_DAYS)),     # a safety net: the worker deletes the original at once
                             s3.LifecycleRule(id="unused-clips-expire", prefix="clips/", expiration=Duration.days(KEPT_DAYS))],
            cors=[s3.CorsRule(allowed_methods=[s3.HttpMethods.POST], allowed_origins=web_origins, allowed_headers=["*"], max_age=3600),       # the browser's presigned POST
                  s3.CorsRule(allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD], allowed_origins=web_origins, allowed_headers=["*"], max_age=3600)],   # the poster link
        )

        layer = _lambda.LayerVersion(self, "VidupDepsLayer", code=_lambda.Code.from_asset(layer_dir), compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
                                     compatible_architectures=[_lambda.Architecture.X86_64], description="Video upload: Pillow and a static ffmpeg")
        code = _lambda.Code.from_asset(bundle(bundle_dir))
        env = {"USAGE_TABLE": main["usage_table"], "FLAGS_TABLE": main["flags_table"], "ENTITLEMENTS_TABLE": main["entitlements_table"], "SAFETY_TABLE": main["safety_table"],
               "PLANS_ENABLED": "1", "PLANS_CONFIG_PARAM": main["plans_param"], "VIDUP_BUCKET": bucket.bucket_name, "OPENAI_SSM_PARAM": OPENAI_SSM_PARAM,
               "ALLOW_UNLIMITED_ACCOUNTS": "0" if is_prod else "1", **({"PLAN_MODEL_ID": plan_model_id} if plan_model_id else {}),
               **({"REVIEW_MODEL_ID": review_model_id} if review_model_id else {})}
        name = f"videomk-{stage}-vidup"
        self.analyse_fn = _lambda.Function(
            self, "AnalyseFn", function_name=f"{name}-analyse", runtime=_lambda.Runtime.PYTHON_3_12, architecture=_lambda.Architecture.X86_64, handler="vidup_analyse.handler", code=code,
            layers=[layer], memory_size=2048, ephemeral_storage_size=__import__("aws_cdk").Size.mebibytes(1024), timeout=Duration.seconds(120), environment=env, reserved_concurrent_executions=analyse_concurrency,
            retry_attempts=0, log_group=logs.LogGroup(self, "AnalyseLogs", log_group_name=f"/aws/lambda/{name}-analyse", retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.DESTROY),
            description="Video upload: checks one clip once (safety, transcript, description) and keeps one normalised copy (docs/VIDEO_UPLOAD_2026-11-28.md)")
        self.api_fn = _lambda.Function(
            self, "ApiFn", function_name=f"{name}-api", runtime=_lambda.Runtime.PYTHON_3_12, architecture=_lambda.Architecture.X86_64, handler="vidup_api.handler", code=code, layers=[layer],
            memory_size=512, timeout=Duration.seconds(15), environment={**env, "ANALYSE_FUNCTION": self.analyse_fn.function_name},
            log_group=logs.LogGroup(self, "ApiLogs", log_group_name=f"/aws/lambda/{name}-api", retention=logs.RetentionDays.ONE_MONTH, removal_policy=RemovalPolicy.DESTROY),
            description="Video upload API: slot, analyse, status, delete")

        # ---- least privilege (tests/test_video_upload_cdk.py reads this from the synthesized template)
        mine = ["vidrec:*", "vidup:*", "vidhash:*", "vidbad"]
        for fn in (self.api_fn, self.analyse_fn):
            fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[bucket.arn_for_objects("in/*"), bucket.arn_for_objects("clips/*")]))
            fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query"], resources=[usage_arn],
                                                      conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": mine}}))
            fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[flags_arn], conditions={"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["ops:switches"]}}))   # the kill switch
        self.api_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[flags_arn]))   # the account's own flags row (entitlements -> wallet.is_unlimited reads it by user id; read only, like every runtime function)
        self.api_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[ent_arn]))
        self.api_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:Query", "dynamodb:GetItem"], resources=[safety_arn]))   # is the account paused or on hold?
        self.api_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[arn("ssm", "parameter" + main["plans_param"])]))
        self.api_fn.add_to_role_policy(iam.PolicyStatement(actions=["lambda:InvokeFunction"], resources=[self.analyse_fn.function_arn]))
        self.analyse_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:PutItem", "dynamodb:Query"], resources=[safety_arn]))   # a real policy verdict is a recorded stop
        self.analyse_fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:::foundation-model/*", arn("bedrock", "inference-profile/*")]))
        self.analyse_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[arn("ssm", "parameter" + OPENAI_SSM_PARAM)]))   # the transcription and moderation provider's key

        # ---- the API: every route behind the customer pool's token, checked by API Gateway before any of our code runs
        jwt = authorizers.HttpJwtAuthorizer("CustomerToken", f"https://cognito-idp.{self.region}.amazonaws.com/{main['customer_pool_id']}", jwt_audience=list(main["client_ids"]),
                                            identity_source=["$request.header.Authorization"])
        api = apigw2.HttpApi(self, "Api", api_name=name, default_authorizer=jwt, create_default_stage=True,
                             cors_preflight=apigw2.CorsPreflightOptions(allow_origins=web_origins, allow_methods=[apigw2.CorsHttpMethod.GET, apigw2.CorsHttpMethod.POST, apigw2.CorsHttpMethod.DELETE, apigw2.CorsHttpMethod.OPTIONS],
                                                                        allow_headers=["Content-Type", "Authorization", "X-Locale", "X-Timezone"], max_age=Duration.hours(1)))
        integ = integrations.HttpLambdaIntegration("Api", self.api_fn)
        base = "/users/{user_id}/video-uploads"
        for path, methods in ((base, [apigw2.HttpMethod.GET, apigw2.HttpMethod.POST]), (base + "/{clip_id}", [apigw2.HttpMethod.GET, apigw2.HttpMethod.DELETE]), (base + "/{clip_id}/analyse", [apigw2.HttpMethod.POST])):
            api.add_routes(path=path, methods=methods, integration=integ)
        api.default_stage.node.default_child.default_route_settings = apigw2.CfnStage.RouteSettingsProperty(throttling_burst_limit=20, throttling_rate_limit=10)

        cw.Alarm(self, "AnalyseErrorsAlarm", metric=self.analyse_fn.metric_errors(period=Duration.hours(1)), threshold=3, evaluation_periods=1,
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description="Video upload analysis failed to run 3 or more times in an hour (a refused clip is not an error). No action attached.")
        CfnOutput(self, "VidupApiUrl", value=api.api_endpoint)
        CfnOutput(self, "VidupBucket", value=bucket.bucket_name)
        CfnOutput(self, "VidupAnalyseFunction", value=self.analyse_fn.function_name)
