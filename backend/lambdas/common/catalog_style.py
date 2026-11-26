"""The catalog's house style and composition rules (docs/IMAGE_CATALOG.md). One place, so every image of the library is made the same way and looks like one product."""
from typing import Dict, List

STYLE_VERSION = "house-v1"

HOUSE_STYLE = (
    "Editorial documentary photograph, natural light, shot on a full-frame camera with a 35mm lens, gentle film-like colour grade with slightly muted, warm and "
    "natural colours, fine detail, shallow to medium depth of field, clean uncluttered composition, calm and optimistic mood."
)
COMPOSITION = (
    "Wide 16:9 landscape frame. The main subject sits in the middle third of the frame with generous space on both sides, so a vertical 9:16 crop or a square crop of "
    "the centre still shows the whole subject. The bottom quarter of the frame is calm, low-detail and slightly darker (sky, water, grass, floor, soft shadow) so white "
    "captions stay readable on top of it. Nothing important touches the left or right edge."
)
NO_PEOPLE = "Any people are small, seen from behind, in silhouette or as hands only: no face is visible and nobody is recognisable."
NEGATIVE = (
    "text, letters, words, numbers, captions, logos, brand names, trademarks, watermark, signature, signs with writing, screen content with readable text, "
    "recognisable person, face close-up, celebrity, deformed hands, extra fingers, distorted anatomy, warped objects, duplicated objects, cartoon, 3d render, "
    "oversaturated, HDR halo, blurry, low quality, jpeg artefacts, frame, border"
)

CATEGORIES = ("nature", "sky", "work", "city", "food", "people", "animals", "science", "money", "history", "travel", "mood")


def full_prompt(subject: str, people: bool = False) -> str:
    """The prompt sent to the image model for a catalog subject."""
    return f"{subject.strip().rstrip('.')}. {HOUSE_STYLE} {COMPOSITION}" + (f" {NO_PEOPLE}" if people else "")


# crop rules: the share of the 16:9 frame's width that survives, always centred
CROPS: Dict[str, float] = {"16:9": 1.0, "9:16": (9 / 16) / (16 / 9), "1:1": 9 / 16, "4:5": (4 / 5) / (16 / 9)}


def crop_box(width: int, height: int, aspect: str) -> List[int]:
    """(left, top, right, bottom) of the centred crop of a wide image for an aspect such as '9:16' (the whole image when the aspect is unknown or already narrower)."""
    try:
        a, b = (int(x) for x in aspect.split(":"))
        target = a / b
    except (ValueError, AttributeError, ZeroDivisionError):
        return [0, 0, width, height]
    if width / height <= target:
        return [0, 0, width, height]
    w = int(round(height * target))
    left = (width - w) // 2
    return [left, 0, left + w, height]
