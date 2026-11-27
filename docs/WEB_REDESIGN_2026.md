# videomk web redesign 2026: audit, parity and design spec (marketing site + web app)

Date 2026-11-27. Stage 1 of 2: audit and spec only. Nothing under `frontend/`, `backend/` or `mobile/` was changed, nothing committed or deployed.
Owner brief: a FULL web application at videomk.com with everything the iOS and Android apps do; world-class, minimalist, Apple-inspired design for the web app AND the homepage ("the homepage looks really crap"). Owner decisions received during the work: the app lives on the **subdomain app.videomk.com**; the homepage hero shows **rich, inspiring sample videos, each together with the prompt that made it**.

How to read the evidence labels: **VERIFIED** = measured or read in this session (screenshots, curl, code). **SECONDARY** = a web article or general product knowledge, not a primary page. **UNVERIFIED** = needs a check before relying on it.
Evidence folder: `docs/web_2026/evidence/` (real captures, JPEG, of the live site and of the built app with mocked API data and a fake sign-in token), `docs/web_2026/mockups/` (26 redesign mockups, light and dark, desktop 1440 and phone 390), `docs/web_2026/src/` (generator `gen.py`, `snap.mjs`, and the capture harness `shoot.mjs`). Full capture set (52 screenshots, 4 breakpoints) is in the session scratchpad `.../scratchpad/webaudit/shots/` (temporary).

---

## 0. The three findings that change the plan (read first)

1. **There is no web app on the internet.** videomk.com is a static "public pages" site (`backend/site_stack.py`, `backend/scripts/site.sh build` copies only privacy, terms, support, delete-account, the hand-written `frontend/site-pages/index.html` and the CSS). The app screens exist in `frontend/src/pages` and build to `frontend/dist`, but they are never uploaded. VERIFIED by curl on 2026-11-27: `/signin/index.html`, `/generations/index.html`, `/auth/callback/index.html`, `/signin`, `/generations`, `/auth/callback` all answer **404**; `/`, `/privacy`, `/es/` answer 200.
2. **Web sign-in cannot work on prod today, for two more reasons even once the pages are uploaded.** (a) `frontend/src/lib/auth.ts` sends `redirect_uri=https://videomk.com/auth/callback/index.html`, while the prod Cognito web client allows only `https://videomk.com/auth/callback` (registered today in `backend/stages.json`): VERIFIED `redirect_mismatch` from `https://login.videomk.com/oauth2/authorize?...`. (b) `frontend/src/lib/config.ts` defaults the API to `https://api.videomk.com`, which has **no DNS record** (`dig` empty); the prod API is `https://7ol62ca7j5.execute-api.us-west-2.amazonaws.com/prod/` and `PUBLIC_API_BASE`, `PUBLIC_COGNITO_CLIENT_ID` are not set by any build script I found (`site.sh` sets none). The mobile client on the same pool does redirect to Google correctly (VERIFIED), so Cognito and Google are fine; the web build and hosting are what is missing.
3. **There are two homepages and neither is good.** The live one is a separate hand-written file (`frontend/site-pages/index.html`: old lightning-bolt mark, "The iPhone and Android apps are coming soon" although both are in TestFlight/Play testing, no video, no sample, no way into the app). The Astro `Landing.astro` (prompt box + three example chips) is the better draft but is not what is published. Both are in `docs/web_2026/evidence/` (`live_home__*`, `local_home__*`). Sign-in still shows the old bolt mark too (`signin__d1440__light__en.jpg`).

Consequence: the first deliverable is not a redesign, it is **hosting, auth wiring and a clean split of the marketing site from the app** (work package 0, section 11), then the new design on top.

---

## 1. Audit of the current frontend (VERIFIED unless marked)

Stack: Astro 5 + React 19 islands + Tailwind 4; 18 static pages; `dist` is 832 KB; the React client chunk is 179 KB (about 57 KB gzip, SECONDARY estimate), the i18n chunk 43 KB (both languages bundled), CSS 41 KB. Tokens are good and shared with mobile (`src/styles/tokens.css`, contrast test in `tokens.test.ts`), dark mode exists (system + footer switch). 142 vitest tests pass. Performance is not the problem; design and completeness are.

Measured on the built pages at 1440 px with mocked data (`shoot.mjs`): visible words / interactive controls.

| Page (state) | Words | Controls | What the eye gets |
|---|---|---|---|
| Live homepage | 114 | 7 | Bolt logo, headline, paragraph, a pill saying "coming soon", three step cards. No video, no sample, no CTA into the app |
| Astro landing (unpublished) | 143 | 19 | Prompt box, 3 chips, steps, cookie toast covering step 3 |
| Videos (list, 6 items) | 143 | 26 | Every ready card carries an "Edit video" button; the Making card takes one third of a row |
| **Create (modal)** | **239** | **49** | Prompt, a 4-line presentation drop zone, 3 example chips, 4 platform chips, 9 length chips, then (below the fold) format, quality, captions, language, narration, "why does it cost" |
| Credits | 101 | 15 | Hero number, buckets, "How credits work" prose, "coming soon" notice |
| Feedback | 88 | 19 | Form plus the full footer |
| Watch | 59 | 18 | Edge-to-edge black band, title, Share, Save, "Make another video" card, feedback link |
| Sign-in | 41 | 14 | Bolt mark, headline, one button (Google and Apple are build-flag OFF), full footer |

Problems with evidence:

1. **Create is a form, not a prompt box.** 239 words and 49 controls (table). The same decision is asked more than once (platform implies format, length and resolution; they are then asked again). On phone the sheet opens over a header that has wrapped to two lines (`app_create__p390__light__en.jpg`). The presentation drop zone sits above the options and pushes everything down.
2. **No app shell.** Navigation is three text links in the header that wrap and collide with the logo at 390 px (`app_generations__p390__dark__en.jpg`); no sidebar, no tab bar, no persistent "New". Every app screen also carries the marketing footer (8 links, language switch, theme switch).
3. **The video list is a gallery of gradients with buttons.** Ready videos show a purple placeholder when no preview exists and an "Edit video" button on every card (clutter; the apps put edit behind the detail screen). Sections are labelled in small caps ("YESTERDAY", "EARLIER").
4. **The player page wastes the moment.** A full-bleed black band, title "Untitled" while loading, three actions and a feedback link; no prompt, no scenes, no re-make. (Captured with the video blocked by my mock, the layout is still visible.)
5. **Credits explained in prose** (four sentences) and a permanent "coming soon" notice.
6. **Two visual systems.** Marketing: pale pastel blobs; app: gradient buttons plus cards with several shadows; the mobile apps have just been redesigned toward subtraction (`docs/UX_2026_REDESIGN.md`). Typography starts with Inter then system; Apple devices should get SF Pro first for the Apple look the owner wants.
7. **Stale brand**: lightning-bolt tile on the homepage and sign-in; the Sparklet Trio mark is only in the app header/favicon (commit ff97226).
8. **Accessibility debt** (partly code reading): header nav wraps; cookie toast overlaps content; the grid/list switch is hidden under 768 px; nothing is wrong with contrast (tokens are tested), focus rings exist.
9. **Static i18n done twice**: `data-i18n` DOM patching in the layout and React `useLocale`, both reading the same JSON (works, but a source of flashes and untested edges).
10. **Legacy and dead routes**: `/questions` (calls an API "not served by this repo's backend", 404 in the capture) and `/edit` reachable only from the card button.

What is good and must survive: the headline "Describe it. We'll make the video." (we keep its spirit), the gradient Making card with four stages, the credit pill, the tokens and their contrast tests, dark mode, EN/ES parity, the legal pages and their content, the `lib/*` API client and its tests.

---

## 2. Feature parity: web today vs iPhone and Android

Source: `frontend/src`, iOS `mobile/ios/VideoMK/*.swift`, Android `ui/*.kt`, `docs/CREATE_API.md`, `docs/MEDIA_LIBRARY.md`, `docs/DECK_TO_VIDEO.md`.

| Capability | iOS | Android | Web today | Web target |
|---|---|---|---|---|
| Sign in with email code | yes | yes | yes (hosted UI) | yes |
| Sign in with Google / Apple | yes (flags) | yes (flags) | coded, build flag OFF | **Google ON in prod**, Apple when credentials exist |
| Videos list, making progress, errors | yes | yes | yes | yes, redesigned (thumbnails, search) |
| Create: prompt, platform, length, aspect, resolution, captions, language | yes | yes | yes | yes, as prompt box + 3 pills + one Options popover |
| Request check questions (brief) and safety stop | yes | yes | yes (`QuestionsStepper`) | yes, as a sheet |
| Photos in a video (up to 100) | yes | yes | **no** | yes (drag and drop, paste, My media) |
| **My media library**: upload, search ("Thailand 2024"), places/years, collections, smart organise, select, delete, make a video | yes | yes | **no** | yes (section 6.4) |
| Presentation (pptx/pdf) to video | yes | yes | yes (`DeckPicker`) | yes, an attach icon in the composer |
| Dictation (voice prompt) | yes | yes | **no** | optional: Web Speech API where supported (SECONDARY: Chrome/Safari yes, Firefox no), hidden elsewhere |
| Player: play, captions, fullscreen, share, save | yes | yes | basic `<video controls>` | custom minimal controls (6.3) |
| Share / download | yes | yes | share + save | Share (Web Share API, copy link) + Download |
| Editor: scenes, narration, candidates, re-render | yes | yes | yes (`Editor.tsx`) | yes, restyled, two-pane |
| Credits / wallet | yes | yes | yes | yes, short |
| Buy credits | not yet | not yet | not yet | not yet (coming with store work) |
| Settings (language, photo dates/locations, organise preference, about) | yes | yes | **no** (language/theme in the footer) | yes (6.6) |
| Feedback | yes | yes | yes | yes |
| Rating prompt | yes | yes | n/a | n/a (a "Share what you think" link only) |
| In-app account deletion with re-auth | yes | yes | **page of text only** | yes (flow `docs/ACCOUNT_DELETION.md`, web variant exists as `web_return_url`) |
| Notifications / Live Activity | planned | planned | n/a | optional: browser notification when a video finishes (permission asked only after the first Create) |
| 4K option | yes | yes | yes (capability driven) | yes |
| Spanish UI | yes | yes | yes | yes |
| Publish to YouTube/TikTok/etc. | planned (`docs/SOCIAL_PUBLISHING_RESEARCH.md`) | planned | no | same plan, share first |

Missing on web, in priority order: (1) media library and photo upload (largest), (2) settings, (3) in-app account deletion, (4) dictation, (5) notifications, (6) Google/Apple sign-in switched on.

Browser upload design (the part with no precedent in the repo): the API is the same as mobile (`POST /library/uploads` with `{size, sha256, taken?, lat?, lon?}` x 1..100, then `POST` of the returned presigned `fields` + `file` to S3; links live 15 minutes; the S3 CORS rule for POST is already derived from the web origins, `backend_stack._web_origins`). Web rules: drag and drop onto the page, "Add photos" button (`<input type=file multiple accept="image/*">`), paste, optional folder (`webkitdirectory`); SHA-256 with `crypto.subtle.digest` over `file.arrayBuffer()` (photos are small; process in a worker so the UI stays responsive); concurrency 4; per-file retry with backoff; one aggregate progress (the apps' upload journey); resumable by re-listing, duplicates are answered by the server (`status: duplicate`); EXIF taken-date and GPS read client-side with a tiny library only when the "use photo dates/locations" settings are on (same toggles as mobile); **HEIC**: Chrome and Firefox cannot decode HEIC, so either convert in the browser (lazy-loaded decoder, about 1 MB, only when a HEIC file is picked) or confirm the backend accepts HEIC as is: **UNVERIFIED, an open question for the media package**. Thumbnails come from the API (`thumb_url`), cached by id; the grid is a virtualised justified/square grid with `loading="lazy"` and `decoding="async"`.

---

## 3. Research: what the best sites and web apps do in 2026

Honest scope: web search in this session returned generic 2026 SaaS-design roundups, not teardowns of Apple, Linear, Runway or Luma (so statements about those products below are from general product knowledge, **SECONDARY, not re-verified today**). Core Web Vitals thresholds were confirmed as unchanged: LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 at the 75th percentile (web.dev, VERIFIED via the search results). WCAG 2.2 target-size minimum 24x24 CSS px (criterion 2.5.8) is from general knowledge, UNVERIFIED this session.

What the evidence and the usual practice agree on, applied to us:

- **Homepage**: one promise, one action, then proof. A muted, looping short clip near the top works when the product's value is visual (SECONDARY: the roundups say exactly this); longer demos sit behind a click. Our product is visual, so the hero is a video; the prompt that made it sits beside it, because the prompt-to-video link IS the product explanation.
- **Apple-style site**: very large tight headings (56 to 72 px, -0.035 em), one accent colour, a lot of whitespace, glass sticky nav (blur 20 px, saturate 180 %), pill buttons, big rounded media cards, sections alternating background and surface-2, no decorative blobs, scroll-linked fades only (no parallax games).
- **AI creation tools (Runway, Luma, Sora-style)**: the prompt box is the page; settings are a single compact pill that opens a popover; results are a grid of thumbnails with hover preview; the library and the composer share one shell with a left rail on desktop and a bottom tab bar on phone.
- **Video player**: native `<video>` with custom, minimal chrome: play, scrubber with time, captions, fullscreen; auto-hide after 3 s; keyboard Space, K, J/L, F, C, arrows; Picture in Picture and speed behind a menu.
- **App shell**: left rail with 4 destinations (Videos, Media, Credits, Settings) plus a prominent "New video"; a command palette (Cmd/Ctrl-K) for power users, not required for v1.
- **Typography**: system stack with SF Pro first on Apple devices (`-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text"`), then Inter if installed, then system-ui. No webfont download on the marketing site; Windows/Android get Inter only if we self-host one 30 to 40 KB variable subset (decision in 7).
- **Performance**: static HTML with zero JavaScript on the marketing site; hydrate only the app. Hero video is never preloaded; poster first; autoplay only after LCP and only when allowed.

---

## 4. Design principles (shared with mobile, `docs/UX_2026_REDESIGN.md` section 2)

1. One screen, one job, one primary action (a gradient pill; everything else is quiet).
2. Say it once; the button carries the price (`Create · 5 ⚡`).
3. Icon-only for universal icons (share, download, more, close, back, plus, mic, photo, play, captions, fullscreen), with accessible labels and tooltips; menus for 4 or more choices; chips for 3 or fewer.
4. Smart defaults decide: the platform sets format, length, resolution; the AI sets look, voice, music, language, pace.
5. Two layers only: the surface (prompt + pills) and ONE options popover; explanations live in an (i) popover.
6. Content is the interface: thumbnails and video get the pixels; chrome is glass and recedes.
7. Text budget per screen is a requirement and is tested (section 9).
8. Same tokens, same names, same words as the apps; web may use more space, never more options.
9. Spanish is +20 to 30 % wider: no layout may depend on one line except tab labels.
10. Every feature stays reachable; only clutter goes.

## 5. Shared design tokens (web = mobile)

Keep the semantic names and values of `src/styles/tokens.css` (they equal `Theme.swift`/`Theme.kt` and `docs/ux_2026/tokens.css`); changes below are additions for the web, to be mirrored in the app tokens file by the UX packages.

| Token | Value (light / dark) | Note |
|---|---|---|
| `--background` | `#fbfbfd` / `#07091a` | web only slightly lighter/darker than the app's `#f6f7fc`/`#0a0d1f`; the app keeps its values. Decision: use the app's values everywhere to stay ONE system unless the owner prefers the whiter Apple look in the mockups |
| `--surface`, `--surface-2` | `#fff`,`#f2f3f8` / `#10142b`,`#181d3a` | cards on background, sections on alternating background |
| `--text`, `--text-secondary`, `--text-tertiary` | `#11142b`,`#565d78`,`#6a7090` / `#f3f4fb`,`#a2a9c5`,`#8f97b6` | tertiary is at least 4.5:1 on surface (re-run the token test) |
| `--primary` | `#4f52e0` / `#9ea0ff` | links, selected chips, focus |
| `--gradient-start/end` | `#5b5ef0`/`#8452f4` (dark `#8f92ff`/`#ae8aff`) | only the primary pill, the mark tile, the Making card |
| `--making-start/end` | `#2b2f9a`/`#6a3fc4` | Making card, the logo tile |
| `--live` | `#22d3ee` | only "alive" progress; never on light surfaces |
| Type | `-apple-system, "SF Pro Display", "SF Pro Text", Inter, system-ui, sans-serif` | marketing display 72/56 px, h2 44/32, lead 22/18, body 17/16 (web 17 px, phone 16); app title 32/28, body 15 to 17; never below 14 px; tracking -0.035 em on display, -0.02 em on titles |
| Radii | field 12, thumb 14, card 22, composer 28, sheet 30, pill 999 | cards 22 on web (mobile video card 22 too) |
| Spacing | 4 px base; marketing section padding 96 px (56 phone); app gutter 40 desktop, 16 phone | |
| Elevation | hairline `0 0 0 1px --line` + one soft shadow `0 12px 40px rgba(40,44,110,.10)`; dark swaps the shadow for a 1 px ring | at most one shadow per card, none on list rows |
| Glass | `rgba(251,251,253,.78)` + `backdrop-filter: saturate(180%) blur(20px)` / dark `rgba(7,9,26,.72)` | sticky nav, tab bar, floating selection bar, player controls |
| Motion | 120 press, 200 selection, 280 insertions, 380 sheets; ease `cubic-bezier(.2,.8,.2,1)`; reduced-motion: fades <= 120 ms, no autoplay, no scale | |
| Target size | 44 px | WCAG 2.2 minimum is 24 px; we exceed it |

## 6. Information architecture, sitemap and per-page design

### 6.1 Sites and URLs

- **videomk.com (marketing, static, zero JS)**: `/` and `/es/` (home), `/privacy`, `/terms`, `/support`, `/delete-account` (info), `/es/*` equivalents, `/sitemap.xml`, `/robots.txt`. Optional later: `/gallery`, `/pricing`, `/formats` as anchors of the home page first (no new pages until there is content). CTAs: **Open the app** and **Try this prompt** go to `https://app.videomk.com`.
- **app.videomk.com (the web app, React islands)**: `/` Videos (library, signed in; a signed-out visitor is sent to `/signin`), `/new` Create (also a modal route from anywhere), `/watch?id=` video, `/edit?id=` editor, `/media` My media (+ `/media/collections`), `/credits`, `/settings`, `/feedback`, `/signin`, `/auth/callback`, `/delete-account` (in-app flow). Clean URLs through the existing CloudFront rewrite function (adds `/index.html`), so links are written without `index.html` (the current code writes `/generations/index.html`, which is ugly and is the root of the redirect-uri bug).
- **Old URLs**: `videomk.com/generations`, `/signin`, `/wallet`, `/feedback`, `/watch`, `/edit`, `/auth/callback` answer 404 today; add a CloudFront Function 301 to the same path on app.videomk.com (covers old emails, store listings and anything shared). `/es/` stays on the marketing domain; the app picks the language from the account or the browser (same rule as mobile `X-Locale`).

**Why a subdomain (owner decision, with reasons for the record):** independent deploys (the marketing site ships without risking the app and vice versa); security isolation: tokens live in the app origin's localStorage, so the marketing site (which must stay script-free for Google verification and simplicity) shares no storage or cookies with it, and the app can carry a strict CSP; OAuth hygiene: one callback origin (`https://app.videomk.com/auth/callback`) and one logout origin, no `index.html` suffixes; caching: marketing assets cache for a year, app shell revalidates; analytics or experiments on marketing can never touch auth. Cost: one more CloudFront distribution and certificate (cents per month).

### 6.2 App shell (all signed-in pages)

Desktop >= 900 px: left rail 232 px (mark + wordmark, Videos, Media, Credits, Settings; bottom: credit pill and account), content max 1180 px, **New video** pill top right of the list page. Phone: bottom glass tab bar with five items (Videos, Media, New, Credits, Settings), no rail, no footer. The footer links (Privacy, Terms, Support) move into Settings. Mockups: `videos__desktop__light.jpg`, `videos__phone__dark.jpg`.

### 6.3 Pages (mockups in `docs/web_2026/mockups/`)

| Page | Design | Text budget (visible words besides user content) | Mockups |
|---|---|---|---|
| **Home (marketing)** | Sticky glass nav (logo, Gallery, Formats, Pricing, Help, Sign in, Open the app) -> hero: headline, 1 sentence, prompt pill with Create -> big hero player with its prompt and "Try this prompt" -> "One sentence in. Any style out." sample grid (4 more samples, each with prompt + Try) -> "For every screen" format pills -> three steps -> credits teaser -> three FAQs -> footer with company and registration | 190 | `home__desktop__light/dark`, `home__phone__light/dark` |
| **Sign in** | Split: left a full-height sample frame with its prompt (phone: below), right: Welcome, Google, Apple, email, one legal line | 25 | `signin__*` |
| **Videos** | Rail + grid of 16:9 thumbnails (real preview frames), title and "2 h ago" under each, duration chip, hover = muted preview; Making card first with 4 segments and ETA; search pill; no per-card buttons (card click opens; the "..." menu on hover holds Edit, Share, Delete) | 6 | `videos__*` |
| **Create** | Centered: "What should we make?", one composer card: text area, icon buttons (photos, presentation, dictate), ONE pill `YouTube · 5 min · 1080p` that opens the Options popover (made for, length, quality, captions; voice, music and style are AI decisions, "Change them later in the editor"), primary `Create · 5 ⚡`. Three suggestion pills underneath (prompts of the gallery). On phone the CTA is full width above the keyboard | 14 surface, 40 in Options | `create__*`, `create_options__desktop__*` |
| **Watch / Player** | Two columns: 16:9 player with minimal glass controls (play, scrubber + time, captions, fullscreen; auto-hide 3 s), title, meta line (`1:31 · 1080p · English · 4 credits`), Share (primary), Download, "..." (Edit, Delete). Right: **The prompt** + "Make another version", then **Scenes** (thumbnail, name, time; click seeks). Phone: single column | 14 | `player__*` |
| **Media** | Search ("Thailand 2024"), chips (All, years, places, Collections), square grid, drop-anywhere upload, floating selection bar (Make a video, Add to collection) | 8 | `media__*` |
| **Editor** | Two panes: scene list left (thumbnails), scene form right; restyle only, behaviour unchanged | 30 | not mocked (restyle) |
| **Credits** | Big number card, one line "1 credit = up to 1 minute", buckets as rows, (i) popover for the rules | 18 | not mocked |
| **Settings** | Rows: Language, Appearance, Photo dates, Photo locations, Organise after upload, Feedback, Privacy, Terms, Support, Sign out, Delete account; explanations in (i) | 30 | not mocked |
| **Feedback** | One text box, one button | 14 | not mocked |

Component list (build once, in `src/components/ds/`): `Button` (primary/tonal/ghost/icon), `Pill` and `PillMenu`, `Chip` (check glyph when selected), `Segmented`, `Popover`, `Sheet` (modal with focus trap, ESC, one close), `Toast`, `Card`, `VideoCard`, `MakingCard`, `MediaTile`, `Tabbar`, `Rail`, `Player` (own controls, keyboard map), `EmptyState` (title + action), `Skeleton`, `Toggle`, `Field`, `InfoPopover`, `Kbd` hint. Each with light/dark and focus-visible states; icons as one inline SVG sprite (no icon font), the same glyph set as the mockups.

Keyboard shortcuts (app): `N` new video, `/` search, `G` then `V`/`M`/`C` go to Videos/Media/Credits, `?` shortcut sheet; player: Space/K play, J/L -10/+10 s, left/right -5/+5 s, F fullscreen, C captions, M mute. Cmd/Ctrl-K palette: later.

Responsive: breakpoints 390 (phone), 820 (tablet: rail collapses to icons), 1280, 1440 (content max 1180 centered). Grids use `auto-fill, minmax(250px,1fr)` (2 columns on phone).

## 7. Homepage: hero concept, samples, copy

### 7.1 Hero set (5 to 6 samples, each shown WITH its prompt)

Rule (owner): rich in media, inspiring, beautiful, showing what the platform can do; the prompt text sits beside or under the player; "Try this prompt" opens the app with the prompt filled (signed-out: stored in `sessionStorage`, restored after sign-in). The prompt shown must be the real prompt that produced the video (store it with the sample file).

Hero cut vs full length: the hero player autoplays a muted, looped **15 to 30 s cut** (720p, 24 fps, H.264, about 1.2 Mbit/s, target <= 4.5 MB) after LCP and only when `prefers-reduced-motion` is not set and the connection is not "save-data"; a click plays the **full video with sound** (1080p, CRF 24, about 12 MB for 90 s, streamed from the same CloudFront bucket, `preload="none"`). Posters are WebP <= 70 KB (hero) and <= 35 KB (grid).

| # | Topic and prompt (shown verbatim) | Length, aspect | Media shown | Status and cost to produce |
|---|---|---|---|---|
| 1 (hero) | "How a forest breathes, for curious teenagers" | 1:31 (cut 0:04 to 0:32), 16:9 | Gemini library clips (10), stat and list elements, narration, music | **Exists** (`.../scratchpad/fulltest/forest_full.mp4`, made with the real QA pipeline). Cost already spent ($0.32 run + clips). Re-make once the library has 8 to 10 s clips so it needs no prompt workaround: about $0.35 |
| 2 | "A day in Lisbon: the sights, the light, the food" (photo-rich) | 1:00, 9:16 | Licensed photos (Unsplash/Wikimedia via the pipeline) in collages and Ken Burns, kinetic captions | New on QA, about $0.30 to $0.45 (plan $0.25, narration $0.05, image checks) |
| 3 | "How €100 grows over 30 years with compound interest" (data) | 0:45, 1:1 | Counter (after the counter fix), animated chart, bar race, ranking | New, about $0.30 (no clips) |
| 4 | "Five habits that help you sleep better" (type-led) | 0:45, 9:16 | Animated gas backgrounds (needs the backgrounds library, `docs` prototype in progress) + kinetic text | New, after backgrounds ship behind their flag; about $0.30 |
| 5 | "A slow, soothing story about a lighthouse keeper" (illustrated) | 1:30, 16:9 | Layered vector scenes with parallax (prototype in progress) or catalog illustrations with Ken Burns if the prototype is not ready | New; $0.40 for 1:30; the vector prototype's spend is separate |
| 6 | "Turn our Q3 product update deck into a one-minute video" | 1:00, 16:9 | A real sample deck (generated by `backend/scripts/deck_demo.py`), slides + narration | New, about $0.30 |

Total to produce: **about $2 to $3 (cap $4 with re-runs)** on QA, all through the real pipeline (nothing mocked), plus the one-time encode (free, local ffmpeg). The page ships with the forest video as hero and samples 2 to 4 as soon as they exist; until then the grid shows only the samples that are real (no placeholders, no fake videos).

### 7.2 Copy (short, no hype)

EN: nav: Gallery · Formats · Pricing · Help · Sign in · **Open the app**. Hero: **Describe it. Get the video.** / Type or say an idea. videomk writes it, narrates it and adds pictures, clips and music. Ready in minutes. / [How do bees make honey?] **Create** / Free to start · 5 credits on sign-up · no card. Under the player: THE PROMPT / "How a forest breathes, for curious teenagers" / **Try this prompt**. Grid title: **One sentence in. Any style out.** / Every video below came from a single prompt. Tap Try to make your own version. Formats: **For every screen** / Pick where it will play and videomk sets the format, length and resolution for you. Steps: Say it · One sentence, a few photos or a presentation. / We make it · Script, voice, pictures, clips and music, in minutes. / Share it · Edit any scene, then post or save it. Credits: **Simple credits** / 1 credit makes up to a minute of video. New accounts get 5 credits, plus 1 free every day. / **Start free**. FAQ: Who owns my videos? You do. Images and clips come from licensed sources or ones we create. Which languages? English and Spanish narration, in the app and on the web. Can I use my own photos? Yes, up to 100 per video, or a PowerPoint or PDF. Footer: Privacy · Terms · Support · Delete account · English · Español; A product of Agilegency Ltd · Registered in England, 16838077.

ES: Navegación: Galería · Formatos · Precios · Ayuda · Entrar · **Abrir la app**. Hero: **Descríbelo. Recibe el vídeo.** / Escribe o di una idea. videomk la redacta, la narra y añade imágenes, clips y música. Listo en minutos. / [¿Cómo hacen la miel las abejas?] **Crear** / Gratis para empezar · 5 créditos al registrarte · sin tarjeta. Bajo el vídeo: EL PROMPT / **Probar este prompt**. Rejilla: **Una frase entra. Cualquier estilo sale.** / Cada vídeo de abajo salió de una sola frase. Toca Probar para hacer el tuyo. Formatos: **Para cada pantalla** / Elige dónde se verá y videomk ajusta formato, duración y resolución. Pasos: Dilo · Una frase, unas fotos o una presentación. / Lo hacemos · Guion, voz, imágenes, clips y música, en minutos. / Compártelo · Edita cualquier escena y publícalo o guárdalo. Créditos: **Créditos sencillos** / 1 crédito da hasta un minuto de vídeo. Las cuentas nuevas reciben 5 créditos y 1 gratis cada día. / **Empezar gratis**. FAQ: ¿De quién son mis vídeos? Tuyos. Las imágenes y los clips vienen de fuentes con licencia o los creamos nosotros. ¿Qué idiomas? Narración en inglés y español, en la app y en la web. ¿Puedo usar mis fotos? Sí, hasta 100 por vídeo, o una presentación PowerPoint o PDF. (Spanish samples: the same videos in their Spanish version where they exist; otherwise the English ones with Spanish prompts are not allowed, because the prompt shown must be the real prompt. Plan one Spanish-language sample, "Cómo respiran los bosques, explicado a adolescentes", about $0.35.)

SEO and sharing (marketing): `<title>` "videomk: AI explainer videos from a sentence", meta description (150 chars), `hreflang` EN/ES + x-default (already in the sitemap), Open Graph/Twitter image 1200x630 from the hero poster, `VideoObject` JSON-LD for the hero (name, description = the prompt, thumbnailUrl, uploadDate, duration, contentUrl), `Organization` JSON-LD (Agilegency Ltd, logo), canonical URLs, `sitemap.xml` (exists), `robots.txt` (exists; the app host gets `Disallow: /`).

## 8. Performance, accessibility, security budgets

| Budget | Marketing (videomk.com) | App (app.videomk.com) |
|---|---|---|
| JavaScript | 0 KB external; at most 2 KB inline (hero play/autoplay, language remember) hashed in the CSP | initial route <= 130 KB gzip (React client about 57 KB + app code); Editor, Media and Player lazy-loaded; i18n split per language (today both languages ship, 43 KB raw) |
| CSS | <= 20 KB gzip, one file | <= 30 KB gzip |
| Fonts | system stack; optional single self-hosted Inter variable subset <= 40 KB, `font-display: swap`, only for non-Apple platforms | same |
| Images/video | hero poster WebP <= 70 KB preloaded; hero cut <= 4.5 MB after LCP; page weight before video <= 400 KB | thumbnails <= 40 KB each, lazy, `decoding=async` |
| Core Web Vitals (p75, mobile 4G) | LCP <= 2.0 s, CLS <= 0.05 | LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1 |
| Caching | assets immutable 1 year (hashed), HTML 5 min | same; `index.html` of the app `no-cache` |
| Security headers | exists (HSTS, nosniff, frame DENY, referrer); add CSP `default-src 'self'; media-src 'self' blob:; img-src 'self' data:; script-src 'self' 'sha256-...'` | CSP `default-src 'self'; connect-src 'self' API_ORIGIN https://login.videomk.com https://*.s3.*.amazonaws.com; img-src 'self' data: blob: https://*.s3.amazonaws.com <thumbnail origin>; media-src 'self' blob: <video origin>; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://*.s3.*.amazonaws.com`; tokens stay in localStorage (as today; XSS is the risk, hence the CSP, no third-party scripts) |

Accessibility (WCAG 2.2 AA): all colour pairs in `tokens.test.ts` stay >= 4.5:1 (tertiary text on surface-2 must pass; re-run); targets 44 px (2.5.8 minimum is 24 px: UNVERIFIED wording); focus never hidden by the sticky nav (2.4.11): `scroll-padding-top: 72px`; drag and drop always has a button alternative and scene re-ordering has move up/down buttons (2.5.7); sign-in needs no cognitive test (3.3.8: Google/Apple/email code); custom player is fully keyboard operable, captions on by default for the hero, `aria-live="polite"` for Making progress; one `<h1>` per page; skip link; `lang` per page; `prefers-reduced-motion` and `prefers-color-scheme` honoured; hero never autoplays with sound.

## 9. Test plan

1. **Screenshots**: `docs/web_2026/src/shoot.mjs` (Playwright core with the installed Chrome, API mocked, fake token) run for every page at 390, 820, 1280, 1440, light/dark, EN/ES; PNGs compared with the committed baselines (pixelmatch, 0.3 % tolerance) in CI; the mockups are the acceptance images.
2. **Text budget test** (vitest + jsdom or Playwright): counts visible words per page against the budgets in 6.3 and fails above +10 %; also fails if a primary gradient button appears twice on a screen.
3. **axe-core** (`@axe-core/playwright`) on every page, both themes, both languages: zero serious/critical violations; keyboard-only run of Create, Videos, Watch and Media.
4. **Lighthouse CI** on the marketing home (performance >= 95, accessibility 100, best practices >= 95, SEO 100) and on `/signin` of the app.
5. **Unit**: the existing 142 vitest tests must keep passing (`npm test` in `frontend/`; `legal.test.ts`, `tokens.test.ts`, `create.test.ts`, `i18n.test.ts`, `authUrl.test.ts` are the guards); new tests for the upload queue (hash, retry, duplicate, no_space), redirect URI builder (`/auth/callback`), i18n key parity EN/ES, number formatting.
6. **End-to-end on QA**: sign in with a test account, create a video, watch it, upload 20 photos, search them, make a video from them, delete the account (the QA test user list is in memory notes). Never run against prod with real accounts except the final smoke test by the owner.

## 10. Google OAuth brand verification (must stay satisfied)

The consent screen points at the marketing site: the homepage must be public (no sign-in wall), be on the verified domain videomk.com, show the app name exactly as on the consent screen ("videomk"), show the logo, explain what the app does and how it uses Google data (sign-in only: name, email), and link to the Privacy Policy and Terms visibly on the page; the privacy policy contains the Google API Services Limited Use sentence (already added 2026-11-26) and the contact (hello@videomk.com). These are Google's published requirements as I understand them; **UNVERIFIED in this session, re-check against the current Google page before submitting**. Design consequences: the new homepage keeps "videomk" + logo + a one-line description above the fold, privacy and terms links in the footer, no redirect from `/` to the app, no JavaScript needed to see the content, and `app.videomk.com` is added to the consent screen's authorised domains if Google asks for it (the OAuth redirect stays `https://login.videomk.com/oauth2/idpresponse`, so moving the app to a subdomain does not change the Google client).

## 11. Implementation plan (work packages)

### Work package 0: foundations (one agent, FIRST, blocks the others; about 1 day)

Infra and wiring for the subdomain, all in the prod account (464863885161), us-east-1 for the CDN:
1. New CDK stack `AppSiteStack` (new file `backend/app_site_stack.py`, wired in `backend/app.py` like `site_stack.py`): private S3 bucket + CloudFront with OAC, the same rewrite function and headers policy as the marketing stack plus the app CSP, SPA-safe error pages, **ACM certificate for `app.videomk.com` in us-east-1** (DNS-validated in the existing `videomk.com` hosted zone), **Route 53 A/AAAA alias records**, upload via `BucketDeployment` and invalidation.
2. `backend/stages.json` prod: `callbackUrls: ["https://app.videomk.com/auth/callback"]`, `logoutUrls: ["https://app.videomk.com/"]` (replaces today's `https://videomk.com/...` entries; keep `http://localhost:4321/auth/callback` only in `qa`); this also changes `web_return_url` for account deletion to `https://app.videomk.com/delete-account`. Redeploy prod (stack videomk-prod; the Cognito web client updates in place).
3. `backend/backend_stack._web_origins`: add `https://app.videomk.com` to the fixed set (S3 upload CORS for the media library) and a test in `tests/` (the existing CDK tests check CORS origins).
4. API domain: either set `PUBLIC_API_BASE` at build time to the execute-api URL (quick) or add an API Gateway custom domain `api.videomk.com` (regional cert in us-west-2 + Route 53) so `config.ts`'s default finally resolves; recommended: custom domain, so mobile and web share a stable URL.
5. `frontend/src/lib/auth.ts`: `redirectUri()` -> `${location.origin}/auth/callback` (no `/index.html`), `SIGNIN_PATH` -> `/signin`, internal links without `index.html`; `PUBLIC_API_BASE`, `PUBLIC_COGNITO_CLIENT_ID` (prod web client `55borf73gh37uka0t3vj965dkc`), `PUBLIC_AUTH_DOMAIN=https://login.videomk.com`, `PUBLIC_AUTH_GOOGLE=1` in the prod build script.
6. Split the Astro project in two builds from one repo (`astro.config.marketing.mjs`, `astro.config.app.mjs`, or one config with `APP_TARGET=marketing|app` choosing `srcDir`/page globs): marketing = zero-JS static pages; app = React islands. `backend/scripts/site.sh app` builds and deploys the app stack; `site.sh full` stays for marketing.
7. Redirects: a CloudFront Function on videomk.com 301-ing `/generations`, `/signin`, `/wallet`, `/feedback`, `/watch`, `/edit`, `/auth/callback` (and `/x/index.html`) to `https://app.videomk.com/...`.
8. Tokens and shell skeleton: update `src/styles/tokens.css` (font stack, radii, glass, gradient CTA rules) and `global.css`; create `layouts/MarketingLayout.astro` and `layouts/AppLayout.astro` (rail, tab bar, no footer); split `BaseLayout.astro`; keep all legal pages working; move i18n into per-area files (`i18n/marketing.*.json`, `i18n/app.*.json`) so the packages below never edit the same JSON.
9. Google consent screen: authorised domain `videomk.com`; no new redirect URI. (Owner action: console.)
10. Prod smoke test: sign-in through `https://app.videomk.com/signin` with email code and with Google; `/auth/callback` completes; Videos loads. Owner action: Search Console domain verification if not done.
Acceptance: curl shows 200 on `https://app.videomk.com/signin`, `redirect_mismatch` gone, `app.videomk.com` serves only the app, old URLs 301, `npm test` green, CDK tests green. Files owned by WP0 and not editable by others: `tokens.css`, `global.css`, `layouts/*`, `lib/auth.ts`, `lib/config.ts`, `backend/*`, `scripts/site.sh`.

### Work package A: marketing site (one agent, after WP0 layouts exist)

Files: `src/pages/index.astro`, `src/pages/es/index.astro`, `src/components/marketing/*` (Nav, Hero, HeroPlayer, SampleGrid, FormatPills, Steps, CreditsTeaser, Faq, Footer), `src/data/samples.ts` (prompt, length, aspect, poster, hero cut, full video URL), `public/samples/*` (encoded media, posters), `frontend/site-pages/*` (deleted: the home page is generated by Astro), `src/i18n/marketing.*.json`, OG image, JSON-LD, sitemap/robots. Includes producing and encoding the samples of section 7 (QA account, cost cap $4) with the pipeline, ffmpeg encodes, `Try this prompt` links `https://app.videomk.com/new?prompt=<encoded>`.
Acceptance: mockups `home__*` matched at 4 breakpoints; Lighthouse targets; zero JS except the 2 KB hashed inline; text budget; Google brand-verification checklist (section 10) passes; ES home complete.
Screenshots to capture: home at 390/820/1280/1440 light/dark EN/ES, hero player states (poster, playing, reduced motion), samples grid.

### Work package B: app shell, Create, library, media (one agent, after WP0)

Files: `src/pages/{index,new,media}.astro`, `src/components/app/{Rail,Tabbar,Library,VideoCard,MakingCard,Composer,OptionsPopover,QuestionSheet,DeckAttach,MediaPage,MediaGrid,UploadQueue,Collections,OrganizeSheet}.tsx`, `src/lib/{library.ts,media.ts,upload.ts,exif.ts}` (+ tests), replaces `GenerationsPage/GenerationsList/CreateSheet/PromptForm` (keep `DeckPicker` logic and `lib/create.ts`, `lib/deck.ts`, `lib/videos.ts` with their tests), `src/i18n/app.*.json` keys `app.*`.
Acceptance: mockups `videos__*`, `create__*`, `create_options__*`, `media__*`; Create surface <= 14 words (+40 in Options); upload of 50 photos works with progress, duplicates and `no_space` handled (QA); search and collections work; keyboard shortcuts; text-budget and axe tests green; no per-card Edit button.
Screenshots: Videos (empty, making, error, 40 items), Create (empty, filled, Options open, with photos, with a deck, questions sheet, blocked, not enough credits), Media (empty, grid, search, selection, upload in progress).

### Work package C: player, editor, credits, settings, feedback, sign-in, delete account (one agent, after WP0; can run in parallel with B)

Files: `src/pages/{watch,edit,credits,settings,feedback,signin,auth/callback,delete-account}.astro`, `src/components/app/{Player,WatchPage,Editor,CreditsPage,SettingsPage,FeedbackPage,SignIn,DeleteAccountFlow}.tsx`, `src/lib/{player.ts,settings.ts}`, `src/i18n/app.*.json` keys `watch.*`, `edit.*`, `credits.*`, `settings.*`, `signin.*` (different namespace files from B: `app.watch.*.json` etc. to avoid conflicts).
Acceptance: mockups `player__*`, `signin__*`; custom controls keyboard operable with the shortcut map; Share uses the Web Share API with copy-link fallback; Settings (language, appearance, photo dates, locations, organise preference) persisted the same way as the apps (`prefs`); in-app account deletion with re-auth working on QA; Credits <= 18 words; axe green.
Screenshots: Watch (playing, paused with controls, captions on, fullscreen, phone), Editor (two panes), Credits, Settings, Sign-in (4 states), Delete account steps.

Shared files that cannot be edited concurrently (owned by WP0, changes requested through it): `src/styles/tokens.css`, `src/styles/global.css`, `src/layouts/*`, `src/lib/auth.ts`, `src/lib/config.ts`, `src/lib/i18n.ts`, `src/lib/api.ts` (any new endpoint helper goes into the package's own `lib` file), `package.json` (dependency additions go through WP0 in one batch: `@axe-core/playwright`, `playwright-core`, `exifr`, an optional HEIC decoder), `backend/**`. Other packages never touch `mobile/`.

Order: WP0 -> A and B and C in parallel (A and B/C touch disjoint page and component folders) -> integration pass (one agent): cross-links, ES review by a Spanish reader, final screenshots, Lighthouse, prod smoke test by the owner. Estimated effort: WP0 1 day, A 1.5 days (plus the sample production, mostly waiting), B 3 days (media upload is the bulk), C 2 days.

## 12. Risks and open decisions

1. **Samples must be real.** The hero shows videos made by the real pipeline with the real prompts; the 91 s forest video was made with a prompt workaround for 5 s clips (`docs/VIDEO_CATALOG.md`), so it should be re-made with 8 to 10 s clips (about $0.35) before launch, or shown with the actual prompt used. Decision for the owner: ship the hero with the existing forest video now, or wait for the clip library.
2. **Library not yet generated**: until the 100-clip batch is approved only 10 pilot clips exist; sample 1 depends on it, samples 2 to 6 do not.
3. **Animated backgrounds and vector scenes are prototypes** (agents running now): samples 4 and 5 depend on them; each has a fallback.
4. **HEIC upload** (section 2) is unverified.
5. **Tokens in localStorage** stay (static site, no server): XSS is the main risk; mitigated by the strict CSP and no third-party scripts; a BFF/HttpOnly-cookie flow is a later hardening step (also noted in `auth.ts`).
6. **Hero autoplay** has accessibility and data-saver rules (section 7.1); on iOS Safari muted inline autoplay needs `playsinline`.
7. **Owner actions**: Search Console verification of videomk.com (and confirm no extra for app.), Google consent screen branding and publish to In production, Apple credentials for Apple sign-in, approve the sample budget (about $4), supply the Play/App Store store links for the "Get the app" buttons on the home page (replace the "coming soon" line when the apps are public), decide the whiter Apple background vs the app's `#f6f7fc` (section 5).
8. **Two languages everywhere** doubles review work; a Spanish reader should check the ES copy before launch.
9. **Spend**: this stage spent $0 (local captures and mockups).

## 13. Top 10 problems (summary)

1. The web app is not published at all; app pages return 404 on videomk.com.
2. Web sign-in cannot work on prod: redirect URI mismatch (`/auth/callback/index.html` vs `/auth/callback`), no `api.videomk.com` DNS, no `PUBLIC_*` build values.
3. Two homepages; the live one is stale (bolt logo, "apps coming soon"), has no video, no sample, no path into the app.
4. Create is a 239-word, 49-control form instead of a prompt box.
5. No app shell: wrapping header nav, no sidebar or tab bar, marketing footer on every screen.
6. Video list: placeholders instead of thumbnails, an Edit button on every card.
7. Player page: black band, "Untitled", no prompt, no scenes.
8. Parity gaps: no media library or photo upload, no settings, no in-app account deletion, no dictation, Google/Apple sign-in off.
9. Two visual languages (marketing vs app) and neither matches the new mobile direction; typography is not SF-first.
10. Stale brand on the homepage and sign-in; two i18n mechanisms; dead `/questions` route.

## WP0 status (2026-11-27, foundations agent)

**Live in prod:**
- **https://app.videomk.com**: stack `videomk-app-site` (us-east-1): private bucket + CloudFront (OAC), ACM certificate, Route 53 A/AAAA, HSTS, CSP, `noindex`, hashed files cached a year, HTML `no-cache`, unknown addresses answer `/index.html` (the app root sends people to `/generations`). Serves the CURRENT app screens (old design): `/signin`, `/generations`, `/wallet`, `/watch`, `/edit`, `/feedback`, `/questions`, `/auth/callback`, `/delete-account`. /privacy, /terms, /support (and `/es/...`) 301 to videomk.com.
- **https://backend.videomk.com**: the API's custom domain (stage `prod`, `apiHost` in `stages.json`). **The spec's `api.videomk.com` is not possible**: API Gateway says "domain name already exists" and no such domain exists in the prod account (us-west-2, us-east-1), so another AWS account of the owner still holds it (same story as `auth.videomk.com`). The app build, CSP and `config.ts` default use `backend.videomk.com`.
- **videomk.com** (stack `videomk-site`): the old app addresses `/signin /generations /wallet /feedback /watch /edit /questions /auth/callback` answer 301 to the same path on app.videomk.com with the query string; public pages untouched; the marketing build now also ships `apple-touch-icon.png`, `icon-192/512.png`, `site.webmanifest` (they were linked but missing, which broke `test_no_broken_internal_links`).
- **Cognito (prod web client)**: callbacks `https://app.videomk.com/auth/callback` + `https://videomk.com/auth/callback`; logout `https://app.videomk.com/` + `https://videomk.com/`. Redirect URI in `lib/auth.ts` is exactly `<origin>/auth/callback` (the `redirect_mismatch` is gone). S3 upload CORS includes app.videomk.com.
- Commands: `backend/scripts/site.sh app-build|app` (app), `site.sh build|full` (marketing). Values for the app build (client id, hosts, `PUBLIC_AUTH_GOOGLE=1`) are defaults in the script and can be overridden by environment variables.

**What WP-A/B/C can assume:** links inside the app are plain `/generations`, `/wallet`, `/watch?id=`, `/edit?id=`, `/feedback` (no `index.html`); unknown paths fall back to `/index.html`, so a client-side route like `/videos/:id` can be added later with no infra change; the app shell must not link to `/privacy` etc. without expecting the 301 to videomk.com; CSP forbids third-party scripts, frames and hosts outside `backend.videomk.com`, `login.videomk.com` and S3 (change `CSP` in `backend/app_site_stack.py` if a package needs more, through WP0).

**Not done (left to the packages or the owner):** tokens/shell skeleton and the layout split (`MarketingLayout`/`AppLayout`, per-area i18n files) were not part of this foundations pass (the directive was wiring only); the marketing homepage still has no link into the app; Cognito's hosted sign-in page is the default unstyled one (Managed Login branding would be a WP-C item); Google Search Console verification and the consent screen are owner actions; the old `https://videomk.com/auth/callback` entries can be removed from `stages.json` after a few weeks.

## WP0b status (2026-11-27, shell and tokens): done, ready for packages A, B, C

Built in `frontend/` only; nothing deployed (the packages deploy with `site.sh full` / `site.sh app`). Vitest 168 green (142 old + 26 new), both targets build (`site.sh build`, `site.sh app-build`), public pages carry no script, marketing CTA links to `https://app.videomk.com/`. Screenshots of the kit: `docs/web_2026/shell/uikit_{desktop,phone}_{light,dark}.jpg`.

**What exists now**
- **Tokens**: `src/styles/tokens.css` (existing names kept; added SF Pro first font stack with Inter fallback, marketing display scale `--fs-hero/--fs-h2/--fs-lead`, tracking, `--space-10/12/16/24`, `--section-pad`, `--gutter`, rail/tab bar/header sizes, z-index scale). `tokens.test.ts` keeps the AA contrast checks, the 14 px floor, the 4 px grid and pins the `theme-color` metas to the tokens.
- **Layouts** (`BaseLayout` is gone): `layouts/Head.astro` (shared head), `layouts/MarketingLayout.astro` (public pages, header CTA "Open the app", footer with language and theme), `layouts/AppLayout.astro` (left rail on desktop, tab bar on phone, no footer; `shell={false}` gives the bare frame used by sign-in). All app pages use `AppLayout`, `LegalDoc` and `Landing` use `MarketingLayout`.
- **Navigation list**: `src/lib/appNav.ts` (one line per destination, 5 max). Packages add their item there.
- **Styles by owner**: `styles/shell.css` (shell, WP0), `styles/marketing.css` (package A), `styles/app.css` (packages B and C, sections marked), `styles/ui.css` (kit extras, WP0), `styles/global.css` (WP0).
- **i18n split**: `src/i18n/<area>.{en,es}.json` for `common`, `marketing`, `auth`, `app-create`, `app-library`, `app-player`; `i18n/areas.json` maps key prefixes to areas (add a prefix there only through WP0); `i18n/catalog.ts` merges them; `catalog.test.ts` enforces EN/ES parity, placeholders and prefix ownership.
- **Links**: `lib/config.ts` has `SITE_URL`/`APP_URL` (`PUBLIC_SITE_URL`, `PUBLIC_APP_URL`; defaults `https://videomk.com`, `https://app.videomk.com`; use `http://localhost:4321` for both in local dev); `lib/links.ts` has `appUrl`, `siteUrl`, `tryPromptUrl`, `APP_PATHS`, `SITE_PATHS` (tested).
- **UI kit**: `src/components/ui/` (`Button`, `IconButton`, `Chip`, `Dialog`, `Toast`, `Tabs`, `Skeleton`; `Sheet`, `Spinner`, `EmptyState`, `Icon`, `Thumb`, `MakingCard`, `CostLine`, `useToast` re-exported from `components/ui.tsx`), tests in `ui.test.tsx`, preview page `/ui-kit` (noindex, no auth, not copied by `site.sh` to either site).

**Ownership**
| Package | Edits | Does not edit |
|---|---|---|
| WP0 (shell) | `tokens.css`, `global.css`, `shell.css`, `ui.css`, `layouts/*`, `lib/auth.ts`, `lib/config.ts`, `lib/links.ts`, `lib/appNav.ts` (items), `lib/i18n.ts`, `i18n/catalog.ts`, `i18n/areas.json`, `components/ui/*`, `package.json`, `backend/**` | |
| A marketing | `styles/marketing.css`, `components/Landing.astro`, `pages/index.astro`, `pages/es/*`, `components/LegalDoc.astro`, `pages/{privacy,terms,support,delete-account}.astro`, `site-pages/*`, `i18n/marketing.*.json` | layouts, tokens, app pages |
| B app: Create, library, media | `styles/app.css` (section B), `pages/generations.astro`, new `pages/media/*`, `components/{CreateSheet,PromptForm,DeckPicker,GenerationsList,GenerationsPage,QuestionsStepper}.tsx` and new media components, `lib/{create,deck,videos}.ts` and new `lib/media*.ts`, `i18n/app-create.*`, `i18n/app-library.*` | layouts, tokens, package C files |
| C app: player, edit, credits, settings, feedback, sign-in | `styles/app.css` (section C), `pages/{watch,edit,wallet,feedback,signin,questions}`, new `pages/settings/*`, `components/{WatchPage,Editor,SceneForm,WalletPage,FeedbackPage}.tsx`, `lib/{editor,feedback}.ts`, `i18n/auth.*`, `i18n/app-player.*` | layouts, tokens, package B files |
Shared files a package needs changed (a new token, a nav item beyond the list, a new i18n prefix, a dependency): ask WP0; do not edit them concurrently.

**Notes for the packages:** the live marketing homepage is still the hand-written `frontend/site-pages/index.html` (not the Astro `Landing.astro`); package A decides which one wins. Dark mode and the language switch work in both layouts through the existing `data-theme-switch` / `data-lang-switch` hooks. The `dots` icon in `ui.tsx` is faint at 20 px (known, cosmetic).

## WP-C status (2026-11-27, player, editor, credits, settings, feedback, sign-in): built, not deployed

Vitest 268 green (the 168 of WP0b plus package B's and C's new tests); `astro build` works for both targets. Screenshots (390 / 820 / 1440, light and dark, EN and ES where text changes): `docs/web_2026/app_c/` (78 JPEGs); generator `docs/web_2026/src/shoot_c.mjs` (fake API in the browser, serves the build), word counter `docs/web_2026/src/count_c.mjs`.

**Shipped**
- **Watch page** (`WatchPage.tsx`, `Player.tsx`, `lib/player.ts`): our own controls over a plain `<video>`, icons only: play, scrubber with buffered range and spoken value, time, volume (hover devices), speed cycle, picture in picture, full screen (iPhone Safari falls back to the video's own), captions only when the file carries a track (ours are burned in, so no button). YouTube-style shortcuts (space/k, arrows, j/l, m, f, p, c, 0-9, < >). Controls rest after 3 s of playback, never while paused, never while a control has keyboard focus. Poster = the list's cached preview when there is one, with a big glass play button. **End card**: replay and "New video". **One row of icons** under a single caption line ("1:20 · 720p"): Share (the one gradient button; Web Share API, else copy link), Save (asks `?download=1` so the server names the file and the page stays), Edit (only when editable), Details (sheet with the description and photo credits, Copy), More (Make another video, Send feedback, Report this video). States: loading, still being made (409), failed (409 ERROR/FAILED/REJECTED: "No credits used"), error with Try again. Vertical, square and 4:5 videos keep their own shape (size from the file's pixels).
- **Credits** (`WalletPage.tsx`): the number and one word on the gradient card, one line about the next free credit, New video (primary) and Get more (disabled, "Coming soon"), a small "How credits work" table, the buckets as history. Unlimited accounts see the infinity sign and "Unlimited", nothing about test accounts.
- **Settings** (new `pages/settings`, `SettingsPage.tsx`, `lib/settings.ts`, `lib/account.ts`): account row (email, Sign out), Language (EN/ES), Appearance (Auto/Light/Dark), Subtitles, Photo dates, Photo locations (one (i)), Watermark default when the server has the feature (None / videomk / Your logo (Pro), position, logo upload and removal for premium; checked on the file's size and type, the server checks the bytes again), Send feedback, Support, Privacy, Terms, **Delete account**: type DELETE, a sign-in no older than 10 minutes (`auth_time`; otherwise "Sign in again": sign out locally, hosted `/logout`, the sign-in page puts the person back on `/settings?delete=1`, one last confirmation without typing), the request (idempotent), Sign in with Apple's step when the answer says `revoke_available` (the page opens Apple's link, local data already wiped), local wipe (tokens, caches, drafts, preferences; language and theme stay) and the closing message with the manual Apple steps when needed.
- **Feedback** (`FeedbackPage.tsx`): "Tell us anything.", Topic chips, one box; opened from Report this video it carries the video id in the context (`report:<id>`, `after_video:<id>`) and starts on "Problem".
- **Editor** (`Editor.tsx`): same flow and logic, restyled with tokens, back icon, status badge, the player for previews, **Undo** (50 steps, one per pause in typing; Cmd/Ctrl+Z outside text fields), icon tools on the selected scene.
- **Sign-in** (`signin.astro`, `auth/callback.astro`): the new mark (the Sparklet tile), the two-line promise, **Continue with Apple / Google / email** in that order (Apple's black or white button, Google's white or dark button, each only when its switch is on; email goes to the hosted page with `lang`), the legal line, "Opening..." while the browser leaves, no box on phones and a soft card from tablet up. The callback page has a working state and an error state with Try again. Google is on in the prod build (`PUBLIC_AUTH_GOOGLE=1` in `site.sh app-build`); Apple needs `PUBLIC_AUTH_APPLE=1` once the credentials exist.
- **Navigation**: Settings replaces Feedback in `appNav.ts` (Feedback lives in Settings, the video's More menu and after a video).

**Visible words in the main area (English, `count_c.mjs`, counted from the DOM)**
| Screen | Words (main) | Budget (UX doc) |
|---|---|---|
| Watch (title, time, quality) | 8 | 8 |
| Credits (with the history list) | 22 | 18 |
| Settings | 23 | 30 |
| Feedback | 12 | 14 |
| Sign-in (promise, three buttons, legal line) | 26 | 12 + buttons |
Taps: watch to share 1; sign in 1 (provider) ; delete account 3 + typing.

**Needs WP0 / other owners (not changed by WP-C)**
- `backend/scripts/site.sh` `app_build`: add `settings` to the page list (`for p in signin generations wallet watch edit feedback questions settings delete-account`), or the settings page is not published. Same for `media` and `new` of package B.
- Package B: the Create sheet should open when the URL has `?create=1` (the end card, credits and More menu link to `/generations?create=1`; `/new` may replace it). The Create sheet should read `readPref("subtitles")` from `lib/settings.ts`; the media upload should read `readPref("photoDates")` and `readPref("photoLocations")`.
- Package A: the public `/delete-account` page is where Apple returns after revoking (`?status=ok|cancelled|mismatch|failed|invalid`, docs/ACCOUNT_DELETION.md section 4); it could show one line per status.
- Backend/Cognito: if the pool moves to Managed Login, `prompt=login&max_age=0` works and `signInAgain()` can skip the hosted `/logout`.

**Not done / limits**
- Save has no resolution choice: the API returns one rendition per video (the one it was made in); the caption states its quality.
- Publish (social) is not on the watch page: phase 0 of docs/SOCIAL_PUBLISHING_RESEARCH.md is the existing Share button; direct publishing waits for its own work.
- The questions page (`questions.astro`) still shows package B's stepper unchanged.
- Verified with a fake API in the browser (Chrome, Playwright), never against the real server; delete and Apple steps were exercised only up to the request (the fake answered 202).

## WP-A status (2026-11-27, marketing site agent): built and tested, NOT deployed

**What shipped (frontend/, plus the publish wiring in `backend/scripts/site.sh`):** a new home page at `/` and `/es/` (components `Landing.astro`, `SampleCard.astro`, `MIcon.astro`; styles in `styles/marketing.css`; strings in `i18n/marketing.*.json`; data in `src/data/samples.ts`). Sections: hero (prompt box that opens the app with the idea filled in, a large muted-loop sample with its real prompt and "Try this prompt"), a gallery of 5 real samples plus "Make your own" (snap rail on phones), formats, three steps, six features, credits, FAQ (incl. the Google/Apple data answer), final call, footer with Agilegency Ltd, company number, Privacy, Terms, Support, language. Header: Gallery, Formats, Pricing, Help, Open the app. The hand-written `site-pages/index.html` and `es/index.html` are deleted; `site.sh build` now publishes the Astro pages, the samples folder and `og.jpg`; `site.sh` keeps inline scripts marked `data-keep` (JSON-LD and a 1.4 KB player) and strips every other script. The shared layout got two small additive slots (`head`, `nav`, `footer-extra`) and `Head.astro` got Open Graph and Twitter tags (these two files belong to WP0; the edit is additive).
**Samples (all real videomk outputs, short cuts with sound, 9 MB in total):** forest (hero, own AI clips; the prompt shown is a word-for-word excerpt of the prompt that made it), bees, focus tips (9:16), AI and jobs (1:1), AI agents (4:5), octopus (Spanish, 15 s). Only the hero has a prompt: the others were made earlier and their prompts were not saved, so they show title only (no invented prompts). Left out on purpose: the Majorca family videos (identifiable private people), and features that are not live for everybody (animated backgrounds, cartoon scenes). More samples need the owner's approval (about $4) and go in `samples.ts`.
**Checked:** vitest 263 pass (21 files, incl. `src/data/samples.test.ts`); backend `test_site_build.py` (home page: one h1, logo, visible Privacy and Terms links, JSON-LD, og:image, exactly two kept scripts, no redirect, every video poster-first with `preload="none"`, all media files exist) and `test_app_site_cdk.py` pass (15). Lighthouse on the built page (local server): desktop 100/100/100/100 (LCP 0.6 s, CLS 0); mobile 97/100/100/100, LCP 2.6 s on the simulated slow 4G (budget 2.0 s: open, see report). CSS 15 KB gzip in total. Screenshots (1440, 820, 390, light and dark, EN and ES) in `docs/web_2026/marketing/`; generator `docs/web_2026/src/shoot_marketing.mjs`.
**Open for the owner:** more sample videos with their real prompts (about $4), App Store and Google Play URLs (`PUBLIC_APP_STORE_URL`, `PUBLIC_PLAY_STORE_URL` at build; the buttons stay hidden until set), Google brand-verification wording re-check, Search Console and consent screen.

## WP-B status (2026-11-27, Videos, Create, My media): built and verified against a mocked API; not deployed

**Screens** (all in `frontend/src/components/app/`, styles in `src/styles/app-b.css` imported by those components so the shared `app.css` is untouched): **Videos** (`/generations`), **Create** (`/new`, "What should we make?"), **My media** (`/media`). The nav gets two lines (`Media`, `New`) in `lib/appNav.ts`. The old `CreateSheet`, `PromptForm`, `GenerationsList`, `GenerationsPage` are removed; `DeckPicker` and the Create/deck/videos logic in `lib/` are kept and extended. Old links keep working: `/generations?new=1&prompt=...` (the contract of `tryPromptUrl` and `APP_PATHS.create`) redirects to `/new?prompt=...`.
- **Videos**: grid of real thumbnails (making card first), search pill, `New video`; no per-card buttons, the `...` menu holds Edit, Copy link, Download. Skeleton, empty, error, search-no-match states. No flicker: unchanged cards keep their object and their first thumbnail link (`reuseUnchanged`, `stableThumbs`), polling 5 s backing off to 30 s, only while something is being made and the tab is visible. No select mode (nothing to apply it to: the API has no delete or archive for videos).
- **Create**: prompt, photo menu (From this device / From My media), presentation attach (when `capabilities.deck`), dictation (Web Speech API, hidden where unsupported), three pill menus (made for, length with credit prices, look), ONE Options popover (format, quality incl. 4K only for platforms with `supports_4k`, subtitles, narration language, scene style behind `PUBLIC_SCENE_STYLE=1`, watermark when `capabilities.watermark`), `Create · n`. Request check (questions as a sheet, kind stops), same request id on retry, `?prompt=` prefill, photos up to 100 with the capacity hint, My media handoff.
- **My media**: search by meaning with removable chips, filters (years, places, collections), month-grouped square grid, shift-click range, checkbox select, drag-select in selection mode, floating selection bar (Make a video, Add to collection, Delete), full-size viewer with arrows, drop anywhere (folders too), paste, one upload banner (pause, cancel, retry, duplicates, no space, unreadable files), smart organise after 30 or more photos, one-time privacy note, storage meter, collections create and delete.
- **Shortcuts**: N, /, G then V/M/C, ?.

**Numbers** (visible fixed words, EN): Create 12 (limit 14), Options 36 (limit 40), Videos 5; taps from the Videos screen to a made video with defaults: 3 (New video, type, Create). Pinned by `components/app/app.test.tsx` for EN and ES.

**Tests**: vitest 284 green (142 old + 142 new): `lib/{exif,library,upload,droppedFiles,shortcuts,dictation}.test.ts`, additions to `create.test.ts` and `videos.test.ts`, `components/app/app.test.tsx`. `docs/web_2026/src/verify_b.mjs` drives a real Chrome against a mocked API (15 checks: request bodies for plain, YouTube 4K look, photos from this device, My media handoff, shortcuts, old link redirect). `shoot_b.mjs` produced `docs/web_2026/app_b/` (about 70 screenshots at 1440 and 390, light and dark, EN and ES, with the states).

**Upload rules** (browser): upright, at most 2048 px, JPEG re-encoded (no metadata), sha256 of the exact bytes, capture time and position read from the original Exif only when the "photo dates / locations" switches are on (`lib/mediaPrefs.ts`, same defaults as the apps; Settings should use those functions), 4 at a time, retry with backoff, fresh slot on retry, `no_space` and `storage_full` handled. HEIC: Safari decodes it, Chrome and Firefox cannot: those files are listed as "can't be read here" (no decoder was added: the package file is owned by WP0).

**Needs backend (blocks upload to My media in a browser):** the media bucket (`backend/media_library.py`) has NO CORS rule. A presigned POST from `app.videomk.com` needs `AllowedMethods=[POST]`, `AllowedOrigins=_web_origins(stage_cfg)` (same as the assets bucket in `backend_stack.py`), `AllowedHeaders=["*"]`. Thumbnails (plain `<img>`) need nothing. Photos for ONE video ("From this device") go to the assets bucket, which already has the rule.
**Not verified:** a real upload against QA (no CORS yet), the real capabilities payload with `watermark`, axe accessibility run (labels, roles, focus and keyboard were built in and checked by hand and by tests, not by axe), Safari and Firefox (only Chrome was driven).
**Notes for the shell owner:** Spanish tab bar label `nav.videos` ("Mis videos") wraps to two lines at 390 px; the rail's credit pill from the spec is not in the shell yet; `components/ui.tsx` has no `search`, `image`, `sliders`, `trash` icons, so package B draws its own in `components/app/icons.tsx`.

<!-- DESIGN-BAR-PASS-BEGIN (2026-11-27, web) -->
## Design bar pass (2026-11-27): the web now follows docs/DESIGN_BAR_2026.md and its web mockups

Source of truth for the look: `docs/design_bar/mockups/web_1..web_5` (and `docs/design_bar/src/base.css` for the values). What changed, and where it lives:

| Area | What it is now | Files |
|---|---|---|
| Tokens | The design bar's colours in both modes (near-black `#06070d` dark, `#f7f7fa` light), one deep primary gradient with white text in both modes, headline gradient tokens | `styles/tokens.css`, `styles/tokens.test.ts` |
| Home | Two-line headline with the gradient second line, one field with a working mic (hidden where the browser has no speech recognition), "Free to start. No card.", a 1120 px hero video with the prompt and "Try this prompt" on its lower edge (above the video's own caption line; under the video on phones), gallery "One sentence in. Any shape out." with aspect badges; nav Gallery, Pricing, Help, Sign in and one inverse pill | `components/Landing.astro`, `components/SampleCard.astro`, `styles/marketing.css` (last block), `data/samples.ts` |
| App shell | 248 px rail: Videos, Media, Settings; the credits card (links to Credits) and the account (links to Settings) at its foot. Phones: a floating glass tab bar with the same three places and ONE round button that makes a video | `layouts/AppLayout.astro`, `styles/shell.css`, `lib/appNav.ts` |
| Videos | 40 px title, search field, one New video button, the making banner (title, one live line, the four steps as tiles, time left), aspect badges, failed card with Try again (same video) and Remove | `components/app/VideosPage.tsx`, `useVideos.ts`, `lib/videos.ts`, `styles/bar.css` |
| Create | "What's the video about?", one centred card, photo strip with count, For / Length / Look pills, options, Create with the credit cost, suggestion chips, and the locked wait capsule ("Checking your request…" with Cancel, then "Starting your video…") | `components/app/Composer.tsx`, `styles/bar.css` |
| Media | Search in the header, Select / Done, one labelled Add photos, month groups with counts, 3:2 tiles, the floating selection bar "N selected · folder · delete · Make a video · N", upload progress as a floating card; the selection survives the trip to Create and back | `components/app/MediaPage.tsx`, `MediaGrid.tsx`, `styles/bar.css` |
| Watch | Back to Videos, the player (800 px), title and meta, Share as the one primary, save / edit / more, "Make another" chips that open Create pre-filled (Short, other language, same idea) | `components/WatchPage.tsx`, `styles/bar.css` |

Rules kept from the design bar: one primary action per screen, never more than one "+" on a screen (New video is a sparkle, Add photos an image-plus, New collection a folder), no number shown at zero (home samples start past their count-up), word budgets (tests in `components/app/app.test.tsx`).

Known gaps against the mockups (in priority order):
1. **Making banner tiles**: the mockup shows scene thumbnails appearing; the API has no per-scene thumbnails yet, so the banner shows the four real steps. Needs a backend field (scene previews) first.
2. **Gallery lines**: the mockup shows the sentence that made each sample; only the hero's prompt was saved, so the others show their title (no invented prompts). New samples with saved prompts fix this.
3. **Watch "The prompt"**: the video API returns a description, not the prompt; the side column shows "Make another" only. Needs the prompt in `GET /videos/{id}`.
4. **Get the app**: the header pill says "Open the app" until store links exist (`PUBLIC_APP_STORE_URL`, `PUBLIC_PLAY_STORE_URL`).
5. **Phone web**: follows the phone mockups' language (floating bar, round button, same cards); the phone Create card stacks its pills in two rows.
6. **Signed-in flows against the real API**: verified with mocks and with real preflights only (no test token could be minted in this session). My media needed a backend fix (every `/library` route lacked the browser preflight; commit `786cd5b`, deployed with the next backend deploy).

Tooling: `docs/web_2026/src/walk.mjs` (tour and behaviour checks against a mocked API) and `shoot_home.mjs` (home page, local or live).
<!-- DESIGN-BAR-PASS-END -->

<!-- REAL-QA-PASS-BEGIN (2026-11-27, web) -->
## Real-API pass (2026-11-27): the signed-in web app driven in Chrome against the QA backend

How: `astro dev` with `PUBLIC_API_BASE` = the QA API, `PUBLIC_AUTH_DOMAIN` = the QA hosted sign-in, `PUBLIC_COGNITO_CLIENT_ID` = the QA web client (stack output `UserPoolClientId`), both `PUBLIC_SITE_URL` and `PUBLIC_APP_URL` = `http://localhost:4321`. Playwright (installed Chrome) signs in through the real hosted page with the QA test account and keeps the session. Scripts: `docs/web_2026/real_qa/src/` (`login`, `tour`, `flow_media`, `flow_create`, `flow_watch`, `mock_making`, `home`, `serve`; set `OUT` to a scratch folder; no password or token is in them). Screenshots: `docs/web_2026/real_qa/shots/` (`*_real` = taken during the real journey; `t_*` = tour at 1440 and 390, light and dark, EN and ES; `mk_*` = the Making views with the documented `making` object injected into the real list; `h_*` = the built home page).

| Flow | What ran against the real API | Result |
|---|---|---|
| Sign-in | Hosted page, code exchange, return to Videos | pass |
| Videos | List, thumbnails, search, toast after Create, polling | pass |
| My media | Upload 4 photos (slot, direct S3 post), month grid, search by meaning, viewer, select, delete with confirm | 4 defects fixed (below) |
| Media to Create | "Make a video · 3", back keeps the selection, photos arrive in the composer | pass |
| Create | Request check (locked form, capsule with Cancel), `generate` with `library_media`, 15 s for 1 credit | pass; phone layout and the balance line fixed |
| Making | The real `making` object (scenes, pictures, live line) drawn in the banner while two videos were made | pass; counter fixed for the render phase |
| Watch | Play (1920x1080), keyboard, Share (copy path), Save (download), Details, Make another, Edit | 3 defects fixed (below) |
| Settings, Credits | Language, appearance, watermark default saved (`PUT /watermark` 200), balance and buckets | pass |
| Try again / Remove | The card and both calls reach the real routes (a made-up id answers 404: "not found" / removed) | routes and messages verified; a REAL failed video was not available, so a real restart was not seen |

**Defects found and fixed (each with a test where it is logic):**
1. My media stayed empty after an upload: the server lists a photo a few seconds after it took the file, and the page looked once. It now looks again until every new photo is listed (about a minute at most; `SETTLE_DELAYS_MS`, `pendingIds`). Seen: 4 tiles after 6 to 10 s.
2. After deleting the selection the page stayed in select mode (a tap ticked instead of opening the photo).
3. The finished upload card sat over the selection bar: it now leaves by itself after 6 s when there is nothing to fix, and never sits under the bar.
4. Spanish at 390 px: the search field was cut ("Buscar fot"), Add photos wrapped, the selection bar ran off the screen.
5. Watch: a vertical video sat in a black 16:9 box with its last controls cut off; the player is now its own shape and drops the volume slider when narrow.
6. Watch: the picture-in-picture button never showed its state (React has no props for those events: two console errors per visit).
7. Watch: after the big play button the keyboard did nothing (focus was lost with the button).
8. Create: "you have 1" under the card was a fragment; it now says what the video needs and what is left, and at 390 px the page scrolled sideways by 64 px.
9. Rail: "0 credits" is now "No credits left".
10. Making: "Scene 3 of 3 · Putting the scenes together" during the render (no scene is in work then): the counter is dropped once every scene is done.

**Mockup gaps, now:**
- **Making** (was gap 1): done against the live contract. Videos banner = title, "Scene 5 of 9 · live line", film strip with the scene pictures (cached by video and scene, never by link; links never stored), time left when the server gives one. The Watch page follows a video being made (same strip, the narrated sentence, "You can leave") and turns into the player when it is ready. Without `making` both fall back to the four steps / "Still being made".
- **Watch "The prompt"** (was gap 3): shown with "Use this prompt again". The API still does not return the prompt, so it is the sentence remembered by the browser that made the video (`lib/prompts.ts`, this device only, wiped with the local data); `prompt` in `GET /videos/{id}` wins as soon as the server sends it. Videos made elsewhere show "Make another" only.
- **Phone Create pills** (was gap 5): tools with Options at the far end, one row of three short pills, full-width Create with its price, the balance beneath (phone_3_create).
- **Gallery lines** (was gap 2): NOT closed in content. The card now shows the sentence in quotes whenever a sample has its real prompt, and the subtitle switches to "Each one started as the line under it" when all of them do; the five gallery samples still have no saved prompt (no invented prompts), so they show their subject. Needs new samples with saved prompts (owner approval, about $4).
- **Home page mobile LCP**: 2.2 s before (same harness: built page, gzip, Lighthouse 12 mobile, simulated slow 4G; the earlier report said 2.6 s without compression), **1.5 s after** (three runs: 1.5, 1.5, 1.5; budget 2.0). The five gallery posters no longer load with the first screen (they wait in `data-poster` and are set after load when the gallery is within 300 px), and the hero video starts downloading after load. Desktop 0.4 s. Without JavaScript the gallery videos have native controls but no poster.

**Not verified:** Safari and Firefox (Chrome only); the native share sheet (headless Chrome has none: the copy-link path was run); a real "Try again" on a really failed video; Apple and Google sign-in; delete account; deck upload; the editor beyond opening a real video in it.
<!-- REAL-QA-PASS-END -->

<!-- LOOK-PICKER-BEGIN (2026-11-28, web) -->
## Look and cast picker, plan locks, note, cancel, delete (2026-11-28): built against the documented contract with a mocked API; not deployed

Contract: `docs/CREATE_API.md` "Video look (chosen and enforced)", "Plans", "Cancel", "Delete". QA does not serve `looks.look` yet, so the mock is the server's own output (`docs/web_2026/src/look_caps.py` runs `common/look_choice.capabilities` with every look on). Without the new fields the form and the request are exactly what they were (tested).

- **Look pill** (`components/app/LookPicker.tsx`, rules in `lib/looks.ts`): one surface under the card (a bottom sheet on a phone) with at most four picture tiles from capabilities. Auto by default; a look the stage lacks is hidden; one the plan does not allow is locked with the plan's name; with photos or a deck only the looks made from them are offered, and attaching photos after choosing another look resets it to Auto with one line. Cartoon reveals the cast in the same surface (Auto, or 1 to 3 faces, numbered in the order picked; 2 or 3 show the server's conversation note) and the Hand-drawn board switch when listed. A look with nothing more to decide closes on choice. The pill shows the look and the faces; the last choice is remembered (`vmk_look_choice`).
- **Request**: `look`, `cast` (ids), `extras` in `generate` and in `options` of `brief`; nothing on Auto; the older `style` is never sent when the picker exists. The colour theme that used the Look pill moves to Options ("Colors") when the picker exists.
- **Keyboard**: Enter opens with the focus on the chosen tile, arrows move (tiles, then faces: one tab stop each), Space or Enter chooses, Escape closes and returns the focus to the pill.
- **Note**: the `note` of `generate` (or `brief`) is kept by video id on this device (`vmk_look_notes`) and shown on the Making banner and on the video page while it is made. **Details** on the video page shows the record's `look` (name, cast, extras, `why`).
- **Plan** (`lib/plan.ts`): lengths over the plan's longest video and 4K are locked with the plan's name; the default length comes down to the plan's longest; 403 `plan_*` / `free_not_available` and 429 `free_budget_spent` / `free_monthly_cap` show the server's sentence in place and keep the draft (before: a 403 read as "session expired"); no upgrade button anywhere; a Free account that cannot create and has no credits sees the locked card and the showcase from `GET /gallery` (`CreateLocked.tsx`); Credits shows the plan's name and longest video.
- **Cancel** while making (banner and video page): one question, `POST .../cancel` (one resend on `try_again`), toast with the credits returned; the item becomes a stopped card (Try again / Remove). **Delete** a finished video (card menu, video page More): the card leaves at once, "Deleted · Undo" for 6 s, and the `DELETE` is sent only then, or with `keepalive` when the page is left first (the server has no bin).
- **Also fixed on the way**: an open menu or popover on Create sat under the lines below the card and under the phone tab bar; at 768 px the composer bar ran out of the card and the page scrolled sideways; toasts sat on the phone tab bar.

Tests: vitest 377 green (`lib/looks.test.ts`, `plan.test.ts`, `api.test.ts`, additions to `create.test.ts` and `videos.test.ts`, `components/app/look.test.tsx`). `docs/web_2026/src/shoot_look.mjs`: 79 states in `docs/web_2026/look_picker/` (390, 768, 1440; light, dark; EN, ES; each checked for cut text, sideways scroll and overlapping controls) and 35 behaviour checks (request bodies, keyboard, reset, undo, cancel, locks). `REVIEW=1` produces the 2x review set.

**Not verified against the real API**: everything above that needs the new fields (`looks.look`, `looks.cast`, `note`, the record's `look`, the plan fields, `/gallery`, cancel, delete of a finished video). The delete sent while leaving the page was seen being requested by the page, not arriving at a server. Chrome only.

**After the independent design review (2026-11-28, `~/Downloads/videomk-looks/review-ios/EXPERT_REVIEW.md`; this replaces the description above where they differ):** selection is the ring only (no tick on pictures or faces, no recoloured label, no order number); the Auto tile is a brand-tinted tile with the sparkle, never a photo, and is "Auto" in both languages; every tile picture has a 1 px inner hairline; tile notes are the server's, on one quiet line without the full stop; a look the plan does not allow, or that is not made from the attached photos or deck, stays in its place at 40 percent with the reason where the note was ("Pro plan", "Not with photos", "Not with slides"): only a look the stage lacks is hidden, and the "only these looks apply" line is gone; the cast has no Auto face (none chosen means we cast it), ten faces in a 5 x 2 grid (one row of ten when the surface is wide), one text slot under them ("We pick for you. Or choose up to 3." / "Fox presents." / "Fox and Bruno talk it through."); the role and topic line is gone; a close X instead of Done; picture, name and note share the surface's left edge; the "look set to Auto" line sits right above the pills; the "looks best in" hint on Create has a one-tap fix. Tests: vitest 378 green; the mocked pass still 79 states and 35 checks. The mock carries the shorter notes and "Animado" the review asked the server for (`OLD_STRINGS=1` shows today's strings); the web renders whatever arrives.
<!-- LOOK-PICKER-END -->
