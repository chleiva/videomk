"""The unit operations of the pipeline, free of any AWS code. Lambda handlers wrap these with S3 I/O;
scripts/local_render.py runs the very same functions on a laptop."""
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from . import media
from .audio import MIX_SR, SR, build_narration, build_sfx_track, generate_music, write_wav
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
) -> Dict[str, Any]:
    r = Renderer(timeline, image_loader, draft=draft)
    gop = r.fps * GOP_SECONDS
    if f0 % gop:
        raise ValueError(f"chunk start {f0} is not a multiple of the GOP ({gop})")
    n = media.encode_segment(
        r.frames(f0, f1), out_path,
        width=r.out_w, height=r.out_h, fps=r.fps, start_time=f0 / r.fps, gop=gop,
        crf=28 if draft else 20, preset="ultrafast" if draft else "veryfast",
    )
    return {"frames": n, "f0": f0, "f1": f0 + n}


def sfx_events(timeline: Dict[str, Any]) -> List[Tuple[float, str, float]]:
    ev: List[Tuple[float, str, float]] = []
    for i, sc in enumerate(timeline["scenes"]):
        start = float(sc["start"])
        if i > 0:
            ev.append((max(0.0, start - 0.12), "whoosh", 0.28))
        if sc["type"] in POP_SCENES:
            for c in sc.get("cues") or []:
                ev.append((start + float(c), "pop", 0.16))
    return ev


def make_audio(
    timeline: Dict[str, Any],
    beat_samples: Sequence[np.ndarray],
    out_path: str,
    *,
    music_path: Optional[str] = None,
    music_volume: float = 0.2,
) -> None:
    """Narration (placed per scene) + music (generated unless provided) + sfx -> AAC."""
    duration = float(timeline["duration"])
    with tempfile.TemporaryDirectory() as tmp:
        beats = [
            {"offset": float(sc["start"]) + float(sc.get("narration_offset", 0.0)), "samples": s}
            for sc, s in zip(timeline["scenes"], beat_samples)
        ]
        nar = os.path.join(tmp, "nar.wav")
        write_wav(nar, build_narration(beats, duration, SR), SR)
        if not music_path:
            music_path = os.path.join(tmp, "music.wav")
            write_wav(music_path, generate_music(min(duration, 90.0), timeline.get("mood", "calm")), MIX_SR, channels=2)
        sfx = os.path.join(tmp, "sfx.wav")
        write_wav(sfx, build_sfx_track(sfx_events(timeline), duration), MIX_SR, channels=2)
        media.mix_audio(nar, music_path, sfx, out_path, duration=duration, music_volume=music_volume)


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
