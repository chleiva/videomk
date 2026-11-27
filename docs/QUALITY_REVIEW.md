# Video quality and engagement review (2026-11-26)

Scope: what the QA account really produced (26 of the last completed videos, 15 s to 12 min, 16:9 / 9:16 / 1:1 / 4:5, EN and ES), research on retention, an engagement brief for the director, and a measured A/B. Raw material: frames and contact sheets in the session scratchpad (`quality_review/`, not committed); A/B runs in `docs/audit/2026-11-26-engagement/` (`before`, `after`, `after2`, `s46_0`, `s46_1`, tables `ab_*.txt`). Model spend: about USD 7.7 of the 15 cap (before 1.81, after 2.03, after2 3.11 in two passes, Sonnet 4.6 pair 0.79).

Honesty: n = 10-12 prompts, one run each, a harsh and noisy judge (0.1-0.3 differences are noise). The deterministic metrics are firmer. The video ratings below are my reading of contact sheets, not viewer data; there is no retention analytics in the app.

## 1. What we produce (measured, 17 of 26 videos fully measured by ffmpeg)
- Loudness is consistent: -13.6 to -14.2 LUFS everywhere. Narration pace 118-146 words per minute (the research rule of thumb for explainers is about 150, opinion). No silence gaps over 0.7 s except one.
- One scene per beat, and a beat is about 13-15 s (60 s videos have only 4-5 beats; 12 min videos have 54-56). Motion share (frames that change) is 18-41 %. Longest fully still stretch 11.4 s (1:1 video 071dc642, stat ring), 14.8 s (590e7696, 12 min), 9.2 s (67bc8a53).
- Scene variety is good (max same-type run 1-3, 4-16 types), but in 60 s videos only 2-4 types exist.
- Hook: 20 % of A/B baseline plans open on a title card; in the QA videos the first 6-12 s are a title card with a subtitle in 7 of the 12 videos I read (f328a527 0-10 s, 10059fa6 0-10 s, 0f277b25 0-10 s, c75bf27d 0-8 s, 4386a78e 0-8 s, b7bc3144 0-6 s).

## 2. Critique by element (rating 1-10, evidence)
| Element | Rating | Evidence |
|---|---|---|
| Hook | 5 | Strong lines ("A tree can weigh tons, yet it never eats a meal", 4386a78e) but shown over a static title card; 15 s octopus video (b7bc3144) opens with text only, no octopus picture, and the caption repeats the title; business videos (10059fa6 and 4 siblings) open "Want a video about your business?" over a title card |
| Narration script | 6 | specific when notes exist (flats 59b09cd3: GBP 465,000 vs 504,000, instantly concrete); vague prompts give generic overviews ("Make a video about my business": five near-identical 60 s videos); agenda announcement at 1:18 of 59b09cd3 ("What we will cover") |
| Pacing and rhythm | 6 | 13 s average beat; long static holds (above); reveals follow the voice, which is good |
| Scene variety | 7 | good mix; overused: title cards and bullets/steps for stories (fox story 0f277b25 "How to fish" bullets), definition card ("Hominino", 590e7696 1:18), equation card in a property promo (59b09cd3 1:48, numbers without separators, 0.077 instead of 7.7 %) |
| Typography and layout | 7 | clean, big on 9:16; chart axis and category text only 24-28 px (smallest text in landscape); empty ghost slots on steps/bullets in 9:16 fill 60 % of the frame for 8-14 s (f328a527 0:10-0:24, 0f277b25 0:26-0:44) |
| Colour/theme | 8 | coherent per video; midnight and sunrise purple/orange repeated across most videos (sameness) |
| Captions | 7 | karaoke with highlight, readable; 9:16 caption box bottom was 250 px from the edge, inside the area guides say TikTok/Reels overlay (vendor figures 320-420 px, disagree); caption duplicates on-screen text in short videos (b7bc3144) |
| Transitions | 7 | crossfades fine; no motion between same-type scenes |
| Photos and clips | 6 | clip relevance is the weak point: 12 min es video on human evolution opens with a cheetah clip (590e7696 0-12 s); user photos (13fb8e83) held 12-14 s each with a static look and no title; clip work is owned elsewhere |
| Music and sound | 8 | level and ducking consistent; no effects by decision |
| Narration voice | 7 | clear, even pace, 118-146 wpm slightly slow; prosody not assessed beyond rate |
| Ending / CTA | 6 | takeaway cards fine ("Be patient, keep trying", c75bf27d); none generic "thanks for watching" in the sample |
| Vertical / square | 6 | big type works; empty-slot lists and tiny chart text; 1:1 stat ring holds 12 s (071dc642) |
| Minute 1 of long video | 5 | 590e7696 at 0:54-2:00: cards, timeline with tiny text, definition card, map, title card: informative but low motion, nothing opens a loop |

## 3. Ten findings
1. Openings are title cards in most videos; the hook sentence is good, the picture is not. 2. One scene per 13-15 s beat caps visual change. 3. Vague prompts yield generic videos. 4. No scene-type bursts but too many static holds (11-15 s). 5. Empty ghost slots dominate vertical frames. 6. Chart text small; charts show empty axes until the voice names the first bar (17f4b4bb 0:10-0:16). 7. Clip relevance (cheetah in a human-evolution video). 8. Definition and agenda cards read like a textbook. 9. Equation card style dated and misformatted in a promo. 10. Captions duplicate title text in 15-45 s videos and sat close to the platform UI zone in 9:16.

## 4. Research (accessed 2026-11-26; search quality was poor, most sources are vendor blogs: opinion)
- Hook: payoff or surprising claim in the first 3 s, no greetings ([vidIQ](https://vidiq.com/blog/post/youtube-video-intros/), opinion; [TikTok/CreatorIQ via Marketing Brew](https://www.marketingbrew.com/stories/2023/12/18/pay-attention-to-me-report-shares-brand-tips-for-catching-users-interest-on-tiktok), platform report about ads).
- Cadence: no verified per-channel data; guides argue for varied, content-driven holds, not a metronome ([Emergency Creative](https://emergencycreative.squarespace.com/blog/why-i-refuse-to-cut-every-4-seconds-the-case-for-slow-and-intentional-editing), opinion). Guo, Kim and Rubin 2014, 6.9 M edX sessions: shorter videos and drawn-as-you-go / informal beat static slide screencasts ([abstract](https://pg.ucsd.edu/publications/edX-MOOC-video-production-and-engagement_LAS-2014.txt), data, MOOC context).
- Open loops: information-gap theory ([HubSpot](https://blog.hubspot.com/marketing/psychology-hacks-for-making-engaging-videos), [Descript](https://www.descript.com/blog/article/the-youtubers-guide-to-the-curiosity-gap-how-to-keep-your-audiences-interest), opinion). No evidence found for concrete-vs-abstract effects or rule-of-three.
- Pace: 130-150 wpm tutorials/documentary, up to 165-170 energetic shorts ([Syllaby](https://syllaby.io/blog/voiceover-pacing-silence-trimming-retention-editing/), opinion).
- Captions: word-highlight lifts of 18-34 % are vendor claims without controls ([dev.to](https://dev.to/clamper_ai/how-ai-caption-styles-affect-watch-time-and-engagement-409i), [Opus](https://www.opus.pro/blog/best-caption-presets-styles-boost-retention)); 9:16 safe zones disagree between vendors ([Ignite](https://www.ignitesocialmedia.com/content-creation/what-are-the-safe-zones-for-tiktoks-and-instagram-reels/), [Remotion](https://www.remotion.dev/elements/overlays/social-safe-zones/)).
- Mayer: coherence 18 of 19 experiments positive, signaling 26 of 28, redundancy small effect ([UNH summary](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-research-based-principles-for-designing-multimedia-instruction-mayer.pdf), data, lab learning).
- Competitors: reviews of Pictory/InVideo report generic or repeated stock visuals and a "slideshow" feel ([Trustpilot InVideo](https://uk.trustpilot.com/review/ai.invideo.io?page=4), [fast.io Pictory](https://fast.io/resources/pictory-ai-review-2026/), opinion). No source measures the share of clips vs stills; the owner's observation (competitor used more clips) is not contradicted or confirmed.
Earlier research is in `docs/DIRECTOR_CRAFT.md`.

## 5. Engagement rubric (for instructing and judging)
1. Hook: a concrete surprise or open question in beat 1 (under 2 s for shorts, under 8 s mid, cold open for 4 min+), never greeting or "in this video". 2. First picture shows the subject or a big number, not a title card. 3. One through-line promise; every beat advances it. 4. One open loop early, paid off later; long videos reopen every 60-90 s. 5. A concrete thing (number, name, example) per beat, from the notes only. 6. A visual change at least every 4 s (short) / 8 s; no scene type more than twice in a row. 7. On-screen text is key words only; no definition cards as openers; first item named in the beat's first sentence. 8. Short active sentences, mixed length, no cliches. 9. Captions large and clear of platform UI; music under voice, no sound effects. 10. Ending pays off the hook and ends on one repeatable line; CTA only if requested.

## 6. What changed
- New `backend/lambdas/engine/engagement.py` (the brief, about 2,000 characters, hook rule by length, vague-prompt rule, banned-cliche list EN/ES). Connected by one edit in `engine/director.py` (appended to `craft`, so it reaches single-pass and staged videos); skipped for videos made of the person's photos. Flag `ENGAGEMENT_PROMPT` (default ON; set 0 to disable). Tests `tests/test_engagement.py`. `plan.py`, `clips.py`, `beat_handler.py` untouched.
- `engine/frame.py`: 9:16 caption box bottom 1670 to 1600 (320 px clearance) and content bottom 1450 to 1385.
- `scenes/viz_scenes.py`: landscape chart text scale 1.0 to 1.15 (same as portrait).
- `scripts/engagement_ab.py`: deterministic metrics and judge means for two audit folders.

## 7. A/B (same 12 prompts, QA, Sonnet 5.5 writer, judge Sonnet 5.5)
`before` = flag off. `after` = flag on (first wording, 12 prompts). `after2` = final wording (with a "first item fast" line), 10 prompts completed in both.
| metric | before (n=12) | after | before (n=10) | after2 |
|---|---|---|---|---|
| plans opening on a title card | 17 % | 0 % | 20 % | 0 % |
| definition-card openers per plan | 0.83 | 0.50 | 0.90 | 0.50 |
| judge structure | 3.42 | 3.67 | 3.50 | 3.80 |
| judge hook/ending | 3.33 | 3.75 | 3.40 | 3.50 |
| judge visuals | 3.33 | 3.67 | 3.40 | 3.60 |
| judge accuracy | 3.25 | 3.50 | 3.30 | 3.30 |
| judge coverage | 2.75 | 3.08 | 2.80 | 2.70 |
| judge originality | 2.75 | 2.75 | 2.80 | 2.70 |
| judge language / tone | 4.08 / 3.83 | 4.08 / 3.92 | 4.10 / 3.90 | 4.20 / 3.90 |
| cost per plan USD | 0.122 | 0.141 (+15 %) | 0.133 | 0.141 (+6 %) |
| plan seconds | 40.4 | 43.9 | 44.6 | 45.7 |
No regression in accuracy, language or instruction following. Gains are small and directionally consistent (structure, hook, visuals); coverage and originality do not move (they depend on research, not the prompt). Cost: the brief itself adds about 600 input tokens per call (about +2-4 %); the observed +6 to +15 % comes mostly from run-to-run differences in retries and grounding rewrites (big-model calls 2.25 vs 2.42 per plan). Sonnet 4.6 (global profile): only 2 prompts completed per arm in a USD 0.79 smoke test, with no title-card or cliche regression and the same cost; not enough to conclude. Default: ON, because deterministic effects are clean and there is no accuracy regression, but the cost delta is at the edge of the +10 % allowance: the owner may flip `ENGAGEMENT_PROMPT=0`.

## 8. Backlog (effort / impact)
1. Beat length: lower the 14 s per beat target (`plan.expected_beats`) to about 10 s so visual change doubles (S / high; needs plan.py, held back for the concurrent builder; costs more TTS and scenes). 2. Opening visual rule enforced in code: if beat 1 is a title card, swap it for the first image/stat/clip (S / high). 3. Replace ghost slots with only revealed items centered in 9:16 lists (M / medium). 4. Clip relevance check for the opening clip (cheetah case) (owned by clip work). 5. Chart: start with the first bar visible (cap first cue at 1.2 s) (S / medium). 6. Pacing from narration word timing: lengthen or shorten holds to the voice (M / high). 7. Word-by-word emphasis in the voice and a faster 150-160 wpm option for shorts (M / medium). 8. New scene families: big-number + photo split, before/after, map route animation (L / high). 9. Auto-chapters and thumbnail (M / medium). 10. Music swells at section changes following docs/MUSIC.md (M / low).

## 9. Decisions for the owner
Keep `ENGAGEMENT_PROMPT` default ON? Allow the plan.py beat-length change? Confirm the 9:16 caption position against a real TikTok/Reels preview (sources disagree 320-420 px). Retention analytics would end the guessing.

## 10. Backlog items done (2026-11-27, R045; tests `backend/tests/test_quality_backlog.py`)
| Backlog | What changed | Where |
|---|---|---|
| 1. Beat length 14 s to 10 s | `plan.BEAT_S = 10`: a minute is 6 beats (was 4), 3 minutes 18 (13), 12 minutes 72 (51; the cap is 90); about 21 words a beat. Videos of the person's own photos keep 14 s (`PHOTO_BEAT_S`); 15 to 45 s were already 10 s. | `engine/plan.py expected_beats` |
| 2. Beat 1 is not a title card | The scene list no longer offers the title card for the opening, and the director replaces one that still arrives (also a first scene that was invalid and fell back to a card): a photograph of the subject (search words from the card's own title) when the photo budget has room, else the card's line as moving words. Narration, captions and timing are untouched. Only for a new video: never on an edit, never for photo videos; off with `QUALITY_FIXES=0`. Recorded in `research.opening`. | `plan.enforce_opening`, `director.direct` |
| 5. Chart first cue | The first bar or point is up by 1.2 s (`CHART_FIRST_CUE_S`) even when the voice names it later; the other values keep their moments. | `scenes/viz_scenes.chart_times` |
| 3. Ghost slots | In 9:16, 1:1 and 4:5 the cards and icons list styles and the diagrams no longer draw empty slots and faint tracks before the voice reaches an item: the list grows in place. Landscape is unchanged (the structure reads well there). Items are not re-centred as they appear (they would have to move): they appear in their final places. | `scenes/list_scenes.py`, `scenes/flow_scenes.py` |
| Icon picker no-match | An item whose words name no icon used to get a rotating decoration (sparkles, target, lightbulb ...). Now: when most items of the list or diagram have a real icon the others get a plain marker (`circle-dot`); when fewer than half do (most Spanish lists, abstract steps) the whole list is numbered 1, 2, 3. The 16:9 reference pictures of 8 samples changed for this (fixture regenerated for those only). | `scenes/style_kit.py icon_for / group_icon`, `flow_scenes.icon_for_node` |
| also | A stat whose value is a year or a decade ("1970s") is shown as written instead of counting up to it (seen on QA: "1912s" on the way). | `scenes/text_scenes.is_calendar_year` |

**Audit before/after (cheap re-run: 6 of the A/B prompts, plan stage only, QA, USD 1.01; `docs/audit/2026-11-27-beats10/`, before = the same prompts in `2026-11-26-engagement/after2`).** n = 6, one run each: differences of 0.1 to 0.3 in judge scores are noise.
| metric | before | after |
|---|---|---|
| beats per plan | 10.5 | 14.0 |
| words per beat | 28.1 | 21.2 |
| scene types per plan | 7.5 | 8.3 |
| plans opening on a title card | 0 % | 0 % (the backstop did not have to act) |
| judge overall (mean of the per-plan means) | 3.37 | 3.44 |
| judge accuracy / coverage / originality | 3.17 / 2.50 / 2.50 | 3.50 / 2.67 / 2.83 |
| judge structure / visuals / tone / language | 3.67 / 3.67 / 4.00 / 4.17 | 3.67 / 3.67 / 4.00 / 4.17 |
| judge hook and ending | 3.50 | 3.17 |
| cost per plan USD | 0.118 | 0.142 (+20 %) |
| plan seconds | 40.4 | 47.6 |
Reading: the visual change rate went up by a third as intended and nothing regressed beyond noise; the judge does not see pictures, so it cannot reward it. The plan costs about 2 cents more (more scenes to write), and each extra beat is one more voice call and one more stock lookup at generation. Rollback: `plan.BEAT_S = 14`.

## 11. Length: at least what was asked, at most about 5 percent more (2026-11-27; `engine/length.py`, tests `backend/tests/test_length_fit.py`)
**Measured before (97 first renders on QA with a recorded target, requested against actual):** nothing was ever short (the timeline already holds scenes longer to reach the length), but 20 of 97 ran more than 5 percent long: 60 s videos worst (10 of 22 over; up to +23 percent; the 69 s video), 15 to 45 s up to +27 percent (38 s for 30), 1 to 3 minutes up to +22 percent, above 3 minutes never more than +1.4 percent.
**Where the overshoot comes from:**
1. The writer does not keep the word count: 150 to 170 words against 130 asked for a minute, also after being sent back once (the repair accepts whatever returns). Extra beats add to it (7 or 8 beats where 6 were asked; every beat carries 0.95 s of silence).
2. Words predict speech badly: the same voice ran from 2.2 to 3.2 words a second from video to video (numbers, long words, commas). The budget assumes 2.4; the real median is 2.63 (Amy 2.67, Ruth 2.63, Lucia 2.84), which is why most videos come out a little short and are held to the length, and why the long ones are the scripts that are both wordy and slow.
3. Pauses, intro and outro and rounding are not the cause: 0.95 s a beat and 1.4 s at the end are in the budget already, and the hold step aims 0.4 to 1 s past the length.
**What changed (deterministic, no model call):**
1. *Before the voice* (`length.fit_script`, in the director): the speaking time is estimated from the text with rates fitted per voice on 1,757 beats of 174 QA videos (seconds per character, per punctuation mark and per digit; error per video: mean +0.4 percent, standard deviation 3.5 percent, worst -11 and +10 percent). A script estimated more than 3 percent past the length loses whole sentences until it is as near the length as a sentence allows: never the opening line or the last line, never leaving a beat under 6 words, middle beats and middle sentences first. If no sentence can go and there are more beats than the length has room for, a whole middle beat goes (never a pause, a dialogue line or a photo beat). Recorded in `research.length` and as a plan warning.
2. *With the measured audio* (`length.tighten`, in the timeline, first render only): a video still more than 3 percent long gives up silence around each spoken beat, evenly, from 0.40 + 0.55 s down to no less than 0.22 + 0.25 s. The pace is stored in `plan["pace"]` so edits keep it.
3. *Too short:* unchanged (`timeline.stretch_to`).
Switch: `FIT_TO_TARGET=0` on the engine functions turns 1 and 2 off. The writer's word budget and prompts are unchanged.
**Replay on the 96 historical plans (real audio lengths; a cut beat's audio scaled by its estimate):** inside [asked, asked + 5 percent]: 77 of 96 before, 94 of 96 after; none short. The two left are a 60 s video at +8.8 percent and a 3 minute photo video at +6.6 percent (the voice ran 10 percent slower than estimated: the tail the pauses cannot cover). 30 of 96 scripts would have been cut (62 sentences in all, 29 of them in 6 long Spanish photo videos), 13 would have had their pauses shortened.
**Two real QA videos after the deploy:** English, 60 s asked: the writer delivered 170 words (estimated 72 s), 2 sentences (32 words) were cut, the video is **61.0 s** (+1.7 percent; speech estimate off by +2.9 percent). Spanish, 30 s asked, 9:16: 71 words against 58 asked but estimated 30.1 s (Lucia speaks fast), nothing cut, the video is **30.4 s** (+1.3 percent). Neither needed its pauses shortened.
**Limits, said plainly:** a cut sentence is chosen by arithmetic, not by meaning (the opening and the ending are protected, nothing else); the replay is on the same videos the rates were fitted on, so 94 of 96 is optimistic; voices other than Amy, Ruth, Lucia and Lupe use a per-language average; a video whose voice runs more than about 9 percent slower than estimated still ends up over; long holds on scripts that are far too short (seen: 40 s of padding on a 3 minute photo video) are the opposite problem and were not touched.
