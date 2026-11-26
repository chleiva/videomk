"""The prepared deck, on the planner's side: read what the converter left under uploads/<user>/decks/<id>/, put the slide pictures with the video's own assets (where the
renderer may read them), make small JPEGs for the vision model, and delete everything the person uploaded. Storage calls are passed in (testable without AWS)."""
import io
import json
import re
from typing import Any, Callable, Dict, List, Sequence, Tuple

from PIL import Image

from common.photo_ids import ID_RE

VISION_WIDTH = 1024
_NAME = re.compile(r"^slide_\d{3}\.png$")


def deck_dir(user_id: str, deck_id: str) -> str:
    if not ID_RE.match(deck_id):
        raise ValueError("bad deck id")
    return f"uploads/{user_id}/decks/{deck_id}/"


def load(user_id: str, deck_id: str, asset_prefix: str, *, get: Callable[[str], bytes], put: Callable[[str, bytes, str], None], delete: Callable[[str], None]
         ) -> Tuple[Dict[str, Any], List[bytes], Callable[[int], str]]:
    """(deck, JPEGs for the vision model in slide order, asset key of slide n). The uploaded files are deleted whether or not they were usable."""
    base = deck_dir(user_id, deck_id)
    names: List[str] = []
    try:
        deck = json.loads(get(base + "deck.json").decode("utf-8"))
        names = [n for n in deck.get("images", []) if isinstance(n, str) and _NAME.match(n)]
        if len(names) != len(deck["slides"]):
            raise ValueError("deck and slide pictures disagree")
        images: List[bytes] = []
        for n in names:
            raw = get(base + n)
            put(f"{asset_prefix}deck/{n}", raw, "image/png")
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((VISION_WIDTH, VISION_WIDTH))
            b = io.BytesIO()
            im.save(b, "JPEG", quality=80)
            images.append(b.getvalue())
    finally:
        for n in names + ["deck.json", "status.json"]:
            try:
                delete(base + n)
            except Exception:
                pass
    by = {i + 1: names[i] for i in range(len(names))}
    return deck, images, lambda n: f"{asset_prefix}deck/{by[n]}"
