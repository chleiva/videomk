# Art direction: one look per video (2026-11-28)

Why: the owner's test on his phone. "If I want one of the features I have to push the prompt very well ... it feels random ... it's just mixing too many things." The contract for the apps is in `docs/CREATE_API.md`, "Video look (chosen and enforced)". This page is how the engine keeps it, what was measured, and what is weak. Code: `lambdas/common/look_choice.py` (the request, the answers, capabilities), `lambdas/engine/art_direction.py` (the decision, the writer's instructions, the check and the repair), `lambdas/engine/scenes/elements/presenter.py` (a conversation on screen, the board beside the characters). Tests: `tests/test_look_choice.py` (24), `tests/test_art_direction.py` (26). QA: deployed (commit c1ae9c4). Production: every look other than Real is still off there (the same server switches as before: `WHITEBOARD`, `PRESENTERS`, `VECTOR_SCENES`).

## How a video gets its look
1. **Decide once, before anything is written** (`art_direction.decide`). A look the person chose is taken as it is: the `look` / `cast` / `extras` fields; else the older `style` / `presenter` fields; else plain words ("as a whiteboard video", "explained by a fox and a bear", "three characters talking", "characters who draw on a board"). Otherwise (`auto`) the topic policies say which of the named recipes this video MAY have and one small model call picks one and writes a one-sentence reason; with a single candidate there is no call. Any failure is `footage`.
2. **Recipes**: `footage` (photos, clips and our titles, charts and maps under one background and type treatment), `whiteboard`, `presenter`, `conversation`, `presenter_board`, `conversation_board`.
3. **The older policies are built from the decision** (`art_direction.policies`): exactly one look is on. The per-scene "maybe a cartoon scene here" on `auto` is gone: a cartoon scene now only exists inside a cartoon video (as the backdrop behind the characters, or at most one scene in five without them).
4. **Check and repair after the plan is written, and again on the final plan** (`art_direction.enforce`). A scene outside the look is converted to the look's own scene type with the same narration; the plan records every conversion (`plan.look.repairs`: beat, from, to, why). Never an error, never ignored.
5. **Recorded**: `plan.look` = chosen, applied, recipe, by (`you` | `words` | `auto`), why, cast, extras, share (of the video's time in the look), share_written (what the writer delivered before repair), min_share, ok, systems, families, repaired, repairs. The compact form is on the video record (`look` in the list and item answers).

## The rule per look (tested numbers)
| Look | Share of the time that must be in the look | What else is allowed | What a broken scene becomes |
|---|---|---|---|
| whiteboard | at least 80 % on a board | a photograph, gallery or clip: at most one per 30 s, inside the 20 %, never the first or last scene, never two in a row. A video under 30 s has none. A pause keeps its picture (that time comes out of the allowance) | a title, list, number or quote is written; a chart is drawn by hand with its numbers; a picture over the allowance becomes its subject drawn (when the library has it by name) under a written title; anything else its heading and points written |
| cartoon | 100 % in the cartoon world, at least 80 % with a character on screen | a full-screen cartoon scene without the character: at most 20 % of the time, never first or last, never two in a row | the character beside the same content: a list as points, a chart as the small chart, a photograph or clip as the picture on the card, a cartoon scene as the backdrop; with the board extra, as a hand-drawn board |
| real / footage | 100 %: no cartoon scene, no board, no character | - | a cartoon scene becomes a photograph of what it showed (or a text card), a character scene the plain scene with the same content, a board its written lines |
A conversation in addition: every line belongs to a character of the cast (a script that was not written as a dialogue is given turns line by line, recorded as repairs), each character has its own voice, a line that shows nothing new keeps what is on screen, one backdrop for the whole conversation.
What still overrides a chosen look: safety; the person's own photos or a deck (`reason: own_photos | deck`); a look the stage does not have (`not_available`); a conversation asked for in under 20 s (`too_short`: one character presents). Words alone do not put characters into news (`serious`); the `look` field does.

## Auto before and after (12 requests, plan stage only, 45 s, QA switches on; 2026-11-27)
"Systems" = how many of these appear in one video: real media (photos, clips), our graphics (titles, lists, charts), cartoon scenes, characters, whiteboard. Before = commit bc5b025, after = this work.
| Request (45 s) | Before: look | Before: main system, share | Before: systems | After: direction | After: reason recorded | After: share in the look | After: systems | Repaired |
|---|---|---|---|---|---|---|---|---|
| How does compound interest work? | whiteboard, chosen by itself | whiteboard 100% | 1 | whiteboard | Compound interest is a mechanism with steps and numbers, so a drawn board explains how it grows better than stock footage. | 100% | 1 | 0 |
| Why is the sky blue? For young children | whiteboard, chosen by itself | whiteboard 100% | 1 | conversation | Two characters asking and answering a child's 'why' question suits young viewers and a 45-second playful explainer. | 100% | 1 | 0 |
| The history of the Eiffel Tower | no stated look | media 52% | 2 | footage | Real pictures tell this topic best. | 100% | 2 | 0 |
| How to bake sourdough bread at home, step by step | whiteboard, chosen by itself | whiteboard 100% | 1 | footage | Sourdough is a visual craft: real shots of dough, hands and crust show each step more truthfully than drawings or cartoons. | 100% | 2 | 0 |
| Cinco datos curiosos sobre los pulpos, para niños | whiteboard, chosen by itself | whiteboard 100% | 1 | footage | Los pulpos reales son asombrosos de ver, así que las imágenes auténticas transmiten mejor el asombro que un dibujo. | 100% | 2 | 0 |
| How vaccines train the immune system | whiteboard, chosen by itself | whiteboard 100% | 1 | whiteboard | A vaccine explainer is a mechanism told in steps, which a hand-drawn board shows clearly better than real photographs could. | 100% | 1 | 0 |
| Top 5 places to visit in Japan | no stated look | media 81% | 2 | footage | Real pictures tell this topic best. | 100% | 1 | 0 |
| What is machine learning? Explain it simply | whiteboard, chosen by itself | whiteboard 100% | 1 | whiteboard | Machine learning is a process and an idea, best shown through drawn steps rather than stock footage. | 100% | 1 | 0 |
| Cómo ahorrar dinero cada mes: tres hábitos sencillos | whiteboard, chosen by itself | whiteboard 100% | 1 | whiteboard | Un proceso de tres hábitos con pasos y números se explica mejor dibujado en pizarra que con imágenes reales. | 100% | 1 | 0 |
| Why do we dream? | whiteboard, chosen by itself | whiteboard 100% | 1 | whiteboard | Dreaming is a mechanism and an open question, so drawn diagrams explaining the theories suit it better than footage. | 100% | 1 | 0 |
| Our new project management app launches next week: make a short product teaser | no stated look | media 56% | 2 | footage | Real pictures tell this topic best. | 100% | 2 | 0 |
| A funny explanation of why cats knock things off tables | whiteboard, chosen by itself | whiteboard 100% | 1 | footage | Real cat clips with punchy captions will make the funny explanation land better than cartoons on TikTok. | 100% | 2 | 0 |

What it shows, honestly:
* **Before, a 45 s video was not a mix; it was a whiteboard almost every time** (9 of 12, including bread baking, octopus facts for children and a joke about cats): the old automatic whiteboard rule said yes to nearly any explainer. The scene-by-scene mixing the owner saw (a cartoon scene dropped into a photo video, a presenter in a third of the scenes) needs five or more scenes, so it shows in videos of a minute and longer; those were not planned here (cost), only removed in code and covered by tests.
* **After**: 5 whiteboard, 6 footage, 1 conversation, each with a reason written for that video (a stock sentence where only one direction was allowed). Every plan was 100 % in its direction as written; nothing needed repair in these 12.
* A footage video has two systems by design (real media and our graphics).
* Cost of the 12 plans: USD 1.38 before, USD 0.79 after (fewer whiteboard videos, each of which pays for a board review).
* Not measured: whether people prefer the new choices. For children the director now tends to real footage for animals and a conversation for "why" questions; the owner should look at `look_f_auto_sky_conversation.mp4`.

## QA videos (made through the API, 45 s, 16:9, 1080p; `~/Downloads/videomk-looks/web/look_*.mp4`, `captions_look.json` has the exact request and what is wrong with each)
| File | Request | Result | Share in look | Repaired |
|---|---|---|---|---|
| look_a_whiteboard_eiffel | look whiteboard, "The history of the Eiffel Tower" (auto never picks the whiteboard for history) | every scene a board | 100 % | 0 |
| look_b_cartoon_owl_volcanoes | look cartoon, cast [owl] | Hugo in every scene, one backdrop, cards | 100 % | 1 |
| look_c_conversation_fox_bear_sleep | look cartoon, cast [fox, bear], for children | both on screen throughout, a dialogue in two voices | 100 % | 0 |
| look_d_turtle_board_plants | look cartoon, cast [turtle], extras [board] | Tula beside a board drawn as she speaks | 100 % | 0 |
| look_e_auto_japan_footage | auto, "Top 5 places to visit in Japan" | footage | 100 % | 0 |
| look_f_auto_sky_conversation | auto, "Why is the sky blue? For young children" | conversation, fox and owl, reason recorded | 100 % | 0 |
| look_g_local_conversation_board_rain | look cartoon, cast [fox, bear], extras [board] (laptop render, same engine code) | two characters either side of a hand-drawn board | 100 % | 0 |

## Render cost
* **QA Lambda** (`v2_render_chunk`, 10 GB, 600 s limit; the six videos above, 37 render pieces): a piece is at most 150 frames (5 s) in any video with a cartoon backdrop (the cap that existed for cartoon scenes now also applies when a character stands in front of one: `timeline_handler`). Pieces took 65 to 137 s (the slowest were two figures and the board video: about 0.9 s a frame), peak memory 0.77 to 1.21 GB. So the slowest piece used 23 % of the time limit. Whole videos: 140 to 175 s from request to finished.
* **Laptop, 1080p, per frame after the first** (busy machine): two figures with a card on a backdrop 123 ms, two with the board 139 ms, three with a card 122 to 128 ms, one with the board 135 ms; without a backdrop three figures and a board 56 ms. The backdrop is the largest part; a third figure adds a few ms. 9:16 is slower (172 to 199 ms: more pixels of backdrop). Peak memory of a whole local conversation video: 609 MB.
* **Three figures were not run on Lambda** (only locally): from the local ratio expect about the same as two (under 150 s a piece).
* Turned pieces are cached per character as before (4 characters, 48 MB each): three fit.

## Weak points (looked at the frames)
* **Boards beside characters are sparse**: 3 to 6 things each, and every scene that shows something new starts a fresh board; the full whiteboard look fills a board over two or three scenes, this does not yet. Stand-in drawings as in the whiteboard look (a heart for oxygen).
* **A conversation's lines are 10 to 20 words** (5 to 9 s): turn-taking, not banter. The short-form beat budget (4 to 5 beats in 45 s) limits it; longer videos get about one line per 6 s.
* **Listeners only look and rarely nod**: the rig has no head turn or eyebrows. A cut between two lines restarts each figure's idle sway.
* **One backdrop per conversation**, one or two per presenter video: 45 s in front of the same picture. The card hides the middle of the backdrop.
* **9:16** shows whole small figures under the content (the known weakest shape); 1:1 and 4:5 put the row above the caption band. Only 16:9 was made on QA; the other shapes were looked at as single local frames.
* **Three-character conversations and `conversation_board` were rendered locally only**; a chosen look on a video over a minute (the staged writer) was not run.
* The auto reason is a stock sentence when only one direction is allowed.
* Capabilities is 155 KB on QA: the ten face thumbnails are in both `looks.presenter.cast` (older apps) and `looks.cast.members`.
* The phone editors do not know the new props (`cast`, `board`, `talk`, `held`): such scenes are read-only there, as presenter scenes already were. Editing the narration of a board scene does not re-tie its board.

## Try it locally
```
AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/presenter_local.py "Why does it rain? For young children" out_dir --seconds 40 --look cartoon --cast fox,bear --board
```
