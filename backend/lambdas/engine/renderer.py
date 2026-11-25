"""Timeline -> frames. Pure function of (timeline, t): any frame range can be rendered independently,
which is what makes chunk-parallel rendering on Lambda possible."""
import bisect
import os
import sys
import zlib
from typing import Any, Callable, Dict, Iterator, List, Optional

from PIL import Image

from .canvas import Canvas
from .frame import Frame
from .scenes import SCENES
from .scenes.formats import draw_framed, is_native
from .scenes.base import SceneCtx
from .scenes.captions import draw_captions
from .theme import get_theme

TRANSITION_S = 0.4
OUTRO_FADE_S = 0.7
BLACK = (0, 0, 0)
SS_4K = 4   # 4K supersampling: a canvas 4x the design size reduced 2x, i.e. the same 2x2 samples per output pixel as 1080p (measured against 2x and 3x in docs/FOUR_K.md)

# The dict caches that hold pictures (sprites, composed backgrounds, resized photos), by module: emptied by release_caches. Never clips._CACHE (a provider's search results).
_PICTURE_DICTS = (("canvas", "_BG_CACHE"), ("scenes.viz_scenes", "_BACKDROP"), ("scenes.viz_scenes", "_SCRIM"), ("scenes.viz_scenes", "_FOCUS"),
                  ("scenes.elements.people_media", "_PHOTO_CACHE"), ("scenes.elements._photo_kit", "_CACHE"))


def release_caches() -> int:
    """Empties the engine's picture caches (cached sprites, shadows, gradients, backgrounds, resized photos). At 4K each cached picture is 4 times the size it
    has at 1080p and a warm render function would carry them from chunk to chunk, so the 4K render starts every chunk with empty caches (docs/FOUR_K.md).
    Data that is loaded once (the map and icon indexes: caches of size 1 or without a limit) is kept. Returns how many caches were emptied."""
    pkg = __name__.rsplit(".", 1)[0]
    n = 0
    for name, mod in list(sys.modules.items()):
        if mod is None or not (name == pkg or name.startswith(pkg + ".")):
            continue
        for v in list(vars(mod).values()):
            params = getattr(v, "cache_parameters", None)
            if callable(params) and callable(getattr(v, "cache_clear", None)) and params().get("maxsize") not in (None, 1):
                v.cache_clear()
                n += 1
    for mod_name, attr in _PICTURE_DICTS:
        d = getattr(sys.modules.get(f"{pkg}.{mod_name}"), attr, None)
        if isinstance(d, dict):
            d.clear()
            n += 1
    return n


class Renderer:
    def __init__(self, timeline: Dict[str, Any], image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, draft: bool = False,
                 clip_loader: Optional[Callable[[str], Any]] = None):
        self.tl = timeline
        self.draft = draft
        self.W = int(timeline.get("width", 1920))
        self.H = int(timeline.get("height", 1080))
        self.fps = int(timeline.get("fps", 30))
        fr = timeline.get("frame")
        # the shape: the timeline's `frame` (aspect, resolution), else inferred from its pixel size; scenes lay out in the frame's design units
        self.frame = Frame.parse(fr.get("aspect"), fr.get("resolution")) if isinstance(fr, dict) and fr.get("aspect") else Frame.from_size(self.W, self.H)
        self.big = self.frame.scale_factor > 1.0   # 4K: the output is larger than the design canvas
        self.ss = 1 if draft else (SS_4K if self.big else 2)  # draft: no supersampling, half-size output (the downscale antialiases)
        dw, dh = (self.frame.design_w, self.frame.design_h) if self.big else (self.W, self.H)   # a draft of a 4K video is the same small preview as a 1080p one
        self.out_w, self.out_h = (max(2, dw // 4 * 2), max(2, dh // 4 * 2)) if draft else (self.W, self.H)   # draft: half size, kept even (yuv420p): 4:5 at 1080p is 540x674, not 675
        self.fallbacks: Dict[str, Dict[str, Any]] = {}   # scene id -> framed-fallback report (scale, min_text_px, readable), for the preview tooling
        self.theme = get_theme(timeline.get("theme", "midnight"))
        self.scenes: List[Dict[str, Any]] = timeline["scenes"]
        self.lead: Optional[Dict[str, Any]] = timeline.get("lead")
        self.outro: bool = bool(timeline.get("outro", True))
        self.starts = [float(s["start"]) for s in self.scenes]
        last = self.scenes[-1]
        self.total = float(timeline.get("duration") or (float(last["start"]) + float(last["duration"])))
        self.total_frames = int(round(self.total * self.fps))
        self.ctx = SceneCtx(resolve_image=self._load_image, resolve_clip=self._load_clip, captions=bool(timeline.get("captions", True)), frame=self.frame)
        self._clip_loader = clip_loader
        self._clips: Dict[str, Any] = {}
        self._image_loader = image_loader
        self._images: Dict[str, Optional[Image.Image]] = {}

    # ----- assets
    def _load_image(self, key: str) -> Optional[Image.Image]:
        if key in self._images:
            return self._images[key]
        img = None
        if self._image_loader:
            try:
                img = self._image_loader(key)
            except Exception:
                img = None
        if img is not None:
            img = img.convert("RGB")
            limit = self.W * 2
            if max(img.size) > limit * 1.5:  # keep memory/resize cost bounded
                scale = limit * 1.5 / max(img.size)
                img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        self._images[key] = img
        return img

    def _load_clip(self, key: str):
        if key not in self._clips:
            try:
                self._clips[key] = self._clip_loader(key) if self._clip_loader else None
            except Exception:  # an unreadable clip degrades to the placeholder instead of failing the whole video
                self._clips[key] = None
        return self._clips[key]

    # ----- frames
    @staticmethod
    def _ambient_phase(scene: Dict[str, Any]) -> float:
        """Background drift depends on the scene (not on absolute time), so a rendered chunk is identical wherever it sits."""
        return (zlib.crc32(str(scene.get("id", "")).encode()) % 97) * 3.7

    def _draw_scene(self, idx: int, lt: float, t_global: float = 0.0) -> Image.Image:
        return self._draw_spec(self.scenes[idx], lt)

    def _draw_spec(self, sc: Dict[str, Any], lt: float) -> Image.Image:
        draw = SCENES.get(sc["type"])
        fr = self.frame
        cv = Canvas(fr.W, fr.H, ss=self.ss)   # design units; the finished image is scaled to the real output size below
        bg_t = max(0.0, lt) + self._ambient_phase(sc)
        amb = sc["type"] != "image"
        cv.background(self.theme, bg_t, ambience=amb)
        if draw is None:
            cv.text(fr.W / 2, fr.H / 2, f"unknown scene type: {sc['type']}", "semibold", 48, (255, 255, 255, 255), anchor="mm")
        elif is_native(sc["type"], fr):
            draw[0](cv, sc.get("props") or {}, max(0.0, lt), float(sc["duration"]), self.theme, self.ctx)
        else:   # no layout for this shape yet: the landscape scene as a card on the themed frame (never fails, never blank)
            rep = draw_framed(cv, draw[0], sc.get("props") or {}, max(0.0, lt), float(sc["duration"]), self.theme, self.ctx, bg_t=bg_t, ambience=amb)
            self.fallbacks[str(sc.get("id", ""))] = dict(rep, type=sc["type"])
        if self.ctx.captions:
            words = sc.get("words")
            if words:
                draw_captions(cv, self.theme, words, lt, fr)
        if self.big and not self.draft:   # 4K: straight from the supersampled canvas to the output size (never through the 1080 design size)
            return cv.to_rgb((self.out_w, self.out_h))
        return cv.to_rgb()   # design size; frame_at scales it to the output size

    def scene_index(self, t: float) -> int:
        return max(0, min(len(self.scenes) - 1, bisect.bisect_right(self.starts, t) - 1))

    def frame_at(self, t: float) -> Image.Image:
        img = self._compose(t)
        if img.size != (self.out_w, self.out_h):   # draft (half size) or 720p: design units -> output pixels
            img = img.resize((self.out_w, self.out_h), Image.BILINEAR if self.draft else Image.LANCZOS)
        return img

    def _compose(self, t: float) -> Image.Image:
        idx = self.scene_index(t)
        sc = self.scenes[idx]
        lt = t - self.starts[idx]
        img = self._draw_spec(sc, lt)
        tr = min(TRANSITION_S, float(sc["duration"]) * 0.4)
        if lt < tr and sc.get("transition", "fade") != "none":
            prev = self.scenes[idx - 1] if idx > 0 else self.lead  # a chunk starts mid-crossfade using its lead scene
            if prev is not None:
                held = self._draw_spec(prev, float(prev["duration"]) + lt)  # outgoing scene holds its final state
                a = lt / tr
                img = Image.blend(held, img, a * a * (3 - 2 * a))
        if self.outro and t > self.total - OUTRO_FADE_S:
            k = max(0.0, min(1.0, (t - (self.total - OUTRO_FADE_S)) / OUTRO_FADE_S))
            img = Image.blend(img, Image.new("RGB", img.size, BLACK), k)
        return img

    def frames(self, f0: int, f1: int) -> Iterator[bytes]:
        """Raw rgb24 bytes for frames [f0, f1)."""
        for f in range(f0, f1):  # exact count: past the last scene a frame simply holds its final state
            yield self.frame_at(f / self.fps).tobytes()
