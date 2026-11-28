"""A deleted video or account takes its shared link with it (common/share_revoke.py); no error when sharing is not set up."""
import boto3
import pytest
from moto import mock_aws

from common import share_revoke
from share import share_page

SHARE = "videomk-qa-share-bucket"


@pytest.fixture
def shared(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket=SHARE, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        tok = share_page.new_token()
        for n in share_page.FILES:
            s3.put_object(Bucket=SHARE, Key=f"{tok}/{n}", Body=b"x")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
        monkeypatch.delenv("DISTRIBUTION_ID", raising=False)
        yield s3, tok


def _left(s3):
    return [o["Key"] for o in s3.list_objects_v2(Bucket=SHARE).get("Contents", [])]


def test_revoke_item_deletes_the_shared_files(shared, monkeypatch):
    s3, tok = shared
    monkeypatch.setenv("SHARE_BUCKET", SHARE)
    assert share_revoke.revoke_item({"share_token": tok}, s3=s3) is True
    assert _left(s3) == []


def test_off_when_share_bucket_is_absent_or_no_token(shared, monkeypatch):
    s3, tok = shared
    monkeypatch.delenv("SHARE_BUCKET", raising=False)
    assert share_revoke.revoke_item({"share_token": tok}, s3=s3) is False and len(_left(s3)) == 4
    monkeypatch.setenv("SHARE_BUCKET", SHARE)
    assert share_revoke.revoke_item({}, s3=s3) is False
    assert share_revoke.revoke_item({"share_token": "../x"}, s3=s3) is False
    assert len(_left(s3)) == 4


def test_a_failure_is_swallowed(monkeypatch, caplog):
    monkeypatch.setenv("SHARE_BUCKET", SHARE)

    class Boom:
        def delete_objects(self, **kw):
            raise RuntimeError("down")
    assert share_revoke.revoke_item({"share_token": share_page.new_token()}, s3=Boom()) is False
    assert "SHARE_REVOKE_FAILED" in caplog.text


def test_video_delete_calls_it_before_the_row_goes(monkeypatch):
    import video_retry
    calls = []
    monkeypatch.setattr(video_retry.share_revoke, "revoke_item", lambda item, s3=None, strict=False: calls.append(item) or True)
    src = open(video_retry.__file__).read()
    assert src.index("share_revoke.revoke_item(item, strict=True)") < src.index('_table().delete_item(Key={"video_id": video_id}, ConditionExpression="user_id = :u AND #s = :was"')


def test_account_step_videos_revokes_every_shared_row(monkeypatch):
    from common import deletion
    seen = []
    monkeypatch.setattr(deletion, "_video_rows", lambda u, b: [{"video_id": "a", "user_id": "u1", "share_token": "T1"}, {"video_id": "b", "user_id": "u1"}])
    monkeypatch.setattr(deletion, "_video_ids", lambda u, r, b: [])
    monkeypatch.setattr(deletion, "_s3_delete_prefix", lambda *a, **k: 0)
    monkeypatch.setattr(deletion, "_delete_keys", lambda *a, **k: 0)
    monkeypatch.setattr(deletion, "_env", lambda n: "x")

    class T:
        def Table(self, n):
            return None
    monkeypatch.setattr(deletion, "ddb", lambda: T())
    monkeypatch.setattr(share_revoke, "revoke_item", lambda item, s3=None, strict=False: seen.append(item["share_token"]) or True)
    deletion.step_videos("u1", deletion.Budget())
    assert seen == ["T1"]
