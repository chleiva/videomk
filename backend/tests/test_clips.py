import subprocess

import pytest
from PIL import Image

from engine import clips, media, plan as plan_mod, stock
from engine.netsafe import FetchError
from engine.renderer import Renderer
from engine.timeline import build_timeline
from tests.test_engine import small_timeline


@pytest.fixture(autouse=True)
def _no_real_llm_or_cache(monkeypatch):
    monkeypatch.setenv("CLIP_VERIFY", "0")   # tests that exercise verification turn it on and pass their own model stub
    monkeypatch.setenv("CLIPS_COMMONS", "1")  # the interleaving tests include Commons; the test of its contact rule sets this itself
    monkeypatch.setenv("CLIP_RETRY", "0")    # tests of the retry pass switch it on with their own stubs (no model calls)
    monkeypatch.setenv("CLIPS_NASA", "0")    # no network in tests; the NASA tests switch it on with their own stubs
    clips._CACHE.clear()


def make_source(seconds=4, size="640x360", fmt="mp4", tmp_path=None):
    """A real, moving test video made by ffmpeg itself."""
    out = tmp_path / f"src.{fmt}"
    subprocess.run([media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25", "-t", str(seconds), "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


# ---------------------------------------------------------------- licences
@pytest.mark.parametrize("name,ok", [("CC0", True), ("CC BY 4.0", True), ("CC-BY-3.0", True), ("Public domain", True), ("PD US Government", True),
                                     ("CC BY-SA 4.0", False), ("CC BY-NC 2.0", False), ("CC BY-ND 4.0", False), ("GFDL", False), ("Pexels License", False), ("", False)])
def test_only_licences_that_allow_commercial_use_in_a_derived_video_pass(name, ok):
    assert clips.license_allowed(name) is ok


# ---------------------------------------------------------------- providers
PEXELS = {"videos": [
    {"id": 123, "width": 1920, "height": 1080, "duration": 14, "url": "https://www.pexels.com/video/waves-crashing-on-a-rocky-shore-123/", "image": "https://images.pexels.com/p/123.jpg",
     "user": {"name": "Ana Ruiz", "url": "https://www.pexels.com/@ana"},
     "video_files": [{"file_type": "video/mp4", "width": 640, "link": "https://videos.pexels.com/sd.mp4"}, {"file_type": "video/mp4", "width": 1920, "link": "https://videos.pexels.com/hd.mp4"},
                     {"file_type": "video/mp4", "width": 3840, "link": "https://videos.pexels.com/uhd.mp4"}, {"file_type": "application/x-mpegURL", "width": None, "link": "https://x/hls.m3u8"}]},
    {"id": 124, "width": 1920, "height": 1080, "duration": 9, "url": "https://www.pexels.com/video/x-124/", "image": "i", "user": {}, "video_files": [{"file_type": "application/x-mpegURL", "link": "https://x/a.m3u8"}]},
    {"id": "bad"},
]}


def test_pexels_candidates_pick_a_sensible_file_and_carry_the_credit():
    seen = {}
    got = clips.pexels_search("waves", "KEY", fetch=lambda url, **kw: (seen.update(url=url, **kw), PEXELS)[1])
    assert "orientation=landscape" in seen["url"] and seen["headers"] == {"Authorization": "KEY"} and seen["url"].startswith("https://api.pexels.com/v1/videos/search?")
    assert len(got) == 1                                                       # no mp4 file, or a malformed entry: skipped
    c = got[0]
    assert c["video_url"] == "https://videos.pexels.com/hd.mp4"               # Full HD, not the 4K file and not the SD one
    assert c["creator"] == "Ana Ruiz" and c["license"] == "Pexels License" and c["alt"] == "waves crashing on a rocky shore"
    assert c["attribution"] == "Video by Ana Ruiz on Pexels (https://www.pexels.com/video/waves-crashing-on-a-rocky-shore-123/)" and clips.credit_line(c) == "Video: Ana Ruiz / Pexels"
    assert clips.pexels_search("waves", "", fetch=lambda *a, **k: pytest.fail("no key, no request")) == []


def commons_page(i, title, lic, w=1920, h=1080, dur=12, size=20_000_000, artist="<a href='x'>Mostafa</a>", derivs=True):
    return {"pageid": i, "index": i, "title": f"File:{title}", "videoinfo": [{
        "url": f"https://upload.wikimedia.org/{title}", "thumburl": f"https://upload.wikimedia.org/thumb/{title}.jpg", "width": w, "height": h, "duration": dur, "size": size, "mime": "video/webm",
        "derivatives": ([{"src": f"https://upload.wikimedia.org/d480/{title}", "width": 854, "height": 480}, {"src": f"https://upload.wikimedia.org/d240/{title}", "width": 426, "height": 240}] if derivs else []),
        "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}}}]}


def test_commons_candidates_keep_only_clean_licences_and_landscape_footage():
    data = {"query": {"pages": [commons_page(1, "Waves 1.ogv", "CC0"), commons_page(2, "Waves 2.webm", "CC BY-SA 4.0"), commons_page(3, "Phone.webm", "CC0", w=720, h=1280),
                                commons_page(4, "Big.webm", "CC BY 4.0", size=900_000_000), commons_page(5, "Big2.webm", "CC0", size=900_000_000, derivs=False),
                                commons_page(6, "Beach.webm", "Public domain", artist="")]}}
    got = clips.commons_search("waves", fetch=lambda url, **kw: data)
    assert [c["id"] for c in got] == ["1", "4", "6"]
    assert got[0]["video_url"] == "https://upload.wikimedia.org/Waves 1.ogv" and got[0]["creator"] == "Mostafa" and got[0]["thumb_url"].endswith(".jpg")   # HTML stripped from the author
    assert got[1]["video_url"] == "https://upload.wikimedia.org/d480/Big.webm"      # an enormous original is replaced by the largest rendition
    assert got[2]["creator"] == "Unknown" and "Public domain" in got[2]["attribution"] and got[0]["attribution"].startswith("Video by Mostafa (CC0) via Wikimedia Commons (https://commons.wikimedia.org/wiki/File:Waves_1.ogv)")


def cand(provider, i, dur=10.0):
    return {"provider": provider, "id": str(i), "thumb_url": f"https://t/{provider}{i}.jpg", "video_url": f"https://v/{provider}{i}.mp4", "width": 1920, "height": 1080, "duration": dur,
            "creator": "Z", "creator_url": "", "landing_url": "https://l", "license": "CC0", "alt": "a", "attribution": "attr"}


def test_gather_interleaves_providers_survives_one_failing_and_drops_tiny_footage(monkeypatch):
    monkeypatch.setattr(clips, "pexels_search", lambda q, k, f: [cand("pexels", 1), cand("pexels", 2, dur=1.0), cand("pexels", 3)])
    monkeypatch.setattr(clips, "commons_search", lambda q, f: [cand("commons", 1), cand("commons", 2)])
    got = clips.gather("q", pexels_key="k")
    assert [clips.candidate_key(c) for c in got] == ["pexels:1", "commons:1", "pexels:3", "commons:2"]    # the 1 s clip is gone
    monkeypatch.setattr(clips, "pexels_search", lambda q, k, f: (_ for _ in ()).throw(FetchError("down")))
    assert [clips.candidate_key(c) for c in clips.gather("q", pexels_key="k")] == ["commons:1", "commons:2"]


# ---------------------------------------------------------------- footage
def frame_sizes(mp4: bytes, tmp_path):
    p = tmp_path / "n.mp4"
    p.write_bytes(mp4)
    f = clips.ClipFrames(str(p))
    return f, f.frame(0).size


def test_normalise_trims_long_footage_crops_to_16_9_and_never_loops_short_footage(tmp_path):
    long_src = make_source(6, "640x480", tmp_path=tmp_path)                      # 4:3 source
    mp4, loops_after = clips.normalise(long_src, need_seconds=3.0, source_seconds=6.0, suffix=".mp4")
    frames, size = frame_sizes(mp4, tmp_path)
    assert size == (1280, 720) and abs(len(frames) - 90) <= 2 and loops_after == pytest.approx(3.0)
    short_src = make_source(2, tmp_path=tmp_path)
    mp4, loops_after = clips.normalise(short_src, need_seconds=5.0, source_seconds=2.0, suffix=".mp4")
    frames, size = frame_sizes(mp4, tmp_path)
    assert size == (1280, 720) and abs(len(frames) - 60) <= 2 and loops_after == pytest.approx(2.0)     # a 2 s clip stays 2 s: it plays once, it is never looped to 5 s
    assert clips.ClipFrames.frame.__code__ and len(frames) < 100
    with pytest.raises(RuntimeError):
        clips.normalise(b"this is not a video", need_seconds=3.0, source_seconds=5.0, suffix=".mp4")


def test_other_container_formats_decode_too(tmp_path):
    for fmt in ("webm", "ogv"):
        try:
            src = make_source(3, fmt=fmt, tmp_path=tmp_path)
        except subprocess.CalledProcessError:
            pytest.skip(f"this ffmpeg build cannot encode {fmt}")
        mp4, _ = clips.normalise(src, need_seconds=2.0, source_seconds=3.0, suffix="." + fmt)
        assert frame_sizes(mp4, tmp_path)[1] == (1280, 720)


# ---------------------------------------------------------------- scene rendering
def test_a_clip_scene_plays_holds_its_last_frame_and_degrades_to_a_placeholder(tmp_path):
    mp4, _ = clips.normalise(make_source(4, tmp_path=tmp_path), need_seconds=3.0, source_seconds=4.0, suffix=".mp4")
    p = tmp_path / "c.mp4"
    p.write_bytes(mp4)
    frames = clips.ClipFrames(str(p))
    tl = small_timeline(6.0, ["clip", "title"])
    tl["scenes"][0]["props"] = {"asset": "clip.mp4", "alt": "waves", "credit": "Video: Z / Pexels"}
    r = Renderer(tl, clip_loader=lambda key: frames if key == "clip.mp4" else None)
    a, b, end = r.frame_at(0.5), r.frame_at(1.5), r.frame_at(2.99)
    assert a.size == (1920, 1080)
    assert a.tobytes() != b.tobytes() and b.tobytes() != end.tobytes()                                                # it moves
    assert r._draw_spec(tl["scenes"][0], 3.0).tobytes() == r._draw_spec(tl["scenes"][0], 9.0).tobytes()              # after its end (the crossfade) it holds the last frame
    broken = Renderer(tl, clip_loader=lambda key: (_ for _ in ()).throw(RuntimeError("corrupt")))
    assert broken.frame_at(1.0).size == (1920, 1080)                                                                 # unreadable footage never fails the render


# ---------------------------------------------------------------- the scouting flow
def fake_world(monkeypatch, cands, bad_urls=()):
    monkeypatch.setattr(clips, "gather", lambda q, **kw: list(cands))
    def get(url, **kw):
        if url in bad_urls:
            raise FetchError("gone")
        return b"RAW:" + url.encode()
    norm = lambda raw, **kw: (b"MP4:" + raw, kw["source_seconds"])
    return get, norm


def test_scout_picks_the_reviewed_clip_and_returns_a_credit_and_ledger_entry(monkeypatch):
    cands = [cand("commons", 1, dur=4.0), cand("pexels", 2, dur=12.0), cand("commons", 3, dur=9.0)]   # 4 s is under 75% of the 8 s scene: never offered (it would freeze, not loop)
    get, norm = fake_world(monkeypatch, cands)
    seen = {}
    review = lambda cs, n, a, q, **kw: (seen.update(order=[clips.candidate_key(c) for c in cs]) or (1, "the second one fits", 0.003, [0, 1, 2]))
    out = clips.scout_clip("waves", "narration", "alt", need_seconds=8.0, fetch_bytes_fn=get, review=review, normalise_fn=norm)
    assert seen["order"] == ["pexels:2", "commons:3"]                            # footage long enough for the scene is offered first; too-short footage never is
    assert out["chosen"] == "commons:3" and out["mp4"] == b"MP4:RAW:https://v/commons3.mp4" and out["credit"] == "Video: Z (CC0)"
    assert out["review"]["reason"] == "the second one fits" and out["entry"]["source"] == "commons" and len(out["candidates"]) == 2
    assert clips.scout_clip("w", "n", need_seconds=8.0, fetch_bytes_fn=get, review=None, normalise_fn=norm, verify_fn=None) is not None
    monkeypatch.setattr(clips, "gather", lambda q, **kw: [cand("commons", 1, dur=3.0), cand("pexels", 2, dur=5.0)])
    assert clips.scout_clip("w", "n", need_seconds=10.0, fetch_bytes_fn=get, review=None, normalise_fn=norm, verify_fn=None) is None   # all under 75% of the scene: a photo instead


def test_scout_rejects_all_falls_back_on_review_errors_and_tries_the_next_file(monkeypatch):
    get, norm = fake_world(monkeypatch, [cand("pexels", 1), cand("pexels", 2)], bad_urls=("https://v/pexels1.mp4",))
    none = clips.scout_clip("q", "n", review=lambda *a, **k: (None, "all show logos", 0.002, [0, 1]), fetch_bytes_fn=get, normalise_fn=norm)
    assert none["rejected_all"] is True and none["mp4"] is None
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bedrock down"))
    out = clips.scout_clip("q", "n", review=boom, fetch_bytes_fn=get, normalise_fn=norm)
    assert out["chosen"] == "pexels:2" and out["review"]["source"] == "fallback"       # review failed, the first file was gone: the second is used
    assert clips.scout_clip("q", "n", review=None, fetch_bytes_fn=lambda *a, **k: (_ for _ in ()).throw(FetchError("x")), normalise_fn=norm) is None
    monkeypatch.setattr(clips, "gather", lambda q, **kw: [])
    assert clips.scout_clip("a b c d", "n") is None


def test_every_wording_is_searched_and_their_results_are_pooled(monkeypatch):
    asked = []
    monkeypatch.setattr(clips, "gather", lambda q, **kw: (asked.append(q), [cand("commons", 1)] if q == "dark storm" else [cand("commons", 7)] if q == "stormy sky" else [])[1])
    out = clips.scout_clip("dark storm clouds rolling over fields", "n", "stormy sky", fetch_bytes_fn=lambda *a, **k: b"x", review=None, normalise_fn=lambda raw, **kw: (b"m", 5.0))
    assert asked == ["dark storm clouds rolling over fields", "stormy sky", "dark storm"] and {c["id"] for c in out["candidates"]} == {"1", "7"}


def test_query_variants_are_distinct_short_and_at_most_three():
    assert clips.query_variants("waves crashing on rocks", "surf on a rocky coast") == ["waves crashing on rocks", "surf on a rocky coast", "waves crashing"]
    assert clips.query_variants("waves", "Waves") == ["waves"] and clips.query_variants("a b", "") == ["a b"] and clips.query_variants("", "") == []


def test_the_pool_is_round_robin_deduplicated_capped_and_too_short_files_do_not_use_up_slots(monkeypatch):
    got = clips.merge_pools([[cand("pixabay", i) for i in (1, 2, 3)], [cand("pixabay", i) for i in (2, 9)]], limit=4)
    assert [clips.candidate_key(c) for c in got] == ["pixabay:1", "pixabay:2", "pixabay:9", "pixabay:3"]
    monkeypatch.setattr(clips, "gather", lambda q, **kw: [cand("pixabay", i, dur=2.0 if i < 20 else 9.0) for i in (list(range(1, 15)) + [21, 22])])
    out = clips.scout_clip("a", "n", need_seconds=8.0, fetch_bytes_fn=lambda *a, **k: b"x", review=None, normalise_fn=lambda raw, **kw: (b"m", 5.0))
    assert [c["id"] for c in out["candidates"]] == ["21", "22"]     # fourteen 2 s files (under 75% of 8 s) were filtered out before the cap, not after


NASA_SEARCH = {"collection": {"items": [
    {"data": [{"nasa_id": "GSFC_1_Tides", "title": "How Tides Work", "media_type": "video", "center": "GSFC", "secondary_creator": "Jane Doe"}],
     "links": [{"href": "http://images-assets.nasa.gov/video/GSFC_1_Tides/GSFC_1_Tides~large.jpg", "rel": "alternate", "render": "image", "width": 800},
               {"href": "http://images-assets.nasa.gov/video/GSFC_1_Tides/GSFC_1_Tides~small.jpg", "rel": "alternate", "render": "image", "width": 200}]},
    {"data": [{"nasa_id": "HQ_2_Briefing", "title": "Administrator news conference", "media_type": "video"}], "links": [{"href": "https://x/t.jpg", "rel": "alternate", "render": "image", "width": 800}]},
    {"data": [{"nasa_id": "KSC_3_Low", "title": "Old SD footage", "media_type": "video"}], "links": [{"href": "https://x/t.jpg", "rel": "alternate", "render": "image", "width": 800}]},
    {"data": [{"nasa_id": "bad id/../x", "title": "Evil", "media_type": "video"}], "links": []},
]}}
NASA_META = {"GSFC_1_Tides": {"QuickTime:Duration": "0:01:05", "QuickTime:ImageWidth": 1920, "QuickTime:ImageHeight": 1080},
             "KSC_3_Low": {"QuickTime:Duration": "12.5 s", "QuickTime:ImageWidth": 640, "QuickTime:ImageHeight": 480}}


def nasa_fetch(url, **kw):
    if "images-api.nasa.gov/search" in url:
        return NASA_SEARCH
    for nid, meta in NASA_META.items():
        if f"/video/{nid}/metadata.json" in url:
            return meta
    raise FetchError("404", status=404)


def test_nasa_candidates_use_the_720p_rendition_credit_nasa_and_skip_interviews_and_small_files():
    got = clips.nasa_search("tides", fetch=nasa_fetch)
    assert len(got) == 1
    c = got[0]
    assert c["video_url"] == "https://images-assets.nasa.gov/video/GSFC_1_Tides/GSFC_1_Tides~medium.mp4" and (c["width"], c["height"], c["duration"]) == (1280, 720, 65.0)
    assert c["thumb_url"] == "https://images-assets.nasa.gov/video/GSFC_1_Tides/GSFC_1_Tides~large.jpg"    # https, the 800 px poster
    assert clips.credit_line(c) == "Video: NASA" and c["attribution"].startswith("Video: NASA (Jane Doe), https://images.nasa.gov/details/GSFC_1_Tides")
    assert clips.stock.ledger_entry(c)["source"] == "nasa" and "public domain" in c["license"]
    assert clips.nasa_search("tides", fetch=nasa_fetch, hd=True)[0]["video_url"].endswith("~large.mp4")
    assert [c["id"] for c in clips.nasa_search("tides", fetch=nasa_fetch, orientation="portrait")] == ["GSFC_1_Tides"]   # a vertical video takes landscape footage too (cropped)


def test_nasa_joins_the_gather_and_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("CLIPS_NASA", "1")
    monkeypatch.setattr(clips, "commons_usable", lambda: False)
    got = clips.gather("tides", fetch=nasa_fetch)
    assert [c["provider"] for c in got] == ["nasa"]
    monkeypatch.setenv("CLIPS_NASA", "0")
    assert clips.gather("tides", fetch=lambda *a, **k: pytest.fail("NASA is off")) == []


# ---------------------------------------------------------------- the reviewer sees clips as clips
def test_the_review_uses_the_clip_prompt_and_says_clips(monkeypatch):
    seen = {}
    def fake_complete(system, user, images=None, **kw):
        seen.update(system=system, user=user, n=len(images))
        return '{"choice": 2, "scores": [3, 9], "reason": "matches"}', {"cost_usd": 0.001}
    from PIL import Image as I
    import io
    buf = io.BytesIO(); I.new("RGB", (64, 36)).save(buf, "JPEG")
    idx, reason, cost, shown = stock.llm_review([cand("pexels", 1), cand("pexels", 2)], "n", "a", "q", fetch_bytes_fn=lambda *a, **k: buf.getvalue(), complete=fake_complete, system=clips.CLIP_REVIEW_SYSTEM, noun="clip")
    assert idx == 1 and seen["system"] is clips.CLIP_REVIEW_SYSTEM and "best of the 2 clips" in seen["user"] and "footage editor" in seen["system"]


# ---------------------------------------------------------------- planning and the timeline
def test_clip_scenes_are_documented_sanitised_and_remade_only_when_their_query_changes(monkeypatch):
    assert "- clip:" in plan_mod.scene_docs() and "specific named person, place, landmark, brand" in plan_mod.system_prompt("en")
    monkeypatch.setenv("CLIPS_ENABLED", "0")
    assert "- clip:" not in plan_mod.scene_docs()
    monkeypatch.delenv("CLIPS_ENABLED")
    raw = {"legit": True, "title": "T", "beats": [{"narration": "A line of narration that is long enough to count.", "scene": {"type": "clip", "props": {"alt": "traffic at night"}}},
                                                    {"narration": "Another line of narration that is long enough to count.", "scene": {"type": "clip", "props": {}}}]}
    plan, warns = plan_mod.validate_plan(raw)
    assert plan["beats"][0]["scene"] == {"type": "clip", "props": {"clip_query": "traffic at night", "alt": "traffic at night"}}
    assert plan["beats"][1]["scene"]["type"] == "title" and any("scene replaced" in w for w in warns)       # an empty clip scene becomes a plain card, never a hole
    beat = plan["beats"][0]
    done = {"tts_hash": plan_mod.tts_hash(plan, beat), "audio_key": "a", "duration": 3.0, "query": "traffic at night", "clip_asset": "k.mp4"}
    assert plan_mod.needs_media(plan, {**beat, "media": done}) is False
    assert plan_mod.needs_media(plan, {**beat, "media": {**done, "query": "other"}}) is True
    assert plan_mod.needs_media(plan, {**beat, "media": {k: v for k, v in done.items() if k != "clip_asset"}}) is True
    assert plan_mod.needs_media(plan, {**beat, "media": {**{k: v for k, v in done.items() if k != "clip_asset"}, "asset": "still.jpg"}}) is False   # a still photo stood in


def test_the_timeline_uses_the_clip_else_a_still_photo_else_a_title_card():
    beat = {"id": "b1", "narration": "Waves roll in slowly over the sand.", "scene": {"type": "clip", "props": {"clip_query": "waves", "alt": "waves on sand"}}}
    plan = {"beats": [beat], "theme": "midnight"}
    def tl(info):
        return build_timeline(plan, [{"duration": 3.0, **info}], video_id="v")["scenes"][0]
    s = tl({"clip_asset": "c.mp4", "credit": "Video: Z / Pexels"})
    assert s["type"] == "clip" and s["props"] == {"asset": "c.mp4", "alt": "waves on sand", "credit": "Video: Z / Pexels"}
    s = tl({"asset": "still.jpg", "credit": "Photo: Q / Unsplash"})
    assert s["type"] == "image" and s["props"]["asset"] == "still.jpg" and s["props"]["credit"] == "Photo: Q / Unsplash"
    s = tl({})
    assert s["type"] == "title" and s["props"]["title"] == "waves on sand"


# ---------------------------------------------------------------- the beat step
def test_the_beat_step_stores_the_clip_as_a_working_file_and_falls_back_to_a_still(monkeypatch):
    from engine.handlers import beat_handler

    puts = []
    monkeypatch.setattr(beat_handler.awsio, "put_bytes", lambda key, data, ct="", bkt=None, working=False: puts.append((key, ct, working)))
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "PEXELS-KEY")
    seen = {}
    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda q, n, a, **kw: (seen.update(q=q, need=kw["need_seconds"], key=kw["pexels_key"]),
                                                                             {"mp4": b"MP4", "credit": "Video: Z / Pexels", "entry": {"source": "pexels"}, "chosen": "pexels:1", "review": {"cost_usd": 0.0}})[1])
    monkeypatch.setattr(beat_handler.costs, "add_cost", lambda *a, **k: None)
    plan = {"beats": []}
    beat = {"id": "b7", "narration": "Waves roll in.", "scene": {"type": "clip", "props": {"clip_query": "waves", "alt": "waves"}}}
    out = beat_handler.make_clip(plan, beat, "vid", "cost_usd", 4.0)
    assert out["clip_asset"].startswith("generation/v2/vid/assets/clip_b7_") and out["clip_asset"].endswith(".mp4") and puts == [(out["clip_asset"], "video/mp4", True)]
    assert seen == {"q": "waves", "need": pytest.approx(0.4 + 4.0 + 0.55 + 0.6), "key": "PEXELS-KEY"} and out["credit"] == "Video: Z / Pexels" and out["ledger"] == {"source": "pexels"}

    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda *a, **k: None)
    monkeypatch.setattr(beat_handler, "make_photo", lambda plan, b, v, c: {"query": b["scene"]["props"]["image_query"], "pick": None, "asset": "generation/v2/vid/assets/img_b7_x.jpg", "credit": "Photo: Q / Unsplash"})
    out = beat_handler.make_clip(plan, beat, "vid", "cost_usd", 4.0)
    assert "clip_asset" not in out and out["asset"].endswith("img_b7_x.jpg") and out["query"] == "waves"


# ---------------------------------------------------------------- Pixabay
PIXABAY = {"total": 3, "totalHits": 3, "hits": [
    {"id": 283533, "pageURL": "https://pixabay.com/videos/id-283533/", "tags": "ocean, waves, sea", "duration": 40, "user": "BlenderTimer", "user_id": 9538909,
     "videos": {"large": {"url": "https://cdn.pixabay.com/video/l.mp4", "width": 1920, "height": 1080, "size": 38_000_000, "thumbnail": "https://cdn.pixabay.com/video/l.jpg"},
                "medium": {"url": "https://cdn.pixabay.com/video/m.mp4", "width": 1280, "height": 720, "size": 15_000_000, "thumbnail": "https://cdn.pixabay.com/video/m.jpg"},
                "small": {"url": "https://cdn.pixabay.com/video/s.mp4", "width": 960, "height": 540, "size": 10_000_000, "thumbnail": "https://cdn.pixabay.com/video/s.jpg"},
                "tiny": {"url": "", "width": 0, "height": 0, "size": 0, "thumbnail": ""}}},
    {"id": 2, "pageURL": "https://pixabay.com/videos/id-2/", "tags": "x", "duration": 9, "user": "A", "user_id": 1,
     "videos": {"medium": {"url": "https://cdn.pixabay.com/video/p.mp4", "width": 720, "height": 1280, "size": 4_000_000, "thumbnail": "https://cdn.pixabay.com/video/p.jpg"}}},   # portrait
    {"id": 3, "pageURL": "https://pixabay.com/videos/id-3/", "tags": "y", "duration": 9, "user": "B", "user_id": 2,
     "videos": {"medium": {"url": "https://cdn.pixabay.com/video/h.mp4", "width": 1280, "height": 720, "size": 400_000_000, "thumbnail": "https://cdn.pixabay.com/video/h.jpg"}}},    # too big
]}


def test_pixabay_candidates_use_the_smallest_720p_file_and_carry_the_credit():
    clips._CACHE.clear()
    seen = {}
    got = clips.pixabay_search("ocean waves", "PIX-KEY", fetch=lambda url, **kw: (seen.update(url=url), PIXABAY)[1])
    assert seen["url"].startswith("https://pixabay.com/api/videos/?") and "safesearch=true" in seen["url"] and "video_type=film" in seen["url"] and "key=PIX-KEY" in seen["url"]
    assert [c["id"] for c in got] == ["283533"]                                  # portrait and enormous files are skipped
    c = got[0]
    assert c["video_url"] == "https://cdn.pixabay.com/video/m.mp4" and c["thumb_url"].endswith("m.jpg") and c["duration"] == 40.0     # medium (1280x720), not the 1080p file
    assert c["creator"] == "BlenderTimer" and c["creator_url"] == "https://pixabay.com/users/BlenderTimer-9538909/" and c["license"] == "Pixabay Content License"
    assert c["attribution"] == "Video by BlenderTimer on Pixabay (https://pixabay.com/videos/id-283533/)" and clips.credit_line(c) == "Video: BlenderTimer / Pixabay"
    assert clips.pixabay_search("x", "", fetch=lambda *a, **k: pytest.fail("no key, no request")) == []


def test_pixabay_results_are_cached_for_24_hours_and_failures_are_not():
    clips._CACHE.clear()
    calls = []
    fetch = lambda url, **kw: (calls.append(url), PIXABAY)[1]
    clips.pixabay_search("Ocean Waves", "K", fetch=fetch)
    clips.pixabay_search("ocean waves ", "K", fetch=fetch)                       # same query: no second request
    assert len(calls) == 1
    clips.pixabay_search("mountain lake", "K", fetch=fetch)
    assert len(calls) == 2
    clock = {"t": 1000.0}
    assert clips._cached("k", lambda: "a", now=lambda: clock["t"]) == "a"
    clock["t"] += clips.CACHE_TTL_S - 5
    assert clips._cached("k", lambda: "b", now=lambda: clock["t"]) == "a"
    clock["t"] += 10
    assert clips._cached("k", lambda: "b", now=lambda: clock["t"]) == "b"       # expired after 24 h
    with pytest.raises(FetchError):
        clips._cached("bad", lambda: (_ for _ in ()).throw(FetchError("x")))
    assert "bad" not in clips._CACHE


def test_gather_asks_three_providers_and_interleaves_them(monkeypatch):
    monkeypatch.setattr(clips, "pexels_search", lambda q, k, f: [cand("pexels", 1)])
    monkeypatch.setattr(clips, "pixabay_search", lambda q, k, f: [cand("pixabay", 1), cand("pixabay", 2)])
    monkeypatch.setattr(clips, "commons_search", lambda q, f: [cand("commons", 1)])
    assert [clips.candidate_key(c) for c in clips.gather("q", pexels_key="a", pixabay_key="b")] == ["pexels:1", "pixabay:1", "commons:1", "pixabay:2"]


# ---------------------------------------------------------------- three frames of the footage we use (start, middle, end)
@pytest.mark.parametrize("seconds,times", [(1.5, [0.75]), (5, [0.6, 2.5, 4.4]), (20, [2.4, 10.0, 17.6])])
def test_verification_samples_start_middle_and_end_of_the_footage(seconds, times):
    assert clips.verify_frame_times(seconds) == pytest.approx(times, abs=0.02)


def test_verification_sends_only_a_few_small_frames_in_a_single_call(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_VERIFY", "1")
    mp4, _ = clips.normalise(make_source(4, tmp_path=tmp_path), need_seconds=3.0, source_seconds=4.0, suffix=".mp4")
    seen = {"calls": 0}
    def complete(system, user, images=None, **kw):
        seen.update(calls=seen["calls"] + 1, n=len(images), sizes=[Image.open(__import__("io").BytesIO(i)).size for i in images], model=kw.get("model"), max_tokens=kw.get("max_tokens"))
        return '{"ok": true, "score": 9, "reason": "calm waves"}', {"cost_usd": 0.0007}
    ok, why, cost = clips.verify(mp4, "Waves roll in.", "waves", "waves", 3.0, complete=complete)
    assert (ok, why, cost) == (True, "9/10: calm waves", 0.0007) and seen["calls"] == 1 and seen["n"] == 3      # one call, three frames
    weak = lambda *a, **k: ('{"ok": true, "score": 5, "reason": "loosely related"}', {"cost_usd": 0.0007})
    assert clips.verify(mp4, "n", "a", "q", 3.0, complete=weak)[0] is False                              # a loose match is discarded: accuracy over having a clip
    assert seen["sizes"][0][0] == 512 and seen["max_tokens"] == 300
    bad = lambda *a, **k: ('{"ok": false, "reason": "a logo is visible"}', {"cost_usd": 0.0007})
    assert clips.verify(mp4, "n", "a", "q", 3.0, complete=bad)[:2] == (False, "0/10: a logo is visible")


def test_verification_fails_closed_and_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_VERIFY", "1")
    mp4, _ = clips.normalise(make_source(3, tmp_path=tmp_path), need_seconds=2.0, source_seconds=3.0, suffix=".mp4")
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bedrock down"))
    assert clips.verify(mp4, "n", "a", "q", 2.0, complete=boom)[0] is False                        # a clip that could not be checked is discarded: a photo is better than an odd clip
    junk = lambda *a, **k: ("no json here", {"cost_usd": 0.0})
    assert clips.verify(mp4, "n", "a", "q", 2.0, complete=junk)[0] is False
    assert clips.verify(b"not a video", "n", "a", "q", 2.0, complete=boom)[0] is False             # nothing to check
    monkeypatch.setenv("CLIP_VERIFY", "0")
    assert clips.verify(mp4, "n", "a", "q", 2.0, complete=lambda *a, **k: pytest.fail("off means off"))[0] is True


def test_a_clip_that_fails_verification_is_skipped_for_the_next_candidate(monkeypatch):
    get, norm = fake_world(monkeypatch, [cand("pixabay", 1), cand("pixabay", 2)])
    verdicts = iter([(False, "watermark in frame", 0.0007), (True, "fine", 0.0007)])
    seen = []
    def verify_fn(mp4, narration, alt, query, seconds):
        seen.append(mp4)
        return next(verdicts)
    out = clips.scout_clip("q", "n", review=None, fetch_bytes_fn=get, normalise_fn=norm, verify_fn=verify_fn)
    assert out["chosen"] == "pixabay:2" and len(seen) == 2 and out["review"]["verified"] == "fine" and out["review"]["cost_usd"] == pytest.approx(0.0014)
    none = clips.scout_clip("q", "n", review=None, fetch_bytes_fn=get, normalise_fn=norm, verify_fn=lambda *a: (False, "no", 0.0))
    assert none is None                                                                            # every candidate failed: the beat falls back to a still


def test_a_failing_clip_upload_falls_back_to_a_still_instead_of_failing_the_beat(monkeypatch):
    from engine.handlers import beat_handler

    monkeypatch.setattr(beat_handler.awsio, "put_bytes", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("AccessDenied")))
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "")
    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda *a, **k: {"mp4": b"MP4", "credit": "Video: Z / Pixabay", "entry": {}, "chosen": "pixabay:1", "review": {"cost_usd": 0.0}})
    monkeypatch.setattr(beat_handler.costs, "add_cost", lambda *a, **k: None)
    monkeypatch.setattr(beat_handler, "make_photo", lambda plan, b, v, c: {"query": "waves", "pick": None, "asset": "generation/v2/vid/assets/img_x.jpg", "credit": "Photo: Q / Unsplash"})
    beat = {"id": "b7", "narration": "Waves roll in.", "scene": {"type": "clip", "props": {"clip_query": "waves", "alt": "waves"}}}
    out = beat_handler.make_clip({"beats": []}, beat, "vid", "cost_usd", 4.0)
    assert "clip_asset" not in out and out["asset"].endswith("img_x.jpg")


# ================================================================= why clips fell back to photos in real use (found on the owner's morning videos)
def test_commons_is_only_searched_when_the_client_identifies_itself(monkeypatch):
    from engine import netsafe
    monkeypatch.setattr(clips, "pexels_search", lambda q, k, f: [])
    monkeypatch.setattr(clips, "pixabay_search", lambda q, k, f: [cand("pixabay", 1)])
    monkeypatch.setattr(clips, "commons_search", lambda q, f: [cand("commons", 1), cand("commons", 2)])
    monkeypatch.delenv("CLIPS_COMMONS", raising=False)
    monkeypatch.setattr(netsafe, "USER_AGENT", "explainer-engine/2.0")                       # the default: Wikimedia would answer 429 to every download
    assert [clips.candidate_key(c) for c in clips.gather("q", pixabay_key="k")] == ["pixabay:1"]
    monkeypatch.setattr(netsafe, "USER_AGENT", "videomk/1.0 (contact: someone@example.org)")
    assert [clips.candidate_key(c) for c in clips.gather("q", pixabay_key="k")] == ["pixabay:1", "commons:1", "commons:2"]
    monkeypatch.setenv("CLIPS_COMMONS", "0")
    assert [clips.candidate_key(c) for c in clips.gather("q", pixabay_key="k")] == ["pixabay:1"]
    monkeypatch.setattr(netsafe, "USER_AGENT", "explainer-engine/2.0")
    monkeypatch.setenv("CLIPS_COMMONS", "1")
    assert len(clips.gather("q", pixabay_key="k")) == 3


def test_the_alt_wording_is_searched_inside_the_one_scout_call_not_by_a_second_review(monkeypatch):
    from engine.handlers import beat_handler

    seen = []
    def scout(q, n, a, **kw):
        seen.append((q, a))
        return {"mp4": b"MP4", "credit": "Video: Z / Pixabay", "entry": {}, "chosen": "pixabay:9", "review": {"cost_usd": 0.001}}
    monkeypatch.setattr(beat_handler.clips, "scout_clip", scout)
    monkeypatch.setattr(beat_handler.awsio, "put_bytes", lambda *a, **k: None)
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "K")
    monkeypatch.setattr(beat_handler.costs, "add_cost", lambda *a, **k: None)
    beat = {"id": "b7", "narration": "Storm clouds gather over the empty road.", "scene": {"type": "clip", "props": {"clip_query": "dark clouds over desert road", "alt": "storm clouds gathering over empty highway"}}}
    out = beat_handler.make_clip({"beats": []}, beat, "vid", "cost_usd", 4.0)
    assert seen == [("dark clouds over desert road", "storm clouds gathering over empty highway")] and out["clip_asset"].endswith(".mp4")


def test_current_events_get_photographs_not_stock_footage():
    from engine import plan as plan_mod

    def raw(stype, props):
        return {"legit": True, "title": "T", "beats": [{"narration": "A line about the news that is long enough to count.", "scene": {"type": stype, "props": props}}]}
    plan, warns = plan_mod.validate_plan(raw("clip", {"clip_query": "warship at sea", "alt": "navy ship"}), allow_clips=False)
    assert plan["beats"][0]["scene"] == {"type": "image", "props": {"image_query": "warship at sea", "alt": "navy ship", "ken_burns": "in"}} and any("no stock footage" in w for w in warns)
    assert plan_mod.validate_plan(raw("clip", {"clip_query": "waves", "alt": "waves"}))[0]["beats"][0]["scene"]["type"] == "clip"        # everything else keeps clips
    assert "- clip:" in plan_mod.system_prompt("en") and "- clip:" not in plan_mod.system_prompt("en", None, 10, allow_clips=False)
    assert "specific named person, place, landmark, brand, event" in plan_mod.system_prompt("en")


def test_a_brief_that_asks_for_footage_is_told_to_use_clips_freely_with_generic_wording():
    from engine import plan as plan_mod
    p = plan_mod.system_prompt("en")
    assert "asks for video, footage or clips" in p and "use them even more freely" in p and "generic" in p


def test_visual_topics_are_told_to_use_clips_for_a_third_to_almost_half_of_the_beats_each_one_short():
    p = plan_mod.system_prompt("en")
    assert "ONE BEAT IN THREE" in p and "10 to 18 words" in p and "clip_queries" in p and "MONTAGE" in p and "never looped" in p and "never a brand" in p
    assert "never a clip" in p                                                   # numbers, comparisons, lists, abstract ideas keep charts and text
    assert "about 30 to 45 percent of the beats of a visual video are clips or montages" in p   # the photograph rule no longer says every beat is a photograph
    assert "30 to 45 percent" not in plan_mod.system_prompt("en", None, 10, allow_clips=False)
    assert "short video clip" not in plan_mod.images_rule(10) and "short video clip or montage" in plan_mod.images_rule(10, clips=True)


def test_a_clip_with_long_narration_becomes_a_photograph():
    def raw(words):
        return {"legit": True, "title": "T", "beats": [{"narration": " ".join(["word"] * words), "scene": {"type": "clip", "props": {"clip_query": "waves", "alt": "surf"}}}]}
    ok, _ = plan_mod.validate_plan(raw(plan_mod.MAX_CLIP_NARRATION_WORDS))
    assert ok["beats"][0]["scene"]["type"] == "clip"
    long, warns = plan_mod.validate_plan(raw(plan_mod.MAX_CLIP_NARRATION_WORDS + 1))
    assert long["beats"][0]["scene"] == {"type": "image", "props": {"image_query": "waves", "alt": "surf", "ken_burns": "in"}} and any("too long for stock footage" in w for w in warns)


def test_the_reviewers_reject_contradictions_and_loose_matches_accuracy_over_having_a_clip():
    for prompt in (clips.CLIP_REVIEW_SYSTEM, clips.CLIP_VERIFY_SYSTEM):
        low = " ".join(prompt.lower().split())   # the prompts wrap lines
        assert "contradict" in low and "intended subject" in low and "another city" in low
        assert "no clip is better than a wrong one" in low or "a wrong or odd clip is worse than none" in low
    assert clips.MAX_CANDIDATES == 12


def test_playback_holds_the_last_frame_past_the_end_and_never_loops(tmp_path):
    mp4, _ = clips.normalise(make_source(2, tmp_path=tmp_path), need_seconds=2.0, source_seconds=2.0, suffix=".mp4")
    p = tmp_path / "c.mp4"; p.write_bytes(mp4)
    cf = clips.ClipFrames(str(p))
    last = cf.frame(len(cf) - 1).tobytes()
    assert cf.frame(len(cf)).tobytes() == last and cf.frame(len(cf) * 3).tobytes() == last           # past the end: the last frame, not frame 0 again


# ---------------------------------------------------------------- montage: 2-4 short clips in sequence inside one beat
def montage_props(*qs, alt="x"):
    return {"clip_query": qs[0], "clip_queries": list(qs), "alt": alt}


def test_a_montage_scene_is_sanitised_deduplicated_capped_and_a_single_query_is_a_plain_clip():
    sp = plan_mod.sanitize_props
    got = sp("clip", {"clip_queries": ["waves on rocks", "Waves on rocks", "seagulls flying", "fishing boat", "harbour at dusk", "a fifth one"], "alt": "sea"})
    assert got["clip_query"] == "waves on rocks" and got["clip_queries"] == ["waves on rocks", "seagulls flying", "fishing boat", "harbour at dusk"]   # at most 4, duplicates gone
    one = sp("clip", {"clip_queries": ["waves on rocks", "WAVES ON ROCKS"], "alt": "sea"})
    assert "clip_queries" not in one and one["clip_query"] == "waves on rocks"                       # one distinct query is the same thing as a single clip
    assert sp("clip", {"clip_query": "bees"})["clip_query"] == "bees" and plan_mod.clip_queries({"clip_query": "bees"}) == ["bees"]
    assert plan_mod.clip_signature(montage_props("a b", "c d")) == "a b|c d" and plan_mod.clip_signature({"clip_query": "a b"}) == "a b"
    with pytest.raises(ValueError):
        sp("clip", {"clip_queries": ["", "  "]})


def test_montage_validation_limits_narration_and_the_number_of_clips_and_allow_clips_false_removes_it():
    def raw(words, qs):
        return {"legit": True, "title": "T", "beats": [{"narration": " ".join(["word"] * words), "scene": {"type": "clip", "props": {"clip_queries": qs, "alt": "sea"}}}]}
    qs = ["waves on rocks", "seagulls flying", "fishing boat", "harbour at dusk"]
    ok, _ = plan_mod.validate_plan(raw(44, qs))
    assert ok["beats"][0]["scene"]["props"]["clip_queries"] == qs                                       # 44 words: a montage may be up to 45
    few, warns = plan_mod.validate_plan(raw(20, qs))
    assert few["beats"][0]["scene"]["props"]["clip_queries"] == qs[:3] and any("reduced to 3 clips" in w for w in warns)   # about 6 spoken words behind each clip
    one, warns = plan_mod.validate_plan(raw(8, qs))
    assert "clip_queries" not in one["beats"][0]["scene"]["props"] and any("reduced to one clip" in w for w in warns)
    long, warns = plan_mod.validate_plan(raw(46, qs))
    assert long["beats"][0]["scene"] == {"type": "image", "props": {"image_query": "waves on rocks", "alt": "sea", "ken_burns": "in"}} and any("too long" in w for w in warns)
    off, _ = plan_mod.validate_plan(raw(30, qs), allow_clips=False)
    assert off["beats"][0]["scene"]["type"] == "image"


def test_a_montage_is_remade_when_any_of_its_queries_change():
    beat = {"id": "b1", "narration": "n", "silent": True, "hold": 3.0, "scene": {"type": "clip", "props": montage_props("a b", "c d")}}
    plan = {"tts": {}}
    beat["media"] = {"tts_hash": plan_mod.tts_hash(plan, beat), "duration": 3.0, "query": "a b|c d", "clip_asset": "k.mp4"}
    assert plan_mod.needs_media(plan, beat) is False
    beat["scene"]["props"] = montage_props("a b", "c e")
    assert plan_mod.needs_media(plan, beat) is True


def test_the_slot_planner_splits_evenly_stretches_neighbours_and_refuses_a_long_freeze():
    assert clips.plan_slots(12.0, [6, 6, 6]) == [4.0, 4.0, 4.0]
    s = clips.plan_slots(12.0, [3.0, 9.0, 9.0])                      # the first clip has only 3 s (+0.5 hold, - 0.2 dissolve): its neighbours take the rest
    assert s[0] == pytest.approx(3.3) and sum(s) == pytest.approx(12.0) and s[1] > 4.0
    assert clips.plan_slots(12.0, [2.0, 2.0]) is None                 # 4 s of footage cannot cover 12 s: never a long freeze
    assert clips.plan_slots(6.0, [6.5]) == [6.0] and clips.plan_slots(6.0, []) is None


def fake_scout(results, asked=None):
    def scout(q, narration, alt="", **kw):
        if asked is not None:
            asked.append((q, narration, kw["need_seconds"]))
        r = results[q]
        return r if r is None else {"mp4": b"MP4:" + q.encode(), "entry": {"source": "pixabay", "id": q}, "credit": f"Video: {q} / Pixabay", "chosen": f"pixabay:{q}", "loops_after": r, "review": {"cost_usd": 0.001}}
    return scout


def assembled(parts, slots, avail, hd=False):
    assembled.seen = (parts, slots, avail)
    return b"ASSEMBLED"


def test_a_montage_finds_and_verifies_each_clip_on_its_own_and_credits_every_clip():
    asked = []
    out = clips.scout_montage(["a", "b", "c"], "one two three four five six seven eight nine", "alt", need_seconds=12.6, scout=fake_scout({"a": 7, "b": 7, "c": 7}, asked), assemble_fn=assembled, workers=1)
    assert out["mp4"] == b"ASSEMBLED" and out["segments"] == 3 and out["requested"] == 3 and out["slots"] == [4.0, 4.0, 4.0]
    assert [q for q, _, _ in asked] == ["a", "b", "c"] and [n for _, n, _ in asked] == ["one two three", "four five six", "seven eight nine"]   # each clip is judged against its own part of the narration
    assert all(need == pytest.approx(12.0 / 2 + clips.MONTAGE_FADE_S) for _, _, need in asked)   # long enough that the survivors cover the beat if half fail
    assert out["credit"] == "Video: a / Pixabay, b / Pixabay, c / Pixabay" and [e["id"] for e in out["entries"]] == ["a", "b", "c"] and out["chosen"] == "pixabay:a,pixabay:b,pixabay:c"
    assert out["review"]["cost_usd"] == pytest.approx(0.003)


def test_a_failed_segment_is_dropped_neighbours_stretch_and_fewer_than_half_means_the_photo():
    out = clips.scout_montage(["a", "b", "c"], "x " * 30, need_seconds=12.6, scout=fake_scout({"a": 7, "b": None, "c": 7}), assemble_fn=assembled, workers=1)
    assert out["segments"] == 2 and out["requested"] == 3 and out["slots"] == [6.0, 6.0] and out["credit"] == "Video: a / Pixabay, c / Pixabay"   # a dropped, the others take its time
    assert assembled.seen[1] == [6.0, 6.0]
    assert clips.scout_montage(["a", "b", "c"], "x " * 30, need_seconds=12.6, scout=fake_scout({"a": 7, "b": None, "c": None}), assemble_fn=assembled, workers=1) is None
    assert clips.scout_montage(["a", "b"], "x " * 30, need_seconds=12.6, scout=fake_scout({"a": 3, "b": None}), assemble_fn=assembled, workers=1) is None   # 3 s of footage under 12 s: a freeze, so the photo
    def boom(parts, slots, avail, hd=False):
        raise RuntimeError("ffmpeg")
    assert clips.scout_montage(["a", "b"], "x " * 30, need_seconds=12.6, scout=fake_scout({"a": 7, "b": 7}), assemble_fn=boom, workers=1) is None


def test_a_beat_too_short_for_the_queries_uses_fewer_clips_and_one_is_a_plain_scout():
    seen = []
    plain = lambda q, n, a="", **kw: (seen.append((q, a, kw["need_seconds"])), {"mp4": b"M", "entry": {}, "credit": "Video: z / Pixabay", "chosen": "pixabay:1", "review": {"cost_usd": 0.0}})[1]
    out = clips.scout_montage(["a", "b", "c", "d"], "words", "alt", need_seconds=5.6, scout=plain, assemble_fn=assembled)   # 5 s of scene: 2 clips at 2.5 s at most
    assert out is not None and len(seen) == 2
    seen.clear()
    clips.scout_montage(["a", "b"], "words", "alt", need_seconds=3.6, scout=plain, assemble_fn=assembled)
    assert seen == [("a", "alt", 3.6)]                                   # 3 s: a single clip, searched exactly like before


def test_the_montage_is_one_real_file_of_the_beat_length_played_once_with_a_dissolve(tmp_path):
    parts = [clips.normalise(make_source(seconds=6, tmp_path=tmp_path), need_seconds=6, source_seconds=7, suffix=".mp4") for _ in range(3)]
    slots = clips.plan_slots(12.0, [p[1] for p in parts])
    mp4 = clips.assemble_montage([p[0] for p in parts], slots, [p[1] for p in parts])
    f = tmp_path / "m.mp4"
    f.write_bytes(mp4)
    frames = clips.ClipFrames(str(f))
    assert len(frames) == pytest.approx(12 * clips.CLIP_FPS, abs=3) and frames.frame(0).size == (1280, 720)
    hd = clips.normalise(make_source(seconds=4, size="1920x1080", tmp_path=tmp_path), need_seconds=4, source_seconds=5, suffix=".mp4", hd=True)
    one = clips.assemble_montage([hd[0], hd[0]], [3.0, 3.0], [hd[1], hd[1]], hd=True)
    (tmp_path / "h.mp4").write_bytes(one)
    assert clips.ClipFrames(str(tmp_path / "h.mp4")).frame(0).size == (1920, 1080)       # 4K videos: 1080p footage stays 1080p
    vertical = clips.normalise(make_source(seconds=4, tmp_path=tmp_path), need_seconds=4, source_seconds=5, suffix=".mp4", orientation="portrait")
    v = clips.assemble_montage([vertical[0], vertical[0]], [3.0, 3.0], [vertical[1], vertical[1]])
    (tmp_path / "v.mp4").write_bytes(v)
    assert clips.ClipFrames(str(tmp_path / "v.mp4")).frame(0).size == (720, 1280)


def test_the_hard_cut_fallback_works_when_ffmpeg_has_no_xfade(tmp_path, monkeypatch):
    real = clips._montage_cmd
    monkeypatch.setattr(clips, "_montage_cmd", lambda *a, dissolve, hd: real(*a, dissolve=dissolve, hd=hd) if not dissolve else [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", "/nonexistent.mp4", "x.mp4"])
    parts = [clips.normalise(make_source(seconds=4, tmp_path=tmp_path), need_seconds=4, source_seconds=5, suffix=".mp4") for _ in range(2)]
    assert len(clips.assemble_montage([p[0] for p in parts], [3.0, 3.0], [p[1] for p in parts])) > 1000


def test_the_beat_step_stores_a_montage_with_one_ledger_line_per_clip_and_falls_back_to_the_photo(monkeypatch):
    from engine.handlers import beat_handler, timeline_handler

    puts = []
    monkeypatch.setattr(beat_handler.awsio, "put_bytes", lambda key, data, ct="", bkt=None, working=False: puts.append((key, working)))
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "K")
    monkeypatch.setattr(beat_handler.costs, "add_cost", lambda *a, **k: None)
    seen = {}
    montage = {"mp4": b"MONTAGE", "entry": {"source": "pixabay", "id": "1"}, "entries": [{"source": "pixabay", "id": "1"}, {"source": "nasa", "id": "N"}], "credit": "Video: A / Pixabay, NASA",
               "chosen": "pixabay:1,nasa:N", "segments": 2, "requested": 3, "review": {"cost_usd": 0.002}}
    monkeypatch.setattr(beat_handler.clips, "scout_montage", lambda qs, n, a, **kw: (seen.update(qs=qs, need=kw["need_seconds"]), montage)[1])
    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda *a, **k: pytest.fail("a montage is not searched as a single clip"))
    beat = {"id": "b9", "narration": "Waves, gulls and boats.", "scene": {"type": "clip", "props": montage_props("waves", "gulls", "boats", alt="sea")}}
    out = beat_handler.make_clip({"beats": []}, beat, "vid", "cost_usd", 10.0)
    assert seen["qs"] == ["waves", "gulls", "boats"] and out["query"] == "waves|gulls|boats" and out["clip_asset"].endswith(".mp4") and puts[0][1] is True
    assert out["ledger"]["id"] == "1" and [e["id"] for e in out["ledgers"]] == ["1", "N"] and out["segments"] == 2 and out["credit"] == "Video: A / Pixabay, NASA"
    plan = {"beats": [{"id": "b9", "scene": beat["scene"], "media": out}]}
    assert [e["id"] for e in timeline_handler.credits_ledger(plan)] == ["1", "N"]                      # one credit line per clip in the description
    single = {"beats": [{"id": "c", "scene": {"type": "clip", "props": {"clip_query": "x"}}, "media": {"ledger": {"id": "S"}}}]}
    assert timeline_handler.credits_ledger(single) == [{"id": "S"}]
    monkeypatch.setattr(beat_handler.clips, "scout_montage", lambda *a, **k: None)
    monkeypatch.setattr(beat_handler, "make_photo", lambda plan, b, v, c: {"query": "x", "pick": None, "asset": "generation/v2/vid/assets/img.jpg", "credit": "Photo: Q"})
    out = beat_handler.make_clip({"beats": []}, beat, "vid", "cost_usd", 10.0)
    assert "clip_asset" not in out and out["asset"].endswith("img.jpg") and out["query"] == "waves|gulls|boats"


def test_the_timeline_plays_a_montage_like_any_clip_and_the_editor_can_replace_or_remove_it():
    from engine import edits
    from engine.handlers import editor_get

    plan = {"language": "en", "voices": {"narrator": "Ruth"}, "tts": {}, "beats": [
        {"id": "b1", "narration": "One two three four five six seven eight nine ten eleven twelve.", "scene": {"type": "clip", "props": montage_props("a b", "c d", alt="x")}},
        {"id": "b2", "narration": "Another line that is long enough to count here.", "scene": {"type": "title", "props": {"title": "T", "subtitle": ""}}}]}
    new, _ = edits.apply_ops(plan, [{"op": "set_scene", "id": "b1", "type": "clip", "props": {"clip_query": "storm clouds"}}])
    assert new["beats"][0]["scene"]["props"]["clip_query"] == "storm clouds" and "clip_queries" not in new["beats"][0]["scene"]["props"]
    new, _ = edits.apply_ops(plan, [{"op": "set_scene", "id": "b1", "type": "clip", "props": {"clip_queries": ["x y", "z w", "v u"]}}])
    assert new["beats"][0]["scene"]["props"]["clip_queries"] == ["x y", "z w", "v u"]
    new, _ = edits.apply_ops(plan, [{"op": "delete", "id": "b1"}])
    assert [b["id"] for b in new["beats"]] == ["b2"]
    view = editor_get._beat_view(plan, {**plan["beats"][0], "media": {"clip_asset": "g/c.mp4", "credit": "Video: A / Pixabay, B / NASA", "segments": 2, "query": "a b|c d", "duration": 9.0}}, "g/")
    assert view["clip"]["segments"] == 2 and view["clip"]["queries"] == ["a b", "c d"] and view["clip"]["has_clip"] is True


# ---------------------------------------------------------------- landscape footage in vertical and square videos (owner, 2026-11-26)
def test_vertical_and_square_videos_take_landscape_footage_but_prefer_true_shape():
    assert clips.shape_ok(1.78, "landscape") and not clips.shape_ok(0.56, "landscape") and not clips.shape_ok(1.0, "landscape")   # a landscape video never takes tall or square footage
    assert all(clips.shape_ok(r, o) for r in (0.56, 1.0, 1.78) for o in ("portrait", "square"))
    assert clips.fit_rank(0.56, "portrait") == 0 and clips.fit_rank(1.78, "portrait") == 1 and clips.fit_rank(1.0, "square") == 0 and clips.fit_rank(1.78, "square") == 1
    data = {"hits": [
        {"id": 1, "pageURL": "https://pixabay.com/videos/id-1/", "tags": "a", "duration": 9, "user": "A", "user_id": 1, "videos": {"medium": {"url": "https://cdn.pixabay.com/video/l.mp4", "width": 1280, "height": 720, "size": 1_000_000, "thumbnail": "https://cdn.pixabay.com/video/l.jpg"}}},
        {"id": 2, "pageURL": "https://pixabay.com/videos/id-2/", "tags": "b", "duration": 9, "user": "B", "user_id": 2, "videos": {"medium": {"url": "https://cdn.pixabay.com/video/p.mp4", "width": 720, "height": 1280, "size": 1_000_000, "thumbnail": "https://cdn.pixabay.com/video/p.jpg"}}}]}
    assert [c["id"] for c in clips.pixabay_search("q", "K", fetch=lambda *a, **k: data)] == ["1"]                              # landscape video: as before
    assert [c["id"] for c in clips.pixabay_search("q", "K", fetch=lambda *a, **k: data, orientation="portrait")] == ["2", "1"]   # vertical video: true portrait first, then the cropped landscape
    assert [c["id"] for c in clips.pixabay_search("q", "K", fetch=lambda *a, **k: data, orientation="square")] == ["1", "2"]   # neither is square: both are cropped, the provider's order stays


def test_pexels_asks_for_the_true_shape_then_for_landscape_when_there_is_too_little():
    seen = []
    def fetch(url, **kw):
        seen.append(url)
        return PEXELS if "orientation=landscape" in url else {"videos": []}
    got = clips.pexels_search("waves", "KEY", fetch=fetch, orientation="portrait")
    assert ["orientation=portrait" in u for u in seen] == [True, False] and len(got) == 1
    seen.clear()
    clips.pexels_search("waves", "KEY", fetch=fetch)
    assert len(seen) == 1 and "orientation=landscape" in seen[0]                                                                # landscape: exactly the old single call


def test_the_poster_the_reviewer_sees_is_the_crop_the_video_will_show(tmp_path):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), (200, 30, 30)).save(buf, "JPEG")
    wide = buf.getvalue()
    assert clips.crop_poster(wide, "landscape") == wide
    portrait = Image.open(io.BytesIO(clips.crop_poster(wide, "portrait")))
    assert portrait.size == (202, 360) and abs(portrait.width / portrait.height - 9 / 16) < 0.01
    assert Image.open(io.BytesIO(clips.crop_poster(wide, "square"))).size == (360, 360)
    seen = {}
    monkeypatched = clips.stock.llm_review
    clips.stock.llm_review = lambda cands, n, a, q, **k: (seen.update(size=Image.open(io.BytesIO(k["fetch_bytes_fn"](cands[0]["thumb_url"]))).size), (None, "x", 0.0, []))[1]
    try:
        clips._review([cand("pixabay", 1)], "n", "a", "q", fetch_bytes_fn=lambda url, **kw: wide, orientation="portrait")
    finally:
        clips.stock.llm_review = monkeypatched
    assert seen["size"] == (202, 360)


def test_scout_clip_gives_the_orientation_to_the_review_only_for_non_landscape_videos(monkeypatch):
    got = []
    monkeypatch.setattr(clips, "gather", lambda q, **kw: [cand("pixabay", 1), cand("pixabay", 2)])
    def review(cands, n, a, q, **kw):
        got.append(kw.get("orientation"))
        return 0, "ok", 0.0, [0, 1]
    for o in ("landscape", "portrait"):
        clips.scout_clip("a", "n", fetch_bytes_fn=lambda *a, **k: b"x", review=review, normalise_fn=lambda raw, **kw: (b"m", 5.0), verify_fn=None, orientation=o)
    assert got == [None, "portrait"]


def test_landscape_footage_is_cropped_to_portrait_a_little_above_the_middle_and_the_verify_sees_the_crop(tmp_path):
    src = make_source(seconds=3, size="1280x720", tmp_path=tmp_path)
    mp4, secs = clips.normalise(src, need_seconds=2.5, source_seconds=3.0, suffix=".mp4", orientation="portrait")
    f = tmp_path / "p.mp4"
    f.write_bytes(mp4)
    assert clips.ClipFrames(str(f)).frame(0).size == (720, 1280)
    frames = clips.extract_frames(mp4, [0.5])
    assert Image.open(__import__("io").BytesIO(frames[0])).size[0] < Image.open(__import__("io").BytesIO(frames[0])).size[1]   # the checker gets tall frames: a subject the crop lost is not in them


# ---------------------------------------------------------------- one retry with a stock-staple wording
def retry_scout(results, log):
    def scout(q, narration, alt="", **kw):
        log.append(q)
        notes = kw["notes"]
        notes["cost"] += 0.001
        r = results.get(q)
        if r is None:
            notes["reasons"].append(f"verify: 4/10 for {q}")
            return None
        return {"mp4": b"MP4:" + q.encode(), "entry": {"id": q}, "credit": f"Video: {q} / Pixabay", "chosen": f"pixabay:{q}", "loops_after": r, "review": {"cost_usd": 0.001}}
    return scout


def test_a_failed_clip_is_retried_once_with_a_rewritten_wording_through_the_same_pipeline(monkeypatch):
    monkeypatch.setenv("CLIP_RETRY", "1")
    log, asked = [], []
    rewrite = lambda q, n, a, reasons: (asked.append((q, list(reasons))), ("laboratory scientist", 0.0002))[1]
    out = clips.scout_with_retry("dna strand animation", "n", "alt", scout=retry_scout({"laboratory scientist": 8}, log), rewrite=rewrite, need_seconds=5.0)
    assert log == ["dna strand animation", "laboratory scientist"] and out["chosen"] == "pixabay:laboratory scientist"
    assert asked == [("dna strand animation", ["verify: 4/10 for dna strand animation"])]                    # the rewrite is told why the first wording failed
    assert out["review"]["retry_query"] == "laboratory scientist" and out["review"]["cost_usd"] == pytest.approx(0.001 + 0.0002 + 0.001)   # everything spent, failures included
    log.clear()
    both = clips.scout_with_retry("a", "n", "alt", scout=retry_scout({}, log), rewrite=lambda *a: ("b", 0.0), need_seconds=5.0)
    assert both is None and log == ["a", "b"]                                                                 # one retry at most
    log.clear()
    fine = clips.scout_with_retry("a", "n", "alt", scout=retry_scout({"a": 7}, log), rewrite=lambda *a: pytest.fail("no retry when it worked"), need_seconds=5.0)
    assert fine is not None and log == ["a"]
    log.clear()
    assert clips.scout_with_retry("a", "n", scout=retry_scout({}, log), rewrite=lambda *a: ("A", 0.0), need_seconds=5.0) is None and log == ["a"]   # the same wording again is pointless
    monkeypatch.setenv("CLIP_RETRY", "0")
    log.clear()
    assert clips.scout_with_retry("a", "n", scout=retry_scout({}, log), rewrite=lambda *a: pytest.fail("off"), need_seconds=5.0) is None and log == ["a"]


def test_the_retry_respects_the_per_beat_cost_cap_and_time_budget(monkeypatch):
    monkeypatch.setenv("CLIP_RETRY", "1")
    log = []
    rw = lambda *a: ("b", 0.0)
    box = {"cost": clips.RETRY_COST_CAP_USD, "t0": __import__("time").time()}
    assert clips.scout_with_retry("a", "n", scout=retry_scout({}, log), rewrite=rw, box=box, need_seconds=5.0) is None and log == ["a"]   # the beat already spent its cap
    log.clear()
    late = {"cost": 0.0, "t0": __import__("time").time() - clips.RETRY_TIME_BUDGET_S - 1}
    assert clips.scout_with_retry("a", "n", scout=retry_scout({}, log), rewrite=rw, box=late, need_seconds=5.0) is None and log == ["a"]   # too late: the Lambda has 180 s


def test_a_segment_that_would_start_after_the_beat_time_limit_is_not_searched():
    log = []
    gone = {"cost": 0.0, "t0": __import__("time").time() - clips.BEAT_TIME_LIMIT_S - 1}
    assert clips.scout_with_retry("a", "n", scout=retry_scout({"a": 7}, log), box=gone, need_seconds=5.0) is None and log == []   # the beat falls back to its photo instead of timing out the Lambda


def test_the_rewrite_is_a_small_model_call_that_never_raises_and_rejects_nonsense():
    calls = []
    def complete(system, user, **kw):
        calls.append((system, user, kw))
        return '{"query": "tailor sewing fabric"}', {"cost_usd": 0.0002}
    assert clips.rewrite_query("scissors cutting thread", "Cas9 cuts DNA.", "gene editing", ["verify: 3/10"], complete=complete) == ("tailor sewing fabric", 0.0002)
    assert "scissors cutting thread" in calls[0][1] and "verify: 3/10" in calls[0][1] and kw_effort(calls[0]) == "low"
    assert clips.rewrite_query("a", "n", "", [], complete=lambda *a, **k: ("not json", {})) == ("", 0.0)
    assert clips.rewrite_query("a", "n", "", [], complete=lambda *a, **k: ('{"query": "one two three four five six seven eight"}', {"cost_usd": 0.1})) == ("", 0.1)
    def boom(*a, **k):
        raise RuntimeError("bedrock")
    assert clips.rewrite_query("a", "n", "", [], complete=boom) == ("", 0.0)


def kw_effort(call):
    return call[2].get("effort")


def test_a_montage_segment_that_fails_gets_its_retry_and_the_beat_cost_includes_failures(monkeypatch):
    monkeypatch.setenv("CLIP_RETRY", "1")
    log = []
    out = clips.scout_montage(["a", "b", "c"], "x " * 30, need_seconds=12.6, scout=retry_scout({"a": 7, "b2": 7, "c": 7}, log), assemble_fn=assembled, workers=1, rewrite=lambda q, *a: (q + "2", 0.0))
    assert out["segments"] == 3 and out["chosen_all"] == ["pixabay:a", "pixabay:b2", "pixabay:c"] and sorted(log) == ["a", "b", "b2", "c"]
    assert out["review"]["cost_usd"] == pytest.approx(0.004)                                                  # four scout runs, the failed one included
