"""The watermark: its options and where it sits. Dependency-free (no Pillow), like frame.py, so the launcher, the API and the renderer all import it (docs/WATERMARK.md).

Options (one dict, the same in the request, the profile, the plan and the timeline):
  mode      'none' | 'videomk' (the videomk mark, for everyone) | 'custom' (the person's own logo, premium)
  position  'auto' | 'tl' | 'tr' | 'bl' | 'br'      auto = the quiet corner of the shape (below)
  opacity   0.2 .. 1.0 (default 0.65)
  size      'small' (mark height 5 % of the short side) | 'medium' (7 %)
  style     'mark' (default) | 'lockup' (mark plus the word 'videomk')       only for mode 'videomk'
  end_card  true | false (default false)                                      only for mode 'videomk': 2.4 s 'Made with VideoMK' card after the last scene
  presence  'always' (there for the whole video) | 'moments' (fades in for about 4 s near the start and about every 30 s, see `moments`)   only for mode 'videomk'

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
SIZES: Dict[str, float] = {"small": 0.075, "medium": 0.100}   # the mark alone (and a custom logo): its height as a share of the frame's short side (2026-11-28: was 0.05 / 0.07, too small to read)
LOCKUP_W: Dict[str, float] = {"small": 0.26, "medium": 0.34}  # the videomk lockup (mark + the word): its WIDTH as a share of the short side: 281 design px (small) of a 1080 short side; the word's capitals are then 34 design px (22 px at 720p)
CAPTION_LIFT = 40            # 16:9 with the mark in a bottom corner: the captions sit this many design units higher, leaving a band under them for the mark
STYLES = ("mark", "lockup")
PRESENCES = ("always", "moments")
KEYS = {"mode", "position", "opacity", "size", "style", "end_card", "presence"}
# presence 'moments': the mark comes and goes. All times in seconds.
MOMENT_FADE_S = 0.6          # eased fade in and fade out
MOMENT_HOLD_S = 4.0          # fully visible between the fades
MOMENT_FIRST_S = 1.2         # the first appearance starts fading in here: never over the first second of the opening
MOMENT_EVERY_S = 30.0        # about one appearance every 30 s
MOMENT_SNAP_S = 8.0          # ... moved to the nearest scene change within this distance
MOMENT_MIN_GAP_S = 12.0      # between the end of one appearance and the start of the next
MOMENT_END_CLEAR_S = 1.0     # the last appearance is gone this long before the closing card or the final fade
# a scene whose point is a number landing or a ranking settling: the mark does not arrive at its start
EMPHASIS_SCENES = frozenset({"counter", "stat", "bar_race", "pie", "chart", "ranking", "scale_compare"})
DEFAULT_OPACITY = 0.9
OPACITY_MIN, OPACITY_MAX = 0.2, 1.0
MARGIN = 0.035           # of the short side
MARGIN_MIN = 0.020
SHRINK_STEPS = (1.0, 0.85, 0.7, 0.6)
GAP = 10.0               # design units kept clear of a protected zone
CONTENT_GAP = 18.0       # design units between a top-corner mark and the first line of the scene under it
FADE_IN_S = 0.6
END_CARD_S = 2.4
MAX_LOGO_RATIO = 4.3     # the widest a custom logo may be drawn, as a multiple of the mark height (a lockup-shaped logo: as wide as the VideoMK lockup, 4.27)
MARK_RATIO = 1120 / 1024     # width / height of assets/watermark/mark.png (the play and two stars, 2026-11-27)
LOCKUP_RATIO = 4369 / 1024   # and of lockup.png (the mark, then "VideoMK" in Inter)

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
    if strict and set(raw) - KEYS:
        raise WatermarkError("unknown watermark option: " + ", ".join(sorted(set(raw) - KEYS)))
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
        pres = raw.get("presence")
        if pres is not None and pres not in PRESENCES:
            if strict:
                raise WatermarkError("'presence' must be one of: " + ", ".join(PRESENCES))
            pres = None
        if pres is not None:   # absent stays absent: the policy decides the default (watermark_store.resolve); a video without it is 'always', as before the option existed
            out["presence"] = pres
        if not strict and pres == "moments" and isinstance(raw.get("windows"), list):   # server-written by the timeline: when the mark is on screen
            out["windows"] = clean_windows(raw["windows"])
    elif strict and raw.get("presence") is not None:
        raise WatermarkError("'presence' is only for the VideoMK watermark")
    if not strict:   # server-written fields of a stored spec (the custom logo's file in the video's own folder, its content hash)
        if mode == "custom" and isinstance(raw.get("asset"), str):
            out["asset"] = raw["asset"]
            if isinstance(raw.get("hash"), str):
                out["hash"] = raw["hash"][:40]
    return out


# ----------------------------------------------------------------------------- presence 'moments': when the mark is on screen
def clean_windows(raw: Any) -> List[List[float]]:
    out: List[List[float]] = []
    for w in raw if isinstance(raw, list) else []:
        try:
            a, b = float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError):
            continue
        if b > a:
            out.append([round(a, 3), round(b, 3)])
    return out[:64]


def moments(scenes: List[Dict[str, Any]], total: float, end_card_s: float = 0.0, outro_fade_s: float = 0.7) -> List[List[float]]:
    """The appearances of a 'moments' mark for a whole video: [[start, end], ...] in video seconds, each MOMENT_FADE_S in + MOMENT_HOLD_S + MOMENT_FADE_S out.
    A pure function of the timeline, so every render chunk agrees. The first one starts after the first second of the opening; then about one every 30 s, moved
    to the nearest scene change within 8 s whose scene is not an emphasis scene (a counter landing, a chart building): the mark arrives with the new picture, not
    in the middle of a point. None overlaps the closing card or the final fade; they keep at least 12 s apart. A video too short for one gets none (the closing
    card, when it has one, carries the name)."""
    span = MOMENT_HOLD_S + 2 * MOMENT_FADE_S
    limit = float(total) - max(float(end_card_s), float(outro_fade_s)) - MOMENT_END_CLEAR_S   # everything must have left by here
    if limit - MOMENT_FIRST_S < span:
        return []
    starts = sorted(float(sc.get("start", 0.0)) for sc in scenes)
    calm = sorted(float(sc.get("start", 0.0)) for sc in scenes if sc.get("type") not in EMPHASIS_SCENES and not sc.get("silent"))
    out: List[List[float]] = [[MOMENT_FIRST_S, MOMENT_FIRST_S + span]]
    k = 1
    while True:
        target = k * MOMENT_EVERY_S
        k += 1
        if target + span > limit + MOMENT_SNAP_S:
            break
        near = [x for x in calm if abs(x - target) <= MOMENT_SNAP_S]
        t = min(near, key=lambda x: (abs(x - target), x)) + 0.3 if near else target   # 0.3 s into the new scene: after its crossfade has begun
        if not near:   # no calm scene change nearby: if the plain time falls inside an emphasis scene, wait for the next calm scene
            inside = [sc for sc in scenes if float(sc.get("start", 0)) <= t < float(sc.get("start", 0)) + float(sc.get("duration", 0)) and sc.get("type") in EMPHASIS_SCENES]
            if inside:
                later = [x for x in calm if x >= float(inside[0]["start"]) + float(inside[0]["duration"]) - 1e-6]
                if not later:
                    continue
                t = later[0] + 0.3
        if t + span > limit or t - out[-1][1] < MOMENT_MIN_GAP_S:
            continue
        out.append([t, t + span])
    del starts
    return [[round(a, 3), round(b, 3)] for a, b in out]


def moment_alpha(windows: Any, t: float) -> float:
    """0..1: how visible a 'moments' mark is at time t (an eased ramp at both ends of each appearance)."""
    for a, b in windows or []:
        if a <= t <= b:
            u = min((t - a) / MOMENT_FADE_S, (b - t) / MOMENT_FADE_S, 1.0)
            u = max(0.0, u)
            return u * u * (3 - 2 * u)
    return 0.0


def shift_windows(windows: Any, base: float, duration: float) -> List[List[float]]:
    """The appearances as a render chunk sees them: times relative to the chunk's start, only those that touch it (with a little room for the crossfade before it)."""
    out = []
    for a, b in windows or []:
        if b - base >= -1.0 and a - base <= duration + 1.0:
            out.append([round(a - base, 3), round(b - base, 3)])
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
    short = float(min(frame.W, frame.H))
    if spec.get("mode") == "videomk" and spec.get("style") == "lockup":
        w = LOCKUP_W.get(spec.get("size", "small"), LOCKUP_W["small"]) * short
        return w, w / ratio
    h = SIZES.get(spec.get("size", "small"), SIZES["small"]) * short
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
        lift = CAPTION_LIFT if frame.landscape and candidate in ("bl", "br") else 0   # 16:9: the captions rise for a mark under them
        zones: List[Rect] = ([caption_rect(frame.with_cap_lift(lift))] if captions else []) + ([credit_rect(frame)] if candidate == "tr" else [])
        for m in margins:
            rect = _corner(candidate, area, w0 * s, h0 * s, m)
            if not any(intersects(rect, z, GAP) for z in zones):
                return {"rect": rect, "position": candidate, "scale": s, "moved": candidate != pos, "cap_lift": lift if captions else 0}
    return {"rect": _corner(pos, area, w0 * SHRINK_STEPS[-1], h0 * SHRINK_STEPS[-1], margins[-1]), "position": pos, "scale": SHRINK_STEPS[-1], "moved": False, "overlaps": True, "cap_lift": 0}
