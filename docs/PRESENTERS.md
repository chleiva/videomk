# Presenters: cartoon characters in real videos (2026-11-27)

Status: built behind the server switch `PRESENTERS` (QA on in `stages.json`, production off). Not deployed. Five characters: Inés (teacher), David (engineer), Priya (doctor), Mateo (chef), Fox (guide for children). The rig and the gestures are the ones the owner reviewed (`docs/CHARACTER_ANIMATION_PROOF.md`, `docs/CHARACTER_LIBRARY.md`); this note is how they get into a video.

## What a person gets
A video with a presenter is an ordinary video in which a few scenes show the character: it opens the video beside the question, comes back for the key points, and closes with the takeaway. It speaks the narration in its own voice with automatic gestures (wave on "hello", fingers on "first, second, third", the open hand toward the card on "look" and "this", a shrug or two hands on a contrast). The other scenes stay photographs, clips, diagrams and cartoon scenes while the same voice goes on.

## Asking for one
| How | What happens |
|---|---|
| Words in the request: "with a presenter", "with a character", "animated characters", "explained by a fox", "con un presentador", "con personajes", "explicado por un zorro", "con una doctora como presentadora" | A presenter; a named kind of character (fox, teacher, engineer, doctor, chef, and the Spanish words) is that character |
| `"presenter": "<id>"` in `POST .../videos/generate` (`ines`, `david`, `priya`, `mateo`, `fox`) | That character. The option wins over the words |
| `"presenter": "none"`, or "no presenter" / "sin presentador" | Never |
| nothing, or `"presenter": "auto"` | Only where it fits: the director's kind of video is a children's or fun explainer or a tutorial (`kids-family`, `funny-light`, `tutorial-howto`, `coding-tutorial`). Everything else gets none by itself |

Never, not even when asked: a video of the person's own photos, a deck, a whiteboard video, current events (web research) and the serious kinds (`news-explainer`, `mystery-true-crime`, `biography-profile`, `recap-summary`). The request check tells the person in its `note` ("Made as ...: presenter characters are not used for news and real events."), see `docs/CREATE_API.md` "Looks". Any other value of `presenter` is a 400.

**Capabilities** (`GET .../capabilities`, `looks.presenter`, labels in the `X-Locale` language):
```json
"presenter": {"param": "presenter", "default": "auto", "available": true,
  "options": [{"id": "auto", "label": "Auto", "note": "A presenter only where it fits: children's and fun explainers, tutorials."},
              {"id": "none", "label": "No presenter", "note": "Never a character on screen."}],
  "cast": [{"id": "ines", "name": "Inés", "role": "Teacher", "thumbnail": "data:image/png;base64,..."}, {"id": "david", "name": "David", "role": "Engineer", ...},
           {"id": "priya", "name": "Priya", "role": "Doctor", ...}, {"id": "mateo", "name": "Mateo", "role": "Chef", ...}, {"id": "fox", "name": "Fox", "role": "Guide for children", ...}],
  "say": "with a presenter", "note": "A cartoon presenter opens the video, explains the key points and says goodbye. ..."}
```
`available` follows the switch; where it is off the cast is still listed and `note` is "Presenter characters are coming soon." (hide or disable the choice). `thumbnail` is a 112 px PNG as a data URI (2.7 to 4.3 KB each; made by `backend/scripts/presenter_thumbs.py`, stored in `lambdas/common/presenter_thumbs.json`: no bucket). Spanish: `Automático`, `Sin presentador`, `Profesora`, `Ingeniero`, `Doctora`, `Chef`, `Guía para niños`, "con un presentador". The picker is `options` plus one entry per cast member (send its `id`).

## Casting and frequency (`engine/presenter_policy.py`; no model call)
* **Who**: the character asked for; else the Fox for children's and fun videos; else by the topic's words (food: Mateo; health and the body: Priya; software and technology: David); else by the kind of video; else Inés.
* **Voice**: the narrator's voice becomes the character's (EN: Inés Ruth, David Matthew, Priya Kajal, Mateo Stephen, Fox Joanna; ES: Lupe, Pedro, Mia, Andres, Lucia).
* **Dialogues**: with two or three speaking characters the first two speakers each get a presenter (the cast one, and another), one on the left and one on the right, each with their own voice. One figure is on screen at a time (whoever speaks); there is no two-shot yet.
* **How often**: about one beat in three, at least two (the opening and the closing), never two in a row. The director is told so in its prompt; `enforce` then holds it: a presenter scene beyond the cap becomes the plain scene that shows the same thing (list, chart, photograph), and a text card the director wrote as the first or last beat becomes a presenter scene.
* **Cartoon scene behind**: in a video where the cartoon-scene policy offered scenes (children's topics), the opening and the closing stand in front of one of them (`backdrop`).
* Recorded in the plan: `plan.presenter` = `{decision, reason, asked, character, scenes, of, cast, voices}`.

## The scene (`engine/scenes/elements/presenter.py`, element `presenter`, hidden from the ordinary scene list)
Props from the director: `{heading (<=48), points: 0-4 (<=60)}`, or `{heading, chart: {labels 2-5, values, unit}}`, or `{heading, image_query}` (the picture is fetched at the beat stage through the same reviewed stock search as an `image` scene; no picture: the card stays). Set by the policy: `character`, `side`, `backdrop`. Set by the timeline (`presenter_policy.link`): `speech` (the scene's word timings), `enter`, `seed`.
* **Framing** hides what the rig cannot do (below): 16:9, 1:1 and 4:5 show the character from the waist up at one side with the content beside it and the gestures raised (`lift`) to work above the caption band; 9:16 shows the whole figure under the card, above the captions (the weakest shape: the figure is small).
* **Gestures** come from the words and their times (`engine/character_gestures.py`), the **mouth** from the syllables of each word (the render has no audio; three mouth shapes exist), points and bars appear at the words that name them (the engine's usual anchoring).
* **Deterministic across chunks**: a frame is a pure function of the props and the scene time. The performance is planned from the words and a seed derived from the scene id; turned pieces are snapped to 0.5 degrees and 0.4 percent of scale (`vector_presenter.TurnCache`), so a frame is identical whether a piece came from the cache or not (test: same bytes after dropping every cache, in another order, and past the scene's end under a crossfade).
* **Bounded memory**: at most 4 rasterised characters, 48 MB of turned pieces each, 16 planned performances. Peak process memory of the local 1080p runs: 408 and 541 MB.
* **Never fails a render**: an unknown or unreadable character leaves the card alone.

## Render cost (measured on the owner's laptop, 1080p, one process; not yet measured on Lambda)
* The standalone rig: 26 ms per frame at 1080p, 85 percent of it turning pieces. With the cache the hit rate over a talking scene was 82 percent.
* A whole presenter frame (background, card, character, captions) against a plain list scene, same run: 73 ms against 55 ms; under load 94 against 62. So **a presenter scene costs about 20 to 30 ms per frame more than a text scene**.
* "Why is the sky blue" (45.4 s, 24 s of it presenter scenes): 127 s of rendering in three chunks, 68 to 120 ms per frame.
* **A 60 s video** with a presenter on screen a third to a half of the time: about 1,800 frames, 600 to 900 of them presenter frames, so 12 to 27 s of extra rendering in total on this machine, on top of about 2 minutes. On Lambda chunks are 10 s (300 frames) and run in parallel: a chunk that is all presenter is about 30 s here; at a third of this laptop's speed it is about 90 s against the render function's 10 minute limit. The wall time of a video does not grow, the compute grows by a few percent. 4K is not measured: the pieces are four times as large, so treat presenters at 4K as untested.
* The second local run's timings (120 to 239 ms per frame) were taken while another render was running and are not used here.

## Rig limits and how they are kept out of sight
| Limit | What is done about it |
|---|---|
| Flat, front-facing puppet; no turning, no three-quarter view | The character always faces the viewer and gestures toward the content with an open hand; it never has to look at the card |
| Hands turn only in the picture plane; six hand shapes | Only gestures that read flat: wave, count, present, thumb, open palms, shrug |
| Legs: one straight piece each, no walk | Waist-up framing in 16:9, 1:1, 4:5; entrance by a short slide. Only 9:16 shows the legs |
| Three mouths, no eyebrows | Short presenter scenes with the card carrying the content; faces are not held in close-up |
| Raised white or thick sleeves (Priya, Mateo, Inés) | Low gestures are lifted only a little; the wave is the only gesture above the head |

**Art that would lift the quality** (in order of effect): 5 to 6 mouth shapes and eyebrow pieces (expression); a three-quarter head and torso (turning toward the content); sleeves built into a round-shouldered torso (clean raised arms); a second relaxed hand per side; a seated or desk variant for 9:16. About 3 sheets per character (about $0.11 to $0.17).

## More animal presenters (proposal: NOT generated; needs the owner's yes)
The owner asked for animals that explain things; only the Fox exists. Proposed, same style and rig: **owl professor** (learning, science, history), **bear** (health, feelings, bedtime), **cat** (technology, how things work), **parrot** (languages, travel, fun facts), **turtle** (nature, the sea, step by step). Cost through the existing pipeline: one parts sheet (about $0.036) and one hands sheet (about $0.035) per character, about $0.36 for five; with one retry each at most about $0.75. Wings must be drawn as arms with feathered hands, the turtle's shell as part of the torso; each needs the rest-pose check of `docs/CHARACTER_LIBRARY.md`. Suggested order: owl and bear first, look, then the rest. Adding one is: its folder under `engine/assets/vector_characters/`, one entry in `presenter_policy.CAST` and in the element's `CAST`, the id in `sf_launcher`'s list, `presenter_thumbs.py`.

## Running one locally
```
AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/presenter_local.py "Explain why the sky is blue, with a presenter" out_dir --seconds 45
```
Same code as the Lambdas (director, Polly, alignment, timeline, chunk render); clip beats show a still, no music. The two review videos: `~/Downloads/videomk-looks/web/pres_local_sky.mp4`, `pres_local_fox.mp4` (`captions_pres.json`).

## Infra
One environment variable, `PRESENTERS=1`, on the engine functions, capabilities, the request check and the launcher (`stages.json` `"presenters": true`, or `-c presenters=1`). No new function, route, table, bucket or policy statement: the characters ship inside the engine code (about 3.6 MB of SVG for the five). A test asserts the resource count is unchanged.

## Not done
* Not deployed, not run on Lambda (render time there is an estimate), not tried at 4K.
* The apps have no picker yet (capabilities is ready); the phone editors do not know the `presenter` scene (it would be read-only there). Editing a video that has a presenter keeps its scenes (the plan gate reads `plan.presenter`), verified by a unit test only, not through the editor Lambdas.
* A dialogue shows one speaker at a time; no listener in the shot.
* No model-based check that a presenter suits the request on `auto` (rules by kind of video only); long staged videos get the prompt block but were not run.
* The `image_query` variant (a picture beside the presenter) is covered by unit tests of the props and the local runner's path, but neither review video used it and its beat-stage fetch has not run on Lambda.
* The local videos were reviewed from contact sheets and stills, not listened to.
