# The Producer: from "a topic" to "a brief plus media"

This corrects an earlier assumption. videomk is **not** "type a topic, pick some photos". The user gives a **brief**, and an AI **Producer** decides what the video contains: the story, the narration, and *which media appears when*.

## 1. The corrected product model

**Input is a brief**, in text or by voice, with optional attachments:
- *"A video about the Roman Empire."* (a topic: the Producer researches and illustrates everything)
- *"Here are 47 photos and 3 clips from our week in Mallorca. Make a fun story of it, group the beach days, end at the sunset dinner, upbeat music."* (the user's media is the raw material)

**The Producer decides, the user supervises.** It chooses structure and pacing, writes (or adapts) the narration, and builds a **media plan**: for every few seconds, the best type of visual and where it comes from. The user never has to pick a photo. Overrides exist ("use my photo here", "draw this instead", "shorter beach part"), but they are the exception, and can be asked for in plain language.

**What the backend already does, and what it doesn't.** Automatic photo choice is already built: a vision model reviews Unsplash/Openverse candidates and picks (or rejects). The gaps are the *shape* of the plan (today one visual per narration beat, drawn from eight scene types) and the *input* (today a topic only). The manual photo picker I put in the first design should have been an override, not a main-flow screen.

## 2. Media types the Producer can use

| Type | Source | Status |
|---|---|---|
| Scene cards: title, bullets, diagram, chart, timeline, big number, quote | generated from structured data | built (one per beat) |
| Library photo | Unsplash, Openverse; LLM-reviewed | built (one per beat); needs *many per beat*, cut every few seconds, with motion |
| Library video clip | stock video libraries (licences to verify) | new, later |
| **User photo** | uploaded | new: smart crop/motion, collage layouts, story ordering |
| **User video clip** | uploaded | new: trim to best moments, keep or mute audio, duck under narration |
| **Sketch (draw-on)** | drawn live as the narrator speaks | new: see §4 |
| Map | open map data (licences to verify, e.g. ODbL attribution) | new |
| Collage / grid | many user photos at once | new layout |
| AI-generated image | image models | optional premium only (costly, generic) |

## 3. How the Producer works (an agent with tools, inside a bounded pipeline)

```
Intake + safety  ─▶  Understand the media  ─▶  Plan the story  ─▶  Narrate  ─▶  Plan visuals to the words
                                                                                        │
Critic (watches frames, flags problems) ◀─ Render ◀─ Acquire / draw / lay out ◀────────┘
```

1. **Intake and safety:** read the brief, moderate text and every attachment *before* spending anything.
2. **Understand the media:** a vision model captions and tags each photo/clip; EXIF gives time and place (Mallorca, which day); drop duplicates and blurry shots; cluster into chapters; for clips: sample frames, detect scenes and speech, find the best moments.
3. **Plan the story:** chapters, narration (or the user's own words), pacing, music mood.
4. **Narrate:** TTS, or the user's recording (with their consent and moderation, if cloned).
5. **Plan visuals to the words:** a visual track of items, each with start/end, type, source and a one-line rationale ("shows the beach mentioned here"). Needs **word-accurate timing**; today word times are estimated, so forced alignment moves from "nice to have" to required.
6. **Acquire / draw / lay out:** library search + vision rerank, sketch generation, chart building, map rendering, placing user media.
7. **Render** (existing engine) and **critic pass**: vision model checks frames for overflow, mismatch, bad crops; re-render only what's flagged.

Agent tools: `analyze_asset`, `search_photos`, `search_video`, `make_chart`, `make_sketch`, `make_map`, `pick_music`, `place_media`, `ask_user` (rare). Every run has hard budgets (tool calls, dollars, seconds), checkpoints in S3, deterministic fallbacks, and an evaluation set of briefs. It runs as Step Functions steps with *bounded* tool-use loops, never an unbounded autonomous agent.

## 4. Sketches ("an auto sketch drawing what you're saying")

Whiteboard-style drawings that animate stroke by stroke in sync with the narration. Realistic first approach: a curated, permissively licensed **icon/illustration set** (stroke-based: Lucide, Tabler, Material Symbols are candidates; licences to confirm) plus lines, arrows, labels and simple shapes; the Producer *composes* a scene (e.g. sun → raindrop → eye) and the renderer animates the strokes with a slight hand-drawn wobble. Alternatives: LLM-authored SVG (cheap, quality varies), or generated image + vectorisation (costly). **Prototype and judge the quality before committing the design to it.**

## 5. What changes in the engine

- **Timeline model:** from `scenes` (one visual per beat) to **tracks**: narration, **visual items** (each with its own start/end, type, source, rationale), overlays (captions, watermark, credits), music. A v2 beat becomes one visual item spanning the beat, so existing videos keep working.
- **Renderer:** already a pure function of time with content-addressed chunks, so new media types are additive; chunking and cache keys move from "scene" to "visual item group".
- **User media pipeline:** resumable/multipart uploads from phones, normalisation (images to bounded JPEG; metadata read, GPS stripped from the stored copy; videos to a bounded H.264 proxy), thumbnails, per-user storage prefix, retention and deletion, ownership checks.
- **Editing becomes conversational:** besides tapping a visual item, the user can tell the Producer *"make the beach part shorter"* or *"add a map of the island"*; the Producer turns that into validated edit operations (same operation model as today, extended to visual items).

## 6. Economics (from `backend/scripts/pricing_model.py`; estimates)

| Case | Cost per finished minute | Margin on the $9.99 pack at 5 credits/min |
|---|---|---|
| Today's assumption (0.8 photo items/min, reviewed one at a time) | $0.039 | ~10x |
| 10 library photos/min, each reviewed separately | $0.076 | **5.6x** |
| 10 photos/min, **one batched vision call per ~15 s** | $0.051 | 8.4x |
| 15 photos/min, batched | $0.058 | 7.3x |

So **batch the choice** (one call picks several photos for a stretch of narration) and cache aggressively. Extra one-off costs for user media: about **$0.15–0.50 to analyse 50 photos**, and about **$0.09 per minute of source video** to sample frames (plus transcription). The credit formula therefore needs a media component, or an allowance, once these are measured; pricing for uploads is still a decision (`PRICING.md`).

## 7. Risks and open questions (the serious ones first)

1. **Uploaded media is a safety and legal surface.** Moderation before processing, handling of illegal content (including mandatory reporting duties) and minors' images need **legal advice** before launch; store policies for UGC and AI apply. Not optional.
2. **Privacy:** faces, children, EXIF location. Clear consent copy, minimal retention, real deletion, no training on user media, GPS stripped from stored copies.
3. **Voice:** the user may *dictate the brief* (OS dictation, convenience only). Narration is always AI-generated by the Producer; the user's own recording is never used as narration (the Producer would have to build visuals around audio it did not write). No voice cloning.
4. **Rights:** user-supplied music/footage the user may not own; library video/music licences; the credits block grows when 100 photos are used.
5. **Quality bar for sketches** and for photo/story selection across 50+ photos; needs an evaluation set and human review.
6. **Latency and UX:** analysis + planning + render is long; progress must tell the story (see design).
7. **Agent reliability:** bounded loops, retries, fallbacks, cost caps.

## 8. Build order (a sequence, not a schedule)
1. Visual track + multiple automatic library photos per beat + word-accurate alignment.
2. User photos: upload, analysis, story ordering, collage/Ken Burns placement.
3. Sketches and maps.
4. User video clips (highlight reel only: trim, caption, cut to the story; not a timeline editor).
5. Conversational editing with the Producer.

## 9. Media definitions and upload limits

- **Sketch** = AI-directed whiteboard doodle, not an AI image. The Producer picks from curated stroke-icon sets and composes lines, arrows and labels that animate on as the words are spoken.
- **Video clips** = highlight reel only: the Producer trims and places short clips; no timeline editor.
- **Uploads are allowed on every tier, with hard caps** (items per video, per day, bytes, clip seconds), moderation before analysis, originals deleted after normalisation, per-account daily AI-spend cap, rate limits and device attestation.
- **Free tier: very few items** (proposed 5 photos + 1 clip of up to 10 s per video).
- **Pricing:** upload cost is included in the per-minute price, so the item allowance scales with minutes purchased (proposed paid cap: 4 photos and 0.5 clip per minute, at most 60 photos and 6 clips per video).
- **Why a cap is still needed:** upload cost scales with item count, not video length. A 1-minute video with 50 photos costs far more than a 1-minute video with none. Worst-pack margin with Producer visual density (15% store fee, lengths 1-12 min, 0.5 clips/min): at 5 credits/min, 5.8x with no uploads. At 6 credits/min with +10/20% bonus packs and 4 photos/min: 6.0x (low item cost) to 4.6x (high). At 7 credits/min: 7.0x to 5.3x. Reaching 7x robustly means about 7 credits/min, or smaller pack bonuses plus a tighter high-cost path (cheaper per-photo review).

## 10. No generated images in the base product

Visuals come only from open-license library photos (Unsplash, Openverse), the user's own uploads, AI-directed sketches, maps, charts and scene cards. Generative images are far costlier than anything else in the pipeline, so they are excluded from the per-minute price and the Producer never selects them on its own. If added later, they are a premium, opt-in tier, priced per image in credits at cost times the target margin, with a hard per-video cap. When no library photo fits a moment, the Producer falls back to a sketch, map, chart or scene card. The "high item cost" in the pricing grid refers to vision-model photo review and clip processing, not image generation.
