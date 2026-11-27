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

from . import bg_animated, bg_loops

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

# The pre-rendered 3D loops (engine/bg_loops.py, docs/HERO_LOOPS_3D.md; flag BG_LOOPS): the premium look. Which loop palettes sit well under each theme's text and
# card colours (the loop's light/dark mode must also equal the theme's: it decides the text colour).
LOOP_PALETTES: Dict[str, Tuple[str, ...]] = {"midnight": ("brand", "aurora"), "sunrise": ("ember",), "paper": ("brand",)}
# Scenes that are read, not watched: when they make up half of a video or more a moving background distracts, so the video keeps the static look.
DATA_SCENES = frozenset({"chart", "area", "bar_race", "pie", "scatter", "stacked", "table", "matrix", "funnel", "pictogram", "ranking", "scale_compare", "map", "code", "equation"})
DATA_HEAVY_SHARE = 0.5

LOOPS_MENU = """
Premium 3D loops (pre-rendered volumetric gas, the best-looking backgrounds we have). Prefer one of these whenever its mood fits the topic; answer "none" only when none fits and a style above is clearly closer:
{loops}
Answer with ONLY this JSON: {{"style": "<one style>", "palette": "<one palette>", "loop": "<one loop id, or none>"}}"""

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


# ---------------------------------------------------------------- a wish stated in the request ("with a purple 3D background", "fondo fijo")
# The person can ask for a background in plain words, the way "make it a cartoon" asks for cartoon scenes (engine/vector_policy.py). A stated wish wins over the
# mood and over the data-heavy rule; it never applies to a video of the person's own photos. Only phrases that name the BACKGROUND count ("a video about smoke" does not).
_BG = r"(?:background|backdrop|fondo)"
_NONE_RE = re.compile(
    r"\bno\s+(?:moving|animated|3[\s-]?d|motion)\s+(?:background|backdrop)|\bwithout\s+(?:a\s+|an\s+)?(?:moving|animated|3[\s-]?d)\s+(?:background|backdrop)"
    r"|\b(?:still|static|plain|fixed|simple)\s+(?:background|backdrop)|\bno\s+background\s+(?:animation|motion|movement)"
    r"|\bfondo\s+(?:fijo|est[aá]tico|quieto|liso|sin\s+movimiento|sin\s+animaci[oó]n)|\bsin\s+fondo\s+(?:animado|3[\s-]?d|en\s+movimiento|en\s+3[\s-]?d)", re.I)
_3D_RE = re.compile(
    r"\b3[\s-]?d\b[^.\n]{0,30}\b(?:background|backdrop)|\b(?:background|backdrop)\b[^.\n]{0,20}\b3[\s-]?d\b|\bfondo\b[^.\n]{0,25}\b3[\s-]?d\b|\b3[\s-]?d\b[^.\n]{0,15}\bfondo\b"
    r"|\bfondo\s+tridimensional", re.I)
_ANIM_RE = re.compile(
    r"\b(?:animated|moving|motion|live|smoke|smoky|gas|nebula|flowing)\s+(?:background|backdrop)|\b(?:background|backdrop)\s+(?:that\s+moves|animation|in\s+motion)"
    r"|\bfondo\s+(?:animado|en\s+movimiento|con\s+movimiento|de\s+humo|de\s+gas|que\s+se\s+mueve)", re.I)
_COLOUR_BG_RE = re.compile(r"\b([a-záéíóúñü]+)\s+(?:3[\s-]?d\s+)?(?:smoke\s+|gas\s+|animated\s+)?(?:background|backdrop)\b|\bfondo\s+(?:3[\s-]?d\s+|animado\s+|en\s+3[\s-]?d\s+|de\s+humo\s+)?(?:de\s+color\s+|en\s+|color\s+)?([a-záéíóúñü]+)", re.I)
# colour and mood words -> the look they mean: (loop palette, light/dark mode, the theme that carries it, the procedural palette nearest to it)
WISH_LOOKS: Dict[str, Tuple[str, str, str, str]] = {"brand": ("brand", "dark", "midnight", "violet"), "ember": ("ember", "dark", "sunrise", "ember"),
                                                     "aurora": ("aurora", "dark", "midnight", "forest"), "light": ("brand", "light", "paper", "violet")}
WISH_WORDS: Dict[str, Tuple[str, ...]] = {
    "brand": ("purple", "violet", "blue", "indigo", "brand", "morado", "morada", "violeta", "azul", "púrpura", "purpura", "lila"),
    "ember": ("warm", "orange", "fire", "fiery", "ember", "embers", "red", "amber", "cálido", "calido", "cálida", "calida", "naranja", "fuego", "brasas", "rojo", "ámbar", "ambar"),
    "aurora": ("green", "teal", "aurora", "turquoise", "emerald", "verde", "turquesa", "esmeralda"),
    "light": ("light", "white", "bright", "pale", "claro", "clara", "blanco", "blanca", "luminoso", "luminosa"),
}


def request_wish(prompt: Any) -> Optional[Dict[str, Any]]:
    """What the request text says about the background, or None when it says nothing: {"kind": "none"} (no moving background), {"kind": "animated"} (a moving one,
    whichever), {"kind": "loop"} (a 3D one), each with an optional "look" (brand, ember, aurora, light) when a colour or mood word sits right at the word background."""
    text = " ".join(str(prompt or "").split())
    if not text or not re.search(_BG, text, re.I):
        return None
    if _NONE_RE.search(text):
        return {"kind": "none"}
    look = None
    for m in _COLOUR_BG_RE.finditer(text):
        word = (m.group(1) or m.group(2) or "").lower()
        look = next((k for k, words in WISH_WORDS.items() if word in words), None)
        if look:
            break
    three_d = bool(_3D_RE.search(text))
    if not (three_d or look or _ANIM_RE.search(text)):
        return None
    return {"kind": "loop" if three_d or look else "animated", **({"look": look} if look else {})}


def wish_theme(wish: Optional[Dict[str, Any]]) -> Optional[str]:
    """The theme a wished look needs (a light background means the paper theme, a warm one sunrise); None when the wish names no look."""
    look = (wish or {}).get("look")
    return WISH_LOOKS[look][2] if look in WISH_LOOKS else None


def enabled() -> bool:
    return os.environ.get("BG_ANIMATED", "0") == "1" or loops_enabled()


def loops_enabled() -> bool:
    return os.environ.get("BG_LOOPS", "0") == "1"


def loop_fits(spec: Any, theme: str) -> bool:
    """True when this loop may sit behind this theme: same light/dark mode (the text colour) and a palette that suits the theme's cards and accents."""
    return isinstance(spec, bg_loops.LoopSpec) and spec.mode == mode_of(theme) and spec.palette in LOOP_PALETTES.get(theme, ())


def loops_for(theme: str, loops: Any) -> list:
    return [lp for lp in (loops or []) if loop_fits(lp, theme)]


def data_heavy(plan: Dict[str, Any]) -> bool:
    """Half or more of the beats are charts, tables, maps or code: the viewer is reading values, and a moving background would compete with them."""
    beats = [b for b in (plan.get("beats") or []) if isinstance(b, dict)]
    if not beats:
        return False
    n = sum(1 for b in beats if isinstance(b.get("scene"), dict) and b["scene"].get("type") in DATA_SCENES)
    return n / len(beats) >= DATA_HEAVY_SHARE


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


def choose(prompt: str, plan: Dict[str, Any], ask: Optional[Callable[[str, str], str]] = None, loops: Any = None, wish: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The `background` entry of a plan: {style, palette, mode, speed, intensity, seed, loop_seconds, by} and, when a pre-rendered loop was chosen (only from `loops`,
    the index entries; pass them only with BG_LOOPS on), also {loop, loop_palette} with loop_seconds = the loop's own length. The procedural style is always there too:
    it is what plays if the loop cannot be used. Never raises; `by` says who chose ('director' or 'mood')."""
    theme = plan.get("theme") if plan.get("theme") in THEME_PALETTES else "midnight"
    mood = plan.get("mood") if plan.get("mood") in MOOD_STYLE else "calm"
    menu = loops_for(theme, loops)
    asked = wish if isinstance(wish, dict) and wish.get("kind") in ("loop", "animated") else None   # what the request text asked for (request_wish): it wins over the mood
    look = WISH_LOOKS.get(asked.get("look")) if asked else None
    if asked and (look or asked["kind"] == "loop"):   # a look or "3D" was named: settled here, no model call
        pool = [lp for lp in menu if not look or (lp.palette, lp.mode) == look[:2]]
        spec = next((lp for lp in pool if mood in lp.mood), pool[0] if pool else None)
        style, palette = settle("gas", look[3] if look else None, mood, theme)   # the procedural stand-in (also what plays where the loops are switched off): gas in the nearest palette
        seed = zlib.crc32(str(plan.get("title") or prompt or "").encode("utf-8")) % 9973 + 1
        out = {"style": style, "palette": palette, "mode": mode_of(theme), "speed": MOOD_SPEED[mood], "intensity": INTENSITY, "seed": seed, "loop_seconds": LOOP_SECONDS, "by": "request"}
        if spec is not None:
            out.update(loop=spec.id, loop_palette=spec.palette, loop_seconds=min(20.0, max(6.0, float(spec.seconds))))
        return out
    wish: Dict[str, Any] = {}
    if ask is not None:
        try:
            user = f"Request: {str(prompt or '')[:400]}\nTitle: {str(plan.get('title') or '')[:80]}\nMood: {mood}\nTheme: {theme}"
            system = SYSTEM.format(palettes=", ".join(THEME_PALETTES[theme]))
            if menu:   # the JSON line of the plain menu is replaced by the one that also asks for a loop
                system = system.rsplit("\n", 1)[0] + LOOPS_MENU.format(loops=bg_loops.prompt_list(menu))
            wish = _parse(ask(system, user))
        except Exception as e:  # noqa: BLE001 - a background is never worth a failed video
            log.warning("BACKGROUND_CHOICE_FAILED %s", type(e).__name__)
            wish = {}
    answered = str(wish.get("style") or "").strip().lower() in STYLES
    spec = bg_loops.sanitize(str(wish.get("loop") or "").strip().lower(), menu) if menu else None
    if ask is not None and not answered and spec is None:
        log.warning("BACKGROUND_CHOICE_UNUSABLE keys=%s", sorted(wish)[:4])   # never the text itself
    by = "director" if answered or spec is not None else "mood"
    if menu and spec is None and by == "mood":   # no usable answer: the loop whose tags name the video's mood, if there is one (else the procedural style of the mood)
        spec = next((lp for lp in menu if mood in lp.mood), None)
    style, palette = settle(wish.get("style"), wish.get("palette"), mood, theme)
    seed = zlib.crc32(str(plan.get("title") or prompt or "").encode("utf-8")) % 9973 + 1
    out = {"style": style, "palette": palette, "mode": mode_of(theme), "speed": MOOD_SPEED[mood], "intensity": INTENSITY, "seed": seed, "loop_seconds": LOOP_SECONDS, "by": by}
    if spec is not None:
        out.update(loop=spec.id, loop_palette=spec.palette, loop_seconds=min(20.0, max(6.0, float(spec.seconds))))
    return out


def retheme(background: Dict[str, Any], theme: str, mood: str = "calm") -> Dict[str, Any]:
    """The background after the video's theme changed (an edit): the procedural style moves to a palette of the new theme, and a pre-rendered loop is kept only if it
    still fits (same light/dark mode, a palette of the theme); otherwise it is dropped and the procedural style plays."""
    st, pal = settle(background.get("style"), None, mood, theme)
    new = {**background, "style": st, "palette": pal, "mode": mode_of(theme)}
    if "loop" in new and (background.get("mode") != new["mode"] or new.get("loop_palette") not in LOOP_PALETTES.get(theme, ())):
        new.pop("loop", None)
        new.pop("loop_palette", None)
        new["loop_seconds"] = LOOP_SECONDS
    return new


def phase(start: float, background: Dict[str, Any]) -> float:
    """Where in its loop the background is when a scene starts, so it flows on from scene to scene instead of jumping (the loop is exact, so only the time within it matters)."""
    try:
        loop = float(background.get("loop_seconds") or LOOP_SECONDS)
    except (TypeError, ValueError):
        loop = LOOP_SECONDS
    loop = min(20.0, max(6.0, loop))
    return round(float(start) % loop, 3)
