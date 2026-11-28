"""`presenter`: a cartoon character stands beside the content and speaks the narration (docs/PRESENTERS.md).

The character is one of the standing presenters (engine/vector_presenter.py: Inés the teacher, David the engineer, Priya the doctor, Mateo the chef, the Fox); its
gestures come from the words it says and when it says them (engine/character_gestures.py), with no model call. Beside it: a card with the scene's key points
(`heading`, `points`), a small bar chart (`chart`), a picture (`image_query`, fetched at the beat stage), or a cartoon scene of the catalog behind everything (`backdrop`).

HIDDEN from the ordinary scene list: the director only learns about it from the presenter policy's own prompt block (engine/presenter_policy.py), in a video the
policy gave a presenter. The policy also sets `character` and `side`; the timeline adds `speech` (the scene's word timings) and `enter` (engine/presenter_policy.link).

Deterministic: a frame is a pure function of (props, lt). The performance is planned once per scene from the words and a seed taken from the props, the turned pieces
are snapped to half a degree (vector_presenter.TurnCache), so every render chunk draws the same frame. Memory: at most 4 rasterised characters and 48 MB of turned
pieces each (in practice one character per video), 16 planned performances. A character that cannot be drawn leaves the card alone: never a failed render.
"""
import math
import re
import zlib
from collections import OrderedDict
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from ... import character_gestures as cg
from ... import vector_presenter as vp
from ...canvas import Canvas, with_alpha
from ...easing import ease_out_cubic, progress, reveal_times
from ...theme import Theme
from ..base import SceneCtx
from ..registry import Element, PrepareCtx

# id -> how tall the character is drawn against the others (the same numbers the review clips used) and whether it has a tail
CAST: Dict[str, Dict[str, Any]] = {"ines": {"size": 1.0}, "david": {"size": 1.02}, "priya": {"size": 0.99}, "mateo": {"size": 1.03}, "fox": {"size": 0.95, "tail": True},
                                   "owl": {"size": 0.95, "tail": True}, "bear": {"size": 1.04}, "cat": {"size": 0.96, "tail": True},
                                   "parrot": {"size": 0.94, "tail": True}, "turtle": {"size": 0.97, "tail": True}}
DEFAULT_CHARACTER = "ines"
SIDES = ("left", "right")
FRAMINGS = ("auto",) + vp.FRAMINGS
MAX_POINTS, MAX_BARS = 4, 5
MAX_CAST = 3                 # a conversation shows two or three characters
BOARD_MAX_ITEMS = 8          # the hand-drawn board beside a character
MOUTH_FPS = 30
ID_RE = re.compile(r"^[a-z0-9_]{3,64}$")
_PERF: "OrderedDict[Any, cg.Performance]" = OrderedDict()   # planned performances, by what they are planned from (bounded)
_BROKEN: Dict[str, str] = {}                                # character id -> why it could not be loaded (not tried again for every frame)


def _s(v: Any, n: int) -> str:
    return " ".join(str(v or "").split())[:n].strip()


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ----------------------------------------------------------------------------- props
def _sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    p = props if isinstance(props, dict) else {}
    out: Dict[str, Any] = {"character": p.get("character") if p.get("character") in CAST else DEFAULT_CHARACTER,
                           "side": p.get("side") if p.get("side") in SIDES else "left",
                           "framing": p.get("framing") if p.get("framing") in FRAMINGS else "auto"}
    heading = _s(p.get("heading") or p.get("title"), 48)
    if heading:
        out["heading"] = heading
    raw = p.get("points") if isinstance(p.get("points"), list) else p.get("items") if isinstance(p.get("items"), list) else []
    points = [t for t in (_s(x, 60) for x in raw if isinstance(x, (str, int, float))) if t][:MAX_POINTS]
    if points:
        out["points"] = points
    ch = p.get("chart")
    if isinstance(ch, dict) and isinstance(ch.get("labels"), list) and isinstance(ch.get("values"), list):
        pairs = [(_s(l, 24), _num(v)) for l, v in zip(ch["labels"], ch["values"])]
        pairs = [(l, v) for l, v in pairs if l and v is not None and v >= 0][:MAX_BARS]
        if len(pairs) >= 2 and max(v for _, v in pairs) > 0:
            out["chart"] = {"labels": [l for l, _ in pairs], "values": [round(v, 4) for _, v in pairs], "unit": _s(ch.get("unit"), 6)}
    q = _s(p.get("image_query"), 80)
    if q and "chart" not in out:
        out["image_query"] = q
        alt = _s(p.get("alt"), 70)
        if alt:
            out["alt"] = alt
    bd = str(p.get("backdrop") or "").strip().lower()
    if bd and ID_RE.match(bd):
        out["backdrop"] = bd
    if isinstance(p.get("asset"), str) and p["asset"] and "image_query" in out:   # what the beat stage fetched (prepare); kept when a timeline scene is cleaned again
        out["asset"] = p["asset"][:300]
        if _s(p.get("credit"), 120):
            out["credit"] = _s(p.get("credit"), 120)
    # a conversation (docs/CREATE_API.md "Video look"): everyone on screen, in screen order; `character` is the one who speaks this scene
    cast = [c for c in (p.get("cast") if isinstance(p.get("cast"), list) else []) if isinstance(c, str) and c in CAST]
    cast = list(dict.fromkeys(cast))[:MAX_CAST]
    if len(cast) >= 2:
        if out["character"] not in cast:
            out["character"] = cast[0]
        out["cast"] = cast
    bd_in = p.get("board")
    if isinstance(bd_in, dict) and isinstance(bd_in.get("items"), list) and "chart" not in out and "image_query" not in out:   # a hand-drawn board as the content (the whiteboard element's own items)
        from . import whiteboard as wbe
        try:
            board = wbe._sanitize({"items": bd_in["items"][:BOARD_MAX_ITEMS * 2]})
            board["items"] = _trim_board(board["items"])
            out["board"] = {"items": board["items"]}
            out.pop("heading", None)
            out.pop("points", None)
        except (ValueError, TypeError):
            pass
    if p.get("held") is True:   # what the scene before already showed, kept on screen finished (a line of a conversation that shows nothing new)
        out["held"] = True
    has = heading or points or "chart" in out or "image_query" in out or "board" in out
    if p.get("talk") is True and not has:
        out["talk"] = True
    elif not has:
        raise ValueError("presenter needs a heading, points, a chart, a picture or a board")
    return out


def _trim_board(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The board beside a character is small: the first BOARD_MAX_ITEMS items, and nothing that points at an item that was cut."""
    keep = items[:BOARD_MAX_ITEMS]
    ids = {it["id"] for it in keep}
    return [it for it in keep if all(it.get(k) is None or it[k] in ids for k in ("from", "to", "on", "near"))]


def _anchors(props: Dict[str, Any]) -> List[str]:
    if props.get("held"):
        return []
    if props.get("board"):
        return [it["say"] for it in props["board"].get("items", []) if it.get("say")]
    return list(props.get("points") or []) if not props.get("chart") else list(props["chart"]["labels"])


def _n_reveals(props: Dict[str, Any]) -> int:
    if props.get("held"):
        return 0
    if props.get("board"):
        return len(_anchors(props))
    return len(props["chart"]["labels"]) if props.get("chart") else len(props.get("points") or [])


def _cues(props: Dict[str, Any], dur: float) -> List[float]:
    n = _n_reveals(props)
    return reveal_times(n, dur, props.get("cues")) if n else []


def _fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """The same scene without what could not be fetched (the picture): the presenter and the card stay."""
    out = {k: v for k, v in props.items() if k not in ("image_query", "alt", "asset", "credit")}
    if not (out.get("heading") or out.get("points") or out.get("chart") or out.get("board") or out.get("talk")):
        out["heading"] = _s(props.get("alt") or props.get("image_query"), 48) or "…"
    return "presenter", out


def _prepare(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    """Beat stage: the picture beside the presenter, through the same reviewed stock search as an `image` scene. No picture asked: nothing to do."""
    if not props.get("image_query"):
        return {}
    from ...handlers import beat_handler   # the beat Lambda's own photo path (search, review, store, credit)

    beat = {"id": ctx.beat_id, "narration": ctx.narration, "scene": {"type": "image", "props": {"image_query": props["image_query"], "alt": props.get("alt") or props["image_query"]}}}
    got = beat_handler.make_photo({"frame": dict(ctx.frame or {}), "media_items": []}, beat, ctx.video_id, "cost_usd")
    if not got.get("asset"):
        raise RuntimeError("no picture found")
    return {"asset": got["asset"], **({"credit": got["credit"]} if got.get("credit") else {})}


# ----------------------------------------------------------------------------- the performance (pure function of the props)
_VOWELS = re.compile(r"[aeiouyáéíóúü]+", re.I)


def mouth_track(words: List[Any], dur: float, fps: int = MOUTH_FPS) -> List[str]:
    """Mouth shape per frame from the word timings alone (the render has no audio): the mouth opens once per syllable inside each word and closes between words.
    Three shapes exist (closed, half, wide), so this is as much as the art can show."""
    n = max(1, int(math.ceil(dur * fps)) + 1)
    out = ["closed"] * n
    for w in words:
        try:
            text, a, b = str(w[0]), float(w[1]), float(w[2])
        except (TypeError, ValueError, IndexError):
            continue
        if b <= a:
            continue
        syl = max(1, len(_VOWELS.findall(text)))
        for i in range(max(0, int(a * fps)), min(n, int(b * fps) + 1)):
            u = (i / fps - a) / (b - a)
            x = abs(math.sin(math.pi * syl * min(1.0, max(0.0, u))))
            out[i] = "wide" if x > 0.62 else "half"
    return out


def _seed(props: Dict[str, Any]) -> float:
    s = props.get("seed")
    if isinstance(s, (int, float)):
        return float(s) % 1.0
    return (zlib.crc32((props.get("character", "") + "|" + (props.get("heading") or "") + "|" + "|".join(props.get("points") or [])).encode("utf-8")) % 997) / 997.0


def _speech(props: Dict[str, Any]) -> List[Tuple[str, float, float]]:
    out = []
    for w in props.get("speech") or []:
        try:
            out.append((str(w[0]), float(w[1]), float(w[2])))
        except (TypeError, ValueError, IndexError):
            continue
    return out[:600]


def _stress(words: List[Tuple[str, float, float]]) -> List[float]:
    """Moments a listener may nod at: the longer words of the speaker's line."""
    return [a for (w, a, b) in words if len(w.strip(".,;:!?¿¡")) > 5]


def performance(props: Dict[str, Any], dur: float, lift: float, side: str, who: Optional[str] = None, slot: int = 0, toward: float = 0.0, content_side: Optional[int] = None,
                room: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None, geom: Any = None) -> cg.Performance:
    """Everything a character does in this scene, planned once from the words (kept for the frames that follow). `who` is the character (default: the speaker);
    a character that is not the speaker LISTENS: it looks toward the speaker (`toward`: -1 left, +1 right), nods now and then, mouth closed, hands at rest or held
    together. `room`: free space for each hand (`rooms`). The idle life runs on the video's clock (`at`: where the scene starts), and every gesture is home before
    the scene ends, so a cut to the next scene of the same character shows no jump (docs/PRESENTERS.md "Arms")."""
    words = _speech(props)
    who = who or props.get("character")
    speaking = who == props.get("character")
    at = _num(props.get("at")) or 0.0
    room = ((None, None), (None, None)) if room is None else tuple(tuple(round(float(r), 1) for r in pair) for pair in room)
    key = (who, speaking, side, slot, round(toward, 2), content_side, round(lift, 3), round(dur, 3), bool(props.get("enter", True)), _seed(props), tuple(words), round(at, 3), room,
           props.get("prev_speaker"), props.get("next_speaker"))
    perf = _PERF.get(key)
    if perf is not None:
        _PERF.move_to_end(key)
        return perf
    if content_side is None:
        content_side = 1 if side == "left" else -1
    seed = _seed(props) if speaking and not props.get("cast") else ((zlib.crc32(str(who).encode("utf-8")) % 991) / 991.0 * 0.6 + 0.4 * _seed(props)) % 1.0
    # a listener that also listened in the scene before / listens in the next one keeps its hands together across the cut
    fold = (props.get("prev_speaker") not in (None, who), props.get("next_speaker") not in (None, who)) if (props.get("cast") and not speaking) else (False, False)
    perf = cg.Performance(seed=seed, content_side=content_side, tail=bool(CAST.get(who, {}).get("tail")), lift=lift, who=who, clock=at, limit=dur, room=room[0], clear=room[1], fold=fold,
                          quiet=0.0 if props.get("enter", True) else QUIET_S, geom=geom)
    if props.get("enter", True):
        perf.enter(0.10 + 0.16 * slot, from_side=-content_side, distance=55.0)   # each steps in from its own edge of the picture, one after another
    if speaking and words:
        perf.speak(words, None, words[-1][2])
        perf.mouth(0.0, MOUTH_FPS, mouth_track(words, dur))
    elif not speaking and words:
        perf.listen(max(0.0, words[0][1] - 0.25), words[-1][2] + 0.1, toward, _stress(words))
    _PERF[key] = perf
    while len(_PERF) > 24:
        _PERF.popitem(last=False)
    return perf


QUIET_S = 0.36       # a scene that follows another one of the same character fades in over it (renderer.TRANSITION_S 0.4): no gesture starts during that
CARD_PAD = 36.0      # design units of empty margin inside a card: a hand may come over the card's edge this far, never over its text (a board or a picture: 0)


def rooms(lay: Dict[str, Any], fig: Optional[Dict[str, Any]], geom: Any, size: float, frame_w: float, pad: float = CARD_PAD) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """How far each hand of a figure may go outward from its shoulder, in the rig's units -> (held, on the way), each (left, right).
    held: before the hand would cover the card's text or the board, another figure, or leave the picture. on the way: the same without the picture's edge
    (a hand may leave the picture for a few frames as it swings up). Content above the figures (the tall and square layouts) is in nobody's way."""
    x = fig["x"] if fig else lay["x"]
    u = (fig["ppu"] if fig else lay["ppu"]) * size
    ground = fig["ground"] if fig else lay["ground"]
    edge = [0.0 - 0.15 * geom.hand * u, frame_w + 0.15 * geom.hand * u]          # finger tips may touch the picture's edges
    lim = [-1e9, 1e9]
    x0, y0, x1, y1 = lay["content"]
    if x1 > x0 and y1 > ground - 215.0 * u:                                      # the content reaches down to where hands work (beside the figure, not above it)
        if x1 <= x:
            lim[0] = max(lim[0], x1 - pad)
        elif x0 >= x:
            lim[1] = min(lim[1], x0 + pad)
    for o in lay.get("figures") or []:
        if fig is None or o is fig:
            continue
        if o["x"] < x:
            lim[0] = max(lim[0], o["x"] + 46.0 * o["ppu"])
        else:
            lim[1] = min(lim[1], o["x"] - 46.0 * o["ppu"])
    sway = 5.0                                                                    # the body shifts its weight and leans: the hand goes with it
    sl, sr = x - geom.shoulder_x * u, x + geom.shoulder_x * u
    way = (max(8.0, (sl - lim[0]) / u - sway), max(8.0, (lim[1] - sr) / u - sway))
    held = (min(way[0], max(8.0, (sl - edge[0]) / u - sway)), min(way[1], max(8.0, (edge[1] - sr) / u - sway)))
    return held, way


# ----------------------------------------------------------------------------- layout
CARD_TOP = {"9:16": 320.0, "1:1": 160.0, "4:5": 160.0}   # design units: the card (and so its title) never starts above this line in the shapes whose corner mark sits at the top.
# A CONSTANT of the shape, the same for every account and every video (no watermark input: the mark is a final layer, docs/WATERMARK_DECOUPLED_2026-11-28.md); it is
# just below the lowest place the mark can take there (9:16 y 200 to 308, square and 4:5 y 38 to 146); since the frame's own top margin (310 / 150) now clears it for every scene, this is margin_top + 10, so a corner logo never lands on a title.


def layout(props: Dict[str, Any], ctx: SceneCtx) -> Dict[str, Any]:
    """Where the character(s) stand and where the content goes. Over a catalog backdrop the feet are put ON ITS GROUND (engine/stand_zone.py): `unplaced` is set when the ground
    cannot hold them (the backdrop is then not drawn, the plain background stays). The card starts at CARD_TOP at the earliest."""
    lay = _layout_plain(props, ctx)
    lay = _stand(props, ctx, lay) if props.get("backdrop") else lay
    top = CARD_TOP.get(ctx.frame.aspect)
    c = lay.get("content")
    if top is not None and c and c[1] < top and c[3] - top >= 200.0:
        lay = {**lay, "content": (c[0], top, c[2], c[3])}
    return lay


def _stand(props: Dict[str, Any], ctx: SceneCtx, lay: Dict[str, Any]) -> Dict[str, Any]:
    side = props.get("side") if props.get("side") in SIDES else "left"
    tries = [(side, _stage(ctx, lay))]
    if len(props.get("cast") or []) < 2:   # one character: the other side of the picture may have the ground
        other = "right" if side == "left" else "left"
        tries.append((other, _stage(ctx, _layout_plain({**props, "side": other}, ctx))))
    for _, l in tries:
        out = _stand_one(props["backdrop"], ctx, l)
        if out is not None:
            return out
    return {**lay, "unplaced": True}


STAGE_FIGURE = {1: 0.60, 2: 0.54, 3: 0.50}   # 16:9 over a backdrop: the whole figure as a share of the frame height


def _stage(ctx: SceneCtx, lay: Dict[str, Any]) -> Dict[str, Any]:
    """16:9 over a backdrop: the figures are shown WHOLE with their feet on the ground, standing just over the caption band, the card beside them as before (the waist-cut
    figure of the plain background has its feet below the frame, where no backdrop's ground can be seen or checked). Other shapes keep their layout."""
    fr = ctx.frame
    if not fr.landscape or lay.get("floor") is not None:
        return lay
    floor = float(ctx.bottom) - (0 if ctx.captions else 40)
    figs = lay.get("figures")
    ppu = STAGE_FIGURE[len(figs) if figs else 1] * fr.H / 290.0
    out = {**lay, "ppu": ppu, "ground": floor, "floor": floor, "lift": 0.0, "preset": "full"}
    if figs:
        out["figures"] = [{**f, "ppu": ppu, "ground": floor, "lift": 0.0} for f in figs]
    return out


def _stand_one(bd: str, ctx: SceneCtx, l: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from ... import stand_zone as sz

    fr = ctx.frame
    W, H = float(fr.W), float(fr.H)
    figs = l.get("figures")
    full = l.get("floor") is not None
    prefs = [f["x"] / W for f in figs] if figs else [l["x"] / W]
    ppu = figs[0]["ppu"] if figs else l["ppu"]
    top = float(ctx.top)

    def accept(y: float, p: float) -> bool:   # the head stays in the picture and the card above keeps room
        fh, yy = 290.0 * p, y * H
        if fr.landscape:   # the card is beside the figures: only the head must stay in the picture
            return yy - fh >= top + 10
        return yy - fh >= top + 10 and (yy - fh * 1.05 - 20) - (top + 10) >= sz.MIN_CONTENT * H

    shift = 0.25 if (full or not fr.landscape) else 0.07
    pl = sz.place(bd, fr.aspect, prefs, foot_y=l["ground"] / H, ppu=ppu, W=W, H=H, full=full, max_shift=shift, accept=accept if full else None,
                  cap_top=sz.caption_top(fr) if (full and ctx.captions) else None)
    if pl is None:
        return None
    ppu2 = ppu * pl.scale
    ground = pl.y * H if full else l["ground"]
    out = {**l, "ppu": ppu2, "ground": ground}
    if full:
        figure = 290.0 * ppu2
        out["floor"] = ground
        if not fr.landscape:
            out["content"] = (fr.margin_x * 0.8, ctx.top + 10, fr.W - fr.margin_x * 0.8, ground - figure * 1.05 - 20)
    if not figs:
        out["x"], out["ppu"] = pl.xs[0] * W, ppu2
        return out
    mid = (l["content"][0] + l["content"][2]) / 2 if fr.landscape else W / 2
    speaker = next((f for f in figs if f["toward"] == 0.0), figs[0])
    new = []
    for f, x in zip(figs, pl.xs):
        new.append({**f, "x": x * W, "ppu": ppu2, "ground": ground, "content_side": 1 if x * W < mid else -1})
    sx = new[figs.index(speaker)]["x"]
    for f in new:
        if f["toward"] != 0.0:
            f["toward"] = 1.0 if sx > f["x"] else -1.0
    me = new[figs.index(speaker)]
    out.update(figures=new, x=me["x"], ppu=ppu2, side="left" if me["content_side"] > 0 else "right")
    return out


def _layout_plain(props: Dict[str, Any], ctx: SceneCtx) -> Dict[str, Any]:
    """Where the character stands and where the content goes, in design units. Wide, square and 4:5 frames: the character at one side from the waist up, the content
    beside it. 9:16: the content above, the whole character below it, standing just over the caption band."""
    fr = ctx.frame
    side = props.get("side") if props.get("side") in SIDES else "left"
    preset = props.get("framing", "auto")
    if len(props.get("cast") or []) >= 2:
        return group_layout(props, ctx)
    if fr.landscape:
        if preset == "auto":
            preset = "waist_up"   # the flat front-facing puppet reads best from the waist up: the largest face and hands, the legs and feet (its weakest parts) out of
                                  # the picture, and the gestures are made higher (`lift`) so the hands work above the caption band
        f = vp.framing(preset, side, fr.W, fr.H)
        x0, y0, x1, y1 = f["content"]
        content = (x0, max(y0, ctx.top + 20), x1, min(y1, ctx.bottom + 40))
        return {**f, "content": content, "floor": None}
    if fr.W / fr.H >= 0.7:   # square and 4:5: side by side like the wide frame, the character from the waist up in a narrower column, the card beside it
        box_h = fr.H * 0.60
        ppu = box_h / (290.0 * 0.69)
        x = (0.235 if side == "left" else 0.765) * fr.W
        col = 0.455 * fr.W
        content = (col, ctx.top + 10, fr.W - fr.margin_x * 0.6, ctx.bottom + 30) if side == "left" else (fr.margin_x * 0.6, ctx.top + 10, fr.W - col, ctx.bottom + 30)
        return {"ppu": ppu, "x": x, "ground": fr.H + 0.31 * 290.0 * ppu, "content": content, "preset": "waist_up", "side": side, "lift": 0.14, "floor": None}
    # 9:16: the card above, the whole character below it, standing just over the caption band (nothing of the figure is under the captions)
    floor = float(ctx.bottom) - (0 if ctx.captions else 40)
    figure = (floor - ctx.top) * 0.40
    ppu = figure / 290.0
    x = (0.30 if side == "left" else 0.70) * fr.W
    return {"ppu": ppu, "x": x, "ground": floor, "content": (fr.margin_x * 0.8, ctx.top + 10, fr.W - fr.margin_x * 0.8, floor - figure * 1.05 - 20), "preset": "full", "side": side, "lift": 0.0, "floor": floor}


# Where two or three characters stand (shares of the frame width, in screen order) and how large they are against a single presenter.
GROUP_WIDE = {2: ((0.125, 0.875), 0.88, (0.262, 0.738)), 3: ((0.10, 0.285, 0.90), 0.78, (0.405, 0.785))}     # ..., the content between them (x0, x1 shares)
GROUP_CUT = {2: 0.27, 3: 0.20}       # the share of a figure below the bottom edge in the wide two-shot and three-shot (a single presenter: 0.31)
GROUP_ROW = {2: ((0.27, 0.73), 1.0), 3: ((0.18, 0.50, 0.82), 0.86)}


def group_layout(props: Dict[str, Any], ctx: SceneCtx) -> Dict[str, Any]:
    """A two-shot or three-shot: everyone in the picture for the whole conversation, the content where all can gesture at it.
    16:9: from the waist up, one (or two) at the left and one at the right, the content between them. Square and 4:5: a row from the waist up along the bottom, the
    content above their heads. 9:16: the whole figures in a row standing over the caption band, the content above. -> the single layout's keys plus `figures`:
    [{character, x, ppu, ground, lift, content_side, toward, slot}] (toward: where the speaker is, -1 left, +1 right, 0 for the speaker)."""
    fr = ctx.frame
    cast = list(props["cast"])[:MAX_CAST]
    n = len(cast)
    speaker = props.get("character") if props.get("character") in cast else cast[0]
    floor = None
    if fr.landscape:
        xs, k, (c0, c1) = GROUP_WIDE[n]
        f = vp.framing("waist_up", "left", fr.W, fr.H)
        ppu, lift = f["ppu"] * k, f["lift"]
        ground = fr.H + GROUP_CUT[n] * 290.0 * ppu           # smaller figures are cut a little lower on the body, so the heads stay high in the picture
        content = (c0 * fr.W, max(f["content"][1], ctx.top + 20), c1 * fr.W, min(f["content"][3], ctx.bottom + 40))
        sides = [1 if x < (c0 + c1) / 2 else -1 for x in xs]
    elif fr.W / fr.H >= 0.7 and ctx.captions:
        # square and 4:5 with captions: the figures are WHOLE, their feet just above the caption lines (the waist-cut row had its legs and feet running behind the captions)
        xs, k = GROUP_ROW[n]
        from ... import stand_zone as _sz
        floor = _sz.caption_top(fr) * fr.H - 8.0
        figure = (floor - ctx.top) * 0.40 * k
        ppu, ground, lift = figure / 290.0, floor, 0.0
        content = (fr.margin_x * 0.6, ctx.top + 10, fr.W - fr.margin_x * 0.6, floor - figure * 1.05 - 20)
        sides = [1 if x < 0.5 else -1 for x in xs]
    elif fr.W / fr.H >= 0.7:
        xs, k = GROUP_ROW[n]
        base = float(ctx.bottom) + 46 if ctx.captions else float(fr.H)      # the row is cut at the caption band, not behind it (a single presenter's waist is: here the row would lose its faces)
        box_h = (base - ctx.top) * 0.40
        ppu, lift = box_h / (290.0 * 0.69) * k, 0.14
        ground = base + 0.31 * 290.0 * ppu
        content = (fr.margin_x * 0.6, ctx.top + 10, fr.W - fr.margin_x * 0.6, base - box_h * k - 0.02 * fr.H)
        sides = [1 if x < 0.5 else -1 for x in xs]
    else:
        xs, k = GROUP_ROW[n]
        floor = float(ctx.bottom) - (0 if ctx.captions else 40)
        figure = (floor - ctx.top) * 0.36 * k
        ppu, ground, lift = figure / 290.0, floor, 0.0
        content = (fr.margin_x * 0.8, ctx.top + 10, fr.W - fr.margin_x * 0.8, floor - figure * 1.05 - 20)
        sides = [1 if x < 0.5 else -1 for x in xs]
    sx = xs[cast.index(speaker)]
    figures = [{"character": c, "x": x * fr.W, "ppu": ppu, "ground": ground, "lift": lift, "content_side": sides[i], "slot": i,
                "toward": 0.0 if c == speaker else (1.0 if sx > x else -1.0)} for i, (c, x) in enumerate(zip(cast, xs))]
    me = figures[cast.index(speaker)]
    return {"ppu": ppu, "x": me["x"], "ground": ground, "content": content, "preset": "group", "side": "left" if me["content_side"] > 0 else "right", "lift": lift, "floor": floor, "figures": figures}


# ----------------------------------------------------------------------------- drawing
@lru_cache(maxsize=8)
def _glow_mask(w: int, h: int, peak: int) -> Image.Image:
    """A soft elliptical light as an alpha mask (drawn small once, enlarged smoothly, kept)."""
    sw, sh = max(8, w // 16), max(8, h // 16)
    small = Image.new("L", (sw, sh), 0)
    px = small.load()
    for y in range(sh):
        for x in range(sw):
            d = math.hypot((x + 0.5) / sw * 2 - 1, (y + 0.5) / sh * 2 - 1)
            px[x, y] = int(peak * max(0.0, 1.0 - d) ** 1.6)
    return small.resize((w, h), Image.BICUBIC)


def _glow(cv: Canvas, cx: float, cy: float, rx: float, ry: float, color: Tuple[int, int, int], strength: float) -> None:
    ss = cv.ss
    w, h = max(8, int(rx * 2 * ss) // 8 * 8), max(8, int(ry * 2 * ss) // 8 * 8)
    cv.im.paste(tuple(color[:3]), (int(cx * ss) - w // 2, int(cy * ss) - h // 2), _glow_mask(w, h, int(255 * strength)))


def _draw_character(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, lay: Dict[str, Any], fig: Optional[Dict[str, Any]] = None) -> None:
    cid = fig["character"] if fig else props.get("character", DEFAULT_CHARACTER)
    if cid in _BROKEN:
        return
    if fig:   # one of the figures of a conversation: its own place, and it speaks or listens
        lay = {**lay, "x": fig["x"], "ppu": fig["ppu"], "ground": fig["ground"], "lift": fig["lift"], "side": "left" if fig["content_side"] > 0 else "right"}
    # The finished picture is the canvas at half its pixel size (the renderer reduces 2x): the character is drawn at that size on its own layer and pasted doubled
    # with NEAREST, so the 2x reduce gives the very same pixels back (the vector scenes do the same).
    k = cv.im.width / 2.0 / cv.W
    try:
        ch = vp.load_cached(cid, round(lay["ppu"] * k, 4), CAST[cid]["size"])
        room = rooms(lay, fig, ch.g, CAST[cid]["size"], cv.W, 0.0 if (props.get("board") or props.get("asset")) else CARD_PAD)
        perf = performance(props, dur, lay["lift"], lay["side"], cid, fig["slot"], fig["toward"], fig["content_side"], room=room, geom=ch.g) if fig else performance(props, dur, lay["lift"], lay["side"], room=room, geom=ch.g)
        pose, ex = perf.pose(lt, ch.g)
        if ex["alpha"] <= 0.003:
            return
        u = ch.ppu
        x, ground = lay["x"] * k + ex["x"] * u, lay["ground"] * k
        bx0, bx1 = int(max(0, x - 175 * u)), int(min(cv.im.width // 2, x + 175 * u))
        by0, by1 = int(max(0, ground - 365 * u)), int(min(cv.im.height // 2, ground + 6 * u))
        if bx1 - bx0 < 4 or by1 - by0 < 4:
            return
        layer = Image.new("RGBA", (bx1 - bx0, by1 - by0), (0, 0, 0, 0))
        ch.draw(layer, x - bx0, ground - by0, pose)
        box = layer.getbbox()
        if box is None:
            return
        layer = layer.crop(box)
        if ex["alpha"] < 0.997:
            layer.putalpha(layer.getchannel("A").point(lambda v, a=ex["alpha"]: int(v * a)))
        big = layer.resize((layer.width * 2, layer.height * 2), Image.NEAREST)
        cv.im.paste(big.convert("RGB"), ((bx0 + box[0]) * 2, (by0 + box[1]) * 2), big.getchannel("A"))
    except Exception as e:  # noqa: BLE001 - a character that cannot be drawn never fails a render: the card stays
        print(f"PRESENTER_DRAW_FAILED {cid} {type(e).__name__}: {str(e)[:160]}")
        _BROKEN[cid] = type(e).__name__


def _panel(cv: Canvas, rect: Tuple[float, float, float, float], th: Theme, alpha: float, solid: bool) -> None:
    x0, y0, x1, y1 = rect
    if solid:   # over a cartoon scene the card must carry its own ground
        cv.shadow(x0, y0, x1 - x0, y1 - y0, 32, alpha=0.35 * alpha)
        cv.rrect(x0, y0, x1 - x0, y1 - y0, 32, fill=(*th.bg_top[:3], int(232 * alpha)), outline=with_alpha(th.card_outline, alpha), width=1.5)
    else:
        cv.card(x0, y0, x1 - x0, y1 - y0, th, r=32, alpha=alpha)


def _early(times: List[float]) -> List[float]:
    """A card is never empty for long: whatever the narration cues say, the first item starts within 0.7 s of the scene and each next within 0.6 s of the one before."""
    out: List[float] = []
    for i, t in enumerate(times):
        out.append(min(float(t), 0.7 + 0.6 * i))
    return out


def _draw_points(cv: Canvas, props: Dict[str, Any], rect: Tuple[float, float, float, float], lt: float, dur: float, th: Theme, ts: float) -> None:
    x0, y0, x1, y1 = rect
    pad = (54 if y1 - y0 > 520 else 38) * ts
    w = x1 - x0 - 2 * pad
    heading, points = props.get("heading", ""), list(props.get("points") or [])
    y = y0 + pad
    n_pts = len(points)
    if heading and not points:   # a single line: large, centred in the card
        a = progress(lt, 0.25, 0.5)
        size, lines = cv.fit_text(heading, "bold", w, (y1 - y0) - 2 * pad, 92 * ts, 44 * ts)
        ty = (y0 + y1) / 2 - len(lines) * size * 1.16 / 2
        for i, ln in enumerate(lines):
            cv.text((x0 + x1) / 2, ty + i * size * 1.16 + (1 - ease_out_cubic(a)) * 18, ln, "bold", size, with_alpha(th.text, a), anchor="ma")
        cv.rrect((x0 + x1) / 2 - 60 * ts, ty + len(lines) * size * 1.16 + 18 * ts, 120 * ts * ease_out_cubic(a), 8 * ts, 4 * ts, fill=with_alpha(th.accent, a))
        return
    n = len(points)
    times = _early(reveal_times(n, dur, props.get("cues")))
    y_start = y

    def fit_points(top: float) -> float:   # one size for every point: the largest at which all of them fit the card below `top`
        sz = 60 * ts
        while sz > 26 * ts:
            chip_ = sz * 1.14
            tw_ = w - chip_ - 26 * ts
            blocks_ = [cv.wrap(p, "semibold", sz, tw_) for p in points]
            need = sum(max(chip_, len(b) * sz * 1.2) for b in blocks_) + (n - 1) * 26 * ts
            if need <= y1 - pad - top and all(len(b) <= 3 for b in blocks_):
                break
            sz -= 3 * ts
        return sz

    hsize, hlines, hbottom = 0.0, [], y_start
    if heading:   # the heading gives way to the points: the box it may take shrinks until the points are readable (40 units), never below the heading's own floor
        for box in ((180 if n_pts <= 3 else 96), 130, 96, 70):
            hsize, hlines = cv.fit_text(heading, "bold", w, box * ts, 76 * ts, 38 * ts)
            hbottom = y_start + min(2, len(hlines)) * hsize * 1.14 + 16 * ts + 48 * ts
            if not points or fit_points(hbottom) >= 40 * ts:
                break
        a = progress(lt, 0.2, 0.45)
        for i, ln in enumerate(hlines[:2]):
            cv.text(x0 + pad, y + i * hsize * 1.14, ln, "bold", hsize, with_alpha(th.text, a))
        y += min(2, len(hlines)) * hsize * 1.14 + 16 * ts
        cv.rrect(x0 + pad, y, 110 * ts * ease_out_cubic(a), 8 * ts, 4 * ts, fill=with_alpha(th.accent, a))
        y += 48 * ts
    size = fit_points(y)
    chip = size * 1.14
    tw = w - chip - 26 * ts
    blocks = [cv.wrap(p, "semibold", size, tw)[:3] for p in points]
    free = (y1 - pad - y) - sum(max(chip, len(b) * size * 1.2) for b in blocks)
    gap = max(18 * ts, min(84 * ts, free / max(1, n)))
    y += max(0.0, (free - gap * (n - 1)) / 2) * 0.5   # a short list sits a little below the heading, not glued to it
    for i, lines in enumerate(blocks):
        a = progress(lt, times[i], 0.45)
        e = ease_out_cubic(a)
        bh = max(chip, len(lines) * size * 1.2)
        if a > 0:
            dx = (1 - e) * 26
            cv.ellipse(x0 + pad + chip / 2 + dx, y + chip / 2, chip / 2, chip / 2, fill=with_alpha(th.accent, a))
            cv.text(x0 + pad + chip / 2 + dx, y + chip / 2, str(i + 1), "bold", size * 0.6, (255, 255, 255, int(255 * a)), anchor="mm")
            ty = y + (chip - size * 1.2) / 2 if len(lines) == 1 else y
            for j, ln in enumerate(lines):
                cv.text(x0 + pad + chip + 26 * ts + dx, ty + j * size * 1.2, ln, "semibold", size, with_alpha(th.text, a))
        y += bh + gap


def _draw_chart(cv: Canvas, props: Dict[str, Any], rect: Tuple[float, float, float, float], lt: float, dur: float, th: Theme, ts: float) -> None:
    from ... import numfmt

    x0, y0, x1, y1 = rect
    pad = 54 * ts
    ch = props["chart"]
    labels, values, unit = ch["labels"], ch["values"], ch.get("unit", "")
    y = y0 + pad
    if props.get("heading"):
        a = progress(lt, 0.2, 0.45)
        size, lines = cv.fit_text(props["heading"], "bold", x1 - x0 - 2 * pad, 130 * ts, 58 * ts, 38 * ts)
        for i, ln in enumerate(lines[:2]):
            cv.text(x0 + pad, y + i * size * 1.14, ln, "bold", size, with_alpha(th.text, a))
        y += min(2, len(lines)) * size * 1.14 + 30 * ts
    n = len(values)
    times = _early(reveal_times(n, dur, props.get("cues")))
    top = max(values) or 1.0
    base = y1 - pad - (52 + (30 if any(cv.measure(l, 'semibold', 24 * ts) > (x1 - x0 - 2 * pad) / max(1, n) - 10 for l in labels) else 0)) * ts
    area_h = base - y - 60 * ts
    slot = (x1 - x0 - 2 * pad) / n
    bw = min(slot * 0.62, 170 * ts)
    cv.line([(x0 + pad, base), (x1 - pad, base)], with_alpha(th.muted, 0.6), 3)
    lsize = 34 * ts
    while lsize > 24 * ts and any(cv.measure(l, "semibold", lsize) > slot - 10 for l in labels):
        lsize -= 2 * ts
    for i, (lab, v) in enumerate(zip(labels, values)):
        a = ease_out_cubic(progress(lt, times[i], 0.7))
        cx = x0 + pad + slot * (i + 0.5)
        h = max(4.0, area_h * (v / top)) * a
        if a > 0:
            cv.rrect(cx - bw / 2, base - h, bw, h, min(14 * ts, bw / 4), fill=with_alpha(th.accent if i % 2 == 0 else th.accent2, 0.35 + 0.65 * a))
            dec = 0 if float(v).is_integer() else 1
            txt = numfmt.format_number(round(v * a, dec) if a < 1 else v, dec, False) + unit
            cv.text(cx, base - h - 14 * ts, txt, "bold", 40 * ts, with_alpha(th.text, a), anchor="ms")
        for j, ln in enumerate(cv.wrap(lab, "semibold", lsize, slot - 10)[:2]):   # a label wider than its slot goes on a second line instead of running into the next one
            cv.text(cx, base + 14 * ts + j * lsize * 1.15, ln, "semibold", lsize, with_alpha(th.muted, 1.0), anchor="ma")


def _draw_picture(cv: Canvas, props: Dict[str, Any], rect: Tuple[float, float, float, float], lt: float, th: Theme, ctx: SceneCtx, ts: float) -> bool:
    img = ctx.resolve_image(props["asset"]) if props.get("asset") else None
    if img is None:
        return False
    x0, y0, x1, y1 = rect
    a = progress(lt, 0.1, 0.5)
    ss = cv.ss
    pw, ph = int((x1 - x0) * ss), int((y1 - y0) * ss)
    zoom = 1.0 + 0.04 * min(1.0, lt / 8.0)   # a slow push in
    sc = max(pw / img.width, ph / img.height) * zoom
    im = img.resize((max(pw, int(img.width * sc) + 1), max(ph, int(img.height * sc) + 1)), Image.BILINEAR)
    ox, oy = (im.width - pw) // 2, (im.height - ph) // 3
    im = im.crop((ox, oy, ox + pw, oy + ph)).convert("RGB")
    mask = Image.new("L", (pw, ph), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=int(32 * ss), fill=int(255 * a))
    cv.shadow(x0, y0, x1 - x0, y1 - y0, 32, alpha=th.shadow_alpha * a)
    cv.im.paste(im, (int(x0 * ss), int(y0 * ss)), mask)
    label = props.get("heading") or ""
    if label:
        size, lines = cv.fit_text(label, "bold", x1 - x0 - 120 * ts, 70 * ts, 46 * ts, 30 * ts)
        tw = max(cv.measure(lines[0], "bold", size), 10) + 56 * ts
        cv.rrect(x0 + 28 * ts, y1 - 28 * ts - size * 1.7, tw, size * 1.7, 18 * ts, fill=(*th.caption_bg[:3], int(215 * a)))
        cv.text(x0 + 28 * ts + 28 * ts, y1 - 28 * ts - size * 0.85, lines[0], "bold", size, (*th.caption_text, int(255 * a)), anchor="lm")
    if props.get("credit"):
        cv.text(x1 - 20 * ts, y0 + 16 * ts, str(props["credit"])[:60], "regular", 20 * ts, (255, 255, 255, int(170 * a)), anchor="ra")
    return True


_BOARD: Dict[str, Any] = {}      # the one hand-drawn board being shown beside a character: {"key", "board", "cam", "geo"}


class _Sub:
    """What the whiteboard element reads from a scene context, for a board that is only a part of the picture."""

    def __init__(self, w: float, h: float, pad: float):
        self.frame = type("F", (), {"W": w, "H": h, "aspect": "board"})()
        self.box = (pad, pad, w - pad, h - pad)
        self.captions = False


def _draw_board(cv: Canvas, props: Dict[str, Any], rect: Tuple[float, float, float, float], lt: float, dur: float, th: Theme) -> bool:
    """The whiteboard renderer's board as the content beside the character: drawn and written by the marker in time with the words (docs/WHITEBOARD.md). False when
    it cannot be built (the caller then shows a card)."""
    import hashlib
    import json

    from . import whiteboard as wbe
    from ...whiteboard import board as bd

    x0, y0, x1, y1 = rect
    k = cv.im.width / 2.0 / cv.W                           # the finished picture's pixels per design unit (the canvas is twice that)
    w, h = max(8, int(round((x1 - x0) * k))), max(8, int(round((y1 - y0) * k)))
    bprops = {"items": props["board"]["items"], **({"cues": props["cues"]} if isinstance(props.get("cues"), list) and not props.get("held") else {})}
    key = hashlib.sha1(json.dumps([bprops, round(dur, 3), w, h], sort_keys=True, default=str).encode()).hexdigest()
    try:
        if _BOARD.get("key") != key:
            _BOARD.clear()
            board, cam, geo, _ = wbe.build(bprops, 1e6 if props.get("held") else dur, _Sub(x1 - x0, y1 - y0, 0.045 * min(x1 - x0, y1 - y0)), w, h)
            _BOARD.update(key=key, board=board, cam=cam, geo=geo)
        t = 1e6 - 1.0 if props.get("held") else max(0.0, lt)
        frame = _BOARD["board"].frame(t, wbe.full_view(_BOARD["cam"].at(t), _BOARD["geo"]), (w, h), tip=not props.get("held"))
    except Exception as e:  # noqa: BLE001 - never a failed render for a picture
        print(f"PRESENTER_BOARD_FAILED {type(e).__name__}: {str(e)[:200]}")
        _BOARD.clear()
        return False
    a = 1.0 if props.get("held") else progress(lt, 0.05, 0.4)
    r = 26.0
    cv.shadow(x0, y0, x1 - x0, y1 - y0, r, alpha=0.40 * a)
    cv.rrect(x0 - 7, y0 - 7, x1 - x0 + 14, y1 - y0 + 14, r + 7, fill=(92, 98, 110, int(255 * a)))      # the board's frame
    big = frame.resize((w * 2, h * 2), Image.NEAREST)
    from PIL import ImageDraw
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big.width - 1, big.height - 1), radius=int(r * cv.ss), fill=int(255 * a))
    cv.im.paste(big, (int(round(x0 * k)) * 2, int(round(y0 * k)) * 2), mask)
    return True


def _draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    from ... import stand_zone as sz_mod

    fr = ctx.frame
    lay = layout(props, ctx)
    figures = lay.get("figures") or [None]
    ts = 1.0 if fr.landscape else min(1.12, fr.type_scale)
    backdrop = False
    if props.get("backdrop") and not lay.get("unplaced"):   # a cartoon scene of the catalog behind the presenter (its own element draws it; no package, or no ground for the cast -> the plain background stays)
        from . import vector_scene as vse
        if props["backdrop"] in sz_mod.DRAWN:   # a drawn ground: no package, nothing to fetch
            from ... import procedural_ground
            procedural_ground.draw(cv, th, ctx, lt, props["backdrop"])
            backdrop = True
        elif vse.package_folder(props["backdrop"]) is not None:
            vse._draw(cv, {"catalog_id": props["backdrop"]}, lt, dur, th, ctx)
            backdrop = True
    for fig in figures:
        x, ppu = (fig["x"], fig["ppu"]) if fig else (lay["x"], lay["ppu"])
        if not backdrop:   # a soft light where the character stands, so the figure is not floating on the gradient
            figure_h = 290.0 * ppu
            _glow(cv, x, lay["ground"] - figure_h * 0.52, figure_h * 0.50, figure_h * 0.62, th.accent[:3], 0.30)
        if lay.get("floor") is not None:   # the whole figure is in the picture: a contact shadow under the feet
            _glow(cv, x, lay["floor"] + 4, 64 * ppu, 10 * ppu, (0, 0, 0), 0.55)
    rect = lay["content"]
    lc = 1e3 if props.get("held") else lt                  # what the scene before already showed is there, finished, from the first frame
    drawn = False
    if props.get("board"):
        drawn = _draw_board(cv, props, rect, lt, dur, th)
    elif props.get("asset"):
        drawn = _draw_picture(cv, props, rect, lc, th, ctx, ts)
    if not drawn and not (props.get("talk") and not (props.get("heading") or props.get("points") or props.get("chart"))):
        _panel(cv, rect, th, progress(lc, 0.05, 0.4), backdrop)
        if props.get("chart"):
            _draw_chart(cv, props, rect, lc, dur, th, ts)
        else:
            p = props if (props.get("heading") or props.get("points")) else {**props, "heading": props.get("alt") or props.get("image_query") or next((it["write"].split("\n")[0] for it in (props.get("board") or {}).get("items", []) if it.get("write")), "")}
            _draw_points(cv, p, rect, lc, dur, th, ts)
    for fig in sorted(figures, key=lambda f: (f is not None and f["toward"] == 0.0)):   # the speaker last: its gestures are in front of the listeners
        _draw_character(cv, props, lt, dur, lay, fig)


def release() -> None:
    """Drops what is kept between frames (planned performances, rasterised characters and their turned pieces)."""
    _PERF.clear()
    _BROKEN.clear()
    _BOARD.clear()
    vp.load_cached.cache_clear()


ELEMENTS = [
    Element(
        name="presenter", family="People and sources",
        doc="- presenter: {heading (<=48), points: 0-4 short strings (<=60)}. A cartoon presenter stands beside a card and says the narration. Offered to the director only by the presenter policy.",
        sanitize=_sanitize, draw=_draw, cues=_cues, anchors=_anchors, prepare=_prepare, fallback=_fallback,
        samples=[{"character": "ines", "heading": "Why is the sky blue?", "points": ["Sunlight is every colour", "Air scatters blue the most", "So blue comes from everywhere"]},
                 {"character": "fox", "side": "right", "heading": "Hello, explorers!"},
                 {"character": "david", "heading": "Page load time", "chart": {"labels": ["Before", "Cached", "Now"], "values": [4.2, 2.1, 0.9], "unit": "s"}},
                 {"character": "priya", "framing": "waist_up", "heading": "Three daily habits", "points": ["Sleep seven hours", "Walk thirty minutes", "Drink water", "See friends"]}],
        formats=("16:9", "9:16", "1:1", "4:5"), hidden=True, min_seconds=3.0,
    )
]
