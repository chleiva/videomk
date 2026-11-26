"""All /users/{user_id}/library/... routes in one function (see docs/MEDIA_LIBRARY.md). The caller is the verified Cognito `sub` and nothing else."""
import json
import logging
from typing import Any, Dict, Optional

from common import i18n
from common import library as lib
from common import library_organize as organize
from common import library_search as search
from common import usage
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()


def _ask_small(system: str, user: str) -> str:
    from engine import llm

    return llm.complete(system, user, max_tokens=300, model=llm.REVIEW_MODEL, effort="low")[0]


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except (ValueError, TypeError):
        raise lib.LibraryError(400, "the body must be JSON") from None
    if not isinstance(body, dict):
        raise lib.LibraryError(400, "the body must be a JSON object")
    return body


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _items_json(user: str, rows) -> list:
    return [lib.photo_json(user, r) for r in rows]


def route(event: Dict[str, Any], user: str) -> Dict[str, Any]:
    res, method = event.get("resource") or "", event.get("httpMethod") or ""
    params = event.get("pathParameters") or {}
    q = event.get("queryStringParameters") or {}
    base = "/users/{user_id}/library"
    if res == f"{base}/summary" and method == "GET":
        return lib.summary(user)
    if res == f"{base}/uploads" and method == "POST":
        items = _body(event).get("items")

        def consume(u: str) -> None:
            usage.consume(f"libup:{u}", limit=lib.DAILY_SLOTS)

        out = lib.create_slots(user, items, consume=consume)
        if out["uploads"] and all(u["status"] == "no_space" for u in out["uploads"]):
            raise lib.LibraryError(402, "Your storage is full.", code="storage_full", used_bytes=out["used_bytes"], limit_bytes=out["limit_bytes"])
        return out
    if res == f"{base}/items" and method == "GET":
        limit = _int(q.get("limit"), 60, 1, 100)
        if q.get("collection"):
            r = lib.collection_items(user, lib.check_id(q["collection"]), limit, q.get("cursor"))
        else:
            places = [q["place"]] if q.get("place") else []
            countries, plc = search.split_places(user, places) if places else ([], [])
            if places and not (countries or plc):
                return {"items": [], "cursor": None}
            r = lib.list_items(user, limit=limit, cursor=q.get("cursor"), date_from=q.get("from"), date_to=q.get("to"), countries=countries, places=plc)
        return {"items": _items_json(user, r["items"]), "cursor": r["cursor"]}
    if res == f"{base}/items/{{item_id}}" and method == "GET":
        it = lib.get_item(user, params.get("item_id"))
        if not it:
            raise lib.LibraryError(404, i18n.Localized("err.not_found"))
        return lib.photo_json(user, it, full=True)
    if res == f"{base}/items/delete" and method == "POST":
        return lib.delete_items(user, _body(event).get("ids"))
    if res == f"{base}/search" and method == "POST":
        b = _body(event)
        try:
            usage.consume(f"libsearch:{user}", limit=lib.DAILY_SEARCHES)
        except usage.QuotaExceeded:
            raise lib.LibraryError(429, "Too many searches today. Try again tomorrow.") from None
        drop = b.get("drop") if isinstance(b.get("drop"), list) else []
        return search.search(user, b.get("query"), limit=_int(b.get("limit"), 60, 1, 100), cursor=b.get("cursor"), drop=[str(x)[:80] for x in drop[:10]], ask=_ask_small)
    if res == f"{base}/collections":
        if method == "GET":
            return {"collections": lib.collections(user)}
        if method == "POST":
            b = _body(event)
            return lib.create_collection(user, b.get("name"), b.get("emoji"))
    if res == f"{base}/collections/{{collection_id}}" and method == "POST":
        b = _body(event)
        return lib.update_collection(user, params.get("collection_id"), b.get("name"), b["emoji"] if "emoji" in b else "__keep__")
    if res == f"{base}/collections/{{collection_id}}/delete" and method == "POST":
        lib.delete_collection(user, params.get("collection_id"))
        return {"deleted": True}
    if res == f"{base}/collections/{{collection_id}}/items" and method == "POST":
        b = _body(event)
        for k in ("add", "remove"):
            if b.get(k) is not None and not (isinstance(b[k], list) and all(isinstance(i, str) for i in b[k])):
                raise lib.LibraryError(400, f"'{k}' must be a list of photo ids")
        return lib.change_collection(user, params.get("collection_id"), b.get("add") or [], b.get("remove") or [])
    if res == f"{base}/prefs" and method == "POST":
        return lib.set_prefs(user, _body(event).get("organize"))
    if res == f"{base}/organize/preview" and method == "POST":
        return organize.preview(user, _body(event).get("since"))
    if res == f"{base}/organize/apply" and method == "POST":
        b = _body(event)
        if b.get("mode") == "single":
            return organize.apply_single(user, b.get("name"), b.get("since"), b.get("collection_id"))
        if b.get("mode") not in (None, "auto"):
            raise lib.LibraryError(400, "'mode' must be auto or single")
        return organize.apply_auto(user, b.get("since"))
    if res == f"{base}/delete-all" and method == "POST":
        if _body(event).get("confirm") != "DELETE":
            raise lib.LibraryError(400, "send {\"confirm\": \"DELETE\"} to delete everything")
        return lib.purge_user(user)
    raise lib.LibraryError(404, i18n.Localized("err.not_found"))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    try:
        lib.check_user(user)
        return json_response(200, route(event, user))
    except lib.LibraryError as e:
        headers = {"Retry-After": "3600"} if e.status == 429 else None
        return json_response(e.status, {"message": e.text(loc), **e.extra}, headers)
    except Exception:
        logger.exception("library request failed")   # no keys, names or queries in the log line
        return json_response(500, {"message": i18n.t("err.generic", loc)})
