"""Hourly: slots that never got their file (the app was closed) give their reserved bytes back; a file that arrived but was never processed is processed now."""
import logging
import time
from typing import Any, Dict

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import library_ingest
from common import library as lib

logger = logging.getLogger()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, int]:
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - lib.PENDING_MAX_AGE_S))
    released = processed = 0
    start = None
    while True:
        res = lib.table().query(IndexName="Pending", KeyConditionExpression=Key("pend").eq("1") & Key("created").lt(cutoff), **({"ExclusiveStartKey": start} if start else {}))
        for it in res.get("Items", []):
            user, mid = it["user_id"], it["sk"][2:]
            try:
                lib.s3().head_object(Bucket=lib.bucket(), Key=lib.orig_key(user, mid))
                exists = True
            except ClientError:
                exists = False
            if exists:
                try:
                    library_ingest.process(user, mid, attempt=library_ingest.FINAL_ATTEMPT)
                    processed += 1
                except Exception:
                    logger.exception("sweeper could not process a photo")
            else:
                lib.reject(user, mid)
                released += 1
        start = res.get("LastEvaluatedKey")
        if not start:
            break
    logger.info("sweeper released=%s processed=%s", released, processed)
    return {"released": released, "processed": processed}
