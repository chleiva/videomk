"""Icon lookup for the `icons` element: any English word -> the closest Lucide icon (ISC licence, bundled as a font in assets/icons/).

Order: exact icon name, curated synonym, a tag that equals the word, a tag or name that contains it, a fuzzy match on names and tags, and
finally a neutral glyph, so a word the set does not know never fails the scene.
"""
import difflib
import json
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from ._pm_text import ASSETS

FONT_PATH = os.path.join(ASSETS, "icons", "lucide.ttf")
INDEX_PATH = os.path.join(ASSETS, "icons", "lucide_index.json")
NEUTRAL = "sparkles"

# Words a director reaches for that the set names differently (the set's own tags cover most of the rest).
SYNONYMS = {
    "money": "banknote", "cash": "banknote", "dollar": "circle-dollar-sign", "price": "tag", "cost": "receipt", "savings": "piggy-bank", "bank": "landmark",
    "growth": "trending-up", "decline": "trending-down", "profit": "trending-up", "loss": "trending-down", "idea": "lightbulb", "innovation": "lightbulb",
    "security": "shield-check", "safe": "shield-check", "privacy": "lock", "password": "key-round", "speed": "gauge", "fast": "zap", "power": "zap", "energy": "zap",
    "time": "clock", "deadline": "alarm-clock", "people": "users", "team": "users", "person": "user", "customer": "user", "community": "users", "family": "users",
    "love": "heart", "health": "heart-pulse", "medicine": "pill", "doctor": "stethoscope", "hospital": "hospital", "school": "graduation-cap", "education": "graduation-cap",
    "learning": "book-open", "book": "book", "knowledge": "brain", "mind": "brain", "ai": "bot", "robot": "bot", "code": "code", "software": "code", "data": "database",
    "internet": "globe", "web": "globe", "world": "globe", "global": "globe", "earth": "globe", "travel": "plane", "flight": "plane", "car": "car", "transport": "truck",
    "delivery": "truck", "shipping": "package", "home": "house", "house": "house", "building": "building-2", "city": "building-2", "office": "briefcase", "work": "briefcase",
    "job": "briefcase", "business": "briefcase", "goal": "target", "target": "target", "success": "trophy", "win": "trophy", "award": "award", "quality": "badge-check",
    "launch": "rocket", "startup": "rocket", "weather": "cloud-sun", "rain": "cloud-rain", "sun": "sun", "night": "moon", "food": "utensils", "eat": "utensils", "coffee": "coffee",
    "drink": "cup-soda", "water": "droplet", "nature": "leaf", "environment": "leaf", "green": "leaf", "tree": "tree-pine", "mountain": "mountain", "fire": "flame",
    "music": "music", "video": "video", "photo": "camera", "camera": "camera", "phone": "smartphone", "mobile": "smartphone", "computer": "laptop", "email": "mail",
    "message": "message-circle", "chat": "message-circle", "talk": "message-circle", "news": "newspaper", "search": "search", "tools": "wrench", "settings": "settings",
    "cloud": "cloud", "network": "network", "server": "server", "lock": "lock", "unlock": "lock-open", "warning": "triangle-alert", "danger": "triangle-alert", "risk": "triangle-alert",
    "question": "circle-help", "help": "life-buoy", "support": "life-buoy", "check": "check", "done": "circle-check", "error": "circle-x", "star": "star", "favorite": "star",
    "gift": "gift", "shopping": "shopping-cart", "store": "store", "shop": "store", "calendar": "calendar", "date": "calendar", "map": "map", "location": "map-pin", "place": "map-pin",
    "flag": "flag", "law": "scale", "legal": "scale", "justice": "scale", "balance": "scale", "chart": "chart-column", "stats": "chart-column", "analytics": "chart-column",
    "history": "history", "past": "history", "future": "telescope", "vision": "eye", "see": "eye", "hear": "ear", "listen": "ear", "voice": "mic", "speak": "mic",
    "sleep": "bed", "exercise": "dumbbell", "sport": "trophy", "game": "gamepad-2", "play": "play", "art": "palette", "design": "pen-tool", "write": "pencil", "document": "file-text",
    "file": "file", "folder": "folder", "link": "link", "share": "share-2", "download": "download", "upload": "upload", "sync": "refresh-cw", "update": "refresh-cw",
    "science": "flask-conical", "experiment": "flask-conical", "lab": "flask-conical", "atom": "atom", "space": "rocket", "planet": "globe", "diamond": "gem", "premium": "gem",
    "free": "gift", "simple": "feather", "easy": "feather", "light": "sun", "heavy": "weight", "layers": "layers", "steps": "footprints", "path": "route", "route": "route",
}


@lru_cache(maxsize=1)
def _index() -> Dict[str, List]:
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _by_tag() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for name, rec in _index().items():
        for t in rec[1:]:
            out.setdefault(t, []).append(name)
    return out


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(word).lower()).strip("-")


def _stems(w: str) -> List[str]:
    out = [w]
    for suf, rep in (("ies", "y"), ("ing", ""), ("es", ""), ("s", ""), ("ed", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            out.append(w[: -len(suf)] + rep)
    return out


def _rank(names: List[str], word: str) -> str:
    """Among icons that all fit, the plainest: the name that is the word, then one that starts with it, then the shortest (no '-off', '-x' variants)."""
    def score(n: str):
        return (n != word, not n.startswith(word), n.endswith(("-off", "-x", "-slash")), len(n), n)
    return sorted(names, key=score)[0]


def find_icon(word: str) -> Tuple[str, str]:
    """(icon name, how it was found). Never fails: unknown words give the neutral glyph."""
    idx = _index()
    w = _norm(word)
    if not w:
        return NEUTRAL, "neutral"
    cands = [w] + _stems(w)
    for c in cands:
        if c in idx:
            return c, "exact"
    for c in cands:
        s = SYNONYMS.get(c)
        if s and s in idx:
            return s, "synonym"
    tags = _by_tag()
    for c in cands:
        if c in tags:
            return _rank(tags[c], c), "tag"
    if "-" in w:   # 'piggy bank': the joined name failed above; try each part, longest first
        for part in sorted(w.split("-"), key=len, reverse=True):
            if len(part) >= 3 and (part in idx or part in SYNONYMS or part in tags):
                return find_icon(part)[0], "part"
    toks = [c for c in cands if len(c) >= 3]
    hit = [n for n in idx if any(t in n.split("-") for t in toks)]
    if hit:
        return _rank(hit, w), "name-token"
    names = difflib.get_close_matches(w, list(idx), n=1, cutoff=0.78)
    if names:
        return names[0], "fuzzy-name"
    tg = difflib.get_close_matches(w, list(tags), n=1, cutoff=0.82)
    if tg:
        return _rank(tags[tg[0]], tg[0]), "fuzzy-tag"
    return NEUTRAL, "neutral"


def codepoint_char(name: str) -> str:
    return chr(int(_index()[name][0]))


@lru_cache(maxsize=256)
def glyph_mask(name: str, px: int) -> Optional[Image.Image]:
    """The icon as an 'L' mask cropped to its ink, drawn at px pixels (supersampled canvas pixels), or None when the font cannot be read."""
    try:
        font = ImageFont.truetype(FONT_PATH, px)
        m = Image.new("L", (px * 2, px * 2), 0)
        ImageDraw.Draw(m).text((px, px), codepoint_char(name), font=font, fill=255, anchor="mm")
        box = m.getbbox()
        return m.crop(box) if box else None
    except Exception:  # noqa: BLE001
        return None


def draw_icon(cv, cx: float, cy: float, name: str, size: float, color, scale: float = 1.0) -> None:
    """Paste an icon centred on (cx, cy), `size` logical px tall, tinted with color (RGBA: alpha honoured); `scale` animates a pop without re-rasterising."""
    a = int(color[3]) if len(color) == 4 else 255
    if a <= 0 or scale <= 0.02:
        return
    m = glyph_mask(name, cv._s(size))
    if m is None:
        return
    if abs(scale - 1.0) > 0.01:
        m = m.resize((max(1, int(m.width * scale)), max(1, int(m.height * scale))), Image.BILINEAR)
    if a < 255:
        m = m.point(lambda v: v * a // 255)
    cv.im.paste(tuple(color[:3]), (int(cv._s(cx) - m.width / 2), int(cv._s(cy) - m.height / 2)), m)
