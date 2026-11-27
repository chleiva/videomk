# Character library: first five characters (2026-11-27)

Owner decision: generate only **5** new characters, animate them, look at the videos, and only then decide whether to build more. This note is that test. Nothing is deployed and the characters are not wired into the planner.

## The five

| id | Name | Role | Age group | Look (house-v2 flat cartoon) | EN voice (Polly generative) | ES voice hint |
|---|---|---|---|---|---|---|
| `ines` | Inés | senior teacher / mentor | senior | light tan skin, short wavy white-grey hair, round glasses, rose cardigan, cream blouse | Ruth | Lupe, Lucía |
| `david` | David | software engineer | young adult | dark brown skin, short natural black fade, mustard hoodie with headphones round the neck | Matthew | Pedro |
| `priya` | Priya | doctor / scientist | middle-aged adult | medium brown skin, black hair in a low ponytail, white lab coat, teal top, stethoscope | Kajal | Mía |
| `mateo` | Mateo | chef | adult | olive-tan skin, short dark hair and beard, white chef shirt, green apron | Stephen | Andrés, Pedro |
| `fox` | Fox | guide mascot (bipedal fox) | ageless | orange-red fur, cream muzzle, teal scarf, navy waistcoat, brown boots | Joanna (Gregory failed on Polly generative) | Lucía, Sergio |

Assets: `backend/lambdas/engine/assets/vector_characters/<id>/` (11 SVG pieces, `manifest.json` for the rig, `meta.json` with id, name, role, species, age_group, tags, voice_hint EN/ES, personality, suitable_topics, outfit, provenance). 0.44 to 0.69 MB of vector pieces per character.
Made with `backend/scripts/vector_character_sheet5.py` (one parts sheet per character from `gpt-image-2.6-flare`, ledger `docs/vector_character_spend.jsonl`) and `vector_character_build5.py` (cuts and vectorises; adds the eyebrow-over-eyes merge the older cutter did not have).
Demo and test render: `backend/scripts/vector_character_cast_demo.py` (five clips and a team video); tests: `backend/tests/test_vector_character_cast.py` (assets complete, metadata well formed, draws in every pose family).

## Diversity and safety principles used (apply them to every new character)

- Adults and seniors are first-class characters, not only children. Vary age, skin tone, hair, body type, clothing and profession in every cast.
- No real-person likeness, no celebrity, no religious or political symbol, no caricature, no costume. Cultural variety shows through everyday clothes and features, never through stereotype or accent jokes.
- Professions are not tied to demographics: when a planner picks a cast it should vary them (a Black engineer, a South Asian doctor and a Latino chef are examples of the range, not a rule).
- Abilities: respectful representation (wheelchair user, glasses, hearing aid, prosthetic) is wanted but needs a rig that handles it (a seated figure, a chair as its own piece). It is deliberately NOT in this batch.
- Every sheet is viewed by a person (here: the builder) before use; reject mismatched parts, bad anatomy, inconsistent colours and anything off-putting.

## Quality bar for a new character (per-character animation test)

A character is accepted only if the test clip (`vector_character_cast_demo.py --clips --only <id>`) shows, at 1080p and at 100% crops:
1. all 11 pieces found and in order (the builder refuses a sheet that does not give 11);
2. idle + natural blink, talking with the mouth following the voice, wave: no gaps at neck, shoulders, elbows, knees; no piece in the wrong colour;
3. walk across: feet planted on the ground (the walk uses the distance travelled, so this holds by construction);
4. no vertical black strip wider than ~1.5% of the torso on either side; the torso hem does not float above the hips.

## Result of this test (honest)

Per-action rating, SHIP = fine in a customer video, NEEDS WORK = fine in wide shots only:

| Action | Inés | David | Priya | Mateo | Fox |
|---|---|---|---|---|---|
| Idle + blink | SHIP | SHIP | SHIP | SHIP | SHIP |
| Talk (voice-driven mouth, nods, hand beats) | SHIP | SHIP | SHIP | SHIP | SHIP |
| Wave | SHIP | SHIP | NEEDS WORK (white sleeve reads as a pill when raised) | NEEDS WORK (same) | SHIP |
| Point | NEEDS WORK | NEEDS WORK | NEEDS WORK | NEEDS WORK | NEEDS WORK (open hand reads as "presenting") |
| Walk across | NEEDS WORK | NEEDS WORK | NEEDS WORK | NEEDS WORK | NEEDS WORK (crab-like, fine in wide shots) |

Defects seen at 100%, in every character: knee step (the lower-leg piece is wider than the thigh; worst in Mateo's checked trousers); a thin dark vertical strip at the torso sides; the sleeve cap separating from the shoulder when an arm is raised (most visible on white clothing); one open-hand sprite. Fox has no tail piece. The far arm is tinted 0.93 so it does not read as a dark box.

## Not supported (rig limits)

Turning (only a paper-doll flip), 3/4 views, running, sitting, picking up or holding objects, detailed hand shapes, eyebrow expressions, more than three mouth shapes, a seated or wheelchair figure, quadruped walking, tails.
At 4K the characters are drawn at 2.9 s/frame (not optimised: do not use on Lambda yet).

## What would raise the ceiling

Part-sheet spec changes (see `docs/CHARACTER_ANIMATION_PROOF.md`): matched knee widths with an overlap piece, the sleeve built into a round-shouldered torso, 3 hand states, eyebrow pieces and 5-6 mouths, a tail piece for animals; roughly 3 sheets (about $0.11 to $0.17) per character.

## The team video (23.6 s, 1080p, Polly voices, music low)

Five characters walk in together, then take turns on "how a healthy meal gets to your table" (Mateo, Priya, Inés, David, Fox), listeners look at the speaker, everyone waves at the end. Rated: two-shot / group dialogue SHIP; the group walk-in NEEDS WORK (fine in a wide shot); the wave overshoot can swing a raised arm across a neighbour (Fox, last second). Render cost 0 beyond Polly (cents); 285 to 1125 ms per frame on this Mac depending on load (five characters plus a vector scene), so 4K and Lambda need the speed-up first.

## Spend

OpenAI: 5 parts sheets, USD 0.1802 of the USD 1.00 cap (no retries needed: all five sheets followed the layout; ledger `docs/vector_character_spend.jsonl`). Polly: a few cents. No GPU, no other paid services.

## Files

New: `backend/scripts/vector_character_sheet5.py`, `vector_character_build5.py`, `vector_character_cast_demo.py`, `backend/tests/test_vector_character_cast.py`, `backend/lambdas/engine/assets/vector_characters/{ines,david,priya,mateo,fox}/`, `docs/vector_character_spend.jsonl`, this note. Nothing existing was edited.
