# Building a scene element (the contract)

An element is one new kind of scene the director can use (`map`, `code`, `versus`, ...). Each lives in its own module under `backend/lambdas/engine/scenes/elements/`, defines `ELEMENTS = [Element(...)]`, and is found automatically. **You never edit a shared file**: no `plan.py`, `scenes/__init__.py`, `timeline.py`, `sync.py`, handlers or prompts. If you think a shared file must change, say so in your final report instead.

## The pieces (all in `scenes/registry.py`)
`Element(name, family, doc, sanitize, draw, cues, samples, anchors=None, prepare=None, fallback=None, max_per_video=None, min_seconds=0)`

- **name**: the scene type, `lower_snake_case`, not one of the built-ins (title, bullets, diagram, chart, timeline, stat, quote, image, clip, gallery).
- **family**: one of `Text`, `Lists`, `Compare`, `Data`, `Process`, `Maps`, `Code and math`, `People and sources`, `Media`.
- **doc**: what the *director model* reads. One to three lines, starting `- name: {props with limits}. When to use. Never when.` Look at `SCENE_DOCS_BASE` in `plan.py` for the style: terse, with character limits, with a "never invent" rule wherever facts or numbers appear. The director gives **meaning, never layout**: items, places, numbers, steps; never pixels, colours or coordinates.
- **sanitize(props) -> clean props**: the only gate for what the model sends. Clip every string (`plan._s(x, n)` exists but import it lazily or reimplement a tiny helper; do not import `plan` at module top, it imports the registry), cap list lengths, coerce numbers, drop unknown keys, and **raise `ValueError` when the scene is unusable** (the beat then becomes a title card). It must be **idempotent**: `sanitize(sanitize(x)) == sanitize(x)`, and an empty `{}` must raise.
- **draw(cv, props, lt, dur, theme, ctx)**: draw one frame, `lt` seconds into a scene `dur` long, on `engine.canvas.Canvas` (logical 1920x1080, Pillow with 2x supersampling). Study `scenes/text_scenes.py` and `scenes/viz_scenes.py` and the helpers in `scenes/base.py` (`heading`, `CONTENT_TOP`, `ctx.bottom`) and `easing.py` (`progress`, `ease_out_cubic`, `reveal_times`). Rules: pure function of `(props, lt, dur)` (no randomness without a fixed seed, no clock, no I/O); content stays between `CONTENT_TOP` and `ctx.bottom` (the caption band sits below); use only theme colours (`theme.text`, `theme.muted`, `theme.accent`, ...; the video has three themes and every element must look right on all three); animate in (about 0.5 s per part, staggered), then hold the complete picture; the **end state must be complete and readable** because a scene often holds for many seconds; text must never overflow or overlap (use `cv.fit_text`/`cv.measure`); heavy work (projection, layout, large sprites) belongs in an `lru_cache`d function keyed on the props, not inside the frame loop. A frame must render in well under 0.3 s at 1920x1080.
- **cues(props, dur) -> [seconds]**: when parts appear, used for sound effects (`reveal_times(n, dur, props.get("cues"))`).
- **anchors(props) -> [texts]** (optional): for elements that reveal parts one by one, return the text of each part in order; the engine ties each reveal to the word that names it in the narration and stores the times in `props["cues"]`, which your `draw` should then honour via `reveal_times(n, dur, props.get("cues"))`.
- **prepare(props, ctx: PrepareCtx) -> patch** (optional): runs at the beat stage (a Lambda with network, 1 GB, minutes of time) for elements that need outside data (resolving place names, fetching a headline's details). Return a small JSON-serialisable dict; it is merged into `props` before rendering, so `draw` stays pure and offline. **Raise on failure**: the engine then shows `fallback`. Bound every network call with a timeout and cache what you can. Never put secrets or user data in a request.
- **fallback(props) -> (scene_type, props)** (optional): what to show if `prepare` fails. Default: a title card.
- **max_per_video**: budget for heavy or repetitive elements; extra uses become title cards.
- **samples**: 2+ realistic props, **as the director would send them** (before sanitize), covering a typical and a full/edge case. Tests and the preview use them.

## Quality bar (this is what "good" means here)
1. **It looks designed.** Consistent spacing, one clear focal point, restrained motion, theme-aware colour, readable at phone size (text at least ~44 px logical for body, large for the key element). Compare with the existing scenes by rendering them side by side.
2. **It teaches.** The element exists to make the narration easier to follow; a viewer should grasp it in the time the narrator takes to say it.
3. **It degrades.** Bad or sparse props give a clean smaller version or a clean refusal, never an ugly or empty frame.
4. **It is honest.** Never invent facts, numbers, quotes or sources; show only what the props contain.

## How to work
1. Read the registry, `scenes/text_scenes.py`, `scenes/viz_scenes.py`, `scenes/base.py`, `canvas.py` (what the canvas offers), `tests/test_elements_framework.py`, `tests/element_utils.py`.
2. Create `scenes/elements/<family_or_name>.py` (a module may hold several related elements) and `tests/test_el_<name>.py`.
3. Run `cd backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_el_<yourfile>.py tests/test_elements_framework.py -k "<your element names> or framework"`. The generic tests check the contract automatically for every registered element (idempotent sanitize, draws on all themes, something visible, survives hostile props). Add your own tests for what is specific: limits, edge cases, `anchors`, `prepare` with a fake network, the end state containing every item.
4. **Look at it**: `../.venv/bin/python scripts/element_preview.py <names> --theme midnight --out /tmp/<name>-midnight.png` (also `paper`, `sunrise`), then open the PNG and fix what is wrong. Do this for every element before you report.
5. Do **not** run the whole test suite (it takes minutes and other people's work is in progress), do not commit, do not deploy, do not touch git. Do not edit files you did not create.
6. Final report: per element, one line of what it does and its props; anything that needs a shared-file change; anything you could not do and why; the path of your preview sheets.

## Formats (vertical, square, 4:5)
New and converted elements lay out in design units from `ctx.frame` and tag `formats=(...)`; until then they render in a framed fallback. Read `docs/RESPONSIVE_LAYOUT.md` before writing `draw`.
