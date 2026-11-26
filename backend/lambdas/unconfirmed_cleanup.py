"""Scheduled cleanup of abandoned Cognito sign-ups (docs/AUTH_SOCIAL.md, "Unconfirmed sign-ups").

A person who starts the hosted sign-up and never enters the code stays UNCONFIRMED with no password, so they can neither sign in, reset, nor sign up again
("User already exists"). They have never signed in, so they own no data. This function deletes pool users that are UNCONFIRMED and older than UNCONFIRMED_MAX_AGE_HOURS.

Safety rules (each has a test):
  * the list filter is only a hint: every user is re-read with AdminGetUser right before deletion and skipped unless still UNCONFIRMED (a person who confirmed meanwhile is kept);
  * federated users (EXTERNAL_PROVIDER, or any user with an `identities` attribute) are never touched;
  * per-run cap (MAX_DELETIONS_PER_RUN), with a log line when it is hit; the next run continues;
  * throttling is retried with backoff; any other error on one user is counted as skipped, the run goes on;
  * logs hold counts and a short hash of the pool id only: never an email address or a username.
The alarm-friendly line is `UNCONFIRMED_CLEANUP deleted=N skipped=M`.
"""
import hashlib
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

_idp = None
THROTTLE_CODES = ("TooManyRequestsException", "ThrottlingException", "Throttling", "RequestLimitExceeded")


def client():
    global _idp
    if _idp is None:
        _idp = boto3.client("cognito-idp")
    return _idp


def _sleep(s: float) -> None:
    time.sleep(s)


def _call(fn, **kw):
    """Call a Cognito API with exponential backoff and jitter on throttling."""
    for attempt in range(6):
        try:
            return fn(**kw)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in THROTTLE_CODES or attempt == 5:
                raise
            _sleep(min(8.0, 0.25 * 2 ** attempt) * (0.5 + random.random() / 2))


def _attrs(u: Dict[str, Any]) -> Dict[str, str]:
    return {a["Name"]: a.get("Value", "") for a in (u.get("Attributes") or [])}


def _short(pool: str) -> str:
    return hashlib.sha256(pool.encode()).hexdigest()[:8]


def handler(event: Optional[dict] = None, context: Any = None) -> Dict[str, int]:
    pool = os.environ["USER_POOL_ID"]
    max_hours = max(1, int(os.environ.get("UNCONFIRMED_MAX_AGE_HOURS") or 24))
    cap = max(1, int(os.environ.get("MAX_DELETIONS_PER_RUN") or 200))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    idp = client()
    deleted = skipped = 0
    capped = False
    token = None
    while not capped:
        kw: Dict[str, Any] = {"UserPoolId": pool, "Filter": 'cognito:user_status = "UNCONFIRMED"', "Limit": 60}
        if token:
            kw["PaginationToken"] = token
        page = _call(idp.list_users, **kw)
        for u in page.get("Users", []):
            created = u.get("UserCreateDate")
            if u.get("UserStatus") != "UNCONFIRMED" or "identities" in _attrs(u) or created is None or created > cutoff:
                continue   # not a candidate (recent users are simply not due yet, not counted as skipped)
            if deleted >= cap:
                capped = True
                break
            name = u["Username"]
            try:
                now = _call(idp.admin_get_user, UserPoolId=pool, Username=name)
                if now.get("UserStatus") != "UNCONFIRMED" or "identities" in _attrs({"Attributes": now.get("UserAttributes")}):
                    skipped += 1
                    continue
                _call(idp.admin_delete_user, UserPoolId=pool, Username=name)
                deleted += 1
            except ClientError as e:
                skipped += 1
                log.warning("unconfirmed cleanup: one user skipped (%s) pool=%s", e.response.get("Error", {}).get("Code"), _short(pool))
        token = page.get("PaginationToken")
        if not token:
            break
    if capped:
        log.warning("UNCONFIRMED_CLEANUP cap reached (%d deletions); the next run continues pool=%s", cap, _short(pool))
    log.info("UNCONFIRMED_CLEANUP deleted=%d skipped=%d", deleted, skipped)
    return {"deleted": deleted, "skipped": skipped}
