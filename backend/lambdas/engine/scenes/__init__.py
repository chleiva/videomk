from typing import Any, Callable, Dict, List, Tuple

from .text_scenes import (
    bullets_cues, draw_bullets, draw_quote, draw_stat, draw_title, quote_cues, stat_cues, title_cues,
)
from .viz_scenes import (
    chart_cues, clip_cues, diagram_cues, draw_chart, draw_clip, draw_diagram, draw_gallery, draw_image, gallery_cues, draw_timeline, image_cues, timeline_cues,
)

# type -> (draw(cv, props, lt, dur, theme, ctx), cues(props, dur) -> reveal times for SFX)
SCENES: Dict[str, Tuple[Callable[..., None], Callable[[Dict[str, Any], float], List[float]]]] = {
    "title": (draw_title, title_cues),
    "bullets": (draw_bullets, bullets_cues),
    "diagram": (draw_diagram, diagram_cues),
    "chart": (draw_chart, chart_cues),
    "timeline": (draw_timeline, timeline_cues),
    "stat": (draw_stat, stat_cues),
    "quote": (draw_quote, quote_cues),
    "image": (draw_image, image_cues),
    "clip": (draw_clip, clip_cues),
    "gallery": (draw_gallery, gallery_cues),
}

SCENE_TYPES = tuple(SCENES)
