# videomk design bar 2026 (iOS, Android, web)

Status: proposal written 2026-11-27 after the owner's review ("all screens are bad; the bar is an Apple Design Award"). It replaces taste arguments with a bar every screen can be checked against. Mockups: `docs/design_bar/mockups/` (phone: 6 boards, light and dark; web 1440: 5 screens, light and dark). Generator: `docs/design_bar/src/gen.py` + `shoot.sh` (static HTML, headless Chrome). Tokens: `docs/design_bar/src/base.css`.

Evidence labels: **[seen]** = observed in the owner's screenshots or our builds tonight; **[research]** = from the web research pass of 2026-11-27 (secondary summaries of Apple pages, not re-read line by line; re-verify before quoting publicly); **[judgement]** = design judgement.

## 1. The product in one sentence

**Describe it. Get the video.** One sentence in, a narrated video out, and nothing between the two that the person has to learn.

Three emotions, in this order:
1. **Ease**: "I knew what to do without reading."
2. **Wonder**: "I watched it being made."
3. **Pride**: "I want to show this to someone."

Every screen serves one of the three. A control that serves none is removed or moved behind Options.

## 2. What the award bar means for us

Apple Design Award categories **[research]**: Delight and Fun, Innovation, Interaction, Inclusivity, Social Impact, Visuals and Graphics. What recent winners were praised for **[research]**: sound and transitions that feel physical (CapWords), accessibility as the core feature (Speechify, oko: VoiceOver, Dynamic Type, haptics, audio), clarity under pressure (Watch Duty), warmth and character (Bears Gratitude), delight in routine (Duolingo), information made calm (Flighty).

Translated to videomk:

| Category | Our bar | Where it shows |
|---|---|---|
| Interaction | A first video in 3 taps; never a dead end; every wait is honest and locked | Create, Media, retry |
| Delight | You watch the video being made, scene by scene; the reveal feels like a small event | Making, first play |
| Visuals | One typeface, one accent gradient, content is the colour; glass only on floating controls | Everything |
| Inclusivity | Works with VoiceOver/TalkBack, at 200% text, in Spanish, with reduced motion, one-handed | Everything |
| Innovation | The prompt is the interface: remix chips ("Make it a Short", "Spanish version") instead of settings | Player, Create |
| Social impact | Honest about AI: sources and credits one tap away, no fake people, no news in cartoons | Info sheet, policy |

## 3. Signature interactions

1. **Create is one sentence.** The screen is a caret and "A video about…". Three example chips, two icons (photos, mic), three choices already made (YouTube, 1 min, Auto look), one button with its price. Nothing else. `phone_3_create`, `web_3_create`.
2. **The promise is kept after the tap.** The form dims and locks at once, the button becomes a live capsule ("Checking your request", then "Starting your video") with a moving ring, and Cancel is the only control. It ends in exactly one of: a question, a refusal, the Making screen, or the form restored intact. Never a frozen, editable screen. `phone_3_create` (second and fourth phones).
3. **Making is a story, not a progress bar.** The scene being built is shown large; finished scenes fill a film strip one by one; one plain line says what is happening now ("Adding footage of sunlit canopies") and the sentence being narrated appears beneath. No step names, no percentages. One switch: "Tell me when it's ready". `phone_4_making`, the banner in `phone_2_videos` and `web_2_videos`.
4. **The reveal.** When the video is ready the Making card turns into the poster with a shared-element transition, one success haptic, and the video starts muted-to-full with a 300 ms fade. First video only: a single line, "Your first video."
5. **Share is the primary action of a finished video.** One labelled gradient button; Save, Edit, Info and More are quiet icons. The end card offers Replay and New video. Under it, "Make another" chips turn the same idea into a Short, a Spanish version or a 30-second cut. `phone_5_player`, `web_5_watch`.
6. **Photos to video in one move.** In Media, selecting anything brings up one button: "Make a video · 3". It opens Create with the photos attached; Back returns to the same selection. Uploading has its own labelled button, "Add photos". `phone_6_media`, `web_4_media`.

## 4. Visual language

**Type.** System fonts only: SF Pro on Apple platforms, Roboto Flex on Android, the system stack on web (Inter fallback). Sizes follow the platform text styles (Dynamic Type / Material type roles); no fixed sizes in screens.

| Role | iOS style | Size/line (pt) | Weight | Use |
|---|---|---|---|---|
| Large title | Large Title | 34/40 | Bold, -0.6 tracking | One per top-level screen |
| Title | Title 2 | 22/28 | Bold | Video title, sheet title |
| Headline | Headline | 17/22 | Semibold | Buttons, row titles |
| Body | Body | 17/24 | Regular | Prompt text, sheet copy |
| Subhead | Subheadline | 15/20 | Regular | Live line, secondary |
| Footnote | Footnote | 13/18 | Regular | Meta ("1:31 · 1080p") |
| Caption | Caption 1 | 12/16 | Medium | Legal, counts |
| Web display | n/a | 88/92 (hero), 56/62, 40/46 | Bold, tight tracking | Homepage, page titles |

**Colour.** Content carries the colour; the interface is neutral. One accent.

| Token | Light | Dark | Use |
|---|---|---|---|
| bg | `#F7F7FA` | `#06070D` | Page |
| surface / surface2 / surface3 | `#FFFFFF` / `#EEEFF4` / `#E4E6EE` | `#11131D` / `#1A1D2B` / `#242838` | Cards, fills, pressed |
| text / text2 / text3 | `#0B0C14` / `#5C6175` / `#8B90A3` | `#F4F5FA` / `#A2A8BC` / `#70768C` | text3 never for essential text |
| primary / primaryC | `#4B45E0` / `#ECEBFF` | `#AAA8FF` / `#22224A` | Links, selection, tonal buttons |
| action gradient | `#3B36C8` to `#7A4BE6` | same | The ONE primary button per screen |
| brand gradient | `#2B2F9A` to `#6A3FC4` | same | Logo tile, Making card |
| live | `#22D3EE` | same | Only on the gradient or dark: sparkle, live ring |
| danger | `#D92D20` | `#FF6B5E` | Delete only |

Contrast to hold: body text 4.5:1, large text and icons 3:1, white on the action gradient 4.6:1 at its lightest point (computed for `#7A4BE6`). Cyan never on white.

**Space and shape.** 4-pt base, 8-pt rhythm; screen gutter 20 pt on phone (one value, everywhere), 48 px on web content, 64 px on the homepage. Radii: 14 (thumbnails in grids), 22 to 26 (cards, posters), full pill for buttons and chips, 32 to 36 for hero media on web. Touch targets 44 pt (iOS) / 48 dp (Android) / 44 px (web).

**Glass and elevation.** Glass only for things that float over content: the tab bar, the selection bar, player overlays, icon buttons over media **[research: Liquid Glass is for controls and navigation above content; use custom glass sparingly]**. Cards are opaque with one soft shadow. No borders plus shadows together.

**Icons.** SF Symbols on iOS (regular weight, medium scale), Material Symbols Rounded on Android, the same outline set on web (1.8 px stroke at 24 px). Rules: **one "+" per screen, and only where it means "add to this list"**; upload is a photo-plus glyph with the words "Add photos"; new video is a play triangle with a sparkle, never a bare plus; the sparkle marks AI suggestions and live work only.

**Illustration.** Empty states and onboarding use our own cartoon scenes (`docs/VECTOR_CATALOG.md`) with slow parallax, and, once approved, one guide character (`docs/CHARACTER_LIBRARY.md`). No stock illustrations, no 3D blobs.

**Motion.** Springs, not linear tweens (iOS `.spring(response 0.35, damping 0.86)`, Android M3 Expressive spatial springs **[research]**, web 240 to 320 ms `cubic-bezier(.2,.8,.2,1)`). Shared-element transitions: poster to player, Making card to poster, photo to viewer. The live ring rotates once every 2.4 s; scene tiles fill with a 200 ms scale-and-fade. Reduced motion: cross-fades only, the ring becomes a static two-tone border, nothing autoplays **[research: motion must be optional and never the only signal]**.

**Haptics (phones).** Light impact: chip or pill chosen, photo selected. Medium impact: Create tapped. Success: video ready, share sheet completed. Warning: refusal or failure. None for scrolling or typing. All system patterns, all silenced by the system setting.

**Sound.** The app is silent. The only sound is the video. (A soft "ready" chime may ride on the notification, never in-app.)

## 5. Rules (each one is testable)

1. **One primary action per screen**, filled with the action gradient, labelled with a verb. Everything else is an icon, a tonal or a text button.
2. **Never more than one "+" on a screen.**
3. **Primary actions are labelled.** Icon-only is for secondary actions, always with an accessibility label and a tooltip on web.
4. **Word budgets.** Create 14 words, video screen 8, Videos 6 plus titles, Media 8, Settings 30, sign-in 12 plus buttons. A screen over budget fails review.
5. **Three taps to a first video** from launch (signed in): New video, type, Create. Four taps from Media: Select, photos, Make a video, Create.
6. **Decide for the person.** Platform sets format, length and resolution; voice, music and background are chosen by the director. The Options sheet exists but nobody needs it.
7. **Locked, honest waits.** After a commit tap the form locks, says what is happening in three words, and offers Cancel. No spinner without words, no frozen screens.
8. **Undo over confirm.** Delete shows "Deleted · Undo" for 6 s; only account deletion asks to confirm.
9. **Forgiving errors.** A failure keeps everything (prompt, photos, options), says what happened in one line, and offers one action. Retrying reuses the same item and never drops attachments.
10. **No dead ends.** Every screen and sheet has a visible way back and a visible next step.
11. **Skeletons, not spinners,** for lists and grids; posters fade in; nothing jumps (stable keys, reserved sizes).
12. **No number ever starts at zero on screen** (counters, credits, progress), and no text is revealed in lumps.
13. **Same thing, same place, same word** on iOS, Android and web: Videos, Media, New video, Create, Share, Save, Edit, Info, Add photos, Make a video.

## 6. Accessibility and languages

- VoiceOver/TalkBack: every control has a label and a role; reading order follows the visual order; live updates ("Scene 5 of 9") are announced politely, not on every tick.
- Text size: layouts hold at iOS AX3 and Android 200%; pills wrap, titles take two lines, nothing truncates essential text.
- Contrast as in section 4; state never by colour alone (selection has a check, errors have an icon and words).
- Reduced motion and reduce transparency are honoured (glass becomes opaque surface).
- Web: full keyboard path, visible focus ring (2 px primary, 2 px offset), WCAG 2.2 AA, target size 24 px minimum and 44 px for primaries.
- English and Spanish are equals: every string in both, Spanish checked at +30% length; numbers and dates follow the language (`3,3 millones`).
- Captions: videos carry burned-in captions today; the info sheet says so. A real caption track is a follow-up.

## 7. Scorecard (0 to 5, honest starting point)

Scores for the current builds are **[judgement]** from tonight's screenshots and audits that could not finish (the disk filled); re-score after the screen-by-screen audits run.

| Category | iOS today | Android today | Web today | Bar to ship | What moves it |
|---|---|---|---|---|---|
| Interaction | 2 | 2 | 2 | 4 | Rules 5, 7, 9, 10; Media flow |
| Delight and fun | 2 | 2 | 1 | 4 | Signature 3 and 4, haptics |
| Visuals and graphics | 3 | 3 | 3 | 4.5 | Tokens, one gutter, real posters |
| Inclusivity | 2 | 2 | 2 | 4 | Section 6 as acceptance tests |
| Innovation | 3 | 3 | 2 | 4 | Remix chips, live Making, prompt-first web |
| Social impact | 2 | 2 | 2 | 3 | Sources in Info, clear AI labelling |

## 8. Per-screen checklist (copy into every PR)

- [ ] One primary action, labelled, gradient; nothing else filled.
- [ ] At most one "+"; upload says "Add photos"; new video uses the play-sparkle glyph.
- [ ] Word count within budget (count in the PR).
- [ ] Back or close visible; next step visible in every state (empty, loading, selecting, error).
- [ ] Waiting state: locked, three words, Cancel.
- [ ] Error state keeps the person's input and offers one action.
- [ ] Light, dark, Spanish, largest text size, reduced motion: screenshots attached.
- [ ] Screen reader pass: labels, order, announcements.
- [ ] 20-pt gutter (phone), tokens only, no literal colours or sizes.
- [ ] Skeleton for loading; no layout shift; no flicker on refresh.
- [ ] Haptics per the map (phones); no sound.
- [ ] Tap count for the screen's main journey stated and within rule 5.

## 9. Ten delight moments

| # | Moment | Effort (per platform) |
|---|---|---|
| 1 | Create capsule: the button morphs into the live "Checking your request" capsule with the rotating ring | 1 day |
| 2 | Scene tiles filling one by one on the Making card and screen (needs scene thumbnails from the backend) | 2 days + 1 backend |
| 3 | Making card to poster shared-element reveal with success haptic | 1 day |
| 4 | The narration line appearing under the film strip while it is voiced | 1 day + 0.5 backend |
| 5 | Example chips that type themselves into the prompt when tapped | 0.5 day |
| 6 | "Make another" remix chips on the player (Short, Spanish, 30 s) | 1 day + 1 backend |
| 7 | Photo selection: tiles spring 4% smaller with a tick and a light haptic; the bar counts up | 0.5 day |
| 8 | Empty states with a slow-parallax cartoon scene and one line | 1 day |
| 9 | Pull to refresh that draws the sparkle from the logo | 0.5 day |
| 10 | Homepage hero: the prompt types itself, then the video starts (reduced motion: static) | 1 day (web) |

## 10. Anti-patterns seen tonight (and the rule that ends each)

| Seen **[seen]** | Rule |
|---|---|
| Media: photos selected, no visible next step, no way back to the video | 1, 10; signature 6 |
| Three different "+" buttons on Media (upload, new collection, new video) | 2, 3 |
| Upload hidden behind a bare "+" in the header | 3 |
| Create looked frozen after the tap and stayed editable | 7 |
| Try again created a second card and dropped 60+ photos | 9 |
| Failed cards piling up with no way to remove them | 8, 9 |
| Photo-count badge clipped ("45" cut off) | Section 6 (large counts and text sizes are test cases) |
| A stat that sat on "0 billion" before counting | 12 |
| Headings revealed in stuck lumps of words | 12 |
| Player surrounded by labels and five text actions | 1, 4; signature 5 |
| Step names under the Making bar ("Script, Voice, Pictures, Final cut") | Signature 3 |
| Default Cognito sign-in page | Section 4; `phone_1_signin` |
| Homepage sample tiles starting on an empty or zero frame | 12; choose posters by hand |

## 11. What to change, by impact

**Web (the owner is waiting for it)**
1. Homepage: adopt `web_1_home` (88 px two-line headline with the gradient second line, one prompt field, a 1120 px hero video with the prompt and "Try this prompt" laid over its lower edge, a gallery where each tile sits above the sentence that made it). Hand-pick every poster frame.
2. App shell: a 248 px sidebar with three destinations and the credits card; the page title at 40 px; one "New video" button, top right.
3. Create (`/new`): the centred composer card of `web_3_create` on a soft aura, with the locked "Checking your request" state from rule 7.
4. Media: labelled "Add photos", month grid at 6 columns, the floating selection bar with "Make a video · N", the upload toast bottom right.
5. Watch: the player at 800 px with our own controls, Share as the one primary, the prompt and "Make another" chips in the right column.
6. Videos: the Making banner with scene tiles; cards with aspect badges; skeletons.

**iOS and Android (same list, native controls)**
1. Create: caret-first screen, three pills without key labels, the capsule wait state, error that restores everything.
2. Media: "Add photos" button, selection bar, Create opens over Media and Back keeps the selection (in progress tonight; finish and verify).
3. Making: film strip, live line, narration line, notify switch; remove step names everywhere.
4. Player: Share primary + four icons, end card, remix chips.
5. Videos: Making card with scene tiles, large first poster, 20-pt gutter, bottom fade under the floating tab bar, the play-sparkle create button.
6. Sign-in: full-bleed sample footage, Apple and Google buttons, "Use email" as a text button.
7. Tokens: replace literal colours and sizes with the table in section 4; one icon-button component and one top-bar style per platform.

**Backend needed for the full effect:** scene thumbnails and the current narration line in the status payload; a remix endpoint (same plan, new format/language/length).
