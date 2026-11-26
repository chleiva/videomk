"""The image catalog (docs/IMAGE_CATALOG.md): the privacy filter of the demand log, search, the director's use of it, the generator's cost cap and checks, promotion without paying twice,
the plan, and the CDK template (flag off = nothing, flag on = private resources and narrow rights). No network: Bedrock, S3, S3 Vectors and DynamoDB are fakes."""
import base64
import io
import json
import os
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambdas"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from common import catalog, catalog_privacy as priv, catalog_store, catalog_style  # noqa: E402
from engine import catalog_pick  # noqa: E402
import catalog_generate as gen  # noqa: E402
import catalog_promote as promo  # noqa: E402
import catalog_plan as plan_mod  # noqa: E402


def jpeg(color=(120, 140, 160), size=(640, 360)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", quality=90)
    return out.getvalue()


# ----------------------------------------------------------------------------- the privacy filter
@pytest.mark.parametrize("phrase", [
    "Carlos at the beach", "my wife in the kitchen", "mi hijo jugando", "our house in the garden", "call 555 123 4567", "maria@example.com", "12 Baker Street London", "calle Mayor 5",
    "https://example.com/page", "photo of Mr Smith", "my son's birthday", "granny's flat", "named Peter", "my boss at work", "Emma and Noah at school", "one two three four five six seven eight nine ten eleven",
    "1920s office", "", "   ",
])
def test_personal_or_unusable_phrases_are_never_kept(phrase):
    assert priv.generic_phrase(phrase) is None, phrase


@pytest.mark.parametrize("phrase", ["sunrise over mountains", "person working at a laptop in a bright office", "hands typing on a keyboard", "Eiffel Tower Paris", "flat lay desk", "late afternoon light", "forest path autumn leaves"])
def test_generic_phrases_are_kept_lowercased(phrase):
    assert priv.generic_phrase(phrase) == phrase.lower()


def test_the_video_reference_is_salted_stable_and_needs_the_salt():
    a = priv.video_ref("video-1", "salt-A")
    assert a == priv.video_ref("video-1", "salt-A") and len(a) == 16
    assert a != priv.video_ref("video-1", "salt-B") and a != priv.video_ref("video-2", "salt-A")
    assert "video-1" not in a
    with pytest.raises(ValueError):
        priv.video_ref("video-1", "")


class FakeDemandTable:
    def __init__(self):
        self.calls = []

    def update_item(self, **kw):
        self.calls.append(kw)


class FakeDdb:
    def __init__(self):
        self.t = FakeDemandTable()

    def Table(self, name):   # noqa: N802
        return self.t


@pytest.fixture
def cat_env(monkeypatch):
    catalog.reset()
    for k, v in {"CATALOG_BUCKET": "b", "CATALOG_TABLE": "t", "CATALOG_VECTOR_BUCKET": "vb", "CATALOG_DEMAND_TABLE": "demand"}.items():
        monkeypatch.setenv(k, v)
    catalog._cache["salt"] = "pepper"
    yield
    catalog.reset()


def test_the_demand_log_writes_a_counter_with_a_hashed_video_and_a_ttl_and_nothing_personal(cat_env):
    ddb = FakeDdb()
    catalog.set_clients(ddb=ddb)
    assert catalog.log_demand("sunrise over mountains", "video-9", "none", 0.21)
    kw = ddb.t.calls[0]
    assert kw["Key"]["phrase"] == "sunrise over mountains" and kw["Key"]["video"] == priv.video_ref("video-9", "pepper")
    flat = json.dumps({k: str(v) for k, v in kw.items()})
    assert "video-9" not in flat
    assert int(kw["ExpressionAttributeValues"][":ttl"]) - int(kw["ExpressionAttributeValues"][":now"]) == 365 * 86400   # 12 months


def test_the_demand_log_refuses_personal_phrases_without_salt_or_table(cat_env, monkeypatch):
    ddb = FakeDdb()
    catalog.set_clients(ddb=ddb)
    assert not catalog.log_demand("my wife in Paris", "v", "none")
    assert not catalog.log_demand("sunrise", "v", "weird-outcome")
    catalog._cache["salt"] = ""
    assert not catalog.log_demand("sunrise", "v", "none")
    catalog._cache["salt"] = "p"
    monkeypatch.delenv("CATALOG_DEMAND_TABLE")
    assert not catalog.log_demand("sunrise", "v", "none")
    assert ddb.t.calls == []


# ----------------------------------------------------------------------------- search and the director
CID = [("%064x" % i) for i in (1, 2, 3)]


class FakeVectors:
    def __init__(self, hits=None, fail=False):
        self.hits, self.fail, self.calls = hits or [], fail, []

    def query_vectors(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("boom")
        return {"vectors": self.hits}


class FakeTable:
    def __init__(self, items):
        self.items = items

    def get_item(self, Key):   # noqa: N803
        it = self.items.get(Key["id"])
        return {"Item": it} if it else {}


class FakeS3:
    def __init__(self, objs):
        self.objs, self.gets = objs, []

    def get_object(self, Bucket, Key):   # noqa: N803
        self.gets.append((Bucket, Key))
        return {"Body": io.BytesIO(self.objs[Key])}


def setup_catalog(hits, items, objs, fail=False):
    ddb = type("D", (), {"Table": lambda self, n: FakeTable(items)})()
    catalog.set_clients(vectors=FakeVectors(hits, fail), ddb=ddb, s3=FakeS3(objs), embed_text=lambda t: [0.1] * 1024)


def hit(cid, dist, title="t"):
    return {"key": cid, "distance": dist, "metadata": {"title": title, "category": "nature"}}


def test_search_returns_scores_best_first_and_ignores_strange_keys(cat_env):
    setup_catalog([hit(CID[1], 0.5), hit(CID[0], 0.2), {"key": "../x", "distance": 0.1}, {"key": CID[2], "distance": None}], {}, {})
    out = catalog.search("sunrise", "9:16", k=5)
    assert [m["id"] for m in out] == [CID[0], CID[1]] and out[0]["score"] == 0.8 and out[0]["aspect_ok"]


def test_search_never_raises_and_is_empty_when_off_or_failing(cat_env, monkeypatch):
    setup_catalog([], {}, {}, fail=True)
    assert catalog.search("sunrise") == []
    assert catalog.search("   ") == []
    monkeypatch.delenv("CATALOG_BUCKET")
    assert catalog.search("sunrise") == []


def good_item(cid, status="approved"):
    return {"id": cid, "title": "Sunrise", "review_status": status}


def objects(cid):
    return {catalog.key_original(cid): jpeg(size=(1600, 900)), catalog.key_preview(cid): jpeg()}


def yes(system, user, **kw):
    return '{"fits": true, "reason": "ok"}', {"cost_usd": 0.001}


def test_flag_off_the_director_does_nothing_and_touches_nothing(monkeypatch):
    catalog.reset()
    for k in ("CATALOG_BUCKET", "CATALOG_TABLE", "CATALOG_VECTOR_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    assert catalog_pick.try_catalog("sunrise", "n", "a", "v", complete=yes) is None


def test_a_good_verified_approved_match_is_used_cropped_and_recorded_without_a_credit_line(cat_env):
    ddb = FakeDdb()
    setup_catalog([hit(CID[0], 0.2)], {CID[0]: good_item(CID[0])}, objects(CID[0]))
    catalog._cache["ddb"] = type("D", (), {"Table": lambda self, n: FakeTable({CID[0]: good_item(CID[0])}) if n == "t" else ddb.t})()
    r = catalog_pick.try_catalog("sunrise over mountains", "Dawn breaks over the peaks.", "dawn", "video-1", aspect="9:16", complete=yes)
    assert r and r["credit"] == "" and r["entry"]["source"] == "videomk-library" and r["entry"]["license"] == "videomk library" and r["entry"]["attribution"] == ""
    im = Image.open(io.BytesIO(r["jpeg"]))
    assert abs(im.width / im.height - 9 / 16) < 0.01   # the centred 9:16 cut of the 16:9 original
    assert ddb.t.calls and ddb.t.calls[0]["ExpressionAttributeValues"][":o"] == "catalog"


@pytest.mark.parametrize("dist,status,answer,outcome", [
    (0.9, "approved", None, "none"),            # below the threshold
    (0.2, "pending", None, "rejected"),         # not approved: never used
    (0.2, "approved", '{"fits": false}', "rejected"),
    (0.2, "approved", "not json", "rejected"),  # fail closed
    (0.2, "approved", '{"fits": "yes"}', "rejected"),
])
def test_a_match_that_fails_any_check_falls_back_to_stock_and_logs_it(cat_env, dist, status, answer, outcome):
    ddb = FakeDdb()
    setup_catalog([hit(CID[0], dist)], {CID[0]: good_item(CID[0], status)}, objects(CID[0]))
    catalog._cache["ddb"] = type("D", (), {"Table": lambda self, n: FakeTable({CID[0]: good_item(CID[0], status)}) if n == "t" else ddb.t})()
    cmp = (lambda s, u, **kw: (answer, {"cost_usd": 0})) if answer else yes
    assert catalog_pick.try_catalog("sunrise over mountains", "n", "a", "v", complete=cmp) is None
    assert ddb.t.calls[0]["ExpressionAttributeValues"][":o"] == outcome


def test_a_failing_verifier_is_a_no(cat_env):
    setup_catalog([hit(CID[0], 0.2)], {CID[0]: good_item(CID[0])}, objects(CID[0]))
    def boom(*a, **k):
        raise RuntimeError("model down")
    assert catalog_pick.try_catalog("sunrise", "n", "a", "v", complete=boom) is None


def test_the_credit_block_leaves_our_own_images_out_but_keeps_other_sources():
    from engine import assets
    ledger = [catalog.ledger_entry(good_item(CID[0])), {"source": "unsplash", "id": "1", "title": "x", "creator": "Ann", "license": "Unsplash License", "attribution": "Photo by Ann on Unsplash", "landing_url": "https://u"}]
    text = assets.credits_block(ledger, [])
    assert "Ann" in text and "videomk" not in text.lower()
    assert assets.credits_block(ledger[:1], []) == ""


def test_crop_rules_keep_the_centre_for_every_aspect():
    assert catalog_style.crop_box(1600, 900, "16:9") == [0, 0, 1600, 900]
    l, t, r, b = catalog_style.crop_box(1600, 900, "9:16")
    assert (r - l, b - t) == (506, 900) and l == (1600 - 506) // 2
    assert catalog_style.crop_box(1600, 900, "1:1") == [350, 0, 1250, 900]
    assert catalog_style.crop_box(1600, 900, "nonsense") == [0, 0, 1600, 900]
    assert "no" in catalog_style.NEGATIVE or "text" in catalog_style.NEGATIVE and "logos" in catalog_style.NEGATIVE


# ----------------------------------------------------------------------------- the generator
PASS = json.dumps({"adherence": 9, "quality": 9, "text_visible": False, "logo_or_brand": False, "real_person_likeness": False, "anatomy_problem": False, "warped_objects": False, "unsafe": False,
                   "centre_subject": True, "calm_bottom": True, "style_ok": True, "reasons": "clean"})
FAIL = json.dumps({**json.loads(PASS), "text_visible": True, "reasons": "a sign with letters"})


class FakeBedrock:
    """Fake of the OpenAI Images API call (a callable body -> response); the name is kept for the many call sites."""

    def __init__(self, out_tokens=1413):
        self.calls = []
        self.n = 0
        self.out_tokens = out_tokens

    def __call__(self, body):
        self.calls.append(body)
        self.n += 1
        c = (40 + self.n * 7 % 200, 90, 140 - self.n * 3 % 100)
        return {"data": [{"b64_json": base64.b64encode(jpeg(c, (1344 // 4, 768 // 4))).decode()}], "usage": {"input_tokens": 19, "output_tokens": self.out_tokens}}


def plan(n=2):
    return {"plan_id": "t1", "approved_by": "owner", "items": [{"id": f"i{k}", "title": f"Image {k}", "category": "nature", "subject": f"A calm lake number {k}", "layout": "mountains", "seed": k,
                                                           "serves": ["a lake", "calm water", "mountain mirror"]} for k in range(n)]}


def vecfn(seq):
    it = iter(seq)
    return lambda j: next(it)


def basis(i, n=1024):
    v = np.zeros(n)
    v[i] = 1
    return v.tolist()


def test_a_plan_needs_approval_a_name_and_three_different_prompts_per_image():
    assert gen.validate_plan(plan()) == []
    p = plan()
    p["approved_by"] = ""
    p["items"][0]["serves"] = ["one", "one", "two"]
    errs = " ".join(gen.validate_plan(p))
    assert "approved_by" in errs and "at least 3" in errs


def test_the_cap_stops_a_run_before_the_call_that_would_pass_it(tmp_path):
    br = FakeBedrock()
    sp = gen.Spend(0.10, str(tmp_path / "s.jsonl"), "r")
    st = catalog_store.LocalStore(str(tmp_path / "c"))
    out = gen.run(plan(3), st, sp, profile="qa", regen=False, only=None, embed_image=vecfn([basis(1), basis(2), basis(3)]), api=br, complete=lambda *a, **k: (PASS, {"cost_usd": 0.0004}))
    assert out["stopped"] and sp.total <= 0.10 + 1e-9
    assert len(out["made"]) == 1                       # one image (0.0424 real + check + embed) fits; the second item's reserve (0.0655) would pass the cap
    assert len(br.calls) == 1                          # nothing was called after the stop
    assert abs(sp.total - (1413 * 30 / 1e6 + 19 * 5 / 1e6 + 0.0004 + 0.0005)) < 1e-6   # the REAL token cost is charged, not the reserve
    lines = [json.loads(l) for l in open(tmp_path / "s.jsonl")]
    assert abs(sum(l["usd"] for l in lines) - sp.total) < 1e-6


def test_a_run_stores_original_preview_thumbnail_metadata_and_vector_and_is_idempotent(tmp_path):
    br = FakeBedrock()
    st = catalog_store.LocalStore(str(tmp_path / "c"))
    sp = gen.Spend(5, str(tmp_path / "s.jsonl"), "r")
    out = gen.run(plan(2), st, sp, profile="qa", regen=False, only=None, embed_image=vecfn([basis(1), basis(2)]), api=br, complete=lambda *a, **k: (PASS, {"cost_usd": 0.0004}))
    assert len(out["made"]) == 2
    imgs = st.images()
    assert len(imgs) == 2
    it = imgs[0]
    cid = it["id"]
    assert catalog.content_hash(st.get(catalog.key_original(cid))) == cid
    assert st.has(catalog.key_preview(cid)) and st.has(catalog.key_thumb(cid)) and st.get_vector(cid)
    for f in ("prompt", "negative_prompt", "model", "created", "cost_usd", "seed", "licence", "provenance", "review_status", "tags", "serves", "promoted_from"):
        assert f in it, f
    assert it["review_status"] == "approved" and "no text" not in it["prompt"] and "text" in it["negative_prompt"]
    again = gen.run(plan(2), st, gen.Spend(5, str(tmp_path / "s2.jsonl"), "r2"), profile="qa", regen=False, only=None, embed_image=vecfn([]), api=br, complete=lambda *a, **k: (PASS, {"cost_usd": 0}))
    assert again["skipped"] == ["i0", "i1"] and not again["made"] and not os.path.exists(tmp_path / "s2.jsonl")


def test_a_picture_the_check_rejects_is_never_stored_and_regenerates_once_within_the_cap(tmp_path):
    answers = iter([FAIL, PASS])
    st = catalog_store.LocalStore(str(tmp_path / "c"))
    sp = gen.Spend(5, str(tmp_path / "s.jsonl"), "r")
    out = gen.run(plan(1), st, sp, profile="qa", regen=True, only=None, embed_image=vecfn([basis(5)]), api=FakeBedrock(), complete=lambda *a, **k: (next(answers), {"cost_usd": 0.0004}))
    assert len(out["rejected"]) == 1 and out["made"][0]["attempts"] == 2 and len(st.images()) == 1
    st2 = catalog_store.LocalStore(str(tmp_path / "c2"))
    out2 = gen.run(plan(1), st2, gen.Spend(5, str(tmp_path / "s3.jsonl"), "r"), profile="qa", regen=False, only=None, embed_image=vecfn([]), api=FakeBedrock(), complete=lambda *a, **k: (FAIL, {"cost_usd": 0}))
    assert out2["rejected"] and not st2.images()


def test_a_near_duplicate_of_a_stored_image_is_dropped(tmp_path):
    st = catalog_store.LocalStore(str(tmp_path / "c"))
    gen.run(plan(1), st, gen.Spend(5, str(tmp_path / "s.jsonl"), "r"), profile="qa", regen=False, only=None, embed_image=vecfn([basis(7)]), api=FakeBedrock(), complete=lambda *a, **k: (PASS, {"cost_usd": 0}))
    p2 = plan(1)
    p2["plan_id"] = "t2"
    out = gen.run(p2, st, gen.Spend(5, str(tmp_path / "s.jsonl"), "r"), profile="qa", regen=False, only=None, embed_image=vecfn([basis(7)]), api=FakeBedrock(), complete=lambda *a, **k: (PASS, {"cost_usd": 0}))
    assert out["duplicates"] and len(st.images()) == 1


@pytest.mark.parametrize("text", ["", "no json", '{"adherence": 9}', json.dumps({**json.loads(PASS), "quality": 5}), json.dumps({**json.loads(PASS), "calm_bottom": False}), json.dumps({**json.loads(PASS), "real_person_likeness": True}),
                                  json.dumps({**json.loads(PASS), "unsafe": "no"})])
def test_the_quality_judge_fails_closed(text):
    assert gen.judge(text)[0] is False


def test_the_quality_judge_passes_a_clean_picture():
    assert gen.judge(PASS)[0] is True


def test_the_generator_refuses_prod_the_default_profile_and_a_missing_yes(tmp_path, monkeypatch):
    p = tmp_path / "p.json"
    p.write_text(json.dumps(plan()))
    for argv in (["x", str(p), "--store", "prod", "--yes"], ["x", str(p), "--store", "local:" + str(tmp_path), "--yes", "--profile", "default"], ["x", str(p), "--store", "local:" + str(tmp_path)]):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as e:
            gen.main()
        assert e.value.code not in (0, None)
    assert not os.path.exists(tmp_path / "items.json")


def test_the_generator_sends_the_openai_request_with_the_house_prompt_and_prices_it_from_usage():
    br = FakeBedrock(out_tokens=1000)
    jpg, cost = gen.generate_image(br, plan(1)["items"][0])
    body = br.calls[0]
    assert body["model"] == "gpt-image-2.6-flare" and body["size"] == "2048x1152" and body["quality"] == "high" and body["output_format"] == "jpeg" and "seed" not in body
    assert catalog_style.HOUSE_STYLE in body["prompt"] and "bottom quarter" in body["prompt"] and "logos" in body["prompt"]
    assert jpg[:2] == b"\xff\xd8" and abs(cost - (1000 * 30 / 1e6 + 19 * 5 / 1e6)) < 1e-9
    assert gen.PRICES["generate"] > 1500 * 30 / 1e6   # the reserve covers a high-quality image with margin
    with pytest.raises(RuntimeError):
        gen.generate_image(lambda b: {"data": []}, plan(1)["items"][0])


def test_no_stability_or_bedrock_generation_path_is_left():
    src = open(gen.__file__).read()
    assert "invoke_model" not in src and "us.stability" not in src and "boto3.Session(profile_name=profile, region_name=GEN_REGION)" not in src


# ----------------------------------------------------------------------------- promotion
def filled_store(path, n=2):
    st = catalog_store.LocalStore(str(path))
    for k in range(n):
        data = jpeg((10 * k, 50, 90))
        cid = catalog.content_hash(data)
        for key, d in ((catalog.key_original(cid), data), (catalog.key_preview(cid), data + b"p"), (catalog.key_thumb(cid), data + b"t")):
            st.put(key, d)
        st.put_vector(cid, basis(k), {"title": f"t{k}"})
        st.put_item({"id": cid, "title": f"t{k}", "review_status": "approved", "created": f"2026-01-0{k + 1}", "promoted_from": ""})
    return st


def test_promotion_dry_run_writes_nothing_then_copies_objects_vectors_and_rows_with_provenance(tmp_path):
    src, dst = filled_store(tmp_path / "a"), catalog_store.LocalStore(str(tmp_path / "b"))
    rep = promo.promote(src, dst)
    assert len(rep["copied"]) == 2 and not dst.items() and not dst.vector_ids()
    rep = promo.promote(src, dst, dry_run=False, now="2026-02-01T00:00:00Z")
    assert len(rep["copied"]) == 2
    for it in src.images():
        got = dst.get_item(it["id"])
        assert got["promoted_from"] == src.label and got["promoted_at"] == "2026-02-01T00:00:00Z"
        assert dst.get(catalog.key_original(it["id"])) == src.get(catalog.key_original(it["id"]))
        assert dst.get_vector(it["id"])[0] == src.get_vector(it["id"])[0]   # the vector is copied, never re-embedded


def test_promotion_is_idempotent_and_resumes_a_half_copied_image(tmp_path):
    src, dst = filled_store(tmp_path / "a"), catalog_store.LocalStore(str(tmp_path / "b"))
    promo.promote(src, dst, dry_run=False)
    again = promo.promote(src, dst, dry_run=False)
    assert not again["copied"] and len(again["skipped"]) == 2
    cid = src.images()[0]["id"]
    dst._save("items.json", {k: v for k, v in dst._json("items.json").items() if k != cid})   # the row is written last: without it the image is incomplete
    resumed = promo.promote(src, dst, dry_run=False)
    assert resumed["copied"] == [cid]


def test_promotion_refuses_unapproved_images_and_a_corrupted_original(tmp_path):
    src = filled_store(tmp_path / "a", 3)
    ids = sorted(i["id"] for i in src.images())
    row = src.get_item(ids[0])
    row["review_status"] = "pending"
    src.put_item(row)
    src.put(catalog.key_original(ids[1]), b"corrupted")
    dst = catalog_store.LocalStore(str(tmp_path / "b"))
    rep = promo.promote(src, dst, dry_run=False)
    assert rep["copied"] == [ids[2]] and len(rep["refused"]) == 2


def test_promotion_stops_on_a_checksum_mismatch_in_the_target(tmp_path):
    class Flaky(catalog_store.LocalStore):
        def put(self, key, data, content_type="image/jpeg"):
            super().put(key, data[:-1] if key.startswith("p/") else data)
    src = filled_store(tmp_path / "a", 1)
    with pytest.raises(RuntimeError):
        promo.promote(src, Flaky(str(tmp_path / "b")), dry_run=False)
    assert not catalog_store.LocalStore(str(tmp_path / "b")).items()


def test_prod_needs_yes_prod_and_nothing_flows_out_of_prod(monkeypatch):
    for argv in (["x", "--from", "qa", "--to", "prod", "--no-dry-run"], ["x", "--from", "prod", "--to", "qa"], ["x", "--from", "qa", "--to", "qa"]):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit):
            promo.main()


def test_the_default_is_a_dry_run(monkeypatch, tmp_path, capsys):
    filled_store(tmp_path / "a")
    monkeypatch.setattr(sys, "argv", ["x", "--from", f"local:{tmp_path / 'a'}", "--to", f"local:{tmp_path / 'b'}"])
    promo.main()
    assert "Dry run" in capsys.readouterr().out and not catalog_store.LocalStore(str(tmp_path / "b")).items()


# ----------------------------------------------------------------------------- the plan
def test_the_plan_keeps_only_uncovered_clusters_asked_by_three_different_videos(monkeypatch):
    topics = {"sunrise": 0, "sunrise mountain": 0, "dawn peaks": 0, "laptop desk": 1, "typing": 1, "keyboard hands": 1, "eiffel": 2, "eiffel tower": 2, "eiffel paris": 2, "rare thing": 3}
    emb = {}
    for ph, k in topics.items():
        v = np.zeros(1024)
        v[k] = 1
        v[10 + len(ph)] = 0.05
        emb[ph] = v / np.linalg.norm(v)
    rows = [{"phrase": ph, "video": f"v{n}"} for n, ph in enumerate(topics)]
    rows += [{"phrase": "rare thing", "video": "v0"}]
    def asker(system, user):
        if "eiffel" in user:
            return '{"generic": false}'
        return json.dumps({"generic": True, "title": "Sunrise" if "sunrise" in user else "Laptop", "category": "nature", "subject": "A calm scene", "people": False, "layout": "mountains"})
    cat = np.array([emb["laptop desk"]], dtype=np.float32)    # the catalog already answers the laptop cluster
    out = plan_mod.plan_from_rows(rows, embed_queries=lambda ps: np.array([emb[p] for p in ps], dtype=np.float32), catalog_vectors=cat, ask=asker, covered=0.5, cluster_thr=0.9)
    assert [i["title"] for i in out["items"]] == ["Sunrise"]
    it = out["items"][0]
    assert it["distinct_videos"] >= 3 and len(it["serves"]) >= 3 and out["approved_by"] == "" and it["estimated_usd"] > 0
    assert out["report"]["rejected_clusters"] and out["report"]["already_covered"] == 3
    assert gen.validate_plan(out) and "approved_by" in " ".join(gen.validate_plan(out))   # not runnable until the owner approves


# ----------------------------------------------------------------------------- the stores
def test_the_local_store_round_trips_and_refuses_paths_outside_it(tmp_path):
    st = catalog_store.LocalStore(str(tmp_path))
    st.put("o/x.jpg", b"1")
    assert st.has("o/x.jpg") and st.get("o/x.jpg") == b"1"
    with pytest.raises(ValueError):
        st.get("../../etc/passwd")
    st.put_vector("a", basis(1), {"k": 1})
    st.put_vector("b", basis(2), {})
    assert st.query(basis(1), 1)[0][0] == "a"
    assert catalog_store.names("qa")["bucket"] == "videomk-qa-catalog-552357225438" and catalog_store.names("prod")["index"] == "catalog-images"


# ----------------------------------------------------------------------------- the CDK template
@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    cache = {}
    try:
        from backend_stack import BackendStack

        def build(**ctx):
            key = tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-cat-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def test_flag_off_the_template_has_no_catalog_resource(synth):
    t = synth()
    text = json.dumps(t)
    assert "catalog" not in text.lower().replace("catalog_", "x") or "CATALOG_BUCKET" not in text
    assert "CATALOG_BUCKET" not in text and "catalog-images" not in text and not [k for k in t["Resources"] if "ImageCatalog" in k]


def test_flag_on_there_is_a_private_encrypted_bucket_a_table_an_index_and_narrow_rights(synth):
    t = synth(imageCatalog="1")
    ids = [k for k in t["Resources"] if "ImageCatalog" in k]
    bucket = [v for k, v in of(t, "AWS::S3::Bucket").items() if "ImageCatalog" in k][0]["Properties"]
    assert bucket["PublicAccessBlockConfiguration"] == {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
    assert "BucketEncryption" in bucket and bucket["VersioningConfiguration"]["Status"] == "Enabled"
    idx = [v for k, v in of(t, "AWS::S3Vectors::Index").items() if "ImageCatalog" in k][0]["Properties"]
    assert idx["IndexName"] == "catalog-images" and idx["Dimension"] == 1024 and idx["DistanceMetric"] == "cosine"
    tables = [v for k, v in of(t, "AWS::DynamoDB::Table").items() if "ImageCatalog" in k]
    assert len(tables) == 2 and any(tb["Properties"].get("TimeToLiveSpecification", {}).get("AttributeName") == "expires" for tb in tables)
    # nothing in the bucket policy opens it up
    assert not any("Principal" in s and s["Principal"] == "*" and s["Effect"] == "Allow" for p in of(t, "AWS::S3::BucketPolicy").values() for s in p["Properties"]["PolicyDocument"]["Statement"])
    beat = [k for k, v in of(t, "AWS::Lambda::Function").items() if v["Properties"].get("FunctionName") == "v2_beat" or "V2BeatFn" in k][0]
    role = t["Resources"][beat]["Properties"]["Role"]["Fn::GetAtt"][0]
    stmts = [s for p in of(t, "AWS::IAM::Policy").values() if {"Ref": role} in p["Properties"]["Roles"] for s in p["Properties"]["PolicyDocument"]["Statement"]]
    mine = [s for s in stmts if any(a.startswith(("s3vectors:", "dynamodb:GetItem", "dynamodb:UpdateItem")) for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])) or "catalog" in json.dumps(s).lower()]
    assert mine
    for s in mine:
        acts = [s["Action"]] if isinstance(s["Action"], str) else s["Action"]
        res = [s["Resource"]] if not isinstance(s["Resource"], list) else s["Resource"]
        assert not any(a in ("*", "s3:*", "dynamodb:*", "s3vectors:*") for a in acts)
        assert not any(r == "*" for r in res), s
        assert not any(a.startswith("s3:Put") or a.startswith("s3:Delete") or a in ("dynamodb:PutItem", "dynamodb:DeleteItem", "s3vectors:PutVectors") for a in acts if "catalog" in json.dumps(s["Resource"]).lower())
    env = t["Resources"][beat]["Properties"]["Environment"]["Variables"]
    assert env["CATALOG_VECTOR_INDEX"] == "catalog-images" and "CATALOG_BUCKET" in env and ids


def test_a_calm_bottom_band_flattens_the_guide_under_the_subject(tmp_path):
    import catalog_layouts
    g = catalog_layouts.LAYOUTS["forest_path"](3)
    flat = catalog_layouts.calm_band(g, 0.3)
    assert flat.size == g.size
    band = np.array(flat.crop((0, 620, 1344, 768)).convert("L"), dtype=float)
    assert band.std() < np.array(g.crop((0, 620, 1344, 768)).convert("L"), dtype=float).std() + 1e-6 and band.std() < 6

