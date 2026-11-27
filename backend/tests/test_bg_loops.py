"""Pre-rendered background loops (engine/bg_loops.py): the index, the one-time download, frames by t mod loop, centre crops for every aspect, smooth
enlarging, bounded memory. The loop used here is a tiny synthetic one whose brightness encodes the frame number, so every lookup can be checked exactly."""
import os
import shutil
import subprocess

import numpy as np
import pytest

from engine import bg_loops as L
from engine import media

FRAMES, FPS, SW, SH = 60, 30, 320, 180   # a 2 s loop


@pytest.fixture(scope="module")
def loop_file(tmp_path_factory):
    """Grey level = 20 + 3 * frame number; a white vertical bar in the middle third and a red left edge (so crops can be told apart)."""
    d = tmp_path_factory.mktemp("loop")
    raw = d / "in.raw"
    with open(raw, "wb") as f:
        for i in range(FRAMES):
            a = np.full((SH, SW, 3), 20 + 3 * i, np.uint8)
            a[:, :40] = (200, 0, 0)
            a[:, 150:170] = 255
            f.write(a.tobytes())
    out = d / "loop.mp4"
    subprocess.run([media.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}", "-r", str(FPS), "-i", str(raw),
                    "-c:v", "libx264", "-crf", "10", "-g", "15", "-pix_fmt", "yuv420p", "-an", str(out)], check=True)
    # what each frame's grey decodes to with this ffmpeg (the colour conversion shifts it by a level or two): the reference the tests compare against
    proc = subprocess.run([media.ffmpeg_bin(), "-loglevel", "error", "-i", str(out), "-vf", "crop=40:40:280:0", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True)
    GREYS[:] = np.frombuffer(proc.stdout, np.uint8).reshape(FRAMES, -1).mean(axis=1).tolist()
    return str(out)


GREYS = []


def grey_frame(a):
    """The frame number a decoded picture carries (from the plain grey area on the right)."""
    return int(np.argmin(np.abs(np.asarray(GREYS) - float(a[:, -a.shape[1] // 8:].mean()))))


@pytest.fixture(autouse=True)
def clean():
    L.release()
    L.reset_index_cache()
    yield
    L.release()
    L.reset_index_cache()


RAW = {"version": 1, "loops": [
    {"id": "gas-brand-dark", "palette": "brand", "mode": "dark", "mood": ["tech", "calm"], "text": "#FFFFFF", "seconds": 2, "fps": 30, "frames": 60, "width": 320, "height": 180, "description": "blue  violet\n gas"},
    {"id": "gas-ember-dark", "palette": "ember", "mode": "dark", "mood": ["energy"], "text": "#ffffff"},
    {"id": "gas-mist-light", "palette": "brand", "mode": "light", "mood": ["calm"], "text": "nonsense"},
    {"id": "../etc", "mode": "dark"}, {"id": "gas-x", "mode": "sepia"}, {"id": "gas-brand-dark", "mode": "dark"}, "junk", None,
]}


# ---------------------------------------------------------------- index
def test_clean_index_keeps_only_well_formed_entries():
    loops = L.clean_index(RAW)
    assert [lp.id for lp in loops] == ["gas-brand-dark", "gas-ember-dark", "gas-mist-light"]   # bad id, bad mode, duplicate, junk: dropped
    a, b, c = loops
    assert (a.text, a.frames, a.fps, a.width, a.description) == ("#ffffff", 60, 30, 320, "blue violet gas")
    assert (b.seconds, b.fps, b.frames, b.width, b.height) == (10.0, 30, 300, 1920, 1080)       # defaults
    assert c.text == L.DEFAULT_TEXT["light"]                                                    # a bad colour falls back to the mode's ink
    assert L.clean_index(None) == [] and L.clean_index({"loops": "x"}) == [] and L.clean_index([1]) == []


def test_load_index_caches_and_survives_a_missing_file():
    calls = []
    clock = [1000.0]

    def get_json(key):
        calls.append(key)
        return RAW
    assert len(L.load_index(get_json, now=lambda: clock[0])) == 3
    assert len(L.load_index(get_json, now=lambda: clock[0] + 10)) == 3
    assert calls == [L.INDEX_KEY]
    clock[0] += L.INDEX_TTL_S + 1
    L.load_index(get_json, now=lambda: clock[0])
    assert len(calls) == 2
    L.reset_index_cache()

    def boom(key):
        raise RuntimeError("no such key")
    assert L.load_index(boom, now=lambda: 5000.0) == []


def test_pick_and_sanitize():
    loops = L.clean_index(RAW)
    assert L.pick(loops, mood="energy").id == "gas-ember-dark"
    assert L.pick(loops, mood="calm", mode="light").id == "gas-mist-light"
    assert L.pick(loops, palette="ember", mode="dark").id == "gas-ember-dark"
    assert L.pick(loops, mood="unknown").id == "gas-brand-dark"           # nothing matches: the first of the index
    assert L.pick(loops, mood="calm", palette="ember").id == "gas-brand-dark"   # a mood outweighs a palette
    assert L.pick([lp for lp in loops if lp.mode == "dark"], mode="light") is None
    assert L.pick([]) is None
    assert L.sanitize("gas-ember-dark", loops).id == "gas-ember-dark"
    assert L.sanitize({"loop": "gas-mist-light"}, loops).mode == "light"
    assert L.sanitize({"id": "gas-brand-dark"}, loops).id == "gas-brand-dark"
    for bad in (None, 7, "", "nope-nope", "../x", {"loop": 3}, {"style": "gas"}, ["gas-ember-dark"]):
        assert L.sanitize(bad, loops) is None
    assert "gas-ember-dark (dark, ember; energy)" in L.prompt_list(loops)


def test_keys_and_bad_ids():
    assert L.loop_key("gas-brand-dark") == "backgrounds/loops/gas-brand-dark/1080.mp4"
    assert L.loop_key("gas-brand-dark", "4k") == "backgrounds/loops/gas-brand-dark/4k.mp4"
    assert L.loop_key("gas-brand-dark", "poster") == "backgrounds/loops/gas-brand-dark/poster.jpg"
    for bad in ("", "a", "../../etc/passwd", "Gas", "a/b", "x" * 60):
        with pytest.raises(ValueError):
            L.loop_key(bad)
    with pytest.raises(ValueError):
        L.loop_key("gas-brand-dark", "8k")


# ---------------------------------------------------------------- fetch
def test_ensure_local_downloads_once_and_never_keeps_a_broken_file(loop_file, tmp_path):
    calls = []

    def download(key, path):
        calls.append(key)
        shutil.copy(loop_file, path)
    d = str(tmp_path / "cache")
    p1 = L.ensure_local("gas-brand-dark", download=download, cache_dir=d)
    p2 = L.ensure_local("gas-brand-dark", download=download, cache_dir=d)
    assert p1 == p2 and os.path.getsize(p1) == os.path.getsize(loop_file)
    assert calls == ["backgrounds/loops/gas-brand-dark/1080.mp4"]
    assert os.listdir(d) == ["gas-brand-dark-1080.mp4"]          # no .part left behind

    def failing(key, path):
        with open(path, "wb") as f:
            f.write(b"half")
        raise RuntimeError("connection reset")
    with pytest.raises(RuntimeError):
        L.ensure_local("gas-ember-dark", download=failing, cache_dir=d)
    with pytest.raises(RuntimeError):
        L.ensure_local("gas-ember-dark", download=lambda k, p: open(p, "wb").close(), cache_dir=d)   # an empty file is not a loop
    assert os.listdir(d) == ["gas-brand-dark-1080.mp4"]
    with pytest.raises(ValueError):
        L.ensure_local("../x", download=download, cache_dir=d)


# ---------------------------------------------------------------- geometry
@pytest.mark.parametrize("target, crop", [
    ((1920, 1080), (1920, 1080, 0, 0)),
    ((3840, 2160), (1920, 1080, 0, 0)),
    ((1080, 1920), (608, 1080, 656, 0)),
    ((1080, 1080), (1080, 1080, 420, 0)),
    ((1080, 1350), (864, 1080, 528, 0)),
    ((2560, 1080), (1920, 810, 0, 134)),      # wider than the source: top and bottom go
])
def test_crop_is_centred_and_has_the_target_aspect(target, crop):
    cw, ch, x, y = L.crop_box(1920, 1080, *target)
    assert (cw, ch, x, y) == crop
    assert abs(cw / ch - target[0] / target[1]) < 0.005
    assert cw % 2 == 0 and ch % 2 == 0 and x % 2 == 0 and y % 2 == 0
    assert abs((x + cw / 2) - 960) <= 1 and abs((y + ch / 2) - 540) <= 1


def test_decode_size_never_exceeds_the_source_and_halves_4k():
    assert L.decode_size(1920, 1080, 1920, 1080) == (1920, 1080)
    assert L.decode_size(1920, 1080, 1280, 720) == (1280, 720)
    assert L.decode_size(1920, 1080, 3840, 2160) == (1920, 1080)      # 4K: half, then enlarged
    assert L.decode_size(608, 1080, 1080, 1920) == (608, 1080)        # 9:16 from the 16:9 file: the crop, enlarged
    assert L.decode_size(608, 1080, 2160, 3840) == (608, 1080)
    assert L.decode_size(1080, 1080, 720, 720) == (720, 720)


# ---------------------------------------------------------------- frames
def test_frames_follow_t_mod_loop(loop_file):
    p = L.LoopPlayer(loop_file, SW, SH, frames=FRAMES, fps=FPS)
    assert (p.dw, p.dh) == (SW, SH)
    for t, want in [(0.0, 0), (0.5, 15), (1.0, 30), (59 / 30, 59), (2.0, 0), (2.5, 15), (61.0, 30), (7 / 30, 7), (0.249, 7)]:
        a = p.frame(t)
        assert a.shape == (SH, SW, 3) and a.dtype == np.uint8
        assert p.index_of(t) == want
        assert abs(grey_frame(a) - want) <= 0, (t, want, grey_frame(a))


def test_the_loop_closes(loop_file):
    p = L.LoopPlayer(loop_file, SW, SH, frames=FRAMES, fps=FPS)
    assert np.array_equal(p.frame(0.0), p.frame(2.0)) and np.array_equal(p.frame(0.4), p.frame(10.4))
    assert grey_frame(p.frame(2.0 - 1 / 30)) == FRAMES - 1


def test_only_the_needed_windows_are_decoded(loop_file):
    p = L.LoopPlayer(loop_file, SW, SH, frames=FRAMES, fps=FPS, window=15)
    for f in range(0, 15):
        p.frame(f / FPS)
    assert p.decodes == 1                      # one ffmpeg run for a chunk inside one window
    for f in range(15, 20):
        p.frame(f / FPS)
    assert p.decodes == 2
    p.frame(0.1)
    assert p.decodes == 2                      # still cached
    assert len(p._win) == 2 and p.cached_bytes() == 2 * 15 * SW * SH * 3


def test_memory_is_bounded(loop_file):
    per = SW * SH * 3
    p = L.LoopPlayer(loop_file, SW, SH, frames=FRAMES, fps=FPS, window=10, max_bytes=25 * per)   # room for two windows of 10
    assert (p.window, p.max_windows) == (10, 2)
    for f in range(FRAMES):
        assert grey_frame(p.frame(f / FPS)) == f
        assert p.cached_bytes() <= 25 * per
    assert p.decodes == 6
    tiny = L.LoopPlayer(loop_file, SW, SH, frames=FRAMES, fps=FPS, max_bytes=1)                  # an absurd budget still works: one frame at a time
    assert (tiny.window, tiny.max_windows) == (1, 1)
    assert grey_frame(tiny.frame(1.0)) == 30 and tiny.cached_bytes() == per
    p.release()
    assert p.cached_bytes() == 0


def test_default_budget_at_1080p_is_under_200_mb():
    p = L.LoopPlayer("unused.mp4", 1920, 1080, frames=300, fps=30, src_size=(1920, 1080))
    assert p.window * p.max_windows * p.frame_bytes <= L.MAX_CACHE_BYTES <= 200 * 1024 * 1024
    assert p.window == 30 and p.max_windows == 1
    k4 = L.LoopPlayer("unused.mp4", 3840, 2160, frames=300, fps=30, src_size=(1920, 1080))
    assert (k4.dw, k4.dh) == (1920, 1080) and k4.window * k4.max_windows * k4.frame_bytes <= L.MAX_CACHE_BYTES


@pytest.mark.parametrize("w, h", [(180, 320), (240, 240), (216, 270)])
def test_other_aspects_take_the_centre(loop_file, w, h):
    p = L.LoopPlayer(loop_file, w, h, frames=FRAMES, fps=FPS, grain=False)
    a = p.frame(0.5)
    assert a.shape == (h, w, 3)
    assert not (a[..., 0].astype(int) - a[..., 1] > 100).any()          # the red left edge of the 16:9 picture is cut away
    col = a.mean(axis=(0, 2))
    bright = np.where(col > col.max() - 20)[0]
    assert abs(float(bright.mean()) - w / 2) <= max(2, w // 20)         # the white bar of the middle is still in the middle
    assert grey_frame(a) == 15                                          # and it is the right frame


def test_enlarging_is_smooth_and_4k_decodes_half(loop_file):
    p = L.LoopPlayer(loop_file, SW * 2, SH * 2, frames=FRAMES, fps=FPS)                       # bigger than the stored file
    assert (p.dw, p.dh) == (SW, SH)
    a = p.frame(1.0)
    assert a.shape == (SH * 2, SW * 2, 3) and grey_frame(a) == 30
    flat = a[10:-10, -60:-10].astype(int)
    assert flat.max() - flat.min() <= 4                                                       # one level of grain, no blocks
    big = L.LoopPlayer(loop_file, 2560, 1440, frames=FRAMES, fps=FPS, src_size=(3840, 2160))  # above 2.5 MP: half size
    assert (big.dw, big.dh) == (1280, 720)


def test_render_uses_one_cached_player_and_release_frees_it(loop_file, tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CACHE_DIR", str(tmp_path / "c"))
    calls = []

    def download(key, path):
        calls.append(key)
        shutil.copy(loop_file, path)
    spec = L.LoopSpec(id="gas-brand-dark", frames=FRAMES, fps=FPS, seconds=2.0, width=SW, height=SH)
    p = L.player(spec, SW, SH, download)
    assert L.player(spec, SW, SH, download) is p and calls == ["backgrounds/loops/gas-brand-dark/1080.mp4"]
    assert grey_frame(L.render(spec, SW, SH, 0.5)) == 15 and p.decodes == 1
    q = L.player(spec, 180, 320, download)          # another output size replaces the first player and frees its frames
    assert q is not p and p.cached_bytes() == 0 and len(L._players) == 1
    assert len(calls) == 1                          # the file itself is still on disk
    L.render(spec, 180, 320, 0.2)
    L.release()
    assert q.cached_bytes() == 0 and not L._players


def test_unreadable_file_raises(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    assert L.probe_size(str(bad)) == (0, 0)
    with pytest.raises(RuntimeError):
        L.LoopPlayer(str(bad), 320, 180, frames=60)
    with pytest.raises(ValueError):
        L.LoopPlayer(str(bad), 0, 180, frames=60, src_size=(320, 180))
