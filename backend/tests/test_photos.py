import base64
import io
import json

import boto3
import pytest
from PIL import Image

from common import photo_ids, wallet
from engine import director, plan as plan_mod, usermedia
from engine.renderer import Renderer
from tests.test_engine import small_timeline
from tests.test_hardening import launcher  # noqa: F401  (the fixture)

UID = "u1"


def jpeg(w=400, h=300, color=(200, 60, 60), exif=None):
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "JPEG", **({"exif": exif} if exif else {}))
    return out.getvalue()


def exif_with(orientation=1, date="2026:07:12 18:30:00"):
    ex = Image.Exif()
    ex[274] = orientation
    ex[306] = date
    ex[271] = "SomePhone Inc."
    ex.get_ifd(0x8825).update({1: "N", 2: (40.0, 25.0, 0.0), 3: "W", 4: (3.0, 40.0, 0.0)})  # GPS
    return ex.tobytes()


# ---------------------------------------------------------------- preparing the photos
def test_normalizing_applies_rotation_bounds_size_and_keeps_only_pixels():
    full, thumb, facts = usermedia.normalize(jpeg(4000, 3000, exif=exif_with(orientation=6)))
    im = Image.open(io.BytesIO(full))
    assert im.size == (1536, 2048) and facts["orientation"] == "portrait" and (facts["w"], facts["h"]) == (1536, 2048)  # rotated upright, longest side 2048
    assert not im.getexif() and "exif" not in im.info and "icc_profile" not in im.info       # no camera, no GPS, no date left in the stored copy
    assert facts["taken"] == "2026-07-12"                                                      # the date was read before it was stripped
    assert max(Image.open(io.BytesIO(thumb)).size) == 768
    assert usermedia.normalize(jpeg(300, 300))[2]["orientation"] == "square"
    assert usermedia.normalize(jpeg(300, 200))[2]["taken"] is None


@pytest.mark.parametrize("raw", [b"", b"not an image at all", b"GIF89a" + b"\x00" * 64, jpeg(30, 30), b"x" * (usermedia.MAX_UPLOAD_BYTES + 1)])
def test_anything_that_is_not_a_usable_photo_is_refused(raw):
    with pytest.raises(photo_ids.PhotoError):
        usermedia.normalize(raw)


def test_a_gif_and_a_decompression_bomb_are_refused():
    g = io.BytesIO()
    Image.new("P", (200, 200)).save(g, "GIF")
    with pytest.raises(photo_ids.PhotoError):
        usermedia.normalize(g.getvalue())
    big = io.BytesIO()
    Image.new("1", (12000, 12000)).save(big, "PNG")  # 144 megapixels, tiny file
    with pytest.raises(photo_ids.PhotoError):
        usermedia.normalize(big.getvalue())


def test_prepare_makes_clean_copies_numbers_the_photos_and_deletes_every_original():
    store = {usermedia.upload_key(UID, "a" * 16): jpeg(800, 600), usermedia.upload_key(UID, "b" * 16): b"garbage", usermedia.upload_key(UID, "c" * 16): jpeg(600, 800)}
    deleted = []
    photos, thumbs, skipped = usermedia.prepare("vid", UID, ["a" * 16, "b" * 16, "c" * 16, "d" * 16], get=lambda k: store[k], put=lambda k, b: store.__setitem__(k, b),
                                                delete=lambda k: (deleted.append(k), store.pop(k, None)), asset_prefix="generation/v2/vid/assets/")
    assert [p["id"] for p in photos] == ["P1", "P2"] and [p["orientation"] for p in photos] == ["landscape", "portrait"] and len(thumbs) == 2
    assert [s["id"] for s in skipped] == ["b" * 16, "d" * 16] and skipped[0]["reason"] == "not a readable photo" and skipped[1]["reason"] == "photo not found"
    assert all(p["key"].startswith("generation/v2/vid/assets/user_P") and p["key"] in store for p in photos)
    assert not [k for k in store if k.startswith("uploads/")]                                   # no original is left, good or bad


# ---------------------------------------------------------------- understanding them
def _photos(n=3):
    return [{"id": f"P{i}", "key": f"k{i}", "orientation": "landscape", "taken": None} for i in range(1, n + 1)]


def test_review_adds_captions_and_drops_only_photos_the_reviewer_flags():
    ph = _photos(3)
    ask = lambda system, user, images: json.dumps({"photos": [{"n": 1, "caption": "Two kids on a beach", "people": True, "exclude": False},
                                                              {"n": 2, "caption": "A bank card on a table", "people": False, "exclude": True, "reason": "bank card"},
                                                              {"n": 3, "caption": "A dog", "people": False}]})
    flagged = usermedia.analyze(ph, [b"t"] * 3, ask, mode="on")
    assert flagged == [{"id": "P2", "reason": "bank card"}] and [p["id"] for p in ph] == ["P1", "P3"] and ph[0]["caption"] == "Two kids on a beach" and ph[0]["people"] is True
    ph = _photos(3)
    assert len(usermedia.analyze(ph, [b"t"] * 3, ask, mode="log_only")) == 1 and len(ph) == 3        # log only: reported, kept
    ph = _photos(3)
    assert usermedia.analyze(ph, [b"t"] * 3, ask, mode="off") == [] and len(ph) == 3                 # off: never dropped


def test_a_failing_review_never_blocks_the_video():
    ph = _photos(2)
    boom = lambda system, user, images: (_ for _ in ()).throw(RuntimeError("bedrock down"))
    assert usermedia.analyze(ph, [b"t"] * 2, boom, mode="on") == [] and [p["caption"] for p in ph] == ["a photo", "a photo"]
    ph = _photos(2)
    assert usermedia.analyze(ph, [b"t"] * 2, lambda s, u, i: "no json", mode="on") == [] and len(ph) == 2


# ---------------------------------------------------------------- the script uses every photo
def _beat(i, photo=None, narration=None):
    props = {"image_query": f"label {i}", "alt": f"alt {i}", **({"photo": photo} if photo else {})}
    return {"narration": narration or f"This is spoken line number {i} about the photo.", "scene": {"type": "image", "props": props}}


def _plan_json(photos_used):
    return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [_beat(i, p) for i, p in enumerate(photos_used)]})


def test_the_prompt_lists_every_photo_with_caption_orientation_and_date():
    ph = [{"id": "P1", "caption": "Two kids on a beach", "orientation": "portrait", "taken": "2026-07-12"}, {"id": "P2", "caption": "", "orientation": "landscape"}]
    p = plan_mod.build_user_prompt("Our holiday", "", 1, photos=ph)
    assert "P1: Two kids on a beach (portrait, taken 2026-07-12)" in p and "P2: a photo (landscape)" in p and "Use EVERY photo" in p and "about 4 beats" in p
    assert "about 12 beats" in plan_mod.build_user_prompt("x", "", 1, photos=[{"id": f"P{i}"} for i in range(12)])   # at least one beat per photo
    assert "attached" not in plan_mod.build_user_prompt("x", "", 1)


def test_a_photo_the_model_invented_becomes_an_ordinary_scene_and_an_empty_query_is_fine_for_a_real_one():
    raw = {"legit": True, "title": "T", "beats": [
        {"narration": "A line about the first photo, as spoken.", "scene": {"type": "image", "props": {"photo": "p1", "alt": "kids on a beach"}}},
        {"narration": "A line about a photo that doesn't exist, spoken.", "scene": {"type": "image", "props": {"photo": "P9", "alt": "ghost", "image_query": "ghost town"}}}]}
    plan, _ = plan_mod.validate_plan(raw, photo_ids=["P1", "P2"])
    assert plan["beats"][0]["scene"]["props"]["photo"] == "P1" and plan["beats"][0]["scene"]["props"]["image_query"] == "kids on a beach"
    assert "photo" not in plan["beats"][1]["scene"]["props"]


def test_a_missing_photo_triggers_one_retry_then_is_added_rather_than_dropped():
    ph = [{"id": "P1", "caption": "Kids on a beach"}, {"id": "P2", "caption": "A dog"}, {"id": "P3", "caption": "Dinner at sunset"}]
    asked = []
    answers = iter([_plan_json(["P1"]), _plan_json(["P1", "P2", "P3"])])
    plan, _ = plan_mod.generate_plan("holiday", "", 1, lambda s, u: (asked.append(u), next(answers))[1], photos=ph)
    assert len(asked) == 2 and "not used in any scene: P2, P3" in asked[1]
    assert [b["scene"]["props"].get("photo") for b in plan["beats"]] == ["P1", "P2", "P3"]
    lazy = iter([_plan_json(["P1"]), _plan_json(["P1"])])  # the model ignores the correction
    plan, warns = plan_mod.generate_plan("holiday", "", 1, lambda s, u: next(lazy), photos=ph)
    assert [b["scene"]["props"].get("photo") for b in plan["beats"]] == ["P1", "P2", "P3"] and any("unused photos: P2, P3" in w for w in warns)
    assert all(len(b["narration"].split()) >= plan_mod.MIN_BEAT_WORDS for b in plan["beats"]) and len({b["id"] for b in plan["beats"]}) == 3


def test_the_director_records_the_users_photos_in_the_plan():
    ph = [{"id": "P1", "key": "generation/v2/v/assets/user_P1.jpg", "w": 100, "h": 200, "orientation": "portrait", "caption": "A dog", "taken": "2026-01-01"}]
    ask_small = lambda s, u, n=120: '{"mode":"encyclopedia"}'
    r = director.direct("My dog's day out", minutes=1, language="en", today="2026-11-23", ask_small=ask_small, ask_big=lambda s, u: _plan_json(["P1", "P1", "P1", "P1"]), photos=ph)
    assert r["plan"]["media_items"] == [{"id": "P1", "key": "generation/v2/v/assets/user_P1.jpg", "w": 100, "h": 200, "orientation": "portrait", "caption": "A dog"}]


# ---------------------------------------------------------------- beats use the photo instead of searching
def test_a_user_photo_beat_uses_the_upload_and_never_searches(monkeypatch):
    from engine import stock
    from engine.handlers import beat_handler

    searched = []
    monkeypatch.setattr(stock, "scout_reviewed", lambda *a, **k: (searched.append(a), None)[1])
    key = "generation/v2/vid/assets/user_P1.jpg"
    plan = {"media_items": [{"id": "P1", "key": key}], "beats": []}
    beat = {"id": "b1", "narration": "x", "scene": {"type": "image", "props": {"image_query": "kids", "photo": "P1"}}}
    out = beat_handler.make_photo(plan, beat, "vid", "cost_usd")
    assert out["asset"] == key and out["photo"] == "P1" and "credit" not in out and "no_photo" not in out and searched == []   # no search for the user's own photo
    assert plan_mod.needs_media(plan, {**beat, "media": {"tts_hash": plan_mod.tts_hash(plan, beat), "audio_key": "a", "duration": 3, "query": "kids", "pick": None, "asset": key, "photo": "P1"}}) is False
    changed = {**beat, "scene": {"type": "image", "props": {"image_query": "kids", "photo": "P2"}}, "media": {"tts_hash": plan_mod.tts_hash(plan, beat), "audio_key": "a", "duration": 3, "query": "kids", "pick": None, "asset": key, "photo": "P1"}}
    assert plan_mod.needs_media(plan, changed) is True   # pointing the scene at another photo remakes it
    evil = {"media_items": [{"id": "P1", "key": "uploads/someone-else/x.jpg"}], "beats": []}
    out = beat_handler.make_photo(evil, beat, "vid", "cost_usd")   # a key outside this video's own assets is never used
    assert "asset" not in out and out.get("no_photo") is True and len(searched) == 1


# ---------------------------------------------------------------- showing them
def _center_and_corner(photo, props):
    tl = small_timeline(6.0, ["image"])
    tl["scenes"][0]["props"] = {"asset": "k", "ken_burns": "in", **props}
    im = Renderer(tl, lambda k: photo).frame_at(2.0)
    return im.getpixel((960, 400)), im.getpixel((20, 400))


def test_portrait_user_photos_are_shown_whole_over_a_dark_blurred_backdrop_not_cropped():
    portrait = Image.new("RGB", (1200, 1600), (10, 200, 10))
    centre, corner = _center_and_corner(portrait, {"photo": "P1"})
    assert centre[1] > 150 and corner[1] < 120 and corner[1] > 20       # the photo in the middle; the sides are its own colour, darkened and blurred
    crop_centre, crop_corner = _center_and_corner(portrait, {})         # a stock photo of the same shape is still cropped to fill (unchanged behaviour)
    assert crop_corner[1] > 150
    wide = Image.new("RGB", (2400, 1400), (10, 200, 10))
    assert _center_and_corner(wide, {"photo": "P1"})[1][1] > 150          # a landscape user photo already fills the frame: no backdrop needed


# ---------------------------------------------------------------- the upload endpoint
@pytest.fixture
def bucket(aws, monkeypatch):
    monkeypatch.setenv("ASSETS_BUCKET", "photo-test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket="photo-test-bucket", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    return s3


def _ev(count, user=UID, path_user=None):
    return {"pathParameters": {"user_id": path_user or user}, "body": json.dumps({"count": count}), "requestContext": {"authorizer": {"claims": {"sub": user}}}}


def test_upload_slots_pin_the_key_type_and_size(bucket):
    import uploads_api

    out = uploads_api.handler(_ev(3), None)
    body = json.loads(out["body"])
    assert out["statusCode"] == 200 and len(body["uploads"]) == 3 and body["max_bytes"] == 10_000_000
    ids = [u["id"] for u in body["uploads"]]
    assert len(set(ids)) == 3 and all(photo_ids.ID_RE.match(i) for i in ids)
    pol = json.loads(base64.b64decode(body["uploads"][0]["fields"]["policy"]))
    conds = pol["conditions"]
    assert ["content-length-range", 1, 10_000_000] in conds and {"Content-Type": "image/jpeg"} in conds
    assert {"key": f"uploads/{UID}/{ids[0]}.jpg"} in conds and {"bucket": "photo-test-bucket"} in conds   # one key, in the caller's own folder


@pytest.mark.parametrize("count", [0, 11, "3", True, None, 2.5])
def test_upload_counts_are_validated(bucket, count):
    import uploads_api

    assert uploads_api.handler(_ev(count), None)["statusCode"] == 400


def test_uploads_need_the_owner_and_are_rate_limited(bucket, monkeypatch):
    import uploads_api

    assert uploads_api.handler({**_ev(1), "requestContext": {}}, None)["statusCode"] == 401
    assert uploads_api.handler(_ev(1, path_user="u2"), None)["statusCode"] == 403
    monkeypatch.setattr(uploads_api, "DAILY_PHOTOS", 4)
    assert uploads_api.handler(_ev(3), None)["statusCode"] == 200
    assert uploads_api.handler(_ev(3), None)["statusCode"] == 429


# ---------------------------------------------------------------- the launcher checks the photos exist, in the caller's folder
def test_the_launcher_accepts_only_photos_that_were_uploaded_by_this_user(bucket, launcher):
    import sf_launcher

    sf_launcher._s3 = boto3.client("s3", region_name="us-west-2")
    mine, theirs = "a" * 16, "b" * 16
    bucket.put_object(Bucket="photo-test-bucket", Key=photo_ids.upload_key(UID, mine), Body=b"x")
    bucket.put_object(Bucket="photo-test-bucket", Key=photo_ids.upload_key("someone-else", theirs), Body=b"x")
    from tests.test_hardening import _event

    def go(media, rid):
        return launcher.handler(_event(body={"prompt": "Our week at the beach with the family", "target_minutes": 1, "client_request_id": rid, "media": media}), None)

    ok = go([mine], "photo-test-001")
    assert ok["statusCode"] == 202 and json.loads(launcher.fake.calls[0]["input"])["media"] == [mine]
    for bad, rid in (([theirs], "photo-test-002"), (["c" * 16], "photo-test-003"), (["nothex"], "photo-test-004"), ([mine, mine], "photo-test-005"),
                     (["d" * 16] * 11, "photo-test-006"), ([], "photo-test-007")):
        assert go(bad, rid)["statusCode"] == 400, bad
    assert len(launcher.fake.calls) == 1 and wallet.balance(UID)["balance"] == 4        # refused requests started nothing and charged nothing
