from dataclasses import dataclass
from typing import Dict, Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    name: str
    bg_top: RGB
    bg_bottom: RGB
    text: RGB
    muted: RGB
    accent: RGB
    accent2: RGB
    card: Tuple[int, int, int, int]       # RGBA fill for cards
    card_outline: Tuple[int, int, int, int]
    shadow_alpha: float
    caption_bg: Tuple[int, int, int, int]
    caption_text: RGB


THEMES: Dict[str, Theme] = {
    "midnight": Theme(
        "midnight", (10, 14, 32), (30, 27, 75), (248, 250, 252), (148, 163, 184), (99, 102, 241), (34, 211, 238),
        (255, 255, 255, 20), (255, 255, 255, 46), 0.45, (8, 10, 24, 205), (255, 255, 255),
    ),
    "paper": Theme(
        "paper", (251, 248, 243), (238, 230, 218), (31, 41, 55), (107, 114, 128), (225, 29, 72), (37, 99, 235),
        (255, 255, 255, 235), (31, 41, 55, 28), 0.16, (31, 41, 55, 225), (255, 255, 255),
    ),
    "sunrise": Theme(
        "sunrise", (28, 16, 66), (122, 31, 92), (255, 247, 237), (253, 186, 116), (251, 146, 60), (253, 224, 71),
        (255, 255, 255, 24), (255, 255, 255, 50), 0.45, (22, 10, 48, 210), (255, 255, 255),
    ),
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name or "", THEMES["midnight"])
