"""Email forwarding for videomk.com: mail to hello@videomk.com arrives in one personal inbox (docs/EMAIL_FORWARDING.md).

Own stack `videomk-mail` (prod account, us-east-1: SES inbound is a regional service and the site's zone lives there). Switched on with `-c mail=1`.
SES receives -> raw message in a private S3 bucket (7 days) -> small Lambda rewrites the headers and sends it with SES to the destination.
Nothing here touches other SES usage of the account; the one active receipt rule set is taken only if no other set is active.
Context: -c forwardTo=<address> (default chris@agilegency.com)  -c forwardFrom=<address> (default hello@videomk.com)  -c mailZoneId=<hosted zone id>
         -c mailReservedConcurrency=<n> (off by default: an account with a low concurrency quota cannot reserve any, see the docs)
"""
import os
import re
from typing import Optional

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_cloudwatch as cw, aws_iam as iam, aws_lambda as lambda_, aws_logs as logs
from aws_cdk import aws_route53 as r53
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ses as ses
from aws_cdk import aws_ses_actions as actions
from aws_cdk import aws_sqs as sqs
from aws_cdk import CustomResource, custom_resources as cr
from constructs import Construct

PROD_ACCOUNT = "464863885161"
REGION = "us-east-1"
DOMAIN = "videomk.com"
ZONE_ID = "Z07620702J1XHOWB4O7NZ"
DEFAULT_TO = "chris@agilegency.com"
DEFAULT_FROM = "hello@videomk.com"
RULE_SET = "videomk-inbound"
RULE = "forward-hello"
KEY_PREFIX = "incoming/"
RETENTION_DAYS = 7
SPF = "v=spf1 include:amazonses.com ~all"
# p=none = monitor only. To tighten later (docs/EMAIL_FORWARDING.md): p=quarantine, then p=reject, once real mail has flowed for a few weeks.
DMARC = "v=DMARC1; p=none; adkim=r; aspf=r"
LAMBDAS = os.path.join(os.path.dirname(__file__), "lambdas")
_EMAIL = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")


def _ctx_email(node, key: str, default: str) -> str:
    v = str(node.try_get_context(key) or default).strip()
    if not _EMAIL.match(v):
        raise SystemExit(f"-c {key}={v!r} is not an email address")
    return v


def _code(*files: str) -> lambda_.Code:
    return lambda_.Code.from_asset(LAMBDAS, exclude=["*"] + [f"!{f}" for f in files])


class MailForwardStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, forward_to: str, forward_from: str, zone_id: str = ZONE_ID, reserved: Optional[int] = None, **kw) -> None:
        super().__init__(scope, cid, **kw)
        domain = forward_from.split("@")[1]
        zone = r53.PublicHostedZone.from_public_hosted_zone_attributes(self, "Zone", hosted_zone_id=zone_id, zone_name=domain)

        # Sending identity: EasyDKIM, the three DKIM CNAMEs are written into the existing zone by CDK.
        domain_identity = ses.EmailIdentity(self, "DomainIdentity", identity=ses.Identity.public_hosted_zone(zone))
        # The destination must be verified while the account is in the SES sandbox: creating this sends a verification mail the owner clicks once.
        dest_identity = ses.EmailIdentity(self, "DestinationIdentity", identity=ses.Identity.email(forward_to))

        # Receiving + authentication records at the apex.
        r53.MxRecord(self, "Mx", zone=zone, record_name=domain, values=[r53.MxRecordValue(priority=10, host_name=f"inbound-smtp.{REGION}.amazonaws.com")], ttl=Duration.minutes(5))
        r53.TxtRecord(self, "Spf", zone=zone, record_name=domain, values=[SPF], ttl=Duration.minutes(5))
        r53.TxtRecord(self, "Dmarc", zone=zone, record_name=f"_dmarc.{domain}", values=[DMARC], ttl=Duration.minutes(5))

        bucket = s3.Bucket(self, "Raw", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True,
                           removal_policy=RemovalPolicy.RETAIN, lifecycle_rules=[s3.LifecycleRule(id="expire-raw-mail", enabled=True, expiration=Duration.days(RETENTION_DAYS),
                                                                                             abort_incomplete_multipart_upload_after=Duration.days(1))])
        rule_arn = f"arn:aws:ses:{REGION}:{self.account}:receipt-rule-set/{RULE_SET}:receipt-rule/{RULE}"
        bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="AllowSesPutFromThisAccountAndRule", principals=[iam.ServicePrincipal("ses.amazonaws.com")], actions=["s3:PutObject"], resources=[bucket.arn_for_objects(f"{KEY_PREFIX}*")],
            conditions={"StringEquals": {"AWS:SourceAccount": self.account, "AWS:SourceArn": rule_arn}}))

        dlq = sqs.Queue(self, "Dlq", retention_period=Duration.days(14), enforce_ssl=True, encryption=sqs.QueueEncryption.SQS_MANAGED)
        fn = lambda_.Function(
            self, "Forwarder", function_name="videomk-mail-forwarder", runtime=lambda_.Runtime.PYTHON_3_12, handler="mail_forwarder.handler", code=_code("mail_forwarder.py"),
            memory_size=256, timeout=Duration.seconds(60), log_retention=logs.RetentionDays.ONE_MONTH, retry_attempts=2, dead_letter_queue=dlq,
            reserved_concurrent_executions=reserved,
            environment={"MAIL_BUCKET": bucket.bucket_name, "MAIL_KEY_PREFIX": KEY_PREFIX, "FORWARD_TO": forward_to, "FORWARD_FROM": forward_from})
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[bucket.arn_for_objects(f"{KEY_PREFIX}*")]))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ses:SendRawEmail"], resources=[domain_identity.email_identity_arn, dest_identity.email_identity_arn], conditions={"StringEquals": {"ses:FromAddress": forward_from}}))
        cw.Alarm(self, "DlqAlarm", metric=dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(5)), threshold=1, evaluation_periods=1,
                 comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD, treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                 alarm_description="A forwarded mail failed all retries (see the MAIL_FORWARD_FAILED log lines); the original is in the raw bucket for 7 days.")

        rules = ses.ReceiptRuleSet(self, "Rules", receipt_rule_set_name=RULE_SET, drop_spam=False)
        rule = rules.add_rule(
            "ForwardHello", receipt_rule_name=RULE, recipients=[forward_from], enabled=True, scan_enabled=True, tls_policy=ses.TlsPolicy.REQUIRE,
            actions=[actions.S3(bucket=bucket, object_key_prefix=KEY_PREFIX), actions.Lambda(function=fn, invocation_type=actions.LambdaInvocationType.EVENT)])

        # Make the set the active one (CloudFormation cannot): refuses over another active set, deactivates on delete only if still ours.
        activate_fn = lambda_.Function(
            self, "ActivateFn", runtime=lambda_.Runtime.PYTHON_3_12, handler="mail_activate.on_event", code=_code("mail_activate.py"), timeout=Duration.seconds(30), memory_size=128,
            log_retention=logs.RetentionDays.ONE_MONTH)
        activate_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ses:DescribeActiveReceiptRuleSet", "ses:SetActiveReceiptRuleSet"], resources=["*"]))  # these SES actions do not support resource-level permissions
        provider = cr.Provider(self, "ActivateProvider", on_event_handler=activate_fn, log_retention=logs.RetentionDays.ONE_MONTH)
        activation = CustomResource(self, "ActivateRuleSet", service_token=provider.service_token, properties={"RuleSetName": RULE_SET})
        activation.node.add_dependency(rules)
        activation.node.add_dependency(rule)
        activation.node.add_dependency(fn)

        CfnOutput(self, "ForwardFrom", value=forward_from)
        CfnOutput(self, "ForwardTo", value=forward_to)
        CfnOutput(self, "RawBucket", value=bucket.bucket_name)
        CfnOutput(self, "DeadLetterQueue", value=dlq.queue_url)
