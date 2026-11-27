# Character animation proof (2026-11-27)

Owner's question: before more characters are generated, show how they will be animated. "If they look very broken, there is no point generating more than one."
This note is the answer. Everything here was made with the four existing characters (mia, leo, nora, sam), CPU only, cached Polly lines, **no money spent**.

Reel: `character_animation_proof_reel.mp4` (1080p, 30 fps, about 66 s; 15 clips, each with a burned-in label that is for the proof only). For the actions that the new secondary motion
improves, the screen is split: **BEFORE** (the original rig) on the left, **AFTER** on the right, same character, same keyframes.
Joint close-ups at 100%: `joint_crops_100pct.png` (1 px = 1 px of the reel, each tile also shows a 3x enlargement).
Script: `backend/scripts/vector_character_proof.py` (`--measure` prints the numbers below, `--joint-strip` the crops, `--stills name:t` single frames).

## Second pass: the speaker (2026-11-27, after the owner's review)

The owner looked at the five-character clips and said: the characters look nice, but the legs look like everybody is sitting, the arms are not natural, the hands need a natural style,
the motion should be natural by itself (no model deciding what to move), they are SPEAKERS so they should stand and gesture like good speakers, and they do not need to walk.
This pass does exactly that. Same art, a second rig and an automatic gesture system. Clips: `~/Downloads/videomk-looks/web/char2_*` (captions in `captions_char2.json`).

### Verdict of this pass

1. **The sitting look is gone.** It came from the rig, not from the art: the walking rig kept every knee bent (hip at 95.5% of the leg length means a 17 degree bend at hip and knee). The presenter rig has one straight fused piece per leg, feet planted and turned out, about hip width.
2. **Arms attach.** The sleeve now turns about the centre of its round cap, the elbow joint is inside both pieces, and the hand is its own piece at the wrist. No floating cap, no gap at any pose we could produce (tested in pixels at the extremes).
3. **Hands read.** Six shapes per character (relaxed, open palm, one, two, three, thumb up), drawn by the same image model in the same style, tinted to the character's exact skin colour. Nobody points with a finger: showing something is done with the open hand.
4. **Gestures are automatic and they make sense.** They come from the words and their timings only: a wave on "hello", fingers on "first / a, b and c", left hand then right hand on "but", open palms on a question, an open hand toward the content on "look at this". One per sentence, hands back at the sides in between.
5. **Still a puppet, honestly:** front-facing only, hands turn in the picture plane (no real palm-up), the feet are side-view shoes turned out, faces have three mouths and no eyebrow motion. See "What is still weak".

### What good speakers do (research, short)

Presenter body language:
- **Stance:** feet planted about shoulder width, weight even, no swaying or pacing; to move, move on purpose, plant, then speak. A semi-relaxed, upright posture. [Toastmasters, "Back to the Basics: Gestures" (2023)](https://toastmasters.org/magazine/magazine-issues/2023/apr/back-to-the-basics-gestures), [U. Waterloo presentation guidelines](https://ece.uwaterloo.ca/~dwharder/Presentations/Guidelines/PresentationSkills/Composure/Stance/). (Soft, not locked, knees is common coaching advice; no page we read states it.)
- **Home base:** the hands need one place to return to. Most often: arms relaxed at the sides whenever the hands add nothing (Toastmasters 2023; [Buckley School](https://buckleyschool.com/magazine/articles/how-to-use-gestures-in-a-presentation)). Some coaches prefer hands loosely together at navel height ([Science of People](https://www.scienceofpeople.com/what-to-do-with-hands/)). We use the sides: it is the only one of the two a flat front-facing puppet can do without the forearms crossing the body.
- **Gesture box:** from the top of the chest to the bottom of the waist, about shoulder width; outside it gestures look frantic. Gesture away from the torso, not with elbows pinned. [Science of People, "Hand Gestures"](https://www.scienceofpeople.com/hand-gestures/), Buckley.
- **Open hands, never a pointing finger:** in a study of the same talk given by 8 lecturers, palms-up got 84% positive ratings, palms-down 52%, finger pointing 28% (as reported by Science of People; we did not read the original). Indicate with the whole open hand.
- **Numbers and contrasts:** show the number on the fingers when a number is said, count points off, give each side of a contrast its own hand. Give each main point its own gesture; both open hands for emphasis. (Science of People; Toastmasters 2023.)
- **Avoid:** hands in pockets, clasped ("fig leaf") or behind the back, crossed arms, shifting and pacing, circling hands, repeating one gesture, jerky pre-planned moves. (Toastmasters 2023, Buckley, Science of People.)
- **How many:** the best-rated TED talks averaged about 26 gestures a minute, the lowest about 15 (observational; [Science of People](https://www.scienceofpeople.com/secrets-of-a-successful-ted-talk)). About half of natural gestures are plain beats ([Cassell, Vilhjálmsson, Bickmore: BEAT, SIGGRAPH 2001](https://www.media.mit.edu/gnl/publications/siggraph2001.pdf)).
- **Timing:** a gesture has a preparation, a stroke, a hold and a retraction (Kendon); the stroke comes on or just before the stressed syllable, never after (McNeill). Measured: gesture apex within a few tens of ms of the pitch accent ([review](https://arxiv.org/pdf/1312.4640), [Loehr-type measurements](https://repositori.upf.edu/server/api/core/bitstreams/35c60503-71f3-45ff-acb1-115509e6309b/content)); so the preparation must start 0.3 to 0.45 s earlier.
- **Choosing gestures from text without a model** is an old, proven idea: BEAT (above) picks beats for new information, the two-hand "on one hand / on the other" for exactly two contrasted items, gaze toward the listener at the end of an utterance, and aligns the stroke with the word using the speech synthesiser's timings.

Animating cut-out characters so they feel alive (the classic principles applied to a rig):
- **Arcs, slow in and slow out, overlap and drag** (the forearm lags the upper arm, the hand lags the forearm), **anticipation**, **moving holds** (a character is never quite still). [StudioBinder on the 12 principles](https://www.studiobinder.com/blog/what-are-the-12-principles-of-animation/), [Adobe](https://www.adobe.com/creativecloud/animation/discover/principles-of-animation).
- **No twinning:** mirror-image arms with identical timing look flat; lead with one hand and offset the other by 2 to 4 frames. [Animator Island](https://www.animatorisland.com/defining-the-art-twinning/).
- **Idle life:** a breathing cycle with head shifts and small fidgets layered at different lengths ([AnimSchool](https://blog.animschool.edu/2024/06/14/breathing-life-into-idle-animations)); blinks 10 to 20 a minute, 100 to 150 ms, closing faster than opening ([Disney Research](https://la.disneyresearch.com/wp-content/uploads/Modeling-and-Animating-Eye-Blinks-Paper.pdf)).
- **IK where the hand has a goal** (present toward content, planted feet), plain rotation arcs for swings. Adobe Character Animator's own rig has the same pieces: breathing, auto-blink with randomness, limb IK with an elbow-flip threshold, lip sync from audio ([help page](https://helpx.adobe.com/adobe-character-animator/using/behaviors/body--auto-animating-.html), read from search results only).
- Not found: Duik, Moho, Spine or Toon Boom documentation (not needed for the decisions here).

### What changed

New files only; the first rig (`engine/vector_character.py`) and its tests are untouched and still pass.

| Part | Before | Now (`engine/vector_presenter.py`) |
|---|---|---|
| Legs | thigh + shin on a two-bone IK, knee always bent, side-view walk | one straight piece per leg, fused at load (thigh scaled to the shin's width at the knee, the inner outline removed), feet planted and turned out, hips about 107 units up; a weight shift tilts the legs by under 2 degrees with the feet fixed |
| Shoulder | sleeve hung from its top edge, the cap swung away when raised | pivot at the centre of the round cap, arm drawn over the torso: the cap stays on the shoulder at every angle |
| Elbow | angle keyframes | two-bone IK from a wrist target; the elbow is always on the same side of the shoulder-wrist line, so it cannot flip; reach clamped to 98.5% so the arm never locks or pops |
| Hand | part of the forearm, one sprite | own piece at the wrist (cut found automatically: cuff edge, or narrowest row on a bare forearm), tucked under the cuff, turns at the wrist; 6 shapes |
| Bones | piece drawn straight down | each piece is turned so its own pivot-to-end line lies on the bone (the art is never exactly vertical), so joints land where the maths says |
| Fox | no tail, gap at the waist | tail piece behind the body that sways; legs tucked under the waistcoat |
| Walking | walk cycle | removed. Entering: a 0.75 s slide with a lean into the move, a fade and a settle. Repositioning: a side step (leading foot lifts and lands, weight follows, other foot closes) |
| Framing | one size | `framing(preset, side, W, H)`: full, three_quarter, waist_up; left or right; any frame shape (wide: content beside; tall and square: content above) |

Hands and tail were generated with the existing pipeline (`scripts/vector_character_hands.py`, one sheet per character, cuffs cut off, tinted to the skin colour sampled from the character's own forearm, vectorised by the same tracer at 42% size to keep each character under 1 MB).

### The gesture system (`engine/character_gestures.py`)

Input: the words of the narration with their start and end times (from the audio, `engine.align`), optionally the loudness of each word, the side where the content is, a seed. Output: a pose for any time t. No model call, no state: the same input gives the same frames on any machine, in any order.

| Gesture | Chosen when (English and Spanish cue words) | What it looks like |
|---|---|---|
| wave | hello / hi / welcome / hola in the first sentence; thanks / bye / gracias / adiós in the last | hand up beside the head (the only gesture above the shoulders), the hand rocks about 2.3 times a second; uses the hand away from the content |
| count | a sentence that starts with first / second / third; a list "a, b and c"; a number 2 or 3 | forearm upright beside the shoulder, one, two, three fingers, each arriving on its word with a small pump |
| compare | but / however / instead / on the other hand / pero / sin embargo | one open hand for the first idea, the other hand comes up on the contrast word, the head tilts from one to the other; when the sentence opens with "but": the other hand alone |
| shrug | a question | both open hands out, shoulders up, head to one side |
| present | this / these / here / look / mira / aquí | the open hand of the content side reaches toward the content, a glance and a slight lean that way, eyes back to the viewer |
| thumb | great / perfect / exactly / genial | fist with the thumb up beside the shoulder |
| open | very / important / never / always / every / remember, or a sentence ending in "!" | both open hands at waist height ("setting it down") |
| beat | the most stressed content word of a sentence, about 3 in 4 times | at home: a small lift of one forearm with a wrist flick, the other hand answers faintly; during a held gesture: a small drop and return |
| nod | on most gesture strokes and beats, at most every 0.8 s | head dips 1.7 units with a slight squash |

Rules (each one is a test):
- at most one meaningful gesture per sentence; never the same one twice in a row (a running count is one idea); priority when a sentence offers several: wave, count, compare, shrug, present, thumb, open;
- phases: preparation about 0.42 s (longer for the high gestures), stroke 0.06 s before the word, hold until the phrase ends (0.45 to 1.9 s), return 0.6 s; gestures never overlap and the hands rest at least 0.2 s at home between them; when there is no room, the earlier hold is shortened, then the return is quickened a little, then the gesture is dropped;
- limits: 22 meaningful gestures a minute, hands away from home at most about 80% of the talk;
- path: the wrist travels on an arc about the shoulder (angle and radius are blended, not x and y) and folds toward the body on long ways; slow in and slow out, a small wind-up, a 5% overshoot that settles; the hand drags behind the forearm and catches up; the second hand of a two-handed gesture follows 75 ms later and 6% smaller;
- a finger or thumb shape appears only when the hand is nearly up (half way it would read as pointing);
- idle life, always on: breathing (3.7 to 4.3 s), irregular blinks (and often one as a gesture starts), weight from one foot to the other every 5 to 10 s over planted feet, a slow head sway, eye darts of two frames with the gaze on the viewer most of the time, arms that swing a hair with the weight;
- listening (`Performance.listen`): head and eyes toward the speaker, a small nod a beat after some of the speaker's stressed words, no gestures;
- `Performance.gesture(kind, time)` lets a scene ask for one (everybody waves at the end).

### What is still weak (exactly)

- **Hands do not rotate out of the picture plane.** "Palm up" is drawn as an open palm facing the viewer with the fingers along the forearm. It reads as an open hand, not as a cupped, offering palm.
- **Home base is arms at the sides only.** Hands loosely together at the navel needs a foreshortened forearm (pointing at the viewer), which flat pieces cannot do without the forearm crossing the body and the elbow flipping.
- **Feet:** side-view shoes turned out to left and right. It reads as standing; a drawn front-view shoe would be more correct.
- **Elbow shape on white sleeves** (Priya, Mateo): attached, but a bent arm is still two overlapping rounded pieces, and on white you can see that. A drawn elbow would hide it.
- **Thick sleeves** (Inés's cardigan, Mateo's short chef sleeve) make the upper arm look heavy when it is raised sideways.
- **Face:** three mouth shapes, no eyebrow motion, no smile change; the eyes move as a pair with the brows attached.
- **Beats** are small and all the same shape; the first cut had them too wide ("penguin"), they are now modest.
- **Cue words are a word list**, not understanding: "second" the unit of time is handled, but a list is recognised only as "a, b and c", and an unlisted word never triggers a gesture. A sentence with no cue gets a beat or nothing, which is the safe side.
- **Word timings** come from the audio by pause matching (accurate to roughly a tenth of a second on these clips, confidence 1.0); a stroke can still land a few frames off a word inside a long phrase.
- **Tall frames:** the presenting hand reaches sideways, while the content is above the presenter.
- **Speed:** about 0.12 to 0.14 s per 720p frame for one character on this (busy) Mac: PIL rotates about 14 pieces per frame. Not optimised; fine offline, not ready for the renderer.
- Not wired into the planner or the renderer (on purpose: another change is in progress there).

### Cost of this pass

OpenAI: 5 hand sheets (the fox's includes the tail), USD 0.1774 (ledger `docs/vector_character_spend.jsonl`, run `vector-character-hands`; no retries were needed). Polly generative: about 2,000 characters of narration, about USD 0.06. Total about USD 0.24 of the USD 3 cap.

### Tests

`tests/test_character_gestures.py` (plan is deterministic, phases in order, no overlap, home between gestures, limits, cue words EN and ES, no pointing, gesture box, nothing pops, pure function of time, no twinning, idle life, listening, entering / side step / leaving with whole legs) and `tests/test_vector_presenter.py` (IK keeps bone lengths, the elbow never flips, standing pose is straight, feet stay planted in a weight shift, shoulders stay on the torso at every extreme, joints are covered by paint in drawn extreme poses for all five characters, every hand shape draws, framing presets for 16:9, 9:16, 1:1, 4:5). The first rig's tests still pass.

---

# First pass (earlier the same day): the proof with the first rig

## Verdict in four lines

1. **The rig is not broken.** It moves smoothly, the feet do not skate (measured), the mouth follows the voice, and after this pass it no longer looks mechanical when standing, talking or waving.
2. **It is a puppet, and it will always read as one.** The art is front-facing cut-outs with side-view shoes. It is good for upper-body, talking, gesturing, mascot and dialogue scenes. It is weak for walking close up, and it cannot turn, sit or run.
3. **Most of the remaining ugliness comes from the ART, not from the animation:** the knee has a visible step, the shirt sleeve is a separate piece that floats off the shoulder when the arm is raised, the torso has ragged sides, the hand is one open-hand sprite, the face has no eyebrows and only three mouths.
4. **Do not generate the cast yet.** Fix the part-sheet specification first (list below, about 3 sheets per character, roughly $0.11 to $0.17 per character), prove it on 3 characters, then build the diverse cast on that spec.

## What changed in the rig (cheap fixes, `engine/vector_character.py`)

All additive: with no new pose keys every pixel is identical to before (checked by hash on three frames of the story demo and by a test).

| Addition | What it does | Why it matters |
|---|---|---|
| `spring_step`, `spring_keys` | Each keyframe is reached through a damped spring: overshoot, follow-through, settle. Pure function of time (no state), so chunks render the same anywhere. | The main cure for the "robot" feel; the same keyframes with `ease_keys` (smoothstep, the BEFORE) look stiff. |
| `blink_natural` | Blinks 2.4 to 5.4 s apart, sometimes a double blink. | A blink every 3.4 s exactly is the clearest robot tell. |
| `breath` + pose key `torso_sy`, `head_sy`, `head_sx` | Chest rises about 1.6% on the in-breath, head rides on it; squash and stretch on nods and shrugs. | "No one is ever perfectly still." |
| `mouth_track`, `stress_events` | Mouth shapes computed from the audio level with a one-frame lead and a minimum hold; stressed syllables found automatically, so nods and hand beats land on them. | Talking looks acted, not just a flapping mouth. |
| pose key `eyes_scale` | Wide eyes. | The only surprise cue that the art allows. |
| `Character.draw_turned` | Paper-doll flip: squeeze sideways and mirror. | The only "turn" possible with front-facing art; an honest flip, not a body turn. |
| `load(..., back_tint)` | The far arm tint (0.80 = dark box beside the torso) can be lightened. The reel uses 0.93. | Less visible "pasted dark sleeve". |

## Rating per action

SHIP = I would put it in a customer video. NEEDS WORK = usable in wide shots or only with the listed limit. NOT SUPPORTED = do not offer.

| # | Action | Rating | Limit / why |
|---|---|---|---|
| 1 | Idle breathing + blink | **SHIP** | Breathing, weight shift with planted feet, trailing arms and head, irregular blinks. Eyes have only open/closed (no half-lid), so blinks pop. |
| 2 | Head nod and tilt | **SHIP** (small) | Nods of about 2 units and tilts up to about 10 degrees. The head is a rigid front-facing piece: it bobs and tilts, it does not look up, down or sideways. |
| 3 | Talking with pauses | **SHIP** (cartoon scale) | Three mouth shapes, no true visemes. Fine from a distance; stiff in a big close-up. Nods and one-hand beats on stressed syllables help a lot. |
| 4 | Wave | **SHIP** | Overshoot and a decaying hand wave look good. The sleeve cap separates from the shoulder when the arm is high (see defects). |
| 5 | Point | NEEDS WORK | The hand is an open hand: it reads as "presenting", not as pointing. |
| 6 | Shrug | NEEDS WORK | No shoulder bone in the art: arms out, head sinks, torso squashed. Reads as "I don't know" from far away only. |
| 7 | Surprise | NEEDS WORK | No eyebrows. Wide eyes + open mouth + head back + arms up + small hop works at video scale; the sleeve caps float. |
| 8 | Walk in place (treadmill) | NEEDS WORK | Feet are exact (below). It is a crab-like walk: front-facing torso and side-view legs. Knees show a step. Fine in wide shots, poor in close-ups. |
| 9 | Walk across | NEEDS WORK | Same as 8; walking across a static floor with ticks proves the feet stay on the ground. |
| 10 | Stop | **SHIP** | Smooth deceleration, feet blend to standing. |
| 10b | Turn | **NOT SUPPORTED** (as a turn) | There is no 3/4 view. The flip squeezes the whole figure to a thin slab and mirrors it; it works as a "card flip" cut, not as a person turning. Walking back left is the mirror image. |
| 11 | Sit | **NOT SUPPORTED** | One front-facing IK leg pair. The practical option is a presenter behind a desk (legs out of frame). |
| 12 | Two characters talking in turn | **SHIP** | Listener looks at the speaker, nods after stresses, keeps breathing and blinking. The right character is mirrored to face left. |
| 13 | Close-up on the joints | (diagnostic) | See the defect list; not a use case. |
| 14 | Presenter mode (lower third) | **SHIP** (best fit) | Torso static from the hips up, head, mouth, eyes and arms gesturing, with a text card beside: exactly what this art does well. |
| 15 | In a scene (vector park) | NEEDS WORK / SHIP | At the size viewers see in a scene (about half the proof scale) the walk reads fine; two kids walking and stopping works. |

## Defect checklist (severity 0 = none, 1 = only at 100%, 2 = visible at normal size, 3 = blocks use)

| Defect | Severity | Where it shows | Fixable by |
|---|---|---|---|
| Knee step: the lower leg is a flat-topped tube wider than the thigh cuff; corners stick out when the knee bends | **2** | every standing and walking frame, worst at big bends | art (matched widths, knee overlap), not code |
| Sleeve cap floats off the shoulder when the arm is raised (the sleeve is part of the upper-arm piece, the torso has a flat cut shoulder) | **2** | wave, surprise, shrug | art (sleeve integrated in the torso, round shoulder cap) |
| Far-arm sleeve shows as a darker box beside the torso | **2** (was 3 at tint 0.80) | idle, talking, two-shot | `back_tint` 0.93 helps; art fix is better |
| Torso side edges: thick black vertical strips and ragged hem left by the sleeve cut | 1 | close-up, mirrored characters | art / cleanup in the build script |
| Limb stretching | 0 | rigid pieces; IK clamps at full reach, measured: the IK reaches every walk target (miss = 0.0 units) | n/a |
| Popping | 1 | eye and mouth swaps are instant (no in-betweens); no popping seen at 30 fps in the limbs and head (reviewed frame by frame on filmstrips, not measured numerically) | more eye and mouth states (art) |
| Foot skating | 0 | measured below | n/a |
| Stiff "puppet" feel | 2 | front-facing, no head turn, no torso twist, hands are one sprite | art (more poses), not code |
| Mouth sync | 1 | three shapes, lag about 0 frames | more mouth shapes (art) |
| Hands | 2 | one open-hand sprite: no fist, no point, no grip | art (3 hand states) |
| Blank-face head + separate eyes/mouth | 0 | works well; this is a strength | |

## Numbers (`vector_character_proof.py --measure`, reel scale, 30 fps)

- **Planted foot drift on a static floor (8 stances, walk across):** 0.000 px, both BEFORE and AFTER. The IK reaches every foot target (miss 0.000 units). The reach check also showed that the straighter standing pose I use (0.99 of the leg reach) must not be used while walking (the stride would exceed the reach and the foot would hover), so the walk blends back to the original height.
- **Mouth (4 Polly lines, 1.9 to 3.8 s each):**
  - changes per second: BEFORE 6.9 to 8.9, AFTER 5.9 to 6.9;
  - one-frame mouth shapes (flicker): BEFORE 2 to 7 per line, AFTER 1 per line;
  - best lag against the audio level: 0 frames in both (the one-frame lead cancels the hold delay);
  - correlation with the audio level at zero lag: BEFORE 0.87 to 0.95, AFTER 0.70 to 0.85. The AFTER mouth is deliberately smoother than the signal, so it correlates less and flickers less.
- **Speed:** unchanged order of magnitude: the Mac was loaded, a single 1080p character with the new keys costs about the same as before (squash needs one extra resize per scaled piece). 4K is still the problem from the first report (about 2.9 s per frame in the story), not touched here.
- **Tests:** `tests/test_vector_character.py` 25 pass (8 new: spring, stateless keyframes, no-overshoot ease, irregular blinks, mouth lead and hold, stress events, breath, neutral new pose keys give the old pixels, draw_turned width).

## What the rig can and cannot do

Reliable now: idle, small head moves, talking with nods and hand beats, wave, present with an open hand, stop, walk at a distance, two-character dialogue, presenter mode, mirroring a whole character to face the other way.

Not possible with this art: turning the body or head to 3/4 or side, a side-view walk, running, sitting or lying, hand details (fist, point, thumbs up, holding an object), eyebrows and varied facial expressions (only wide eyes, three mouths, closed eyes), interacting with objects, props in hands, dancing or any pose with the torso twisting, a character seen from behind.

## Quality bar before generating more characters

Run this per character, automatically, before it enters the library (a script that renders the clips and checks numbers) plus a 6-frame human look:

1. **Parts:** 11 pieces (or the new spec's count) found, no piece touching the image edge, blank-face head (no pre-drawn eyes or mouth), arm and leg joints inside their pieces.
2. **Knee check:** width of the bottom of the upper leg and the top of the lower leg within 10% of each other, and the upper-leg outline closed (no cuff overhanging more than 8% of the width).
3. **Sleeve check:** raised-arm render (110 degrees): no visible gap between the sleeve cap and the torso at 100% (measure the background pixels between the torso shoulder line and the sleeve).
4. **Torso edge:** no outline strips thicker than 2x the normal outline along the torso sides.
5. **Colour match:** the near and far arms and legs within the same palette; far-arm tint not producing a visible box.
6. **Animation test, 6 renders (idle 3 s, talk 3 s with a fixed Polly line, wave 3 s, walk 3 s, surprise 2 s, shrug 2 s)** at 1080p: no frame with a joint gap over 3 px, planted-foot drift under 0.5 px, no limb leaving the canvas, mouth one-frame flicker at most 1 per line.
7. **Human look:** a contact sheet of 6 frames per character; reject anything that looks broken, off-style, or stereotyped (diversity review, see `docs/CHARACTER_LIBRARY.md` when it exists).

## Options to raise the ceiling (what each costs)

| Option | What it fixes | Cost / effort |
|---|---|---|
| **More parts per character** (recommended first): sleeve cap integrated into the torso and a round shoulder piece; 3 hand states (open, fist, point); 2 eyebrow pieces; half-closed eyelids; 5 mouth shapes (closed, open, wide, O, smile); a neck piece; matched-width legs with a knee overlap | knee step, sleeve cap, hands, pointing, surprise and shrug, eyebrow expressions, blink, mouth sync | one extra parts sheet (about $0.036 each) for hands + face states: about **$0.11 per character** for 3 sheets, about $0.17 with retries; about $7 for 40 characters; plus a day to change the build script and rig for the new parts |
| **Multiple pose sheets per character:** a side-view set (torso, arms, legs) and optionally 3/4, swapped (with a short crossfade) when the character turns or walks | real walking, real turns | about $0.036 per sheet; the risk is consistency of colours and proportions between views (use the front sheet as the reference image in the edit endpoint); several days of rig work (a second skeleton with its own walk) |
| **Lottie / Rive for hero mascots** | hand-polished quality (squash, smears, expressions) | a designer's time (per mascot, not per cast); Rive's runtime is open source but we would need headless export to video; not for a generated, diverse cast |
| **AI video clips of the same cartoon characters** | full body acting, turns, walking with any camera | Gemini Omni Flash is about $0.07 per second at 720p (about $0.35 per 5 s clip); no hard guarantee that the same character looks the same across clips, no lip-sync control, audio always present; fine for atmospheric cartoon b-roll, poor for a recurring cast |

## Recommendation

1. Keep this rig for **presenter mode, dialogue between two or three characters, mascots and guides, and wide walking shots**. That is already enough for kids, education and light explainer videos.
2. **Do not generate the diverse cast yet.** First change the part-sheet specification (more parts, matched legs, sleeve in the torso, hand and face states), build 3 characters on it (about $0.5), run the quality bar above, and show the owner the same reel. If it passes, generate the cast on the new spec (about $7 for 40, within tonight's budget).
3. Keep walking away from close-ups in the planner rules: walking characters only in wide shots, talking characters in medium shots.
4. Skip turning and sitting. If a scene needs them, use another scene type.
5. Do not invest in Lottie/Rive unless the owner wants a hero mascot with hand-polished acting.
