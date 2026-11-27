# Create screen redesign: the brief (owner approved 2026-11-27)

The owner read the independent review (`CREATE_SCREEN_REVIEW_2026-11-27.md`, same folder) and said: "following the designer recommendation, please go ahead and redesign and rebuild in the 3 platforms this particular screen."

So build the review's RECOMMENDED LAYOUT (section C) on iPhone, Android and web, the same on all three:

1. Top bar (X), prompt field with the keyboard OPEN on arrival on every platform (Android currently never focuses it: must fix), example chips only while the field is empty and the account has no finished video yet (two instead of three on short screens).
2. Dock: ONE row of pills (format, length, look, and the Characters pill only when the look has a cast: never a sixth control; extras go to Options), with a small leading glyph on each pill; then ONE tool row: photo-plus, mic and "Options" (the sliders icon, with its label) on the left, a compact labelled Create pill at the trailing end: height 48, min width 112, label + bolt + credit cost as one unit. The persistent helper line "Describe your video" is deleted. Dock height about 124 dp/pt (about 172 with two pill rows).
3. The Options sheet no longer repeats format and look (they are pills); it keeps quality/4K, subtitles, language, watermark, scenes/background and the rest.
4. Create states: inactive (opaque surface fill, secondary label, no glow, still tappable: a tap explains what is missing), active (gradient), creating (springs into the existing full-width live capsule; reduced motion = cross-fade). Teach the credit cost once with a first-video caption ("2 credits. You have 11."); say "credits" in words in the accessibility state description.
5. Voice recording: mic becomes a filled Stop, "Listening..." in the middle of the tool row, attach/Options disabled, Create inactive until stop.
6. Large text (iOS accessibility sizes, Android font scale >= 1.5, web zoom): Create drops to its own full-width 52 dp row (today's layout as the fallback). Keep mic on the LEFT (a mis-tap next to Create would spend credits). Do not swap mic to send.
7. Keep: accessibility ids/test tags, touch targets (44 pt iOS, 48 dp Android), contrast (inactive Create label at least 4.5:1), light/dark, English/Spanish, small phones. The balance caption shows only before the first video and when low (the balance is in the header chip otherwise).

Quality bar: minimalist and perfect. Prove every state with screenshots (light, dark, Spanish, largest text, small phone) in `~/Downloads/videomk-looks/review-create-v2/<platform>/` with an `index.md`; LOOK at each; write `FINDINGS_STATUS.md` listing every review finding id and item above as done / partly / not done. Re-run the budget tests that assert on this surface (`UxBudgetTest` on Android, `VideoMKBudgetUITests` on iOS) and update them to the new, smaller budget.
