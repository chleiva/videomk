"""Emergency switches the owner flips from the admin console (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md section 4, docs/ADMIN_RUNBOOK.md).

  stop_new_videos    generate and "Try again" answer 503 `maintenance` with a localized sentence; videos already being made finish; watching, the library,
                     cancel and delete keep working
  stop_free_videos   the day's free budget reads as 0 (common/free_grants.py): free credits cannot be spent, paid credits work
  stop_dictation     paid dictation (common/dictation.py) answers as switched off; typing and everything else keep working

Where: ONE item in the account-flags table, key `ops:switches` (no account id has that shape). Every function that serves a request can already READ that
table and none can write it, so the main stack needs no new permission or resource. The only writers are the admin console's "act" function (its policy
allows this one item and nothing else) and a person with AWS credentials (the runbook has the command).

Rules:
  * a switch can only RESTRICT: it is "stopped" only when its value is exactly true; anything else (missing, false, text, a number) means "running";
  * read at most once a minute per warm function (OPS_SWITCHES_TTL), with a short network timeout;
  * FAILS OPEN: a read error keeps the last good values, and with none, everything runs. A storage problem must never stop paying customers.
"""
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger()

ITEM_KEY = "ops:switches"
NEW_VIDEOS, FREE_VIDEOS, DICTATION = "stop_new_videos", "stop_free_videos", "stop_dictation"
SWITCHES = (NEW_VIDEOS, FREE_VIDEOS, DICTATION)
RETRY_AFTER_S = 300
MESSAGES = {
    "en": "VideoMK is briefly paused for maintenance. Your videos are safe. Please try again in a little while.",
    "es": "VideoMK está en pausa por mantenimiento durante un momento. Tus videos están a salvo. Inténtalo de nuevo en un rato.",
}

_cache: Dict[str, Any] = {"at": 0.0, "item": None}
_override: Optional[Dict[str, Any]] = None
_table = None


def set_state(values: Optional[Dict[str, Any]]) -> None:
    """Tests: use these values instead of the table (None: back to the table, cache cleared)."""
    global _override
    _override = values
    _cache.update({"at": 0.0, "item": None})


def _read() -> Dict[str, Any]:
    global _table
    name = os.environ.get("FLAGS_TABLE")
    if not name:
        return {}
    if _table is None:
        import boto3
        from botocore.config import Config
        _table = boto3.resource("dynamodb", config=Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 1})).Table(name)
    return _table.get_item(Key={"user_id": ITEM_KEY}).get("Item") or {}


def state(now: Optional[float] = None) -> Dict[str, Any]:
    """The stored switches (possibly empty). Never raises."""
    if _override is not None:
        return dict(_override)
    now = time.time() if now is None else now
    if _cache["item"] is None or now - _cache["at"] > float(os.environ.get("OPS_SWITCHES_TTL", "60")):
        try:
            _cache["item"] = _read()
        except Exception:   # noqa: BLE001 - fail open: the last good values, or everything running
            logger.exception("OPS_SWITCHES_READ_FAILED (keeping %s)", "the last good values" if _cache["item"] is not None else "everything running")
            _cache["item"] = _cache["item"] if _cache["item"] is not None else {}
        _cache["at"] = now
    return dict(_cache["item"])


def stopped(name: str, now: Optional[float] = None) -> bool:
    """True only when the switch is stored as exactly `true`."""
    try:
        return state(now).get(name) is True
    except Exception:   # noqa: BLE001
        return False


def message(locale: Optional[str]) -> str:
    """The maintenance sentence. The stored item may carry its own short text (`message_en`, `message_es`, set by hand: the console cannot write them)."""
    lang = "es" if locale == "es" else "en"
    own = state().get(f"message_{lang}")
    return own.strip()[:300] if isinstance(own, str) and own.strip() else MESSAGES[lang]


def creation_state(locale: Optional[str]) -> Dict[str, Any]:
    """For GET .../capabilities: lets the apps say "paused" before the tap."""
    paused = stopped(NEW_VIDEOS)
    return {"paused": paused, "code": "maintenance" if paused else None, "message": message(locale) if paused else None}


def maintenance(event: Any) -> Optional[Dict[str, Any]]:
    """None while new videos may start; else the 503 answer for a request that would start one."""
    if not stopped(NEW_VIDEOS):
        return None
    from common import i18n
    from common.http import json_response
    loc = i18n.pick_locale(event)
    logger.warning("OPS_NEW_VIDEOS_STOPPED request refused")
    return json_response(503, {"code": "maintenance", "message": message(loc), "retry_after": RETRY_AFTER_S}, {"Retry-After": str(RETRY_AFTER_S), "Content-Language": loc})
