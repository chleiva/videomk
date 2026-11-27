# VideoMK brand rules

Owner decisions of 27 Nov 2026. Short on purpose: one page a person or an agent can hold in their head.

## 1. The name

The name is written **VideoMK**: capital V, lowercase "ideo", capital M, capital K, no space, no hyphen.

- Everywhere a person reads it: screens, buttons, titles, page titles and social tags, emails and their sender names, permission prompts, legal texts, store listings, the watermark and the closing card ("Made with VideoMK" / "Hecho con VideoMK"), release notes, support replies.
- The same in every language. It is never translated and never changes with grammar ("la app de VideoMK", "VideoMK's library").
- At the start of a sentence and in headings it is still VideoMK. Never "Videomk", "VideoMk", "Video MK", "VIDEOMK", "videoMK" or "videomk".

### When lowercase is right

Lowercase `videomk` is an identifier, not the name. It stays exactly as it is in:

- the domain and anything built on it: `videomk.com`, `app.videomk.com`, `https://videomk.com/privacy`, `hello@videomk.com`;
- bundle and package ids and URL schemes: `com.videomk.app`, `com.videomk.app://auth/callback`;
- AWS and other resource names: `videomk-qa-...`, `videomk/qa/deletion_key`, `/videomk/feedback_email_to`;
- code: variables, i18n keys (`wm.mode.videomk`, `videos.videomk`), the watermark mode id `"videomk"`, storage keys, header values (`X-Forwarded-By: videomk`), file and folder names.

A sentence that quotes a URL or an email keeps the address lowercase and the name capitalised: "Write to VideoMK at hello@videomk.com".

### Checks that hold the rule

| Area | Check | Run |
|---|---|---|
| Web | `frontend/src/lib/brand.test.ts` | `cd frontend && npx vitest run src/lib/brand.test.ts` |
| iPhone | `mobile/ios/scripts/check_brand.py` | `python3 mobile/ios/scripts/check_brand.py` |
| Backend | `backend/tests/test_brand_name.py` (string literals; comments are not checked) | `.venv/bin/python -m pytest backend/tests/test_brand_name.py -q` |
| Android | to add with the Android sweep (a unit test over `res/values*/strings*.xml`) | |

Each allows the identifier forms above and fails on any other spelling.

## 2. The logo

**B1 "Action"**, chosen by the owner on 27 Nov 2026. It replaces the Sparklet Trio (three sparks), which is no longer used anywhere.

- **The mark:** one rounded play triangle with two four-point stars above its tip, the second 0.66 of the first. No letters. ONE geometry at every size: the second star is never dropped and there is no simplified small version. The stars are never used without the play.
- **Colour:** white on the action gradient `#3B36C8` to `#7A4BE6`. The dark-appearance app icon is the Midnight ink tile (`#151828` to `#06070D`) with a violet play (`#6360FF` to `#B56CFF`), a cyan big star (`#7CEBFA` to `#22D3EE`) and a pale small star (`#E9E8FF`); it is used only as that icon. Without a tile the mark is gradient ink on light, white on dark, or one colour.
- **Wordmark:** "VideoMK" in Inter (SIL Open Font License), "Video" at weight 600, "MK" at 800, tracking -18/1000, one colour (`#0B0C14` on light, `#F4F5FA` on dark, white on the gradient and over video). Outlines, not live text, in every logo file.
- **Lockups:** horizontal (mark, then word) and stacked (mark above word), each with the tile or with the bare mark, for light and dark backgrounds, plus white-only and black-only. The word's cap-height band is centred on the play (not on the mark's box: the stars lift it).
- **Clear space:** half the mark's height on every side (half the tile's side for the tile). Inside the lockup the gap is fixed: half the cap height after the bare mark, 0.3 of the tile's side after the tile.
- **Minimum size:** app icon 29 pt, favicon 16 px, bare mark 16 px tall, lockup 20 px tall (tile or mark height). Under 20 px use the mark without the word.

**Files:** masters in `docs/brand/final/` (mark, icons light / dark / tinted, Android layers, lockups, favicon), store uploads in `docs/brand/store/`; the list and what each is for is in `docs/brand/README.md`. Everything is made by `docs/brand/final/build_final.py`, which also writes the copies the iPhone app, the Android app, the site and the sign-in page use; the watermark art is then rebuilt with `backend/scripts/watermark_assets.py`. Never edit a copy by hand: change the builder and run it.

**Where it is applied:** iPhone (`AppIcon` with light, dark and tinted appearances, `BrandMark`, `Lockup`), Android (adaptive icon: foreground, gradient background, monochrome layer for themed icons; `LogoMark` draws the same layers), web (`favicon.svg`, `favicon.ico`, `apple-touch-icon.png`, `icon-192/512.png`, `og.jpg`, header lockup, sign-in page, 404 page), the video watermark and its lockup (`backend/lambdas/engine/assets/watermark/`), the Cognito sign-in page (`backend/login_branding/`). The "New video" glyph in the apps (a play with ONE sparkle) is an interface icon, not the logo, and stays as it is.

## 3. Colour

From `docs/DESIGN_BAR_2026.md` section 4 (the tokens are the source; this is the brand's subset).

| Role | Value | Use |
|---|---|---|
| Action gradient | `#3B36C8` to `#7A4BE6` | The logo tile and the app icon; the one primary button per screen; the Create button |
| Brand gradient | `#2B2F9A` to `#6A3FC4` | Making card (it was the old logo's tile) |
| Primary | `#4B45E0` (light), `#AAA8FF` (dark) | Links, selection |
| Live | `#22D3EE` | Only on the gradient or on dark. Never on white (1.7:1) |
| Ink / paper | `#0B0C14` / `#F7F7FA` | Wordmark and text on light; page |
| Night / text on dark | `#06070D` / `#F4F5FA` | Page and wordmark on dark |

White on the action gradient is 5.3:1 at its lightest point; keep any mark or text on a brand surface at 4.5:1 for text and 3:1 for shapes.

## 4. Don'ts

- Do not write the name any other way than VideoMK, and do not capitalise an identifier (`VideoMK.com` is wrong).
- Do not put letters in the mark, use the stars without the play, drop or resize the second star, or add a star colour (outside the dark app icon), glow, outline or shadow to the mark (the watermark's soft shadow is the engine's, for legibility over video).
- Do not recolour, stretch, rotate or round the icon art; do not place the colour mark on a busy photo (use the one-colour white version).
- Do not use red tiles, four-colour triangles or a blue-to-purple lone sparkle: they belong to YouTube, Google Play and Gemini.
- Do not set the wordmark in another typeface, in all caps, or with a colour split between "Video" and "MK".

## 5. Places outside the repo where the name must be typed, or the logo uploaded, by hand

App Store Connect (app name and subtitle, the "videomk: AI Video Maker" style name, promotional text, description, keywords are free), Google Play Console (app name, short and full description), Google Cloud OAuth consent screen (app name), Apple Developer Services ID description (shown on "Sign in with Apple"), the Cognito managed login page (title and any text set in the console), SES / mailbox sender display names, social profiles, TestFlight "What to Test" text.

The logo is uploaded by hand in: App Store Connect (the icon travels with the build; nothing to upload unless a listing asks for it: `docs/brand/store/videomk-app-store-icon-1024.png`), Google Play Console, Store listing (App icon `videomk-play-store-icon-512.png`, Feature graphic `videomk-play-feature-graphic-1024x500.png`), Google Cloud console, OAuth consent screen (App logo `videomk-google-consent-logo-120.png`), social profiles (`docs/brand/final/icon-1024.png`; link previews `videomk-og-1200x630.jpg`).
