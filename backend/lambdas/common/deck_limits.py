"""Deck upload limits, ids, keys, status and the length rule. Pure (no AWS, no models): shared by the API, the launcher, the planner and the converter's contract.
docs/DECK_TO_VIDEO.md has the reasoning behind every number."""
import math
import re
from typing import Any, Dict, Optional, Sequence

MAX_MB = 50
MAX_BYTES = MAX_MB * 1024 * 1024
MAX_SLIDES = 60
FORMATS = ("pptx", "pdf")
CONTENT_TYPES = {"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pdf": "application/pdf"}
ID_RE = re.compile(r"^[0-9a-f]{16}$")
EXPIRES = 900
STALE_PROCESSING_S = 600     # a deck still "processing" after 10 minutes is reported failed (the converter's own limit is 4 minutes of conversion)
SECONDS_PER_SLIDE = 20.0
MIN_AUTO_MINUTES, MAX_AUTO_MINUTES = 0.5, 12.0
TRIVIAL_ROLES = ("agenda", "section", "closing")
ERROR_CODES = ("deck_too_large", "deck_too_many_slides", "deck_unsupported", "deck_corrupt", "deck_encrypted", "deck_macro", "deck_empty", "deck_unsafe",
               "deck_convert_timeout", "deck_convert_failed")


def deck_dir(user_id: str, deck_id: str) -> str:
    """Under uploads/<user>/ on purpose: the two-day lifecycle rule, the account-deletion worker and the planner's delete right already cover that area."""
    return f"uploads/{user_id}/decks/{deck_id}/"


def original_key(user_id: str, deck_id: str, fmt: str) -> str:
    return f"{deck_dir(user_id, deck_id)}original.{fmt}"


def status_key(user_id: str, deck_id: str) -> str:
    return deck_dir(user_id, deck_id) + "status.json"


def auto_minutes(n_slides: int, roles: Optional[Sequence[str]] = None) -> float:
    """The length a deck gets when the person does not choose one: about 25 s per slide (agenda, section and thank-you slides count for a third), in steps of 15 s,
    between 30 s and 12 min (the product maximum). Above about 29 slides the average falls under 25 s a slide; 60 slides is about 12 s each."""
    weight = sum(0.35 if (roles and i < len(roles) and roles[i] in TRIVIAL_ROLES) else 1.0 for i in range(n_slides))
    return round(min(MAX_AUTO_MINUTES, max(MIN_AUTO_MINUTES, round(weight * SECONDS_PER_SLIDE / 15.0) * 15.0 / 60.0)), 4)


def limits() -> Dict[str, Any]:
    return {"max_mb": MAX_MB, "max_slides": MAX_SLIDES, "formats": list(FORMATS)}
