"""The private photo library: quota, uploads, ingest, isolation between users, search, collections, delete."""
import base64
import hashlib
import io
import json
import math
import os
import time

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from common import library as lib
from common import library_search as search
import library_api
import library_ingest
import library_sweeper

A = "11111111-aaaa-bbbb-cccc-000000000001"
B = "22222222-aaaa-bbbb-cccc-000000000002"
EVENT_BASE = "/users/{user_id}/library"


def jpeg(color=(200, 100, 50), size=(640, 480)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG", quality=85)
    return b.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeVectors:
    """Just enough of S3 Vectors: put, delete, filtered cosine query."""

    def __init__(self):
        self.data = {}
        self.queries = []

    def put_vectors(self, vectorBucketName, indexName, vectors):
        for v in vectors:
            self.data[v["key"]] = (v["data"]["float32"], v["metadata"])

    def delete_vectors(self, vectorBucketName, indexName, keys):
        for k in keys:
            self.data.pop(k, None)

    def _match(self, md, f):
        if "$and" in f:
            return all(self._match(md, x) for x in f["$and"])
        if "$or" in f:
            return any(self._match(md, x) for x in f["$or"])
        (k, cond), = f.items()
        (op, val), = cond.items()
        v = md.get(k)
        return {"$eq": lambda: v == val, "$gte": lambda: v is not None and v >= val, "$lte": lambda: v is not None and v <= val, "$in": lambda: v in val}[op]()

    def query_vectors(self, vectorBucketName, indexName, queryVector, topK, filter=None, returnDistance=False, returnMetadata=False):
        self.queries.append(filter)
        q = queryVector["float32"]
        out = []
        for k, (vec, md) in self.data.items():
            if filter and not self._match(md, filter):
                continue
            dot = sum(a * b for a, b in zip(q, vec))
            na, nb = math.sqrt(sum(a * a for a in q)), math.sqrt(sum(b * b for b in vec))
            out.append({"key": k, "distance": 1 - dot / (na * nb or 1)})
        out.sort(key=lambda x: x["distance"])
        return {"vectors": out[:topK]}


def _setup_media(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("MEDIA_TABLE", "Media")
    monkeypatch.setenv("MEDIA_BUCKET", "media-bucket")
    monkeypatch.setenv("VECTOR_BUCKET", "vb")
    lib.reset_clients()
    ddb = boto3.resource("dynamodb", region_name="us-west-2")
    ddb.create_table(TableName="Media", BillingMode="PAY_PER_REQUEST",
                     KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
                     AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("user_id", "sk", "srt", "pend", "created")],
                     GlobalSecondaryIndexes=[
                         {"IndexName": "Timeline", "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "srt", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}},
                         {"IndexName": "Pending", "KeySchema": [{"AttributeName": "pend", "KeyType": "HASH"}, {"AttributeName": "created", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}])
    boto3.client("s3", region_name="us-west-2").create_bucket(Bucket="media-bucket", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    fake = FakeVectors()
    lib.set_vectors(fake)
    monkeypatch.setattr(search, "embed_image", lambda b: _vec(b))
    monkeypatch.setattr(search, "embed_text", lambda t: _text_vec(t))
    return fake


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        ddb.create_table(TableName="Flags", BillingMode="PAY_PER_REQUEST", KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}])
        ddb.create_table(TableName="Usage", BillingMode="PAY_PER_REQUEST", KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "day", "KeyType": "RANGE"}],
                         AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}, {"AttributeName": "day", "AttributeType": "S"}])
        monkeypatch.setenv("FLAGS_TABLE", "Flags")
        monkeypatch.setenv("USAGE_TABLE", "Usage")
        yield _setup_media(monkeypatch)
        lib.reset_clients()


def _vec(data: bytes):
    im = Image.open(io.BytesIO(data)).convert("RGB").resize((1, 1))
    r, g, b = im.getpixel((0, 0))
    return [r / 255, g / 255, b / 255] + [0.01] * 5


def _text_vec(text: str):
    t = text.lower()
    return [1.0 if "red" in t else 0.0, 1.0 if "green" in t else 0.0, 1.0 if "blue" in t else 0.0] + [0.01] * 5


def upload(user, data=None, taken=None, lat=None, lon=None, color=(200, 100, 50)):
    """The whole path: slot, upload to S3, ingest. Returns the photo id."""
    data = data or jpeg(color)
    item = {"size": len(data), "sha256": sha(data)}
    for k, v in (("taken", taken), ("lat", lat), ("lon", lon)):
        if v is not None:
            item[k] = v
    res = lib.create_slots(user, [item], consume=lambda u: None)["uploads"][0]
    assert res["status"] == "upload", res
    boto3.client("s3", region_name="us-west-2").put_object(Bucket="media-bucket", Key=lib.orig_key(user, res["id"]), Body=data, ContentType="image/jpeg")
    assert library_ingest.process(user, res["id"]) == "ready"
    return res["id"]


def call(user, method, resource, path_user=None, body=None, query=None, **params):
    event = {"httpMethod": method, "resource": EVENT_BASE + resource, "pathParameters": {"user_id": path_user or user, **params}, "queryStringParameters": query,
             "body": json.dumps(body) if body is not None else None, "requestContext": {"authorizer": {"claims": {"sub": user}}}}
    r = library_api.handler(event, None)
    return r["statusCode"], json.loads(r["body"])


# ----------------------------------------------------------------------------- uploads, quota, dedupe
def test_a_slot_fixes_the_key_the_size_the_type_and_the_storage_class(env):
    data = jpeg()
    res = lib.create_slots(A, [{"size": len(data), "sha256": sha(data)}], consume=lambda u: None)["uploads"][0]
    assert res["status"] == "upload" and lib.ID_RE.match(res["id"])
    f = res["fields"]
    assert f["key"] == f"o/{A}/{res['id']}.jpg" and f["Content-Type"] == "image/jpeg" and f["x-amz-storage-class"] == "INTELLIGENT_TIERING"
    policy = json.loads(base64.b64decode(f["policy"]))
    assert ["content-length-range", 1, len(data)] in policy["conditions"] and {"x-amz-storage-class": "INTELLIGENT_TIERING"} in policy["conditions"]
    assert lib.stats(A)["used"] == len(data)   # reserved


def test_the_quota_reserves_what_fits_and_names_what_does_not(env, monkeypatch):
    monkeypatch.setattr(lib, "FREE_BYTES", 2500)
    items = [{"size": 1000, "sha256": f"{i:064x}"} for i in range(1, 5)]
    out = lib.create_slots(A, items, consume=lambda u: None)
    assert [u["status"] for u in out["uploads"]] == ["upload", "upload", "no_space", "no_space"] and out["used_bytes"] == 2000 and out["limit_bytes"] == 2500
    code, body = call(A, "POST", "/uploads", body={"items": [{"size": 1000, "sha256": "e" * 64}]})
    assert code == 402 and body["code"] == "storage_full" and body["limit_bytes"] == 2500


def test_the_same_content_is_a_duplicate_and_costs_nothing(env):
    data = jpeg()
    first = upload(A, data)
    again = lib.create_slots(A, [{"size": len(data), "sha256": sha(data)}, {"size": 5, "sha256": "a" * 64}, {"size": 5, "sha256": "a" * 64}], consume=lambda u: None)["uploads"]
    assert again[0] == {"index": 0, "status": "duplicate", "duplicate_of": first}
    assert again[1]["status"] == "upload" and again[2]["status"] == "duplicate" and again[2]["duplicate_of"] == again[1]["id"]
    assert lib.stats(A)["used"] == len(data) + 5
    assert lib.create_slots(B, [{"size": len(data), "sha256": sha(data)}], consume=lambda u: None)["uploads"][0]["status"] == "upload"   # another person's copy is theirs


def test_bad_slot_requests_are_refused(env):
    for bad in ([], "x", [{"size": 0, "sha256": "a" * 64}], [{"size": 5, "sha256": "zz"}], [{"size": 5, "sha256": "a" * 64, "lat": 95, "lon": 0}], [{"size": True, "sha256": "a" * 64}], [1]):
        with pytest.raises(lib.LibraryError) as e:
            lib.create_slots(A, bad, consume=lambda u: None)
        assert e.value.status == 400
    with pytest.raises(lib.LibraryError):
        lib.create_slots(A, [{"size": 5, "sha256": "a" * 64}] * 101, consume=lambda u: None)


def test_the_entitlement_decides_the_limit_and_a_lapsed_plan_falls_back_without_deleting(env):
    flags = boto3.resource("dynamodb").Table("Flags")
    assert lib.limits(A) == {"plan": "free", "limit_bytes": 2 * lib.GB}
    flags.put_item(Item={"user_id": A, "storage_plan": "pro", "storage_extra_gb": 100})
    assert lib.limits(A) == {"plan": "pro", "limit_bytes": 200 * lib.GB}
    flags.put_item(Item={"user_id": A, "storage_plan": "pro", "storage_extra_gb": 100, "storage_until": int(time.time()) - 5})
    assert lib.limits(A) == {"plan": "free", "limit_bytes": 2 * lib.GB}


# ----------------------------------------------------------------------------- ingest
def test_ingest_makes_the_thumbnail_the_vector_and_the_place_without_coordinates(env):
    mid = upload(A, taken="2024-07-14T10:00:00", lat=7.88, lon=98.39, color=(250, 10, 10))    # near Phuket
    it = lib.get_item(A, mid)
    assert it["st"] == "ready" and it["w"] == 640 and it["srt"].startswith("2024-07-14T10:00:00#") and "Thailand" in it["pl"] and it["cc"] == "Thailand"
    assert not any(k in it for k in ("lat", "lon")) and "pend" not in it
    thumb = boto3.client("s3", region_name="us-west-2").get_object(Bucket="media-bucket", Key=lib.thumb_key(A, mid))
    assert thumb["CacheControl"].startswith("private") and max(Image.open(io.BytesIO(thumb["Body"].read())).size) == 480
    vec, md = env.data[f"{A}:{mid}"]
    assert md["user"] == A and md["country"] == "Thailand" and md["year"] == 2024 and md["ts"] > 1.7e9
    assert lib.stats(A) == {"used": it["size_b"], "n": 1}
    f = lib.facets(A)
    assert f["y"] == {"2024": 1} and f["c"] == {"Thailand": 1}


def test_ingest_rejects_what_is_not_a_jpeg_or_does_not_match_and_gives_the_space_back(env):
    s3c = boto3.client("s3", region_name="us-west-2")
    png = io.BytesIO()
    Image.new("RGB", (10, 10)).save(png, "PNG")
    for payload, mismatch in ((png.getvalue(), False), (b"not an image at all", False), (jpeg(), True)):
        declared = payload if not mismatch else jpeg((1, 2, 3))
        res = lib.create_slots(A, [{"size": max(len(payload), len(declared)), "sha256": sha(declared)}], consume=lambda u: None)["uploads"][0]
        s3c.put_object(Bucket="media-bucket", Key=lib.orig_key(A, res["id"]), Body=payload)
        assert library_ingest.process(A, res["id"]) == "rejected"
        assert lib.get_item(A, res["id"], ready_only=False) is None
        assert "Contents" not in s3c.list_objects_v2(Bucket="media-bucket", Prefix=f"o/{A}/")
    assert lib.stats(A)["used"] == 0
    assert library_ingest.process(A, "f" * 16) == "rejected"   # an object nobody asked for is removed


def test_the_ingest_handler_reads_s3_events_ignores_strangers_and_retries_transient_errors(env, monkeypatch):
    data = jpeg()
    res = lib.create_slots(A, [{"size": len(data), "sha256": sha(data)}], consume=lambda u: None)["uploads"][0]
    boto3.client("s3", region_name="us-west-2").put_object(Bucket="media-bucket", Key=lib.orig_key(A, res["id"]), Body=data)
    def ev(key, mid="m1"):
        return {"Records": [{"messageId": mid, "attributes": {"ApproximateReceiveCount": "1"}, "body": json.dumps({"Records": [{"s3": {"object": {"key": key}}}]})}]}
    assert library_ingest.handler({"Records": [{"messageId": "t", "body": json.dumps({"Event": "s3:TestEvent"})}]}, None) == {"batchItemFailures": []}
    assert library_ingest.handler(ev("t/x/y.jpg"), None) == {"batchItemFailures": []}
    monkeypatch.setattr(search, "embed_image", lambda b: (_ for _ in ()).throw(RuntimeError("throttled")))
    assert library_ingest.handler(ev(f"o/{A}/{res['id']}.jpg"), None) == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert lib.get_item(A, res["id"], ready_only=False)["st"] == "pending"
    e4 = ev(f"o/{A}/{res['id']}.jpg"); e4["Records"][0]["attributes"]["ApproximateReceiveCount"] = "4"
    assert library_ingest.handler(e4, None) == {"batchItemFailures": []}
    it = lib.get_item(A, res["id"])
    assert it["st"] == "ready" and it["nov"] is True and f"{A}:{res['id']}" not in env.data   # kept, to be indexed later


def test_the_sweeper_releases_slots_that_never_got_a_file_and_finishes_forgotten_ones(env):
    data = jpeg()
    gone = lib.create_slots(A, [{"size": 1234, "sha256": "b" * 64}], consume=lambda u: None)["uploads"][0]["id"]
    late = lib.create_slots(A, [{"size": len(data), "sha256": sha(data)}], consume=lambda u: None)["uploads"][0]["id"]
    boto3.client("s3", region_name="us-west-2").put_object(Bucket="media-bucket", Key=lib.orig_key(A, late), Body=data)
    old = "2020-01-01T00:00:00"
    for m in (gone, late):
        lib.table().update_item(Key={"user_id": A, "sk": f"m#{m}"}, UpdateExpression="SET created = :c", ExpressionAttributeValues={":c": old})
    assert library_sweeper.handler({}, None) == {"released": 1, "processed": 1}
    assert lib.get_item(A, gone, ready_only=False) is None and lib.get_item(A, late)["st"] == "ready" and lib.stats(A)["used"] == len(data)


# ----------------------------------------------------------------------------- isolation
def test_nobody_can_read_list_delete_or_collect_somebody_elses_photos(env):
    mine = upload(A, color=(255, 0, 0))
    code, body = call(B, "GET", "/items/{item_id}", item_id=mine)
    assert code == 404
    assert call(B, "GET", "/items")[1]["items"] == []
    assert call(B, "POST", "/items/delete", body={"ids": [mine]})[1]["deleted"] == 0
    assert lib.get_item(A, mine) is not None and f"{A}:{mine}" in env.data
    bc = call(B, "POST", "/collections", body={"name": "Mine now"})[1]["id"]
    assert call(B, "POST", "/collections/{collection_id}/items", collection_id=bc, body={"add": [mine]})[1]["added"] == 0
    ac = call(A, "POST", "/collections", body={"name": "Family"})[1]["id"]
    assert call(B, "POST", "/collections/{collection_id}/items", collection_id=ac, body={"add": [mine]})[0] == 404
    assert call(B, "GET", "/items", query={"collection": ac})[0] == 404
    assert call(B, "POST", "/collections/{collection_id}/delete", collection_id=ac)[0] == 404
    assert call(A, "GET", "/collections")[1]["collections"][0]["name"] == "Family"


def test_the_path_user_must_be_the_token_user_and_the_token_is_required(env):
    assert call(A, "GET", "/summary", path_user=B)[0] == 403
    r = library_api.handler({"httpMethod": "GET", "resource": EVENT_BASE + "/summary", "pathParameters": {"user_id": A}, "requestContext": {}}, None)
    assert r["statusCode"] == 401
    assert call("../../etc/passwd", "GET", "/summary")[0] == 403          # not a valid user id, even if a token said so
    assert call(A, "GET", "/nothing")[0] == 404


def test_a_paging_cursor_cannot_point_at_another_users_partition(env):
    ids = [upload(A, taken=f"2024-01-{d:02d}T10:00:00", color=(d * 8, 0, 0)) for d in range(1, 6)]
    theirs = upload(B, taken="2024-01-03T11:00:00", color=(0, 9, 0))
    first = lib.list_items(A, limit=2)
    assert len(first["items"]) == 2 and first["cursor"]
    forged = lib.encode_cursor(s=f"2024-01-03T11:00:00#{theirs}", k=f"m#{theirs}", user_id=B)    # even a cursor naming B's photo and B's partition
    got = lib.list_items(A, limit=10, cursor=forged)
    assert {r["user_id"] for r in got["items"]} == {A} and all(r["sk"][2:] in ids for r in got["items"])
    for bad in ("not-base64!!", lib.encode_cursor(s="x", k="y"), lib.encode_cursor(k="m#../..")):
        with pytest.raises(lib.LibraryError):
            lib.list_items(A, cursor=bad)


def test_every_vector_filter_starts_with_the_callers_id(env):
    for kw in ({}, {"ts_from": 1.0}, {"countries": ["Spain"]}, {"places": ["Madrid, Spain"], "countries": ["France"], "ts_to": 9.0}):
        f = search.vector_filter(A, **kw)
        assert f["$and"][0] == {"user": {"$eq": A}}
    with pytest.raises(lib.LibraryError):
        search.vector_filter("a' OR '1'='1")


def test_a_foreign_vector_in_a_result_is_dropped_and_never_shown(env, monkeypatch):
    mine = upload(A, color=(255, 0, 0))
    theirs = upload(B, color=(255, 0, 0))
    real = env.query_vectors
    env.query_vectors = lambda **kw: {"vectors": [{"key": f"{B}:{theirs}", "distance": 0.0}, {"key": f"{A}:{mine}", "distance": 0.1}, {"key": f"{A}:{theirs}", "distance": 0.1}]}
    out = search.search(A, "red things", ask=lambda s, u: '{"text": "red", "from": null, "to": null, "places": []}')
    assert [i["id"] for i in out["items"]] == [mine]      # B's vector dropped, and A:theirs is not A's row
    env.query_vectors = real


# ----------------------------------------------------------------------------- listing and search
def _trip(env):
    ids = {}
    ids["th1"] = upload(A, taken="2024-07-14T10:00:00", lat=7.88, lon=98.39, color=(255, 0, 0))     # Phuket
    ids["th2"] = upload(A, taken="2024-07-15T10:00:00", lat=13.75, lon=100.5, color=(0, 255, 0))    # Bangkok
    ids["fr"] = upload(A, taken="2024-08-02T10:00:00", lat=48.86, lon=2.35, color=(0, 0, 255))      # Paris
    ids["th23"] = upload(A, taken="2023-03-01T10:00:00", lat=13.75, lon=100.5, color=(250, 5, 5))
    ids["undated"] = upload(A, color=(10, 10, 10))
    return ids


def test_the_timeline_is_newest_first_filters_by_date_and_place_and_pages(env):
    ids = _trip(env)
    allv = lib.list_items(A, limit=100)["items"]
    assert allv[0]["sk"][2:] == ids["undated"]     # no capture time: it sorts by the day it was added (today)
    order = [r["srt"] for r in allv]
    assert order == sorted(order, reverse=True) and len(allv) == 5
    y24 = lib.list_items(A, date_from="2024-01-01", date_to="2024-12-31")["items"]
    assert {r["sk"][2:] for r in y24} == {ids["th1"], ids["th2"], ids["fr"]}
    th = lib.list_items(A, countries=["Thailand"], date_from="2024-01-01", date_to="2024-12-31")["items"]
    assert [r["sk"][2:] for r in th] == [ids["th2"], ids["th1"]]
    p1 = lib.list_items(A, limit=2)
    p2 = lib.list_items(A, limit=2, cursor=p1["cursor"])
    p3 = lib.list_items(A, limit=2, cursor=p2["cursor"])
    seen = [r["sk"] for r in p1["items"] + p2["items"] + p3["items"]]
    assert len(seen) == 5 == len(set(seen)) and p3["cursor"] is None
    with pytest.raises(lib.LibraryError):
        lib.list_items(A, date_from="July")


def test_a_question_that_only_names_a_place_and_a_year_returns_the_whole_filtered_timeline(env):
    ids = _trip(env)
    asked = {}
    def ask(system, user):
        asked["user"] = user
        return '{"text": "", "from": "2024-01-01", "to": "2024-12-31", "places": ["Thailand", "Atlantis"]}'
    out = search.search(A, "videos of my holidays in Thailand in 2024", ask=ask, today="2026-11-25")
    assert out["mode"] == "timeline" and [i["id"] for i in out["items"]] == [ids["th2"], ids["th1"]]
    assert out["understood"]["places"] == ["Thailand"] and {"kind": "place", "label": "Thailand"} in out["understood"]["chips"] and {"kind": "date", "label": "2024"} in out["understood"]["chips"]
    assert "Thailand" in asked["user"] and "2026-11-25" in asked["user"]
    dropped = search.search(A, "videos of my holidays in Thailand in 2024", ask=ask, drop=["2024"])
    assert {i["id"] for i in dropped["items"]} == {ids["th1"], ids["th2"], ids["th23"]} and all(c["kind"] != "date" for c in dropped["understood"]["chips"])


def test_a_visual_question_runs_a_semantic_search_with_the_filters_and_only_your_photos(env):
    ids = _trip(env)
    other = upload(B, color=(255, 0, 0))
    out = search.search(A, "red things in Thailand", ask=lambda s, u: '{"text": "red", "from": null, "to": null, "places": ["Thailand"]}')
    assert out["mode"] == "semantic" and [i["id"] for i in out["items"]][0] == ids["th1"] and other not in [i["id"] for i in out["items"]]
    assert {i["id"] for i in out["items"]} == {ids["th1"], ids["th2"], ids["th23"]}      # Thailand only; the red Paris-less photos outside it are not there
    assert env.queries[-1]["$and"][0] == {"user": {"$eq": A}}
    assert out["items"][0]["score"] > out["items"][1]["score"]


def test_without_the_model_the_question_is_still_understood_and_a_model_cannot_invent_filters(env):
    _trip(env)
    out = search.search(A, "Thailand 2024", ask=lambda s, u: (_ for _ in ()).throw(RuntimeError("down")))
    assert out["mode"] == "timeline" and len(out["items"]) == 2
    inj = search.search(A, "red", ask=lambda s, u: '{"text": "red", "from": "yesterday", "to": "2099-13-45", "places": ["../../x", "Paris, France"]}')
    assert inj["understood"]["from"] is None and inj["understood"]["to"] is None and inj["understood"]["places"] == ["Paris, France"]      # a place only counts when the library has it
    with pytest.raises(lib.LibraryError):
        search.search(A, "   ")
    with pytest.raises(lib.LibraryError):
        search.search(A, "x" * 400)


# ----------------------------------------------------------------------------- collections
def test_collections_hold_a_photo_in_several_places_list_in_time_order_and_keep_counts(env):
    a, b, c = (upload(A, taken=f"2024-05-0{d}T09:00:00", color=(d * 20, 0, 0)) for d in (1, 2, 3))
    fam = call(A, "POST", "/collections", body={"name": "  Family  ", "emoji": "👪"})[1]
    assert fam["name"] == "Family" and fam["emoji"] == "👪" and fam["count"] == 0
    trip = call(A, "POST", "/collections", body={"name": "Trip"})[1]
    r = call(A, "POST", "/collections/{collection_id}/items", collection_id=fam["id"], body={"add": [a, b, c, a, "0" * 16]})[1]
    assert r["added"] == 3 and r["collection"]["count"] == 3
    call(A, "POST", "/collections/{collection_id}/items", collection_id=trip["id"], body={"add": [b]})
    listing = call(A, "GET", "/items", query={"collection": fam["id"]})[1]["items"]
    assert [i["id"] for i in listing] == [c, b, a] and sorted(listing[1]["collections"]) == sorted([fam["id"], trip["id"]])
    assert call(A, "POST", "/collections/{collection_id}/items", collection_id=fam["id"], body={"add": [a]})[1]["added"] == 0     # already there
    assert call(A, "POST", "/collections/{collection_id}/items", collection_id=fam["id"], body={"remove": [a]})[1]["collection"]["count"] == 2
    renamed = call(A, "POST", "/collections/{collection_id}", collection_id=fam["id"], body={"name": "Family 2", "emoji": None})[1]
    assert renamed["name"] == "Family 2" and renamed["count"] == 2 and "emoji" not in renamed
    call(A, "POST", "/collections/{collection_id}/delete", collection_id=fam["id"])
    assert [x["name"] for x in call(A, "GET", "/collections")[1]["collections"]] == ["Trip"]
    assert lib.get_item(A, b)["cols"] == {trip["id"]} and lib.get_item(A, a) is not None
    for bad in ({"name": ""}, {"name": "x" * 41}, {"name": "ok", "emoji": "x" * 20}):
        assert call(A, "POST", "/collections", body=bad)[0] == 400


# ----------------------------------------------------------------------------- delete
def test_deleting_removes_the_file_the_thumbnail_the_vector_the_rows_the_counts_and_the_dedupe_claim(env):
    data = jpeg()
    mid = upload(A, data, taken="2024-07-14T10:00:00", lat=7.88, lon=98.39)
    keep = upload(A, taken="2024-07-15T10:00:00", color=(0, 200, 0))
    col = call(A, "POST", "/collections", body={"name": "X"})[1]["id"]
    call(A, "POST", "/collections/{collection_id}/items", collection_id=col, body={"add": [mid]})
    s3c = boto3.client("s3", region_name="us-west-2")
    assert call(A, "POST", "/items/delete", body={"ids": [mid]})[1]["deleted"] == 1
    for k in (lib.orig_key(A, mid), lib.thumb_key(A, mid)):
        with pytest.raises(Exception):
            s3c.head_object(Bucket="media-bucket", Key=k)
    assert f"{A}:{mid}" not in env.data and f"{A}:{keep}" in env.data
    assert lib.get_item(A, mid, ready_only=False) is None and lib.stats(A)["n"] == 1
    assert lib.stats(A)["used"] == lib.get_item(A, keep)["size_b"]
    assert lib.facets(A)["c"] == {} and call(A, "GET", "/collections")[1]["collections"][0]["count"] == 0
    assert lib.create_slots(A, [{"size": len(data), "sha256": sha(data)}], consume=lambda u: None)["uploads"][0]["status"] == "upload"      # the same photo can be added again


def test_delete_everything_needs_the_word_and_leaves_nothing_of_the_account_and_nothing_of_others(env):
    mine = [upload(A, color=(i * 30, 0, 0)) for i in range(1, 4)]
    theirs = upload(B, color=(0, 50, 0))
    call(A, "POST", "/collections", body={"name": "C"})
    assert call(A, "POST", "/delete-all", body={})[0] == 400
    code, out = call(A, "POST", "/delete-all", body={"confirm": "DELETE"})
    assert code == 200 and out["photos"] == 3 and out["objects"] == 6
    s3c = boto3.client("s3", region_name="us-west-2")
    assert "Contents" not in s3c.list_objects_v2(Bucket="media-bucket", Prefix=f"o/{A}/") and "Contents" not in s3c.list_objects_v2(Bucket="media-bucket", Prefix=f"t/{A}/")
    assert lib.table().query(KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(A))["Items"] == []
    assert not [k for k in env.data if k.startswith(A)] and lib.get_item(B, theirs) is not None and f"{B}:{theirs}" in env.data
    assert call(A, "GET", "/summary")[1]["count"] == 0


def test_summary_and_links(env):
    _trip(env)
    code, s = call(A, "GET", "/summary")
    assert code == 200 and s["plan"] == "free" and s["limit_bytes"] == 2 * lib.GB and s["count"] == 5 and s["can_upgrade"] is False
    assert s["years"] == [{"year": datetime_year(), "count": 1}, {"year": 2024, "count": 3}, {"year": 2023, "count": 1}]
    assert {p["name"] for p in s["places"]} == {"Bangkok, Thailand", "Paris, France", "Phuket, Thailand"} and {c["name"] for c in s["countries"]} == {"Thailand", "France"}
    one = call(A, "GET", "/items", query={"limit": "1"})[1]["items"][0]
    assert "X-Amz-Signature" in one["thumb_url"] and f"t/{A}/" in one["thumb_url"] and "url" not in one
    full = call(A, "GET", "/items/{item_id}", item_id=one["id"])[1]
    assert f"o/{A}/" in full["url"] and "X-Amz-Expires=600" in full["url"]


def datetime_year():
    import datetime
    return datetime.date.today().year


# ----------------------------------------------------------------------------- using library photos in a video
from tests.test_hardening import _event, launcher  # noqa: E402,F401


def test_a_video_can_use_library_photos_only_of_the_caller_and_they_arrive_with_time_and_place(launcher, monkeypatch):    # noqa: F811
    import sf_launcher

    _setup_media(monkeypatch)
    monkeypatch.setenv("ASSETS_BUCKET", "assets-bucket")
    s3c = boto3.client("s3", region_name="us-west-2")
    s3c.create_bucket(Bucket="assets-bucket", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    sf_launcher._s3 = s3c
    one = upload(A, taken="2024-07-14T10:00:00", lat=7.88, lon=98.39)
    two = upload(A, color=(10, 200, 10))
    theirs = upload(B, color=(1, 2, 3))

    def go(ids, rid, user=A, extra=None):
        body = {"prompt": "Our holidays in Thailand last summer", "target_minutes": 1, "client_request_id": rid, "library_media": ids, **(extra or {})}
        return launcher.handler(_event(user=user, body=body), None)

    ok = go([one, two], "library-test-001")
    assert ok["statusCode"] == 202
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert sent["media"] == [one, two] and "library_media" not in sent
    assert sent["media_meta"][one]["taken"] == "2024-07-14T10:00:00" and "Thailand" in sent["media_meta"][one]["where"] and two not in sent["media_meta"]
    assert not any(k in json.dumps(sent) for k in ("lat", "lon"))
    for mid in (one, two):                                   # copied into the video's own uploads, under the caller's folder
        assert s3c.head_object(Bucket="assets-bucket", Key=f"uploads/{A}/{mid}.jpg")["ContentType"] == "image/jpeg"
    assert go([theirs], "library-test-002")[ "statusCode"] == 400          # another person's photo
    assert go([one, "e" * 16], "library-test-003")["statusCode"] == 400    # not in the library
    assert go([one], "library-test-004", extra={"media": [one]})["statusCode"] == 400    # in both lists
    assert go(["f" * 16] * 101, "library-test-005")["statusCode"] == 400
    assert len(launcher.fake.calls) == 1
    with pytest.raises(Exception):
        s3c.head_object(Bucket="assets-bucket", Key=f"uploads/{B}/{theirs}.jpg")      # nothing of B's was copied


def test_a_client_cannot_inject_a_place_name_through_media_meta():
    from common import photo_ids

    ids = ["a" * 16]
    assert photo_ids.valid_media_meta({ids[0]: {"taken": "2024-01-01T10:00:00", "where": "Moon base", "lat": 1.234, "lon": 2.345}}, ids) == {ids[0]: {"taken": "2024-01-01T10:00:00", "lat": 1.23, "lon": 2.35}}


def test_the_admin_can_grant_storage_and_only_the_admin(env):
    lib.set_storage(A, "pro", 50)
    assert lib.limits(A) == {"plan": "pro", "limit_bytes": 150 * lib.GB}
    lib.set_storage(A, "free", 0, until=int(time.time()) + 1000)
    assert lib.limits(A) == {"plan": "free", "limit_bytes": 2 * lib.GB}
    with pytest.raises(ValueError):
        lib.set_storage(A, "platinum")
    for mod in (library_api, library_ingest, library_sweeper, search):          # no runtime code path writes the entitlement
        assert "set_storage" not in open(mod.__file__).read()


def test_a_place_name_from_a_library_photo_reaches_the_video_photo_and_coordinates_never_do(env):
    from engine import usermedia

    store = {}
    data = {"a" * 16: jpeg(size=(900, 700)), "b" * 16: jpeg(size=(900, 700))}
    photos, thumbs, skipped = usermedia.prepare("v1", A, list(data), get=lambda k: data[k.rsplit("/", 1)[1][:-4]], put=lambda k, b: store.__setitem__(k, b), delete=lambda k: None, asset_prefix="x/",
                                                meta={"a" * 16: {"taken": "2024-07-14T10:00:00", "where": "Phuket, Thailand"}, "b" * 16: {"where": "x" * 200}})
    assert photos[0]["where"] == "Phuket, Thailand" and photos[0]["taken"] == "2024-07-14T10:00:00" and len(photos[1]["where"]) == 80


def test_a_retry_after_an_unfinished_upload_gets_a_fresh_link_for_the_same_photo_and_a_stale_claim_is_replaced(env):
    data = jpeg()
    item = {"size": len(data), "sha256": sha(data)}
    first = lib.create_slots(A, [item], consume=lambda u: None)["uploads"][0]
    retry = lib.create_slots(A, [item], consume=lambda u: None)["uploads"][0]      # the file never arrived; the app asks again
    assert retry["status"] == "upload" and retry["id"] == first["id"] and retry["fields"]["key"] == first["fields"]["key"]
    assert lib.stats(A)["used"] == len(data)                                        # still reserved once
    boto3.client("s3", region_name="us-west-2").put_object(Bucket="media-bucket", Key=lib.orig_key(A, retry["id"]), Body=data)
    assert library_ingest.process(A, retry["id"]) == "ready"
    assert lib.create_slots(A, [item], consume=lambda u: None)["uploads"][0]["status"] == "duplicate"     # now it really is in the library
    lib.table().put_item(Item={"user_id": A, "sk": "h#" + "c" * 64, "mid": "d" * 16})                     # a claim with no photo behind it
    assert lib.create_slots(A, [{"size": 9, "sha256": "c" * 64}], consume=lambda u: None)["uploads"][0]["status"] == "upload"


def test_the_summary_says_when_the_library_is_over_its_limit_and_the_apps_get_utc_times_and_cover_thumbnails(env):
    mid = upload(A, taken="2024-07-14T10:00:00")
    col = call(A, "POST", "/collections", body={"name": "C"})[1]["id"]
    call(A, "POST", "/collections/{collection_id}/items", collection_id=col, body={"add": [mid]})
    s = call(A, "GET", "/summary")[1]
    assert s["read_only"] is False and s["collections"][0]["cover_id"] == mid and f"t/{A}/{mid}.jpg" in s["collections"][0]["cover_thumb_url"]
    lib.table().update_item(Key={"user_id": A, "sk": "stats"}, UpdateExpression="SET used = :u", ExpressionAttributeValues={":u": 3 * lib.GB})
    assert call(A, "GET", "/summary")[1]["read_only"] is True
    one = call(A, "GET", "/items")[1]["items"][0]
    assert one["added"].endswith("Z") and one["taken"] == "2024-07-14T10:00:00"


def test_embeddings_use_cohere_with_the_right_request_for_queries_and_for_photos(monkeypatch):
    calls = []

    class FakeBedrock:
        def invoke_model(self, modelId, body):
            calls.append((modelId, json.loads(body)))
            return {"body": io.BytesIO(json.dumps({"embeddings": {"float": [[0.5] * 1024]}}).encode())}

    monkeypatch.setattr(search, "_bedrock", lambda: FakeBedrock())
    from importlib import reload
    assert "cohere.embed-v4" in search.EMBED_MODEL and not search.EMBED_MODEL.startswith("amazon.")
    assert len(search.embed_text("a red car")) == 1024 and len(search.embed_image(jpeg())) == 1024
    (m1, q), (m2, d) = calls
    assert m1 == m2 == search.EMBED_MODEL
    assert q["input_type"] == "search_query" and q["texts"] == ["a red car"] and q["embedding_types"] == ["float"] and q["output_dimension"] == 1024
    assert d["input_type"] == "search_document" and d["images"][0].startswith("data:image/jpeg;base64,") and d["output_dimension"] == 1024
