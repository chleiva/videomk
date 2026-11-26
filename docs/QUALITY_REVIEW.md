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
