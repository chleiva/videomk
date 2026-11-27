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

**Not chosen yet.** Six play + star options are with the owner: `docs/brand/2026-11-27-play-star/` (recommendation: A "Create"; runner-up: B "Midnight"). Until he picks, the mark in the apps, the site, the stores and the watermark stays the Sparklet Trio in `docs/brand/final/` (rules in `docs/brand/README.md`). When he picks, this section gets the files, the construction and the sizes, and the watermark lockup is rebuilt with the new wordmark (`backend/scripts/watermark_assets.py`).

Rules that already hold whichever option wins:

- The mark is a play triangle with a star. No letters in the mark. The star is never used alone.
- Wordmark: "VideoMK" in Inter (SIL Open Font License), "Video" at weight 600, "MK" at 800, tracking -18/1000, one colour. Outlines, not live text, in every logo file.
- Clear space: half the mark's height on every side; in the lockup, half the cap height between mark and word is fixed.
- Minimum size: app icon 29 pt, favicon 16 px, lockup 20 px tall. Under 20 px use the mark without the word.

## 3. Colour

From `docs/DESIGN_BAR_2026.md` section 4 (the tokens are the source; this is the brand's subset).

| Role | Value | Use |
|---|---|---|
| Action gradient | `#3B36C8` to `#7A4BE6` | The one primary button per screen; the Create button |
| Brand gradient | `#2B2F9A` to `#6A3FC4` | Logo tile today, Making card |
| Primary | `#4B45E0` (light), `#AAA8FF` (dark) | Links, selection |
| Live | `#22D3EE` | Only on the gradient or on dark. Never on white (1.7:1) |
| Ink / paper | `#0B0C14` / `#F7F7FA` | Wordmark and text on light; page |
| Night / text on dark | `#06070D` / `#F4F5FA` | Page and wordmark on dark |

White on the action gradient is 5.3:1 at its lightest point; keep any mark or text on a brand surface at 4.5:1 for text and 3:1 for shapes.

## 4. Don'ts

- Do not write the name any other way than VideoMK, and do not capitalise an identifier (`VideoMK.com` is wrong).
- Do not put letters in the mark, use the star alone, or add a second star colour, glow, outline or shadow to the mark (the watermark's soft shadow is the engine's, for legibility over video).
- Do not recolour, stretch, rotate or round the icon art; do not place the colour mark on a busy photo (use the one-colour white version).
- Do not use red tiles, four-colour triangles or a blue-to-purple lone sparkle: they belong to YouTube, Google Play and Gemini.
- Do not set the wordmark in another typeface, in all caps, or with a colour split between "Video" and "MK".

## 5. Places outside the repo where the name must be typed by hand

App Store Connect (app name and subtitle, the "videomk: AI Video Maker" style name, promotional text, description, keywords are free), Google Play Console (app name, short and full description), Google Cloud OAuth consent screen (app name), Apple Developer Services ID description (shown on "Sign in with Apple"), the Cognito managed login page (title and any text set in the console), SES / mailbox sender display names, social profiles, TestFlight "What to Test" text.
