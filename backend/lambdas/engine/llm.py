"""Director LLM call (Bedrock) with model fallback and token accounting."""
import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import boto3
from botocore.exceptions import ClientError

# Cross-region inference profiles are prefixed by geography (us./eu./apac.); derive it from the Bedrock region.
BEDROCK_REGION = os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "us-west-2"
GEO = "eu" if BEDROCK_REGION.startswith("eu-") else "apac" if BEDROCK_REGION.startswith("ap-") else "us"
# Verify access to these in your account/region (Sonnet 4.5 is marked legacy and Claude 3 Haiku is end of life on Bedrock).
# Owner (2026-11-25): Sonnet 5.5 and Haiku 5.5 go through Amazon Bedrock's GLOBAL inference profiles (global.*), not the regional eu./us. ones. GEO remains for other models.
PRIMARY_MODEL = os.environ.get("PLAN_MODEL_ID", "global.anthropic.claude-sonnet-5-5")
# No fallback by default: a silent downgrade hides a broken primary (it already did once). Set PLAN_FALLBACK_MODEL_IDS to opt in.
FALLBACK_MODELS = [m for m in os.environ.get("PLAN_FALLBACK_MODEL_IDS", "").split(",") if m]

# $/1M tokens (input, output) for cost *estimates* only; override with PRICES_JSON={"model":[in,out]}.
# Claude 5.x: thinking is adaptive and temperature/top_p are rejected; depth is set with output_config.effort instead.
DEFAULT_PRICES = {"sonnet-5": (2.0, 10.0), "haiku-5": (0.10, 0.50), "sonnet": (3.0, 15.0), "haiku-4": (1.0, 5.0), "haiku": (0.25, 1.25)}


def is_claude5(model_id: str) -> bool:
    return re.search(r"claude-(sonnet|haiku|opus|fable|mythos)-5", model_id or "") is not None


# Prompt caching (docs/COST_LEVERS_2026-11-28.md). A 5-minute cache write costs 1.25x the input price, a read 0.1x (0.05x on Sonnet 5.5; Anthropic's pricing page, read 2026-11-28).
# `tokens_in` from Bedrock EXCLUDES cached tokens, so a cost that ignored them would read low: they are priced here and counted in the cost record.
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = {"sonnet-5-5": 0.05}   # every other model: 0.1
PROMPT_CACHE = os.environ.get("PROMPT_CACHE", "on") != "off"
CACHE_BREAK = "\u2063\u2063CACHE-BREAK\u2063\u2063"   # in a system prompt: everything before it is the fixed part, cached; removed before the model sees it (system_blocks)
MIN_CACHE_CHARS = 3000                                 # about 800 tokens: under the model's minimum (512 on Sonnet/Haiku 5.5) a checkpoint is simply not used, but not worth a write
_cache_broken = False                                  # set when the model rejected a cache field: caching stays off in this container (the call is repeated without it)


def system_blocks(system: str, cache: bool) -> Any:
    """The `system` field. Text with CACHE_BREAK is sent as two blocks, the fixed first part marked as a cache checkpoint; without caching (or when the model rejected it) the pieces are
    joined and the marker is gone either way."""
    if CACHE_BREAK not in system:
        return system
    head, tail = system.split(CACHE_BREAK, 1)
    if not cache or len(head) < MIN_CACHE_CHARS or not tail.strip():
        return head + tail
    return [{"type": "text", "text": head, "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": tail}]


def estimate_cost(model_id: str, tokens_in: int, tokens_out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    prices = json.loads(os.environ["PRICES_JSON"]) if os.environ.get("PRICES_JSON") else {}
    if model_id in prices:
        pin, pout = prices[model_id]
    else:
        key = next((k for k in ("sonnet-5", "haiku-5", "sonnet", "haiku-4") if k in model_id), "haiku")
        pin, pout = DEFAULT_PRICES[key]
    rmult = next((m for k, m in CACHE_READ_MULT.items() if k in model_id), 0.1)
    return (tokens_in * pin + tokens_out * pout + cache_write * pin * CACHE_WRITE_MULT + cache_read * pin * rmult) / 1_000_000


def usage_of(res: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """(input tokens not cached, output tokens, cache read, cache write) of a response."""
    u = res.get("usage") or {}
    return int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), int(u.get("cache_read_input_tokens", 0) or 0), int(u.get("cache_creation_input_tokens", 0) or 0)


_client = None


def _bedrock():
    global _client
    if _client is None:
        from botocore.config import Config
        # A long script (12 minutes, ~10k output tokens plus thinking) takes more than botocore's default 60 s to come back in one response: with the default, the call timed
        # out and was retried 5 times (5.5 minutes) before failing the video (2026-11-25). One patient attempt and one retry instead.
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION, config=Config(read_timeout=int(os.environ.get("LLM_READ_TIMEOUT_S", "420")), connect_timeout=10, retries={"max_attempts": 2, "mode": "standard"}))
    return _client


REVIEW_MODEL = os.environ.get("REVIEW_MODEL_ID", "global.anthropic.claude-haiku-5-5")
# The whiteboard self-check's rewrite of failing boards (docs/COST_LEVERS_2026-11-28.md): "" = the script model.
WB_REVIEW_MODEL = os.environ.get("WB_REVIEW_MODEL_ID", "")
WB_REVIEW_EFFORT = os.environ.get("WB_REVIEW_EFFORT", "") or None   # None = the same effort as before (medium); "low" measured worse, not shipped
# Research decides what the video says (owner, 2026-11-25: at least Sonnet 5.5 at medium effort): it follows the script model unless RESEARCH_MODEL_ID overrides it.
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL_ID", "") or PRIMARY_MODEL
RESEARCH_EFFORT = os.environ.get("RESEARCH_EFFORT", "medium")


def complete_tools(
    system: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    *,
    max_tokens: int = 900,
    model: Optional[str] = None,
    effort: str = "low",
    tool_choice: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """One turn of a tool-using conversation (Bedrock native tool use). Returns (content blocks, stop_reason, meta{model, tokens, cost_usd}).
    No fallback model: an agent loop that silently changes model half-way is harder to reason about than one that fails and falls back at a higher level."""
    model_id = model or REVIEW_MODEL
    body: Dict[str, Any] = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens, "system": system_blocks(system, False), "messages": messages, "tools": tools}
    if tool_choice:
        body["tool_choice"] = tool_choice  # {"type": "none"} makes the model answer in text, used for the last turn of a loop
    if is_claude5(model_id):
        body["output_config"] = {"effort": effort}
    else:
        body["temperature"] = 0.2
    res = json.loads(_bedrock().invoke_model(modelId=model_id, body=json.dumps(body))["body"].read())
    usage = res.get("usage") or {}
    tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    blocks = [b for b in res.get("content", []) if isinstance(b, dict) and b.get("type") in ("text", "tool_use", "thinking", "redacted_thinking")]   # thinking blocks go back unchanged in the next turn of a tool loop
    return blocks, str(res.get("stop_reason") or ""), {"model": model_id, "tokens_in": tin, "tokens_out": tout, "cost_usd": estimate_cost(model_id, tin, tout)}


def complete(
    system: str,
    user: str,
    *,
    max_tokens: int = 8000,
    temperature: float = 0.5,
    images: Sequence[bytes] = (),
    model: Optional[str] = None,
    effort: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Returns (text, meta{model, tokens_in, tokens_out, cost_usd}). Tries the fallbacks on access/validation errors.

    `images` are JPEG bytes sent before the text as numbered image blocks (Bedrock accepts base64 sources only;
    keep each well under 5 MB: callers send ~512 px thumbnails).
    """
    blocks: List[Dict[str, Any]] = []
    for n, raw in enumerate(images, start=1):
        blocks.append({"type": "text", "text": f"Image {n}:"})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(raw).decode("ascii")}})
    blocks.append({"type": "text", "text": user})
    def body_for(model_id: str, cache: bool = True) -> str:
        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens,
            "system": system_blocks(system, cache and PROMPT_CACHE and not _cache_broken), "messages": [{"role": "user", "content": blocks}],
        }
        if is_claude5(model_id):  # temperature is rejected on 5.x; effort bounds the (adaptive) thinking that counts against max_tokens
            body["output_config"] = {"effort": effort or "medium"}
        else:
            body["temperature"] = temperature
        return json.dumps(body)

    last: Exception | None = None
    for model_id in [model or PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != (model or PRIMARY_MODEL)]:
        model = model_id
        try:
            try:
                res = json.loads(_bedrock().invoke_model(modelId=model_id, body=body_for(model_id))["body"].read())
            except ClientError as e:
                # a model (or a gateway in front of it) that rejects the cache field must not fail a video: once, without it, and no more caching in this container
                if e.response.get("Error", {}).get("Code", "") == "ValidationException" and "cache" in str(e).lower() and CACHE_BREAK in system:
                    global _cache_broken
                    _cache_broken = True
                    logging.warning("PROMPT_CACHE_REJECTED model=%s: %s", model_id, str(e)[:200])
                    res = json.loads(_bedrock().invoke_model(modelId=model_id, body=body_for(model_id, cache=False))["body"].read())
                else:
                    raise
            text = "".join(p.get("text", "") for p in res.get("content", []) if isinstance(p, dict))
            tin, tout, cread, cwrite = usage_of(res)
            return text, {"model": model_id, "tokens_in": tin, "tokens_out": tout, "cache_read_tokens": cread, "cache_write_tokens": cwrite,
                          "cost_usd": estimate_cost(model, tin, tout, cread, cwrite), "stop_reason": res.get("stop_reason")}
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("AccessDeniedException", "ValidationException", "ResourceNotFoundException", "ModelNotReadyException"):
                logging.warning("model %s unavailable (%s); trying next", model_id, code)
                last = e
                continue
            raise
    raise RuntimeError(f"no usable planning model (last error: {last})")
