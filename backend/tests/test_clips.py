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


def test_normalise_trims_long_footage_crops_to_16_9_and_loops_short_footage(tmp_path):
    long_src = make_source(6, "640x480", tmp_path=tmp_path)                      # 4:3 source
    mp4, loops_after = clips.normalise(long_src, need_seconds=3.0, source_seconds=6.0, suffix=".mp4")
    frames, size = frame_sizes(mp4, tmp_path)
    assert size == (1280, 720) and abs(len(frames) - 90) <= 2 and loops_after == pytest.approx(3.0)
    short_src = make_source(2, tmp_path=tmp_path)
    mp4, loops_after = clips.normalise(short_src, need_seconds=5.0, source_seconds=2.0, suffix=".mp4")
    frames, size = frame_sizes(mp4, tmp_path)
    assert size == (1280, 720) and abs(len(frames) - 150) <= 2 and loops_after == pytest.approx(2.0)    # 5 s made of a 2 s clip, looping
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
    cands = [cand("commons", 1, dur=4.0), cand("pexels", 2, dur=12.0), cand("commons", 3, dur=9.0)]
    get, norm = fake_world(monkeypatch, cands)
    seen = {}
    review = lambda cs, n, a, q, **kw: (seen.update(order=[clips.candidate_key(c) for c in cs]) or (1, "the second one fits", 0.003, [0, 1, 2]))
    out = clips.scout_clip("waves", "narration", "alt", need_seconds=8.0, fetch_bytes_fn=get, review=review, normalise_fn=norm)
    assert seen["order"] == ["pexels:2", "commons:3", "commons:1"]               # footage long enough for the scene is offered first
    assert out["chosen"] == "commons:3" and out["mp4"] == b"MP4:RAW:https://v/commons3.mp4" and out["credit"] == "Video: Z (CC0)"
    assert out["review"]["reason"] == "the second one fits" and out["entry"]["source"] == "commons" and len(out["candidates"]) == 3


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


def test_a_long_query_is_retried_shorter(monkeypatch):
    asked = []
    monkeypatch.setattr(clips, "gather", lambda q, **kw: (asked.append(q), [cand("commons", 1)] if q == "dark storm" else [])[1])
    out = clips.scout_clip("dark storm clouds rolling over fields", "n", fetch_bytes_fn=lambda *a, **k: b"x", review=None, normalise_fn=lambda raw, **kw: (b"m", 5.0))
    assert asked == ["dark storm clouds rolling over fields", "dark storm"] and out["chosen"] == "commons:1"


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
    assert "- clip:" in plan_mod.scene_docs() and "Never for a specific named person" in plan_mod.system_prompt("en")
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


# ---------------------------------------------------------------- one frame per 30 seconds of the footage we use
@pytest.mark.parametrize("seconds,times", [(5, [2.5]), (20, [10.0]), (30, [15.0]), (31, [7.75, 23.25]), (61, [10.17, 30.5, 50.83]), (200, [33.33, 100.0, 166.67])])
def test_verification_samples_one_frame_per_30_seconds_between_one_and_three(seconds, times):
    assert clips.verify_frame_times(seconds) == pytest.approx(times, abs=0.02)


def test_verification_sends_only_a_few_small_frames_in_a_single_call(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_VERIFY", "1")
    mp4, _ = clips.normalise(make_source(4, tmp_path=tmp_path), need_seconds=3.0, source_seconds=4.0, suffix=".mp4")
    seen = {"calls": 0}
    def complete(system, user, images=None, **kw):
        seen.update(calls=seen["calls"] + 1, n=len(images), sizes=[Image.open(__import__("io").BytesIO(i)).size for i in images], model=kw.get("model"), max_tokens=kw.get("max_tokens"))
        return '{"ok": true, "reason": "calm waves"}', {"cost_usd": 0.0007}
    ok, why, cost = clips.verify(mp4, "Waves roll in.", "waves", "waves", 3.0, complete=complete)
    assert (ok, why, cost) == (True, "calm waves", 0.0007) and seen["calls"] == 1 and seen["n"] == 1      # a 3 s clip: one frame, one call
    assert seen["sizes"][0][0] == 512 and seen["max_tokens"] == 300
    bad = lambda *a, **k: ('{"ok": false, "reason": "a logo is visible"}', {"cost_usd": 0.0007})
    assert clips.verify(mp4, "n", "a", "q", 3.0, complete=bad)[:2] == (False, "a logo is visible")


def test_verification_fails_open_and_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_VERIFY", "1")
    mp4, _ = clips.normalise(make_source(3, tmp_path=tmp_path), need_seconds=2.0, source_seconds=3.0, suffix=".mp4")
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bedrock down"))
    assert clips.verify(mp4, "n", "a", "q", 2.0, complete=boom)[0] is True                         # a broken check never blocks the video
    junk = lambda *a, **k: ("no json here", {"cost_usd": 0.0})
    assert clips.verify(mp4, "n", "a", "q", 2.0, complete=junk)[0] is True
    assert clips.verify(b"not a video", "n", "a", "q", 2.0, complete=boom)[0] is True              # nothing to check
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
