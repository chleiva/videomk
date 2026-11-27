"""A look or style wish never stops a video (common/looks.py, docs/CREATE_API.md "Looks"): the request check knows the looks of the stage, a wish that cannot be met
as asked becomes a short localized note, the refusal copy never says "I". The owner's own request and its variants, English and Spanish. Fake model, moto DynamoDB."""
import json

import pytest

from common import i18n, intake, looks
import video_brief
from tests.test_hardening import launcher  # noqa: F401  (the fixture)
from tests.test_intake_safety import U, ev, tables  # noqa: F401

OWNER = ("characters explaining the news today and this has to be fun because I want better animated characters, animated like cartoons basically, "
         "so the news are explained by characters")
QA = {"VECTOR_SCENES": "1", "WHITEBOARD": "1", "BG_ANIMATED": "1", "BG_LOOPS": "1"}
# what the real small model answered before the fix (the owner's phone, QA, 2026-11-27)
REFUSAL = {"block": None, "questions": [], "unsupported": {"kind": "content_type", "message": "I can't create cartoon characters or animated drawings, because the app doesn't generate new artwork or AI images.",
                                                             "suggestion": "I can make a narrated news explainer with stock photos instead."}}


def stage(monkeypatch, **env):
    for k in looks.SWITCHES.values():
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def brief(prompt, answer=None, headers=None, **body):
    seen = []

    def model(system, user):
        seen.append(system)
        return json.dumps(answer or {"block": None, "unsupported": None, "questions": []})
    e = ev(prompt, U, **body)
    e["headers"] = headers or {}
    r = video_brief.handler(e, None, ask=model)
    return json.loads(r["body"]), seen


# ----------------------------------------------------------------------------- the prompt the model reads is stage-aware and never says the app cannot make cartoons
def test_the_check_is_told_the_looks_of_the_stage(monkeypatch):
    stage(monkeypatch, **QA)
    p = intake.system_prompt()
    assert "CARTOON scenes" in p and "WHITEBOARD look" in p and "ANIMATED and 3D moving backgrounds" in p and "PRESENTER CHARACTERS" not in p
    assert "Not available here yet: talking animated characters." in p
    assert 'NEVER a reason for "unsupported"' in p and "Never say the app cannot make cartoons" in p and "@@LOOKS@@" not in p
    stage(monkeypatch, PRESENTERS="1", **QA)
    assert "PRESENTER CHARACTERS" in intake.system_prompt() and "Not available here yet" not in intake.system_prompt()
    stage(monkeypatch, BG_ANIMATED="1")   # production today
    p = intake.system_prompt()
    assert "CARTOON scenes" not in p and "Not available here yet: talking animated characters, cartoon scenes, the whiteboard look." in p and "ANIMATED moving backgrounds" in p


def test_the_prompt_asks_for_the_product_voice():
    assert '"VideoMK can\'t ..."' in intake.SYSTEM and 'never "I can\'t"' in intake.SYSTEM


# ----------------------------------------------------------------------------- the owner's request: not blocked, style resolved, note present
def test_the_owners_request_is_made_even_when_the_model_refuses_over_the_look(tables, monkeypatch):
    stage(monkeypatch, **QA)
    body, seen = brief(OWNER, REFUSAL)
    assert body["status"] == "ok" and "message" not in body
    assert body["look"] == {"style": "auto", "asked": ["cartoon", "characters"], "adapted": ["cartoon", "characters"], "presenter": False}   # news: never cartoon scenes; characters are off
    assert body["note"] == "Made as a narrated explainer with animated backgrounds; talking characters are coming soon."
    assert "CARTOON scenes" in seen[0]


@pytest.mark.parametrize("prompt,asked,style,note_has", [
    ("Explain photosynthesis with cartoon characters, make it fun", ["cartoon", "characters"], "cartoon", "illustrated cartoon scenes; talking characters are coming soon"),
    ("How do volcanoes work, explained by animated animals for kids", ["characters"], "auto", "talking characters are coming soon"),
    ("The water cycle for children, with a presenter", ["characters"], "auto", "talking characters are coming soon"),
    ("Why the sky is blue, explained by a fox", ["characters"], "auto", "talking characters are coming soon"),
    ("Today's news explained as a cartoon", ["cartoon"], "auto", "cartoon scenes are not used for news and real events"),
    ("Explica el ciclo del agua con dibujos animados y personajes que hablan", ["cartoon", "characters"], "cartoon", "los personajes que hablan llegarán pronto"),
    ("Las noticias de hoy explicadas con personajes animados, que sea divertido", ["characters"], "auto", "fondos animados; los personajes que hablan llegarán pronto"),
    ("Por qué el cielo es azul, explicado por un zorro", ["characters"], "auto", "los personajes que hablan llegarán pronto"),
    ("Cómo funcionan los volcanes, con animales animados para niños", ["characters"], "auto", "los personajes que hablan llegarán pronto"),
    ("Las noticias de hoy en dibujos animados", ["cartoon"], "auto", "las escenas de dibujos no se usan en noticias"),
])
def test_look_wishes_in_english_and_spanish_are_never_blocked(tables, monkeypatch, prompt, asked, style, note_has):
    stage(monkeypatch, **QA)
    for answer in (None, REFUSAL):   # whatever the model says about the look
        body, _ = brief(prompt, answer)
        assert body["status"] == "ok", body
        assert body["look"]["asked"] == asked and body["look"]["style"] == style and note_has in body["note"], body
        assert not looks.first_person(body["note"]) and "videomk" not in body["note"]


def test_a_wish_the_stage_can_meet_has_no_note(tables, monkeypatch):
    stage(monkeypatch, **QA)
    body, _ = brief("The water cycle for kids, make it a cartoon")
    assert body == {"status": "ok", "brief": {}, "look": {"style": "cartoon", "asked": ["cartoon"], "adapted": [], "presenter": False}}
    body, _ = brief("How a bill becomes law, as a whiteboard video")
    assert body["look"]["style"] == "whiteboard" and "note" not in body
    body, _ = brief("How tides work, explained simply")   # nothing asked: the answer is exactly what it was before
    assert body == {"status": "ok", "brief": {}}
    stage(monkeypatch, PRESENTERS="1", **QA)
    body, _ = brief("Why the sky is blue, explained by a fox")
    assert body["look"] == {"style": "auto", "asked": ["characters"], "adapted": [], "presenter": True} and "note" not in body
    body, _ = brief("The news today explained by animated characters")   # the look exists but is not used for news: still made, and said
    assert body["status"] == "ok" and "presenter characters are not used for news" in body["note"] and body["look"]["presenter"] is False


def test_the_note_follows_the_stage_and_the_form(tables, monkeypatch):
    stage(monkeypatch)   # nothing on
    body, _ = brief("Explain gravity with cartoon characters")
    assert body["status"] == "ok" and body["note"] == "Made as a narrated explainer with photos and footage; talking characters are coming soon." and body["look"]["style"] == "auto"
    body, _ = brief("Explain gravity as a cartoon")
    assert body["note"] == "Made as a narrated explainer with photos and footage; cartoon scenes are coming soon."
    stage(monkeypatch, **QA)
    body, _ = brief("My trip to Lisbon as a cartoon", media_count=12)
    assert body["status"] == "ok" and body["note"].startswith("Made from your photos") and body["look"]["style"] == "auto"
    body, _ = brief("How tides work", options={"style": "cartoon"})   # the form's choice counts like the words
    assert body["look"]["style"] == "cartoon" and "note" not in body
    body, _ = brief("A cartoon about tides, but use real footage only")   # "real" wins, as in the engine
    assert body["look"]["style"] == "real" and "note" not in body
    body, _ = brief("Explain gravity with cartoon characters", headers={"X-Locale": "es"})   # the app's language wins over the request's
    assert body["note"].startswith("Lo hacemos como")
    body, _ = brief("A story about two characters who argue about the best pizza")   # a dialogue is not a look wish
    assert body == {"status": "ok", "brief": {}}


def test_the_models_own_reading_adds_a_wish_the_words_missed(tables, monkeypatch):
    stage(monkeypatch, **QA)
    body, _ = brief("Quiero que un búho simpático cuente por qué llueve", {"block": None, "unsupported": None, "questions": [], "look": {"wish": "characters", "serious": False}})
    assert body["status"] == "ok" and body["look"]["asked"] == ["characters"] and "llegarán pronto" in body["note"]
    body, _ = brief("Make it a cartoon about the earthquake", {"block": None, "unsupported": None, "questions": [], "look": {"wish": "cartoon", "serious": True}})
    assert body["look"]["style"] == "auto" and "not used for news and real events" in body["note"]
    assert looks.clean_model_look({"wish": "nonsense"}) is None and looks.clean_model_look("cartoon") is None


# ----------------------------------------------------------------------------- blocking stays for safety and for what cannot be done at all
def test_safety_and_real_limits_still_stop(tables, monkeypatch):
    stage(monkeypatch, **QA)
    body, _ = brief("A cartoon with characters explaining step by step how to build an explosive device", {"block": "weapons_drugs", "unsupported": None, "questions": []})
    assert body["status"] == "blocked" and "note" not in body and "look" not in body
    body, _ = brief("Explique-moi pourquoi le ciel est bleu, en dessin animé", {"block": None, "questions": [], "unsupported": {"kind": "language", "message": "VideoMK makes videos in English and Spanish, not cartoons in French.", "suggestion": "Write it in English or Spanish."}})
    assert body["status"] == "not_supported"
    body, _ = brief("Edit my existing video and turn it into a cartoon", {"block": None, "questions": [], "unsupported": {"kind": "content_type", "message": "VideoMK can't edit an existing video or turn it into a cartoon.", "suggestion": "Describe the topic and VideoMK makes a new video."}})
    assert body["status"] == "not_supported" and body["message"].startswith("VideoMK can't edit")


def test_the_refusal_copy_never_says_i(tables, monkeypatch):
    stage(monkeypatch, **QA)
    body, _ = brief("Stream my football match live tonight", {"block": None, "questions": [], "unsupported": {"kind": "format", "message": "I can't stream live events.", "suggestion": "I can make an explainer about the match instead."}})
    assert body == {"status": "not_supported", "message": i18n.t("intake.unsupported", "en"), "suggestion": i18n.t("intake.unsupported_suggestion", "en")}
    assert body["message"] == "VideoMK can't make this one as described."
    body, _ = brief("Transmite en directo el partido de fútbol de esta noche para mis amigos", {"block": None, "questions": [], "unsupported": {"kind": "format", "message": "No puedo transmitir en directo.", "suggestion": "Describe el partido y VideoMK crea un video explicativo."}})
    assert body["message"] == "VideoMK no puede crear este video tal como está descrito." and body["suggestion"].startswith("Describe el partido")
    for text, said in (("I can't do that", True), ("I'm sorry", True), ("Lo siento, no puedo", True), ("VideoMK can't edit videos", False), ("VideoMK no puede editar videos", False), ("It can't be done", False)):
        assert looks.first_person(text) is said, text
    for loc in ("en", "es"):   # every fixed sentence a person can read here: the product speaks, and its name is written VideoMK
        for key in [k for k in i18n.EN if k.startswith(("look.", "intake.", "safety."))]:
            assert not looks.first_person(i18n.t(key, loc)) and "videomk" not in i18n.t(key, loc), (key, loc)


# ----------------------------------------------------------------------------- generate: the same note in the 202, and nothing leaks into the stored request
def test_generate_carries_the_note_and_never_refuses_a_look(launcher, tables, monkeypatch):  # noqa: F811
    stage(monkeypatch, **QA)
    monkeypatch.setattr(intake, "bedrock_ask", lambda s, u, **k: json.dumps(REFUSAL))
    r = launcher.handler({"pathParameters": {"user_id": U}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": U}}},
                          "body": json.dumps({"prompt": OWNER, "client_request_id": "req-look-0001", "target_minutes": 1})}, None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 202 and body["note"] == "Made as a narrated explainer with animated backgrounds; talking characters are coming soon." and body["look"]["adapted"] == ["cartoon", "characters"]
    r = launcher.handler({"pathParameters": {"user_id": U}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": U}}},
                          "body": json.dumps({"prompt": "How tides work, explained simply for everyone", "client_request_id": "req-look-0002", "target_minutes": 1})}, None)
    assert r["statusCode"] == 202 and "note" not in json.loads(r["body"]) and "look" not in json.loads(r["body"])


def test_capabilities_and_the_check_read_the_same_switches(monkeypatch):
    import capabilities_api
    stage(monkeypatch, VECTOR_SCENES="1", BG_LOOPS="1")
    cap, f = capabilities_api.looks("en"), looks.flags()
    assert f == {"cartoon": True, "whiteboard": False, "bg_animated": False, "bg_loops": True, "presenters": False}
    by_id = {o["id"]: o["available"] for o in cap["style"]["options"]}
    assert by_id == {"auto": True, "cartoon": True, "real": True, "whiteboard": False} and cap["backgrounds"]["loops_3d"] is True and cap["backgrounds"]["animated"] is False
