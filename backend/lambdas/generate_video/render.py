from typing import Any, Dict, Optional, List, Tuple
import os
import json
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from .db import update_status


# Ensure temp directories point to writable /tmp in Lambda
os.environ.setdefault("TMPDIR", "/tmp")
os.environ.setdefault("TEMP", "/tmp")
os.environ.setdefault("TMP", "/tmp")


def _get_table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("VIDEOS_TABLE", "")
    if not name:
        raise RuntimeError("VIDEOS_TABLE environment variable is not set")
    return boto3.resource("dynamodb").Table(name)


def _get_video_item(video_id: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    table = _get_table(table_name)
    try:
        resp = table.get_item(Key={"video_id": video_id})
        return (resp.get("Item") or {})
    except ClientError as e:
        logging.exception("Failed to get video item for video_id=%s: %s", video_id, str(e))
        return {}


def _is_s3_uri(path: str) -> bool:
    return isinstance(path, str) and path.startswith("s3://")


def _download_s3_uri_to_tmp(s3_uri: str) -> str:
    try:
        # s3://bucket/key
        _, _, rest = s3_uri.partition("s3://")
        bucket, _, key = rest.partition("/")
        if not bucket or not key:
            return s3_uri
        s3 = boto3.client("s3")
        local_dir = Path("/tmp/assets")
        local_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(key).name
        local_path = local_dir / filename
        s3.download_file(bucket, key, str(local_path))
        return str(local_path)
    except Exception as e:
        logging.exception("Failed to download %s: %s", s3_uri, str(e))
        return s3_uri


def _ensure_local_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return path
    if _is_s3_uri(path):
        return _download_s3_uri_to_tmp(path)
    return path


# --------------------------- compatibility shims --------------------------- #

def set_dur(clip, t):
    return clip.set_duration(t) if hasattr(clip, "set_duration") else clip.with_duration(t)


def set_pos(clip, pos):
    return clip.set_position(pos) if hasattr(clip, "set_position") else clip.with_position(pos)


def set_start(clip, t):
    return clip.set_start(t) if hasattr(clip, "set_start") else clip.with_start(t)


def resize_clip(clip, *args, **kwargs):
    if hasattr(clip, "resize"):
        if "newsize" in kwargs:
            return clip.resize(newsize=kwargs["newsize"])
        return clip.resize(*args, **kwargs)
    if hasattr(clip, "resized"):
        if "newsize" in kwargs:
            return clip.resized(kwargs["newsize"])
        if args:
            return clip.resized(*args)
        return clip
    return clip


def subclip_from(clip, start, end=None):
    if hasattr(clip, "subclip"):
        return clip.subclip(start, end) if end is not None else clip.subclip(start)
    return clip.subclipped(start, end) if end is not None else clip.subclipped(start)


def crop_clip(clip, **kwargs):
    from moviepy import vfx  # lazy import for Lambda size
    if hasattr(clip, "crop"):
        return clip.crop(**kwargs)
    if hasattr(vfx, "crop"):
        return clip.fx(vfx.crop, **kwargs)
    return clip


def set_audio_clip(clip, audio):
    return clip.set_audio(audio) if hasattr(clip, "set_audio") else clip.with_audio(audio)


def without_audio(clip):
    return clip.without_audio()


def fade_in(clip, d):
    from moviepy import vfx
    if hasattr(vfx, "fadein"):
        return clip.fx(vfx.fadein, d)
    return clip


def fade_out(clip, d):
    from moviepy import vfx
    if hasattr(vfx, "fadeout"):
        return clip.fx(vfx.fadeout, d)
    return clip


def crossfade_in(clip, d):
    return clip.crossfadein(d) if hasattr(clip, "crossfadein") else clip


def crossfade_out(clip, d):
    return clip.crossfadeout(d) if hasattr(clip, "crossfadeout") else clip


def volume_x(clip, f):
    return clip.volumex(f) if hasattr(clip, "volumex") else clip


# ------------------------------- utilities -------------------------------- #

def pct(val, total):
    return int(val * total) if isinstance(val, float) and 0 <= val <= 1 else int(val)


def _num(x, default=1.0):
    try:
        return float(x)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        from decimal import Decimal as _D
        if isinstance(value, _D):
            return int(value)
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        from decimal import Decimal as _D
        if isinstance(value, _D):
            return float(value)
        return float(value)
    except Exception:
        return default


def loop_audio_to_duration(audio, duration: float):
    """Loop an audio clip to at least the given duration.

    Tries built-in audio_loop if available; otherwise concatenates copies and
    trims to exact duration.
    """
    try:
        from moviepy import afx  # lazy import
        if hasattr(afx, "audio_loop"):
            return afx.audio_loop(audio, duration=float(duration))
    except Exception:
        pass
    try:
        from moviepy import concatenate_audioclips  # lazy import
        total = float(duration)
        src_dur = float(getattr(audio, "duration", 0) or 0)
        if src_dur <= 0 or total <= 0:
            return set_dur(audio, max(0.0, total))
        clips = []
        remaining = total
        while remaining > 0:
            if remaining < src_dur:
                clips.append(subclip_from(audio, 0, remaining))
                remaining = 0
            else:
                clips.append(audio)
                remaining -= src_dur
        out = concatenate_audioclips(clips)
        return set_dur(out, total)
    except Exception:
        return set_dur(audio, float(duration))


def parse_color(color_val):
    if isinstance(color_val, (list, tuple)):
        return tuple(map(int, color_val[:3]))
    if isinstance(color_val, str):
        table = {
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "cyan": (0, 255, 255),
            "magenta": (255, 0, 255),
            "orange": (255, 165, 0),
            "purple": (128, 0, 128),
            "pink": (255, 192, 203),
            "brown": (165, 42, 42),
            "gray": (128, 128, 128),
            "grey": (128, 128, 128),
        }
        return table.get(color_val.lower(), (255, 255, 255))
    return (255, 255, 255)


# ------------------------------- builders --------------------------------- #

def make_bg_clip(bg: Dict[str, Any], duration: float, size: Tuple[int, int]):
    from moviepy import ImageClip, ColorClip, VideoFileClip
    W, H = size
    t = (bg.get("type") or "color").lower()

    if t == "color":
        color = parse_color(bg.get("value", (0, 0, 0)))
        return set_dur(ColorClip(size=(W, H), color=color), duration)

    if t == "image":
        path = _ensure_local_path(bg.get("path", ""))
        if not path or not Path(path).exists():
            return set_dur(ColorClip(size=(W, H), color=(0, 0, 0)), duration)
        img = set_dur(ImageClip(str(path)), duration)
        fit = (bg.get("fit") or "cover").lower()
        if fit == "cover":
            scale = max(W / img.w, H / img.h)
            img = resize_clip(img, scale)
            img = crop_clip(img, x_center=img.w // 2, y_center=img.h // 2, width=W, height=H)
        else:
            scale = min(W / img.w, H / img.h)
            img = resize_clip(img, scale)
            from moviepy import CompositeVideoClip
            bgc = set_dur(ColorClip((W, H), color=(0, 0, 0)), duration)
            img = set_dur(CompositeVideoClip([bgc, set_pos(img, "center")], size=(W, H)), duration)
        return img

    if t == "video":
        path = _ensure_local_path(bg.get("path", ""))
        if not path or not Path(path).exists():
            return set_dur(ColorClip(size=(W, H), color=(0, 0, 0)), duration)
        clip = VideoFileClip(str(path))
        clip = subclip_from(clip, 0, min(duration, getattr(clip, "duration", duration)))
        if (getattr(clip, "w", None), getattr(clip, "h", None)) != (W, H):
            clip = resize_clip(clip, (W, H))
        return set_dur(clip, duration)

    return set_dur(ColorClip(size=(W, H), color=(0, 0, 0)), duration)


def _font(path: Optional[str], size: int):
    from PIL import ImageFont
    try:
        # Resolve S3 or local path if provided
        if path:
            try:
                resolved = _ensure_local_path(path)
            except Exception:
                resolved = path
            if resolved and Path(resolved).exists():
                return ImageFont.truetype(resolved, size)

        # Allow overriding via environment (e.g., Lambda layer under /opt)
        env_font = os.environ.get("FONT_PATH")
        if env_font and Path(env_font).exists():
            return ImageFont.truetype(env_font, size)

        # Bundled font with the lambda package (preferred fallback)
        try:
            here = Path(__file__).resolve().parent
            bundled = here / "assets" / "fonts" / "Inter-Regular.ttf"
            if bundled.exists():
                return ImageFont.truetype(str(bundled), size)
        except Exception:
            pass

        # Common Lambda layer font locations
        lambda_candidates = [
            "/opt/fonts/DejaVuSans.ttf",
            "/opt/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/opt/share/fonts/NotoSans-Regular.ttf",
            "/opt/fonts/NotoSans-Regular.ttf",
        ]
        for cand in lambda_candidates:
            if Path(cand).exists():
                return ImageFont.truetype(cand, size)

        # Try common system locations (useful for local dev)
        system_candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for sys in system_candidates:
            if Path(sys).exists():
                return ImageFont.truetype(sys, size)
    except Exception:
        pass
    return ImageFont.load_default()


def rounded_box(w, h, r, fill=(0, 0, 0, 128)):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=fill)
    return img


def _text_image(item: Dict[str, Any], canvas: Tuple[int, int]):
    from PIL import Image, ImageDraw, ImageFont as _IF
    W, H = canvas
    text = item.get("text", "")
    font_size = _as_int(item.get("fontsize", item.get("font_size", 48)), 48)
    color = parse_color(item.get("color", "white"))
    font_path = item.get("font")
    align = (item.get("align") or "left").lower()
    font = _font(font_path, font_size)

    box_cfg = item.get("box", {})
    pad = _as_int(box_cfg.get("padding", 16), 16)
    radius = _as_int(box_cfg.get("radius", 24), 24)
    fill_val = box_cfg.get("fill", (0, 0, 0, 120))
    if isinstance(fill_val, (list, tuple)):
        fill = tuple(_as_int(c, 0) for c in list(fill_val)[:4])
        if len(fill) < 4:
            fill = tuple(list(fill) + [120] * (4 - len(fill)))
    else:
        fill = (0, 0, 0, 120)

    max_w = None
    if "width" in box_cfg:
        try:
            max_w = max(100, int(_as_float(box_cfg["width"], 0.8) * W) - 2 * pad)
        except Exception:
            max_w = None

    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    words = str(text).split()
    lines: List[str] = []
    if max_w:
        cur = ""
        for w in words:
            tline = (cur + " " + w).strip()
            bbox = draw.textbbox((0, 0), tline, font=font)
            if bbox[2] - bbox[0] <= max_w or not cur:
                cur = tline
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    else:
        lines = str(text).split("\n")

    widths, heights = [], []
    for ln in lines:
        b = draw.textbbox((0, 0), ln, font=font)
        widths.append(b[2] - b[0])
        heights.append(b[3] - b[1])

    text_w = max(widths) if widths else 0
    line_gap = max(4, int(font_size * 0.3))
    text_h = sum(heights) + line_gap * max(0, len(lines) - 1)

    box_w = _as_int((max_w + 2 * pad), text_w + 2 * pad) if max_w else (text_w + 2 * pad)
    box_h = _as_int(text_h + 2 * pad, text_h + 2 * pad)

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    if len(fill) == 4 and fill[3] > 0:
        img.alpha_composite(rounded_box(box_w, box_h, radius, fill))

    y = pad
    draw_img = ImageDraw.Draw(img)
    for ln, w, h in zip(lines, widths, heights):
        if align == "center":
            x = (box_w - w) // 2
        elif align == "right":
            x = box_w - pad - w
        else:
            x = pad
        draw_img.text((x, y), ln, fill=color, font=font)
        y += h + line_gap
    # If we had to fall back to PIL's default bitmap font, upsample the image to approximate requested size
    try:
        if not isinstance(font, _IF.FreeTypeFont):
            # Default bitmap font height is ~11px; scale to requested font_size
            base_h = max(11, heights[0] if heights else 11)
            scale = max(1, int(round(font_size / float(base_h))))
            if scale > 1:
                from PIL import Image as _PILImage
                resample = getattr(_PILImage, "Resampling", _PILImage).__dict__.get("LANCZOS", 1)
                img = img.resize((img.width * scale, img.height * scale), resample=resample)
    except Exception:
        pass
    return img


def make_text_clip(item: Dict[str, Any], size: Tuple[int, int], duration: float):
    import numpy as np
    from moviepy import ImageClip
    W, H = size
    img = _text_image(item, size)
    clip = set_dur(ImageClip(np.array(img)), duration)

    align = (item.get("align") or "left").lower()
    x = item.get("x", 0.5 if align == "center" else 0.08)
    y = item.get("y", 0.5)

    if align == "center":
        left = _as_int((W - img.width) // 2, 0)
    elif align == "right":
        x_px = pct(x, W) if isinstance(x, float) else _as_int(x, 0)
        left = _as_int(W - x_px - img.width, 0)
    else:
        left = pct(x, W) if isinstance(x, float) else _as_int(x, 0)

    top = (_as_int(pct(y, H) - img.height // 2) if isinstance(y, float) and 0 <= y <= 1 else _as_int(y, 0))
    clip = set_pos(clip, (left, top))
    return clip


def make_caption_overlay(item: Dict[str, Any], size: Tuple[int, int], duration: float):
    # Provide strong defaults for captions near the bottom center
    caption: Dict[str, Any] = {
        "type": "text",
        "text": str(item.get("text", "")),
        "fontsize": int(item.get("fontsize", 40)),
        "color": item.get("color", "white"),
        "align": item.get("align", "center"),
        "y": item.get("y", 0.85),
        "effects": item.get("effects", ["fadein:0.3"]),
        "box": item.get(
            "box",
            {"width": 0.9, "padding": 18, "radius": 10, "fill": [0, 0, 0, 220]},
        ),
    }
    return make_text_clip(caption, size, duration)


def make_video_overlay(item: Dict[str, Any], size: Tuple[int, int], duration: float):
    from moviepy import VideoFileClip, ColorClip
    W, H = size
    path = _ensure_local_path(item.get("path"))
    if not path or not Path(path).exists():
        w = int(item.get("width", 300))
        h = int(item.get("height", 200))
        return set_dur(ColorClip((w, h), color=(50, 50, 50)), duration)

    video = VideoFileClip(str(path))
    start_offset = float(item.get("start_offset", 0) or 0)
    if 0 < start_offset < getattr(video, "duration", duration):
        video = subclip_from(video, start_offset)

    width = item.get("width")
    height = item.get("height")
    vw, vh = getattr(video, "w", None), getattr(video, "h", None)
    if isinstance(width, float):
        width = pct(width, W)
    if isinstance(height, float):
        height = pct(height, H)
    if width and height:
        video = resize_clip(video, (int(width), int(height)))
    elif width:
        video = resize_clip(video, width / max(vw or 1, 1))
    elif height:
        video = resize_clip(video, height / max(vh or 1, 1))

    x_val = item.get("x", 0)
    y_val = item.get("y", 0)
    x = pct(x_val, W) if isinstance(x_val, float) and 0 <= x_val <= 1 else int(x_val)
    y = pct(y_val, H) if isinstance(y_val, float) and 0 <= y_val <= 1 else int(y_val)
    video = set_pos(video, (x, y))
    video = set_dur(video, min(duration, getattr(video, "duration", duration)))
    return video


def make_image_overlay(item: Dict[str, Any], size: Tuple[int, int], duration: float):
    from moviepy import ImageClip
    W, H = size
    path = _ensure_local_path(item.get("path"))
    if not path or not Path(path).exists():
        return None
    img = set_dur(ImageClip(str(path)), duration)
    width = item.get("width", 0.5)
    height = item.get("height", 0.5)
    w_px = pct(width, W) if isinstance(width, float) else int(width)
    h_px = pct(height, H) if isinstance(height, float) else int(height)
    img = resize_clip(img, (w_px, h_px))

    align = (item.get("align") or "left").lower()
    x = item.get("x", 0.5 if align == "center" else 0.1)
    y = item.get("y", 0.5)
    pos_x = (W - w_px) // 2 if align == "center" else (pct(x, W) if isinstance(x, float) else int(x))
    pos_y = pct(y, H) - h_px // 2 if isinstance(y, float) else int(y)
    img = set_pos(img, (pos_x, pos_y))
    return img


def build_scene(scene: Dict[str, Any], size: Tuple[int, int]):
    from moviepy import CompositeVideoClip, ColorClip
    dur = float(scene.get("duration", scene.get("duration_s", 3)))
    bg = make_bg_clip(scene.get("background", {"type": "color", "value": (0, 0, 0)}), dur, size)
    layers = [bg]
    scene_audio_clips = []

    overlays = sorted(scene.get("overlays", []), key=lambda it: it.get("z", 0))
    for item in overlays:
        t = (item.get("type") or "").lower()
        try:
            if t in ("text", "textbox"):
                layers.append(make_text_clip(item, size, dur))
            elif t == "caption":
                layers.append(make_caption_overlay(item, size, dur))
            elif t == "video":
                video_clip = make_video_overlay(item, size, dur)
                layers.append(video_clip)
                if getattr(video_clip, "audio", None):
                    scene_audio_clips.append(video_clip.audio)
            elif t == "image":
                img_clip = make_image_overlay(item, size, dur)
                if img_clip:
                    layers.append(img_clip)
        except Exception as e:
            logging.warning("overlay error (%s): %s", t, str(e))

    scene_clip = set_dur(CompositeVideoClip(layers, size=size), dur)
    if scene_audio_clips:
        from moviepy import CompositeAudioClip
        scene_clip = set_audio_clip(scene_clip, CompositeAudioClip(scene_audio_clips))
    return scene_clip


def apply_transition(prev, nxt, spec: str):
    name, arg = (spec.split(":", 1) + ["0.5"])[:2] if ":" in spec else (spec, "0.5")
    d = _num(arg, 0.5)
    name = (name or "none").lower()
    if name == "none":
        return prev, set_start(nxt, prev.end)
    if name == "fade":
        return fade_out(prev, d), set_start(fade_in(nxt, d), prev.end)
    if name == "crossfade":
        return crossfade_out(prev, d), set_start(crossfade_in(nxt, d), prev.end - d)
    return prev, set_start(nxt, prev.end)


def _compose_and_render(storyboard: Dict[str, Any], workdir: Path) -> Tuple[str, float]:
    from moviepy import CompositeVideoClip, AudioFileClip, CompositeAudioClip

    out = storyboard.get("output", {})
    W, H = int(out.get("width", 1920)), int(out.get("height", 1080))
    fps = int(out.get("fps", 30))
    crf = str(out.get("crf", 18))
    audio_bitrate = out.get("audio_bitrate", "192k")

    scenes = storyboard.get("scenes", [])
    comps: List[Any] = []
    for i, scene in enumerate(scenes, 1):
        try:
            comps.append(build_scene(scene, (W, H)))
        except Exception as e:
            logging.warning("scene %s failed: %s", i, str(e))
            from moviepy import ColorClip
            comps.append(set_dur(ColorClip(size=(W, H), color=(0, 0, 0)), float(scene.get("duration", 3))))

    default_tr = (storyboard.get("transitions", {}) or {}).get("default", "none")
    timeline: List[Any] = []
    for i, clip in enumerate(comps):
        if i == 0:
            timeline.append(set_start(clip, 0.0))
        else:
            a, b = apply_transition(timeline[-1], clip, default_tr)
            timeline[-1] = a
            timeline.append(b)

    video = CompositeVideoClip(timeline, size=(W, H))
    total_dur = float(getattr(video, "duration", 0) or 0)
    # Avoid floating-point overshoot at the tail end
    if total_dur > 0:
        total_dur = max(0.0, total_dur - 0.02)

    tracks = []
    if getattr(video, "audio", None):
        tracks.append(video.audio)

    music_cfg = storyboard.get("audio", {}) or {}
    music_path = _ensure_local_path(music_cfg.get("music"))
    music_vol = float(music_cfg.get("music_volume", 0.3))
    if music_path and Path(music_path).exists() and total_dur > 0:
        music = AudioFileClip(music_path)
        src_dur = float(getattr(music, "duration", 0) or 0)
        if src_dur <= 0:
            pass
        elif src_dur + 0.01 < total_dur:
            # Loop music to fill the entire duration
            music = loop_audio_to_duration(music, total_dur)
        else:
            # Trim slightly before the end to prevent out-of-range reads due to float rounding
            safe_end = max(0.0, min(total_dur, src_dur) - 0.05)
            if safe_end > 0:
                music = subclip_from(music, 0, safe_end)
        music = volume_x(music, music_vol)
        tracks.append(music)

    if tracks:
        video = set_audio_clip(video, CompositeAudioClip(tracks))

    filename = out.get("filename", "out.mp4")
    local_out = workdir / filename
    local_out.parent.mkdir(parents=True, exist_ok=True)

    temp_audio = str((workdir / "temp_audio.m4a").resolve())
    os.makedirs(os.path.dirname(temp_audio), exist_ok=True)
    video.write_videofile(
        str(local_out),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=temp_audio,
        remove_temp=True,
        ffmpeg_params=["-movflags", "+faststart", "-crf", crf, "-b:a", audio_bitrate],
    )
    return str(local_out), total_dur


def render_video(
    video_id: str, user_id: str, assets: Dict[str, Any], storyboard: Dict[str, Any], table_name: Optional[str] = None
) -> Dict[str, Any]:
    update_status(video_id, "RENDERING", table_name)

    item = _get_video_item(video_id, table_name)
    user_id_fresh = item.get("user_id") or user_id
    storyboard_fresh = item.get("storyboard") or storyboard or {}

    # Ensure any S3 paths in storyboard are downloadable
    for scene in storyboard_fresh.get("scenes", []) or []:
        bg = scene.get("background") or {}
        if isinstance(bg, dict) and bg.get("type") == "image":
            bg_path = bg.get("path")
            if bg_path:
                bg["path"] = _ensure_local_path(bg_path)
        for ov in scene.get("overlays", []) or []:
            if isinstance(ov, dict) and "path" in ov:
                ov["path"] = _ensure_local_path(ov.get("path"))

    workdir = Path("/tmp/render")
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        local_file, total_dur = _compose_and_render(storyboard_fresh, workdir)
    except Exception as e:
        logging.exception("Rendering failed for video_id=%s: %s", video_id, str(e))
        raise

    # Upload to S3
    bucket = os.environ.get("ASSETS_BUCKET", "videomk.com")
    ext = Path(local_file).suffix or ".mp4"
    key = f"videos/{user_id_fresh}/{video_id}{ext}"
    s3 = boto3.client("s3")
    s3.upload_file(local_file, bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    s3_uri = f"s3://{bucket}/{key}"

    final = {
        "video_uri": s3_uri,
        "duration_s": int(total_dur or 0),
    }
    update_status(video_id, "COMPLETE", table_name, extra_attributes=final)
    return final


