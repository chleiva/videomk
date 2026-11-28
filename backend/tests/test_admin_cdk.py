"""The owner console's stack (backend/admin_stack.py; docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md section 3), read from the synthesized template: the sign-in pool, the
authorizer in front of EVERY route, least privilege function by function (the console can read numbers and flip two switches: no credits, plans, budgets or
customer records), the audit log's lock, the headers, the country allow-list, the alarms and where they notify."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

ACCOUNT, REGION = "123456789012", "eu-west-1"
MAIN = {"videos_table": "videomk-qa-VideosTable-AAA", "usage_table": "videomk-qa-UsageTable-BBB", "flags_table": "videomk-qa-AccountFlagsTable-CCC",
        "state_machine_arn": f"arn:aws:states:{REGION}:{ACCOUNT}:stateMachine:generate_video_workflow_v2", "customer_pool_id": "eu-west-1_CUSTOMER", "plans_param": "/videomk/qa/plans/config",
        "engine_functions": {"v2_plan": 4096, "v2_render_chunk": 10240}}
HOST = "d1234example.cloudfront.net"


@pytest.fixture(scope="module")
def build():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    from admin_stack import AdminStack
    cache = {}

    def make(stage="qa", host=HOST, **kw):
        key = (stage, host, tuple(sorted(kw.items())))
        if key not in cache:
            app = cdk.App(outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-admin-{len(cache)}"))
            stack = AdminStack(app, f"videomk-admin-{stage}", stage=stage, main=dict(MAIN), host=host, env=cdk.Environment(account=ACCOUNT, region=REGION), **kw)
            cache[key] = Template.from_stack(stack).to_json()
        return cache[key]
    return make


@pytest.fixture(scope="module")
def t(build):
    return build()


def of(t, kind):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == kind}


def one(t, kind):
    found = of(t, kind)
    assert len(found) == 1, (kind, list(found))
    return next(iter(found.values()))["Properties"]


def fn(t, suffix):
    return next((k, v) for k, v in of(t, "AWS::Lambda::Function").items() if v["Properties"].get("FunctionName") == f"videomk-admin-qa-{suffix}")


def statements(t, suffix):
    """Every IAM statement of that function's role, as (sorted actions, resource as JSON text, condition as JSON text)."""
    role = fn(t, suffix)[1]["Properties"]["Role"]["Fn::GetAtt"][0]
    assert t["Resources"][role]["Properties"]["ManagedPolicyArns"] == [{"Fn::Join": ["", ["arn:", {"Ref": "AWS::Partition"}, ":iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"]]}]   # its own logs, nothing else
    assert "Policies" not in t["Resources"][role]["Properties"]
    out = []
    for p in of(t, "AWS::IAM::Policy").values():
        if any(r.get("Ref") == role for r in p["Properties"].get("Roles", [])):
            for s in p["Properties"]["PolicyDocument"]["Statement"]:
                assert s["Effect"] == "Allow"
                out.append((sorted(s["Action"] if isinstance(s["Action"], list) else [s["Action"]]), json.dumps(s["Resource"], sort_keys=True), json.dumps(s.get("Condition", {}), sort_keys=True)))
    return out


def actions(t, suffix):
    return sorted({a for acts, _, _ in statements(t, suffix) for a in acts})


def table_arn(name):
    return f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{name}"


# ---------------------------------------------------------------- sign-in
def test_the_admin_pool_is_its_own_closed_pool_with_mfa_and_passkeys(t):
    p = one(t, "AWS::Cognito::UserPool")
    assert p["UserPoolName"] == "videomk-admin-qa" and p["UserPoolTier"] == "ESSENTIALS"
    assert p["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] is True                                   # no self sign-up
    assert p["MfaConfiguration"] == "ON" and p["EnabledMfas"] == ["SOFTWARE_TOKEN_MFA"]                     # MFA required; no SMS, no email codes
    assert p["Policies"]["SignInPolicy"]["AllowedFirstAuthFactors"] == ["PASSWORD", "WEB_AUTHN"]
    assert (p["WebAuthnRelyingPartyID"], p["WebAuthnUserVerification"], p["WebAuthnFactorConfiguration"]) == (HOST, "required", "MULTI_FACTOR_WITH_USER_VERIFICATION")
    assert p["AccountRecoverySetting"]["RecoveryMechanisms"] == [{"Name": "admin_only", "Priority": 1}]    # no "forgot password" by email
    assert p["Policies"]["PasswordPolicy"]["MinimumLength"] == 20 and p["Policies"]["PasswordPolicy"]["TemporaryPasswordValidityDays"] == 3
    assert "{####}" in p["AdminCreateUserConfig"]["InviteMessageTemplate"]["EmailMessage"] and "VideoMK" in p["AdminCreateUserConfig"]["InviteMessageTemplate"]["EmailSubject"]
    assert "DeviceConfiguration" not in p and "SmsConfiguration" not in p
    assert list(p["LambdaConfig"]) == ["PostAuthentication"]                                                # every sign-in is recorded and emailed
    assert of(t, "AWS::Cognito::UserPoolDomain") == {} and of(t, "AWS::Cognito::UserPoolIdentityProvider") == {}   # no hosted page, no Google or Apple
    assert of(t, "AWS::Cognito::UserPoolUser") == {}                                                        # the one user is created by hand, never by the template


def test_the_app_client_has_short_tokens_no_secret_and_no_oauth(t):
    cl = one(t, "AWS::Cognito::UserPoolClient")
    assert cl["GenerateSecret"] is False and sorted(cl["ExplicitAuthFlows"]) == ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_AUTH"]
    assert (cl["AccessTokenValidity"], cl["IdTokenValidity"], cl["RefreshTokenValidity"]) == (10, 10, 60)
    assert cl["TokenValidityUnits"] == {"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "minutes"}
    assert cl["EnableTokenRevocation"] is True and cl["PreventUserExistenceErrors"] == "ENABLED"
    assert not cl.get("AllowedOAuthFlows") and not cl.get("CallbackURLs") and cl.get("AllowedOAuthFlowsUserPoolClient") in (None, False)


def test_passkeys_wait_for_the_address_on_the_first_deploy(build):
    p = one(build(host=None), "AWS::Cognito::UserPool")
    assert p["Policies"]["SignInPolicy"]["AllowedFirstAuthFactors"] == ["PASSWORD"] and "WebAuthnRelyingPartyID" not in p and p["MfaConfiguration"] == "ON"


# ---------------------------------------------------------------- the API: the token is checked before any code runs
def test_every_route_requires_a_token_of_the_admin_pool(t):
    pool_id = next(iter(of(t, "AWS::Cognito::UserPool")))
    client_id = next(iter(of(t, "AWS::Cognito::UserPoolClient")))
    auth_id = next(iter(of(t, "AWS::ApiGatewayV2::Authorizer")))
    a = one(t, "AWS::ApiGatewayV2::Authorizer")
    assert a["AuthorizerType"] == "JWT" and a["IdentitySource"] == ["$request.header.Authorization"]
    assert a["JwtConfiguration"]["Audience"] == [{"Ref": client_id}]                                        # this app client only
    assert a["JwtConfiguration"]["Issuer"] == {"Fn::Join": ["", [f"https://cognito-idp.{REGION}.amazonaws.com/", {"Ref": pool_id}]]}   # the ADMIN pool: a customer's token has another issuer and is refused
    assert MAIN["customer_pool_id"] not in json.dumps(a)
    routes = of(t, "AWS::ApiGatewayV2::Route")
    assert sorted(r["Properties"]["RouteKey"] for r in routes.values()) == ["GET /api/home", "POST /api/switches"]   # no $default, no public route, no OPTIONS
    for r in routes.values():
        assert r["Properties"]["AuthorizationType"] == "JWT" and r["Properties"]["AuthorizerId"] == {"Ref": auth_id}
    api = one(t, "AWS::ApiGatewayV2::Api")
    assert "CorsConfiguration" not in api                                                                   # no other site may call it from a browser
    assert one(t, "AWS::ApiGatewayV2::Stage")["DefaultRouteSettings"] == {"ThrottlingBurstLimit": 10, "ThrottlingRateLimit": 5}
    for p in of(t, "AWS::Lambda::Permission").values():                                                     # only API Gateway, EventBridge and Cognito may invoke the functions
        assert p["Properties"]["Principal"] in ("apigateway.amazonaws.com", "events.amazonaws.com", "cognito-idp.amazonaws.com")
    assert of(t, "AWS::Lambda::Url") == {}


# ---------------------------------------------------------------- least privilege
def test_the_act_function_can_flip_the_two_switches_and_nothing_else(t):
    import admin_stack
    flags = json.dumps(table_arn(MAIN["flags_table"]))
    st = statements(t, "act")
    assert actions(t, "act") == ["dynamodb:GetItem", "dynamodb:UpdateItem", "s3:PutObject", "sns:Publish"]
    ddb = [s for s in st if s[0][0].startswith("dynamodb:")]
    assert all(res == flags for _, res, _ in ddb)                                                           # the flags table only: no wallet, entitlements, usage, videos, claims
    for acts, _, cond in ddb:
        assert json.loads(cond)["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"] == ["ops:switches"]   # ONE item: not the unlimited flag, not a safety hold, not storage
    upd = json.loads(next(cond for acts, _, cond in ddb if acts == ["dynamodb:UpdateItem"]))
    assert upd["ForAllValues:StringEquals"]["dynamodb:Attributes"] == admin_stack.SWITCH_FIELDS == ["user_id", "stop_new_videos", "stop_free_videos", "stop_dictation", "updated_at", "updated_by"]
    put = next(res for acts, res, _ in st if acts == ["s3:PutObject"])
    assert "audit/*" in put and next(iter(k for k in of(t, "AWS::S3::Bucket") if k.startswith("Audit"))) in put
    env = fn(t, "act")[1]["Properties"]["Environment"]["Variables"]
    assert set(env) == {"STAGE", "ALERT_TOPIC_ARN", "AUDIT_BUCKET", "AWS_CLI_PROFILE", "FLAGS_TABLE", "ADMIN_POOL_ID"}   # it does not even know the other tables' names


def test_the_read_function_reads_counts_and_writes_nothing(t):
    st = statements(t, "read")
    assert actions(t, "read") == ["cloudwatch:DescribeAlarms", "dynamodb:GetItem", "dynamodb:Query", "ssm:GetParameter", "states:ListExecutions"]
    rollups = next(k for k in of(t, "AWS::DynamoDB::Table"))
    by_res = {}
    for acts, res, cond in st:
        by_res.setdefault(res, []).append((acts, json.loads(cond)))
    assert by_res[json.dumps(table_arn(MAIN["flags_table"]))] == [(["dynamodb:GetItem"], {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["ops:switches"]}})]
    assert by_res[json.dumps(table_arn(MAIN["usage_table"]))] == [(["dynamodb:GetItem"], {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["fbudget"]}})]
    assert MAIN["videos_table"] not in json.dumps(st) and "cognito" not in json.dumps(st)                  # no video record, no account, no email address
    assert any(rollups in res and acts == ["dynamodb:GetItem", "dynamodb:Query"] for acts, res, _ in st)
    assert json.dumps(f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/videomk/qa/plans/config") in by_res


def test_the_rollup_job_reads_small_fields_and_writes_only_its_own_table(t):
    import admin_stack
    import backend_stack
    st = statements(t, "rollup")
    assert actions(t, "rollup") == ["cloudwatch:GetMetricData", "cognito-idp:ListUsers", "dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:Scan",
                                    "sns:Publish", "ssm:GetParameter", "states:GetExecutionHistory", "states:ListExecutions"]
    videos = table_arn(MAIN["videos_table"])
    q = [s for s in st if videos in s[1]]
    assert sorted(a for acts, _, _ in q for a in acts) == ["dynamodb:Query", "dynamodb:Scan"]              # never GetItem on a video, never a write
    query = next(s for s in q if s[0] == ["dynamodb:Query"])
    assert json.loads(query[1]) == f"{videos}/index/GSI_UsageDay"                                           # the day index only (not the table, not the per-user index)
    scan = json.loads(next(s for s in q if s[0] == ["dynamodb:Scan"])[2])
    assert scan["StringEquals"] == {"dynamodb:Select": "SPECIFIC_ATTRIBUTES"} and scan["ForAllValues:StringEquals"]["dynamodb:Attributes"] == admin_stack.VIDEO_FIELDS
    assert set(admin_stack.VIDEO_FIELDS) == {"video_id", "usage_day", "created_at"} | set(backend_stack.USAGE_DAY_FIELDS) and admin_stack.USAGE_DAY_INDEX == backend_stack.USAGE_DAY_INDEX
    sys.path.insert(0, os.path.join(ROOT, "admin_console", "lambdas"))
    import admin_rollup
    assert list(admin_rollup.FIELDS) == admin_stack.VIDEO_FIELDS and admin_rollup.INDEX == admin_stack.USAGE_DAY_INDEX
    for private in ("prompt", "request_json", "title", "youtube_description", "charge", "video_uri"):
        assert private not in admin_stack.VIDEO_FIELDS
    writes = [s for s in st if set(s[0]) & {"dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem"}]
    rollups = next(k for k in of(t, "AWS::DynamoDB::Table"))
    assert len(writes) == 1 and rollups in writes[0][1] and "videomk-qa-" not in writes[0][1]               # it writes its own table and no table of the main stack
    usage = next(s for s in st if table_arn(MAIN["usage_table"]) in s[1])
    assert usage[0] == ["dynamodb:GetItem"] and json.loads(usage[2]) == {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["fbudget"]}}
    assert MAIN["flags_table"] not in json.dumps(st)


def test_the_sign_in_hook_can_only_record_and_notify(t):
    assert actions(t, "signin") == ["s3:PutObject", "sns:Publish"]


FORBIDDEN = ("ssm:PutParameter", "ssm:DeleteParameter", "dynamodb:BatchWriteItem", "dynamodb:*", "s3:GetObject", "s3:DeleteObject", "s3:*", "iam:", "lambda:", "cognito-idp:Admin", "secretsmanager:",
             "states:StartExecution", "states:StopExecution", "states:DescribeExecution", "kms:", "sts:", "bedrock:", "ses:", "*")


def test_nothing_in_the_console_can_touch_credits_plans_budgets_or_customer_data(t):
    all_statements = [s for name in ("act", "read", "rollup", "signin") for s in statements(t, name)]
    for acts, res, _ in all_statements:
        for a in acts:
            assert not any(a == bad or (bad.endswith(":") and a.startswith(bad)) or (bad.endswith("Admin") and a.startswith(bad)) for bad in FORBIDDEN), a
            assert "*" not in a                                                                             # no wildcard action anywhere
    text = json.dumps(t["Resources"])
    for word in ("Wallet", "Entitlements", "FreeClaims", "WALLET_TABLE", "ENTITLEMENTS_TABLE", "plans/config\"]]}, \"Action\": \"ssm:Put"):
        assert word not in text
    # the plans parameter (the free budget and every plan knob) is readable by two functions and writable by none
    param = f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/videomk/qa/plans/config"
    assert sorted(acts[0] for acts, res, _ in all_statements if param in res) == ["ssm:GetParameter", "ssm:GetParameter"]
    # the only writes to the main stack's tables: the act function's one item
    main_writes = [(acts, res) for acts, res, _ in all_statements if "videomk-qa-" in res and set(acts) & {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"}]
    assert main_writes == [(["dynamodb:UpdateItem"], json.dumps(table_arn(MAIN["flags_table"])))]
    assert {v["Properties"]["FunctionName"] for v in of(t, "AWS::Lambda::Function").values() if "FunctionName" in v["Properties"]} == {f"videomk-admin-qa-{n}" for n in ("act", "read", "rollup", "signin")}


def test_the_stack_adds_nothing_to_the_main_stack(t):
    text = json.dumps(t)
    assert "Fn::ImportValue" not in text                                                                    # names only: nothing is exported from, or coupled to, the main stack
    assert len(t["Resources"]) < 80


# ---------------------------------------------------------------- the audit log
def test_the_audit_log_is_locked_for_400_days(t):
    audit = next(v for k, v in of(t, "AWS::S3::Bucket").items() if k.startswith("Audit"))
    p = audit["Properties"]
    assert p["ObjectLockEnabled"] is True and p["ObjectLockConfiguration"] == {"ObjectLockEnabled": "Enabled", "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 400}}}
    assert p["VersioningConfiguration"] == {"Status": "Enabled"} and audit["DeletionPolicy"] == "Retain" and audit["UpdateReplacePolicy"] == "Retain"
    assert p["PublicAccessBlockConfiguration"] == {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
    assert min(r["ExpirationInDays"] for r in p["LifecycleConfiguration"]["Rules"]) > 400                   # nothing is removed before its lock ends


# ---------------------------------------------------------------- the page
def test_the_page_is_private_with_a_strict_content_security_policy(t):
    import admin_stack
    h = one(t, "AWS::CloudFront::ResponseHeadersPolicy")["ResponseHeadersPolicyConfig"]
    sec = h["SecurityHeadersConfig"]
    csp = sec["ContentSecurityPolicy"]["ContentSecurityPolicy"]
    assert csp == admin_stack.csp(REGION) == ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://cognito-idp.eu-west-1.amazonaws.com; "
                                              "manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'")
    assert "unsafe" not in csp and "*" not in csp and sec["ContentSecurityPolicy"]["Override"] is True
    assert sec["StrictTransportSecurity"]["AccessControlMaxAgeSec"] >= 31536000 and sec["FrameOptions"]["FrameOption"] == "DENY" and sec["ReferrerPolicy"]["ReferrerPolicy"] == "no-referrer"
    assert sec["ContentTypeOptions"]["Override"] is True
    custom = {x["Header"]: x["Value"] for x in h["CustomHeadersConfig"]["Items"]}
    assert custom["X-Robots-Tag"].startswith("noindex") and "publickey-credentials-get=(self)" in custom["Permissions-Policy"] and custom["Cross-Origin-Opener-Policy"] == "same-origin"
    d = one(t, "AWS::CloudFront::Distribution")["DistributionConfig"]
    policy = {"Ref": next(iter(of(t, "AWS::CloudFront::ResponseHeadersPolicy")))}
    assert d["DefaultCacheBehavior"]["ResponseHeadersPolicyId"] == policy and d["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "https-only"
    assert [b["PathPattern"] for b in d["CacheBehaviors"]] == ["/api/*"] and d["CacheBehaviors"][0]["ResponseHeadersPolicyId"] == policy and d["CacheBehaviors"][0]["ViewerProtocolPolicy"] == "https-only"
    assert "CustomErrorResponses" not in d                                                                  # a refusal from the API is never turned into a page
    site = next(v for k, v in of(t, "AWS::S3::Bucket").items() if k.startswith("Site"))
    assert site["Properties"]["PublicAccessBlockConfiguration"]["RestrictPublicBuckets"] is True and "WebsiteConfiguration" not in site["Properties"]
    assert len(of(t, "AWS::CloudFront::OriginAccessControl")) == 1


def test_the_console_is_served_to_the_allowed_countries_only_and_the_list_is_a_stack_parameter(t):
    assert t["Parameters"]["AllowedCountries"]["Type"] == "CommaDelimitedList" and t["Parameters"]["AllowedCountries"]["Default"] == "GB,ES"
    d = one(t, "AWS::CloudFront::Distribution")["DistributionConfig"]
    assert d["Restrictions"]["GeoRestriction"] == {"RestrictionType": "whitelist", "Locations": {"Ref": "AllowedCountries"}}


# ---------------------------------------------------------------- alerts
def test_the_alarms_exist_and_notify_the_owner(t):
    topic = next(iter(of(t, "AWS::SNS::Topic")))
    sub = one(t, "AWS::SNS::Subscription")
    assert sub["Protocol"] == "email" and sub["Endpoint"] == "hello@videomk.com" and sub["TopicArn"] == {"Ref": topic}
    alarms = {a["Properties"]["AlarmName"]: a["Properties"] for a in of(t, "AWS::CloudWatch::Alarm").values()}
    assert set(alarms) == {"videomk-admin-qa-rollup-stopped", "videomk-admin-qa-rollup-errors", "videomk-admin-qa-console-errors"}
    for a in alarms.values():
        assert a["AlarmActions"] == [{"Ref": topic}]
    stopped = alarms["videomk-admin-qa-rollup-stopped"]
    assert (stopped["Namespace"], stopped["MetricName"], stopped["Period"], stopped["EvaluationPeriods"], stopped["TreatMissingData"], stopped["ComparisonOperator"], stopped["Threshold"]) == \
        ("videomk/Admin", "RollupHeartbeat", 3600, 2, "breaching", "LessThanThreshold", 1)                 # two hours without a finished run
    assert stopped["Dimensions"] == [{"Name": "Stage", "Value": "qa"}] and stopped["OKActions"] == [{"Ref": topic}]
    rules = [r["Properties"] for r in of(t, "AWS::Events::Rule").values()]
    hourly = next(r for r in rules if "ScheduleExpression" in r)
    assert hourly["ScheduleExpression"] == "rate(1 hour)" and hourly["Targets"][0]["Arn"] == {"Fn::GetAtt": [fn(t, "rollup")[0], "Arn"]}
    # the main stack's alarms (which have no action of their own) are forwarded to the same topic, without touching the main stack; other projects' alarms are not
    fwd = next(r for r in rules if "EventPattern" in r)
    assert fwd["EventPattern"]["source"] == ["aws.cloudwatch"] and fwd["EventPattern"]["detail-type"] == ["CloudWatch Alarm State Change"]
    assert fwd["EventPattern"]["detail"]["alarmName"] == [{"prefix": "videomk-qa-"}] and fwd["EventPattern"]["detail"]["state"] == {"value": ["ALARM", "OK"]}
    assert fwd["Targets"][0]["Arn"] == {"Ref": topic}
    policy = json.dumps(one(t, "AWS::SNS::TopicPolicy")["PolicyDocument"])
    assert "cloudwatch.amazonaws.com" in policy and "events.amazonaws.com" in policy and '"Principal": "*"' not in policy.replace('"Effect": "Deny", "Principal": "*"', "")


def test_production_keeps_its_data_and_leaves_test_accounts_out(build):
    prod = build(stage="prod")
    assert next(v for v in of(prod, "AWS::DynamoDB::Table").values())["DeletionPolicy"] == "Retain"
    assert one(prod, "AWS::Cognito::UserPool")["DeletionProtection"] == "ACTIVE"
    env = next(v for v in of(prod, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == "videomk-admin-prod-rollup")["Properties"]["Environment"]["Variables"]
    assert env["EXCLUDE_TEST_ACCOUNTS"] == "1" and fn(build(), "rollup")[1]["Properties"]["Environment"]["Variables"]["EXCLUDE_TEST_ACCOUNTS"] == "0"


def test_the_main_stack_names_come_from_the_deployed_launcher_and_a_missing_one_stops_the_synth():
    import aws_cdk as cdk
    import admin_stack

    class Lam:
        class exceptions:
            class ResourceNotFoundException(Exception):
                pass

        def get_function_configuration(self, FunctionName):
            if FunctionName == "VideoGenerationSFLauncher":
                return {"Environment": {"Variables": {"VIDEOS_TABLE": "V", "USAGE_TABLE": "U", "FLAGS_TABLE": "F", "STATE_MACHINE_ARN": "arn:sm", "USER_POOL_ID": "pool", "PLANS_CONFIG_PARAM": "/p", "OTHER": "x"}}}
            if FunctionName == "v2_audio":
                raise self.exceptions.ResourceNotFoundException()
            return {"MemorySize": 4096}

    got = admin_stack.main_stack_values(type("S", (), {"client": lambda self, name: Lam()})())
    assert got["videos_table"] == "V" and got["customer_pool_id"] == "pool" and got["engine_functions"]["v2_plan"] == 4096 and "v2_audio" not in got["engine_functions"]
    with pytest.raises(ValueError, match="flags_table"):
        admin_stack.AdminStack(cdk.App(), "x", stage="qa", main={**MAIN, "flags_table": ""}, env=cdk.Environment(account=ACCOUNT, region=REGION))
