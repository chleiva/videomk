"""Sign in with Apple revocation (docs/ACCOUNT_DELETION.md): the ES256 client secret, the signed state, the callback and the start route, against a fake Apple server on loopback (no network)."""
import base64
import json
import logging
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

import account_api
import apple_revoke
from common import apple, deletion
from tests.test_account_deletion import A, FakeIdp, NOW, call, cerr, event, world  # noqa: F401  (the moto/fake world fixture is shared)

SERVICES, TEAM, KEYID = "com.videomk.signin.qa", "39ANXJNUTL", "ABC123DEFG"
APPLE_SUB = "001234.0123456789abcdef0123456789abcdef.0101"
APPLE_IDENTITIES = [{"providerName": "SignInWithApple", "userId": APPLE_SUB, "providerType": "SignInWithApple", "primary": "false", "dateCreated": "1"}]
RETURN = "https://api.example.test/prod/account/apple-callback"

KEY = ec.generate_private_key(ec.SECP256R1())
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
PUB = KEY.public_key()


def b64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_jwt(jwt):
    h, c, s = jwt.split(".")
    raw = b64u(s)
    assert len(raw) == 64
    PUB.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")), f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))
    return json.loads(b64u(h)), json.loads(b64u(c))


def fake_id_token(sub):
    body = base64.urlsafe_b64encode(json.dumps({"iss": "https://appleid.apple.com", "sub": sub, "aud": SERVICES}).encode()).rstrip(b"=").decode()
    return f"xx.{body}.yy"


class FakeApple:
    """appleid.apple.com as far as we use it: /auth/token (a code works once) and /auth/revoke. Checks the client secret's signature and claims on every call."""

    def __init__(self):
        self.codes = {"good-code": APPLE_SUB, "other-code": "999999.other.0000"}
        self.revoked, self.requests, self.fail = [], [], None
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                outer.requests.append((self.path, form))
                head, claims = verify_jwt(form["client_secret"])
                assert head == {"alg": "ES256", "kid": KEYID, "typ": "JWT"}
                assert claims["iss"] == TEAM and claims["sub"] == SERVICES and claims["aud"] == "https://appleid.apple.com" and form["client_id"] == SERVICES
                assert 0 < claims["exp"] - claims["iat"] <= 300
                status, body = 200, {}
                if outer.fail:
                    status, body = outer.fail
                elif self.path == "/auth/token":
                    sub = outer.codes.pop(form["code"], None)
                    assert form["grant_type"] == "authorization_code" and form["redirect_uri"] == RETURN
                    if sub is None:
                        status, body = 400, {"error": "invalid_grant"}
                    else:
                        body = {"access_token": "AT-secret", "refresh_token": "RT-secret-" + sub, "id_token": fake_id_token(sub), "expires_in": 3600, "token_type": "Bearer"}
                elif self.path == "/auth/revoke":
                    assert form["token_type_hint"] == "refresh_token"
                    outer.revoked.append(form["token"])
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_apple(monkeypatch):
    f = FakeApple()
    monkeypatch.setenv("APPLE_BASE_URL", f.url)
    yield f
    f.close()


@pytest.fixture
def ready(world, fake_apple, monkeypatch):  # noqa: F811
    w = world
    monkeypatch.setenv("APPLE_REVOKE_ENABLED", "1")
    monkeypatch.setenv("APPLE_RETURN_URL", RETURN)
    monkeypatch.setenv("APPLE_APP_RETURN", "com.videomk.app://auth/apple-revoked")
    monkeypatch.setenv("APPLE_WEB_RETURN", "https://videomk.com/delete-account")
    apple.set_config({"services_id": SERVICES, "team_id": TEAM, "key_id": KEYID, "private_key": PEM})
    w.idp.users.pop(A)
    w.idp.add("SignInWithApple_" + APPLE_SUB, A, "a@example.com", identities=APPLE_IDENTITIES)
    w.apple = fake_apple
    yield w
    apple.set_config(None)


def form_event(code=None, state=None, error=None):
    f = {k: v for k, v in (("code", code), ("state", state), ("error", error)) if v}
    return {"httpMethod": "POST", "body": urllib.parse.urlencode(f), "isBase64Encoded": False}


def start_deleting(w):
    deletion.create_job(A, "SignInWithApple_" + APPLE_SUB)


def good_state(back="app"):
    return apple.sign_state(A, APPLE_SUB, back)


# ----------------------------------------------------------------------------- the client secret
def test_the_client_secret_is_a_valid_short_lived_es256_jwt():
    jwt = apple.client_secret(TEAM, KEYID, SERVICES, PEM, now=1_800_000_000)
    head, claims = verify_jwt(jwt)
    assert head == {"alg": "ES256", "kid": KEYID, "typ": "JWT"}
    assert claims == {"iss": TEAM, "iat": 1_800_000_000, "exp": 1_800_000_300, "aud": "https://appleid.apple.com", "sub": SERVICES}


def test_a_key_that_is_not_p256_is_refused():
    other = ec.generate_private_key(ec.SECP384R1()).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    with pytest.raises(ValueError):
        apple.client_secret(TEAM, KEYID, SERVICES, other)


def test_the_authorize_url_points_at_apple_with_our_return_url_and_state():
    u = urllib.parse.urlparse(apple.authorize_url(SERVICES, RETURN, "st"))
    q = urllib.parse.parse_qs(u.query)
    assert f"{u.scheme}://{u.netloc}{u.path}" == "https://appleid.apple.com/auth/authorize"
    assert {k: v[0] for k, v in q.items()} == {"response_type": "code", "response_mode": "form_post", "client_id": SERVICES, "redirect_uri": RETURN, "state": "st"}


def test_only_a_loopback_host_may_replace_apples_address(monkeypatch):
    monkeypatch.setenv("APPLE_BASE_URL", "https://evil.example.com")
    assert apple.base_url() == "https://appleid.apple.com"
    monkeypatch.setenv("APPLE_BASE_URL", "http://127.0.0.1:9")
    assert apple.base_url() == "http://127.0.0.1:9"


# ----------------------------------------------------------------------------- the state
def test_state_round_trip_tamper_expiry_and_foreign_keys(world):
    st = apple.sign_state(A, APPLE_SUB, "app", now=time.time())
    assert apple.read_state(st)["u"] == A and apple.read_state(st)["a"] == APPLE_SUB
    body, sig = st.split(".")
    forged = apple.b64(json.dumps({"u": "bbbbbbbb-1111-2222-3333-444444444444", "a": APPLE_SUB, "b": "app", "e": int(time.time()) + 600}).encode())
    assert apple.read_state(f"{forged}.{sig}") is None
    assert apple.read_state(f"{body}.{sig[:-1]}x") is None
    assert apple.read_state(apple.sign_state(A, APPLE_SUB, "app", now=time.time() - 601)) is None
    assert apple.read_state("garbage") is None and apple.read_state("") is None and apple.read_state("a.b") is None
    assert apple.read_state(apple.sign_state(A, APPLE_SUB, "evil")) is None
    deletion.set_key(b"z" * 32)
    assert apple.read_state(st) is None                                              # signed with another key


# ----------------------------------------------------------------------------- the callback
def test_the_good_path_revokes_the_refresh_token_and_sends_the_person_back_to_the_app(ready):
    w = ready
    start_deleting(w)
    r = apple_revoke.handler(form_event("good-code", good_state()), None)
    assert r["statusCode"] == 303 and r["headers"]["Location"] == "com.videomk.app://auth/apple-revoked?status=ok"
    assert w.apple.revoked == ["RT-secret-" + APPLE_SUB]
    assert [p for p, _ in w.apple.requests] == ["/auth/token", "/auth/revoke"]
    assert deletion.get_job(A)["apple_revoked_at"]


def test_the_web_return_goes_to_the_website(ready):
    start_deleting(ready)
    r = apple_revoke.handler(form_event("good-code", good_state("web")), None)
    assert r["headers"]["Location"] == "https://videomk.com/delete-account?status=ok"


def test_an_authorization_code_works_once(ready):
    w = ready
    start_deleting(w)
    apple_revoke.handler(form_event("good-code", good_state()), None)
    r = apple_revoke.handler(form_event("good-code", good_state()), None)
    assert r["headers"]["Location"].endswith("status=failed") and len(w.apple.revoked) == 1


def test_another_apple_account_is_never_revoked(ready):
    w = ready
    start_deleting(w)
    r = apple_revoke.handler(form_event("other-code", good_state()), None)
    assert r["headers"]["Location"].endswith("status=mismatch")
    assert w.apple.revoked == [] and "apple_revoked_at" not in deletion.get_job(A)


@pytest.mark.parametrize("state", ["", "garbage", "a.b"])
def test_an_unsigned_or_bad_state_never_reaches_apple(ready, state):
    start_deleting(ready)
    r = apple_revoke.handler(form_event("good-code", state), None)
    assert r["headers"]["Location"].endswith("status=invalid") and ready.apple.requests == []


def test_an_expired_state_never_reaches_apple(ready):
    start_deleting(ready)
    r = apple_revoke.handler(form_event("good-code", apple.sign_state(A, APPLE_SUB, "app", now=time.time() - 700)), None)
    assert r["headers"]["Location"].endswith("status=invalid") and ready.apple.requests == []


def test_it_only_works_for_a_deletion_that_is_under_way(ready):
    r = apple_revoke.handler(form_event("good-code", good_state()), None)         # no job
    assert r["headers"]["Location"].endswith("status=invalid") and ready.apple.requests == []
    start_deleting(ready)
    deletion._update(A, "SET #s = :d", {"#s": "status"}, {":d": "done"})
    r = apple_revoke.handler(form_event("good-code", good_state()), None)
    assert r["headers"]["Location"].endswith("status=invalid") and ready.apple.requests == []


def test_cancelling_at_apple_is_reported_without_calls(ready):
    start_deleting(ready)
    r = apple_revoke.handler(form_event(None, good_state(), error="user_cancelled_authorize"), None)
    assert r["headers"]["Location"].endswith("status=cancelled") and ready.apple.requests == []


def test_an_apple_error_is_reported_and_logged_without_secrets(ready, caplog):
    w = ready
    start_deleting(w)
    w.apple.fail = (400, {"error": "invalid_client"})
    with caplog.at_level(logging.DEBUG):
        r = apple_revoke.handler(form_event("good-code", good_state()), None)
    assert r["headers"]["Location"].endswith("status=failed")
    assert "ACCOUNT_APPLE_REVOKE_FAILED" in caplog.text and "invalid_client" in caplog.text
    assert "good-code" not in caplog.text and "BEGIN PRIVATE KEY" not in caplog.text


def test_no_token_key_secret_or_code_is_ever_logged(ready, caplog):
    start_deleting(ready)
    with caplog.at_level(logging.DEBUG):
        apple_revoke.handler(form_event("good-code", good_state()), None)
    for secret in ("RT-secret", "AT-secret", "good-code", "PRIVATE KEY", PEM.splitlines()[1], "client_secret"):
        assert secret not in caplog.text
    assert "ACCOUNT_APPLE_REVOKED" in caplog.text


def test_a_broken_key_is_reported_as_a_failure_by_class_name_only(ready, caplog):
    start_deleting(ready)
    apple.set_config({"services_id": SERVICES, "team_id": TEAM, "key_id": KEYID, "private_key": "-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----"})
    with caplog.at_level(logging.DEBUG):
        r = apple_revoke.handler(form_event("good-code", good_state()), None)
    assert r["headers"]["Location"].endswith("status=failed") and "not a key" not in caplog.text


def test_a_base64_form_body_is_understood(ready):
    start_deleting(ready)
    ev = form_event("good-code", good_state())
    ev["body"], ev["isBase64Encoded"] = base64.b64encode(ev["body"].encode()).decode(), True
    assert apple_revoke.handler(ev, None)["headers"]["Location"].endswith("status=ok")


# ----------------------------------------------------------------------------- the start route
def start_event(user=A, body='{"return": "app"}'):
    return event(user=user, body=body, res="/users/{user_id}/account/apple-revoke", username="SignInWithApple_" + APPLE_SUB)


def test_start_is_off_unless_the_flag_is_on(ready, monkeypatch):
    start_deleting(ready)
    monkeypatch.setenv("APPLE_REVOKE_ENABLED", "0")
    code, body = call(start_event())
    assert code == 404 and body["code"] == "apple_revoke_off"


def test_start_needs_a_deletion_under_way_and_an_apple_identity(ready):
    code, body = call(start_event())
    assert code == 409 and body["code"] == "not_deleting"
    start_deleting(ready)
    ready.idp.users.clear()
    ready.idp.add("plain", A, "a@example.com")
    code, body = call(start_event())
    assert code == 409 and body["code"] == "no_apple_identity"
    deletion._update(A, "SET #s = :d", {"#s": "status"}, {":d": "done"})
    assert call(start_event())[0] == 410


def test_start_returns_the_apple_url_with_a_state_only_this_account_can_use(ready):
    start_deleting(ready)
    code, body = call(start_event())
    assert code == 200 and body["expires_in"] == 600
    u = urllib.parse.urlparse(body["authorize_url"])
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    assert u.netloc == "appleid.apple.com" and q["client_id"] == SERVICES and q["redirect_uri"] == RETURN
    st = apple.read_state(q["state"])
    assert st["u"] == A and st["a"] == APPLE_SUB and st["b"] == "app"


def test_start_rejects_another_users_path_and_bad_return(ready):
    start_deleting(ready)
    assert call(event(user="bbbbbbbb-1111-2222-3333-444444444444", path_user=A, res="/users/{user_id}/account/apple-revoke", body="{}"))[0] == 403
    assert call(start_event(body='{"return": "https://evil.example"}'))[0] == 400


def test_the_delete_answer_tells_the_app_when_the_apple_step_is_available(ready):
    code, body = call(event(username="SignInWithApple_" + APPLE_SUB))
    assert code == 202 and body["apple"] == "revoke_available"
