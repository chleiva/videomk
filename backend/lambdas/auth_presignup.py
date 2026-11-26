"""Cognito pre sign-up trigger: one person, one account (docs/AUTH_SOCIAL.md).

For a federated sign-up (Google, Sign in with Apple) whose provider email is VERIFIED, link the federated identity to the pool user that already
has that email (AdminLinkProviderForUser), so the token's `sub` stays the existing one and no second welcome credit is granted (credits are keyed by `sub`).
Anything else is let through: the federated user is created, auto-confirmed.

Security rules (each has a test):
  * never link on an unverified provider email (that would let anyone take over an account by claiming its email at a lax provider);
  * only link INTO a native user that is CONFIRMED with a verified email (an unconfirmed squatter account must never receive the real owner's identity);
  * fail closed: an unexpected error raises, so sign-in fails and the client retries, rather than silently creating a duplicate account;
  * logs carry a short hash of the email and its provider, never the address.
"""
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

APPLE_RELAY_DOMAIN = "privaterelay.appleid.com"
# Cognito provider names (the same names the identity providers have in the pool).
PROVIDERS = ("Google", "SignInWithApple")
_idp = None


def client():
    global _idp
    if _idp is None:
        _idp = boto3.client("cognito-idp")
    return _idp


def _h(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:10]


def _is_true(v: Any) -> bool:
    return v is True or str(v).strip().lower() == "true"


def split_username(user_name: str) -> Optional[Tuple[str, str]]:
    """'Google_1234' -> ('Google', '1234'); 'SignInWithApple_001.abc.0042' -> ('SignInWithApple', '001.abc.0042')."""
    for p in PROVIDERS:
        if user_name.startswith(p + "_") and len(user_name) > len(p) + 1:
            return p, user_name[len(p) + 1:]
    return None


def provider_email_verified(provider: str, attrs: Dict[str, Any]) -> bool:
    """Google states it in `email_verified`; a missing or false value is NOT verified. Apple only returns emails it has verified
    (a real address or a private relay one), and Cognito does not always surface a flag for it, so an Apple email counts as verified unless the flag says false."""
    flag = attrs.get("email_verified")
    if provider == "SignInWithApple":
        return flag is None or _is_true(flag)
    return _is_true(flag)


def _attr(user: Dict[str, Any], name: str) -> Optional[str]:
    for a in user.get("Attributes") or user.get("UserAttributes") or []:
        if a.get("Name") == name:
            return a.get("Value")
    return None


def find_by_email(pool_id: str, email: str) -> List[Dict[str, Any]]:
    """Every pool user with this email. Cognito's email filter is case sensitive, so the lowercase and the given spelling are both asked."""
    if '"' in email or "\\" in email:
        return []
    found: Dict[str, Dict[str, Any]] = {}
    for spelling in dict.fromkeys([email, email.lower()]):
        r = client().list_users(UserPoolId=pool_id, Filter=f'email = "{spelling}"', Limit=20)
        for u in r.get("Users", []):
            found[u["Username"]] = u
    return list(found.values())


def _linkable_native(u: Dict[str, Any]) -> bool:
    return u.get("UserStatus") == "CONFIRMED" and _is_true(_attr(u, "email_verified"))


def _link(pool_id: str, dest: Dict[str, str], provider: str, subject: str) -> bool:
    """True when linked or already linked; False when Cognito refuses this destination; raises on anything unexpected."""
    try:
        client().admin_link_provider_for_user(
            UserPoolId=pool_id, DestinationUser=dest,
            SourceUser={"ProviderName": provider, "ProviderAttributeName": "Cognito_Subject", "ProviderAttributeValue": subject})
        return True
    except ClientError as e:
        msg = e.response.get("Error", {}).get("Message", "").lower()
        if e.response.get("Error", {}).get("Code") == "InvalidParameterException":
            if "already linked" in msg or "already exists" in msg or "already found an entry" in msg:
                return True   # a concurrent sign-up of the same person linked it first: the goal is reached
            if "destination" in msg:
                return False
        raise


def handler(event, context=None):
    source = event.get("triggerSource", "")
    resp = event.setdefault("response", {})
    if source != "PreSignUp_ExternalProvider":
        return event   # native sign-up and admin-created users: untouched, the pool's own rules apply
    pool_id, user_name = event["userPoolId"], event.get("userName", "")
    attrs = (event.get("request") or {}).get("userAttributes") or {}
    parsed = split_username(user_name)
    if parsed is None:
        log.warning("presignup: unknown federated username shape, creating the user unlinked")
        resp["autoConfirmUser"] = True
        return event
    provider, subject = parsed
    email = (attrs.get("email") or "").strip()
    verified = bool(email) and provider_email_verified(provider, attrs)

    def create_unlinked(reason: str):
        log.info("presignup: provider=%s no link (%s)", provider, reason)
        resp["autoConfirmUser"] = True
        if verified:
            resp["autoVerifyEmail"] = True
        return event

    if not email:
        return create_unlinked("no email")
    if not verified:
        return create_unlinked("email not verified by provider")
    if email.lower().endswith("@" + APPLE_RELAY_DOMAIN):
        return create_unlinked("apple private relay address")   # the relay address is unique to this app: it can never match another account
    users = find_by_email(pool_id, email)
    natives = [u for u in users if u.get("UserStatus") != "EXTERNAL_PROVIDER"]
    federated = [u for u in users if u.get("UserStatus") == "EXTERNAL_PROVIDER" and u["Username"] != user_name]
    ok = [u for u in natives if _linkable_native(u)]
    if len(ok) == 1:
        if _link(pool_id, {"ProviderName": "Cognito", "ProviderAttributeValue": ok[0]["Username"]}, provider, subject):
            log.info("presignup: provider=%s linked to existing account email_hash=%s", provider, _h(email))
            return event
        return create_unlinked("link refused")
    if len(ok) > 1:
        log.error("presignup: provider=%s %d confirmed accounts share email_hash=%s, not guessing", provider, len(ok), _h(email))
        raise RuntimeError("ambiguous account for this email; contact support")
    if natives:
        return create_unlinked("existing account unconfirmed or email unverified")   # never hand an identity to an account whose email was not proven
    if len(federated) == 1:
        other = split_username(federated[0]["Username"])
        if other and _link(pool_id, {"ProviderName": other[0], "ProviderAttributeName": "Cognito_Subject", "ProviderAttributeValue": other[1]}, provider, subject):
            log.info("presignup: provider=%s linked to account first made with %s email_hash=%s", provider, other[0], _h(email))
            return event
        return create_unlinked("link to federated account refused")
    return create_unlinked("no existing account" if not federated else "several federated accounts")
