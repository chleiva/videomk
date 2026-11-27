# When the director may use the cartoon scenes (2026-11-27)

Owner rule: the cartoon vector scenes (docs/VECTOR_CATALOG.md, scene type `vector_scene`, docs/VECTOR_SCENES.md) are a **special, peculiar style**. They must NOT appear in every video: the director selects them carefully, for particular kinds of video only, and we must be able to tell exactly **which videos show them**.

Code: `backend/lambdas/engine/vector_policy.py` (policy, prompt block, plan cleaning), wired in `engine/director.py` and `engine/plan.py`; tests `backend/tests/test_vector_policy.py` (59); evidence `backend/scripts/vector_policy_eval.py` and the table at the end.

## 1. The switches

| Switch | Where | Default | Meaning |
|---|---|---|---|
| `VECTOR_SCENES` | Lambda environment (plan Lambda) | **OFF** | Global kill switch. Off: nothing is offered, a stray `vector_scene` in a plan becomes an ordinary scene, no trace in the plan. **Do not switch it on in any stage until the element reads `catalog_id` (section 6).** |
| `style` | create option (`POST .../videos/generate` body) | `auto` | `auto` = the director decides under the rules below; `cartoon` = the person wants illustrated scenes; `real` = photographs and footage only, never a cartoon scene. `auto` is not stored (absent). Invalid value is a 400. |
| the request text | the prompt | | "make it a cartoon", "illustrated style", "dibujos animados", "estilo ilustrado" act as `cartoon`; "real footage", "no cartoons", "imágenes reales", "sin dibujos" act as `real` (and win when both appear). The create option, when set, always wins over the words. |

## 2. Decision table (style `auto`)

The kind of video comes from the producer's guide choice (`engine/skills.py`, already paid for) plus one small judge call (`vector_policy.classify`, about $0.0005, Haiku-class, conservative: any doubt or failure is "no").

| Situation | Result | Reason code |
|---|---|---|
| `VECTOR_SCENES` off | never | `flag_off` |
| `style: real` or the person asked for real footage / photos | never | `style_real` |
| the person's own photos or media are in the request | never | `user_media` |
| a deck-to-video request | never | `deck` |
| current events (the research step chose the web agent) | never | `current_events` |
| platform LinkedIn (serious thought leadership), unless `style: cartoon` | never | `platform_linkedin` |
| guide is news, product-marketing, history, biography, true crime, comparison, coding, deck, photo-memories, recap | never | `serious_topic:<guide>` |
| guide is science-wonder, tutorial-howto, listicle-ranking or finance-business | only if the judge says it suits (children's or everyday/abstract idea, nothing that needs real pictures) | `not_suited:<why>` or offered |
| any request the judge says needs real pictures: named real person, place, brand, product, company, event or figures; news; tragedy, war, violence, crime, disease, injury, emergency, medical / legal / investment advice; cooking, repairs, sport technique or any physical how-to; real science best shown by photographs (telescope, wild animals, anatomy, geology) | never | `not_suited:<why>` |
| children's / family topic (guide kids-family) | offered, share **40%**, may open with one | `kids` |
| everyday or abstract explainer, light-hearted, wellness, relaxing travel atmosphere, story, motivation (judge yes) | offered, share **20%** | `judged:<kind>` |
| fewer than 5 expected beats (3 for kids) | never | `too_short` |
| no catalog scene fits the topic (cosine below `vector_catalog.MIN_SCORE` 0.30; 0.24 for kids and cartoon) | never | `no_catalog_match` |
| aspect without scenes (only 16:9 and 9:16 have scenes; 1:1 and 4:5 none) | never (no match) | `no_catalog_match` |

Style `cartoon` (explicit request): offered for everything except the first four rows (flag, real, media, deck); share up to **60%**; the director is still told never to use a cartoon scene for a named real thing, a number or list that needs a chart, news, tragedy, violence, illness or any serious moment. The judge is only used to find the right setting to search for, never to veto.

## 3. What the director is told

When (and only when) the policy offers the style, the prompt gets a short block (`Policy.prompt_block`): the `vector_scene` scene type with props `{catalog_id, seconds?}`, the share it may use ("RARELY", "about 40 percent", "up to 60 percent"), where it fits (general, atmospheric or conceptual beats, chapter openers, transitions), where it never fits, never two in a row, never the first beat (except kids and cartoon), a scene at most twice, and **the menu of up to 3 scenes (6 for cartoon)** found by searching the catalog with the topic and the setting the judge described. The model uses an id from the menu or does not use the scene type at all. With the style not offered the prompt is byte-identical to today's.

## 4. What is enforced in code (the model cannot override it)

1. `plan.validate_plan` (`_validate_plan`): a `vector_scene` is accepted only while a policy that offered it is in force and only with a `catalog_id` from that video's menu (lower-cased, `[a-z0-9_]{3,64}`); anything else is replaced like any invalid scene (a photograph of the beat's `alt` when it has one, else the usual card), and the scene repair step then gets one chance to write an ordinary scene.
2. `vector_policy.enforce` runs once on the finished plan (also for long, staged videos): no policy = no cartoon scene survives; share cap `floor(share x beats)` (at least one when the video is long enough); never the first beat unless allowed; never two in a row; one scene at most twice; not on a silent beat. Extras become ordinary scenes with a warning (`beat N: cartoon scene replaced (why)`).
3. Props written to the plan: `{"catalog_id": "<id>", "seconds": 4-12 (advisory), "motion": "default", "alt": "<fallback caption>"}`.

## 5. How we know which videos show them

Every video made with the flag on carries `plan["vector"]`:
```json
{"decision": "offered|never", "style": "auto|cartoon|real", "reason": "kids", "share": 0.4, "candidates": ["flower_meadow", ...], "aspect": "16:9",
 "judged": {"fit": true, "kind": "kids", "why": "...", "scene": "sunny meadow with green leaves"}, "used": [{"beat": 1, "id": "flower_meadow"}], "beats": 10, "cap": 4}
```
and the plan Lambda logs one CloudWatch line per video: `VECTOR_SCENES decision=offered style=auto reason=kids candidates=[...] used=[...] beats=10`. Count videos with cartoon scenes with a Logs Insights query on `VECTOR_SCENES` and `used=[` not empty; the per-video record is in the saved plan (`plan.vector`). With the flag off nothing is added.

## 6. What other owners must do before the flag can go on

* **Element owner (`elements/vector_scene.py`, `engine/vector_scene.py`)**: accept `catalog_id` (fetch the package with `common.vector_catalog.fetch_package` once per chunk, fall back to a card on any failure; the bundled `scene` id may stay for the three prototype scenes), accept the optional props above, and remove `max_per_video=2` (the policy owns the cap; `plan.enforce_elements` already skips that limit for this element). Enabling `test_vector_policy.py::test_element_accepts_the_catalog_id_prop` (now `xfail`) is the acceptance test. Also CDK: `s3:GetObject` on `<catalog bucket>/v/*` and `CATALOG_BUCKET` in the Lambda that renders; the plan Lambda needs `bedrock:InvokeModel` for the Cohere query embedding (it already has Bedrock).
* **Apps (iOS, Android, web)**: expose the option as in section 7, send `style` only when the person chose Illustrated or Real (omit for Auto).
* **Whoever turns the flag on**: set `VECTOR_SCENES=1` on QA first, run `scripts/vector_policy_eval.py` again, watch the `VECTOR_SCENES` log lines for a week.

## 7. App copy for the Options sheet (one segmented row, no new pill)

| Key | EN | ES |
|---|---|---|
| `create.scenes_title` | Scenes | Escenas |
| `create.scenes_auto` | Auto | Automático |
| `create.scenes_illustrated` | Illustrated | Ilustradas |
| `create.scenes_real` | Real | Reales |
| `create.scenes_hint` (footer, shown only under this row) | Illustrated adds cartoon scenes. Real uses only photos and footage. | Ilustradas añade escenas de dibujos animados. Reales usa solo fotos y vídeo. |
| accessibility label of the row | Scene style | Estilo de las escenas |

Values sent: Auto = omit, Illustrated = `"style": "cartoon"`, Real = `"style": "real"`. Not a Look (theme) choice: the existing Look pill (Auto / Midnight / Paper / Sunrise) is unrelated.

## 8. Evaluation

Run: `AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/vector_policy_eval.py` on 2026-11-27 (31 briefs; QA Bedrock, Sonnet 5.5 director; the real producer, research decision, catalog search and `director.direct`; no voice, no render, no web agent in stage 2). **Spend $1.96 of the $4 cap.** Raw results: `docs/vector_policy_eval/results.json`. "cartoon scenes" = how many beats of the finished plan use `vector_scene` (a plan is only written for briefs the policy offered, plus five refusals as a leak check). `judge` = a small model's 1-5 rating of whether the chosen cartoon scenes suit their beats.

| id | brief | guides | research | policy | beats | cartoon scenes | judge | $ |
|---|---|---|---|---|---|---|---|---|
| kids-story | A bedtime story for five-year-olds about a little cloud who  | kids-family | encyclopedia | offered: kids | 11 | 0 |  | 0.143 |
| kids-photosynthesis | How photosynthesis works, explained for children | kids-family, explainer-education | encyclopedia | offered: kids | 10 | 2 (flower_meadow, river_valley_morning) | 5 | 0.099 |
| kids-seasons | Why do we have seasons? For kids aged 7 | kids-family, explainer-education | encyclopedia | never: not_suited:Seasons explanation depends on astronomy best shown with real imagery |  | n/a |  | 0.001 |
| kids-es-volcano | Explícale a un niño de 6 años cómo funcionan los volcanes | kids-family, explainer-education | encyclopedia | offered: kids | 10 | 2 (volcano_island, river_valley_morning) | 4 | 0.094 |
| light-es-water | Cómo ahorrar agua en casa, con un tono simpático y cercano | tutorial-howto | encyclopedia | offered: judged:wellness | 10 | 0 |  | 0.154 |
| abstract-internet | How does the internet work, in simple terms | explainer-education, science-wonder | encyclopedia | offered: judged:concept | 10 | 0 |  | 0.100 |
| abstract-blockchain | Explain blockchain simply for complete beginners | explainer-education, finance-business | encyclopedia | never: no_catalog_match |  | n/a |  | 0.001 |
| wellness-sleep | Five simple habits for better sleep, in a friendly tone | health-wellbeing, listicle-ranking | encyclopedia | offered: judged:wellness | 10 | 1 (study_desk_window) | 5 | 0.087 |
| funny-cats | Why do cats knock things off tables? A funny explainer | funny-light, explainer-education | encyclopedia | offered: judged:kids | 10 | 0 |  | 0.142 |
| motivation-habits | Why small daily habits beat big goals | inspiration-motivation, health-wellbeing | encyclopedia | offered: judged:concept | 10 | 1 (flower_meadow) | 5 | 0.136 |
| travel-beach | A relaxing beach holiday: what to pack and how to unwind | explainer-education | encyclopedia | offered: judged:travel | 10 | 1 (tropical_beach) | 5 | 0.098 |
| travel-rome | A tour of Rome: the Colosseum, the Vatican and the Trevi Fou | travel-places, history-story | encyclopedia | never: serious_topic:history-story |  | n/a |  | 0.001 |
| cooking-pancakes | How to make fluffy pancakes | tutorial-howto | encyclopedia | never: not_suited:Cooking how-to needs real footage to show technique |  | n/a |  | 0.000 |
| finance-earnings | Quarterly earnings summary for a SaaS company: revenue up 12 | finance-business, recap-summary | encyclopedia | never: serious_topic:recap-summary | 10 | 0 |  | 0.145 |
| news-ukraine | What happened this week in the war in Ukraine | news-explainer | web | never: current_events |  | n/a |  | 0.001 |
| news-election | Latest news on the polls for the US presidential election th | news-explainer | web | never: current_events | 10 | 0 |  | 0.130 |
| product-launch | Launch video for our new noise-cancelling headphones, the Ae | product-marketing | encyclopedia | never: serious_topic:product-marketing | 10 | 0 |  | 0.097 |
| es-pensions | Resumen de la reforma de pensiones en España | recap-summary, news-explainer | web | never: current_events |  | n/a |  | 0.000 |
| linkedin-leadership | Three lessons on leading remote teams | explainer-education | encyclopedia | never: platform_linkedin |  | n/a |  | 0.001 |
| user-photos | Make a video of my holiday photos | travel-places | encyclopedia | never: user_media |  | n/a |  | 0.000 |
| medical-heart-attack | What to do if you think you are having a heart attack | health-wellbeing, tutorial-howto | encyclopedia | never: not_suited:Medical emergency guidance needs real, accurate visuals and advice |  | n/a |  | 0.001 |
| history-rome | The fall of the Roman Empire | history-story | encyclopedia | never: serious_topic:history-story |  | n/a |  | 0.000 |
| tragedy-titanic | The Titanic disaster and why so many people died | history-story, mystery-true-crime | encyclopedia | never: serious_topic:history-story | 10 | 0 |  | 0.093 |
| science-jwst | How the James Webb telescope sees the early universe | science-wonder, explainer-education | encyclopedia | never: not_suited:Real telescope science best shown with actual space imagery |  | n/a |  | 0.001 |
| coding-fastapi | How to build a REST API in Python with FastAPI | coding-tutorial, tutorial-howto | encyclopedia | never: serious_topic:coding-tutorial |  | n/a |  | 0.001 |
| compare-phones | iPhone vs Android: which should you buy in 2026 | comparison-versus, product-marketing | web | never: current_events |  | n/a |  | 0.000 |
| cartoon-bill | Make it a cartoon: how a bill becomes law | explainer-education | encyclopedia | offered: style_cartoon | 10 | 4 (suburb_street_morning, modern_office_exterior, workshop_exterior, solar_wind_farm) |  | 0.090 |
| cartoon-es-water | Un vídeo con dibujos animados sobre el ciclo del agua | explainer-education, kids-family | encyclopedia | offered: style_cartoon | 10 | 2 (river_valley_morning, pine_forest_valley) | 5 | 0.136 |
| cartoon-mortgage | Cartoon-style video about how mortgages work | finance-business, explainer-education | encyclopedia | offered: style_cartoon | 10 | 3 (suburb_street_morning, home_garden_backyard, workshop_exterior) | 2 | 0.051 |
| real-bees | Explain how bees make honey, use real footage and real photo | explainer-education, science-wonder | encyclopedia | never: style_real | 10 | 0 |  | 0.133 |
| kids-tiktok-vertical | Fun fact for kids: why is the sky blue | kids-family, science-wonder | encyclopedia | offered: kids | 4 | 1 (tall_forest_trail) | 5 | 0.037 |

**What it shows**
* **No leaks.** Five briefs the policy refused (earnings, election news, product launch, Titanic, real footage) were planned anyway with the flag on: 0 cartoon scenes in all of them. The wording rule ("real footage and real photos") and the news / product / history / finance cases never reach the director's menu.
* **Offered only where it fits:** children's topics (photosynthesis, volcanoes in Spanish, the sky is blue), everyday and wellness ideas (sleep habits, small habits, a beach holiday), the abstract internet explainer, and the explicit cartoon requests. Refused with a reason: Rome tour (named real places), history, medical emergency, cooking, the telescope, code, comparisons, LinkedIn, the person's own photos, anything research chose to search the web for.
* **Restraint:** even when offered, the director used few: 0 to 2 scenes in a 10-beat video in auto mode (kids-story, the water-saving tips, the internet explainer and the cats video used none: "a video with no cartoon scene is perfectly good"). Explicit cartoon requests used 2 to 4 (cap 6 of 10).
* **Judge:** every auto-mode use scored 4 or 5. The 4 is a volcano video whose second scene was a river valley (menu had no second volcano-like scene): the menu is by topic, so it can offer a scene that fits the topic loosely.
* **Weak spots (honest):** (1) `cartoon-mortgage` scored 2: asked for a cartoon of how mortgages work, the director put cartoon scenes on beats that were about interest and budget numbers (the prompt forbids it, the model followed the person's request over the rule; the person did ask for cartoons, so it was left). A stricter version would add a per-beat check on beats that carry numbers. (2) `cartoon-bill` produced 4 scenes of buildings for "how a bill becomes law" (suburb, office, workshop, wind farm): the catalog has no parliament or civic scene, so the match is loose; the judge reply was unparseable and is recorded as a judge error, not a pass. (3) `kids-seasons` is refused (the judge says seasons need an astronomy diagram), which is conservative; my expectation was "offered". (4) 1:1 and 4:5 never get scenes (no scenes drawn for them); 9:16 has only three tall scenes (one was used in the vertical kids video). (5) Stage 2 ran without the web agent, so current-events briefs were refused in stage 1 by the research decision (`current_events`), not re-planned.
* **Known limit of the share cap:** it is applied to the finished plan, so a long staged video is capped as a whole, not per section.

## 9. Files

`backend/lambdas/engine/vector_policy.py` (new), `engine/director.py` (decision, prompt block, final pass), `engine/plan.py` (accept `vector_scene` only under a policy; no `max_per_video` for it), `sf_launcher.py` (`style` option, validated), `engine/handlers/plan_handler.py` (passes `style` to the director), `backend/tests/test_vector_policy.py` (59 tests + 1 expected-fail for the element), `backend/scripts/vector_policy_eval.py`, `docs/vector_policy_eval/results.{md,json}`.

## 10. Switched on in QA (2026-11-27 evening; tests `backend/tests/test_looks.py`)
Section 6 is done for QA: `VECTOR_SCENES=1` on the engine functions through `backend/stages.json` `"vectorScenes": true` (QA only; prod has neither the flag nor a catalog bucket, and the stack refuses the flag without `-c imageCatalog=1`).
* **Element** (`engine/scenes/elements/vector_scene.py`, `engine/vector_scene.py`): reads `catalog_id`; the package is fetched once per render function to `/tmp/vector_scenes/<id>` (temporary name, then renamed); a scene that cannot be fetched or drawn becomes a card with its `alt` line and is not tried again for every frame (`VECTOR_SCENE_FETCH_FAILED` in the log). No `max_per_video`. `resvg-py` is now in the engine layer.
* **Every aspect:** the scene is full bleed in 16:9, 9:16, 1:1 and 4:5 (before: a framed card outside 16:9). It is rendered in its own shape so that it covers the frame and the frame shows its centre: never stretched. The policy searches landscape scenes for 16:9 and 1:1 (a square shows the middle 56 percent of the width) and tall scenes for 9:16 and 4:5 (4:5 shows the middle 70 percent of the height). Not composed per shape: a subject near the edge of a landscape scene can fall outside a square frame.
* **Speed:** a cartoon scene cost 1.3 s a frame on Lambda in the first real video (a 10.3 s scene took 399 s of the function's 600). Now: drawn on twos (15 drawings a second, each held for two frames), and a video that has a cartoon scene is cut into render pieces of at most 150 frames (`CHUNK_MAX_FRAMES_VECTOR`), so no function works for more than a few minutes. 4K: animated at 1440p and enlarged (flat art), 0.54 s a drawing on the laptop against about 1.2 s at full size.
* **IAM / environment:** `s3:GetObject` on `<catalog bucket>/v/*` and `CATALOG_BUCKET` for the chunk renderer and the self-test; the planner already had Bedrock rights for the Cohere query embedding (the index ships in the code).
* **Held back:** the three scenes with rotating wind turbines (`offshore_wind_farm`, `solar_wind_farm`, `tall_wind_turbines_vertical`) are not offered (`vector_policy.HELD_BACK_MOTION`). Re-check at 1080p: the rotors turn and nothing tears across the picture, but the cut-out leaves stubs of the nacelle turning with the blades, a faint lighter patch beside one tower and, in the tall scene, a blade with a square notch. 154 of 157 scenes are offered.
* **Three real QA videos (60 s, 16:9, qa-tester6, 15:01 UTC):** "Make it a cartoon: where does rain come from? The water cycle, told simply" (no `style` field): `style_cartoon`, 3 cartoon scenes of 8 (river_valley_morning, spring_hills_flowers, flower_meadow); "How do fish breathe under water? For children aged six" on auto: `kids`, 1 of 7 (deep_ocean_reef: the fish swim, the seaweed sways); "Three lessons on managing cash flow in a small business" on auto: `never`, 0 of 7. Honest note on the last: the reason recorded is `not_suited:classifier failed` (the small judge call failed and the policy fails closed), not a judged "no"; the result is the right one, the path to it was the safety net.
* **Not done:** scenes composed for 1:1 and 4:5; a cartoon scene shorter than 4 s is allowed (one lasted 2.8 s on a 6-word beat); the per-beat check on beats that carry numbers (section 8, weak spot 1); prod.

