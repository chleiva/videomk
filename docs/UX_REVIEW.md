# videomk UX review and design spec (iPhone, Android, web)

Date 2026-11-26. Phase 1 of 2: review and spec only. Nothing under `mobile/` or `frontend/src` was edited, nothing committed or deployed.
Owner brief: "good, but not extremely good; we want definitely world class". Brand kept: modern, calm, premium (indigo to violet).

Evidence folder in the repo (small, for implementers): `docs/ux_review/` (`ev_*.png` real captures, `mockup_*.png` redesigns, `tokens_v2.css`, `mockups_gen.py.txt` = generator of the mockups).
Full capture set (about 90 screenshots, scripts, mockup HTML) lives in the session scratchpad: `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/ux_review/` (`shots/`, `mockups/`, `ios_shot.sh`, `cdp.mjs`, `fakeapi.py`). That folder is temporary; the repo copies are the durable ones.

## 0. What was captured, and what was not (honest scope)

| Platform | Captured (fixtures and fakes only, no real account) | Not captured |
|---|---|---|
| iPhone 17 Pro (light, dark) | Sign-in (light, dark), home empty / with videos (Making, Failed, Ready) / 40 videos, Create (empty, filled, photos, options, no credits, 4K setup), question sheets 1, 2, summary, checking, unsupported, blocked, paused, Settings, Delete account (+ done), Media (plain, uploading, queue, error), Organize states, iPad Pro 11 (home, create) | Wallet sheet, video detail, player, share sheet, editor, photo viewer, Add photos sheet: no debug fixture opens them and the Simulator cannot be tapped from here (macOS assistive access denied). These were reviewed from code (`WalletView.swift`, `VideoDetailView.swift`, `PlayerView.swift`) and from the older mockups in `docs/ui/`. Scores for them are marked "code only". |
| iPhone SE-size (VMK SE sim) | Home empty / videos, Create filled, question sheet, sign-in | |
| Large text (accessibility-extra-large) | Home, Create, question sheet, sign-in on iPhone 17 Pro | Android large font |
| Android | **Nothing usable.** The emulator `pi35` booted to a black screen / "System UI isn't responding" twice, even with `-gpu swiftshader_indirect` (the README documents the same failure). Android has no fixture for the video list, so even a working emulator could not show home. | All Android screens. Android is reviewed from code (`ui/*.kt`, `Theme.kt`, `UiKit.kt`) and `docs/ui/*.png` (the project's own mockups, which the Android code follows). Findings marked "Android (code)" are not screenshot-verified. |
| Web | Sign-in (phone, desktop), generations (phone light/dark-emulated, tablet 820, desktop, 150% text), create modal (phone, desktop), watch, privacy / support / delete-account (phone, desktop) via headless Chrome with a device-metrics override (worked down to 390 px) and a local fake API | Editor (`/edit`, the fake API has no plan data so it rendered blank), landing page (there is none: `/` redirects to sign-in when signed out), any real video playback |
| Dark mode on web | Does not exist (0 `dark:` classes), so nothing to capture | |
| Competitors | WebSearch returned only affiliate comparisons; Apple HIG / M3 pages came back as titles only (JS rendered). Comparisons below are from general product knowledge and labelled as such, not from fresh fetches. | Hands-on use of CapCut, Descript, Canva, HeyGen, InVideo, Pictory |

Build note: the iOS app was built from the working tree (which has other builders' uncommitted sign-in and deletion edits) into the scratchpad DerivedData; sign-in screens therefore reflect work in progress.

## 1. The ten biggest findings (with evidence)

1. **The wait is the weakest part of the product, and the product is mostly waiting (1 to 10 min).** Home card shows 4 thin segments and "About 3 min left" (`ios_home_videos_light.png`); the detail screen shows a different thing (a checklist with spinner, `ProgressCard` in `VideoDetailView.swift`); nothing shows what is being made; no push, no Live Activity (iOS README: "Not yet: push, Live Activity"). Highest-impact area for retention: see section 4 and mockup 03.
2. **Create asks too much before value.** At 393 pt the main Create screen stacks prompt (140 pt), Add photos card, "What is it for" chip row, a format summary, "Also works" chips, 5 Length chips, More options and a status line (`ev_c_create.png`). The "What is it for" row is clipped on both sides ("dIn", "Shorts - Re"), and `LinkedIn / X / Shorts` chips are 1-line only: will not survive Spanish. Competitors that win on activation (CapCut templates, Pictory, InVideo) are prompt-first with one settings affordance.
3. **Dynamic Type is only half implemented on iOS.** 255 `.font(.system(size:))` calls (do not scale) vs 111 semantic text styles, 4 `ScaledMetric`/`relativeTo`. At accessibility-extra-large the home screen, video cards, composer, tab bar are pixel-identical to normal size while Create's chips do reflow (`ev_b_text_size.png`). The sign-in screen, which does scale, **overflows horizontally and clips** "Continue with Google" and the headline (`ios_xxl_signin.png`). This is an App Store accessibility risk and will compound with Spanish.
4. **The floating "New video" button covers content.** On the video list it sits over the third card's title and play button (`ev_a_fab_overlap.png`: iPhone 17 Pro, SE, 40-video list). On iPad the phone layout stretches: empty state is a full-width list of tiny rows and the Create sheet is a small form sheet whose Length row is cut off (`ev_g_ipad.png`).
5. **Web is a different product visually and functionally.** White page, blue-to-pink gradient button (21 `pink-*` classes, 0 indigo), black sign-in card, no dark mode, grey placeholder boxes instead of thumbnails (`web_generations_desktop.png`), 23 uses of `text-xs`/`text-[11px]`, a create modal with a single-line input and no length, look, format or cost (`ev_f_web.png`). The apps use indigo/violet with light and dark. The brand does not feel like one product. White on the pink end of the web gradient is 3.5:1 and on the blue end 3.7:1 (fails AA for 14 px text).
6. **Video detail and player under-deliver the moment of delight** (code only). Player inset 20 pt with 16 pt radius; actions are three equal bordered buttons: Share, **Copy title** (low value), **Copy description with credits**; Edit (the best retention feature) is a text button in the nav bar. No Save to Photos, no "make a vertical version", no "make another".
7. **Credits are explained in footnotes.** Wallet is a stock grouped `List` (not branded); the cost rule ("1 credit makes up to 1 minute, rounded up... 61 seconds costs 2") is 13 pt footer text; "Get more credits" is a permanently disabled button; one bucket label reads "unlimited (test account)" in production code paths. The Create screen shows a good receipt line ("3 credits - you'll have 39 left"), but 4K doubling is only visible inside More options. No cost explainer is reachable from Create.
8. **No first-run path to a result.** After sign-in the person lands on an empty list with three examples, a default of 3 min (3 credits) and the full options (`ios_home_empty_light.png`); question sheets can add 3 more steps. There is no sample video anywhere before sign-in (the sign-in screen is logo + one line, `ios_signin_light.png`), and its tagline differs from the home headline.
9. **Tokens are good and shared on mobile, but not governed.** `Theme.swift` and `Theme.kt` carry the same values as `docs/UI_DESIGN.md` section (g) and pass contrast almost everywhere (computed below), but: `textTertiary` fails AA on `background` (4.41) and `surface2` (4.15); iOS bypasses its own type scale 255 times; there is no token file for web; radii, durations and haptics exist only as prose in a doc.
10. **Sheet craft has rough edges.** In the question sheets a sliver of the chip row behind it shows at the sheet edges (the "e" fragments right of the sheet in `ios_create_q1_light.png`); on SE the sheet content is cut at the right edge (`ios_se_q1.png`, may be a mid-animation capture: verify); the paused / unsupported sheets are 60% empty; "Make it now" (top) and "Skip" (bottom) look like duplicates. Settings (`ios_settings_light.png`, first screen only; a Privacy link exists lower down in the in-progress code) has no Notifications / Language / Support / About rows visible, and a danger-red "Sign out" (it is not destructive).

What is already good and must not be broken: the home empty headline "Describe it. We'll make the video."; the Making card gradient (the one rich surface); the receipt-style CTA "Create video - 3"; "Nothing was charged." / "No credits were used." trust copy; the failed-state "Try again" action; privacy-first Media screens (storage meter, upload bar with pause/cancel and "You can close the app"); account-deletion screens (plain, itemised, honest); the web legal pages (readable at 390 px and 150% text); touch targets (44 pt hit areas around 32 pt chips); the existing token naming; tabular numerals on credits; the fixture system (`VMK_DEBUG_*`) which made this review possible.

Contrast computed (WCAG 2.2, ratio): light text2/bg 6.07; **text3/surface 4.72, text3/bg 4.41, text3/surface2 4.15 (fail for small text)**; primary/bg 5.43; primary/primaryContainer 4.85; white on gradient 4.88 to 4.67; warning/warningContainer 5.56; danger/dangerContainer 5.35; dark text3/surface 4.88; dark onPrimary on gradient 7.1 to 7.2. Web: white on pink-500 3.53, white on blue-500 3.68.

## 2. Scorecard (1 to 10; evidence = capture file, or "code")

Clarity / Hierarchy / Polish / Consistency / Delight / Accessibility.

| Screen | Cl | Hi | Po | Co | De | Ac | Evidence and main reason |
|---|---|---|---|---|---|---|---|
| iOS sign-in | 7 | 6 | 7 | 6 | 4 | 4 | `ios_signin_light/dark`; clean but generic; XXL overflow (`ios_xxl_signin`) |
| iOS home empty | 8 | 8 | 8 | 8 | 7 | 5 | `ios_home_empty_light`; best screen; text does not scale at XXL |
| iOS home list | 7 | 7 | 6 | 7 | 6 | 5 | `ios_home_videos_light`; FAB overlaps; big cards = 2.5 videos per screen; no thumbnails for Making/Failed |
| Create (main) | 6 | 5 | 7 | 7 | 5 | 6 | `ios_create_filled_light`; too many controls, clipped chip row |
| Options / Style | 7 | 6 | 7 | 7 | 6 | 6 | `ios_create_options_light`; good defaults, header crowding when scrolled |
| Question sheets | 8 | 7 | 6 | 7 | 7 | 6 | `ios_create_q1/q2/summary`; strong content ("You decide"); edge artefacts, duplicate exits |
| Blocked / paused / unsupported | 8 | 7 | 6 | 7 | 4 | 7 | `ios_create_unsupported/blocked/paused`; copy is kind and clear; sheet is mostly empty; generic text for blocked |
| Waiting (list card / detail) | 5 | 5 | 6 | 4 | 3 | 5 | `ios_home_videos_light` + `VideoDetailView` (code); two different progress UIs |
| Player / detail | 5 | 5 | 5 | 6 | 3 | 6 | code only |
| Wallet | 5 | 5 | 5 | 4 | 2 | 6 | code only (stock `List`) |
| Settings | 7 | 7 | 7 | 7 | 4 | 7 | `ios_settings_light`; no notifications / language / support rows; Sign out in red |
| Delete account | 9 | 8 | 8 | 8 | 4 | 7 | `ios_delete_light`, `ios_deletedone_light`; model of honest copy |
| Media | 8 | 7 | 8 | 8 | 6 | 6 | `ios_media_*`; polished; header pill row sits low (large empty status area) |
| iPad | 4 | 4 | 4 | 5 | 3 | 5 | `ev_g_ipad`; phone layout stretched |
| Android (all) | 7 | 7 | 7 | 8 | 5 | 7 | **code only**: Material 3 theme with the same tokens, fewer fixed sizes (14 `fontSize` vs 250 `typography` uses), 4 haptic calls, reduced-motion check in `Common.kt`; unverified visually |
| Web sign-in | 8 | 7 | 6 | 3 | 3 | 6 | `web_signin_phone_light`; black card vs white site |
| Web generations | 6 | 6 | 5 | 3 | 3 | 5 | `ev_f_web`; no thumbnails, tiny text, "Not allowed" chip |
| Web create modal | 4 | 5 | 5 | 3 | 2 | 6 | `ev_f_web` panel 2; no options, no cost |
| Web legal / support | 8 | 8 | 8 | 7 | 4 | 8 | `web_privacy_phone`, `web_delete_phone` |

## 3. Critique by theme

**Information architecture and navigation.** Two tabs (Videos, Media) plus Settings in a gear: right-sized. Create is a modal sheet from a floating button: move it into the tab bar centre (mockup 01) so it never covers content and is findable on iPad / Android / web the same way. Settings should hold Account, Credits, Notifications, Language (Spanish soon), Support, Terms, Privacy, About, Sign out. Credits chip is the only wallet entry: fine.

**First run (does a person get a result in 60 s?).** No. Sign-in (about 20 s via Apple/Google) then a list, a 3 min default (about 3 to 6 min of waiting), up to 3 question steps. Target flow in section 5: sign-in, one prefilled prompt, 30 s video (renders in roughly a minute or two; **verify actual render time on QA**), push permission asked while waiting.

**Create flow.** Prompt entry is good (dictation, examples). Problems: control density, clipped platform chips, "Also works" duplicates the format row, cost clarity partial, 4K double only deep. The question sheet is the best idea in the flow ("You decide" chips, progress dots); keep it, but run it only when the intake judges the prompt vague and never for the first video. Cost clarity rule for all platforms: the CTA always carries the final credit number, one tap shows "why" (length x1 per minute, 4K x2).

**Waiting.** Section 4.

**List and player.** See findings 4 and 6 and mockups 01, 04. Add thumbnails (poster frame) for finished and in-progress; group by day; one component for Making everywhere.

**Sharing and export.** Share (system sheet) is right; add Save to Photos / download (web), link share (a `watch` page exists), and make the file name the title. Remove "Copy title".

**Editing.** Not captured (editor screens need a real video). From code the editor is a full-screen cover on iOS and `EditorScreen.kt` on Android, `Editor.tsx` on web (three implementations of a scene list). Surface it as a primary action on the player and keep scene-level edits cost-free where true.

**Credits, wallet, paywall.** Mockup 05. Principles for the future paywall: show cost before the tap (already done), never block a finished video, offer purchase at the moment of insufficient credits (the existing no-credits status line "You have no credits - Add credits" is the right place), packs with a clear "never expire", free daily credit explained kindly. No price is proposed here.

**Trust and safety messaging.** Tone is already the best part: plain, specific, "Nothing was charged." Improve: blocked/unsupported sheets should offer an example and a way to ask for review; the web "Not allowed" chip is cold, use "Can't be made" with the reason inline (as iOS does).

**Empty, error, offline, loading.** Good empty states on home and Media. Missing or unverified: offline banner on home (no capture; code has `cloud_off` icons in Media only), skeletons on the video list (the Create checking state has a good skeleton: reuse its look), web grid uses grey boxes forever because there are no thumbnails.

**Motion and haptics.** Spec exists in `docs/UI_DESIGN.md` (motion table) but only 16 `sensoryFeedback`/UIKit haptic call sites on iOS and 4 on Android; reduced-motion handled on iOS (55 references) and Android (`Common.kt`), only 2 on web. Add the haptic rules in section 6.

**Typography, spacing, colour, icons.** Tokens fine (section 6 compares). Issues: iOS fixed sizes (finding 3); type on web is small; web icons are ad hoc while mobile is SF Symbols / Material Symbols Rounded (acceptable: "native expression"); the gradient is used on every primary button, hero and logo: keep it for the one primary per screen.

**Accessibility.** iOS: Dynamic Type (finding 3), sign-in overflow; `accessibilityLabel` exists on chips (e.g. FixChip replaces the bolt glyph with "credits": good); VoiceOver order not verified. Android: 68 `contentDescription` sites; TalkBack and font scale 200% not verified (emulator). Web: 46 aria/role attributes, focus ring pink (`.focus-visible`), reduced motion 2 references; keyboard path through the modal not tested.

**Copy and microcopy; Spanish.** Voice is warm, short, honest: keep. Spanish expands about 20 to 30%: the issues are 1-line chips ("Shorts - Reels - TikTok", "Use 1 min - 1"), the nav "Cancel / New video / (hidden)" header, "Describe your video to continue", tab labels ("Videos", "Media" -> "Mis fotos"/"Multimedia"). Rules: every label wraps except tab titles (max 14 chars, abbreviate), chips grow in height not width (wrap or move to a grid), no text baked into images (none found: the logo and the empty-state fan are pictures without text), numbers and units via formatters (`3 min`, `⚡3`), no string concatenation for sentences (`Just a video - Landscape 16:9 - 1080p - about 3 min` is concatenated).

**Cross-platform consistency.** iOS and Android share tokens and flows (the Android code follows the same mockups). Web diverges (finding 5). The three "making" UIs differ (list card segments, detail checklist, web "Running" chip).

**Tablet / landscape / wide web.** iPad: stretched phone layout (finding 4). Web: grid goes 3 columns at 1280 and 1 at 390, fine, but the content is left-aligned in a wide empty page and the 820 px tablet view uses 2 columns with 11 px text.

## 4. Waiting-experience concept (mockup 03, `docs/ux_review/mockup_03_waiting.png`)

What the person sees:
1. Tap Create: the sheet closes, the new card appears on top of the list already in the **Making** state with the title (from the prompt) and an honest ETA range, not "3 min": show "about 2 min left" once the backend reports it, else "a few minutes" (current copy "About 3 min left" is derived from requested minutes; check how it is estimated, `stageSince` in `AppModel`).
2. Stage names that are verbs of real work: Script written (7 scenes) / Voice recorded / Finding visuals 3 of 7 / Final cut. Backend already has the stages (`VideoStatus.Stage`: starting, writing, voiceAndVisuals, rendering); **needs backend**: per-scene progress and scene thumbnails / the narration line per scene (progressive preview). Without backend work, phase 1 ships the nicer layout with the 4 stages.
3. Preview stage: the narration line of the current scene on the making gradient; thumbnails fill in as visuals are found; tapping a thumbnail shows it large. Not gimmicky because it is true work, readable, and lets the person catch a wrong script early (offer "Looks wrong? Cancel and edit" while credits are still returnable, if the product allows).
4. Leaving is explicit and safe ("You can leave: we'll tell you when it's ready"). The notification permission is asked here with a reason (not at launch); iOS Live Activity (compact: bolt + "scene 3/7", expanded: stage + bar), Android ongoing progress notification, web: tab title "(2 min) videomk" plus Notification API if granted.
5. Done: one push "Your video is ready" with the poster frame; one success haptic if the app is open; the card flips to Ready with a 280 ms cross-fade; tapping it opens the player with autoplay muted off (the person pressed play by tapping the notification).
6. Failure: the same card turns calm (danger container, no brown), "No credits were used", Try again.

Requires: APNs / FCM registration endpoint and a "video complete / failed" send (not built, `docs/mobile/SPEC.md` lists it as future); everything else is client work.

## 5. First-run flow (mockup 07, `mockup_07_onboarding.png`)

1. Sign-in (mockup 06): one headline, a 20 s sample video (muted loop, poster only with Reduce Motion), Apple / Google / email.
2. "What should your first video be about?" Prefilled editable prompt, 3 example chips, defaults 30 s / landscape / auto look / subtitles on, shown as "about 2 minutes to make, free". No question sheet this time. "Customise length and look" stays as a text link.
3. Making (waiting concept) with the notification ask.
4. Result: the player edge to edge, Share, "Make the 3-minute version", free daily credit mentioned once.
Success metric: time from install to first playable video under 3 minutes on a median connection; first-video completion rate; D1 return for people who got push.
Decision needed: is the first video free (the sign-in copy "Your first video is free" is a promise; today there are welcome and daily free credits per `WalletView` strings).

## 6. Design system proposal

### 6.1 What exists (reuse, do not rewrite)
- iOS `mobile/ios/VideoMK/Theme.swift`: colours (dyn light/dark), `radius 16`, `gradient`, `makingGradient`, `PrimaryButtonStyle`, `Card`, `Elevation`, `FixChip`, `Shake`. Fixed font sizes in views.
- Android `ui/Theme.kt`: `VmkColors` (same values), `Vmk.radius`, gradients, `PrimaryButton`, `Card`, M3 `ColorScheme` mapping. `UiKit.kt`, `Common.kt` (reduced-motion check).
- Web: none (Tailwind default palette, `global.css` has only shimmer / ratio / focus utilities).
- Spec: `docs/UI_DESIGN.md` (g) and (h) already define roles, type scale, radii, motion, haptics, components. Mobile code matches (checked `Theme.swift` against the table: identical hex values). **The spec is right; the gap is enforcement and web.**

### 6.2 Tokens v2 (`docs/ux_review/tokens_v2.css`)
Same names as today. Changes only: `textTertiary` light `#6C7290 -> #5F6585` (5.0:1 on surface2) and dark `#7C84A3 -> #8A92B0`; new `live` accent = existing `secondary #22D3EE`, restricted to live progress; add `glass` and `shadow` tokens. Everything else unchanged so nothing breaks.

Ten-line summary:
1. Colour: background / surface1-3 / outline / text 1-3 / primary + container / success / warning / danger (+containers), light and dark; one gradient (#5B5EF0 to #8452F4, lighter in dark) for the single primary action per screen; "making" gradient for in-progress surfaces; cyan only for "alive".
2. Type: iOS SF with **text styles** (`largeTitle 34, title 28/30 bold, title3 19, body 17, subheadline 15, footnote 13, caption 12`) and `relativeTo:` scaling for any custom size; Android Roboto Flex mapped to M3 roles (`headlineLarge ... labelSmall`) with sp; web Inter (self-hosted) in rem (16 px base) with the same scale; tabular numerals for credits, durations, counts; max 1 line only on tab labels.
3. Spacing: 4 pt base (4, 8, 12, 16, 20, 24, 32); screen margin 16; sheet margin 20; min touch target 44 pt iOS / 48 dp Android / 44 px web.
4. Radii: 12 fields and thumbs, 16 cards and snackbars, 22 video cards and rows' thumbnails 14, 28 composer, 30 sheets, full pills.
5. Elevation: level 1 hairline, 2 `0 8 24` tinted, 3 `0 16 48` (sheets, tab bar); dark mode uses lighter surfaces plus 1 px ring instead of shadow.
6. Motion: 120 to 200 ms for press and selection, 280 to 380 ms for sheets and card insertions, ease-out `cubic-bezier(.2,.8,.2,1)`; sheets use system spring on iOS and `cubic-bezier(.05,.7,.1,1)` on Android; shimmer 2.4 s; **reduced motion: fades up to 120 ms, no scale, no shimmer** (already specified).
7. Haptics: send / create (medium impact), selection (selection tick), limit or not-ready (warning), video finished with app open (success), upload finished (success once). Nothing else vibrates.
8. Components (exact specs live in `docs/UI_DESIGN.md` (h); additions): **VideoRow** (128x72 thumbnail radius 14 with duration chip, title 16/21 semibold 2 lines, meta 13/18), **MakingCard** (gradient, stage verb, scene counter, 5-thumb strip, 4-segment bar), **StyleRow** (summary + Change), **CostLine** (bolt + "3 credits - 39 left" + "What does this cost?"), **WalletHero**, **EmptyState** (illustration, 28/34 headline, 15 body, one action), **Toast/Snackbar** (existing spec).
9. Icons: SF Symbols iOS, Material Symbols Rounded Android, one shared 24 grid SVG set on web with 1.8 stroke; the bolt is the brand glyph everywhere (filled).
10. Governance: one `tokens.json` (colours, spacing, radii, durations, haptic map) generates `Theme+Generated.swift`, `Tokens.kt` and `tokens.css`; a CI check compares the generated files; no raw hex or `font(.system(size:))` outside the generator (lint rule).

### 6.3 Platform notes
- iOS: build `Font.vmk(.body)` that wraps a text style so `Theme` owns the scale; replace the 255 fixed sizes mechanically (map by size: 34/30/28 title, 19 title3, 17 body, 15 subheadline, 13 footnote, 11-12 caption) and add `dynamicTypeSize(...accessibility3)` caps only where a one-line chip must stay one line.
- Android: already uses `MaterialTheme.typography`; confirm `Typography` is defined (not default) and check `fontScale 2.0`.
- Web: introduce CSS variables from `tokens_v2.css`; replace the pink/blue gradient with the indigo gradient; add `prefers-color-scheme` dark; thumbnails from `preview_gif_url` (already in the list payload) with a poster fallback.

## 7. The ten most valuable changes (ranked by activation, retention, perceived quality)

Effort: S under 2 days, M 2 to 6 days, L over 6 days, per platform.

| # | Change | Impact | iOS | Android | Web | Notes |
|---|---|---|---|---|---|---|
| 1 | Waiting experience: one Making component (list card + detail), scene counter, preview, leave-safe copy, completion transition | Retention, quality | M | M | M | Phase 1 with existing stages. Scene thumbnails need backend (L) |
| 2 | Push + Live Activity / ongoing notification on completion | Retention | M (+Live Activity M) | M | S (title/Notification API) | Needs backend registration and send (M) |
| 3 | First-run: prefilled first prompt, 30 s defaults, sample video on sign-in, push ask | Activation | M | M | M | Needs owner decision on free first video |
| 4 | Create simplification: prompt-first, Style row + sheet, cost line with explainer | Activation | M | M | L (web create has no options today) | Keep question sheets; presets for platforms |
| 5 | Dynamic Type / font scale: scale tokens, fix sign-in overflow, test at XXL | Accessibility, store risk | M (mechanical, 255 sites) | S (verify) | S | Do before localization lands in views |
| 6 | Video list: thumbnails rows, day groups, Create in tab bar (no FAB overlap), iPad two-column | Quality | M | M | M | |
| 7 | Player and detail: edge to edge, Share primary, Save, Edit prominent, Next card (vertical version, another) | Retention | M | M | M | Vertical version = a new create call with same script (check backend) |
| 8 | Web visual unification: tokens, indigo gradient, dark mode, thumbnails, AA contrast, 16 px base | Perceived quality | - | - | L | Biggest visual gap |
| 9 | Wallet rebuild and cost explainer shared with Create; paywall-ready layout | Revenue readiness | S-M | S-M | M (web has no wallet) | No pricing decisions |
| 10 | Token governance: `tokens.json` generator, fix textTertiary, haptic/motion helpers, audit lint | Consistency | S | S | S | Enables all above without drift |

## 8. Annotated mockups (clearly "MOCKUP", light and dark)

All in `docs/ux_review/` (PNG; source generator `mockups_gen.py.txt`; tokens `tokens_v2.css`):
`mockup_01_home.png` (before real capture, after light, after dark), `mockup_02_create.png` (before, after light, Style sheet dark), `mockup_03_waiting.png` (before, detail light, lock screen Live Activity + done push), `mockup_04_player.png`, `mockup_05_wallet.png`, `mockup_06_signin.png`, `mockup_07_onboarding.png` (three steps). Numbered pins on the left edge of each phone map to the annotation list beside it. Thumbnails are gradient placeholders; prices in the wallet are `$X` (not a proposal); "Your first video is free" depends on the owner decision. Not mocked up: web screens and Android (the Android expression follows the same tokens with M3 components: `NavigationBar` with a centre FAB-style Create, `ModalBottomSheet`, ongoing progress notification). Spanish check: mockup labels were designed to wrap; real validation happens in the implementation gate below.

## 9. Phased implementation plan (parallel, low collision)

Constraints: account-deletion UI and sign-in work are in flight (files: `DeleteAccountView.swift`, `SignInView.swift`, `AppModel.swift`, `SettingsView.swift`, `VideoMKApp.swift`; Android `DeleteAccountUi.kt`, `SignInScreen.kt`, `Root.kt`, `SettingsScreen.kt`; web `BaseLayout.astro`, `signin.astro`, legal pages), and localization will touch almost every string.

- **Phase 0 (now, no UI code):** owner decisions (section 11), `tokens.json`, backend tickets (scene progress, push).
- **Phase 1: tokens (S each, parallel).** iOS `Theme.swift` + new `Typography.swift` (Font.vmk), Android `Theme.kt`/`Type.kt`, web `tokens.css` imported from `global.css`. Gate: unit/snapshot of token values equal across platforms; contrast script green; no visual change except textTertiary.
- **Phase 2: Dynamic Type + components (M).** iOS replace fixed fonts file by file, in **localization-friendly order**: do the type pass in the same PR window as string extraction for each file to avoid two merges; Android verify font scale 2.0; web rem scale. Components: VideoRow, MakingCard, CostLine, StyleRow, EmptyState, WalletHero per platform. Gate: existing UI tests (`VideoMKUITests`, `QuickUiTest`) + screenshots at default, XXL, SE for sign-in, home, Create using the `VMK_DEBUG_*` fixtures.
- **Phase 3: screens, one owner per platform per screen (order avoids conflicts):** (a) home list + tab bar Create + iPad layout, (b) waiting component and detail, (c) player/detail, (d) Create + Style sheet, (e) wallet, (f) first-run. Do not touch sign-in, settings or delete screens until their in-flight work merges; they only receive token/type updates (Phase 2) and the sample video (Phase 3f).
- **Phase 4: web unification** (parallel to 3): tokens, dark mode, thumbnails, create modal parity, generations grid, watch page; keep `signin.astro` changes minimal until sign-in work merges.
- **Phase 5: push / Live Activity / notifications** after the backend endpoint exists.
Each phase gate: build + unit tests, UI tests on iPhone 17 Pro and the SE simulator, Android emulator tests (**needs a working emulator image: the current `pi35` shows a black screen here; fix environment first**), web headless screenshots at 390 / 820 / 1280 light and dark, a Spanish pseudo-localization run (strings +35% with accents) on Create and home, and a screenshot diff against these mockups.

## 10. Quick wins (safe now, no flows change)

1. `textTertiary` to `#5F6585` (light) / `#8A92B0` (dark): fixes AA on background and surface2.
2. iOS Settings: "Sign out" in `primary` text, not danger red; add rows Support and Terms next to the Privacy link already being added (pages exist on the web).
3. Remove "Copy title" from the detail screen; move "Copy description with credits" inside the credits disclosure.
4. Wallet: delete the permanently disabled "Get more credits" button or label it "Coming soon" with a tertiary style; move the 1 credit = 1 minute sentence out of the footer into the body at 15 pt; never render "unlimited (test account)" outside debug builds.
5. Sign-in: make the tagline equal the home headline; wrap (never clip) button labels at XXL.
6. Home: add bottom content inset equal to the floating button height so the last card is never covered; failed card from near-black brown to `dangerContainer`.
7. Web: contrast fix on the gradient (use `#4F52E0 to #8452F4` with white, 4.9:1), minimum 14 px text, `Not allowed` -> `Can't be made`, show `preview_gif_url` thumbnail when present, add `color-scheme: light dark`.
8. Question sheet: clip the chip row behind the sheet and decide one exit label ("Skip" and "Make it now" differ only subtly: pick "Skip questions").
9. Formatters: replace concatenated strings (`Just a video - Landscape 16:9 - 1080p - about 3 min`) with one localizable format string before Spanish.
10. Add a Support / contact row to the paused, blocked and failed states.

## 11. Decisions needed from the owner

1. Is the first video free (sign-in copy and first-run depend on it)? How many free credits at sign-up versus daily?
2. Default first-run length (proposal: 30 s) and whether a 30 s video is an acceptable first impression for the category.
3. Approve moving Create into the tab bar centre (removes the floating button) and the Style sheet replacing the visible format/length chips.
4. Approve the web switching to the app's indigo identity with dark mode (retiring the blue-pink gradient).
5. Push notifications and Live Activity: go ahead and fund the backend work (device registration, send on complete/failed)?
6. Backend: expose per-scene progress and poster thumbnails during the render (needed for the progressive preview; otherwise stage-only).
7. Paywall timing and shape (packs vs subscription) and whether to show prices on web first.
8. Tablet: invest in a real iPad / Android tablet layout now or ship phone-only with a centred max-width column first?
9. Android: provide a working emulator image or a device for the screenshot gate (current AVDs show a black screen).
