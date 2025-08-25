from aws_cdk import (
    Duration,
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_iam as iam,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as targets,
)
from constructs import Construct
import os
import json

class BackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================
        # DynamoDB: Videos table (import existing)
        # ============================
        # NOTE: The table 'Videos' already exists. Leaving the original creation code here commented.
        # videos_table = dynamodb.Table(
        #     self,
        #     "VideosTable",
        #     table_name="Videos",
        #     partition_key=dynamodb.Attribute(
        #         name="video_id",
        #         type=dynamodb.AttributeType.STRING,
        #     ),
        #     billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        #     removal_policy=RemovalPolicy.RETAIN,
        # )
        # videos_table.add_global_secondary_index(
        #     index_name="GSI_UserVideos",
        #     partition_key=dynamodb.Attribute(
        #         name="user_id",
        #         type=dynamodb.AttributeType.STRING,
        #     ),
        #     sort_key=dynamodb.Attribute(
        #         name="created_at",
        #         type=dynamodb.AttributeType.STRING,
        #     ),
        #     projection_type=dynamodb.ProjectionType.INCLUDE,
        #     non_key_attributes=[
        #         "title",
        #         "status",
        #         "thumbnail_url",
        #         "duration_s",
        #     ],
        # )
        videos_table = dynamodb.Table.from_table_name(self, "VideosTable", "Videos")

        # ============================
        # Lambda functions
        # ============================
        # Lambda Layer for video rendering dependencies
        video_layer = _lambda.LayerVersion(
            self,
            "VideoDepsLayer",
            code=_lambda.Code.from_asset("layers/video_deps"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Video rendering Python dependencies (moviepy, pillow, numpy, etc)",
        )

        generate_video_fn = _lambda.Function(
            self,
            "GenerateVideoFunction",
            function_name="generate_video",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.index.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.minutes(15),
            memory_size=2048,
            environment={
                "VIDEOS_TABLE": videos_table.table_name,
                "GSI_USER_VIDEOS": "GSI_UserVideos",
                "ASSETS_BUCKET": "videomk.com",
                "OPENAI_API_SECRET_NAME": "OPENAI_API_KEY",
                "OPENAI_MODEL": "gpt-5",
            },
            layers=[video_layer],
        )

        list_videos_fn = _lambda.Function(
            self,
            "ListVideosFunction",
            function_name="list_videos",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="list_videos.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(30),
            environment={
                "VIDEOS_TABLE": videos_table.table_name,
                "GSI_USER_VIDEOS": "GSI_UserVideos",
            },
        )

        get_video_fn = _lambda.Function(
            self,
            "GetVideoFunction",
            function_name="get_video",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="get_video.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(30),
            environment={
                "VIDEOS_TABLE": videos_table.table_name,
            },
        )

        # Full read/write access as requested
        videos_table.grant_read_write_data(generate_video_fn)
        videos_table.grant_read_write_data(list_videos_fn)
        videos_table.grant_read_data(get_video_fn)

        # Ensure list_videos can Query GSIs explicitly (some imports may miss index ARNs)
        list_videos_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:DescribeTable"],
                resources=[
                    videos_table.table_arn,
                    f"{videos_table.table_arn}/index/*",
                ],
            )
        )

        # Allow Bedrock model invocation (all models in us-west-2 and us-east-1)
        generate_video_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-west-2::foundation-model/*",
                    "arn:aws:bedrock:us-east-1::foundation-model/*",
                ],
            )
        )

        # Allow put/get to the assets bucket path
        generate_video_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:AbortMultipartUpload",
                ],
                resources=[
                    "arn:aws:s3:::videomk.com/generation/assets/*",
                    "arn:aws:s3:::videomk.com/videos/*",
                ],
            )
        )

        # Allow get to the video objects for presigning via get_video
        get_video_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    "arn:aws:s3:::videomk.com",
                    "arn:aws:s3:::videomk.com/videos/*",
                ],
            )
        )

        # Allow Secrets Manager get for OpenAI key
        generate_video_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["arn:aws:secretsmanager:us-west-2:*:secret:OPENAI_API_KEY*"]
            )
        )

        # ----------------------------
        # New multi-step workflow Lambdas
        # ----------------------------
        intent_plot_fn = _lambda.Function(
            self,
            "IntentPlotFunction",
            function_name="intent_plot_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.intent_plot_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(60),
            memory_size=512,
        )

        assets_plan_fn = _lambda.Function(
            self,
            "AssetsPlanFunction",
            function_name="assets_plan_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.assets_plan_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(30),
            memory_size=512,
        )

        asset_scene_fn = _lambda.Function(
            self,
            "AssetSceneFunction",
            function_name="asset_scene_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.asset_scene_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(120),
            memory_size=1024,
        )

        assets_collect_fn = _lambda.Function(
            self,
            "AssetsCollectFunction",
            function_name="assets_collect_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.assets_collect_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(60),
            memory_size=512,
        )

        storyboard_render_fn = _lambda.Function(
            self,
            "StoryboardRenderFunction",
            function_name="storyboard_render_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.storyboard_render_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.minutes(15),
            memory_size=4096,
            layers=[video_layer],
        )

        mark_failed_fn = _lambda.Function(
            self,
            "MarkFailedFunction",
            function_name="mark_failed_handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.handlers.mark_failed_handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
            memory_size=256,
        )

        # Grants for new lambdas
        videos_table.grant_read_write_data(intent_plot_fn)
        videos_table.grant_read_write_data(assets_collect_fn)
        videos_table.grant_read_write_data(storyboard_render_fn)
        videos_table.grant_read_write_data(mark_failed_fn)

        # Bedrock permissions for intent/plot generation
        intent_plot_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-west-2::foundation-model/*",
                    "arn:aws:bedrock:us-east-1::foundation-model/*",
                ],
            )
        )

        # Bedrock permissions only for per-scene asset generation
        asset_scene_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-west-2::foundation-model/*",
                    "arn:aws:bedrock:us-east-1::foundation-model/*",
                ],
            )
        )

        # S3 permissions: scene generation (put assets), renderer (get assets, put videos)
        asset_scene_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:AbortMultipartUpload"],
                resources=["arn:aws:s3:::videomk.com/generation/assets/*"],
            )
        )
        storyboard_render_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:GetBucketLocation",
                    "s3:PutObject",
                    "s3:AbortMultipartUpload",
                ],
                resources=[
                    "arn:aws:s3:::videomk.com",
                    "arn:aws:s3:::videomk.com/generation/assets/*",
                    "arn:aws:s3:::videomk.com/videos/*",
                ],
            )
        )

        # Secrets Manager for storyboard (OpenAI)
        storyboard_render_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["arn:aws:secretsmanager:us-west-2:*:secret:OPENAI_API_KEY*"],
            )
        )

        # ----------------------------
        # Step Functions workflow definition
        # ----------------------------
        intent_plot_task = tasks.LambdaInvoke(
            self,
            "IntentAndPlot",
            lambda_function=intent_plot_fn,
            payload_response_only=True,
            result_path="$",
        )

        assets_plan_task = tasks.LambdaInvoke(
            self,
            "PlanAssets",
            lambda_function=assets_plan_fn,
            payload_response_only=True,
            result_path="$",
        )

        scene_task = tasks.LambdaInvoke(
            self,
            "GenerateSceneAsset",
            lambda_function=asset_scene_fn,
            payload_response_only=True,
            result_path="$",
        )

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
        assets_map.item_processor(scene_task)

        assets_collect_task = tasks.LambdaInvoke(
            self,
            "CollectAssets",
            lambda_function=assets_collect_fn,
            payload_response_only=True,
            result_path="$",
        )

        storyboard_render_task = tasks.LambdaInvoke(
            self,
            "StoryboardAndRender",
            lambda_function=storyboard_render_fn,
            payload_response_only=True,
            result_path="$",
        )

        # Choice to skip map when there are no scenes
        has_scenes = sfn.Choice(self, "HasScenes?")
        has_scenes.when(
            sfn.Condition.is_present("$.scenes[0]"),
            assets_map,
        ).otherwise(sfn.Pass(self, "NoScenes"))

        # Failure handling: mark FAILED then end with Fail state
        mark_failed_task = tasks.LambdaInvoke(
            self,
            "MarkFailed",
            lambda_function=mark_failed_fn,
            payload_response_only=True,
            result_path="$.error",
        )
        fail_state = sfn.Fail(self, "WorkflowFailed")
        failure_chain = sfn.Chain.start(mark_failed_task).next(fail_state)

        for t in [intent_plot_task, assets_plan_task, assets_map, assets_collect_task, storyboard_render_task]:
            t.add_catch(failure_chain, result_path="$.error")

        definition = (
            sfn.Chain.start(intent_plot_task)
            .next(assets_plan_task)
            .next(has_scenes.afterwards())
            .next(assets_collect_task)
            .next(storyboard_render_task)
        )

        state_machine = sfn.StateMachine(
            self,
            "GenerateVideoWorkflow",
            state_machine_name="generate_video_workflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
        )

        # ============================
        # API Gateway + Custom Domain
        # ============================
        hosted_zone = route53.HostedZone.from_lookup(
            self, "HostedZone", domain_name="videomk.com"
        )

        certificate = acm.Certificate(
            self,
            "ApiCertificate",
            domain_name="api.videomk.com",
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        api = apigw.RestApi(
            self,
            "VideoMkApi",
            rest_api_name="videomk-api",
            deploy_options=apigw.StageOptions(stage_name="prod"),
        )

        # Ensure CORS headers are returned even on 4XX/5XX (e.g., authorizer failures)
        api.add_gateway_response(
            "Default4xxGatewayResponse",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'*'",
                "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )
        api.add_gateway_response(
            "Default5xxGatewayResponse",
            type=apigw.ResponseType.DEFAULT_5_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'*'",
                "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )

        # Explicit API custom domain and base path mapping
        api_domain = apigw.DomainName(
            self,
            "ApiDomain",
            domain_name="api.videomk.com",
            certificate=certificate,
            endpoint_type=apigw.EndpointType.REGIONAL,
            security_policy=apigw.SecurityPolicy.TLS_1_2,
        )

        apigw.BasePathMapping(
            self,
            "ApiBasePathMapping",
            domain_name=api_domain,
            rest_api=api,
            stage=api.deployment_stage,
        )

        # Route53 alias record for the custom domain
        route53.ARecord(
            self,
            "ApiAliasRecord",
            zone=hosted_zone,
            record_name="api",
            target=route53.RecordTarget.from_alias(targets.ApiGatewayDomain(api_domain)),
        )

        # Resources: /users/{user_id}/videos and subresource /generate
        users = api.root.add_resource("users")
        user_id = users.add_resource("{user_id}")
        videos = user_id.add_resource("videos")
        generate = videos.add_resource("generate")
        video_item = videos.add_resource("{video_id}")

        # Cognito Authorizer (required for all methods)
        # Load from config.json first, then fall back to env/context. Accept ARN or ID.
        config_user_pool_id = None
        config_user_pool_arn = None
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as config_file:
                    cfg = json.load(config_file)
                    config_user_pool_id = cfg.get("cognitoUserPoolId")
                    config_user_pool_arn = cfg.get("cognitoUserPoolArn")
        except Exception:
            # Ignore config read errors and fall back to env/context
            pass

        user_pool_ref = (
            config_user_pool_arn
            or os.environ.get("COGNITO_USER_POOL_ARN")
            or self.node.try_get_context("cognitoUserPoolArn")
            or config_user_pool_id
            or os.environ.get("COGNITO_USER_POOL_ID")
            or self.node.try_get_context("cognitoUserPoolId")
        )
        if not user_pool_ref:
            raise ValueError(
                "Provide Cognito pool via COGNITO_USER_POOL_ARN (or context cognitoUserPoolArn) or ID (COGNITO_USER_POOL_ID)."
            )
        if isinstance(user_pool_ref, str) and user_pool_ref.startswith("arn:") and ":userpool/" in user_pool_ref:
            user_pool = cognito.UserPool.from_user_pool_arn(self, "ImportedUserPool", user_pool_ref)
        else:
            user_pool = cognito.UserPool.from_user_pool_id(self, "ImportedUserPool", str(user_pool_ref))
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "ApiAuthorizer",
            cognito_user_pools=[user_pool],
        )

        # CORS preflight on resources (adds OPTIONS)
        users.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )
        user_id.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )
        videos.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )
        generate.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )
        video_item.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )

        # GET /users/{user_id}/videos -> list_videos Lambda (proxy integration)
        list_integration = apigw.LambdaIntegration(list_videos_fn, proxy=True)
        videos.add_method(
            "GET",
            list_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )

        # GET /users/{user_id}/videos/{video_id} -> get_video Lambda (proxy integration)
        get_video_integration = apigw.LambdaIntegration(get_video_fn, proxy=True)
        video_item.add_method(
            "GET",
            get_video_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )

        # Launcher Lambda to start Step Functions execution
        launcher_fn = _lambda.Function(
            self,
            "VideoGenerationSFLauncher",
            function_name="VideoGenerationSFLauncher",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="sf_launcher.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
        )

        # Allow the launcher to start executions and list state machines
        launcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution", "states:ListStateMachines"],
                resources=["*"],
            )
        )

        # Allow the launcher to write to the Videos table
        videos_table.grant_read_write_data(launcher_fn)

        # POST /users/{user_id}/videos/generate -> launcher Lambda (proxy integration)
        generate_integration = apigw.LambdaIntegration(launcher_fn, proxy=True)
        generate.add_method(
            "POST",
            generate_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
        )

