"""User feedback (docs/FEEDBACK.md): the API function, the daily email function and the account-deletion step, with moto and a fake SES."""
import json
import logging
import os

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

import feedback_api
import feedback_digest as dg
from common import deletion, feedback

USER = "11111111-aaaa-bbbb-cccc-222222222222"
OTHER = "99999999-aaaa-bbbb-cccc-222222222222"


class FakeSes:
    def __init__(self, fail_on=None):
        self.sent, self.fail_on, self.n = [], fail_on, 0

    def send_email(self, **kw):
        self.n += 1
        if self.fail_on == self.n:
            raise ClientError({"Error": {"Code": "MessageRejected"}}, "SendEmail")
        self.sent.append(kw)


@pytest.fixture
def world(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        ddb.create_table(
            TableName="Feedback", KeySchema=[{"AttributeName": "feedbackId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("feedbackId", "pending", "userId")], BillingMode="PAY_PER_REQUEST",
            GlobalSecondaryIndexes=[
                {"IndexName": "GSI_Pending", "KeySchema": [{"AttributeName": "pending", "KeyType": "HASH"}, {"AttributeName": "feedbackId", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}},
                {"IndexName": "GSI_User", "KeySchema": [{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "feedbackId", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "KEYS_ONLY"}}])
        ddb.create_table(TableName="UsageFb", KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "day", "KeyType": "RANGE"}],
                         AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}, {"AttributeName": "day", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
        monkeypatch.setenv("FEEDBACK_TABLE", "Feedback")
        monkeypatch.setenv("USAGE_TABLE", "UsageFb")
        monkeypatch.setenv("FEEDBACK_FROM", "hello@videomk.com")
        feedback.set_resource(ddb)
        w = type("W", (), {})()
        w.ddb, w.table = ddb, ddb.Table("Feedback")
        w.ssm = boto3.client("ssm", region_name="us-west-2")
        w.ses = FakeSes()
        monkeypatch.setattr(dg, "_ddb", ddb)
        monkeypatch.setattr(dg, "_ssm", w.ssm)
        monkeypatch.setattr(dg, "_ses", w.ses)
        yield w
        feedback.set_resource(None)


def call(body, user=USER, path_user=None, headers=None, raw=None):
    ev = {"body": raw if raw is not None else json.dumps(body), "pathParameters": {"user_id": path_user or user}, "headers": headers or {},
          "requestContext": {"authorizer": {"claims": {"sub": user}}}}
    return feedback_api.handler(ev, None)


def good(**kw):
    return {"text": "Please add dark mode", "kind": "idea", "app": "ios", "version": "1.4", "locale": "en", "context": "settings", **kw}


# ----------------------------------------------------------------------------- API
def test_accepts_and_stores_the_item_verbatim(world):
    r = call(good(text="  Hola‮ mundo\x00\nsegunda línea <b>x</b>  "))
    assert r["statusCode"] == 202 and json.loads(r["body"]) == {"ok": True}
    (it,) = world.table.scan()["Items"]
    assert it["text"] == "Hola mundo\nsegunda línea <b>x</b>"   # controls and bidi override gone, markup kept as text
    assert it["userId"] == USER and it["kind"] == "idea" and it["app"] == "ios" and it["version"] == "1.4" and it["locale"] == "en" and it["context"] == "settings"
    assert it["category"] == "" and it["status"] == "new" and it["pending"] == "1" and "emailedAt" not in it
    assert len(it["feedbackId"]) == 26 and it["createdAt"].endswith("Z")


def test_optional_fields_default(world):
    assert call({"text": "abc", "app": "web"})["statusCode"] == 202
    (it,) = world.table.scan()["Items"]
    assert it["kind"] == "other" and it["version"] == "" and it["locale"] == "" and it["context"] == ""


@pytest.mark.parametrize("body", [
    good(text="ab"), good(text="   \n\t  "), good(text="x" * 2001), good(text=5), {"app": "web"}, good(kind="nope"), good(app="tv"), {"text": "hello"}, good(locale="fr"),
    good(version="v" * 33), good(version=3), good(context="c" * 65), good(context=["x"]), [], "text"])
def test_bad_input_is_400_and_nothing_stored(world, body):
    r = call(body)
    assert r["statusCode"] == 400 and "message" in json.loads(r["body"])
    assert world.table.scan()["Items"] == []


def test_boundaries_and_non_json(world):
    assert call(good(text="abc"))["statusCode"] == 202
    assert call(good(text="x" * 2000))["statusCode"] == 202
    assert call(None, raw="not json")["statusCode"] == 400
    assert call(None, raw="x" * 20000)["statusCode"] == 400


def test_spanish_error_text(world):
    r = call(good(text="a"), headers={"X-Locale": "es"})
    assert r["statusCode"] == 400 and "caracteres" in json.loads(r["body"])["message"]


def test_user_must_be_the_token_subject(world):
    assert call(good(), path_user=OTHER)["statusCode"] == 403
    assert feedback_api.handler({"body": json.dumps(good()), "pathParameters": {"user_id": USER}, "requestContext": {}}, None)["statusCode"] == 401
    assert world.table.scan()["Items"] == []


def test_rate_limit_ten_an_hour_then_429(world):
    for _ in range(10):
        assert call(good())["statusCode"] == 202
    r = call(good())
    assert r["statusCode"] == 429 and json.loads(r["body"])["code"] == "rate_limited" and r["headers"]["Retry-After"]
    assert call(good(), user=OTHER)["statusCode"] == 202   # per user
    assert len(world.table.scan()["Items"]) == 11


def test_rate_limit_thirty_a_day_and_the_hour_slot_is_given_back(world):
    base = 1_800_000_000
    for i in range(30):   # three clock hours of ten
        feedback.take_slot(USER, now=base + (i // 10) * 3600)
    with pytest.raises(feedback.FeedbackError) as e:
        feedback.take_slot(USER, now=base + 3 * 3600)
    assert e.value.status == 429
    # the refused request gave its hour slot back, so the hour stays at 0 and a request in the same hour is refused for the day limit, not the hour limit
    h = world.ddb.Table("UsageFb").scan()["Items"]
    assert max(int(i["count"]) for i in h if i["user_id"].startswith("feedbackh:")) == 10
    assert [int(i["count"]) for i in h if i["user_id"].startswith("feedback:")] == [30]


def test_the_text_is_never_logged(world, caplog):
    caplog.set_level(logging.INFO)
    call(good(text="SECRET-WORDS-123 hello"))
    assert "SECRET-WORDS" not in caplog.text and "FEEDBACK_STORED" in caplog.text and USER not in caplog.text


def test_ids_sort_by_time():
    a, b = feedback.new_id(1_000_000), feedback.new_id(1_000_001)
    assert a < b and len(a) == 26


# ----------------------------------------------------------------------------- digest
def put_param(w, value="owner@example.com"):
    w.ssm.put_parameter(Name="/videomk/feedback_email_to", Value=value, Type="String")


def seed(w, n, **kw):
    for i in range(n):
        feedback.store(USER, {"text": f"msg {i}", "kind": kw.get("kind", "idea"), "app": "ios", "version": "1.0", "locale": "es", "context": "settings"}, now=1_800_000_000 + i)


def test_no_new_feedback_sends_nothing(world):
    put_param(world)
    assert dg.handler() == {"sent": 0} and world.ses.sent == []


def test_sends_one_email_grouped_with_count_and_marks_after(world):
    put_param(world)
    seed(world, 2, kind="idea")
    feedback.store(OTHER, {"text": "it crashes\nat start", "kind": "problem", "app": "android", "version": "2.1", "locale": "en", "context": ""}, now=1_800_000_100)
    assert dg.handler() == {"sent": 3, "emails": 1}
    (m,) = world.ses.sent
    assert m["Destination"] == {"ToAddresses": ["owner@example.com"]} and m["Source"] == "hello@videomk.com"
    assert m["Message"]["Subject"]["Data"] == "videomk feedback: 3 new"
    body = m["Message"]["Body"]["Text"]["Data"]
    assert "Html" not in m["Message"]["Body"]
    assert body.index("=== problem (1)") < body.index("=== idea (2)")
    assert "android 2.1" in body and "locale es" in body and "it crashes" in body and "user " + feedback.user_hash(OTHER) in body
    assert USER not in body and "@" not in body.replace("owner@example.com", "")
    items = world.table.scan()["Items"]
    assert all(i.get("emailedAt") and "pending" not in i for i in items)
    assert dg.handler() == {"sent": 0} and len(world.ses.sent) == 1   # the next day: nothing new, no email


def test_only_items_new_since_the_last_email_are_listed(world):
    put_param(world)
    seed(world, 1)
    dg.handler()
    seed(world, 1)
    dg.handler()
    assert "1 new" in world.ses.sent[1]["Message"]["Subject"]["Data"] and len(world.ses.sent) == 2


def test_send_failure_marks_nothing(world):
    put_param(world)
    seed(world, 3)
    world.ses.fail_on = 1
    with pytest.raises(ClientError):
        dg.handler()
    assert all("pending" in i and "emailedAt" not in i for i in world.table.scan()["Items"])
    world.ses.fail_on = None
    assert dg.handler()["sent"] == 3


def test_large_batches_are_split_and_marked_part_by_part(world, monkeypatch):
    put_param(world)
    monkeypatch.setattr(dg, "MAX_ITEMS_PER_EMAIL", 4)
    seed(world, 10)
    world.ses.fail_on = 3   # the third part fails: the first two stay marked
    with pytest.raises(ClientError):
        dg.handler()
    assert sorted(i.get("emailedAt") is not None for i in world.table.scan()["Items"]).count(True) == 8
    assert [m["Message"]["Subject"]["Data"] for m in world.ses.sent] == ["videomk feedback: 10 new (part 1/3)", "videomk feedback: 10 new (part 2/3)"]
    world.ses.fail_on = None
    assert dg.handler() == {"sent": 2, "emails": 1}


def test_missing_parameter_does_nothing_with_a_warning(world, caplog):
    seed(world, 1)
    caplog.set_level(logging.WARNING)
    assert dg.handler() == {"sent": 0, "skipped": "no_recipient"} and world.ses.sent == []
    assert "FEEDBACK_DIGEST_NO_RECIPIENT" in caplog.text
    assert "pending" in world.table.scan()["Items"][0]


def test_bad_parameter_value_and_no_sender(world, monkeypatch):
    seed(world, 1)
    put_param(world, "not an address")
    assert dg.handler()["skipped"] == "no_recipient"
    world.ssm.put_parameter(Name="/videomk/feedback_email_to", Value="a@b.co", Type="String", Overwrite=True)
    monkeypatch.setenv("FEEDBACK_FROM", "")
    assert dg.handler()["skipped"] == "no_sender" and world.ses.sent == [] and "pending" in world.table.scan()["Items"][0]


# ----------------------------------------------------------------------------- account deletion
def test_deletion_keeps_the_text_and_cuts_the_user_link(world, monkeypatch):
    deletion.reset_clients()
    deletion.set_key(b"k" * 32)
    monkeypatch.setenv("FEEDBACK_TABLE", "Feedback")
    deletion.set_client("ddb", world.ddb)
    seed(world, 2)
    feedback.store(OTHER, {"text": "other person", "kind": "idea", "app": "web", "version": "", "locale": "", "context": ""})
    assert deletion.step_feedback(USER, deletion.Budget()) == {"rows": 2}
    items = {i["text"]: i for i in world.table.scan()["Items"]}
    assert items["msg 0"]["userId"] == f"deleted:{deletion.account_ref(USER)}" and items["msg 1"]["userId"].startswith("deleted:")
    assert USER not in json.dumps(list(items.values()), default=str)
    assert items["other person"]["userId"] == OTHER
    assert deletion.step_feedback(USER, deletion.Budget()) == {"rows": 0}   # idempotent
    monkeypatch.delenv("FEEDBACK_TABLE")
    assert deletion.step_feedback(USER, deletion.Budget()) == {"skipped": 1}
    deletion.reset_clients()
    deletion.set_key(None)
