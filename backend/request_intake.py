"""The request check (intake) and the per-account record of safety stops (docs/INTAKE_AND_SAFETY.md).

One Lambda (`video_brief`), one table (SafetyTable: the stops, 90 days), one route (POST /users/{user_id}/videos/brief). Least privilege: the check function can read and
write only the stop table and the usage counters, read (never write) the admin-only account flags, and call only the small model. The video launcher gets the same
rights on the stop table so that `generate` runs the same check; it can never write the flags either.
"""
from typing import Callable, Dict

from aws_cdk import CfnOutput, Duration, RemovalPolicy, aws_apigateway as apigw, aws_dynamodb as dynamodb, aws_iam as iam, aws_lambda as _lambda
from constructs import Construct


class RequestIntake(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, account: str, is_prod: bool, make_fn: Callable[..., _lambda.Function], flags_table: dynamodb.ITable, usage_table: dynamodb.ITable,
        extra_env: Dict[str, str], videos_resource: apigw.IResource, cognito_auth: Dict, launcher_fn: _lambda.Function,
    ) -> None:
        super().__init__(scope, construct_id)
        table = dynamodb.Table(
            self, "SafetyTable", partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING), sort_key=dynamodb.Attribute(name="ts", type=dynamodb.AttributeType.NUMBER),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="ttl", point_in_time_recovery=is_prod, removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
        )
        env = {"SAFETY_TABLE": table.table_name, **extra_env}   # extra_env: the small-model id when the account cannot use the default (see docs/DEPLOY.md)
        brief_fn = make_fn("VideoBriefFn", "video_brief", "video_brief.handler", timeout=Duration.seconds(20), memory=512, env=env)   # two model attempts of 4 s each fit comfortably

        model = ["arn:aws:bedrock:*::foundation-model/anthropic.*", "arn:aws:bedrock:::foundation-model/anthropic.*", f"arn:aws:bedrock:*:{account}:inference-profile/*anthropic.*"]   # the small model (REVIEW_MODEL_ID) through its regional profile; Anthropic models only
        for fn in (brief_fn, launcher_fn):
            table.grant_read_write_data(fn)
            flags_table.grant_read_data(fn)   # READ only: staff clear or hold an account with scripts/safety_admin.py; nothing at runtime can clear its own stops
            fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=model))
        usage_table.grant_read_write_data(brief_fn)   # the per-account daily cap on checks
        launcher_fn.add_environment("SAFETY_TABLE", table.table_name)
        for k, v in extra_env.items():
            launcher_fn.add_environment(k, v)

        brief_res = videos_resource.add_resource("brief")
        brief_res.add_method("POST", apigw.LambdaIntegration(brief_fn, proxy=True), **cognito_auth)
        CfnOutput(self, "SafetyTableName", value=table.table_name)
        self.table, self.brief_fn = table, brief_fn
