"""Timeline -> frames. Pure function of (timeline, t): any frame range can be rendered independently,
which is what makes chunk-parallel rendering on Lambda possible."""
import bisect
import os
import sys
import zlib
from typing import Any, Callable, Dict, Iterator, List, Optional

from PIL import Image

from . import numfmt
from . import watermark as watermark_mod
from .canvas import Canvas
from .frame import Frame
from .scenes import SCENES
from .scenes.formats import draw_framed, is_native
from .scenes.base import SceneCtx
from .scenes.captions import draw_captions, draw_translation, translation_height
from .theme import get_theme


def _bg_anim(timeline: Dict[str, Any], theme: str):
    """The moving background the timeline asks for (`timeline["background"]`, cleaned), or None: a pre-rendered 3D loop (bg_loops.LoopSpec; BG_LOOPS=1, the id is in
    the index and the loop fits the theme, docs/HERO_LOOPS_3D.md), else the procedural one (bg_animated.BgSpec; BG_ANIMATED=1, docs/BACKGROUNDS_ANIMATED.md)."""
    bg = timeline.get("background")
    if not isinstance(bg, dict):
        return None
    if os.environ.get("BG_LOOPS", "0") == "1" and bg.get("loop"):
        from . import background as background_mod, bg_loops
        spec = bg_loops.sanitize(bg, bg_loops.load_index())
        if background_mod.loop_fits(spec, theme):   # the mode decides the text colour: a dark loop never sits under the paper theme
            return spec
    if os.environ.get("BG_ANIMATED", "0") != "1":
        return None
    from . import bg_animated
    return bg_animated.sanitize(bg, theme)

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
    loops_mod = sys.modules.get(f"{pkg}.bg_loops")
    if loops_mod is not None:   # the decoded frames of a background loop (up to 192 MB)
        loops_mod.release()
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
        self.bg_anim = _bg_anim(timeline, self.theme.name)
        self.scenes: List[Dict[str, Any]] = timeline["scenes"]
        self.lead: Optional[Dict[str, Any]] = timeline.get("lead")
        self.outro: bool = bool(timeline.get("outro", True))
        self.starts = [float(s["start"]) for s in self.scenes]
        last = self.scenes[-1]
        self.total = float(timeline.get("duration") or (float(last["start"]) + float(last["duration"])))
        self.total_frames = int(round(self.total * self.fps))
        self.ctx = SceneCtx(resolve_image=self._load_image, resolve_clip=self._load_clip, captions=bool(timeline.get("captions", True)), frame=self.frame, language=numfmt.norm_lang(timeline.get("language")))
        self._clip_loader = clip_loader
        self._clips: Dict[str, Any] = {}
        cv = timeline.get("cover")   # docs/SHARE_PREVIEWS_2026-11-27.md: the designed cover held over the first frames, dissolving into the real opening (first chunk of a final render only)
        self._cover_cfg: Optional[Dict[str, Any]] = cv if isinstance(cv, dict) and not draft and timeline.get("lead") is None else None
        self._cover_img: Optional[Image.Image] = None
        self._image_loader = image_loader
        self._images: Dict[str, Optional[Image.Image]] = {}
        # the watermark (docs/WATERMARK.md): drawn last on every frame, at the output size; None when the timeline has none
        self.wm = watermark_mod.build(timeline.get("watermark"), self.frame, (self.out_w, self.out_h), self.ctx.captions, image_loader)
        if self.wm is not None and self.wm.inset:   # a mark in a top corner: every scene's content box starts below it (seen on QA: a 9:16 logo on a list heading)
            self.frame = self.frame.with_top_inset(self.wm.inset)
            self.ctx.frame = self.frame

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
        # an animated background runs on the video's own clock (the scene's place in the loop, written by the timeline), so it never jumps at a scene change
        bg_t = max(0.0, lt) + (float(sc["bg_t0"]) if self.bg_anim is not None and "bg_t0" in sc else self._ambient_phase(sc))
        amb = sc["type"] != "image"
        cv.background(self.theme, bg_t, ambience=amb, anim=self.bg_anim)
        if draw is None:
            cv.text(fr.W / 2, fr.H / 2, f"unknown scene type: {sc['type']}", "semibold", 48, (255, 255, 255, 255), anchor="mm")
        elif is_native(sc["type"], fr):
            with numfmt.language_scope(self.ctx.language):   # numbers follow the video's language (3,3 in Spanish)
                draw[0](cv, sc.get("props") or {}, max(0.0, lt), float(sc["duration"]), self.theme, self.ctx)
        else:   # no layout for this shape yet: the landscape scene as a card on the themed frame (never fails, never blank)
            with numfmt.language_scope(self.ctx.language):
                rep = draw_framed(cv, draw[0], sc.get("props") or {}, max(0.0, lt), float(sc["duration"]), self.theme, self.ctx, bg_t=bg_t, ambience=amb)
            self.fallbacks[str(sc.get("id", ""))] = dict(rep, type=sc["type"])
        words = sc.get("words") if self.ctx.captions else None
        tr = sc.get("translation")   # a line spoken in another language than the video's (engine/plan_langs.py): its translation row shows even with captions off
        if words:
            draw_captions(cv, self.theme, words, lt, fr, translation_height(cv, fr, tr) if tr else 0.0)
        if tr:
            draw_translation(cv, self.theme, tr, lt, fr)
        if self.big and not self.draft:   # 4K: straight from the supersampled canvas to the output size (never through the 1080 design size)
            return cv.to_rgb((self.out_w, self.out_h))
        return cv.to_rgb()   # design size; frame_at scales it to the output size

    def scene_index(self, t: float) -> int:
        return max(0, min(len(self.scenes) - 1, bisect.bisect_right(self.starts, t) - 1))

    def _cover_frame(self) -> Image.Image:
        """The cover at the output size (made once per Renderer; the first scene at its settled moment, its title, the mark)."""
        if self._cover_img is None:
            from . import cover
            art = cover.render_art(self.tl, self._image_loader, self._clip_loader)
            if art.size != (self.out_w, self.out_h):
                art = art.resize((self.out_w, self.out_h), Image.LANCZOS)
            cfg = self._cover_cfg or {}
            self._cover_img = cover.in_frame(art, str(cfg.get("title") or ""), aspect=self.frame.aspect, theme=self.theme.name, layout=cfg.get("layout"))
        return self._cover_img

    def frame_at(self, t: float) -> Image.Image:
        img = self._compose(t)
        if img.size != (self.out_w, self.out_h):   # draft (half size) or 720p: design units -> output pixels
            img = img.resize((self.out_w, self.out_h), Image.BILINEAR if self.draft else Image.LANCZOS)
        if self._cover_cfg is not None and t < float(self._cover_cfg.get("blend_s", 0.4)):   # frame 0 IS the cover; it dissolves into the opening (no flash, same length, audio untouched)
            a = max(0.0, t) / float(self._cover_cfg.get("blend_s", 0.4))
            img = Image.blend(self._cover_frame(), img, a * a * (3 - 2 * a))
        if self.wm is not None:   # last of all, at output pixels: never scaled with the picture, fades in with the video and out with the closing fade
            k = max(0.0, min(1.0, (t - (self.total - OUTRO_FADE_S)) / OUTRO_FADE_S)) if self.outro else 0.0
            img = self.wm.apply(img, t, first=self.lead is None, outro_k=k)
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
