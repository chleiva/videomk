import io
import json
import threading

import pytest
from PIL import Image

from engine import curate, plan as plan_mod, usermedia


def jpeg(color=(120, 90, 60), size=(640, 480)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    return b.getvalue()


def photos_of(n):
    return [{"id": f"P{i}", "key": f"k{i}", "w": 640, "h": 480, "orientation": "landscape"} for i in range(1, n + 1)]


class FakeVision:
    """Answers a contact sheet with a caption per numbered photo, and counts what it was shown."""

    def __init__(self, bad=(), garbage_first=False, exclude=(), poor=()):
        self.calls, self.images, self.lock, self.bad, self.garbage_first, self.exclude, self.poor = 0, 0, threading.Lock(), set(bad), garbage_first, set(exclude), set(poor)
        self.seen_sheets = []

    def __call__(self, system, user, images):
        import re
        a, b = (int(x) for x in re.search(r"numbered (\d+) to (\d+)", user).groups())
        with self.lock:
            self.calls += 1
            self.images += len(images)
            first = self.calls == 1
            self.seen_sheets.append(images[0])
        if self.garbage_first and first:
            return "sorry, I cannot do that"
        rows = []
        for n in range(a, b + 1):
            if n in self.bad:
                continue
            rows.append({"n": n, "caption": f"photo {n} of the trip", "place": "Eiffel Tower" if n % 7 == 0 else "", "subject": "landmark" if n % 7 == 0 else "city", "people": n % 3 == 0,
                         "quality": "poor" if n in self.poor else "good", "similar": [n - 1] if n % 10 == 5 else [], "exclude": n in self.exclude, "reason": "ID card" if n in self.exclude else ""})
        return "Here you go: " + json.dumps({"photos": rows})


def story_json(photos, per=3, drop=()):
    ids = [p["id"] for p in photos if p["id"] not in drop]
    moments = [{"photos": ids[i:i + per], "role": "detail", "note": "a moment"} for i in range(0, len(ids), per)]
    half = len(moments) // 2
    return json.dumps({"story": "A holiday in Paris.", "voice": "first_person", "tone": "warm", "title_idea": "Our Paris",
                       "chapters": [{"title": "Arrival", "summary": "s", "moments": moments[:half]}, {"title": "The sights", "summary": "t", "moments": moments[half:]}],
                       "unused": [{"id": d, "reason": "duplicate"} for d in drop]})


# ----------------------------------------------------------------------------- contact sheets
def test_photos_are_laid_on_numbered_sheets_of_ten():
    ph = photos_of(25)
    sheets = curate.make_sheets(ph, [jpeg((i * 9 % 255, 80, 120)) for i in range(25)])
    assert [len(ids) for ids, _ in sheets] == [10, 10, 5]
    assert sheets[1][0][0] == "P11" and sheets[2][0][-1] == "P25"
    for ids, raw in sheets:
        im = Image.open(io.BytesIO(raw))
        assert im.width <= 1600 and len(raw) < 400_000                      # small enough to be cheap for the model
        px = im.convert("L").load()
        for k in range(len(ids)):                                          # the number box in each cell's corner: dark box with white digits
            cx, cy = 6 + (k % 5) * 306, 6 + (k // 5) * 231
            region = [px[x, y] for x in range(cx + 4, cx + 36) for y in range(cy + 4, cy + 36)]
            assert min(region) < 20 and max(region) > 235, (ids[k], "no label")


def test_an_unreadable_thumbnail_leaves_an_empty_numbered_cell_not_a_crash():
    sheets = curate.make_sheets(photos_of(3), [jpeg(), b"not an image", jpeg()])
    assert len(sheets) == 1 and len(sheets[0][0]) == 3


# ----------------------------------------------------------------------------- the catalogue
def test_one_hundred_photos_cost_ten_images_and_one_text_call_not_a_hundred_pictures():
    ph = photos_of(100)
    vision, texts = FakeVision(), []
    def ask_text(system, user):
        texts.append(user)
        return story_json(ph, per=3)
    flagged, story = curate.curate(ph, [jpeg() for _ in ph], "my holiday in Paris", 8, ask_vision=vision, ask_text=ask_text)
    assert vision.calls == 10 and vision.images == 10                       # 100 photos = 10 contact sheets, one image each
    assert len(texts) == 1 and "photos:" not in texts[0].lower().replace("photos:\n", "")   # one text call; it carries captions, never pictures
    assert "P37: photo 37 of the trip" in texts[0] and "near-duplicate of P34" in texts[0]
    assert flagged == [] and len(ph) == 100 and ph[6]["place"] == "Eiffel Tower" and ph[2]["people"] is True
    assert len(curate.used_ids(story)) == 100 and story["voice"] == "first_person"


def test_a_sheet_the_model_cannot_read_is_retried_once_and_missing_rows_get_a_plain_default():
    ph = photos_of(12)
    v = FakeVision(garbage_first=True, bad=(4,))
    rows = curate.describe(curate.make_sheets(ph, [jpeg()] * 12), "x", v, workers=1)
    assert v.calls >= 3 and rows["P1"]["caption"] == "photo 1 of the trip" and rows["P4"]["caption"] == "a photo" and rows["P12"]["caption"] == "photo 12 of the trip"


def test_unsafe_photos_are_left_out_in_mode_on_kept_in_log_only_and_the_reason_is_reported():
    for mode, kept in (("on", 9), ("log_only", 10), ("off", 10)):
        ph = photos_of(10)
        flagged, story = curate.curate(ph, [jpeg()] * 10, "x", 3, ask_vision=FakeVision(exclude=(3,)), ask_text=lambda s, u: story_json(ph), mode=mode)
        assert len(ph) == kept and (flagged == [{"id": "P3", "reason": "ID card"}]) == (mode != "off")
        if mode == "on":
            assert "P3" not in curate.used_ids(story)


def test_a_failing_story_call_degrades_to_a_mechanical_grouping_and_never_blocks():
    ph = photos_of(14)
    def boom(system, user):
        raise RuntimeError("model down")
    _, story = curate.curate(ph, [jpeg()] * 14, "x", 5, ask_vision=FakeVision(), ask_text=boom)
    assert sorted(curate.used_ids(story), key=lambda i: int(i[1:])) == [p["id"] for p in ph] and all(1 <= len(m["photos"]) <= 9 for m in curate.moments(story))
    _, story2 = curate.curate(photos_of(5), [jpeg()] * 5, "x", 5, ask_vision=lambda *a: "garbage", ask_text=lambda s, u: "garbage")
    assert len(curate.used_ids(story2)) == 5


# ----------------------------------------------------------------------------- the story
def test_the_length_decides_how_many_photos_can_be_used():
    assert curate.max_used(1) == 42 and curate.max_used(2) == 85 and curate.max_used(3) == 127 and curate.max_used(0.1) == 4 and curate.max_used(0.01) == 3
    assert 2.3 < curate.minutes_for(100) < 2.4 and curate.max_used(curate.minutes_for(100)) >= 99        # 100 photos need a little over 2 minutes


def test_reconcile_makes_a_messy_story_safe():
    ph = photos_of(12)
    messy = {"story": "x" * 2000, "voice": "weird", "chapters": [
        {"title": "A", "moments": [{"photos": ["P1", "p2", "P99", "P1"]}, {"photos": ["P3", "P4", "P5", "P6", "P7", "P8", "P9"]}, {"photos": []}, "nonsense"]},
        {"title": "", "moments": []}, "junk"], "unused": [{"id": "P12", "reason": "blurry"}]}
    s = curate.reconcile(messy, ph, 50)
    placed = curate.used_ids(s)
    assert len(placed) == len(set(placed)) and set(placed) <= {p["id"] for p in ph}              # real ids, each once
    assert all(1 <= len(m["photos"]) <= 9 and m["layout"] in curate.LAYOUTS for m in curate.moments(s)) and all(c["moments"] for c in s["chapters"])
    assert "P10" in placed and "P11" in placed                                                  # forgotten photos are kept when there is room
    assert s["voice"] == "narrator" and len(s["story"]) <= 700
    assert s["unused"] == [{"id": "P12", "reason": "blurry"}] and "P12" not in placed           # the model's own decision to leave P12 out stands, with its reason
    assert {p["id"] for p in ph} == set(placed) | {u["id"] for u in s["unused"]}


def test_over_capacity_drops_poor_and_duplicate_photos_first_and_keeps_the_first_and_last():
    ph = photos_of(30)
    for i in (5, 6, 7):
        ph[i - 1]["quality"] = "poor"
    ph[19]["similar"] = ["P2"]
    ph[29]["quality"] = "poor"
    s = curate.reconcile(json.loads(story_json(ph, per=3)), ph, 20)
    used = curate.used_ids(s)
    assert len(used) == 20 and "P1" in used and "P30" in used and not {"P5", "P6", "P7"} & set(used) and "P20" not in used
    assert {p["id"] for p in ph} == set(used) | {u["id"] for u in s["unused"]}


def test_moments_carry_the_chapter_title_only_on_the_first_of_each_chapter():
    ph = photos_of(9)
    s = curate.reconcile(json.loads(story_json(ph, per=3)), ph, 40)
    ms = curate.moments(s)
    assert [m.get("chapter") for m in ms] == ["Arrival", None, "The sights"][: len(ms)] or any(m.get("chapter") for m in ms)
    assert sum(1 for m in ms if m.get("chapter")) == len(s["chapters"])


# ----------------------------------------------------------------------------- what the director is told
def test_the_director_gets_the_story_the_moments_and_the_rules():
    ph = photos_of(9)
    for p in ph:
        p["caption"] = f"photo {p['id']}"
    s = curate.reconcile(json.loads(story_json(ph, per=3, drop=("P9",))), ph, 40)
    text = plan_mod.photos_prompt([p for p in ph], s)
    assert "THE STORY: A holiday in Paris." in text and "first person" in text and "Chapter \"Arrival\"" in text and "LEFT OUT (do not use): P9" in text
    assert "[sequence]" in text and "[single]" in text and "photo_collage" in text and "chapter_card" in text and "Write ONE beat per moment" in text
    assert plan_mod.photo_slots(ph, s) == len(curate.moments(s)) and plan_mod.photo_slots(ph, None) == 9
    legacy = plan_mod.photos_prompt(ph, None)
    assert "Use EVERY photo" in legacy                                                          # no story: the old behaviour is untouched


def test_gallery_scenes_of_the_users_photos_are_validated_captioned_and_not_charged_to_the_stock_budget():
    raw = {"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": "Our first morning started at the tower and ended by the river.", "scene": {"type": "gallery", "props": {"photos": ["p1", "P2", "P2", "P77"], "alt": "the tower"}}},
        {"narration": "Then we walked through the old streets for an hour or two.", "scene": {"type": "gallery", "props": {"photos": ["P3", "P99"]}}},
        {"narration": "A last photo of the evening sky above the whole city skyline.", "scene": {"type": "gallery", "props": {"photos": ["P88", "P99"]}}}]}
    plan, warns = plan_mod.validate_plan(raw, photo_ids=["P1", "P2", "P3"], photo_captions={"P1": "the Eiffel Tower", "P2": "a boat on the Seine", "P3": "old streets"}, max_images=0)
    g = [b["scene"] for b in plan["beats"]]
    assert g[0] == {"type": "gallery", "props": {"photos": ["P1", "P2"], "image_queries": ["the Eiffel Tower", "a boat on the Seine"], "alt": "the tower"}}   # existing ids, in order, captions as anchors
    assert g[1]["type"] == "image" and g[1]["props"]["photo"] == "P3"                         # only one real photo left: a plain photo scene
    assert g[2]["type"] == "title" and any("do not exist" in w for w in warns)               # none real: a plain card
    assert plan_mod.count_images(plan["beats"][0]) == 0                                       # the user's own photos never count against stock photographs


def test_with_a_story_every_moment_photo_must_be_used_then_the_missing_ones_are_added():
    ph = photos_of(9)
    for p in ph:
        p["caption"] = f"photo {p['id']}"
    story = curate.reconcile(json.loads(story_json(ph, per=3)), ph, 40)
    calls = []
    def llm(system, user):
        calls.append(user)
        beats = [{"narration": "A good long line about one part of our trip that the story needs told.", "scene": {"type": "gallery", "props": {"photos": ["P1", "P2", "P3"]}}}] * 2
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": beats})
    plan, warns = plan_mod.generate_plan("my trip", "", 1, llm, photos=ph, story=story, retries=1)
    used = set()
    for b in plan["beats"]:
        used |= set(b["scene"]["props"].get("photos") or [b["scene"]["props"].get("photo")])
    assert {f"P{i}" for i in range(1, 10)} <= used and len(calls) == 2 and "must use every photo of every moment" in calls[1] and any("added scenes" in w for w in warns)
    assert any(b["scene"]["type"] == "image" for b in plan["beats"][2:])                      # six missing photos: a scene each (many would be grouped into galleries)


# ----------------------------------------------------------------------------- uploads of many photos
def test_a_hundred_photos_are_prepared_in_parallel_but_numbered_in_the_order_given():
    ids = [f"{i:016x}" for i in range(100)]
    store, deleted = {}, []
    def get(key):
        mid = key.split("/")[-1][:-4]
        n = int(mid, 16)
        if n == 40:
            raise KeyError("gone")
        if n == 41:
            return b"not a photo at all"
        return jpeg((n * 2 % 255, 100, 100), (900, 700))
    photos, thumbs, skipped = usermedia.prepare("vid", "user1", ids, get=get, put=lambda k, b: store.__setitem__(k, b), delete=deleted.append, asset_prefix="a/")
    assert len(photos) == 98 and [p["id"] for p in photos][:3] == ["P1", "P2", "P3"] and photos[-1]["id"] == "P98"
    assert sorted(s["id"] for s in skipped) == sorted([ids[40], ids[41]]) and len(thumbs) == 98 and set(store) == {f"a/user_P{i}.jpg" for i in range(1, 99)}
    assert photos[39]["key"] == "a/user_P40.jpg" and len(deleted) >= 98                        # the 41st upload (index 40) was missing, so photo index 40 is the 42nd upload; order preserved


def test_limits_are_a_hundred_per_video_and_three_digit_ids_are_accepted():
    from common import photo_ids
    assert photo_ids.MAX_PHOTOS == 100 and usermedia.PHOTO_ID_RE.match("P100") and usermedia.PHOTO_ID_RE.match("P7") and not usermedia.PHOTO_ID_RE.match("P1000")
    assert len(photo_ids.valid_media_ids([f"{i:016x}" for i in range(100)])) == 100
    with pytest.raises(photo_ids.PhotoError):
        photo_ids.valid_media_ids([f"{i:016x}" for i in range(101)])


# ----------------------------------------------------------------------------- galleries of the user's own photos, end to end in the engine
def _plan_with_photos():
    items = [{"id": f"P{i}", "key": f"gen/assets/user_P{i}.jpg", "caption": f"photo {i}", "w": 600, "h": 900, "orientation": "portrait"} for i in (1, 2, 3)]
    return {"media_items": items, "mood": "calm", "theme": "paper", "beats": [
        {"id": "aaaaaaa1", "narration": "words " * 25, "scene": {"type": "gallery", "props": {"photos": ["P1", "P2", "P3"], "image_queries": ["photo 1", "photo 2", "photo 3"], "alt": "x"}}}]}


def test_the_beat_stage_builds_a_user_gallery_without_any_search_or_cost(monkeypatch):
    from engine.handlers import beat_handler
    monkeypatch.setattr(beat_handler, "make_photo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no stock search for the user's own photos")))
    plan = _plan_with_photos()
    out = beat_handler.make_gallery(plan, plan["beats"][0], "vid", "cost_usd")
    assert [s["asset"] for s in out["gallery"]] == ["gen/assets/user_P1.jpg", "gen/assets/user_P2.jpg", "gen/assets/user_P3.jpg"]
    assert out["photos"] == ["P1", "P2", "P3"] and all(s["credit"] == "" for s in out["gallery"]) and out["query"] == "photo 1|photo 2|photo 3"
    plan["beats"][0]["scene"]["props"]["photos"] = ["P9"]
    assert beat_handler.make_gallery(plan, plan["beats"][0], "vid", "cost_usd")["no_photo"] is True


def test_the_timeline_keeps_a_user_gallery_a_gallery_and_a_single_survivor_a_user_image():
    from engine import timeline as tl_mod
    plan = _plan_with_photos()
    shots = [{"asset": f"gen/assets/user_P{i}.jpg", "credit": "", "query": f"photo {i}", "photo": f"P{i}"} for i in (1, 2, 3)]
    tl = tl_mod.build_timeline(plan, [{"duration": 9.0, "gallery": shots, "words": None}], video_id="v")
    sc = tl["scenes"][0]
    assert sc["type"] == "gallery" and sc["props"]["user"] is True and len(sc["props"]["assets"]) == 3 and len(sc["props"]["cues"]) == 3 if "cues" in sc["props"] else sc["props"]["user"]
    one = tl_mod.build_timeline(plan, [{"duration": 9.0, "gallery": shots[1:2]}], video_id="v")["scenes"][0]
    assert one["type"] == "image" and one["props"]["photo"] == "P2" and one["props"]["asset"] == "gen/assets/user_P2.jpg"


def test_portrait_photos_in_a_user_gallery_are_shown_whole_over_a_dark_backdrop_while_stock_photos_still_fill_the_frame():
    from tests.element_utils import render
    portrait = Image.new("RGB", (600, 900), (250, 200, 40))
    loader = lambda key: portrait
    props = {"assets": ["a", "b"], "credits": ["", ""], "alt": "x", "user": True}
    im = render("gallery", props, 1.0, 8.0, image_loader=loader, draft=False)
    w, h = im.size
    assert im.getpixel((w // 2, h // 2))[0] > 200 and sum(im.getpixel((int(w * 0.04), h // 2))) < 330     # the photo in the middle, a dark blurred backdrop at the sides
    stock = render("gallery", {**props, "user": False}, 1.0, 8.0, image_loader=loader, draft=False)
    assert sum(stock.getpixel((int(w * 0.04), h // 2))) > 450                                             # a stock gallery still fills the frame (cover)


def test_a_changed_user_gallery_is_remade_and_an_unchanged_one_is_not():
    plan = _plan_with_photos()
    beat = plan["beats"][0]
    beat["media"] = {"query": "photo 1|photo 2|photo 3", "photos": ["P1", "P2", "P3"], "gallery": [{"asset": "x"}], "duration": 5.0, "audio_key": "k", "words_key": "w",
                     "tts_hash": plan_mod.tts_hash(plan, beat)}
    assert plan_mod.needs_media(plan, beat) is False
    beat["scene"]["props"]["photos"] = ["P1", "P3"]                  # same captions in the query, different photos: must still be remade
    beat["scene"]["props"]["image_queries"] = ["photo 1", "photo 2", "photo 3"]
    assert plan_mod.needs_media(plan, beat) is True


def test_the_api_schema_allows_exactly_as_many_media_ids_as_the_server_limit():
    """API Gateway validates the request body before any code runs: its limit must follow common.photo_ids.MAX_PHOTOS (it was left at 10 once, and 100-photo requests were refused)."""
    import re
    from common import photo_ids
    src = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "backend_stack.py"), encoding="utf-8").read()
    m = re.search(r'"media": apigw\.JsonSchema\(type=apigw\.JsonSchemaType\.ARRAY, min_items=1, max_items=(\d+)', src)
    assert m and int(m.group(1)) == photo_ids.MAX_PHOTOS


# ----------------------------------------------------------------------------- grouping by day, never mixing days, layouts
def _trip(n=30, per_day=10, step_h=1.2):
    import datetime
    base = datetime.datetime(2026, 4, 11, 9, 0)
    ph = []
    for i in range(n):
        t = base + datetime.timedelta(days=i // per_day, hours=(i % per_day) * step_h)
        ph.append({"id": f"P{i + 1}", "taken": t.strftime("%Y-%m-%dT%H:%M:%S"), "where": "Paris, France", "caption": f"c{i + 1}", "quality": "good", "similar": []})
    return ph


def test_photos_are_grouped_by_day_and_split_into_sessions_by_long_pauses():
    ph = _trip(30)
    g = curate.group_photos(ph)
    assert [(x["id"], len(x["ids"])) for x in g] == [("G1", 10), ("G2", 10), ("G3", 10)] and g[0]["label"] == "Sat 11 Apr, morning, Paris, France"
    assert curate.groups_text(g).splitlines()[1] == "G2: Sun 12 Apr, morning, Paris, France - P11-P20 (10 photos)"
    import datetime
    for p in ph[4:10]:                                                           # a gap of hours inside the day starts a new session of the same day
        p["taken"] = (datetime.datetime.strptime(p["taken"], "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S")
    ph.sort(key=lambda p: p["taken"])
    sessions = [x for x in curate.group_photos(ph) if x["day"] == "2026-04-11"]
    assert len(sessions) >= 2 and all(x["day"] == "2026-04-11" for x in sessions)
    undated = _trip(10)
    for p in undated[:5]:
        p.pop("taken")
    assert curate.group_photos(undated) == []                                    # too few dates to trust: the model decides
    mixed = _trip(10) + [{"id": "P99", "caption": "x"}]
    assert curate.group_photos(mixed)[-1] == {"day": None, "label": "no date", "ids": ["P99"], "id": f"G{len(curate.group_photos(mixed))}"}


def test_a_moment_never_mixes_days_and_moments_follow_the_clock_whatever_the_model_said():
    ph = _trip(30)
    messy = {"story": "s", "chapters": [{"title": "Sights", "moments": [{"photos": ["P1", "P2", "P15", "P16", "P25"], "layout": "collage"}]}, {"title": "Food", "moments": [{"photos": ["P11", "P12", "P5"], "layout": "collage"}]}]}
    s = curate.reconcile(messy, ph, 85)
    by_id = {p["id"]: p for p in ph}
    for m in curate.moments(s):
        assert len({by_id[i]["taken"][:10] for i in m["photos"]}) == 1, m           # one day per moment
    order = [by_id[m["photos"][0]]["taken"] for m in curate.moments(s)]
    assert order == sorted(order)                                                  # chronological
    assert [c["title"] for c in s["chapters"]] == ["Saturday 11 April - Paris, France", "Sunday 12 April - Paris, France", "Monday 13 April - Paris, France"]   # the model's chapters cut across the days: chapters follow the days


def test_over_eight_days_the_chapters_are_weeks_and_a_consistent_model_answer_keeps_its_own_chapters():
    ph = _trip(60, per_day=3, step_h=2)                                             # 20 days
    s = curate.reconcile({"story": "s", "chapters": [{"title": "X", "moments": [{"photos": [f"P{i}"]} for i in range(1, 61, 7)]}]}, ph, 100)
    assert all(c["title"].startswith("Week of") for c in s["chapters"]) and len(s["chapters"]) >= 3
    ph2 = _trip(20, per_day=10)
    ok = {"story": "s", "chapters": [{"title": "Arrival", "moments": [{"photos": [f"P{i}" for i in range(1, 11)], "layout": "collage"}]}, {"title": "Day two", "moments": [{"photos": [f"P{i}" for i in range(11, 21)], "layout": "collage"}]}]}
    assert [c["title"] for c in curate.reconcile(ok, ph2, 85)["chapters"]] == ["Arrival", "Day two"]


def test_layouts_are_made_consistent_with_the_number_of_photos():
    f = curate.fit_layout
    assert f({"photos": ["P1"], "layout": "collage"})["layout"] == "single"
    assert f({"photos": ["P1", "P2"], "layout": "collage"})["layout"] == "sequence"
    assert f({"photos": ["P1", "P2", "P3"], "layout": "collage"})["layout"] == "collage" and f({"photos": ["P1", "P2", "P3"]})["layout"] == "sequence"
    assert f({"photos": [f"P{i}" for i in range(1, 8)], "layout": "sequence"})["layout"] == "collage"
    assert f({"photos": ["P1", "P2", "P3"], "layout": "nonsense"})["layout"] == "sequence"


def test_the_mechanical_fallback_follows_the_days_with_collages():
    s = curate.reconcile({}, _trip(30), 85)
    assert [c["title"] for c in s["chapters"]] == ["Sat 11 Apr", "Sun 12 Apr", "Mon 13 Apr"] and all(m["layout"] in ("collage", "sequence") for m in curate.moments(s))
    assert sorted(curate.used_ids(s), key=lambda i: int(i[1:])) == [f"P{i}" for i in range(1, 31)]
