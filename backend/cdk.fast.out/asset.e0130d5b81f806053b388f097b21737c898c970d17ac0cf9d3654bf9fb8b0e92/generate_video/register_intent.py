import uuid
import time
from typing import Any, Dict, Optional

from .db import put_video_item


def register_intent(user_id: str, prompt: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Create the video record in DynamoDB with STARTED_PROCESSING status.
    """
    video_id = str(uuid.uuid4())
    item: Dict[str, Any] = {
        "video_id": video_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "STARTED_PROCESSING",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    put_video_item(table_name, item)
    return item


