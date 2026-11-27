# VideoMK logo: B1 "Action"

Chosen by the owner on 27 Nov 2026. The rules are in `docs/BRAND.md`; this file says what is in these folders and how the files are made.

## The mark

One rounded **play triangle** and **two four-point stars** above its tip: a big one and a second at 0.66 of its size. No letters. The same drawing at every size, from the 1024 px icon to the 16 px favicon: the second star is never dropped and there is no simplified small version.

- Colour: **white on the action gradient** `#3B36C8` to `#7A4BE6` (top left to bottom right), the gradient of the Create button.
- Dark-appearance app icon: the Midnight ink tile `#151828` to `#06070D`, play `#6360FF` to `#B56CFF`, big star cyan `#7CEBFA` to `#22D3EE`, small star `#E9E8FF`.
- Without a tile: the mark in the action gradient on light backgrounds, white on dark ones, or one colour (white, ink `#0B0C14`, or any single colour through `mark-mono.svg`).
- Geometry on a 1024 grid: play `tri(242, 326, h 468, w 420, r 54)`, stars at (630, 318) radius 128 and (786, 472) radius 84; ink box 628 x 574. In the app icon the mark is 1.06 of the grid about the centre; in the rounded tile 1.155; on Android 0.848 (all ink inside the 66 dp safe circle: farthest point 304 px, limit 313).

## The wordmark

"VideoMK" in **Inter** (SIL Open Font License), "Video" at weight 600 and "MK" at 800, tracking -18/1000, one colour. Outlines only (`final/wordmark.json`), never live text in a logo file.

## Contrast (WCAG, computed)

| Pair | Ratio |
|---|---|
| White mark on the gradient | 8.2:1 at `#3B36C8`, 5.3:1 at `#7A4BE6` |
| Gradient mark on the page `#F7F7FA` | 7.7:1 to 4.9:1 |
| Dark icon: play, big star, small star on the ink tile | 3.9:1, 9.7:1, 14.6:1 |
| Wordmark: ink on `#F7F7FA`, `#F4F5FA` on `#06070D` | 18.2:1, 18.5:1 |

## Files

`final/` (the masters; made by `final/build_final.py`, plain paths only: no groups, transforms, masks, clip paths or fonts):

| File | Use |
|---|---|
| `mark-tile.svg` | The mark on the rounded gradient tile (the favicon, the mark inside the apps and the site) |
| `mark-gradient.svg`, `mark-white.svg`, `mark-black.svg`, `mark-mono.svg` | The mark alone: gradient ink for light backgrounds, white, ink, and `currentColor` for any single colour |
| `icon-1024.svg/.png` | App icon, default (light). Full-bleed, square, no alpha |
| `icon-1024-dark.svg/.png` | App icon, dark appearance (iPhone) |
| `icon-1024-tinted.svg/.png` | App icon, tinted appearance (iPhone): grey values only, opaque; iOS lays the tint over it |
| `android-adaptive-foreground.svg`, `android-adaptive-background.svg`, `android-monochrome.svg` | The three layers of the Android adaptive icon (1024 stands for 108 dp) |
| `lockup-horizontal-tile-light/-tile-dark.svg/.png` | Tile + word, for light and dark backgrounds (headers, the sign-in page) |
| `lockup-horizontal-light/-dark/-white/-black.svg` | Mark without the tile + word; `-white` is the watermark's source (`.png` too) |
| `lockup-stacked-*.svg` | The same six, mark above the word |
| `favicon.svg`, `favicon-512.png` | The rounded tile for browsers |
| `wordmark.json` | The wordmark's outlines |
| `preview.png` | All of it on one sheet |

`store/` (upload these by hand):

| File | Where |
|---|---|
| `videomk-app-store-icon-1024.png` | App Store Connect (comes with the build; also the listing icon). 1024, no alpha, square corners |
| `videomk-play-store-icon-512.png` | Google Play Console, Store listing, App icon. 512, 32-bit PNG, full-bleed (Play rounds it) |
| `videomk-play-feature-graphic-1024x500.png` | Google Play Console, Store listing, Feature graphic |
| `videomk-google-consent-logo-120.png` | Google Cloud console, OAuth consent screen, App logo |
| `videomk-og-1200x630.jpg` | The share image (the site's `og.jpg`); also for social profiles' link previews |

## Rebuilding

```
.venv/bin/python docs/brand/final/build_final.py      # masters, store files, and the copies in the apps, the site and the sign-in page
.venv/bin/python backend/scripts/watermark_assets.py  # the watermark art the video engine ships
```

`build_final.py` also writes: `mobile/ios/VideoMK/Assets.xcassets/{AppIcon.appiconset (light, dark, tinted), BrandMark.imageset, Lockup.imageset}`, `mobile/android/app/src/main/res/drawable/ic_launcher_{foreground,background,monochrome}.xml`, `frontend/public/{favicon.svg, favicon.ico, apple-touch-icon.png, icon-192.png, icon-512.png, og.jpg}`, `backend/login_branding/{logo-light.svg, logo-dark.svg, favicon.svg, favicon.ico}`. The web header's word is `frontend/src/components/Wordmark.astro` (the same outlines).

## History

- `2026-11-27-play-star/`: the six play + star options (round 1) and the eight colour treatments of option B's shape (round 2, `round2/`), with the look-alike check and the sources on what makes a mark work. B1 won.
- `archive/2026-11-26-sparklet-trio/`: the previous mark (a play with three sparks at its tip, lowercase hand-built wordmark). Superseded; not used anywhere.
- `final-alt/`, `concepts/`, `round2/`, `round3/`, `archive-mk-cursor/`, `archive-play-mk/`: earlier explorations.

A design check is not legal clearance: do a trademark and store similarity search before launch (generic "AI video" play + sparkle glyphs are common; ours is told apart by the two stars in a fixed 3:2 rhythm and the indigo-violet).
