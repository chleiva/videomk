from aws_cdk import (
    Duration,
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_iam as iam,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as targets,
)
from constructs import Construct

class BackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================
        # DynamoDB: Videos table + GSI
        # ============================
        videos_table = dynamodb.Table(
            self,
            "VideosTable",
            table_name="Videos",
            partition_key=dynamodb.Attribute(
                name="video_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        videos_table.add_global_secondary_index(
            index_name="GSI_UserVideos",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=[
                "title",
                "status",
                "thumbnail_url",
                "duration_s",
            ],
        )

        # ============================
        # Lambda functions
        # ============================
        generate_video_fn = _lambda.Function(
            self,
            "GenerateVideoFunction",
            function_name="generate_video",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="generate_video.index.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.minutes(15),
            environment={
                "VIDEOS_TABLE": videos_table.table_name,
                "GSI_USER_VIDEOS": "GSI_UserVideos",
            },
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

        # Full read/write access as requested
        videos_table.grant_read_write_data(generate_video_fn)
        videos_table.grant_read_write_data(list_videos_fn)

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

        # Step Functions workflow: single task invoking generate_video
        generate_task = tasks.LambdaInvoke(
            self,
            "InvokeGenerateVideo",
            lambda_function=generate_video_fn,
            payload_response_only=True,
        )

        state_machine = sfn.StateMachine(
            self,
            "GenerateVideoWorkflow",
            state_machine_name="generate_video_workflow",
            definition_body=sfn.DefinitionBody.from_chainable(generate_task),
            timeout=Duration.minutes(15),
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

        # GET /users/{user_id}/videos -> list_videos Lambda (proxy integration)
        list_integration = apigw.LambdaIntegration(list_videos_fn, proxy=True)
        videos.add_method("GET", list_integration)

        # Launcher Lambda to start Step Functions execution
        launcher_fn = _lambda.Function(
            self,
            "VideoGenerationSFLauncher",
            function_name="VideoGenerationSFLauncher",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="sf_launcher.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
            environment={
                "STATE_MACHINE_ARN": state_machine.state_machine_arn,
            },
        )

        # Allow the launcher to start executions
        launcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[state_machine.state_machine_arn],
            )
        )

        # POST /users/{user_id}/videos/generate -> launcher Lambda (proxy integration)
        generate_integration = apigw.LambdaIntegration(launcher_fn, proxy=True)
        generate.add_method("POST", generate_integration)

