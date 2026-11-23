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
PRIMARY_MODEL = os.environ.get("PLAN_MODEL_ID", f"{GEO}.anthropic.claude-sonnet-5-5")
# No fallback by default: a silent downgrade hides a broken primary (it already did once). Set PLAN_FALLBACK_MODEL_IDS to opt in.
FALLBACK_MODELS = [m for m in os.environ.get("PLAN_FALLBACK_MODEL_IDS", "").split(",") if m]

# $/1M tokens (input, output) for cost *estimates* only; override with PRICES_JSON={"model":[in,out]}.
# Claude 5.x: thinking is adaptive and temperature/top_p are rejected; depth is set with output_config.effort instead.
DEFAULT_PRICES = {"sonnet-5": (2.0, 10.0), "haiku-5": (0.10, 0.50), "sonnet": (3.0, 15.0), "haiku-4": (1.0, 5.0), "haiku": (0.25, 1.25)}


def is_claude5(model_id: str) -> bool:
    return re.search(r"claude-(sonnet|haiku|opus|fable|mythos)-5", model_id or "") is not None


def estimate_cost(model_id: str, tokens_in: int, tokens_out: int) -> float:
    prices = json.loads(os.environ["PRICES_JSON"]) if os.environ.get("PRICES_JSON") else {}
    if model_id in prices:
        pin, pout = prices[model_id]
    else:
        key = next((k for k in ("sonnet-5", "haiku-5", "sonnet", "haiku-4") if k in model_id), "haiku")
        pin, pout = DEFAULT_PRICES[key]
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


_client = None


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


REVIEW_MODEL = os.environ.get("REVIEW_MODEL_ID", f"{GEO}.anthropic.claude-haiku-5-5")


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
    def body_for(model_id: str) -> str:
        body: Dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens,
            "system": system, "messages": [{"role": "user", "content": blocks}],
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
            res = json.loads(_bedrock().invoke_model(modelId=model_id, body=body_for(model_id))["body"].read())
            text = "".join(p.get("text", "") for p in res.get("content", []) if isinstance(p, dict))
            usage = res.get("usage") or {}
            tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            return text, {"model": model_id, "tokens_in": tin, "tokens_out": tout, "cost_usd": estimate_cost(model, tin, tout)}
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("AccessDeniedException", "ValidationException", "ResourceNotFoundException", "ModelNotReadyException"):
                logging.warning("model %s unavailable (%s); trying next", model_id, code)
                last = e
                continue
            raise
    raise RuntimeError(f"no usable planning model (last error: {last})")
