"""The final stage: the watermark and the closing card, applied to a FINISHED video (docs/WATERMARK.md, docs/WATERMARK_DECOUPLED_2026-11-28.md).

The watermark is independent of how a video is made. Scenes, captions, plan, timeline, audio and the cached render segments know nothing about it; this module is the only place it
exists. Its input is the watermark-free master (the cached segments stitched with the audio: `media.mux_final`), its output the video the customer gets:

  1. the lockup is drawn over the master (ffmpeg overlay of two pre-rendered transparent PNGs, a white one with a shadow and an ink one with a glow, or the person's own logo): its place is
     fixed per shape (watermark_spec.layout), its visibility is an alpha envelope worked out from the timeline (always: fades in, leaves with the closing fade; moments: the timeline's windows),
     and white or ink follows the brightness measured under it in the finished frames (per scene piece, smooth crossfade);
  2. the 'Made with videomk' card (an optional 2.4 s clip, rendered here, silent) is appended after the content: the content's own length, audio and music fade are untouched, and the audio
     gets 2.4 s of silence at the end.

`export(...)` with `spec_override` = {"mode": "none"} returns the master itself: the SAME video without the watermark, from the same cached segments, no scene re-rendered.
Only the video track is re-encoded (same x264 settings as a segment); the audio is copied except for the padding of the card.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from . import media
from . import watermark as wm_mod
from . import watermark_spec as ws
from .frame import Frame
from .renderer import OUTRO_FADE_S, Renderer, output_size
from .timeline import GOP_SECONDS, end_card_timeline

log = logging.getLogger(__name__)
SAMPLE_FPS = 4              # frames per second looked at under the mark to choose white or ink
PIECE_S = 4.0               # a scene longer than this is judged in pieces, so a slow change of picture under the mark is followed
INK_FLIP_S = 0.4            # white and ink crossfade over this long
HYST = 0.03                 # a piece changes colour only when its brightness is this far past the middle of the white/ink band
CARD_FADE_IN_S = 0.4        # the card comes up from black (the content ended on its closing fade to black)
MAX_FLIPS = 120
_UNSET: Any = object()


# ----------------------------------------------------------------------------- the alpha envelope and the ink schedule (pure functions of the timeline and the measured brightness)
def _ss(x: str) -> str:
    c = f"clip({x},0,1)"
    return f"({c}*{c}*(3-2*{c}))"


def envelope_expr(spec: Dict[str, Any], duration: float) -> str:
    """The mark's visibility 0..1 as an ffmpeg expression of the time T (seconds of the content): `moments` = the timeline's appearances (eased ramps), `always` = eased fade in over FADE_IN_S
    and gone with the closing fade to black (the last OUTRO_FADE_S of the content)."""
    if spec.get("mode") == "videomk" and spec.get("presence") == "moments":
        f = ws.MOMENT_FADE_S
        terms = [_ss(f"min((T-{a:.3f})/{f},({b:.3f}-T)/{f})") for a, b in ws.clean_windows(spec.get("windows"))]
        return "max(" + ",".join(terms) + ")" if len(terms) > 1 else (terms[0] if terms else "0")
    return f"{_ss(f'T/{ws.FADE_IN_S}')}*(1-clip((T-({duration:.3f}-{OUTRO_FADE_S}))/{OUTRO_FADE_S},0,1))"


def envelope(spec: Dict[str, Any], duration: float, t: float) -> float:
    """The same envelope in Python (tests; what the expression computes)."""
    def ss(x: float) -> float:
        c = max(0.0, min(1.0, x))
        return c * c * (3 - 2 * c)
    if spec.get("mode") == "videomk" and spec.get("presence") == "moments":
        return max([ss(min((t - a) / ws.MOMENT_FADE_S, (b - t) / ws.MOMENT_FADE_S)) for a, b in ws.clean_windows(spec.get("windows"))] or [0.0])
    return ss(t / ws.FADE_IN_S) * (1.0 - max(0.0, min(1.0, (t - (duration - OUTRO_FADE_S)) / OUTRO_FADE_S)))


def pieces(scenes: List[Dict[str, Any]], duration: float) -> List[Tuple[float, float]]:
    """The intervals of the content the colour under the mark is judged over: every scene, cut into pieces of at most PIECE_S."""
    bounds: List[float] = []
    for i, sc in enumerate(scenes):
        a = float(sc["start"])
        b = float(scenes[i + 1]["start"]) if i + 1 < len(scenes) else duration
        n = max(1, int(-(-(b - a) // PIECE_S)))
        bounds += [a + (b - a) * k / n for k in range(n)]
    bounds = sorted(set(round(x, 3) for x in bounds if 0 <= x < duration)) or [0.0]
    return [(a, (bounds[i + 1] if i + 1 < len(bounds) else duration)) for i, a in enumerate(bounds)]


def ink_schedule(means: List[float], scenes: List[Dict[str, Any]], duration: float, fps: float = SAMPLE_FPS) -> Tuple[int, List[Tuple[float, int]]]:
    """(the starting colour 0 white / 1 ink, [(time, colour)] flips): the mean brightness (0..1) of the finished frames under the mark, judged per scene piece, with hysteresis. The closing
    fade to black is ignored (the mark leaves with the picture, it does not turn white while it goes)."""
    mid = (wm_mod.LIGHT_FROM + wm_mod.LIGHT_TO) / 2.0
    usable = duration - OUTRO_FADE_S - 0.1
    cur: Optional[int] = None
    start, flips = 0, []
    for a, b in pieces(scenes, duration):
        vals = [m for k, m in enumerate(means) if a <= k / fps < b and k / fps <= usable]
        if not vals:
            continue
        m = sum(vals) / len(vals)
        want = (1 if m >= mid else 0) if cur is None else (1 if m > mid + HYST else 0 if m < mid - HYST else cur)
        if cur is None:
            cur = start = want
        elif want != cur:
            flips.append((a, want))
            cur = want
    return start, flips[:MAX_FLIPS]


def ink_expr(start: int, flips: List[Tuple[float, int]]) -> str:
    """The ink weight 0..1 as an expression of T: `start`, then a smooth step to each flip's colour over INK_FLIP_S centred on its time."""
    terms, prev = [str(start)], start
    for t, v in flips:
        terms.append(f"{v - prev:+d}*{_ss(f'(T-{t - INK_FLIP_S / 2:.3f})/{INK_FLIP_S}')}")
        prev = v
    return "(" + "".join(terms) + ")"


# ----------------------------------------------------------------------------- ffmpeg
def sample_brightness(video: str, rect: Tuple[int, int, int, int], size: Tuple[int, int], fps: float = SAMPLE_FPS) -> List[float]:
    """Mean brightness 0..1 of the area `rect` (output px) in the frames of `video`, `fps` samples a second."""
    x0, y0 = max(0, rect[0]), max(0, rect[1])
    x1, y1 = min(size[0], rect[2]), min(size[1], rect[3])
    w, h = max(2, (x1 - x0) // 2 * 2), max(2, (y1 - y0) // 2 * 2)
    cmd = [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-i", video, "-an", "-vf", f"fps={fps},crop={w}:{h}:{x0}:{y0},scale=16:8:flags=area,format=gray", "-f", "rawvideo", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg brightness sampling failed: {proc.stderr[-400:].decode('utf-8', 'replace')}")
    n = 16 * 8
    data = proc.stdout
    return [sum(data[i:i + n]) / (255.0 * n) for i in range(0, len(data) - n + 1, n)]


def _overlay_graph(art: "wm_mod.Watermark", env: str, ink: Optional[str]) -> str:
    """The filter graph: the master, then the white layer (and the ink layer) with their alpha computed per frame from the envelope, overlaid at the mark's place."""
    x, y = art.pos
    g = ["[0:v]format=yuv420p[b0]"]
    layers = [("w", 1, f"({env})*(1-{ink})" if ink else f"({env})")] + ([("k", 2, f"({env})*{ink}")] if ink else [])
    cur = "b0"
    for i, (name, idx, expr) in enumerate(layers):
        g.append(f"[{idx}:v]format=gbrap,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({expr})'[{name}]")
        g.append(f"[{cur}][{name}]overlay=x={x}:y={y}:format=auto:eof_action=pass[o{i}]")
        cur = f"o{i}"
    g.append(f"[{cur}]format=yuv420p[v]")
    return ";\n".join(g)


def draw_mark(master: str, out_ts: str, tl: Dict[str, Any], spec: Dict[str, Any], art: "wm_mod.Watermark", size: Tuple[int, int], draft: bool, tmp: str) -> None:
    """Master MP4 -> an MPEG-TS of the same video with the lockup drawn on it (re-encoded with the segments' x264 settings)."""
    duration = float(tl["duration"])
    fps = int(tl.get("fps") or 30)
    white = os.path.join(tmp, "wm_white.png")
    art.layer.save(white)
    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{duration + 1:.3f}", "-i", white]
    ink = None
    if art.layer_ink is not None:
        kp = os.path.join(tmp, "wm_ink.png")
        art.layer_ink.save(kp)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{duration + 1:.3f}", "-i", kp]
        start, flips = ink_schedule(sample_brightness(master, art.rect_px, size), tl["scenes"], duration)
        ink = ink_expr(start, flips)
        log.info("WATERMARK_INK start=%s flips=%s", start, flips)
    graph_path = os.path.join(tmp, "wm_graph.txt")
    with open(graph_path, "w") as fh:
        fh.write(_overlay_graph(art, envelope_expr(spec, duration), ink))
    enc = media.encode_settings(size[0], size[1], draft)
    gop = fps * GOP_SECONDS
    cmd = [media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", master, *inputs, "-filter_complex_script", graph_path, "-map", "[v]", "-an",
           "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]), "-pix_fmt", "yuv420p", *enc["extra"],
           "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-bf", "2", "-x264-params", "open-gop=0", "-threads", "0",
           "-output_ts_offset", "0", "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", out_ts]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg watermark overlay failed: {proc.stderr[-800:]}")


def render_end_card(tl: Dict[str, Any], out_ts: str, draft: bool, image_loader: Any = None) -> int:
    """The closing card as a TS segment, same size, fps and encoder settings as the content; comes up from black over CARD_FADE_IN_S and ends on the closing fade to black."""
    ct = end_card_timeline(tl)
    r = Renderer(ct, image_loader, draft=draft)
    enc = media.encode_settings(r.out_w, r.out_h, draft)
    black = Image.new("RGB", (r.out_w, r.out_h), (0, 0, 0))
    n = int(round(float(ct["duration"]) * r.fps))

    def frames():
        for f in range(n):
            t = f / r.fps
            img = r.frame_at(t)
            if t < CARD_FADE_IN_S:
                u = t / CARD_FADE_IN_S
                img = Image.blend(black, img, u * u * (3 - 2 * u))
            yield img.tobytes()
    return media.encode_segment(frames(), out_ts, width=r.out_w, height=r.out_h, fps=r.fps, start_time=0.0, gop=r.fps * GOP_SECONDS, crf=enc["crf"], preset=enc["preset"], extra=enc["extra"])


def pad_audio(audio: str, out_path: str, seconds: float) -> None:
    """The content's audio followed by `seconds` of silence (the card has no sound: no music tail, no sting)."""
    proc = subprocess.run([media.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", audio, "-af", f"apad=pad_dur={seconds:.3f}", "-c:a", "aac", "-b:a", "192k", out_path],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio pad failed: {proc.stderr[-400:]}")


def spec_of(tl: Dict[str, Any], override: Any = _UNSET) -> Optional[Dict[str, Any]]:
    """The watermark spec the final stage uses: the timeline's (what the video was made with) or `override` (None / {"mode": "none"} = none). A `moments` spec without the
    timeline's windows (an override) gets them worked out from the content's scenes."""
    spec = ws.parse(tl.get("watermark") if override is _UNSET else override, strict=False)
    if not spec or spec["mode"] == "none":
        return None
    if spec.get("mode") == "videomk" and spec.get("presence") == "moments" and "windows" not in spec:
        spec = {**spec, "windows": ws.moments(tl["scenes"], float(tl["duration"]), 0.0)}
    return spec


def export(tl: Dict[str, Any], master: str, audio: Optional[str], out_mp4: str, *, draft: bool = False, image_loader: Any = None, spec_override: Any = _UNSET, tmp: Optional[str] = None) -> Dict[str, Any]:
    """Master (watermark-free) -> the video to deliver, at `out_mp4`. Returns {"watermark": spec or None, "end_card": bool, "duration": content seconds}. With no watermark the master is copied
    as it is. `audio`: the mix the master was muxed with (needed only to pad it for the card)."""
    spec = spec_of(tl, spec_override)
    info = {"watermark": spec, "end_card": False, "duration": float(tl["duration"])}
    own = tmp is None
    work = tempfile.mkdtemp(prefix="final_") if own else tmp
    try:
        size = output_size(tl, draft)
        fr = tl.get("frame")
        frame = Frame.parse(fr.get("aspect"), fr.get("resolution")) if isinstance(fr, dict) and fr.get("aspect") else Frame.from_size(int(tl.get("width", 1920)), int(tl.get("height", 1080)))
        art = wm_mod.build(spec, frame, size, bool(tl.get("captions", True)), image_loader) if spec else None
        card = bool(art is not None and spec and spec.get("mode") == "videomk" and spec.get("end_card"))
        if art is None:
            if out_mp4 != master:
                shutil.copyfile(master, out_mp4)
            return info
        body = os.path.join(work, "final_body.ts")
        draw_mark(master, body, tl, spec, art, size, draft, work)
        if not card:
            media.mux_final([body], audio, out_mp4, fps=int(tl.get("fps") or 30))
            return info
        tail = os.path.join(work, "final_card.ts")
        render_end_card(tl, tail, draft, image_loader)
        padded = None
        if audio:
            padded = os.path.join(work, "final_audio.m4a")
            pad_audio(audio, padded, ws.END_CARD_S)
        media.mux_final([body, tail], padded, out_mp4, fps=int(tl.get("fps") or 30))
        info["end_card"] = True
        return info
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)
