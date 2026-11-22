"""The full v2 pipeline through the real Lambda handlers, against moto S3/DynamoDB.
LLM, Wikipedia and Openverse are stubbed; TTS is the mock provider; rendering/ffmpeg are real."""
import io
import json
import os

import boto3
import pytest
from PIL import Image

from common import usage
from engine import assets, costs, llm, research
from engine.handlers import (audio_handler, beat_handler, finalize_handler, plan_handler, render_chunk_handler, timeline_handler)
from tests.tests_helpers import PLAN_WITH_IMAGE


@pytest.fixture
def pipeline_env(aws, monkeypatch):
    boto3.client("s3", region_name="us-west-2").create_bucket(Bucket="videomk.com", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("ASSETS_BUCKET", "videomk.com")
    monkeypatch.setattr(finalize_handler, "OUTPUT_BUCKET", "videomk.com")
    monkeypatch.setattr(research, "gather_notes", lambda topic, **k: ("notes", [{"title": "Rainbow", "url": "https://en.wikipedia.org/wiki/Rainbow", "publisher": "Wikipedia"}]))
    buf = io.BytesIO()
    Image.new("RGB", (3000, 1700), (90, 140, 210)).save(buf, "JPEG")
    monkeypatch.setattr(assets, "scout", lambda q, **k: (buf.getvalue(), {"source": "openverse", "id": "1", "title": "Sky", "creator": "Ann", "license": "BY 4.0", "license_url": "", "landing_url": "https://l/1", "attribution": '"Sky" by Ann, CC BY 4.0'}))
    return aws


def _start(aws, video_id="vid1"):
    day = usage._today()
    usage.consume("u1", limit=5)
    aws.Table("Videos").put_item(Item={"video_id": video_id, "user_id": "u1", "usage_day": day, "status": "STARTED_PROCESSING"})
    return {"user_id": "u1", "video_id": video_id, "prompt": "How do rainbows form?", "usage_day": day}


def test_full_pipeline_produces_a_playable_video_with_credits(pipeline_env, monkeypatch):
    aws = pipeline_env
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: (json.dumps(PLAN_WITH_IMAGE), {"model": "m", "cost_usd": 0.01, "tokens_in": 1, "tokens_out": 1}))
    ev = _start(aws)

    out = plan_handler.handler(ev, None)
    assert out["plot"]["legit"] and out["beat_indices"] == [0, 1, 2, 3]

    beats = [beat_handler.handler({"video_id": ev["video_id"], "i": i}, None) for i in out["beat_indices"]]
    assert all(b["duration"] > 0.5 for b in beats)
    assert beats[3]["asset"].startswith("generation/v2/vid1/assets/") and "Ann" in beats[3]["credit"]

    tl_out = timeline_handler.handler({**out, "beats": beats}, None)
    assert tl_out["chunks"] and all(c["f0"] % 60 == 0 for c in tl_out["chunks"])

    segs = [render_chunk_handler.handler({**c, "draft": True}, None) for c in tl_out["chunks"]]
    aud = audio_handler.handler({"video_id": "vid1", "timeline_key": tl_out["timeline_key"]}, None)
    fin = finalize_handler.handler({**tl_out, "render": {"segments": segs, "audio": aud}}, None)
    assert fin["status"] == "COMPLETE"

    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["status"] == "COMPLETE" and item["title"] == PLAN_WITH_IMAGE["title"]
    assert item["video_uri"] == "s3://videomk.com/videos/u1/vid1.mp4" and item["duration_s"] > 5
    assert "Image credits" in item["youtube_description"] and "Wikipedia" in item["youtube_description"]
    assert float(item["cost_usd"]) > 0  # cost accounting ran

    s3 = boto3.client("s3", region_name="us-west-2")
    assert s3.head_object(Bucket="videomk.com", Key="videos/u1/vid1.mp4")["ContentLength"] > 10_000
    assert s3.head_object(Bucket="videomk.com", Key="videos/u1/vid1.gif")["ContentType"] == "image/gif"
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="videomk.com", Prefix="generation/v2/vid1/").get("Contents", [])]
    assert not any("/segments/" in k for k in keys) and "generation/v2/vid1/plan.json" in keys  # intermediates cleaned, plan kept


def test_rejected_prompt_stops_before_any_spend(pipeline_env, monkeypatch):
    aws = pipeline_env
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: ('{"legit": false, "reason": "I can\'t help with that."}', {"model": "m", "cost_usd": 0.001, "tokens_in": 1, "tokens_out": 1}))
    ev = _start(aws, "vid2")
    out = plan_handler.handler(ev, None)
    assert out["plot"] == {"legit": False, "reason": "I can't help with that."} and "plan_key" not in out
    from generate_video.handlers import mark_rejected_handler

    mark_rejected_handler.handler(out, None)
    assert aws.Table("Videos").get_item(Key={"video_id": "vid2"})["Item"]["status"] == "REJECTED"
    assert usage.consume("u1", limit=1) == 1  # quota refunded


def test_cost_cap_fails_the_job_instead_of_overspending(pipeline_env, monkeypatch):
    aws = pipeline_env
    aws.Table("Videos").put_item(Item={"video_id": "vid3", "user_id": "u1", "status": "X"})
    monkeypatch.setattr(costs, "MAX_COST_USD", 0.05)
    costs.add_cost("vid3", 0.03)
    costs.add_cost("vid3", 0.02)
    with pytest.raises(costs.CostCapExceeded):
        costs.add_cost("vid3", 0.01)


def test_chunk_handler_refuses_images_outside_its_own_prefix(pipeline_env):
    loader = render_chunk_handler.make_image_loader("vidA")
    assert loader("generation/v2/vidB/assets/img_000.jpg") is None
    assert loader("generation/v2/vidA/assets/../../vidB/assets/x.jpg") is None
    assert loader("videos/u1/secret.jpg") is None
