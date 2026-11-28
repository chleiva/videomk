# Create screen redesign: the values the web build chose

For the iPhone and Android builders (same brief: `CREATE_SCREEN_REDESIGN_BRIEF.md`). Where the brief left a choice, this is what web did. Sizes are CSS px (1 px = 1 pt = 1 dp at the same scale). Match them or tell the web builder why not. Web source: `frontend/src/components/app/Composer.tsx`, `LookPicker.tsx`, styles in `frontend/src/styles/bar.css`.

## Layout (identical at 390, 768 and 1440 px)

Inside ONE card, top to bottom: prompt, photo strip (when photos), presentation card (when attached), status line (only when there is something to say), look-reset line (when a look went back to Auto), then the dock:

1. Pills row: made for, length, look, and the Characters pill only when the look has a cast. Pills wrap to a second row; there is never a fifth pill.
2. Tool row: photo, mic, Options on the left; Create at the trailing end.
3. Caption row (only before the first finished video, or when the balance is low).

Web has no top bar with X (the page sits in the app shell, the heading "What's the video about?" stays). Autofocus on the prompt is kept (`autoFocus`).

## Sizes and spacing

| Thing | Value |
|---|---|
| Pill | height 44, horizontal padding 12 (10 below 768 px), 16 glyph, 6 gap glyph to text (4 below 768), 16 chevron, radius full, fill `surface2`, label 15 / weight 600 |
| Gap between pills | 6 horizontal, 8 vertical (second row) |
| Gap pills row to tool row | 8 |
| Photo and mic | 44 x 44 round, fill `surface2`, 22 glyph |
| Options | height 44, sliders glyph 22 + label "Options", padding 8 left / 10 right, gap 4, fill `surface2` (pill shaped) |
| Gap between tools | 4 |
| Create | height 48, min width 112, horizontal padding 20, gap 6 between label and bolt+price, bolt 16, label 16 / weight 700, radius full |
| Create, active | gradient (`gradientStart` to `gradientEnd`, 135 deg), white label, small shadow `0 2 8` at 28% brand colour (no glow) |
| Create, inactive | opaque `surface3` fill, `textSecondary` label and bolt, no shadow. Light 4.9:1, dark 6.2:1 (measured). Still focusable and tappable |
| Create, large-text fallback | own row, full width, height 52 (scales with the text size on web), tool row above it unchanged |
| Card padding at phone width | 16 top, 12 sides, 12 bottom (it gives the tool row 334 pt at 390 so Create fits beside Options in English and Spanish) |
| Caption | 14, `textSecondary`, centred, 8 under the tool row |
| Dock height at 390 | one pill row about 124 (measured 124), two pill rows about 172 |
| Live capsule (creating) | full width of the card, height 64, `surface2` fill with a hairline, spinner + sentence + Cancel at the end |

## Glyph names (web icon names; draw the same thing)

- Made for: the shape of the chosen format: `shape-wide` (rounded rectangle 18 x 11, for 16:9 and wider than 1.2), `shape-portrait` (12 x 16, for 4:5), `shape-square` (14 x 14), `shape-tall` (9 x 18, for 9:16). Stroke 1.8, round caps, radius 2.5 on a 24 box.
- Length: `clock` (circle, hands at 12 and 3-4).
- Look: `sparkle`, for every look (the picture thumbnail that web had in the pill on phones is gone).
- Characters: the faces picked, overlapped 6, 22 each; when none is picked (we choose) the `people` glyph (two heads). Then the word "Characters", then the chevron.
- Photo button: `addphoto` (photo with a plus). Count badge when photos are attached: 20 circle, 14 digit, `text` fill, `background` digit, top right.
- Options: `sliders`. Mic: `mic`; while recording: filled `stop` square on the danger container.

## Strings (English / Spanish)

| Key | English | Spanish |
|---|---|---|
| Options label | Options | Opciones |
| Create label | Create | Crear |
| Create name (accessibility) | Create video | Crear video |
| Characters pill | Characters | Personajes |
| Characters pill accessibility | Characters: Fox and Bruno (or "Characters: Auto") | Personajes: Fox y Bruno (or "Personajes: Auto") |
| Mic, recording (name) | Stop dictating | Detener el dictado |
| Recording label in the tool row | Listening... | Escuchando... |
| First-video caption | 1 credit. You have 11. / 3 credits. You have 11. | 1 crédito. Tienes 11. / 3 créditos. Tienes 11. |
| Low-balance caption | 4 credits left | 4 créditos disponibles |
| Create state, ready (accessibility description) | Ready, costs 3 credits. | Listo, cuesta 3 créditos. |
| Create state, empty prompt | Not ready: describe your video. | No está listo: describe tu video. |
| Create state, recording | Not ready: stop dictating first. | No está listo: deja de dictar primero. |
| Create state, photos or presentation still being added | Not ready: one moment. | No está listo: un momento. |
| Tap on the inactive Create (status line, fades after 4.5 s, caret goes back to the field) | Describe your video to create it. | Describe tu video para crearlo. |

The credit price in words always uses the plural rule ("1 credit", "2 credits").

## Rules web chose where the brief was open

- "Low balance": the balance is less than 2 x the price of this video (so it could not make a second one like it). Then "N credits left" shows under the tool row. Never for unlimited accounts. When the balance is below the price the existing "needs N credits, you have M" sentence takes over and the caption steps aside.
- First-video caption and chips depend on "has a finished video": from the Videos list (cached list first, else one read). If that cannot be read, neither chips nor caption show.
- Chips: three (How bees make honey, 3 focus tips for busy days, Why forests matter), two when the window is shorter than 640 px. They are below the card on web, left aligned on a phone.
- The caption row is hidden while a status or error sentence shows, and while creating.
- Creating: the whole dock (pills and tool row) is replaced by the capsule. Spring in from the Create pill's corner, 380 ms, overshoot curve `0.34, 1.4, 0.64, 1`; reduced motion is a 120 ms cross-fade. The prompt is dimmed to 50% and inert.
- Recording: the mic becomes Stop and stays LEFT of Create. Photo and Options are disabled and Options drops its label (icon only) so "Listening..." has room at 390. The field is read-only.
- Presentation: it is the third row of the photo menu (From this device, From My media, Add a presentation). While a presentation is attached the photo button is not shown.
- Options sheet: quality (and the 4K note), subtitles, narration language, colors (the colour theme, which is NOT the look: only when the server has the look picker), scenes (only when the server offers it), watermark, the note. Format and the look tiles are gone. Web's made-for pill also lists the shapes no platform starts with (Square, Portrait) so a shape is chosen in exactly one place.
- Characters pill and Look pill open the same surface; the Characters pill puts the focus on the cast.
- Fallback to the full-width Create row is measured (Create no longer fits beside the tools in the row), not tied to one scale number; it triggers at 150% text and 320 px width.
