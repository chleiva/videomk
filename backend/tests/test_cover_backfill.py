"""scripts/cover_backfill.py on fake AWS: dry run writes nothing, apply writes both JPEGs and the row once, covered videos are left alone."""
import io
import os
import sys

import boto3
import pytest
from moto import mock_aws
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "lambdas"))
import cover_backfill as cb  # noqa: E402

B = "videomk-qa-1"


def gif_bytes(size=(320, 180)):
    frames = [Image.new("RGB", size, c) for c in ((255, 255, 255), (200, 220, 255), (255, 240, 200))]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=200)
    return buf.getvalue()


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket=B, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        d = boto3.resource("dynamodb", region_name="us-west-2")
        t = d.create_table(TableName="V", KeySchema=[{"AttributeName": "video_id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "video_id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")

        def add(vid, user="u1", status="COMPLETE", gif=True, **extra):
            item = {"video_id": vid, "user_id": user, "status": status, "title": "How tides work", "aspect": "16:9", "final_rev": 1, **extra}
            if gif:
                k = f"videos/{user}/{vid}/r1.gif"
                s3.put_object(Bucket=B, Key=k, Body=gif_bytes())
                item["preview_gif_uri"] = f"s3://{B}/{k}"
            t.put_item(Item=item)
        yield s3, t, add


def keys(s3):
    return sorted(o["Key"] for o in s3.list_objects_v2(Bucket=B).get("Contents", []))


def test_dry_run_writes_nothing(aws):
    s3, t, add = aws
    add("a")
    before = keys(s3)
    c = cb.run(cb.scan_items(t), s3, t, apply=False, log=lambda m: None)
    assert c["would"] == 1 and keys(s3) == before and "cover_uri" not in t.get_item(Key={"video_id": "a"})["Item"]


def test_apply_writes_both_jpegs_and_the_row_then_a_second_run_leaves_it(aws):
    s3, t, add = aws
    add("a")
    slept = []
    c = cb.run(cb.scan_items(t), s3, t, apply=True, rate=2, sleep=slept.append, log=lambda m: None)
    assert c["done"] == 1 and slept == [0.5]
    item = t.get_item(Key={"video_id": "a"})["Item"]
    assert item["cover_uri"] == f"s3://{B}/videos/u1/a/r1_cover.jpg" and item["cover_og_uri"].endswith("r1_og.jpg")
    og = Image.open(io.BytesIO(s3.get_object(Bucket=B, Key="videos/u1/a/r1_og.jpg")["Body"].read()))
    assert og.size == (1200, 630)
    c2 = cb.run(cb.scan_items(t), s3, t, apply=True, log=lambda m: None)
    assert c2["has_cover"] == 1 and c2.get("done", 0) == 0


def test_skips_unfinished_no_gif_and_foreign_gif(aws):
    s3, t, add = aws
    add("making", status="ASSETS_CREATION")
    add("nogif", gif=False)
    add("evil", gif=False, preview_gif_uri=f"s3://{B}/videos/other/x/r1.gif")
    add("done", cover_uri="s3://x/a", cover_og_uri="s3://x/b")
    c = cb.run(cb.scan_items(t), s3, t, apply=True, log=lambda m: None)
    assert (c["not_ready"], c["no_gif"], c["unsafe"], c["has_cover"]) == (1, 1, 1, 1) and not [k for k in keys(s3) if "cover" in k or "_og" in k]


def test_vertical_video_and_limit_and_one_failure_does_not_stop(aws):
    s3, t, add = aws
    add("v", aspect="9:16")
    add("w")
    add("bad", gif=False, preview_gif_uri=f"s3://{B}/videos/u1/bad/r1.gif")   # object missing -> failure, counted
    c = cb.run(cb.scan_items(t), s3, t, apply=True, rate=0, log=lambda m: None)
    assert c["done"] == 2 and c["failed"] == 1
    c = cb.run(iter([{"video_id": "z", "user_id": "u1", "status": "COMPLETE"}] * 3), s3, t, apply=False, limit=2, log=lambda m: None)
    assert c["no_gif"] == 2
