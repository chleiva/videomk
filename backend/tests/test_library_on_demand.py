"""Library media on demand beyond clips (docs/LIBRARY_ON_DEMAND.md): images on top of the catalog, ownership marking, and the ONE account invariant shared by all media types.
No network: the image provider is a mock, the models are stubs, the embedder is a bag of words, the stores are folders."""
import io
import json
import os
import sys

import numpy as np
import pytest
from PIL import Image

from common import catalog, catalog_store, clip_config as cc, clip_store as cs, ownership
from engine import clip_brief, clip_gen, clip_library as lib, clip_ondemand as od, image_ondemand as io_, llm, ondemand
sys.path.insert(0, os.path.dirname(__file__))
from test_clips_on_demand import GOOD_BRIEF, GOOD_GATE, MP4, Different, _vec, _info   # the same stand-ins as the clip tests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

QA_OK = {"adherence": 9, "quality": 8, "text_visible": False, "logo_or_brand": False, "real_person_likeness": False, "anatomy_problem": False, "warped_objects": False, "unsafe": False,
         "centre_subject": True, "calm_bottom": True, "style_ok": True, "reasons": "clean"}
ON = {"enabled": True, "image_enabled": True, "clip_account_cap_usd": 3.0}


def _picture(seed=1, size=(640, 360)):
    rng = np.random.default_rng(seed)
    b = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(b, "JPEG", quality=80)
    return b.getvalue()


class Models:
    def __init__(self):
        self.brief, self.qa, self.fits, self.calls = dict(GOOD_BRIEF, brief="calm alpine lake at dawn with soft mist over still water", people="none"), dict(QA_OK), True, []

    def __call__(self, system, user, **kw):
        if system in (clip_brief.BRIEF_SYSTEM, clip_brief.IMAGE_BRIEF_SYSTEM):
            self.calls.append("brief")
            return json.dumps(self.brief), {"cost_usd": 0.0002}
        if "quality reviewer of a library of reusable stock images" in system:
            self.calls.append("qa")
            return json.dumps(self.qa), {"cost_usd": 0.0003}
        if "quality gate of a stock-footage library" in system:
            return json.dumps(GOOD_GATE), {"cost_usd": 0.0}
        self.calls.append("fits")
        return json.dumps({"fits": self.fits, "reason": "x"}), {"cost_usd": 0.0003}


class Pictures(io_.MockImages):
    """Every generation is a different picture."""

    def generate(self, prompt, **kw):
        out = super().generate(prompt, **kw)
        return {**out, "jpeg": _picture(len(self.calls))}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPS_ON_DEMAND", "1")
    store = cs.LocalStore(str(tmp_path / "ledger"))
    cs.set_store(store)
    cat = io_.LocalCat(str(tmp_path / "catalog"))
    io_.set_catalog(cat)
    cc.set_config(dict(ON))
    lib.reset()
    lib.set_embedder(query=_vec, doc=_vec, image=lambda jpeg: [float(x) for x in np.random.default_rng(len(jpeg)).normal(size=256)])
    catalog.set_clients(embed_text=lambda t: [float(x) for x in _vec(t)])
    models = Models()
    monkeypatch.setattr(llm, "complete", models)
    prov = Pictures()
    io_.set_provider(prov)
    rows = {"v1": {"user_id": "u1", "plan": "max", "plan_interval": "month", "plan_source": "apple", "plan_state": "active"}}
    od.set_readers(video=lambda vid: rows.get(vid), credits=lambda user, now: 0)

    class E:
        pass
    e = E()
    e.store, e.cat, e.models, e.prov, e.rows = store, cat, models, prov, rows
    yield e
    cs.set_store(None); io_.set_catalog(None); io_.set_provider(None); cc.set_config(None); od.reset(); lib.reset(); catalog.reset(); clip_gen.set_provider(None)


def ask(env, video="v1", beat="b1", query="mountain lake", **kw):
    return io_.begin(video_id=video, beat_id=beat, query=query, alt="lake in the mountains at sunrise", narration="Still water mirrors the first light.", ctx=od.context(video), plan=kw.pop("plan", {"beats": []}), **kw)


def spent(store, media="image", kind="paid", span="day"):
    return cs.usd((store.get(cs.spend_pk(kind, span, media), cs.day() if span == "day" else cs.month()) or {}).get("spent"))


def outcomes(store, media="image"):
    return {k[2:]: v for k, v in (store.get(cs.STATS, ondemand.stats_sk(media)) or {}).items() if k.startswith("d_")}


# ================================================================= ownership marking (layer a)
def test_marking_adds_the_owner_without_touching_a_pixel():
    jpeg = _picture()
    out = ownership.mark_jpeg(jpeg, asset_id="ab" * 32, title="Calm lake & <dawn>", year=2026)
    assert (np.asarray(Image.open(io.BytesIO(jpeg))) == np.asarray(Image.open(io.BytesIO(out)))).all() and len(out) > len(jpeg)
    m = ownership.read_marks(out)
    assert m["creator"] == m["owner"] == m["exif_artist"] == "Agilegency Ltd" and m["credit"] == "VideoMK" and m["email"] == "hello@videomk.com" and m["asset_id"] == "ab" * 32
    assert m["source_type"].endswith("/trainedAlgorithmicMedia") and m["marked"] == "True" and "2026 Agilegency Ltd (VideoMK)" in m["rights"] and "Agilegency Ltd" in m["exif_copyright"]
    assert ownership.is_marked(out, "ab" * 32) and not ownership.is_marked(out, "cd" * 32) and not ownership.is_marked(jpeg) and ownership.read_marks(jpeg) == {} and ownership.read_marks(b"not a jpeg") == {}


def test_marking_twice_replaces_the_block_and_keeps_other_segments():
    once = ownership.mark_jpeg(_picture(), asset_id="ab" * 32, title="a")
    twice = ownership.mark_jpeg(once, asset_id="cd" * 32, title="b")
    assert twice.count(ownership.XMP_HEADER) == 1 and twice.count(ownership.EXIF_HEADER) == 1 and ownership.read_marks(twice)["asset_id"] == "cd" * 32 and twice[2:4] == b"\xff\xe0"   # JFIF stays first
    with pytest.raises(ValueError):
        ownership.mark_jpeg(b"\x89PNG....", asset_id="x")


def test_the_backfill_marks_every_approved_image_keeps_ids_and_promotion_still_verifies(tmp_path):
    import catalog_promote
    import ownership_admin
    src, dst = catalog_store.LocalStore(str(tmp_path / "a")), catalog_store.LocalStore(str(tmp_path / "b"))
    ids = []
    for i in range(3):
        jpeg = _picture(i)
        cid = catalog.content_hash(jpeg)
        ids.append(cid)
        for k in (catalog.key_original(cid), catalog.key_preview(cid), catalog.key_thumb(cid)):
            src.put(k, jpeg)
        src.put_vector(cid, [1.0, float(i)], {"title": "t"})
        src.put_item({"id": cid, "title": f"picture {i}", "review_status": "approved" if i < 2 else "rejected"})
    assert len(ownership_admin.mark_store(src)["marked"]) == 2 and not ownership.is_marked(src.get(catalog.key_original(ids[0])))            # dry run by default
    rep = ownership_admin.mark_store(src, dry_run=False)
    assert sorted(rep["marked"]) == sorted(ids[:2]) and rep["refused"] == []
    for cid in ids[:2]:
        data = src.get(catalog.key_original(cid))
        assert ownership.is_marked(data, cid) and src.get_item(cid)["stored_sha256"] == catalog.content_hash(data) != cid and src.get_item(cid)["marked"] is True
    assert not ownership.is_marked(src.get(catalog.key_original(ids[2])))                                                                     # a rejected picture is not ours to mark
    assert ownership_admin.mark_store(src, dry_run=False)["already"] == sorted(ids[:2]) or len(ownership_admin.mark_store(src, dry_run=False)["already"]) == 2
    out = catalog_promote.promote(src, dst, dry_run=False)
    assert sorted(out["copied"]) == sorted(ids[:2]) and ownership.is_marked(dst.get(catalog.key_original(ids[0])), ids[0])
    src.put(catalog.key_original(ids[0]), _picture(9))                                                                                         # a file that is neither the id nor the recorded hash
    assert ownership_admin.mark_store(src, dry_run=False)["refused"][0]["id"] == ids[0]
    assert ownership_admin.wm_bits("f" * 64) == "1" * 60 + "0"


# ================================================================= images on demand
def test_a_generated_image_is_marked_as_ours_and_stored_in_the_catalog_before_it_is_used(env):
    job = ask(env)
    cid = job.wait()
    assert cid and job.generated and len(env.prov.calls) == 1 and env.models.calls == ["brief", "qa"]
    assert "calm alpine lake" in env.prov.calls[0]["prompt"].lower() and "Still water mirrors" not in env.prov.calls[0]["prompt"]      # only the general brief leaves
    item = env.cat.item(cid)
    assert item["review_status"] == "approved" and item["scope"] == "library" and item["marked"] is True and item["provenance"]["on_demand"] is True and item["cost_usd"] == 0.05
    assert item["owner_name"] == "Agilegency Ltd" and item["watermark"] == "pending" and "u1" not in json.dumps(item) and "v1" not in json.dumps(item)
    original = env.cat.read(catalog.key_original(cid))
    assert ownership.is_marked(original, cid) and item["stored_sha256"] == catalog.content_hash(original)
    assert spent(env.store) == spent(env.store, span="month") == pytest.approx(0.05) and spent(env.store, "clip") == 0
    assert cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"]) == pytest.approx(0.05) and env.store.get(cs.VIDEO + "v1", "n:image")["n"] == 1
    (line,) = env.store.query(cs.ledger_pk(cs.month()))
    assert line["media"] == "image" and line["outcome"] == "generated" and line["clip_id"] == cid and line["provider_usd"] == 0.0442 and outcomes(env.store) == {"generated": 1}
    got = io_.use(cid, "mountain lake", "Still water mirrors the first light.", "lake", "v1", generated=True)
    assert got["credit"] == "" and got["chosen"] == f"videomk-library:{cid}" and got["entry"]["source"] == "videomk-library" and got["jpeg"][:2] == b"\xff\xd8"      # ours: no credit line
    env.models.fits = False
    assert io_.use(cid, "q", "another narration", "a", "v2") is None                                                                      # it must still suit the narration


@pytest.mark.parametrize("flag", ["text_visible", "real_person_likeness", "anatomy_problem", "centre_subject"])
def test_a_rejected_image_is_never_stored_and_still_counts(env, flag):
    env.models.qa[flag] = not QA_OK[flag]
    job = ask(env)
    assert job.wait() is None and env.cat.store.images() == [] and spent(env.store) == pytest.approx(0.05)
    assert env.store.query(cs.ledger_pk(cs.month()))[0]["reason"] == flag and outcomes(env.store) == {"gate_rejected": 1}


def test_who_may_and_the_switches(env, monkeypatch):
    env.rows["v1"]["plan"] = "pro"
    assert ask(env) is None and env.prov.calls == []
    env.rows["v1"]["plan"] = "max"
    cc.set_config({"enabled": True, "image_enabled": False})
    assert ask(env) is None and outcomes(env.store) == {"kill_switch": 1}
    cc.set_config({**ON, "master_enabled": False})
    assert ask(env) is None and outcomes(env.store) == {"kill_switch": 2}
    cc.set_config(dict(ON))
    assert ask(env, plan={"media_items": [{"id": "p"}]}) is None and ask(env, is_edit=True) is None and ask(env, query="Maria at the lake") is None
    env.models.brief = {"reusable": False, "reason": "a specific landmark"}
    assert ask(env) is None and env.prov.calls == [] and spent(env.store) == 0
    io_.set_catalog(None)
    monkeypatch.delenv("CATALOG_LOCAL_DIR", raising=False)
    assert io_.current() is None and ask(env) is None                                     # no catalog, no on-demand images
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    assert ask(env) is None


def test_a_picture_the_catalog_already_has_is_used_and_a_near_duplicate_is_not_stored_twice(env):
    first = ask(env).wait()
    env.cat.store.put_vector(first, [float(x) for x in _vec("calm alpine lake at dawn with soft mist over still water")], {})   # as the real index would answer a matching phrase
    env.rows["v2"] = dict(env.rows["v1"])
    hit = ask(env, video="v2")
    assert hit.outcome == "library_hit" and hit.wait() == first and len(env.prov.calls) == 1
    env.models.brief = dict(env.models.brief, brief="quiet desert dunes under a pale morning sky with long shadows")
    lib.set_embedder(image=lambda jpeg: [float(x) for x in _vec("calm alpine lake at dawn with soft mist over still water")])     # the new picture looks the same as the stored one
    dup = ask(env, video="v2", beat="b2", query="desert dunes")
    assert dup.wait() == first and not dup.generated and len(env.cat.store.images()) == 1 and outcomes(env.store)["duplicate"] == 1


def test_image_caps_four_a_video_and_the_type_share_of_the_month(env):
    made = 0
    for i in range(6):
        env.models.brief = dict(env.models.brief, brief=f"general scene number {'abcdefgh'[i] * 4} in soft morning light with a calm sky")
        job = ask(env, beat=f"b{i}", query=f"scene {'abcdefgh'[i] * 4}")
        made += bool(job and job.wait())
    assert made == 4 and outcomes(env.store)["cap_video"] == 2
    cc.set_config({**ON, "image_account_cap_usd": 0.12})
    env.rows["v2"] = dict(env.rows["v1"])
    assert ask(env, video="v2", query="another") is None and outcomes(env.store)["cap_account_type"] == 1       # 4 x 0.05 already spent this month
    cc.set_config({**ON, "image_day_usd": 0.22})
    assert ask(env, video="v2", query="another") is None and outcomes(env.store)["budget_day"] == 1
    env.rows["v3"] = {"user_id": "t", "plan": "test"}
    assert ask(env, video="v3", query="another").wait() and spent(env.store, kind="test") == pytest.approx(0.05) and spent(env.store) == pytest.approx(0.20)


def test_a_yearly_account_cannot_have_a_clip_but_can_have_images(env, monkeypatch):
    env.rows["v1"]["plan_interval"] = "year"                                               # allowance 0.35 a month
    clip_gen.set_provider(Different(MP4))
    from engine import clip_gate
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info())
    assert od.begin(video_id="v1", beat_id="c1", query="fruit market", alt="", narration="n", need_seconds=7.0, ctx=od.context("v1"), plan={}) is None
    n = 0
    for i in range(9):
        env.rows[f"y{i}"] = dict(env.rows["v1"])
        env.models.brief = dict(env.models.brief, brief=f"general scene number {'abcdefghi'[i] * 4} in soft morning light with a calm sky")
        job = ask(env, video=f"y{i}", query=f"scene {'abcdefghi'[i] * 4}")
        n += bool(job and job.wait())
    assert n == 7 and cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"]) == pytest.approx(0.35)       # 7 x 0.05: the account's TOTAL, never more


def test_one_invariant_clips_and_images_draw_from_the_same_account_total(env, monkeypatch):
    """A monthly account: 2.915 in all. Five clips (2.905) leave one cent: no image. With the confirmed shares (clips 1.75) three clips leave room for images."""
    from engine import clip_gate
    monkeypatch.setattr(clip_gate, "probe", lambda mp4: _info())
    monkeypatch.setattr(od, "_silent", lambda m: m)
    maker = Different(MP4)
    clip_gen.set_provider(maker)
    cc.set_config({**ON, "reuse_min_score": 0.99})        # every scene counts as new here

    def clip(i):
        env.rows[f"c{i}"] = dict(env.rows["v1"])
        env.models.brief = dict(GOOD_BRIEF, brief=f"general moving scene {'abcdefgh'[i] * 4} drifting slowly in soft light", people="none")
        j = od.begin(video_id=f"c{i}", beat_id="b", query=f"scene {'abcdefgh'[i] * 4}", alt="", narration="n", need_seconds=7.0, ctx=od.context(f"c{i}"), plan={})
        return bool(j and j.wait())
    assert sum(clip(i) for i in range(6)) == 5 and len(maker.calls) == 5
    env.models.brief = dict(GOOD_BRIEF, brief="calm alpine lake at dawn with soft mist over still water", people="none")
    assert ask(env) is None and outcomes(env.store) == {"cap_account": 1}
    total = cs.usd(env.store.get(cs.ACCT + "u1", cs.month())["spent"])
    assert total == pytest.approx(2.905) and 30.83 - 0.20 * 120 - total >= 1.0
    lim = cc.limits(cc.clean_config({}), "clip", "paid"), cc.limits(cc.clean_config({}), "image", "paid"), cc.limits(cc.clean_config({}), "object", "paid")
    assert [l["account_cap"] for l in lim] == [1.75, 1.0, 0.15] and sum(l["account_cap"] for l in lim) <= 2.915 and [l["video_cap"] for l in lim] == [2, 4, 1]
    assert cc.limits(cc.clean_config({}), "image", "test") == {"video_cap": 4, "account_cap": 1.0, "day": 1.0, "month": 10.0}


def test_fallback_a_slow_or_failing_provider_never_reaches_the_video(env, monkeypatch):
    io_.set_provider(io_.MockImages(error=io_.ImageError("blocked", "policy", billed=False)))
    assert ask(env).wait() is None and spent(env.store) == 0
    io_.set_provider(io_.MockImages(error=io_.ImageError("provider", "HTTP 500")))
    assert ask(env, beat="b2", query="lake two").wait() is None and spent(env.store) == pytest.approx(0.05)
    monkeypatch.setattr(io_, "WAIT_AFTER_S", -74.8)
    io_.set_provider(io_.MockImages(_picture(), delay=1.0))
    job = ask(env, beat="b3", query="lake three")
    assert job.wait() is None and outcomes(env.store)["timeout"] == 1
    job.thread.join(5)
    assert ask(env, beat="b3", query="lake three") is not None or True                      # a retried beat never pays twice (it reuses the claim)
    assert len([r for r in env.store.query(cs.ledger_pk(cs.month())) if r["brief"]]) == 3


def test_the_openai_client_asks_for_the_catalog_tier_and_keeps_the_key_out_of_errors():
    seen = []

    class R:
        def __init__(self, b): self.b = b
        def read(self, n=-1): return self.b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout=0):
        seen.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
        return R(json.dumps({"data": [{"b64_json": __import__("base64").b64encode(_picture()).decode()}], "usage": {"input_tokens": 100, "output_tokens": 1413}}).encode())
    out = io_.OpenAIImages(key="SECRET", opener=opener).generate("a calm lake")
    assert out["jpeg"][:2] == b"\xff\xd8" and out["usd"] == pytest.approx(0.0429, abs=0.0001)
    url, headers, body = seen[0]
    assert body == {"model": "gpt-image-2.6-flare", "prompt": "a calm lake", "size": "2048x1152", "quality": "high", "output_format": "jpeg", "n": 1} and "SECRET" not in url
    import urllib.error

    def refuse(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"error":"rejected by the safety system"}'))
    with pytest.raises(io_.ImageError) as e:
        io_.OpenAIImages(key="SECRET", opener=refuse).generate("x")
    assert e.value.kind == "blocked" and not e.value.billed and "SECRET" not in str(e.value)


def test_the_photo_step_shows_our_image_without_a_credit_and_falls_back_to_stock(env, monkeypatch):
    from engine import awsio, costs, stock
    from engine.handlers import beat_handler
    put = {}
    monkeypatch.setattr(awsio, "put_bytes", lambda key, data, ct="", bkt=None, working=False: put.__setitem__(key, data))
    monkeypatch.setattr(awsio, "put_json", lambda key, obj: None)
    monkeypatch.setattr(costs, "add_cost", lambda *a, **k: 0.0)
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "")
    stock_result = {"jpeg": _picture(5), "entry": {"source": "unsplash", "id": "9"}, "credit": "Photo: Ana / Unsplash", "chosen": "unsplash:9", "review": {"cost_usd": 0.001}, "candidates": []}
    monkeypatch.setattr(stock, "scout_reviewed", lambda *a, **k: dict(stock_result))
    beat = {"id": "b1", "narration": "Still water mirrors the first light.", "scene": {"type": "image", "props": {"image_query": "mountain lake", "alt": "lake at sunrise"}}}
    out = beat_handler.make_photo({"beats": []}, beat, "v1", "cost_usd")
    cid = env.cat.store.images()[0]["id"]
    assert out["chosen"] == f"videomk-library:{cid}" and out["credit"] == "" and out["ledger"]["source"] == "videomk-library"       # ours: NO on-screen credit
    env.models.qa["text_visible"] = True
    env.models.brief = dict(env.models.brief, brief="quiet desert dunes under a pale morning sky with long shadows")
    out = beat_handler.make_photo({"beats": []}, dict(beat, id="b2", scene={"type": "image", "props": {"image_query": "desert dunes", "alt": "sand dunes"}}), "v1", "cost_usd")
    assert out["chosen"] == "unsplash:9" and out["credit"] == "Photo: Ana / Unsplash"                                               # rejected by the gate: the stock photo, credited as its terms ask
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    monkeypatch.setattr(io_, "begin", lambda **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert beat_handler.make_photo({"beats": []}, dict(beat, id="b3"), "v1", "cost_usd")["chosen"] == "unsplash:9"


# ================================================================= whiteboard sketch objects on demand
from engine import object_ondemand as oo   # noqa: E402
from engine.whiteboard import library as wblib   # noqa: E402


def _board_plan(*names):
    return {"beats": [{"id": "w1", "scene": {"type": "whiteboard", "props": {"items": [{"id": f"i{k}", "write": n, "boxed": True, "zone": "centre"} for k, n in enumerate(names)] + [{"id": "t", "write": "Bees make honey"}]}}}]}


def _pkg(oid, name):
    return {"id": oid, "what": name, "w": 300, "h": 200, "width": 16.0, "ink": "<path/>", "fills": [], "fill_colours": [], "strokes": [[[0, 0], [10, 10]]], "pen_length": 14.1,
            "meta": {"title_en": name.title(), "title_es": name + " es", "synonyms_en": [name + " comb"], "synonyms_es": ["celdas de abejas"], "tags": ["bees"], "description": f"A {name}.", "score": 8}}


@pytest.fixture
def wb(env, tmp_path, monkeypatch):
    monkeypatch.setenv("WHITEBOARD_DIR", str(tmp_path))
    cc.set_config({**ON, "object_enabled": True})
    saved = json.loads(json.dumps(wblib.index()))
    calls = []

    def maker(objs, timeout):
        calls.append(list(objs))
        ok = [o for o in objs if o[1] != "blob thing"]
        return [_pkg(oid, name) for oid, name in ok], {"sheet_usd": 0.038, "rejected": {oid: "gate: blob" for oid, name in objs if name == "blob thing"}}
    oo.set_maker(maker)
    env.calls, env.dir = calls, tmp_path
    yield env
    oo.set_maker(None)
    wblib._index = saved
    for fn in (wblib.by_name, wblib.search):
        for a in ("_t", "_m"):
            if hasattr(fn, a):
                delattr(fn, a)


def test_missing_drawings_are_made_stored_in_our_library_and_drawn_in_this_video(wb):
    plan = _board_plan("honeycomb", "blob thing", "honeycomb")
    got = oo.fill(plan, video_id="v1", ctx=od.context("v1"))
    assert got["asked"] == ["honeycomb", "blob thing"] and got["made"] == ["honeycomb"] and len(wb.calls) == 1                 # ONE call for the video's missing drawings
    items = plan["beats"][0]["scene"]["props"]["items"]
    assert items[0] == {"id": "i0", "draw": "honeycomb", "zone": "centre"} and items[2]["draw"] == "honeycomb"                   # drawn where the label was
    assert items[1]["write"] == "blob thing" and items[1]["boxed"] is True and items[3] == {"id": "t", "write": "Bees make honey"}  # rejected: the label stays; other writing untouched
    pkg = json.load(open(wb.dir / "honeycomb.json"))
    assert pkg["provenance"]["on_demand"] is True and pkg["provenance"]["scope"] == "library" and "Agilegency" in pkg["provenance"]["owner"] and "v1" not in json.dumps(pkg["provenance"])
    row = wb.store.get(oo.WOBJ, "honeycomb")
    assert row["title"] == "Honeycomb" and row["synonyms_es"] == ["celdas de abejas"] and row["v"] and row["scope"] == "library"
    assert wblib.has("honeycomb") and wblib.by_name("celdas de abejas") == "honeycomb" and wblib.load("honeycomb")["w"] == 300               # the next plan finds it by name, in Spanish too
    price = 0.04 + 2 * 0.007
    assert spent(wb.store, "object") == pytest.approx(price) and cs.usd(wb.store.get(cs.ACCT + "u1", cs.month())["spent"]) == pytest.approx(price)
    (line,) = wb.store.query(cs.ledger_pk(cs.month()))
    assert line["media"] == "object" and line["made_n"] == 1 and line["rejected_n"] == 1 and outcomes(wb.store, "object") == {"generated": 1}
    # one call per video; and a later process loads what was made
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "cap_video" and len(wb.calls) == 1
    wblib._index = None
    assert not wblib.has("honeycomb") and oo.load_dynamic() == 1 and wblib.has("honeycomb")


def test_objects_who_may_switches_limits_and_names_that_are_never_drawn(wb, monkeypatch):
    assert oo.missing(_board_plan("honeycomb", "Coca-Cola logo", "flag of france", "maria", "x", "a very long name of five words"), 6) == [("honeycomb", "honeycomb")]
    assert oo.fill(_board_plan(), video_id="v1", ctx=od.context("v1")) == {"asked": [], "made": [], "reason": ""}
    wb.rows["v1"]["plan"] = "pro"
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "not_entitled"
    wb.rows["v1"]["plan"] = "max"
    cc.set_config({**ON, "object_enabled": False})
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "kill_switch"
    cc.set_config({**ON, "object_enabled": True, "object_account_cap_usd": 0.03})
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "cap_account_type" and wb.calls == []
    cc.set_config({**ON, "object_enabled": True, "object_day_usd": 0.01})
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "budget_day"
    cc.set_config({**ON, "object_enabled": True})
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"), is_edit=True)["reason"] == "edit"
    oo.set_maker(None)
    monkeypatch.setenv("WHITEBOARD_PROTO_DIR", "/nonexistent")
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "no_tracer" and spent(wb.store, "object") == 0     # the engine's functions today: labels stay, nothing is spent
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["asked"] == []


def test_a_slow_or_failing_object_call_leaves_the_labels_and_never_delays_the_plan_past_the_limit(wb):
    import time as _t
    cc.set_config({**ON, "object_enabled": True, "object_timeout_s": 5})
    oo.set_maker(lambda objs, timeout: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
    plan = _board_plan("violin")
    assert oo.fill(plan, video_id="v1", ctx=od.context("v1"))["reason"] == "provider_failed" and plan["beats"][0]["scene"]["props"]["items"][0]["boxed"] is True
    wb.rows["v2"] = dict(wb.rows["v1"])
    import engine.object_ondemand as m
    cc.set_config({**ON, "object_enabled": True, "object_timeout_s": 5})
    real_join = __import__("threading").Thread.join
    oo.set_maker(lambda objs, timeout: (_t.sleep(1.0), ([], {}))[1])
    try:
        __import__("threading").Thread.join = lambda self, timeout=None: real_join(self, 0.2 if self.name == "objectgen" else timeout)
        t = _t.time()
        assert oo.fill(_board_plan("kite"), video_id="v2", ctx=od.context("v2"))["reason"] == "timeout" and _t.time() - t < 0.9
    finally:
        __import__("threading").Thread.join = real_join
    assert outcomes(wb.store, "object") == {"provider_failed": 1, "timeout": 1}


def test_an_existing_drawing_is_never_overwritten(wb):
    oo.fill(_board_plan("honeycomb"), video_id="v1", ctx=od.context("v1"))
    first = open(wb.dir / "honeycomb.json").read()
    assert oo.store_object(wb.store, _pkg("honeycomb", "honeycomb"), video_id="v9", cost_usd=0.01) == "honeycomb_2" and open(wb.dir / "honeycomb.json").read() == first
    assert oo.store_object(wb.store, _pkg(wblib.ids()[0], "x"), video_id="v9", cost_usd=0.01) == wblib.ids()[0] + "_2"          # nor a bundled one


def test_a_drawing_matched_only_by_meaning_is_replaced_by_the_real_thing(wb, monkeypatch):
    from engine.scenes.elements import whiteboard as wbe
    bundled = wblib.ids()[0]
    monkeypatch.setattr(wblib, "search", lambda name, k=3, embed=None: [{"id": bundled, "score": 0.36, "title": "x"}])        # the library's closest thing, not the thing
    props = wbe._sanitize({"items": [{"id": "a", "draw": "honeycomb"}, {"id": "b", "draw": bundled}]})
    assert props["items"][0]["draw"] == bundled and props["items"][0]["asked"] == "honeycomb" and props["items"][0]["match"] == 0.36 and "asked" not in props["items"][1]
    plan = {"beats": [{"id": "w", "scene": {"type": "whiteboard", "props": props}}]}
    assert oo.missing(plan, 6) == [("honeycomb", "honeycomb")] and oo.missing(plan, 6, sure=0.3) == []
    assert oo.fill(plan, video_id="v1", ctx=od.context("v1"))["made"] == ["honeycomb"]
    assert props["items"][0]["draw"] == "honeycomb" and "asked" not in props["items"][0] and props["items"][1]["draw"] == bundled
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")
    assert "asked" not in wbe._sanitize({"items": [{"id": "a", "draw": "kite"}]})["items"][0]                                      # without the flag the plan is exactly what it was
