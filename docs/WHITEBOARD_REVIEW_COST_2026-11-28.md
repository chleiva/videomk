# Whiteboard review cost (2026-11-28)

Branch `wb-review-analysis`. Owner's constraint: **no loss of quality, on any plan**. QA Bedrock spent: USD 1.73 of 2.00 (plan stage only, profile qa, eu-west-1).

## What the review does, in plain words
After the script is written, every whiteboard board is laid out and timed exactly as the renderer will, without drawing anything, and scored (`engine/whiteboard/score.py`): enough drawings and
written phrases for its length, nothing overlapping or off the board, arrows with a clear way, text big enough, items finished close to the word they are tied to. Whatever can be mended
without a model is (`_repair`: `make_safe`, `make_clean`, `fill_out`). Boards that still fail for one of `DIRECTOR_KINDS` (`count`, `arrow`, `crossed`, `small`, `late`, `layout`, `gap`)
are sent ONCE to the script model (Sonnet 5.5, effort medium) with their complaints; it writes those boards again, the new boards get the same clean-up, and they are kept only if the video
scores at least as well. A call costs USD 0.02 to 0.15 because most of its output is thinking, not the answer.

## Data (8 plans, plan stage, QA)
Plans: `p1` en 16:9, `p2` es 9:16, `p3` fr 16:9, `p4` de 16:9, `p5` it 1:1, `p6` pt 9:16, `p7` nl 16:9, `p8` pl 16:9 (40 to 75 s each). The plan as it stood just before the review, the director's
prompts and answers, tokens and cost were recorded (harness kept in the session scratch, four plans are fixtures: `backend/tests/fixtures/whiteboard_plans/review_cost_qa_2026-11-28.json`).
The six QA plans of the earlier round (`es_vacuna`, `fr_sea_salt` fixtures, proof2 `v1..v7`) are the SHIPPED plans, already rewritten, so the first state cannot be replayed from them; the four of them
that carry `plan.whiteboard.score` agree with the new data: `director_calls` 1, `kept` new, failing boards before the director to final: 1 to 1, 3 to 1, 5 to 4, 2 to 0.

**The director is called on 7 of 8 plans (88 %).** Review cost on those 7: USD 0.146, 0.071, 0.021, 0.039, 0.068, 0.057, 0.022 (mean 0.061; 34 % of everything the plan step spent on these plans).
Failing boards before the director to after it: 22 to 15 over the 7 plans (5 to 4, 2 to 1, 3 to 0, 3 to 2, 3 to 3, 3 to 3, 3 to 2).

| Kind | Calls with it | Occurrences | Cleared | Not cleared | Mean cost of those calls |
|---|---|---|---|---|---|
| count (too few drawings/phrases) | 6 | 9 | 8 | 1 | USD 0.064 |
| arrow (blocked, two bare drawings) | 5 | 10 | 4 | 6 (2 of them reduced from 2 arrows to 1) | USD 0.059 |
| late (finished > 0.8 s after its word) | 2 | 2 | 2 | 0 | USD 0.093 |
| gap (two texts read as one word) | 1 | 1 | 1 | 0 | USD 0.146 |
| small, crossed, layout | 0 | 0 | | | never seen in these plans |

("Cleared" = no complaint of that kind left on the boards covering those beats after the rewrite; one call carries several kinds, so the mean costs overlap.)

**Calls that paid and gave nothing usable or nothing gained** (2 of the 9 calls on 7 plans' reviews, plus one more):
* p2, first call: 9,250 output tokens (the whole limit), `max_tokens` before any JSON, USD 0.108, asked again at once (a retry of 2,288 tokens, USD 0.038). Paid twice for one answer.
* p7: 3 failing boards before, 3 after (two `count` boards were fixed, the rewrite introduced a `gap` and a `late`; kept because ties keep the new boards). USD 0.057.
* p6: 3 failing before, 3 after (6 complaints to 5), USD 0.068.

## Output budget (question 4)
The answer is small: about 0.5 token per character of JSON, 330 to 2,300 tokens here (about 600 per board sent). The rest is thinking: 0 to over 14,000 tokens. Output tokens of the successful calls by boards sent:
1 board 1.2k; 2 boards 4.7k and 6.0k; 3 boards 1.0k, 2.8k, 5.5k; 5 boards (p2) 2.3k once and 13.9k to 16k+ otherwise. The same p2 prompt asked three more times with a 16,000 limit: 16,000 (cut, no JSON), 15,090, 13,857
(USD 0.175 / 0.166 / 0.154). So the limit that was shipped (`plan_max_tokens`: 6,000 + 2,600 per minute, 9,250 for 75 s) is below what 5 boards need, and p2 only got an answer because the retry happened to think little.
Effort and model are untouched.

## What changed (all in `backend/lambdas/engine`)
1. **`whiteboard/mend.py` (new), setting `WB_MEND`, default ON.** Before the director is asked (and again on the director's new boards before they are compared), small moves are tried on the real plan and scored with the
   renderer's own layout: a late item tied one word earlier (never before the word of the item before it), a text one size larger, the label of a too-close pair on another side, one end of a blocked or
   crossing arrow in a free zone or swapped with another drawing. A move is kept only if the video scores strictly better (fewer complaints, no board that passed now failing, no board with a kind of complaint it
   did not have). Nothing is added, taken off or reworded; the narration and the order of the words are untouched (test). Capped at 40 tries and 6 s.
2. **Skipping the director** needs no extra rule: a board that passes after the moves is not sent (a passing board cannot score better), so the call is skipped when every board passes. In these data that never happened (see below).
3. **`director_budget(boards)` and the retry, setting `WB_REVIEW_BUDGET`, default ON.** The director is asked for 6,000 + 3,200 per board sent output tokens (at least the old limit), the retry after an answer that is not JSON for 1.5 times that
   (it used to repeat the same limit). A limit is only what may be used: a call that thinks little costs the same.
4. **Option `WB_MEND_COUNT`, default OFF** (`mend.fill_count`): a board short of its count gets the longest words of its own narration written in a free zone, tied to the word.

## Measured: mend on, against off (same plans, same recorded director answers, final scores of what ships)
| Plan | Failing boards / complaints, off | on | Director prompt, characters off to on |
|---|---|---|---|
| p1 | 0 / 0 (no call) | 0 / 0 | |
| p2 | 4 / 6 | **2 / 4** | 16,475 to 15,781 |
| p3 | 1 / 1 | **0 / 0** | 3,115 (same) |
| p4 | 0 / 0 | 0 / 0 | 2,945 to 706 |
| p5 | 2 / 2 | **0 / 0** | 3,412 to 1,126 |
| p6 | 3 / 5 | **1 / 2** | 4,595 to 2,596 |
| p7 | 3 / 3 | **2 / 2** | 2,359 (same) |
| p8 | 1 / 2 | 1 / 2 | 2,455 to 1,312 |

Failing boards over the eight plans: 14 off, 6 on. On no plan is the final score worse. Before the director, mend alone cleared the arrow complaint on p4 (2 boards), p5 (2), p6 (2 arrows), p8 (1), p2 (3 of 4) and the gap on p2.
The director is still called on 7 of 8 plans with mend on: the `count` complaint (6 plans) is new content, not geometry, and `late` on a board whose neighbour is tied to the next word cannot be moved without changing the order.

Model-free repair for `count`: `fill_count` (option, OFF) clears 6 of the 9 count boards (p2 b6, p8 b6, p3 b4, p6 b3, p7 b2 and a partial p3 b2) and lowers failing boards on all five plans it touched, but the words it writes are rule-picked
(`enfermedad`, `responda`, `Wichtigste`, `simplement`, `s'évapore`): the scorer counts them, it cannot tell whether they read as well as the drawings the director chose. Not proven equal, so OFF.
`small`, `gap`, `late` moves exist and are tested; `small` and `crossed` never occurred in the data, so there is no measure of the director's rate on them.

## Savings per video
* **Money: not proven.** The director is still called on 7 of 8 plans, so the call (USD 0.02 to 0.15, mean 0.061, 34 % of the plan step) is not skipped in the data. With mend on it is sent fewer boards (prompts 44 to 76 % shorter on 4 of 8 plans),
  which should shorten the thinking, but that was not measured with live calls (budget). The budget change costs the same when thinking is short; on p2 it would turn USD 0.146 (cut, then a lucky retry) into about USD 0.16 to 0.18 for one
  answer, so it is a robustness change, not a saving: it removes the case where both attempts are cut and the rewrite is lost.
* **Quality: up.** Failing boards on the shipped video 14 to 6 over 8 plans.
* **Time:** mend adds 0.3 to 3 s on most plans, 4.6 s on p6 and 16 s on p2 (a few layouts take seconds); a director call is 11 to 77 s.

## Not proven / not shipped
* Skipping the director for a kind it "never fixes": the data has no such kind (it cleared count 8 of 9, arrow 4 of 10, late 2 of 2, gap 1 of 1).
* `fill_count` (OFF) as above. Effort or model changes: not touched, as asked.
* Savings from shorter prompts: needs live calls on the mended input. The director replay used its recorded answers for boards it was shown; with a shorter prompt it would write new answers.
* One sample per plan and 8 plans; the director's answer varies from call to call.
* Setting names: `WB_MEND` (1), `WB_MEND_COUNT` (0), `WB_REVIEW_BUDGET` (1). Tests: `backend/tests/test_whiteboard_review_cost.py`.
