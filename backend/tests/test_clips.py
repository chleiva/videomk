import subprocess

import pytest
from PIL import Image

from engine import clips, media, plan as plan_mod, stock
from engine.netsafe import FetchError
from engine.renderer import Renderer
from engine.timeline import build_timeline
from tests.test_engine import small_timeline


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
