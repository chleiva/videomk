"""Per-video cost accounting with a hard cap, kept on the video item (DynamoDB ADD is atomic)."""
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

MAX_COST_USD = float(os.environ.get("MAX_VIDEO_COST_USD", "1.50"))

# $ per unit, estimates: override via env for your negotiated/current rates
TTS_PER_CHAR = {"gemini": float(os.environ.get("TTS_GEMINI_PER_CHAR", "0.000016")),    # ~$10/M audio tokens at ~25 tok/s, ~15 chars/s
                "openai": float(os.environ.get("TTS_OPENAI_PER_CHAR", "0.000018")),
                "polly": float(os.environ.get("TTS_POLLY_PER_CHAR", "0.000016")),    # neural: ~$16 per 1M characters (list price; verify)
                "mock": 0.0}


class CostCapExceeded(RuntimeError):
    pass


PARTS = ("speech", "script", "research", "photos", "stock", "deck", "stt", "vidup")   # what a cost paid for: narration, the script's language models, web research, the user's photos, stock photo/clip reviews


def add_cost(video_id: str, usd: float, table_name: str | None = None, field: str = "cost_usd", part: str | None = None) -> float:
    """Atomically add `usd`; raises CostCapExceeded (job fails, quota refunded) if the cap would be passed.
    With `part` the same amount is also added to the video's `c_<part>` attribute, so each video carries its own breakdown."""
    if not field.replace("_", "").isalnum():
        raise ValueError("bad cost field")
    if part is not None and part not in PARTS:
        raise ValueError("bad cost part")
    if usd <= 0:  # nothing to record (e.g. mock provider); also avoids a no-op write
        return 0.0
    table = boto3.resource("dynamodb").Table(table_name or os.environ.get("VIDEOS_TABLE", "Videos"))
    try:
        res = table.update_item(
            Key={"video_id": video_id},
            UpdateExpression="ADD #f :c" + (", #p :c" if part else ""),
            ConditionExpression="attribute_not_exists(#f) OR #f <= :room",
            ExpressionAttributeNames={"#f": field, **({"#p": f"c_{part}"} if part else {})},
            ExpressionAttributeValues={":c": Decimal(str(round(usd, 6))), ":room": Decimal(str(round(MAX_COST_USD - usd, 6)))},
            ReturnValues="UPDATED_NEW",
        )
        return float(res.get("Attributes", {}).get(field, usd))
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise CostCapExceeded(f"video exceeded the ${MAX_COST_USD:.2f} cost cap") from e
        raise


def add_tokens(video_id: str, tokens: dict, table_name: str | None = None) -> None:
    """Add token counts (today: `cache_read_tokens`, `cache_write_tokens` of prompt caching) to the video item. Information only: never raises."""
    names = {k: v for k, v in tokens.items() if k in ("cache_read_tokens", "cache_write_tokens") and int(v) > 0}
    if not names:
        return
    try:
        boto3.resource("dynamodb").Table(table_name or os.environ.get("VIDEOS_TABLE", "Videos")).update_item(
            Key={"video_id": video_id}, UpdateExpression="ADD " + ", ".join(f"#{i} :{i}" for i in range(len(names))),
            ExpressionAttributeNames={f"#{i}": k for i, k in enumerate(names)}, ExpressionAttributeValues={f":{i}": int(v) for i, v in enumerate(names.values())})
    except Exception:   # noqa: BLE001 - a counter must never fail a video
        import logging
        logging.warning("CACHE_TOKENS_NOT_SAVED video=%s", video_id)


LAMBDA_GBS_USD = float(os.environ.get("LAMBDA_GBS_USD", "0.0000166667"))   # x86 Lambda, $ per GB-second (list price)


def render_cost(gbs: float) -> float:
    return round(max(0.0, float(gbs)) * LAMBDA_GBS_USD, 6)


def add_render(video_id: str, gbs: float, table_name: str | None = None) -> float:
    """Add the render chunks' compute to the video: `render_gbs` (GB-seconds) and `c_render` (USD, estimated from wall time x memory; the bill rounds to 1 ms and adds cold starts).
    NOT part of `cost_usd` and not under its hard cap (a 12-minute 4K render alone is about $1.9): the plans economics read `cost_usd + c_render`. Never raises."""
    usd = render_cost(gbs)
    if usd <= 0:
        return 0.0
    try:
        boto3.resource("dynamodb").Table(table_name or os.environ.get("VIDEOS_TABLE", "Videos")).update_item(
            Key={"video_id": video_id}, UpdateExpression="ADD c_render :c, render_gbs :g",
            ExpressionAttributeValues={":c": Decimal(str(usd)), ":g": Decimal(str(round(float(gbs), 2)))})
    except Exception:   # noqa: BLE001
        import logging
        logging.warning("RENDER_COST_NOT_SAVED video=%s", video_id)
        return 0.0
    return usd
