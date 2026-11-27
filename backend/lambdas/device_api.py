"""Device proof for the free allowance (docs/PLANS.md, "Abuse controls"; verification in common/device_proof.py). Only the mobile apps call this.

  POST /users/{user_id}/device/challenge   -> {"challenge": "<base64url, 32 bytes>", "expires_in": 300}        one use, 5 minutes, bound to the account
  POST /users/{user_id}/device/verify      -> {"verified": true, "valid_until": ISO, "free": {...}}             or 403 {"code": "device_not_verified"}
      iOS      {"platform": "ios", "challenge": c, "key_id": "<base64 of the App Attest key id>", "attestation": "<base64>"}     the first time for a key
               {"platform": "ios", "challenge": c, "key_id": k, "assertion": "<base64>"}                                          afterwards
               optional with either: "device_check_token": "<base64 from DCDevice.generateToken>" (used only when the knob device_check_ios is on)
               The app passes SHA-256(challenge text, UTF-8) as clientDataHash to attestKey / generateAssertion.
      Android  {"platform": "android", "challenge": c, "integrity_token": "<Play Integrity standard token, requestHash = c>"}    (knob device_proof_android, off)

A verified proof gives the account a short pass (knob device_pass_minutes) during which the wallet may grant and the launcher may spend free credits, and it is the
moment the free allowance is tried (the eligibility step of common/free_grants.py runs here with the proof in hand). What is kept: in the account's own wallet rows the
app key (public key and counter, removed with the account), and for the allowance claim a salted hash of the key id, nothing else. A refusal never says which check failed.
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from common import device_proof as dp, free_grants, i18n, plans, wallet
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()
logger.setLevel(logging.INFO)
CHALLENGE_SECONDS = 300
CHALLENGES_PER_DAY = 200
_HEADERS = {"Access-Control-Allow-Methods": "POST,OPTIONS", "Cache-Control": "no-store"}
_secrets: Dict[str, Any] = {}


def _secret(env: str) -> Optional[Dict[str, Any]]:
    name = os.environ.get(env)
    if not name:
        return None
    if name not in _secrets:
        _secrets[name] = json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=name)["SecretString"])
    return _secrets[name]


def app_ids() -> list:
    return [x.strip() for x in os.environ.get("APP_ATTEST_APP_IDS", "39ANXJNUTL.com.videomk.app").split(",") if x.strip()]


def new_challenge(user: str, now: float) -> Dict[str, Any]:
    from common import usage
    usage.consume(f"devch:{user}", limit=CHALLENGES_PER_DAY)
    c = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    free_grants.usage_table().put_item(Item={"user_id": f"devch:{user}", "day": f"c#{c}", "until": int(now) + CHALLENGE_SECONDS, "ttl": int(now) + CHALLENGE_SECONDS + 3600})
    return {"challenge": c, "expires_in": CHALLENGE_SECONDS}


def use_challenge(user: str, challenge: Any, now: float) -> str:
    if not isinstance(challenge, str) or not 20 <= len(challenge) <= 64:
        raise dp.ProofError("challenge")
    try:
        free_grants.usage_table().delete_item(Key={"user_id": f"devch:{user}", "day": f"c#{challenge}"}, ConditionExpression="attribute_exists(user_id) AND #u > :now",
                                              ExpressionAttributeNames={"#u": "until"}, ExpressionAttributeValues={":now": int(now)})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise dp.ProofError("challenge") from None
        raise
    return challenge


def _ios(user: str, body: Dict[str, Any], challenge: str, cfg: Dict[str, Any], now: float) -> Dict[str, Any]:
    if not cfg["device_proof_ios"]:
        raise dp.ProofError("ios_off")
    key_id = dp.b64d(body.get("key_id"))
    sk = f"DEV#{hashlib.sha256(key_id).hexdigest()[:40]}"
    t = wallet._table()
    if body.get("attestation") is not None:
        got = dp.verify_attestation(dp.b64d(body["attestation"]), key_id, challenge.encode(), app_ids(), allow_development=os.environ.get("APP_ATTEST_ALLOW_DEVELOPMENT") == "1", now=now)
        t.put_item(Item={"user_id": user, "sk": sk, "platform": "ios", "public_key": got["public_key_pem"], "counter": 0, "environment": got["environment"], "created_at": int(now)})
    else:
        item = t.get_item(Key={"user_id": user, "sk": sk}, ConsistentRead=True).get("Item")
        if not item:
            raise dp.ProofError("unknown_key")
        counter = dp.verify_assertion(dp.b64d(body.get("assertion")), challenge.encode(), str(item["public_key"]), int(item.get("counter") or 0), app_ids())
        try:
            t.update_item(Key={"user_id": user, "sk": sk}, UpdateExpression="SET #c = :n", ConditionExpression="#c < :n", ExpressionAttributeNames={"#c": "counter"}, ExpressionAttributeValues={":n": counter})
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise dp.ProofError("counter") from None   # the same assertion twice
            raise
    out: Dict[str, Any] = {"device_ref": free_grants.mac("device", "ios:" + hashlib.sha256(key_id).hexdigest()), "claimed": False}
    if cfg["device_check_ios"]:   # needs the owner's DeviceCheck key; a device whose bit is set already used a free allowance, whatever account or reinstall
        creds = _secret("DEVICECHECK_SECRET")
        token = body.get("device_check_token")
        if not creds or not isinstance(token, str) or not token:
            raise dp.ProofError("device_check_missing")
        out["claimed"] = dp.devicecheck_bits(token, creds, now=now)["bit0"]
        out["mark"] = lambda: dp.devicecheck_set(token, creds)
    return out


def _android(user: str, body: Dict[str, Any], challenge: str, cfg: Dict[str, Any], now: float) -> Dict[str, Any]:
    if not cfg["device_proof_android"]:
        raise dp.ProofError("android_off")
    sa, token, package = _secret("PLAY_INTEGRITY_SECRET"), body.get("integrity_token"), os.environ.get("ANDROID_PACKAGE", "com.videomk.app")
    if not sa or not isinstance(token, str) or not 50 <= len(token) <= 20000:
        raise dp.ProofError("integrity_missing")
    verdict = dp.check_play_verdict(dp.play_decode(token, package, sa, now=now), package, challenge, now=now)
    return {"device_ref": None, "claimed": verdict["device_claimed"], "mark": lambda: dp.play_recall_write(token, package, sa)}


def verify(user: str, body: Dict[str, Any], event: Dict[str, Any], now: float) -> Dict[str, Any]:
    cfg = plans.config()
    challenge = use_challenge(user, body.get("challenge"), now)
    platform = body.get("platform")
    if platform not in ("ios", "android"):
        raise dp.ProofError("platform")
    proof = _ios(user, body, challenge, cfg, now) if platform == "ios" else _android(user, body, challenge, cfg, now)
    until = int(now) + int(cfg["device_pass_minutes"]) * 60
    ctx = {**free_grants.context(event), "platform": platform}   # a verified proof IS the mobile app, whatever the header says
    wallet._ensure_grants_plans(user, now=now, tz=None, ctx=None, ent=None)   # the wallet row exists (no free grant without a context)
    sets, vals = ["device_pass_until = :u", "device_platform = :p"], {":u": until, ":p": platform}
    if proof["device_ref"]:
        sets.append("device_ref = :r")
        vals[":r"] = proof["device_ref"]
    if proof["claimed"]:
        sets.append("device_claimed = :t")
        vals[":t"] = True
    wallet._table().update_item(Key={"user_id": user, "sk": "META"}, UpdateExpression="SET " + ", ".join(sets), ConditionExpression="attribute_exists(user_id)", ExpressionAttributeValues=vals)
    before = wallet._table().get_item(Key={"user_id": user, "sk": "META"}, ConsistentRead=True).get("Item") or {}
    body_out = wallet._balance_plans(user, now=now, tz=None, ctx=ctx)   # the eligibility step and, if it passes, the welcome grant
    after = wallet._table().get_item(Key={"user_id": user, "sk": "META"}, ConsistentRead=True).get("Item") or {}
    if before.get("welcome_state") == "pending" and after.get("welcome_state") == "granted" and proof.get("mark"):
        try:
            proof["mark"]()   # remember on Apple's / Google's side that this DEVICE has had its allowance
        except Exception:   # noqa: BLE001
            logger.exception("DEVICE_MARK_FAILED")
    return {"verified": True, "valid_until": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(until)), "free_creation": body_out["free_creation"], "free": body_out["free"]}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)}, _HEADERS)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)}, _HEADERS)
    if not plans.enabled():
        return json_response(404, {"message": i18n.t("err.not_found", loc)}, _HEADERS)
    resource, now = str(event.get("resource") or ""), time.time()
    try:
        if resource.endswith("/device/challenge"):
            return json_response(200, new_challenge(user, now), _HEADERS)
        raw = event.get("body") or "{}"
        if len(raw) > 60000:
            raise dp.ProofError("too_large")
        try:
            body = json.loads(raw)
        except ValueError:
            raise dp.ProofError("encoding") from None
        if not isinstance(body, dict):
            raise dp.ProofError("encoding")
        out = verify(user, body, event, now)
        logger.info("DEVICE_PROOF result=verified platform=%s user=%s", body.get("platform"), user)
        free_grants.emit("DeviceProofVerified", Platform=str(body.get("platform")))
        out["free"]["message"] = i18n.t(f"plan.free.{out['free']['reason']}", loc) if out["free"]["reason"] else None
        return json_response(200, out, _HEADERS)
    except dp.ProofError as e:
        logger.warning("DEVICE_PROOF result=refused reason=%s user=%s", e.reason, user)
        free_grants.emit("DeviceProofRefused", Reason=e.reason)
        free_grants.stat(f"device_refused_{e.reason}", now)
        return json_response(403, {"code": "device_not_verified", "message": i18n.t("plan.device_unverified", loc)}, _HEADERS)
    except Exception as e:   # noqa: BLE001
        from common import usage
        if isinstance(e, usage.QuotaExceeded):
            return json_response(429, {"code": "rate_limited", "message": i18n.t("err.busy", loc)}, {**_HEADERS, "Retry-After": "3600"})
        logger.exception("DEVICE_PROOF_FAILED")
        return json_response(500, {"message": i18n.t("err.generic", loc)}, _HEADERS)
