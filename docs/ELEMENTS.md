# Proposal: a richer element library (2026-11-24)

**Status: a proposal, nothing built.** Today the director chooses from 10 scene types: `title`, `bullets`, `diagram` (left-to-right flow), `chart` (bar or line), `timeline`, `stat`, `quote`, `image`, `gallery`, `clip`. Each is drawn frame by frame on a 2D canvas (Pillow, 1920x1080, theme-aware), takes a small JSON of props, and can anchor its reveals to the words that name them (`engine/sync.py`).

**What the research supports** (the sources are mostly vendor and academic pages; nothing ranks elements, and almost nothing covers maps): explainers lean on kinetic typography for key phrases, animated charts, animated icons, labelled diagrams and arrows that walk through a process, callouts that point at a feature, comparison graphics, and maps used to guide attention ([Storyblocks](https://www.storyblocks.com/resources/tutorials/types-of-motion-graphics), [B2W](https://www.b2w.tv/blog/types-of-motion-graphics), [Vimeo](https://vimeo.com/blog/post/whats-motion-graphics-in-video)). Data-video research says visual variety across visual, motion, narrative and audio components raises expressive range ([arXiv 2502.04801](https://arxiv.org/html/2502.04801v1)), and a narrative-visualization taxonomy lists annotated chart, flow chart, slide show and film as separate genres ([Segel and Heer](https://homes.cs.washington.edu/~jheer/files/narrative.pdf)). Animated routes are drawn as a line that grows along the path with dates as it moves, with the camera following ([MapTiler](https://www.maptiler.com/news/2026/06/animated-routes-on-maps), [PremiumBeat](https://www.premiumbeat.com/blog/animated-map-after-effects-video-tutorial)); animated legends can distract, so they must be unobtrusive ([PSU GEOG 486](https://courses.ems.psu.edu/geog486/node/916)). Everything else below (what is worth building, in what order) is my judgement from the kinds of videos the testers ask for: news, history, learning, coding, places, inspiration, funny.

## How the director should choose (the part to get right)
- **Families, then elements.** The prompt lists the elements under 8 headings (Text, Lists, Compare, Data, Process, Maps, Code and math, People and sources, Media), each element on one or two lines with a "use when" and a "never when". 35 elements cost about 1.5k tokens; models handle a flat list of that size well, and the headings do the categorising. No two-step call is needed.
- **The director gives meaning, not layout.** Items, places, numbers, steps; never coordinates, pixels or colours. The renderer decides layout, as today.
- **Every element has a contract:** props schema with limits, a sync rule (which words each reveal is anchored to), a minimum and maximum duration, and a **fallback** (an unresolvable map becomes a title or photo, a failed icon becomes text), so a bad prop never leaves a hole.
- **Variety and restraint rules in the prompt:** never the same element twice in a row, an element only when the narration names what it shows, and a budget per heavy element (maps, code, equations) like the photo budget.
- **A preview for each element** (a contact sheet from `scripts/local_render.py`) so every new element is looked at before it ships.

## The catalogue: what exists, what to add
Effort: S = a day or less, M = a few days, L = a week or more (including data and tests). Value: how much it would improve the testers' kinds of video.

| Family | Element | What it shows | Effort | Value |
|---|---|---|---|---|
| **Text** | `title`, `quote`, `stat` | (have) | | |
| | `kinetic_text` | one key sentence, words popping in time with the voice, one word emphasised | S | high |
| | `definition` | a term, its definition, optional origin or example ("Inflation: ...") | S | high |
| | `myth_fact` | a claim struck out, then the truth | S | medium |
| | `question_card` | the hook as one large question | S | medium |
| | `counter` | a number counting up or down with unit and a before/after delta | S | high |
| | `takeaways` | the closing recap: 3 numbered points | S | medium |
| **Lists** | `bullets` | (have) | | |
| | `checklist` | items ticked off one by one | S | medium |
| | `ranking` | a top-N countdown, number big, optional photo per item | M | high |
| | `table` | rows and columns, one cell or row highlighted | M | high |
| **Compare** | `versus` | A vs B, matching rows, a winner or a verdict | M | high |
| | `pros_cons` | two columns with ticks and crosses | S | medium |
| | `matrix` | a 2x2 with labelled axes and items placed in it | M | medium |
| | `before_after` | two images or states, a wipe between them | S | medium |
| | `scale_compare` | things drawn to the same scale (heights, areas, sizes: tower vs tree vs person) | M | high |
| **Data** | `chart` | (have bar and line) | | |
| | `chart` kinds to add | `pie`/`donut`, `area`, `stacked`, `scatter` | M | high |
| | `bar_race` | bars re-ranking as the years pass | M | high |
| | `pictogram` | "1 in 5" as 100 icons, or a waffle | M | high |
| | `gauge` | a value on a meter or a progress ring | S | medium |
| | `treemap` | shares of a whole as nested boxes | M | medium |
| **Process** | `timeline`, `diagram` | (have) | | |
| | `steps` | a numbered process with chevrons, one step lit at a time | S | high |
| | `cycle` | a loop (water cycle, product cycle) with arrows | M | medium |
| | `funnel` / `pyramid` | stages that narrow, or levels that stack | S | medium |
| | `hub` | a concept map: one centre, spokes | M | medium |
| | `flowchart` | decisions with yes/no branches | M | medium |
| | `sequence` | actors and the messages between them (clients, servers, people) | M | high for tech |
| **Maps** | `map` | see the dedicated section | L | very high |
| **Code and math** | `code` | code typed on, lines highlighted as they are explained, a diff mode | M | very high for coding |
| | `terminal` | a command and its output | S | high for coding |
| | `equation` | a formula revealed step by step | M | medium |
| | `function_plot` | y = f(x) with a moving point | M | medium |
| **People and sources** | `quote` | (have) | | |
| | `headline` | a real news headline with outlet and date, from the research (never invented) | S | very high for news |
| | `profile` | a person card: photo from Wikimedia, name, years, role | M | high for history |
| | `dialogue` | chat bubbles for the two-voice videos, each speaker their colour | M | high |
| **Media** | `image`, `gallery`, `clip` | (have) | | |
| | `icons` | a row or grid of large icons with labels (features, steps, categories) | M | high |
| | `annotated_image` | a photo or diagram with arrows and labels on parts | M | high |
| | `generated_illustration` | an AI-made illustration for abstract ideas (a paid model call, about 4 cents; needs a policy for people and brands) | M | medium |
| | `collage` | photos stacked like polaroids | S | low |
| **Chrome** | `chapter_card`, `lower_third` | chapter titles from `chapter`, source credit overlay | S | medium |

That is 25 new elements plus 4 new chart kinds, 39 in all. Suggested order, by value for the cost: (1) `map`, `code`, `counter`, `headline`, `versus`, `steps`, `kinetic_text`, `definition`; (2) `scale_compare`, `pictogram`, `bar_race`, `table`, `ranking`, `dialogue`, `sequence`, `icons`, `annotated_image`; (3) the rest.

## Maps: how to do them well
**Why they matter and why they are hard.** Maps appear in news, history, travel, geopolitics, economics and science; they are the single element that most separates a "slide" video from an explainer. They are hard because they need data, projections, labelling and a camera, and because the director must name places without coordinates.

**Principles**
1. **Our own style, not tiles.** Draw maps ourselves from vector data, in the video's theme (midnight, paper, sunrise), with the highlighted region in the accent colour. Tile servers (OpenStreetMap, Mapbox, MapTiler) carry usage and attribution limits, need keys, and would not match the theme.
2. **Data we may ship:** Natural Earth (public domain) for countries, states and provinces, coastlines, lakes, rivers and about 7,000 populated places; Wikidata (CC0) and Wikipedia for the coordinates of landmarks and anything not in Natural Earth (we already read Wikipedia). City-street maps would need OpenStreetMap data (ODbL, attribution) and a much heavier renderer, so they are a later phase.
3. **The director names, the engine places.** The scene gives names and modes, never coordinates: `{"mode": "route", "stops": ["Paris", "Lyon", "Marseille"]}`. A resolver (Natural Earth first, then Wikidata) turns names into coordinates with a confidence check; ambiguous or unknown names fail the scene into a fallback (a photo or title card), exactly as images do today.
4. **Sync is the differentiator.** Each stop, region or label is anchored to the word that names it, with the same word-timing engine used for lists, so Lyon lights up as the narrator says "Lyon".
5. **One camera, one idea.** Each map beat has one job (where is it, what is the route, what is the spread) and the camera moves once, eased, to fit the content with padding. Heavy motion is not allowed under narration.
6. **Honesty.** Borders are today's borders; the scene says so in a small caption. Disputed areas use Natural Earth's neutral lines. No historical borders until we have a licensed historical dataset.

**Modes**, as one element with a `mode`: `focus` (zoom to a country or region with its name), `regions` (highlight several countries or states: empires, alliances, outbreaks, a spread), `points` (labelled places revealed in order), `route` (a line that grows along a journey with the moving head), `arcs` (connections between places: trade, flights, migrations, the width as the amount), `choropleth` (values per country or state in a colour scale, with a small legend), `globe` (a rotating globe that settles on a place, for "where in the world"), `locator` (a small inset globe beside another scene).

**Projection by extent:** orthographic globe for world and continents, Equal Earth for the whole world, a conic projection for countries and regions, Web Mercator only for small areas.

**Phases.** M1: `focus`, `regions`, `points`, `route` and `arcs` on Natural Earth with the resolver and fallbacks (the first useful release). M2: `choropleth` and `globe`. M3: city-level maps from OSM extracts for a short list of big cities. M4: historical borders, only with a licensed dataset.

**Risks.** Label collisions need a placement routine; render time rises with polygon count (so we ship simplified geometry per zoom level and cache the projected base map per video); the resolver is the main source of wrong results, so unresolved names must degrade rather than guess.

## Other things worth settling before building
- **Budgets and variety:** a per-video cap on maps, code and equations (like the photo density cap), and a rule against repeating an element.
- **Icons:** a licensed icon set (Lucide is ISC, Tabler is MIT; both free for commercial use) bundled with the renderer, chosen by name with a fallback when a name is unknown.
- **Math typesetting:** Matplotlib's mathtext is pure Python and avoids a LaTeX install, at the cost of a larger layer.
- **Code highlighting:** Pygments (BSD) for tokens; the director sends code and the lines to emphasise.
- **Editor:** each new element needs its fields in the phone editors (iOS and Android), or they stay read-only there.
- **Testing:** each element gets a unit test of its props and a render test, and a contact sheet reviewed by eye.
