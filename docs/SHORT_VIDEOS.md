# Short videos (15, 30, 45 seconds)

`target_minutes` runs from 0.25 to 12 (API Gateway schema, `sf_launcher.validate_options`, plan handler). Credits are unchanged: started minutes, minimum 1 (15 to 60 s = 1 credit, 61 s = 2).

Under a minute (`plan.is_short`):
* Budgets (`plan.expected_beats` / `expected_words`): one beat per about 10 s (2, 3, 4 beats), the final fade (1.4 s) is subtracted, and the word count is calibrated by 0.94 because the writer lands 8 to 10 percent over any stated count (measured on QA). 15 s is 26 words, 30 s 58, 45 s 89. A minute and above is unchanged.
* The director gets a SHORT-FORM block (`plan.short_form_block`, through `frame_prompt(options, minutes)`): hook in the first 2 seconds, one idea, no preamble, a call to action only if the request has one, at most 2 to 3 simple scenes, big text, no pauses. The user message states the length in seconds and asks for 0.90 to 1.00 of the words.
* Repair loops: too short below 0.88 of the target, too long above 1.08 (long videos: 0.93 and 1.12), once, with exact word counts per beat. Photo videos also get the "too long" repair when short.
* Research: only time-sensitive requests use the web agent (budget 2 searches, 1 page, 30 s); thin encyclopedia notes never escalate; notes are capped at 2,500 characters. The staged writer starts at 4 minutes.
* Photo videos: music-only opening and ending are 1.0 s and 1.5 s (6 s from one minute); no extra non-photo scenes. Capacity (`curate.max_used`, 1 s per photo at 85 percent of the time) is unchanged: 15 s fits 12 photos, 30 s 25, 45 s 38.
* Timeline: the stretch margin is 0.4 s under a minute (1 s otherwise).

Measured on QA with the real director (12 prompts, English and Spanish): see the hand-off report; est. total video time was within about 8 percent of the target for all but one photo run.
