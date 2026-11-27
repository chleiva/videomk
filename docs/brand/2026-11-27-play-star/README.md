# VideoMK logo options: play + star (27 Nov 2026)

Status: **decided (27 Nov 2026).** The owner chose option B's shape in round 2's colour treatment **B1 "Action"** (`round2/`). The final files are in `../final/` and the rules in `docs/BRAND.md`; this folder is the record of the options.

The brief: the owner prefers the lean glyph on the Create button (a play triangle with a little star; "one play and two stars is fine as well") and asked for a colour combination worthy of a top startup. No letters in the mark, it must say "video" at a glance, minimalist, right as an app icon.

## The six options

| | Name | Shape | Colour system | Weak point |
|---|---|---|---|---|
| A | Create | One rounded play, one four-point star above the tip (the Create button) | Action gradient tile `#3B36C8` to `#7A4BE6`, white mark; dark icon: ink tile, mark `#7672FF` to `#B78CFF` | The most generic shape of the six; the colour and fixed star position carry it |
| B | Midnight | One play, two stars (big and small) wrapping the tip | Ink tile `#151828` to `#06070D`, play `#6360FF` to `#B56CFF`, big star cyan `#22D3EE`, small star `#E9E8FF` | Small star is gone at 16 px; three colours |
| C | Flat | A star cut out of the play | One flat indigo `#4B45E0` and white | The hole fills in at 16 px; closest to "white play on a colour tile" |
| D | Paper | Play as negative space in a rounded badge, star on its corner | Light tile, badge in the action gradient, star `#7A4BE6` (cyan on dark) | A tile inside a tile; busiest silhouette |
| E | Sunspark | An amber star set into the play's upper edge (halo gap) | Brand gradient tile `#2B2F9A` to `#6A3FC4`, white play, amber `#FFD35C` to `#FF9A1F` | The bite muddies at 16 px; amber on white is 1.7:1, so the star needs a dark ground |
| F | Aurora | One play, two rising stars | White tile, mark `#3B36C8` to `#7A4BE6` to `#EC4F9E`, coral star | Lowest contrast (3.0:1 at the pink end); nearest to Google Play at a glance |

**Recommendation: A (Create).** It is the glyph the owner pointed at, drawn with care (corner radii, a slightly fuller star, optical centring), on the product's own action gradient, so the icon, the Create button and the watermark are one and the same thing. It is the cleanest of the six at 16 px and in one colour. **Runner-up: B (Midnight)**: the "one play and two stars" version; the ink tile stands apart from the many purple tiles on a home screen.

Contrast (WCAG, worst gradient end): A white on tile 5.3:1. B play 3.9:1, stars 9.7:1 and 14.6:1. C 6.5:1. D 4.5:1. E play 6.7:1, star 3.2:1. F play 3.0:1, coral star 2.1:1 (fails 3:1).

## Look-alike check (visual only, not legal clearance)

- A: generic "AI video" glyphs (CapCut AI, Canva Magic Media). Differs by one fuller star in a fixed place and our indigo-violet. Not YouTube (no red, no rectangle).
- B: the sparkles emoji or Gemini star cluster beside a play. The play stays dominant; two star colours.
- C: YouTube's white play on a colour tile, Pictory's rounded play. Indigo, square tile, star inside.
- D: YouTube / Google TV "play in a rounded rectangle". Square badge, indigo-violet, star.
- E: Plex (amber chevron on black), "premium" star badges. White play first, four-point star interlocked.
- F: Google Play (multi-colour triangle on white), Instagram's gradient. One continuous gradient, rounded, with stars; still the closest of the six to Google Play.
- Never use a star alone (Gemini, OpenAI-style sparkles): the play is always present.

## Wordmark

`VideoMK` in **Inter** (SIL Open Font License, free for logo use; already the web fallback face and the engine's caption face, and the nearest open relative of SF Pro, which Apple does not license for logos). Display optical size, tracking -18/1000, "Video" at weight 600 and "MK" at 800, one colour: the weight step makes the capital M and K read as the brand's signature without a second colour. Compared with Manrope, Plus Jakarta Sans and Sora in `sheets/wordmark-typefaces.jpg`. Outlines only (no font needed to render).

## What makes a startup mark work (sources)

One idea in a minimal number of shapes on a simple ground; still itself in one colour; legible at 16 px; a colour it can own.

- Apple, Human Interface Guidelines, App icons: https://developer.apple.com/design/human-interface-guidelines/app-icons
- Microsoft, App icon design (a singular element, at most two metaphors): https://learn.microsoft.com/windows/apps/design/iconography/app-icon-design
- "What makes a logo work at 16x16 pixels": https://dev.to/alphashark/what-makes-a-logo-work-at-16x16-pixels-c4i
- Piktochart, Designing minimalist logos (geometry, monochrome test): https://piktochart.com/blog/designing-minimalist-logos/
- Ramotion, Tech startup logos: https://ramotion.com/blog/tech-startup-logos

## Files

- `svg/`: per option `X-mark-on-light`, `X-mark-on-dark`, `X-mark-white`, `X-mark-black`, `X-icon-1024`, `X-icon-1024-dark`, `X-lockup-tile|light|dark|white|black`. D and E use an SVG `<mask>` for the halo gap; it will be flattened to plain paths for the one that is chosen (Android VectorDrawable has no masks).
- `sheets/`: seven comparison sheets (one per view, A to F), a detail sheet per option, the typeface sheet.
- `build.py` (resvg_py + Pillow, the repo's `.venv`) rebuilds everything; `wordmarks.py` (fontTools, needs Inter / Manrope / Sora / Plus Jakarta Sans variable fonts from Google Fonts in `fonts/`) made `wordmarks.json`.
