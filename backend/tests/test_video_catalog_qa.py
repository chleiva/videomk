"""video_catalog_qa: synthetic videos made with ffmpeg prove the temporal checks flag flicker, a hard swap (morph/cut), a freeze and a static clip,
and pass a clean moving clip. The vision layer is tested with a fake `complete` (no network)."""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import video_catalog_qa as qa  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg not installed")

BASE = "mandelbrot=size=640x360:rate=24,format=yuv420p"   # smooth continuous zoom: a stand-in for calm footage


def make(tmp_path, name, graph, seconds=5, extra=()):
    out = str(tmp_path / name)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", graph, "-t", str(seconds), *extra, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    subprocess.run(cmd, check=True)
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    c = {}
    c["clean"] = make(d, "clean.mp4", "gradients=size=640x360:rate=24:speed=0.02:nb_colors=4,format=yuv420p")
    c["flicker"] = make(d, "flicker.mp4", "gradients=size=640x360:rate=24:speed=0.02:nb_colors=4,format=yuv420p", extra=["-vf", "eq=brightness='0.18*mod(n,2)':eval=frame"])
    # hard swap at 2.5 s: first half one scene, second half a totally different one (an object morphing into another is this, in the extreme)
    a = str(d / "a.mp4"), str(d / "b.mp4")
    make(d, "a.mp4", "gradients=size=640x360:rate=24:speed=0.02:nb_colors=4:seed=1,format=yuv420p", seconds=2.5)
    make(d, "b.mp4", "gradients=size=640x360:rate=24:speed=0.02:nb_colors=4:seed=9,hue=h=140,negate,format=yuv420p", seconds=2.5)
    lst = d / "l.txt"
    lst.write_text(f"file '{a[0]}'\nfile '{a[1]}'\n")
    swap = str(d / "swap.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-pix_fmt", "yuv420p", swap], check=True)
    c["swap"] = swap
    c["static"] = make(d, "static.mp4", "color=c=0x336699:size=640x360:rate=24")
    return c


def test_clean_clip_has_no_temporal_issue(clips):
    t = qa.analyse_temporal(clips["clean"])
    assert t.issues == [], t
    assert not t.spikes and t.flicker_beats < qa.FLICKER_MAX_BEATS


def test_flicker_is_flagged(clips):
    t = qa.analyse_temporal(clips["flicker"])
    assert t.flicker_beats >= qa.FLICKER_MAX_BEATS
    assert any("flicker" in i for i in t.issues)


def test_hard_swap_is_flagged_as_sudden_change(clips):
    t = qa.analyse_temporal(clips["swap"])
    assert t.spikes, t
    assert 2.2 <= t.spikes[0]["t"] <= 2.8
    assert any("sudden change" in i for i in t.issues)


def test_freeze_is_flagged(clips, tmp_path):
    frozen = make(tmp_path, "freeze.mp4", "gradients=size=640x360:rate=24:speed=0.02:nb_colors=4,format=yuv420p,trim=duration=2,tpad=stop_mode=clone:stop_duration=3", seconds=5)
    t = qa.analyse_temporal(frozen)
    assert t.freeze_seconds >= 2.5 and any("frozen" in i for i in t.issues)


def test_static_clip_is_flagged(clips):
    t = qa.analyse_temporal(clips["static"])
    assert any("no motion" in i for i in t.issues)


def test_technical_probe_flags_short_and_audio_free(clips, tmp_path):
    short = make(tmp_path, "short.mp4", "gradients=size=640x360:rate=24", seconds=1.5)
    tech = qa.probe(short)
    assert any("too short" in i for i in tech.issues)
    assert qa.probe(clips["clean"]).has_audio is False
    assert qa.probe(clips["clean"]).issues == []


GOOD = json.dumps({"scores": {k: 9 for k in qa.RUBRIC_KEYS}, "findings": [], "verdict": "pass"})


def fake(text, cost=0.01):
    def complete(system, user, **kw):
        assert len(kw["images"]) == 6 and "frames 3 and 4" in user
        return text, {"cost_usd": cost}
    return complete


def test_clean_clip_with_good_vision_is_accepted(clips):
    r = qa.score_clip(clips["clean"], "calm abstract gradient", complete=fake(GOOD))
    assert r.decision == "accept", r.reasons
    assert r.vision.cost_usd == 0.01 and r.vision.mean == 9


def test_severe_vision_finding_rejects_even_if_temporal_is_clean(clips):
    bad = json.loads(GOOD)
    bad["scores"]["anatomy"] = 2
    bad["findings"] = ["hand has seven fingers"]
    r = qa.score_clip(clips["clean"], "x", complete=fake(json.dumps(bad)))
    assert r.decision == "reject" and any("anatomy" in x for x in r.reasons)


def test_borderline_goes_to_human_review(clips):
    mid = json.loads(GOOD)
    mid["scores"] = {k: 7.5 for k in qa.RUBRIC_KEYS}
    r = qa.score_clip(clips["clean"], "x", complete=fake(json.dumps(mid)))
    assert r.decision == "review"


def test_temporal_flicker_rejects_despite_perfect_vision(clips):
    r = qa.score_clip(clips["flicker"], "x", complete=fake(GOOD))
    assert r.decision == "reject" and any("flicker" in x for x in r.reasons)


def test_unreadable_vision_answer_fails_closed(clips):
    r = qa.score_clip(clips["clean"], "x", complete=fake("sorry"))
    assert r.decision == "reject"


def test_no_vision_never_accepts(clips):
    assert qa.score_clip(clips["clean"], "x", use_vision=False).decision == "review"


def test_contact_sheet_and_review_row(clips, tmp_path):
    out = qa.contact_sheet([clips["clean"], clips["swap"]], str(tmp_path / "s.png"))
    from PIL import Image
    im = Image.open(out)
    assert im.width == 6 * 256 and im.height > 2 * 100
    r = qa.score_clip(clips["swap"], "x", complete=fake(GOOD))
    assert qa.review_row(r).startswith("| swap.mp4 | reject |")


def test_rubric_prompt_lists_every_category():
    for k in qa.RUBRIC_KEYS:
        assert k in qa.VISION_SYSTEM
