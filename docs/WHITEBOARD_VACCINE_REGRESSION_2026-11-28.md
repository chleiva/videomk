# Whiteboard vaccine board failures: variance, review changes or watermark band? (2026-11-28)

Branch `wb-vaccine-fix` (from 432b9bd). QA Bedrock spent about USD 2.2 of 2.50 (plan stage only, profile qa, eu-west-1). Owner standard: whiteboard quality must not drop.

## Question
The QA Spanish 9:16 vaccine video ended with 3 of 4 boards failing after the review (earlier proof `v4_vaccine`: 1 of 5). Variance, or a regression from the review changes (`WB_MEND`, `WB_REVIEW_BUDGET`, caching) or from the larger watermark band?

## Method
Same request every time ("Cómo funcionan las vacunas", look whiteboard, 9:16, 1 minute, language es), plan stage with the lambda's own `ask_small/ask_big/ask_review`, scored by `plan.whiteboard.score`. Harness in the session scratch (`wbfix/plan_run.py`).

## Data
| Arm | Runs | Failing boards after review (of boards) | Director called | Kept new / first / no call | Review cost per run | Script cost per run |
|---|---|---|---|---|---|---|
| current code (mend ON, budget ON) | 8 | 1/4, 1/4, 0/5, 0/4, 1/6, 1/5, 0/4, 0/4 = **4 of 36 boards, mean 0.5 a video** | 6 of 8 | 6 new / 0 first / 2 no call | 0.00 to 0.06 (mean 0.028) | 0.05 to 0.17 |
| `WB_MEND=0 WB_REVIEW_BUDGET=0` | 4 | 1/4, 1/4, 1/3, 3/4 = **6 of 15 boards, mean 1.5** | 3 of 4 | 3 new / 0 first / 1 no call | 0.00 to 0.10 (mean 0.052) | 0.06 to 0.14 |
| the QA run itself (current code, full pipeline) | 1 | 3/4 | 1 | new | 0.19 total script | |

* Failing boards before the director on the current arm: 1, 3, 1, 1, 3, 2, 1, 0 (the QA run: 3). **The 3 of 4 of the QA run is inside the spread** (the mend-off arm also produced 3 of 4 once, and its 3 other runs 1 each); with 8 samples there is no sign that mend or the budget makes it worse, the current arm is if anything better (0.5 against 1.5 failing boards a video). Caching changes no prompt text (`docs/COST_LEVERS_2026-11-28.md`), so it cannot change boards except through sampling.
* Script cost varies 0.05 to 0.17 with the cache state, review 0 to 0.06.

### The watermark band
`score.score_plan` (and so the plan stage, the director's review and every number above) lays boards out on `Frame.parse(aspect)` with **no top inset**: the band exists only in the renderer (`Renderer.__init__` applies `wm.inset`). So the plan-stage failing counts cannot depend on the band, by construction. To see what the band does to the same boards, the 12 final plans were rescored with the 9:16 inset at 0 (no mark), 117 (before 06842e0: lockup 212 wide, content box starts 267) and 134 (now: 281 wide, box starts 284):

| plan | failing / complaints at 0 | 117 | 134 | mean coverage 0 / 117 / 134 |
|---|---|---|---|---|
| all 8 current plans | identical at the three insets on every plan | | | e.g. cur1 0.444 / 0.470 / 0.468, cur3 0.342 / 0.385 / 0.389 |
| all 4 mend-off plans | identical at the three insets | | | |

Failing boards, complaints and smallest text are identical on all 12 plans; coverage goes up a little with the band (the same drawings fill a smaller picture). The band is 17 units (1.4 %) of the 1,235-unit box between 117 and 134. **The band is not the cause.** (The owner has since decided the mark becomes a final overlay with no band; this analysis is the baseline for that, nothing here depends on a band.) The "old band" arm was not run live: the plan stage never sees the band, so it would be the same code path.

**Verdict: (a) run-to-run variance.** The rate of failing boards after review is about 0.5 a video with the current code; the QA run was a bad draw (3 before the director, `count` x2, `rest`, and one crossing of arrows the scorer did not look at).

## What the failing boards of the QA video were
Board 3 (beats 5 and 6 on one board): 7 drawings and phrases for 23 s (bar 9), two green arrows crossing (a6 shield to family, a7 family to old person). Board 4 (beat 7): one xl line "Vacuna = entrenamiento" and an underline for 11 s, the pen rests 5.7 s at the end; `count` 1 of 4. Board 2: a 3.2 s rest. The director was called once and its rewrite was kept as new, which did not fix them; mend kept one move (the arrow end swap) only after this change.

## What changed (all model-free, `backend/lambdas/engine`)
1. **Arrows that cross each other are now a complaint** (`whiteboard/spec._arrow_crossings`, `score`: kind `crossed`, key `arrow_cross`). The layout comment said "two arrows may cross"; viewers read an X as a tangle. A crossing close to an arrow's end (two arrows meeting at one thing) does not count. `mend` already had arrow moves for `crossed`; they now also try the crossing pair: on the QA board one swap (`o` to the other zone) clears it. In the 12 plans + 6 fixtures this adds the complaint on 3 boards, none unresolvable.
2. **`mend.fill_words`, setting `WB_FILL_WORDS` (default ON)**, run only in the FINAL repair, after the director had its chance, for boards still failing `count`, `rest` or `busy`. It adds, one at a time and kept only if no board gets a kind of complaint it did not have, none that passed now fails, and some wanted complaint is gone (else everything of that board is undone): first the library drawing that a word of the beat's narration names (title or synonym, English or Spanish, exact and unique: `cuerpo` gives the person; `te` never gives a cup), then, only on a board with 3 or fewer drawings and phrases or a rest of 3.5 s or more, at most 2 written key words (7+ letters, no adverb, not the first word of a sentence). Each is tied to the word said, in a free zone, size l then m. Nothing is invented and nothing is said that is not narrated.
3. `score` keeps `rests` (gap, beat, where) per board; `docs/CREDITS.md` cost basis corrected (below).

Tried and dropped: splitting a thin shared board into one board per beat (the QA board 3: 2 boards failing, `empty` + `count`, instead of 1 failing: the bar is per second so it moves the problem); `fill_count` style written words picked by length alone (they read as noise: "primero", "verdad"); extending the paper under the mark (no band needed any more, and the band was not the cause).

## Scores, before and after the new final step (mend ON in both; the new `crossed` complaint counted in both)
18 plans (12 vaccine harness plans, the QA vaccine, `es_vacuna_916_r2`, `fr_sea_salt_r2`, and p3, p4, p5, p7 of `review_cost_qa_2026-11-28.json`): failing boards **19 to 15**, complaints **24 to 17**, no plan worse. Largest: p4 1 to 0 (2 to 0 complaints), cur2 1 to 0, p7 3 to 2, `es_vacuna` 2 to 1, QA vaccine 3 failing / 4 complaints to 3 / 3 (board 4: `count` and its 5.7 s rest cleared, a `busy` left; board 3's crossing cleared by mend). The other four plans of the earlier eight (p1, p2, p6, p8) are not stored anywhere I could reach: not measured here.
Live, new code (4 runs): failing 2/4, 0/5, 0/4, 1/3 (mean 0.75); current code 0.5. That is a sample, not a proof either way: the live runs differ in what the model writes, and the new `crossed` complaint counts boards the old scorer passed.

## What I looked at
Local renders (`wbfix/frames.py`, the engine's own renderer, 9:16, paper theme, no captions) of the QA vaccine plan before and after the final step, boards 3 to 7, and the closing board mid-way. After: the closing board has the person icon at "cuerpo" and the two written words "enemigo" and "infecta" beside "Vacuna = entrenamiento"; the crossed arrows are separated. **Taste caveat:** the two small written words are weak key words; the pen no longer rests and the board is not one lonely line, but a human should look at a few more videos before the setting stays ON in production (switch off with `WB_FILL_WORDS=0`).

## Not verified
* Live QA video with the new code (plan stage only was run; no render with captions and the mark).
* Quality of written fills across languages other than es and the 4 fixtures (drawings by name exist for en and es only).
* p1, p2, p6, p8 of the review-cost study.
* The 1:1 and 4:5 shapes (only 9:16 analysed for the band).

## CREDITS.md
It said a 1-minute video is about USD 0.06 per credit. Measured on QA: about USD 0.22 to 0.24 per credit with the render (the QA vaccine: script 0.233, speech 0.036, render 0.029 = 0.269). Corrected in `docs/CREDITS.md` (cost basis and the free-exposure figures that followed from it).

Tests: `backend/tests/test_whiteboard_vaccine_fix.py` (fixture `vaccine_es_916_qa_2026-11-28.json`).
