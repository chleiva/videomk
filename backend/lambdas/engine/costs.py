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


PARTS = ("speech", "script", "research", "photos", "stock")   # what a cost paid for: narration, the script's language models, web research, the user's photos, stock photo/clip reviews


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
