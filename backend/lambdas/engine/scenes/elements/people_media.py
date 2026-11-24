"""People and sources (`headline`, `dialogue`) and Media (`icons`, `annotated_image`) elements."""
import json
import math
import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from ...canvas import Canvas, with_alpha
from ...easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress, reveal_times
from ...theme import Theme
from ..base import CONTENT_TOP, SceneCtx, heading
from ..registry import Element, PrepareCtx
from . import _pm_icons
from ._pm_text import clean, hue_shift, on_color, serif_measure, serif_text, serif_wrap


# ===================================================================================================== headline
# A headline is kept only when it can be traced to a cited source. The thresholds below are deliberately strict: a copy of a title (with or without the
# outlet suffix, punctuation or a truncated tail) scores about 1.0 on both ratios; a paraphrase scores about 0.3-0.5 and an invention near 0.
HEADLINE_MIN_SHARED = 3          # content words in common
HEADLINE_COVER_H = 0.75          # share of the headline's content words found in the source title (a headline cannot add words the source lacks)
HEADLINE_COVER_T = 0.5           # share of the title's content words found in the headline (a headline cannot be a few words cherry-picked from a long title)

_STOP = frozenset("a an the and or of to in on at for by with from as is are was were be been it its this that these those he she they his her their after over into amid".split())


def _words(s: str) -> List[str]:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", s.replace("'", ""))


def _content(s: str) -> List[str]:
    return [w for w in _words(s) if w not in _STOP and (len(w) > 1 or w.isdigit())]


def _squash(s: str) -> str:
    return "".join(_words(re.sub(r"^\s*the\s+", "", str(s).strip(), flags=re.I)))


def _domain_keys(url: str) -> List[str]:
    host = (urlparse(url if "//" in str(url) else "//" + str(url)).hostname or "").lower()
    host = re.sub(r"^(www|m|amp)\.", "", host)
    if not host:
        return []
    labels = host.split(".")
    core = labels[-3] if len(labels) >= 3 and labels[-2] in ("co", "com", "org", "gov", "ac", "net") else labels[-2] if len(labels) >= 2 else labels[0]
    return [core, "".join(labels)]


def outlet_matches(outlet: str, source: Dict[str, Any]) -> bool:
    """The outlet name equals or contains (or is contained in) the source's publisher or URL domain, ignoring case, 'The ' and dots ('bbc.co.uk' ~ 'BBC News')."""
    o = _squash(outlet)
    if len(o) < 2:
        return False
    initials = "".join(w[0] for w in _words(re.sub(r"^\s*the\s+", "", outlet, flags=re.I)))
    keys = [k for k in [_squash(source.get("publisher") or "")] + [_squash(k) for k in _domain_keys(str(source.get("url") or ""))] if k]
    for k in keys:
        short, long_ = sorted((o, k), key=len)
        if len(short) >= 3 and short in long_:
            return True
        if o == k:
            return True
        if len(initials) >= 3 and (k == initials or k.startswith(initials)):   # 'New York Times' ~ nytimes.com
            return True
    return False


def _title_variants(title: str, outlet: str) -> List[str]:
    out = [str(title)]
    parts = re.split(r"\s+[|\-–—:]\s+", str(title))
    if len(parts) > 1:   # 'Headline - BBC News': the trailing outlet tag is not part of the headline
        out.append(" - ".join(parts[:-1]))
        out.append(" - ".join(parts[1:]))
    return out


def text_matches_title(text: str, title: str, outlet: str = "") -> bool:
    h = _content(text)
    if len(h) < HEADLINE_MIN_SHARED:
        return False
    for t in (_content(v) for v in _title_variants(title, outlet)):
        if not t:
            continue
        shared = set(h) & set(t)
        nums_h = {w for w in h if any(c.isdigit() for c in w)}
        if len(shared) >= HEADLINE_MIN_SHARED and len(shared) / len(set(h)) >= HEADLINE_COVER_H and len(shared) / len(set(t)) >= HEADLINE_COVER_T and nums_h <= set(t):
            return True
    return False


def _year(s: Any) -> Optional[str]:
    m = re.search(r"\b(19|20)\d{2}\b", str(s or ""))
    return m.group(0) if m else None


def verify_headline(item: Dict[str, Any], sources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The source this headline traces to (outlet matches, title overlaps, and the year agrees when both are known), else None."""
    for s in sources or []:
        if not isinstance(s, dict) or not outlet_matches(item["outlet"], s) or not text_matches_title(item["text"], str(s.get("title") or ""), item["outlet"]):
            continue
        sy, hy = _year(s.get("date") or s.get("published") or s.get("published_at")), _year(item.get("date"))
        if sy and hy and sy != hy:
            continue
        return s
    return None


def sanitize_headline(p: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for h in (p.get("headlines") or []) if isinstance(p.get("headlines"), list) else []:
        if not isinstance(h, dict):
            continue
        text, outlet = clean(h.get("text"), 10_000), clean(h.get("outlet"), 40)
        if not text or not outlet or len(text) > 140:   # a real headline is never shortened: too long means it is not copied as it is, so it is not used
            continue
        it = {"text": text, "outlet": outlet, "date": clean(h.get("date"), 20)}
        src = clean(h.get("source"), 60)    # set by prepare: the verified source's domain
        if src:
            it["source"] = src
        if all(it["text"].lower() != o["text"].lower() for o in items):
            items.append(it)
    if not items:
        raise ValueError("headline needs at least one headline with text and outlet")
    return {"headlines": items[:3]}


def prepare_headline(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    clean_props = sanitize_headline(props)
    kept = []
    for it in clean_props["headlines"]:
        src = verify_headline(it, ctx.sources)
        if src is None:
            continue
        host = (_domain_keys(str(src.get("url") or "")) or [""])[0]
        full = re.sub(r"^(www|m|amp)\.", "", (urlparse(str(src.get("url") or "")).hostname or "")) or host
        kept.append({**it, **({"source": clean(full or src.get("publisher"), 60)} if (full or src.get("publisher")) else {})})
    if not kept:
        raise ValueError("no headline traces to a cited source")
    return {"headlines": kept}


def headline_anchors(p: Dict[str, Any]) -> List[str]:
    return [h["text"] for h in p.get("headlines") or []]


def headline_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(p.get("headlines") or []), dur, p.get("cues"), first=0.12, last=0.7)


def draw_headline(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [h for h in props.get("headlines") or [] if isinstance(h, dict)][:3]
    if not items:
        return
    n = len(items)
    top, bottom = CONTENT_TOP + 50, ctx.bottom - 20
    gap = 24
    avail = bottom - top
    h_card = min(500.0 if n == 1 else 330.0, (avail - gap * (n - 1)) / n)
    y0 = top + (avail - (h_card * n + gap * (n - 1))) / 2
    start = {1: 92, 2: 62, 3: 54}[n]
    times = reveal_times(n, dur, props.get("cues"), first=0.12, last=0.7)
    x, w = 140.0, 1640.0
    left_w = 340.0 if n == 1 else 300.0 if n == 2 else 250.0
    for i, it in enumerate(items):
        p = progress(lt, times[i], 0.6)
        if p <= 0:
            continue
        a, s = ease_out_cubic(p * 1.6), ease_out_cubic(p)
        y = y0 + i * (h_card + gap) + (1 - s) * 44
        cv.card(x, y, w, h_card, th, r=30, alpha=a)
        pad = 34 if n < 3 else 24
        cv.rrect(x + 26, y + pad, 10, h_card - 2 * pad, 5, fill=with_alpha(th.accent, a))
        lx = x + 62
        # outlet and date, left column
        osize, olines = cv.fit_text(it["outlet"], "bold", left_w - 20, 130, 34 if n == 3 else 40 if n == 2 else 46, 26)
        ty = y + pad + 2
        for k, line in enumerate(olines[:2]):
            cv.text(lx, ty + k * osize * 1.18, line, "bold", osize, with_alpha(th.accent, a))
        if it.get("date"):
            cv.text(lx, ty + len(olines[:2]) * osize * 1.18 + 12, it["date"], "regular", 30, with_alpha(th.muted, a))
        # the headline itself, serif, as large as fits
        rx = lx + left_w + 24
        cv.line([(rx - 24, y + pad + 4), (rx - 24, y + h_card - pad - 4)], with_alpha(th.muted, 0.35 * a), 2, round_caps=False)
        rw = x + w - 44 - rx
        rh = h_card - 2 * pad - (38 if n < 3 else 30)
        size, lines, first = float(start), [], None
        while size >= 30:
            lines = serif_wrap(cv, it["text"], size, rw)
            if len(lines) * size * 1.2 <= rh:
                first = first or (size, lines)
                if len(lines) == 1 or len(lines[-1].split()) >= 2:   # no one-word last line
                    break
            size -= 3
        if size < 30 and first:
            size, lines = first
        size = max(size, 30.0)
        lh = size * 1.2
        block = len(lines) * lh
        sy = y + pad + (rh - block) / 2
        for k, line in enumerate(lines):
            serif_text(cv, rx, sy + k * lh, line, size, with_alpha(th.text, ease_out_cubic(progress(lt, times[i] + 0.1 + k * 0.08, 0.5))))
        credit = f"Source: {it.get('source') or it['outlet']}"
        cv.text(x + w - 44, y + h_card - pad + 6, credit, "regular", 24, with_alpha(th.muted, ease_out_cubic(progress(lt, times[i] + 0.4, 0.5)) * a), anchor="rb")


# ===================================================================================================== dialogue
def sanitize_dialogue(p: Dict[str, Any]) -> Dict[str, Any]:
    turns: List[Dict[str, str]] = []
    seen: Dict[str, str] = {}
    for t in (p.get("turns") or []) if isinstance(p.get("turns"), list) else []:
        if not isinstance(t, dict):
            continue
        sp, text = clean(t.get("speaker"), 16), clean(t.get("text"), 120)
        if not sp or not text:
            continue
        key = sp.lower()
        if key not in seen and len(seen) >= 3:   # a fourth voice is dropped, the others keep their order
            continue
        sp = seen.setdefault(key, sp)
        turns.append({"speaker": sp, "text": text})
    if len(turns) < 2 or len(seen) < 2:
        raise ValueError("dialogue needs 2+ turns from at least 2 speakers")
    return {"turns": turns[:6]}


def dialogue_anchors(p: Dict[str, Any]) -> List[str]:
    return [t["text"] for t in p.get("turns") or []]


def dialogue_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(p.get("turns") or []), dur, p.get("cues"), first=0.12, last=0.75)


def _speakers(turns) -> List[str]:
    out: List[str] = []
    for t in turns:
        if t["speaker"].lower() not in [o.lower() for o in out]:
            out.append(t["speaker"])
    return out


def _dialogue_layout(cv: Canvas, turns, avail: float):
    """Largest text size at which every bubble fits; returns (size, rows[{lines, w, h, label}], total height)."""
    names = [s.lower() for s in _speakers(turns)]
    size = 50.0
    while True:
        rows, total, prev = [], 0.0, None
        for t in turns:
            lines = cv.wrap(t["text"], "regular", size, 1150)[:4]
            tw = max(cv.measure(l, "regular", size) for l in lines)
            label = t["speaker"].lower() != prev
            h = len(lines) * size * 1.3 + 28
            rows.append({"lines": lines, "w": tw + 56, "h": h, "label": label, "side": names.index(t["speaker"].lower()) % 2})
            total += h + (28 if label else 0) + 14
            prev = t["speaker"].lower()
        if total - 14 <= avail or size <= 26:
            return size, rows, total - 14
        size -= 2


def draw_dialogue(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    turns = [t for t in props.get("turns") or [] if isinstance(t, dict)][:6]
    if not turns:
        return
    names = [s.lower() for s in _speakers(turns)]
    pal = [th.accent, th.accent2, hue_shift(th.accent, 0.36)]
    top, bottom = CONTENT_TOP + 20, ctx.bottom - 10
    size, rows, total = _dialogue_layout(cv, turns, bottom - top)
    times = reveal_times(len(turns), dur, props.get("cues"), first=0.12, last=0.75)
    y0 = top + max(0.0, (bottom - top - total) / 2)
    ys, y = [], y0
    for r in rows:
        ys.append(y + (28 if r["label"] else 0))
        y += r["h"] + (28 if r["label"] else 0) + 14
    # chat-like scroll, only if even the smallest text does not fit
    offs = [max(0.0, ys[k] + rows[k]["h"] - bottom) for k in range(len(rows))]
    off = 0.0
    for k in range(len(rows)):
        prev = offs[k - 1] if k else 0.0
        off = prev + (offs[k] - prev) * ease_in_out_cubic(progress(lt, times[k], 0.45)) if lt >= times[k] else off
        if lt < times[k]:
            break
    av = 80.0
    for k, t in enumerate(turns):
        r = rows[k]
        col = pal[names.index(t["speaker"].lower())]
        tcol = on_color(col)
        by = ys[k] - off
        if by + r["h"] < top - 40:
            continue
        fade = min(1.0, max(0.0, (by + r["h"] - top + 20) / 120.0)) if off > 0 else 1.0
        left = r["side"] == 0
        ax = 140 + av / 2 if left else 1780 - av / 2
        bx = 140 + av + 20 if left else 1780 - av - 20 - r["w"]
        # typing dots just before the bubble pops
        dot_t0 = max(0.0, times[k] - 0.6)
        if times[k] > 0.12 and dot_t0 <= lt < times[k]:
            da = min(1.0, (lt - dot_t0) / 0.12) * fade
            dw = 120.0
            dx = 140 + av + 20 if left else 1780 - av - 20 - dw
            cv.rrect(dx, by, dw, 66, 30, fill=with_alpha(col, 0.9 * da))
            for j in range(3):
                bounce = max(0.0, math.sin(lt * 10 - j * 0.9)) * 7
                cv.ellipse(dx + dw / 2 + (j - 1) * 28, by + 33 - bounce, 8, 8, fill=with_alpha(tcol, da))
            _avatar(cv, ax, by + av / 2, av, t["speaker"], col, tcol, da)
        p = progress(lt, times[k], 0.4)
        if p <= 0:
            continue
        a = ease_out_cubic(p * 2) * fade
        sc = max(0.05, ease_out_back(p, 1.7))
        w, h = r["w"] * sc, r["h"] * sc
        x = bx if left else bx + r["w"] - w
        if r["label"]:
            cv.text(bx + (4 if left else r["w"] - 4), by - 28, t["speaker"], "semibold", 24, with_alpha(col if th.name != "paper" else col, a), anchor="la" if left else "ra")
        cv.shadow(x, by, w, h, 30, blur=14, dy=8, alpha=th.shadow_alpha * 0.7 * a)
        cv.rrect(x, by, w, h, 30, fill=with_alpha(col, a))
        cv.rrect(x if left else x + w - 40, by, 40, 40, 10, fill=with_alpha(col, a))   # the corner nearest the speaker is squarer, like a chat tail
        for li, line in enumerate(r["lines"]):
            if sc > 0.85:
                cv.text(bx + 28, by + 14 + li * size * 1.3, line, "regular", size, with_alpha(tcol, a))
        _avatar(cv, ax, by + av / 2, av, t["speaker"], col, tcol, a)


def _avatar(cv: Canvas, cx: float, cy: float, d: float, name: str, col, tcol, a: float) -> None:
    cv.ellipse(cx, cy, d / 2, d / 2, fill=with_alpha(col, a), outline=with_alpha((255, 255, 255), 0.85 * a), width=3)
    cv.text(cx, cy + 1, (name.strip()[:1] or "?").upper(), "bold", d * 0.5, with_alpha(tcol, a), anchor="mm")


# ===================================================================================================== icons
def sanitize_icons(p: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for it in (p.get("items") or []) if isinstance(p.get("items"), list) else []:
        if not isinstance(it, dict):
            continue
        label = clean(it.get("label"), 24)
        if not label:
            continue
        o = {"icon": clean(it.get("icon") or label, 30), "label": label}
        sub = clean(it.get("sub"), 40)
        if sub:
            o["sub"] = sub
        items.append(o)
    if len(items) < 2:
        raise ValueError("icons needs 2+ items with a label")
    out: Dict[str, Any] = {"items": items[:6]}
    title = clean(p.get("title"), 50)
    if title:
        out["title"] = title
    return out


def icons_anchors(p: Dict[str, Any]) -> List[str]:
    return [i["label"] for i in p.get("items") or []]


def icons_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(p.get("items") or []), dur, p.get("cues"), first=0.12, last=0.75)


def draw_icons(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [i for i in props.get("items") or [] if isinstance(i, dict)][:6]
    if not items:
        return
    n = len(items)
    top = heading(cv, th, str(props.get("title", "")), lt, y=CONTENT_TOP + 20) + 10 if props.get("title") else CONTENT_TOP + 50
    bottom = ctx.bottom - 10
    cols = n if n <= 4 else 3
    rows = 1 if n <= 4 else 2
    gap = 32.0
    area_w = 1640.0
    card_w = min(520.0 if n <= 3 else 440.0, (area_w - gap * (cols - 1)) / cols)
    card_h = min(620.0, (bottom - top - gap * (rows - 1)) / rows)
    times = reveal_times(n, dur, props.get("cues"), first=0.12, last=0.75)
    gx0 = 960 - (card_w * cols + gap * (cols - 1)) / 2
    gy0 = top + ((bottom - top) - (card_h * rows + gap * (rows - 1))) / 2
    for i, it in enumerate(items):
        p = progress(lt, times[i], 0.55)
        if p <= 0:
            continue
        r, c = divmod(i, cols)
        if rows == 2 and r == 1 and n - cols < cols:   # a short last row is centred
            c_off = (cols - (n - cols)) * (card_w + gap) / 2
        else:
            c_off = 0.0
        x = gx0 + c * (card_w + gap) + c_off
        y = gy0 + r * (card_h + gap)
        a, s = ease_out_cubic(p * 1.8), max(0.05, ease_out_back(p, 1.5))
        cw, ch = card_w * (0.9 + 0.1 * s), card_h * (0.9 + 0.1 * s)
        cx, cy = x + card_w / 2, y + card_h / 2 + (1 - ease_out_cubic(p)) * 24
        cv.card(cx - cw / 2, cy - ch / 2, cw, ch, th, r=30, alpha=a)
        # inside: icon disc, label, sub (the disc takes what the text leaves)
        lsize, llines = cv.fit_text(it["label"], "bold", card_w - 44, 110, 44, 30)
        llines = llines[:2]
        slines = cv.wrap(it.get("sub", ""), "regular", 28, card_w - 44)[:2] if it.get("sub") else []
        text_h = len(llines) * lsize * 1.18 + (len(slines) * 34 + 8 if slines else 0)
        disc = max(80.0, min(card_h - 2 * 28 - 22 - text_h, card_w * 0.6, 320.0))
        block = disc + 22 + text_h
        by = cy - block / 2
        dcx, dcy = cx, by + disc / 2
        cv.ellipse(dcx, dcy, disc / 2 * s, disc / 2 * s, fill=with_alpha(th.accent, 0.16 * a), outline=with_alpha(th.accent, 0.55 * a), width=3)
        name, _ = _pm_icons.find_icon(it.get("icon") or it["label"])
        _pm_icons.draw_icon(cv, dcx, dcy, name, disc * 0.52, with_alpha(th.accent, a), scale=s)
        ty = by + disc + 22
        for k, line in enumerate(llines):
            cv.text(cx, ty + k * lsize * 1.18, line, "bold", lsize, with_alpha(th.text, a), anchor="ma")
        ty += len(llines) * lsize * 1.18 + 8
        for k, line in enumerate(slines):
            cv.text(cx, ty + k * 34, line, "regular", 28, with_alpha(th.muted, a), anchor="ma")


# ===================================================================================================== annotated_image
def _unit(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 3) if 0.0 <= f <= 1.0 else None


def sanitize_annotated(p: Dict[str, Any]) -> Dict[str, Any]:
    q = clean(p.get("image_query"), 80)
    if len(q) < 2:
        raise ValueError("annotated_image needs an image_query")
    pins = []
    for pin in (p.get("pins") or []) if isinstance(p.get("pins"), list) else []:
        if isinstance(pin, dict) and clean(pin.get("label"), 30) and _unit(pin.get("x")) is not None and _unit(pin.get("y")) is not None:
            pins.append({"label": clean(pin["label"], 30), "x": _unit(pin["x"]), "y": _unit(pin["y"])})
    pins = pins[:4]
    labels: List[str] = []
    for lab in (p.get("labels") or []) if isinstance(p.get("labels"), list) else []:
        s = clean(lab, 30)
        if s and s.lower() not in [x.lower() for x in labels]:
            labels.append(s)
    labels = [x["label"] for x in pins] if pins else labels[:4]
    if len(labels) < (1 if pins else 2):
        raise ValueError("annotated_image needs 2+ labels")
    out: Dict[str, Any] = {"image_query": q, "alt": clean(p.get("alt"), 70) or q, "labels": labels}
    if pins:
        out["pins"] = pins
    asset, credit = clean(p.get("asset"), 300), clean(p.get("credit"), 90)
    if asset:
        out["asset"] = asset
    if credit:
        out["credit"] = credit
    return out


def annotated_anchors(p: Dict[str, Any]) -> List[str]:
    return [x["label"] for x in p["pins"]] if p.get("pins") else list(p.get("labels") or [])


def annotated_cues(p: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(annotated_anchors(p)), dur, p.get("cues"), first=0.25, last=0.75)


def prepare_annotated(props: Dict[str, Any], ctx: PrepareCtx) -> Dict[str, Any]:
    """Fetch the photograph exactly as an image scene does (handlers.beat_handler.make_photo), then ask the small vision model where each label is.
    No photograph -> raise (fallback). A photograph but no label two looks agree on -> the photo alone (pins empty): the scene then draws as a plain image,
    which is the honest fallback and keeps the licensed photograph that was already paid for."""
    import logging

    from ... import awsio, llm
    from ...handlers.beat_handler import make_photo
    from . import _pm_vision

    p = sanitize_annotated(props)
    beat = {"id": ctx.beat_id, "narration": ctx.narration, "scene": {"type": "image", "props": {"image_query": p["image_query"], "alt": p["alt"]}}}
    got = make_photo({}, beat, ctx.video_id, "cost_usd")
    if not got.get("asset"):
        raise RuntimeError("no photograph found for the annotated image")
    patch: Dict[str, Any] = {"asset": got["asset"], "pins": []}
    if got.get("credit"):
        patch["credit"] = got["credit"]
    if got.get("ledger"):
        patch["ledger"] = got["ledger"]    # the licence record (see the report: timeline_handler must read it to credit the photo in the description)
    try:
        found, cost = _pm_vision.locate(awsio.get_bytes(got["asset"]), p["labels"], p["alt"], llm.complete, model=llm.REVIEW_MODEL)
        if cost:
            from ... import costs
            costs.add_cost(ctx.video_id, cost, field="cost_usd", part="stock")
        patch["pins"] = [{"label": lab, "x": found[lab][0], "y": found[lab][1]} for lab in p["labels"] if lab in found]
    except Exception:  # noqa: BLE001
        logging.exception("annotated_image: locating the labels failed; showing the photograph alone")
    patch["labels"] = [x["label"] for x in patch["pins"]] or p["labels"]
    return patch


def annotated_fallback(props: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    q = clean(props.get("image_query"), 80)
    return "image", {"image_query": q, "alt": clean(props.get("alt"), 70) or q, "ken_burns": "in"}


_PHOTO_CACHE: Dict[Tuple[int, int, int], Image.Image] = {}


def _photo_sprite(cv: Canvas, src: Image.Image, w: float, h: float) -> Image.Image:
    key = (id(src), cv._s(w), cv._s(h))
    if key not in _PHOTO_CACHE:
        if len(_PHOTO_CACHE) > 4:
            _PHOTO_CACHE.clear()
        im = src.convert("RGB").resize((cv._s(w), cv._s(h)), Image.BILINEAR)
        _PHOTO_CACHE[key] = im
    return _PHOTO_CACHE[key]


def draw_annotated(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    from ..viz_scenes import draw_image

    src = ctx.resolve_image(str(props["asset"])) if props.get("asset") else None
    pins = [x for x in props.get("pins") or [] if isinstance(x, dict)][:4]
    if src is not None and not pins and props.get("asset") and "pins" in props:   # located nothing: the photograph alone
        draw_image(cv, {"asset": props["asset"], "alt": props.get("alt", ""), "credit": props.get("credit", ""), "ken_burns": "in"}, lt, dur, th, ctx)
        return
    labels = [x["label"] for x in pins] if pins else [str(x) for x in props.get("labels") or []][:4]
    n = len(labels)
    if not n:
        return
    top, bottom = CONTENT_TOP + 30, ctx.bottom - 40
    bx0, bx1 = 100.0, 1230.0
    if src is not None:
        sc = min((bx1 - bx0) / src.width, (bottom - top) / src.height)
        pw, ph = src.width * sc, src.height * sc
    else:
        pw, ph = bx1 - bx0, bottom - top
    px0 = bx0 + (bx1 - bx0 - pw) / 2
    py0 = top + (bottom - top - ph) / 2
    fa = ease_out_cubic(progress(lt, 0.0, 0.55))
    r_px = 26
    if src is not None:
        cv.shadow(px0, py0, pw, ph, r_px, alpha=th.shadow_alpha * fa)
        sprite = _photo_sprite(cv, src, pw, ph)
        mask = Image.new("L", sprite.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, sprite.width - 1, sprite.height - 1], cv._s(r_px), fill=int(255 * fa))
        cv.im.paste(sprite, (cv._s(px0), cv._s(py0)), mask)
        credit = str(props.get("credit") or "").strip()
        if credit:
            cv.text(px0 + pw, py0 + ph + 10, credit[:90], "regular", 22, with_alpha(th.muted, fa), anchor="ra")
    else:   # no photograph (a preview, or not yet fetched): a quiet placeholder so the legend still reads
        cv.card(px0, py0, pw, ph, th, r=r_px, alpha=fa)
        from . import _pm_icons as ic
        ic.draw_icon(cv, px0 + pw / 2, py0 + ph / 2 - 30, "image", 150, with_alpha(th.muted, 0.6 * fa))
        cv.text(px0 + pw / 2, py0 + ph / 2 + 80, str(props.get("alt") or ""), "regular", 32, with_alpha(th.muted, fa), anchor="ma")
    times = reveal_times(n, dur, props.get("cues"), first=0.25, last=0.75)
    num_col = on_color(th.accent)
    # legend, right column
    lx, lw = 1290.0, 500.0
    row_h = 118.0
    ly0 = (top + bottom) / 2 - n * row_h / 2
    for i, lab in enumerate(labels):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        a, s = ease_out_cubic(p * 1.6), ease_out_back(p, 1.6)
        y = ly0 + i * row_h + row_h / 2
        slide = (1 - ease_out_cubic(p)) * 40
        cv.card(lx + slide, y - 46, lw, 92, th, r=24, alpha=a, shadow=False)
        _pin_chip(cv, lx + 48 + slide, y, 27, i + 1, th, num_col, a)
        size, lines = cv.fit_text(lab, "semibold", lw - 120, 80, 38, 26)
        lh = size * 1.18
        for k, line in enumerate(lines[:2]):
            cv.text(lx + 92 + slide, y - (len(lines[:2]) - 1) * lh / 2 + k * lh, line, "semibold", size, with_alpha(th.text, a), anchor="lm")
        if pins:
            x, yy = px0 + pins[i]["x"] * pw, py0 + pins[i]["y"] * ph
            pulse = progress(lt, times[i] + 0.15, 0.9)
            if 0 < pulse < 1:
                cv.ellipse(x, yy, 26 + 40 * pulse, 26 + 40 * pulse, outline=with_alpha(th.accent2 if th.name != "paper" else th.accent, 0.8 * (1 - pulse)), width=4)
            cv.ellipse(x, yy + 5, 30 * s, 30 * s, fill=(0, 0, 0, int(70 * a)))
            _pin_chip(cv, x, yy, 28 * s, i + 1, th, num_col, a)


def _pin_chip(cv: Canvas, cx: float, cy: float, r: float, num: int, th: Theme, num_col, a: float) -> None:
    if r <= 1:
        return
    cv.ellipse(cx, cy, r, r, fill=with_alpha(th.accent, a), outline=with_alpha((255, 255, 255), a), width=4)
    cv.text(cx, cy + 1, str(num), "bold", r * 1.15, with_alpha(num_col, a), anchor="mm")


# ===================================================================================================== registration
ELEMENTS = [
    Element(
        name="headline", family="People and sources",
        doc=("- headline: {headlines: 1-3 [{text (<=140), outlet (<=40), date (<=20, e.g. '12 Nov 2026')}]}. A news-headline card per item, stacked in order. Use when the "
             "narration cites what a named outlet reported. Only headlines that appear in the grounding notes with their outlet and date; never invented or rephrased (copy "
             "the title exactly). Never for opinion, for a claim with no source in the notes, or for more than 3."),
        sanitize=sanitize_headline, draw=draw_headline, cues=headline_cues, anchors=headline_anchors, prepare=prepare_headline,
        samples=[
            {"headlines": [{"text": "Central bank holds interest rates steady as inflation cools", "outlet": "Reuters", "date": "12 Nov 2026"}]},
            {"headlines": [{"text": "Ministers agree new flood defence funding for coastal towns", "outlet": "BBC News", "date": "3 Nov 2026"},
                           {"text": "Coastal towns welcome flood funding but warn it may arrive too late", "outlet": "The Guardian", "date": "4 Nov 2026"},
                           {"text": "Insurers say flood-prone homes will cost more to cover next year", "outlet": "Financial Times", "date": "6 Nov 2026"}]},
        ],
    ),
    Element(
        name="dialogue", family="People and sources",
        doc=("- dialogue: {turns: 2-6 [{speaker (<=16), text (<=120)}]}, at most 3 distinct speakers. Chat bubbles, one colour and initial per speaker, popping in order. Use when "
             "two or three voices really talk: a question and its answer, an interview, an argument, a myth and its reply. Never for one speaker, for text nobody says, or "
             "to put invented words in a real person's mouth."),
        sanitize=sanitize_dialogue, draw=draw_dialogue, cues=dialogue_cues, anchors=dialogue_anchors,
        samples=[
            {"turns": [{"speaker": "Maya", "text": "Why does the moon look bigger near the horizon?"}, {"speaker": "Leo", "text": "It is an illusion. The moon is the same size all night."},
                       {"speaker": "Maya", "text": "So my camera would not see a difference?"}]},
            {"turns": [{"speaker": "Host", "text": "Is it true that we only use ten percent of our brains?"}, {"speaker": "Dr. Okafor", "text": "No. Brain scans show activity across nearly all regions each day."},
                       {"speaker": "Host", "text": "Then where did the idea come from?"}, {"speaker": "Dr. Okafor", "text": "Mostly from misquoted early twentieth-century self-help books."},
                       {"speaker": "Student", "text": "Can training still make a brain work better, though?"}, {"speaker": "Dr. Okafor", "text": "Yes, practice strengthens the connections you use, at any age."}]},
        ],
    ),
    Element(
        name="icons", family="Media",
        doc=("- icons: {title (<=50, optional), items: 2-6 [{icon (one plain English word, e.g. lock, cloud, heart, rocket, money), label (<=24), sub (<=40, optional)}]}. Large "
             "icons with labels, revealed in order. Use when the narration names 2-6 features, categories or steps that each have a familiar symbol, "
             "and ONLY when every item has an obviously fitting everyday symbol (lock, cloud, clock, money, map pin, heart). Never for named artworks, people, places or abstract ideas (use bullets), "
             "numbers, long sentences or logos."),
        sanitize=sanitize_icons, draw=draw_icons, cues=icons_cues, anchors=icons_anchors,
        samples=[
            {"title": "Why people love it", "items": [{"icon": "rocket", "label": "Fast", "sub": "Ready in seconds"}, {"icon": "lock", "label": "Private", "sub": "Your data stays yours"},
                                                      {"icon": "money", "label": "Affordable"}]},
            {"items": [{"icon": "cloud", "label": "Cloud storage", "sub": "Files anywhere"}, {"icon": "heart", "label": "Health"}, {"icon": "brain", "label": "Learning", "sub": "Adapts to you"},
                       {"icon": "handshake", "label": "Community"}, {"icon": "xylophone", "label": "Music", "sub": "Fuzzy word falls back"}, {"icon": "zzzz", "label": "Anything"}]},
        ],
    ),
    Element(
        name="annotated_image", family="Media",
        doc=("- annotated_image: {image_query (2-6 words describing a real photograph), alt (<=70), labels: 2-4 (<=30 chars each, parts clearly visible in that picture)}. A real "
             "photograph with numbered pins on the named parts and a legend. Use when the narration points out parts of one object or place. Never for parts that may "
             "not be visible, for people's faces or names, for abstract ideas (use diagram), or more than 3 per video."),
        sanitize=sanitize_annotated, draw=draw_annotated, cues=annotated_cues, anchors=annotated_anchors, prepare=prepare_annotated, fallback=annotated_fallback,
        max_per_video=3, min_seconds=5.0,
        samples=[
            {"image_query": "bicycle close up", "alt": "A bicycle seen from the side", "labels": ["Front wheel", "Handlebars", "Saddle"]},
            {"image_query": "old stone bridge river", "alt": "A stone arch bridge over a river", "labels": ["Arch", "Parapet"],
             "pins": [{"label": "Arch", "x": 0.45, "y": 0.62}, {"label": "Parapet", "x": 0.7, "y": 0.35}]},
        ],
    ),
]
