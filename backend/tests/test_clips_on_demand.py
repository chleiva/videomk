"""Library clips on demand (docs/CLIPS_ON_DEMAND.md): every rule has a test. No network, no model, no provider: the provider is a Mock, the models are stubs,
the embedder is a deterministic bag of words, the store is a folder (and DynamoDB through moto for the transaction)."""
import io
import json
import re
import subprocess
import threading
import time

import boto3
import numpy as np
import pytest
from PIL import Image

from common import clip_config as cc, clip_store as cs, deletion
from engine import clip_brief, clip_gate, clip_gen, clip_library as lib, clip_ondemand as od, clips, llm, media

MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x01" * 20_000   # passes the provider's "is it an MP4" look; the gate's probe is stubbed where this is used
ON = {"enabled": True}


def _vec(text):
    """A deterministic 'embedding': one dimension per word (hashed), so texts that share words are close."""
    v = np.zeros(256, dtype=np.float32)
    for w in re.findall(r"[a-z]+", str(text).lower()):
        if len(w) > 2:
            v[sum(ord(c) * (i + 7) for i, c in enumerate(w)) % 256] += 1.0
    return v if v.any() else np.ones(256, dtype=np.float32)


def _jpeg(shade=120):
    b = io.BytesIO()
    Image.new("RGB", (64, 36), (shade, shade, shade)).save(b, "JPEG")
    return b.getvalue()


def _info(seconds=8.0, w=1280, h=720, moving=True):
    rng = np.random.default_rng(1)
    base = rng.uniform(60, 180, (36, 64)).astype(np.float32)
    gray = [base + (i * 3.0 if moving else 0.0) for i in range(6)]
    return {"width": w, "height": h, "seconds": seconds, "frames": [_jpeg(100 + i) for i in range(6)], "gray": gray}


GOOD_BRIEF = {"reusable": True, "reason": "general", "brief": "busy outdoor fruit market stall, close on hands choosing ripe fruit", "tags": ["market", "fruit", "hands"], "people": "hands", "motion": "slow", "policy": "none"}
GOOD_GATE = {"score": 9, "artefacts": False, "text": False, "brand": False, "person": False, "unsafe": False, "cut": False, "center_safe": True, "policy": "none", "reason": "clean"}


class Different(clip_gen.Mock):
    """A provider whose every generation is its own file."""

    def generate(self, prompt, **kw):
        out = super().generate(prompt, **kw)
        return {**out, "mp4": out["mp4"] + prompt.encode()}


class Models:
    """Stands in for llm.complete: the brief model and the gate model, told apart by their system prompt."""

    def __init__(self, brief=None, gate=None):
        self.brief, self.gate, self.calls = brief or GOOD_BRIEF, gate or GOOD_GATE, []

    def __call__(self, system, user, **kw):
        which = "brief" if system == clip_brief.BRIEF_SYSTEM else "gate" if system == clip_gate.GATE_SYSTEM else "other"
        self.calls.append(which)
        ans = self.brief if which == "brief" else self.gate
        return (ans if isinstance(ans, str) else json.dumps(ans)), {"cost_usd": 0.001}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """The feature switched on over a folder store, a Mock provider, stub models, a paying monthly Max account that has used 40 credits."""
    monkeypatch.setenv("CLIPS_ON_DEMAND", "1")
    store = cs.LocalStore(str(tmp_path / "lib"))
    cs.set_store(store)
    cc.set_config(dict(ON))
    lib.reset()
    lib.set_embedder(query=_vec, doc=_vec, image=lambda jpeg: _vec("picture"))
    models = Models()
    monkeypatch.setattr(llm, "complete", models)
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info())
    monkeypatch.setattr(od, "_silent", lambda mp4: mp4)
    prov = clip_gen.Mock(MP4)
    clip_gen.set_provider(prov)
    rows = {"v1": {"user_id": "u1", "plan": "max", "plan_interval": "month", "plan_source": "apple", "plan_state": "active"}}
    credits = {"u1": 40}
    od.set_readers(video=lambda vid: rows.get(vid), credits=lambda user, now: credits.get(user, 0))

    class E:
        pass
    e = E()
    e.store, e.models, e.prov, e.rows, e.credits = store, models, prov, rows, credits
    yield e
    cs.set_store(None)
    cc.set_config(None)
    clip_gen.set_provider(None)
    od.reset()
    lib.reset()


def ask(env, video="v1", beat="b1", query="fruit market", alt="people buying fruit outdoors", need=7.0, **kw):
    ctx = od.context(video)
    return od.begin(video_id=video, beat_id=beat, query=query, alt=alt, narration="Markets are where fresh food changes hands every morning.", need_seconds=need, ctx=ctx,
                    plan=kw.pop("plan", {"beats": []}), **kw)


def spent(store, kind="paid", span="day"):
    return cs.usd((store.get(cs.spend_pk(kind, span), cs.day() if span == "day" else cs.month()) or {}).get("spent"))


def ledger(store):
    return store.query(cs.ledger_pk(cs.month()))


def outcomes(store):
    return {k[2:]: v for k, v in (store.get(cs.STATS, cs.day()) or {}).items() if k.startswith("d_")}


# ================================================================= the knobs and the maths
def test_generation_is_off_by_default_and_needs_both_switches(monkeypatch):
    cc.set_config({})
    try:
        assert cc.config()["enabled"] is False and not cc.generation_on()
        monkeypatch.setenv("CLIPS_ON_DEMAND", "1")
        assert not cc.generation_on()                      # the flag alone is not enough
        cc.set_config({"enabled": True})
        assert cc.generation_on()
        monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
        assert not cc.generation_on()                      # the knob alone is not enough
    finally:
        cc.set_config(None)


def test_a_bad_knob_falls_back_to_its_default_and_the_admin_value_is_refused():
    cfg = cc.clean_config({"platform_day_usd": "lots", "video_cap_clips": 2.5, "share": 7, "account_cap_usd": 4, "reuse_plans": ["max", "gold"], "unknown": 1})
    assert cfg["platform_day_usd"] == 10.0 and cfg["video_cap_clips"] == 2 and cfg["share"] == 0.5 and cfg["account_cap_usd"] == 4.0 and sorted(cfg["reuse_plans"]) == ["free", "max", "pro", "test"]
    with pytest.raises(ValueError):
        cc.coerce("share", 1.5)
    assert cc.coerce("enabled", "off") is False and cc.coerce("reuse_plans", "max,test") == ["max", "test"]


def test_a_config_that_cannot_be_read_leaves_generation_off(monkeypatch):
    monkeypatch.setenv("CLIPS_CONFIG_PARAM", "/videomk/test/clips/config")
    monkeypatch.setattr(cc, "_read_raw", lambda: (_ for _ in ()).throw(RuntimeError("ssm down")))
    cc.set_config(None)
    assert cc.config()["enabled"] is False


def test_what_the_providers_own_token_counts_come_to():
    usage = {"total_input_tokens": 132, "total_output_tokens": 5793, "output_tokens_by_modality": [{"modality": "video", "tokens": 5793}], "total_thought_tokens": 1166}   # a real 3 s 360p answer
    assert clip_gen.usage_usd(usage) == pytest.approx(0.0802, abs=0.0001) and clip_gen.usage_usd(None) is None and clip_gen.usage_usd({"output_tokens_by_modality": "x"}) is None


def test_the_price_of_a_generation():
    assert cc.price_usd(8, cc.clean_config({})) == pytest.approx(0.581) and cc.price_usd(10, cc.clean_config({})) == pytest.approx(0.72)


def test_the_account_allowance_is_half_of_what_is_left_after_all_credits_at_the_high_cost():
    cfg = cc.clean_config({})
    assert cc.account_allowance_usd("month", 0, cfg) == pytest.approx(2.915)          # 0.5 x (30.83 - 1 - 24)
    assert cc.account_allowance_usd("month", 120, cfg) == pytest.approx(2.915)        # the whole grant is reserved from the first day: using it changes nothing
    assert cc.account_allowance_usd("year", 0, cfg) == pytest.approx(0.35)            # less than one clip
    assert cc.account_allowance_usd("month", 130, cfg) == pytest.approx(1.915)        # rolled-over credits: 10 cents each
    assert cc.account_allowance_usd("month", 149, cfg) < 0.02 and cc.account_allowance_usd("month", 150, cfg) == 0.0 and cc.account_allowance_usd("month", 240, cfg) == 0.0
    assert cc.account_allowance_usd("month", 0, cc.clean_config({"credit_cost_usd": 0.09})) == 3.0   # a cheaper credit never lifts it over the cap


@pytest.mark.parametrize("interval,kept", [("month", 30.83), ("month", 32.48), ("month", 33.99), ("year", 25.70), ("year", 27.07), ("year", 28.33)])
@pytest.mark.parametrize("used", [0, 60, 120])
def test_the_invariant_no_month_ends_under_the_floor(interval, kept, used):
    """kept - cost of the credits at p90 - the whole clip allowance >= floor, for every storefront and every use of the month's grant."""
    cfg = cc.clean_config({})
    assert kept - 0.20 * used - cc.account_allowance_usd(interval, used, cfg) >= cfg["floor_usd"] - 1e-9


# ================================================================= who may generate
@pytest.mark.parametrize("ctx,want", [
    ({"plan": "free"}, None), ({"plan": "pro", "plan_source": "apple", "plan_state": "active"}, None), (None, None), ({}, None),
    ({"plan": "max", "plan_source": "apple", "plan_state": "active"}, "paid"), ({"plan": "max", "plan_source": "google", "plan_state": "active"}, "paid"),
    ({"plan": "max", "plan_source": "web", "plan_state": "active"}, "paid"),
    ({"plan": "max", "plan_source": "admin", "plan_state": "active"}, "test"),       # granted by an admin: no revenue, so the test budget
    ({"plan": "max"}, "test"),                                                        # an old row without a source: never the paying budget
    ({"plan": "max", "plan_source": "apple", "plan_state": "grace"}, None),          # the renewal has not been paid
    ({"plan": "test"}, "test"), ({"plan": "gold"}, None)])
def test_entitlement(ctx, want):
    assert od.entitlement(ctx) == want


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_free_and_pro_never_generate_but_do_reuse_the_library(env, plan):
    env.rows["v1"] = {"user_id": "u1", "plan": plan, "plan_source": "apple", "plan_state": "active"}
    assert ask(env) is None and env.prov.calls == [] and env.models.calls == [] and spent(env.store) == 0
    assert lib.usable(plan) and not lib.usable(plan, cc.clean_config({"reuse_plans": ["max", "test"]}))


def test_flag_off_means_nothing_runs(env, monkeypatch):
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    assert ask(env) is None and env.prov.calls == [] and env.models.calls == [] and env.store.query(cs.STATS) == []


def test_the_kill_switch_stops_generation_and_says_so(env):
    cc.set_config({"enabled": False})
    assert ask(env) is None and env.prov.calls == [] and outcomes(env.store) == {"kill_switch": 1}
    assert lib.usable("free")                                   # reuse goes on
    cc.set_config({"enabled": False, "reuse_enabled": False})
    assert not lib.usable("max")


def test_never_on_the_persons_own_photos_a_deck_or_an_edit(env):
    assert ask(env, plan={"media_items": [{"id": "p1"}]}) is None
    assert ask(env, plan={"deck": {"slides": 3}}) is None
    assert ask(env, is_edit=True) is None
    assert env.prov.calls == [] and outcomes(env.store) == {"own_photos": 2, "edit": 1}


def test_too_late_in_the_beat_or_a_beat_too_long_for_a_clip(env, monkeypatch):
    assert ask(env, beat_started=time.time() - 61) is None
    assert ask(env, need=14.0) is None                          # 75 % of 14 s is more than the 10 s the provider is asked for
    assert env.prov.calls == [] and outcomes(env.store) == {"too_late": 1, "too_long": 1}
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info(seconds=10.0))
    job = ask(env, need=9.5)
    assert job.wait() and env.prov.calls[0]["seconds"] == 10    # a longer beat gets the longer clip


# ================================================================= is it reusable?
@pytest.mark.parametrize("query,alt,why", [
    ("Maria buying mangoes", "", "personal"), ("my son playing football", "", "personal"), ("market in 1985", "", "personal"),
    ("presidential election rally", "", "news"), ("protesters in the street", "", "news"), ("coca-cola bottle on a table", "", "brand"), ("company logo on a wall", "", "brand"),
    ("famous actor on a red carpet", "", "identity"), ("close-up of a woman smiling", "", "identity"), ("newspaper headline", "", "text or graphic"),
    ("stock chart on a screen", "", "text or graphic"), ("dna animation", "", "text or graphic"), ("car crash on a road", "", "unsafe"),
    ("fruit market", "The market of Oaxaca in the rain", "proper noun"), ("", "", "empty")])
def test_searches_that_can_never_become_a_library_clip_are_refused_without_a_model_call(query, alt, why):
    assert why in (clip_brief.pre_filter(query, alt) or "")
    called = []
    d, cost = clip_brief.generalise(query, alt, "n", complete=lambda *a, **k: called.append(1))
    assert d["reusable"] is False and d["reason"].startswith("filter:") and cost == 0 and called == []


@pytest.mark.parametrize("query", ["fruit market", "waves on a rocky shore", "hands kneading bread dough", "misty forest at dawn", "bees on a flower", "steam rising from a cup of coffee"])
def test_general_searches_pass_the_filter(query):
    assert clip_brief.pre_filter(query, "a second general wording") is None


def test_the_model_turns_a_specific_search_into_a_general_brief():
    d, cost = clip_brief.generalise("woman buying mangoes at a market", "rainy day fruit stall", "n", complete=Models())
    assert d["reusable"] and d["brief"] == GOOD_BRIEF["brief"] and d["tags"] == ["market", "fruit", "hands"] and d["people"] == "hands" and cost == 0.001


@pytest.mark.parametrize("answer,reason", [
    ({"reusable": False, "reason": "needs a specific landmark"}, "not_reusable:needs a specific landmark"),
    ("I think this is fine", "not_reusable:unreadable answer"), ({"reusable": "yes"}, "not_reusable:unreadable answer"),
    ({**GOOD_BRIEF, "people": "faces"}, "filter:people"), ({**GOOD_BRIEF, "motion": "fast"}, "filter:motion"),
    ({**GOOD_BRIEF, "brief": "a market"}, "filter:brief length"), ({**GOOD_BRIEF, "brief": "a market stall in the year 1999 with ripe fruit"}, "filter:digits"),
    ({**GOOD_BRIEF, "brief": "the old market of Oaxaca with ripe fruit on wooden stalls"}, "filter:proper noun"),
    ({**GOOD_BRIEF, "brief": "a shop sign above a market stall with ripe fruit"}, "filter:text or graphic"),
    ({**GOOD_BRIEF, "brief": "a large crowd pushing through a busy market street"}, "filter:crowd"),
    ({**GOOD_BRIEF, "brief": "cars racing down a wet street at night in the city"}, "filter:fast motion")])
def test_what_the_model_answers_is_checked_and_anything_else_is_a_refusal(answer, reason):
    d, _ = clip_brief.generalise("fruit market", "fruit stall", "n", complete=Models(brief=answer))
    assert d["reusable"] is False and d["reason"] == reason


def test_a_failing_model_is_a_refusal_not_an_error():
    d, cost = clip_brief.generalise("fruit market", "", "n", complete=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bedrock down")))
    assert d["reusable"] is False and d["reason"].startswith("not_reusable:error")


def test_the_prompt_is_written_by_code_with_the_clauses_against_known_failures():
    p = clip_brief.build_prompt(GOOD_BRIEF["brief"], people="hands", aspect="9:16")
    for clause in ("one continuous shot", "Slow, steady camera", "main subject centred", "No text", "logos", "no fast motion", "no crowds", "No cuts", "no faces", "vertical 9:16"):
        assert clause in p, clause
    assert "No people in the shot." in clip_brief.build_prompt("misty forest at dawn with slow drifting fog") and "wide 16:9" in clip_brief.build_prompt("x y z w")
    assert clip_brief.brief_key("fruit market stall hands") == clip_brief.brief_key("Hands, market stall: fruit") != clip_brief.brief_key("forest fog")


def test_a_not_reusable_search_spends_nothing_and_logs_why(env):
    env.models.brief = {"reusable": False, "reason": "specific place"}
    assert ask(env) is None and env.prov.calls == [] and spent(env.store) == 0 and outcomes(env.store) == {"not_reusable": 1}
    assert ask(env, query="Maria at the market") is None and outcomes(env.store)["filter"] == 1


# ================================================================= the quality gate
def test_technical_checks():
    ok = _info()
    assert clip_gate.technical(ok, asked_seconds=8, aspect="16:9") is None
    assert clip_gate.technical(_info(seconds=6.9), asked_seconds=8, aspect="16:9") == "too short"
    assert clip_gate.technical(_info(w=640, h=360), asked_seconds=8, aspect="16:9") == "wrong size or shape"
    assert clip_gate.technical(_info(), asked_seconds=8, aspect="9:16") == "wrong size or shape"            # a landscape file when a vertical one was asked
    assert clip_gate.technical(_info(w=720, h=1280), asked_seconds=8, aspect="9:16") is None
    assert clip_gate.technical(_info(moving=False), asked_seconds=8, aspect="16:9") == "no motion"
    black = _info(); black["gray"][3] = np.zeros((36, 64), dtype=np.float32)
    assert clip_gate.technical(black, asked_seconds=8, aspect="16:9") == "black or blank frame"
    cut = _info(); cut["gray"][3:] = [g[::-1, ::-1] * 0.2 + 150 for g in cut["gray"][3:]]
    assert clip_gate.technical(cut, asked_seconds=8, aspect="16:9") == "abrupt change (cut)"
    few = _info(); few["frames"] = few["frames"][:3]
    assert clip_gate.technical(few, asked_seconds=8, aspect="16:9") == "unreadable video"


@pytest.mark.parametrize("flag", ["artefacts", "text", "brand", "person", "unsafe", "cut"])
def test_any_flag_rejects_the_clip(flag):
    r = clip_gate.check(MP4, "brief", asked_seconds=8, complete=Models(gate={**GOOD_GATE, flag: True}), probe_fn=lambda m: _info())
    assert r["ok"] is False and r["reason"] == flag


def test_the_gate_passes_a_clean_clip_and_keeps_its_poster_and_crop_verdict():
    r = clip_gate.check(MP4, "brief", asked_seconds=8, complete=Models(), probe_fn=lambda m: _info())
    assert r["ok"] and r["score"] == 9 and r["center_safe"] is True and r["poster"][:2] == b"\xff\xd8" and (r["width"], r["height"], r["seconds"]) == (1280, 720, 8.0)


@pytest.mark.parametrize("gate", [{**GOOD_GATE, "score": 6}, "no json here", {"score": 9}, {**GOOD_GATE, "score": "high"}, {**GOOD_GATE, "text": "no"}])
def test_the_gate_fails_closed(gate):
    assert clip_gate.check(MP4, "brief", asked_seconds=8, complete=Models(gate=gate), probe_fn=lambda m: _info())["ok"] is False


def test_a_gate_that_cannot_run_rejects():
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
    assert clip_gate.check(MP4, "b", asked_seconds=8, complete=boom, probe_fn=lambda m: _info())["ok"] is False
    assert clip_gate.check(MP4, "b", asked_seconds=8, complete=Models(), probe_fn=boom)["ok"] is False
    no_model = []
    assert clip_gate.check(MP4, "b", asked_seconds=8, complete=lambda *a, **k: no_model.append(1), probe_fn=lambda m: _info(seconds=2))["reason"] == "too short" and no_model == []


# ================================================================= ours first: generate -> gate -> library -> the video
def test_a_generated_clip_is_stored_in_the_library_with_everything_before_anyone_gets_it(env):
    job = ask(env)
    cid = job.wait()
    assert cid and job.generated and len(env.prov.calls) == 1 and env.models.calls == ["brief", "gate"]
    call = env.prov.calls[0]
    assert call["seconds"] == 8 and call["aspect"] == "16:9" and "fruit market stall" in call["prompt"].lower() and "Markets are where" not in call["prompt"]   # only the general brief goes out
    doc = json.loads(env.store.get_object(f"m/{cid}.json"))
    assert doc["brief"] == GOOD_BRIEF["brief"] and doc["license"] == "VideoMK library" and doc["scope"] == "library" and doc["cost_usd"] == pytest.approx(0.581)
    assert doc["prompt"] == call["prompt"] and doc["provider"] == "mock" and doc["aspect"] == "16:9" and doc["seconds"] == 8.0 and doc["center_safe"] is True
    assert doc["demand_video"] == lib.video_ref("v1") and "v1" not in json.dumps(doc) and "u1" not in json.dumps(doc) and doc["tvec"] and doc["ivec"] and doc["paid_by"] == "paid"
    assert env.store.get_object(f"v/{cid}.mp4") == MP4 and env.store.has_object(f"p/{cid}.jpg")
    row = env.store.get(cs.LIB, cid)
    assert row["uses"] == 0 and row["brief"] == doc["brief"]
    # the money: one price on the four counters, a closed ledger line, no lock left
    assert spent(env.store) == spent(env.store, span="month") == pytest.approx(0.581)
    assert cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"]) == pytest.approx(0.581) and env.store.get(cs.VIDEO + "v1", "n")["n"] == 1
    (line,) = ledger(env.store)
    assert line["outcome"] == "generated" and line["clip_id"] == cid and line["charged_usd"] == pytest.approx(0.581) and line["kind"] == "paid" and line["account"] == lib.account_ref("u1")
    assert env.store.query(cs.LOCK) == [] and outcomes(env.store) == {"generated": 1}
    assert spent(env.store, "test") == 0


def test_a_rejected_clip_is_never_stored_and_still_counts_against_the_budgets(env):
    env.models.gate = {**GOOD_GATE, "artefacts": True}
    job = ask(env)
    assert job.wait() is None and not job.generated
    assert env.store.list_objects("v/") == [] and env.store.list_objects("m/") == [] and env.store.query(cs.LIB) == []
    assert spent(env.store) == pytest.approx(0.581) and ledger(env.store)[0]["outcome"] == "gate_rejected" and ledger(env.store)[0]["reason"] == "artefacts"
    assert outcomes(env.store) == {"gate_rejected": 1} and env.store.query(cs.LOCK) == []


def test_a_provider_refusal_before_anything_was_made_gives_the_money_back(env):
    clip_gen.set_provider(clip_gen.Mock(error=clip_gen.GenError("blocked", "policy", billed=False)))
    assert ask(env).wait() is None
    assert spent(env.store) == 0 and spent(env.store, span="month") == 0 and env.store.get(cs.VIDEO + "v1", "n")["n"] == 0 and env.store.get(cs.ACCT + "u1", cs.month())["spent"] == 0
    assert ledger(env.store)[0]["outcome"] == "provider_failed" and ledger(env.store)[0]["charged_usd"] == 0


def test_a_provider_failure_that_may_have_been_billed_stays_charged(env):
    clip_gen.set_provider(clip_gen.Mock(error=clip_gen.GenError("provider", "HTTP 500")))
    assert ask(env).wait() is None and spent(env.store) == pytest.approx(0.581)


def test_a_slow_generation_is_abandoned_and_the_beat_goes_on(env, monkeypatch):
    cc.set_config({**ON, "gen_timeout_s": 10})
    monkeypatch.setattr(od, "WAIT_AFTER_S", -9.7)             # the beat waits 0.3 s in this test
    clip_gen.set_provider(clip_gen.Mock(MP4, delay=1.0))
    t = time.time()
    job = ask(env)
    assert job.wait() is None and time.time() - t < 1.0       # the caller got its answer; the stock clip or photo is used
    assert spent(env.store) == pytest.approx(0.581) and outcomes(env.store)["timeout"] == 1   # assumed billed
    job.thread.join(5)


def test_a_crash_inside_the_generation_never_reaches_the_video(env, monkeypatch):
    monkeypatch.setattr(lib, "add_clip", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("s3 down")))
    assert ask(env).wait() is None and ledger(env.store)[0]["outcome"] == "provider_failed" and env.store.query(cs.LOCK) == []
    monkeypatch.setattr(od, "entitlement", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ask(env, beat="b2") is None


def test_a_scene_the_library_already_has_is_used_and_nothing_is_generated(env):
    first = ask(env).wait()
    env.rows["v2"] = dict(env.rows["v1"])
    job = ask(env, video="v2", query="market fruit stall", alt="hands picking fruit")
    assert job.outcome == "library_hit" and job.wait() == first and not job.generated and len(env.prov.calls) == 1 and spent(env.store) == pytest.approx(0.581)


def test_a_retried_beat_never_pays_twice(env):
    first = ask(env).wait()
    again = ask(env)                                           # Step Functions ran the same beat again
    assert again.wait() == first and len(env.prov.calls) == 1 and spent(env.store) == pytest.approx(0.581)
    env.models.gate = {**GOOD_GATE, "text": True}
    env.models.brief = {**GOOD_BRIEF, "brief": "slow river flowing through a quiet green valley at dawn", "tags": ["river"]}
    assert ask(env, beat="b2", query="river valley").wait() is None
    assert ask(env, beat="b2", query="river valley") is None and len(env.prov.calls) == 2   # the failed attempt is not repeated either


def test_two_beats_never_buy_the_same_scene_at_once(env):
    clip_gen.set_provider(clip_gen.Mock(MP4, delay=0.3))
    a = ask(env, beat="b1")
    b = ask(env, beat="b2")
    assert a is not None and b is None and outcomes(env.store)["in_flight"] == 1
    assert a.wait()


# ================================================================= caps and budgets
def _different_scene(env, i):
    words = ["river valley dawn mist", "desert dunes wind sand", "kitchen steam pot stove", "snow pine forest quiet", "harbour boats calm water", "wheat field summer breeze",
             "rain window drops glass", "candle flame dark room", "mountain lake reflection clouds", "city rooftops sunset birds"][i]
    env.models.brief = {**GOOD_BRIEF, "brief": f"{words} seen in a calm continuous shot", "tags": words.split()[:3], "people": "none"}
    return words


def test_at_most_two_generations_per_video(env):
    for i in range(3):
        q = _different_scene(env, i)
        job = ask(env, beat=f"b{i}", query=q)
        assert (job is not None) == (i < 2)
        if job:
            job.wait()
    assert len(env.prov.calls) == 2 and outcomes(env.store)["cap_video"] == 1 and env.store.get(cs.STATS, cs.day())["cap_video"] == 1
    assert spent(env.store) == pytest.approx(2 * 0.581)        # the refused one moved no counter


def test_clips_have_their_own_share_of_the_account_allowance(env):
    made = 0
    for i in range(5):
        env.rows[f"w{i}"] = dict(env.rows["v1"])
        job = ask(env, video=f"w{i}", query=_different_scene(env, i))
        if job:
            job.wait()
            made += 1
    assert made == 3 and outcomes(env.store)["cap_account_type"] == 2          # 3 x 0.581 = 1.743 <= 1.75: the rest of the 2.915 is kept for images and objects
    assert cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"]) == cs.usd(env.store.get(cs.ACCT + "u1", cs.month() + ":clip")["spent"]) == pytest.approx(1.743)


def test_the_account_allowance_stops_the_sixth_generation_of_the_month(env):
    cc.set_config({**ON, "clip_account_cap_usd": 3.0})                          # the type share out of the way: the TOTAL of the account is what stops it
    made = 0
    for i in range(7):
        env.rows[f"w{i}"] = dict(env.rows["v1"])
        job = ask(env, video=f"w{i}", query=_different_scene(env, i))
        if job:
            job.wait()
            made += 1
    assert made == 5 and len(env.prov.calls) == 5              # 5 x 0.581 = 2.905 <= 2.915 < 6 x 0.581
    assert outcomes(env.store)["cap_account"] == 2 and cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"]) == pytest.approx(2.905)
    # the invariant, with every credit of the month used at the high cost, at the lowest price
    assert 30.83 - 0.20 * 120 - 2.905 >= 1.0


def test_a_yearly_account_generates_nothing(env):
    env.rows["v1"]["plan_interval"] = "year"
    assert ask(env) is None and env.prov.calls == [] and outcomes(env.store) == {"cap_account": 1}


def test_the_allowance_tightens_when_rolled_over_credits_are_burnt(env):
    env.credits["u1"] = 140                                     # 20 above the month's grant: the allowance is 0.915, one clip
    assert ask(env, query=_different_scene(env, 0)).wait()
    env.rows["v2"] = dict(env.rows["v1"])
    assert ask(env, video="v2", query=_different_scene(env, 1)) is None
    env.credits["u1"] = 150
    env.rows["v3"] = dict(env.rows["v1"])
    assert ask(env, video="v3", query=_different_scene(env, 2)) is None and len(env.prov.calls) == 1 and outcomes(env.store)["cap_account"] == 2


def test_unreadable_credits_mean_no_generation(env):
    od.set_readers(credits=lambda u, n: (_ for _ in ()).throw(RuntimeError("table down")))
    assert ask(env) is None and env.prov.calls == [] and spent(env.store) == 0 and env.store.query(cs.LOCK) != []   # the lock simply expires; no money moved


def test_the_platform_daily_budget_is_a_hard_stop(env):
    cc.set_config({**ON, "platform_day_usd": 1.0, "tight_share": 1.0})
    for i in range(3):
        env.rows[f"w{i}"] = {**env.rows["v1"], "user_id": f"user{i}"}
        job = ask(env, video=f"w{i}", query=_different_scene(env, i))
        if job:
            job.wait()
    assert len(env.prov.calls) == 1 and spent(env.store) == pytest.approx(0.581)
    assert outcomes(env.store)["budget_day"] == 2 and env.store.get(cs.STATS, cs.day())["cap_platform_day"] == 2
    assert env.store.get(cs.ACCT + "user1", cs.month()) is None                # a refused reservation moved nothing, on any counter


def test_the_platform_monthly_budget_is_a_hard_stop(env):
    cc.set_config({**ON, "platform_month_usd": 0.5})
    assert ask(env) is None and outcomes(env.store) == {"budget_month": 1} and spent(env.store) == 0


def test_test_and_comped_accounts_use_their_own_budget_and_cap(env):
    env.rows["v1"] = {"user_id": "tester", "plan": "test"}
    env.rows["v2"] = {"user_id": "comped", "plan": "max", "plan_source": "admin", "plan_state": "active", "plan_interval": "year"}
    cc.set_config({**ON, "test_day_usd": 1.2, "platform_day_usd": 0, "tight_share": 1.0})          # the paying budget is closed: it must not matter
    assert ask(env, query=_different_scene(env, 0)).wait()
    assert ask(env, video="v2", query=_different_scene(env, 1)).wait()        # a comped yearly Max: the flat test cap, not the formula
    env.rows["v3"] = {"user_id": "tester2", "plan": "test"}
    assert ask(env, video="v3", query=_different_scene(env, 2)) is None       # 3 x 0.581 > 1.20
    assert spent(env.store, "test") == pytest.approx(1.162) and spent(env.store, "paid") == 0 and outcomes(env.store)["budget_day"] == 1
    assert {l["kind"] for l in ledger(env.store)} == {"test"}
    cc.set_config({**ON, "test_account_cap_usd": 0.5})
    env.rows["v4"] = {"user_id": "tester", "plan": "test"}
    assert ask(env, video="v4", query=_different_scene(env, 3)) is None


def test_when_half_the_day_is_spent_only_scenes_asked_twice_are_made(env):
    cc.set_config({**ON, "platform_day_usd": 1.0})
    assert ask(env, query=_different_scene(env, 0)).wait()                     # 0.581 of 1.00: the day is now tight
    env.rows["v2"] = {**env.rows["v1"], "user_id": "u2"}
    env.rows["v3"] = {**env.rows["v1"], "user_id": "u3"}
    q = _different_scene(env, 1)
    cc.set_config({**ON, "platform_day_usd": 1.2, "tight_share": 0.4})
    assert ask(env, video="v2", query=q) is None and outcomes(env.store)["low_demand"] == 1
    (row,) = [r for r in env.store.query(cs.DEMAND) if "desert" in r["brief"]]
    assert row["asks"] == 1 and row["videos"] == [lib.video_ref("v2")]
    job = ask(env, video="v3", query=q)                                         # a second video asks for the same scene: now it is made
    assert job is not None and job.wait()


def test_no_double_spend_when_many_beats_race_for_the_last_dollars(env, monkeypatch):
    """12 videos of 12 accounts ask at the same moment with a day budget for 2 generations: exactly 2 are made and paid."""
    cc.set_config({**ON, "platform_day_usd": 1.2, "tight_share": 1.0})
    names = "abcdefghijkl"
    for i in range(12):
        env.rows[f"r{i}"] = {**env.rows["v1"], "user_id": f"racer{i}"}

    class PerQuery(Models):   # every video asks for a different scene, so only the budget can stop them
        def __call__(self, system, user, **kw):
            if system == clip_brief.BRIEF_SYSTEM:
                word = re.search(r"zz(\w+)", user).group(1)
                return json.dumps({**GOOD_BRIEF, "brief": f"calm general scene of {word} drifting slowly in soft light", "people": "none"}), {"cost_usd": 0.0}
            return json.dumps(GOOD_GATE), {"cost_usd": 0.0}
    monkeypatch.setattr(llm, "complete", PerQuery())
    clip_gen.set_provider(Different(MP4, delay=0.05))
    jobs, gate = [None] * 12, threading.Barrier(12)

    def go(i):
        gate.wait()
        jobs[i] = ask(env, video=f"r{i}", query=f"scene zz{names[i] * 5}", alt="")
    ts = [threading.Thread(target=go, args=(i,)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    started = [j for j in jobs if j is not None]
    assert len(started) == 2
    assert all(j.wait() for j in started)
    assert spent(env.store) == pytest.approx(2 * 0.581) and len(ledger(env.store)) == 2 and len(env.store.query(cs.LIB)) == 2


# ================================================================= the store: the transaction on DynamoDB
def test_reserve_on_dynamodb_moves_all_counters_or_none(aws):
    store = cs.AwsStore("Usage", "bucket")
    a = [cs.line("clipgen:x", "d", 600, 1000, extra={"n": 1}), cs.line("clipgen:y", "m", 600, 5000, extra={"n": 1})]
    assert store.reserve(a) is None
    assert store.get("clipgen:x", "d") == {"pk": "clipgen:x", "sk": "d", "spent": 600, "n": 1}
    assert store.reserve(a) == 0                                # the first counter would pass its limit ...
    assert store.get("clipgen:y", "m")["spent"] == 600          # ... so the second did not move either
    b = [cs.line("clipgen:z", "d", 100, 1000), cs.line("clipgen:y", "m", 4500, 5000)]
    assert store.reserve(b) == 1 and store.get("clipgen:z", "d") is None
    assert store.reserve([cs.line("clipgen:z", "d", 2000, 1000)]) == 0
    store.release(a)
    assert store.get("clipgen:x", "d")["spent"] == 0 and store.get("clipgen:x", "d")["n"] == 0


def test_rows_on_dynamodb(aws):
    store = cs.AwsStore("Usage", "bucket")
    assert store.put(cs.LOCK, "k", {"expires": 100}, only_if_absent=True) and not store.put(cs.LOCK, "k", {"expires": 100}, only_if_absent=True)
    assert not store.put(cs.LOCK, "k", {"expires": 300}, only_if_absent=True, or_expired=50) and store.put(cs.LOCK, "k", {"expires": 300}, only_if_absent=True, or_expired=200)
    store.add(cs.LIB, "c1", {"uses": 1}, sets={"videos": ["a"]}, fields={"last_used": 5, "cost_usd": 0.581})
    store.add(cs.LIB, "c1", {"uses": 1}, sets={"videos": ["a", "b"]})
    assert store.get(cs.LIB, "c1") == {"pk": cs.LIB, "sk": "c1", "uses": 2, "videos": ["a", "b"], "last_used": 5, "cost_usd": 0.581}
    assert [r["sk"] for r in store.query(cs.LIB)] == ["c1"]
    store.delete(cs.LIB, "c1")
    assert store.query(cs.LIB) == []


def test_the_whole_flow_on_dynamodb_and_s3(aws, env):
    boto3.client("s3", region_name="us-west-2").create_bucket(Bucket="bucket", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    store = cs.AwsStore("Usage", "bucket")
    cs.set_store(store)
    cid = ask(env).wait()
    assert cid and store.has_object(f"v/{cid}.mp4") and not store.has_object("v/" + "0" * 64 + ".mp4") and store.list_objects("m/") == [f"m/{cid}.json"]
    assert boto3.client("s3", region_name="us-west-2").list_objects_v2(Bucket="bucket", Prefix="cliplib/v/")["KeyCount"] == 1
    assert spent(store) == pytest.approx(0.581) and [r["sk"] for r in lib.rows(store, fresh=True)] == [cid]
    with pytest.raises(ValueError):
        store.put_object("../x", b"", "x")


def test_account_rows_go_with_the_account():
    assert "clipgen:acct:" in deletion.USAGE_PREFIXES and cs.ACCT == "clipgen:acct:"


# ================================================================= the library: search, shapes, scope, promotion
def _add(store, brief, *, aspect="16:9", safe=True, seconds=8.0, n=1, **meta):
    return lib.add_clip(store, mp4=MP4 + bytes([n]) + brief.encode(), poster=_jpeg(), tvec=_vec(brief), ivec=_vec("picture"),
                        meta={"brief": brief, "aspect": aspect, "center_safe": safe, "seconds": seconds, "width": 1280, "height": 720, "cost_usd": 0.581, **meta})


def test_search_finds_clips_by_meaning_and_respects_the_floor(env):
    a = _add(env.store, "misty pine forest at dawn with slow drifting fog")
    b = _add(env.store, "waves rolling onto a rocky shore under grey clouds")
    got = lib.search("pine forest fog", "landscape")
    assert [r["sk"] for _, r in got] == [a] and got[0][0] > 0.5
    assert [r["sk"] for _, r in lib.search("rocky shore waves", "landscape")] == [b]
    assert lib.search("volcano lava eruption", "landscape") == [] and lib.search("", "landscape") == []
    assert lib.search("pine forest fog", "landscape", min_seconds=9.0) == []      # footage too short for the scene is never offered


def test_shapes_a_landscape_clip_serves_vertical_and_square_only_when_the_centre_holds_the_subject(env):
    wide_safe = _add(env.store, "pine forest fog dawn", safe=True)
    wide_unsafe = _add(env.store, "pine forest fog dawn", safe=False, n=2)
    tall = _add(env.store, "pine forest fog dawn", aspect="9:16", n=3)
    ids = lambda o: [r["sk"] for _, r in lib.search("pine forest fog", o, k=5)]
    assert set(ids("landscape")) == {wide_safe, wide_unsafe}                       # a vertical clip is never cropped to landscape
    assert ids("portrait")[0] == tall and set(ids("portrait")) == {tall, wide_safe}  # the true shape first; the unsafe wide one is not offered
    assert set(ids("square")) == {wide_safe, tall}


def test_exclusive_media_can_never_enter_the_shared_library_or_its_search(env):
    with pytest.raises(ValueError):
        _add(env.store, "pine forest fog", scope="exclusive", owner="u9")
    cid = _add(env.store, "pine forest fog dawn")
    env.store.add(cs.LIB, cid, fields={"scope": "exclusive", "owner": "u9"})       # a future exclusive row, however it got there
    assert lib.rows(env.store, fresh=True) == [] and lib.search("pine forest fog", "landscape") == []


def test_retire_reindex_and_use_counts(env):
    cid = _add(env.store, "pine forest fog dawn")
    lib.record_use(cid, "videoA"); lib.record_use(cid, "videoA"); lib.record_use(cid, "videoB")
    row = env.store.get(cs.LIB, cid)
    assert row["uses"] == 3 and len(row["videos"]) == 2 and "videoA" not in row["videos"]
    lib.set_status(env.store, cid, "retired")
    assert lib.search("pine forest fog", "landscape") == []
    lib.set_status(env.store, cid, "active")
    env.store.delete(cs.LIB, cid)                                                 # the table was lost
    assert lib.reindex(env.store) == 1 and lib.reindex(env.store) == 0 and [r["sk"] for _, r in lib.search("pine forest fog", "landscape")] == [cid]


def test_promotion_copies_without_generating_or_embedding_again(env, tmp_path):
    a = _add(env.store, "pine forest fog dawn")
    b = _add(env.store, "waves rocky shore", n=2)
    lib.set_status(env.store, b, "retired")
    lib.record_use(a, "videoA")
    prod = cs.LocalStore(str(tmp_path / "prod"))
    boom = lambda *x: (_ for _ in ()).throw(AssertionError("promotion must not embed"))
    lib.set_embedder(query=boom, doc=boom, image=boom)
    clip_gen.set_provider(clip_gen.Mock(error=AssertionError("promotion must not generate")))
    plan = lib.promote(env.store, prod)
    assert {p["id"]: p["action"] for p in plan} == {a: "would copy", b: "skipped: retired"} and prod.list_objects("m/") == []     # dry run by default
    done = lib.promote(env.store, prod, dry_run=False)
    assert [p["action"] for p in done if p["id"] == a] == ["copied"]
    assert prod.get_object(f"v/{a}.mp4") == env.store.get_object(f"v/{a}.mp4") and prod.has_object(f"p/{a}.jpg")
    doc = json.loads(prod.get_object(f"m/{a}.json"))
    assert doc["cost_usd"] == 0.581 and doc["promoted_from"] and doc["tvec"] == json.loads(env.store.get_object(f"m/{a}.json"))["tvec"]
    assert prod.get(cs.LIB, a)["uses"] == 0                                        # use counts are the target's own history
    assert [p["action"] for p in lib.promote(env.store, prod, dry_run=False) if p["id"] == a] == ["already there"]
    lib.set_embedder(query=_vec)
    assert [r["sk"] for _, r in lib.search("pine forest fog", "landscape", store=prod)] == [a]


# ================================================================= the provider client
class _Res:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_gemini_client_asks_for_720p_and_never_puts_the_key_in_a_url(monkeypatch):
    seen = []

    def opener(req, timeout=0):
        seen.append((req.get_method(), req.full_url, dict(req.header_items()), json.loads(req.data) if req.data else None))
        if req.full_url.endswith("/interactions"):
            return _Res({"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "mime_type": "video/mp4", "uri": clip_gen.API + "/files/abc123:download?alt=media"}]}]})
        if req.full_url.endswith("/files/abc123"):
            return _Res({"state": "ACTIVE"})
        return _Res(MP4)
    out = clip_gen.GeminiOmni("gemini-omni-1.2-flash", key="SECRET", opener=opener).generate("a calm scene", seconds=8, aspect="9:16", timeout=30)
    assert out["mp4"] == MP4 and out["seconds"] == 8.0
    method, url, headers, body = seen[0]
    assert method == "POST" and body["model"] == "gemini-omni-1.2-flash" and body["input"] == "a calm scene"
    assert body["response_format"] == {"type": "video", "aspect_ratio": "9:16", "duration": "8s", "resolution": "720p", "delivery": "uri"}
    assert all("SECRET" not in u for _, u, _, _ in seen) and all(h.get("X-goog-api-key") == "SECRET" for _, _, h, _ in seen)


def test_the_key_is_read_at_every_call_so_a_rotation_needs_no_deploy(monkeypatch):
    used = []
    monkeypatch.setattr(clip_gen.GeminiOmni, "_call", lambda self, method, url, body, timeout, key, raw=False: (used.append(key), {"status": "completed", "steps": [
        {"type": "model_output", "content": [{"type": "video", "data": __import__("base64").b64encode(MP4).decode()}]}]})[1])
    monkeypatch.setenv("GEMINI_API_KEY", "old")
    p = clip_gen.GeminiOmni()
    p.generate("x")
    monkeypatch.setenv("GEMINI_API_KEY", "new")
    p.generate("x")
    assert used == ["old", "new"]


def test_provider_errors_say_whether_they_could_have_been_billed(monkeypatch):
    import urllib.error

    def http(code, text):
        def opener(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(text.encode()))
        return opener
    for code, text, kind, billed in ((403, "API key invalid", "auth", False), (429, "quota", "quota", False), (400, "blocked by safety policy", "blocked", False),
                                     (400, "bad duration", "bad_request", False), (500, "oops", "provider", True)):
        with pytest.raises(clip_gen.GenError) as e:
            clip_gen.GeminiOmni(key="SECRET", opener=http(code, text)).generate("x")
        assert (e.value.kind, e.value.billed) == (kind, billed) and "SECRET" not in str(e.value)
    with pytest.raises(clip_gen.GenError) as e:
        clip_gen.GeminiOmni(key="SECRET", opener=lambda req, timeout=0: (_ for _ in ()).throw(TimeoutError("timed out"))).generate("x")
    assert e.value.kind == "timeout" and e.value.billed
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(clip_gen, "_key", lambda: "")
    with pytest.raises(clip_gen.GenError) as e:
        clip_gen.GeminiOmni().generate("x")
    assert e.value.kind == "auth" and not e.value.billed
    with pytest.raises(clip_gen.GenError) as e:
        clip_gen.GeminiOmni(key="k", opener=lambda req, timeout=0: _Res({"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "data": "AAAA"}]}]})).generate("x")
    assert e.value.kind == "no_video"


# ================================================================= the beat step (real ffmpeg for the trim and crop)
@pytest.fixture(scope="module")
def real_clip(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("clip") / "c.mp4")
    subprocess.run([media.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=8", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                    "-pix_fmt", "yuv420p", out], check=True, timeout=120)
    return open(out, "rb").read()


def _size(mp4):
    import os, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x.mp4")
        open(path, "wb").write(mp4)
        return clips.probe_size(path)


@pytest.fixture
def beat_env(env, real_clip, monkeypatch):
    from engine import awsio, costs
    from engine.handlers import beat_handler
    env.put, env.cost = {}, []
    monkeypatch.setattr(awsio, "put_bytes", lambda key, data, ct="", bkt=None, working=False: env.put.__setitem__(key, data))
    monkeypatch.setattr(costs, "add_cost", lambda vid, usd, field="cost_usd", part=None, **k: env.cost.append((field, round(usd, 4))))
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "")
    monkeypatch.setenv("CLIP_VERIFY", "0")
    env.stock_calls = []
    stock_result = {"mp4": b"STOCK", "entry": {"source": "pixabay", "id": "9"}, "credit": "Video: Ana / Pixabay", "chosen": "pixabay:9", "review": {"cost_usd": 0.002}}
    monkeypatch.setattr(clips, "scout_with_retry", lambda q, n, a, **kw: (env.stock_calls.append(kw), dict(stock_result, review=dict(stock_result["review"])))[1])
    clip_gen.set_provider(clip_gen.Mock(real_clip))
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info())
    env.make = lambda **kw: beat_handler.make_clip(kw.get("plan", {"beats": []}), {"id": kw.get("beat", "b1"), "narration": "Fresh fruit changes hands every morning.",
                                                   "scene": {"type": "clip", "props": {"clip_query": kw.get("query", "fruit market"), "alt": "people buying fruit outdoors"}}},
                                                   kw.get("video", "v1"), kw.get("cost_field", "cost_usd"), 4.0, time.time())
    return env


def test_the_beat_shows_our_generated_clip_read_back_from_the_library(beat_env):
    out = beat_env.make()
    (cid,) = [r["sk"] for r in beat_env.store.query(cs.LIB)]
    assert out["chosen"] == f"videomk-library:{cid}" and out["credit"] == "Video: VideoMK library"
    assert out["ledger"]["source"] == "videomk-library" and out["ledger"]["license"] == "VideoMK library" and out["ledger"]["attribution"] == ""
    mp4 = beat_env.put[out["clip_asset"]]
    assert mp4 != beat_env.store.get_object(f"v/{cid}.mp4") and _size(mp4) == (1280, 720)     # the trimmed, normalised copy, not the library file
    row = beat_env.store.get(cs.LIB, cid)
    assert row["uses"] == 1 and row["videos"] == [lib.video_ref("v1")] and beat_env.store.get(cs.STATS, cs.day())["used_generated"] == 1
    assert len(beat_env.stock_calls) == 1 and "own_library" not in beat_env.stock_calls[0]      # the stock search ran meanwhile as the fallback, exactly as before
    assert beat_env.cost == [("cost_usd", 0.002)]                                                # the generation is NOT a cost of the customer's video


def test_the_next_video_of_any_plan_reuses_it_without_a_generation_or_a_stock_search(beat_env):
    beat_env.make()
    beat_env.rows["v2"] = {"user_id": "someone", "plan": "free"}
    out = beat_env.make(video="v2", query="market fruit stall")
    assert out["chosen"].startswith("videomk-library:") and len(beat_env.prov.calls) == 0 and len(clip_gen._override.calls) == 1 and len(beat_env.stock_calls) == 1
    row = beat_env.store.query(cs.LIB)[0]
    assert row["uses"] == 2 and len(row["videos"]) == 2 and beat_env.store.get(cs.STATS, cs.day())["used_library"] == 1


@pytest.mark.parametrize("how", ["rejected", "slow", "failed", "not_fitting"])
def test_fallback_the_stock_clip_is_used_when_ours_does_not_come(beat_env, how, monkeypatch, real_clip):
    if how == "rejected":
        beat_env.models.gate = {**GOOD_GATE, "artefacts": True}
    elif how == "slow":
        monkeypatch.setattr(od, "WAIT_AFTER_S", -149.8)
        clip_gen.set_provider(clip_gen.Mock(real_clip, delay=1.0))
    elif how == "failed":
        clip_gen.set_provider(clip_gen.Mock(error=clip_gen.GenError("provider", "HTTP 500")))
    else:   # our clip is fine and stays in the library, but the normal check says it does not fit THIS narration
        monkeypatch.setenv("CLIP_VERIFY", "1")   # the stub model gives the narration check no readable verdict, and that check fails closed
    out = beat_env.make()
    assert out["chosen"] == "pixabay:9" and out["credit"] == "Video: Ana / Pixabay" and beat_env.put[out["clip_asset"]] == b"STOCK"
    assert len(beat_env.store.query(cs.LIB)) == (1 if how == "not_fitting" else 0)


def test_with_the_flag_off_the_beat_step_calls_exactly_what_it_called_before(beat_env, monkeypatch):
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    monkeypatch.setattr(od, "context", lambda v: (_ for _ in ()).throw(AssertionError("must not be read")))
    monkeypatch.setattr(clips, "scout_own", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    out = beat_env.make()
    assert out["chosen"] == "pixabay:9" and set(beat_env.stock_calls[0]) == {"need_seconds", "pexels_key", "pixabay_key"} and beat_env.store.query(cs.STATS) == []


def test_a_4k_video_keeps_our_clip_at_720_and_a_vertical_video_asks_for_a_vertical_clip(beat_env, monkeypatch):
    from engine import format_options as fo
    out = beat_env.make(plan={"beats": [], "frame": fo.frame_dict("16:9", "2160p")})
    assert _size(beat_env.put[out["clip_asset"]]) == (1280, 720)       # 4K video: our 720p clip stays 720p (the renderer frames it), never enlarged
    assert clip_gen._override.calls[0]["aspect"] == "16:9"
    beat_env.rows["v2"] = dict(beat_env.rows["v1"])
    beat_env.models.brief = {**GOOD_BRIEF, "brief": "slow river flowing through a quiet green valley at dawn", "people": "none"}
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info(w=720, h=1280))
    beat_env.make(video="v2", query="river valley", plan={"beats": [], "frame": fo.frame_dict("9:16", "1080p")})
    assert clip_gen._override.calls[1]["aspect"] == "9:16"


def test_the_plan_record_carries_what_the_budget_choice_needs():
    import plan_gate

    class G:
        plan, free_credits, rights = "max", 0, {"priority_queue": True}
        ent = {"unlimited": False, "interval": "year", "source": "apple", "state": "active"}
    rec = plan_gate.record(G(), 3)
    assert rec["plan"] == "max" and rec["plan_interval"] == "year" and rec["plan_source"] == "apple" and rec["plan_state"] == "active"
    G.ent = {"unlimited": True, "interval": None, "source": None, "state": "active"}
    assert "plan_source" not in plan_gate.record(G(), 3) and plan_gate.record(G(), 3)["plan"] == "test"


# ================================================================= the report
def test_the_report_shows_spend_rejections_cap_hits_and_which_clips_are_misses(env):
    import importlib.util
    import os
    spec = importlib.util.spec_from_file_location("clips_admin", os.path.join(os.path.dirname(__file__), "..", "scripts", "clips_admin.py"))
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    clip_gen.set_provider(Different(MP4))
    a = ask(env, query=_different_scene(env, 0)).wait()
    b = ask(env, beat="b2", query=_different_scene(env, 1)).wait()
    assert ask(env, beat="b3", query=_different_scene(env, 2)) is None                 # the video's cap
    env.models.gate = {**GOOD_GATE, "text": True}
    env.rows["v2"] = {**env.rows["v1"], "user_id": "u2"}
    assert ask(env, video="v2", query=_different_scene(env, 3)).wait() is None           # rejected by the gate
    for v in ("x1", "x2", "x3"):
        od.used(v, f"videomk-library:{a}")
    od.used("x1", f"videomk-library:{b}", generated_id=b)
    rep = admin.report(env.store, 30)
    assert rep["generations"] == 3 and rep["kept"] == 2 and rep["rejected"] == 1 and rep["rejection_rate"] == pytest.approx(0.333, abs=0.001)
    assert rep["spend_usd"] == pytest.approx(3 * 0.581) and rep["cost_per_kept_clip_usd"] == pytest.approx(0.8715, abs=0.001) and rep["not_kept_by_reason"] == {"gate_rejected:text": 1}
    assert rep["cap_hits"] == {"video": 1} and rep["budget_stops"] == 0 and rep["decisions"]["generated"] == 2 and rep["used"] == {"library": 3, "generated": 1}
    assert rep["spend_by_day"]["paid"] == {cs.day(): pytest.approx(1.743)} and len(rep["spend_by_account"]) == 2 and "u1" not in json.dumps(rep)
    assert rep["library"]["clips"] == 2 and rep["reuse"]["miss_rate"] is None            # nothing is 30 days old yet
    later = admin.report(env.store, 30, now=time.time() + 31 * 86400)
    assert later["reuse"]["older_than_30_days"] == 2 and later["reuse"]["misses"] == 1 and later["reuse"]["miss_rate"] == 0.5
    assert later["reuse"]["miss_list"][0]["id"] == b[:12] and later["top_clips"][0]["id"] == a[:12] and later["top_clips"][0]["videos"] == 3
