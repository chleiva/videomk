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
SECONDS_PER_PHOTO = 1.0       # on average a photo needs this long on screen when several are shown at once (collages, galleries): a 2-minute video can carry about 85 photos
SHARE_FOR_PHOTOS = 0.85       # the rest of the video's time is for chapter titles and narration without photos
MAX_PER_MOMENT = 9            # a collage shows up to 9 photos together
LAYOUTS = ("single", "sequence", "collage")   # one photo | 2-5 photos one after another (gallery) | 3-9 photos at once (photo_collage)
SESSION_GAP_H = 3.0           # within a day, a pause this long starts a new session (morning, afternoon, evening)
DATED_SHARE = 0.7             # with this share of photos dated, the order and the day groups are decided here, not by the model
QUALITIES = ("good", "ok", "poor")
SUBJECTS = ("landmark", "landscape", "city", "food", "people", "pet", "indoor", "event", "document", "object", "other")


def max_used(minutes: float) -> int:
    """The most photos a video of this length can show: about SECONDS_PER_PHOTO each over most of its time."""
    return max(3, int(float(minutes) * 60 * SHARE_FOR_PHOTOS / SECONDS_PER_PHOTO))


def minutes_for(n_photos: int) -> float:
    """The shortest video that can show all `n_photos` (the apps tell the person when the length they chose is shorter)."""
    return n_photos * SECONDS_PER_PHOTO / SHARE_FOR_PHOTOS / 60.0


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


def photo_day(p: Dict[str, Any]) -> Optional[str]:
    return str(p["taken"])[:10] if p.get("taken") else None


def dated_share(photos: List[Dict[str, Any]]) -> float:
    return sum(1 for p in photos if p.get("taken")) / len(photos) if photos else 0.0


def _dt(taken: str):
    import datetime
    try:
        return datetime.datetime.strptime(taken[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _part_of_day(hour: int) -> str:
    return "night" if hour < 5 or hour >= 22 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def group_photos(photos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Programmatic groups, in time order: one per DAY, split into sessions when two photos are SESSION_GAP_H or more apart; photos without a date form their own group.
    [{"id": "G1", "day": "2026-04-11" | None, "label": "Sat 11 Apr, morning, Paris, France", "ids": [...]}]. Empty when too few photos have a date to trust."""
    if dated_share(photos) < DATED_SHARE:
        return []
    dated = sorted((p for p in photos if _dt(p.get("taken", ""))), key=lambda p: (p["taken"], number(p["id"])))
    groups: List[Dict[str, Any]] = []
    last = None
    for p in dated:
        t = _dt(p["taken"])
        if groups and groups[-1]["day"] == photo_day(p) and (t - last).total_seconds() < SESSION_GAP_H * 3600:
            groups[-1]["ids"].append(p["id"])
        else:
            groups.append({"day": photo_day(p), "t0": t, "ids": [p["id"]]})
        last = t
    by_id = {p["id"]: p for p in photos}
    for g in groups:
        places = [by_id[i]["where"].replace("near ", "") for i in g["ids"] if by_id[i].get("where")]
        top = max(set(places), key=places.count) if places else ""
        g["label"] = f"{g['t0'].strftime('%a %d %b')}, {_part_of_day(g['t0'].hour)}" + (f", {top}" if top else "")
        del g["t0"]
    undated = [p["id"] for p in photos if not _dt(p.get("taken", ""))]
    if undated:
        groups.append({"day": None, "label": "no date", "ids": undated})
    for k, g in enumerate(groups, start=1):
        g["id"] = f"G{k}"
    return groups


def _ranges(ids: List[str]) -> str:
    nums = sorted(number(i) for i in ids)
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"P{start}" if start == prev else f"P{start}-P{prev}"); start = prev = n
    if start is not None:
        out.append(f"P{start}" if start == prev else f"P{start}-P{prev}")
    return ", ".join(out)


def groups_text(groups: List[Dict[str, Any]]) -> str:
    return "\n".join(f"{g['id']}: {g['label']} - {_ranges(g['ids'])} ({len(g['ids'])} photos)" for g in groups)


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


SPARSE_SPP = 7.0    # seconds of screen time per photo from which photos are shown large, one at a time
DENSE_SPP = 3.0     # below this they have to share the screen


def pace(cap: int, n: int) -> Tuple[str, float]:
    """("sparse"|"balanced"|"dense", seconds per photo) for n photos in a video whose capacity is `cap` photos (capacity is 1.2 s of screen per photo, so cap x 1.2 is the time available)."""
    spp = cap * SECONDS_PER_PHOTO / max(1, n)
    return ("sparse" if spp >= SPARSE_SPP else "dense" if spp < DENSE_SPP else "balanced"), round(spp, 1)


def pace_rules(cap: int, n: int) -> str:
    """How to balance full-page photos and collages for this much time per photo: the producer and the director both get it."""
    kind, spp = pace(cap, n)
    head = f"PACE: about {spp:g} seconds of screen time per photo ({kind}). "
    if kind == "sparse":
        return head + ("There is plenty of time, so show the photos LARGE: most moments are a single full-page photo (give a standout its own moment), related shots as short sequences of 2 or 3 "
                       "that follow each other; use a collage only for a real burst of near-identical frames or 4 or more shots of one thing, and at most one moment in six. Do not squeeze photos together to save time you do not need to save.")
    if kind == "balanced":
        return head + ("Mix them: standout photos single and full page (about a third of the moments), sequences of 2 to 4 to tell the story, and collages of 4 to 6 for groups of related photos "
                       "(a market, a hike, a dinner). Vary the rhythm so it does not feel like the same layout repeated.")
    return head + ("Photos must share the screen: collages of 5 to 9 are the main device, with sequences of 2 to 3 for related shots; keep a few standout photos single and full page (about one moment in "
                   "six) so the pace varies and the best pictures get their moment.")


def story_system(minutes: float, cap: int, grouped: bool = False, n: Optional[int] = None) -> str:
    return (
        "You are the story producer for a video made from a person's OWN photos. You get the person's request, the video's length and a numbered catalogue of their photos. "
        "First work out what these photos are about and what the person wants the video to be (a holiday memory, a property tour, a family event, a project...). Then plan the video's moments.\n"
        'Return ONLY JSON: {"story": "2-4 sentences: what the photos are about (who, where, when, only as evident from the captions or the request) and what the video is for", '
        '"voice": "first_person" (the person tells their own trip or event: we, I) or "narrator" (a presenter explains it), "tone": "a few words", "title_idea": "<=60 chars", '
        '"chapters": [{"title": "<=50 chars", "summary": "one sentence", "moments": [{"photos": ["P3"], "layout": "single|sequence|collage", "role": "opening|establishing|detail|people|climax|transition|closing", '
        '"note": "<=20 words: what this moment shows and why it is here"}]}], "unused": [{"id": "P9", "reason": "duplicate|blurry|off-topic|surplus"}]}\n'
        "Rules:\n"
        "- Every photo appears in exactly one moment or in unused. A moment has 1 to 9 photos and a layout: single (1 standout photo), sequence (2 to 5 photos shown one after another), collage (3 to 9 photos of the same "
        "subject, place and day shown TOGETHER on one screen, in a styled layout: use collages to fit many photos into a short video).\n"
        f"- This video is {minutes:g} minutes and can show about {cap} photos. If there are more photos than that, keep the best of near duplicates, drop POOR quality photos first and put the rest in unused; if there "
        "are fewer, use single and sequence moments for the best photos and collages for the rest. Prefer variety and what the request is about.\n"
        + (pace_rules(cap, n) + "\n" if n else "")
        + "- Order the moments to tell a story: usually the order things happened, or by theme when there is no sequence. Open with a strong, establishing photo and end with a fitting one.\n"
        "- Group into chapters by place, subject or time: 2 to 8 chapters, fewer for short videos (a chapter may be a day, a few days or a week).\n"
        "- Lines may say when ('taken Sun 12 Apr 14:32') and where ('GPS place: Paris, France') each photo was taken, from the photo's own data. Trust them over visual guesses for ORDER and for PLACE NAMES. "
        "A photo without them is placed by what it shows.\n"
        + ("- The photos are already grouped by DAY (and by session within a day) below. NEVER put photos of different days in the same moment (a collage or sequence is always from one day), and never reorder "
           "moments against the clock; chapters follow the days in order.\n" if grouped else "")
        + "- The request decides the emphasis. Never invent names, places, dates or events that the captions and the request do not support; say less rather than guess."
    )


def fit_layout(m: Dict[str, Any]) -> Dict[str, Any]:
    """A moment's layout made consistent with its size: 1 photo is single, 2 are a sequence, more than 5 must be a collage, 3 to 5 keep the model's choice (default sequence)."""
    n = len(m["photos"])
    want = m.get("layout") if m.get("layout") in LAYOUTS else "sequence"
    m["layout"] = "single" if n == 1 else "sequence" if n == 2 else "collage" if n > 5 else ("collage" if want == "collage" else "sequence")
    return m


def _per_moment(cap: int, n: int) -> int:
    """How many photos the mechanical grouping puts in one moment for this pace: one when there is time to show each large, up to six when they must share."""
    return {"sparse": 1, "balanced": 3, "dense": 6}[pace(cap, n)[0]]


def _moments_of(ids: List[str], per: int = 6) -> List[Dict[str, Any]]:
    out = []
    for k in range(0, len(ids), per):
        part = ids[k:k + per]
        out.append(fit_layout({"photos": part, "layout": "collage" if per >= 4 else "sequence", "role": "detail", "note": ""}))
    return out


def _fallback_story(photos: List[Dict[str, Any]], cap: int) -> Dict[str, Any]:
    """No model answer: the best photos in the order given (by the clock when dated), a chapter per day, collages of up to six."""
    by_id = {p["id"]: p for p in photos}
    chosen = rank_and_trim([p["id"] for p in photos], by_id, cap)
    groups = [g for g in group_photos([by_id[i] for i in chosen]) if g["ids"]]
    per = _per_moment(cap, len(photos))
    if groups:
        chapters = [{"title": g["label"].split(",")[0] if g["day"] else "", "summary": "", "moments": _moments_of(g["ids"], per)} for g in groups]
    else:
        moments = _moments_of(chosen, per)
        chapters = [{"title": f"Part {k + 1}" if len(moments) > 4 else "", "summary": "", "moments": moments[i:i + 4]} for k, i in enumerate(range(0, len(moments), 4))]
    return {"story": "", "voice": "narrator", "tone": "", "title_idea": "", "chapters": chapters, "unused": [{"id": p["id"], "reason": "surplus"} for p in photos if p["id"] not in chosen]}


def enforce_days(chapters: List[Dict[str, Any]], by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """When most photos have a date the order is decided here, not by the model: a moment never mixes days (it is split at the day change), moments follow the clock,
    and chapters are the model's own chapters cut into contiguous runs in that order (a chapter that comes back later is titled 'continued')."""
    flat = []
    for ci, ch in enumerate(chapters):
        for m in ch["moments"]:
            parts: Dict[Any, List[str]] = {}
            last = None
            for pid in m["photos"]:
                d = photo_day(by_id[pid]) or last
                last = photo_day(by_id[pid]) or last
                parts.setdefault(d, []).append(pid)
            for d, ids in parts.items():
                for k in range(0, len(ids), MAX_PER_MOMENT):
                    flat.append((ci, fit_layout({**m, "photos": ids[k:k + MAX_PER_MOMENT]})))
    def stamp(m: Dict[str, Any]) -> str:
        ts = [by_id[i]["taken"] for i in m["photos"] if by_id[i].get("taken")]
        return min(ts) if ts else ""
    keyed, carry = [], ""
    for n, (ci, m) in enumerate(flat):
        k = stamp(m) or carry          # an undated moment keeps its place among its neighbours
        carry = k or carry
        keyed.append((k or "0", n, ci, m))
    keyed.sort(key=lambda x: (x[0], x[1]))
    runs = 0
    prev_ci = None
    per_chapter: Dict[int, int] = {}
    for _, _, ci, _m in keyed:
        if ci != prev_ci:
            runs += 1
            per_chapter[ci] = per_chapter.get(ci, 0) + 1
            prev_ci = ci
    if max(per_chapter.values(), default=1) > 1 or runs > len(chapters) + 1:
        return _day_chapters([m for _, _, _, m in keyed], by_id)   # the model's chapters cut across the days: the chapters follow the days instead
    out: List[Dict[str, Any]] = []
    for _, _, ci, m in keyed:
        if not out or out[-1]["_ci"] != ci:
            out.append({"_ci": ci, "title": chapters[ci]["title"], "summary": chapters[ci]["summary"], "moments": []})
        out[-1]["moments"].append(m)
    for c in out:
        del c["_ci"]
    return out


def _day_chapters(moments: List[Dict[str, Any]], by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One chapter per day in time order, titled 'Saturday 11 April' (plus the place when known); with more than 8 days, one per week."""
    import datetime
    def day_of(m: Dict[str, Any]) -> str:
        return next((photo_day(by_id[i]) for i in m["photos"] if photo_day(by_id[i])), "")
    days = list(dict.fromkeys(day_of(m) for m in moments))
    weekly = len([d for d in days if d]) > 8
    def key(d: str) -> str:
        if not d or not weekly:
            return d
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        return (dt - datetime.timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
    out: List[Dict[str, Any]] = []
    for m in moments:
        k = key(day_of(m))
        if not out or out[-1]["_k"] != k:
            places = [by_id[i].get("where", "").replace("near ", "") for mm in moments if key(day_of(mm)) == k for i in mm["photos"] if by_id[i].get("where")]
            top = max(set(places), key=places.count) if places else ""
            try:
                d0 = datetime.datetime.strptime(k, "%Y-%m-%d")
                title = (f"Week of {d0.day} {d0.strftime('%B')}" if weekly else d0.strftime("%A ") + f"{d0.day} {d0.strftime('%B')}") + (f" - {top}" if top else "")
            except ValueError:
                title = ""
            out.append({"_k": k, "title": title[:50], "summary": "", "moments": []})
        out[-1]["moments"].append(m)
    for c in out:
        del c["_k"]
    return out


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
                moments.append(fit_layout({"photos": part, "layout": m.get("layout"), "role": _clean(m.get("role"), 20) or "detail", "note": _clean(m.get("note"), 160)}))
        if moments:
            chapters.append({"title": _clean(ch.get("title"), 50), "summary": _clean(ch.get("summary"), 200), "moments": moments})
    if not chapters:
        return _fallback_story(photos, cap)
    left_out = {str(u.get("id", "")).strip().upper() for u in (story.get("unused") or []) if isinstance(u, dict)}   # the model's own decision to leave a photo out stands
    forgotten = [p["id"] for p in photos if p["id"] not in placed and p["id"] not in left_out]
    if forgotten and len(placed) < cap:
        room = forgotten[: cap - len(placed)]
        chapters.append({"title": "More moments", "summary": "", "moments": _moments_of(room, _per_moment(cap, len(photos)))})
        placed += room
    flat = [i for ch in chapters for m in ch["moments"] for i in m["photos"]]
    keep = set(rank_and_trim(flat, by_id, cap))
    if len(keep) < len(flat):   # over the length's capacity: thin out
        for ch in chapters:
            for m in ch["moments"]:
                m["photos"] = [i for i in m["photos"] if i in keep]
                fit_layout(m) if m["photos"] else None
            ch["moments"] = [m for m in ch["moments"] if m["photos"]]
        chapters = [ch for ch in chapters if ch["moments"]]
    if dated_share(photos) >= DATED_SHARE:
        chapters = enforce_days(chapters, by_id)
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
    groups = group_photos(photos)
    user = (f"The person's request: {request[:500]}\nVideo length: {minutes:g} minutes (about {cap} photos fit)." + (f"\nAbout the photos: {summary}." if summary else "")
            + (f"\n\nGroups by day and session (from the photos' own dates):\n{groups_text(groups)}" if groups else "")
            + f"\n\nPhotos:\n{_catalogue_text(photos)}\n\nReturn the JSON now.")
    try:
        raw = _json_obj(ask_text(story_system(minutes, cap, bool(groups), len(photos)), user)) or {}
    except Exception:
        logging.exception("the photo story could not be written; grouping the photos mechanically")
        raw = {}
    return reconcile(raw, photos, cap)


def moments(story: Dict[str, Any]) -> List[Dict[str, Any]]:   # each: photos, layout (single|sequence|collage), role, note, chapter (on the first of a chapter)
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
