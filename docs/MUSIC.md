# Music director, sound effects and image density (2026-11-24)

## The music director
The planner (the LLM that writes the script) now also picks the background music, the way a human editor would:
`"music": {"style": "<id>", "energy": 1-5, "key": "D minor" (optional), "tempo": 50-140 (optional), "changes": [{"beat": n, "style": "<id>", "energy": n}]}`.
- **10 styles** (`engine/music.py`, `STYLES`): ambient_pad, soft_piano, lofi_chill, bright_pluck, cinematic_rise, tense_pulse, acoustic_warm, minimal_tech, uplifting_corporate, dreamy_bells. Each has a feel the planner reads ("slow weightless pads... calm, science, nature"), a mode, a tempo, chord progressions and instrument layers.
- **Different every time**: the seed comes from the video id and varies the chord progression, the patterns, the tempo (about ±6 %) and the stereo placement; the key is the planner's or a random one that suits the style. The same style sounds like a different piece in two videos.
- **Energy** 1-5 scales how busy it is (drums only join from energy 2 or 3).
- **Changes**: at most two style changes at a chapter or mood shift, never within 12 seconds of an edge, crossfaded over 2.6 s with equal-power fades (tested for clicks).
- **Fallback**: no `music` in the plan (old videos, the model skipped it) means the mood decides (calm = ambient_pad, bright = bright_pluck, tense = tense_pulse).
- **Editing**: edit op `set_music` (style, energy, key, tempo, changes; `null` clears it) and `set_sfx`; the editor view returns `music`, `music_styles` and `sfx`. Music is audio only, so changing it never re-renders the picture (video chunks are cached on pictures alone).
- **Mix**: unchanged: music volume 0.2, ducked under speech by side-chain compression, faded in and out, limiter.
- Cost and speed: numpy synthesis, about 0.3 s per 30 s of music on a laptop, free, licence-free, no Content ID risk.

## Sound effects
Eleven effects, all synthesised: whoosh (transition), pop (small reveal), ding (a fact lands), click (a step), riser (tension into this beat, placed to peak at the cut), impact (a big moment), shutter (a photo), sparkle (wonder), typing (writing or computing), swipe (quick change), chime (success). A beat may carry `"sfx": "<name>"` (or `"none"` for a silent transition); the planner is told to use them sparingly (at most one beat in three). Beats without one keep the default transition whoosh.

## What about AI music models? (the decision for later)
| Option | Fit | Cost / risk |
|---|---|---|
| Procedural synth (now) | instant, free, safe, varied, but "game-like" next to a produced track | none |
| Curated licensed library (CC0 / paid pack) | most polished, instant | needs a source we are allowed to bundle and a curation pass; Openverse/Commons audio is hit and miss |
| ElevenLabs Music, Google Lyria 2 (Vertex), Stable Audio | real produced instrumentals from a text brief, the planner's `style` + `energy` + `key` becomes the prompt | roughly 10-60 s latency and cents to tens of cents per track (5-10x today's cost of a whole video); check each licence's commercial terms; generated tracks must be cached by prompt hash |
| Suno / Udio | quality, but no official API and unresolved licensing | do not use |
| Open-weight models (MusicGen etc.) | self-hosted | MusicGen weights are non-commercial; a GPU endpoint breaks "serverless, zero idle cost" |

Recommendation: keep the synth as the default and the offline fallback, and add one AI provider behind `music.render_segment` only for longer or premium videos, with the planner's brief as the prompt, after listening to the synth and deciding what is missing. The interface is already the planner's JSON, so nothing upstream changes.

## Image density
`max_images_per_minute` (0-10, default 10, request field and `MAX_IMAGES_PER_MINUTE` env) is a **ceiling**, never a target or a minimum: 0 means no stock photographs at all and the planner is not even shown the image scenes. The budget for a video is `floor(rate x target minutes)`. A new `gallery` scene shows 2-4 photographs one after another inside ONE beat (a beat is about 14 s, so one image per beat could never reach 10 a minute), crossfading with a gentle push. Every photograph in a gallery counts; the user's own photos never do. After the planner answers, `enforce_image_budget` keeps the first photographs up to the budget, trims a gallery, reduces it to one image, and turns anything beyond into a plain card (tests cover each case). Gallery photos are fetched in parallel in the beat step, each searched and reviewed like a single image scene; a query that finds nothing is dropped (one left = a plain image scene, none = a card).

Stock photographs come from Unsplash (the Plorer production key, 5000 requests/hour, stored in SSM `/videomk/unsplash_access_key`) and Openverse. Unsplash's production approval belongs to the application it was granted to: apply for videomk's own key before launch (the key is read from SSM, so switching is one parameter).

## Clip verification (one frame per 30 seconds)
Candidate clips are judged from their poster frame (one image each, one model call per beat). The clip chosen is then trimmed and checked with one more small call on frames of the footage we will really use, one per 30 s of it (so one frame for any clip up to 30 s, at most three). A clip that fails (logo, watermark, private person, mismatch) is skipped for the next candidate; a failing check never blocks a video. `CLIP_VERIFY=0` turns it off. Pixabay clips are one of the providers (key in SSM `/videomk/pixabay_api_key`, results cached 24 h as its API terms require).

## The curated library (Lyria), 2026-11-24
The procedural synth sounds like a game, not like a produced track (the owner's verdict). The planned fix is a **curated catalogue of 20-30 recordings** made once with Google's Lyria 3.5 (Gemini API, `lyria-3.5`, about $0.08 per song, roughly two minutes of 44.1 kHz stereo MP3, no seed or BPM field: control is by prompt), listened to by a person, stored in S3, and **chosen by the planner from their descriptions**.
- `scripts/music_library.py list | generate | publish`: 23 briefs (calm pads, soft piano, lo-fi, plucks, cinematic, tension, acoustic, tech, business, bells, nature, folk, Mediterranean, jazz, documentary, history, inspiring, playful, mystery, electro, hopeful piano, light orchestral, meditative drone; about $1.84 for all). Generate writes drafts and `music-draft/catalog.json` locally; delete what you dislike, edit descriptions, then `publish --profile qa` uploads the survivors to `s3://<assets bucket>/music/<id>.mp3` and the catalogue to `music/catalog.json`.
- `engine/library.py`: the planner prompt lists each track (id, length, energy, bpm, and the description saying what to expect). The plan names `{"music": {"track": "<id>", "changes": [{"beat": n, "track": "<id>"}]}}`. The audio step downloads only the tracks used, levels them to the synth's loudness, **loops short tracks with 3 s equal-power crossfades**, crossfades track changes, and keeps the swell under silent beats and the ducking under speech. A missing catalogue or track falls back to the synth: a video is never silent because of the library.
- **Not done until you provide a key**: no track exists yet. Create `GEMINI_API_KEY` at https://aistudio.google.com/apikey (Lyria has no free tier: link billing, the minimum prepay is $5), put it in `.env`, run `generate`, listen, `publish`.
- **Terms to accept knowingly** (Gemini API Additional Terms, as read 2026-11-24): Google claims no ownership of the output but may generate the same or similar content for others; you are responsible for its use; no clause explicitly permits or forbids keeping a fixed catalogue and reusing it across users (the terms are silent: if that matters to you, ask Google or counsel); no indemnity was found; paid services are required when serving the EEA, Switzerland or the UK; the audio carries an inaudible SynthID watermark; apps for under-18s are excluded.
