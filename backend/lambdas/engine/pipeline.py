"""The unit operations of the pipeline, free of any AWS code. Lambda handlers wrap these with S3 I/O;
scripts/local_render.py runs the very same functions on a laptop."""
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from . import media
from . import music as music_mod
from .audio import MIX_SR, SFX_KINDS, SR, build_narration, build_sfx_track, write_wav
from .renderer import Renderer
from .timeline import GOP_SECONDS

# Scenes that "build up" get a soft pop per reveal; calm scenes stay quiet.
POP_SCENES = {"bullets", "diagram", "timeline", "chart"}


def render_chunk(
    timeline: Dict[str, Any],
    f0: int,
    f1: int,
    out_path: str,
    image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None,
    *,
    draft: bool = False,
    clip_loader: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Render frames [f0, f1) of `timeline` into a TS segment whose timestamps start at 0.

    Every segment starts on an IDR frame (fresh encoder), so segments of any length concatenate with `-c copy`.
    """
    r = Renderer(timeline, image_loader, draft=draft, clip_loader=clip_loader)
    gop = r.fps * GOP_SECONDS
    n = media.encode_segment(
        r.frames(f0, f1), out_path,
        width=r.out_w, height=r.out_h, fps=r.fps, start_time=0.0, gop=gop,
        crf=28 if draft else 20, preset="ultrafast" if draft else "veryfast",
    )
    return {"frames": n}


def sfx_events(timeline: Dict[str, Any]) -> List[Tuple[float, str, float]]:
    ev: List[Tuple[float, str, float]] = []
    for i, sc in enumerate(timeline["scenes"]):
        start = float(sc["start"])
        chosen = sc.get("sfx")
        if chosen and chosen != "none":  # the director's own effect replaces the default transition whoosh; a removed tonal effect (bell, ding, chime...) in an old plan is silence
            if chosen in SFX_KINDS:
                ev.append((start + (0.0 if chosen in ("impact", "shutter") else 0.12), chosen, 0.34))
        elif chosen == "none":
            pass
        elif i > 0:
            ev.append((max(0.0, start - 0.12), "whoosh", 0.28))
    return ev


TARGET_LUFS = float(os.environ.get("TARGET_LUFS", "-14"))   # what YouTube plays at; set TARGET_LUFS=-16 for quieter platforms


def make_audio(
    timeline: Dict[str, Any],
    beat_samples: Sequence[np.ndarray],
    out_path: str,
    *,
    music_path: Optional[str] = None,
    music_volume: float = 0.2,
    track_loader: Optional[Callable[[str], Any]] = None,
) -> None:
    """Narration (placed per scene) + music (a library recording, if any) + sfx -> AAC."""
    duration = float(timeline["duration"])
    with tempfile.TemporaryDirectory() as tmp:
        beats = [
            {"offset": float(sc["start"]) + float(sc.get("narration_offset", 0.0)), "samples": s}
            for sc, s in zip(timeline["scenes"], beat_samples)
            if s is not None   # a silent beat has no narration
        ]
        swells = [(float(sc["start"]) + 0.3, float(sc["start"]) + float(sc["duration"]) - 0.2) for sc in timeline["scenes"] if sc.get("silent")]
        intro, outro = float(timeline.get("intro_s") or 0.0), float(timeline.get("outro_s") or 0.0)
        if intro >= 1.2:   # a music-only opening: the bed is up until the voice comes in
            swells.append((0.2, intro + 0.3))
        if outro >= 2.4:   # and a music-only ending, up while the last picture is held
            swells.append((duration - outro + 0.3, duration - 0.2))
        nar = os.path.join(tmp, "nar.wav")
        write_wav(nar, build_narration(beats, duration, SR), SR)
        if not music_path:
            samples = music_mod.render(timeline.get("music"), duration, track_loader)   # a library recording, or None: then there is no background music
            if samples is not None:
                music_path = os.path.join(tmp, "music.wav")
                write_wav(music_path, samples, MIX_SR, channels=2)
        sfx = os.path.join(tmp, "sfx.wav")
        write_wav(sfx, build_sfx_track(sfx_events(timeline), duration), MIX_SR, channels=2)
        media.mix_audio(nar, music_path, sfx, out_path, duration=duration, music_volume=music_volume, swells=swells, loudness_lufs=TARGET_LUFS)


def preview_gif(video_path: str, out_gif: str, duration: float, width: int = 320) -> bool:
    """3-frame crossfading GIF (what the existing UI shows in the Generations grid)."""
    frames: List[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, frac in enumerate((0.2, 0.5, 0.8)):
            png = os.path.join(tmp, f"{k}.png")
            try:
                media.extract_frame(video_path, duration * frac, png)
                im = Image.open(png).convert("RGB")
                frames.append(im.resize((width, max(1, int(im.height * width / im.width))), Image.LANCZOS))
            except Exception:
                continue
    if not frames:
        return False
    seq: List[Image.Image] = []
    durs: List[int] = []
    for i, f in enumerate(frames):
        seq.append(f)
        durs.append(1200)
        if i < len(frames) - 1:
            for k in range(1, 6):
                seq.append(Image.blend(f, frames[i + 1], k / 6))
                durs.append(120)
    seq[0].save(out_gif, save_all=True, append_images=seq[1:], duration=durs, loop=0, optimize=True)
    return True
