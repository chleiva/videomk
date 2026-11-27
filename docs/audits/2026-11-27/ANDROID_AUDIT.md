# VideoMK Android app: design audit, 2026-11-27

Audited build: branch `android-pass2` at `d248a13` (the UI of build 475994 from `da6af96`, plus the R124 fix, which changes no screen), debug build with the fake backend (`files/fake_backend`, `fake_media`, `fake_intake`), emulator `pi35` (Android 15, 1080 x 2400, 420 dpi = 411 dp wide). Judged against `docs/DESIGN_BAR_2026.md`, `docs/design_bar/mockups/phone_1..6`, and the iPhone audit (`IOS_AUDIT.md`) as the checklist, plus the Android points: system back, edge-to-edge and insets, 48 dp targets, TalkBack, font scale 200 %, a 360 dp phone, dark, Spanish.

Evidence: 104 captures in `docs/audits/2026-11-27/android/` (referenced as `android/<file>`): every main screen in light, the key screens again in dark (`_dark`), Spanish (`_es`), 200 % text (`_xl`), Spanish at 200 % (`_es_xl`) and at 360 dp (`_360`), and a read of every file in `mobile/android/app/src/main/kotlin/com/videomk/app/ui/`. Source references are `File.kt:line` under that folder (or `core/`) at `d248a13`. Contrast figures are computed from the token values.

## Verdict

**Overall 3.2 / 5. The bar to ship is 4 or more in every category; no category reaches it.**

The six rebuilt screens (sign-in, Videos, Create, Making, player, Media) are close to their mockups at rest, and they hold at 200 % text and at 360 dp better than the iPhone build did. The app falls short in the same three places as the iPhone app, plus one of its own:

1. **Dead ends and missing exits.** Zero credits leads to a sheet with nothing to do; a video being made cannot be cancelled; a finished video cannot be deleted; a failed video page has no title and no action.
2. **The screens that were only re-tokened are a different app.** Add photos (an explainer before the picker), Options, the question and refusal sheets, the photo viewer, Collections, Settings, Editor, Delete account and Rating draw their own bars, buttons and chip shapes.
3. **Confirm instead of undo.** Sixteen alert dialogs; "Remove" on a failed video has neither.
4. **Android only: the new server rules would break the app.** Any 403 from the API signs the person out, and the plan refusals are 403s. Lengths and 4K the plan forbids are offered. A Free account that cannot create would get a working-looking form that always fails.

## 1. Scorecard

Scale 0 to 5, the categories of section 7 of the design bar.

### By category

| Category | Bar doc "today" | This build | Bar to ship | What holds it back |
|---|---|---|---|---|
| Interaction | 2 | 3.0 | 4 | Credits dead end; photos from Create take 6 taps; no delete, no undo, no cancel; plan refusals sign the person out |
| Delight and fun | 2 | 3.5 | 4 | Capsule, film strip, typed examples work. Sign-in is a still picture of unconfirmed licence; empty Videos is text only |
| Visuals and graphics | 3 | 3.4 | 4.5 | Three chip shapes, two top-bar styles, stock player controls with a gear, weak fade under the tab bar, a clipped day label on every poster |
| Inclusivity | 2 | 3.3 | 4 | Landscape enabled with no layout; "videomk" and "My media / Mi biblioteca" naming; a wrapped selection button and clipped names at 200 %; 40 dp targets |
| Innovation | 3 | 3.5 | 4 | Remix chips and live Making exist; no Look choice although the server offers styles |
| Social impact | 2 | 2.5 | 3 | The Info sheet is raw text with no "made with AI" line; no watermark row |

### By screen

| Screen | Score | State | One line |
|---|---|---|---|
| Sign-in | 3.6 | Rebuilt | Matches the mockup. A still of unconfirmed licence; 20 words against 12 |
| Videos | 3.4 | Rebuilt | Good at rest. Day label clipped, poster reads through the tab bar, Remove has no undo, no delete for a finished video |
| Create (form and capsule) | 3.6 | Rebuilt | The best screen. Opens on "Video · 30 s", never looks disabled, "Add credits" goes nowhere |
| Create sheets (options, questions, summary, refusals) | 2.8 | Re-tokened | Unlabelled format tiles with an orange dot, "Edit request" on a pause, a 470 dp sheet for three chips |
| Add photos sheet | 2.0 | Re-tokened | An explainer with about 45 words between the photo icon and the system picker |
| Making | 3.8 | Rebuilt | Tells the story. No way to cancel |
| Player | 3.2 | Rebuilt | Share is primary. Stock player controls with a settings gear beside our own; no delete; 11 words against 8 |
| Media (grid, select) | 3.4 | Rebuilt | Select to "Make a video · 1" works. Disabled button is see-through; two borders on a selected tile; collections strip before the grid |
| Photo viewer, Collections | 2.6 | Re-tokened | Stock icon buttons, a doubled "Collections" title, an empty collection with no action |
| Settings | 2.7 | Re-tokened | Stock cards; three row styles; sign out and Photos (i) open dialogs |
| Credits (wallet) | 1.8 | Re-tokened | A number, one line and an (i). No plan, nothing to do |
| Editor | 2.4 | Not redesigned | Outlined stock field and buttons; a disabled Publish at 40 % opacity |
| Rating, Feedback | 3.0 | Re-tokened | Work and are calm; outlined secondary button, lower-case brand |
| Delete account | 3.0 | Re-tokened | Thorough and honest; its own field and button shapes, about 90 words |

### Journey checks (rules 4 and 5)

| Journey | Taps | Rule | Result |
|---|---|---|---|
| First video, signed in | New video, type, Create = 3 | 3 | Pass when the server asks no questions |
| First video when the server asks 3 questions | "Skip" in the first question skips all of them: 4 | 3 | Near pass; the label says "Skip", not what it does |
| From Media | Select, photo, Make a video, Create = 4 | 4 | Pass |
| Photos added from Create | Photo icon, Open photo picker, pick, Done (system), Add, Create = 6 | 3 to 4 | Fail |

| Screen | Words on screen | Budget | Result |
|---|---|---|---|
| Create (empty) | 22: "A video about…", three chips (10), three pills (5), Create, "9 credits left" | 14 | Over |
| Player | 11: Share, MAKE ANOTHER, three chips (8) | 8 | Over |
| Videos | 3 plus titles | 6 | Pass |
| Media | 10: Media, Select, Search photos, Add photos, Collections, See all | 8 | Over |
| Settings | About 26 | 30 | Pass |
| Sign-in | 20: sample 4, tagline 6, legal 10 | 12 plus buttons | Over |

The three rulings of the iPhone audit apply unchanged: Create opens on "YouTube · 1 min" and then remembers; "Media" everywhere in English and "Biblioteca" everywhere in Spanish; the remix chips stay and shrink ("As a Short", "In Spanish", "30 seconds", no header).

## 2. Findings

P0 = broken or blocks the job. P1 = clearly below the bar. P2 = polish. The "iOS" column names the matching finding of `IOS_AUDIT.md`.

### P0

| # | Screen | What is wrong (evidence) | Fix | iOS | Source |
|---|---|---|---|---|---|
| P0-1 | Whole app | **A finished video stays "being made" after the phone was locked or the app left (tracker R124).** One failed token refresh cancelled the refresh scope for the rest of the process; polling then ended silently. | Fixed in `d248a13` before this audit (see the pass report). `android/r124_list_after_return.jpg`, `android/r124_making_after_return.jpg` | n/a | `core/Auth.kt:144`, `AppViewModel.kt:199-282` |
| P0-2 | Whole app | **Any HTTP 403 signs the person out.** The plan refusals (`plan_length`, `plan_resolution`, `plan_watermark`, `plan_photos`, `free_not_available`) are 403s: a Free account asking for 1 minute would be thrown to the sign-in screen. 429 `free_budget_spent` shows the wrong text ("daily limit"). | A 403 or 429 with a `code` is a refusal the person reads: the server's message in a sheet on Create, the draft kept. Only a 401 that survives a token refresh ends the session. | n/a | `core/Api.kt:243`, `core/Api.kt:263-271`, `AppViewModel.kt:216` |
| P0-3 | Create, Credits | **"Add credits" leads nowhere.** With 0 credits Create offers "Add credits"; it opens a page with a number, "Next free credits: in 1 hour" and an (i). Nothing can be done there, and the plan is not named. `android/create_nocredits_light.jpg`, `android/wallet_light.jpg` | The chip says "See credits". Credits becomes a sheet that answers: the balance, the plan and its limits, when the next free credit arrives (`next_free_credit_at`), what expires. No buy button until `can_upgrade` is true. | P0-3 | `CreateScreen.kt:161`, `WalletScreen.kt`, `core/Models.kt:142` |
| P0-4 | Create | **The form offers what the plan forbids, and a Free account that cannot create gets a form that always fails.** The length menu lists every length although Free stops at 30 s (the server refuses, it does not shorten); 4K is offered to every plan; `free.available` and `free_creation` are not read. | Lengths over `lengths.plan_max_seconds` and resolutions with `available: false` are shown locked with the plan's name. When the balance is 0 and free creation is not available, Create shows the server's sentence, the plan names and the showcase from `GET /gallery`. | n/a | `CreateScreen.kt:222-226`, `OptionsSheet.kt:86-93`, `core/CreateModels.kt` |

The two iPhone P0s about bars drawn under the tab-bar fade do not reproduce on Android: the fade is drawn only behind the bar (`Root.kt:197`) and the upload pill reserves the bar's height (`LibraryScreen.kt:158`).

### P1

| # | Screen | What is wrong (evidence) | Fix | iOS | Source |
|---|---|---|---|---|---|
| P1-1 | Whole app | Landscape is enabled on phones and no screen is laid out for it (the manifest sets no orientation for `MainActivity`). | Portrait on phones; the full-screen player keeps its own landscape activity. | P1-2 | `AndroidManifest.xml:33-57` |
| P1-2 | Create | The Create button looks fully active with an empty prompt and with no credits; the only signal is a footnote. `android/create_light.jpg`, `android/create_nocredits_light.jpg` | An opaque disabled style when it cannot send (the tap still explains why). For "not affordable" the fix sits on the button row: one tap to the longest length the balance pays for. | P1-3 | `CreateScreen.kt:357-374` |
| P1-3 | Create, Add photos | The photo icon opens a sheet with two tabs, an explainer ("The system photo picker shows your gallery…", about 45 words) and "Open photo picker"; then the system picker, then "Add". Six taps before Create. The tab says "My media". `android/addphotos_light.jpg`, `android/addphotos_es_xl.jpg` | The photo icon becomes a menu: "Photo library" opens the system picker at once, "Media" opens the grid with "Add · N", "Presentation" where the server offers it. The explainer goes (its privacy sentence is in Settings). | P1-5 | `AddPhotosSheet.kt:99-180`, `CreateScreen.kt:198` |
| P1-4 | Create, questions | "Skip" skips every remaining question (good) but says "Skip". The back arrow is a stock icon button. The sheet is at least 470 dp tall whatever it holds. `android/create_questions_light.jpg`, `android/create_summary_light.jpg` | "Skip all". Kit icon button. Content-height sheets. | P1-6, P2-13 | `CreateSheets.kt:37`, `CreateSheets.kt:73-78` |
| P1-5 | Create, refusal sheets | A pause offers "Edit request" as its one primary; editing cannot lift a pause. The message repeats the title ("Creating videos is paused" / "Creating videos is paused for now."), then a third line with the time. `android/create_paused_light.jpg`, `android/create_blocked_light.jpg` | Paused: the time moves into the title ("Paused · try again in about 1 hour"), the primary is "OK". Blocked and unsupported keep "Edit request". A message equal to the title is not drawn. The plan refusals use the same sheet. | P1-7 | `CreateSheets.kt:186-209` |
| P1-6 | Videos, Player, Media, Create, Settings | Rule 8 says undo, not confirm. Sixteen `AlertDialog`s (delete photos, delete photo, delete collection, discard draft, sign out, stop organizing, cancel uploads, replace photos, notices). "Remove" on a failed video deletes at once with no undo. A finished video cannot be deleted anywhere. `android/videos_bottom_light.jpg`, `android/player_more_light.jpg` | One "Deleted · Undo" bar for 6 s; the server call goes out when it expires (or when the app leaves the screen). Used for videos, photos and collections. "Delete" in the player's More menu. Closing Create keeps the draft. Sign out asks nothing. | P1-8 | `LibraryScreen.kt:146-153`, `MediaScreen.kt` (5), `MediaViewer.kt:94`, `CreateScreen.kt:308-320`, `SettingsScreen.kt` (2), `AppViewModel.kt:362` |
| P1-7 | Making | No way to cancel a video while it is being made; the mockup has a More button. `android/making_light.jpg` | A More button with "Cancel video" (`POST …/cancel`); the bar then says "Cancelled · N credits back". | P1-9 | `VideoDetailScreen.kt:103`, `core/Api.kt` |
| P1-8 | Video page, failed | A card with "Didn't finish" and one line: no title, no Try again, no Remove. A cancelled video has no page at all (it is mapped to "failed"). | The title, the same line as the list card, Try again (when the server allows) and Remove. Cancelled is its own state. | P1-10 | `VideoDetailScreen.kt:114-115`, `core/Models.kt:36` |
| P1-9 | Media, whole app | The disabled primary button is the gradient at 40 % opacity: over the photo grid "Choose photos" is see-through. The same on the editor's Publish and the delete-account button. `android/media_select_light.jpg`, `android/editor_light.jpg`, `android/delete_sheet-form_light.jpg` | Disabled = an opaque `surface3` fill with a `textSecondary` label and no glow. | P1-13 | `Theme.kt:186-196` |
| P1-10 | Videos | The day under every poster ("Today", "Earlier") has its top cut off at every text size. `android/videos_light.jpg`, `android/videos_360.jpg` | Give the two text lines their own line heights (no negative spacing, no clip on the text column). | n/a | `LibraryScreen.kt:251-254` |
| P1-11 | Videos, Media | The fade under the floating bar is too weak: the next poster and the photo grid read through the bar. `android/videos_light.jpg`, `android/media_dark.jpg` | Reach the page colour at the top edge of the bar's pill; the list already pads its end by the bar's height. | P1-19 | `Root.kt:197` |
| P1-12 | Player | Two control vocabularies: the stock media controls (rewind 5, forward 15, a settings gear that opens a stock menu) and our own full-screen button. `android/player_light.jpg` | One set: play/pause, the time bar and full screen. No gear, no skip buttons. | P1-1 | `PlayerComponents.kt:86-96` |
| P1-13 | 200 % text, Spanish | (a) "Crear video · 1" wraps onto two lines inside the selection button. (b) Collection names are cut ("May 2…"). (c) "Este teléfono" pushes its icon to the edge. (d) The count beside "Select" wraps under the title. `android/media_selected_es_xl.jpg`, `android/media_es_xl.jpg`, `android/addphotos_es_xl.jpg` | (a) The two icon buttons move above the button at large text. (b) Two lines, then the count. (c) goes with P1-3. (d) The title takes the row; actions drop below it at large text. | P1-14 | `MediaScreen.kt`, `MediaComponents.kt` |
| P1-14 | Whole app | Same thing, same word (rule 13): "Media" on the tab and "My media" in 20 strings; "Mi biblioteca" in Spanish (the ruling is "Biblioteca"); "Video" on the pill and "Just a video" in its menu; "Auto look" and "Estilo automático". The product name is written "videomk" in 25 strings and under the app icon. | "Media" / "Biblioteca" everywhere; the pill and the menu use one word; **VideoMK** wherever a person reads the name, with a source check. | P1-16 | `res/values*/strings*.xml` |
| P1-15 | Options sheet | Four format tiles; the three unselected show only an outline, two of them the same upright rectangle; an unexplained orange dot marks beta. "For" chips carry small square icons; "Done" is a text button; no style choice although the server lists styles; no watermark row. `android/options_light.jpg`, `android/options2_light.jpg` | Every tile shows its ratio and "Beta" in words. One chip shape. A Look row from `capabilities.looks` when the server offers it. A Watermark row per `docs/WATERMARK.md` section 8 (fixed on Free). | P1-17 | `OptionsSheet.kt:68-140` |
| P1-16 | Photo viewer, Collections, Editor, Delete account, Rating, Settings, Wallet | Component drift. Viewer: stock `IconButton`s, a bare text "Collection / Make a video" bar. Collections: the title twice, a stock menu button. Editor: an outlined stock text field, a stock switch, a 40 % Publish. Delete account: a rectangular field and its own red button. Rating: an outlined secondary. Settings: stock cards, three row styles, two dialogs. Wallet: a full page with a top bar for one number. 7 literal `sp` sizes and 17 literal colours outside the kit. `android/viewer_light.jpg`, `android/collections_light.jpg`, `android/editor_light.jpg`, `android/delete_sheet-form_light.jpg`, `android/rating_light.jpg`, `android/settings_light.jpg` | Rebuild on the kit: `VmkTopBar`, `GlassIconButton`, `PrimaryButton`, one tonal button, one row, one switch colour, one field, type roles only. | P1-18 | `MediaViewer.kt:87-94`, `CollectionsScreen.kt`, `EditorScreen.kt`, `DeleteAccountUi.kt`, `RatingUi.kt`, `SettingsScreen.kt`, `WalletScreen.kt` |
| P1-17 | Create | Opens on "Video · 30 s". "Video" on a video app says nothing. | "YouTube · 1 min" on the first run (the longest the plan makes when that is shorter), then the last choice. | Ruling 1 | `core/CreateLogic.kt:119-128` |
| P1-18 | Sign-in | The picture is a stock photograph whose licence is not confirmed; the bar asks for our own footage. | A silent loop cut from our own sample video (`frontend/dist/samples/forest.mp4`); a still from the same video when animations are off. | P2-15 | `SignInScreen.kt:84`, `res/drawable-nodpi/signin_sample.jpg` |
| P1-19 | Player | "MAKE ANOTHER" and three long chips put the page at 11 words against 8. | No header; "As a Short", "In Spanish" / "In English", "30 seconds". | Ruling 3 | `VideoDetailScreen.kt:222-229` |

### P2

| # | Screen | What is wrong (evidence) | Fix | iOS | Source |
|---|---|---|---|---|---|
| P2-1 | Player | The Info sheet is a raw text dump with no "made with AI" line. `android/player_info_light.jpg` | Three short groups: About (made with AI, captions burned in), Sources and credits, one Copy button. | P2-6 | `VideoDetailScreen.kt:236-258` |
| P2-2 | Player | A playback error is a sentence and a bare text button; an expired session offers "Try again", which cannot help. | Icon, one line, a tonal button. | P2-7 | `VideoDetailScreen.kt:140-146` |
| P2-3 | Making, Videos | The fallback live lines end with a full stop ("Getting started.") while the server's do not. | No full stops. | P2-9 | `strings_library.xml:52-55`, `strings_deck.xml:32-33` |
| P2-4 | Media | A selected tile has two borders (a square stroke and the shrunken rounded picture). `android/media_selected_light.jpg` | One border on the shrunken tile, and the tick. | P2-2 | `MediaComponents.kt` |
| P2-5 | Media | The collections strip sits between "Add photos" and the grid and costs about 190 dp before the first photo. `android/media_light.jpg` | One "Collections" row that opens the list. | P2-4 | `MediaScreen.kt` |
| P2-6 | Collection page | "No photos here yet. Add photos in the Media tab." and no button. `android/collection_light.jpg` | One tonal button, "Add photos". | P2-5 | `MediaScreen.kt` (CollectionScreen) |
| P2-7 | Media, storage | The storage sheet is about 70 words; the plan row says "Free" with no limits. `android/storage_light.jpg` | The meter, three rows, one sentence. | n/a | `MediaScreen.kt` (storageSheet) |
| P2-8 | Settings | Feedback has an icon and a chevron; Support, Privacy and Terms are bare; About is a label. Switches are lavender with a dark knob in dark mode here and green on Making. `android/settings_light.jpg`, `android/settings_dark.jpg` | One row style with a trailing glyph for links; one switch colour. | P2-17 | `SettingsScreen.kt` |
| P2-9 | Create | Attached-photo remove buttons are 40 dp targets with a 22 dp glyph; the status-line close is 44 dp. | 48 dp targets. | P2-20 | `CreateScreen.kt:485`, `ComposerBar.kt:203` |
| P2-10 | Player | The More menu repeats "New video" (already on the end card) and has no Delete. `android/player_more_light.jpg` | More = Delete, Send feedback. | P1-8 | `VideoDetailScreen.kt:208-212` |
| P2-11 | Videos | The empty state is text only. | A slow scene from our own footage and one line. Not built in this pass (needs the illustration set). | P2-21 | `LibraryScreen.kt:316-345` |
| P2-12 | Rating | The secondary is an outlined button; the sheet title uses the lower-case name. `android/rating_light.jpg` | A tonal secondary; the brand spelled right. | P2-18 | `RatingUi.kt` |
| P2-13 | Create | The summary's close icon means "edit the request"; the question dots have no spoken label. | Label the icon; give the dots "Question 1 of 3". | P2-13, VoiceOver | `CreateSheets.kt:76`, `CreateSheets.kt:156` |

### TalkBack (from the code and the semantics tree; not run with TalkBack speaking)

The rebuilt screens are labelled with care: `GlassIconButton` requires a label, pills speak "Length: 30 s", the capsule and the live line are polite live regions, posters merge into one sentence. Gaps:

| Where | Gap | Fix | Source |
|---|---|---|---|
| Question sheet | The progress dots have no label. | One merged description, "Question 1 of 3". | `CreateSheets.kt:75-77` |
| Photo viewer | "1 of 60" is plain text; paging announces nothing. | A polite live region on the counter. | `MediaViewer.kt:88` |
| Floating bar | Two tabs with the selected state but no "tab list" grouping beyond traversal. | `selectableGroup()` on the pill. | `Root.kt:201-207` |
| Storage meter | Checked again: the row already speaks its text ("Storage: 1.8 GB of 2 GB, almost full") as one element. | None needed. | `MediaComponents.kt:277-285` |
| Undo | No undo exists, so nothing is announced after a removal. | The undo bar is an assertive live region with "Undo" as its action. | new |

### Android points

| Point | Result |
|---|---|
| System back | Works on every screen and sheet seen: sheets close first, Create asks before discarding typed text (to be replaced by keeping the draft), selection mode ends before the tab is left. |
| Edge to edge and insets | `enableEdgeToEdge()`; status and navigation insets are respected on every captured screen; the keyboard lifts Create's controls and the Create button above it (seen during the sweep; no capture kept). |
| 48 dp targets | Kit controls are 48 dp. Exceptions: P2-9 and the Photos (i) in Settings (44 dp). |
| 200 % text | Holds on sign-in, Videos, Create, Making, player, Credits, Settings. Breaks: P1-13. |
| 360 dp | Holds on every key screen (`android/*_360.jpg`); the Making title wraps to two lines, which is fine. |
| Dark | Holds; the fade under the bar is the weakest point (P1-11). |
| Spanish | Complete; "Mi biblioteca" must become "Biblioteca" (P1-14). |

## 3. What was not reached or verified

- **The real backend.** Everything ran on the fake: no real request check, upload, retry, cancel, delete or plan refusal was seen.
- **The reveal** (Making card to poster) was seen only as the list refreshing after `fake_finish`; motion was not judged.
- **Sign-in beyond the first screen**: the hosted pages were not opened.
- **System pickers and permissions**: the photo picker, the document picker, dictation, save to gallery and the notification prompt were not opened.
- **Uploads and organize states on Media, deck states, the editor beyond its first screen, media search results, an empty library.**
- **TalkBack, reduced motion and haptics** were read in code, not run.
- **Landscape and tablets** were not captured.

## Method

One emulator, one job at a time. States were reached with the debug file flags and `adb shell input`; node positions came from `uiautomator dump` by test tag. Captures are JPEG at 540 x 1200.

## 4. After the fixes (same day, branch `android-pass2`)

Captures after the fixes: `docs/audits/2026-11-27/android_after/` (136 files: the full light set, and the key screens in dark, Spanish, 200 % text, Spanish at 200 % and 360 dp; file names match the "before" set where the screen still exists). Looked at against the before set and the mockups, screen by screen.

Commits: `d248a13` (R124), `3f25b1b` (plans, looks, watermark, cancel, gallery, refusal sheets, kit), `33cf34f` (fixes part 1), `9ef4d63` (fixes part 2), and the closing commit of this pass (player button, viewer at large text, captures, this section).

| # | Status | What was done | Evidence |
|---|---|---|---|
| P0-1 | Fixed | See the pass report: refresh scope, forced refresh on 401, read on return, poll loop. Verified again on the final build with `deviceidle force-idle`. | `android_after/r124_back_from_idle_light.jpg` |
| P0-2 | Fixed | A 403 or 429 with a `code` is `ApiError.Plan`: the server's sentence in the refusal sheet, draft kept, "Use 30 s" when the length is the problem. Unit tests for every code. | `PlansTest`, `AppViewModelTest` |
| P0-3 | Fixed | "See credits"; Credits is a sheet with the balance, the next free credit, the plan and its limits, what expires. No buy button. | `android_after/credits_light.jpg`, `plan_free_credits_light.jpg` |
| P0-4 | Fixed | Lengths over the plan's longest and qualities the plan lacks are locked with the plan's name; Create never starts on one; with nothing to spend and no free video the screen shows the server's sentence, the plans and the showcase. | `plan_free_lengths_light.jpg`, `plan_free_create_light.jpg`, `plan_locked_create_light.jpg` |
| P1-1 | Fixed | `MainActivity` is portrait; the full-screen player keeps its own orientation. | manifest |
| P1-2 | Fixed | Opaque disabled Create; "Create · 1 min" when the balance pays for a shorter video. | `create_light.jpg`, `create_nocredits_light.jpg`, `create_notaffordable_light.jpg` |
| P1-3 | Fixed | The photo icon is a menu: Photo library (system picker at once), Media ("Add · N"), Presentation where offered. Explainer removed. | `create_photo_menu_light.jpg` |
| P1-4 | Fixed | "Skip all", kit back button, content-height sheets, spoken position. | `create_questions_light.jpg`, `create_summary_light.jpg` |
| P1-5 | Fixed | "Paused · try again in about 1 hour" with OK; a message that repeats the title is not drawn; plan refusals share the sheet. | `create_paused_light.jpg`, `create_blocked_light.jpg` |
| P1-6 | Fixed, one exception | One "Deleted · Undo" bar for videos, photos, collections and failed requests; nine confirm dialogs removed. Kept on purpose: the editor's "discard changes?" (unsaved edits cannot be restored by an undo) and the name sheets (forms, not confirmations). | `videos_deleted_undo_light.jpg`, `media_deleted_undo_light.jpg` |
| P1-7 | Fixed | More > Cancel video; "Cancelled · 2 credits back"; a cancelled card with Try again and Remove. | `making_more_light.jpg`, `videos_cancelled_light.jpg` |
| P1-8 | Fixed | The failed, refused and cancelled page shows the list's card: title, line, Try again, Remove. | code; the card is the one in `videos_bottom_light.jpg` |
| P1-9 | Fixed | Opaque disabled primary everywhere. | `delete_sheet-form_light.jpg`, `editor_light.jpg` |
| P1-10 | Fixed | The picture alone is clipped; the day is whole. | `videos_light.jpg` |
| P1-11 | Fixed | The fade reaches the page colour behind the bar's pill. | `videos_light.jpg`, `media_dark.jpg` |
| P1-12 | Fixed | One set of controls drawn by the app, inline and full screen: play or pause, time, a bar, full screen. | `player_light.jpg`, `player_playing_light.jpg` |
| P1-13 | Fixed | The selection button keeps one line (icons above it at large text), the collections strip is one row, rows put their value under the title at large text, the viewer's button keeps one line. | `media_selected_es_xl.jpg`, `media_es_xl.jpg`, `viewer_es_xl.jpg`, `settings_es_xl.jpg` |
| P1-14 | Fixed | Media / Biblioteca in every string; "Video" on the pill and in its menu; VideoMK in every string, the app label and code literals, held by `BrandTest`. | `media_es.jpg`, `rating_light.jpg` |
| P1-15 | Fixed | Options on the kit: one chip, Scenes and Background from `looks`, the Watermark row (fixed on Free; mode and presence otherwise), ratio and "Beta" on the tiles. The person's own logo is not set up from the phone (web only for now). | `options_light.jpg`, `options2_light.jpg`, `plan_free_options_light.jpg`, `plan_pro_options_light.jpg` |
| P1-16 | Mostly fixed | Viewer, Collections, Editor, Delete account, Rating, Feedback, Settings, Credits and Storage use the kit (top bar, icon button, primary, tonal, row, switch, field, menu). Left: about 20 literal colours outside the theme (upload tile states drawn over photographs, the look swatches, the official Google and Apple button colours, the white end-card pill) and 7 literal text sizes; the upload bar and the deck card were not rebuilt. | `viewer_light.jpg`, `collections_light.jpg`, `editor_light.jpg`, `settings_light.jpg`, `feedback_light.jpg` |
| P1-17 | Fixed | YouTube · 1 min on the first run (30 s where the plan stops there), then the last choice. | `create_light.jpg`, `plan_free_create_light.jpg` |
| P1-18 | Fixed | Six silent seconds of our own forest sample, cut above its captions, over a still from the same video; the still alone when animations are off. | `signin_light.jpg` |
| P1-19 | Fixed | No header; "As a Short", "In Spanish", "30 seconds". | `player_light.jpg` |
| P2-1 | Fixed | About (made with AI, captions), the description, Sources and credits, one Copy. | `player_info_light.jpg` |
| P2-2 | Fixed | Icon, one line, a tonal Try again; a player error first fetches a fresh link by itself. | code |
| P2-3 | Fixed | No full stops; "Finding the story". | strings |
| P2-4 | Fixed | One border on the shrunken tile. | `media_selected_light.jpg` |
| P2-5 | Fixed | One "Collections" row. | `media_light.jpg` |
| P2-6 | Fixed | "No photos here yet" and "Add photos" (Media opens ready to select). | `collection_light.jpg` |
| P2-7 | Fixed | The meter, three rows, one sentence. | `storage_light.jpg` |
| P2-8 | Fixed | One row style with icons and trailing glyphs; one switch colour (green) in Settings, Options, Editor, Organize. | `settings_light.jpg`, `settings_dark.jpg` |
| P2-9 | Partly | Attached-photo remove is a 48 dp target. The old composer strip's 44 dp close (not on any current screen) was left. | code |
| P2-10 | Fixed | More = Send feedback, Delete. | `player_more_light.jpg` |
| P2-11 | Not done | The empty Videos screen is still text and chips: it needs the illustration set, which this pass did not have. | n/a |
| P2-12 | Fixed | Tonal secondary; "Enjoying VideoMK?". | `rating_light.jpg` |
| P2-13 | Fixed | The summary's close says "Edit request"; the dots speak "Question 1 of 3". | code |
| TalkBack | Fixed where listed | Question position, viewer position (polite live region), the tab pill as a selectable group, the undo bar (assertive, with Undo). Not run with TalkBack speaking. | code |

Word counts after: Create 12 on its surface (hint 3, "YouTube", "1 min", "Auto look", "Create", "9 credits left"; the three example chips are suggestions and are counted apart, 10 words, as on the iPhone); player 7 (Share, three chips); sign-in 10 plus the button; Media 7; Videos 3 plus titles.

Score after, judged from the after captures: **Interaction 4.2, Delight 3.8, Visuals 4.1, Inclusivity 4.0, Innovation 4.0, Social impact 3.2; overall about 3.9.** Below the bar of 4 in Delight (no empty-state art, the reveal is a cross-fade, not a shared element) and under 4.5 in Visuals (the upload bar and the deck card were not rebuilt).

Not verified after the fixes: anything against the real backend (cancel, delete, plan refusals, the gallery, looks and the watermark row were exercised only with the debug fakes and unit tests), the system photo picker opening from the new menu, the sign-in loop on a real phone, TalkBack speaking, the instrumented tests (they compile; they were not run).
