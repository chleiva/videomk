"""Pre-rendered 3D background loops (the volumetric "gas" looks made with Blender, docs/HERO_LOOPS_3D.md): the premium tier above the procedural
backgrounds of bg_animated.py. Self-contained: nothing in the engine imports this module yet (the hook-up steps are in the doc).

What it does
  * index: `backgrounds/loops/index.json` in the assets bucket lists the loops (id, palette, mode, mood tags, the text colour to use). `load_index`,
    `clean_index`, `pick`, `sanitize`.
  * fetch: `ensure_local` downloads `backgrounds/loops/<id>/1080.mp4` once per container into /tmp/bg_loops (a few MB per loop) and reuses it.
  * frames: `render(spec, w, h, t)` returns the (h, w, 3) uint8 picture for time t, the same shape of call as `bg_animated.render`. Time wraps by the loop
    length (frame = round(t * fps) mod frames), so any t is valid and the loop never ends.
  * aspects: the stored loop is 16:9; other aspects (9:16, 1:1, 4:5) take the centre crop (the calm, dark middle the loops are built around stays in the middle).
  * 4K: frames are decoded at no more than the stored size (and at half size above 1440p) and enlarged smoothly: gas has no fine detail to lose.
  * memory: frames are decoded in windows by one short ffmpeg run each (never the whole loop: 300 frames of 1080p are 1.9 GB), and the decoded windows
    kept in memory are bounded in bytes (MAX_CACHE_BYTES, default 192 MB).

S3 layout (assets bucket, private): backgrounds/loops/index.json and backgrounds/loops/<id>/{1080.mp4, 4k.mp4, poster.jpg}
index.json: {"version": 1, "loops": [{"id", "title", "palette", "mode": "dark"|"light", "mood": [..], "text": "#rrggbb", "seconds", "fps", "frames",
             "width", "height", "contrast": {...}, "description"}]}
The engine only ever reads 1080.mp4 (keyframe every second, so a window decode never has to run through more than one second of video); 4k.mp4 is the master for
download and marketing.
"""
import os
import re
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import media

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PREFIX = "backgrounds/loops/"
INDEX_KEY = PREFIX + "index.json"
INDEX_TTL_S = 300
MODES = ("dark", "light")
VARIANTS = ("1080", "4k")
CACHE_DIR = os.environ.get("BG_LOOPS_DIR", "/tmp/bg_loops")
MAX_CACHE_BYTES = int(os.environ.get("BG_LOOPS_CACHE_MB", "192")) * 1024 * 1024   # decoded frames kept in memory, per player
WINDOW_FRAMES = 30                      # frames decoded per ffmpeg run (one second: one GOP of the 1080p file)
HALF_ABOVE_PIXELS = 2_500_000           # the same rule as bg_animated: above 1440p decode at half size and enlarge
DEFAULT_TEXT = {"dark": "#ffffff", "light": "#0b1020"}

_index: Dict[str, Any] = {"at": 0.0, "loops": []}
_lock = threading.Lock()


@dataclass(frozen=True)
class LoopSpec:
    id: str
    palette: str = ""
    mode: str = "dark"
    mood: Tuple[str, ...] = ()
    text: str = "#ffffff"
    seconds: float = 10.0
    fps: int = 30
    frames: int = 300
    width: int = 1920
    height: int = 1080
    title: str = ""
    description: str = ""


# ---------------------------------------------------------------- index
def loop_key(loop_id: str, variant: str = "1080") -> str:
    if not ID_RE.match(loop_id or ""):
        raise ValueError("bad loop id")
    if variant == "poster":
        return f"{PREFIX}{loop_id}/poster.jpg"
    if variant not in VARIANTS:
        raise ValueError("bad variant")
    return f"{PREFIX}{loop_id}/{variant}.mp4"


def _num(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if lo <= f <= hi else default


def clean_index(raw: Any) -> List[LoopSpec]:
    """Only well-formed entries survive (a usable id, a known mode, sane numbers); everything else is dropped, never guessed."""
    out: List[LoopSpec] = []
    seen = set()
    for e in (raw or {}).get("loops", []) if isinstance(raw, dict) else []:
        if not isinstance(e, dict):
            continue
        lid = str(e.get("id", ""))
        mode = str(e.get("mode", "")).lower()
        if not ID_RE.match(lid) or mode not in MODES or lid in seen:
            continue
        fps = int(_num(e.get("fps"), 1, 60, 30))
        seconds = _num(e.get("seconds"), 1.0, 60.0, 10.0)
        frames = int(_num(e.get("frames"), 2, 3600, round(seconds * fps)))
        text = str(e.get("text", ""))
        mood = e.get("mood") if isinstance(e.get("mood"), list) else []
        seen.add(lid)
        out.append(LoopSpec(
            id=lid, palette=str(e.get("palette") or "")[:20].lower(), mode=mode, mood=tuple(str(m)[:20].lower() for m in mood)[:8],
            text=text.lower() if HEX_RE.match(text) else DEFAULT_TEXT[mode], seconds=seconds, fps=fps, frames=frames,
            width=int(_num(e.get("width"), 16, 8192, 1920)), height=int(_num(e.get("height"), 16, 8192, 1080)),
            title=str(e.get("title") or lid)[:60], description=" ".join(str(e.get("description") or "").split())[:300]))
    return out


def load_index(get_json: Optional[Callable[[str], Any]] = None, now: Callable[[], float] = time.time) -> List[LoopSpec]:
    """The index from S3, cached for a few minutes; [] when it is missing or unreadable (then there are simply no loops to offer)."""
    if _index["at"] and now() - _index["at"] < INDEX_TTL_S:
        return _index["loops"]
    if get_json is None:
        from . import awsio
        get_json = awsio.get_json
    try:
        loops = clean_index(get_json(INDEX_KEY))
    except Exception:
        loops = []
    _index.update(at=now(), loops=loops)
    return loops


def find(loops: List[LoopSpec], loop_id: str) -> Optional[LoopSpec]:
    return next((lp for lp in loops if lp.id == loop_id), None)


def pick(loops: List[LoopSpec], mood: Optional[str] = None, palette: Optional[str] = None, mode: Optional[str] = None) -> Optional[LoopSpec]:
    """The best match, deterministic: the mode is a hard filter (it decides the text colour), then a mood tag (2 points) and the palette (1 point); the index
    order breaks ties. None when no loop has the mode."""
    pool = [lp for lp in loops if mode is None or lp.mode == mode]
    if not pool:
        return None
    mood_l, pal_l = (mood or "").lower(), (palette or "").lower()
    return max(pool, key=lambda lp: (2 if mood_l and mood_l in lp.mood else 0) + (1 if pal_l and pal_l == lp.palette else 0))


def sanitize(raw: Any, loops: List[LoopSpec]) -> Optional[LoopSpec]:
    """A planner/timeline value -> a loop of the index, or None. Accepts an id string or a dict {"loop": id} / {"id": id}; nothing else gets through."""
    lid = raw if isinstance(raw, str) else (raw.get("loop") or raw.get("id")) if isinstance(raw, dict) else None
    return find(loops, lid) if isinstance(lid, str) and ID_RE.match(lid) else None


def prompt_list(loops: List[LoopSpec]) -> str:
    return "\n".join(f"  {lp.id} ({lp.mode}, {lp.palette}; {', '.join(lp.mood)}): {lp.description}" for lp in loops)


# ---------------------------------------------------------------- fetch
def ensure_local(loop_id: str, variant: str = "1080", download: Optional[Callable[[str, str], None]] = None, cache_dir: Optional[str] = None) -> str:
    """The loop's file on local disk: downloaded once (to a temporary name, then renamed, so a half download is never used), then reused."""
    key = loop_key(loop_id, variant)
    d = cache_dir or CACHE_DIR
    path = os.path.join(d, f"{loop_id}-{variant}.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    with _lock:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        os.makedirs(d, exist_ok=True)
        if download is None:
            from . import awsio
            download = awsio.download
        tmp = f"{path}.{os.getpid()}.part"
        try:
            download(key, tmp)
            if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                raise RuntimeError("empty download: " + key)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return path


# ---------------------------------------------------------------- geometry
def _even(v: float) -> int:
    return max(2, int(round(v / 2.0)) * 2)


def crop_box(src_w: int, src_h: int, w: int, h: int) -> Tuple[int, int, int, int]:
    """(crop_w, crop_h, x, y): the largest centred rectangle of the source with the target's aspect (even numbers: the video is 4:2:0)."""
    if w * src_h <= h * src_w:      # the target is narrower than the source: keep the height, cut the sides
        ch = src_h - src_h % 2
        cw = min(src_w - src_w % 2, _even(ch * w / h))
    else:                           # wider: keep the width, cut top and bottom
        cw = src_w - src_w % 2
        ch = min(src_h - src_h % 2, _even(cw * h / w))
    x, y = (src_w - cw) // 2, (src_h - ch) // 2
    return cw, ch, x - x % 2, y - y % 2


def decode_size(crop_w: int, crop_h: int, w: int, h: int) -> Tuple[int, int]:
    """The size frames are decoded at: the target, halved above 1440p, and never larger than the crop itself (enlarging happens once, in `frame`)."""
    tw, th = (w, h) if w * h <= HALF_ABOVE_PIXELS else ((w + 1) // 2, (h + 1) // 2)
    if tw > crop_w or th > crop_h:
        tw, th = crop_w, crop_h
    return max(2, tw), max(2, th)


_NOISE: Dict[Tuple[int, int], np.ndarray] = {}


def _grain(w: int, h: int, frame: int) -> np.ndarray:
    """A fixed tile of -1/0/+1 (int16), shifted per frame: one level of grain so an enlarged dark gradient does not show steps."""
    tile = _NOISE.get((0, 0))
    if tile is None:
        r = np.random.RandomState(20261127)
        tile = (r.randint(0, 2, (1024, 1024)) - r.randint(0, 2, (1024, 1024))).astype(np.int16)
        _NOISE[(0, 0)] = tile
    oy, ox = (frame * 131) % 1024, (frame * 197) % 1024
    t = np.roll(tile, (oy, ox), axis=(0, 1))
    return np.tile(t, (h // 1024 + 1, w // 1024 + 1))[:h, :w]


# ---------------------------------------------------------------- frames
class LoopPlayer:
    """Frames of one loop file for one output size. Decodes a window of frames per ffmpeg run and keeps a bounded number of windows (least recently used out)."""

    def __init__(self, path: str, w: int, h: int, *, frames: int, fps: int = 30, src_size: Optional[Tuple[int, int]] = None,
                 window: int = WINDOW_FRAMES, max_bytes: Optional[int] = None, grain: bool = True):
        if w < 2 or h < 2 or frames < 1 or fps < 1:
            raise ValueError("bad loop geometry")
        self.path, self.w, self.h, self.frames, self.fps, self.grain = path, int(w), int(h), int(frames), int(fps), grain
        self.src_w, self.src_h = src_size or probe_size(path)
        if self.src_w < 2 or self.src_h < 2:
            raise RuntimeError("unreadable loop file: " + os.path.basename(path))
        self.crop = crop_box(self.src_w, self.src_h, self.w, self.h)
        self.dw, self.dh = decode_size(self.crop[0], self.crop[1], self.w, self.h)
        self.frame_bytes = self.dw * self.dh * 3
        budget = MAX_CACHE_BYTES if max_bytes is None else int(max_bytes)
        self.window = max(1, min(int(window), self.frames, max(1, budget // self.frame_bytes)))
        self.max_windows = max(1, budget // (self.window * self.frame_bytes))
        self._win: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self.decodes = 0   # ffmpeg runs so far (for tests and measurements)

    # -- bookkeeping
    def index_of(self, t: float) -> int:
        return int(round(float(t) * self.fps)) % self.frames

    def cached_bytes(self) -> int:
        return sum(a.nbytes for a in self._win.values())

    def release(self) -> None:
        self._win.clear()

    # -- decoding
    def _decode(self, start: int, count: int) -> np.ndarray:
        cw, ch, x, y = self.crop
        vf = f"crop={cw}:{ch}:{x}:{y},scale={self.dw}:{self.dh}:flags=bilinear"
        # seek half a frame early: ffmpeg drops everything before the seek time, and a time rounded up (20/30 s -> 0.6667) would skip the wanted frame
        cmd = [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, (start - 0.5) / self.fps):.5f}", "-i", self.path, "-an", "-frames:v", str(count),
               "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        got = len(proc.stdout) // self.frame_bytes
        if proc.returncode != 0 or got < 1:
            raise RuntimeError("could not decode the background loop: " + proc.stderr[-200:].decode("utf8", "replace"))
        self.decodes += 1
        arr = np.frombuffer(proc.stdout[:got * self.frame_bytes], dtype=np.uint8).reshape(got, self.dh, self.dw, 3)
        if got < count:   # a file a frame short of its index: repeat the last picture rather than fail the render
            arr = np.concatenate([arr, np.repeat(arr[-1:], count - got, axis=0)], axis=0)
        return arr

    def _window(self, k: int) -> np.ndarray:
        win = self._win.get(k)
        if win is not None:
            self._win.move_to_end(k)
            return win
        while len(self._win) >= self.max_windows:
            self._win.popitem(last=False)
        start = k * self.window
        win = self._decode(start, min(self.window, self.frames - start))
        self._win[k] = win
        return win

    def raw(self, t: float) -> np.ndarray:
        """The decoded frame for time t at the decode size (read-only view into the window)."""
        i = self.index_of(t)
        return self._window(i // self.window)[i % self.window]

    def frame(self, t: float) -> np.ndarray:
        """(h, w, 3) uint8 for time t (wrapped by the loop length). Enlarged smoothly when the output is bigger than what is stored."""
        a = self.raw(t)
        if (self.dw, self.dh) == (self.w, self.h):
            return a
        img = Image.fromarray(a, "RGB").resize((self.w, self.h), Image.BICUBIC)
        if not self.grain:
            return np.asarray(img)
        out = np.asarray(img).astype(np.int16)
        out += _grain(self.w, self.h, self.index_of(t))[..., None]
        np.clip(out, 0, 255, out=out)
        return out.astype(np.uint8)


def probe_size(path: str) -> Tuple[int, int]:
    """(width, height) of the first video stream, read with ffmpeg itself (the layer has no ffprobe); (0, 0) when unreadable."""
    try:
        proc = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
    except Exception:
        return 0, 0
    for line in proc.stderr.splitlines():
        if "Video:" in line:
            m = re.search(r"\b(\d{2,5})x(\d{2,5})\b", line.split("Video:")[1])
            if m:
                return int(m.group(1)), int(m.group(2))
    return 0, 0


# ---------------------------------------------------------------- the one call the renderer needs
_players: "OrderedDict[Tuple[str, int, int], LoopPlayer]" = OrderedDict()
MAX_PLAYERS = 1   # one background per video and one output size per render: a second size replaces the first (its frames are freed)


def player(spec: LoopSpec, w: int, h: int, download: Optional[Callable[[str, str], None]] = None) -> LoopPlayer:
    key = (spec.id, int(w), int(h))
    p = _players.get(key)
    if p is None:
        while len(_players) >= MAX_PLAYERS:
            _players.popitem(last=False)[1].release()
        p = LoopPlayer(ensure_local(spec.id, "1080", download), w, h, frames=spec.frames, fps=spec.fps)
        _players[key] = p
    return p


def render(spec: LoopSpec, w: int, h: int, t: float) -> np.ndarray:
    """One background frame, (h, w, 3) uint8: the same call shape as bg_animated.render(spec, w, h, t). Raises when the file cannot be fetched or decoded:
    the caller falls back to the procedural or static background."""
    return player(spec, w, h).frame(t)


def release() -> None:
    """Frees every decoded frame (call it where the renderer empties its picture caches)."""
    for p in _players.values():
        p.release()
    _players.clear()


def reset_index_cache() -> None:
    _index.update(at=0.0, loops=[])
