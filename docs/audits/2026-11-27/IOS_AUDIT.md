# videomk iPhone app: design audit, 2026-11-27

Audited build: branch `ccr-3c41ecff-680028` at `cf51759` (the build on TestFlight today), Debug configuration with the fake backend (`VMK_DEBUG_FAKE_LIBRARY=1`), iPhone 17 Pro simulator, iOS 26.5. Judged against `docs/DESIGN_BAR_2026.md` and `docs/design_bar/mockups/phone_1..6`.

Evidence: the 56 captures in `docs/design_bar/ios/` (referenced as `design_bar/ios/<file>`), 146 new captures in `docs/audits/2026-11-27/ios/` (referenced as `ios/<file>`), and a read of every view file in `mobile/ios/VideoMK/`. Source references are `File.swift:line` under `mobile/ios/VideoMK/` unless a longer path is given. Contrast figures marked "measured" were sampled from the screenshot pixels; "computed" figures come from the token values.

Two of the implementer's captures are not what their names say: `design_bar/ios/videos_light.jpg` is a blank dark screen and `design_bar/ios/create_checking_light.jpg` is the simulator home screen. Correct versions: `ios/videos_light.jpg`, `ios/create_checking_light.jpg`.

## Verdict

**Overall 3.1 / 5. The bar to ship is 4 or more in every category; no category reaches it.**

The six rebuilt screens are close to their mockups when nothing unusual is happening. The app falls short in three places:

1. **States around the happy path are broken or dead ends.** Everything that floats above the tab bar on Media is washed out by the tab-bar fade, the upload pill on Videos is hidden behind the tab bar, and "Add credits" leads to a sheet with nothing to do.
2. **The screens that were only re-tokened are a different app.** Add photos, Options, the question sheets, the photo viewer, Collections, Editor, Delete account and Rating use other button shapes, other navigation bars, fixed font sizes and many more words.
3. **The largest text size, Spanish and landscape were captured but not fixed.** Labels overflow, names hyphenate, the narration line hides under a card, and iPhone landscape is enabled with no layout for it.

## 1. Scorecard

Scale 0 to 5, same categories as section 7 of the design bar.

### By category

| Category | Bar doc "today" | This build | Bar to ship | What holds it back |
|---|---|---|---|---|
| Interaction | 2 | 3.0 | 4 | Credits dead end; photos from Create take 6 taps; questions cannot be skipped in one tap; no delete or undo; no cancel while making |
| Delight and fun | 2 | 3.5 | 4 | Capsule, film strip and typed examples work. No footage on sign-in, no empty-state art, no drawn pull-to-refresh; the reveal could not be verified |
| Visuals and graphics | 3 | 3.4 | 4.5 | Fade washes out bars; two chip shapes; two navigation-bar styles; translucent sheets over the photo grid; duplicated player controls |
| Inclusivity | 2 | 3.0 | 4 | Six measured contrast failures; seven layout breaks at the largest text size; Spanish naming split; landscape undesigned |
| Innovation | 3 | 3.5 | 4 | Remix chips and live Making exist; the chips push the player over its word budget |
| Social impact | 2 | 2.5 | 3 | The Info sheet is raw text with no AI disclosure and no structured sources |

### By screen

| Screen | Score | State | One line |
|---|---|---|---|
| Sign-in | 3.6 | Rebuilt | Matches the mockup. Still picture, not footage; the Apple label does not scale with text size |
| Videos | 3.3 | Rebuilt | Good at rest. Upload pill hidden, failed card reads through the tab bar, Remove has no undo, no delete for finished videos |
| Create (form and capsule) | 3.6 | Rebuilt | The best screen. Create never looks disabled, text scrolls under the top bar, Cancel fails contrast |
| Create sheets (options, questions, summary, refusals) | 2.7 | Re-tokened | Rounded-rectangle chips, unlabelled format tiles, wrong primary on "paused", up to 5 extra taps |
| Add photos sheet | 2.0 | Re-tokened | An explainer with about 60 words between the photo icon and the system picker |
| Making | 3.8 | Rebuilt | Tells the story. No way to cancel; narration hides under the notify card at large text |
| Player | 3.3 | Rebuilt | Share is primary. Two full-screen buttons, no delete, 11 words against a budget of 8 |
| Media (grid, select) | 3.3 | Rebuilt | Selecting to "Make a video · 3" works and Back keeps the selection. Tab bar rides above the keyboard; 17 words against a budget of 8 |
| Media bars (upload, added, storage full, toasts) | 1.5 | Re-tokened | Illegible: drawn under the tab-bar fade |
| Photo viewer, Collections, Organize | 2.5 | Re-tokened | System navigation bar, different icons, translucent sheets, truncation in Spanish |
| Settings | 2.6 | Re-tokened | A stock grouped list; the Photos (i) popover is clipped |
| Credits (wallet) | 1.5 | Re-tokened | Shows a number and nothing to do; contradicts itself when the breakdown is empty |
| Deck (presentation) flow | 3.0 | Re-tokened | Clear states and actions; placeholder truncated; Create looks active while uploading |
| Editor | 2.0 | Not redesigned | Stock list and stock buttons. Only its error state could be reached; the rest is from code |
| Feedback | 3.0 | Re-tokened | Works and is calm; system-bar look, fixed font sizes |
| Rating prompt | 2.8 | Re-tokened | Two rounded-rectangle buttons in a half-empty sheet |
| Delete account | 3.0 | Re-tokened | Thorough and honest; stock list with its own button shapes |

### Journey checks (rule 5 and rule 4)

| Journey | Taps | Rule | Result |
|---|---|---|---|
| First video, signed in | New video, type, Create = 3 | 3 | Pass, only when the server asks no questions |
| First video when the server asks 3 questions | 3 + up to 3 answers or skips + Create on the summary = up to 7 | 3 | Fail |
| From Media | Select, photo, Make a video, Create = 4 (plus typing) | 4 | Pass |
| Photos added from Create | Photo icon, Choose photos, pick, Add (system), Add N, Create = 6 | 3 to 4 | Fail |

| Screen | Words on screen | Budget | Result |
|---|---|---|---|
| Create (empty) | 22: "A video about…", three chips (10), three pills (5), Create, "9 credits left" | 14 | Over. The mockup has the same 22 |
| Player | 11: Share, MAKE ANOTHER, three chips (8) | 8 | Over (see ruling 3) |
| Videos | 3 plus titles | 6 | Pass |
| Media | 9, and 17 with the coach line | 8 | Over |
| Settings | About 27 | 30 | Pass |
| Sign-in | 20: tagline 6, sample 4, legal 10 | 12 plus buttons | Over. The mockup has the same 20 |

### Rulings on the three open points

1. **Create defaults: ship "YouTube · 1 min" on the first run, then remember the person's last choice.** One minute costs 1 credit instead of 3, so 12 free credits make twelve videos, not four, and the reveal arrives sooner. A pill that says "Video" on a video app carries no information; "YouTube" says 16:9 and matches rule 6. Change `defaultMinutes` (`Packages/VideoMKCore/Sources/VideoMKCore/Models.swift:140`) to 1 and the default platform (`Models.swift:153`, `CreateModels.swift:284`) to the YouTube chip. `CreateDefaults` already restores the last choice.
2. **Spanish: "Biblioteca" everywhere.** One word for the tab, the title and every sheet (rule 13). English has the same split ("Media" on the tab, "My media" in sheets): use "Media" everywhere. Keys in `Localizable.xcstrings`: `media.media`, `add.my_media`, `add.open_my_media`, `add.add_photos_to_my_media`, `collections.photos_stay_in_my_media`, `delete.item.media`, `create.use_library`.
3. **Player budget: the chips stay and the words shrink.** Remove the "MAKE ANOTHER" header (the sparkle already marks a suggestion) and shorten the chips to "As a Short", "In Spanish", "30 seconds". With Share that is 8 words. `VideoDetailView.swift:199`; keys `detail.remix_short`, `detail.remix_spanish`, `detail.remix_english`, `detail.remix_30s`.

## 2. Findings

P0 = broken or blocks the job. P1 = clearly below the bar. P2 = polish.

### P0

| # | Screen | Element | What is wrong (evidence) | Exact fix | Source |
|---|---|---|---|---|---|
| P0-1 | Media | Everything that floats above the tab bar: upload bar, "6 photos added / Make a video · 6", storage-full card, toasts | The tab-bar fade is drawn over the whole screen, so these bars sit under it. Measured: upload title 2.6:1, subtitle 1.3:1, the white label on "Make a video · 6" 2.3:1, dark toast text 2.3:1 and its "View" action 1.7:1. "Manage storage" and "Not now" look disabled. `ios/media_uploading_light.jpg`, `ios/media_upload_added_light.jpg`, `ios/media_upload_error_light.jpg`, `ios/organize_progress_light.jpg`, `ios/organize_done_dark.jpg`, `ios/media_upload_done_dark.jpg` | Draw the fade inside each tab's scroll view, beneath the bottom inset, not as an overlay on `MainTabs`. Limit its height to the tab bar (84 pt). Give the bars an opaque surface. | `VideoMKApp.swift:62`, `DesignKit.swift:369-373`, `MediaView.swift:55-63` |
| P0-2 | Videos | Upload progress pill | The pill is laid out at the same height as the tab bar and sits behind it and the New video button. Only "…ding 38 of" shows. `ios/videos_while_uploading_light.jpg` | Reserve the tab bar's height under the pill, as Media does at `MediaView.swift:62`. Better: show uploads as a card at the top of the list, where the Making card lives. | `LibraryView.swift:38`, `LibraryView.swift:86-90` |
| P0-3 | Create, Credits | "Add credits" and the Credits sheet | With 0 credits Create offers "Add credits". It opens a sheet with a number, one line and an (i): no way to get credits and no date for the next free ones. With an empty breakdown the sheet says "No credits right now." under a hero that says "12 credits". `ios/create_nocredits_dark.jpg`, `ios/wallet_es_dark.jpg`, `ios/wallet_light.jpg` | Until purchases exist: rename the chip "See credits", and make the sheet answer the question with one line, "Next free credits: tomorrow". Never show `wallet.none` when the balance is above 0. When purchases exist, the sheet gets one primary, "Get credits". | `CreateView.swift:456`, `CreateView.swift:472`, `WalletView.swift:13-19`, `LibraryView.swift:64` |

### P1

| # | Screen | Element | What is wrong (evidence) | Exact fix | Source |
|---|---|---|---|---|---|
| P1-1 | Player | Full-screen controls | Two full-screen buttons: the system's (top left, shown on tap) and ours (top right, always). Ours turns muddy over bright video. In full screen our X sits on the system's top-left controls. `ios/player_controls_light.jpg`, `ios/player_playing_controls_light.jpg`, `ios/player_fullscreen.jpg` | Keep one. Remove the custom button and close button; route the system full-screen button to the landscape presentation through the `AVPlayerViewController` delegate. | `PlayerView.swift:113-123`, `PlayerView.swift:43-58` |
| P1-2 | Whole app | iPhone landscape | Landscape is enabled on iPhone and no screen is laid out for it: the tab bar covers the first poster, Create's examples are cut in half, and the video page stayed sideways after leaving full screen in the simulator. `ios/landscape_videos.jpg`, `ios/landscape_create.jpg`, `ios/landscape_media.jpg`, `ios/landscape_detail_after_fullscreen.jpg` | iPhone: portrait only in `project.yml`. The full-screen player keeps its own landscape through `application(_:supportedInterfaceOrientationsFor:)`. | `mobile/ios/project.yml:37`, `PlayerView.swift:33-37` |
| P1-3 | Create | The Create button when it cannot send | It looks fully active when the person cannot afford the video, while a presentation uploads, and when a presentation failed. The only signal is a footnote. `ios/create_notaffordable_light.jpg`, `ios/deck_uploading_light.jpg`, `ios/deck_fail_light.jpg` | When `canSend` is false, draw the opaque disabled style (see P1-13) and keep the tap so the caption still shakes. For "not affordable", put the fix on the button: "Create · 1 min · 1". | `CreateView.swift:394-409` |
| P1-4 | Create | Top bar | The top bar has no background, so the prompt and deck text scroll under the X and the status bar. `ios/deck_toolarge_xl.jpg`, `ios/create_typed_keyboard_xl.jpg` | Give the top inset the page background with a 16 pt fade below it. | `CreateView.swift:64-66` |
| P1-5 | Create, Add photos sheet | The whole sheet | The photo icon opens an explainer ("Pick from this phone", three paragraphs, about 60 words), then "Choose photos", then the system picker, then "Add N". Six taps before Create. The button is the stock prominent style, not ours; in dark it is white on `#AAA8FF` (2.15:1 computed). "Select all (up to 100)" wraps onto three lines. The title says "Photos" and the icon says "Add photos". `ios/addphotos_phone_light.jpg`, `ios/addphotos_phone_dark.jpg`, `ios/addphotos_library_selected.jpg`, `ios/addphotos_library_dark.jpg` | The photo icon becomes a two-item menu. "Photo library" opens the system picker directly. "Media" opens the grid with the same selection bar as the Media tab ("Add · 3"). Delete the explainer; its privacy sentence already lives in Settings. | `AddPhotosSheet.swift:99-140`, `AddPhotosSheet.swift:156-180`, `CreateView.swift:195-207`, `CreateView.swift:261` |
| P1-6 | Create, questions | Skip | "Skip" skips one question. Three questions and the summary add up to four taps after Create, against the 3-tap rule. `ios/create_q1_light.jpg`, `ios/create_q2_dark.jpg`, `ios/create_summary_light.jpg` | "Skip" becomes "Skip all" and starts the video at once. Show the summary only when at least one answer was given. | `CreateSheets.swift:82`, `CreateSheets.swift:137-144`, `CreateModel.swift` (`answer`) |
| P1-7 | Create, refusal sheets | Primary action when creating is paused | The one primary is "Edit request". Editing cannot lift a pause. In the fixtures the message repeats the title; real server copy was not seen. `ios/create_paused_light.jpg`, `ios/create_blocked_dark.jpg` | Paused: primary "OK" closes the sheet, and the retry time moves into the title ("Paused · try again in about 1 hour"). Blocked and unsupported keep "Edit request". Do not render a message that equals the title. | `CreateSheets.swift:22`, `CreateSheets.swift:207-222`, `LibraryView.swift:376-381` |
| P1-8 | Videos, Player, Media, Create, Settings | Delete, remove, discard | Rule 8 says undo, not confirm. The app has five confirm dialogs (delete photos, delete photo, delete collection, discard, sign out) and one removal with neither confirm nor undo ("Remove" on a failed video). A finished video cannot be deleted anywhere. `ios/media_delete_dialog.jpg`, `ios/create_discard_dialog.jpg`, `ios/settings_signout_dialog.jpg`, `ios/videos_failed_menu.jpg`, `ios/videos_failed_removed.jpg`, `ios/player_more_menu.jpg` | One toast component, "Deleted · Undo", for 6 s, with the server call sent when it expires. Use it for photos, collections, failed videos and finished videos. Add "Delete" to the player's More menu. Closing Create keeps the draft instead of asking. Sign out needs no question. | `MediaView.swift:94-99`, `PhotoViewer.swift:72-74`, `CollectionViews.swift:44`, `CollectionViews.swift:147`, `CollectionViews.swift:217`, `CreateView.swift:71-74`, `SettingsView.swift:77-79`, `AppModel.swift:412-420`, `VideoDetailView.swift:184-187` |
| P1-9 | Making | Top bar | No way to cancel or remove a video while it is being made. The mockup has a More button. `design_bar/ios/making_light.jpg` against `mockups/phone_4_making.jpg` | Add a trailing More button with "Cancel video". Needs a cancel endpoint; `backend/lambdas/generate_video/handlers/mark_cancelled_handler.py` exists untracked on this branch. `MakingCard` already takes `onRemove` and nobody passes it. | `VideoDetailView.swift:36`, `MakingCard.swift:33`, `VideoCards.swift:152` |
| P1-10 | Video page, failed | Whole state | No title, so the person cannot tell which video failed. Only "Try again"; Remove exists on the list card but not here. Spanish says "No se completó" here and "No terminó" on the list; English says "No credits used." here and "No credits were used." on the list. `ios/detail_failed_light.jpg`, `ios/detail_failed_es_dark.jpg` | Show the title and reuse the list's `FailedRow` content, with Try again and Remove. One string for each idea. | `VideoDetailView.swift:43`, `VideoDetailView.swift:212-220`; keys `detail.failed_title`, `detail.failed_body` |
| P1-11 | Settings | Photos (i) popover | The popover is clipped: its first lines are cut off and it covers the Language row. `ios/settings_photos_info.jpg` | Replace the popover with a section footer of one sentence, or a small sheet. A popover anchored in a list header does not lay out on iOS 26. | `SettingsView.swift:43`, `DesignKit.swift:377-391` |
| P1-12 | Media | Tab bar and selection bar with the keyboard up | The floating tab bar and New video button ride above the keyboard and cover the grid. Tapping Select keeps the keyboard up, so the selection bar floats mid-screen. There is no Cancel for search. `ios/media_select_keyboard_up.jpg`, `ios/media_select_empty_light.jpg` | Make the tab-bar inset ignore the keyboard safe area. Clear the search focus when Select is tapped. Add a Cancel text button beside the field while it has focus. | `VideoMKApp.swift:63-65`, `MediaView.swift:156`, `MediaView.swift:263-279` |
| P1-13 | Media, whole app | Disabled primary button | Disabled is the same gradient at 45% opacity. Over the grid it is see-through: "Make a video" and the month header print on top of each other. `ios/media_select_empty_light.jpg`, `design_bar/ios/media_select-mode-empty.jpg` | Disabled = an opaque `surface3` fill with `text2` label and no shadow. Apply it to the placeholder Share button too. | `DesignKit.swift:57-59`, `VideoDetailView.swift:329-335` |
| P1-14 | Largest text size (AX) | Seven breaks | (a) The tab label "Biblioteca" overflows its capsule: `ios/videos_scrolled_es_dark_xl.jpg`. (b) Collection names hyphenate ("Lon-don ·…"): `design_bar/ios/media_xl.jpg`. (c) The account email is cut in the middle: `design_bar/ios/settings_xl.jpg`. (d) "Continue with Apple" stays small beside a large "Continuar con Google": `design_bar/ios/signin_both_xl.jpg`. (e) The narration line hides under the notify card: `design_bar/ios/making_xl.jpg`, `ios/making_es_xl.jpg`. (f) With the keyboard up Create shows two and a half lines of the prompt: `ios/create_typed_keyboard_xl.jpg`. (g) The deck placeholder is truncated even at the default size: `ios/deck_ready_light.jpg` | (a) Remove `maxWidth: 230`, or show icons only at AX sizes. (b) Stack name and count beside a smaller cover at AX; no hyphenation. (c) Let the email wrap to two lines. (d) Draw our own Apple button (logo plus scaled text, as for Google). (e) Put the notify card inside the scroll content at AX. (f) Hide the pills row while the keyboard is up at AX. (g) Shorten to "Who is it for?" | `DesignKit.swift:331-332`, `DesignKit.swift:356`, `CollectionViews.swift:56-63`, `SettingsView.swift:20`, `SignInView.swift:78-94`, `VideoDetailView.swift:55`, `CreateView.swift:373-389`, `CreateView.swift:122` |
| P1-15 | Several | Contrast | Cancel under the capsule is 2.3:1 measured on the aura (`ios/create_checking_light.jpg`). Section headers in the Options and Credits sheets use `text3` at 12 pt: 2.97:1 computed on the light page. Deck and Add-photos hints use `text3` at 13 pt. Stock prominent buttons in dark are white on `#AAA8FF`, 2.15:1. Dark-mode switches have a white knob on the same lavender. | Cancel uses `text` on a `surface` capsule. Essential text never uses `text3`: switch those to `text2` (5.7:1). Replace the stock buttons with `PrimaryButtonStyle`. Tint every switch with `success`, as on Making. | `CreateView.swift:430-431`, `CreateOptionsSheet.swift:42`, `WalletView.swift:43`, `DeckViews.swift:94`, `AddPhotosSheet.swift:169`, `AddPhotosSheet.swift:172`, `AddPhotosSheet.swift:283`, `CreateOptionsSheet.swift:22`, `SettingsView.swift:66` |
| P1-16 | Whole app | Same thing, same word (rule 13) | "Media" and "My media"; "Biblioteca" and "Mi biblioteca"; "All" where the mockup says "Select all"; "Photos" as the title of the sheet the "Add photos" icon opens; "Video" on the pill and "Just a video" in its menu; "Auto" and "automático" (lower case) in the same Spanish sheet. | Rulings 2 and 3. Also `media.all_short` becomes "Select all", `create.add_photos` becomes "Add photos", the pill and the menu use the same word, and `look.auto` in Spanish gets a capital. | `Localizable.xcstrings`; `MediaView.swift:143`, `AddPhotosSheet.swift:101`, `CreateView.swift:293-298`, `CreateOptionsSheet.swift:130` |
| P1-17 | Options sheet | Format tiles | Four tiles; the three unselected ones show only an outline, and two of those are near-identical upright rectangles. An unexplained orange dot marks beta. Only the selected tile shows its ratio. `ios/options_expanded_light.jpg`, `ios/options_vertical_light.jpg`, `ios/create_options_xl3.jpg` | Every tile always shows its ratio ("16:9", "9:16", "1:1", "4:5"). Replace the dot with the word "Beta" under the ratio. | `CreateOptionsSheet.swift:144-163` |
| P1-18 | Photo viewer, Collections, Editor, Organize, Delete account, Rating | Component drift | These screens draw their own controls. Viewer: a stock close glyph with a target of about 30 pt, a "sparkles" glyph on "Make a video" where the rule says play-sparkle, its own material bar (`ios/viewer_light.jpg`). Collections: the system navigation bar and `ellipsis.circle` while every other screen uses `TopBar`, and the tab bar stays visible on a pushed page while it hides on a video page (`ios/collections_list_light.jpg`, `ios/collection_detail_light.jpg`). Editor: stock list, stock buttons, a spinner with no words and no Cancel (`ios/editor_light.jpg`, code). Delete and Rating: rounded-rectangle buttons where the system is pills (`ios/delete_bottom_light.jpg`, `ios/rating_light.jpg`). Options and question chips are rounded rectangles; every other chip is a pill. More than 200 lines across the app set fonts with `.vmk(size)` (a point size mapped to a text style) and 56 use raw system text styles, where the bar asks for type roles only. | Rebuild these on `TopBar`, `IconButton`, `PrimaryButtonStyle`, `TonalButtonStyle`, `SparkleChip` and `Font.role`. One rule for the tab bar: hidden on every pushed page. | `PhotoViewer.swift:36-60`, `CollectionViews.swift:103-128`, `CollectionViews.swift:210`, `EditorView.swift:15-34`, `EditorView.swift:92-104`, `EditorView.swift:147-159`, `DeleteAccountView.swift:258-272`, `RatingPromptView.swift:51-59`, `CreateOptionsSheet.swift:59`, `CreateSheets.swift:125` |
| P1-19 | Videos | Fade under the tab bar | Even where the fade is meant to work it is too weak. The failed card's text and a second "Try again" read through and beside the bar. `design_bar/ios/videos_dark.jpg`, `ios/videos_light.jpg`, `ios/videos_failed_xl.jpg` | After P0-1: reach full opacity at the top edge of the bar, and give the list bottom padding equal to the bar so the last card rests above it. | `DesignKit.swift:371`, `LibraryView.swift:152` |
| P1-20 | Organize sheet (Spanish) | Rows and the toggle | The collection name is cut to "London ·…" by the "+ Se agrega a una existente" chip, and the toggle's description is clipped under the buttons. `ios/organize_sheet_es_dark.jpg` | Put the chip under the name. Give the toggle text `fixedSize(horizontal: false, vertical: true)`. | `OrganizeViews.swift:103-110`, and `GroupRow` in the same file |

### P2

| # | Screen | Element | What is wrong (evidence) | Exact fix | Source |
|---|---|---|---|---|---|
| P2-1 | Media, Add to collection, Storage | Sheet background | Medium-height sheets use the default translucent glass, so the photo grid shows through the list. `ios/media_storage_sheet.jpg`, `ios/media_add_to_collection_light.jpg` | `.presentationBackground(Theme.surface)` on both. | `MediaView.swift:485`, `CollectionViews.swift:187` |
| P2-2 | Media | Selected tile | Two borders (a square stroke and an inner rounded picture) plus a numbered badge. The mockup has one border and a tick. `ios/media_selected3_light.jpg` | One 3 pt border on the shrunken tile. Keep the number only where order matters. | `MediaGrid.swift:123-128` |
| P2-3 | Media | Coach line | "Tap Select, choose photos, then Make a video." adds 8 words to a screen with a budget of 8. `ios/media_uploading_light.jpg` | Remove it. "Select" is visible in the bar. | `MediaView.swift:42`, `MediaView.swift:435-450` |
| P2-4 | Media | Collections strip | Sits between "Add photos" and the grid; the mockup goes straight to the month grid. Costs 150 pt before the first photo. `design_bar/ios/media_light.jpg` | Collapse it to one "Collections" row that pushes the list, or move it behind More. | `MediaView.swift:43`, `CollectionViews.swift:4-48` |
| P2-5 | Collection page | Empty state | "Nothing here yet" with an instruction and no button. `ios/collection_detail_light.jpg` | One tonal button: "Add photos". | `CollectionViews.swift:98` |
| P2-6 | Player | Info sheet | A raw text dump ("Chapters / 0:00 Intro / Photo credits…"). No "Made with AI" line, no grouped sources. `ios/player_info_sheet.jpg` | Three short groups: About (AI made, captions burned in), Sources, Credits. One Copy button. | `VideoDetailView.swift:304-326` |
| P2-7 | Player | Playback error | A black box with a sentence and "Try again" as bare white text; Share sits dimmed beside it. Seen with "Your session expired", where Try again cannot help. `ios/flow_10_reveal.jpg` | Icon, one line and a tonal button. For an expired session the button is "Sign in". | `VideoDetailView.swift:89-93` |
| P2-8 | Making | Notify row | Only the switch reacts; tapping the label does nothing. `ios/making_notify_tapped.jpg` | Make the whole row toggle. | `MakingScreen.swift:92-102` |
| P2-9 | Making, Videos | Fallback live lines | "Getting started.", "Writing the script." and "Putting it all together." end with a full stop; "Making voice and pictures" does not. "Writing the script" is a step name. `ios/videos_tryagain_later.jpg`, `ios/videos_deck_dark.jpg` | No full stops. Rewrite as what is happening to this video ("Finding the story"). | `Localizable.xcstrings` keys `making.line.*` |
| P2-10 | Videos | List rhythm | After a failed card an odd video becomes a second full-width hero mid-list. `ios/videos_many_scrolled.jpg` | Only the newest video is a hero. An odd one out keeps half width. | `LibraryView.swift:277-293` |
| P2-11 | Create | Platform menu | The menu lists the platforms bottom-up (Instagram first, YouTube last), the reverse of the Options sheet. `ios/create_for_menu.jpg`, `ios/create_for_menu_dark.jpg` | Add `.menuOrder(.fixed)`. | `CreateView.swift:300-314`, `DesignKit.swift:223` |
| P2-12 | Create | Library photo thumbnails | Each thumbnail carries a small library badge, and the count appears twice (the badge on the icon and "3 photos"). `ios/create_with_library_photos_light.jpg` | Drop the per-thumbnail badge. Keep one count. | `PhotoAttachments.swift:190`, `CreateView.swift:213`, `CreateView.swift:246` |
| P2-13 | Create, summary sheet | Layout | Two thirds of the sheet is empty; the X means "Edit request". `ios/create_summary_light.jpg` | Size the sheet to its content. Label the X "Close". | `CreateSheets.swift:27-28`, `CreateSheets.swift:162` |
| P2-14 | Options sheet (large text) | Look labels | "Auto", "Midnight", "Paper" and "Sunrise" render at four different sizes. `ios/create_options_xl2.jpg` | Two rows of two at AX sizes; no `minimumScaleFactor`. | `CreateOptionsSheet.swift:18`, `CreateOptionsSheet.swift:81` |
| P2-15 | Sign-in | Sample | A still picture; the bar and the mockup say sample footage. | Ship a 6 s muted loop (`sample_signin.mp4`; the README names the seam). Reduce Motion keeps the still. | `SignInView.swift:49-51` |
| P2-16 | Sign-in | Terms and Privacy links | 12 pt inline links; the target is the text height. `design_bar/ios/signin_light.jpg` | Give the legal line a 44 pt row height. | `SignInView.swift:34-35` |
| P2-17 | Settings | Rows | Feedback and Support have icons and chevrons; Terms and Privacy are bare blue text; About is a label. Switches are purple here and green on Making. `ios/settings_bottom_light.jpg` | One row style: text colour label and a trailing glyph for links. `success` tint for switches. | `SettingsView.swift:46-57` |
| P2-18 | Rating, Feedback | Sheets | The rating sheet is half empty. In Spanish the feedback title sits against the Cancel button. `ios/rating_light.jpg`, `ios/feedback_es_dark.jpg` | Rating: a content-height sheet. Feedback: use `TopBar` with a close icon. | `RatingPromptView.swift:33`, `FeedbackView.swift:33-35` |
| P2-19 | Player (full screen) | Close button | 40 by 40 pt. | 44 pt, or remove it with P1-1. | `PlayerView.swift:55` |
| P2-20 | Media | Search clear and privacy-note close | Small glyph buttons without a 44 pt frame. | Wrap in `frame(width: 44, height: 44)`. | `MediaView.swift:273`, `MediaView.swift:316` |
| P2-21 | Delight list | Items 8 and 9 | The empty Videos screen is text only, with no cartoon scene. Pull to refresh is the system spinner, not the drawn sparkle. `ios/videos_empty_light.jpg` | Build both as specified in section 9 of the bar. | `LibraryView.swift:202-227`, `LibraryView.swift:157` |
| P2-22 | Code | Dead file | `OptionsSheet.swift` (128 lines) is not referenced. | Delete. | `OptionsSheet.swift` |

### VoiceOver (from the code; not run with VoiceOver on)

The rebuilt screens are labelled with care: every `IconButton` requires a label, the capsule and the Making hero are marked as updating often, scene changes are announced once, and collection cards carry rename and delete actions. Gaps:

| Where | Gap | Fix | Source |
|---|---|---|---|
| Question sheet | The progress dots carry a label on a plain stack that is not an accessibility element, so it may never be read. | Add `.accessibilityElement()` before the label. | `CreateSheets.swift:80` |
| Photo viewer | "3 of 100" is plain text; swiping pages announces nothing. | Post the position when the page changes. | `PhotoViewer.swift:39` |
| Floating tab bar | Two buttons with the selected trait, no tab-bar container. | Add `.accessibilityElement(children: .contain)` and the tab-bar trait. | `DesignKit.swift:327-332` |
| Editor scene rows | Buttons with no label; they read the raw row text in visual order. | One combined label: kind, seconds, narration, "edited". | `EditorView.swift:75-77` |
| Storage sheet | The progress bar has no label or value. | Label it with the meter text. | `MediaView.swift:466` |

## 3. The ten changes that move the app most

1. **Fix the tab-bar fade and the hidden upload pill (P0-1, P0-2, P1-19).** One change in `MainTabs` restores six states.
2. **Close the credits dead end (P0-3).** Zero credits needs an answer: when the next ones arrive, or how to get more.
3. **Replace the Add photos sheet with a two-item menu and direct pickers (P1-5).** Six taps become three.
4. **One undo toast; remove the confirm dialogs; add Delete for videos (P1-8).**
5. **Rebuild the re-tokened screens on the design kit (P1-18):** viewer, Collections, Options chips, questions, Rating, Delete, Editor. One chip shape, one top bar, one button family, text styles only.
6. **One player control set (P1-1) and portrait-only iPhone (P1-2).**
7. **Make "cannot do this yet" visible (P1-3, P1-13):** an opaque disabled style, and the fix written on the Create button.
8. **A large-text and Spanish pass with acceptance captures (P1-14, P1-20, P1-16):** the seven AX breaks, one word per thing in both languages.
9. **Ship the defaults that keep the 3-tap promise (rulings 1 and 3, P1-6):** YouTube · 1 min, "Skip all", shorter remix chips.
10. **Give every video an exit and an identity while it is not ready (P1-9, P1-10):** Cancel on Making; title, Try again and Remove on the failed page.

## 4. What was not reached or verified

- **The real backend.** Everything ran on the fake. Not seen: the real request check leading to questions or a refusal, real photo uploads, a real retry, real server copy in the refusal sheets.
- **The reveal** (Making card to poster, autoplay with the 300 ms fade, "Your first video."). The fake video became ready and the player then showed "Your session expired", because the fake has no playback for a newly made video. Shared-element motion was not judged.
- **Sign-in beyond the first screen.** The hosted Apple, Google and email pages were not opened.
- **Editor.** Only its error state appears with the fake. The scene list, scene editor, preview, publish and done states were judged from code.
- **System pickers and permissions.** Not opened: the Photos picker, the Files importer for presentations, dictation and its permission, Save to Photos and its saved or failed states. Seen: the notification prompt and the share sheet.
- **Media search.** The fake returns every photo for any query; results, filter chips and "No photos match" were not seen. An empty Media library was not reachable (the fake always has 150 photos). A collection with photos in it was not seen (the fake collection opens empty).
- **Whether the keyboard opens by itself on Create.** In the simulator it did not appear until the field was tapped, which may be the simulator's hardware-keyboard setting.
- **Landscape on a device.** The simulator stayed sideways after leaving full screen; a phone held upright may rotate back.
- **VoiceOver, Reduce Motion, Reduce Transparency, haptics.** Read in code, not run.
- **Not captured:** iPad, the small phone beyond the implementer's five captures, the rating "ask" and "Not really" stages, the expanded upload panel, a read-only library, the storage meter, Organize's "nothing to organize" and failure states, deck states other than uploading, reading, ready, protected, too large and vertical, the Settings language menu (the capture missed it), and the Settings language switch taking effect.
- **Dark mode** was captured for a subset of the new states (Add photos, Options, Media selection, Settings, Credits, refusal sheets, Collections). The rest of the new captures are light.

## Method

- One simulator (iPhone 17 Pro), one job at a time, the existing derived data. States with a debug fixture were launched with `simctl launch` and captured with `simctl io screenshot`. States that need taps were captured by a throwaway UI test that was deleted afterwards; `git status --short mobile/ios` is clean.
- Largest text size here means Accessibility Large, the same category the implementer's `_xl` captures use. The app caps at AX3.
- Touch targets and fonts were read from code. Contrast was sampled from PNG captures where the background is not a flat token, and computed from `DesignTokens` elsewhere.
