"""The Making status (docs/CREATE_API.md "Making status"): what the apps poll while a video is being built.

What is proven here: the shape of the `making` object, the language of the live line (X-Locale), a scene counter that never goes down, thumbnails that only the owner
of the video can get (and that the status functions may read nothing else of the working files), and that nothing is recorded for an edit of a finished video."""
import io
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from common import i18n, making
from engine import making_progress

BUCKET = "assets-making-test"
USER, OTHER = "user-a", "user-b"
VID = "0a1b2c3d-0000-4000-8000-000000000001"
PFX = f"generation/v2/{VID}/"

PLAN = {
    "language": "en", "title": "How a forest breathes",
    "media_items": [{"id": "P1", "key": PFX + "assets/user_P1.jpg"}],
    "beats": [
        {"id": "aaaaaaa1", "narration": "Sunlight pours through the canopy, and the forest breathes. Every leaf is a tiny factory.", "scene": {"type": "clip", "props": {"clip_query": "sunlit canopies", "alt": "sun through tree tops"}}},
        {"id": "aaaaaaa2", "narration": "Dr. Okafor measured it for ten years. The numbers surprised her.", "scene": {"type": "image", "props": {"image_query": "bearded vulture in flight", "alt": "A bearded vulture"}}},
        {"id": "aaaaaaa3", "narration": "A single oak moves four hundred litres of water a day.", "scene": {"type": "chart", "props": {"title": "Water moved per day", "kind": "bar"}}},
        {"id": "aaaaaaa4", "narration": "This is the tree in our garden.", "scene": {"type": "image", "props": {"image_query": "old oak in a garden", "alt": "Our oak", "photo": "P1"}}},
        {"id": "aaaaaaa5", "narration": "So next time you walk under the trees, breathe in.", "scene": {"type": "kinetic_text", "props": {"text": "Breathe in."}}},
    ],
}
IDS = [b["id"] for b in PLAN["beats"]]


def _jpeg(size=(1600, 900), color=(40, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def _record(status="ASSETS_CREATION", done=(), thumbs=(), plan=PLAN, user=USER, **extra):
    item = {"video_id": VID, "user_id": user, "status": status, making.ATTR_PLAN: making.manifest(plan), **extra}
    if done:
        item[making.ATTR_DONE] = set(done)
    if thumbs:
        item[making.ATTR_THUMBS] = set(thumbs)
    return item


def _sign(key):
    return "https://signed.example/" + key


# ----------------------------------------------------------------------------- the shape
def test_the_making_object_has_exactly_the_contract_fields():
    mk = making.shape(_record(done=IDS[:2], thumbs=IDS[:2]), "en", _sign)
    assert set(mk) == {"scene_total", "scene_done", "live_line", "narration_line", "scenes"}
    assert mk["scene_total"] == 5 and mk["scene_done"] == 2
    assert mk["scenes"] == [
        {"index": 1, "done": True, "thumb_url": _sign(PFX + "thumbs/aaaaaaa1.jpg")},
        {"index": 2, "done": True, "thumb_url": _sign(PFX + "thumbs/aaaaaaa2.jpg")},
        {"index": 3, "done": False}, {"index": 4, "done": False}, {"index": 5, "done": False},
    ]
    # the scene being worked on is the first one not done: its plain line and the first sentence of its narration
    assert mk["live_line"] == "Narrating “Water moved per day”"
    assert mk["narration_line"] == "A single oak moves four hundred litres of water a day."
    json.dumps(mk)   # plain JSON: no sets, no Decimals


def test_absent_before_a_plan_exists_and_when_the_video_is_not_being_made():
    assert making.shape({"video_id": VID, "user_id": USER, "status": "PLOT_CREATION"}, "en", _sign) is None          # no plan yet
    assert making.shape({"video_id": VID, "user_id": USER, "status": "ASSETS_CREATION"}, "en", _sign) is None        # an older video in flight: no manifest
    for status in ("STARTED_PROCESSING", "PLOT_CREATION", "COMPLETE", "FAILED", "REJECTED", "CANCELLED", ""):
        assert making.shape(_record(status=status, done=IDS), "en", _sign) is None, status                             # a retry's leftovers are never shown before its own plan
    assert making.shape(_record(**{making.ATTR_PLAN: "not json"}), "en", _sign) is None
    assert making.shape(_record(**{making.ATTR_PLAN: '{"v":1,"scenes":[]}'}), "en", _sign) is None


def test_a_scene_without_a_picture_has_no_thumb_url_and_a_thumb_is_never_shown_before_the_scene_is_done():
    mk = making.shape(_record(done=[IDS[2], IDS[0]], thumbs=[IDS[0], IDS[1]]), "en", _sign)   # scene 3 (a chart) is done without a picture; scene 2 has a thumb flag but is not done
    assert [("thumb_url" in s, s["done"]) for s in mk["scenes"]] == [(True, True), (False, False), (False, True), (False, False), (False, False)]
    assert mk["scene_done"] == 2


def test_progress_is_only_what_is_known_ids_that_are_not_scenes_of_this_plan_count_for_nothing():
    mk = making.shape(_record(done=["ffffffff", "../../x", IDS[1]], thumbs=["ffffffff", "../../x"]), "en", _sign)
    assert mk["scene_done"] == 1 and not any("thumb_url" in s for s in mk["scenes"])


def test_first_sentence_is_one_whole_sentence():
    assert making.first_sentence("Sunlight pours through the canopy, and the forest breathes. Every leaf is a tiny factory.") == "Sunlight pours through the canopy, and the forest breathes."
    assert making.first_sentence("Dr. Okafor measured it for ten years. The numbers surprised her.") == "Dr. Okafor measured it for ten years."
    assert making.first_sentence("¿Sabes por qué? Porque el bosque respira.") == "¿Sabes por qué?"
    assert making.first_sentence("  One sentence without an end ") == "One sentence without an end"
    assert making.first_sentence("") == "" and making.first_sentence(None) == ""
    long = making.first_sentence("word " * 80)
    assert len(long) <= making.MAX_NARRATION_CHARS and long.endswith("…") and not long.endswith(" …")


def test_when_every_scene_is_done_the_line_says_so_and_the_last_step_has_its_own_line():
    all_done = making.shape(_record(done=IDS), "en", _sign)
    assert all_done["scene_done"] == all_done["scene_total"] == 5 and all_done["live_line"] == "Putting the scenes together"
    assert all_done["narration_line"] == "Sunlight pours through the canopy, and the forest breathes."   # no single scene is being worked on: the opening sentence
    assert making.shape(_record(done=IDS, **{making.ATTR_STEP: "finish"}), "en", _sign)["live_line"] == "Adding the finishing touches"
    assert making.shape(_record(done=IDS, **{making.ATTR_STEP: "finish"}), "es", _sign)["live_line"] == "Dando los últimos toques"


# ----------------------------------------------------------------------------- the live line and the locale
def _lines(locale, plan=PLAN):
    """The live line while each scene in turn is the one being worked on."""
    ids = [b["id"] for b in plan["beats"]]
    return [making.shape(_record(done=ids[:k], plan=plan), locale, _sign)["live_line"] for k in range(len(ids))]


def test_live_line_in_english_names_the_subject():
    assert _lines("en") == ["Adding footage of sunlit canopies", "Finding pictures of bearded vulture in flight", "Narrating “Water moved per day”", "Placing your photos", "Recording the narration"]


def test_live_line_in_spanish_is_spanish_and_never_mixes_in_an_english_subject():
    # the stock searches are worded in English and the titles of an English video are English: a Spanish app gets the plain Spanish sentence
    assert _lines("es") == ["Añadiendo video a esta escena", "Buscando la imagen adecuada", "Grabando la narración", "Colocando tus fotos", "Grabando la narración"]
    es_plan = {"language": "es", "beats": [
        {"id": "bbbbbbb1", "narration": "Su mayor talento es la comida.", "scene": {"type": "diagram", "props": {"title": "La ruta de mis patatas"}}},
        {"id": "bbbbbbb2", "narration": "A la hora del baño es un delfín.", "scene": {"type": "clip", "props": {"clip_query": "child playing in bathtub", "alt": "kid splashing water"}}},
        {"id": "bbbbbbb3", "narration": "Los guacamayos son ruidosos.", "scene": {"type": "image", "props": {"image_query": "guacamayo azul y amarillo", "alt": "Guacamayo"}}},
    ]}
    assert _lines("es", es_plan) == ["Narrando «La ruta de mis patatas»", "Añadiendo video a esta escena", "Buscando imágenes de guacamayo azul y amarillo"]
    # an English app following a Spanish video: no Spanish title or Spanish search words inside an English sentence
    assert _lines("en", es_plan) == ["Recording the narration", "Adding footage of child playing in bathtub", "Finding the right picture"]
    assert making.shape(_record(plan=es_plan), "en", _sign)["narration_line"] == "Su mayor talento es la comida."   # the narration stays in the video's language


def test_an_unknown_or_missing_locale_is_english():
    for loc in ("fr", "", None, "zz-ZZ"):
        assert making.shape(_record(), loc, _sign)["live_line"] == "Adding footage of sunlit canopies"
    assert making.shape(_record(), "es-MX", _sign)["live_line"] == "Añadiendo video a esta escena"


@pytest.mark.parametrize("locale", ["en", "es"])
def test_every_live_line_is_short_plain_and_has_no_numbers_or_step_names(locale):
    long_q = "an extremely long description of footage that goes on and on"
    plan = {"language": locale, "beats": [
        {"id": "ccccccc1", "narration": "x y z.", "scene": {"type": "clip", "props": {"clip_query": long_q, "alt": long_q}}},
        {"id": "ccccccc2", "narration": "x y z.", "scene": {"type": "gallery", "props": {"image_queries": ["jellyfish underwater", "sea anemone reef"], "alt": "Sea life"}}},
        {"id": "ccccccc3", "narration": "x y z.", "scene": {"type": "bullets", "props": {"heading": "A heading that is far too long to be read in one short line"}}},
        {"id": "ccccccc4", "narration": "x y z.", "scene": {"type": "slide", "props": {"asset": "x", "title": "Revenue"}}},
        {"id": "ccccccc5", "narration": "x y z.", "scene": {"type": "photo_collage", "props": {"photos": ["P1", "P2"], "title": "Sábado"}}},
        {"id": "ccccccc6", "narration": "x y z.", "scene": {"type": "stat", "props": {}}},
    ]}
    lines = _lines(locale, plan) + [making.live_line(None, locale, locale, all_done=True), making.live_line(None, locale, locale, step="finish")]
    for line in lines:
        assert 2 <= len(line.split()) <= making.MAX_LINE_WORDS, line
        assert not re.search(r"\d|%|ASSETS|PLOT|RENDER|_", line), line
        assert "{" not in line and line == line.strip()
    assert long_q not in " ".join(lines)   # a subject too long for the line is left out, never cut in the middle


def test_every_live_line_exists_in_both_languages_and_differs():
    keys = [k for k in i18n.EN if k.startswith("making.line.")]
    assert len(keys) == 10
    for k in keys:
        assert k in i18n.ES and i18n.ES[k] != i18n.EN[k], k
        assert ("{subject}" in i18n.EN[k]) == ("{subject}" in i18n.ES[k]) == k.endswith("_of"), k


# ----------------------------------------------------------------------------- the manifest
def test_the_manifest_is_small_and_carries_no_more_than_the_screen_needs():
    m = json.loads(making.manifest(PLAN))
    assert m["v"] == 1 and m["lang"] == "en" and [s["id"] for s in m["scenes"]] == IDS
    assert [s["k"] for s in m["scenes"]] == ["clip", "image", "words", "own", "words"]
    assert set().union(*[set(s) for s in m["scenes"]]) <= {"id", "k", "q", "t", "n"}
    assert "q" not in m["scenes"][3]   # the person's own photo: its caption is not put in a sentence
    big = {"language": "es", "beats": [{"id": f"{i:08x}", "narration": "palabra " * 60, "scene": {"type": "clip", "props": {"clip_query": "waves crashing on rocks", "alt": "sea"}}} for i in range(100)]}
    assert len(making.manifest(big).encode("utf-8")) < 40_000   # 100 scenes stay far below the 400 KB a record may hold


# ----------------------------------------------------------------------------- AWS: the record, the thumbnails, the routes
@pytest.fixture
def cloud(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("ASSETS_BUCKET", BUCKET)
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        monkeypatch.setattr(making, "_signer_client", None)
        monkeypatch.setattr("engine.awsio._s3", None)
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        ddb.create_table(
            TableName="Videos", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "video_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "video_id", "AttributeType": "S"}, {"AttributeName": "user_id", "AttributeType": "S"}, {"AttributeName": "created_at", "AttributeType": "S"}],
            GlobalSecondaryIndexes=[{"IndexName": "GSI_UserVideos", "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}],
                                     "Projection": {"ProjectionType": "ALL"}}],
        )
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})

        class C:
            pass

        c = C()
        c.table, c.s3 = ddb.Table("Videos"), s3
        yield c


def _put(cloud, status="ASSETS_CREATION", user=USER, video_id=VID, with_plan=True, **extra):
    item = {"video_id": video_id, "user_id": user, "status": status, "created_at": "2026-11-27T10:00:00Z", **extra}
    if with_plan:
        item[making.ATTR_PLAN] = making.manifest(PLAN)
    cloud.table.put_item(Item=item)


def _item(cloud, video_id=VID):
    return cloud.table.get_item(Key={"video_id": video_id}, ConsistentRead=True)["Item"]


def _count(cloud, locale="en"):
    return making.shape(_item(cloud), locale, _sign)["scene_done"]


def test_the_counter_never_goes_down_whatever_order_the_scenes_finish_in(cloud):
    _put(cloud)
    seen = [_count(cloud)]
    for beat in (IDS[3], IDS[0], IDS[3], IDS[4], IDS[0], IDS[1], IDS[2], IDS[2]):   # out of order, with repeats (a retried beat reports again)
        assert making_progress.mark_done(VID, beat, has_thumb=False) is True
        seen.append(_count(cloud))
    assert seen == sorted(seen) and seen[0] == 0 and seen[-1] == 5
    assert seen == [0, 1, 2, 2, 3, 3, 4, 5, 5]


def test_a_thumbnail_flag_once_set_is_not_lost_when_the_beat_reports_again_without_one(cloud):
    _put(cloud)
    making_progress.mark_done(VID, IDS[0], has_thumb=True)
    making_progress.mark_done(VID, IDS[0], has_thumb=False)
    assert _item(cloud)[making.ATTR_THUMBS] == {IDS[0]} and _item(cloud)[making.ATTR_DONE] == {IDS[0]}


def test_nothing_is_recorded_once_the_video_is_no_longer_being_made(cloud):
    for status in ("COMPLETE", "FAILED", "CANCELLED", "REJECTED", "PLOT_CREATION"):
        _put(cloud, status=status)
        assert making_progress.mark_done(VID, IDS[0], True) is False
        making_progress.finishing(VID)
        assert making.ATTR_DONE not in _item(cloud) and making.ATTR_STEP not in _item(cloud), status
    _put(cloud, with_plan=False)                                   # in flight but started before this existed: no manifest, nothing to count against
    assert making_progress.mark_done(VID, IDS[0], True) is False
    assert making_progress.mark_done("no-such-video", IDS[0], True) is False and "Item" not in cloud.table.get_item(Key={"video_id": "no-such-video"})


def test_a_new_attempt_starts_from_nothing(cloud):
    _put(cloud)
    making_progress.mark_done(VID, IDS[0], True)
    making_progress.finishing(VID)
    making_progress.begin(VID)                                      # "Try again": the plan step of the new attempt
    item = _item(cloud)
    assert not any(a in item for a in making.ATTRS) and item["status"] == "ASSETS_CREATION" and item["user_id"] == USER
    making_progress.begin("no-such-video")                          # never creates a record, never raises
    assert "Item" not in cloud.table.get_item(Key={"video_id": "no-such-video"})


def test_the_small_picture_is_small_upright_and_a_jpeg():
    out = Image.open(io.BytesIO(making_progress.image_thumb(_jpeg((3000, 1700)))))
    assert out.format == "JPEG" and out.size == (320, 181)
    assert len(making_progress.image_thumb(_jpeg((3000, 1700)))) < 30_000
    assert Image.open(io.BytesIO(making_progress.image_thumb(_jpeg((200, 300))))).size == (200, 300)   # never enlarged
    png = io.BytesIO()
    Image.new("RGBA", (1920, 1080), (10, 20, 30, 255)).save(png, "PNG")                                 # a slide
    assert Image.open(io.BytesIO(making_progress.image_thumb(png.getvalue()))).size == (320, 180)


def test_the_picture_comes_only_from_the_videos_own_folder():
    beat = lambda i: PLAN["beats"][i]   # noqa: E731
    src = lambda b, media: making_progress.thumb_source(PLAN, b, media, VID)   # noqa: E731
    assert src(beat(0), {"clip_asset": PFX + "assets/clip_x.mp4"}) == (PFX + "assets/clip_x.mp4", "video")
    assert src(beat(0), {"asset": PFX + "assets/img_x.jpg"}) == (PFX + "assets/img_x.jpg", "image")           # a clip that fell back to a still
    assert src(beat(1), {"gallery": [{"asset": PFX + "assets/g0.jpg"}, {"asset": PFX + "assets/g1.jpg"}]}) == (PFX + "assets/g0.jpg", "image")
    assert src(beat(3), {}) == (PFX + "assets/user_P1.jpg", "image")                                            # the person's own photo
    assert src(beat(2), {"element": {"assets": [PFX + "assets/user_P1.jpg"]}}) == (PFX + "assets/user_P1.jpg", "image")
    assert src(beat(2), {}) is None and src(beat(4), {}) is None                                                # drawn scenes have no picture
    other = "generation/v2/another-video/assets/user_P1.jpg"
    for bad in (other, "uploads/user-b/x.jpg", "videos/user-b/v/r1.mp4", PFX + "assets/../../other/x.jpg", "s3://bucket/x.jpg", None, 7):
        assert src(beat(2), {"asset": bad, "clip_asset": bad, "gallery": [{"asset": bad}], "element": {"asset": bad, "assets": [bad]}}) is None, bad
    assert making.thumb_key(VID, "aaaaaaa1") == PFX + "thumbs/aaaaaaa1.jpg"
    for bad_id in ("../x", "a/b", "", "a" * 40, "x.jpg"):
        assert making.thumb_key(VID, bad_id) is None
    assert making.thumb_key("../other", "aaaaaaa1") is None and making.thumb_key("a/b", "aaaaaaa1") is None


def test_a_finished_beat_stores_its_small_picture_and_counts(cloud):
    _put(cloud)
    cloud.s3.put_object(Bucket=BUCKET, Key=PFX + "assets/img_2.jpg", Body=_jpeg())
    making_progress.record_beat(VID, PLAN, PLAN["beats"][1], {"asset": PFX + "assets/img_2.jpg"})
    making_progress.record_beat(VID, PLAN, PLAN["beats"][2], {})                                           # a chart: done, no picture
    making_progress.record_beat(VID, PLAN, PLAN["beats"][0], {"clip_asset": PFX + "assets/missing.mp4"})   # the picture cannot be made: the scene still counts
    item = _item(cloud)
    assert item[making.ATTR_DONE] == {IDS[0], IDS[1], IDS[2]} and item[making.ATTR_THUMBS] == {IDS[1]}
    keys = [o["Key"] for o in cloud.s3.list_objects_v2(Bucket=BUCKET, Prefix=PFX + "thumbs/").get("Contents", [])]
    assert keys == [PFX + "thumbs/aaaaaaa2.jpg"]
    head = cloud.s3.head_object(Bucket=BUCKET, Key=keys[0])
    assert head["ContentType"] == "image/jpeg" and head["ContentLength"] < 30_000
    tags = cloud.s3.get_object_tagging(Bucket=BUCKET, Key=keys[0])["TagSet"]
    assert tags == [{"Key": "retention", "Value": "working"}]                                              # the bucket deletes it after a week
    assert Image.open(io.BytesIO(cloud.s3.get_object(Bucket=BUCKET, Key=keys[0])["Body"].read())).width == 320


def test_an_edit_of_a_finished_video_records_nothing_and_stores_no_picture(cloud):
    _put(cloud, status="COMPLETE", with_plan=False)
    cloud.s3.put_object(Bucket=BUCKET, Key=PFX + "assets/img_2.jpg", Body=_jpeg())
    making_progress.record_beat(VID, PLAN, PLAN["beats"][1], {"asset": PFX + "assets/img_2.jpg"})
    assert not any(a in _item(cloud) for a in making.ATTRS)
    assert cloud.s3.list_objects_v2(Bucket=BUCKET, Prefix=PFX + "thumbs/")["KeyCount"] == 0


def test_recording_progress_can_never_fail_a_beat(cloud, monkeypatch):
    making_progress.record_beat("no-such-video", PLAN, PLAN["beats"][1], {"asset": "x"})
    _put(cloud)
    monkeypatch.setattr(making_progress, "store_thumb", lambda *a, **k: 1 / 0)
    making_progress.record_beat(VID, PLAN, PLAN["beats"][1], {})
    assert _item(cloud)[making.ATTR_DONE] == {IDS[1]}                                                       # the picture failed, the scene is still done
    monkeypatch.setattr(making_progress, "is_making", lambda *a, **k: 1 / 0)
    making_progress.record_beat(VID, PLAN, PLAN["beats"][2], {})                                           # the record cannot be read: nothing raised
    assert making_progress.plan_attributes({"beats": "not a list"}) == {}                                   # a plan the manifest cannot read: no Making status, the video is made all the same


# ----------------------------------------------------------------------------- the routes
def _event(user=USER, path_user=None, video_id=None, locale=None, authed=True):
    return {"pathParameters": {"user_id": path_user or user, **({"video_id": video_id} if video_id else {})},
            "headers": {"X-Locale": locale} if locale else {},
            "requestContext": {"authorizer": {"claims": {"sub": user}}} if authed else {}}


def _list(event):
    import list_videos
    r = list_videos.handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def _get(event):
    import get_video
    r = get_video.handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def _in_flight(cloud):
    _put(cloud)
    cloud.s3.put_object(Bucket=BUCKET, Key=PFX + "assets/img_2.jpg", Body=_jpeg())
    making_progress.record_beat(VID, PLAN, PLAN["beats"][1], {"asset": PFX + "assets/img_2.jpg"})
    making_progress.record_beat(VID, PLAN, PLAN["beats"][0], {})


def test_the_list_carries_making_for_a_video_in_flight_in_the_apps_language(cloud):
    _in_flight(cloud)
    _put(cloud, status="COMPLETE", video_id="done-1", with_plan=False, created_at="2026-11-26T10:00:00Z")
    _put(cloud, status="PLOT_CREATION", video_id="planning-1", with_plan=False, created_at="2026-11-27T11:00:00Z")
    code, body = _list(_event(locale="es"))
    assert code == 200
    items = {i["video_id"]: i for i in body["items"]}
    assert "making" not in items["done-1"] and "making" not in items["planning-1"]            # additive: other items are exactly as before
    assert set(items["done-1"]) == {"user_id", "video_id", "status", "created_at", "editable"}
    mk = items[VID]["making"]
    assert mk["scene_total"] == 5 and mk["scene_done"] == 2 and mk["live_line"] == "Grabando la narración"
    assert mk["narration_line"] == "A single oak moves four hundred litres of water a day."
    assert [s["done"] for s in mk["scenes"]] == [True, True, False, False, False]
    assert "thumb_url" not in mk["scenes"][0] and not any(a in items[VID] for a in making.ATTRS)   # the raw record attributes never leave the server
    url = urlparse(mk["scenes"][1]["thumb_url"])
    q = parse_qs(url.query)
    assert url.scheme == "https" and url.path == "/" + PFX + "thumbs/aaaaaaa2.jpg" and BUCKET in url.netloc
    assert q["X-Amz-Expires"] == [str(making.THUMB_URL_SECONDS)] and making.THUMB_URL_SECONDS <= 900 and "X-Amz-Signature" in q   # short-lived, signed
    assert _list(_event(locale="en"))[1]["items"][0]["video_id"] == "planning-1"
    assert {i["video_id"]: i for i in _list(_event())[1]["items"]}[VID]["making"]["live_line"] == "Narrating “Water moved per day”"   # no locale: English


def test_nobody_else_gets_the_making_status_or_a_thumbnail_url(cloud):
    _in_flight(cloud)
    # another signed-in person asking for the owner's list, or for their own list
    code, body = _list(_event(user=OTHER, path_user=USER))
    assert code == 403 and "items" not in body and "thumbs" not in json.dumps(body)
    code, body = _list(_event(user=OTHER))
    assert code == 200 and body["items"] == []
    assert _list(_event(authed=False))[0] == 401
    # the one-video route
    code, body = _get(_event(video_id=VID, locale="en"))
    assert code == 409 and body["status"] == "ASSETS_CREATION" and body["making"]["scene_done"] == 2 and "thumb_url" in body["making"]["scenes"][1]
    for ev in (_event(user=OTHER, path_user=USER, video_id=VID), _event(user=OTHER, video_id=VID), _event(video_id=VID, authed=False)):
        code, body = _get(ev)
        assert code in (401, 403) and "making" not in body and "thumbs" not in json.dumps(body)
    # a record that names no owner belongs to nobody
    assert making.for_owner({**_item(cloud), "user_id": None}, USER, "en") is None and making.for_owner(_item(cloud), OTHER, "en") is None
    assert making.for_owner(_item(cloud), "", "en") is None and making.for_owner(_item(cloud), USER, "en")["scene_done"] == 2
    # a signed URL is only ever made for a thumbs/ object of the working folder
    for key in ("videos/user-a/x/r1.mp4", PFX + "assets/user_P1.jpg", PFX + "plan_r1.json", PFX + "thumbs/../assets/user_P1.jpg", "uploads/user-a/x.jpg"):
        assert making.presign_thumb(key) is None, key


def test_the_one_video_route_is_unchanged_for_a_video_that_is_not_ready_and_has_no_plan(cloud):
    _put(cloud, status="PLOT_CREATION", with_plan=False)
    assert _get(_event(video_id=VID)) == (409, {"message": "Video not ready", "status": "PLOT_CREATION"})


# ----------------------------------------------------------------------------- the pipeline's own handlers (plan -> beats), with the stubs of the end-to-end test
def test_the_plan_step_stores_the_manifest_and_each_beat_reports(aws, monkeypatch):
    from engine import llm, research, stock
    from engine.handlers import beat_handler, plan_handler
    from tests.tests_helpers import PLAN_WITH_IMAGE

    boto3.client("s3", region_name="us-west-2").create_bucket(Bucket="videomk.com", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_TTS_SPEED", "3")
    monkeypatch.setenv("ASSETS_BUCKET", "videomk.com")
    monkeypatch.setattr("engine.awsio._s3", None)
    monkeypatch.setattr(research, "gather_notes", lambda topic, **k: ("notes", []))
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: (json.dumps(PLAN_WITH_IMAGE), {"model": "m", "cost_usd": 0.01, "tokens_in": 1, "tokens_out": 1}))
    monkeypatch.setattr(stock, "scout_reviewed", lambda q, n, alt="", **k: {"jpeg": _jpeg((3000, 1700)), "entry": {}, "credit": "Photo: Ann / Unsplash", "chosen": "unsplash:uA", "candidates": [], "review": {"cost_usd": 0.0}})
    table = aws.Table("Videos")
    table.put_item(Item={"video_id": "vid1", "user_id": USER, "status": "STARTED_PROCESSING", making.ATTR_DONE: {"stale-from-a-failed-attempt"}, making.ATTR_STEP: "finish"})
    state = plan_handler.handler({"user_id": USER, "video_id": "vid1", "prompt": "How do rainbows form?"}, None)
    item = table.get_item(Key={"video_id": "vid1"})["Item"]
    assert item["status"] == "ASSETS_CREATION" and making.ATTR_DONE not in item and making.ATTR_STEP not in item      # the earlier attempt is forgotten
    mk = making.shape(item, "en", _sign)
    assert mk["scene_total"] == 4 and mk["scene_done"] == 0 and mk["live_line"] == "Narrating “How Rainbows Form”"
    assert mk["narration_line"] == "Ever wondered why a rainbow always shows up opposite the sun in the sky?"
    counts = []
    for bid in reversed(state["beat_ids"]):                                                                            # the Map finishes in any order
        beat_handler.handler({"video_id": "vid1", "plan_key": state["plan_key"], "cost_field": "cost_usd", "beat_id": bid}, None)
        counts.append(making.shape(table.get_item(Key={"video_id": "vid1"})["Item"], "en", _sign))
    assert [c["scene_done"] for c in counts] == [1, 2, 3, 4]
    assert [s for s in counts[0]["scenes"] if s["done"]] == [{"index": 4, "done": True, "thumb_url": _sign("generation/v2/vid1/thumbs/" + state["beat_ids"][3] + ".jpg")}]   # the photograph scene
    assert counts[0]["live_line"] == "Narrating “How Rainbows Form”" and counts[-1]["live_line"] == "Putting the scenes together"
    assert sum(1 for s in counts[-1]["scenes"] if "thumb_url" in s) == 1                                             # title, diagram and chart are drawn later: no picture
    s3 = boto3.client("s3", region_name="us-west-2")
    assert s3.list_objects_v2(Bucket="videomk.com", Prefix="generation/v2/vid1/thumbs/")["KeyCount"] == 1
    monkeypatch.setattr("engine.awsio._s3", None)


# ----------------------------------------------------------------------------- IAM: what the two status functions may read
@pytest.fixture(scope="module")
def template():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, root)
    cwd = os.getcwd()
    os.chdir(root)
    try:
        from backend_stack import BackendStack
        os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
        app = cdk.App(context={"stage": "qa", "engine": "v2"}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-making-qa"))
        stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["http://localhost:4321/auth/callback"]},
                             env=cdk.Environment(account="123456789012", region="eu-west-1"))
        yield Template.from_stack(stack).to_json()
    finally:
        os.chdir(cwd)


def _s3_statements(template, function_name):
    res = template["Resources"]
    (fn,) = [v for v in res.values() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("FunctionName") == function_name]
    role = fn["Properties"]["Role"]["Fn::GetAtt"][0]
    out = []
    for v in res.values():
        if v["Type"] == "AWS::IAM::Policy" and {"Ref": role} in v["Properties"]["Roles"]:
            for st in v["Properties"]["PolicyDocument"]["Statement"]:
                actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
                if any(a.startswith("s3:") for a in actions):
                    out.append((sorted(actions), json.dumps(st["Resource"])))
    return out


@pytest.mark.parametrize("function_name", ["list_videos", "get_video"])
def test_the_status_functions_may_read_thumbnails_and_finished_videos_and_nothing_else(template, function_name):
    statements = _s3_statements(template, function_name)
    bucket = "videomk-qa-123456789012"
    assert (["s3:GetObject"], json.dumps(f"arn:aws:s3:::{bucket}/generation/v2/*/thumbs/*")) in statements
    for actions, resource in statements:
        assert set(actions) <= {"s3:GetObject", "s3:GetBucketLocation"}, actions                       # read only: nothing can be written, listed or deleted
        for arn in re.findall(r"arn:aws:s3:::[^\"]+", resource):
            assert arn in (f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/videos/*", f"arn:aws:s3:::{bucket}/generation/v2/*/thumbs/*"), arn   # no plans, photos, audio, clips, uploads


def test_the_bucket_that_holds_the_thumbnails_is_private(template):
    (bucket,) = [v for v in template["Resources"].values() if v["Type"] == "AWS::S3::Bucket" and v["Properties"].get("BucketName") == "videomk-qa-123456789012"]
    assert bucket["Properties"]["PublicAccessBlockConfiguration"] == {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}


# ----------------------------------------------------------------------------- the whole pipeline (real handlers, real render; slow)
from tests.test_engine_e2e import env, run_tail, start_video   # noqa: E402,F401  (the end-to-end fixture: stubs for the model and the stock search, mock voice)


@pytest.mark.slow
def test_the_whole_run_says_finishing_at_the_end_and_leaves_nothing_on_the_finished_video(env, monkeypatch):   # noqa: F811
    from engine import media as media_mod
    from engine.handlers import plan_handler

    seen = {}
    real_mux = media_mod.mux_final

    def mux(*a, **k):   # what a poll during the last step would get
        seen["making"] = making.shape(env.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"], "en", _sign)
        return real_mux(*a, **k)

    monkeypatch.setattr(media_mod, "mux_final", mux)
    state = plan_handler.handler(start_video(env), None)
    run_tail(state)
    assert seen["making"]["scene_done"] == seen["making"]["scene_total"] == 4 and seen["making"]["live_line"] == "Adding the finishing touches"
    item = env.Table("Videos").get_item(Key={"video_id": "vid1"})["Item"]
    assert item["status"] == "COMPLETE" and not any(a in item for a in making.ATTRS)   # the record of a finished video carries no Making leftovers
    assert making.shape(item, "en", _sign) is None
