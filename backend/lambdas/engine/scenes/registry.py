"""The element registry: one self-contained module per scene type.

An element is everything the engine needs to know about one kind of scene: what the director is told (`doc`), how the director's props are cleaned (`sanitize`),
how it is drawn (`draw`) and when its parts appear (`cues`, `anchors`), and, when it needs outside data, how that is fetched at the beat stage (`prepare`)
and what to show if that fails (`fallback`). Modules in `scenes/elements/` define `ELEMENTS = [Element(...), ...]`; they are found automatically (see `load_all`),
so adding an element never touches a shared file. The contract is in docs/ELEMENT_BUILD_GUIDE.md.
"""
import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Props = Dict[str, Any]


@dataclass
class PrepareCtx:
    """What the beat stage hands to `Element.prepare`."""

    video_id: str
    beat_id: str
    narration: str              # what is said over this scene
    duration: float             # seconds of speech of this beat
    sources: List[Dict[str, Any]] = field(default_factory=list)   # the plan's cited sources (title, url, publisher): the only place a news headline may come from
    language: str = "en"
    region: Optional[str] = None
    media_items: List[Dict[str, Any]] = field(default_factory=list)   # the user's own photos of this video: {id, key, w, h, orientation, caption, taken, where}; their clean copies are ready in storage


@dataclass
class Element:
    name: str                                   # the scene type, lower_snake_case, unique
    family: str                                 # heading in the director's prompt: Text, Lists, Compare, Data, Process, Maps, Code and math, People and sources, Media
    doc: str                                    # director-facing: `- name: {props with limits}. When to use. Never when.` (one to three lines)
    sanitize: Callable[[Props], Props]          # director props -> clean props; raise ValueError when unusable (the beat then falls back to a title card)
    draw: Callable[..., None]                   # draw(cv, props, lt, dur, theme, ctx) like the built-in scenes
    cues: Callable[[Props, float], List[float]] # reveal times in seconds (for sound effects), like the built-in scenes
    samples: List[Props]                        # 2+ realistic props (as the director would send them) used by tests and the preview sheet
    anchors: Optional[Callable[[Props], List[str]]] = None       # texts whose reveal times are tied to the words that name them; result lands in props["cues"]
    prepare: Optional[Callable[[Props, PrepareCtx], Props]] = None   # beat stage: fetch or compute data; returns a patch merged into props (JSON, small); raise to fall back
    fallback: Optional[Callable[[Props], Tuple[str, Props]]] = None  # (stype, props) to show instead when prepare fails; default is a title card
    max_per_video: Optional[int] = None         # budget for heavy elements; extra uses become title cards
    min_seconds: float = 0.0                    # shortest sensible scene length


ELEMENTS: Dict[str, Element] = {}
FAILED: Dict[str, str] = {}      # module name -> error, for modules that could not be imported (a test asserts this stays empty)


def register(el: Element) -> Element:
    if not el.name or not el.name.replace("_", "").isalnum() or el.name != el.name.lower():
        raise ValueError(f"bad element name {el.name!r}")
    ELEMENTS[el.name] = el
    return el


def load_all() -> None:
    """Import every module in scenes/elements/ and register its ELEMENTS. A module that fails to import is recorded in FAILED, never raised: one broken element
    must not take the video engine down."""
    from . import elements as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{pkg.__name__}.{mod.name}")
            for el in getattr(m, "ELEMENTS", []):
                register(el)
        except Exception as e:  # noqa: BLE001
            logging.exception("element module %s failed to load", mod.name)
            FAILED[mod.name] = f"{type(e).__name__}: {e}"


def docs_by_family() -> str:
    """The elements' director-facing docs, grouped under their family headings, in a stable order."""
    fams: Dict[str, List[Element]] = {}
    for el in ELEMENTS.values():
        fams.setdefault(el.family, []).append(el)
    lines: List[str] = []
    for fam in sorted(fams):
        lines.append(f"  [{fam}]")
        lines += [el.doc.rstrip() for el in sorted(fams[fam], key=lambda e: e.name)]
    return "\n".join(lines)
