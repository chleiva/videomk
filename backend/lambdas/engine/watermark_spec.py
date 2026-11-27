"""The watermark: its options and where it sits. Dependency-free (no Pillow), like frame.py, so the launcher, the API and the renderer all import it (docs/WATERMARK.md).

Options (one dict, the same in the request, the profile, the plan and the timeline):
  mode      'none' | 'videomk' (the videomk mark, for everyone) | 'custom' (the person's own logo, premium)
  position  'auto' | 'tl' | 'tr' | 'bl' | 'br'      auto = the quiet corner of the shape (below)
  opacity   0.2 .. 1.0 (default 0.65)
  size      'small' (mark height 5 % of the short side) | 'medium' (7 %)
  style     'mark' (default) | 'lockup' (mark plus the word 'videomk')       only for mode 'videomk'
  end_card  true | false (default false)                                      only for mode 'videomk': 2.4 s 'Made with videomk' card after the last scene

Placement is worked out in DESIGN units (the frame's 1080-short-side canvas) and never covers the captions, the clip credit line or (auto, 9:16) the platform UI zones:
  16:9  bottom right, 3.5 % margin;  9:16  top left under the platform header (TikTok / Reels / Shorts keep the bottom 320 and the right 130 for their own buttons);
  1:1 and 4:5  top left (the captions use almost the whole bottom width).
If the wanted corner would touch a protected zone the mark first takes the smaller margin (2 %), then shrinks (a corner the person chose: down to 60 %; the default corner: to 70 %
and then the other corners are tried at full size), then moves to the next corner.
"""
from typing import Any, Dict, List, Optional, Tuple

from .frame import Frame

MODES = ("none", "videomk", "custom")
POSITIONS = ("auto", "tl", "tr", "bl", "br")
SIZES: Dict[str, float] = {"small": 0.050, "medium": 0.070}   # mark height as a share of the frame's short side
STYLES = ("mark", "lockup")
DEFAULT_OPACITY = 0.65
OPACITY_MIN, OPACITY_MAX = 0.2, 1.0
MARGIN = 0.035           # of the short side
MARGIN_MIN = 0.020
SHRINK_STEPS = (1.0, 0.85, 0.7, 0.6)
GAP = 10.0               # design units kept clear of a protected zone
CONTENT_GAP = 18.0       # design units between a top-corner mark and the first line of the scene under it
FADE_IN_S = 0.6
END_CARD_S = 2.4
MAX_LOGO_RATIO = 6.3     # the widest a custom logo may be drawn, as a multiple of the mark height (the videomk lockup is 6.26)
MARK_RATIO = 1384 / 1024     # width / height of assets/watermark/mark.png
LOCKUP_RATIO = 6407 / 1024   # and of lockup.png

AUTO_POSITION = {"16:9": "br", "1:1": "tl", "4:5": "tl", "9:16": "tl"}   # square and 4:5: the captions take almost the whole bottom width, so the quiet corner is the top left
_OTHERS = {"tl": ("bl", "br", "tr"), "tr": ("br", "bl", "tl"), "bl": ("tl", "tr", "br"), "br": ("tr", "tl", "bl")}
# 9:16: the area free of platform UI (design units: x0, y0, x1, y1): header 162 at the top, the buttons column from x=950, the caption/description band from y=1600
UI_SAFE_TALL = (0.0, 162.0, 950.0, 1600.0)

Rect = Tuple[float, float, float, float]


class WatermarkError(ValueError):
    """An invalid option (a 400 with the message)."""


def _num(v: Any, name: str, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not (lo <= float(v) <= hi):
        raise WatermarkError(f"'{name}' must be a number from {lo:g} to {hi:g}")
    return float(v)


def parse(raw: Any, *, strict: bool = True) -> Optional[Dict[str, Any]]:
    """The cleaned option dict, or None when nothing was given (None / missing). strict (the API): anything invalid raises WatermarkError and unknown keys are refused;
    lenient (rendering older or odd data): invalid values fall back to the defaults. A 'none' mode is returned as {'mode': 'none'} so 'choose no watermark' differs from 'nothing chosen'."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        if strict:
            raise WatermarkError("'watermark' must be an object")
        return None
    if strict and set(raw) - {"mode", "position", "opacity", "size", "style", "end_card"}:
        raise WatermarkError("unknown watermark option: " + ", ".join(sorted(set(raw) - {"mode", "position", "opacity", "size", "style", "end_card"})))
    out: Dict[str, Any] = {}
    mode = raw.get("mode", "videomk")
    if mode not in MODES:
        if strict:
            raise WatermarkError("'mode' must be one of: " + ", ".join(MODES))
        mode = "videomk"
    out["mode"] = mode
    if mode == "none":
        return out
    pos = raw.get("position", "auto")
    if pos not in POSITIONS:
        if strict:
            raise WatermarkError("'position' must be one of: " + ", ".join(POSITIONS))
        pos = "auto"
    out["position"] = pos
    op = raw.get("opacity", DEFAULT_OPACITY)
    try:
        out["opacity"] = round(_num(op, "opacity", OPACITY_MIN, OPACITY_MAX), 3)
    except WatermarkError:
        if strict:
            raise
        out["opacity"] = DEFAULT_OPACITY
    size = raw.get("size", "small")
    if size not in SIZES:
        if strict:
            raise WatermarkError("'size' must be one of: " + ", ".join(SIZES))
        size = "small"
    out["size"] = size
    style = raw.get("style", "mark")
    if style not in STYLES:
        if strict:
            raise WatermarkError("'style' must be one of: " + ", ".join(STYLES))
        style = "mark"
    ec = raw.get("end_card", False)
    if not isinstance(ec, bool):
        if strict:
            raise WatermarkError("'end_card' must be true or false")
        ec = False
    if mode == "videomk":
        out["style"], out["end_card"] = style, ec
    if not strict:   # server-written fields of a stored spec (the custom logo's file in the video's own folder, its content hash)
        if mode == "custom" and isinstance(raw.get("asset"), str):
            out["asset"] = raw["asset"]
            if isinstance(raw.get("hash"), str):
                out["hash"] = raw["hash"][:40]
    return out


# ----------------------------------------------------------------------------- zones and placement
def intersects(a: Rect, b: Rect, gap: float = 0.0) -> bool:
    return a[0] < b[2] + gap and a[2] > b[0] - gap and a[1] < b[3] + gap and a[3] > b[1] - gap


def caption_rect(frame: Frame) -> Rect:
    """The widest box the karaoke captions can occupy (engine/scenes/captions.py): centred in the caption span, as wide as a full line and as tall as the lines it may take."""
    cap = frame.caption
    lines = 3 if frame.landscape else int(cap.get("max_lines", 2))
    pad_x, pad_y = (36, 22) if frame.landscape else (32, 20)
    w = cap["max_w"] + (2 * pad_x if frame.landscape else 0)
    h = lines * cap["size"] * 1.32 + 2 * pad_y
    cx = (cap["x0"] + cap["x1"]) / 2
    return (cx - w / 2, cap["bottom"] - h, cx + w / 2, float(cap["bottom"]))


def credit_rect(frame: Frame) -> Rect:
    """The clip / photo credit line (top right, up to 90 characters)."""
    y = 40 if frame.landscape else max(40, frame.base_margin_top - 30)
    size = 22 if frame.landscape else 26
    return (frame.W - 40 - 720.0, y - 8.0, frame.W - 40.0, y + size + 8.0)


def mark_box(frame: Frame, spec: Dict[str, Any], ratio: float) -> Tuple[float, float]:
    """(w, h) in design units of the mark for this size: height is a share of the short side; a wide logo is limited to MAX_LOGO_RATIO times the height."""
    h = SIZES.get(spec.get("size", "small"), SIZES["small"]) * min(frame.W, frame.H)
    w = h * ratio
    if w > h * MAX_LOGO_RATIO:
        w, h = h * MAX_LOGO_RATIO, h * MAX_LOGO_RATIO / ratio
    return w, h


def ratio_of(spec: Dict[str, Any], logo_ratio: Optional[float] = None) -> float:
    if spec.get("mode") == "custom":
        return float(logo_ratio or 1.0)
    return LOCKUP_RATIO if spec.get("style") == "lockup" else MARK_RATIO


def _corner(pos: str, area: Rect, w: float, h: float, m: float) -> Rect:
    x = area[0] + m if pos in ("tl", "bl") else area[2] - m - w
    y = area[1] + m if pos in ("tl", "tr") else area[3] - m - h
    return (x, y, x + w, y + h)


def content_inset(lay: Dict[str, Any], frame: Frame) -> int:
    """How far the scenes' content box must start lower so a mark in a TOP corner sits in a band of its own instead of on a heading (seen on QA: a 9:16 logo on the
    first letters of a list heading). 0 for a bottom corner (the caption band is already kept clear) and when the mark is above the content anyway."""
    if lay.get("position") not in ("tl", "tr") or frame.landscape:   # 16:9 scenes sit at fixed heights and keep 140 at the sides: the mark alone fits beside them (a wide logo in a chosen top corner can still touch a heading)
        return 0
    need = lay["rect"][3] + CONTENT_GAP - frame.base_margin_top
    return int(max(0, min(frame.design_h // 10, round(need))))


def effective_position(spec: Dict[str, Any], frame: Frame) -> str:
    pos = spec.get("position", "auto")
    return AUTO_POSITION.get(frame.aspect, "br") if pos == "auto" else pos


def layout(spec: Dict[str, Any], frame: Frame, logo_ratio: Optional[float] = None, captions: bool = True) -> Dict[str, Any]:
    """Where the mark goes: {'rect': (x0, y0, x1, y1) in design units, 'position': the corner used, 'scale': 1.0 .. 0.6 of the wanted size, 'moved': True when the other corner was used}.
    Deterministic and pure: the same answer for every frame of the video."""
    pos = effective_position(spec, frame)
    ratio = ratio_of(spec, logo_ratio)
    w0, h0 = mark_box(frame, spec, ratio)
    short = float(min(frame.W, frame.H))
    area: Rect = UI_SAFE_TALL if (spec.get("position", "auto") == "auto" and frame.aspect == "9:16") else (0.0, 0.0, float(frame.W), float(frame.H))
    margins = (MARGIN * short, MARGIN_MIN * short)
    order = [pos] + [c for c in _OTHERS[pos]]   # the wanted corner, then the other three (vertical flip, diagonal, horizontal flip)
    if spec.get("position", "auto") != "auto":   # a corner the person chose is kept as long as the mark can shrink to fit there (down to 60 %), before it moves
        tries = [(pos, s) for s in SHRINK_STEPS] + [(c, s) for c in order[1:] for s in SHRINK_STEPS]
    else:   # the default corner shrinks a little (to 70 %), then the other corners are tried at full size, then smaller
        tries = [(pos, s) for s in SHRINK_STEPS[:3]] + [(c, 1.0) for c in order[1:]] + [(pos, SHRINK_STEPS[3])] + [(c, s) for c in order[1:] for s in SHRINK_STEPS[1:]]
    for candidate, s in tries:
        zones: List[Rect] = ([caption_rect(frame)] if captions else []) + ([credit_rect(frame)] if candidate == "tr" else [])
        for m in margins:
            rect = _corner(candidate, area, w0 * s, h0 * s, m)
            if not any(intersects(rect, z, GAP) for z in zones):
                return {"rect": rect, "position": candidate, "scale": s, "moved": candidate != pos}
    return {"rect": _corner(pos, area, w0 * SHRINK_STEPS[-1], h0 * SHRINK_STEPS[-1], margins[-1]), "position": pos, "scale": SHRINK_STEPS[-1], "moved": False, "overlaps": True}
