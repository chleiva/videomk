# videomk native apps: design brief

For the design agent. Read `SPEC.md` §3 for screen behaviour; this document says what to design, the constraints, and what to hand back.

## 1. The product in one paragraph
Describe the video you want, optionally with your own photos, clips and voice. An AI **Producer** makes it: it writes the story and chooses, every few seconds, the right visual (library photos, *your* photos and clips, draw-on sketches, charts, maps, diagrams), with narration, captions and music. The user supervises: see what the Producer chose and why, change anything by tapping or by telling the Producer.
(Earlier drafts assumed "topic in, photos picked by the user". That was wrong: see `docs/PRODUCER.md`. The user should almost never have to choose a photo.) Creators publish to YouTube and social. The apps must feel like a
**confident, calm creative tool**: fast to start, never overwhelming, with the editor as the place where people feel in control.

## 2. Design principles
1. **Start in one gesture.** A new user should be one text field away from their first video. Everything else is progressive.
2. **Show the work.** Generation takes a while: make progress legible (stages, partial results) instead of a spinner.
3. **Editing is direct.** Tap the thing you want to change. Prefer structured controls (rows, chips, steppers) over typed syntax.
4. **Trust and attribution are visible.** Photo credits, sources and what "published" means are first-class, not fine print.
5. **Platform-idiomatic, brand-consistent.** One identity (colour, type, motion, voice), but navigation and components feel native: iOS (HIG) and Android (Material 3).
6. **Accessible by default.** Large text, screen readers, contrast, reduced motion: designed in, not audited in.

## 3. Brand starting points (challenge them)
The video engine already has three "looks" that the app's brand should be able to sit beside. Sampled from the product:

| Look | Background | Text | Accent | Accent 2 |
|---|---|---|---|---|
| Midnight | `#0A0E20` → `#1E1B4B` | `#F8FAFC` | `#6366F1` | `#22D3EE` |
| Paper | `#FBF8F3` → `#EEE6DA` | `#1F2937` | `#E11D48` | `#2563EB` |
| Sunrise | `#1C1042` → `#7A1F5C` | `#FFF7ED` | `#FB923C` | `#FDE047` |

The current web app uses neutral greys, rounded 2xl cards, Inter, and a blue `#3B82F6` → pink `#EC4899` gradient for the main action.
**Decided:** UI type is **SF Pro (iOS) and Roboto Flex/system (Android)**, for the best Dynamic Type/font scaling and native feel; Inter stays inside the generated videos. Brand expression comes from colour, motion, iconography and the wordmark: design those to carry it.
**Decided:** Android is **brand-first**, with *Use system colours* (Material You dynamic colour) as an opt-in setting on Android 12+. Show how each screen looks in both modes; status colours never follow the wallpaper.
Voice: plain, warm, specific; no hype, no "magic" language; errors say what happened and what to do.

## 4. Deliverables

### 4.1 Foundations (hand back first)
- Brand: name treatment, **app icon** (iOS and Android adaptive + monochrome), launch screen, empty-state illustration style.
- **Design tokens** in a machine-readable format (JSON): colour (light/dark, semantic: surface, onSurface, primary, danger, success, warning, scrim…), type scale, spacing, radii, elevation, motion durations/curves. Tokens must map cleanly to SwiftUI and Compose themes. Android may use Material You dynamic colour as an option; propose how the brand survives it.
- **Component inventory with all states** (default, pressed, disabled, loading, error, focused, selected, dragging): buttons, text fields (with counters and errors), status chips, video card (grid/list), scene row, scene-type icon set (title, bullets, diagram, chart, timeline, big number, quote, photo), bottom sheet / side panel, tabs/segmented control (Preview | Published), toasts/snackbars, empty states, skeletons, banners (conflict, render failed, offline).
- **Iconography:** SF Symbols on iOS and Material Symbols on Android where they exist; custom icons only for the 8 scene types and brand marks.
- **Motion principles:** screen transitions, reorder lift/drop, stage-by-stage progress, success moment when a video finishes. Everything has a Reduce Motion alternative.

### 4.2 Flows and screens (iPhone, iPad, Android phone, Android tablet/foldable)
1. **Onboarding + sign-in:** native **Sign in with Apple** and **Sign in with Google** (one-tap sheets, no browser handoff); Apple's button must follow Apple's identity guidelines and Google's the Google branding rules; first-run value moment before asking for notifications; sign-in errors; a hidden email/password reviewer path (not shown to normal users).
2. **Library** (grid/list; statuses: running, complete, failed, rejected-with-reason, editing; empty; offline; first-run examples).
3. **Create = brief composer:** free-text/voice brief; attached photos and videos (grid of selected media, remove/reorder, "+42 more"); length ("Producer decides" or fixed), look, music; cost estimate; upload progress and privacy copy; validation errors; "not allowed" explanation. Show three example briefs: a topic, a holiday story from photos, "turn my clips into a highlight reel".
4. **Progress** (6 stages; live status; what happens if the user leaves; push permission request at the moment of value; Live Activity design for iOS lock screen/Dynamic Island, ongoing notification for Android).
5. **Player/detail** (player controls with chapters; share/save; copy title/description; revision info; report).
6. **Producer's plan and editor** (the priority screens: see 4.3). The plan view is the *main* editing view; the scene inspector is secondary.
7. **Credits and purchases:** balance chip (always visible in Library/Create), **a quote shown before every spend** (create and AI edits), **free allowance states** (welcome: 3 clean videos up to 3 min in the first day; then one free video per day, up to 2 min, watermarked, with a clear "next free video in…" state; the paid-only options are visible but explained, not hidden), **the watermark** (small bottom-right wordmark: design it and show it on the real caption/photo-credit layouts) and the **remove-watermark** action on free videos, the **credit store** (three packs shown honestly with what each buys, store-native purchase sheets, pending/Ask-to-Buy, failed, success), transaction history, low-balance and out-of-credits states that route to purchase without pressure, refunded-render messaging ("no credits used").
8. **Settings** (account, delete account confirmation, notifications, appearance, *Use system colours* on Android, legal, report, feedback).
9. **System surfaces:** push notification content, widgets (recent videos), share-sheet presentation, App Shortcuts/Intents UI.

### 4.3 The editor, in detail
This is where design effort should concentrate. Design for one-handed phone use first, then expand to tablet.
- **Producer's plan (main view):** a vertical storyboard: each narration chapter with its text, then a horizontally scrolling strip of visual items (thumbnail, duration, a small badge for the kind: *Your photo*, *Library photo*, *Your clip*, *Sketch*, *Chart*, *Map*, *Scene*). Tap an item: a sheet with *why this was chosen*, *Ask the Producer for another*, *Use one of my photos*, *Draw it instead*, *Remove*. A **chat bar** ("Ask the Producer to change something…") with suggestion chips ("Shorter beach part", "More drawings", "Add a map") is the primary way to make bigger changes.
- **Replace media sheet** (replaces the old photo picker): suggestions / my media / draw tabs; library candidates always show photographer + source as tappable credit.
- **Scene list:** each row shows type icon, narration excerpt, duration, state (*edited*, *needs attention*, *will be re-made*). Reordering by long-press drag with a clear lift state and haptics; delete with undo; insert affordance between rows. Accessible alternative to dragging.
- **Inspector:** bottom sheet on phones (peek / half / full detents, with a pinned mini-player or preview thumbnail so the user doesn't lose context), side panel on tablets.
  Forms for each scene type; pay special attention to **diagram** (steps and arrows as rows/chips with a live mini-preview, no typed syntax), **chart** (label/value rows, bar/line toggle), **timeline** (date/label rows), and **photo** (search field, candidate grid with photographer + "Unsplash"/licence line as tappable links, selected state, "no good photo" state).
- **Narration field:** word count, spoken-time estimate, limits and inline errors; "listen to this scene" affordance.
- **Preview vs Publish:** make the difference obvious (draft quality, fast, doesn't change the published video vs full quality, new version). Show render progress in place; lock editing during render with a clear explanation.
- **Revision/conflict states:** "this video changed on another device" with *Reload* and *Keep my changes*; revision list with restore.
- **Undo/redo**, draft-saved indicator, discard changes confirmation.

### 4.4 Content and states to design explicitly
Loading skeletons, empty, offline, error, rate-limited ("5 of 5 videos used today"), rejected prompt, failed render ("no quota used"), long titles/narrations, very long lists, right-to-left readiness, largest Dynamic Type/font scale, dark mode, landscape on phones, split-screen/multi-window on tablets.

### 4.5 Store and marketing assets
App Store and Google Play screenshot sets (light/dark where useful), feature graphic, preview-video storyboard, store listing copy tone.

## 5. Constraints from the product (not negotiable)
- Videos are **16:9, 1080p**, with burned-in captions; the apps never render video.
- Eight scene types only (listed above); the editor can't invent new ones.
- Photos come from Unsplash and Openverse. **Attribution must be visible and linked** wherever a photo appears in the app (picker, editor row, player details), using the photographer name and "Unsplash"; Unsplash reviews screenshots of this.
- Narration limits: 6–70 words per scene. A video has up to 90 scenes.
- Money is **credits plus a free allowance (3 videos on day one, then 1 per day), bought only through the stores**; AI edit actions cost credits and are quoted first, non-AI edits are free; amounts, costs and offers are server-driven and may change, so no price or credit count is hard-coded in copy or layouts (layouts must survive different numbers and currencies). Editing has its own limit and a "one render at a time per video" rule.
- No analytics/crash SDK UI (no consent walls from third parties); telemetry is first-party and anonymous.
- Safety: users must be able to **report** content in-app; rejected prompts show the server's reason.
- Photos of identifiable private people are rejected by the photo reviewer; the UI should never promise a specific photo.

## 6. Hand-off requirements
1. Tokens as JSON (and the source Figma/file), with a README of semantic naming.
2. Every screen in light and dark, at the sizes above, annotated with spacing, type styles and states; interactive prototypes for: create → progress → player, and the editor (reorder, inspector sheet, photo picker, preview/publish).
3. Redlines for the editor's gestures and sheet detents; motion specs with durations and curves.
4. An accessibility spec per screen: reading order, labels/hints, actions for non-gesture alternatives, minimum touch targets (44 pt / 48 dp), contrast ratios.
5. Rationale for any place the iOS and Android designs diverge.

## 7. How the design is checked against the build
Native implementation uses the exported tokens directly (compiled to Swift/Kotlin), and each component has a screenshot test per state so drift from the design is caught automatically.
