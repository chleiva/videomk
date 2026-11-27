# videomk brand mark

Status: proposal for owner approval. Nothing in the apps or the site uses these files yet.

## The mark

An uppercase **M** and **K** that share one stem. The stem is cyan, taller than the letters and round-capped: it is a **text cursor**. You type a request, the cursor is in the middle of the name, and a video comes out. No play triangle: videomk is about making, not watching.

- Geometry: one stroke weight (88 on a 1024 grid), round caps and joins, no fills other than the background. Two colours (white, cyan) on one gradient.
- Wordmark: `videomk`, lowercase, hand-built from the same round monoline strokes (circles, stems, arches). No font is used or needed, so there is no licence to carry. The letters are stroked paths; if a printer needs filled outlines, use "Outline stroke" in any vector editor.

## Colour

| Role | Value | Source |
|---|---|---|
| Background gradient start (top-left) | `#2b2f9a` | `--making-start` in `frontend/src/styles/tokens.css` |
| Background gradient end (bottom-right) | `#6a3fc4` | `--making-end` |
| Letters | `#ffffff` | |
| Cursor stem | `#22d3ee` | `--live` (already the colour of the old play triangle) |
| Wordmark on light | `#11142b` | `--text` |
| Wordmark on dark | `#f3f4fb` | dark `--text` |

Continuity: indigo to violet and the cyan accent are kept. What changes is the background: the old icon was near-black navy with a small cyan triangle (low presence on a dark home screen, and the same shape as every video app). The new one uses the app's own "making" gradient, which stands out on both light and dark wallpapers and ties the icon to the in-app making screen.

WCAG 2.x contrast (computed, see `tokens` pairs):

- White letters on `#2b2f9a` 10.6:1, on `#6a3fc4` 6.7:1 (AA text and graphics).
- Cyan stem on `#2b2f9a` 5.9:1, on `#6a3fc4` 3.7:1 (passes the 3:1 non-text minimum everywhere on the gradient).
- Wordmark `#11142b` on `#f6f7fc` 16.9:1; `#f3f4fb` on `#0a0d1f` 17.6:1.
- Never put the cyan on white or light surfaces (1.7:1). On light pages the mark lives on its gradient tile; the wordmark is ink only.

## Files (`final/`)

| File | Use |
|---|---|
| `icon-1024.svg` / `.png` | iOS App Store / AppIcon. Full-bleed square, no rounded corners, no alpha needed (iOS applies the mask). |
| `android-adaptive-foreground.svg`, `android-adaptive-background.svg` | Adaptive icon layers, 1024 grid standing for the 108 dp canvas. Foreground is scaled to 0.78 so all ink sits inside the 66 dp safe circle. |
| `android-monochrome.svg` | Themed icon layer (single colour, transparent). Same safe-zone scale. |
| `wordmark-lockup-light.svg` / `-dark.svg` (+ `.png` previews) | Tile plus `videomk`. Light = ink wordmark for light backgrounds; dark = near-white wordmark for dark backgrounds. |
| `favicon.svg` | Rounded tile, glyph enlarged and stroke thickened for 16 px. `favicon-512.png` is a preview. |
| `preview.png` | Everything above, masks, sizes, light and dark. |

Android notes: the svgs are source art; import to Android Studio Vector Asset (or convert to `VectorDrawable`) when wiring. Keep the gradient as the background layer so launcher parallax looks right.

## Clear space and minimum size

- Clear space around the lockup or the tile: half the tile height on all sides. Nothing (text, edges, other logos) inside it.
- Minimum sizes: app icon 29 pt (checked at 29, 40, 60, 87, 120, 180 px, see `preview.png`); lockup 24 px tile height (about 150 px wide); favicon 16 px (the cursor reads as a thin line there, M and K still read).
- At or below 24 px prefer the tile alone, without the wordmark.

## Do

- Use the supplied files unmodified. Scale proportionally.
- Use the dark lockup on dark surfaces, the light lockup on light ones.
- Keep the tile as the only place the cyan appears.

## Do not

- Recolour the letters, the cursor or the gradient; swap the cyan for white.
- Add a play triangle, a sparkle, a glow, a drop shadow, or text inside the icon.
- Round the iOS icon art yourself; stretch, rotate, outline or put it on a busy photo.
- Set the wordmark in another font, in capitals, or with the M K highlighted.
- Use the mono layer where a colour icon is available.

## How this was chosen

`concepts/` has the five round-one concepts and `contact-sheet-round1.png`; `round2/` has the three refinements and `contact-sheet-round2.png`. Each sheet shows 1024 (full-bleed and iOS-masked) and 180 / 60 / 29 px on light and dark.

Round one (honest critique):

- **A MK monogram**: strongest at small size and ownable, but M and K stems collided (blob at 29 px) and as drawn it was just two letters. "MK" is also Michael Kors and Mortal Kombat territory, so it needs a distinguishing device.
- **B Spark**: reads at 29 px but is the most common AI symbol today (Gemini, Adobe, Notion AI and dozens more) and says nothing about video.
- **C Viewfinder**: reads as "frame" but also as a QR/scan/focus utility icon; any camera or scanner app looks like it.
- **D Caret + frame**: the best idea (a prompt cursor next to a video frame) but drawn it reads as "10" or "IO"; after refinement attempts (caret inside the frame, caret as the frame edge, a solid screen) it read as a battery, toggle or the letter b. A 16:9 frame is too short in a square icon.
- **E Drawn play**: still a play button; the "pen tip" dot is invisible at 29 px.

Round two (carrying the cursor idea into the monogram): lowercase `mk` with a cyan k (friendly, legible, but generic rounded-letters look), `mk` with a separate cursor stem (k arms collide with the stem), and **uppercase MK on a shared cyan cursor stem** (chosen: most distinctive, clearest at 29 px, and the cursor idea survives).

Look-alike check (from knowledge, no live trademark search): no known video or AI app uses a white M/K with a cyan vertical bar through the join on an indigo gradient. Nearest neighbours: Michael Kors "MK" (black/gold serif monogram, different), Mortal Kombat "MK" dragon logo (different), Monzo/MailerLite-style gradient tiles (colour only). Do a proper trademark search in the app-store classes before launch; this is a design sanity check, not legal clearance.

Caveats: the cursor is a metaphor, not an obvious "video" cue; the name carries that. The M/K reading also depends on the stem being exactly where the M's right leg and the K's spine meet.
