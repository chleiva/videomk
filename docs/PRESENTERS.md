# Presenters: cartoon characters in real videos (2026-11-27)

**Since 2026-11-28** a video's look is one decision (`docs/ART_DIRECTION.md`): a presenter is no longer added to a third of the scenes of an ordinary video. A video with characters is a cartoon-look video (the character in every scene, or a conversation of two or three on screen together, optionally beside a hand-drawn board); "How often" and "Dialogues" below describe the behaviour before that.


Status: built behind the server switch `PRESENTERS` (QA on in `stages.json`, production off). Not deployed. Ten characters: four people, Inés (teacher), David (engineer), Priya (doctor), Mateo (chef), and six animals, Fox (guide for children), Hugo (owl professor), Bruno (bear), Mika (cat), Paco (parrot), Tula (turtle): see "Animal presenters" below. The rig and the gestures are the ones the owner reviewed (`docs/CHARACTER_ANIMATION_PROOF.md`, `docs/CHARACTER_LIBRARY.md`); this note is how they get into a video.

## What a person gets
A video with a presenter is an ordinary video in which a few scenes show the character: it opens the video beside the question, comes back for the key points, and closes with the takeaway. It speaks the narration in its own voice with automatic gestures (wave on "hello", fingers on "first, second, third", the open hand toward the card on "look" and "this", a shrug or two hands on a contrast). The other scenes stay photographs, clips, diagrams and cartoon scenes while the same voice goes on.

## Asking for one
| How | What happens |
|---|---|
| Words in the request: "with a presenter", "with a character", "animated characters", "explained by a fox", "explained by an owl", "by a cat", "con un presentador", "con personajes", "explicado por un zorro", "explicado por un oso", "con un búho", "con un loro", "con una tortuga", "con una doctora como presentadora" | A presenter; a named kind of character (fox, owl, bear, cat, parrot, turtle, teacher, engineer, doctor, chef, and the Spanish words: zorro, búho or lechuza, oso, gato, loro, tortuga) is that character. An animal of the cast named at the END of the request ("Why the sky is blue, with an owl", "Los planetas, con un búho") is the presenter; in the middle of a sentence ("a story with a bear who loses his hat") it is the subject of the video |
| `"presenter": "<id>"` in `POST .../videos/generate` (`ines`, `david`, `priya`, `mateo`, `fox`, `owl`, `bear`, `cat`, `parrot`, `turtle`) | That character. The option wins over the words |
| `"presenter": "none"`, or "no presenter" / "sin presentador" | Never |
| nothing, or `"presenter": "auto"` | Only where it fits: the director's kind of video is a children's or fun explainer or a tutorial (`kids-family`, `funny-light`, `tutorial-howto`, `coding-tutorial`). Everything else gets none by itself |

Never, not even when asked: a video of the person's own photos, a deck, a whiteboard video, current events (web research) and the serious kinds (`news-explainer`, `mystery-true-crime`, `biography-profile`, `recap-summary`). The request check tells the person in its `note` ("Made as ...: presenter characters are not used for news and real events."), see `docs/CREATE_API.md` "Looks". Any other value of `presenter` is a 400.

**Capabilities** (`GET .../capabilities`, `looks.presenter`, labels in the `X-Locale` language):
```json
"presenter": {"param": "presenter", "default": "auto", "available": true,
  "options": [{"id": "auto", "label": "Auto", "note": "A presenter only where it fits: children's and fun explainers, tutorials."},
              {"id": "none", "label": "No presenter", "note": "Never a character on screen."}],
  "cast": [{"id": "ines", "name": "Inés", "role": "Teacher", "thumbnail": "data:image/png;base64,..."}, {"id": "david", "name": "David", "role": "Engineer", ...},
           {"id": "priya", "name": "Priya", "role": "Doctor", ...}, {"id": "mateo", "name": "Mateo", "role": "Chef", ...}, {"id": "fox", "name": "Fox", "role": "Guide for children", ...},
           {"id": "owl", "name": "Hugo", "role": "Owl professor", ...}, {"id": "bear", "name": "Bruno", "role": "Caring bear", ...}, {"id": "cat", "name": "Mika", "role": "Curious cat", ...},
           {"id": "parrot", "name": "Paco", "role": "Travelling parrot", ...}, {"id": "turtle", "name": "Tula", "role": "Wise turtle", ...}],
  "say": "with a presenter", "note": "A cartoon presenter opens the video, explains the key points and says goodbye. ..."}
```
`available` follows the switch; where it is off the cast is still listed and `note` is "Presenter characters are coming soon." (hide or disable the choice). `thumbnail` is a 112 px PNG as a data URI (2.6 to 4.3 KB each, 43 KB for the ten; made by `backend/scripts/presenter_thumbs.py`, stored in `lambdas/common/presenter_thumbs.json`: no bucket). Spanish: `Automático`, `Sin presentador`, `Profesora`, `Ingeniero`, `Doctora`, `Chef`, `Guía para niños`, `Búho profesor`, `Oso cariñoso`, `Gata curiosa`, `Loro viajero`, `Tortuga sabia`, "con un presentador". The picker is `options` plus one entry per cast member (send its `id`).

## Casting and frequency (`engine/presenter_policy.py`; no model call)
* **Who**: the character asked for. Else a children's or fun video (`kids-family`, `funny-light`, or words like "for kids", "para niños") gets an ANIMAL by the topic's words, first match in this order: Bruno the bear (health, feelings, worries, bedtime, sleep, teeth), Mika the cat (technology, robots, computers, machines, "how ... works", "cómo funciona"), Paco the parrot (languages, travel, countries, fun facts, "datos curiosos"), Tula the turtle (nature, the sea, rivers, forests, plants, recycling, step by step, "how to"), Hugo the owl (learning, school, science, history, numbers, planets, dinosaurs); when no topic decides, Paco in a Spanish children's video and the Fox everywhere else. Every OTHER video keeps a person exactly as before the animals: by the topic's words (food: Mateo; health and the body: Priya; software and technology: David); else by the kind of video; else Inés. An animal presents an adult topic only when asked for by name.
* **Voice**: the narrator's voice becomes the character's (EN: Inés Ruth, David Matthew, Priya Kajal, Mateo Stephen, Fox Joanna, Hugo Brian (calm, British), Bruno Stephen (soft), Mika Olivia, Paco Nate, Tula Amy; ES: Lupe, Pedro, Mia, Andres, Lucia, Hugo Sergio, Bruno Andres, Mika Mia, Paco Pedro (second choice Sergio), Tula Lupe).
* **Dialogues**: with two or three speaking characters the first two speakers each get a presenter (the cast one, and another of the same kind: an animal talks with an animal, a person with a person), one on the left and one on the right, each with their own voice. One figure is on screen at a time (whoever speaks); there is no two-shot yet.
* **How often**: about one beat in three, at least two (the opening and the closing), never two in a row. The director is told so in its prompt; `enforce` then holds it: a presenter scene beyond the cap becomes the plain scene that shows the same thing (list, chart, photograph), and a text card the director wrote as the first or last beat becomes a presenter scene.
* **Cartoon scene behind**: in a video where the cartoon-scene policy offered scenes (children's topics), the opening and the closing stand in front of one of them (`backdrop`).
* Recorded in the plan: `plan.presenter` = `{decision, reason, asked, character, scenes, of, cast, voices}`.

## The scene (`engine/scenes/elements/presenter.py`, element `presenter`, hidden from the ordinary scene list)
Props from the director: `{heading (<=48), points: 0-4 (<=60)}`, or `{heading, chart: {labels 2-5, values, unit}}`, or `{heading, image_query}` (the picture is fetched at the beat stage through the same reviewed stock search as an `image` scene; no picture: the card stays). Set by the policy: `character`, `side`, `backdrop`. Set by the timeline (`presenter_policy.link`): `speech` (the scene's word timings), `enter`, `seed`.
* **Framing** hides what the rig cannot do (below): 16:9, 1:1 and 4:5 show the character from the waist up at one side with the content beside it and the gestures raised (`lift`) to work above the caption band; 9:16 shows the whole figure under the card, above the captions (the weakest shape: the figure is small).
* **Gestures** come from the words and their times (`engine/character_gestures.py`; how the arms move: "Arms" below), the **mouth** from the syllables of each word (the render has no audio; three mouth shapes exist), points and bars appear at the words that name them (the engine's usual anchoring).
* **Deterministic across chunks**: a frame is a pure function of the props and the scene time. The performance is planned from the words and a seed derived from the scene id; turned pieces are snapped to 0.5 degrees and 0.4 percent of scale (`vector_presenter.TurnCache`), so a frame is identical whether a piece came from the cache or not (test: same bytes after dropping every cache, in another order, and past the scene's end under a crossfade).
* **Bounded memory**: at most 4 rasterised characters, 48 MB of turned pieces each, 16 planned performances. Peak process memory of the local 1080p runs: 408 and 541 MB.
* **Never fails a render**: an unknown or unreadable character leaves the card alone.

## Arms (2026-11-27, branch `natural-arms`; not deployed)
The owner's review of the QA videos, the third time arms came up: "When the characters are bending their arms, it looks like sometimes they are bending it in the opposite way, almost like breaking the arms ... it feels like the arms just drop immediately ... the still needs to look more natural ... releasing their arms doesn't mean you let them drop." This section is what was wrong, the rules the arms now follow and where they come from, and the numbers. Code: `engine/vector_presenter.py` (the rig: bone angles, joint limits, the elbow rule), `engine/character_gestures.py` (rest, gestures, timing), `engine/scenes/elements/presenter.py` (`rooms`: how much space each hand has in the layout), `engine/arm_check.py` (the instrument), `scripts/presenter_arms.py` (run it, make the sheets). Tests: `tests/test_presenter_arms.py` (103), `tests/test_character_gestures.py` (50), `tests/test_vector_presenter.py` (69).

### What was wrong (found by measuring every frame, then by looking at them)
| What the owner saw | Cause, in the code before (`b56d544`) |
|---|---|
| "bending the opposite way, like breaking" | An arm was a WRIST target solved by IK with the elbow on a fixed side of the shoulder-to-wrist line (`vector_presenter.arm_ik`, lines 40-57), and the wrist path was pulled up to 38 % toward the body mid-way (`character_gestures._arc`, lines 397-405). Together: on the way up the upper arm swung INTO the chest (up to 27.6 degrees inward in the matrix, 35 with the first measurement) while the forearm swung out sideways from an elbow pressed into the ribs, like a windscreen wiper. 13.7 % of all frames of the matrix were in such a shape |
| the bend changes side | At rest the arm used fixed angles (elbow out, forearm in: the fix of 02b4fef), away from rest the IK solution (elbow in, forearm out), blended inside 30 % of the arm's length (`solve_arm`, lines 108-121): the elbow passed through straight and bent the other way on every departure and every return, 13,688 times in the matrix, at up to 1,680 degrees a second |
| "the arms just drop" | The return took 0.6 s (`RETRACT_S`), 0.44 s when the planner needed room (`_fit`), on a steep S-curve; because of the pulled-in path the forearm turned at up to 1,680 degrees a second and the wrist fell at 5.1 arm lengths a second. A limp arm let go from the horizontal reaches about 7 |
| "the still needs to look more natural" | At rest both arms were the same straight pose and did not move: the idle sway moved the wrist TARGET by 1 % of the arm, which inside the rest zone gives back the home angles. Measured: 0.01 to 0.21 degrees of movement in 3 s. Every scene also restarted the idle life (seed per scene, scene time), so breath and weight jumped at each cut of a conversation |
| hands over the card | The key poses put the wrist 0.62 to 0.90 arm lengths out to the side whatever stood there: in the 16:9 two-shot and three-shot a hand was over the card's text or the neighbour in 580 of 13,818 frames |
| not a cause | The mirror: both arms and both sides of a conversation use one rule mirrored (now pinned by a test). The draw order (torso, upper arms, head, hands, forearms) was right. Bones never changed length |

### The rules, and where they come from
Speakers (what coaches teach, and what gesture research describes):
* **A home base, and a return to it.** Between gestures the hands go back to a relaxed rest: arms loose at the sides, or hands loosely together at waist height; the mark of a good rest is the absence of tension, and hands that never stop moving make the important gestures impossible to tell from filler ([Science of People](https://www.scienceofpeople.com/what-to-do-with-hands/), [Buckley School](https://buckleyschool.com/magazine/articles/frequently-asked-what-should-i-do-with-my-hands), [Toastmasters, "What a nice gesture"](https://www.toastmasters.org/magazine/magazine-issues/2020/may/what-a-nice-gesture)). Here: four relaxed poses at the sides (elbows a little out, never a straight stick) that each arm drifts between every 8 to 16 s, the two arms at different moments; a LISTENER holds its hands together in front of the belly (all but the fox, whose forearms are too short and would cross).
* **The gesture box.** Gestures live between the waist and the shoulders, about as wide as the body, in front of it; lower they are lost, higher only for a greeting ([Toastmasters, "7 hand gestures"](https://www.toastmasters.org/magazine/magazine-issues/2021/june/7-hand-gestures), [Genard Method](https://www.genardmethod.com/blog/what-should-i-do-with-my-hands-a-speakers-guide-to-gestures), [Ethos3](https://ethos3.com/?p=48809), [Effective Presentations](https://effectivepresentations.com/?p=29648)). Here: elbows near the body, forearms up and out, hands at chest height; only the wave goes beside the head.
* **Open palms, nobody points; fingers count.** Same sources. Here: open hand for everything but a count (one, two, three fingers, forearm upright) and a thumb.
* **Preparation, stroke, hold, retraction; the stroke belongs to its word.** Kendon's phases of a gesture and the post-stroke hold that keeps the gesture with the words it goes with ([Haviland, "Different strokes"](https://pages.ucsd.edu/~jhaviland/Publications/DifferentStrokes2ndProof.pdf), [MIT Speech Communication, "Co-speech gesture"](https://speech.mit.edu/?p=49); Kendon, *Gesture: Visible Action as Utterance*, 2004; McNeill, *Hand and Mind*, 1992, for the stroke falling on the stressed syllable: taken from the book, not found restated online). Here: the stroke lands 0.06 s before its word starts and is held (0.45 to 1.9 s); the only late strokes are on the first word of a scene that fades in over another (up to 0.45 s late).
* **Not on every sentence, never two the same in a row, size to the idea.** Here: at most 13 a minute and 60 % of the talk with a hand up; emphasis is skipped three times in ten; a speaker who has had nothing to gesture about for 4 s gives the next stressed word ONE open hand, hands in turn. All from the words and a seed: the same plan gives the same performance.
* **Asymmetry.** Two hands doing the same thing in step reads as flapping. Here: one hand leads by 0.13 s, the two land on different poses (12 to 13 degrees apart) and the second lets go 0.25 s later.

Animators (the principles for arms):
* **Arcs, slow in and slow out, anticipation, overshoot and settle** (Thomas and Johnston, *The Illusion of Life*, 1981; [the twelve principles](https://people.wku.edu/joon.sung/edu/anim/3d/theory/principles.html)). Here: the arm turns about shoulder and elbow, so every hand path is an arc; a 3 % wind-up the other way; 4.5 % past the pose and back as it lands; 2 % past rest and back as it comes home.
* **Follow through, overlapping action, successive breaking of joints** ([Follow through and overlapping action](https://en.wikipedia.org/wiki/Follow_through_and_overlapping_action), [Brian Lemay's notes](https://www.brianlemay.com/Pages/animationschool/animation/1stsemesteranimation/successivebreaking.html); Williams, *The Animator's Survival Kit*, not checked online). Here: the upper arm leads the forearm by a frame on the way up and follows it on the way down, the hand trails the forearm by up to 13 degrees and catches up. Done on a flat puppet this must never read as a broken arm, hence the elbow rule below.
* **A moving hold**: a pose that is held still moves a little, or it dies (same sources). Here: a held hand drifts 1.4 degrees; at rest the forearm sways about 2 degrees over 5 s with the breath and the weight shift (measured: 0.7 to 16 degrees in any 3 s, never under 0.5).

The rig's own rules (what a flat, front-facing cut-out arm needs so that it looks like an arm; ours, justified by the frames):
* **Bone angles, not wrist targets.** A pose is (upper arm, forearm, wrist) in degrees from hanging, positive away from the body. Bones cannot stretch, an elbow cannot change side by accident, and joint limits hold whatever is asked: upper arm never further in than 6 degrees (never across the chest), elbow between -150 (forearm across the body) and +150 (folded up), wrist 45.
* **The elbow goes out with the forearm** (`elbow_need`): a forearm at 60 degrees needs the upper arm 19 degrees out, falling to 2 for a forearm that is up. The arm lifts as a whole with a soft elbow; a forearm sticking out of the ribs cannot be drawn.
* **Through straight only low and slowly**: the elbow may change the side it bends to only while the upper arm is under 38 degrees and the bend changes slower than 300 degrees a second (it happens as an arm leaves rest, where a straight arm is natural).
* **The way home is longer than the way up** and slowest at the end: the forearm averages 200 degrees a second up and 132 down (top speed 1.4 to 1.5 times that), 0.6 to 0.94 s up and 0.92 to 1.3 s down depending on how far the arm goes.
* **Never by way of rest when there is no time to rest**: a gesture that starts before the arm would be home, or less than 0.9 s after, takes the arm over from the pose it is in.
* **Room** (`presenter.rooms`): each hand knows how far it may go before it covers the card's text (the card's 36-unit margin may be touched), the board, a neighbour or leaves the picture. A held pose folds the forearm up until the whole hand fits. An arm without the room to swing up beside the body (the bear between the frame's edge and the card in the 16:9 two-shot, everyone in the three-shot, a single presenter in 4:5) makes the same gestures IN FRONT of the body, hand before the chest, finger tips under the chin; a two-handed gesture is then made by one hand; a wave, a count or a thumb goes to the hand that has room.
* **No jump at a cut**: breath, weight, sway and the rest pose run on the VIDEO's clock with a seed per character; every gesture is home before its scene ends; a scene that fades in over another starts no gesture for 0.36 s; a listener that listens on both sides of a cut keeps its hands together across it.

### The instrument (`engine/arm_check.py`) and its numbers
Per frame and arm: shoulder, elbow, wrist, the three angles, the signed bend. Counted (frames), with the limits the tests hold:
| Class | What counts | Limit |
|---|---|---|
| wrong way | elbow inside the shoulder line (`tucked`); forearm out sideways from a hanging upper arm, more than 4 degrees short of the elbow rule (`wiper`); past a joint limit (`limit`); through straight while raised or fast (`flip`) | 0 frames |
| discontinuity | a segment faster than 400 degrees a second, a change of speed over 4,500 degrees a second squared, a wrist falling faster than 2.6 arm lengths a second, a pose that differs by more than 2 degrees across a cut | 0 frames |
| stretch | a bone more than 0.5 % off its length | 0 |
| penetration | the middle of a hand over the character's own face, across its centre line, over the card's text or the board, over another figure | 0 |
| twin | both arms moving the same way with the same angles (within 3 degrees, faster than 90 degrees a second) for 4 frames or more | 0 |
| dead | 3 s of rest in which neither bone turns 0.5 degrees, or the forearm turns more than 18 | 0 |

The matrix: 10 characters x (8 gestures x each hand x content on either side x low and raised framing = 60 cases; 64 ordered pairs of gestures x either side, the second after the first and, new, cutting into it; 4 spoken lines in English, Spanish and German x 3 seeds x either side x 2 framings; a listener on either side x 2 seeds), every frame at 30 a second. Whole scenes: 7 casts (fox+bear, bear+fox, owl, Inés, cat+parrot+turtle, David+Priya, Mateo+Inés+Priya) x 4 frame shapes through the element, five scenes each with the cuts between them.

| | Before (matrix, 588,760 frames) | After (the same cases, 627,880) | After (with cut-in pairs, 844,150) | Before (scenes, 55,272) | After (scenes, 55,272) |
|---|---|---|---|---|---|
| wrong way | 80,431 (tucked 55,090, wiper 71,650, flip 13,688) | 0 | 0 | 4,132 | 0 |
| discontinuity | 75,614 (speed 55,935, acceleration 46,076, drop 24,490) | 0 | 0 | 4,661 (224 at cuts) | 0 |
| stretch | 0 | 0 | 0 | 0 | 0 |
| penetration | 0 | 0 | 0 | 671 (hand over the card or a neighbour) | 0 |
| twin | 0 | 0 | 0 | 0 | 0 |
| dead rest | 54,000 (all of it) | 0 | 0 | 22,680 | 0 |
| fastest segment | 1,680 degrees a second | 389 | 389 | 1,621 | 364 |
| largest change of speed | 46,821 degrees a second squared | 3,506 | 3,506 | 42,056 | 3,468 |
| fastest falling wrist | 5.1 arm lengths a second | 2.4 | 2.4 | 4.7 | 2.3 |
| upper arm furthest in | 27.6 degrees into the chest | 1.7 out | 1.7 out | 27.3 in | 1.5 out |

Per character before (wrong way / discontinuity of 58,876 frames each): Inés 8,262 / 7,498, David 7,932 / 7,579, Priya 8,346 / 7,466, Mateo 7,178 / 7,889, Fox 7,472 / 7,784, Hugo 7,963 / 7,558, Bruno 8,283 / 7,470, Mika 8,768 / 7,315, Paco 8,050 / 7,538, Tula 8,177 / 7,517. Per gesture before, alone (wrong way / discontinuity of the frames of its cases): wave 588 / 1,796 of 11,040, count 736 / 1,056, thumb 776 / 984, present 736 / 898, open 716 / 542 of 5,520, shrug 676 / 628, compare 450 / 420, the small beat at rest 4,358 / 304 of 11,040; pairs 41,578 / 35,554 of 243,920; speech 29,817 / 33,432 of 254,880; the listener 0 / 0 and all 18,200 frames dead. After: every cell 0. Twins and stretching were not defects of the old code by this measure (its two hands were 2 frames apart).

What the numbers do not say: the thresholds are ours (400 degrees a second, the elbow curve); "natural" was judged by looking at every frame of the clips below. The instrument checks the skeleton, not the paint: a hand SHAPE that changes size as it opens (the open hand is drawn larger than the relaxed one) is not counted.

### Render time
No change. The same windows rendered with the old and the new code on the laptop, 720p, one process: Inés alone 59 and 59 ms a frame, three characters 66 and 66, the 9:16 two-shot on a backdrop 220 and 220, the owl 80 and 67 (the 16:9 two-shot on a backdrop, 147 and 242, was measured while other jobs ran and is not used). The arm maths is a few hundred floating-point operations a frame; turned pieces are cached as before (the sway moves a bone by one cache step about four times a second). Not measured on Lambda: nothing suggests a change from the 65 to 137 s a piece in `docs/ART_DIRECTION.md`.

### Review files (`~/Downloads/videomk-looks/web/`, `captions_arms.json`)
`arms_fox_bear_conversation_de_before_after.mp4` (the German QA video's own timeline and voices, first 15 s), `arms_owl_alone_before_after.mp4`, `arms_human_ines_before_after.mp4`, `arms_three_cat_parrot_turtle_before_after.mp4`, `arms_fox_bear_9x16_before_after.mp4`, each with a poster; `arms_rest_poses.jpg` (ten characters in every rest pose), `arms_gesture_sheet.jpg` (every gesture beside the body and in front of it); `arms_before_after_frames.jpg` (the same shrug frame by frame, old above new).

### What still looks unnatural, and what was not verified
See `captions_arms.json` for each clip. In short: the open gesture hand is larger than the relaxed one, so a hand visibly grows as it opens and shrinks as it comes home; a flat arm lifting to the side passes through "arm out, low" on its way up, where a real arm would come up in front of the body; gestures in front of the chest hide the jumper's pattern and are the least expressive (the bear in the 16:9 two-shot has no others); held hands are two hand drawings laid over each other, not interlaced fingers; listeners still have no head turn. Not verified: the new arms on Lambda (the QA requests to make again are listed in the report of this work), 4K, and the three-character conversation with real voices (rendered here with estimated word times and no sound).

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

## Animal presenters (built 2026-11-27 on branch `animal-cast`; the owner approved the list and the cost)
Same house style and rig as the Fox, made with the same pipeline (`backend/scripts/vector_character_sheet5.py --animals`, `vector_character_build5.py --only <id>`, `vector_character_hands.py generate|build --only <id>`): one parts sheet and one hands sheet each, no retries, USD 0.3618 for the five (ledger `docs/vector_character_spend.jsonl`, runs `vector-character-animals` and `vector-character-hands`).

| id | Name | Role EN / ES | Look | Topics (children's and fun videos) | Voice EN / ES | Tail | Size |
|---|---|---|---|---|---|---|---|
| `owl` | Hugo | Owl professor / Búho profesor | chestnut feathers, cream face, round gold glasses, olive tweed waistcoat, bow tie | learning, science, history | Brian / Sergio | small fan behind one hip | 0.92 MB |
| `bear` | Bruno | Caring bear / Oso cariñoso | honey-brown, teal knitted jumper with a cream zigzag | health, feelings, bedtime | Stephen / Andres | none | 0.70 MB |
| `cat` | Mika | Curious cat / Gata curiosa | grey tabby, orange hoodie, sneakers | technology, how things work | Olivia / Mia | striped, sways | 0.77 MB |
| `parrot` | Paco | Travelling parrot / Loro viajero | scarlet macaw, yellow neckerchief, blue feathered hands | languages, travel, fun facts; the default in a Spanish children's video | Nate / Pedro | long red feathers | 0.87 MB |
| `turtle` | Tula | Wise turtle / Tortuga sabia | green, cream belly plate, shell behind, backpack straps | nature, the sea, step by step | Amy / Lupe | small point | 0.71 MB |

How an animal differs from a person on the rig (all recorded in the build scripts, so a rebuild from the sheets gives the same character):
* **Wings are arms** ending in hands that form the six shapes. **A beak is the mouth piece** (the head is drawn blank): `manifest.json` `"face": {"mouth_anchor": "top"}` hangs it from its top edge so it opens downward. `"face"` also sets where the eyes and mouth sit and how wide they are (`eyes_y`, `eyes_w`, `mouth_y`, `mouth_w`); without it the old defaults apply (the people and the Fox are unchanged).
* **The turtle's shell is part of the torso piece**; `presenter.json` `shoulder_x` hangs the arms from the body in front of it. The owl and the bear also set `shoulder_x` (their torso is much wider at the ribs than at the shoulders).
* **Fixes the builder applies** (`vector_character_build5.py`): the owl's waistcoat notch filled with the trouser colour (the backdrop showed between the legs), the parrot's upper arm made plain red (the sheet repeated the colour bands on both arm pieces), the turtle's nostrils painted over (they sat where the mouth goes); the cat's gesture hands are drawn 1.3 times larger (`vector_character_hands.py` `HAND_K`).
* **Thumb sides** were read by eye from each forearm drawing (`RELAXED_THUMB`: parrot +1, the others -1) and are pinned by `tests/test_vector_presenter.py`.

Adding another: its prompt in `sheet5.ANIMALS` and `hands.ANIMAL_WHO` (and `TAILS`), its face and meta in `build5`, one entry in `presenter_policy.CAST` / `ORDER` / `ANIMALS` (and `KIDS_TOPICS` if it has topics), in the element's `CAST`, in `looks.PRESENTER_WORDS` and `_ANIMAL_CAST`, the test casts, then `presenter_thumbs.py`. The launcher reads its ids from the policy.

Review files: `~/Downloads/videomk-looks/web/animal_<name>_talk.mp4`, `animal_<name>_poses.jpg`, `animal_cast_all.jpg`, `captions_animals.json` (`vector_character_presenter_demo.py --talk --only <id>`, `--animals` for the group still).

Honest rating against the Fox: Bruno and Mika are as good; Hugo and Paco are close (Hugo's hands are glove-like rather than feathered and his tail fan is busy when small; Paco's legs are plain red tubes); Tula is the weakest (a plain dome head, thin arms, the arms cover the shell's rim at rest, and her 112 px face thumbnail is a green head with no shell in it). None was seen in a real pipeline video yet, only in the demo clips; the voices were chosen from the catalog's descriptions and not listened to.

## Running one locally
```
AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/presenter_local.py "Explain why the sky is blue, with a presenter" out_dir --seconds 45
```
Same code as the Lambdas (director, Polly, alignment, timeline, chunk render); clip beats show a still, no music. The two review videos: `~/Downloads/videomk-looks/web/pres_local_sky.mp4`, `pres_local_fox.mp4` (`captions_pres.json`).

## Infra
One environment variable, `PRESENTERS=1`, on the engine functions, capabilities, the request check and the launcher (`stages.json` `"presenters": true`, or `-c presenters=1`). No new function, route, table, bucket or policy statement: the characters ship inside the engine code (about 7.6 MB of SVG for the ten). A test asserts the resource count is unchanged.

## Not done
* Not deployed, not run on Lambda (render time there is an estimate), not tried at 4K.
* The apps have no picker yet (capabilities is ready); the phone editors do not know the `presenter` scene (it would be read-only there). Editing a video that has a presenter keeps its scenes (the plan gate reads `plan.presenter`), verified by a unit test only, not through the editor Lambdas.
* A dialogue shows one speaker at a time; no listener in the shot.
* No model-based check that a presenter suits the request on `auto` (rules by kind of video only); long staged videos get the prompt block but were not run.
* The `image_query` variant (a picture beside the presenter) is covered by unit tests of the props and the local runner's path, but neither review video used it and its beat-stage fetch has not run on Lambda.
* The local videos were reviewed from contact sheets and stills, not listened to.
