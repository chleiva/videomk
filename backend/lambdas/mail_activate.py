"""CloudFormation custom resource: make our SES receipt rule set the active one, only if that is safe.

SES has ONE active receipt rule set per region. Create/Update: if another set is active, fail (so CloudFormation rolls back and the message tells the owner what to do);
if none, or ours, activate ours. Delete: deactivate only when ours is still the active one (never switch off somebody else's).
"""
import logging

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)


def _active(ses) -> str:
    return (ses.describe_active_receipt_rule_set().get("Metadata") or {}).get("Name", "")


def on_event(event, _ctx=None, ses=None):
    ses = ses or boto3.client("ses")
    name = event["ResourceProperties"]["RuleSetName"]
    kind = event["RequestType"]
    if kind in ("Create", "Update"):
        current = _active(ses)
        if current and current != name:
            raise RuntimeError(f"Refusing to deploy: the receipt rule set '{current}' is already active in this region and only one can be. "
                               f"Not touching it. Merge the videomk rule into it by hand or deactivate it first (docs/EMAIL_FORWARDING.md).")
        ses.set_active_receipt_rule_set(RuleSetName=name)
        log.info("activated %s", name)
    elif kind == "Delete":
        if _active(ses) == name:
            ses.set_active_receipt_rule_set()
            log.info("deactivated %s", name)
        else:
            log.info("%s is not the active rule set: left alone", name)
    return {"PhysicalResourceId": name}
