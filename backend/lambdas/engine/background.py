"""The director's choice of the moving background behind the drawn scenes (docs/BACKGROUNDS_ANIMATED.md; owner decision 2026-11-27: the director picks it by the topic's mood).

One background for the whole video (a change per scene would pop). Off unless BG_ANIMATED=1 (QA only for now): with the flag off nothing here runs and the plan, the
timeline and every frame are exactly what they always were.

How it is chosen:
  1. one small-model call reads the request, the title and the mood the writer gave the video, and picks a style (and optionally a palette) from the menu below;
  2. the answer is checked against what is allowed: the palette must suit the video's theme (the text and the cards keep the theme's colours), and the combinations that
     look muddy are never used (mesh and lava on the warm palettes, mesh in light mode: seen on the sample sheet of every style and palette);
  3. if the call fails or answers nonsense, the mood decides (calm: aurora or gas; bright: bokeh; tense: smoke), so a video never waits on this and never fails on it.
Videos made of the person's own photos keep today's backdrop (the photographs are the picture).
"""
import json
import logging
import os
import re
import zlib
from typing import Any, Callable, Dict, Optional, Tuple

from . import bg_animated

log = logging.getLogger(__name__)

STYLES: Tuple[str, ...] = ("gas", "smoke", "aurora", "bokeh", "mesh", "lava")
WARM = ("sunrise", "ember")
# the palettes that sit well under each theme's text and card colours; the first is the theme's own
THEME_PALETTES: Dict[str, Tuple[str, ...]] = {
    "midnight": ("midnight", "ocean", "violet", "forest", "mono"),
    "sunrise": ("sunrise", "ember", "violet"),
    "paper": ("violet", "ocean", "forest", "midnight", "mono"),   # light mode: pastel versions
}
MOOD_STYLE = {"calm": "aurora", "bright": "bokeh", "tense": "smoke"}
MOOD_SPEED = {"calm": 0.7, "bright": 1.0, "tense": 1.15}
LOOP_SECONDS = 12.0
INTENSITY = 0.8   # a little under the showreel's 1.0: in the first real 4K video the smoke's ribbons were bright enough to compete with a diagram

SYSTEM = """You choose the moving background that sits quietly behind the text scenes of a short explainer video. Pick by the MOOD of the topic, not by its literal subject.
Styles:
- gas: slow satin nebula. Calm science, space, technology, AI, ideas.
- aurora: curtains of light across the top. Nature, weather, oceans, wonder, travel.
- smoke: dark with thin drifting wisps. Serious, news, finance, law, history's hard chapters, tense stories.
- bokeh: soft floating discs. Lists, how-to, tips, lifestyle, wellness, kids, friendly explainers.
- mesh: broad soft colour fields. Design, product, business, modern tech.
- lava: glowing blobs that merge and split. Energy, sport, music, bold or playful topics.
Palettes: {palettes}. Use the first unless the topic clearly belongs to another (ocean for water and sky, forest for plants and animals, mono for sober or serious, violet for creative, ember for fire and heat).
Answer with ONLY this JSON: {{"style": "<one style>", "palette": "<one palette>"}}"""


def enabled() -> bool:
    return os.environ.get("BG_ANIMATED", "0") == "1"


def mode_of(theme: str) -> str:
    return "light" if theme == "paper" else "dark"


def allowed(style: str, palette: str, mode: str) -> bool:
    """False for the combinations that look muddy or broken on the sample sheet: mesh and lava on the warm palettes (brown in the quiet middle), mesh in light mode (a dark corner)."""
    if style not in STYLES or palette not in bg_animated.PALETTES:
        return False
    if style in ("mesh", "lava") and palette in WARM:
        return False
    if style == "mesh" and mode == "light":
        return False
    return True


def fallback_style(mood: str, theme: str) -> str:
    style = MOOD_STYLE.get(mood, "gas")
    return style if allowed(style, THEME_PALETTES.get(theme, THEME_PALETTES["midnight"])[0], mode_of(theme)) else "gas"


def _parse(text: Any) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def settle(style: Any, palette: Any, mood: str, theme: str) -> Tuple[str, str]:
    """The (style, palette) really used: the wish when it is allowed for this theme, else the nearest allowed thing (the wished style with the theme's palette, then the mood's style)."""
    theme = theme if theme in THEME_PALETTES else "midnight"
    pals, mode = THEME_PALETTES[theme], mode_of(theme)
    style = str(style or "").strip().lower()
    palette = str(palette or "").strip().lower()
    if style not in STYLES:
        style = fallback_style(mood, theme)
    cands = ([palette] if palette in pals else []) + [p for p in pals if p != palette]
    for p in cands:
        if allowed(style, p, mode):
            return style, p
    style = fallback_style(mood, theme)   # e.g. mesh under the sunrise theme: no palette of that theme carries it
    for p in pals:
        if allowed(style, p, mode):
            return style, p
    return "gas", pals[0]


def choose(prompt: str, plan: Dict[str, Any], ask: Optional[Callable[[str, str], str]] = None) -> Dict[str, Any]:
    """The `background` entry of a plan: {style, palette, mode, speed, intensity, seed, loop_seconds, by}. Never raises; `by` says who chose ('director' or 'mood')."""
    theme = plan.get("theme") if plan.get("theme") in THEME_PALETTES else "midnight"
    mood = plan.get("mood") if plan.get("mood") in MOOD_STYLE else "calm"
    wish: Dict[str, Any] = {}
    if ask is not None:
        try:
            user = f"Request: {str(prompt or '')[:400]}\nTitle: {str(plan.get('title') or '')[:80]}\nMood: {mood}\nTheme: {theme}"
            wish = _parse(ask(SYSTEM.format(palettes=", ".join(THEME_PALETTES[theme])), user))
        except Exception as e:  # noqa: BLE001 - a background is never worth a failed video
            log.warning("BACKGROUND_CHOICE_FAILED %s", type(e).__name__)
            wish = {}
    if ask is not None and str(wish.get("style") or "").strip().lower() not in STYLES:
        log.warning("BACKGROUND_CHOICE_UNUSABLE keys=%s", sorted(wish)[:4])   # never the text itself
    by = "director" if str(wish.get("style") or "").strip().lower() in STYLES else "mood"
    style, palette = settle(wish.get("style"), wish.get("palette"), mood, theme)
    seed = zlib.crc32(str(plan.get("title") or prompt or "").encode("utf-8")) % 9973 + 1
    return {"style": style, "palette": palette, "mode": mode_of(theme), "speed": MOOD_SPEED[mood], "intensity": INTENSITY, "seed": seed, "loop_seconds": LOOP_SECONDS, "by": by}


def phase(start: float, background: Dict[str, Any]) -> float:
    """Where in its loop the background is when a scene starts, so it flows on from scene to scene instead of jumping (the loop is exact, so only the time within it matters)."""
    try:
        loop = float(background.get("loop_seconds") or LOOP_SECONDS)
    except (TypeError, ValueError):
        loop = LOOP_SECONDS
    loop = min(20.0, max(6.0, loop))
    return round(float(start) % loop, 3)
