"""Sign in with Apple token revocation (docs/ACCOUNT_DELETION.md, section "Apple"). Only used when the deploy flag `appleRevoke` is on.

  1. the app opens `authorize_url(...)` (Apple's own page, Services ID, our callback as return URL, a signed `state` that names the account);
  2. Apple POSTs `code` + `state` to our callback; we exchange the code for tokens (`/auth/token`), check that the tokens belong to the Apple account linked to this person,
     and revoke the refresh token (`/auth/revoke`). The tokens live in memory for those two calls and are never stored or logged;
  3. both calls authenticate with `client_secret`, an ES256 JWT signed with the `.p8` key (Team ID as issuer, Key ID as `kid`, the Services ID as subject, valid 5 minutes).
Needs `cryptography` (layer apple_deps). Nothing here touches the network except `post_form`, which tests point at a local fake server.
"""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from common import deletion

logger = logging.getLogger()

APPLE = "https://appleid.apple.com"
STATE_SECONDS = 600


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def base_url() -> str:
    """Apple's host. Tests may point it at a loopback server; anything else in APPLE_BASE_URL is ignored."""
    override = os.environ.get("APPLE_BASE_URL", "")
    if override:
        host = urllib.parse.urlparse(override).hostname
        if host in ("127.0.0.1", "localhost"):
            return override.rstrip("/")
    return APPLE


def client_secret(team_id: str, key_id: str, client_id: str, pem: str, *, now: Optional[float] = None, ttl: int = 300) -> str:
    """The ES256 client-secret JWT. Never logged."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    now = int(time.time() if now is None else now)
    head = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    claims = {"iss": team_id, "iat": now, "exp": now + ttl, "aud": APPLE, "sub": client_id}
    signing_input = f"{b64(json.dumps(head, separators=(',', ':')).encode())}.{b64(json.dumps(claims, separators=(',', ':')).encode())}"
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("the Apple key is not a P-256 key")
    r, s = decode_dss_signature(key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({"response_type": "code", "response_mode": "form_post", "client_id": client_id, "redirect_uri": redirect_uri, "state": state})
    return f"{APPLE}/auth/authorize?{q}"   # always the real Apple host: this URL is for the person's browser


# ----------------------------------------------------------------------------- the state: who asked, which Apple account is expected, where to send the person back
def sign_state(user: str, apple_sub: str, back: str, *, now: Optional[float] = None) -> str:
    body = b64(json.dumps({"u": user, "a": apple_sub, "b": back, "e": int((time.time() if now is None else now) + STATE_SECONDS)}, separators=(",", ":")).encode())
    return f"{body}.{deletion.mac('apple-state', body)[:43]}"


def read_state(state: str, *, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The state's content, or None when it is not ours, was changed, or has expired."""
    import hmac as _h

    try:
        body, sig = state.split(".", 1)
        if not _h.compare_digest(sig, deletion.mac("apple-state", body)[:43]):
            return None
        d = json.loads(unb64(body))
        if int(d["e"]) < (time.time() if now is None else now) or not deletion.USER_RE.match(str(d["u"])) or d["b"] not in ("app", "web"):
            return None
        return d
    except Exception:   # noqa: BLE001 - anything malformed is simply "not valid"
        return None


# ----------------------------------------------------------------------------- Apple calls
def post_form(url: str, fields: Dict[str, str], timeout: float = 10.0) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - https (or loopback in tests)
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def exchange_code(code: str, *, client_id: str, secret: str, redirect_uri: str, post=post_form) -> Dict[str, Any]:
    status, body = post(f"{base_url()}/auth/token", {"client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    if status != 200 or not body.get("refresh_token"):
        raise AppleError("token", status, str(body.get("error", "")))
    return body


def revoke(refresh_token: str, *, client_id: str, secret: str, post=post_form) -> None:
    status, body = post(f"{base_url()}/auth/revoke", {"client_id": client_id, "client_secret": secret, "token": refresh_token, "token_type_hint": "refresh_token"})
    if status != 200:
        raise AppleError("revoke", status, str(body.get("error", "")))


def id_token_subject(id_token: str) -> Optional[str]:
    """The `sub` of an id token that came straight from Apple's token endpoint over TLS (OpenID Connect allows skipping the signature check in that case)."""
    try:
        return str(json.loads(unb64(id_token.split(".")[1]))["sub"])
    except Exception:   # noqa: BLE001
        return None


class AppleError(Exception):
    def __init__(self, where: str, status: int, error: str):
        super().__init__(f"apple {where} failed: HTTP {status} {error}")   # status and Apple's error code only: never a token, never the key
        self.where, self.status, self.error = where, status, error


# ----------------------------------------------------------------------------- configuration (SSM String parameters and one Secrets Manager secret, the same ones Cognito's Apple provider uses)
_cfg: Dict[str, Any] = {}


def set_config(cfg: Optional[Dict[str, str]]) -> None:
    _cfg.clear()
    if cfg:
        _cfg.update(cfg)


def services_id() -> str:
    if "services_id" not in _cfg:
        import boto3

        _cfg["services_id"] = boto3.client("ssm").get_parameter(Name=os.environ.get("APPLE_SERVICES_ID_PARAM", "/videomk/apple_services_id"))["Parameter"]["Value"].strip()
    return _cfg["services_id"]


def signing_config() -> Dict[str, str]:
    import boto3

    ssm = boto3.client("ssm")
    for k, env, default in (("team_id", "APPLE_TEAM_ID_PARAM", "/videomk/apple_team_id"), ("key_id", "APPLE_KEY_ID_PARAM", "/videomk/apple_key_id")):
        if k not in _cfg:
            _cfg[k] = ssm.get_parameter(Name=os.environ.get(env, default))["Parameter"]["Value"].strip()
    if "private_key" not in _cfg:
        _cfg["private_key"] = boto3.client("secretsmanager").get_secret_value(SecretId=os.environ.get("APPLE_KEY_SECRET", "/videomk/apple_private_key"))["SecretString"]
    return {"services_id": services_id(), **{k: _cfg[k] for k in ("team_id", "key_id", "private_key")}}
