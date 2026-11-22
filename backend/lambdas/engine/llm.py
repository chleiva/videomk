"""Director LLM call (Bedrock) with model fallback and token accounting."""
import json
import logging
import os
from typing import Any, Dict, Tuple

import boto3
from botocore.exceptions import ClientError

# Verify access to these in your account/region; the legacy Haiku 3 is the last-resort fallback.
PRIMARY_MODEL = os.environ.get("PLAN_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
FALLBACK_MODELS = [m for m in os.environ.get("PLAN_FALLBACK_MODEL_IDS", "us.anthropic.claude-haiku-4-5-20251001-v1:0,anthropic.claude-3-haiku-20240307-v1:0").split(",") if m]

# $/1M tokens (input, output) for cost *estimates* only; override with PRICES_JSON={"model":[in,out]}.
DEFAULT_PRICES = {"sonnet": (3.0, 15.0), "haiku-4": (1.0, 5.0), "haiku": (0.25, 1.25)}


def estimate_cost(model_id: str, tokens_in: int, tokens_out: int) -> float:
    prices = json.loads(os.environ["PRICES_JSON"]) if os.environ.get("PRICES_JSON") else {}
    if model_id in prices:
        pin, pout = prices[model_id]
    else:
        key = "sonnet" if "sonnet" in model_id else "haiku-4" if "haiku-4" in model_id else "haiku"
        pin, pout = DEFAULT_PRICES[key]
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


_client = None


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=os.environ.get("BEDROCK_REGION", "us-west-2"))
    return _client


def complete(system: str, user: str, *, max_tokens: int = 8000, temperature: float = 0.5) -> Tuple[str, Dict[str, Any]]:
    """Returns (text, meta{model, tokens_in, tokens_out, cost_usd}). Tries the fallbacks on access/validation errors."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens, "temperature": temperature,
        "system": system, "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
    })
    last: Exception | None = None
    for model in [PRIMARY_MODEL] + FALLBACK_MODELS:
        try:
            res = json.loads(_bedrock().invoke_model(modelId=model, body=body)["body"].read())
            text = "".join(p.get("text", "") for p in res.get("content", []) if isinstance(p, dict))
            usage = res.get("usage") or {}
            tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            return text, {"model": model, "tokens_in": tin, "tokens_out": tout, "cost_usd": estimate_cost(model, tin, tout)}
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("AccessDeniedException", "ValidationException", "ResourceNotFoundException", "ModelNotReadyException"):
                logging.warning("model %s unavailable (%s); trying next", model, code)
                last = e
                continue
            raise
    raise RuntimeError(f"no usable planning model (last error: {last})")
