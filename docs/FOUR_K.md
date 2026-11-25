# 4K (2160p) videos: design, measurements, costs and limits (2026-11-25)

Owner decisions: 4K is a third resolution, `2160p`, next to `720p` and `1080p`. It is meant for YouTube and general use (16:9 at 3840x2160); it costs **double the credits** of the same video at 1080p; for platforms that do not deliver 4K the app recommends against it; nothing changes for 720p and 1080p. The app contract is `docs/CREATE_API.md`; this file is the why and the numbers.

**Status: built, tested locally, off by default.** Nothing here has run on Lambda yet. Every Lambda number below is an estimate: a local measurement scaled by the ratio measured between this laptop and real QA renders at 1080p. Run `engine_selftest` (it now reports `ms_per_frame_4k` and `peak_rss_mb`) and one real 4K video on QA before switching it on anywhere else.

## Switching it on
```
cdk deploy videomk-qa -c stage=qa -c engine=v2 ... -c readyResolutions=720p,1080p,2160p
```
* `readyResolutions` (default `720p,1080p`) becomes `READY_RESOLUTIONS` on the capabilities and launcher functions, exactly like `readyAspects`. Without `2160p` nothing changes: capabilities does not list 4K and `generate` answers 400 `This resolution is not available yet`.
* The deploy **refuses** `2160p` on a stage whose functions are capped below 10240 MB (`lambdaMemoryCap`; production is capped at 3008 MB until its Lambda quota is raised): a 4K render needs about 6 GB (below).
* Like every context key it must be passed on each deploy.

## Sizes
The short side is 2160: 16:9 3840x2160, 9:16 2160x3840, 1:1 2160x2160, 4:5 2160x2700. All four shapes work (scenes lay out in design units, `engine/frame.py`; 4K is a scale of 2.0 of the same design canvas, so there is no 4K layout to maintain) and all fit H.264 level 5.1. Which shapes are offered is still `readyAspects`; capabilities lists them per resolution (`resolutions[].aspects`).

## How a 4K frame is made
* **Drawn natively, not enlarged.** Pillow's shapes have no anti-aliasing, so every frame is drawn on a larger canvas and reduced. 1080p draws at 2x and reduces 2x. 4K draws at **4x the design size (7680x4320) and reduces 2x**: the same 2x2 samples per output pixel as 1080p, so text, charts, icons (font glyphs), maps (vector outlines) and card sprites are all rasterised at 4K density. Checked for every built-in scene and every element sample: the 4K frame reduced 2x matches the 1080p frame (same layout), and its edges are 1.3 to 1.8 times crisper than the 1080p frame enlarged to 4K (photo scenes aside, whose test photo is small).
* Options that were measured and rejected (local, mean over 56 sample scenes, ms per frame; 1080p is 57 to 70):

| 4K canvas | ms per frame | verdict |
|---|---|---|
| 2x, not reduced | 69 | cheapest, but shapes are not anti-aliased: stair-steps on chart lines, pie edges and arcs at 100% |
| 3x, Lanczos to 2/3 | 290 | the non-integer resize costs more than it saves; 2.25 samples per pixel |
| 4x, reduced 2x | 224 | same edge quality as 1080p |
| 4x, reduced 2x, with the two savings below | **125** | chosen |

* Two savings that apply only to the 4x canvas (1080p and 720p code paths are untouched): the blurred background glow is enlarged to half the canvas and doubled (`canvas.Canvas.background`), and a full-frame photograph or clip frame is resampled once to the output size and doubled (`scenes/viz_scenes._fill`); after the final 2x reduce both give exactly the picture a direct resample would.
* **Previews** of a 4K video (editor drafts) are the same small draft as for 1080p (960x540 for 16:9). Only the final render is 4K.

## Sources
| Source | 720p / 1080p (unchanged) | 4K |
|---|---|---|
| Stock photos (Unsplash, Openverse) | asked at 2400 wide, stored at most 2800 on the long side | asked at 4400 wide, stored at most **4400** (3840 plus the 1.14x push-in of an image scene, so the photo is never enlarged when the original is that large). `assets.MAX_SIDE_4K`, `stock.UNSPLASH_W_4K` |
| The person's own photos | stored at most 2048 | stored at most **4096** (`usermedia.MAX_SIDE_4K`). **The apps upload 2048 px today**, so until they send more a person's photo is enlarged about 1.9x in a 4K frame |
| Stock clips (Pexels, Pixabay, Commons) | file of 1280 to 1920 on the long side, normalised to 1280x720 (CRF 26) | the smallest file that is at least 1080p (Pexels: up to 1440p; Pixabay: any size under the 70 MB limit), normalised to **1920x1080** (CRF 23), enlarged 2x in the frame, which is the same enlargement 720p footage gets at 1080p |
| Text, charts, icons, maps, sprites | canvas 2x | canvas 4x: native |

A photograph smaller than the frame (an Openverse original of 1600 px, a phone photo) is still enlarged; candidates are not filtered by size for 4K, so the reviewer still sees the same pool. Asset keys carry a content hash, so the two size tiers never collide and nothing cached for a 1080p video is reused for a 4K one (chunk hashes include the pixel size).

Memory of `ClipFrames` (all frames of a clip as JPEGs in memory), measured on the longest clip the engine keeps (20 s, 600 frames, busy real footage): 37 MB at 1280x720, **66 MB at 1920x1080**; the normalised file is 4.5 MB against 12 MB. Safe.

## Encoding
`media.encode_settings`: up to 1080p exactly as before (CRF 20, `veryfast`, profile and level left to x264; drafts CRF 28 `ultrafast`). For 4K: **H.264 High, level 5.1, CRF 21, `veryfast`, `-maxrate 24M -bufsize 48M`**, yuv420p, same 2 s closed GOPs; the final MP4 is still a stream copy with `+faststart`. Measured on one 36.5 s chunk (title, photo with push-in, gallery of three photos, a real stock clip, line chart, map, card bullets, diagram, steps; captions on; real 4400 px photos):

| Setting | MB per minute | Mbps | wall time |
|---|---|---|---|
| 1080p, CRF 20 veryfast (today) | 31.4 | 4.2 | 61.5 s |
| 4K, CRF 20 veryfast | 81.0 | 10.8 | 152.5 s |
| **4K, CRF 21 veryfast** | **73.6** | **9.8** | **152.3 s** |
| 4K, CRF 23 veryfast | 58.3 | 7.8 | 152.8 s |
| 4K, CRF 21 faster | 80.5 | 10.7 | 156.5 s (50% more encoder CPU) |
| 4K, CRF 21 superfast | 117.7 | 15.7 | 152.0 s |

The wall time does not move with the encoder: drawing (one Python thread) is the bottleneck, the encoder runs on the other cores. CRF 21 at four times the pixels is visually on par with CRF 20 at 1080p. The 24 Mbps ceiling only bites on busy footage (which is 1080p material enlarged, so it has no 4K detail to lose) and bounds the file: 12 minutes is about **0.9 GB** as measured, at most 2.2 GB.

## Time, memory and chunks
Local (Apple M3), the chunk above: 1080p 1.68 s per second of video (56 ms per frame, peak memory 1.3 GB Python + 0.5 GB ffmpeg); **4K 4.17 s per second of video (139 ms per frame), 2.48 times 1080p; peak memory 4.1 GB Python + 1.6 GB ffmpeg** when all nine scenes are rendered in one process.

Lambda, measured at 1080p on QA (10 GB functions, two real 12-minute videos of 21,630 frames, from the execution history): 195 and 219 ms per frame over all chunks, i.e. **5.8 to 6.6 compute-seconds per second of video**; single chunks range from 125 to 440 ms per frame; the whole workflow took 7.5 minutes. So Lambda is about 3.7 times slower than this laptop, and the estimate for 4K is **about 0.5 s per frame, 14.5 to 16.3 compute-seconds per second of video**, up to about 1.5 s per frame for the heaviest scenes (card and sprite scenes are 3.3 times their 1080p cost).

What follows from that (`handlers/timeline_handler.py`, `timeline.chunk_plan`):
* **Chunks of 6 s instead of 10 s, and no piece longer than 180 frames.** At 1080p a chunk is one or more whole scenes; the slowest 1080p chunk seen on QA took 300 s of the 600 s limit, so the same chunk at 4K would time out. For 4K a group of scenes longer than 180 frames is cut into even pieces (`{"f0": first frame, "frames": n}`), each rendered by its own function and stitched like any other segment (every segment starts on a key frame). A piece is then about 90 s of Lambda time, about 260 s for the heaviest scene: under half the limit. Pieces are content-addressed like chunks, so an edit re-renders only what changed. Settings: `CHUNK_SECONDS_4K` (6), `CHUNK_MAX_FRAMES_4K` (180). 720p, 1080p and all previews are chunked exactly as before.
* **Memory: 10 GB functions are required.** One 180-frame piece in a fresh process peaks at 1.2 to 1.4 GB (photo gallery, clip, map, collage) and 3.2 to 3.7 GB (card and diagram scenes, whose sprites are built at 8x) for Python, plus 1.4 to 1.6 GB for the encoder: **about 5.5 GB at worst**, 5.7 GB for the nine-scene chunk above (1080p: 0.4 to 1.3 GB plus 0.5 GB; 1.4 GB is the most ever used on QA). A warm function would also carry the previous chunk's cached sprites and photos, which are four times larger at 4K, so the 4K render empties the picture caches at the start of every chunk (`renderer.release_caches`). On a 3 GB function a 4K render would run out of memory, hence the deploy guard.
* **Storage.** Render chunk: 1 GB of `/tmp` is enough (a clip of a few MB and a segment of at most 18 MB), unchanged. Finalize holds the segments and the stitched MP4 together: 1.8 GB for a typical 12-minute 4K video, 4.4 GB at the bitrate ceiling, so its `/tmp` went from 4 GB to **8 GB** (`engine_v2.py`; the only infrastructure change besides the flag). Its 10-minute limit is ample for a stream copy and a 1 to 2 GB upload.
* **Workflow time: the 45-minute limit stays.** A 12-minute 4K video is about 125 pieces and about 11,000 compute-seconds; at 32 parallel functions that is 6 minutes when perfectly packed, 8 to 12 minutes in practice, and **15 to 20 minutes for the whole workflow** (1080p: 7.5 minutes measured). With the plan step at its own 15-minute ceiling and a retried chunk it still ends inside 45 minutes, so no maximum length was imposed for 4K: up to 12 minutes, like every video.

## Cost
Lambda at 10 GB (x86, $0.0000166667 per GB-second):

| | compute-seconds per second of video | per minute of video | 12-minute video |
|---|---|---|---|
| 1080p (measured on QA) | 5.8 to 6.6 | $0.058 to $0.066 | $0.70 to $0.79 |
| 4K (estimated) | 14.5 to 16.3 | **$0.145 to $0.163** | **$1.74 to $1.96** |

So 4K adds about **$0.09 per minute of video** in rendering, against one extra credit per minute (about $0.40 to $0.50 at the proposed pack prices). The AI costs (script, voice, photo review) do not change with resolution. Two smaller things do: the finished file is 2.3 times larger (storage, and about $0.08 of S3 transfer each time a 12-minute 4K video is downloaded in full, against $0.03 at 1080p), and each 4K photo or clip is a larger download for the beat step (no measurable cost).

Note for whoever tunes cost next (not changed here, it would also change 1080p): the render functions use about 1.5 cores (one Python thread plus the encoder) of the 6 a 10 GB function has. A 4K render needs the memory, a 1080p render does not: its peak on QA is 1.4 GB.

## Credits
`common/wallet.credits_for_minutes(minutes, resolution)` is the one place the price is worked out: started minutes (at least 1, at most 12) times the resolution's `credits_multiplier` from `engine/format_options.RESOLUTIONS` (1, 1, 2). The launcher charges that, records `credits_charged` (and, for 4K only, `resolution` and `credits_multiplier`) on the video item together with the exact buckets charged, and the 402 body carries the doubled `needed`. A failed, rejected or unstarted 4K video refunds those exact buckets, i.e. the doubled amount. Edits and re-renders cost no credits at any resolution and keep the video's resolution (it lives in the plan's `frame`); an edit cannot change it.

## Capabilities (what the apps read)
`resolutions` lists only what is switched on, each with `credits_multiplier`, `aspects` and, for 4K, `label: "4K"` and a `note`; every platform has `supports_4k` (true for `youtube` and `other`) and `note_4k` (null there; elsewhere a sentence such as "TikTok publishes at 1080p or lower; 4K would cost twice the credits for no visible gain."). The server accepts 4K for any platform: the note is a recommendation the app must show, not a rule. The per-platform statements were not checked against each platform's current documentation; they follow the owner's decision and are worded "1080p or lower" on purpose. Edit them in `format_options.note_4k`.

## Limits and what was not verified
* Not run on Lambda: time, memory and cost at 4K are estimates (method above). Verify with `engine_selftest` and a real video on QA.
* No maximum length for 4K (12 minutes like everything else). If real renders turn out slower than estimated, lower `CHUNK_MAX_FRAMES_4K` first (more, shorter pieces), then `renderConcurrency` is the other lever.
* The person's own photos are at most 2048 px until the apps upload larger ones (out of scope here).
* Framed scenes (elements without a native layout in a vertical or square frame) draw a second full canvas; they render correctly at 4K but were only timed in 16:9.
* Playback: 4K H.264 at level 5.1 plays on current phones, computers and TVs and is accepted by YouTube; very old devices cannot decode it. No HEVC or AV1 version is made.
* Concurrency: a 12-minute 4K video holds up to 32 render functions for about 10 minutes; several at once need the account's Lambda concurrency to match.

## Files
`engine/frame.py` (sizes), `engine/format_options.py` (options, capabilities, multiplier, flag), `common/wallet.py` (price), `sf_launcher.py` (gate, charge, record, 402), `engine/renderer.py` + `canvas.py` + `scenes/viz_scenes.py` (4K frame), `engine/media.py` + `pipeline.py` (encoder), `engine/timeline.py` + `handlers/timeline_handler.py` + `handlers/render_chunk_handler.py` (pieces), `engine/assets.py` + `stock.py` + `usermedia.py` + `clips.py` + `handlers/beat_handler.py` + `handlers/plan_handler.py` (sources), `handlers/selftest_handler.py` (4K timing), `backend_stack.py` + `request_options.py` + `engine_v2.py` (flag, guard, finalize storage), tests in `backend/tests/test_four_k.py`.
