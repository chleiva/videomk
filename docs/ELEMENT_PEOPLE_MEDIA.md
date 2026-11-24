# People and sources, Media: `headline`, `dialogue`, `icons`, `annotated_image`

Code: `backend/lambdas/engine/scenes/elements/people_media.py` (+ `_pm_text.py`, `_pm_icons.py`, `_pm_vision.py`). Tests: `backend/tests/test_el_people_media.py`.

## Bundled assets (all under 3 MB)
| File (in `backend/lambdas/engine/assets/`) | What | Licence | Source |
|---|---|---|---|
| `icons/lucide.ttf` (1.0 MB) | Lucide icon font, 2,436 icons, drawn as text glyphs by Pillow (no SVG renderer) | ISC (some icons MIT, Feather) | npm `lucide-static` 1.79.0, `font/lucide.ttf`; licence in `icons/LUCIDE-LICENSE.txt` |
| `icons/lucide_index.json` (0.4 MB) | Generated: icon name -> [codepoint, tags...] from the package's `font/codepoints.json` and `tags.json` | same | same package |
| `fonts/PlayfairDisplay_700Bold.ttf` (0.2 MB) | Serif face for headline cards | SIL OFL 1.1 | npm `@expo-google-fonts/playfair-display`; licence in `fonts/PlayfairDisplay-OFL-LICENSE.txt` |

## headline
Real news headlines only. `prepare` keeps a headline only if, for one cited source (`ctx.sources`): the outlet equals/contains the source's publisher or URL domain (case-insensitive, ignoring "The ", dots, `bbc.co.uk` ~ `BBC News`, `NYT` ~ `nytimes.com`); at least 3 content words are shared; at least 75% of the headline's content words are in the source title (it cannot add claims) and at least 50% of the title's content words are in the headline (it cannot cherry-pick a fragment); every number in the headline is in the title; and the years agree when the source carries a date. A headline over 140 characters is dropped, never shortened. If none survive, `prepare` raises and the beat falls back to a title card. The credit line shows the verified source's domain.

## dialogue
2-6 turns, 2-3 distinct speakers (a fourth voice is dropped, one voice is refused). Speaker side and colour are fixed per speaker (accent, accent2, a hue shift of accent); text is trimmed on a word boundary with an ellipsis; typing dots show just before each bubble; if even the smallest text cannot fit, the chat scrolls.

## icons
`find_icon(word)`: exact name, curated synonym, tag equal to the word, name token, fuzzy name, fuzzy tag, then `sparkles` (never an error).

## annotated_image
`prepare` fetches the photograph with `beat_handler.make_photo` (same search, review, credit, Unsplash tracking as an image scene), then asks the small vision model (`llm.REVIEW_MODEL`) twice (plain picture, and picture with a labelled 10% grid) where each label is. A pin is kept only if both looks say visible, agree within 0.15, each pin lies in its own box, the box is not most of the picture, and it does not sit on another pin. If nothing survives, the patch carries the photo with `pins: []` and the scene draws as a plain image. Not yet run against a live model (tests use a fake).
