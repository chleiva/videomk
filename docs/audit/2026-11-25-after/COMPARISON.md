# Before and after the quality fixes (2026-11-25)

What this compares: the 40 prompts of `docs/audit/prompts.json`, one run each, on QA, with the same harness, the same judge (Claude Sonnet 5.5, strict anchors) and the same rules.
**Before** = `docs/audit/2026-11-25/` (original code). **After** = `docs/audit/2026-11-25-after/` (code with fixes 1 to 7, `QUALITY_FIXES` on). Spend of the re-run: **$7.96** (plan stage $6.78 + judge $1.10 + search); plus $0.16 of smoke tests and **$1.17** for the second, partial re-run described in section 3: **$9.29 of the $10 budget**. Tables regenerate with `python backend/scripts/audit_compare.py docs/audit/2026-11-25 docs/audit/2026-11-25-after`.

Read this first (honesty): one run per prompt, the writer is non-deterministic (the same prompt moved by up to 0.5 judge points between runs in this very exercise) and the judge is harsh and noisy; a difference of about 0.1 in a mean over 40 videos is not a real difference, and per-category means rest on 2-3 videos. The rule metrics (notes length, ungrounded share, length ratio, flags) are deterministic and are the firmer evidence. The full 40-prompt run was made with the code as it stood after fixes 1 to 7; two follow-up adjustments (section 3) were checked only on 8 prompts, because the budget did not allow a second full run.

## 1. Before / after table (40 prompts)

| metric | before | after | verdict |
|---|---|---|---|
| failures (no plan) | 0 | 0 | same (the one staged failure of the audit, `hea-03`, did not recur; not evidence of a fix: 1 in 9 before) |
| notes chars, median | 3,960 | 5,238 | better |
| videos with no notes (0 chars) | 14 | 2 (both fables, where no notes are wanted) | **much better** |
| videos with thin notes (< 1,500 chars) | 16 | 2 | **much better** |
| videos citing no source | 15 | 2 | **much better** |
| sources cited, median | 3 | 4 | better |
| ungrounded numbers/names, mean share (all / en / es) | 20% / 24% / 10% | 5% / 3% / 10% | better (an upper bound; known facts count; Spanish unchanged) |
| judge accuracy defects, all / major | 79 / 25 | 79 / 19 | fewer major ones; the judge's `wrong_facts` list is unchanged (49 vs 51) |
| videos reading "the notes" aloud | 2 | 1 (`mkt-02`: "the work around the notes grows" is the app's own subject, a false positive of the regex) | better |
| judge accuracy, mean (all / es) | 3.15 / 3.33 | 3.21 / 3.09 | flat (es lower, n=11) |
| judge coverage, mean | 2.80 | 2.64 | **worse** (see 2) |
| judge structure / hook_ending / tone / visuals | 3.42 / 3.23 / 3.90 / 3.23 | 3.38 / 3.33 / 3.95 / 3.33 | flat |
| judge originality | 2.48 | 2.56 | flat |
| judge instructions | 3.30 | 3.23 | flat/worse |
| judge language (all / es) | 4.03 / 3.92 | 4.05 / 3.91 | same |
| judge mean of means (all / es) | 3.28 / 3.32 | 3.30 / 3.27 | same within noise |
| est. speech time / target at 1 min (median, max; n=3) | 1.23, 1.44 | 1.03, 1.07 | **better** |
| est. speech time / target at 2 min (median, max; n=11) | 1.18, 1.41 | 1.09, 1.19 | better |
| est. speech time / target, all (median, p90) | 1.10, 1.23 | 1.06, 1.18 | better |
| flag too_long / too_short | 11 / 0 | 5 / 2 | fewer long, two new short (`opi-01` 0.84, `pro-02` 0.89 of the words) |
| videos within +/-7% of the expected words | 14 | 20 | better |
| screen/narration mismatch, looser checker as warned | 9 | 6 | partly the looser check (see 3) |
| screen/narration mismatch, strict (old) rule on the final plans | 18 | 26 | **not improved**: bullets, diagram and timeline 22 -> 28 problems; the rise is galleries (9 -> 24), whose "items" are stock-photo search words |
| videos with a scene rejected as invalid (warning count) | 5 | 3 | better (the one-call repair fixed the scenes of `fin-03` and `his-01`, not `new-03`) |
| web research used (videos) / escalations from thin notes | 8 / - | 10 / 9 | |
| videos with Wikipedia fetch errors logged | not logged | 22 of 40, all HTTP 429 | **new information** (see 4) |
| grounding check: videos with a model call / beats flagged / repaired | - | 10 / 5 / 5 | small effect; one call was probably cut off (see 3) |
| plan cost per video, median / p90 / total | $0.135 / $0.324 / $6.36 | $0.151 / $0.341 / $6.78 | +7% |
| plan latency, median / p90 | 41 s / 68 s | 64 s / 92 s | **worse**, +23 s median (see 4) |
| language wrong, hook greeting, generic close | 0 / 0 / 0 | 0 / 0 / 0 | same |

Judge means by group (videos judged in both runs, n=39): videos that formerly had thin notes (n=16) 3.42 -> 3.31 (coverage 2.94 -> 2.56, structure 3.75 -> 3.38, instructions 3.50 -> 3.19); the others (n=23) 3.18 -> 3.29; 4-5 minutes 3.33 -> 3.49 (accuracy 3.00 -> 3.22); 1-2 minutes 3.25 -> 3.21; 3 minutes 3.28 -> 3.27. Per-video detail: `docs/audit/2026-11-25-after/` (`tables.md`, `runs/`) and the last table of `audit_compare.py`.

## 2. What improved, what did not, what regressed

Improved (deterministic evidence):
* **Research input.** Videos with no notes 14 -> 2, thin notes 16 -> 2, no source 15 -> 2. 9 videos escalated from thin Wikipedia notes to the web agent (all but the 2 fables got 4 to 10 sources for about $0.001 of agent cost plus the searches). Nothing else changed the input as much.
* **Specifics.** The ungrounded share of numbers and names fell from 20% to 5% overall (24% to 3% in English), major accuracy defects 25 -> 19, one fewer script that talks about its notes. This is the combined effect of better notes, the prompt rule and the grounding check; the audit cannot separate them (the check itself flagged only 5 beats in 10 videos, so most of the drop comes from notes and the prompt).
* **Length of short videos.** Estimated speech time / target at 1 minute 1.23 -> 1.03 and at 2 minutes 1.18 -> 1.09, and 20 of 40 videos land within 7% of the words (14 before). The trim repair fired in about a third of the videos.
* Fewer videos with a scene rejected as invalid (5 -> 3; the warning is still counted when the one-call repair then fixes the scene: 2 of the 3 were fixed).

Did not improve:
* **Screen/narration mismatch for lists** (bullets, diagrams, timelines): the strict count is flat (22 -> 28 problems). The prompt rule and the looser check changed the warning count, not the underlying behaviour; the looser check also removed repair attempts. Gallery "mismatches" are an artefact of how stock-photo queries are checked (the renderer does not need the narrator to say them), and there were more galleries in this run.
* **Spanish accuracy** (3.33 -> 3.09, n=11) and **judge means overall** (3.28 -> 3.30): within noise, no evidence of a gain.
* **Latency** (see 4).

Regressed (and what was done):
* **Coverage and instructions of the videos that used to have no notes** (coverage 2.94 -> 2.56). Reading the judge's reasons: for `kid-01`, `hea-01`, `rec-01`, `opi-02` the notes that now exist were a single Wikipedia page, and the writer followed it (half of `kid-01` on shield volcanoes, `hea-01` on prevalence statistics) instead of covering the request, and the grounding rule made it timid about concrete steps. Two adjustments were made after the full run: the rule now says that general explanations and well-known facts need no source and that the notes never narrow the topic, and the beat-count wording changed. Checked on 8 prompts (section 3): coverage back to the old level, judge 3.45 vs 3.31 before and 3.06 in the full run for the same 8. This is one run of 8 videos: encouraging, not proof.
* **Length overshoot of some 3-minute videos** (`cmp-01` 0.93 -> 1.21, `how-02` 1.12 -> 1.35 of the words): the trim retry hardly shortened them because the prompt asked for "at least N beats" and the writer added beats; two scripts came out too short (0.84, 0.89), probably from the writer's variance. Adjusted (beat range N to N+2, a trim message with a per-beat budget and the number of words to cut); on the same prompts the ratios are now 0.99 and 1.05.

## 3. Second, partial re-run with the final code (8 prompts, $1.17)

`docs/audit/2026-11-25-after2/`: `hea-01 kid-01 rec-01 opi-02 cmp-01 how-02 mkt-01 bio-03` (the formerly-thin videos that dropped and the length outliers).

| | before | after (full run) | after2 (final code) |
|---|---|---|---|
| judge mean (8 videos) | 3.31 | 3.06 (one judge failure excluded in the 8-video mean) | 3.45 |
| mean words / expected | 1.15 | 1.12 | 1.05 |
| per-video judge (cmp-01, hea-01, how-02, bio-03, mkt-01, rec-01, kid-01, opi-02) | 3.00 3.67 3.22 2.89 3.67 3.22 3.56 3.22 | 3.00 3.00 - 3.00 3.56 2.89 3.11 2.89 | 3.56 3.56 3.78 2.89 3.56 3.33 3.67 3.22 |

Not re-run in full: the other 32 prompts; a change that helps these 8 could hurt others. The grounding check's answer limit was also raised after the full run (a 14-beat rewrite took 2,380 of the 2,400 tokens and, in `mkt-02`, the check probably came back cut off and empty); a live check on the saved `mkt-02` script afterwards flagged 5 beats and rewrote 3, but that is a single call.

## 4. Cost and latency, and why latency got worse

* Plan cost +7% per video overall (median $0.135 -> $0.151, p90 $0.324 -> $0.341, total $6.36 -> $6.78); on the 8-video subset +27% (web escalation, one more script call when a script has to be trimmed). The grounding check is under $0.01 per video (a Haiku call, none when nothing is flagged).
* Median latency 41 s -> 64 s. The cause is the Wikipedia throttle, not the new model calls: before the first script call the median wait went from 4.8 s to 22 s, because 22 of 40 videos hit HTTP 429 and the retries waited. The 429s carried `Retry-After` values of 57 s counting down, i.e. an address-wide block of about a minute, so waiting 3 to 4 seconds could not help; the code was then changed to **not wait for a long Retry-After and to stop sending requests to Wikimedia for that period** (process-wide cooldown, unit-tested); the escalation to the web agent is what actually rescued the notes. In the 8-video re-run median latency was 42 s vs 29 s before. The block is probably made worse by the User-Agent having no contact: the owner must set `httpUserAgent` (see `docs/QUALITY_FIXES.md`).
* The audit machine is one address with 3 parallel workers; production Lambdas share NAT addresses, so the same risk exists there.

## 5. What this does not show

No audio or video was rendered; the judge reads the script. A blind human comparison of before/after scripts (the `review.html` sheet) has not been done. Spanish naturalness was not changed by these fixes (3.91 -> 3.90). The effect of each individual fix cannot be separated from this data.
