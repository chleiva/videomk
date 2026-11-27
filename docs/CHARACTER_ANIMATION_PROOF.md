# Character animation proof (2026-11-27)

Owner's question: before more characters are generated, show how they will be animated. "If they look very broken, there is no point generating more than one."
This note is the answer. Everything here was made with the four existing characters (mia, leo, nora, sam), CPU only, cached Polly lines, **no money spent**.

Reel: `character_animation_proof_reel.mp4` (1080p, 30 fps, about 66 s; 15 clips, each with a burned-in label that is for the proof only). For the actions that the new secondary motion
improves, the screen is split: **BEFORE** (the original rig) on the left, **AFTER** on the right, same character, same keyframes.
Joint close-ups at 100%: `joint_crops_100pct.png` (1 px = 1 px of the reel, each tile also shows a 3x enlargement).
Script: `backend/scripts/vector_character_proof.py` (`--measure` prints the numbers below, `--joint-strip` the crops, `--stills name:t` single frames).

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
