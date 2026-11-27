"""`whiteboard`: one board of marker drawings and handwriting that appear along a pen path as the narrator names them (docs/WHITEBOARD.md).

The director writes ITEMS (what to draw from the library, what to write, arrows, emphasis marks), a zone for each and the narration word each is tied to; never
coordinates. Layout, timing and camera are computed (engine/whiteboard/spec.py). HIDDEN from the ordinary scene list: the planner learns about it only from the
whiteboard policy's prompt block (engine/whiteboard_policy.py), when the look is on for the video.

Rendering is a pure function of the scene-local time, so chunks agree with each other. The board is built once per container for a scene (about half a second
at 1080p) and kept while its frames are drawn. A drawing that cannot be fetched is written as a boxed label; a board that cannot be built at all shows its
written items as a plain card: a render never fails for this scene.
"""
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
MAX_ITEMS, MAX_SOLID, MIN_SOLID = 16, 9, 1
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
                if oid is None:
                    hit = library.search(name, 1)
                    oid = hit[0]["id"] if hit else None
                if oid is not None:
                    o["draw"] = oid
                    if it.get("ink") in INKS:
                        o["ink"] = it["ink"]
                    if it.get("fill") is False:
                        o["fill"] = False
                else:                                  # not in the library: its name, written in a box
                    o["write"], o["boxed"] = name.replace("_", " ")[:28], True
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
PAN_S = 0.8               # the camera's move from the previous panel of the big board to this one, at the start of a scene
WALL_S = 3.0              # the last scene's final pull-back over every panel of the big board
WALL_MAX = 9
_STILLS: Dict[str, Image.Image] = {}     # the finished pictures of other panels (the previous one for the pan, all of them for the last pull-back): small, at most WALL_MAX + 1


def geometry(ctx: SceneCtx, w: int, h: int) -> Dict[str, Any]:
    """The board for this frame: the content box (above the captions, below a top watermark band) becomes the board, the rest of the frame is paper around it.
    The board is BOARD_K design units wide per design unit of the box: smaller than the standalone demos' 2.0, so that drawings and writing are still a good
    size when the camera has pulled back to the whole board (looked at on the first local video: at 2.0 a finished board was mostly white). The close view
    (2x2 of the 3x3 zones) is one raster pixel per output pixel."""
    fr = ctx.frame
    x0, y0, x1, y1 = ctx.box
    bw, bh = float(x1 - x0), float(y1 - y0)
    ppd = w / float(fr.W)                                  # real pixels per design unit
    k = BOARD_K
    return {"units": (k * bw, k * bh), "scale": 1.5 / k * ppd, "pad": (k * x0, k * y0, k * (fr.W - x1), k * (fr.H - y1)),
            "box": (x0, y0, bw, bh), "frame": (float(fr.W), float(fr.H))}


def full_view(view: Tuple[float, float, float], geo: Dict[str, Any]) -> Tuple[float, float, float]:
    """A camera view of the content -> the window of the whole frame that shows it inside the content box."""
    vx, vy, vw = view
    x0, y0, bw, bh = geo["box"]
    vh = vw * bh / bw
    return (vx - vw * x0 / bw, vy - vh * y0 / bh, vw * geo["frame"][0] / bw)


def _tail(props: Dict[str, Any], dur: float) -> float:
    """Seconds kept at the end of the LAST scene of a run for the pull-back over the whole big board."""
    return min(WALL_S, max(0.0, dur - 5.0)) if props.get("wall") else 0.0


def build(props: Dict[str, Any], dur: float, ctx: SceneCtx, w: int, h: int):
    from ...whiteboard import library, spec

    geo = geometry(ctx, w, h)
    cues = _cues(props, dur)
    anchors, k = {}, 0
    for it in props["items"]:
        if it.get("say"):
            if k < len(cues):
                anchors[it["id"]] = float(cues[k]) + LEAD_IN_S
            k += 1
    board, cam, report = spec.compile_board(props["items"], anchors, dur, geo["units"], geo["scale"], library.load, hand=props.get("hand", "neat"), tool=props.get("tool", "marker"),
                                            pad=geo["pad"], frame_aspect=geo["box"][2] / geo["box"][3], tail=_tail(props, dur))
    return board, cam, geo, report


def grid(n: int) -> Tuple[int, int]:
    """The big board: `n` panels, row by row -> (columns, rows)."""
    import math

    cols = max(1, int(math.ceil(math.sqrt(n))))
    return cols, int(math.ceil(n / cols))


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
    cols = grid(min(int(n), WALL_MAX))[0]
    dx, dy = ((-1, 1) if cols > 1 else (0, 1)) if int(k) % cols == 0 else (1, 0)      # the next panel is to the right; after the end of a row, below and back to the left
    out = Image.new("RGB", (w, h), bd.PAPER)
    out.paste(_still(props["prev"], ctx, w, h), (int(round(-dx * u * w)), int(round(-dy * u * h))))
    out.paste(frame, (int(round(dx * (1 - u) * w)), int(round(dy * (1 - u) * h))))
    return out


def _wall(frame: Image.Image, props: Dict[str, Any], u: float, ctx: SceneCtx) -> Image.Image:
    """The end of the last scene: the camera pulls back from this panel until every panel of the big board is in the picture."""
    from ...whiteboard import board as bd

    w, h = frame.size
    others = list(props["wall"])[-(WALL_MAX - 1):]
    m = len(others) + 1
    cols, rows = grid(m)
    g = float(max(cols, rows))                               # the final view, in panels: the grid centred in a frame-shaped window
    end = ((cols - g) / 2.0, (rows - g) / 2.0, g)
    c0, r0 = (m - 1) % cols, (m - 1) // cols
    u = bd.ease(u)
    vw = float(g ** u)                                       # zoom eased in log space, like the board's own camera
    f = (vw - 1.0) / (g - 1.0) if g > 1 else 1.0
    vx, vy = c0 + (end[0] - c0) * f, r0 + (end[1] - r0) * f
    out = Image.new("RGB", (w, h), bd.PAPER)
    cw, ch = w / vw, h / vw
    sw, sh = max(2, int(round(w * min(1.0, 2.0 / g)))), max(2, int(round(h * min(1.0, 2.0 / g))))      # the other panels are only ever seen small
    for i in range(m):
        x, y = (i % cols - vx) * cw, (i // cols - vy) * ch
        if x >= w or y >= h or x + cw <= 0 or y + ch <= 0:
            continue
        src = frame if i == m - 1 else _still(others[i], ctx, sw, sh)
        box = (int(round(x)), int(round(y)), int(round(x + cw)), int(round(y + ch)))
        size = (max(1, box[2] - box[0]), max(1, box[3] - box[1]))
        out.paste(src if src.size == size else src.resize(size, Image.BILINEAR, reducing_gap=2.0), box[:2])
    return out


def _draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, theme: Theme, ctx: SceneCtx) -> None:
    # The finished picture is the canvas at half its pixel size (the renderer reduces 2x; a draft has no supersampling and is reduced afterwards): the board is
    # drawn at that size and pasted doubled with NEAREST.
    w, h = max(2, cv.im.width // 2), max(2, cv.im.height // 2)
    lt = max(0.0, lt)
    core_props = {k: v for k, v in props.items() if k not in ("prev", "wall", "panel")}
    key = hashlib.sha1(json.dumps([core_props, bool(props.get("wall")), round(dur, 3), w, h, ctx.frame.aspect, ctx.frame.top_inset, bool(ctx.captions)], sort_keys=True, default=str).encode()).hexdigest()
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
            frame = _wall(frame, props, (lt - (dur - tail)) / max(min(1.6, tail - 0.4), 0.2), ctx)
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
