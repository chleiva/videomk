"""Cost levers of 2026-11-28 (docs/COST_LEVERS_2026-11-28.md): prompt caching of the fixed script prompt, cache tokens and render compute on the video record."""
import json

import boto3
import pytest
from botocore.exceptions import ClientError

from engine import llm


class _Body:
    def __init__(self, usage):
        self.usage = usage

    def read(self):
        return json.dumps({"content": [{"type": "text", "text": "ok"}], "usage": self.usage, "stop_reason": "end_turn"}).encode()


def _client(sent, usage, reject_cache=False):
    class C:
        def invoke_model(self, modelId, body):
            b = json.loads(body)
            sent.append(b)
            if reject_cache and isinstance(b["system"], list):
                raise ClientError({"Error": {"Code": "ValidationException", "Message": "cache_control: Extra inputs are not permitted"}}, "InvokeModel")
            return {"body": _Body(usage)}
    return C()


HEAD = "H" * 5000


def test_system_blocks_split_and_marker_never_reaches_the_model():
    s = HEAD + llm.CACHE_BREAK + "\n\nLanguage: English"
    blocks = llm.system_blocks(s, True)
    assert blocks[0] == {"type": "text", "text": HEAD, "cache_control": {"type": "ephemeral"}} and blocks[1] == {"type": "text", "text": "\n\nLanguage: English"}
    assert llm.system_blocks(s, False) == HEAD + "\n\nLanguage: English"                       # off: the same text the model always saw
    assert llm.system_blocks("short" + llm.CACHE_BREAK + "tail", True) == "shorttail"          # under the minimum: no checkpoint
    assert llm.system_blocks("no marker", True) == "no marker"
    assert "CACHE-BREAK" not in json.dumps(llm.system_blocks(s, True))


def test_cached_tokens_are_priced_and_reported(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_bedrock", lambda: _client(sent, {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 8000, "cache_read_input_tokens": 0}))
    monkeypatch.setattr(llm, "_cache_broken", False)
    text, meta = llm.complete(HEAD + llm.CACHE_BREAK + "tail", "u", model="global.anthropic.claude-sonnet-5-5")
    assert sent[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert meta["cache_write_tokens"] == 8000 and meta["cache_read_tokens"] == 0
    assert meta["cost_usd"] == pytest.approx((100 * 2 + 50 * 10 + 8000 * 2 * 1.25) / 1e6)
    # Sonnet 5.5 reads at 0.05x, other models at 0.1x
    assert llm.estimate_cost("global.anthropic.claude-sonnet-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.10)
    assert llm.estimate_cost("global.anthropic.claude-haiku-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.01)
    assert llm.estimate_cost("global.anthropic.claude-sonnet-5-5", 10, 5) == pytest.approx((10 * 2 + 5 * 10) / 1e6)   # no cache: as before


def test_a_model_that_rejects_the_cache_field_costs_one_retry_and_never_fails(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_bedrock", lambda: _client(sent, {"input_tokens": 10, "output_tokens": 5}, reject_cache=True))
    monkeypatch.setattr(llm, "_cache_broken", False)
    text, meta = llm.complete(HEAD + llm.CACHE_BREAK + "tail", "u", model="m-sonnet-5-5")
    assert text == "ok" and isinstance(sent[0]["system"], list) and sent[1]["system"] == HEAD + "tail"
    assert llm._cache_broken is True
    llm.complete(HEAD + llm.CACHE_BREAK + "tail", "u", model="m-sonnet-5-5")
    assert sent[2]["system"] == HEAD + "tail"            # later calls in this container do not try again


def test_switch_off(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_bedrock", lambda: _client(sent, {"input_tokens": 10, "output_tokens": 5}))
    monkeypatch.setattr(llm, "_cache_broken", False)
    monkeypatch.setattr(llm, "PROMPT_CACHE", False)
    llm.complete(HEAD + llm.CACHE_BREAK + "tail", "u", model="m-sonnet-5-5")
    assert sent[0]["system"] == HEAD + "tail"


def test_the_script_prompt_has_a_fixed_part_worth_caching_and_the_text_is_unchanged():
    from engine import plan as plan_mod
    for lang, region in (("en", "US"), ("es", "ES"), ("fr", "FR")):
        sp = plan_mod.system_prompt(lang, region)
        head, tail = sp.split(llm.CACHE_BREAK)
        assert len(head) > llm.MIN_CACHE_CHARS and tail.lstrip().startswith("Language:")
    en, es = (plan_mod.system_prompt(l, "US").split(llm.CACHE_BREAK)[0] for l in ("en", "es"))
    assert en == es                                                    # the fixed part is the same in every language, so one cache entry serves all
    assert llm.system_blocks(plan_mod.system_prompt("en", "US"), False) == plan_mod.system_prompt("en", "US").replace(llm.CACHE_BREAK, "")


def test_ask_with_effort_only_passes_it_to_callables_that_take_it():
    from engine import plan as plan_mod
    assert plan_mod.ask_with_effort(lambda s, u: "two", "s", "u", "low") == "two"
    assert plan_mod.ask_with_effort(lambda s, u, effort=None: f"e={effort}", "s", "u", "low") == "e=low"
    assert plan_mod.ask_with_effort(lambda s, u, effort=None: f"e={effort}", "s", "u", None) == "e=None"
    assert plan_mod.RETRY_EFFORT == "" and llm.WB_REVIEW_EFFORT is None and not llm.WB_REVIEW_MODEL   # nothing that was not proven neutral is on


def test_cache_tokens_and_render_compute_on_the_video(aws):
    from engine import costs
    aws.Table("Videos").put_item(Item={"video_id": "v1"})
    costs.add_tokens("v1", {"cache_read_tokens": 8239, "cache_write_tokens": 0})
    costs.add_tokens("v1", {"cache_read_tokens": 100, "cache_write_tokens": 50})
    usd = costs.add_render("v1", 100.0)
    costs.add_render("v1", 50.0)
    it = aws.Table("Videos").get_item(Key={"video_id": "v1"})["Item"]
    assert it["cache_read_tokens"] == 8339 and it["cache_write_tokens"] == 50
    assert usd == pytest.approx(100 * 0.0000166667, abs=1e-6) and float(it["c_render"]) == pytest.approx(150 * 0.0000166667, abs=2e-6) and float(it["render_gbs"]) == 150
    assert "cost_usd" not in it                      # the render is NOT under the hard cap of cost_usd
    assert costs.add_render("v1", 0) == 0.0


def test_chunk_handler_reports_gbs(monkeypatch):
    from engine.handlers import render_chunk_handler as h
    monkeypatch.setattr(h.awsio, "head", lambda k: False)
    monkeypatch.setattr(h.awsio, "get_json", lambda k: {"frame": {"resolution": "1080p"}})
    monkeypatch.setattr(h, "chunk_timeline", lambda tl, lo, hi: {})
    monkeypatch.setattr(h.pipeline, "render_chunk", lambda *a, **k: (__import__("time").sleep(0.05), {"frames": 3})[1])
    monkeypatch.setattr(h.awsio, "upload", lambda *a, **k: None)

    class Ctx:
        memory_limit_in_mb = 4096
    out = h.handler({"video_id": "v1", "k": 0, "hash": "a" * 24, "timeline_key": "t", "lo": 0, "hi": 1, "frames": 3}, Ctx())
    assert out["gbs"] == pytest.approx(0.05 * 4, abs=0.2) and out["cached"] is False
    monkeypatch.setattr(h.awsio, "head", lambda k: True)
    assert "gbs" not in h.handler({"video_id": "v1", "k": 0, "hash": "a" * 24, "timeline_key": "t", "lo": 0, "hi": 1, "frames": 3}, Ctx())


def test_retry_clears_the_new_cost_fields():
    import video_retry
    for a in ("c_render", "render_gbs", "cache_read_tokens", "cache_write_tokens"):
        assert a in video_retry.COST_ATTRS
