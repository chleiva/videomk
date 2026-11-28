# Whiteboard drawing search (28 Nov 2026): built, evaluated, shipped OFF

Setting `WB_SEARCH` (default **OFF**), `WB_SEARCH_K` (default 60). With it off the prompt is what it was; the only change is a log warning if the full list is ever cut at `MAX_MENU_CHARS`.

## A correction to the audit first

`docs/SELECTION_ARCHITECTURE.md` said the drawing ids take 9,372 characters and are already cut at the 9,000-character cap. **Measured today, the full menu of 354 drawings is 3,704 characters (about 1,300 tokens) and is not cut.** (9,372 is about the size of the whole whiteboard block.) The "silent cut" is not a bug today; it would start at roughly 900 drawings. The case for search is scale, not today's tokens.

## Design

* `engine/whiteboard/retrieval.py`: hybrid search. **Lexical:** BM25 over title, title_es, id words, synonyms_en/es, tags, category (weights 3, 3, 2, 2, 2, 1.5, 0.2); accent-folded, stop words dropped, a light plural/ending stemmer that works for en, es, fr, de, it, pt, nl. **Embedding:** cosine of the query against the vector `v` that every library item already carries (Cohere Embed v4 on Bedrock through `common.library_search.embed_text`, never Titan). Up to 4 queries are embedded (the request; request plus the first notes lines; two more passages of the research notes) and the best cosine per drawing counts. The two ranks are fused by reciprocal rank (k 20). Top K plus 49 fixed generics (marks, simple people, faces, money and numbers, and common process elements such as sun, water drop, wind, fire, clock), grouped by category as before.
* The query is known only to the director: `director.py` calls `retrieval.set_context(prompt, notes)` before the prompt block is built (long videos use the whole request and notes, not each section).
* `whiteboard_policy.prompt_block` calls `retrieval.menu(items)`; `None` (off, no context, or any failure) means the old full list. Embedding failure means lexical only. A video is never failed by search. With search on there is no character cut.
* Embeddings: **no new embedding of the 354 was needed**; `library_index.json` already holds one per item (and drawings made on demand register with theirs). `backend/scripts/whiteboard_embed.py check|fill` covers any item that has none: `fill` embeds it from title, synonyms and tags into `engine/assets/whiteboard/library_embeddings.json` (idempotent, keyed by a hash of the text, items that left the library are dropped). `tests/test_whiteboard_search.py::test_every_library_drawing_has_a_vector` fails if an item has neither. **A new drawing:** `lib_index.py build` (writes `v`), or run `whiteboard_embed.py fill`; the test tells you if you forgot.

## Evaluation (QA, Sonnet 5.5 planner, 0.5 minute whiteboard plans, same research notes in both arms)

Run with `scripts/wb_search_eval.py run`; raw results in `backend/scripts/wb_search_eval_2026-11-28.json`. Counts are distinct drawings the planner chose in its first answer (before repair), full list vs retrieved menu (K 60 + generics, about 100 shown). Recall is computed offline with the final code over the full runs' chosen ids that exist in the library, counting each use.

| Request | Drawn, full | Drawn, retrieved | Written items, full / retr. | Asked (new) full / retr. | Prompt tokens full / retr. | Cost USD full / retr. |
|---|---|---|---|---|---|---|
| sundial (en) | 4 | 4 | 9 / 9 | 2 / 2 | 11,197* / 10,101* | 0.100 / 0.069 |
| windmill (es) | 6 | 4 | 10 / 9 | 0 / 0 | 18,612 / 17,783 | 0.070 / 0.070 |
| vaccine (en) | 10 | 8 | 12 / 11 | 0 / 0 | 18,650 / 17,531 | 0.102 / 0.069 |
| sea salt (fr) | 8 | 5 | 8 / 10 | 0 / 0 | 19,219 / 18,113 | 0.089 / 0.072 |
| compound interest (en) | 7 | 8 | 10 / 8 | 0 / 0 | 18,596 / 17,468 | 0.083 / 0.086 |
| water cycle (de) | 7 | 8 | 8 / 6 | 0 / 0 | 19,780 / 18,676 | 0.108 / 0.103 |
| compass (it) | 5 | 7 | 6 / 7 | 0 / 0 | 19,622 / 18,505 | 0.075 / 0.067 |
| bread (es) | 9 | 6 | 11 / 9 | 0 / 0 | 19,275 / 18,163 | 0.078 / 0.034 |
| refrigerator (de) | 8 | 4 | 9 / 7 | 0 / 0 | 18,386 / 17,296 | 0.096 / 0.100 |
| beehive (en) | 9 | 7 | 9 / 8 | 0 / 0 | 19,363 / 18,228 | 0.105 / 0.073 |

*the first row's token count excludes cached tokens (the harness was fixed afterwards); all drawings chosen existed in the library except the sundial's two asked names. Cost differences are planner output variance, not caused by the menu.

**Prompt size:** full menu 3,704 chars; retrieved 1,170 to 1,285 chars (average 1,230). Saving about 2,470 chars, **about 880 tokens per planner call (measured prompt difference about 1,100)**, which is 6 percent of the prompt and about USD 0.002 per plan at USD 2 per million input tokens. Search costs 3 to 4 query embeddings (about USD 0.0001) and about 0.3 s.

**Recall of the drawings the full-list run chose, inside the menu shown:**

| K | menu size | recall |
|---|---|---|
| 40 | about 75 | 57 % |
| 60 | about 94 | 65 % |
| 100 | about 130 | 76 % |
| 200 | about 217 | 88 % |
| 60 + process generics (sun, water drop, wind, fire, snowflake, clock, calendar, mountain, river...) | about 100 | 83 % (in-sample: the generics were chosen from these same runs, so this is optimistic) |
| 100 + those generics | about 135 | 89 % (in-sample) |

What retrieval hid: the planner picks associated pictures, not only the named object: sun and wind for evaporation and salt, snowflake and river for the water cycle, bank and money bag for compound interest, fire and recycle for a refrigerator, a lock and a stomach for honey, a cheering person for a vaccine. No topic words point at these. Where a better library match existed and was hidden: compound interest (bank, money bag at K 60 before the generics), vaccine (cell, puzzle piece).

## Decision: OFF

The gate was "no request loses a drawing it needed". Recall is not 100 percent at any reasonable K, drawings per video fell in 5 of 10 requests (refrigerator 8 to 4, sea salt 8 to 5, bread 9 to 6, windmill 6 to 4, vaccine 10 to 8), and today the saving is only about 880 tokens against a menu that fits. So it stays off. Turn it on (with K near 100 plus generics) when the library passes about 800 drawings, or when the music/element lists have moved and this is the largest list left, and re-run the evaluation first.

## Not proven

* Planner run-to-run variance was not measured (one run per arm, USD 2 budget): some of the drop may be noise; the recall table does not depend on it.
* Whether fewer drawings hurts the finished video (score, viewers) was not judged; only counts.
* Long staged videos use one query for all sections.
* The generics are tuned in-sample. Languages pt, nl and the tall aspects were not run. `WB_SEARCH` on with Bedrock embedding down (lexical only) was unit tested, not run against a planner.
