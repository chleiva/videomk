"""The user-feedback loop (docs/FEEDBACK.md): POST /users/{user}/feedback -> a DynamoDB table -> ONE plain-text email a day to the owner, only on days with new feedback.

On by default; `-c feedback=0` removes all of it. Context: -c feedbackFrom=<address> (prod default hello@videomk.com; other stages send nothing unless this is given)
  -c feedbackSesRegion=<region> (prod default us-east-1, where the videomk.com SES identity lives; elsewhere the stack's region)  -c feedbackHourUtc=<0-23> (default 9)
The recipient is the SSM String parameter /videomk/feedback_email_to (no value is created here; with no parameter the daily function logs a warning and does nothing).
"""
import re
from typing import Any, Callable, Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_apigateway as apigw, aws_dynamodb as dynamodb, aws_events as events, aws_events_targets as targets, aws_iam as iam
from constructs import Construct

PARAM = "/videomk/feedback_email_to"
PROD_FROM = "hello@videomk.com"
PROD_SES_REGION = "us-east-1"
_EMAIL = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")


def enabled(node) -> bool:
    v = node.try_get_context("feedback")
    return True if v is None else str(v).strip().lower() not in ("0", "false", "no", "off")


class FeedbackLoop(Construct):
    def __init__(self, scope: Construct, cid: str, *, is_prod: bool, make_fn: Callable[..., Any], usage_table: Any, user_id_resource: apigw.IResource, cognito_auth: dict, cors_headers: list) -> None:
        super().__init__(scope, cid)
        stack = Stack.of(self)
        node = stack.node
        sender = str(node.try_get_context("feedbackFrom") or (PROD_FROM if is_prod else "")).strip()
        if sender and not _EMAIL.match(sender):
            raise ValueError(f"-c feedbackFrom={sender!r} is not an email address")
        ses_region = str(node.try_get_context("feedbackSesRegion") or (PROD_SES_REGION if is_prod else stack.region))
        hour = int(node.try_get_context("feedbackHourUtc") or 9)
        if not 0 <= hour <= 23:
            raise ValueError("-c feedbackHourUtc must be 0..23")

        table = dynamodb.Table(
            self, "FeedbackTable", partition_key=dynamodb.Attribute(name="feedbackId", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN,   # the owner keeps feedback: never deleted with the stack; no TTL
        )
        # Sparse: only items not yet mailed carry `pending`, so the daily run reads exactly the new ones (a scan would read the whole table every day).
        table.add_global_secondary_index(index_name="GSI_Pending", partition_key=dynamodb.Attribute(name="pending", type=dynamodb.AttributeType.STRING),
                                         sort_key=dynamodb.Attribute(name="feedbackId", type=dynamodb.AttributeType.STRING), projection_type=dynamodb.ProjectionType.ALL)
        # Lets the account deletion find a person's rows without a scan (keys only: it never reads the text).
        table.add_global_secondary_index(index_name="GSI_User", partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
                                         sort_key=dynamodb.Attribute(name="feedbackId", type=dynamodb.AttributeType.STRING), projection_type=dynamodb.ProjectionType.KEYS_ONLY)

        api_fn = make_fn("FeedbackApiFunction", "feedback_api", "feedback_api.handler", timeout=Duration.seconds(10), env={"FEEDBACK_TABLE": table.table_name})
        api_fn.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:PutItem"], resources=[table.table_arn]))   # write only: the function never reads feedback back
        usage_table.grant_read_write_data(api_fn)   # the per-user counters
        res = user_id_resource.add_resource("feedback")
        res.add_method("POST", apigw.LambdaIntegration(api_fn, proxy=True), **cognito_auth)
        res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["POST", "OPTIONS"], allow_headers=cors_headers)

        digest = make_fn("FeedbackDigestFunction", "feedback_digest", "feedback_digest.handler", timeout=Duration.minutes(5),
                         env={"FEEDBACK_TABLE": table.table_name, "FEEDBACK_EMAIL_TO_PARAM": PARAM, "FEEDBACK_FROM": sender, "FEEDBACK_SES_REGION": ses_region})
        digest.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:Query"], resources=[f"{table.table_arn}/index/GSI_Pending"]))
        digest.add_to_role_policy(iam.PolicyStatement(actions=["dynamodb:UpdateItem"], resources=[table.table_arn]))
        digest.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{PARAM}"]))
        if sender:
            digest.add_to_role_policy(iam.PolicyStatement(actions=["ses:SendEmail"], resources=[f"arn:aws:ses:{ses_region}:{stack.account}:identity/*"], conditions={"StringEquals": {"ses:FromAddress": sender}}))
        self.rule = events.Rule(self, "DailySchedule", schedule=events.Schedule.cron(minute="0", hour=str(hour)), targets=[targets.LambdaFunction(digest, retry_attempts=1)])

        CfnOutput(self, "FeedbackTableName", value=table.table_name)
        self.table, self.api_fn, self.digest_fn = table, api_fn, digest
