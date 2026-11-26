"""Account deletion (docs/ACCOUNT_DELETION.md): the API routes, the queue and its worker, the job/tombstone table, the keyed-hash secret, and (behind `-c appleRevoke=1`) Sign in with Apple revocation.

Least privilege, per function:
  account_api      (API)    reads and writes the deletion table, sends to the queue, reads the user pool (ListUsers/AdminGetUser), reads the hash secret
  account_deleter  (worker) the ONLY function that may delete a person's data: Query/DeleteItem on each per-user table, DeleteObject under the exact per-user prefixes, DeleteVectors on the photo
                            index, the Cognito admin calls on this pool, StopExecution on the video workflows. DynamoDB and Step Functions cannot be scoped to one user, so the worker is
                            trusted to act only on the id in its job; the API rule "path user = token sub" is what guarantees that id.
  apple_revoke     (flag)   the only function that can read the Apple key; no access to any user data but the deletion table
The flags table stays admin-written: the worker gets DeleteItem only, never PutItem.
"""
from typing import Any, Callable, Dict, List, Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_apigateway as apigw, aws_cloudwatch as cw, aws_dynamodb as dynamodb, aws_iam as iam, aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as sources, aws_logs as logs, aws_secretsmanager as secretsmanager, aws_sqs as sqs
from constructs import Construct

TOKEN_VALID_SECONDS = 3600     # both app clients issue 1 hour id/access tokens (backend_stack.py); the worker waits this long (plus a margin) before the final sweep
SETTLE_SECONDS = TOKEN_VALID_SECONDS + 300

# What the worker cleans, by CDK logical id of the table (regex on the logical id). The test in tests/test_account_deletion.py fails when the stack has a table or bucket that is
# neither listed here nor in EXEMPT, so a future per-user table cannot be forgotten silently.
COVERED_TABLES = {"VideosTable": "videos", "UsageTable": "usage", "WalletTable": "wallet", "AccountFlagsTable": "flags", "MediaTable": "media", "SafetyTable": "safety"}
EXEMPT_TABLES = {"AccountDeletionTable": "the deletion jobs and tombstones themselves"}
COVERED_BUCKETS = {"AssetsBucket": ["videos/<user>/", "uploads/<user>/", "generation/v2/<video>/", "generation/assets/<video>/"], "MediaBucket": ["o/<user>/", "t/<user>/"]}
COVERED_VECTOR_INDEXES = ["PhotoIndex"]


class AccountDeletion(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, stage: str, is_prod: bool, make_fn: Callable[..., _lambda.Function], user_pool: Any, api: apigw.RestApi, user_id_resource: apigw.IResource,
        cognito_auth: Dict, cors_headers: List[str], common_env: Dict[str, str], videos_table: Any, usage_table: Any, wallet_table: Any, flags_table: Any, safety_table: Any,
        assets_bucket_name: str, generate_machines: List[Any], edit_machine: Optional[Any], media: Optional[Any], tombstone: bool, tombstone_days: int, domain: Optional[str],
        web_return_url: str, apple: bool, apple_layer: Optional[_lambda.ILayerVersion] = None,
    ) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        account, region = stack.account, stack.region
        keep = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        table = dynamodb.Table(
            self, "AccountDeletionTable", partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl", point_in_time_recovery=False, removal_policy=keep,   # no backup: a backup would keep what a person asked us to delete
        )
        key_secret = secretsmanager.Secret(
            self, "DeletionKey", secret_name=f"videomk/{stage}/deletion_key", description="HMAC key for hashed account references and the tombstone (docs/ACCOUNT_DELETION.md). Losing it only makes old hashes unmatchable.",
            generate_secret_string=secretsmanager.SecretStringGenerator(password_length=48, exclude_punctuation=True), removal_policy=keep,
        )
        dlq = sqs.Queue(self, "DeletionDlq", retention_period=Duration.days(14), encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True)
        queue = sqs.Queue(self, "DeletionQueue", visibility_timeout=Duration.seconds(660), encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True,
                          dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=5, queue=dlq), retention_period=Duration.days(4))

        pool_arn = user_pool.user_pool_arn
        base_env = {
            "DELETION_TABLE": table.table_name, "DELETION_QUEUE_URL": queue.queue_url, "USER_POOL_ID": user_pool.user_pool_id, "DELETION_KEY_SECRET": key_secret.secret_arn,
            "TOMBSTONE_ENABLED": "1" if tombstone else "0", "TOMBSTONE_DAYS": str(tombstone_days), "DELETION_SETTLE_SECONDS": str(SETTLE_SECONDS),
            "APPLE_REVOKE_ENABLED": "1" if apple else "0",
        }
        worker_env = {**base_env, "SAFETY_TABLE": safety_table.table_name,
                      "GENERATE_STATE_MACHINE_ARNS": ",".join(m.state_machine_arn for m in generate_machines), "EDIT_STATE_MACHINE_ARN": edit_machine.state_machine_arn if edit_machine else ""}
        if media is not None:
            worker_env.update({"MEDIA_TABLE": media.table.table_name, "MEDIA_BUCKET": media.media_bucket_name, "VECTOR_BUCKET": media.vector_bucket_name, "VECTOR_INDEX": "photos"})

        # ---- the API function
        api_env = dict(base_env)
        api_fn = make_fn("AccountApiFn", "account_api", "account_api.handler", timeout=Duration.seconds(20), memory=512, env=api_env)
        table.grant_read_write_data(api_fn)
        queue.grant_send_messages(api_fn)
        key_secret.grant_read(api_fn)
        api_fn.add_to_role_policy(iam.PolicyStatement(actions=["cognito-idp:ListUsers", "cognito-idp:AdminGetUser"], resources=[pool_arn]))

        # ---- the worker
        worker = make_fn("AccountDeleterFn", "account_deleter", "account_deleter.handler", timeout=Duration.minutes(10), memory=1024, env=worker_env)
        worker.add_event_source(sources.SqsEventSource(queue, batch_size=1, report_batch_item_failures=True, max_concurrency=5))
        table.grant_read_write_data(worker)
        queue.grant_send_messages(worker)
        key_secret.grant_read(worker)

        def tbl(t: Any, actions: List[str], index: bool = False) -> None:
            worker.add_to_role_policy(iam.PolicyStatement(actions=actions, resources=[t.table_arn] + ([f"{t.table_arn}/index/GSI_UserVideos"] if index else [])))

        tbl(videos_table, ["dynamodb:Query"], index=True)
        tbl(videos_table, ["dynamodb:DeleteItem", "dynamodb:BatchWriteItem"])
        for t in (usage_table, wallet_table):
            tbl(t, ["dynamodb:Query", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"])
        tbl(flags_table, ["dynamodb:DeleteItem"])   # delete only: nothing at runtime can write a flag
        tbl(safety_table, ["dynamodb:Query", "dynamodb:PutItem", "dynamodb:DeleteItem"])
        if media is not None:
            tbl(media.table, ["dynamodb:Query", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"])
        assets_arn = f"arn:aws:s3:::{assets_bucket_name}"
        asset_prefixes = ["videos/*", "uploads/*", "generation/v2/*", "generation/assets/*"]
        worker.add_to_role_policy(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[assets_arn], conditions={"StringLike": {"s3:prefix": asset_prefixes}}))
        worker.add_to_role_policy(iam.PolicyStatement(actions=["s3:DeleteObject"], resources=[f"{assets_arn}/{p}" for p in asset_prefixes]))
        if media is not None:
            worker.add_to_role_policy(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[media.bucket.bucket_arn], conditions={"StringLike": {"s3:prefix": ["o/*", "t/*"]}}))
            worker.add_to_role_policy(iam.PolicyStatement(actions=["s3:DeleteObject"], resources=[f"{media.bucket.bucket_arn}/o/*", f"{media.bucket.bucket_arn}/t/*"]))
            worker.add_to_role_policy(iam.PolicyStatement(actions=["s3vectors:DeleteVectors"], resources=[media.index_arn]))
        worker.add_to_role_policy(iam.PolicyStatement(actions=["cognito-idp:ListUsers", "cognito-idp:AdminGetUser", "cognito-idp:AdminDisableUser", "cognito-idp:AdminUserGlobalSignOut", "cognito-idp:AdminDeleteUser"], resources=[pool_arn]))
        if generate_machines:
            worker.add_to_role_policy(iam.PolicyStatement(actions=["states:StopExecution"], resources=[f"arn:aws:states:{region}:{account}:execution:{m.state_machine_name}:*" for m in generate_machines]))
        if edit_machine is not None:
            worker.add_to_role_policy(iam.PolicyStatement(actions=["states:ListExecutions"], resources=[edit_machine.state_machine_arn]))
            worker.add_to_role_policy(iam.PolicyStatement(actions=["states:StopExecution"], resources=[f"arn:aws:states:{region}:{account}:execution:{edit_machine.state_machine_name}:*"]))

        # ---- alarms: a failing step logs ACCOUNT_DELETION_FAILED (a stuck job also ACCOUNT_DELETION_STUCK); no address is ever in these lines. No action is attached: the owner picks one (SNS, chat).
        mf = logs.MetricFilter(
            self, "FailedFilter", log_group=worker.log_group, filter_pattern=logs.FilterPattern.any_term("ACCOUNT_DELETION_FAILED", "ACCOUNT_DELETION_STUCK", "ACCOUNT_DELETION_WORKER_ERROR"),
            metric_namespace="videomk/AccountDeletion", metric_name="Failures", metric_value="1", default_value=0,
        )
        lr = worker.node.try_find_child("LogRetention")
        if lr is not None:
            mf.node.add_dependency(lr)   # the log group is created by the log-retention resource
        cw.Alarm(self, "FailedAlarm", metric=cw.Metric(namespace="videomk/AccountDeletion", metric_name="Failures", statistic="Sum", period=Duration.minutes(5)), threshold=1, evaluation_periods=1,
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING, alarm_description="An account deletion step failed (docs/ACCOUNT_DELETION.md)")
        cw.Alarm(self, "DlqAlarm", metric=dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(5)), threshold=1, evaluation_periods=1,
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING, alarm_description="An account deletion message is in the dead-letter queue")

        # ---- routes
        acct_res = user_id_resource.add_resource("account")
        delete_res = acct_res.add_resource("delete")
        integration = apigw.LambdaIntegration(api_fn, proxy=True)
        delete_res.add_method("POST", integration, **cognito_auth)
        delete_res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["POST", "OPTIONS"], allow_headers=cors_headers)

        self.apple_fn = None
        if apple:
            if apple_layer is None:
                raise ValueError("appleRevoke needs the apple_deps layer")
            return_url = f"https://api.{domain}/account/apple-callback" if domain else f"https://{api.rest_api_id}.execute-api.{region}.amazonaws.com/prod/account/apple-callback"   # not api.url_for_path: that would make the function depend on the deployment that contains it
            api_fn.add_environment("APPLE_RETURN_URL", return_url)
            api_fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter/videomk/apple_services_id"]))
            rev = acct_res.add_resource("apple-revoke")
            rev.add_method("POST", integration, **cognito_auth)
            rev.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["POST", "OPTIONS"], allow_headers=cors_headers)
            fn = make_fn("AppleRevokeFn", "apple_revoke", "apple_revoke.handler", timeout=Duration.seconds(25), memory=512, layers=[apple_layer],
                         env={**base_env, "APPLE_RETURN_URL": return_url, "APPLE_APP_RETURN": "com.videomk.app://auth/apple-revoked", "APPLE_WEB_RETURN": web_return_url})
            table.grant_read_write_data(fn)
            key_secret.grant_read(fn)
            fn.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[f"arn:aws:ssm:{region}:{account}:parameter/videomk/{n}" for n in ("apple_services_id", "apple_team_id", "apple_key_id")]))
            fn.add_to_role_policy(iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[f"arn:aws:secretsmanager:{region}:{account}:secret:/videomk/apple_private_key-*"]))
            cb = api.root.add_resource("account").add_resource("apple-callback")
            cb.add_method("POST", apigw.LambdaIntegration(fn, proxy=True))   # public on purpose: Apple's form post; the signed state is the credential
            self.apple_fn = fn
            CfnOutput(self, "AppleRevokeReturnUrl", value=return_url, description="Register this exact URL as a second Return URL on the Apple Services ID (docs/ACCOUNT_DELETION.md)")

        CfnOutput(self, "DeletionTableName", value=table.table_name)
        CfnOutput(self, "DeletionQueueUrl", value=queue.queue_url)
        CfnOutput(self, "DeletionWorkerName", value=worker.function_name)
        self.table, self.queue, self.key_secret, self.api_fn, self.worker, self.base_env = table, queue, key_secret, api_fn, worker, base_env
