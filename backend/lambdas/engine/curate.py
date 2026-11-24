"""Videos built from the user's OWN photos (up to 100): understand the photos cheaply, then understand the story, before any script is written.

Cost is the design constraint, so the pictures are shown to a model as few times as possible:
  1. CATALOGUE  the photos are laid on contact sheets of 10, each numbered in its corner, and a small vision model describes every numbered photo (one image per
                10 photos: 100 photos = 10 images, in parallel). Nothing downstream ever sees the pictures again.
  2. STORY      one text-only call to the writing model reads the person's request and the numbered captions and works out what the photos are about, what the video
                is for, how to order them, how to group them into chapters and "moments" (1 photo, or 2-5 that belong together and are shown as a gallery), and which
                to leave out (duplicates, blurred, surplus for the length asked).
  3. The director then writes one beat per moment, referring to photos by id.
A failure at any stage degrades (a plain caption, a mechanical grouping) and never blocks the video.
"""
import io
import json
import logging
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageOps

from .canvas import load_font

PER_SHEET = 10
COLS = 5
CELL_W, CELL_H = 300, 225
GAP = PAD = 6
SECONDS_PER_PHOTO = 3.5       # the least a photo stays on screen on average (a gallery shows several in one beat)
SHARE_FOR_PHOTOS = 0.8        # the rest of the video's time is for narration without a photo
MAX_PER_MOMENT = 5
QUALITIES = ("good", "ok", "poor")
SUBJECTS = ("landmark", "landscape", "city", "food", "people", "pet", "indoor", "event", "document", "object", "other")


def max_used(minutes: float) -> int:
    """The most photos a video of this length can show: about SECONDS_PER_PHOTO each over most of its time."""
    return max(3, int(float(minutes) * 60 * SHARE_FOR_PHOTOS / SECONDS_PER_PHOTO))


def number(pid: str) -> int:
    return int(pid[1:])


# ----------------------------------------------------------------------------- 1. the catalogue
def make_sheets(photos: List[Dict[str, Any]], thumbs: List[bytes]) -> List[Tuple[List[str], bytes]]:
    """Contact sheets of PER_SHEET photos, each cell carrying the photo's number (P37 -> 37). Returns [(ids, jpeg)]."""
    out: List[Tuple[List[str], bytes]] = []
    font = load_font("bold", 26)
    for start in range(0, len(photos), PER_SHEET):
        batch = list(zip(photos[start:start + PER_SHEET], thumbs[start:start + PER_SHEET]))
        rows = math.ceil(len(batch) / COLS)
        w = PAD * 2 + COLS * CELL_W + (COLS - 1) * GAP
        h = PAD * 2 + rows * CELL_H + (rows - 1) * GAP
        sheet = Image.new("RGB", (w, h), (24, 24, 28))
        d = ImageDraw.Draw(sheet)
        for k, (p, raw) in enumerate(batch):
            cx, cy = PAD + (k % COLS) * (CELL_W + GAP), PAD + (k // COLS) * (CELL_H + GAP)
            try:
                im = ImageOps.contain(Image.open(io.BytesIO(raw)).convert("RGB"), (CELL_W, CELL_H))
                sheet.paste(im, (cx + (CELL_W - im.width) // 2, cy + (CELL_H - im.height) // 2))
            except Exception:   # an unreadable thumbnail leaves an empty cell, still numbered
                pass
            label = str(number(p["id"]))
            tw = d.textlength(label, font=font)
            d.rounded_rectangle((cx + 4, cy + 4, cx + 4 + tw + 16, cy + 4 + 34), radius=8, fill=(0, 0, 0))
            d.text((cx + 12, cy + 7), label, font=font, fill=(255, 255, 255))
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=82)
        out.append(([p["id"] for p, _ in batch], buf.getvalue()))
    return out


_SHEET_SYSTEM = (
    "You catalogue a person's OWN photos so a video can be made from them. The image is a contact sheet: every photo has a white number in a black box in its top-left corner. "
    "For EVERY numbered photo return: caption (at most 18 words: what is visible, plain and factual; name a landmark, city or place only when it is clearly recognisable), "
    "place (the recognisable place or landmark name, else \"\"), subject (one of: landmark, landscape, city, food, people, pet, indoor, event, document, object, other), "
    "people (true if a person is visible), quality (good, ok or poor: poor = blurred, very dark, accidental, or a near copy of another photo on this sheet), "
    "similar (numbers of other photos on this sheet that are near duplicates of it, else []), exclude (true ONLY for nudity or sexual content, graphic violence or gore, "
    "identity documents, bank cards or screens showing personal data, hate symbols), reason (short, only when exclude is true). "
    "Never guess names, ages or relationships of people. Use the person's request only to notice what matters; do not invent anything. "
    'Return ONLY JSON: {"photos":[{"n":37,"caption":"...","place":"","subject":"landmark","people":false,"quality":"good","similar":[],"exclude":false,"reason":""}]}'
)


def _json_obj(text: str) -> Optional[Dict[str, Any]]:
    dec, i = json.JSONDecoder(), (text or "").find("{")
    while i >= 0:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return None


def _clean(s: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def describe(sheets: List[Tuple[List[str], bytes]], request: str, ask_vision: Callable[..., str], *, workers: int = 5) -> Dict[str, Dict[str, Any]]:
    """{photo id: row} from one vision call per sheet (in parallel; one retry for a sheet whose answer is unusable). Missing rows get a plain default."""
    def one(item: Tuple[List[str], bytes]) -> Dict[str, Dict[str, Any]]:
        ids, jpeg = item
        nums = [number(i) for i in ids]
        user = f"This sheet shows photos numbered {nums[0]} to {nums[-1]} ({len(ids)} photos). The person's request: {request[:300]}"
        rows: Dict[int, Dict[str, Any]] = {}
        for _ in range(2):
            try:
                obj = _json_obj(ask_vision(_SHEET_SYSTEM, user, [jpeg]))
            except Exception:
                logging.exception("contact sheet %s-%s could not be described", nums[0], nums[-1])
                obj = None
            got = {int(r["n"]): r for r in (obj or {}).get("photos", []) if isinstance(r, dict) and str(r.get("n", "")).isdigit()}
            rows.update(got)
            if all(n in rows for n in nums):
                break
        out: Dict[str, Dict[str, Any]] = {}
        for pid, n in zip(ids, nums):
            r = rows.get(n) or {}
            sim = [f"P{int(x)}" for x in (r.get("similar") or []) if str(x).isdigit() and int(x) in nums and int(x) != n]
            out[pid] = {
                "caption": _clean(r.get("caption"), 160) or "a photo",
                "place": _clean(r.get("place"), 60),
                "subject": r.get("subject") if r.get("subject") in SUBJECTS else "other",
                "people": bool(r.get("people")),
                "quality": r.get("quality") if r.get("quality") in QUALITIES else "ok",
                "similar": sim,
                "exclude": r.get("exclude") is True,
                "reason": _clean(r.get("reason"), 120) or "not suitable",
            }
        return out

    result: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(sheets) or 1))) as ex:
        for part in ex.map(one, sheets):
            result.update(part)
    return result


# ----------------------------------------------------------------------------- 2. the story
def when(taken: str) -> str:
    """'2026-04-12T14:32:00' -> 'Sun 12 Apr 14:32'."""
    import datetime
    try:
        return datetime.datetime.strptime(taken[:19], "%Y-%m-%dT%H:%M:%S").strftime("%a %d %b %H:%M")
    except ValueError:
        return taken


def trip_summary(photos: List[Dict[str, Any]]) -> str:
    """One line about when and where the photos were taken (from the photos' own data), or ''."""
    import datetime
    days: List[datetime.date] = []
    for p in photos:
        try:
            days.append(datetime.datetime.strptime(p["taken"][:10], "%Y-%m-%d").date())
        except (KeyError, ValueError, TypeError):
            pass
    places = list(dict.fromkeys(p["where"].replace("near ", "") for p in photos if p.get("where")))
    bits = []
    if days and len(days) * 2 >= len(photos):
        a, b = min(days), max(days)
        bits.append(f"taken {a.strftime('%d %b %Y')}" + (f" to {b.strftime('%d %b %Y')} ({(b - a).days + 1} days, {len(set(days))} with photos)" if b != a else ""))
    if places:
        bits.append("places from the photos' GPS: " + ", ".join(places[:8]))
    return "; ".join(bits)


def _catalogue_text(photos: List[Dict[str, Any]]) -> str:
    lines = []
    for p in photos:
        bits = [p.get("caption") or "a photo"]
        if p.get("place") and p["place"].lower() not in bits[0].lower():
            bits.append(f"place: {p['place']}")
        bits.append(p.get("subject", "other") + (", people" if p.get("people") else ""))
        if p.get("taken"):
            bits.append("taken " + when(p["taken"]))
        if p.get("where"):
            bits.append("GPS place: " + p["where"])
        if p.get("quality") == "poor":
            bits.append("POOR quality")
        if p.get("similar"):
            bits.append("near-duplicate of " + ", ".join(p["similar"]))
        lines.append(f'{p["id"]}: ' + " | ".join(bits))
    return "\n".join(lines)


def story_system(minutes: float, cap: int) -> str:
    return (
        "You are the story producer for a video made from a person's OWN photos. You get the person's request, the video's length and a numbered catalogue of their photos. "
        "First work out what these photos are about and what the person wants the video to be (a holiday memory, a property tour, a family event, a project...). Then plan the video's moments.\n"
        'Return ONLY JSON: {"story": "2-4 sentences: what the photos are about (who, where, when, only as evident from the captions or the request) and what the video is for", '
        '"voice": "first_person" (the person tells their own trip or event: we, I) or "narrator" (a presenter explains it), "tone": "a few words", "title_idea": "<=60 chars", '
        '"chapters": [{"title": "<=50 chars", "summary": "one sentence", "moments": [{"photos": ["P3"], "role": "opening|establishing|detail|people|climax|transition|closing", '
        '"note": "<=20 words: what this moment shows and why it is here"}]}], "unused": [{"id": "P9", "reason": "duplicate|blurry|off-topic|surplus"}]}\n'
        "Rules:\n"
        "- Every photo appears in exactly one moment or in unused. A moment has 1 to 5 photos: 1 for a standout photo, 2 to 5 for photos of the same subject or place that belong together (they are shown as a gallery).\n"
        "- Order the moments to tell a story: usually the order things happened (use visual clues like daylight and the order the photos were chosen as hints), or by theme when there is no sequence. "
        "Open with a strong, establishing photo and end with a fitting one.\n"
        f"- Group into chapters by place, subject or time: 2 to 8 chapters, fewer for short videos. This video is {minutes:g} minutes, so use at most {cap} photos in total: keep the best of near duplicates, "
        "drop POOR quality photos first, prefer variety and what the request is about; put the rest in unused.\n"
        "- Lines may say when ('taken Sun 12 Apr 14:32') and where ('GPS place: Paris, France') each photo was taken, from the photo's own data. Trust them over visual guesses for ORDER and for PLACE NAMES: order moments by time, "
        "start a new chapter when the day changes, and name places as given. A photo without them is placed by what it shows.\n"
        "- The request decides the emphasis. Never invent names, places, dates or events that the captions and the request do not support; say less rather than guess."
    )


def _fallback_story(photos: List[Dict[str, Any]], cap: int) -> Dict[str, Any]:
    """No model answer: keep the photos in the order given, three to a gallery, ten to a chapter, the best ones if there are too many."""
    chosen = rank_and_trim([p["id"] for p in photos], {p["id"]: p for p in photos}, cap)
    moments = [{"photos": chosen[i:i + 3], "role": "detail", "note": ""} for i in range(0, len(chosen), 3)]
    chapters = [{"title": f"Part {k + 1}" if len(moments) > 4 else "", "summary": "", "moments": moments[i:i + 4]} for k, i in enumerate(range(0, len(moments), 4))]
    return {"story": "", "voice": "narrator", "tone": "", "title_idea": "", "chapters": chapters, "unused": [{"id": p["id"], "reason": "surplus"} for p in photos if p["id"] not in chosen]}


def rank_and_trim(ids: List[str], by_id: Dict[str, Dict[str, Any]], cap: int) -> List[str]:
    """At most `cap` ids, in their given order: poor quality and near-duplicates (of an earlier photo) go first, then the middle thins out evenly; the first and last stay."""
    if len(ids) <= cap:
        return list(ids)
    seen: set = set()

    def score(pos: int, pid: str) -> float:
        p = by_id.get(pid) or {}
        s = {"good": 2.0, "ok": 1.0, "poor": 0.0}.get(p.get("quality", "ok"), 1.0)
        if any(x in seen for x in p.get("similar") or []):
            s -= 1.5
        seen.add(pid)
        return s - 1e-4 * pos   # ties: drop later ones first

    scored = [(score(i, pid), i) for i, pid in enumerate(ids)]
    keep = {0, len(ids) - 1}
    for _, i in sorted((x for x in scored if x[1] not in keep), key=lambda x: (-x[0], x[1]))[: max(0, cap - len(keep))]:
        keep.add(i)
    return [pid for i, pid in enumerate(ids) if i in keep]


def reconcile(story: Dict[str, Any], photos: List[Dict[str, Any]], cap: int) -> Dict[str, Any]:
    """The model's story made safe: only real photo ids, each placed once, 1-5 per moment, no empty chapters, at most `cap` used; photos it forgot go in a last chapter
    (when there is room) or in unused. Always returns a usable story."""
    by_id = {p["id"]: p for p in photos}
    placed: List[str] = []
    chapters: List[Dict[str, Any]] = []
    for ch in story.get("chapters") if isinstance(story.get("chapters"), list) else []:
        if not isinstance(ch, dict):
            continue
        moments = []
        for m in ch.get("moments") if isinstance(ch.get("moments"), list) else []:
            ids = [str(i).strip().upper() for i in (m.get("photos") if isinstance(m, dict) else []) or []]
            ids = [i for i in dict.fromkeys(ids) if i in by_id and i not in placed]
            for k in range(0, len(ids), MAX_PER_MOMENT):
                part = ids[k:k + MAX_PER_MOMENT]
                placed += part
                moments.append({"photos": part, "role": _clean(m.get("role"), 20) or "detail", "note": _clean(m.get("note"), 160)})
        if moments:
            chapters.append({"title": _clean(ch.get("title"), 50), "summary": _clean(ch.get("summary"), 200), "moments": moments})
    if not chapters:
        return _fallback_story(photos, cap)
    left_out = {str(u.get("id", "")).strip().upper() for u in (story.get("unused") or []) if isinstance(u, dict)}   # the model's own decision to leave a photo out stands
    forgotten = [p["id"] for p in photos if p["id"] not in placed and p["id"] not in left_out]
    if forgotten and len(placed) < cap:
        room = forgotten[: cap - len(placed)]
        chapters.append({"title": "More moments", "summary": "", "moments": [{"photos": room[i:i + 3], "role": "detail", "note": ""} for i in range(0, len(room), 3)]})
        placed += room
    flat = [i for ch in chapters for m in ch["moments"] for i in m["photos"]]
    keep = set(rank_and_trim(flat, by_id, cap))
    if len(keep) < len(flat):   # over the length's capacity: thin out
        for ch in chapters:
            for m in ch["moments"]:
                m["photos"] = [i for i in m["photos"] if i in keep]
            ch["moments"] = [m for m in ch["moments"] if m["photos"]]
        chapters = [ch for ch in chapters if ch["moments"]]
    used = {i for ch in chapters for m in ch["moments"] for i in m["photos"]}
    reasons = {str(u.get("id", "")).upper(): _clean(u.get("reason"), 40) for u in (story.get("unused") or []) if isinstance(u, dict)}
    return {
        "story": _clean(story.get("story"), 700), "voice": "first_person" if story.get("voice") == "first_person" else "narrator",
        "tone": _clean(story.get("tone"), 60), "title_idea": _clean(story.get("title_idea"), 60), "chapters": chapters,
        "unused": [{"id": p["id"], "reason": reasons.get(p["id"]) or "surplus"} for p in photos if p["id"] not in used],
    }


def make_story(request: str, minutes: float, photos: List[Dict[str, Any]], ask_text: Callable[[str, str], str]) -> Dict[str, Any]:
    cap = max_used(minutes)
    summary = trip_summary(photos)
    user = (f"The person's request: {request[:500]}\nVideo length: {minutes:g} minutes (use at most {cap} photos)." + (f"\nAbout the photos: {summary}." if summary else "")
            + f"\n\nPhotos:\n{_catalogue_text(photos)}\n\nReturn the JSON now.")
    try:
        raw = _json_obj(ask_text(story_system(minutes, cap), user)) or {}
    except Exception:
        logging.exception("the photo story could not be written; grouping the photos mechanically")
        raw = {}
    return reconcile(raw, photos, cap)


def moments(story: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The story's moments in order, each with its chapter title when it opens a chapter."""
    out = []
    for ch in story.get("chapters") or []:
        for k, m in enumerate(ch["moments"]):
            out.append({**m, **({"chapter": ch["title"]} if k == 0 and ch.get("title") else {})})
    return out


def used_ids(story: Dict[str, Any]) -> List[str]:
    return [i for m in moments(story) for i in m["photos"]]


# ----------------------------------------------------------------------------- the whole stage
def curate(photos: List[Dict[str, Any]], thumbs: List[bytes], request: str, minutes: float, *, ask_vision: Callable[..., str], ask_text: Callable[[str, str], str],
           mode: Optional[str] = None) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Describes every photo (adds caption, place, subject, people, quality, similar in place), drops the ones the safety review excludes (mode as in PHOTO_REVIEW),
    and makes the story. Returns (flagged [{id, reason}], story). `photos` is edited in place to the photos that stay."""
    mode = (mode or os.environ.get("PHOTO_REVIEW", "on")).lower()
    if not photos:
        return [], {"story": "", "voice": "narrator", "tone": "", "title_idea": "", "chapters": [], "unused": []}
    rows = describe(make_sheets(photos, thumbs), request, ask_vision)
    flagged: List[Dict[str, str]] = []
    for p in photos:
        r = rows.get(p["id"]) or {}
        p.update({k: r.get(k) for k in ("caption", "place", "subject", "people", "quality", "similar")})
        if r.get("exclude") and mode != "off":
            flagged.append({"id": p["id"], "reason": r.get("reason") or "not suitable"})
    if mode == "on":
        drop = {f["id"] for f in flagged}
        photos[:] = [p for p in photos if p["id"] not in drop]
    return flagged, (make_story(request, minutes, photos, ask_text) if photos else {"story": "", "voice": "narrator", "tone": "", "title_idea": "", "chapters": [], "unused": []})
