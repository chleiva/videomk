"""Photos (`photo_collage`, `photo_frame`, `chapter_card`): the user's own photos shown in designed layouts, so a video made from up to 100 photos in a short time
can show nearly all of them. Drawing lives in `_photo_collage.py` and `_photo_frame.py`, shared helpers in `_photo_kit.py`; the contract is docs/ELEMENT_BUILD_GUIDE.md,
the element notes are docs/ELEMENT_PHOTO_LAYOUTS.md."""
from typing import Any, Dict, List, Tuple

from ...canvas import Canvas, with_alpha
from ...easing import ease_out_cubic, progress
from ...theme import Theme
from ..base import CONTENT_TOP, SceneCtx
from ..registry import Element, PrepareCtx
from . import _photo_collage, _photo_frame
from . import _photo_kit as K
from ._pm_text import clean

COLLAGE_STYLES = _photo_collage.STYLES
FRAME_STYLES = _photo_frame.STYLES
MAX_PHOTOS = 9


def _strs(raw: Any, n: int, each: int) -> List[str]:
    return [clean(x, each) for x in (raw if isinstance(raw, list) else [])][:n]


# ===================================================================================================== photo_collage
def sanitize_collage(p: Dict[str, Any]) -> Dict[str, Any]:
    ids = K.id_list(p.get("photos"), MAX_PHOTOS)
    if len(ids) < 2:
        raise ValueError("photo_collage needs 2+ photo ids like P7")
    out: Dict[str, Any] = {"photos": ids, "alt": clean(p.get("alt"), 70) or "Photos"}
    if p.get("style") in COLLAGE_STYLES:
        out["style"] = p["style"]
    for k, n in (("title", 50), ("subtitle", 80)):
        v = clean(p.get(k), n)
        if v:
            out[k] = v
    caps = _strs(p.get("captions"), len(ids), 80)
    if caps:
        out["captions"] = caps
    assets = [clean(a, 300) for a in (p.get("assets") or [])] if isinstance(p.get("assets"), list) else []
    if len(assets) == len(ids) and all(assets):            # the patch that `prepare` adds: kept whole or not at all
        out["assets"] = assets
        out["ratios"] = [round(K.num(r, 0.2, 5.0, 1.0), 4) for r in (p.get("ratios") or [])][: len(ids)] if isinstance(p.get("ratios"), list) else []
        if len(out["ratios"]) != len(ids):
            out["ratios"] = [1.0] * len(ids)
        out["orientations"] = [K.orientation_of(r) for r in out["ratios"]]
    return out


def collage_anchors(p: Dict[str, Any]) -> List[str]:
    """One text per photo, in order: its caption when the planner filled them in, else a generic string (the reveals are then spread over the beat)."""
    n = len(p.get("photos") or p.get("assets") or [])
    caps = [str(c) for c in (p.get("captions") or [])]
    return [caps[i] if i < len(caps) and caps[i].strip() else f"photo {i + 1}" for i in range(n)]


def collage_cues(p: Dict[str, Any], dur: float) -> List[float]:
    n = len(p.get("photos") or p.get("assets") or [])
    return K.reveal_schedule(n, dur, p.get("cues")) if n else []


def prepare_collage(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    """Look every id up in the video's photos; keep the ones that exist (in the order given). Fewer than 2 -> raise (the beat falls back)."""
    p = sanitize_collage(props)
    items = {str(m.get("id")): m for m in (ctx.media_items or []) if isinstance(m, dict)}
    keep = [i for i in p["photos"] if i in items and items[i].get("key")]
    if len(keep) < 2:
        raise ValueError("photo_collage: fewer than 2 of its photos exist")
    ratios = [K.ratio_of(items[i]) for i in keep]
    patch: Dict[str, Any] = {"photos": keep, "assets": [str(items[i]["key"]) for i in keep], "ratios": ratios, "orientations": [K.orientation_of(r) for r in ratios]}
    caps = p.get("captions")
    if caps:
        by_id = dict(zip(p["photos"], caps))
        patch["captions"] = [by_id.get(i, "") for i in keep]
    return patch


def collage_fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    title = clean(props.get("title"), 70) or clean(props.get("alt"), 70) or "Photos"
    out: Dict[str, Any] = {"title": title}
    if clean(props.get("subtitle"), 110):
        out["subtitle"] = clean(props.get("subtitle"), 110)
    return "title", out


# ===================================================================================================== photo_frame
def sanitize_frame(p: Dict[str, Any]) -> Dict[str, Any]:
    pid = K.photo_id(p.get("photo"))
    if not pid:
        raise ValueError("photo_frame needs a photo id like P7")
    out: Dict[str, Any] = {"photo": pid, "alt": clean(p.get("alt"), 70) or "A photo"}
    if p.get("style") in FRAME_STYLES:
        out["style"] = p["style"]
    for k, n in (("title", 50), ("subtitle", 80), ("date_label", 30)):
        v = clean(p.get(k), n)
        if v:
            out[k] = v
    asset = clean(p.get("asset"), 300)
    if asset:
        out["asset"] = asset
        out["ratio"] = round(K.num(p.get("ratio"), 0.2, 5.0, 1.0), 4)
    return out


def frame_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return [min(0.3, max(0.0, dur - 0.5))]


def prepare_frame(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    p = sanitize_frame(props)
    item = next((m for m in (ctx.media_items or []) if isinstance(m, dict) and str(m.get("id")) == p["photo"] and m.get("key")), None)
    if item is None:
        raise ValueError(f"photo_frame: unknown photo {p['photo']}")
    return {"asset": str(item["key"]), "ratio": K.ratio_of(item)}


def frame_fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    title = clean(props.get("title"), 70) or clean(props.get("alt"), 70) or "Photo"
    out: Dict[str, Any] = {"title": title}
    if clean(props.get("subtitle"), 110):
        out["subtitle"] = clean(props.get("subtitle"), 110)
    return "title", out


# ===================================================================================================== chapter_card
def sanitize_chapter(p: Dict[str, Any]) -> Dict[str, Any]:
    title = clean(p.get("title"), 60)
    if not title:
        raise ValueError("chapter_card needs a title")
    out: Dict[str, Any] = {"title": title}
    for k, n in (("subtitle", 100), ("kicker", 40)):
        v = clean(p.get(k), n)
        if v:
            out[k] = v
    pid = K.photo_id(p.get("photo"))
    if pid:
        out["photo"] = pid
    asset = clean(p.get("asset"), 300)
    if asset:
        out["asset"] = asset
    return out


def chapter_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return [min(0.5, max(0.0, dur - 0.5))]


def prepare_chapter(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    """The hero photo becomes the background. A missing hero is not an error: the card then uses the theme's ambience."""
    try:
        pid = K.photo_id(props.get("photo"))
        item = next((m for m in (ctx.media_items or []) if isinstance(m, dict) and str(m.get("id")) == pid and m.get("key")), None) if pid else None
        return {"asset": str(item["key"])} if item else {}
    except Exception:  # noqa: BLE001
        return {}


def draw_chapter(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    title, kicker, subtitle = str(props.get("title") or ""), str(props.get("kicker") or "").upper(), str(props.get("subtitle") or "")
    src = None
    if props.get("asset"):
        try:
            src = ctx.resolve_image(str(props["asset"]))
        except Exception:
            src = None
    hero = K.backdrop(cv, src, th, dark=0.34, mix=0.9, blur=4.0, wash=False)
    ink = th.caption_text if hero else th.text
    soft = th.caption_text if hero else th.muted
    if not hero:                                              # theme ambience: two slow rings as a quiet ornament
        grow = ease_out_cubic(progress(lt, 0.0, 1.4))
        for r, w, a in ((300, 3, 0.16), (440, 2, 0.10), (590, 2, 0.06)):
            cv.ellipse(1560, 420, r * (0.85 + 0.15 * grow), r * (0.85 + 0.15 * grow), outline=with_alpha(th.accent, a * grow), width=w)

    left, text_x = 150.0, 205.0
    max_w = 1480.0
    size, lines = cv.fit_text(title, "bold", max_w, 330, 128, 60, line_h=1.12)
    lines = lines[:3]
    ssize = 42
    slines = cv.wrap(subtitle, "regular", ssize, max_w)[:2] if subtitle else []
    kh = 34 + 30 if kicker else 0
    th_h = len(lines) * size * 1.12
    sh = (30 + len(slines) * ssize * 1.3) if slines else 0
    total = kh + th_h + sh
    top = CONTENT_TOP + ((ctx.bottom - 24) - CONTENT_TOP - total) / 2
    top = max(CONTENT_TOP + 10, top)

    if kicker:
        p = ease_out_cubic(progress(lt, 0.1, 0.6))
        K.spaced_text(cv, text_x + (1 - p) * -30, top + 34, kicker, "semibold", 32, with_alpha(th.accent if not hero else th.accent2, p), track=0.2)
    ty = top + kh
    bar = ease_out_cubic(progress(lt, 0.2, 0.7))
    cv.rrect(left, ty + 6 + (th_h - 12) * (1 - bar) / 2, 12, (th_h - 12) * bar, 6, fill=with_alpha(th.accent, 1.0))
    words = [(li, j, w) for li, l in enumerate(lines) for j, w in enumerate(l.split())]
    step = min(0.13, 1.3 / max(1, len(words)))
    t_word = 0.5
    for k, (li, j, w) in enumerate(words):
        pre = " ".join(lines[li].split()[:j])
        wx = text_x + (cv.measure(pre + " ", "bold", size) if j else 0.0)
        p = ease_out_cubic(progress(lt, t_word + k * step, 0.45))
        if p <= 0.01:
            continue
        y = ty + li * size * 1.12 + (1 - p) * 26
        if hero:
            cv.text(wx + 3, y + 5, w, "bold", size, (0, 0, 0, int(110 * p)))
        cv.text(wx, y, w, "bold", size, with_alpha(ink, p))
    t_sub = t_word + len(words) * step + 0.25
    if slines:
        p = ease_out_cubic(progress(lt, t_sub, 0.6))
        for i, l in enumerate(slines):
            cv.text(text_x, ty + th_h + 30 + i * ssize * 1.3 + (1 - p) * 16, l, "regular", ssize, with_alpha(soft, 0.9 * p))


# ===================================================================================================== registry
ELEMENTS = [
    Element(
        name="photo_collage", family="Photos",
        doc=("- photo_collage: {photos: 3-9 ids from the user's photo list (like \"P7\"), style: \"mosaic\"|\"polaroids\"|\"grid\"|\"filmstrip\"|\"stack\" (optional), title (<=50), "
             "subtitle (<=80), alt (<=70)}. The user's OWN photos on screen together, appearing one by one as the narration names them, in the order given. Use for 3-9 photos "
             "of the same day or place shown together, and to fit many photos into a short video: polaroids for personal memories, mosaic or grid for variety, filmstrip for a "
             "sequence of moments, stack for a few favourites. Never for stock or searched photos, ids not in the list, one photo (use photo_frame), or the same id twice."),
        sanitize=sanitize_collage, draw=_photo_collage.draw_collage, cues=collage_cues, anchors=collage_anchors, prepare=prepare_collage, fallback=collage_fallback,
        min_seconds=4.0,
        samples=[
            {"photos": ["P1", "P2", "P3", "P4"], "style": "polaroids", "title": "Saturday in Paris", "subtitle": "Eiffel Tower, the Seine, a long lunch", "alt": "Four photos of a day in Paris"},
            {"photos": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"], "alt": "Nine photos of the trip"},
            {"photos": ["P5", "P6", "P7", "P8", "P9"], "style": "filmstrip", "title": "The walk", "alt": "Five moments of the walk"},
            {"photos": ["P2", "P3", "P4", "P5", "P6", "P7"], "style": "grid", "alt": "Six photos in a grid"},
            {"photos": ["P1", "P2", "P3"], "style": "stack", "alt": "Three favourite photos"},
        ],
    ),
    Element(
        name="photo_frame", family="Photos",
        doc=("- photo_frame: {photo: one id from the user's photo list (like \"P7\"), style: \"polaroid\"|\"matte\"|\"tilted\"|\"film\"|\"pinned\" (optional), title (<=50), subtitle (<=80), "
             "date_label (<=30, only a date the photo list gives), alt (<=70)}. ONE of the user's OWN photos shown as a framed piece with a slow zoom. Use for the one important "
             "photo of a moment or chapter (polaroid for a personal memory, matte for a landscape, pinned for a keepsake). Never for several photos (use photo_collage), stock or "
             "searched photos, an id not in the list, or an invented date or place."),
        sanitize=sanitize_frame, draw=_photo_frame.draw_frame, cues=frame_cues, prepare=prepare_frame, fallback=frame_fallback,
        samples=[
            {"photo": "P1", "style": "polaroid", "title": "Golden hour", "subtitle": "The Eiffel Tower from the Trocadero", "date_label": "Sunday 12 April", "alt": "The Eiffel Tower at sunset"},
            {"photo": "P2", "style": "matte", "title": "The Louvre", "alt": "The glass pyramid"},
            {"photo": "P3", "style": "tilted", "subtitle": "A quiet corner of the city", "alt": "A street"},
            {"photo": "P4", "style": "film", "title": "Along the Seine", "date_label": "Monday 13 April", "alt": "The river"},
            {"photo": "P6", "style": "pinned", "title": "Montmartre", "alt": "A hill street"},
        ],
    ),
    Element(
        name="chapter_card", family="Photos",
        doc=("- chapter_card: {title (<=60), subtitle (<=100), kicker (<=40, small uppercase line above, e.g. 'DAY 2 - SUNDAY 12 APRIL' or 'PARIS'), photo (optional id from the user's "
             "photo list, used as a blurred background)}. A full-screen opener for one chapter of a story, the title revealing word by word. Use only when the video has 3 or more "
             "chapters, and keep the beat's narration to one short line. Never as the video's first scene (use title), for one-chapter videos, or with an invented date or place."),
        sanitize=sanitize_chapter, draw=draw_chapter, cues=chapter_cues, prepare=prepare_chapter, min_seconds=3.0,
        samples=[
            {"title": "A day in the city", "kicker": "Day 2 - Sunday 12 April", "subtitle": "Markets, museums and a long walk home", "photo": "P1"},
            {"title": "Paris"},
        ],
    ),
]
