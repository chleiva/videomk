import io
import json

import boto3
import pytest
from PIL import Image

from common import photo_ids
from engine import curate, geoname, plan as plan_mod, usermedia
from tests.test_curate import FakeVision, jpeg, photos_of, story_json

IDS = [f"{i:016x}" for i in range(6)]


# ----------------------------------------------------------------------------- validation (the launcher's contract with the apps)
def test_media_meta_keeps_only_known_fields_rounds_coordinates_and_drops_empty_entries():
    m = photo_ids.valid_media_meta({IDS[0]: {"taken": "2026-04-12T14:32:07", "lat": 48.85837, "lon": 2.29448, "camera": "x", "gps_exact": 1},
                                    IDS[1]: {"lat": -33.8567, "lon": 151.2153}, IDS[2]: {"taken": "2026-04-13T09:00:00"}, IDS[3]: {}}, IDS)
    assert m == {IDS[0]: {"taken": "2026-04-12T14:32:07", "lat": 48.86, "lon": 2.29}, IDS[1]: {"lat": -33.86, "lon": 151.22}, IDS[2]: {"taken": "2026-04-13T09:00:00"}}
    assert photo_ids.valid_media_meta(None, IDS) == {}


@pytest.mark.parametrize("bad", [
    "text", [1], {"nothex": {"lat": 1, "lon": 1}}, {IDS[0]: "x"}, {IDS[0]: {"taken": "yesterday"}}, {IDS[0]: {"taken": "2026-13-45T99:00:00"}},
    {IDS[0]: {"lat": 91, "lon": 0}}, {IDS[0]: {"lat": 0, "lon": 181}}, {IDS[0]: {"lat": "48.8", "lon": 2}}, {IDS[0]: {"lat": 48.8}}, {IDS[0]: {"lat": True, "lon": False}},
])
def test_malformed_media_meta_is_refused(bad):
    with pytest.raises(photo_ids.PhotoError):
        photo_ids.valid_media_meta(bad, IDS)


def test_the_launcher_forwards_clean_meta_to_the_workflow_and_refuses_bad_meta(monkeypatch):
    import sf_launcher
    out = sf_launcher.validate_options({"media": IDS[:2], "media_meta": {IDS[0]: {"taken": "2026-04-12T14:32:07", "lat": 48.85837, "lon": 2.29448}}})
    assert out["media_meta"] == {IDS[0]: {"taken": "2026-04-12T14:32:07", "lat": 48.86, "lon": 2.29}}
    assert "media_meta" not in sf_launcher.validate_options({"media": IDS[:2]})
    with pytest.raises(sf_launcher.BadRequest):
        sf_launcher.validate_options({"media": IDS[:2], "media_meta": {IDS[5]: {"lat": 1, "lon": 1}}})        # not one of the photos sent
    with pytest.raises(sf_launcher.BadRequest):
        sf_launcher.validate_options({"media": IDS[:2], "media_meta": {IDS[0]: {"lat": 200, "lon": 1}}})


def test_the_api_schema_accepts_media_meta():
    src = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "backend_stack.py"), encoding="utf-8").read()
    assert '"media_meta": apigw.JsonSchema(type=apigw.JsonSchemaType.OBJECT)' in src


# ----------------------------------------------------------------------------- place names, offline
@pytest.mark.parametrize("lat,lon,expected", [(48.86, 2.29, "Paris, France"), (40.43, -3.70, "Madrid, Spain"), (35.68, 139.69, "Tokyo, Japan"), (-33.86, 151.21, "Sydney, Australia"),
                                              (48.80, 2.12, "near Paris, France"), (0.0, -30.0, None)])
def test_coordinates_become_a_place_name_from_the_bundled_data(lat, lon, expected):
    assert geoname.place_for(lat, lon) == expected


def test_attach_places_names_the_place_then_forgets_the_coordinates():
    ph = [{"id": "P1", "lat": 48.86, "lon": 2.29, "taken": "2026-04-12T14:32:00"}, {"id": "P2", "lat": 0.0, "lon": -30.0}, {"id": "P3"}]
    assert usermedia.attach_places(ph) == 1
    assert ph[0]["where"] == "Paris, France" and "where" not in ph[1] and all("lat" not in p and "lon" not in p for p in ph)       # no coordinates survive
    assert ph[0]["taken"] == "2026-04-12T14:32:00"


# ----------------------------------------------------------------------------- order by capture time
def test_photos_are_numbered_in_the_order_they_were_taken_when_most_have_a_time():
    ids = IDS[:5]
    meta = {ids[0]: {"taken": "2026-04-12T18:00:00"}, ids[1]: {"taken": "2026-04-11T09:00:00"}, ids[2]: {"taken": "2026-04-12T08:30:00"}, ids[3]: {"lat": 48.86, "lon": 2.29}}
    colors = {ids[i]: (i * 40, 90, 90) for i in range(5)}
    photos, thumbs, skipped = usermedia.prepare("v", "u", ids, get=lambda k: jpeg(colors[k.split("/")[-1][:-4]], (900, 700)), put=lambda k, b: None, delete=lambda k: None, asset_prefix="a/", meta=meta)
    assert [p.get("taken") for p in photos][:3] == ["2026-04-11T09:00:00", "2026-04-12T08:30:00", "2026-04-12T18:00:00"]      # earliest first
    assert photos[3].get("lat") == 48.86 and photos[3].get("taken") is None and len(photos) == 5                              # untimed photos follow, coordinates carried until attach_places
    # fewer than half have a time: the given order stands
    p2, _, _ = usermedia.prepare("v", "u", ids, get=lambda k: jpeg((1, 2, 3), (900, 700)), put=lambda k, b: None, delete=lambda k: None, asset_prefix="a/", meta={ids[4]: {"taken": "2020-01-01T00:00:00"}})
    assert [p.get("taken") for p in p2] == [None, None, None, None, "2020-01-01T00:00:00"]


# ----------------------------------------------------------------------------- what the story model is told
def test_the_story_model_gets_time_place_and_a_trip_summary_and_is_told_to_trust_them():
    ph = photos_of(6)
    for i, p in enumerate(ph):
        p.update({"caption": f"photo {i + 1}", "taken": f"2026-04-{11 + i // 3:02d}T{9 + i:02d}:00:00", "where": "Paris, France" if i < 4 else "near Versailles, France", "subject": "city", "quality": "good"})
    seen = {}
    def ask_text(system, user):
        seen["system"], seen["user"] = system, user
        return story_json(ph, per=3)
    curate.make_story("my trip", 3, ph, ask_text)
    assert "taken Sat 11 Apr 09:00" in seen["user"] and "GPS place: Paris, France" in seen["user"] and "2 days" in seen["user"] or "(2 days" in seen["user"]
    assert "places from the photos' GPS: Paris, France, Versailles, France" in seen["user"]
    assert "Trust them over visual guesses for ORDER and for PLACE NAMES" in seen["system"] and "start a new chapter when the day changes" in seen["system"]
    assert curate.trip_summary(photos_of(3)) == ""                                                                      # photos with no data say nothing


def test_the_director_sees_the_time_and_place_of_each_photo_and_the_plan_keeps_them_without_coordinates():
    ph = photos_of(2)
    for p in ph:
        p.update({"caption": "a street", "taken": "2026-04-12T14:32:00", "where": "Paris, France"})
    line = plan_mod.photos_prompt(ph, None)
    assert "taken 2026-04-12T14:32:00" in line and "GPS place: Paris, France" in line
    from engine import director
    out = director.direct("trip", minutes=1.0, ask_small=lambda s, u, n=120: "en", ask_big=lambda s, u: json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": " ".join(["w"] * 30), "scene": {"type": "image", "props": {"photo": "P1", "image_query": "a street", "alt": "a"}}}, {"narration": " ".join(["w"] * 30), "scene": {"type": "image", "props": {"photo": "P2", "image_query": "a street", "alt": "a"}}}]}),
        language="en", photos=ph)
    items = out["plan"]["media_items"]
    assert items[0]["taken"] == "2026-04-12T14:32:00" and items[0]["where"] == "Paris, France" and all("lat" not in i and "lon" not in i for i in items)
    assert "lat" not in json.dumps(out["plan"]) and '"lon"' not in json.dumps(out["plan"])
