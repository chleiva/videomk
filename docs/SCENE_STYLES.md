# Scene styles: the `bullets` list and the `diagram` flow

The two oldest scenes looked like office slides (white rows with a red badge, three boxes joined by thin arrows, half the frame empty). They now have several
looks the director chooses per scene, a colour control, and motion that follows the narration. Old plans render unchanged in props and timing; they just look better.

Code: `engine/scenes/style_kit.py` (palettes, sprites, backdrop, motion, prop cleaning), `scenes/list_scenes.py` (lists), `scenes/flow_scenes.py` (flows).
`draw_bullets` / `draw_diagram` in `text_scenes.py` / `viz_scenes.py` delegate to them. Previews: `backend/scripts/scene_styles_preview.py` writes `docs/scene_styles/*.png`.

## Props (all optional; unknown or missing = the default)

| scene | prop | values |
|---|---|---|
| bullets | `style` | `rail` (default), `spotlight`, `icons`, `cards`, `keywords` |
| diagram | `style` | `cards` (default), `pills`, `ladder`, `stack` |
| both | `accent` | `indigo coral teal amber emerald violet rose sky`, or `auto` / missing = the theme's own colour (midnight indigo, paper rose, sunrise amber) |
| both | `emphasis` | index of the key item/node: it stays filled with the accent gradient instead of only lighting while narrated |
| bullets | `icons` | one icon word per item (`"rocket"`, `"money"`, `""` = automatic); resolved to a name of the bundled Lucide set by `find_icon`, dropped if nothing fits |
| diagram | `nodes[].icon` | the same, per node |

`plan.sanitize_props` keeps only these (style/accent from the allowed lists, lower-cased; emphasis a non-bool int in range; icons resolved and bounded) and drops
everything else, so a model cannot inject colours, sizes or paths. A flow style sent to a list (or the reverse) is dropped. Props are idempotent under sanitising.
The director docs (`SCENE_DOCS`, the `- bullets:` / `- diagram:` lines, 722 and 677 characters) name each style, each accent with a topic hint, and require
matching style and accent to the topic and varying them (a line in `skills/listicle-ranking.md` repeats it).

## Styles

Lists (`bullets`):
- `rail` (default): numbered gradient discs on a rail that draws down to each new item, large type, a ghost numeral on the right that follows the voice. General purpose.
- `spotlight`: huge two-digit index and bold type; a soft light moves to the item being narrated, the others dim to about half. Claims, mottos, a few strong statements.
- `icons`: full-width glass rows with a tinted icon tile (icon chosen from the words, or `icons`). Features, benefits, tips.
- `cards`: glass cards in a grid (2 to 5 wide; the second column sits a little lower), icon tile, number, text. Parallel ideas.
- `keywords`: a big accent keyword, a divider and a lighter explanation; write items as `Keyword: explanation` (a dash also splits; a phrase of 3 words or fewer stays whole). Principles, definitions.

Flows (`diagram`): one layered layout (the old longest-path layering, so `sync.diagram_order` still names the reveal order), four node looks.
- `cards` (default): rounded glass cards, icon tile on top, label centred. For 3 to 4 steps with short labels. More than 4 layers wrap into a two-row snake (the second row runs right to left).
- `pills`: capsules with an icon disc; light and quick, for short steps.
- `ladder`: nodes rise step by step; progress, growth, levels.
- `stack`: top to bottom, wide rows; long labels, hierarchy, chains of up to 5 layers (6 or more fall back to `cards`).
Connectors are smooth curves that draw on toward each new node (starting just before it appears), land with an arrowhead that bounces in, and then carry a slow
travelling pulse; edge labels sit on the line as small chips; a backward edge loops under (or beside) the nodes; branches fan out as S-curves.

## What every look does
- **Follows the voice.** The item whose reveal time (`props["cues"]`, written by `sync.apply`) is the latest is lit (colour, glow, small scale); when the next one arrives it settles back
  (type stays at 66 to 100 percent opacity, never invisible). The last one stays lit. `emphasis` keeps one filled.
- **Springs, not slides.** Each part fades in and overshoots slightly (ease-out-back) while rising 30 to 60 px; sprites are cached and only scaled and faded per frame.
- **Never empty.** Slots (cards, rows, flow nodes and their connectors) are drawn as faint ghosts before their reveal, the heading is always there, and the first part is
  clamped to appear by 1.0 s even when the narrator reaches it late (the same rule as `sync.FIRST_REVEAL_S`; later parts keep their cues). The last frame shows everything.
- **Uses the frame.** The block is centred in the band between heading and caption line (`ctx.bottom`), type is 2 to 3 times larger than before (list 44 to 92 px, flow
  30 to 60 px), minimum 30 px, one common size per scene. Everything stays inside x 150 to 1770 and above the caption band (tested).
- **Quiet depth.** A faint dot grid drifts 3 px per second (integer offsets, no shimmer), soft shadows, an accent glow under the lit item.

## Colour
`style_kit.palette` derives, per theme and accent: a fill gradient (`c1`, `c2`) with a text colour on it, an accent for text and icons on the plain background,
the glass surface, border and track colours. Checked (tests): accent text is at least 4.5:1 on the lightest/darkest background of each theme, ink on both gradient
ends is at least 4.6:1 (white ink if at most about 30 percent darkening makes it read, else dark ink with the fill lightened), body text 7:1 or better.
Teal, amber, emerald and sky therefore get dark ink on their tiles; indigo, violet, rose and coral get white.
Previews of all accents on all themes: `docs/scene_styles/bullets-accents.png`, `diagram-accents.png`.

## Previews (docs/scene_styles/)
`before-after.png` (the two screenshots' content, old on the left), `bullets-{rail,spotlight,icons,cards,keywords}.png` and `diagram-{cards,pills,ladder,stack}.png`
(midnight/indigo, paper/rose, sunrise/amber; start, mid-reveal, end), `*-accents.png`, `diagram-long.png` (7 nodes wrap into a snake).
Regenerate: `cd backend && ../.venv/bin/python scripts/scene_styles_preview.py`.

## Performance
Measured at 1920x1080 with 2x supersampling (full quality), per frame, five items or four nodes, midnight and paper: lists 0.055 to 0.09 s, flows 0.06 to 0.13 s
(worst frame of eight sampled; the old scenes were about 0.04 to 0.06 s). Static layers are cached: gradient sprites by size and colour, blurred shadows at full
strength (alpha scales the pasted mask), the dot-grid mask once per size.

## Research (what was learned, and what was adopted)
- **Material motion** ([choreography](https://m1.material.io/motion/choreography.html), [duration and easing](https://m1.material.io/motion/duration-easing.html)):
  stagger entrances without waiting for each to finish, ease out for arrivals, keep individual moves short (about 200 to 400 ms). Adopted: 0.6 s springs, the next part
  starts as soon as the narration reaches it, connectors start 0.4 to 0.65 s before the node they lead to, so arrival and arrow land together.
- **Disney's principles in UI** ([IxDF](https://ixdf.org/literature/article/ui-animation-how-to-apply-disney-s-12-principles-of-animation-to-ui-design)):
  overshoot and settle (follow-through) reads as natural; staggered arrival (overlapping action); anticipation. Adopted: ease-out-back on every part, the arrowhead bounce,
  a draw-on line that leads into the node.
- **Apple's slides** ([Gallo](https://www.carminegallo.com/?p=3865), [Medium](https://medium.com/adventures-in-consumer-technology/this-is-how-we-make-slides-at-apple-b8a84352bf6d)):
  one theme per slide, bullets as a last resort, animate list items in one by one as spoken. Adopted: one lit item at a time, huge type (`spotlight`), at most 5 items.
- **Safe areas and type size** ([Dartmouth guide](https://services.dartmouth.edu/TDClient/1806/Portal/KB/Article/171286/Title-Safe-Areas-Quick-Guide-for-Video-Creation),
  a [mobile video guide](https://www.vidio.ai/blog/article/what-is-the-titlesafe-area-and-how-should-wedding-slideshow-editors-design-text-for-phones-and-tvs)): title-safe is about the
  inner 80 to 90 percent; commonly quoted minimums are about 36 px on a 1080-wide vertical frame and 48 to 72 px for primary text (secondary sources, not a standard).
  Adopted: margins of 150 px, a 30 px floor and 44 to 92 px for list text, one size per scene.
- **Contrast** ([WCAG 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [WebAIM](https://webaim.org/articles/contrast/)): 4.5:1 for text, 3:1 for large text
  and graphics; tokens that pass on white often fail on dark, so recompute. Adopted: palettes are computed and tested per theme.
- **Flowchart conventions** ([Nulab](https://nulab.com/learn/design-and-ux/keep-it-simple-follow-flowchart-rules-for-better-diagrams), [Creately](https://creately.com/guides/flowchart-rules/),
  [Miro](https://miro.com/blog/diagram-design/)): consistent spacing, connectors bold enough to read and never crossing nodes, shapes above connectors, one icon per node at most.
  Adopted: straight reading direction, curves that stay between nodes, a single icon per node, edge labels on the line.
- **Product-video look** ([LogRocket on Linear design](https://blog.logrocket.com/ux-design/linear-design), [Stripe Sessions](https://stripe.com/en-si/sessions/2024/craft-and-beauty-the-business-value-of-form-in-function)):
  soft gradients, glass surfaces, bold type, restrained slow ambient motion. Adopted: gradient fills, glass cards, the drifting grid; glass is used with solid, tested text colours.
  (Searches for Kurzgesagt-specific guidance returned nothing usable, so no claim is made about that style.)

## Not done here: the other basic scenes against the same bar
Looked at in midnight, end state. Order of need: **timeline** (tiny labels, flat boxes, no icons or active emphasis), **chart** (small axis text, plain bars, no accent control),
**quote** (small, left-heavy, empty frame), **title** (fine but plain; underline only), **stat** (the ring is good; label small). All still use `th.accent`; they can
adopt `style_kit.pal_for(th, props.get("accent"))` for a one-line palette hookup, which was left alone on purpose.
