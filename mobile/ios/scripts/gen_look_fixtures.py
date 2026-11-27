"""Regenerates VideoMKUITests/Fixtures/looks_<lang>.json from the backend's own capabilities answer (run with the repository's .venv python, no arguments)."""
import json, os, sys
root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path[:0] = [os.path.join(root, "backend"), os.path.join(root, "backend", "lambdas")]
for k in ("VECTOR_SCENES", "WHITEBOARD", "PRESENTERS"):
    os.environ[k] = "1"
import capabilities_api
for lang in ("en", "es"):
    ev = {"pathParameters": {"user_id": "u1"}, "headers": {"X-Locale": lang}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}
    r = capabilities_api.handler(ev, None)
    assert r["statusCode"] == 200, r
    looks = json.loads(r["body"])["looks"]
    path = os.path.join(root, "mobile/ios/VideoMKUITests/Fixtures", f"looks_{lang}.json")
    old = json.load(open(path, encoding="utf-8"))
    new = {"looks": {k: looks[k] for k in old["looks"]}}
    print(lang, list(old["looks"]), [o["label"] + ": " + o["note"] for o in new["looks"]["look"]["options"]], new["looks"]["cast"]["auto"], new["looks"]["cast"]["conversation"]["note"])
    json.dump(new, open(path, "w", encoding="utf-8"), ensure_ascii=False)
