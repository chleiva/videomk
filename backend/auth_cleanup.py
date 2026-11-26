"""Scheduled cleanup of abandoned (UNCONFIRMED) sign-ups (docs/AUTH_SOCIAL.md, "Unconfirmed sign-ups").

On by default, it is safe; `-c unconfirmedCleanup=0` removes it. `-c unconfirmedMaxAgeHours=N` (default 24, minimum 1) sets the age.
Least privilege: ListUsers, AdminGetUser (the re-check right before deleting) and AdminDeleteUser on this one pool; nothing else.
"""
from aws_cdk import Duration, aws_events as events, aws_events_targets as targets, aws_iam as iam
from constructs import Construct

DEFAULT_MAX_AGE_HOURS = 24
MAX_DELETIONS_PER_RUN = 200


def enabled(node) -> bool:
    v = node.try_get_context("unconfirmedCleanup")
    return True if v is None else str(v).strip().lower() not in ("0", "false", "no", "off")


def max_age_hours(node) -> int:
    v = node.try_get_context("unconfirmedMaxAgeHours")
    return max(1, int(v)) if v not in (None, "") else DEFAULT_MAX_AGE_HOURS


class UnconfirmedCleanup(Construct):
    def __init__(self, scope: Construct, cid: str, *, user_pool, make_fn, max_age_hours: int = DEFAULT_MAX_AGE_HOURS, every_hours: int = 6) -> None:
        super().__init__(scope, cid)
        self.fn = make_fn(
            "UnconfirmedCleanupFunction", "unconfirmed_cleanup", "unconfirmed_cleanup.handler", timeout=Duration.minutes(5),
            env={"USER_POOL_ID": user_pool.user_pool_id, "UNCONFIRMED_MAX_AGE_HOURS": str(max_age_hours), "MAX_DELETIONS_PER_RUN": str(MAX_DELETIONS_PER_RUN)})
        self.fn.add_to_role_policy(iam.PolicyStatement(
            actions=["cognito-idp:ListUsers", "cognito-idp:AdminGetUser", "cognito-idp:AdminDeleteUser"], resources=[user_pool.user_pool_arn]))
        self.rule = events.Rule(self, "Schedule", schedule=events.Schedule.rate(Duration.hours(every_hours)), targets=[targets.LambdaFunction(self.fn, retry_attempts=1)])
