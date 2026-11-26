"""Server-sent user-facing text in English and Spanish (docs/I18N.md).

  pick_locale(event)   -> 'en' | 'es'   from X-Locale (the apps), else Accept-Language (browsers), else English
  explicit_locale(ev)  -> 'en' | 'es' | None   only when X-Locale is present (None: the caller may fall back on its own guess, e.g. the prompt language)
  t(key, locale, **p)  -> the message; `{name}` placeholders and `{n, plural, one {# x} other {# xs}}` (one/other only, `#` is the number)

English is the default and the fallback: an unknown locale, a missing Spanish key or a request without locale gives exactly the English text that
existed before localization (tests/test_i18n.py proves it). Machine codes (`code`, `status`, ids) are never localized. Developer-facing protocol
errors ("'media' must be a non-empty list") stay English on purpose: the apps never show them.
"""
import re
from typing import Any, Dict, Optional

LOCALES = ("en", "es")
DEFAULT = "en"

EN: Dict[str, str] = {
    # ---- request problems every endpoint can answer
    "err.unauthorized": "Unauthorized",
    "err.forbidden": "Forbidden",
    "err.generic": "Something went wrong. Please try again.",
    "err.server_config": "Server configuration error",
    "err.not_found": "not found",
    "err.busy": "Busy, please try again.",
    # ---- create (sf_launcher, intake)
    "create.prompt_required": "'prompt' is required",
    "create.prompt_min": "'prompt' must be at least {min} characters",
    "create.prompt_max": "'prompt' must be at most {max} characters",
    "create.language_unavailable": "This language is not available yet",
    "create.format_unavailable": "This format is not available yet",
    "create.resolution_unavailable": "This resolution is not available yet",
    "create.photo_unfinished": "One of your photos didn't finish uploading. Please try again.",
    "create.photo_missing": "One of the photos you chose is no longer in your library.",
    "create.photo_prepare": "Could not prepare your photos. Please try again.",
    "create.test_limit": "Daily limit for this test account reached.",
    "create.credits_needed": "This video needs {needed, plural, one {# credit} other {# credits}} and you have {balance}.",
    "create.start_failed": "Failed to start workflow",
    # ---- uploads, wallet, account
    "uploads.too_many": "Too many photos uploaded today. Try again tomorrow.",
    "deck.err.deck_too_large": "This file is too large. Decks can be up to {max_mb} MB.",
    "deck.err.deck_too_many_slides": "This deck has too many slides. The limit is {max_slides}.",
    "deck.err.deck_unsupported": "We can only use PowerPoint (.pptx) and PDF files.",
    "deck.err.deck_corrupt": "We couldn't read this file. It may be damaged. Try saving it again as .pptx or PDF.",
    "deck.err.deck_encrypted": "This file is password protected or in the old .ppt format. Save it as .pptx or PDF without a password and try again.",
    "deck.err.deck_macro": "This file contains macros or embedded programs, which we don't accept. Save a copy without them.",
    "deck.err.deck_empty": "This deck has no slides we can use.",
    "deck.err.deck_unsafe": "We couldn't accept this file because it looks unsafe.",
    "deck.err.deck_convert_timeout": "This deck took too long to process. Try a smaller deck or fewer large images.",
    "deck.err.deck_convert_failed": "We couldn't turn this deck into pictures. Try exporting it as PDF.",
    "deck.unavailable": "Decks aren't available yet.",
    "deck.not_ready": "Your deck is still being prepared. Try again in a moment.",
    "deck.missing": "We couldn't find that deck. Please upload it again.",
    "deck.with_photos": "A video can be made from a deck or from photos, not both.",
    "deck.blocked": "We can't make a video from this deck.",
    "deck.unusable": "We couldn't make a video from this deck. Try a different one.",
    "uploads.too_many_decks": "Too many decks uploaded today. Try again tomorrow.",
    "wallet.read_failed": "Couldn't read your credits. Please try again.",
    "account.reauth": "Please sign in again to confirm.",
    "account.delete_first": "Delete the account first.",
    "account.already_deleted": "The account is already deleted.",
    "account.no_apple": "This account has no Sign in with Apple identity.",
    "feedback.text_length": "Please write between {min} and {max} characters.",
    "feedback.invalid": "That feedback could not be sent. Please check it and try again.",
    "feedback.rate_limited": "You have sent a lot of feedback just now. Please try again a little later.",
    # ---- library (My media)
    "library.name_length": "the name must be 1 to 40 characters",
    "library.too_many_collections": "too many collections",
    "library.query_empty": "'query' must be a non-empty text",
    "library.query_long": "'query' is too long (at most {max} characters)",
    # ---- videos and the editor
    "video.not_found": "Video not found",
    "video.not_ready": "Video not ready",
    "video.get_failed": "Failed to get video",
    "video.sign_failed": "Failed to sign url",
    "video.list_failed": "Failed to query videos",
    "edit.stale": "This video changed since you loaded it. Reload to continue.",
    "edit.already_rendered": "This revision is already rendered.",
    "edit.daily_limit": "Daily edit limit reached.",
    "edit.busy": "An edit is already rendering. Wait for it to finish.",
    "edit.render_failed": "Couldn't start the render. Please try again.",
    "edit.not_editable": "This video was made with the previous engine and can't be edited.",
    "edit.nothing": "Nothing to edit",
    # ---- safety stops (short, neutral, kind: never name the rule)
    "safety.blocked": "We can't make this video. If you had something else in mind, try describing a different idea.",
    "safety.paused": "Video creation is paused on your account for now. Please try again later.",
    "safety.hold": "Video creation is on hold while we take a look at your account. If you think this is a mistake, please contact support.",
    # ---- capabilities: labels and notes
    "cap.aspect.16:9": "Landscape",
    "cap.aspect.9:16": "Vertical",
    "cap.aspect.1:1": "Square",
    "cap.aspect.4:5": "Portrait",
    "cap.platform.other": "Just a video",
    "cap.platform_note": "{shape} {aspect} · 1080p · about {dur}",
    "cap.resolution.2160p.note": "4K (2160p) costs twice the credits. Best for YouTube and large screens.",
    "cap.note_4k": "{platform} publishes at 1080p or lower; 4K would cost twice the credits for no visible gain.",
}

ES: Dict[str, str] = {
    "err.unauthorized": "Tu sesión no es válida. Inicia sesión de nuevo.",
    "err.forbidden": "No tienes acceso a esto.",
    "err.generic": "Algo salió mal. Inténtalo de nuevo.",
    "err.server_config": "Error del servidor. Inténtalo más tarde.",
    "err.not_found": "No encontrado",
    "err.busy": "Estamos ocupados. Inténtalo de nuevo.",
    "create.prompt_required": "Escribe una descripción para tu video.",
    "create.prompt_min": "La descripción debe tener al menos {min} caracteres.",
    "create.prompt_max": "La descripción debe tener como máximo {max} caracteres.",
    "create.language_unavailable": "Este idioma aún no está disponible.",
    "create.format_unavailable": "Este formato aún no está disponible.",
    "create.resolution_unavailable": "Esta resolución aún no está disponible.",
    "create.photo_unfinished": "Una de tus fotos no terminó de subirse. Inténtalo de nuevo.",
    "create.photo_missing": "Una de las fotos que elegiste ya no está en tu biblioteca.",
    "create.photo_prepare": "No pudimos preparar tus fotos. Inténtalo de nuevo.",
    "create.test_limit": "Se alcanzó el límite diario de esta cuenta de prueba.",
    "create.credits_needed": "Este video necesita {needed, plural, one {# crédito} other {# créditos}} y tienes {balance}.",
    "create.start_failed": "No pudimos iniciar tu video.",
    "uploads.too_many": "Subiste demasiadas fotos hoy. Inténtalo de nuevo mañana.",
    "deck.err.deck_too_large": "Este archivo es demasiado grande. Las presentaciones pueden pesar hasta {max_mb} MB.",
    "deck.err.deck_too_many_slides": "Esta presentación tiene demasiadas diapositivas. El límite es {max_slides}.",
    "deck.err.deck_unsupported": "Solo podemos usar archivos de PowerPoint (.pptx) y PDF.",
    "deck.err.deck_corrupt": "No pudimos leer este archivo. Puede estar dañado. Prueba a guardarlo de nuevo como .pptx o PDF.",
    "deck.err.deck_encrypted": "Este archivo tiene contraseña o está en el formato antiguo .ppt. Guárdalo como .pptx o PDF sin contraseña e inténtalo de nuevo.",
    "deck.err.deck_macro": "Este archivo contiene macros o programas incrustados, que no aceptamos. Guarda una copia sin ellos.",
    "deck.err.deck_empty": "Esta presentación no tiene diapositivas que podamos usar.",
    "deck.err.deck_unsafe": "No pudimos aceptar este archivo porque parece poco seguro.",
    "deck.err.deck_convert_timeout": "Esta presentación tardó demasiado en procesarse. Prueba con una más pequeña o con menos imágenes grandes.",
    "deck.err.deck_convert_failed": "No pudimos convertir esta presentación en imágenes. Prueba a exportarla como PDF.",
    "deck.unavailable": "Las presentaciones aún no están disponibles.",
    "deck.not_ready": "Tu presentación aún se está preparando. Inténtalo de nuevo en un momento.",
    "deck.missing": "No encontramos esa presentación. Súbela de nuevo.",
    "deck.with_photos": "Un video se puede hacer con una presentación o con fotos, no con ambas.",
    "deck.blocked": "No podemos hacer un video con esta presentación.",
    "deck.unusable": "No pudimos hacer un video con esta presentación. Prueba con otra.",
    "uploads.too_many_decks": "Subiste demasiadas presentaciones hoy. Inténtalo de nuevo mañana.",
    "wallet.read_failed": "No pudimos cargar tus créditos. Inténtalo de nuevo.",
    "account.reauth": "Inicia sesión de nuevo para confirmar.",
    "account.delete_first": "Primero elimina la cuenta.",
    "account.already_deleted": "La cuenta ya está eliminada.",
    "account.no_apple": "Esta cuenta no usa Iniciar sesión con Apple.",
    "feedback.text_length": "Escribe entre {min} y {max} caracteres.",
    "feedback.invalid": "No pudimos enviar tu mensaje. Revísalo e inténtalo de nuevo.",
    "feedback.rate_limited": "Has enviado muchos mensajes hace poco. Inténtalo de nuevo un poco más tarde.",
    "library.name_length": "El nombre debe tener entre 1 y 40 caracteres.",
    "library.too_many_collections": "Tienes demasiadas colecciones.",
    "library.query_empty": "Escribe algo para buscar.",
    "library.query_long": "La búsqueda es demasiado larga (máximo {max} caracteres).",
    "video.not_found": "No encontramos este video.",
    "video.not_ready": "El video aún no está listo.",
    "video.get_failed": "No pudimos cargar el video. Inténtalo de nuevo.",
    "video.sign_failed": "No pudimos cargar el video. Inténtalo de nuevo.",
    "video.list_failed": "No pudimos cargar tus videos. Inténtalo de nuevo.",
    "edit.stale": "Este video cambió desde que lo abriste. Recarga para continuar.",
    "edit.already_rendered": "Esta versión ya está lista.",
    "edit.daily_limit": "Alcanzaste el límite diario de ediciones.",
    "edit.busy": "Ya se está procesando una edición. Espera a que termine.",
    "edit.render_failed": "No pudimos iniciar el procesamiento. Inténtalo de nuevo.",
    "edit.not_editable": "Este video se creó con una versión anterior y no se puede editar.",
    "edit.nothing": "No hay nada que editar.",
    "safety.blocked": "No podemos crear este video. Si tenías otra idea en mente, prueba a describir una distinta.",
    "safety.paused": "La creación de videos está en pausa en tu cuenta por ahora. Inténtalo de nuevo más tarde.",
    "safety.hold": "La creación de videos está detenida mientras revisamos tu cuenta. Si crees que es un error, escribe a soporte.",
    "cap.aspect.16:9": "Horizontal",
    "cap.aspect.9:16": "Vertical",
    "cap.aspect.1:1": "Cuadrado",
    "cap.aspect.4:5": "Retrato",
    "cap.platform.other": "Solo un video",
    "cap.platform_note": "{shape} {aspect} · 1080p · unos {dur}",
    "cap.resolution.2160p.note": "4K (2160p) cuesta el doble de créditos. Ideal para YouTube y pantallas grandes.",
    "cap.note_4k": "{platform} publica en 1080p o menos; el 4K costaría el doble de créditos sin una mejora visible.",
}

CATALOG: Dict[str, Dict[str, str]] = {"en": EN, "es": ES}

_PLURAL = re.compile(r"\{(\w+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}")
_PARAM = re.compile(r"\{(\w+)\}")


def normalize(tag: Any) -> Optional[str]:
    """'es', 'es-MX', 'es_419', 'ES' -> 'es'; 'en-GB' -> 'en'; anything else (including empty) -> None."""
    s = str(tag or "").strip().lower().replace("_", "-")
    primary = s.split("-", 1)[0]
    return primary if primary in LOCALES else None


def _headers(event: Any) -> Dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (((event or {}).get("headers")) or {}).items() if v is not None}


def explicit_locale(event: Any) -> Optional[str]:
    """The app's own choice: the X-Locale header (a device locale mapped to en/es). Present but unknown (say 'fr') means English. Absent: None."""
    raw = _headers(event).get("x-locale", "").strip()
    if not raw:
        return None
    return normalize(raw.split(",")[0]) or DEFAULT


def _accept_language(raw: str) -> Optional[str]:
    """The best supported language of an Accept-Language header by q-value (ties keep the written order)."""
    best, best_q = None, -1.0
    for part in raw.split(",")[:20]:
        tag, _, params = part.strip().partition(";")
        loc = normalize(tag)
        if loc is None or tag.strip() == "*":
            continue
        q = 1.0
        m = re.search(r"q\s*=\s*([0-9.]+)", params)
        if m:
            try:
                q = float(m.group(1))
            except ValueError:
                q = 0.0
        if q > 0 and q > best_q:
            best, best_q = loc, q
    return best


def pick_locale(event: Any) -> str:
    """X-Locale wins; else the best supported Accept-Language; else English. Never raises."""
    try:
        loc = explicit_locale(event)
        if loc:
            return loc
        return _accept_language(_headers(event).get("accept-language", "")) or DEFAULT
    except Exception:   # noqa: BLE001 - a header problem must never break a request
        return DEFAULT


def _plural(text: str, params: Dict[str, Any]) -> str:
    def sub(m: "re.Match[str]") -> str:
        n = params.get(m.group(1), 0)
        body = m.group(2) if n == 1 else m.group(3)
        return body.replace("#", str(n))
    return _PLURAL.sub(sub, text)


def t(key: str, locale: Optional[str] = None, **params: Any) -> str:
    """The message for `key` in `locale` (English when the locale or the key is unknown; the key itself when even English lacks it)."""
    loc = normalize(locale) or DEFAULT
    text = CATALOG[loc].get(key) or EN.get(key) or key
    text = _plural(text, params)
    return _PARAM.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), text)


class Localized(Exception):
    """An error carrying a catalog key: `str(e)` is the English text (as before), `e.message(locale)` the localized one."""

    def __init__(self, key: str, **params: Any):
        self.key, self.params = key, params
        super().__init__(t(key, "en", **params))

    def message(self, locale: Optional[str] = None) -> str:
        return t(self.key, locale, **self.params)


def error_text(exc: BaseException, locale: Optional[str] = None) -> str:
    """The message of an exception in the person's language when it carries a catalog key (`Localized`, or an error whose `.localized` is one), else its own text."""
    loc = exc if isinstance(exc, Localized) else getattr(exc, "localized", None)
    return loc.message(locale) if isinstance(loc, Localized) else str(exc)


def vary_headers() -> Dict[str, str]:
    """For responses that differ by locale (capabilities): caches must key on the locale."""
    return {"Vary": "X-Locale, Accept-Language"}
