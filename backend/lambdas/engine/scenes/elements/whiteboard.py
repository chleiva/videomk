"""`whiteboard`: one board of marker drawings and handwriting that appear along a pen path as the narrator names them (docs/WHITEBOARD.md).

The director writes ITEMS (what to draw from the library, what to write, arrows, emphasis marks), a zone for each and the narration word each is tied to; never
coordinates. Layout, timing and camera are computed (engine/whiteboard/spec.py). HIDDEN from the ordinary scene list: the planner learns about it only from the
whiteboard policy's prompt block (engine/whiteboard_policy.py), when the look is on for the video.

Rendering is a pure function of the scene-local time, so chunks agree with each other. The board is built once per container for a scene (about half a second
at 1080p) and kept while its frames are drawn. A drawing that cannot be fetched is written as a boxed label; a board that cannot be built at all shows its
written items as a plain card: a render never fails for this scene.
"""
import os
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from ...canvas import Canvas
from ...theme import Theme
from ..base import SceneCtx
from ..registry import Element

ZONES = ("top-left", "top", "top-right", "left", "centre", "right", "bottom-left", "bottom", "bottom-right")
SPANS = ("top-row", "middle-row", "bottom-row", "left-col", "centre-col", "right-col", "full", "top-left-wide", "top-right-wide", "left-wide", "right-wide", "bottom-left-wide",
         "bottom-right-wide", "left-tall", "right-tall", "left-low", "right-low", "upper", "lower")
SIZES = ("xs", "s", "m", "l", "xl")
INKS = ("black", "blue", "red", "orange", "green", "purple", "grey")
CONNECT = ("arrow", "wavy", "dashed", "line")
MARKS = ("underline", "double_underline", "circle", "box", "tick", "cross", "cross_out", "highlight")
SIDES = ("below", "above", "left", "right", "over")
MAX_ITEMS, MAX_SOLID, MIN_SOLID = 20, 9, 1
CHARTS = ("bars", "line")
MAX_BARS = 6
MAX_TEXT = 70
LEAD_IN_S = 0.15          # engine/sync.py puts a cue this long before its word; the board wants the word itself
_ID = re.compile(r"[^a-z0-9_]")
_STATE: Dict[str, Any] = {}      # one built board per container: {"key", "board", "cam"} (a board at 4K is a few hundred MB: never two)


def _clean_text(v: Any, n: int = MAX_TEXT) -> str:
    return " ".join(str(v or "").split())[:n]


def _sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    """Director items -> clean items. Unknown drawings become written labels (by exact name first, then by meaning, see engine/whiteboard/library.py);
    items that point at nothing are dropped; a board with nothing on it is refused (the beat then falls back to an ordinary scene)."""
    from ...whiteboard import library

    raw = (props or {}).get("items")
    if not isinstance(raw, list):
        raise ValueError("whiteboard needs items")
    out: List[Dict[str, Any]] = []
    ids: set = set()
    used_zones: Dict[str, int] = {}
    solid = 0
    for k, it in enumerate(raw[:MAX_ITEMS * 2]):
        if not isinstance(it, dict) or len(out) >= MAX_ITEMS:
            continue
        iid = _ID.sub("", str(it.get("id") or f"i{k}").lower())[:24] or f"i{k}"
        if iid in ids:
            iid = f"{iid}_{k}"
        o: Dict[str, Any] = {"id": iid}
        say = _clean_text(it.get("say"), 40)
        if it.get("chart") and not (it.get("draw") or it.get("write")):
            vals = [float(v) for v in (it.get("values") or []) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e12][:MAX_BARS]
            if len(vals) < 2 or solid >= MAX_SOLID or max(vals) <= 0 or min(vals) < 0:
                continue
            labels = [_clean_text(x, 14) for x in (it.get("labels") if isinstance(it.get("labels"), list) else [])][:len(vals)]
            o.update(chart=it["chart"] if it["chart"] in CHARTS else "bars", values=vals, labels=labels + [""] * (len(vals) - len(labels)))
            zone = it.get("zone") if it.get("zone") in ZONES + SPANS else None
            if zone is None or used_zones.get(zone):
                zone = next((z for z in ("centre", "right", "left", "bottom", "top") if not used_zones.get(z)), "centre")
            used_zones[zone] = used_zones.get(zone, 0) + 1
            o["zone"] = zone
            if it.get("color") in INKS:
                o["color"] = it["color"]
            if say:
                o["say"] = say
            solid += 1
        elif it.get("draw") or it.get("write"):
            if solid >= MAX_SOLID:
                continue
            if it.get("draw"):
                name = _clean_text(it.get("draw"), 48)
                oid = name if library.has(name) else library.by_name(name)
                guess = None
                if oid is None:
                    hit = library.search(name, 1)
                    oid = hit[0]["id"] if hit else None
                    guess = hit[0]["score"] if hit else None
                if oid is not None:
                    o["draw"] = oid
                    if guess is not None and os.environ.get("CLIPS_ON_DEMAND") == "1":   # found by MEANING only (a honeycomb can come back as a cheese): remembered, so the
                        o["asked"], o["match"] = name.replace("_", " ")[:28], guess    # drawing itself can be made on demand (engine/object_ondemand.py). Nothing changes without the flag
                    if it.get("ink") in INKS:
                        o["ink"] = it["ink"]
                    if it.get("fill") is False:
                        o["fill"] = False
                else:                                  # not in the library: its name, written in a box
                    o["write"], o["boxed"] = name.replace("_", " ")[:28], True
                if ("boxed" in o or "asked" in o) and isinstance(it.get("describe"), str):      # what the director says it looks like: sent to the drawer if it is made (engine/object_ondemand.py)
                    text_ = " ".join(re.sub(r"[^A-Za-z ,\-]", " ", it["describe"]).split())[:160]
                    if len(text_.split()) >= 3:
                        o["describe"] = text_
            else:
                text = "\n".join(_clean_text(line) for line in str(it.get("write") or "").split("\n")[:5] if _clean_text(line))
                if not text:
                    continue
                o["write"] = text
            if "write" in o:
                for f, allowed in (("hand", ("neat", "casual")), ("tool", ("pen", "marker")), ("ink", INKS), ("align", ("left", "center"))):
                    if it.get(f) in allowed:
                        o[f] = it[f]
            near = _ID.sub("", str(it.get("near") or "").lower())
            if near and near in ids:
                o["near"] = near
                o["side"] = it.get("side") if it.get("side") in SIDES[:4] else ("below" if "write" in o else "right")
            else:
                zone = it.get("zone") if it.get("zone") in ZONES + SPANS else None
                if zone is None or ("draw" in o and used_zones.get(zone, 0) >= 2):
                    zone = next((z for z in ("centre", "left", "right", "top", "bottom", "top-left", "top-right", "bottom-left", "bottom-right") if not used_zones.get(z)), "centre")
                used_zones[zone] = used_zones.get(zone, 0) + 1
                o["zone"] = zone
            o["size"] = it.get("size") if it.get("size") in SIZES else ("l" if "draw" in o and "near" not in o else ("xs" if "draw" in o else "m"))
            if say:
                o["say"] = say
            elif "write" in o:
                o["say"] = o["write"].split("\n")[0].split(" ")[-1][:40]      # a written line lands as its last word is said, when the narration says it
            solid += 1
        elif it.get("connect"):
            a, b = _ID.sub("", str(it.get("from") or "").lower()), _ID.sub("", str(it.get("to") or "").lower())
            if a not in ids or b not in ids or a == b:
                continue
            o.update(connect=it["connect"] if it["connect"] in CONNECT else "arrow", **{"from": a, "to": b})
            if it.get("color") in INKS:
                o["color"] = it["color"]
            if say:
                o["say"] = say
        elif it.get("mark"):
            on = _ID.sub("", str(it.get("on") or "").lower())
            if on not in ids or it["mark"] not in MARKS:
                continue
            o.update(mark=it["mark"], on=on)
            if isinstance(it.get("word"), str) and it["word"].strip():
                o["word"] = _clean_text(it["word"], 30)
            if it.get("color") in INKS or (it["mark"] == "highlight" and it.get("color") in ("yellow", "green", "pink", "orange")):
                o["color"] = it["color"]
            if it.get("side") in SIDES:
                o["side"] = it["side"]
            if say:
                o["say"] = say
        else:
            continue
        ids.add(iid)
        out.append(o)
    if solid < MIN_SOLID:
        raise ValueError("whiteboard has nothing to draw or write")
    clean: Dict[str, Any] = {"items": out}
    if (props or {}).get("board") == "same":                  # this beat goes on drawing on the previous beat's board (engine/whiteboard_policy.compose decides if it may)
        clean["board"] = "same"
    for f, allowed in (("hand", ("neat", "casual")), ("tool", ("pen", "marker"))):
        if (props or {}).get(f) in allowed:
            clean[f] = props[f]
    return clean


def _anchors(props: Dict[str, Any]) -> List[str]:
    return [it["say"] for it in props.get("items", []) if it.get("say")]


def _cues(props: Dict[str, Any], dur: float) -> List[float]:
    cues = props.get("cues")
    if isinstance(cues, list) and cues:
        return [float(c) for c in cues]
    n = len(_anchors(props))
    return [round(dur * (0.1 + 0.7 * k / max(1, n - 1)), 3) for k in range(n)]


BOARD_K = 1.5
PAN_S = 0.8               # the camera's move from the previous board to this one, at the start of the first scene of a board
WALL_S = 3.8              # the last scene's final pull-back over every board: 1.5 s of travel, then held clear of the 1.4 s closing fade
WALL_SHORT_S = 1.8        # ... when the boards would be too small to read in one picture: the video ends on the last board and only glances at the whole
WALL_LEGIBLE = 4          # at most this many boards are shown together as a picture to read (a 2x2 grid: each at half size)
WALL_MAX = 9
_STILLS: Dict[str, Image.Image] = {}     # the finished pictures of other panels (the previous one for the pan, all of them for the last pull-back): small, at most WALL_MAX + 1


def geometry(ctx: SceneCtx, w: int, h: int) -> Dict[str, Any]:
    """The board for this frame: the content box (above the captions, below a top watermark band) becomes the board, the rest of the frame is paper around it.
    The board is BOARD_K design units wide per design unit of the box: smaller than the standalone demos' 2.0, because the whole board is the picture (one
    framing per board, no close views): drawings and writing must be a good size seen whole."""
    fr = ctx.frame
    x0, y0, x1, y1 = ctx.box
    bw, bh = float(x1 - x0), float(y1 - y0)
    ppd = w / float(fr.W)                                  # real pixels per design unit
    k = BOARD_K
    from ...whiteboard import spec

    # one raster pixel per output pixel when the framing is at its closest (a board that is not full is enlarged up to spec.MAX_ZOOM); never finer than that
    return {"units": (k * bw, k * bh), "scale": spec.MAX_ZOOM / k * ppd, "pad": (k * x0, k * y0, k * (fr.W - x1), k * (fr.H - y1)),
            "box": (x0, y0, bw, bh), "frame": (float(fr.W), float(fr.H))}


def full_view(view: Tuple[float, float, float], geo: Dict[str, Any]) -> Tuple[float, float, float]:
    """A camera view of the content -> the window of the whole frame that shows it inside the content box."""
    vx, vy, vw = view
    x0, y0, bw, bh = geo["box"]
    vh = vw * bh / bw
    return (vx - vw * x0 / bw, vy - vh * y0 / bh, vw * geo["frame"][0] / bw)


def _tail(props: Dict[str, Any], dur: float) -> float:
    """Seconds kept at the end of the LAST scene of a run for the pull-back over the whole big board (short when there are too many boards to read together)."""
    if not props.get("wall"):
        return 0.0
    return min(WALL_S if len(props["wall"]) + 1 <= WALL_LEGIBLE else WALL_SHORT_S, max(0.0, dur - 5.0))


def board_items(props: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Everything on this scene's board, in drawing order -> (items, ids earlier scenes of the board already drew, ids later scenes will draw)."""
    before, after = list(props.get("before") or []), list(props.get("after") or [])
    return before + list(props["items"]) + after, [it["id"] for it in before], [it["id"] for it in after]


def build(props: Dict[str, Any], dur: float, ctx: SceneCtx, w: int, h: int, *, load=None, layout_only: bool = False, tidy: bool = True):
    from ...whiteboard import library, spec

    geo = geometry(ctx, w, h)
    cues = _cues(props, dur)
    anchors, k = {}, 0
    for it in props["items"]:
        if it.get("say"):
            if k < len(cues):
                anchors[it["id"]] = float(cues[k]) + LEAD_IN_S
            k += 1
        elif isinstance(it.get("at"), (int, float)):        # a mark the engine added at a fixed time of the scene (whiteboard_policy.fill_rests)
            anchors[it["id"]] = float(it["at"])
    items, done, hidden = board_items(props)
    board, cam, report = spec.compile_board(items, anchors, dur, geo["units"], geo["scale"], load or library.load, hand=props.get("hand", "neat"), tool=props.get("tool", "marker"),
                                            pad=geo["pad"], frame_aspect=geo["box"][2] / geo["box"][3], tail=_tail(props, dur), done=done, hidden=hidden,
                                            t_min=PAN_S + 0.1 if props.get("prev") else (0.05 if props.get("before") else 0.3), layout_only=layout_only, tidy=tidy)
    return board, cam, geo, report


def grid(n: int, portrait: bool = False) -> Tuple[int, int]:
    """The big board: `n` panels, row by row -> (columns, rows). Two panels of a tall frame are one above the other."""
    import math

    if n == 2 and portrait:
        return 1, 2
    cols = max(1, int(math.ceil(math.sqrt(n))))
    return cols, int(math.ceil(n / cols))


def _portrait(ctx: SceneCtx) -> bool:
    return ctx.frame.H > ctx.frame.W * 1.1


def _still(lite: Dict[str, Any], ctx: SceneCtx, w: int, h: int) -> Image.Image:
    """Another panel of the big board, finished: its items laid out exactly as its own scene lays them out (layout does not depend on timing)."""
    key = hashlib.sha1(json.dumps([lite, w, h, ctx.frame.aspect, ctx.frame.top_inset, bool(ctx.captions)], sort_keys=True, default=str).encode()).hexdigest()
    im = _STILLS.get(key)
    if im is None:
        try:
            board, cam, geo, _ = build({"items": lite["items"], **{f: lite[f] for f in ("hand", "tool") if f in lite}}, 1e6, ctx, w, h)
            im = board.frame(1e6 - 1.0, full_view(cam.at(1e6), geo), (w, h), tip=False)
            del board
        except Exception as e:  # noqa: BLE001 - a neighbour that cannot be drawn is blank paper, never a failed frame
            print(f"WHITEBOARD_STILL_FAILED {type(e).__name__}: {str(e)[:200]}")
            from ...whiteboard import board as bd

            im = Image.new("RGB", (w, h), bd.PAPER)
        if len(_STILLS) > WALL_MAX:
            _STILLS.pop(next(iter(_STILLS)))
        _STILLS[key] = im
    return im


def _pan(frame: Image.Image, props: Dict[str, Any], lt: float, ctx: SceneCtx) -> Image.Image:
    """The first moments of a scene that continues a big board: the camera travels from the previous panel (finished) to this one (still empty)."""
    from ...whiteboard import board as bd

    w, h = frame.size
    u = bd.ease(lt / PAN_S)
    k, n = (list(props.get("panel") or [1, 2]) + [2])[:2]
    cols = grid(min(int(n), WALL_MAX), _portrait(ctx))[0]
    dx, dy = ((-1, 1) if cols > 1 else (0, 1)) if int(k) % cols == 0 else (1, 0)      # the next panel is to the right; after the end of a row, below and back to the left
    out = Image.new("RGB", (w, h), bd.PAPER)
    out.paste(_still(props["prev"], ctx, w, h), (int(round(-dx * u * w)), int(round(-dy * u * h))))
    out.paste(frame, (int(round(dx * (1 - u) * w)), int(round(dy * (1 - u) * h))))
    return out


WALL_GAP = (0.03, 0.05)       # paper between the boards of the final overview, as shares of the frame's width and height


def wall_views(m: int, cols: int, rows: int, geo_box: Tuple[float, float, float, float], frame_wh: Tuple[float, float]):
    """The final overview as geometry, in frame widths (x) and frame heights (y). The boards' CONTENT boxes tile a wall (the paper margins and the caption band
    of each frame are not repeated between them), and the last view shows the whole wall inside this frame's content box: above the captions, clear of the
    watermark band. -> (origins of every board's frame on the wall, the first view = the last board's frame, the last view); a view is (x, y, width)."""
    fx0, fy0, fw, fh = geo_box[0] / frame_wh[0], geo_box[1] / frame_wh[1], geo_box[2] / frame_wh[0], geo_box[3] / frame_wh[1]
    gx, gy = WALL_GAP
    origins = [((i % cols) * (fw + gx), (i // cols) * (fh + gy)) for i in range(m)]
    gw, gh = cols * fw + (cols - 1) * gx, rows * fh + (rows - 1) * gy
    vw = max(gw / fw, gh / fh, 1.0)
    end = (fx0 + gw / 2 - (fx0 + fw / 2) * vw, fy0 + gh / 2 - (fy0 + fh / 2) * vw, vw)
    return origins, (origins[m - 1][0], origins[m - 1][1], 1.0), end


def _wall(frame: Image.Image, props: Dict[str, Any], u: float, ctx: SceneCtx) -> Image.Image:
    """The end of the last scene: the camera pulls back from this board until every board is in the picture, side by side like one large whiteboard."""
    from ...whiteboard import board as bd

    w, h = frame.size
    others = list(props["wall"])[-(WALL_MAX - 1):]
    m = len(others) + 1
    cols, rows = grid(m, _portrait(ctx))
    fr = ctx.frame
    x0, y0, x1, y1 = ctx.box
    box = (float(x0), float(y0), float(x1 - x0), float(y1 - y0))
    origins, first, end = wall_views(m, cols, rows, box, (float(fr.W), float(fr.H)))
    u = bd.ease(u)
    g = end[2]
    vw = float(g ** u)                                       # zoom eased in log space, like the board's own camera
    f = (vw - 1.0) / (g - 1.0) if g > 1 else 1.0
    vx, vy = first[0] + (end[0] - first[0]) * f, first[1] + (end[1] - first[1]) * f
    out = Image.new("RGB", (w, h), bd.PAPER)
    k = 1.0 / vw                                             # output frames per wall unit
    ox, oy = origins[m - 1]
    lw, lh = max(1, int(round(w * k))), max(1, int(round(h * k)))
    out.paste(frame if (lw, lh) == (w, h) else frame.resize((lw, lh), Image.BILINEAR, reducing_gap=2.0), (int(round((ox - vx) * k * w)), int(round((oy - vy) * k * h))))
    sw, sh = max(2, int(round(w * min(1.0, 2.0 / g)))), max(2, int(round(h * min(1.0, 2.0 / g))))      # the other boards are only ever seen small
    pad = 0.012
    cx0, cy0, cx1, cy1 = box[0] / fr.W - pad, box[1] / fr.H - pad, (box[0] + box[2]) / fr.W + pad, (box[1] + box[3]) / fr.H + pad      # a board's content box, in shares of its frame
    for i in range(m - 1):
        ox, oy = origins[i]
        dst = (int(round((ox + cx0 - vx) * k * w)), int(round((oy + cy0 - vy) * k * h)), int(round((ox + cx1 - vx) * k * w)), int(round((oy + cy1 - vy) * k * h)))
        if dst[0] >= w or dst[1] >= h or dst[2] <= 0 or dst[3] <= 0 or dst[2] - dst[0] < 2 or dst[3] - dst[1] < 2:
            continue
        still = _still(others[i], ctx, sw, sh)
        crop = still.crop((int(round(cx0 * sw)), int(round(cy0 * sh)), int(round(cx1 * sw)), int(round(cy1 * sh))))
        out.paste(crop.resize((dst[2] - dst[0], dst[3] - dst[1]), Image.BILINEAR, reducing_gap=2.0), dst[:2])
    return out


def _draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, theme: Theme, ctx: SceneCtx) -> None:
    # The finished picture is the canvas at half its pixel size (the renderer reduces 2x; a draft has no supersampling and is reduced afterwards): the board is
    # drawn at that size and pasted doubled with NEAREST.
    w, h = max(2, cv.im.width // 2), max(2, cv.im.height // 2)
    lt = max(0.0, lt)
    core_props = {k: v for k, v in props.items() if k not in ("prev", "wall", "panel")}
    key = hashlib.sha1(json.dumps([core_props, len(props.get("wall") or []), bool(props.get("prev")), round(dur, 3), w, h, ctx.frame.aspect, ctx.frame.top_inset, bool(ctx.captions)], sort_keys=True, default=str).encode()).hexdigest()
    try:
        if _STATE.get("key") != key:
            _STATE.clear()
            board, cam, geo, _ = build(props, dur, ctx, w, h)
            _STATE.update(key=key, board=board, cam=cam, geo=geo)
        st = _STATE
        tail = _tail(props, dur)
        t_board = min(lt, dur - tail) if tail else lt          # during the last pull-back this panel is finished and still
        frame = st["board"].frame(t_board, full_view(st["cam"].at(t_board), st["geo"]), (w, h))
        if props.get("prev") and lt < PAN_S:
            frame = _pan(frame, props, lt, ctx)
        elif tail and lt > dur - tail:
            frame = _wall(frame, props, (lt - (dur - tail)) / max(min(1.5, tail - 0.3), 0.2), ctx)
    except Exception as e:  # noqa: BLE001 - never a failed render for a picture
        print(f"WHITEBOARD_DRAW_FAILED {type(e).__name__}: {str(e)[:200]}")
        _STATE.clear()
        _STATE["key"] = None
        _card(cv, props, lt, theme, ctx)
        return
    cv.im.paste(frame.resize(cv.im.size, Image.NEAREST), (0, 0))


def _card(cv: Canvas, props: Dict[str, Any], lt: float, theme: Theme, ctx: SceneCtx) -> None:
    cv.background(theme, lt)
    text = next((it["write"].split("\n")[0] for it in props.get("items", []) if it.get("write")), "")
    if text:
        fr = ctx.frame
        cv.text(fr.W / 2, fr.H / 2, text[:40], "semibold", 56, (*theme.text[:3], 255), anchor="mm")


def _fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    text = next((it["write"].split("\n")[0] for it in props.get("items", []) if it.get("write")), "")
    return "title", {"title": text[:60] or " "}


ELEMENTS = [
    Element(
        name="whiteboard", family="Media",
        doc="- whiteboard: {items: [...]}. A hand-drawn board. Offered to the director only by the whiteboard policy.",
        sanitize=_sanitize, draw=_draw, cues=_cues, anchors=_anchors, fallback=_fallback,
        samples=[
            {"items": [{"id": "title", "write": "How plants eat light", "zone": "top", "say": "light"}, {"id": "sun", "draw": "sun", "zone": "left", "say": "sun"},
                       {"id": "plant", "draw": "plant_sprout", "zone": "centre", "size": "l", "say": "leaves"}, {"id": "ray", "connect": "dashed", "from": "sun", "to": "plant", "color": "orange"},
                       {"id": "sugar", "write": "sugar", "zone": "right", "ink": "orange", "say": "sugar"}, {"id": "ring", "mark": "circle", "on": "sugar", "color": "red"}]},
            {"items": [{"id": "t", "write": "Three habits", "zone": "top", "say": "habits"}, {"id": "l", "write": "1. Start early\n2. Add a little\n3. Wait", "zone": "left-wide", "tool": "pen", "say": "wait"},
                       {"id": "pig", "draw": "piggy_bank", "zone": "right", "say": "save"}, {"id": "u", "mark": "underline", "on": "t", "color": "red"}]},
        ],
        formats=("16:9", "9:16", "1:1", "4:5"),
        hidden=True, min_seconds=4.0,
    )
]
