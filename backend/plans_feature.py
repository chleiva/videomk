"""Plans, phase 1 (docs/PLANS.md): the entitlements table, the free-allowance claims, the owner's knobs, the plan and gallery routes, the purchase stubs, the daily metric
and the alarms on free spend. Everything is ADDITIVE: two new tables, one SSM parameter, new functions and routes; no existing table, bucket or user pool property changes.

On by default; `-c plans=0` removes all of it (every function then behaves exactly as before plans).
`-c deviceProof=1` adds the device-proof routes (iOS App Attest; needs the apple_deps layer: `backend/layers/build_layer.sh apple_deps`). Off by default.
`-c freeCostAlarmUsd=3` and `-c freeCreditsAlarm=15` set the two alarm thresholds. The alarms have NO action: there is no notification topic yet.

The stack is close to CloudFormation's 500 resources (421 before plans), so this construct is frugal: one Lambda permission per function for the whole API
(scope_permission_to_method=False), `{store}` path parameters instead of a resource per store, CORS preflight only where a browser needs it (GET .../plan), and the
statements go into each function's own default policy. Plans add about 34 resources, the device routes about 11 more.

Who may do what (least privilege; the launcher gets ONE separate inline policy, because adding statements one by one to its large default policy has dropped statements before):
  entitlements table   READ for the launcher, wallet, capabilities, watermark, library, plan and device functions; DeleteItem for the account-deletion worker; NOBODY at
                       runtime can write it (the writers are an admin with AWS credentials now, and the purchase functions in phase 2)
  free-claims table    read and write for the wallet, the launcher and the device function (they record a claim when a free allowance is granted)
  the knobs (SSM)      GetParameter on the one parameter; changed by an admin (`scripts/plans_admin.py config set ...`), never by a function
  showcase/* (S3)      GetObject for the gallery function only; written by an admin (`scripts/plans_admin.py showcase add ...`)
"""
from typing import Any, Callable, Dict, List, Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_apigateway as apigw, aws_cloudwatch as cw, aws_dynamodb as dynamodb, aws_events as events, aws_events_targets as targets
from aws_cdk import aws_iam as iam, aws_lambda as _lambda, aws_ssm as ssm
from constructs import Construct

NAMESPACE = "videomk/Plans"
APP_ATTEST_APP_IDS = "39ANXJNUTL.com.videomk.app"   # <Apple team id>.<bundle id>


def enabled(node) -> bool:
    v = node.try_get_context("plans")
    return True if v is None else str(v).strip().lower() not in ("0", "false", "no", "off")


def device_proof(node) -> bool:
    v = node.try_get_context("deviceProof")
    return False if v is None else str(v).strip().lower() in ("1", "true", "yes", "on")


class Plans(Construct):
    def __init__(self, scope: Construct, cid: str, *, stage: str, is_prod: bool, make_fn: Callable[..., Any], api: apigw.RestApi, user_id_resource: apigw.IResource, cognito_auth: Dict,
                 cors_headers: List[str], assets_bucket_name: str, videos_table: Any, usage_table: Any, wallet_table: Any, flags_table: Any, launcher_fn: _lambda.Function,
                 wallet_fn: _lambda.Function, capabilities_fn: _lambda.Function, watermark_fn: Optional[_lambda.Function], library_fns: List[_lambda.Function], deletion: Any,
                 tombstone: bool, user_pool_arn: str, device_layer: Optional[_lambda.ILayerVersion]) -> None:
        super().__init__(scope, cid)
        stack = Stack.of(self)
        keep = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        entitlements = dynamodb.Table(
            self, "EntitlementsTable", partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=is_prod), removal_policy=keep,
        )
        claims = dynamodb.Table(
            self, "FreeClaimsTable", partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl", removal_policy=keep,   # salted hashes only; no backup on purpose (a claim that expired must not come back)
        )
        param_name = f"/videomk/{stage}/plans/config"
        ssm.StringParameter(self, "Config", parameter_name=param_name, string_value="{}",
                            description="videomk plans: the owner's knobs as one JSON object (docs/PLANS.md). Edit with backend/scripts/plans_admin.py config set; {} = every default.")
        param_arn = f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{param_name}"
        env = {"PLANS_ENABLED": "1", "ENTITLEMENTS_TABLE": entitlements.table_name, "FREE_CLAIMS_TABLE": claims.table_name, "PLANS_CONFIG_PARAM": param_name,
               "PLANS_REQUIRE_DEVICE_PROOF_DEFAULT": "1" if is_prod else "0"}   # production: no free creation without a device proof; other stages: testing goes on

        read_ent = iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[entitlements.table_arn])
        read_cfg = iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[param_arn])
        rw_claims = iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], resources=[claims.table_arn])
        rw_usage = iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"], resources=[usage_table.table_arn])
        read_usage = iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[usage_table.table_arn])
        read_wallet = iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:Query"], resources=[wallet_table.table_arn])
        rw_wallet = iam.PolicyStatement(actions=["dynamodb:GetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem"], resources=[wallet_table.table_arn])
        read_flags = iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[flags_table.table_arn])
        read_key = iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[deletion.key_secret.secret_arn])   # the HMAC key of the claim hashes (the deletion key, another domain)

        def attach(fn: _lambda.Function, name: str, statements: List[iam.PolicyStatement], variables: Optional[Dict[str, str]] = None, separate: bool = False) -> None:
            for k, v in (env if variables is None else variables).items():
                fn.add_environment(k, v)
            if separate:
                fn.role.attach_inline_policy(iam.Policy(self, f"{name}Policy", statements=statements))
            else:
                for s in statements:
                    fn.add_to_role_policy(s)

        def integration_of(fn: _lambda.Function) -> apigw.LambdaIntegration:   # one permission for the function on this API, not two per route
            return apigw.LambdaIntegration(fn, proxy=True, allow_test_invoke=False, scope_permission_to_method=False)

        # the two functions that grant and spend credits
        attach(launcher_fn, "Launcher", [read_ent, read_cfg, rw_claims, read_key], separate=True)   # (it already reads and writes the usage and wallet tables)
        attach(wallet_fn, "Wallet", [read_ent, read_cfg, rw_claims, read_key, rw_usage])
        attach(capabilities_fn, "Capabilities", [read_ent, read_cfg, read_wallet, read_flags, read_usage])
        if watermark_fn is not None:
            attach(watermark_fn, "Watermark", [read_ent, read_cfg])
        for i, fn in enumerate(library_fns):   # the storage quota follows the plan: these only need to read it
            attach(fn, f"Library{i}", [read_ent], {"PLANS_ENABLED": "1", "ENTITLEMENTS_TABLE": entitlements.table_name})
        attach(deletion.worker, "Deleter", [iam.PolicyStatement(actions=["dynamodb:DeleteItem"], resources=[entitlements.table_arn])], {"ENTITLEMENTS_TABLE": entitlements.table_name})

        # ---- GET /users/{user}/plan and the purchase contract of phase 2 (501 today)
        plan_fn = make_fn("PlansApiFunction", "plans_api", "plans_api.handler", timeout=Duration.seconds(10), env=env)
        attach(plan_fn, "PlansApi", [read_ent, read_cfg, read_wallet, read_flags, read_usage], {})
        integration = integration_of(plan_fn)
        plan_res = user_id_resource.add_resource("plan")
        plan_res.add_method("GET", integration, **cognito_auth)
        plan_res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=["GET", "OPTIONS"], allow_headers=cors_headers)
        user_id_resource.add_resource("purchases").add_resource("{store}").add_method("POST", integration, **cognito_auth)   # store = apple | google (the mobile apps: no CORS preflight needed)
        # public on purpose (the stores call it): store = apple | google | web; answers 501 until phase 2 verifies the signed payload
        api.root.add_resource("purchases").add_resource("webhooks").add_resource("{store}").add_method("POST", integration)

        # ---- GET /gallery: the showcase (public, read-only)
        gallery_fn = make_fn("GalleryFunction", "gallery_api", "gallery_api.handler", timeout=Duration.seconds(10))
        gallery_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[f"arn:aws:s3:::{assets_bucket_name}/showcase/*"]))
        gallery_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[f"arn:aws:s3:::{assets_bucket_name}"], conditions={"StringLike": {"s3:prefix": ["showcase/*"]}}))   # an empty showcase answers 404, not 403
        # no preflight route: the answer carries Access-Control-Allow-Origin: * and a browser's plain GET (language from Accept-Language) needs no preflight
        api.root.add_resource("gallery").add_method("GET", integration_of(gallery_fn))

        # ---- device proof (iOS App Attest now; DeviceCheck and Play Integrity behind their knobs until the owner has the credentials)
        self.device_fn = None
        if device_layer is not None:
            dev_env = {**env, "APP_ATTEST_APP_IDS": APP_ATTEST_APP_IDS, "APP_ATTEST_ALLOW_DEVELOPMENT": "0" if is_prod else "1", "ANDROID_PACKAGE": "com.videomk.app",
                       "DEVICECHECK_SECRET": f"videomk/{stage}/devicecheck", "PLAY_INTEGRITY_SECRET": f"videomk/{stage}/play_integrity",
                       **{k: deletion.base_env[k] for k in ("DELETION_TABLE", "USER_POOL_ID", "DELETION_KEY_SECRET", "TOMBSTONE_ENABLED", "TOMBSTONE_DAYS")}}
            device_fn = make_fn("DeviceApiFunction", "device_api", "device_api.handler", timeout=Duration.seconds(15), memory=1024, env=dev_env, layers=[device_layer])
            secrets_arn = f"arn:aws:secretsmanager:{stack.region}:{stack.account}:secret:videomk/{stage}"
            attach(device_fn, "DeviceApi", [read_ent, read_cfg, rw_claims, read_key, rw_usage, rw_wallet, read_flags,
                                            iam.PolicyStatement(actions=["dynamodb:GetItem"], resources=[deletion.table.table_arn]),
                                            iam.PolicyStatement(actions=["secretsmanager:GetSecretValue"], resources=[f"{secrets_arn}/devicecheck-*", f"{secrets_arn}/play_integrity-*"])]
                   + ([iam.PolicyStatement(actions=["cognito-idp:ListUsers"], resources=[user_pool_arn])] if tombstone else []), {})
            dev = user_id_resource.add_resource("device")
            for name in ("challenge", "verify"):   # the mobile apps only: no CORS preflight
                dev.add_resource(name).add_method("POST", integration_of(device_fn), **cognito_auth)
            self.device_fn = device_fn

        # ---- measurement: yesterday's free and paid usage as metrics, and two alarms on free spend (no action: there is no notification topic yet)
        daily_fn = make_fn("PlansDailyFunction", "plans_daily", "plans_daily.handler", timeout=Duration.minutes(5), env=env)
        attach(daily_fn, "PlansDaily", [iam.PolicyStatement(actions=["dynamodb:Scan"], resources=[videos_table.table_arn]), read_usage, read_cfg], {})
        events.Rule(self, "DailySchedule", schedule=events.Schedule.cron(minute="20", hour="0"), targets=[targets.LambdaFunction(daily_fn, retry_attempts=1)])
        node = stack.node
        cost_usd = float(node.try_get_context("freeCostAlarmUsd") or 3)
        credits = int(node.try_get_context("freeCreditsAlarm") or 15)
        cw.Alarm(self, "FreeCostAlarm", metric=cw.Metric(namespace=NAMESPACE, metric_name="FreeCostEstimatedUsdDay", statistic="Maximum", period=Duration.days(1)), threshold=cost_usd,
                 evaluation_periods=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description=f"Free videos cost more than ${cost_usd:g} yesterday (estimate: free credits x cost per credit). docs/PLANS.md, Measurement. No action attached.")
        cw.Alarm(self, "FreeCreditsAlarm", metric=cw.Metric(namespace=NAMESPACE, metric_name="FreeCreditsSpent", statistic="Sum", period=Duration.days(1)), threshold=credits,
                 evaluation_periods=1, comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description=f"{credits} or more free credits were spent in a day across all accounts (the global free budget is reached or was raised). No action attached.")

        CfnOutput(self, "EntitlementsTableName", value=entitlements.table_name)
        CfnOutput(self, "FreeClaimsTableName", value=claims.table_name)
        CfnOutput(self, "PlansConfigParameter", value=param_name)
        self.entitlements, self.claims, self.plan_fn, self.gallery_fn, self.daily_fn, self.param_name = entitlements, claims, plan_fn, gallery_fn, daily_fn, param_name
