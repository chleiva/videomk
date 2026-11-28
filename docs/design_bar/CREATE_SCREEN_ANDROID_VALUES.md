# Android Create v2: the values chosen

Brief: `CREATE_SCREEN_REDESIGN_BRIEF.md` (items 1-7). Code: `ui/CreateScreen.kt`, `ui/CreateDockUi.kt` (dock pieces), `core/CreateDock.kt` (decisions, JVM-tested), `ui/OptionsSheet.kt`, `ui/UiKit.kt` (Pill, PillButton, GlassIconButton). dp = Android dp.

## Layout
Top bar: only the X (kept). Prompt: keyboard opens on arrival (`LaunchedEffect` focus + show; was never focused). Dock, bottom, side padding 16, top 8, bottom 12:
1. Status sentence (only when something is wrong; never for Ready, Listening, empty prompt).
2. Pills row (`PillRows`, gap 6, wraps to two rows, never a fifth): made for (drawn shape glyph), length (clock), look (sparkle), Characters only with a cast (faces, or the person glyph for "we choose"; compact faces-only form when the word does not fit). Pill: 44 visible / 48 target, padding 10 start / 6 end, 4 glyph gap, glyph 18 (grows with font scale up to 1.5x), chevron 18, label 14 sp semibold.
3. Tool row: photo-plus, mic (48 targets, 44 circles), Options (sliders 22 + label, 44 visible / 48 target, padding 10 / 12), Create at the trailing end.
4. Caption (one line, centred, 12 sp, secondary): first video "2 credits. You have 11." (plural-aware), later only when balance < 2 x price: "N credits left" (N = balance, as web). Never for unlimited accounts, nor below the price (the "needs N credits" sentence takes over), nor while a presentation's price is unknown.

## Create pill
Height 48 (52 on its own row), min width 112, padding 18 (web 20; 18 so the row fits at 360 dp), label 16 sp bold, bolt 16, price 16 bold; label never wraps or truncates. Active: gradient, no glow. Inactive: opaque `surface3`, `textSecondary` label and bolt (same token as web: 4.9:1 light, 6.2:1 dark), tappable, the tap pulses the status sentence ("Describe your video") and announces it. Creating: the whole dock (pills, tools, caption) is replaced by the existing full-width live capsule (cross-fade, 220 ms; 120 ms with reduced motion); the prompt is dimmed to 50% and inert. TalkBack: name "Create video" (or "Create · 1 min" with the affordable-length fix), state "Ready, costs 3 credits" / "Not ready. ...".

## Own row
`CreateDock.createOnOwnRow`: font scale >= 1.5, or measured: tools + 4 + Create > row width. Then Create is full width, 52 high, under the tools; mic stays left. At 360 dp and 100% text, English and Spanish, Create sits beside the tools.

## Recording
Mic becomes a filled Stop on the danger colour (`GlassIconButton(danger = true)`), photo and Options disabled (Options icon only), "Listening..." (12 sp, danger colour) centred between tools and Create, Create inactive.

## Chips
Only while the field is empty, nothing attached, not listening/creating, and no finished video. Unknown (list not loaded or unreadable) counts as finished (no guess). Three; two when the area above the keyboard is under 640 dp; none under 340 dp (a small phone with the keyboard up: one clipped chip is worse than none).

## Short windows
Pills scroll with the prompt only when the area is under 270 dp, or at font scale >= 1.5 under 620 dp; the tool row and Create are always pinned.

## Options sheet
No "made for" chips, no look swatches without the look picker. Kept: Colours (only with the look picker), Scenes/Background where offered, Quality, Subtitles, Language, Watermark, Format tiles (the only place that picks Square or Portrait; iOS keeps them too, web moved them into its pill).

## Not the same as the other platforms
Low-balance caption shows the balance (web) not balance minus price (iOS draws the latter). Create padding 18 vs 20. Dock text is not capped at a font scale (iOS caps at accessibility1); glyphs scale to 1.5x only.
