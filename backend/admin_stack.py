"""The owner-only console (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md, slice one), in its OWN stack `videomk-admin-<stage>`.

  cd backend && scripts/admin_console.sh qa diff|deploy          (or: cdk deploy videomk-admin-qa -c admin=1 -c stage=qa)

It owns no customer data: deleting the stack loses nothing (the audit bucket alone stays, by design). Nothing here is added to the main stack; the main
stack's tables, workflow and customer pool are referred to by NAME (read from the deployed launcher's settings when the stack is synthesized), never imported.

What it creates
  * the page: one static page in a private bucket behind CloudFront (strict Content-Security-Policy, no outside scripts), only served to the countries
    of the `AllowedCountries` stack parameter (CloudFront's own geo restriction, free);
  * the API: an HTTP API reached through the same address (`/api/*`). EVERY route requires a token of the admin pool, checked by API Gateway itself
    before any of our code runs; throttled to a few requests a second;
  * sign-in: a dedicated Cognito user pool. No self sign-up, MFA required, a passkey with user verification as the normal way in, a long password plus
    an authenticator code as the recovery way, 10-minute tokens, no hosted page, no social sign-in. One user, created from the command line;
  * the data: one small rollup table and an hourly job;
  * the audit log: a bucket with Object Lock (compliance mode, 400 days);
  * alerts: one SNS topic that emails the owner; three alarms of its own; every alarm of the main stack is forwarded to it by an EventBridge rule
    (so the main stack's alarms notify without changing the main stack).

Who may do what (least privilege; tests/test_admin_cdk.py reads this from the synthesized template)
  rollup job    reads: the videos of a day (the day index; small fields only, never the prompt), the free-budget counter, the plans parameter, the run
                list and the history of failed runs, the customer pool's user list, Lambda metrics. Writes: the rollup table. Publishes alerts.
  read function reads: the rollup table, the switches item, the free-budget counter, the plans parameter, the runs in progress, alarm states. Writes nothing.
  act function  reads and updates ONE item (`ops:switches` in the account-flags table, two true/false fields), writes audit files, publishes alerts.
                It cannot touch credits, wallets, plans, entitlements, budgets, videos or any other flag.
  sign-in hook  writes audit files, publishes alerts.
"""
import os
from typing import Any, Dict, List, Optional

from aws_cdk import CfnOutput, CfnParameter, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigw2
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(HERE, "admin_console", "site")
LAMBDAS_DIR = os.path.join(HERE, "admin_console", "lambdas")
DEFAULT_ALERT_EMAIL = "hello@videomk.com"
DEFAULT_COUNTRIES = "GB,ES"
AUDIT_DAYS = 400
STEP_UP_SECONDS = 300
TOKEN_MINUTES, RENEWAL_MINUTES = 10, 60
SWITCH_ITEM = "ops:switches"
SWITCH_FIELDS = ["user_id", "stop_new_videos", "stop_free_videos", "stop_dictation", "stop_video_upload", "updated_at", "updated_by"]
USAGE_DAY_INDEX = "GSI_UsageDay"
# the attributes the rollup job may read from a video record: the keys and backend_stack.USAGE_DAY_FIELDS (a test holds the two lists together). Never the prompt.
VIDEO_FIELDS = ["video_id", "usage_day", "created_at", "status", "plan", "user_id", "cost_usd", "c_speech", "c_script", "c_research", "c_photos", "c_stock", "c_deck", "duration_s",
                "aspect", "resolution", "failure_code", "credits_charged", "credits_multiplier", "free_credits", "last_rendered_at", "retries", "deck"]
ENGINE_FUNCTIONS = ("v2_plan", "v2_beat", "v2_timeline", "v2_render_chunk", "v2_audio", "v2_finalize")
LAUNCHER_FUNCTION = "VideoGenerationSFLauncher"
MAIN_KEYS = ("videos_table", "usage_table", "flags_table", "state_machine_arn", "customer_pool_id", "plans_param")


def csp(region: str) -> str:
    """Only this address and the Cognito endpoint of the admin pool. No inline script or style, no outside host, no framing, no forms, no plugins."""
    return "; ".join([
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        f"connect-src 'self' https://cognito-idp.{region}.amazonaws.com",
        "manifest-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    ])


def main_stack_values(session: Any) -> Dict[str, Any]:
    """The names of the main stack's resources the console reads, taken from the DEPLOYED launcher's own settings (so nothing is exported from, or added to,
    the main stack), and the memory of the engine functions (for the compute estimate)."""
    lam = session.client("lambda")
    env = lam.get_function_configuration(FunctionName=LAUNCHER_FUNCTION)["Environment"]["Variables"]
    out = {"videos_table": env["VIDEOS_TABLE"], "usage_table": env["USAGE_TABLE"], "flags_table": env["FLAGS_TABLE"], "state_machine_arn": env["STATE_MACHINE_ARN"],
           "customer_pool_id": env["USER_POOL_ID"], "plans_param": env["PLANS_CONFIG_PARAM"], "engine_functions": {}}
    for name in ENGINE_FUNCTIONS:
        try:
            out["engine_functions"][name] = int(lam.get_function_configuration(FunctionName=name)["MemorySize"])
        except lam.exceptions.ResourceNotFoundException:
            pass
    return out


class AdminStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, stage: str, main: Dict[str, Any], host: Optional[str] = None, alert_email: str = DEFAULT_ALERT_EMAIL,
                 cli_profile: str = "", **kw: Any) -> None:
        super().__init__(scope, cid, description=f"VideoMK owner console ({stage}): private page, API, sign-in, rollups, audit log, alerts. Owns no customer data.", **kw)
        missing = [k for k in MAIN_KEYS if not main.get(k)]
        if missing:
            raise ValueError(f"the console needs these names of the main stack: {', '.join(missing)}")
        is_prod = stage == "prod"
        keep = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        prefix = f"videomk-admin-{stage}"
        arn = lambda service, rest: f"arn:aws:{service}:{self.region}:{self.account}:{rest}"   # noqa: E731
        videos_arn, usage_arn, flags_arn = (arn("dynamodb", "table/" + main[k]) for k in ("videos_table", "usage_table", "flags_table"))
        machine_arn = main["state_machine_arn"]
        machine_name = machine_arn.rsplit(":", 1)[1]
        plans_param_arn = arn("ssm", "parameter" + main["plans_param"])
        customer_pool_arn = arn("cognito-idp", "userpool/" + main["customer_pool_id"])

        countries = CfnParameter(self, "AllowedCountries", type="CommaDelimitedList", default=DEFAULT_COUNTRIES,
                                 description="Two-letter country codes the console is served to (CloudFront geo restriction). Change it before travelling: docs/ADMIN_RUNBOOK.md.")

        # ------------------------------------------------------------------ data: the rollups (counts; no account ids, no text) and the locked audit log
        rollups = dynamodb.Table(
            self, "Rollups", partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING), sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="ttl", removal_policy=keep,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=is_prod),
        )
        # Object Lock, compliance mode: nobody, not even the account's root user, can change or delete an entry before its date. The bucket therefore outlives the stack.
        audit = s3.Bucket(
            self, "Audit", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True, versioned=True,
            object_lock_enabled=True, object_lock_default_retention=s3.ObjectLockRetention.compliance(Duration.days(AUDIT_DAYS)), removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[s3.LifecycleRule(id="remove-after-the-lock", expiration=Duration.days(AUDIT_DAYS + 30), noncurrent_version_expiration=Duration.days(30))],
        )

        # ------------------------------------------------------------------ alerts: one topic, one email address
        topic = sns.Topic(self, "Alerts", display_name=f"VideoMK alerts ({stage})", enforce_ssl=True)
        topic.add_subscription(subs.EmailSubscription(alert_email))
        topic.add_to_resource_policy(iam.PolicyStatement(   # alarms of THIS account may publish (a topic with its own policy loses the default one)
            sid="AlarmsOfThisAccount", actions=["sns:Publish"], principals=[iam.ServicePrincipal("cloudwatch.amazonaws.com")], resources=[topic.topic_arn],
            conditions={"ArnLike": {"aws:SourceArn": arn("cloudwatch", "alarm:*")}, "StringEquals": {"aws:SourceAccount": self.account}}))

        # ------------------------------------------------------------------ functions (their own code folder: none of it ships with the customer-facing functions)
        code = _lambda.Code.from_asset(LAMBDAS_DIR, exclude=["__pycache__", "*.pyc"])
        common_env = {"STAGE": stage, "ALERT_TOPIC_ARN": topic.topic_arn, "AUDIT_BUCKET": audit.bucket_name, "AWS_CLI_PROFILE": cli_profile or stage}

        def make(name: str, handler: str, *, timeout: int, memory: int = 256, env: Optional[Dict[str, str]] = None) -> _lambda.Function:
            group = logs.LogGroup(self, f"{name}Logs", log_group_name=f"/aws/lambda/{prefix}-{name.lower()}", retention=logs.RetentionDays.THREE_MONTHS, removal_policy=RemovalPolicy.DESTROY)
            return _lambda.Function(self, f"{name}Fn", function_name=f"{prefix}-{name.lower()}", runtime=_lambda.Runtime.PYTHON_3_12, architecture=_lambda.Architecture.ARM_64,
                                    handler=handler, code=code, timeout=Duration.seconds(timeout), memory_size=memory, environment={**common_env, **(env or {})}, log_group=group)

        def allow(fn: _lambda.Function, actions: List[str], resources: List[str], conditions: Optional[Dict[str, Any]] = None) -> None:
            fn.add_to_role_policy(iam.PolicyStatement(actions=actions, resources=resources, **({"conditions": conditions} if conditions else {})))

        only_item = lambda key: {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": [key]}}   # noqa: E731
        table_env = {"USAGE_TABLE": main["usage_table"], "FLAGS_TABLE": main["flags_table"], "PLANS_CONFIG_PARAM": main["plans_param"], "STATE_MACHINE_ARN": machine_arn,
                     "ROLLUP_TABLE": rollups.table_name}

        rollup_fn = make("Rollup", "admin_rollup.handler", timeout=300, memory=512, env={
            **table_env, "VIDEOS_TABLE": main["videos_table"], "CUSTOMER_POOL_ID": main["customer_pool_id"], "EXCLUDE_TEST_ACCOUNTS": "1" if is_prod else "0",
            "ENGINE_FUNCTIONS": self.to_json_string(main.get("engine_functions") or {})})
        allow(rollup_fn, ["dynamodb:Query"], [f"{videos_arn}/index/{USAGE_DAY_INDEX}"])   # the day index carries the small fields only
        allow(rollup_fn, ["dynamodb:Scan"], [videos_arn],   # until the index exists: a scan that may return these attributes and no others (never the prompt)
              {"ForAllValues:StringEquals": {"dynamodb:Attributes": VIDEO_FIELDS}, "StringEquals": {"dynamodb:Select": "SPECIFIC_ATTRIBUTES"}})
        allow(rollup_fn, ["dynamodb:GetItem"], [usage_arn], only_item("fbudget"))
        allow(rollup_fn, ["ssm:GetParameter"], [plans_param_arn])
        allow(rollup_fn, ["states:ListExecutions"], [machine_arn])
        allow(rollup_fn, ["states:GetExecutionHistory"], [arn("states", f"execution:{machine_name}:*")])   # read with includeExecutionData=false: the step of a failed run
        allow(rollup_fn, ["cognito-idp:ListUsers"], [customer_pool_arn])
        allow(rollup_fn, ["cloudwatch:GetMetricData"], ["*"])   # metrics have no resource to name
        allow(rollup_fn, ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query"], [rollups.table_arn])
        allow(rollup_fn, ["sns:Publish"], [topic.topic_arn])
        hourly = events.Rule(self, "Hourly", schedule=events.Schedule.rate(Duration.hours(1)), targets=[targets.LambdaFunction(rollup_fn, retry_attempts=1)])

        read_fn = make("Read", "admin_read.handler", timeout=15, env={**table_env, "ALARM_PREFIXES": f"videomk-{stage}-,{prefix}-"})
        allow(read_fn, ["dynamodb:GetItem", "dynamodb:Query"], [rollups.table_arn])
        allow(read_fn, ["dynamodb:GetItem"], [flags_arn], only_item(SWITCH_ITEM))
        allow(read_fn, ["dynamodb:GetItem"], [usage_arn], only_item("fbudget"))
        allow(read_fn, ["ssm:GetParameter"], [plans_param_arn])
        allow(read_fn, ["states:ListExecutions"], [machine_arn])
        allow(read_fn, ["cloudwatch:DescribeAlarms"], ["*"])   # alarm states have no narrower resource for a list

        act_fn = make("Act", "admin_act.handler", timeout=10, env={"FLAGS_TABLE": main["flags_table"]})
        allow(act_fn, ["dynamodb:GetItem"], [flags_arn], only_item(SWITCH_ITEM))
        allow(act_fn, ["dynamodb:UpdateItem"], [flags_arn],   # ONE item, and only its two switches and the two stamps: no other flag (unlimited, storage, safety holds) can be written
              {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": [SWITCH_ITEM], "dynamodb:Attributes": SWITCH_FIELDS},
               "StringEqualsIfExists": {"dynamodb:ReturnValues": ["NONE", "UPDATED_OLD", "UPDATED_NEW"]}})
        hook_fn = make("SignIn", "admin_auth_event.handler", timeout=5)
        for fn in (act_fn, hook_fn):
            allow(fn, ["s3:PutObject"], [audit.arn_for_objects("audit/*")])
            allow(fn, ["sns:Publish"], [topic.topic_arn])

        # ------------------------------------------------------------------ sign-in: a pool of its own, nothing shared with customer accounts
        pool = cognito.UserPool(
            self, "AdminPool", user_pool_name=prefix, feature_plan=cognito.FeaturePlan.ESSENTIALS,   # passkeys need Essentials
            self_sign_up_enabled=False, sign_in_aliases=cognito.SignInAliases(email=True), sign_in_case_sensitive=False,
            mfa=cognito.Mfa.REQUIRED, mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True, email=False),
            password_policy=cognito.PasswordPolicy(min_length=20, require_lowercase=True, require_uppercase=True, require_digits=True, require_symbols=False,
                                                   temp_password_validity=Duration.days(3)),
            account_recovery=cognito.AccountRecovery.NONE,   # no "forgot password" by email: recovery is the command line (docs/ADMIN_RUNBOOK.md)
            device_tracking=None, deletion_protection=is_prod, removal_policy=keep,
            user_invitation=cognito.UserInvitationConfig(
                email_subject="VideoMK console: your first sign-in",
                email_body="Your sign-in name for the VideoMK console is {username} and your temporary password is {####} (valid for 3 days, used once). "
                           "You will be asked to choose your own long password, add an authenticator app, and then add a passkey."),
            lambda_triggers=cognito.UserPoolTriggers(post_authentication=hook_fn),
        )
        cfn_pool = pool.node.default_child
        factors = ["PASSWORD"] + (["WEB_AUTHN"] if host else [])
        cfn_pool.add_property_override("Policies.SignInPolicy.AllowedFirstAuthFactors", factors)
        if host:   # the passkey is bound to the console's own address; with user verification (Face ID, fingerprint or the device passcode) it counts as both factors
            cfn_pool.add_property_override("WebAuthnRelyingPartyID", host)
            cfn_pool.add_property_override("WebAuthnUserVerification", "required")
            cfn_pool.add_property_override("WebAuthnFactorConfiguration", "MULTI_FACTOR_WITH_USER_VERIFICATION")
        client = pool.add_client(
            "Web", generate_secret=False, disable_o_auth=True, auth_flows=cognito.AuthFlow(user=True),   # the choice-based flow (passkey, or password then code); no hosted page, no social sign-in
            access_token_validity=Duration.minutes(TOKEN_MINUTES), id_token_validity=Duration.minutes(TOKEN_MINUTES), refresh_token_validity=Duration.minutes(RENEWAL_MINUTES),
            enable_token_revocation=True, prevent_user_existence_errors=True,
        )
        act_fn.add_environment("ADMIN_POOL_ID", pool.user_pool_id)   # only to print the lock command in the alert email (the sign-in hook gets the pool id with each event)

        # ------------------------------------------------------------------ the API: every route behind the admin pool's token, checked by API Gateway
        jwt = authorizers.HttpJwtAuthorizer("AdminToken", f"https://cognito-idp.{self.region}.amazonaws.com/{pool.user_pool_id}", jwt_audience=[client.user_pool_client_id],
                                            identity_source=["$request.header.Authorization"])
        api = apigw2.HttpApi(self, "Api", api_name=prefix, default_authorizer=jwt, create_default_stage=True)   # no CORS: only the console's own address calls it (through CloudFront)
        api.add_routes(path="/api/home", methods=[apigw2.HttpMethod.GET], integration=integrations.HttpLambdaIntegration("Read", read_fn))
        api.add_routes(path="/api/switches", methods=[apigw2.HttpMethod.POST], integration=integrations.HttpLambdaIntegration("Act", act_fn))
        api.default_stage.node.default_child.default_route_settings = apigw2.CfnStage.RouteSettingsProperty(throttling_burst_limit=10, throttling_rate_limit=5)

        # ------------------------------------------------------------------ the page: private bucket, CloudFront, strict headers, country allow-list
        site = s3.Bucket(self, "Site", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
                         removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        headers = cf.ResponseHeadersPolicy(
            self, "Headers", response_headers_policy_name=f"{prefix}-headers",
            security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
                strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(access_control_max_age=Duration.days(730), include_subdomains=True, preload=True, override=True),
                content_type_options=cf.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cf.ResponseHeadersFrameOptions(frame_option=cf.HeadersFrameOption.DENY, override=True),
                referrer_policy=cf.ResponseHeadersReferrerPolicy(referrer_policy=cf.HeadersReferrerPolicy.NO_REFERRER, override=True),
                content_security_policy=cf.ResponseHeadersContentSecurityPolicy(content_security_policy=csp(self.region), override=True)),
            custom_headers_behavior=cf.ResponseCustomHeadersBehavior(custom_headers=[
                cf.ResponseCustomHeader(header="X-Robots-Tag", value="noindex, nofollow, noarchive", override=True),
                cf.ResponseCustomHeader(header="Permissions-Policy", override=True,
                                        value="publickey-credentials-get=(self), publickey-credentials-create=(self), camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
                cf.ResponseCustomHeader(header="Cross-Origin-Opener-Policy", value="same-origin", override=True),
                cf.ResponseCustomHeader(header="Cross-Origin-Resource-Policy", value="same-origin", override=True),
            ]))
        dist = cf.Distribution(
            self, "Cdn", comment=f"{prefix} (owner console)", default_root_object="index.html", minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            http_version=cf.HttpVersion.HTTP2_AND_3, price_class=cf.PriceClass.PRICE_CLASS_100,
            default_behavior=cf.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(site), viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY,
                                                response_headers_policy=headers, compress=True, allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD),
            additional_behaviors={"/api/*": cf.BehaviorOptions(   # the API through the same address: one origin for the page, the geo restriction covers it too
                origin=origins.HttpOrigin(f"{api.api_id}.execute-api.{self.region}.amazonaws.com", protocol_policy=cf.OriginProtocolPolicy.HTTPS_ONLY),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY, allowed_methods=cf.AllowedMethods.ALLOW_ALL, cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER, response_headers_policy=headers, compress=True)},
        )
        dist.node.default_child.add_property_override("DistributionConfig.Restrictions.GeoRestriction", {"RestrictionType": "whitelist", "Locations": countries.value_as_list})
        s3deploy.BucketDeployment(
            self, "Deploy", destination_bucket=site, distribution=dist, distribution_paths=["/*"], prune=True, memory_limit=256,
            cache_control=[s3deploy.CacheControl.from_string("no-cache, max-age=0, must-revalidate")],
            sources=[s3deploy.Source.asset(SITE_DIR), s3deploy.Source.json_data("config.json", {
                "stage": stage, "region": self.region, "clientId": client.user_pool_client_id, "passkeys": bool(host), "host": host or "",
                "tokenMinutes": TOKEN_MINUTES, "stepUpSeconds": STEP_UP_SECONDS})],
        )

        # ------------------------------------------------------------------ alarms of the console itself, and the main stack's alarms forwarded to the same topic
        to_topic = cw_actions.SnsAction(topic)
        stopped = cw.Alarm(
            self, "RollupStopped", alarm_name=f"{prefix}-rollup-stopped", evaluation_periods=2, threshold=1, comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.BREACHING, alarm_description="The console's hourly rollup job has not finished a run for two hours: the numbers on the console are getting old.",
            metric=cw.Metric(namespace="videomk/Admin", metric_name="RollupHeartbeat", dimensions_map={"Stage": stage}, statistic="Sum", period=Duration.hours(1)))
        failed = cw.Alarm(
            self, "RollupErrors", alarm_name=f"{prefix}-rollup-errors", evaluation_periods=1, threshold=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING, alarm_description="A run of the console's hourly rollup job failed.", metric=rollup_fn.metric_errors(period=Duration.hours(1), statistic="Sum"))
        console = cw.Alarm(
            self, "ConsoleErrors", alarm_name=f"{prefix}-console-errors", evaluation_periods=1, threshold=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING, alarm_description="A function behind the console (read, switches or the sign-in hook) raised an error.",
            metric=cw.MathExpression(expression="a + b + c", period=Duration.minutes(5), using_metrics={
                "a": read_fn.metric_errors(period=Duration.minutes(5), statistic="Sum"), "b": act_fn.metric_errors(period=Duration.minutes(5), statistic="Sum"),
                "c": hook_fn.metric_errors(period=Duration.minutes(5), statistic="Sum")}))
        for alarm in (stopped, failed, console):
            alarm.add_alarm_action(to_topic)
        stopped.add_ok_action(to_topic)
        # The main stack's alarms (account deletion, free spend, and any added later) have no action of their own: their state changes are forwarded here,
        # so they notify without a change to the main stack. Other projects' alarms in the same account are left out by the name prefix.
        events.Rule(
            self, "MainAlarms", description=f"Alarms of videomk-{stage} to the console's alert topic",
            event_pattern=events.EventPattern(source=["aws.cloudwatch"], detail_type=["CloudWatch Alarm State Change"],
                                              detail={"alarmName": [{"prefix": f"videomk-{stage}-"}], "state": {"value": ["ALARM", "OK"]}, "previousState": {"value": ["ALARM", "OK"]}}),
            targets=[targets.SnsTopic(topic, message=events.RuleTargetInput.from_text(
                f"VideoMK {stage}: the alarm {events.EventField.from_path('$.detail.alarmName')} is now {events.EventField.from_path('$.detail.state.value')} "
                f"(it was {events.EventField.from_path('$.detail.previousState.value')}).\n\nWhy: {events.EventField.from_path('$.detail.state.reason')}\n\n"
                f"What it watches: {events.EventField.from_path('$.detail.configuration.description')}"))])

        url = f"https://{dist.distribution_domain_name}"
        CfnOutput(self, "ConsoleUrl", value=url)
        CfnOutput(self, "ConsoleHost", value=dist.distribution_domain_name, description="Put this in stages.json as adminHost and deploy again: the passkey is bound to it")
        CfnOutput(self, "AdminPoolId", value=pool.user_pool_id)
        CfnOutput(self, "AdminClientId", value=client.user_pool_client_id)
        CfnOutput(self, "ApiId", value=api.api_id)
        CfnOutput(self, "RollupTableName", value=rollups.table_name)
        CfnOutput(self, "RollupFunctionName", value=rollup_fn.function_name)
        CfnOutput(self, "AuditBucketName", value=audit.bucket_name)
        CfnOutput(self, "AlertTopicArn", value=topic.topic_arn)
        CfnOutput(self, "DistributionId", value=dist.distribution_id)
        self.pool, self.client, self.api, self.rollups, self.audit, self.topic, self.dist, self.hourly = pool, client, api, rollups, audit, topic, dist, hourly
        self.rollup_fn, self.read_fn, self.act_fn, self.hook_fn = rollup_fn, read_fn, act_fn, hook_fn
