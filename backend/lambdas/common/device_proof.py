"""Device proofs: is this request coming from the real videomk app on a real phone? (docs/PLANS.md, "Abuse controls"). Verification only; lambdas/device_api.py is the route.

  iOS App Attest      verify_attestation() once per app key, then verify_assertion() per challenge. Needs NO secret: only the app id (<team id>.<bundle id>) and Apple's
                      public App Attestation root certificate (below). BUILT. It proves a genuine app on a genuine Apple device; it does not by itself tell two installs
                      on one device apart (an app can make a new key), which is what DeviceCheck's two bits are for.
  iOS DeviceCheck     devicecheck_bits() / devicecheck_set(): two bits Apple keeps per device and developer, surviving reinstall. Needs the owner's DeviceCheck key
                      (.p8, key id, team id): NOT available yet, so the knob device_check_ios is off and these are never called.
  Android             play_decode() (Google decodes the token: needs the Play Console to Cloud project link and a service account, NOT available yet, knob
  Play Integrity      device_proof_android off) and check_play_verdict() (pure: is the decoded verdict good enough).

Needs `cryptography` (the apple_deps layer). Network calls go through `http_json`, which tests replace. Nothing here stores anything.
"""
import base64
import hashlib
import json
import struct
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

APPLE_APP_ATTEST_ROOT_PEM = b"""-----BEGIN CERTIFICATE-----
MIICITCCAaegAwIBAgIQC/O+DvHN0uD7jG5yH2IXmDAKBggqhkjOPQQDAzBSMSYw
JAYDVQQDDB1BcHBsZSBBcHAgQXR0ZXN0YXRpb24gUm9vdCBDQTETMBEGA1UECgwK
QXBwbGUgSW5jLjETMBEGA1UECAwKQ2FsaWZvcm5pYTAeFw0yMDAzMTgxODMyNTNa
Fw00NTAzMTUwMDAwMDBaMFIxJjAkBgNVBAMMHUFwcGxlIEFwcCBBdHRlc3RhdGlv
biBSb290IENBMRMwEQYDVQQKDApBcHBsZSBJbmMuMRMwEQYDVQQIDApDYWxpZm9y
bmlhMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAERTHhmLW07ATaFQIEVwTtT4dyctdh
NbJhFs/Ii2FdCgAHGbpphY3+d8qjuDngIN3WVhQUBHAoMeQ/cLiP1sOUtgjqK9au
Yen1mMEvRq9Sk3Jm5X8U62H+xTD3FE9TgS41o0IwQDAPBgNVHRMBAf8EBTADAQH/
MB0GA1UdDgQWBBSskRBTM72+aEH/pwyp5frq5eWKoTAOBgNVHQ8BAf8EBAMCAQYw
CgYIKoZIzj0EAwMDaAAwZQIwQgFGnByvsiVbpTKwSga0kP0e8EeDS4+sQmTvb7vn
53O5+FRXgeLhpJ06ysC5PrOyAjEAp5U4xDgEgllF7En3VcE3iexZZtKeYnpqtijV
oyFraWVIyd/dganmrduC1bmTBGwD
-----END CERTIFICATE-----
"""   # https://www.apple.com/certificateauthority/Apple_App_Attestation_Root_CA.pem, fetched 2026-11-27 (SHA-256 1cb9823b...6242c932, valid to 2045-03-15)
NONCE_OID = "1.2.840.113635.100.8.2"
AAGUID_PROD, AAGUID_DEV = b"appattest" + b"\x00" * 7, b"appattestdevelop"
_root_pem = APPLE_APP_ATTEST_ROOT_PEM


class ProofError(Exception):
    """The proof is not valid. `reason` goes to the log and the metric, never to the client."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def set_root(pem: Optional[bytes]) -> None:   # tests sign with their own root
    global _root_pem
    _root_pem = pem or APPLE_APP_ATTEST_ROOT_PEM


def b64d(text: Any) -> bytes:
    if not isinstance(text, str) or not text or len(text) > 20000:
        raise ProofError("encoding")
    try:
        return base64.b64decode(text.replace("-", "+").replace("_", "/") + "=" * (-len(text) % 4), validate=True)
    except Exception:   # noqa: BLE001
        raise ProofError("encoding") from None


# ----------------------------------------------------------------------------- CBOR (the small subset App Attest uses: maps, arrays, byte and text strings, unsigned ints)
def cbor_decode(data: bytes) -> Any:
    def head(i: int) -> Tuple[int, int, int]:
        if i >= len(data):
            raise ProofError("cbor")
        major, info = data[i] >> 5, data[i] & 31
        i += 1
        if info < 24:
            return major, info, i
        size = {24: 1, 25: 2, 26: 4, 27: 8}.get(info)
        if size is None or i + size > len(data):
            raise ProofError("cbor")
        return major, int.from_bytes(data[i:i + size], "big"), i + size

    def item(i: int, depth: int) -> Tuple[Any, int]:
        if depth > 8:
            raise ProofError("cbor")
        major, n, i = head(i)
        if major == 0:
            return n, i
        if major in (2, 3):
            if i + n > len(data):
                raise ProofError("cbor")
            raw = data[i:i + n]
            return (raw if major == 2 else raw.decode("utf-8", "replace")), i + n
        if major == 4:
            out = []
            for _ in range(min(n, 64)):
                v, i = item(i, depth + 1)
                out.append(v)
            return out, i
        if major == 5:
            d: Dict[Any, Any] = {}
            for _ in range(min(n, 64)):
                k, i = item(i, depth + 1)
                v, i = item(i, depth + 1)
                if isinstance(k, (str, int)):
                    d[k] = v
            return d, i
        raise ProofError("cbor")
    value, _ = item(0, 0)
    return value


def cbor_encode(value: Any) -> bytes:   # for tests and tools
    def head(major: int, n: int) -> bytes:
        if n < 24:
            return bytes([major << 5 | n])
        for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * size):
                return bytes([major << 5 | info]) + n.to_bytes(size, "big")
        raise ValueError("too large")
    if isinstance(value, int):
        return head(0, value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        return head(3, len(value.encode())) + value.encode()
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(cbor_encode(v) for v in value)
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(cbor_encode(k) + cbor_encode(v) for k, v in value.items())
    raise ValueError("unsupported")


# ----------------------------------------------------------------------------- iOS App Attest
def _auth_data(raw: bytes) -> Dict[str, Any]:
    if not isinstance(raw, bytes) or len(raw) < 37:
        raise ProofError("auth_data")
    out: Dict[str, Any] = {"rp_id_hash": raw[:32], "flags": raw[32], "counter": struct.unpack(">I", raw[33:37])[0]}
    if len(raw) >= 55:
        n = struct.unpack(">H", raw[53:55])[0]
        out.update({"aaguid": raw[37:53], "credential_id": raw[55:55 + n]})
    return out


def _check_chain(x5c: List[bytes], now: float) -> Any:
    """The credential certificate, after checking leaf <- intermediate <- Apple's root and every validity period."""
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec
    from datetime import datetime, timezone
    if not isinstance(x5c, list) or not 2 <= len(x5c) <= 4 or not all(isinstance(c, bytes) for c in x5c):
        raise ProofError("chain")
    try:
        certs = [x509.load_der_x509_certificate(c) for c in x5c] + [x509.load_pem_x509_certificate(_root_pem)]
        at = datetime.fromtimestamp(now, timezone.utc)
        for cert, issuer in zip(certs[:-1], certs[1:]):
            if not (cert.not_valid_before_utc <= at <= cert.not_valid_after_utc) or cert.issuer != issuer.subject:
                raise ProofError("chain")
            issuer.public_key().verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm))
        if not (certs[-1].not_valid_before_utc <= at <= certs[-1].not_valid_after_utc):
            raise ProofError("chain")
        return certs[0]
    except ProofError:
        raise
    except Exception:   # noqa: BLE001 - a bad signature, a certificate that does not parse, a key of another kind
        raise ProofError("chain") from None


def verify_attestation(attestation: bytes, key_id: bytes, challenge: bytes, app_ids: List[str], *, allow_development: bool, now: Optional[float] = None) -> Dict[str, Any]:
    """Apple's nine steps ("Validating apps that connect to your server"). Returns {"public_key_pem", "counter": 0, "environment"} to store for later assertions."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    now = time.time() if now is None else now
    obj = cbor_decode(attestation)
    if not isinstance(obj, dict) or obj.get("fmt") != "apple-appattest" or not isinstance(obj.get("attStmt"), dict) or not isinstance(obj.get("authData"), bytes):
        raise ProofError("format")
    cert = _check_chain(obj["attStmt"].get("x5c"), now)
    nonce = hashlib.sha256(obj["authData"] + hashlib.sha256(challenge).digest()).digest()
    try:
        ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(NONCE_OID)).value.value
    except Exception:   # noqa: BLE001
        raise ProofError("nonce") from None
    if ext[-34:-32] != b"\x04\x20" or ext[-32:] != nonce:
        raise ProofError("nonce")
    public = cert.public_key()
    point = public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    if hashlib.sha256(point).digest() != key_id:
        raise ProofError("key_id")
    ad = _auth_data(obj["authData"])
    if ad["rp_id_hash"] not in [hashlib.sha256(a.encode()).digest() for a in app_ids]:
        raise ProofError("app_id")
    if ad["counter"] != 0:
        raise ProofError("counter")
    if ad.get("aaguid") not in ((AAGUID_PROD, AAGUID_DEV) if allow_development else (AAGUID_PROD,)):
        raise ProofError("environment")
    if ad.get("credential_id") != key_id:
        raise ProofError("credential_id")
    return {"public_key_pem": public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(), "counter": 0,
            "environment": "production" if ad["aaguid"] == AAGUID_PROD else "development"}


def verify_assertion(assertion: bytes, client_data: bytes, public_key_pem: str, last_counter: int, app_ids: List[str]) -> int:
    """An assertion made with a key attested earlier, over `client_data` (our challenge). Returns the new counter, which the caller must store (it only ever grows)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    obj = cbor_decode(assertion)
    if not isinstance(obj, dict) or not isinstance(obj.get("signature"), bytes) or not isinstance(obj.get("authenticatorData"), bytes):
        raise ProofError("format")
    nonce = hashlib.sha256(obj["authenticatorData"] + hashlib.sha256(client_data).digest()).digest()
    try:
        serialization.load_pem_public_key(public_key_pem.encode()).verify(obj["signature"], nonce, ec.ECDSA(hashes.SHA256()))
    except Exception:   # noqa: BLE001
        raise ProofError("signature") from None
    ad = _auth_data(obj["authenticatorData"])
    if ad["rp_id_hash"] not in [hashlib.sha256(a.encode()).digest() for a in app_ids]:
        raise ProofError("app_id")
    if ad["counter"] <= int(last_counter):
        raise ProofError("counter")
    return int(ad["counter"])


# ----------------------------------------------------------------------------- network (replaced in tests)
def _http_json(url: str, body: Any, headers: Dict[str, str], form: bool = False) -> Dict[str, Any]:
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded" if form else "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=6) as r:   # noqa: S310 - fixed https hosts below
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw.strip().startswith("{") else {"text": raw}
    except ValueError:
        return {"text": raw}


http_json: Callable[..., Dict[str, Any]] = _http_json


def _jwt(header: Dict[str, Any], claims: Dict[str, Any], pem: str, alg: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

    def enc(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    signing = enc(json.dumps(header, separators=(",", ":")).encode()) + "." + enc(json.dumps(claims, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if alg == "ES256":
        r, s = utils.decode_dss_signature(key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
        sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    else:
        sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    return signing + "." + enc(sig)


# ----------------------------------------------------------------------------- iOS DeviceCheck (needs the owner's key: not live)
DEVICECHECK_HOST = "https://api.devicecheck.apple.com"


def devicecheck_bits(device_token: str, creds: Dict[str, str], *, now: Optional[float] = None) -> Dict[str, bool]:
    """{bit0, bit1} Apple keeps for this device and our team. bit0 = "this device already used its free allowance". creds: {team_id, key_id, private_key (the .p8 text)}."""
    now = time.time() if now is None else now
    token = _jwt({"alg": "ES256", "kid": creds["key_id"]}, {"iss": creds["team_id"], "iat": int(now)}, creds["private_key"], "ES256")
    res = http_json(f"{DEVICECHECK_HOST}/v1/query_two_bits", {"device_token": device_token, "transaction_id": hashlib.sha256(f"{device_token}{now}".encode()).hexdigest()[:32],
                                                             "timestamp": int(now * 1000)}, {"Authorization": f"Bearer {token}"})
    return {"bit0": bool(res.get("bit0")), "bit1": bool(res.get("bit1"))}   # a device never seen answers with plain text ("Bit State Not Found"): both false


def devicecheck_set(device_token: str, creds: Dict[str, str], *, bit0: bool = True, bit1: bool = False, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    token = _jwt({"alg": "ES256", "kid": creds["key_id"]}, {"iss": creds["team_id"], "iat": int(now)}, creds["private_key"], "ES256")
    http_json(f"{DEVICECHECK_HOST}/v1/update_two_bits", {"device_token": device_token, "transaction_id": hashlib.sha256(f"set{device_token}{now}".encode()).hexdigest()[:32],
                                                         "timestamp": int(now * 1000), "bit0": bit0, "bit1": bit1}, {"Authorization": f"Bearer {token}"})


# ----------------------------------------------------------------------------- Android Play Integrity (needs the Play Console link and a service account: not live)
def _google_token(service_account: Dict[str, str], now: float) -> str:
    assertion = _jwt({"alg": "RS256", "typ": "JWT"}, {"iss": service_account["client_email"], "scope": "https://www.googleapis.com/auth/playintegrity",
                                                     "aud": "https://oauth2.googleapis.com/token", "iat": int(now), "exp": int(now) + 600}, service_account["private_key"], "RS256")
    res = http_json("https://oauth2.googleapis.com/token", {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, {}, True)
    if not res.get("access_token"):
        raise ProofError("google_auth")
    return str(res["access_token"])


def play_decode(integrity_token: str, package: str, service_account: Dict[str, str], *, now: Optional[float] = None) -> Dict[str, Any]:
    """Ask Google to decode and verify the token (the standard API: the token cannot be read locally)."""
    now = time.time() if now is None else now
    res = http_json(f"https://playintegrity.googleapis.com/v1/{package}:decodeIntegrityToken", {"integrity_token": integrity_token}, {"Authorization": f"Bearer {_google_token(service_account, now)}"})
    payload = res.get("tokenPayloadExternal")
    if not isinstance(payload, dict):
        raise ProofError("google_decode")
    return payload


def play_recall_write(integrity_token: str, package: str, service_account: Dict[str, str], *, now: Optional[float] = None) -> None:
    """Remember on Google's side that this device used its free allowance (device recall, bit 1 of 3): survives reinstall and factory reset."""
    now = time.time() if now is None else now
    http_json(f"https://playintegrity.googleapis.com/v1/{package}/deviceRecall:write", {"integrityToken": integrity_token, "newValues": {"bitFirst": True}},
              {"Authorization": f"Bearer {_google_token(service_account, now)}"})


def check_play_verdict(payload: Dict[str, Any], package: str, challenge: str, *, now: Optional[float] = None, max_age_s: int = 600) -> Dict[str, Any]:
    """Pure: is this decoded verdict acceptable? The request must be ours (package, our challenge as the request hash or nonce, fresh), the app the one Google Play
    distributes, the device a genuine certified one. Returns {"device_claimed": the recall bit}."""
    now = time.time() if now is None else now
    req, app, dev = payload.get("requestDetails") or {}, payload.get("appIntegrity") or {}, payload.get("deviceIntegrity") or {}
    if req.get("requestPackageName") != package:
        raise ProofError("package")
    if challenge not in (req.get("requestHash"), req.get("nonce")):
        raise ProofError("nonce")
    try:
        age = now - int(req.get("timestampMillis")) / 1000.0
    except (TypeError, ValueError):
        raise ProofError("timestamp") from None
    if not -60 <= age <= max_age_s:
        raise ProofError("timestamp")
    if app.get("appRecognitionVerdict") != "PLAY_RECOGNIZED":
        raise ProofError("app")
    if "MEETS_DEVICE_INTEGRITY" not in (dev.get("deviceRecognitionVerdict") or []):
        raise ProofError("device")
    recall = ((dev.get("deviceRecall") or {}).get("values") or {})
    return {"device_claimed": bool(recall.get("bitFirst"))}
