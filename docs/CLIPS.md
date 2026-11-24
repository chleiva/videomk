# Stock video clips (2026-11-24)

The planner can use short real footage behind the narration: a `clip` scene `{clip_query, alt}`, at most 1 beat in 4, never two in a row, only for generic
motion stock footage really has (waves, traffic, clouds, hands typing, wildlife). Named people, places, brands and facts stay with images, diagrams and charts.
`CLIPS_ENABLED=0` (Lambda env) removes clips from the planner's menu.

## Flow
1. **Plan**: the director writes `clip` scenes like any other scene (sanitised; an empty one becomes a plain card).
2. **Beat step** (`engine/clips.py`, `beat_handler.make_clip`): search **Pexels** (only when `/videomk/pexels_api_key` exists in SSM), **Pixabay** (only when
   `/videomk/pixabay_api_key` exists; videos are cached 24 h as its terms require, 100 requests/60 s per key) and **Wikimedia Commons** (keyless), keep landscape footage of 3 s or more with an allowed licence, show the poster frames to the small vision model (same reviewer as photos, with a
   footage-editor prompt: no logos, no private people, must match), download the winner (≤ 70 MB, SSRF-safe fetch), and **normalise** it with ffmpeg: trimmed to the
   length the scene needs (a short clip loops inside its scene), cropped to 16:9, 1280x720, 30 fps, no audio, H.264 (about 1 MB per 10 s). Stored as
   `generation/v2/<video>/assets/clip_<beat>_<hash>.mp4` with the `retention=working` tag (expires after 7 days; the editor re-renders from it until then).
2b. **Verification**: the clip is then checked on one frame per 30 s of the footage actually used (one call, at most 3 frames; `CLIP_VERIFY=0` disables it); a failing clip is skipped for the next candidate.
3. **Fallbacks, so there is never a hole**: reviewer rejects everything / nothing found / download or decode fails (3 tries) → a still photo of the same subject
   (Unsplash/Openverse path) → a title card.
4. **Render** (chunk Lambda): the clip is decoded once per chunk to JPEG frames in memory and drawn like a photo scene (slow push-in, bottom scrim for captions,
   credit top-right). An outgoing clip holds its last frame during the crossfade. Measured on Lambda: ~190 ms per frame (a 1-minute video renders in parallel
   30-second chunks, about 3 minutes each at worst; chunk timeout is 10 minutes).
5. **Credits**: on-screen "Video: Name / Pexels" or "Video: Name (CC0)"; the description lists "Video by Name on Pexels (link)" or "Video by Name (CC0) via Wikimedia Commons (link)".

## Licensing (what the providers' own terms say)
- **Pexels** ("All photos and videos on Pexels are free to use", commercial use allowed, attribution not required; the API asks for a prominent link to Pexels and
  credit to the creator "when possible", which we give). Not allowed: selling unaltered copies, implying endorsement, recognisable people shown in a bad light,
  using content for machine-learning training, copying Pexels' core functionality. Our use (clips combined with narration and captions into a new video) is the intended
  pattern; we never serve the clips as a library. Default limit 200 requests/hour and 20,000/month: ask Pexels for a lift with a demo showing attribution before launch.
  **New API keys were reported paused when this was written.**
- **Pixabay** (Pixabay Content License: free for commercial use, attribution not required; the API asks to show where videos come from, done on screen and in the description; permanent hotlinking is not allowed, so videos are downloaded as working copies).
- **Wikimedia Commons**: only per-file CC0, public domain and plain CC BY (no -SA/-ND/-NC), the same bar as Openverse photos. Author and licence come from the file's own metadata.
- Not a licence matter but worth knowing: Pexels content showing logos or trademarks cannot be used commercially for goods and services; the reviewer rejects visible logos.

## Operating notes
- **Commons throttles clients without contact details in the User-Agent (HTTP 429 on downloads).** Set `-c httpUserAgent="videomk/1.0 (<a contact URL or email you are happy to publish>)"` at deploy
  (`deploy.sh`), which every outbound fetch uses. Without it clips fall back to stills on Commons-only deployments. Search itself works without.
- Pexels needs a key in SSM: `aws ssm put-parameter --name /videomk/pexels_api_key --type SecureString --value ...` (the beat Lambda already may read `/videomk/*_api_key`).
- The selftest Lambda (`engine_selftest`) now proves the whole clip path on the Lambda runtime (decoders h264/vp8/vp9/theora present, normalise, decode, render).
- Not built: choosing a clip in the editor (the editor lists clip beats and can change their narration; changing the clip needs a new `clip_query`), clips of the user's own phone videos,
  a second keyless provider (Internet Archive public-domain footage would be the next one), per-clip start offsets.


## Why clips fell back to photos in real use, and what changed (2026-11-24)
Measured since clips went live: 9 of 24 videos had a clip scene; of 10 clip scenes 6 got a real clip (all Pixabay), 4 fell back to a photo. Causes in the beat logs: Wikimedia downloads refused with HTTP 429 (8, no contact in the User-Agent), the reviewer rejecting every candidate (5), the verifier rejecting footage that did not fit a very specific narration (5), and the planner picking clips for news beats (an attack in Yemen) where generic footage can only mislead.
Changes: Commons is skipped unless the User-Agent carries contact details (`CLIPS_COMMONS=1/0` overrides), so Pixabay gets all the review slots (now 8 candidates); the planner's second wording (`alt`) is searched when the first finds nothing; current-events videos (web research) get photographs instead of clip scenes; when the brief asks for video or footage the planner uses clips freely (up to 1 beat in 3, worded generically); and the reviewer and verifier now reject footage that contradicts the narration or misses the intended subject, but accept a fair generic fit (footage is atmosphere, not an illustration of every detail).
Trade-off to know: a generic fit can be the wrong place (a canal at dusk under a Tiber video). Making the reviewers stricter brings back the fallbacks to photos; the prompts are `CLIP_REVIEW_SYSTEM` and `CLIP_VERIFY_SYSTEM`.
