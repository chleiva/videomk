# Silent beats: pauses, held pictures and one big word (2026-11-24)

Narration does not have to run all the time. The planner may add **silent beats**: `"narration": ""`, `"hold": 2.5-8` seconds (3-6 typical), on an image, gallery, clip, title, quote or stat scene. Optionally `"word": "<up to 24 characters>"` on an image, gallery or clip scene shows one big word over the picture (fades in, holds, fades out, soft shadow).
- **Rules** (`plan.enforce_silence`): never the first or last beat, never two in a row, at most one in four, not for scene types that need narration (bullets, diagrams, charts, timelines). A beat that breaks a rule is dropped (it is only a picture).
- **Cost and speed:** a silent beat synthesises nothing and costs no speech (about $0.03 per narrated minute). Its stock photo or clip is chosen from the scene's own description instead of the narration.
- **Timeline:** the scene lasts exactly as long as it is held (at least 2.8 s), has no captions and no audio file (`silent: true`, `audio_key: null`).
- **Music:** while nobody speaks the music comes up (about 2.2x, 0.8 s ramps in and out), so the pause breathes instead of going quiet. Measured on a real video: no speech-band energy during the pause, the music louder than under speech.
- **Editing:** `set_hold` changes the time; `set_narration` on a silent beat gives it a voice (it becomes a spoken beat); `insert` with `hold` and no narration adds a pause. iOS and Android editors show "Silent pause, N s" and do not treat the empty narration as an error.
- Not done: a silent beat with a spoken cue-in (a short line before the pause), and pauses inside a beat's narration (a beat is spoken as one piece).
