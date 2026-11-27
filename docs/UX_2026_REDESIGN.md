# videomk UI/UX 2026 redesign: review and spec (iPhone first, Android second)

Date 2026-11-27. Stage 1 of 2: review and spec only. No app source was edited, nothing committed or deployed.
Owner brief: "too much text cluttering the options; when you play a video too many labels with text, not easy to understand and select; minimalist, modern, 2026 world class, like the best apps in the world; nothing is off limits."
This replaces the "polish" tone of `docs/UX_REVIEW.md` (2026-11-26, phases 1 to 3 already built on iPhone) with a **subtraction brief**: every screen loses most of its words. That review's findings on accessibility, Dynamic Type, tokens and the waiting card remain valid and are not repeated.

Evidence in this repo: `docs/ux_2026/` (`ev_*.png` = real iPhone 17 Pro captures of the current build, light; `board_light.png` / `board_dark.png` = the redesign mockups; `gen.py` = their generator, `tokens.css` = the tokens used). Full capture set (33 screens, dark too) and the capture script: `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/ux26/` (`shots/`, `shot.sh`); temporary, the repo copies are the durable ones.

## 0. How this was done, and what is not verified

| Item | Status |
|---|---|
| iPhone 17 Pro, light | Captured from a fresh Debug build of the working tree with the app's own fake data (`VMK_DEBUG_*`): home empty / list / many, Create (empty, filled, options, photos, 4K, no credits, question 1/2/summary, checking, unsupported, blocked, paused), video detail ready (real forest clip) / making / failed, Media, upload, organize, Settings, Credits, Feedback, Rating, a presentation (deck) state. |
| iPhone dark | Home, Create, player detail, Media captured, **not studied in detail**; the redesign boards are drawn in both. |
| iPhone SE, Dynamic Type XXL, Spanish | Not re-captured now. `docs/UX_REVIEW.md` has SE and XXL captures from the previous build; Spanish expansion is estimated (+20 to 30 %). |
| System player controls | Not captured: the simulator tool in this session cannot tap. The inline and full screen controls are Apple's `AVPlayerViewController` (code: `PlayerView.swift`) and I describe them from code and from Apple documentation, **not from a screenshot**. |
| Android | **Not captured.** The emulator is still unusable (black screen, documented in `docs/UX_REVIEW.md` section 0; I did not retry). Android is reviewed from code (`ui/*.kt`, 8,252 lines, same flows and the same tokens as iOS) and `docs/ui/*.png`. Every Android statement is marked "(code)". |
| Competitor research | Web search in this session returned only Apple WWDC25 session pages (tab bar, sheets, "clear" Liquid Glass for content over video), Android Media3 Compose Material 3 docs (Player with `topControls` / `centerControls` / `bottomControls` slots, configurable auto-hide timeout), and app-design write-ups. It did **not** return the actual Runway, Luma, Sora or CapCut flows. Where I name them below it is **general product knowledge, labelled as such**, not a fresh fetch. |
| Text counts | Counted by hand from the captures (visible words, one screen state, no scrolling unless stated). Good to about +-10 %. |

Not-yet-known: how the iOS 26 system player looks on this exact build (the simulator is iOS 26.5); whether the inline `AVPlayerViewController` already shows its own full screen button next to ours (`InlinePlayer` adds one: **verify on a device**; if the system one is present, delete ours).

## 1. The ten biggest problems (with evidence)

1. **Create is a form, not a prompt box.** Before the first tap the iPhone Create screen shows about **82 words and 30 text elements** (`ev_a_home_create.png` panels 3 to 4): Cancel, title, placeholder, mic hint, "Add photos / Optional · from this phone or My media", "WHAT IS IT FOR?", six platform chips, a format sentence ("Just a video · Landscape 16:9 · 1080p · about 3 min") with a "Change" link, "Also works:" and three more chips, "LENGTH" and five two-line chips, a status line and the button. "More options" adds about 55 more words (Look x4, Subtitles, Language, Format x4 with "Beta", 720p/1080p/4K, "2x credits", a 12 word 4K note: `ev_b_create_options_questions.png`). Total about **140 words in one sheet**. The best apps in this category are prompt-first with one settings affordance.
2. **The same decision is asked three times.** "What is it for?" (platform) already implies format, length and resolution, yet the screen then repeats it as a sentence, as "Also works" chips, as five length chips and again in More options (Format and quality). The user chooses one thing and sees it four times.
3. **The video screen puts 8 text elements next to one video.** Ready video detail (`ev_c_detail_media.png`, panel 1): navigation title, the same title again as a heading, "Share", "Save to Photos", "Make another video", "Describe your next idea.", "Send feedback", "Description and photo credits": about 22 words and **five different actions (two of them full-width buttons, one a bordered card)**, under a player whose own controls (time, scrubber, skip, speed, captions, AirPlay, PiP in the system control set) already carry text. The owner's complaint ("too many labels with text") is exactly this: nothing is wrong, everything is labelled and nothing wins.
4. **Home hides content and repeats itself.** The floating "New video" pill covers the third video card on iPhone 17 Pro (`home_videos`, `home_many`), the first-run home shows the same idea three times (headline, "Make your first video" card with its own quoted idea and two buttons, "TRY ONE" list row, plus the "New video" pill) = about **70 words before the user has typed anything**. A video list row carries title, "1 day ago", "Landscape", duration: 4 text items for one fact (when it was made).
5. **Settings is a wall of footnotes.** First Settings screen: about 100 words, of which **70 are footer paragraphs** (language, photos, organize, delete) (`ev_d_settings_wallet_feedback_rating.png`). Footers explaining a switch belong behind an (i), not under every row.
6. **Credits explained in prose.** The Credits sheet opens with four bullet paragraphs (about 55 words) before it says what to do (`wallet.*` strings: "1 credit makes up to 1 minute of video, rounded up", "A 10-second and a 60-second video cost 1 credit...", "4K costs double...", "Free credits expire..."), "Get more credits" is a disabled button, and one bucket label reads "unlimited (test account)". The Create button already shows the answer ("Create · ⚡2").
7. **Two vocabularies for "making".** Home card ("Making", stage words, four step labels under a bar, ETA), detail ("MAKING YOUR VIDEO" overline, title, a promise sentence, a card with the same four labels as a checklist). Same data, two layouts, about 45 words on detail.
8. **Chips and tiles are the default control, even for 6-way choices.** 11 chips on Create (platform 6 + also-works 3 + ...), 5 more for length, 4 format tiles, 4 look tiles, 3 resolution segments: **27 selectable things** on one task. Menus, steppers and presets exist for this; a chip row should be 3 items or fewer.
9. **Icons and labels are inconsistent, and the brand mark is stale inside the app.** SF Symbols with text for the same action in different places; **the iOS home header and sign-in still draw the old play-in-a-tile mark** (`LibraryView.swift:103`, visible in every capture) although the app icon, favicon and Android icon are now the Sparklet Trio. The logo pass missed the in-app mark on iOS.
10. **Accessibility debt that more text makes worse** (from `docs/UX_REVIEW.md`, still true): fixed font sizes in iOS views (255 `.font(.system(size:))` at that date), sign-in overflow at XXL, one-line chips that will not survive Spanish ("Shorts · Reels · TikTok", "Landscape 16:9"). A minimalist redesign fixes these by deleting the text, not by shrinking it.

What is already good and must survive: the headline "Describe it. We'll make the video."; the gradient Making card as the one rich surface; the "Create video · ⚡2" receipt-style button; "Nothing was charged." and "No credits were used."; the question sheet idea ("You decide" chips); upload/pause/cancel and the privacy-first Media screens; account deletion copy; the honest failed state with "Try again".

### Text per screen today (hand count of visible words, one state, light)

| Screen | Visible text elements | Approx words | Main contributors |
|---|---|---|---|
| Home, first run (empty) | 24 | 70 | headline, sub, first-video card, "TRY ONE" row, New video, tabs |
| Home, with videos | 22 | 45 | header, Making card with 4 step labels, rows with 3 meta items |
| Create, main | 30 | 82 | platform 6 chips + format sentence + also-works + 5 length chips |
| Create, More options | 28 | 55 | look 4, format 4 + Beta, resolution, 4K notes |
| Question sheet | 10 | 22 | progress, "Make it now", title, helper, 5 chips, Skip |
| Video detail, ready | 8 + system controls | 22 | title twice, Share, Save, Make another (+ sub), feedback, credits |
| Video detail, making | 10 | 45 | overline, title, promise, card with 4 labels |
| Settings | 17 | 100 | rows + 4 footers of 14 to 25 words |
| Credits | 12 | 85 | 4 bullets, buckets, disabled button |
| Feedback | 8 | 45 | 24-word intro, label, 3 chips |
| Media | 18 | 40 | storage, search, collections, month headers (acceptable) |

## 2. Principles (the rules every screen is judged by)

1. **One screen, one job, one primary action.** One filled gradient control per screen (Create, Share, Done). Everything else is a quiet glass or tinted control.
2. **Say it once.** If a number or word is in the title, it is not in the body. If the button carries the price, no status line repeats it.
3. **Icon-only when the icon is universal; menu when there are 4 or more choices; chip row only for 3 or fewer.** Universal here means: share, download, edit (sliders), info, more, close, back, plus, mic, photo, play. Everything else keeps a word.
4. **Smart defaults decide; the user overrides.** Platform sets format, length and resolution. The AI sets look, voice, music, language, pace. Nothing the AI can decide is a question.
5. **Progressive disclosure in two layers only:** the surface (prompt + 3 pills) and **one** Options sheet. No third level except an (i) popover for an explanation.
6. **Content is the interface.** Thumbnails and the video get the pixels; chrome floats on glass and gets out of the way (iOS 26 Liquid Glass with the "clear" variant over video; Material 3 Expressive surfaces on Android).
7. **Text budget is a requirement, not a hope.** Section 4 gives a word budget per screen; a UI test counts visible static texts and fails over budget (see work packages).
8. **Native, then brand.** System navigation, sheets, menus, haptics and the system player; the brand shows in colour, the gradient CTA, the Making card and the mark.
9. **Localisation is a layout constraint.** Spanish is +20 to 30 %: no label may rely on a single line, except tab titles (max 14 characters) and pills (max 12 characters, truncate in the middle never).
10. **Nothing leaves the product.** Every feature stays reachable (section 3 maps each one); we only remove clutter, never function.

## 3. Information architecture (new)

```
Tab bar (floating, glass):   [ Videos | Media ]   (+)   <- Create is a separate round action, always reachable, never covers content
Top right (every tab):       credits chip  ·  account (person icon) -> Settings
Videos -> Video (player)  -> Share · Save · Edit · Info · More (Make another, Send feedback, Delete)
(+)    -> Create sheet: prompt · 3 pills (For, Length, Look) · Options sheet (everything else)
Media  -> unchanged structure (collections, months, search), text diet
Settings (from account icon): Account · Language · Photos · Help (Feedback, Support, About) · Delete account
Credits (from chip): one number, one line, "How credits work" behind (i)
```

Where each existing feature goes (nothing removed):

| Today | New home |
|---|---|
| Floating "New video" pill | Round (+) next to the tab bar (iOS), FAB-in-bar on Android (Material 3 Expressive navigation bar with a FAB slot or an extended `+`) |
| Platform chips (6) + format sentence + Change + "Also works" | **"For" pill** (menu of 6) + the same list inside Options |
| Length chips (5) | **"Length" pill** (menu or stepper with the credit price per row) |
| Look tiles | **"Look" pill** (menu with swatches) + Options |
| Format tiles, 720p/1080p/4K, Subtitles, Language | Options sheet only |
| Add photos card, deck button | Photo icon button inside the prompt card (+ thumbnail strip appears only when something is attached); "Add a presentation" is a row in the photo menu |
| Credit status line | The button label (`Create · ⚡2`) and, under it, one caption only when it matters ("3 left") |
| Question sheets | Same flow, stripped (section 4.6) |
| Share / Save to Photos / Edit | Icon actions under the video (Share filled, others glass) |
| Make another video, Send feedback, Description and credits | `More` menu and Info sheet |
| Wallet explanation | (i) popover on the credits sheet |
| Settings footers | (i) popovers or deleted |

## 4. Per-screen redesign

Mockups: `docs/ux_2026/board_light.png` and `board_dark.png` (seven screens: Home, First run, Create, Options, Video, Making, Settings). Numbers are word budgets (visible static text, English, not counting the user's own content).

### 4.1 Video screen (the player), priority 1. Budget: 8 words visible besides the title
Today: see problem 3. Redesign (mockup "Video (player)"):
- **Navigation**: back (glass circle), title centred once (one line, truncate), nothing on the right. The heading under the video is **deleted**; instead a small caption "1:20 · 1080p" under the video (duration and quality are the only metadata).
- **Video**: edge to edge, poster with a centred glass play button before playback, system controls after the first tap. Inline player keeps the system controls (scrubber, play/pause, skip, captions, AirPlay, PiP: accessible, familiar) but:
  - **we add nothing text-like on top of it**. Our own full screen button is an icon in the same glass style, top right, auto-hiding with the controls (today it stays; verify duplicate with the system button, section 0).
  - Controls auto-hide after 3 s of playback (Android: Media3 `controllerShowTimeoutMs = 3000`; iOS system default).
  - Portrait/square videos keep their own shape (as built), max height 560 pt.
- **Action row under the video, icons only**, spaced evenly, each 44 pt (56 for Share), spoken labels for VoiceOver/TalkBack:
  `Share` (filled gradient, the one primary) · `Save to Photos` (download) · `Edit` (sliders) · `Info` (i) · `More` (...).
  - `Info` opens a bottom sheet: description, photo credits, copy button (replaces the "Description and photo credits" disclosure and "Copy description with credits").
  - `More` menu: Make another video, Send feedback, (Report this video if the report path ships), Delete video if/when it exists.
  - **"Make another video" disappears as a card.** After playback ends, the video area shows an **end card with two icon buttons**: replay and "+" (new video, label "New video" shown only here because the video has ended and there is room). That is the retention hook without a permanent card.
  - Tooltips/long-press: iOS `.help` + `accessibilityLabel`; Android `tooltip` + `contentDescription`. A first-run coach mark is not used.
- **States**: loading = black with a spinner; error = one line + "Try again"; failed (detail failed) = one icon, "Something went wrong" (3 words) + "No credits used" + Try again (3 elements, today 4); rejected = same pattern with the reason line.
- **Making** (video not ready): see 4.5.
- Acceptance: static texts on the ready screen <= 6 (title, caption, "Share" is **not** visible text because it is an icon) + system controls; at XXL the five icons wrap to two rows, never clip.

### 4.2 Create, priority 1. Budget: 14 words on the main surface, 40 in Options
Surface (mockup "Create"):
- Top: close (X, glass circle). No "Cancel" text, no "New video" title (the sheet is the title). If text is typed, closing asks "Discard?" (existing).
- **Prompt**: large borderless text (24 pt, light weight feel), placeholder "A video about…" (3 words; the long example sentence moves to the example chips on first run only). Caret and keyboard open immediately.
- Under the prompt, two glass icon buttons: **photo** (opens the photo menu; shows a count badge when attached) and **mic** (dictation; the "Tap the mic to speak" hint is deleted: the mic icon is universal and the listening state already says "Listening… tap to stop").
- **Three pills** in one horizontally non-scrolling row: `For ▾` (value shows the choice: "Video", "YouTube", "Shorts"), `⏱ 2 min ▾`, `✦ Look ▾`. Each pill opens a native menu (iOS `Menu`, Android `DropdownMenu`/`ExposedDropdown`): checkmark on the selected row; the Length menu shows the credit price on each row ("2 min  ⚡2") and greys rows over the platform's max with one footer line ("YouTube allows up to 8 min"). A fourth, icon-only `…` opens the Options sheet; **tapping any pill while holding... is not required**.
- **Create button**: full width, gradient, `Create · ⚡2`. Under it one caption, **only when informative**: "40 left" (balance) normally; "Describe your video" (disabled state, replaces the status line); "Not enough credits · Add credits" (no credits). Never more than one line.
- Removed from the surface: "WHAT IS IT FOR?", the 6 platform chips, the format sentence + Change, "Also works", "LENGTH" label and 5 chips, "Add photos" card, "Tap the mic to speak", the (i) icon (its content moves to a long-press/(i) on the Length pill and the credits sheet).
- **Photos**: when images are attached a single horizontal thumbnail strip (56 pt) appears between the prompt and the pills with "+" at the end and "100" count badge for >4. "Add more photos" and "Edit" labels become icons. A presentation attached shows one chip "slides.pptx ✕".
- **Platform behaviour (the smart default)**: choosing "For: YouTube" sets format 16:9, length 3 min default (platform recommendation already in the backend `platforms`), resolution 1080p (4K offered only for YouTube and "Video", and only in Options with the 2x note once). "Shorts · Reels · TikTok" sets 9:16 and 30 s. "Instagram" sets 4:5 and 30 s. "X", "LinkedIn" set their recommendations. The pill values update visibly, no sentence needed. The user's later manual change of length sticks.
- **Options sheet** (mockup "Options", one sheet, medium detent, scrolls if needed; title "Options", "Done"): `FOR` six chips (the same list, so VoiceOver users have all choices in one place), `LOOK` four swatches with their names (Auto, Midnight, Paper, Sunrise), `QUALITY` segmented (720p | 1080p | 4K; "4K" shows a small "2x" tag, the explanatory sentence is replaced by an (i) popover), `Subtitles` switch, `Language` row (value "Auto"), and `Format` as **four icon tiles** (landscape, vertical, square, portrait; the shape is the label; the name only as the selected tile's caption; the word "Beta" becomes a small dot with an accessibility label; **hide formats that are not ready for the account** instead of dimming).
- **Question sheet**: unchanged flow, text diet in 4.6.
- Acceptance: main surface visible static text <= 14 words (tests count the strings in the view hierarchy); Create reachable without scrolling on iPhone SE (the surface has no scroll); 3 pills fit on SE at default size and wrap to 2 rows at XXL.

### 4.3 Home and first run, priority 2. Budget: 12 words (first run), 6 plus the user's own titles (list)
- **Header**: new Sparklet mark (small, no wordmark: the app name is the icon), credits chip, account icon (replaces the gear: it leads to Settings and signed-in state). Large title "Videos".
- **Making card**: one card, title (the user's own words), **one line** "Finding pictures · 3 of 7", thin progress bar. The four step labels under the bar are deleted (the line says the stage). Tapping opens the Making detail (4.5).
- **List**: row = thumbnail 112x63 with duration chip on the picture, title (2 lines max), and **one** meta word when it is not the default ("Vertical" icon badge for 9:16/1:1/4:5 instead of the word; "1 min" is dropped because duration is on the picture; day grouping headers replace "1 day ago"). Failed row: red-tinted thumbnail with "!", line "Didn't finish · Try again" (4 words; the reassurance "No credits were used" moves to the detail).
- **Create (+)** sits beside the floating tab bar, so it never covers a row; the tab bar minimises on scroll (`tabBarMinimizeBehavior(.onScrollDown)` on iOS 26; custom fallback below 26).
- **First run** (mockup "First run"): headline (the existing 2 lines), a real prompt field (tapping opens Create with the keyboard up), **three example chips**. Deleted: the fan illustration copy line, "Make your first video" card with quote and two buttons, "TRY ONE" row. The first video defaults (30 s, 1 credit, auto look) are not announced: the Create button shows the price.
- **Empty list after first video**: nothing but the list.
- Acceptance: first run visible text <= 14 words; a list of 40 videos shows >= 6 rows on iPhone 17 Pro without overlap; no element within 16 pt above the tab bar except content.

### 4.4 Settings, Credits, Feedback, Rating. Budget: Settings 30 words, Credits 18, Feedback 14
- **Settings** (mockup): large title, `Done`. Groups: account (email as the header row, `Sign out` as a plain row), `Language`, `Photo dates` and `Photo locations` switches (no footers; one (i) per group), `Send feedback`, `Support`, `About 1.0`, then **`Delete account`** as a plain red row (no footer; the confirmation screen already itemises the consequences). "Organize new uploads" becomes a row with a value ("Ask") and no footer.
- **Credits**: hero card (the number and one word "credits"), under it a single line **"Free credits renew daily"**-style sentence only if true (the backend knows), a `How credits work (i)` that opens a popover with the four lines as a tiny table (`1 min = 1 credit · 4K = 2x · free credits expire · bought credits never expire`), and **no disabled button**: until purchase exists show nothing (not "Get more credits" greyed). The label "unlimited (test account)" is removed from user-visible strings (show "∞").
- **Feedback**: intro is one line "Tell us anything." (3 words); text field; the category chips stay (3, optional) with the word "Optional" removed (the label "What is it about? (optional)" becomes a plain placeholder in the chip row: "Topic"); `Send`.
- **Rating**: unchanged (already minimal: "Enjoying videomk?" Yes / Not really).

### 4.5 Making (progress). Budget: 12 words
Mockup "Making": back, the user's title (large, 2 lines), one gradient card: the stage in a verb ("Finding pictures", the one live word), `Scene 3 of 7 · about 2 min`, a strip of **scene thumbnails as they are found** (4 slots, the last empty; needs backend only for real thumbnails: phase 1 shows the four stage dots instead), progress bar. Below it **one** sentence: "You can leave. We'll tell you when it's ready." (existing `making.leave_promise` shortened). Deleted: the overline "MAKING YOUR VIDEO", the second header, the checklist with four words and spinner (a duplicate of the card), the 15 word sub line.
Same component on the Home card (Making card compact = title + stage line + bar) and the detail; the Live Activity and Android ongoing notification reuse the stage verb and the scene counter.

### 4.6 Question sheets and system sheets. Budget: 12 words
- Question sheet: progress dots, **`Skip`** (top right, replaces both "Make it now" top and "Skip" bottom, which look like duplicates, `ev_b_create_options_questions.png`), the question as a title ("Who is this for?", the helper line "Helps us pick the right words and pace." is deleted), the answer chips, "You decide" (with the sparkle) as the last chip. "QUESTION 1 OF 3" becomes the dots only.
- Summary sheet ("Ready when you are"): the request as editable text, the answer chips, the price on the button; deleted: "Tap an answer to change it." (chips already show a pencil), the format sentence (it is in the pills), the second exit "Edit request" (replaced by the sheet's grabber and a close icon).
- Blocked / unsupported / paused: icon, one title, one reason line, `Nothing was charged.`, one button (`Edit request`), close icon. The example box ("FOR EXAMPLE ... Use this") stays only when the model gave one. Today these sheets are 60 % empty: use a small detent, not a tall one.

### 4.7 Media, Upload, Organize (lighter pass). Budget: no new text
Media is already the cleanest screen. Changes: search placeholder "Search photos" (was "Search your photos, try 'beach in Thailand'", 8 words to 2; the example becomes a rotating placeholder after a 3 s pause), storage "210 MB of 2 GB" becomes a thin ring in the header with the number only on tap, month headers keep, collection names wrap to 2 lines not 3 ("London · May 2026" fits as two lines on iPhone 17 Pro). Upload/Organize sheets: remove helper sentences that restate the title; keep progress, pause, cancel and "You can close the app" (that one is reassurance, keep).

### 4.8 Sign-in
Mark (the new one, not the old tile), "videomk" wordmark as image, the two-line tagline, **Continue with Apple / Google / email** (current build shows "Sign in or create account" opening the system sheet: keep it that simple), terms line. No change in copy; fix the stale logo and the XXL overflow.

### 4.9 Tablet and wide screens (not a priority now)
iPad: adaptive split view (list left, video right); Android large screens: list-detail canonical layout. Not in the work packages below; tracked as a follow-up.

## 5. Component rules

| Component | Rule |
|---|---|
| Primary button | Gradient, 54 pt high, full width, label <= 3 words plus an optional price (`Create · ⚡2`), **one per screen**. Disabled = flat tinted container, never a gradient at low opacity. |
| Secondary | Tinted text button or glass icon button. No bordered buttons stacked in a column. |
| Icon button | 44 pt hit target (48 dp Android), glass circle (iOS 26 `glassEffect` / material fallback `.ultraThinMaterial`, Android `surfaceContainerHigh` at 80 %), **spoken label mandatory**, tooltip on pointer/long-press. |
| Pill (menu) | 38 pt, icon + value + chevron, max 12 characters of value, opens a native menu; value always visible (the state is the label). |
| Chip | Only inside Options and question sheets, groups of <= 6, wrapping rows, selected = primary container + checkmark glyph (colour is never the only cue). |
| Segmented | 2 or 3 options of one dimension (quality). |
| Sheet | Medium detent by default, grabber, **one close affordance** (a button or the grabber, never "Skip" + "Close"), `presentationBackground` system glass on iOS 26. |
| List row | One line, value on the right, chevron only when it navigates; footers are not used, use an (i). |
| (i) popover | The only place for an explanation sentence; max 40 words; dismisses on tap outside. |
| Empty state | One title, one action. No illustration copy lines. |
| Error | Icon + one sentence + one action. "Try again" is the action; the reassurance ("No credits were used") is part of the sentence. |
| Toast/snackbar | One line, 2.5 s, no action unless Undo. |
| Typography | Text styles only (iOS `largeTitle 34`, `title 28`, `title3 20`, `body 17`, `subheadline 15`, `footnote 13`, with `relativeTo:` for any custom size), at most **3 sizes per screen**. Android M3 roles (`headlineLarge`, `titleMedium`, `bodyMedium`, `labelMedium`). |
| Colour | Existing tokens (`docs/ux_review/tokens_v2.css`, copied to `docs/ux_2026/tokens.css`): the gradient only on the primary button, the mark and the Making card. Cyan (`--live`) only for "alive" progress. Never cyan on light surfaces. |
| Iconography | SF Symbols (iOS, weight regular, 22 pt) and Material Symbols Rounded (Android, 24 dp); no emoji, no custom icons except the mark. |
| Touch | 44 pt minimum, 8 pt gaps between adjacent targets. |

## 6. Motion, haptics, glass

- **Glass**: iOS 26 only (`#available(iOS 26, *)` because the deployment target is iOS 17): `glassEffect` on floating controls (tab bar, (+), icon buttons over video, sheet backgrounds); fallback `Material.regularMaterial` with the same shapes. Over video use the **clear** variant (WWDC25 guidance: "clear" glass is for controls over photos and video); never on text blocks. Android: tonal surfaces and `Surface` shadows, no blur dependency (minSdk 26).
- **Motion** (as `docs/UI_DESIGN.md`): 120 to 200 ms selection, 280 to 380 ms for sheets and card insertion, ease-out; the (+) morphs into the Create sheet (iOS 26 "sheets morph out of the button that presents them"); pills show a 120 ms scale on press; the video row insert fades. **Reduced motion**: fade only.
- **Haptics**: unchanged table (create = medium impact, selection tick, warning, success when a video finishes with the app open). Nothing new.
- **Auto-hide**: player controls 3 s; the tab bar minimises on scroll.

## 7. Strings to delete or shorten (EN / ES)

All of these go through the existing catalogs: iOS `Packages/VideoMKCore/Sources/VideoMKCore/Strings/Localizable.xcstrings` (767 keys today; `create` 79 keys / 287 words alone), Android `res/values/strings_*.xml` + `values-es`. Keys unchanged where only the text changes; "(new)" keys are added; "(delete)" keys are removed after the view stops using them (the iOS `check_strings.py` gate fails on missing keys, reports unused ones, and forbids the spellings listed in `docs/I18N.md`, e.g. use "video", not "vídeo"). Spanish is given for every changed or new string; review by the owner (native speaker).

| Key (iOS) | Now (EN) | New (EN) | New (ES) |
|---|---|---|---|
| `create.describe_your_video_for_example` | Describe your video. For example: how bees make honey, explained for kids. | A video about… | Un video sobre… |
| `create.tap_the_mic_to_speak` | Tap the mic to speak | (delete; mic icon keeps `create.dictate` as its spoken label) | |
| `create.what_is_it_for` | What is it for? | (delete as a section; becomes the label of the "For" pill, spoken only) | Para |
| `create.also_works` | Also works: | (delete) | |
| `create.change` | Change | (delete: the summary sentence is deleted) | |
| `create.summary_format` / `create.more_summary_on` / `create.more_summary_off` | Just a video · Landscape 16:9 … / %@ look · Subtitles on · … | (delete) | |
| `create.length` | Length | (delete as a section; the pill shows "2 min") | |
| `create.optional_from_this_phone_or` | Optional · from this phone or My media | (delete) | |
| `create.add_photos` | Add photos | Photos (spoken label of the photo button) | Fotos |
| `create.add_more_photos` | Add more photos | (delete; "+" tile with spoken label `create.add_photos`) | |
| `create.describe_to_continue` | Describe your video to continue | Describe your video | Describe tu video |
| `create.new_video` | New video | (delete as a nav title; accessibility label of the sheet only) | |
| `create.cost_4k_double` / `create.fourk_advice` / `wallet.cost_4k` | 4K costs double the credits. / %1$@ does not show %2$@; it would cost … | One (i) popover: "4K costs 2x credits." | "4K cuesta 2x créditos." |
| `create.not_ready` | Not ready. %@ | (delete; the disabled button and its caption say it) | |
| `create.tap_an_answer_to_change` | Tap an answer to change it. | (delete) | |
| `create.make_it_now` + `create.skip` | Make it now / Skip | one key `create.skip` = Skip | Omitir |
| `create.your_request` / `create.for_example` | YOUR REQUEST / FOR EXAMPLE | (keep only inside the summary sheet; shown as the first line of the request, no overline) | |
| `create.beta` | Beta | (delete as visible text; the dot has the spoken label) | |
| `detail.copy_title` | Copy title | (delete) | |
| `detail.copy_description` | Copy description with credits | Copy | Copiar |
| `detail.description_credits` | Description and photo credits | Info (spoken label of the (i); sheet title "Info") | Info |
| `detail.make_another` + `detail.make_another_sub` | Make another video / Describe your next idea. | New video (end card and More menu only) / (delete sub) | Nuevo video |
| `detail.save` / `detail.saved` | Save to Photos / Saved to Photos | (spoken labels only; toast "Saved") | Guardado |
| `detail.failed_title` / `detail.failed_body` | Something went wrong / We couldn't finish this video. You haven't been charged for it. | Didn't finish / No credits used. | No se completó / Sin créditos usados. |
| `detail.making_overline` / `detail.making` / `detail.making_sub` | MAKING YOUR VIDEO / Making your video / This usually takes … | (delete all three; the card and the title are enough) | |
| `making.leave_promise` | You can leave. It keeps going, and it will be here when it's ready. | You can leave. We'll tell you when it's ready. | Puedes salir. Te avisamos cuando esté listo. |
| `making.step.*` (4) | Script / Voice / Pictures / Final cut | (delete as visible labels; stage verbs `making.line.*` remain in the card) | |
| `making.line.voice_visuals` | Recording the voice and drawing the pictures. | Making voice and pictures | Voz e imágenes |
| `settings.*_footer` (language, photos, organize, delete) | 14 to 25 words each | (delete; two become (i) popovers: photos 12 words, organize 10 words) | |
| `settings.signed_in_as` | Signed in as | (delete; the email is the row) | |
| `wallet.cost_title`, `wallet.cost_minute`, `wallet.cost_example`, `wallet.cost_4k`, `wallet.cost_expiry`, `wallet.rules` | four paragraphs | one popover: "1 min = 1 credit. 4K = 2x. Free credits expire; bought credits never do." | "1 min = 1 crédito. 4K = 2x. Los gratis caducan; los comprados no." |
| `wallet.get_more` / `wallet.coming_soon` | Get more credits (disabled) / Buying credits is coming soon. | (delete until purchasing exists) | |
| `wallet.unlimited` | unlimited (test account) | ∞ | ∞ |
| feedback intro | Tell us anything: an idea, something missing, something that annoyed you. We read every message and we act on it. | Tell us anything. | Cuéntanos lo que quieras. |
| `settings.*` "We read every message" under Send feedback | We read every message | (delete) | |
| `media` search placeholder | Search your photos, try 'beach in Thailand' | Search photos | Buscar fotos |
| Home first run (`videos.*`) | headline sub "Narrated and illustrated in minutes. Add your own photos if you like." + "Make your first video" card strings + "TRY ONE" | (delete sub, card and row; keep the headline) | |

Net effect on the main flows (target): Create surface 82 to 14 words, Create total 140 to 55, video detail 22 to 6, Home first run 70 to 14, Settings 100 to 30, Credits 85 to 18, Making 45 to 12. Overall about **-75 % visible words**; the iOS catalog shrinks by about 90 keys.

## 8. Defaults the AI decides (never asked in the UI)

| Decision | Who decides | UI exposure |
|---|---|---|
| Look (Auto), voice, music, pace, scenes, element types, clip/photo mix, subtitles style | Producer/director agent (already) | Look pill and Options only to override; voice/music never exposed |
| Aspect ratio, resolution default, default length | The **platform** chosen in "For" (backend `platforms` recommendations) | The pills show the result; Options override |
| Language | Same as the prompt (existing) | Options row "Language: Auto" |
| 4K | Offered only for YouTube / generic video and only when the account has it (`capabilities`) | One quality segment in Options, 2x tag |
| Clarifying questions | The intake judge (existing), **never on the first video**, never more than 3 | Question sheet with a single `Skip` |
| Subtitles | On by default (new default; the per-user choice is remembered) | Options switch |
| Photo selection | The agent picks and orders (existing behaviour) | Photo button + strip only |
| Which formats are ready | Backend `readyAspects` (existing) | **Hide** formats that are not ready instead of showing "Beta" / "Soon" tiles |

## 9. Implementation plan: independent work packages

Order: iOS player and Create first (priority 1), then home, then the rest. One iOS implementer and one Android implementer work in parallel; they share this spec and the string table (section 7); the Android implementer starts after WP-I1/I2 screenshots exist if they want a visual reference, but the packages do not depend on iOS code. Neither touches `backend/` (nothing here needs the backend; the optional scene thumbnails do, see risks).

Common rules for every package: strings through the catalogs (EN + ES), text styles only, light + dark, iPhone SE and iPhone 17 Pro, XXL Dynamic Type, Spanish, VoiceOver labels on every icon, update/extend the existing UI tests (`VideoMKUITests`) and unit tests, `swift test` + the three `scripts/check_*.py` + simulator build (iOS), `testDebugUnitTest assembleDebug compileReleaseKotlin lintDebug` (Android), screenshots with the existing `VMK_DEBUG_*` fixtures, no commit/deploy by the builder.

### iOS (one implementer)

**WP-I0 Foundations (1 day).** Files: `Theme.swift`, `Components.swift`, new `GlassKit.swift`, `LibraryView.swift` (header), `SignInView.swift`, `Assets.xcassets`. Build `GlassIconButton` (44 pt, spoken label required by the initializer, `#available(iOS 26)` glass + material fallback), `Pill` (menu label), the floating tab bar with a separate round (+) (`tabBarMinimizeBehavior` on iOS 26, custom bar below), the new mark as a SwiftUI shape/asset (replaces the old play tile at `LibraryView.swift:103`, the sign-in mark and the Making card logo), a `TextBudget` test helper (counts `Text` static strings in a view hierarchy for UI tests via accessibility). Acceptance: the old tile is gone (`grep "play.fill"` shows only real play controls); screenshots of tab bar light/dark/SE; pills and icon buttons have previews.

**WP-I1 Video screen (1 to 1.5 days). PRIORITY 1.** Files: `VideoDetailView.swift`, `PlayerView.swift`, `VideoCards.swift`, strings. Implement 4.1: delete the heading and the stacked buttons, icon action row, Info sheet, More menu, end card with replay and (+), failed/rejected layout, remove duplicate full screen button if the system one is present (verify on a device and in the simulator), auto-hide behaviour of our overlay. Acceptance: static texts on the ready screen <= 6; the five actions reachable with VoiceOver labels; Share works as before (`SharedVideo`), Save/Edit unchanged; `testDetail*` UI tests updated; screenshots: ready (portrait + landscape video), playing with controls, end card, info sheet, more menu, failed, XXL, Spanish.

**WP-I2 Create (2 days). PRIORITY 1.** Files: `CreateView.swift`, `CreateSheets.swift`, `OptionsSheet.swift`, `CreateModel.swift` (platform to defaults is already there; expose "pill values" and "hidden formats"), `AddPhotosSheet.swift`, `PhotoAttachments.swift`, `DeckViews.swift`, strings. Implement 4.2 and 4.6: prompt-first surface with photo + mic buttons, three pills with menus (Length rows with credit price), Create button with one caption, Options sheet (For, Look swatches, Quality segmented, Subtitles, Language, Format icon tiles hiding not-ready formats), photo strip, deck chip, question and blocked sheets diet. Acceptance: surface <= 14 visible words; no scroll on SE; every previous capability still reachable (UI test walks: platform change updates the pills; length menu respects platform max and shows the price; 4K only when capabilities allow; photos 1 and 100; deck attach; question flow; blocked/paused/unsupported states); cost line logic untouched (`CreateModelTests` pass); screenshots per state in light/dark/SE/XXL/ES.

**WP-I3 Home, first run, Making (1.5 days).** Files: `LibraryView.swift`, `VideoCards.swift`, `MakingCard.swift`, `AppModel.swift` (copy only), strings. Implement 4.3 and 4.5: header with account icon, thin Making card, thumbnail rows with day groups, vertical badge, failed row, first-run prompt field + 3 examples, delete the first-video card and "TRY ONE", detail Making layout (shared `MakingCard`). Acceptance: first run <= 14 words; no overlap with tab bar on 40 videos; screenshots as above.

**WP-I4 Settings, Credits, Feedback, Rating, Delete (1 day).** Files: `SettingsView.swift`, `WalletView.swift`, `FeedbackView.swift`, `RatingPromptView.swift`, `DeleteAccountView.swift` (copy only), strings. Implement 4.4. Acceptance: Settings <= 30 words, Credits <= 18, no disabled "Get more credits", (i) popovers for the explanations.

**WP-I5 Media, upload, organize text diet (0.5 day).** Files: `MediaView.swift`, `UploadViews.swift`, `OrganizeViews.swift`, `CollectionViews.swift`, strings. Implement 4.7.

**WP-I6 Hardening (1 day).** Dynamic Type everywhere touched (no fixed `system(size:)` in new code, replace the remaining fixed sizes in touched files), Spanish and XXL overflow checks, VoiceOver order, dark mode contrast, `check_strings.py` clean (no orphan keys), UI test for the text budget, final screenshot set into `docs/ux_2026/after_*`, TestFlight build.

### Android (one implementer; mirrors iOS, Compose)

**WP-A0 Foundations.** Files: `Theme.kt`, `UiKit.kt`, `Components.kt`, `Root.kt`, `LibraryScreen.kt` (header). Build `GlassIconButton` (48 dp, `contentDescription` required), `Pill` with `DropdownMenu`, the navigation bar with a (+) FAB-in-bar (Material 3 Expressive), the new mark (already in `LogoMark`, make it the only one). Acceptance: previews; font scale 200 % ok.

**WP-A1 Video screen. PRIORITY 1.** Files: `VideoDetailScreen.kt`, `PlayerComponents.kt`, `FullScreenPlayerActivity`. Same as WP-I1: delete the heading and stacked buttons, icon row, Info sheet, More menu, end card, 3 s control timeout. Optionally migrate to the Media3 `media3-ui-compose-material3` Player with `topControls`/`centerControls`/`bottomControls` slots (documented and available in Media3 1.11; **verify the dependency version before choosing**; staying on `PlayerView` is acceptable for now). Acceptance: static texts <= 6; TalkBack labels; unit + (if the emulator ever works) instrumented tests.

**WP-A2 Create. PRIORITY 1.** Files: `CreateScreen.kt`, `CreateSheets.kt`, `OptionsSheet.kt`, `ComposerBar.kt`, `ComposerViewModel.kt`, `AddPhotosSheet.kt`, `DeckUi.kt`, strings (EN + `values-es`). Same as WP-I2 (pills with dropdown menus, Options sheet, hidden formats).

**WP-A3 Home, first run, Making.** Files: `LibraryScreen.kt`, `Components.kt`, `VideoDetailScreen.kt`. Same as WP-I3.

**WP-A4 Settings, Credits, Feedback, Rating.** Files: `SettingsScreen.kt`, `WalletScreen.kt`, `FeedbackUi.kt`, `RatingUi.kt`.

**WP-A5 Media text diet.** Files: `MediaScreen.kt`, `UploadJourney.kt`, `OrganizeUi.kt`, `MediaComponents.kt`.

**WP-A6 Hardening.** Font scale 200 %, Spanish, TalkBack order, dark, lint clean, string parity EN/ES (`strings_*.xml`), a Robolectric/compose test for the text budget, screenshots (need a working emulator or a device: **blocker for visual verification; until then every Android change is verified by unit tests and code review only**), new bundle number, Play internal testing upload.

### Priorities and sequencing

1. Day 1: WP-I0 + WP-A0 in parallel, then **WP-I1 (video) and WP-I2 (create)** and **WP-A1, WP-A2**.
2. Day 2: WP-I3/A3 (home), WP-I4/A4 (settings and credits).
3. Day 3: WP-I5/A5, WP-I6/A6, TestFlight and Play uploads.
First visible result for the owner: the iOS video screen and Create sheet after about 2 days of iOS work (screenshots per state attached to each package).

## 10. Risks and open decisions

| Risk | Mitigation / decision needed |
|---|---|
| **Icon-only actions are less discoverable** (Share/Save/Edit). | Follow Apple Photos and Files (icons with spoken labels), keep Share filled, tooltips on pointer and long press; run a 5-person hallway test; fallback: show a one-word caption only under the selected action. |
| Hiding platform chips behind a pill could cost discoverability of platform recommendations. | The pill always shows the current platform; Options keeps all six chips; first-run example chips; measure how often "For" is changed (analytics not built: add the two events `create_for_changed`, `create_options_opened` in WP-I2/A2). |
| iOS 26 glass APIs on a deployment target of iOS 17 | `#available` fallbacks, tested on an iOS 18 simulator (installed: iOS 18.2) and iOS 26.5. |
| Removing "Beta/Soon" tiles hides what is coming | Intentional; decide whether any "coming soon" lives in Settings > About. |
| 4K note and credit logic moves into (i) | Keep the price on the Quality row ("4K  2x") and on the button; the (i) is the explanation, not the only place. |
| Backend gaps: scene thumbnails and ETA ranges for Making, a "report this video" path, Live Activity/push | Phase 1 ships without them (stage dots, current ETA). Not required for this redesign. |
| Android cannot be verified visually | Needs a working emulator image or a physical device; until then Android changes carry a "code-verified only" flag in their report. |
| Spanish expansion in the pills (12 characters) | Pill values are single words ("Video", "YouTube", "Corto"); menus show the long name. |
| Stage 2 agents re-adding text | The `TextBudget` test per screen fails the build over budget (section 4 numbers). |
| In-app mark stale on iOS | Fixed in WP-I0 (found in this review: `LibraryView.swift:103`, sign-in screen). |

## 11. What the best apps do (research summary; see section 0 for what was and was not verified)

- **Verified in this session (Apple WWDC25 session pages, Android developer docs):** iOS 26 tab bars float and can minimise on scroll (`tabBarMinimizeBehavior`), partial-height sheets are inset with Liquid Glass backgrounds and can morph out of the button that presents them, "clear" glass is meant for controls over photos and video, reduce-motion affects glass motion so custom elements need fallbacks. Media3 1.11 Compose Material 3 Player has `topControls` / `centerControls` / `bottomControls` / `errorOverlay` slots and a configurable controls timeout; Material guidance: standard sheets for persistent features, modal sheets for menus, full-height modal sheets need a close affordance.
- **Verified in this session (app-design write-ups):** AI video apps that do best make the path from prompt to preview the shortest, show settings after the prompt (invideo AI surfaces voice options only after a prompt), reduce blank-prompt friction ("Surprise me", examples), and show cost and constraints before the tap.
- **General product knowledge, not freshly verified:** Apple Photos and Files use an icon bottom bar (Share, Favourite, Info, Delete) with spoken labels; CapCut and Descript keep the editing surface to a few icons with long press and sheets for the rest; Runway/Luma mobile creation flows are a prompt field plus a settings affordance (model, duration, aspect) in a sheet; Arc, Linear and Airbnb reduce settings to grouped single-line rows with (i) help. These informed the choices but are not cited as evidence.

## 12. Files produced

`docs/UX_2026_REDESIGN.md` (this); `docs/ux_2026/board_light.png`, `board_dark.png` (mockups), `gen.py`, `tokens.css`, `board_*.html`; evidence `ev_a_home_create.png`, `ev_b_create_options_questions.png`, `ev_c_detail_media.png`, `ev_d_settings_wallet_feedback_rating.png`, `ev_e_questions_blocked.png`. Nothing under `mobile/`, `backend/` or `frontend/` was changed.
