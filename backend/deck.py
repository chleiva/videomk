"""Deck to video infrastructure (docs/DECK_TO_VIDEO.md). Created ONLY with `-c deckToVideo=1` (default off: the stack is then exactly what it was).

* The converter: a container-image Lambda (arm64, LibreOffice + poppler, built from deck_converter/ at deploy time, needs Docker on the deploying machine) in a VPC whose
  subnets have NO route out (no internet gateway, no NAT): the only way anywhere is a gateway endpoint to S3, restricted by its policy to this bucket's deck folders. An
  untrusted deck is opened only here. Its role can read, write and delete under uploads/<user>/decks/ and nothing else; it has no model, table or secret access.
* The decks API (presigned upload, start processing, status) and the flag that tells the launcher, the planner and the capabilities endpoint the feature is on.
* Nothing new to delete or expire: decks live under uploads/<user>/decks/, which the two-day lifecycle rule, the account-deletion worker and its guard already cover.
"""
from typing import Any, Callable, Dict, Optional

from aws_cdk import CfnOutput, Duration, Size, aws_ec2 as ec2, aws_ecr_assets as ecr_assets, aws_iam as iam, aws_lambda as _lambda, aws_apigateway as apigw
from constructs import Construct


class DeckToVideo(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, make_fn: Callable[..., _lambda.Function], assets_bucket: str, usage_table: Any, plan_fn: _lambda.Function,
                 launcher_fn: _lambda.Function, capabilities_fn: Optional[_lambda.Function], user_resource: apigw.IResource, auth: Dict[str, Any], cors_headers: list,
                 memory_mb: int = 3008, concurrency: Optional[int] = None) -> None:
        super().__init__(scope, construct_id)
        decks_objects = f"arn:aws:s3:::{assets_bucket}/uploads/*/decks/*"
        uploads_objects = f"arn:aws:s3:::{assets_bucket}/uploads/*"

        vpc = ec2.Vpc(self, "DeckVpc", max_azs=2, nat_gateways=0,
                      subnet_configuration=[ec2.SubnetConfiguration(name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=26)])
        endpoint = vpc.add_gateway_endpoint("DeckS3", service=ec2.GatewayVpcEndpointAwsService.S3)
        endpoint.add_to_policy(iam.PolicyStatement(principals=[iam.AnyPrincipal()], actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[decks_objects]))
        sg = ec2.SecurityGroup(self, "DeckSg", vpc=vpc, description="deck converter: no inbound; the subnets have no route except the S3 gateway endpoint", allow_all_outbound=True)

        self.prep_fn = _lambda.DockerImageFunction(
            self, "DeckPrepFn", function_name="deck_prep",
            code=_lambda.DockerImageCode.from_image_asset("deck_converter", platform=ecr_assets.Platform.LINUX_ARM64, exclude=["__pycache__", "*.pyc"]),
            architecture=_lambda.Architecture.ARM_64, memory_size=memory_mb, ephemeral_storage_size=Size.gibibytes(4), timeout=Duration.minutes(8),
            vpc=vpc, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED), security_groups=[sg], allow_public_subnet=False,
            environment={"ASSETS_BUCKET": assets_bucket, "DECK_TMP": "/tmp"}, retry_attempts=0, max_event_age=Duration.minutes(5),
            reserved_concurrent_executions=concurrency,
        )
        self.prep_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], resources=[decks_objects]))

        decks_fn = make_fn("DecksApiFunction", "decks_api", "decks_api.handler", timeout=Duration.seconds(15), env={"DECKS_ENABLED": "1", "DECK_PREP_FN": self.prep_fn.function_name})
        decks_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:PutObject", "s3:GetObject"], resources=[decks_objects]))   # presigned POSTs are signed with this role; status files
        usage_table.grant_read_write_data(decks_fn)
        self.prep_fn.grant_invoke(decks_fn)

        plan_fn.add_environment("DECK_TO_VIDEO", "1")
        for fn in (launcher_fn, plan_fn) + ((capabilities_fn,) if capabilities_fn is not None else ()):
            fn.add_environment("DECKS_ENABLED", "1")
        launcher_fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[decks_objects]))   # the status file of the deck being used

        decks = user_resource.add_resource("decks")
        item = decks.add_resource("{deck_id}")
        process = item.add_resource("process")
        for res, methods in ((decks, ["POST", "OPTIONS"]), (item, ["GET", "OPTIONS"]), (process, ["POST", "OPTIONS"])):
            res.add_cors_preflight(allow_origins=apigw.Cors.ALL_ORIGINS, allow_methods=methods, allow_headers=cors_headers)
        integ = apigw.LambdaIntegration(decks_fn, proxy=True)
        decks.add_method("POST", integ, **auth)
        item.add_method("GET", integ, **auth)
        process.add_method("POST", integ, **auth)
        CfnOutput(self, "DeckPrepFunctionName", value=self.prep_fn.function_name)
