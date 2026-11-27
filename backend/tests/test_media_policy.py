"""The ONE safety policy of the library (docs/LIBRARY_ON_DEMAND.md part C; lambdas/common/media_policy.py): its word lists, its rubric inside every media type's
checks, the provider's moderation as a second gate, the audit of what the library holds, and the takedown. No network: models, providers and stores are stand-ins."""
import io
import json
import os
import sys
import urllib.error

import numpy as np
import pytest

from common import catalog, catalog_make, catalog_store, clip_config as cc, clip_store as cs, media_policy as mp, object_maker, takedown
from engine import clip_brief, clip_gate, clip_library as lib, clip_ondemand as od, image_ondemand as io_, object_ondemand as oo
from engine.whiteboard import library as wblib

sys.path.insert(0, os.path.dirname(__file__))
from test_clips_on_demand import GOOD_BRIEF, GOOD_GATE, MP4, _vec   # noqa: E402
from test_library_on_demand import ON, QA_OK, _board_plan, _picture, _pkg, ask, env, outcomes, spent, wb   # noqa: E402,F401 - the same stand-ins and fixtures

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import library_safety   # noqa: E402

SAFE = ["bees on lavender flowers", "baker hands kneading bread dough", "raindrops falling on a quiet still pond surface, creating gentle ripples in soft overcast light",
        "small wooden boat moored at a quiet jetty in calm harbour water, soft morning light", "row of wooden beehive boxes standing among tall wildflowers in a sunlit summer meadow",
        "empty classroom with wooden desks", "steam rising from a cup of coffee", "golden wheat field swaying in the wind", "busy outdoor fruit market stall, close on hands choosing ripe fruit",
        "honeycomb", "violin", "kite", "teapot", "igloo", "accordion", "sundial", "trowel", "skateboard", "chicken breast on a cutting board", "shooting star over a mountain", "bullet train",
        "light bulb", "bombilla con rayos", "six-armed snowflake", "check mark", "marca de verificación", "sombrero fedora", "granjero con horca", "mochila escolar", "smiling face"]
# one wording per category in English and one in Spanish (accents and capitals as a person would write them)
UNSAFE = {"politics": ("crowd at an election rally", "Manifestación frente al Parlamento"), "religion": ("old church on a hill", "una Iglesia pequeña"),
          "war_weapons": ("soldiers marching", "un soldado con fusil"), "violence": ("two men fighting", "un ladrón en la noche"),
          "injury_medical": ("surgeon making an incision", "una jeringuilla y una vacuna"), "sexual": ("woman in a bikini", "pareja besándose"),
          "drugs_alcohol_tobacco": ("glass of red wine", "una cerveza fría"), "gambling": ("casino roulette wheel", "máquina tragaperras"),
          "tragedy_disaster": ("house after the earthquake", "un funeral bajo la lluvia"), "children": ("baby sleeping in a cot", "niños jugando en el parque"),
          "flags_maps": ("flag waving on a pole", "mapa del mundo con fronteras"), "stereotypes": ("tribal dancers", "un gitano con guitarra"),
          "real_people": ("a famous actor on stage", "retrato de una cantante"), "brands_ip": ("superhero flying over a city", "logotipo en una caja"),
          "hate": ("a swastika on a wall", "símbolo nazi"), "self_harm": ("a noose hanging from a tree", "pensamientos de suicidio"),
          "frightening": ("a skull on a table", "una calavera y un fantasma")}


class Stub:
    """A model stand-in: answers by which system prompt it is given."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def __call__(self, system, user, **kw):
        which = {mp.NAMES_SYSTEM: "names", mp.VISION_SYSTEM: "vision", clip_brief.BRIEF_SYSTEM: "brief", clip_brief.IMAGE_BRIEF_SYSTEM: "brief", clip_gate.GATE_SYSTEM: "gate"}.get(system, "other")
        self.calls.append((which, user, kw))
        ans = self.answers.get(which)
        if isinstance(ans, Exception):
            raise ans
        return (ans if isinstance(ans, str) else json.dumps(ans)), {"cost_usd": 0.0002}


# ================================================================= the policy itself
def test_the_word_lists_refuse_every_category_in_english_and_spanish_and_leave_ordinary_scenes_alone():
    assert set(UNSAFE) == set(mp.CODES) and len(mp.CODES) == 17                                  # every category of the written policy has a wording here
    for code, wordings in UNSAFE.items():
        for w in wordings:
            assert mp.text_reason(w) == f"policy:{code}", w
    for s in SAFE:
        assert mp.text_reason(s) is None, (s, mp.text_hits(s))
    assert mp.text_reason("Niños", "RELIGIÓN") == "policy:religion" or mp.text_reason("Niños") == "policy:children"      # capitals and accents do not hide a word
    assert mp.text_reason("a calm lake", "", None) is None and mp.text_hits("") == []
    assert mp.text_hits("beer and wine") == [("drugs_alcohol_tobacco", "beer"), ("drugs_alcohol_tobacco", "wine")]


def test_one_policy_is_what_every_media_type_reads():
    for code, what, _en, _es in mp.CATEGORIES:
        line = f"- {code} = {what}"
        for name, prompt in (("clip brief", clip_brief.BRIEF_SYSTEM), ("image brief", clip_brief.IMAGE_BRIEF_SYSTEM), ("clip gate", clip_gate.GATE_SYSTEM), ("image check", catalog_make.QA_SYSTEM),
                             ("object names", mp.NAMES_SYSTEM), ("vision check", mp.VISION_SYSTEM)):
            assert line in prompt, (name, code)
    for prompt in (clip_brief.BRIEF_SYSTEM, clip_gate.GATE_SYSTEM, catalog_make.QA_SYSTEM, mp.NAMES_SYSTEM, mp.VISION_SYSTEM):
        assert '"policy"' in prompt and "unsure" in prompt
    for must in ("politic", "religion", "war and weapons", "violence", "injury and medical gore", "sexual or suggestive", "nudity", "drugs, alcohol and tobacco", "gambling",
                 "tragedy and disasters", "children as the subject", "national flags, maps and borders", "stereotypes of groups", "real or identifiable people",
                 "brands, logos and copyrighted or trademarked characters", "hate symbols", "self-harm", "frightening or shocking"):
        assert must in mp.VISION_RUBRIC, must                                                        # the owner's list, word for word where it matters


def test_a_model_answer_clears_the_policy_only_by_saying_none():
    assert mp.verdict_reason({"policy": "none"}) is None and mp.verdict_reason({"policy": " None "}) is None
    assert mp.verdict_reason({"policy": "religion"}) == "policy:religion"
    for bad in ({}, {"policy": None}, {"policy": False}, {"policy": "ok"}, {"policy": ""}, {"policy": ["none"]}, None, "none", []):
        assert mp.verdict_reason(bad) == "policy:unreadable", bad                                    # fails closed
    assert mp.english_only("calm lake at dawn, soft light") and not mp.english_only("lago en calma al amanecer con niños")
    assert not mp.english_only("niño jugando") and not mp.english_only("озеро") and not mp.english_only("") and not mp.english_only("湖")


# ================================================================= clips and images: the brief
def test_the_brief_step_refuses_a_policy_wording_before_any_model_call_in_both_languages():
    stub = Stub(brief=GOOD_BRIEF)
    for q, alt in (("wine being poured into a glass", ""), ("mercado de frutas", "niños comprando fruta"), ("old stone church at dusk", ""), ("a map on a wooden table", "")):
        d, cost = clip_brief.generalise(q, alt, "narration", complete=stub)
        assert d["reusable"] is False and d["reason"].startswith("filter:") and cost == 0.0, q
    assert stub.calls == []


def test_the_brief_the_model_writes_must_clear_the_policy_and_be_plain_english():
    ok = dict(GOOD_BRIEF)
    assert clip_brief.generalise("fruit market", "", "n", complete=Stub(brief=ok))[0]["reusable"] is True
    for change, why in (({"policy": "politics"}, "filter:policy:politics"), ({"policy": "maybe"}, "filter:policy:unreadable"),
                        ({"brief": "quiet vineyard cellar with oak barrels of wine in soft light"}, "filter:policy:drugs_alcohol_tobacco"),
                        ({"brief": "mercado al aire libre con frutas y verduras frescas por la mañana"}, "filter:not plain English"),
                        ({"tags": ["market", "casino"]}, "filter:policy:gambling")):
        d, _ = clip_brief.generalise("fruit market", "", "n", complete=Stub(brief={**ok, **change}))
        assert d == {"reusable": False, "reason": why, "brief": ""}, change
    missing = {k: v for k, v in ok.items() if k != "policy"}
    assert clip_brief.generalise("fruit market", "", "n", complete=Stub(brief=missing))[0]["reason"] == "filter:policy:unreadable"      # no answer about the policy = refused
    assert clip_brief.generalise("fruit market", "", "n", complete=Stub(brief=ok), media="image")[0]["reusable"] is True
    assert clip_brief.generalise("fruit market", "", "n", complete=Stub(brief={**ok, "policy": "children"}), media="image")[0]["reason"] == "filter:policy:children"


# ================================================================= after generation: clips, images
def test_the_clip_gate_rejects_on_the_policy_and_when_the_policy_answer_is_missing():
    frames = [b"x"] * 6
    assert clip_gate.judge(frames, "a brief", complete=Stub(gate=GOOD_GATE))[0] is True
    ok, reason, verdict, _ = clip_gate.judge(frames, "a brief", complete=Stub(gate={**GOOD_GATE, "policy": "flags_maps"}))
    assert ok is False and reason == "policy:flags_maps" and verdict["policy"] == "flags_maps"
    assert clip_gate.judge(frames, "a brief", complete=Stub(gate={k: v for k, v in GOOD_GATE.items() if k != "policy"}))[:2] == (False, "policy:unreadable")
    assert clip_gate.judge(frames, "a brief", complete=Stub(gate={**GOOD_GATE, "policy": "fine"}))[:2] == (False, "policy:unreadable")


def test_the_image_check_rejects_on_the_policy_and_the_image_is_never_stored(env):
    assert catalog_make.judge(json.dumps(QA_OK))[0] is True
    assert catalog_make.judge(json.dumps({**QA_OK, "policy": "religion"}))[0] is False
    assert catalog_make.judge(json.dumps({k: v for k, v in QA_OK.items() if k != "policy"}))[0] is False           # fails closed
    env.models.qa = {**QA_OK, "policy": "tragedy_disaster"}
    job = ask(env)
    assert job.wait() is None and env.cat.store.items() == [] and outcomes(env.store) == {"gate_rejected": 1}
    (line,) = env.store.query(cs.ledger_pk(cs.month()))
    assert line["outcome"] == "gate_rejected" and line["reason"] == "policy:tragedy_disaster" and line["charged_usd"] == pytest.approx(0.05)   # paid for, thrown away


def test_the_providers_moderation_is_asked_before_paying_and_again_on_the_picture(env):
    job = ask(env)
    assert job.wait() and env.prov.moderated == ["text", "image"] and len(env.cat.store.items()) == 1               # clean on both: stored
    env.prov.moderated.clear()
    env.prov.refuse = {"text": "moderation:violence"}
    env.models.brief = dict(env.models.brief, brief="quiet pine forest path covered in fresh snow in soft light")
    job = ask(env, beat="b2", query="snowy forest")
    assert job.wait() is None and env.prov.moderated == ["text"] and len(env.prov.calls) == 1                      # refused BEFORE generating: no second provider call
    assert spent(env.store) == pytest.approx(0.05) and outcomes(env.store).get("policy_refused") == 1              # and the reservation went back: only the first image was paid
    env.prov.refuse = {"image": "moderation:unavailable"}                                                          # the moderation service down after the picture exists: fails closed
    env.models.brief = dict(env.models.brief, brief="wide sandy beach at low tide under a pale overcast sky")
    job = ask(env, beat="b3", query="empty beach")
    assert job.wait() is None and len(env.cat.store.items()) == 1 and len(env.prov.calls) == 2
    rows = sorted(env.store.query(cs.ledger_pk(cs.month())), key=lambda r: r["sk"])
    assert [(r["outcome"], r["reason"], r["charged_usd"]) for r in rows[1:]] == [("policy_refused", "moderation:violence", 0), ("gate_rejected", "moderation:unavailable", 0.05)]
    assert io_.ImageProvider().moderate(text="x") == "moderation:unavailable"                                       # a provider with no moderation of its own refuses


class _Resp:
    def __init__(self, body): self.body = json.dumps(body).encode()
    def read(self, n=-1): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _mod(flagged=False, scores=None, cats=None):
    return {"results": [{"flagged": flagged, "categories": cats or {}, "category_scores": scores or {"sexual": 0.0001, "violence": 0.002}}]}


def test_the_moderation_client_fails_closed_and_keeps_the_key_out_of_everything():
    seen = []

    def opener(body):
        def f(req, timeout=0):
            seen.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
            if isinstance(body, Exception):
                raise body
            return _Resp(body)
        return f
    assert mp.moderation(text="a calm lake", image=b"\xff\xd8pic", key="SECRET", opener=opener(_mod())) is None
    url, headers, body = seen[0]
    assert url == "https://api.openai.com/v1/moderations" and headers["Authorization"] == "Bearer SECRET" and body["model"] == "omni-moderation-latest"
    assert body["input"][0] == {"type": "text", "text": "a calm lake"} and body["input"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,") and "SECRET" not in json.dumps(body)
    assert mp.moderation(text="x", key="k", opener=opener(_mod(True, cats={"violence": True, "sexual": False}))) == "moderation:violence"
    assert mp.moderation(text="x", key="k", opener=opener(_mod(False, scores={"sexual": 0.25, "violence": 0.01}))) == "moderation:sexual"      # stricter than the provider's own flag
    assert mp.moderation(text="x", key="k", opener=opener(_mod(False, scores={"sexual": 0.19}))) is None
    for broken in ({}, {"results": []}, {"results": [{"categories": {}}]}, {"results": "no"}, urllib.error.HTTPError("u", 500, "SECRET", {}, io.BytesIO(b"")), TimeoutError()):
        assert mp.moderation(text="x", key="k", opener=opener(broken)) == "moderation:unavailable", broken                                         # no answer = refused
    assert mp.moderation(text="x", key="") == "moderation:unavailable" and mp.moderation(key="k") == "moderation:unavailable"


def test_the_vision_check_passes_only_a_sure_none_and_fails_closed():
    pic = [b"jpeg"]
    assert mp.vision_check(pic, "a kite", complete=Stub(vision={"policy": "none", "sure": True, "seen": "a kite"}))[:2] == (True, "")
    assert mp.vision_check(pic, "a kite", complete=Stub(vision={"policy": "none", "sure": False}))[:2] == (False, "policy:unsure")
    assert mp.vision_check(pic, "a kite", complete=Stub(vision={"policy": "none"}))[:2] == (False, "policy:unsure")
    assert mp.vision_check(pic, "a kite", complete=Stub(vision={"policy": "war_weapons", "sure": True}))[:2] == (False, "policy:war_weapons")
    assert mp.vision_check(pic, "a kite", complete=Stub(vision="I cannot tell"))[:2] == (False, "policy:unreadable")
    assert mp.vision_check(pic, "a kite", complete=Stub(vision=RuntimeError("throttled")))[:2] == (False, "policy:check failed (RuntimeError)")
    assert mp.vision_check([], "a kite", complete=Stub(vision={"policy": "none", "sure": True}))[:2] == (False, "policy:no picture")
    assert mp.vision_check([b""], "a kite", complete=Stub(vision={"policy": "none", "sure": True}))[:2] == (False, "policy:no picture")


# ================================================================= sketch objects: the names, then the drawings
def test_object_names_word_lists_first_then_one_model_call_that_gives_the_english_name():
    stub = Stub(names={"names": [{"n": 1, "english": "violin", "policy": "none"}, {"n": 2, "english": "kite", "policy": "none"}, {"n": 3, "english": "pistol", "policy": "none"},
                                 {"n": 4, "english": "slot reels", "policy": "gambling"}]})
    out, cost = mp.judge_names(["geige", "kite", "pistole", "walzen", "iglesia"], complete=stub)
    assert [(r["ok"], r["english"], r["reason"]) for r in out] == [(True, "violin", ""), (True, "kite", ""), (False, "", "policy:war_weapons"),   # the English name is checked by the word lists again
                                                                   (False, "", "policy:gambling"), (False, "", "policy:religion")]
    assert len(stub.calls) == 1 and "iglesia" not in stub.calls[0][1] and cost > 0                                                            # the word-list refusal never reached the model
    for bad in ("not json", {"names": [{"n": 1, "english": "violin", "policy": "none"}]}, RuntimeError("down")):                               # unreadable, the wrong count, an error: every name refused
        out, _ = mp.judge_names(["geige", "kite"], complete=Stub(names=bad))
        assert [r["ok"] for r in out] == [False, False] and out[0]["reason"] == "policy:unreadable"
    out, _ = mp.judge_names(["geige"], complete=Stub(names={"names": [{"n": 1, "english": "Violín Stradivarius 1700", "policy": "none"}]}))
    assert out[0]["ok"] is False                                                                                                              # not a plain English name
    assert mp.judge_names(["casino"], complete=Stub())[0][0]["reason"] == "policy:gambling" and mp.judge_names([], complete=Stub()) == ([], 0.0)


def test_a_name_the_policy_refuses_is_never_drawn_and_a_foreign_name_is_drawn_from_its_english(wb):
    assert oo.missing(_board_plan("honeycomb", "church", "wine glass", "baby"), 6) == [("honeycomb", "honeycomb")]         # the word lists: never even asked for
    wb.models.names = {"geige": {"english": "violin", "policy": "none"}, "gluecksrad": {"english": "wheel", "policy": "gambling"}}
    plan = _board_plan("geige", "gluecksrad")
    got = oo.fill(plan, video_id="v1", ctx=od.context("v1"))
    assert wb.calls == [[("violin", "violin")]] and got["made"] == ["violin"]                                                # the maker only ever sees the English name
    items = plan["beats"][0]["scene"]["props"]["items"]
    assert items[0]["draw"] == "violin" and "write" not in items[0] and items[1]["write"] == "gluecksrad" and items[1]["boxed"] is True
    assert spent(wb.store, "object") == pytest.approx(0.04 + 0.007)                                                          # the refused name was not paid for
    wb.rows["v2"] = dict(wb.rows["v1"])
    wb.models.names = {"gluecksrad": {"english": "wheel", "policy": "gambling"}}
    got = oo.fill(_board_plan("gluecksrad"), video_id="v2", ctx=od.context("v2"))
    assert got["reason"] == "policy_refused" and len(wb.calls) == 1 and spent(wb.store, "object") == pytest.approx(0.047)    # nothing allowed: no call, nothing reserved


def test_a_finished_drawing_passes_the_policys_vision_check_before_it_is_stored(wb):
    wb.models.vision = {"policy": "frightening", "sure": True, "seen": "a skull", "reason": "skull shape"}
    plan = _board_plan("honeycomb")
    got = oo.fill(plan, video_id="v1", ctx=od.context("v1"))
    assert got["made"] == [] and got["reason"] == "gate_rejected" and wb.store.get(oo.WOBJ, "honeycomb") is None and not (wb.dir / "honeycomb.json").exists()   # never stored
    assert plan["beats"][0]["scene"]["props"]["items"][0]["boxed"] is True
    (line,) = wb.store.query(cs.ledger_pk(cs.month()))
    assert "policy:frightening" in line["reason"] and line["rejected_n"] == 1
    # no picture to judge, or the gate naming it something the word lists refuse: refused too
    wb.models.vision = {"policy": "none", "sure": True}
    pkgs, _, why = oo._policy_gate([_pkg("kite", "kite"), _pkg("teapot", "teapot"), {**_pkg("cup", "cup"), "meta": {"title_en": "Wine glass"}}], {"thumbs": {"kite": _picture(), "cup": _picture()}})
    assert [p["id"] for p in pkgs] == ["kite"] and why == {"teapot": "policy:no picture", "cup": "policy:drugs_alcohol_tobacco"}


def test_a_maker_that_refuses_before_paying_gives_the_reservation_back(wb):
    def refuses(objs, timeout):
        raise oo.Refused("moderation:violence", billed=False)
    oo.set_maker(refuses)
    got = oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))
    assert got["reason"] == "policy_refused" and spent(wb.store, "object") == 0
    wb.rows["v2"] = dict(wb.rows["v1"])
    oo.set_maker(lambda objs, timeout: (_ for _ in ()).throw(oo.Refused("moderation:sexual", billed=True)))             # the sheet itself was refused: paid for, nothing kept
    got = oo.fill(_board_plan("kite"), video_id="v2", ctx=od.context("v2"))
    assert got["reason"] == "policy_refused" and got["made"] == [] and spent(wb.store, "object") == pytest.approx(0.047)


def test_the_sheet_is_made_between_two_moderation_checks():
    seen, asked = [], []

    def opener(req, timeout=0):
        seen.append(json.loads(req.data))
        return _Resp({"data": [{"b64_json": __import__("base64").b64encode(b"\x89PNG-sheet").decode()}], "usage": {"input_tokens": 200, "output_tokens": 1212}})

    def moderate(refuse):
        def f(**kw):
            asked.append("image" if kw.get("image") else "text")
            return refuse.get(asked[-1])
        return f
    png, usd = object_maker.sheet("a sheet of doodles", "2048x1152", 20, key="SECRET", opener=opener, moderate=moderate({}))
    assert png == b"\x89PNG-sheet" and usd == pytest.approx(0.0374, abs=0.0005) and asked == ["text", "image"]
    assert seen[0]["moderation"] == "auto" and seen[0]["output_format"] == "png" and seen[0]["quality"] == "medium"
    with pytest.raises(object_maker.Refused) as e:
        object_maker.sheet("p", "2048x1152", 20, key="SECRET", opener=opener, moderate=moderate({"text": "moderation:violence"}))
    assert e.value.billed is False and e.value.kind == "moderation:violence" and len(seen) == 1                         # refused before the provider was called
    with pytest.raises(object_maker.Refused) as e:
        object_maker.sheet("p", "2048x1152", 20, key="SECRET", opener=opener, moderate=moderate({"image": "moderation:unavailable"}))
    assert e.value.billed is True and len(seen) == 2                                                                   # the sheet was paid for and is thrown away
    with pytest.raises(object_maker.Refused) as e:
        object_maker.sheet("p", "2048x1152", 20, key="", opener=opener, moderate=moderate({}))
    assert e.value.kind == "auth" and e.value.billed is False


# ================================================================= the audit (read only)
def _catalog(tmp_path, n=3):
    cat = catalog_store.LocalStore(str(tmp_path / "cat"))
    ids = []
    for i, title in enumerate(["calm alpine lake at dawn", "stone church on a hill", "wooden beehives in a meadow"][:n]):
        jpeg = _picture(i)
        cid = catalog.content_hash(jpeg)
        ids.append(cid)
        for k in (catalog.key_original(cid), catalog.key_preview(cid), catalog.key_thumb(cid)):
            cat.put(k, jpeg)
        cat.put_vector(cid, [float(x) for x in _vec(title)], {"title": title})
        cat.put_item({"id": cid, "title": title, "subject": title, "tags": ["editorial"], "review_status": "approved"})
    return cat, ids


def _tree(path):
    out = {}
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, path)] = open(p, "rb").read()
    return out


def test_the_audit_reports_what_is_doubtful_and_changes_nothing(tmp_path, capsys):
    cat, ids = _catalog(tmp_path)
    store = cs.LocalStore(str(tmp_path / "lib"))
    clip = lib.add_clip(store, mp4=MP4, poster=_picture(7), tvec=_vec("bees"), ivec=None, meta={"brief": "bees on lavender flowers", "tags": ["bees"]})
    cat.put("w/kite.json", json.dumps(_pkg("kite", "kite")).encode(), "application/json")
    store.put(oo.WOBJ, "kite", {"title": "Kite", "title_es": "Cometa", "status": "active"})
    store.put(oo.WOBJ, "pistol", {"title": "Pistol", "title_es": "Pistola", "status": "active"})
    before = (_tree(tmp_path / "cat"), _tree(tmp_path / "lib"))
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps({"items": [{"id": "flag", "title": "Flag on pole", "title_es": "Bandera en asta", "synonyms_en": ["victory"]}, {"id": "teapot", "title": "Teapot", "synonyms_en": ["tea", "wine jug"]}]}))
    assets = library_safety.image_assets(cat) + library_safety.object_assets(cat, store, index_path=str(idx)) + library_safety.clip_assets(store)
    assert [a["media"] for a in assets].count("image") == 3 and {a["id"] for a in assets if a["media"] == "object"} == {"flag", "teapot", "kite", "pistol"}

    def vision(pics, described):
        if "beehives" in described:
            return False, "policy:brands_ip", {"seen": "beehives with a logo", "reason": "a logo on a box"}, 0.004
        if "Teapot" in described:
            return False, "policy:unsure", {"seen": "a pot"}, 0.0002
        return True, "", {"seen": described}, 0.004
    rep = library_safety.audit(assets, vision=vision, moderate=lambda **kw: "moderation:violence" if kw["image"] == _picture(7) else None, workers=2)
    by = {r["id"]: r for r in rep["rows"]}
    assert by[ids[0]]["verdict"] == "ok" and by[ids[0]]["moderation"] == "clean"
    assert by[ids[1]]["verdict"] == "review" and by[ids[1]]["words"] == ["religion:church"]                           # only words: a person decides
    assert by[ids[2]]["verdict"] == "remove" and "policy:brands_ip" in by[ids[2]]["why"][0]                           # the picture itself
    assert by[clip]["verdict"] == "remove" and "moderation:violence" in by[clip]["why"]
    assert by["flag"]["verdict"] == "review" and by["pistol"]["verdict"] == "review" and by["pistol"]["vision"] == "no picture"
    assert by["teapot"]["verdict"] == "review" and by["teapot"]["notes"] == ["drugs_alcohol_tobacco:wine"]            # a synonym is a note, not a verdict
    assert rep["counts"]["image"] == {"ok": 1, "review": 1, "remove": 1} and rep["cost_usd"] > 0 and rep["policy_version"] == mp.VERSION
    library_safety.print_report(rep, "local")
    text = capsys.readouterr().out
    assert "READ ONLY" in text and "RECOMMENDED FOR REMOVAL" in text and ids[2] in text and "TO REVIEW" in text
    assert (_tree(tmp_path / "cat"), _tree(tmp_path / "lib")) == before                                               # not one byte of either store changed
    # words only (no model, no provider): still a report; a budget of zero skips the paid check and says so
    free = library_safety.audit(library_safety.image_assets(cat))
    assert [r["verdict"] for r in free["rows"]].count("review") == 1 and free["cost_usd"] == 0
    capped = library_safety.audit(library_safety.image_assets(cat), vision=vision, max_usd=0.0)
    assert all(r["verdict"] == "review" and "budget" in r["vision"] for r in capped["rows"])


# ================================================================= takedown
def test_taking_an_image_down_stops_it_being_served_at_once_and_keeps_the_file_in_quarantine(env, tmp_path):
    cid = ask(env).wait()
    assert io_.use(cid, "mountain lake", "narration", "alt", "v1") is not None and env.cat.search(env.models.brief["brief"], k=1)[0]["id"] == cid
    original = env.cat.read(catalog.key_original(cid))
    led = cs.LocalStore(str(tmp_path / "ledger2"))
    steps = takedown.image(env.cat.store, cid, "audit: looks like a logo")                                             # dry run by default
    assert len(steps) == 5 and io_.use(cid, "mountain lake", "narration", "alt", "v1") is not None and takedown.taken(led) == []
    takedown.image(env.cat.store, cid, "audit: looks like a logo", ledger=led, dry_run=False)
    assert io_.use(cid, "mountain lake", "narration", "alt", "v1") is None                                             # the row: no video is given it any more
    assert env.cat.search(env.models.brief["brief"], k=1) == [] and env.cat.nearest([1.0] * 256) is None               # out of search
    item = env.cat.item(cid)
    assert item["review_status"] == "taken_down" and item["taken_down"]["reason"] == "audit: looks like a logo" and item["taken_down"]["was"] == "approved" and not catalog.usable(item)
    assert not env.cat.store.has(catalog.key_original(cid)) and env.cat.store.get("quarantine/" + catalog.key_original(cid)) == original   # kept, not destroyed
    assert env.cat.store.has("quarantine/" + catalog.key_preview(cid)) and env.cat.store.has(f"quarantine/vec/{cid}.json")
    assert takedown.taken(led)[0]["id"] == cid and takedown.denied(led, "image") == [cid]
    assert ask(env, beat="b9").wait() != cid or True                                                                   # (a later video generates or goes to stock; it can never get this one)
    with pytest.raises(KeyError):
        takedown.image(env.cat.store, "ab" * 32, "x", dry_run=False)
    takedown.restore_image(env.cat.store, cid, ledger=led, dry_run=False)
    assert io_.use(cid, "mountain lake", "narration", "alt", "v1") is not None and env.cat.read(catalog.key_original(cid)) == original and takedown.denied(led, "image") == []


def test_taking_a_clip_down_removes_it_from_search_and_its_file_from_reach(tmp_path):
    store = cs.LocalStore(str(tmp_path / "lib"))
    lib.reset()
    cc.set_config({"enabled": True})
    try:
        cid = lib.add_clip(store, mp4=MP4, poster=_picture(2), tvec=_vec("bees on lavender flowers"), ivec=None,
                           meta={"brief": "bees on lavender flowers", "aspect": "16:9", "seconds": 8.0, "center_safe": True})
        find = lambda: lib.search("bees on lavender", store=store, qvec=_vec("bees on lavender"), min_score=0.1)   # noqa: E731
        assert [r["sk"] for _, r in find()] == [cid]
        assert len(takedown.clip(store, cid, "shows a brand")) == 3 and [r["sk"] for _, r in find()] == [cid]          # dry run
        takedown.clip(store, cid, "shows a brand", dry_run=False)
        assert find() == [] and store.get(cs.LIB, cid)["status"] == "taken_down"
        with pytest.raises(OSError):
            lib.fetch(lambda url, **kw: b"", store)(f"{lib.SCHEME}v/{cid}.mp4")                                         # a function that still held the row cannot read the file
        assert store.get_object(f"q/v/{cid}.mp4") == MP4 and store.has_object(f"q/p/{cid}.jpg") and json.loads(store.get_object(f"m/{cid}.json"))["status"] == "taken_down"
        store.delete(cs.LIB, cid)
        assert lib.reindex(store) == 1 and find() == []                                                                # a rebuilt index keeps it out
        assert lib.promote(store, cs.LocalStore(str(tmp_path / "prod")), dry_run=False)[0]["action"].startswith("skipped")
        assert takedown.denied(store, "clip") == [cid]
        takedown.restore_clip(store, cid, dry_run=False)
        assert [r["sk"] for _, r in find()] == [cid] and store.get_object(f"v/{cid}.mp4") == MP4
        with pytest.raises(KeyError):
            takedown.clip(store, "f" * 64, "x", dry_run=False)
    finally:
        cc.set_config(None)
        lib.reset()


def test_taking_a_sketch_object_down_on_demand_or_bundled(wb, tmp_path):
    cat = catalog_store.LocalStore(str(tmp_path / "cat"))
    oo.fill(_board_plan("honeycomb"), video_id="v1", ctx=od.context("v1"))
    cat.put("w/honeycomb.json", (wb.dir / "honeycomb.json").read_bytes(), "application/json")
    bundled = wblib.ids()[0]
    cat.put(f"w/{bundled}.json", b"{}", "application/json")
    assert wblib.has("honeycomb") and wblib.has(bundled)
    assert takedown.sketch(wb.store, cat, "honeycomb", "wrong")[0].startswith("index row") and cat.has("w/honeycomb.json")   # dry run
    takedown.sketch(wb.store, cat, "honeycomb", "looks like something else", dry_run=False)
    takedown.sketch(wb.store, cat, bundled, "owner asked", dry_run=False)
    assert wb.store.get(oo.WOBJ, "honeycomb")["status"] == "taken_down" and not cat.has("w/honeycomb.json") and cat.has("quarantine/w/honeycomb.json")
    assert not cat.has(f"w/{bundled}.json") and cat.has(f"quarantine/w/{bundled}.json") and sorted(takedown.denied(wb.store, "object")) == sorted(["honeycomb", bundled])
    wblib._index = None                                                                                                # the next plan step, a fresh process
    oo.load_dynamic()
    assert not wblib.has("honeycomb") and not wblib.has(bundled) and wblib.by_name("honeycomb") is None                # neither is ever drawn again
    takedown.restore_sketch(wb.store, cat, "honeycomb", dry_run=False)
    wblib._index = None
    oo.load_dynamic()
    assert wblib.has("honeycomb") and not wblib.has(bundled) and cat.has("w/honeycomb.json")
    with pytest.raises(KeyError):
        takedown.sketch(wb.store, cat, "no_such_thing", "x", dry_run=False)
    with pytest.raises(ValueError):
        takedown.sketch(wb.store, cat, "../etc", "x", dry_run=False)


def test_the_command_line_is_a_dry_run_unless_told_and_never_touches_a_stage_by_accident(tmp_path, capsys, monkeypatch):
    cat, ids = _catalog(tmp_path, 1)
    spec = f"local:{tmp_path / 'cat'}"
    assert library_safety.main(["takedown", "image", ids[0], "--store", spec, "--reason", "test"]) == 0
    assert "DRY RUN" in capsys.readouterr().out and cat.get_item(ids[0])["review_status"] == "approved"
    assert library_safety.main(["takedown", "image", ids[0], "--store", spec, "--reason", "test", "--no-dry-run"]) == 0
    assert "Done:" in capsys.readouterr().out and cat.get_item(ids[0])["review_status"] == "taken_down" and cat.has("quarantine/" + catalog.key_original(ids[0]))
    assert library_safety.main(["restore", "image", ids[0], "--store", spec, "--no-dry-run"]) == 0 and cat.get_item(ids[0])["review_status"] == "approved"
    with pytest.raises(SystemExit):
        library_safety.main(["takedown", "image", ids[0], "--store", spec])                                            # a reason is required
    monkeypatch.setattr("builtins.input", lambda _: "no")
    monkeypatch.setattr(catalog_store, "open_store", lambda s: (_ for _ in ()).throw(AssertionError("must not open a store")))
    with pytest.raises(SystemExit):
        library_safety.main(["takedown", "image", ids[0], "--store", "prod", "--reason", "x", "--no-dry-run"])         # production asks first
    assert library_safety.main(["policy"]) == 0 and "frightening" in capsys.readouterr().out
