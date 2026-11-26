"""Spanish and English server text (docs/I18N.md): locale picking, catalog parity, English byte-identical to before, Spanish where a locale is sent."""
import json
import os

import pytest

import capabilities_api
from common import i18n, safety, wallet
from engine import format_options as fo
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)

HERE = os.path.dirname(__file__)


def ev(headers=None, **kw):
    e = _event(**kw)
    e["headers"] = {**e["headers"], **(headers or {})}
    return e


# ---------- locale picking
@pytest.mark.parametrize("headers,expected", [
    ({}, "en"), ({"X-Locale": "es"}, "es"), ({"x-locale": "ES"}, "es"), ({"X-Locale": "es-MX"}, "es"), ({"X-Locale": "es_419"}, "es"), ({"X-Locale": "en-GB"}, "en"),
    ({"X-Locale": "fr"}, "en"), ({"X-Locale": ""}, "en"), ({"X-Locale": "xx-garbage;;"}, "en"),
    ({"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}, "es"), ({"Accept-Language": "en-US,en;q=0.9,es;q=0.8"}, "en"), ({"Accept-Language": "fr-FR,fr;q=0.9"}, "en"),
    ({"Accept-Language": "fr;q=1.0,es;q=0.5"}, "es"), ({"Accept-Language": "*"}, "en"), ({"Accept-Language": "es;q=0,en"}, "en"),
    ({"X-Locale": "en", "Accept-Language": "es"}, "en"),   # the app's own choice wins over the browser's
    ({"X-Locale": "fr", "Accept-Language": "es"}, "en"),   # present but unsupported: English, never a silent switch to the browser
])
def test_pick_locale(headers, expected):
    assert i18n.pick_locale({"headers": headers}) == expected


def test_pick_locale_is_safe_on_junk():
    for event in (None, {}, {"headers": None}, {"headers": {"X-Locale": None}}, {"headers": {1: 2}}, "x"):
        assert i18n.pick_locale(event) == "en"


def test_explicit_locale_only_for_x_locale():
    assert i18n.explicit_locale({"headers": {"Accept-Language": "es"}}) is None and i18n.explicit_locale({"headers": {"X-Locale": "es"}}) == "es"


def test_t_fallbacks_and_params():
    assert i18n.t("err.forbidden", "es") == "No tienes acceso a esto."
    assert i18n.t("err.forbidden", "fr") == "Forbidden" and i18n.t("err.forbidden") == "Forbidden"
    assert i18n.t("no.such.key", "es") == "no.such.key"
    assert [i18n.t("create.credits_needed", "en", needed=n, balance=0) for n in (1, 2)] == ["This video needs 1 credit and you have 0.", "This video needs 2 credits and you have 0."]
    assert i18n.t("create.credits_needed", "es", needed=1, balance=0) == "Este video necesita 1 crédito y tienes 0."
    assert i18n.t("create.prompt_min", "es", min=10) == "La descripción debe tener al menos 10 caracteres."


# ---------- catalog parity (the same checks as scripts/i18n_check.py)
def test_catalog_check_script_passes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("i18n_check", os.path.join(HERE, "..", "scripts", "i18n_check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    errors, _warnings = mod.check_all()
    assert errors == []


# ---------- English output is byte-identical to before localization
def _caps(env):
    for k in ("READY_ASPECTS", "BETA_ASPECTS", "READY_RESOLUTIONS", "INTAKE_ENABLED", "READY_LANGUAGES"):
        os.environ.pop(k, None)
    os.environ.update(env)
    return fo.capabilities()


def test_capabilities_english_matches_the_golden_file(monkeypatch):
    golden = json.load(open(os.path.join(HERE, "fixtures", "i18n_golden_capabilities_en.json"), encoding="utf-8"))
    for k in ("READY_ASPECTS", "BETA_ASPECTS", "READY_RESOLUTIONS", "INTAKE_ENABLED", "READY_LANGUAGES"):
        monkeypatch.delenv(k, raising=False)
    got = {"default": fo.capabilities(), "all": None}
    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16,1:1,4:5")
    monkeypatch.setenv("BETA_ASPECTS", "9:16")
    monkeypatch.setenv("READY_RESOLUTIONS", "720p,1080p,2160p")
    monkeypatch.setenv("INTAKE_ENABLED", "1")
    got["all"] = fo.capabilities()
    assert json.dumps(got, sort_keys=True, ensure_ascii=False) == json.dumps(golden, sort_keys=True, ensure_ascii=False)
    assert fo.capabilities("en") == got["all"] and fo.capabilities("fr") == got["all"]


# the exact English texts as they were before the catalog existed
ENGLISH_BEFORE = [
    ("err.unauthorized", {}, "Unauthorized"), ("err.forbidden", {}, "Forbidden"), ("err.generic", {}, "Something went wrong. Please try again."),
    ("err.server_config", {}, "Server configuration error"), ("err.not_found", {}, "not found"), ("err.busy", {}, "Busy, please try again."),
    ("create.prompt_required", {}, "'prompt' is required"), ("create.prompt_min", {"min": 10}, "'prompt' must be at least 10 characters"),
    ("create.prompt_max", {"max": 2000}, "'prompt' must be at most 2000 characters"), ("create.language_unavailable", {}, "This language is not available yet"),
    ("create.format_unavailable", {}, "This format is not available yet"), ("create.resolution_unavailable", {}, "This resolution is not available yet"),
    ("create.photo_unfinished", {}, "One of your photos didn't finish uploading. Please try again."),
    ("create.photo_missing", {}, "One of the photos you chose is no longer in your library."), ("create.photo_prepare", {}, "Could not prepare your photos. Please try again."),
    ("create.test_limit", {}, "Daily limit for this test account reached."), ("create.credits_needed", {"needed": 1, "balance": 0}, "This video needs 1 credit and you have 0."),
    ("create.credits_needed", {"needed": 3, "balance": 2}, "This video needs 3 credits and you have 2."), ("create.start_failed", {}, "Failed to start workflow"),
    ("uploads.too_many", {}, "Too many photos uploaded today. Try again tomorrow."), ("wallet.read_failed", {}, "Couldn't read your credits. Please try again."),
    ("account.reauth", {}, "Please sign in again to confirm."), ("account.delete_first", {}, "Delete the account first."),
    ("account.already_deleted", {}, "The account is already deleted."), ("account.no_apple", {}, "This account has no Sign in with Apple identity."),
    ("library.name_length", {}, "the name must be 1 to 40 characters"), ("library.too_many_collections", {}, "too many collections"),
    ("library.query_empty", {}, "'query' must be a non-empty text"), ("library.query_long", {"max": 300}, "'query' is too long (at most 300 characters)"),
    ("video.not_found", {}, "Video not found"), ("video.not_ready", {}, "Video not ready"), ("video.get_failed", {}, "Failed to get video"),
    ("video.sign_failed", {}, "Failed to sign url"), ("video.list_failed", {}, "Failed to query videos"),
    ("edit.stale", {}, "This video changed since you loaded it. Reload to continue."), ("edit.already_rendered", {}, "This revision is already rendered."),
    ("edit.daily_limit", {}, "Daily edit limit reached."), ("edit.busy", {}, "An edit is already rendering. Wait for it to finish."),
    ("edit.render_failed", {}, "Couldn't start the render. Please try again."), ("edit.not_editable", {}, "This video was made with the previous engine and can't be edited."),
    ("edit.nothing", {}, "Nothing to edit"),
    ("safety.blocked", {}, "We can't make this video. If you had something else in mind, try describing a different idea."),
    ("safety.paused", {}, "Video creation is paused on your account for now. Please try again later."),
    ("safety.hold", {}, "Video creation is on hold while we take a look at your account. If you think this is a mistake, please contact support."),
]


@pytest.mark.parametrize("key,params,text", ENGLISH_BEFORE)
def test_english_text_is_unchanged(key, params, text):
    assert i18n.t(key, "en", **params) == text


def test_every_english_key_is_in_the_golden_table():
    assert {k for k, _, _ in ENGLISH_BEFORE} >= {k for k in i18n.EN if not k.startswith(("cap.", "deck.", "uploads.too_many_decks", "feedback."))}   # the deck messages are new (tests/test_deck.py checks them)


# ---------- Spanish where a locale is sent, English where not
CAPS_ENV = {"READY_ASPECTS": "16:9,9:16,1:1,4:5", "READY_RESOLUTIONS": "720p,1080p,2160p"}


def test_capabilities_handler_spanish_and_english(monkeypatch):
    for k, v in CAPS_ENV.items():
        monkeypatch.setenv(k, v)
    es = capabilities_api.handler(ev({"X-Locale": "es"}), None)
    en = capabilities_api.handler(ev(), None)
    assert es["statusCode"] == en["statusCode"] == 200
    b_es, b_en = json.loads(es["body"]), json.loads(en["body"])
    assert [a["label"] for a in b_es["aspects"]] == ["Horizontal", "Vertical", "Cuadrado", "Retrato"] and [a["label"] for a in b_en["aspects"]][0] == "Landscape"
    assert b_en == json.loads(json.dumps(fo.capabilities()))
    assert next(r for r in b_es["resolutions"] if r["id"] == "2160p")["note"].startswith("4K (2160p) cuesta el doble")
    youtube = next(p for p in b_es["platforms"] if p["id"] == "youtube")
    assert youtube["note"] == "Horizontal 16:9 · 1080p · unos 3 min" and youtube["note_4k"] is None
    assert next(p for p in b_es["platforms"] if p["id"] == "other")["label"] == "Solo un video"
    assert "publica en 1080p" in next(p for p in b_es["platforms"] if p["id"] == "tiktok")["note_4k"]
    # machine values never change with the locale
    strip = lambda b: json.dumps({k: v for k, v in b.items()}, sort_keys=True) and ([a["id"] for a in b["aspects"]], [p["id"] for p in b["platforms"]], b["lengths"], b["languages"], [p["supports_4k"] for p in b["platforms"]])
    assert strip(b_es) == strip(b_en)
    # caches must key on the locale
    assert es["headers"]["Vary"] == "X-Locale, Accept-Language" and es["headers"]["Content-Language"] == "es" and en["headers"]["Content-Language"] == "en"


def test_capabilities_accept_language_and_auth_errors():
    assert json.loads(capabilities_api.handler(ev({"Accept-Language": "es-419,es;q=0.9"}), None)["body"])["aspects"][0]["label"] == "Horizontal"
    r = capabilities_api.handler(ev({"X-Locale": "es"}, authed=False), None)
    assert r["statusCode"] == 401 and json.loads(r["body"])["message"] == "Tu sesión no es válida. Inicia sesión de nuevo."
    r = capabilities_api.handler(ev(path_user="other"), None)
    assert r["statusCode"] == 403 and json.loads(r["body"])["message"] == "Forbidden"


def _post(launcher, headers=None, **body):
    e = ev(headers, body=body)
    r = launcher.handler(e, None)
    return r["statusCode"], json.loads(r["body"])


def test_launcher_errors_follow_the_locale(launcher):
    assert _post(launcher, prompt="short") == (400, {"message": "'prompt' must be at least 10 characters"})
    assert _post(launcher, {"X-Locale": "es"}, prompt="short") == (400, {"message": "La descripción debe tener al menos 10 caracteres."})
    assert _post(launcher, {"X-Locale": "es"}, prompt="A short explainer about black holes", language="es", aspect="9:16")[1]["message"] == "Este formato aún no está disponible."
    assert _post(launcher, prompt="A short explainer about black holes", aspect="9:16")[1]["message"] == "This format is not available yet"
    # protocol errors stay English for everyone: the apps never show them
    assert _post(launcher, {"X-Locale": "es"}, prompt="A short explainer about black holes", target_minutes=99)[1]["message"].startswith("'target_minutes' must be")


def test_insufficient_credits_message_and_machine_fields(launcher, monkeypatch):
    def broke(*a, **k):
        raise wallet.InsufficientCredits(0, 3)
    monkeypatch.setattr(wallet, "charge", broke)
    status, body = _post(launcher, {"X-Locale": "es"}, prompt="A short explainer about how black holes form", target_minutes=3)
    assert status == 402 and body["message"] == "Este video necesita 3 créditos y tienes 0." and body["code"] == "insufficient_credits" and (body["balance"], body["needed"]) == (0, 3)
    status, body = _post(launcher, prompt="A short explainer about how black holes form (again)", target_minutes=3)
    assert body["message"] == "This video needs 3 credits and you have 0."


def test_safety_messages_follow_the_app_locale_else_the_prompt_language():
    assert safety.blocked_message("es") == i18n.t("safety.blocked", "es") and safety.blocked_message("en") == i18n.t("safety.blocked", "en")
    assert safety.blocked_message() == i18n.t("safety.blocked", "en")


def test_safety_gate_uses_x_locale(launcher, monkeypatch):
    from common import intake
    monkeypatch.setattr(safety, "enabled", lambda: True)
    monkeypatch.setattr(intake, "paused", lambda user, lang: {"status": "paused", "message": safety._PAUSED[lang], "retry_after": 5})
    english_prompt = "A short explainer about how black holes form"
    spanish_prompt = "Un video corto sobre cómo se forman los agujeros negros"
    assert _post(launcher, prompt=spanish_prompt)[1]["message"] == i18n.t("safety.paused", "es")           # no locale: today's behaviour (the prompt's language)
    assert _post(launcher, {"X-Locale": "en"}, prompt=spanish_prompt + " x")[1]["message"] == i18n.t("safety.paused", "en")   # the app's language wins
    assert _post(launcher, {"X-Locale": "es"}, prompt=english_prompt)[1]["message"] == i18n.t("safety.paused", "es")


def test_library_and_localized_errors():
    from common import library
    e = library.LibraryError(400, i18n.Localized("library.name_length"))
    assert e.message == "the name must be 1 to 40 characters" and e.text("es") == "El nombre debe tener entre 1 y 40 caracteres." and e.text("en") == e.message
    plain = library.LibraryError(400, "invalid cursor")
    assert plain.text("es") == "invalid cursor" and plain.message == "invalid cursor"
