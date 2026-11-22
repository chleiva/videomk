"""The v2 pipeline and the editor through the real Lambda handlers, against moto S3/DynamoDB.
LLM, Wikipedia and stock APIs are stubbed; TTS is the mock provider; rendering/ffmpeg are real."""
import io
import json

import boto3
import pytest
from PIL import Image

from common import usage
from engine import costs, llm, research, stock
from engine.handlers import (audio_handler, beat_handler, edit_failed_handler, edit_prep_handler, editor_apply, editor_get, finalize_handler,
                             plan_handler, render_chunk_handler, timeline_handler)
from tests.tests_helpers import PLAN_WITH_IMAGE

pytestmark = pytest.mark.slow

USER = "u1"


def _jpeg(color):
    buf = io.BytesIO()
    Image.new("RGB", (3000, 1700), color).save(buf, "JPEG")
    return buf.getvalue()


CANDS = [
    {"provider": "unsplash", "id": "uA", "thumb_url": "https://images.unsplash.com/a?w=400", "full_url": "https://images.unsplash.com/a?w=2400", "width": 4000, "height": 2600,
     "creator": "Ann", "creator_url": "https://unsplash.com/@ann", "landing_url": "https://unsplash.com/photos/uA", "license": "Unsplash License", "alt": "rainbow", "download_location": "", "attribution": "Photo by Ann on Unsplash"},
    {"provider": "openverse", "id": "oB", "thumb_url": "https://x/b.jpg", "full_url": "https://x/b_full.jpg", "width": 3000, "height": 1800,
     "creator": "Bob", "creator_url": "", "landing_url": "https://l/b", "license": "CC0", "alt": "field", "download_location": "", "attribution": "Field by Bob"},
]


@pytest.fixture
def env(aws, monkeypatch):
    boto3.client("s3", region_name="us-west-2").create_bucket(Bucket="videomk.com", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_TTS_SPEED", "3")  # short narration => short test videos
    monkeypatch.setenv("ASSETS_BUCKET", "videomk.com")
    monkeypatch.setenv("EDIT_STATE_MACHINE_ARN", "arn:aws:states:us-west-2:123456789012:stateMachine:edit")
    monkeypatch.setattr(finalize_handler, "OUTPUT_BUCKET", "videomk.com")
    monkeypatch.setitem(costs.TTS_PER_CHAR, "mock", 0.0001)  # exercise cost accounting
    monkeypatch.setattr(research, "gather_notes", lambda topic, **k: ("notes", [{"title": "Rainbow", "url": "https://en.wikipedia.org/wiki/Rainbow", "publisher": "Wikipedia"}]))
    monkeypatch.setattr(timeline_handler, "CHUNK_SECONDS", 2)  # ~one scene per chunk even in a short test video
    calls = {"scout": 0, "fetch_full": []}

    def scout(query, narration, alt="", **k):
        calls["scout"] += 1
        return {"jpeg": _jpeg((90, 140, 210)), "entry": stock.ledger_entry(CANDS[0]), "credit": stock.credit_line(CANDS[0]), "chosen": "unsplash:uA",
                "candidates": CANDS, "review": {"cost_usd": 0.002, "source": "llm"}}

    def fetch_full(c, *a, **k):
        calls["fetch_full"].append(stock.candidate_key(c))
        return _jpeg((200, 60, 60))

    monkeypatch.setattr(stock, "scout_reviewed", scout)
    monkeypatch.setattr(stock, "fetch_full", fetch_full)
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: (json.dumps(PLAN_WITH_IMAGE), {"model": "m", "cost_usd": 0.01, "tokens_in": 1, "tokens_out": 1}))
    aws.calls = calls
    return aws


def run_tail(state):
    """What the state machine does after Plan / EditPrep: Beats(Map) -> Timeline -> Parallel{Chunks(Map), Audio} -> Finalize."""
    beats = [beat_handler.handler({"video_id": state["video_id"], "plan_key": state["plan_key"], "cost_field": state["cost_field"], "beat_id": bid}, None) for bid in state["beat_ids"]]
    tl = timeline_handler.handler({**state, "beats": beats}, None)
    segs = [render_chunk_handler.handler({**c, "draft": True}, None) for c in tl["chunks"]]  # draft: speed
    aud = audio_handler.handler(tl, None)
    fin = finalize_handler.handler({**tl, "render": {"segments": segs, "audio": aud}}, None)
    return beats, tl, segs, fin


def start_video(aws, video_id="vid1"):
    usage.consume(USER, limit=5)
    aws.Table("Videos").put_item(Item={"video_id": video_id, "user_id": USER, "usage_day": usage._today(), "status": "STARTED_PROCESSING"})
    return {"user_id": USER, "video_id": video_id, "prompt": "How do rainbows form?", "usage_day": usage._today()}


def api_event(video_id="vid1", user=USER, path_user=None, body=None):
    return {"pathParameters": {"user_id": path_user or user, "video_id": video_id}, "body": json.dumps(body) if body is not None else None,
            "requestContext": {"authorizer": {"claims": {"sub": user}}}}


@pytest.fixture
def generated(env):
    state = plan_handler.handler(start_video(env), None)
    assert state["plot"]["legit"] and len(state["beat_ids"]) == 4
    beats, tl, segs, fin = run_tail(state)
    return env, state, tl


# ----------------------------------------------------------------------------- generation
def test_full_pipeline_produces_a_playable_video_with_credits(generated):
    aws, state, tl = generated
    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["status"] == "COMPLETE" and item["title"] == PLAN_WITH_IMAGE["title"] and item["rev"] == 1 and item["final_rev"] == 1
    assert item["video_uri"] == "s3://videomk.com/videos/u1/vid1/r1.mp4" and item["duration_s"] > 5
    assert "Image credits" in item["youtube_description"] and "Unsplash" in item["youtube_description"] and "Wikipedia" in item["youtube_description"]
    assert float(item["cost_usd"]) > 0
    s3 = boto3.client("s3", region_name="us-west-2")
    assert s3.head_object(Bucket="videomk.com", Key="videos/u1/vid1/r1.mp4")["ContentLength"] > 10_000
    assert s3.head_object(Bucket="videomk.com", Key="videos/u1/vid1/r1.gif")["ContentType"] == "image/gif"
    plan = json.loads(s3.get_object(Bucket="videomk.com", Key=item["plan_key"])["Body"].read())
    assert all(b["media"]["duration"] > 0 for b in plan["beats"])  # the plan carries its measured media
    assert len({c["hash"] for c in tl["chunks"]}) == len(tl["chunks"]) >= 2


def test_rejected_prompt_stops_before_any_spend(env, monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: ('{"legit": false, "reason": "I can\'t help with that."}', {"model": "m", "cost_usd": 0.001, "tokens_in": 1, "tokens_out": 1}))
    out = plan_handler.handler(start_video(env, "vid2"), None)
    assert out["plot"] == {"legit": False, "reason": "I can't help with that."} and "plan_key" not in out
    from generate_video.handlers import mark_rejected_handler

    mark_rejected_handler.handler(out, None)
    assert env.Table("Videos").get_item(Key={"video_id": "vid2"})["Item"]["status"] == "REJECTED"
    assert usage.consume(USER, limit=1) == 1  # refunded


def test_cost_cap_fails_the_job_instead_of_overspending(env, monkeypatch):
    env.Table("Videos").put_item(Item={"video_id": "vid3", "user_id": USER, "status": "X"})
    monkeypatch.setattr(costs, "MAX_COST_USD", 0.05)
    costs.add_cost("vid3", 0.03)
    costs.add_cost("vid3", 0.02)
    with pytest.raises(costs.CostCapExceeded):
        costs.add_cost("vid3", 0.01)
    costs.add_cost("vid3", 0.04, field="cost_r2")  # edits have their own per-revision budget
    with pytest.raises(ValueError):
        costs.add_cost("vid3", 0.01, field="x; DROP")


def test_loaders_refuse_paths_outside_the_video(env):
    loader = render_chunk_handler.make_image_loader("vidA")
    assert loader("generation/v2/vidB/assets/img.jpg") is None and loader("generation/v2/vidA/assets/../../vidB/x.jpg") is None and loader("videos/u1/secret.jpg") is None
    with pytest.raises(ValueError):
        render_chunk_handler.segment_key("vidA", "../../etc", False)


# ----------------------------------------------------------------------------- editor API
def test_editor_get_returns_beats_with_signed_media_and_candidates(generated):
    aws, state, tl = generated
    r = editor_get.handler(api_event(), None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and body["rev"] == 1 and body["edit_state"] == "READY" and len(body["beats"]) == 4
    img = next(b for b in body["beats"] if b["scene"]["type"] == "image")
    assert img["photo"]["url"].startswith("https://") and "Unsplash" in img["photo"]["credit"]
    assert [c["id"] for c in img["candidates"]] == ["uA", "oB"] and all(not b["stale"] for b in body["beats"])
    assert body["final"]["url"].startswith("https://") and body["preview"]["url"] is None
    assert "secret" not in r["body"].lower() and "s3://" not in r["body"]  # no internal locations leak


def test_editor_api_enforces_auth_ownership_and_revisions(generated, monkeypatch):
    aws, state, tl = generated
    assert editor_get.handler({**api_event(), "requestContext": {}}, None)["statusCode"] == 401
    assert editor_get.handler(api_event(user="intruder", path_user="intruder"), None)["statusCode"] == 403   # not the owner
    assert editor_get.handler(api_event(user="intruder", path_user=USER), None)["statusCode"] == 403          # path user != caller
    assert editor_get.handler(api_event(video_id="nope"), None)["statusCode"] == 404

    started = []
    monkeypatch.setattr(editor_apply, "_sfn", type("S", (), {"start_execution": staticmethod(lambda **kw: started.append(kw) or {})})())
    ids = [b["id"] for b in json.loads(editor_get.handler(api_event(), None)["body"])["beats"]]
    ops = [{"op": "set_narration", "id": ids[1], "text": "Light enters a raindrop, bends, bounces off the back and bends again."}]
    stale = editor_apply.handler(api_event(body={"base_rev": 7, "ops": ops, "mode": "preview"}), None)
    assert stale["statusCode"] == 409 and not started
    bad = editor_apply.handler(api_event(body={"base_rev": 1, "ops": [{"op": "set_narration", "id": "zzzzzzzz", "text": "a b c d e f g"}], "mode": "preview"}), None)
    assert bad["statusCode"] == 400 and not started
    assert editor_apply.handler(api_event(body={"base_rev": 1, "ops": ops, "mode": "nuke"}), None)["statusCode"] == 400
    ok = editor_apply.handler(api_event(body={"base_rev": 1, "ops": ops, "mode": "preview"}), None)
    assert ok["statusCode"] == 202 and json.loads(ok["body"])["rev"] == 2 and len(started) == 1
    sent = json.loads(started[0]["input"])
    assert sent == {"user_id": USER, "video_id": "vid1", "plan_key": "generation/v2/vid1/plan_r2.json", "rev": 2, "mode": "preview"}
    # a second edit while the first renders is refused (and the revision does not advance)
    busy = editor_apply.handler(api_event(body={"base_rev": 2, "ops": ops, "mode": "preview"}), None)
    assert busy["statusCode"] == 409 and len(started) == 1
    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["rev"] == 2 and item["edit_state"] == "RENDERING" and item["status"] == "COMPLETE"


def test_failed_edit_leaves_the_video_playable(generated):
    aws, state, tl = generated
    edit_failed_handler.handler({"video_id": "vid1", "error": {"Error": "States.TaskFailed"}}, None)
    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["edit_state"] == "FAILED" and item["status"] == "COMPLETE" and item["video_uri"].endswith("r1.mp4")
    assert json.loads(editor_get.handler(api_event(), None)["body"])["edit_state"] == "FAILED"


# ----------------------------------------------------------------------------- the editing loop
def _apply_and_get_state(aws, monkeypatch, ops, mode, base_rev):
    started = []
    monkeypatch.setattr(editor_apply, "_sfn", type("S", (), {"start_execution": staticmethod(lambda **kw: started.append(kw) or {})})())
    r = editor_apply.handler(api_event(body={"base_rev": base_rev, "ops": ops, "mode": mode}), None)
    assert r["statusCode"] == 202, r["body"]
    return json.loads(started[0]["input"])


def test_editing_one_narration_remakes_only_that_beat_and_reuses_cached_chunks(generated, monkeypatch):
    aws, state, tl = generated
    ids = [b["id"] for b in json.loads(editor_get.handler(api_event(), None)["body"])["beats"]]
    scouted_before = aws.calls["scout"]
    assert len(tl["chunks"]) == 4

    # edit 1: change the opening narration, preview it. Draft and final never share cache, so this first preview renders its own draft chunks.
    inp = _apply_and_get_state(aws, monkeypatch, [{"op": "set_narration", "id": ids[0], "text": "Here is a brand new opening line about rainbows and how they appear in the sky."}], "preview", 1)
    prep = edit_prep_handler.handler(inp, None)
    assert prep["beat_ids"] == [ids[0]] and prep["cost_field"] == "cost_r2"      # only the edited beat is re-synthesised
    _, _, segs1, fin1 = run_tail(prep)
    assert fin1["status"] == "PREVIEW_READY" and aws.calls["scout"] == scouted_before   # photo untouched: no new search
    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["preview_rev"] == 2 and item["preview_uri"].endswith("preview_r2.mp4") and item["video_uri"].endswith("r1.mp4") and item["edit_state"] == "READY"
    assert float(item["cost_r2"]) > 0 and float(item["cost_usd"]) > 0              # edit cost tracked apart from the original

    # edit 2: tweak only the LAST beat. Every chunk before it is already cached from preview 1.
    inp2 = _apply_and_get_state(aws, monkeypatch, [{"op": "set_narration", "id": ids[3], "text": "That is why a rainbow appears after a storm when the sun comes back out."}], "preview", 2)
    _, _, segs2, _ = run_tail(edit_prep_handler.handler(inp2, None))
    assert [s["cached"] for s in segs2][:2] == [True, True] and segs2[-1]["cached"] is False, [s["cached"] for s in segs2]

    # approve: publish the same revision as the final video (ops empty). Chunks whose scenes never changed are reused from the ORIGINAL render.
    inp3 = _apply_and_get_state(aws, monkeypatch, [], "final", 3)
    assert inp3["rev"] == 3 and inp3["plan_key"].endswith("plan_r3.json")
    prep3 = edit_prep_handler.handler(inp3, None)
    assert prep3["beat_ids"] == []                                                 # nothing left to synthesise
    _, _, segs3, fin3 = run_tail(prep3)
    item = aws.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert fin3["status"] == "COMPLETE" and item["video_uri"].endswith("/r3.mp4") and item["final_rev"] == 3 and item["status"] == "COMPLETE"
    assert any(s["cached"] for s in segs3) and not all(s["cached"] for s in segs3)
    boto3.client("s3", region_name="us-west-2").head_object(Bucket="videomk.com", Key="videos/u1/vid1/r1.mp4")  # earlier versions are kept


def test_picking_a_different_photo_fetches_that_candidate_and_updates_credit(generated, monkeypatch):
    aws, state, tl = generated
    body = json.loads(editor_get.handler(api_event(), None)["body"])
    img = next(b for b in body["beats"] if b["scene"]["type"] == "image")
    old_asset_credit = img["photo"]["credit"]
    inp = _apply_and_get_state(aws, monkeypatch, [{"op": "pick_image", "id": img["id"], "candidate": "openverse:oB"}], "preview", 1)
    prep = edit_prep_handler.handler(inp, None)
    assert prep["beat_ids"] == [img["id"]]
    run_tail(prep)
    assert aws.calls["fetch_full"] == ["openverse:oB"]
    body2 = json.loads(editor_get.handler(api_event(), None)["body"])
    img2 = next(b for b in body2["beats"] if b["id"] == img["id"])
    assert img2["photo"]["chosen"] == "openverse:oB" and img2["photo"]["credit"] != old_asset_credit and "Bob" in img2["photo"]["credit"]


def test_inserting_deleting_and_reordering_beats_keeps_everything_consistent(generated, monkeypatch):
    aws, state, tl = generated
    ids = [b["id"] for b in json.loads(editor_get.handler(api_event(), None)["body"])["beats"]]
    ops = [
        {"op": "insert", "after": ids[0], "narration": "Here is a surprising number about how often you can spot a rainbow each year.", "scene": {"type": "stat", "props": {"value": "42°", "label": "the rainbow angle"}}},
        {"op": "delete", "id": ids[2]},
        {"op": "move", "id": ids[3], "to": 0},
    ]
    inp = _apply_and_get_state(aws, monkeypatch, ops, "preview", 1)
    prep = edit_prep_handler.handler(inp, None)
    assert len(prep["beat_ids"]) == 1                                             # only the inserted beat needs media
    _, tl2, segs, fin = run_tail(prep)
    assert [s["type"] for s in tl2["chunks"] and json.loads(boto3.client("s3", region_name="us-west-2").get_object(Bucket="videomk.com", Key=tl2["timeline_key"])["Body"].read())["scenes"]] == ["image", "title", "stat", "diagram"]
    assert fin["status"] == "PREVIEW_READY"
