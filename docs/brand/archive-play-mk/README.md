# videomk brand mark (v2: play + MK)

Status: proposal for owner approval. No app or site code uses these files yet. The rejected shared-stem MK cursor logo is kept in `archive-mk-cursor/`.

## The mark

A soft, large **play triangle** (white, generous corner radius) with **M K cut out of it** as negative space, on the app's indigo-to-violet gradient. The play shape says video at a glance; the letters are the name, and because they are holes, the background gradient shows through them: one shape, no extra colour.

- Geometry: triangle with 65-unit corner radius on a 1024 grid, letters in one 58-unit round-capped monoline stroke (same stroke language as the wordmark). All art is real filled paths (even-odd holes), no masks, strokes or fonts, so Android VectorDrawable and Xcode import cleanly.
- Wordmark: `videomk`, lowercase, hand-built round monoline letters, converted to filled paths. No font licence.
- Colour: one foreground colour (white) plus the gradient. Cyan is held in reserve (see `final-alt/`).

## Colour and contrast (WCAG 2.x, computed)

| Item | Value | Contrast |
|---|---|---|
| Gradient start / end | `#2b2f9a` / `#6a3fc4` (`--making-start` / `--making-end` in `frontend/src/styles/tokens.css`) | |
| White triangle on gradient | `#ffffff` | 10.6:1 / 6.7:1 |
| MK holes (gradient) against the white triangle | | same ratios, so letters meet 3:1+ everywhere |
| Wordmark on light | `#11142b` on `#f6f7fc` | 16.9:1 |
| Wordmark on dark | `#f3f4fb` on `#0a0d1f` | 17.6:1 |
| Cyan `#22d3ee` (alt only) on gradient | | 5.9:1 / 3.7:1; never on white (1.7:1) |

Continuity: the old icon was a cyan play triangle on near-black navy. Same idea, same family, but the triangle is now white (higher contrast, letters can be knocked out) and the background is the app's own making gradient so the icon matches the in-app making screen and stands out on dark wallpapers.

## Files

`final/` (recommended): `icon-1024.svg/.png` (iOS, full-bleed, no rounding, no alpha), `android-adaptive-foreground.svg` (scaled 0.78 so all ink is inside the 66 dp safe circle), `android-adaptive-background.svg`, `android-monochrome.svg` (themed layer, letters are true transparent holes), `wordmark-lockup-light.svg/.png`, `wordmark-lockup-dark.svg/.png`, `favicon.svg` (+ `favicon-512.png`; heavier letters, larger glyph), `preview.png`.

`final-alt/`: the runner-up with the same set of files (cyan triangle, K only).

Android: the SVGs are source art; import with Android Studio Vector Asset. The 1024 grid stands for the 108 dp canvas.

## Clear space and minimum size

- Clear space around lockup or tile: half the tile height on every side.
- Minimum: app icon 29 pt (the triangle always reads; M K reads from about 40 px, below that it becomes texture); lockup 24 px tile height; favicon 16 px (play shape only).
- Below 24 px use the tile without the wordmark.

## Do / do not

Do: use files unmodified; dark lockup on dark, light on light; keep the letters as holes.
Do not: recolour; fill the letters with another colour; add sparkles, glow or shadow; round the iOS art yourself; stretch or outline; set the wordmark in another font or in capitals; use cyan on light backgrounds.

## How it was chosen

Round 1 (`concepts/contact-sheet-round1a/b/c.png`, 11 concepts, each at 1024 full-bleed and iOS-masked, and 180 / 60 / 29 px on light and dark):

| # | Concept | Verdict |
|---|---|---|
| P1 | White play, K cut out | Works; video-obvious, K integrated, M missing |
| P2 | White play, M cut out | Works; same, K missing |
| P3 | Outline play with cyan K inside | K turns to mush at 60 px; outline play is thin |
| P4 | M then cyan play | Clear, but K absent and it reads as "M, play" (two objects) |
| P5 | Rounded video frame + play | Generic "video" glyph, no letters; any media app |
| P6 | Clapperboard + play | Very video, but busy at 29 px, no letters, looks like iMovie/CapCut family |
| P7 | Caret + play | Reads as skip-to-start; no letters |
| P8 | Play + AI spark | Spark is the generic AI cue and fights the play shape; no letters |
| P9 | Outline play, K arms on edges | Muddled at small size |
| P10 | M, cyan stem, white play | Good proportions but K only implied |
| P11 | M, stem, cyan play | Reads "MI play"; K lost |

Round 2 (`round2/`): R2-1 white play + K, R2-2 cyan play + K cut as slits through the edges, **R2-3 white play + MK**. Round 3 (`round3/`) refined R2-3: a) white, b) cyan (letters lose contrast and it is less legible), c) shared-stem ligature (letters collide). **R3-a is final.**

Recommendation reasoning (the owner's test): video-obvious yes (a play button at any size), MK integrated yes (both letters, as negative space of the play shape itself, legible from 60 px), distinctive geometry partly (large soft triangle, letters as cut-outs, gradient showing through). Honest limit: a white rounded triangle on a purple tile is a familiar silhouette; what separates it is the knocked-out MK, the proportions (triangle fills ~60% of the tile, wide soft corners) and the gradient. At 29 px it is a play button with a texture, not readable letters (intended).

Runner-up (`final-alt/`, R2-2): cyan play triangle with a K sliced through the edges. More ownable and keeps the old cyan, but only the K, and the slits make the triangle read slightly "broken" at 29 px.

## Look-alike check (from knowledge, no live trademark search)

Too close: **P5 and P6** (frame/clapper plus play are the stock video glyph, and CapCut, InShot, iMovie and Canva video tiles live there) and **P7/P4** (skip/media-control glyphs). **P8** is close to the generic AI spark (Gemini, Adobe, Canva Magic) added to a play button.
Nearest to the recommended mark: YouTube (red rounded rectangle with a white triangle, no letters; different colour and container), Google Play (multicolour triangle, different shape language), Vimeo (blue tile with a "v"), Netflix (red N), TikTok (musical note), Loom (burst), Descript (D-shaped wave), CapCut (stylised cut), InVideo / Pictory / HeyGen / Synthesia / Runway (letters or abstract marks, none is a play triangle with knocked-out initials), Canva (script "Canva"). Closest conceptually: stock "play" icons and the white-triangle-on-purple of many small tools. The knocked-out MK inside the play shape is the differentiator; no known brand uses it. Do a proper trademark and app-store similarity search before launch; this is a design check, not legal clearance.
