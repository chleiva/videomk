"""The watermark (docs/WATERMARK.md): GET/PUT/DELETE /users/{user}/watermark and PUT/DELETE /users/{user}/watermark/logo, the per-account saved settings and logo, and the rights the other
functions need to use them. The drawing itself is in the render (engine/watermark.py); nothing here is public.

On by default; `-c watermark=0` removes all of it (the launcher then ignores a `watermark` option and capabilities does not list it).
`-c forceWatermark=1` is the owner's policy switch (default OFF): every video of an account that is not premium carries the videomk mark and 'none' is not offered to it.
Premium (custom logo) comes from the admin-written flags table: `scripts/wallet_admin.py watermark <who> on`, or an active Pro library plan.
"""
from typing import Any, Callable, List, Optional

from aws_cdk import Duration, aws_apigateway as apigw, aws_iam as iam, aws_lambda as _lambda
from constructs import Construct


def enabled(node) -> bool:
    v = node.try_get_context("watermark")
    return True if v is None else str(v).strip().lower() not in ("0", "false", "no", "off")


def forced(node) -> bool:
    v = node.try_get_context("forceWatermark")
    return False if v is None else str(v).strip().lower() in ("1", "true", "yes", "on")


class WatermarkSettings(Construct):
    def __init__(self, scope: Construct, cid: str, *, make_fn: Callable[..., Any], engine_layer: _lambda.ILayerVersion, usage_table: Any, flags_table: Any, assets_bucket_name: str,
                 user_id_resource: apigw.IResource, cognito_auth: dict, cors_headers: List[str], launcher_fn: _lambda.Function, capabilities_fn: _lambda.Function,
                 plan_fn: Optional[_lambda.Function], force: bool) -> None:
        super().__init__(scope, cid)
        env = {"WATERMARK_ENABLED": "1", "FORCE_WATERMARK": "1" if force else "0"}
        objects = f"arn:aws:s3:::{assets_bucket_name}/watermark/*"
        api_fn = make_fn("WatermarkApiFunction", "watermark_api", "watermark_api.handler", timeout=Duration.seconds(15), memory=1024, env=env, layers=[engine_layer])   # Pillow + resvg: the logo is decoded and re-encoded here
        api_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[objects]))
        api_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:ListBucket"], resources=[f"arn:aws:s3:::{assets_bucket_name}"], conditions={"StringLike": {"s3:prefix": ["watermark/*"]}}))   # a missing logo answers 404, not 403
        flags_table.grant_read_data(api_fn)   # read only: nothing at runtime can grant itself premium
        usage_table.grant_read_write_data(api_fn)   # the daily logo-upload counter

        base = user_id_resource.add_resource("watermark")
        logo = base.add_resource("logo")
        for res, methods in ((base, ["GET", "PUT", "DELETE"]), (logo, ["PUT", "DELETE"])):
            for m in methods:
                res.add_method(m, apigw.LambdaIntegration(api_fn, proxy=True), **cognito_auth)
            res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=methods + ["OPTIONS"], allow_headers=cors_headers)

        # the launcher settles the video's watermark (saved default, entitlement, policy); capabilities lists what the account may use; the plan step copies a custom logo into the video's folder
        for fn in (launcher_fn, capabilities_fn):
            for k, v in env.items():
                fn.add_environment(k, v)
            flags_table.grant_read_data(fn)
        launcher_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[objects]))
        # (the launcher's ListBucket on watermark/* is part of its existing ListBucket statement in backend_stack.py: a second, separately conditioned statement made CDK drop another statement of that role)
        if plan_fn is not None:
            plan_fn.add_environment("FORCE_WATERMARK", env["FORCE_WATERMARK"])
            plan_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[objects]))
        self.api_fn = api_fn
