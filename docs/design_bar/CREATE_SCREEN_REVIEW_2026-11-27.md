# VideoMK Create screen: independent design review

Reviewer stance: outside senior product designer, no stake in the build. Date of review: 2026-11-27. Read-only review: nothing in the repo was changed, nothing was run.

Evidence labels used throughout: **[code]** read in the repo, **[shot]** seen in a screenshot, **[src]** read on a web page I actually opened, **[snippet]** only a search-result summary (page not opened or the fetch failed), **[memory]** my own knowledge, not re-verified today, **[judgement]** design judgement.

---

## 0. Verdict

1. The concept is defensible and current: prompt-first page, quiet icon tools, option pills that show their value, ONE labelled primary button with its price. Nothing here is "wrong 2026 practice", and the owner's instinct that something feels off is half right: what is off is the **bottom dock as built** (four stacked bands, a full-width 56 dp bar whose price sits 200 dp away from its verb, a helper line that repeats the placeholder) and, on Android only, that **the keyboard never opens by itself**, which leaves a 38% dead gap and makes the whole screen read as a form with a huge button.
2. Recommendation: **keep the concept, rebuild the dock** (Create becomes a compact labelled pill at the trailing end of the tool row, tools and Create share one row, helper line deleted, Android autofocus added). Without the rebuild the screen is "acceptable with small fixes" (list in section C.6); with it, it matches how every leading composer in the benchmark behaves. Confidence: 80% that the autofocus fix and the helper-line deletion are right, 70% that the compact Create beats the full-width bar for our product (the benchmark is mostly secondary sources, and our action spends credits, which is the one argument for keeping a loud button).

---

## A. BENCHMARK

### A.1 Sources actually read, and what each shows

| # | Source | What it shows | Status |
|---|---|---|---|
| 1 | NN/g, "Adding UI Controls to Prompting" https://www.nngroup.com/articles/prompt-controls-genai/ | Prompt controls "surround the input field"; formats are buttons, toggles, menus, cards; Perplexity puts Focus and Attach next to each other and **away from the Send icon**; unlabeled icons confuse people new to genAI, use conventional icons with labels or tooltips; long control lists overwhelm; error text must sit near the control that caused it. | [src] (about text chatbots, not video tools) |
| 2 | Apple HIG, Buttons https://developer.apple.com/design/human-interface-guidelines/buttons | "Use a button that has a prominent visual style for the most likely action in a view", "keep the number of prominent buttons to one or two per view"; "use style, not size, to distinguish the preferred choice"; hit region at least 44x44 pt; an activity indicator inside the button with a changed label ("Checkout" becomes "Checking out…") is the sanctioned wait state; "prefer buttons that span the width of the screen for primary actions" is **watchOS only**. Nothing says a primary action must be full width on iPhone. | [src] |
| 3 | Apple HIG, Text fields https://developer.apple.com/design/human-interface-guidelines/text-fields | iOS: "use the leading end of a text field to indicate purpose and the trailing end to offer additional features". Text fields are for small inputs; larger text uses a text view. | [src] |
| 4 | 9to5Google, Gemini redesign, 3 May 2026 https://9to5google.com/2026/05/03/gemini-full-redesign/ | Pill-shaped prompt box; the **only** left control is "+" (opens a sheet: Photos, Camera, recent images, Files, Notebooks); voice input and Gemini Live on the right; model picker moved to the top-left. Limited iOS rollout at time of writing. | [src] |
| 5 | 9to5Google, Gemini "+" menu, 24 Mar 2026 https://9to5google.com/2026/03/24/gemini-plus-menu-redesign-early-2026/ | Tools merged into the single "+" menu; model picker left of the voice button; **once text is typed the mic turns into a send button** (web). Reviewer finds the merged menu cluttered. | [src] (web, one account) |
| 6 | 9to5Google, Gemini prompt bar, 9 Oct 2025 https://9to5google.com/2025/10/09/gemini-app-prompt-bar-redesign/ | Box removed, bar is a bottom sheet with a shadow; "+" and Live pushed to the edges; mic "housed in a circle"; model picker bottom-right of the bar. | [src] |
| 7 | BGR, ChatGPT makeover, 22 May 2025 https://bgr.com/tech/chatgpt-got-a-makeover-but-all-of-your-ai-tools-are-still-there | "+" (files, cloud) and a **Tools** menu beside it; dictate and Advanced Voice icons in the composer area; same design on the iPhone app. Send position not described. | [src] |
| 8 | AI UX Playground, Claude composer teardown https://aiuxplayground.com/teardowns/claude/composer | "+" on the left opens one menu (attachments, projects, skills, connectors, style); model and effort on the right rail; mic and waveform side by side on the right; "send affordance appears when content is ready"; attached images preview above the prompt; empty card shows starter pills. Also Anthropic support: the "+" opens camera, photos, files. | [src] third-party teardown, plus [snippet] for the support page |
| 9 | Google Flow help https://support.google.com/flow/answer/16352836 | Before generating, "in the prompt box settings, check the active model, resolution, and the latest credit costs": one **settings** entry on the prompt box holds model, aspect ratio, outputs and shows credit cost. Search summary says top right of the prompt box. | [src] for the quote, [snippet] for "top right" |
| 10 | WCAG 2.2, 2.5.8 https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | 24x24 CSS px minimum with a spacing exception (web). | [src] |
| 11 | Android Developers, accessibility principles https://developer.android.com/guide/topics/ui/accessibility/principles | Labels on every interactive element, `onClickLabel` for non-obvious actions, do not rely on colour alone, group related content with `mergeDescendants`. | [src] |

### A.2 Sources I could only see as summaries (treat as lower confidence)

| Product | What the summary said | Link | Status |
|---|---|---|---|
| Midjourney (web) | An image icon in the prompt bar adds image/style references; a settings icon at the end of the prompt line sets defaults for all prompts including aspect ratio; `--ar` still works typed. Docs page returned 403 to my fetch. | https://docs.midjourney.com/docs/create-page | [snippet] |
| Sora | Prompt box at the bottom, a settings icon (orientation, duration), an arrow submits. One guide claims OpenAI **discontinued the Sora apps on 26 April 2026**; I could not confirm this. Treat Sora as historical. | https://www.datacamp.com/tutorial/sora-ai | [snippet], unverified |
| Runway | Prompt box and image picker, then "Settings" for duration and aspect ratio, then Generate. | https://www.tomsguide.com/ai/how-to-use-runway-on-your-smartphone (body truncated for me) and https://online.hitpaw.com/learn/runway-ai-video-app.html | [snippet], third party |
| Luma | Prompt box with mode tabs; model, duration shown as settings you "check before generating"; aspect ratio taken from attached media in Keyframe mode. Help page 404 on fetch. | https://lumaai-help.freshdesk.com/support/solutions/articles/151000214865 | [snippet] |
| Pika | One "Create anything" prompt with model, aspect ratio, resolution pickers and a Generate button; Video Studio panel adds duration, audio, references. Versions conflict between sources. | https://digitaltrends.com/computing/how-to-make-ai-videos-pika | [snippet] |
| CapCut | Prompt field or image upload, aspect ratio and duration set before generating, a Generate/Create button; credits are deducted on confirm. Layout position not described. | https://www.capcut.com/resource/ai-video-generator-guide | [snippet], vendor |
| Material 3 | Bottom app bar is being replaced by the docked toolbar in M3 Expressive; Material 2 advised against an extended FAB stacked above a bottom bar because it eats space. The official m3.material.io pages are script-rendered and did not load for me, so FAB size and "one primary action" wording are **not verified today**. 48 dp touch target is [memory]. | https://9to5google.com/2025/05/18/material-3-expressive-toolbars/ | [snippet] |
| Thumb reach | Hoober's grip study: bottom of the screen is the comfortable zone; top and far corners are least accurate; on very large phones people shift grip so the lower half can go out of reach. One source calls the thumb zone a hypothesis, not universal evidence. | https://gizmodo.com/how-to-design-for-thumbs-in-the-era-of-huge-screens-1636955848 | [snippet] |
| Descript | Not researched. **Unverified.** | | |
| Canva Magic / Canva AI | Mobile composer layout not found; only that Canva AI 2.0 (April 2026) is conversational and starts from a search-style bar. **Unverified.** | | |

### A.3 Table: products by pattern

"Cost" = where a credit price shows. "Options" = per-request choices visible on the composer itself.

| Product (surface) | Attach | Voice | Send / generate | Options visible | Options container | Primary visible when empty | Cost shown | Evidence |
|---|---|---|---|---|---|---|---|---|
| ChatGPT (web, iPhone) | "+" left | dictate + voice mode icons in the composer | send (position not confirmed) | none (a Tools menu beside "+") | menu | not confirmed | none | #7 [src] |
| Claude (app) | "+" left, one menu | mic and waveform, right rail | appears when content is ready | model and effort, right rail | menu/sheet | **no, appears with content** | none | #8 [src, third party] |
| Gemini (iOS 2026, web) | "+" only control on left; opens sheet | mic and Live on the right | mic **becomes** send when text typed (web) | none (model picker moved to top-left) | sheet/menu | swap, not hidden | none | #4 #5 #6 [src] |
| Perplexity (chat) | Attach next to Focus, kept away from Send | n/a | send trailing | Focus, Pro toggle | toggle | n/a | none | #1 [src] |
| Google Flow (web) | in prompt box | n/a | Generate | **one Settings entry** (model, aspect, outputs) | popover | n/a | **in the settings popover** | #9 [src] partial |
| Midjourney (web) | image icon in bar | n/a | Enter / submit | **one settings icon** at the end of the line | panel | n/a | none | [snippet] |
| Sora (historical) | in bar | n/a | arrow | one settings icon (orientation, duration) | popover | n/a | none | [snippet], app status unverified |
| Runway (mobile) | image picker in the prompt area | n/a | Generate | Settings (duration, ratio) | panel | n/a | not confirmed | [snippet] |
| Luma, Pika | in the prompt box | n/a | Generate | model, duration, ratio, resolution (2 to 4) | pickers/panel | n/a | not confirmed | [snippet] |
| CapCut (AI video) | image upload | n/a | Generate/Create | ratio and duration before generating | panel | n/a | on confirm | [snippet] |
| **VideoMK Android (today)** | photo icon, bottom-left, own row | mic next to it | **full-width 56 dp bar, own band** | 3 to 4 pills plus a sliders icon | per-pill menu, Look sheet, Options sheet | yes, flat grey | on the button, far right | [shot] [code] |

### A.4 Consensus and outliers

**Consensus (high confidence for the chat apps, medium for the video tools):**

1. **Attach is a single "+" (or one image icon) at the leading end of the composer**, inside or directly under the field. Gemini, ChatGPT and Claude all do this.
2. **Voice sits at the trailing end, next to send**, in the chat apps (ChatGPT, Claude, Gemini). Perplexity's rule, from NN/g, is the counter-argument: keep context-gathering controls (attach, focus) away from Send. Both exist; nobody puts them in different bands of the screen.
3. **Send is in the input row, small and round or compact, at the trailing end.** It is a state of the composer, not a separate bar. Claude shows it only when content exists; Gemini swaps the mic for it. I found **no** chat composer whose send is a full-width labelled bar.
4. **Per-request options are hidden behind one settings affordance, or one or two pills, never four.** Chat apps show zero (model only). Image and video tools (Flow, Midjourney, Sora, Runway) use one settings icon that opens a popover or panel; Luma/Pika/CapCut show two to four pickers. The video tools that cost money put the **cost near the settings or on Generate**, not in a footer.
5. **Generate/Create is a labelled verb in video tools** (Flow, Runway, Luma, Pika, CapCut all call it Generate or Create in their docs); chat apps use a bare arrow because a reply is cheap and instantly reversible.
6. Prominent button = the single most likely action, one or two per view, 44 pt minimum hit region (Apple HIG, [src]). Apple's text does not mandate full width on iPhone.

**Outliers:**

- VideoMK's full-width bar as the send action of a composer: no verified chat app does it. It is, however, a normal pattern for **forms** and for credit-spending commits, which is the reasoning behind our choice [judgement]. This is why I call it defensible rather than wrong.
- Four visible per-request pills plus a sliders icon: more than any verified product (the max in the sources is the four pickers of Luma/Pika, and those are model-dependent controls on desktop-class screens).
- Bolt-plus-number as the price glyph: I found no verified product using it; Flow words the cost in a popover. Not an error, but it must be taught (see B).
- Android screen opening with no keyboard: all chat composers open with the caret; our iOS and web do as well [code].

---

## B. CRITIQUE

### B.1 What is on the screen, counted

Empty state, Android dark [shot] [code]:

- Elements: X, prompt field with placeholder, 3 example chips, attach, mic, sliders, 3 pills, Create (label + bolt + price), helper line (bolt + words) = **13 visible elements, 12 tap targets** (X, field, 3 chips, 3 icons, 3 pills, Create).
- Visible words: about 22 including chips, 12 without. Our own budget in `docs/UX_2026_REDESIGN.md` is 14 words on the surface and `docs/DESIGN_BAR_2026.md` says "two icons, three choices, one button. Nothing else." The sliders button is the "something else".
- Vertical budget (device 1440x3088 at about 3.75x, so about 384x823 dp): the controls block, from the icon row to the helper line, is about **220 dp, 27% of the screen**. The empty gap between the last chip and the icon row is about **38% of the screen**. Prompt field and its own tools are about 600 dp apart.
- With the keyboard up (about 300 dp) and the status and nav bars, roughly 450 dp is left. X row 60 dp plus a 220 dp dock leaves **about 160 dp for the sentence**: the code already contains a special `compact` mode (CreateScreen.kt line 284) that makes the controls scroll away when height is under 460 dp, which is the dock admitting it is too tall.
- Create button: 56 dp high, about 336 dp wide. The verb is left-aligned and the price right-aligned, so verb and price are about **200 dp apart** with empty gradient (or empty grey) between them [shot].

Densest state, with 3 photos, a notice and a cast look [code]: X, field, 3 photo remove targets plus the add tile, attach, mic, sliders, 4 pills (two rows), a look notice line, a status line with a fix chip, Create = about **16 tap targets and 6 stacked text or control rows** in the lower half. Layout copes (PillRows has four fallback arrangements), but the screen has stopped being "one sentence".

Note on "up to five pills": the code places at most four (For, Length, Look, Characters); the fifth child is the compact twin of Characters used at large text. Treat four as the real maximum.

### B.2 Per element: keep, move, merge, delete

| Element | Verdict | Why |
|---|---|---|
| **X (top-left)** | **Keep** | Full-screen route; a close icon top-left is the HIG/Material norm and the 48 dp hit target is right. Polish: it is a filled glass disc, the only filled circle at the top; a plain glyph on a 48 dp target is calmer. Keep the "Discard?" guard when text exists. |
| **Prompt field** | **Keep, and make it open with the keyboard** | Borderless 24 sp text on the page is the best thing on the screen: it reads as a sentence, not a form. A short brief of one to four sentences does not need a docked chat box. Fix: Android must focus it on open (iOS does after 450 ms, CreateView.swift line 89; web has `autoFocus`; Android only focuses when coming from Media, Root.kt line 255) [code]. Placeholder colour textTertiary on background is 4.46:1, just under 4.5; it passes as large text (3:1) but use textSecondary on the placeholder at no cost. |
| **Three example chips** | **Keep, but fewer and temporary** | They are the best first-run accelerator (one tap to a first video). They already vanish when typing, voice starts or anything is attached [code], which is right. Add: hide for good after the account's first video; show two, not three, when free height is under about 520 dp; never show them while the keyboard is down and the window is short. |
| **Attach (photo-plus icon, left)** | **Keep, keep the photo glyph, keep the badge** | All benchmark apps have it leading. Our glyph is a photo-plus on purpose (design-bar rule 3: "upload is a photo-plus glyph", never a bare plus) and our menu offers phone photos, My media, presentation. A bare "+" is the chat convention, but ours is a video-maker whose attachments are photos; the specific glyph discovers better. Position is right; what is wrong is that it sits in a band of its own, far from Create. |
| **Microphone** | **Keep, same cluster as attach** | The chat apps put mic at the trailing end next to send; I recommend the opposite for us, on NN/g's Perplexity reasoning: our send **spends credits**. A mis-tap on a mic next to Create is harmless; a mis-tap on Create costs a video. Keep mic in the left cluster. Do not do Gemini's "mic becomes send" swap: our Create is labelled and priced and must not move or change identity while the person is dictating. |
| **Sliders (settings) icon** | **Move into the tool cluster; keep, rename "Options"** | It holds things the pills do not: Quality (720p/1080p/4K and the 2x price), Subtitles, Language, Format tiles, Watermark, Scenes and Background when the server offers them (OptionsSheet.kt) [code]. These are real but rarely changed, so one settings icon is the benchmark pattern (Flow, Midjourney, Sora, Runway). The problem is placement: today it is the right end of the icon row, about 300 dp from the other two icons, and it competes with the pills. Move it next to attach and mic. Also remove the duplicates inside the sheet (the For chips and the Look swatches are already pills): two ways to set one thing is how "Auto" gets confusing. |
| **Pills: For (Shorts), Length (2 min), Look (Auto)** | **Keep all three visible; add a leading glyph** | They are the state of the video ("what you will get") and Length is the cost driver, so Length must stay one tap from the thumb. Problem: a value alone is ambiguous. "Auto" means nothing to a first-time user (auto what: voice, look, length?), and "Shorts" is not obviously a format. Our own spec (`UX_2026_REDESIGN.md` 4.2) calls for glyphs (clock for length, sparkle for look); the build dropped them, while web mobile kept a sparkle on "Auto" [shot]. Use a 16 dp leading glyph: aspect shape, clock, sparkle. |
| **Characters pill** | **Keep as built (conditional), never add a sixth** | It appears only for looks with a cast, and the layout drops to two rows only then. That is an exception state, not the baseline. Rule going forward: anything beyond For, Length, Look, Characters goes to Options. If the owner wants one row always, the alternative is faces as an accessory inside the Look pill and the cast chosen inside the Look sheet; that undoes the expert-reviewed split, so I do not recommend it now. |
| **Create (full-width bar, 56 dp, own band)** | **Change: compact labelled pill at the trailing end of the tool row** | See B.3. |
| **Cost chip "bolt 2"** | **Keep the glyph, move it next to the verb, teach it once** | See B.4. |
| **Helper line "Describe your video"** | **Delete** | See B.5. |

### B.3 Is the Create button too massive?

Honest answer: **it is large for what it does, not wrong in kind.**

For keeping it: Apple's HIG asks for one prominent button for the most likely action and our screen has exactly one [src #2]; the disabled-but-tappable state that explains itself on tap is good (the code shakes the status line and puts the caret back in the field); a loud credit-spending button is a reasonable safeguard.

Against it, in order of weight:

1. **Fitts and placement.** With the keyboard up (the normal state once autofocus is fixed) the bar sits above the keyboard on its own band, with two more bands above it. The common action, "I finished typing, make it", should be the nearest, smallest-travel target; in every composer in the benchmark it is the trailing key of the input row.
2. **Space.** The bar plus its caption and gaps cost about 100 dp of the 160 dp the sentence has left with the keyboard open (B.1).
3. **Verb and price split by 200 dp.** "Create" at the left edge and "bolt 2" at the right edge read as two unrelated things; the price needs to read as part of the verb ("Create, 2 credits").
4. **Disabled state, empty prompt.** A 336x56 dp flat grey slab with a grey bolt and "2" is the largest object on the screen while saying "not yet". Contrast is fine (label #A2A8BC on #242838 is 6.2:1; WCAG exempts inactive components anyway), but the container against the page is 1.4:1 so it reads as a hole, not a button. A compact tonal pill says the same thing with far less visual weight.
5. **Consistency with web desktop**, which already ships the compact version: icons, pills, and a compact Create in one row inside one card [shot web d1440]. Web mobile (390 px) is the same stacked bands as Android.

So: it should become a compact labelled pill (not a bare arrow: the action costs credits and the benchmark's video tools all label it), at the trailing end of the tool row. Staying a bar remains defensible if the owner prefers the louder affordance; in that case apply C.6.

### B.4 Is the cost chip understood?

Probably not on first sight. A bolt plus a bare number is our own convention; the only benchmark source on cost (Flow) words it ("credit costs") and puts it with the settings. The number is reinforced in the Length menu rows (price on each row) and the balance caption, but on Android's empty state the caption is replaced by the helper line, so **the balance and the word "credits" appear nowhere on the empty screen**, and the helper line carries its own bolt, which makes the glyph decorative on one line and meaningful on another [shot]. Fixes: keep "bolt 2" adjacent to the verb; until the account has made its first video, show one caption under the dock, "2 credits, you have 11"; the accessibility label already says what it costs (stateDescription) and should say "credits" in words.

### B.5 Is the helper line redundant?

Yes. When the prompt is empty it says "Describe your video" under a field that says "A video about…" and above a button that is visibly inactive. Three signals for one fact. Its only unique job is to be the target of the shake when someone taps the disabled Create, and that can be a transient message (StatusLine already supports it). In the empty state it also displaces the balance caption. Delete the persistent line; keep real status messages (too long, not enough credits, over a platform limit, a fix) as a single live-region line above the dock only when there is something to say.

### B.6 First principles checks

- **Fitts and thumb zones (tall phone, about 823 dp).** The prompt field is at the top, in the hard-to-reach zone, but it is only tapped once (and never, once autofocus lands); typing is on the keyboard. What must be in reach is Create, attach, mic, and the pills: all bottom third. Today they are, so the zones are respected; the defect is **distance between related controls**, not reach. Create, being right-edge-bottom, is easy for right-handed thumbs and a stretch for left-handed; chat apps accept this.
- **Hierarchy.** One gradient object, good. But the grey disabled Create is the same size as the gradient one will be, so the screen's dominant shape is a non-action in its first state.
- **Minimalism.** The surface fails its own budget (12 words without chips against 14, plus the sliders icon against "nothing else") and the helper line is pure repetition.
- **Discoverability.** Strong: every control shows its value; the weakness is unlabeled values ("Auto") and the bare bolt.
- **Consistency across platforms** [code] [shot]: iOS and Android share the same band structure, which is good; but iOS auto-focuses and Android does not; iOS caps the dock at Dynamic Type accessibility1 while Android relies on a compact scroll mode; defaults differ (Android Shorts, 2 min; iOS YouTube, 1 min; web Video, 1 min), which may be saved preferences, I cannot tell; the web mobile pills carry a sparkle, the apps do not; web desktop puts Create in the card, the apps do not.
- **Accessibility** [code]: icon buttons are 44 dp drawn on a 48 dp target (pass); pills 48 dp hit (pass); Create 56 dp (pass); every control has a content description and the disabled-looking Create stays focusable and announces "Not ready, <reason>" (good). Contrast: Create disabled label 6.2:1 (pass), placeholder 4.46:1 (large text, passes 3:1), pill glyphs and chevrons on #1A1D2B high. Container-to-page contrast of pills and disabled button is 1.2 to 1.4:1; fine for inactive pieces and for pills whose text carries the meaning, but it is why the dark screen looks like floating text and one large slab. TalkBack order today: X, field, chips, attach, mic, options, For, Length, Look, Create, status; this is visual order and should stay so, with Create last. Font scaling: Android drops to a scroll mode below 460 dp or at large text under 620 dp; the proposed row needs its own fallback (C.4).
- **Duplicates in code:** `PhotoStrip` exists twice, a 56 dp one in ComposerBar.kt and a 64 dp one in CreateScreen.kt; I could not tell which one renders. If the 56 dp one is dead code, delete it (polish).

---

## C. PROPOSAL: one layout

### C.1 Principle

The page stays what it is (a sentence on a quiet background). The bottom dock becomes **one composer toolbar**: choices above, actions below, Create at the trailing end of the actions. No full-width bar, no caption band, no helper line. The keyboard opens on its own.

### C.2 Wireframe

Keyboard up, empty prompt (Android 384 dp wide; the same on iOS in pt):

```
+--------------------------------------------------+
| 22:07                              status bar     |
|  (X)                                              |  top bar 56 dp, X 48 dp hit, no fill
|                                                   |
|  A video about...|                                |  prompt 24 sp, min 2 lines, caret live
|                                                   |
|  (* How bees make honey) (* 3 focus tips)         |  chips: 40 dp, empty + first video only
|  (* Why forests matter)                           |
|                                                   |
|                  . . . free space . . .           |
|                                                   |
|  [Shorts v] [clock 2 min v] [sparkle Auto v]      |  pills 44 dp visual / 48 hit, wrap to 2 rows
|  (photo+)  (mic)  (sliders)        [ Create  z2 ] |  tool row 48 dp: tools left, Create right
+--------------------------------------------------+
|  keyboard                                         |
+--------------------------------------------------+
```

Typing (text present, Create live):

```
|  How bees make honey, explained for kids|         |  chips gone
|  ...                                              |
|  [Shorts v] [2 min v] [Cartoon v] [Characters fox bear v]   <- 2 rows when cast pill shows
|  (photo+)  (mic)  (sliders)        [ Create  z2 ] |  Create = gradient, glow off, 48 dp
```

With photos attached (strip appears between prompt and dock; badge on the photo icon):

```
|  How bees make honey...                           |
|  [ph][ph][ph][ + ]    3 of 100                    |  64 dp tiles, each remove has 44+ dp hit
|  [Shorts v] [2 min v] [Auto v]                    |
|  (photo+ 3)  (mic)  (sliders)      [ Create  z2 ] |
```

Voice recording:

```
|  How bees make (live transcript, read-only)       |
|  [Shorts v] [2 min v] [Auto v]                    |
|  (photo+)  (STOP)  Listening...    [ Create  z2 ] |  STOP = filled, danger tint; Create tonal until stopped
```

Creating (after the tap; the Create pill grows to the existing live capsule):

```
|  (X is Cancel) prompt dimmed 50%, touches locked  |
|  ( sparkle  Checking your request      (ring) )   |  full-width capsule, 64 dp, replaces the dock
|                 Cancel                            |  text button, keeps its place
```

### C.3 Exact specification for the builder

Order, top to bottom: top bar, prompt, chips (conditional), flexible space, strip (conditional: photos or presentation card), status line (conditional), pills, tool row. Everything from "strip" down is one bottom-docked column above the IME and the navigation bars (`windowInsetsPadding(ime union navigationBars)` as today). Gutter 20 dp (`Vmk.space.screen`). Vertical gaps 8 dp between rows, 12 dp below the tool row.

1. **Top bar:** 56 dp, X on a 48 dp target, glyph 24 dp, no filled disc (keep the existing Close or Cancel label). Unchanged behaviour.
2. **Prompt:** as today (`PromptField`, VmkType.prompt 24 sp, min 52 dp), placeholder `create_prompt_hint` in textSecondary. **New:** on first composition, if text is empty, no photos and no presentation, `delay(450)` then `focus.requestFocus()` and `keyboard.show()`, the same guard as iOS CreateView.swift line 89. This single change removes the 38% void.
3. **Chips:** unchanged component. Visible only while text is empty, nothing attached, not listening, not locked (as `showExamples`). New: also hidden once the account has any video; two chips instead of three when `maxHeight < 520 dp`.
4. **Pills:** same three pills and the conditional Characters pill, same menus and sheets. New: 16 dp leading glyph on each of For (aspect shape of the chosen format), Length (clock), Look (sparkle); keep the chevron at 16 dp; visual height 44 dp inside a 48 dp hit area. `PillRows` keeps its two-row fallbacks. Add a hard rule in the code comment: no fifth pill.
5. **Tool row (48 dp):** left cluster, 4 dp apart, each a 48 dp target with the 44 dp disc: Attach (photo-plus, badge with count, same three-source menu), Mic (becomes Stop while listening), **Options** (sliders; moved here, label "Options"). Right: **Create pill**, height 48 dp, minimum width 112 dp, 20 dp horizontal padding, shape full pill. Content: label `create_create_video` in VmkType.cta, then 16 dp bolt and the price, 6 dp apart, so verb and price form one unit. Active: action gradient and the existing glow reduced to the small shadow. Inactive: opaque `surface3` fill, `textSecondary` content (6.2:1), no glow, stays focusable and tappable (tap shakes and shows the status line, as now). Accessibility: contentDescription "Create", stateDescription "Ready, costs 2 credits" or "Not ready, <reason>".
6. **Status line:** the existing `StatusLine`, unchanged, but shown only when `status.kind` is not Ready/Idle (too short after a tap, too long, not affordable, over max, photo hint) and as a transient after a tap on the inactive Create. No persistent helper, no persistent balance caption. Until the account's first video exists, add one caption row under the tool row: "2 credits. You have 11." (the balance); afterwards the balance lives in the header credit chip and in the Credits screen, and appears here only when low or insufficient.
7. **Attachments:** photos or a presentation card appear between the chips area and the status line, as today (64 dp tiles, remove targets at least 44 dp). The attach icon keeps the count badge. While a presentation is attached the attach icon is replaced by nothing, as today.
8. **Voice recording:** mic turns into a filled Stop; "Listening…" appears in the middle of the tool row (it already exists, CreateScreen.kt line 299); Attach and Options disabled; Create inactive until stop; prompt read-only and shows the transcript.
9. **Creating:** unchanged state machine (`CreateCapsule`). The Create pill's bounds animate (spring) into the full-width capsule; the whole dock is replaced, Cancel keeps its place. Reduced motion: cross-fade.
10. **Large text and small windows:** at font scale 1.5 or more, or when the tool row cannot fit three icons plus the pill (about 160 dp plus the pill's width), the Create pill moves to its own row, full width, 52 dp, below the tool row (this is today's layout, used only as the fallback). Keep the `compact` scroll mode for very short windows.
11. **Options sheet:** remove the For chips and Look swatches (they are pills now); keep Quality, Subtitles, Language, Format, Watermark, Scenes, Background.
12. **Platforms:** iOS: identical structure (`bottomBar` in CreateView.swift lines 419 to 451: move `createButton` into the icon HStack, `Spacer` then the pill; remove `caption(s)` except the first-video line); keep its accessibility1 cap on the dock. Web: desktop already matches; on 390 px width use the same two-row dock inside the card, Create in the tool row.

### C.4 Reasoning tied to the benchmark

- Attach and mic leading, in the field's own container: matches Gemini, ChatGPT, Claude (#4, #7, #8).
- Create at the trailing end of the input row, a compact labelled pill: matches where every composer puts send (#4 #5 #8), but keeps the label and the price because our action spends credits and the video tools all label Generate/Create (A.4 point 5). It is a deliberate hybrid, not a chat clone.
- Mic kept away from Create: NN/g's Perplexity example (#1) and a credit-cost mis-tap argument.
- One options icon plus three value pills: the video tools show one settings affordance or two to four pickers (A.4 point 4); we stay at the low end.
- Cost beside the verb, explained once: Flow ties cost to the settings and the button (#9).
- Apple HIG (#2): one prominent button, style not size, activity indicator in place of the label while waiting: the capsule transition is exactly that.
- Web desktop already ships this arrangement; the change makes the three platforms agree.

### C.5 Expected effect on the common paths

Taps counted after the screen is open; "keyboard" means an extra tap today on Android only.

| Path | Today (Android) | Proposed | Note |
|---|---|---|---|
| Type a prompt and create | tap field (1), type, tap Create (2) = **2 taps** | type, tap Create = **1 tap** | Autofocus. iOS and web already do this. Create is also nearer the keyboard (about 12 dp above it, against about 40 dp). |
| Example chip | chip (1), Create (2) | same | unchanged |
| Add a photo | attach (1), source (2), pick | same | unchanged; no gain, no loss |
| Dictate | mic (1), speak, stop (2), Create (3) | same | unchanged |
| Change length | pill (1), row (2) | same | unchanged; cost shown in the menu rows |
| Choose a look | pill (1), tile (2), Done (3) | same | unchanged |
| Open Options (4K, language) | sliders (1) | sliders (1) | now next to the other tools |

Honest summary: **taps do not drop except for the autofocus**. The gains are vertical space (the dock goes from about 220 dp to about 124 dp, or about 172 dp with a second pill row; the sentence area with the keyboard open goes from about 160 dp to about 260 dp), shorter travel between the field's tools and Create, and a calmer first state. The words on the empty surface drop from about 22 to about 19 including the chips.

### C.6 What we lose

- The loud, unmistakable full-width primary. A compact pill is easier to miss for a first-time user; mitigations: gradient only when active, bolt and price, last element in reading order. I judge this acceptable because nothing else on the screen competes with it.
- The persistent "Describe your video" and "N left" reassurance: replaced by transient status and a first-video caption.
- A big forgiving target for the one action that spends credits: Create falls from 336x56 dp to about 112x48 dp (still above the 44 pt and 48 dp minimums). The mis-tap risk is lowered by keeping mic and Create apart.
- Left-handed reach to a trailing-edge button (the same trade chat apps make).
- Build cost: roughly a day per platform plus screenshots in light, dark, Spanish, 200% font, since three platforms and the UX budget test (`UxBudgetTest`, `VideoMKBudgetUITests`) all assert on this surface. Existing test tags (`sendButton`, `photoButton`, `micButton`, `optionsMenu`, `pillFor`, `pillLength`, `pillLook`, `pillCast`) can stay.

### C.7 If the owner keeps the full-width bar: minimum fixes

1. Android autofocus (above).
2. Delete the helper line; show the balance only on the first video and when low.
3. Merge the sliders icon into the left cluster of the icon row (or into the pills row end).
4. Bring the price next to the verb: left-align label and price together ("Create bolt 2"), not label left and price right.
5. Leading glyphs on pills.
6. Reduce the bar to 52 dp and remove the glow in the inactive state.

With those six it is "acceptable". It would still be the one composer in the benchmark with a full-width send.

---

## D. Ranked findings

**Must fix**

1. Android does not focus the prompt on open (only from Media's "Make a video": Root.kt line 255); iOS and web do. Result: no caret, no keyboard, 38% void, the screen reads as a form. Change: `LaunchedEffect(Unit)` in CreateScreen.kt that, when text is empty and nothing is attached, waits 450 ms then calls `focus.requestFocus()` and `keyboard?.show()`.

**Should fix**

2. Rebuild the dock as in C.3 (Create compact pill in the tool row; one row of tools plus one row of pills; no caption band).
3. Delete the persistent helper line "Describe your video" (redundant with the placeholder and the inactive button; it displaces the balance caption).
4. Move the sliders icon into the left tool cluster, rename its label "Options", remove the For and Look duplicates from its sheet.
5. Keep verb and price together on Create; teach "bolt 2" once with "2 credits, you have 11" until the first video.
6. Add 16 dp leading glyphs to the three pills (our own spec asked for them; "Auto" alone is ambiguous).
7. Example chips: hide after the first video; show two when the window is short.

**Polish**

8. X without the filled disc (or keep the disc on all three platforms; only decide once).
9. Placeholder in textSecondary (4.46:1 now, passes only as large text).
10. Cross-platform parity: autofocus (done by 1), glyphs on the apps' pills like web mobile, defaults per platform (check whether Shorts/YouTube/Video are saved preferences or true defaults), dock cap at large text on Android as on iOS.
11. Delete the duplicate 56 dp `PhotoStrip` in ComposerBar.kt if it is dead code.
12. Say "credits" in words in the Create stateDescription and the Length menu footer.

---

## E. What I could not verify

- **No live look at any other app.** Every benchmark detail comes from text on web pages, not from screenshots or the apps themselves. Gemini (3 articles), ChatGPT (1 article, May 2025) and Claude (1 third-party teardown) are the best covered; the video tools are mostly third-party summaries.
- **Midjourney, Runway, Luma, Pika, CapCut:** only search-result summaries; Midjourney docs returned 403, Luma help 404, the Tom's Guide Runway article was truncated.
- **Sora:** the claim that the apps were discontinued on 26 April 2026 is from one search summary; unconfirmed. Its UI is historical in any case.
- **Descript and Canva:** not verified at all.
- **Material 3 official guidance:** m3.material.io pages did not render for my fetch; I could not quote the FAB or one-primary-action rules or sizes. The 48 dp target is from memory.
- **Apple HIG thumb-reach or bottom-bar guidance:** the pages I read do not address it; the thumb-zone points rest on Hoober-based summaries.
- **Whether the credit price is better understood as a bolt:** no usability data; my claim is a judgement.
- **Pill glyph widths:** I estimated that three glyph pills still fit one row at 384 dp but did not measure; `PillRows` wraps safely if not.
- **The Android screenshot has no keyboard, and the code has no auto-focus.** I read the code for every `requestFocus` call; if something outside `ui/` focuses the field, my must-fix would be wrong. Nothing was run.
- **Defaults differing per platform** (Shorts 2 min on Android, YouTube 1 min on iOS, Video 1 min on web) may come from saved preferences in the screenshots.
