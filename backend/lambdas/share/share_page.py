"""The share page of one video (docs/SHARE_PREVIEWS_2026-11-27.md): the HTML a link-preview crawler reads (WhatsApp, LinkedIn, Facebook, X, Slack, Telegram, iMessage, Discord) and a visitor sees.

Pure functions, no AWS and no JavaScript on the page: crawlers do not run scripts, so the tags are in the HTML as delivered, and the visitor's player is the browser's own <video>.
Every value that came from a person's request (the title, the description) is escaped; nothing personal is ever written here: no user id, no email, no video id.
The address of a share is `https://<host>/<token>`; the token is 128 random bits (`new_token`), so an unlisted link cannot be guessed. The page, the cover cards and the video sit
next to each other under that token: index.html, og.jpg (1200x630), poster.jpg (the video's own shape), video.mp4.
"""
import html
import re
import secrets
from typing import Dict, Optional

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")
FILES = ("index.html", "og.jpg", "poster.jpg", "video.mp4")
OG_W, OG_H = 1200, 630
DESC_MAX = 200
TITLE_MAX = 90

# the few words the page itself says, in the video's language (the title and the description are already in it)
STRINGS: Dict[str, Dict[str, str]] = {
    "en": {"made": "Made with VideoMK", "default_desc": "A short narrated explainer video made with VideoMK.", "cta": "Make your own video"},
    "es": {"made": "Hecho con VideoMK", "default_desc": "Un vídeo explicativo breve con narración, hecho con VideoMK.", "cta": "Crea tu propio vídeo"},
    "fr": {"made": "Fait avec VideoMK", "default_desc": "Une courte vidéo explicative avec narration, faite avec VideoMK.", "cta": "Créez votre vidéo"},
    "de": {"made": "Erstellt mit VideoMK", "default_desc": "Ein kurzes Erklärvideo mit Sprecher, erstellt mit VideoMK.", "cta": "Erstelle dein eigenes Video"},
    "it": {"made": "Fatto con VideoMK", "default_desc": "Un breve video esplicativo con narrazione, fatto con VideoMK.", "cta": "Crea il tuo video"},
    "pt": {"made": "Feito com VideoMK", "default_desc": "Um vídeo explicativo curto com narração, feito com VideoMK.", "cta": "Crie o seu vídeo"},
    "nl": {"made": "Gemaakt met VideoMK", "default_desc": "Een korte uitlegvideo met verteller, gemaakt met VideoMK.", "cta": "Maak je eigen video"},
    "pl": {"made": "Stworzone w VideoMK", "default_desc": "Krótki film objaśniający z lektorem, stworzony w VideoMK.", "cta": "Stwórz własny film"},
    "fi": {"made": "Tehty VideoMK:lla", "default_desc": "Lyhyt selittävä video selostuksella, tehty VideoMK:lla.", "cta": "Tee oma videosi"},
}
OG_LOCALE = {"en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE", "it": "it_IT", "pt": "pt_PT", "nl": "nl_NL", "pl": "pl_PL", "fi": "fi_FI"}
RATIOS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def new_token() -> str:
    """128 random bits as 22 URL-safe characters."""
    t = secrets.token_urlsafe(16)
    assert TOKEN_RE.match(t)
    return t


def valid_token(t: object) -> bool:
    return isinstance(t, str) and bool(TOKEN_RE.match(t))


def clean(text: Optional[str], limit: int) -> str:
    """One line, no control characters, at most `limit` characters (a cut word ends with an ellipsis)."""
    s = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(text or "")).split())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.-") + "…"


def blurb(description: Optional[str]) -> str:
    """The first paragraph of the video's description, as one short line (it is stored on the record at finalize). Links and chapter lists are dropped."""
    first = next((p for p in re.split(r"\n\s*\n", str(description or "")) if p.strip()), "")
    first = re.sub(r"https?://\S+", "", first)
    return clean(first, DESC_MAX)


def render(*, host: str, token: str, title: str, description: str = "", language: str = "en", aspect: str = "16:9", has_cover: bool = True, has_poster: bool = True,
           video_tags: bool = False, duration_s: Optional[int] = None) -> str:
    """The page for one share. `host`: the share host, e.g. "share.videomk.com". `video_tags`: also write og:video / twitter:player (off unless the research
    in the doc says a platform plays it: today none of the ones people share to does, and some drop the image when the video tag is there)."""
    if not valid_token(token):
        raise ValueError("bad token")
    if not re.match(r"^[a-z0-9.-]+$", host):
        raise ValueError("bad host")
    lang = language if language in STRINGS else "en"
    st = STRINGS[lang]
    title = clean(title, TITLE_MAX) or "VideoMK"
    desc = clean(description, DESC_MAX) or st["default_desc"]
    e = lambda v: html.escape(str(v), quote=True)   # noqa: E731
    base = f"https://{host}/{token}"
    page, og, poster, video = base, f"{base}/og.jpg", f"{base}/poster.jpg", f"{base}/video.mp4"
    w, h = RATIOS.get(aspect, RATIOS["16:9"])
    meta = [
        f'<title>{e(title)}</title>',
        f'<meta name="description" content="{e(desc)}">',
        '<meta name="robots" content="noindex, nofollow">',          # an unlisted link: never in a search index
        '<meta name="referrer" content="no-referrer">',
        f'<link rel="canonical" href="{e(page)}">',
        f'<meta property="og:site_name" content="VideoMK">',
        f'<meta property="og:type" content="{"video.other" if video_tags else "website"}">',
        f'<meta property="og:url" content="{e(page)}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:locale" content="{OG_LOCALE[lang]}">',
    ]
    if has_cover:
        meta += [f'<meta property="og:image" content="{e(og)}">', f'<meta property="og:image:secure_url" content="{e(og)}">', '<meta property="og:image:type" content="image/jpeg">',
                 f'<meta property="og:image:width" content="{OG_W}">', f'<meta property="og:image:height" content="{OG_H}">', f'<meta property="og:image:alt" content="{e(title)}">']
    if video_tags:
        meta += [f'<meta property="og:video" content="{e(video)}">', f'<meta property="og:video:secure_url" content="{e(video)}">', '<meta property="og:video:type" content="video/mp4">',
                 f'<meta property="og:video:width" content="{w // 2}">', f'<meta property="og:video:height" content="{h // 2}">']
        if duration_s:
            meta.append(f'<meta property="og:video:duration" content="{int(duration_s)}">')
    meta += [f'<meta name="twitter:card" content="{"summary_large_image" if has_cover else "summary"}">', f'<meta name="twitter:title" content="{e(title)}">',
             f'<meta name="twitter:description" content="{e(desc)}">']
    if has_cover:
        meta += [f'<meta name="twitter:image" content="{e(og)}">', f'<meta name="twitter:image:alt" content="{e(title)}">']
    ratio = f"{w} / {h}"
    maxw = "min(100%, 960px)" if w >= h else ("min(100%, 420px)" if h > w * 1.5 else "min(100%, 560px)")
    body = (f'<main><div class="v" style="aspect-ratio:{ratio};max-width:{maxw}">'
            f'<video controls playsinline preload="metadata" {"poster=" + chr(34) + e(poster) + chr(34) if has_poster else ""} src="{e(video)}"></video></div>'
            f'<h1>{e(title)}</h1><p>{e(desc)}</p>'
            f'<p class="m"><a href="https://videomk.com/" rel="noopener">{e(st["made"])}</a> · <a href="https://videomk.com/" rel="noopener">{e(st["cta"])}</a></p></main>')
    css = ("html{color-scheme:light dark}body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#fff;color:#11142b}"
           "main{max-width:960px;margin:0 auto;padding:16px}.v{width:100%;margin:0 auto 16px;background:#000;border-radius:12px;overflow:hidden}"
           "video{width:100%;height:100%;display:block}h1{font-size:1.5rem;line-height:1.25;margin:0 0 8px}p{margin:0 0 12px}.m{font-size:.875rem;opacity:.75}a{color:inherit}"
           "@media(prefers-color-scheme:dark){body{background:#06070d;color:#f4f4f8}}")
    return ("<!doctype html>\n" f'<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + "".join(meta) + f"<style>{css}</style></head><body>{body}</body></html>\n")
