# Long videos are written in stages (2026-11-24)

**The bug:** "All about Paris" asked for 5 minutes (5 credits charged) and came out 2:30: the planner wrote 326 words in 15 beats when 5 minutes needs about 670 in 21+. Nothing compared the script with the length asked for, and one 8,000-token call (thinking included) is also near the limit for a long plan.

**Fixes (all videos):** the prompt states the length as a hard requirement with numbers (words = (seconds - beats x 0.95) x 2.4, the speaking rate measured on real videos); a script under 85 % of its words gets up to two repairs with its own numbers before it is accepted (with a `length:` warning if it stays short); the output limit scales with the length (6,000 + 2,600 tokens per minute, max 32,000) and a cut-off is logged.

**Long videos (4 minutes and up, no user photos) are built the way Plorer builds long articles** (`engine/staged.py`, `STAGED_PLANS=off` disables):
1. **Outline** (one call): title, description, mood, theme, voice, music, and 3-8 sections of about 1.5 minutes (title, goal, key points, research queries, minutes adding up to the length asked, optional music change).
2. **Sections** (one call each, in parallel): each runs its **own research pass** (the web agent with the section's queries when a search provider is configured, else the encyclopedia), is told the whole outline so it does not repeat the others, whether it opens, continues or closes the video, and its own word and beat budget; each is checked on its own length and on whether its list items are spoken, and repaired once.
3. **Assembly**: beats joined in order, each section's first beat becomes a chapter, then the usual validation once (voices, image budget, pauses, sfx, music; a section that chose different music becomes a change at its first beat). The plan Lambda has 10 minutes.
Measured on QA: "All about Paris", 5 minutes: 5:00 exactly, 24 beats, 729 words, 3 chapters, 11 sources, $0.42 (script $0.20, speech $0.12, research $0.09, reviews $0.005).
Not done: generating sections for videos built around the user's own photos (they keep the single call), a per-section image budget beyond the global one, resuming a failed section without redoing the others.
