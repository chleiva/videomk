"""Timeline -> frames. Pure function of (timeline, t): any frame range can be rendered independently,
which is what makes chunk-parallel rendering on Lambda possible."""
import bisect
from typing import Any, Callable, Dict, Iterator, List, Optional

from PIL import Image

from .canvas import Canvas
from .scenes import SCENES
from .scenes.base import SceneCtx
from .scenes.captions import draw_captions
from .theme import get_theme

TRANSITION_S = 0.4
OUTRO_FADE_S = 0.7
BLACK = (0, 0, 0)


class Renderer:
    def __init__(self, timeline: Dict[str, Any], image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, draft: bool = False):
        self.tl = timeline
        self.draft = draft
        self.ss = 1 if draft else 2  # draft: no supersampling, half-size output (the downscale antialiases)
        self.W = int(timeline.get("width", 1920))
        self.H = int(timeline.get("height", 1080))
        self.fps = int(timeline.get("fps", 30))
        self.out_w, self.out_h = (self.W // 2, self.H // 2) if draft else (self.W, self.H)
        self.theme = get_theme(timeline.get("theme", "midnight"))
        self.scenes: List[Dict[str, Any]] = timeline["scenes"]
        self.starts = [float(s["start"]) for s in self.scenes]
        last = self.scenes[-1]
        self.total = float(timeline.get("duration") or (float(last["start"]) + float(last["duration"])))
        self.total_frames = int(round(self.total * self.fps))
        self.ctx = SceneCtx(resolve_image=self._load_image, captions=bool(timeline.get("captions", True)))
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

    # ----- frames
    def _draw_scene(self, idx: int, lt: float, t_global: float) -> Image.Image:
        sc = self.scenes[idx]
        draw = SCENES.get(sc["type"])
        cv = Canvas(self.W, self.H, ss=self.ss)
        cv.background(self.theme, t_global, ambience=sc["type"] != "image")
        if draw is None:
            cv.text(self.W / 2, self.H / 2, f"unknown scene type: {sc['type']}", "semibold", 48, (255, 255, 255, 255), anchor="mm")
        else:
            draw[0](cv, sc.get("props") or {}, max(0.0, lt), float(sc["duration"]), self.theme, self.ctx)
        if self.ctx.captions:
            words = sc.get("words")
            if words:
                draw_captions(cv, self.theme, words, lt)
        return cv.to_rgb()

    def scene_index(self, t: float) -> int:
        return max(0, min(len(self.scenes) - 1, bisect.bisect_right(self.starts, t) - 1))

    def frame_at(self, t: float) -> Image.Image:
        img = self._compose(t)
        return img.resize((self.out_w, self.out_h), Image.BILINEAR) if self.draft else img

    def _compose(self, t: float) -> Image.Image:
        idx = self.scene_index(t)
        sc = self.scenes[idx]
        lt = t - self.starts[idx]
        img = self._draw_scene(idx, lt, t)
        tr = min(TRANSITION_S, float(sc["duration"]) * 0.4)
        if idx > 0 and lt < tr and sc.get("transition", "fade") != "none":
            prev_lt = float(self.scenes[idx - 1]["duration"]) + lt  # outgoing scene holds its final state
            prev = self._draw_scene(idx - 1, prev_lt, t)
            a = lt / tr
            a = a * a * (3 - 2 * a)
            img = Image.blend(prev, img, a)
        if t > self.total - OUTRO_FADE_S:
            k = max(0.0, min(1.0, (t - (self.total - OUTRO_FADE_S)) / OUTRO_FADE_S))
            img = Image.blend(img, Image.new("RGB", img.size, BLACK), k)
        return img

    def frames(self, f0: int, f1: int) -> Iterator[bytes]:
        """Raw rgb24 bytes for frames [f0, f1)."""
        for f in range(f0, min(f1, self.total_frames)):
            yield self.frame_at(f / self.fps).tobytes()
