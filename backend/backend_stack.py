import json
import os
from typing import Any, Dict, List, Optional

from aws_cdk import (
    Duration,
    Size,
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_s3 as s3,
    CfnOutput,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_iam as iam,
    aws_logs as logs,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as targets,
)
from constructs import Construct

from engine_v2 import EngineV2

OPENAI_SSM_PARAM = "/videomk/openai_api_key"  # standard SSM parameter: free (Secrets Manager costs ~$0.40/mo idle)
TRANSIENT_LAMBDA_ERRORS = [
    "Lambda.ServiceException",
    "Lambda.AWSLambdaException",
    "Lambda.SdkClientException",
    "Lambda.TooManyRequestsException",
]


class BackendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, stage: str, stage_cfg: Dict[str, Any], **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_prod = stage == "prod"
        keep = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        domain = stage_cfg.get("domain")  # e.g. "videomk.com": enables api.<domain>; None => default execute-api URL
        ASSETS_BUCKET = f"videomk-{stage}-{self.account}"

        # ============================
        # Data
        # ============================
        # Everything is created per stage and account: no resource is shared with, or imported from, any other account.
        videos_table = dynamodb.Table(
            self, "VideosTable",
            partition_key=dynamodb.Attribute(name="video_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=is_prod),
            removal_policy=keep,
        )
        videos_table.add_global_secondary_index(
            index_name="GSI_UserVideos",
            partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        assets_bucket = s3.Bucket(
            self, "AssetsBucket",
            bucket_name=ASSETS_BUCKET,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=keep,
            auto_delete_objects=not is_prod,
            lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(2))],
            cors=[s3.CorsRule(allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD], allowed_origins=["*"], allowed_headers=["*"], max_age=3600)],
        )

        # Per-user daily quota counters. On-demand + TTL => zero idle cost.
        usage_table = dynamodb.Table(
            self,
            "UsageTable",
            partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="day", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        common_env = {
            "VIDEOS_TABLE": videos_table.table_name,
            "USAGE_TABLE": usage_table.table_name,
            "ASSETS_BUCKET": ASSETS_BUCKET,
            "OPENAI_SSM_PARAM": OPENAI_SSM_PARAM,
        }

        # ============================
        # Lambda layer (built by layers/build_layer.sh for linux/x86_64)
        # ============================
        layer_dir = os.path.join(os.path.dirname(__file__), "layers", "video_deps")
        if not os.path.isdir(os.path.join(layer_dir, "python")) and not os.environ.get("CDK_SKIP_LAYER_CHECK"):
            raise ValueError(
                "Lambda layer not built. Run `backend/layers/build_layer.sh` first "
                "(or set CDK_SKIP_LAYER_CHECK=1 for a synth-only check)."
            )
        video_layer = _lambda.LayerVersion(
            self,
            "VideoDepsLayer",
            code=_lambda.Code.from_asset("layers/video_deps"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            compatible_architectures=[_lambda.Architecture.X86_64],
            description="Video rendering Python dependencies (moviepy, pillow, numpy, etc)",
        )

        def make_fn(
            construct_id: str,
            name: str,
            handler: str,
            *,
            timeout: Duration,
            memory: int = 256,
            env: Optional[Dict[str, str]] = None,
            layers: Optional[List[_lambda.ILayerVersion]] = None,
            ephemeral_mb: Optional[int] = None,
        ) -> _lambda.Function:
            return _lambda.Function(
                self,
                construct_id,
                function_name=name,
                runtime=_lambda.Runtime.PYTHON_3_12,
                architecture=_lambda.Architecture.X86_64,
                handler=handler,
                code=_lambda.Code.from_asset("lambdas"),
                timeout=timeout,
                memory_size=memory,
                environment={**common_env, **(env or {})},
                layers=layers or [],
                **({"ephemeral_storage_size": Size.mebibytes(ephemeral_mb)} if ephemeral_mb else {}),
                log_retention=logs.RetentionDays.TWO_WEEKS,  # no unbounded log storage
            )

        # ----------------------------
        # API-facing Lambdas
        # ----------------------------
        list_videos_fn = make_fn("ListVideosFunction", "list_videos", "list_videos.handler", timeout=Duration.seconds(30), env={"GSI_USER_VIDEOS": "GSI_UserVideos"})
        get_video_fn = make_fn("GetVideoFunction", "get_video", "get_video.handler", timeout=Duration.seconds(30))
        launcher_fn = make_fn(
            "VideoGenerationSFLauncher", "VideoGenerationSFLauncher", "sf_launcher.handler", timeout=Duration.seconds(10),
            env={"DAILY_VIDEO_LIMIT": str(self.node.try_get_context("dailyVideoLimit") or 5)},
        )

        videos_table.grant_read_write_data(list_videos_fn)
        videos_table.grant_read_data(get_video_fn)
        videos_table.grant_read_write_data(launcher_fn)
        usage_table.grant_read_write_data(launcher_fn)

        # Imported tables don't carry index ARNs: grant them explicitly for the GSI query.
        list_videos_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:DescribeTable", "dynamodb:BatchGetItem"],
                resources=[videos_table.table_arn, f"{videos_table.table_arn}/index/*"],
            )
        )
        for fn in (list_videos_fn, get_video_fn):
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:GetBucketLocation"],
                    resources=[f"arn:aws:s3:::{ASSETS_BUCKET}", f"arn:aws:s3:::{ASSETS_BUCKET}/videos/*"],
                )
            )

        # ----------------------------
        # Workflow Lambdas
        # ----------------------------
        bedrock_policy = iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:us-west-2::foundation-model/*",
                "arn:aws:bedrock:us-east-1::foundation-model/*",
                f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
            ],
        )
        openai_key_policy = iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{OPENAI_SSM_PARAM}"],
        )
        # Legacy fallback until the key is migrated to SSM; remove after `aws secretsmanager delete-secret`.
        legacy_secret_policy = iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[f"arn:aws:secretsmanager:us-west-2:{self.account}:secret:OPENAI_API_KEY*"],
        )

        intent_plot_fn = make_fn("IntentPlotFunction", "intent_plot_handler", "generate_video.handlers.intent_plot_handler.handler", timeout=Duration.seconds(60), memory=512)
        assets_plan_fn = make_fn("AssetsPlanFunction", "assets_plan_handler", "generate_video.handlers.assets_plan_handler.handler", timeout=Duration.seconds(30), memory=512)
        asset_scene_fn = make_fn("AssetSceneFunction", "asset_scene_handler", "generate_video.handlers.asset_scene_handler.handler", timeout=Duration.seconds(120), memory=1024)
        assets_collect_fn = make_fn("AssetsCollectFunction", "assets_collect_handler", "generate_video.handlers.assets_collect_handler.handler", timeout=Duration.seconds(60), memory=512)
        storyboard_render_fn = make_fn(
            "StoryboardRenderFunction",
            "storyboard_render_handler",
            "generate_video.handlers.storyboard_render_handler.handler",
            timeout=Duration.minutes(15),
            memory=4096,
            env={"OPENAI_MODEL": "gpt-5"},
            layers=[video_layer],
        )
        mark_failed_fn = make_fn("MarkFailedFunction", "mark_failed_handler", "generate_video.handlers.mark_failed_handler.handler", timeout=Duration.seconds(10))
        mark_rejected_fn = make_fn("MarkRejectedFunction", "mark_rejected_handler", "generate_video.handlers.mark_rejected_handler.handler", timeout=Duration.seconds(10))

        for fn in (intent_plot_fn, assets_collect_fn, storyboard_render_fn, mark_failed_fn, mark_rejected_fn):
            videos_table.grant_read_write_data(fn)
        for fn in (mark_failed_fn, mark_rejected_fn):
            usage_table.grant_read_write_data(fn)

        intent_plot_fn.add_to_role_policy(bedrock_policy)
        for fn in (asset_scene_fn, storyboard_render_fn):
            fn.add_to_role_policy(openai_key_policy)
            fn.add_to_role_policy(legacy_secret_policy)
        asset_scene_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:AbortMultipartUpload"],
                resources=[f"arn:aws:s3:::{ASSETS_BUCKET}/generation/assets/*"],
            )
        )
        storyboard_render_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload", "s3:GetBucketLocation"],
                resources=[
                    f"arn:aws:s3:::{ASSETS_BUCKET}",
                    f"arn:aws:s3:::{ASSETS_BUCKET}/generation/assets/*",
                    f"arn:aws:s3:::{ASSETS_BUCKET}/videos/*",
                ],
            )
        )

        # ----------------------------
        # Step Functions (legacy v1 pipeline, hardened)
        # ----------------------------
        def invoke(construct_id: str, fn: _lambda.IFunction) -> tasks.LambdaInvoke:
            task = tasks.LambdaInvoke(self, construct_id, lambda_function=fn, payload_response_only=True, result_path="$")
            task.add_retry(errors=TRANSIENT_LAMBDA_ERRORS, interval=Duration.seconds(2), max_attempts=3, backoff_rate=2.0)
            return task

        intent_plot_task = invoke("IntentAndPlot", intent_plot_fn)
        assets_plan_task = invoke("PlanAssets", assets_plan_fn)
        assets_collect_task = invoke("CollectAssets", assets_collect_fn)
        storyboard_render_task = invoke("StoryboardAndRender", storyboard_render_fn)

        scene_task = invoke("GenerateSceneAsset", asset_scene_fn)
        # Image providers rate-limit/flake: retry any task failure twice, then degrade to a plain-colour scene.
        scene_task.add_retry(errors=["States.TaskFailed"], interval=Duration.seconds(5), max_attempts=2, backoff_rate=2.0)
        scene_degraded = sfn.Pass(
            self,
            "SceneAssetDegraded",
            parameters={
                "video_id.$": "$.video_id",
                "scene_id.$": "$.scene.id",
                "image": None,
                "text": {"scene_id.$": "$.scene.id", "type": "text", "content.$": "$.scene.description"},
            },
        )
        scene_task.add_catch(scene_degraded, errors=["States.ALL"], result_path="$.error")
        scene_chain = sfn.Chain.start(scene_task)

        assets_map = sfn.Map(
            self,
            "GenerateAssetsMap",
            items_path=sfn.JsonPath.string_at("$.scenes"),
            max_concurrency=3,
            item_selector={
                "video_id.$": "$.video_id",
                "plot.$": "$.plot",
                "scene.$": "$$.Map.Item.Value",
            },
            result_path="$.assetResults",
        )
        assets_map.item_processor(scene_chain)

        has_scenes = sfn.Choice(self, "HasScenes?")
        has_scenes.when(sfn.Condition.is_present("$.scenes[0]"), assets_map).otherwise(sfn.Pass(self, "NoScenes"))

        mark_failed_task = tasks.LambdaInvoke(self, "MarkFailed", lambda_function=mark_failed_fn, payload_response_only=True, result_path="$.error_result")
        failure_chain = sfn.Chain.start(mark_failed_task).next(sfn.Fail(self, "WorkflowFailed"))
        for t in (intent_plot_task, assets_plan_task, assets_map, assets_collect_task, storyboard_render_task):
            t.add_catch(failure_chain, errors=["States.ALL"], result_path="$.error")

        # Prompt judged not legitimate: stop here (no images, no render, no cost), mark REJECTED, refund.
        mark_rejected_task = tasks.LambdaInvoke(self, "MarkRejected", lambda_function=mark_rejected_fn, payload_response_only=True, result_path="$.rejected")
        rejected_chain = sfn.Chain.start(mark_rejected_task).next(sfn.Succeed(self, "Rejected"))
        mark_rejected_task.add_catch(failure_chain, errors=["States.ALL"], result_path="$.error")

        legit_choice = sfn.Choice(self, "PromptLegit?")
        legit_choice.when(sfn.Condition.boolean_equals("$.plot.legit", True), assets_plan_task).otherwise(rejected_chain)
        assets_plan_task.next(has_scenes.afterwards()).next(assets_collect_task).next(storyboard_render_task)

        definition = sfn.Chain.start(intent_plot_task).next(legit_choice)
        state_machine = sfn.StateMachine(
            self,
            "GenerateVideoWorkflow",
            state_machine_name="generate_video_workflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
        )

        # ----------------------------
        # Engine v2 (opt-in: `cdk deploy -c engine=v2`). v1 stays the default until v2 is proven on real Lambda.
        # ----------------------------
        engine = str(self.node.try_get_context("engine") or "v1")
        active_machine = state_machine
        v2 = None
        if engine == "v2":
            engine_dir = os.path.join(os.path.dirname(__file__), "layers", "engine_deps")
            if not os.path.isdir(os.path.join(engine_dir, "python")) and not os.environ.get("CDK_SKIP_LAYER_CHECK"):
                raise ValueError("Engine layer not built. Run `backend/layers/build_layer.sh engine_deps` first.")
            engine_layer = _lambda.LayerVersion(
                self, "EngineDepsLayer",
                code=_lambda.Code.from_asset("layers/engine_deps"),
                compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
                compatible_architectures=[_lambda.Architecture.X86_64],
                description="Engine v2: numpy, Pillow, static ffmpeg (all manylinux wheels)",
            )
            engine_env = {
                "TTS_PROVIDER": str(self.node.try_get_context("ttsProvider") or "polly"),
                "MAX_VIDEO_COST_USD": str(self.node.try_get_context("maxVideoCostUsd") or "1.50"),
                "DEFAULT_TARGET_MINUTES": str(self.node.try_get_context("defaultMinutes") or "3"),
                "CHUNK_SECONDS": "30",
            }
            for ctx_key, env_key in (("editDailyLimit", "EDIT_DAILY_LIMIT"), ("planModelId", "PLAN_MODEL_ID"), ("reviewModelId", "REVIEW_MODEL_ID"), ("unsplashAppName", "UNSPLASH_APP_NAME"), ("httpUserAgent", "HTTP_USER_AGENT"), ("ttsVoice", "TTS_VOICE"), ("pollyEngine", "POLLY_ENGINE"), ("pollyRegion", "POLLY_REGION")):
                if self.node.try_get_context(ctx_key):
                    engine_env[env_key] = str(self.node.try_get_context(ctx_key))
            v2 = EngineV2(
                self, "EngineV2",
                make_fn=make_fn, engine_layer=engine_layer, videos_table=videos_table, assets_bucket=ASSETS_BUCKET,
                mark_failed_fn=mark_failed_fn, mark_rejected_fn=mark_rejected_fn, usage_table=usage_table, env=engine_env,
                account=self.account, region=self.region,
                render_concurrency=int(self.node.try_get_context("renderConcurrency") or 8),
            )
            active_machine = v2.state_machine

        active_machine.grant_start_execution(launcher_fn)
        launcher_fn.add_environment("STATE_MACHINE_ARN", active_machine.state_machine_arn)

        # ============================
        # API Gateway + custom domain
        # ============================
        api = apigw.RestApi(
            self,
            "VideoMkApi",
            rest_api_name="videomk-api",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=20,   # req/s across the stage (per-user limits are the daily quota)
                throttling_burst_limit=40,
            ),
        )
        cors_headers = {
            "Access-Control-Allow-Origin": "'*'",
            "Access-Control-Allow-Headers": "'*'",
            "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
        }
        api.add_gateway_response("Default4xxGatewayResponse", type=apigw.ResponseType.DEFAULT_4_XX, response_headers=cors_headers)
        api.add_gateway_response("Default5xxGatewayResponse", type=apigw.ResponseType.DEFAULT_5_XX, response_headers=cors_headers)

        if domain:
            hosted_zone = route53.HostedZone.from_lookup(self, "HostedZone", domain_name=domain)
            certificate = acm.Certificate(
                self, "ApiCertificate", domain_name=f"api.{domain}", validation=acm.CertificateValidation.from_dns(hosted_zone)
            )
            api_domain = apigw.DomainName(
                self, "ApiDomain", domain_name=f"api.{domain}", certificate=certificate,
                endpoint_type=apigw.EndpointType.REGIONAL, security_policy=apigw.SecurityPolicy.TLS_1_2,
            )
            apigw.BasePathMapping(self, "ApiBasePathMapping", domain_name=api_domain, rest_api=api, stage=api.deployment_stage)
            route53.ARecord(
                self, "ApiAliasRecord", zone=hosted_zone, record_name="api",
                target=route53.RecordTarget.from_alias(targets.ApiGatewayDomain(api_domain)),
            )

        users = api.root.add_resource("users")
        user_id = users.add_resource("{user_id}")
        videos = user_id.add_resource("videos")
        generate = videos.add_resource("generate")
        video_item = videos.add_resource("{video_id}")

        user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name=f"videomk-{stage}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(min_length=10, require_digits=True, require_lowercase=True, require_uppercase=False, require_symbols=False),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=keep,
        )
        callback_urls = list(stage_cfg.get("callbackUrls") or ["http://localhost:4321/auth/callback"])
        logout_urls = list(stage_cfg.get("logoutUrls") or ["http://localhost:4321/"])
        user_pool_client = user_pool.add_client(
            "WebClient",
            generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=callback_urls, logout_urls=logout_urls,
            ),
            prevent_user_existence_errors=True,
        )
        # Native iOS/Android apps: public client, authorization code + PKCE through the hosted UI, custom-scheme redirect.
        mobile_client = user_pool.add_client(
            "MobileClient",
            generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                callback_urls=["com.videomk.app://auth/callback"], logout_urls=["com.videomk.app://auth/signout"],
            ),
            # Admin password auth needs IAM credentials, so it is not reachable by app users; QA scripts use it to get test tokens.
            auth_flows=cognito.AuthFlow(admin_user_password=(stage != "prod")),
            access_token_validity=Duration.hours(1), id_token_validity=Duration.hours(1), refresh_token_validity=Duration.days(60),
            prevent_user_existence_errors=True,
        )
        hosted_ui = user_pool.add_domain("HostedUi", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"videomk-{stage}-{self.account[-6:]}"))
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "MobileClientId", value=mobile_client.user_pool_client_id)
        CfnOutput(self, "AuthDomain", value=hosted_ui.base_url())
        CfnOutput(self, "AssetsBucketName", value=assets_bucket.bucket_name)
        authorizer = apigw.CognitoUserPoolsAuthorizer(self, "ApiAuthorizer", cognito_user_pools=[user_pool])

        for resource, methods in ((users, ["GET", "POST", "OPTIONS"]), (user_id, ["GET", "POST", "OPTIONS"]), (videos, ["GET", "POST", "OPTIONS"]), (generate, ["POST", "OPTIONS"]), (video_item, ["GET", "OPTIONS"])):
            resource.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=methods, allow_headers=["Content-Type", "Authorization", "X-Region"])

        cognito_auth = dict(authorization_type=apigw.AuthorizationType.COGNITO, authorizer=authorizer)
        videos.add_method("GET", apigw.LambdaIntegration(list_videos_fn, proxy=True), **cognito_auth)
        video_item.add_method("GET", apigw.LambdaIntegration(get_video_fn, proxy=True), **cognito_auth)

        # Reject malformed/oversized prompts at the edge, before any Lambda runs.
        generate_model = api.add_model(
            "GenerateRequestModel",
            content_type="application/json",
            model_name="GenerateRequest",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                type=apigw.JsonSchemaType.OBJECT,
                required=["prompt"],
                properties={
                    "prompt": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING, min_length=10, max_length=2000),
                    "client_request_id": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING, min_length=8, max_length=64),
                    "target_minutes": apigw.JsonSchema(type=apigw.JsonSchemaType.NUMBER, minimum=1, maximum=12),
                    "theme": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING, enum=["midnight", "paper", "sunrise"]),
                    "language": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING, enum=["en", "es"]),
                },
            ),
        )
        validator = api.add_request_validator("GenerateBodyValidator", validate_request_body=True, validate_request_parameters=False)
        generate.add_method(
            "POST",
            apigw.LambdaIntegration(launcher_fn, proxy=True),
            request_validator=validator,
            request_models={"application/json": generate_model},
            **cognito_auth,
        )

        # ----------------------------
        # Editor API (engine v2 only): read the plan, submit validated edits.
        # ----------------------------
        if v2 is not None:
            plan_res = video_item.add_resource("plan")
            edits_res = video_item.add_resource("edits")
            plan_res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["GET", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
            edits_res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
            plan_res.add_method("GET", apigw.LambdaIntegration(v2.editor_get_fn, proxy=True), **cognito_auth)
            edits_model = api.add_model(
                "EditRequestModel", content_type="application/json", model_name="EditRequest",
                schema=apigw.JsonSchema(
                    schema=apigw.JsonSchemaVersion.DRAFT4, type=apigw.JsonSchemaType.OBJECT, required=["base_rev"],
                    properties={
                        "base_rev": apigw.JsonSchema(type=apigw.JsonSchemaType.INTEGER, minimum=1),
                        "mode": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING, enum=["preview", "final"]),
                        "ops": apigw.JsonSchema(type=apigw.JsonSchemaType.ARRAY, max_items=40, items=apigw.JsonSchema(type=apigw.JsonSchemaType.OBJECT)),
                    },
                ),
            )
            edits_validator = api.add_request_validator("EditBodyValidator", validate_request_body=True, validate_request_parameters=False)
            edits_res.add_method(
                "POST", apigw.LambdaIntegration(v2.editor_apply_fn, proxy=True),
                request_validator=edits_validator, request_models={"application/json": edits_model}, **cognito_auth,
            )
