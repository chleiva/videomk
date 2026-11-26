# videomk's own library of AI-generated video clips: research and plan (2026-11-26)

Owner brief: about 100 high-quality, general b-roll clips that we generate once and reuse in many customers' videos. Quality first, then cost (about $100 total is fine). No hallucination artefacts. Clips play once, never looped (docs/CLIPS.md).
Everything below is dated 2026-11-26. **Verified** = read on the provider's own page or the AWS price list today. **Secondary** = a blog or reseller (indicative only). **Unverified** = could not be confirmed; do not rely on it.
This market moves monthly (Sora shut down in September, the Veo 3.1 preview in the Gemini API shut down in October): re-check prices on the day of purchase.

## 1. The plain answer

**Which model for a 100-clip library of general b-roll?** There is no single proven winner, and the honest answer is "run a blind 10-prompt pilot on three candidates before buying 100 clips". On the evidence found:
- **Best value and cleanest terms: Google (Veo 3.1 GA on Vertex, or Gemini Omni Flash 1.2).** Google's pricing page puts Omni Flash 1.2 at about $0.07 per second of 720p video (verified footnote), Veo 3.1 Lite/Fast at $0.05 to $0.12 per second, and Google Cloud's generative AI indemnity names Veo (GA versions on Vertex). Needs a new Google Cloud account.
- **Fastest way to compare many models with ONE account and ONE set of terms: the Runway API** (Gen-4.5 at $0.12/s, plus hosted Veo 3.1, Kling 3.0, Wan 3.0, Seedance 2.x, MiniMax H3; all prices verified on Runway's pricing page). Its terms say the company "does not restrict your commercial use of your Outputs".
- **Only thing we can call today without a new account: Luma Ray2 on Bedrock in `qa` (us-west-2)**, $0.75/s at 540p, $1.50/s at 720p (AWS price list, verified). Pilot done (section 7): 2 of 2 clips looked clean, but it is the most expensive per clip by 5 to 10 times and its "540p" output is 960x544.

**What will 100 clips cost?** Roughly **$50 to $120 total** on the cheap per-second models (Gemini/Veo Lite, Kling, Wan, Hailuo, Runway Gen-4.5) at a 50% reject rate (section 5), **$150 to $300** with Veo 3.1 Standard or Seedance 2.0, and **about $750 to $1,500** on Luma Ray2 through Bedrock. A 30-clip pilot costs $10 to $40.

**Hallucination risk?** For the scene types in section 3 (landscapes, sky, sea at distance, forest light, empty interiors, macro textures, abstract, no people) the risk is **low but not zero**: expect 20% to 40% of generations to be rejected by the automated checks even then, and **60%+ for anything with people, hands, animals walking, text or crowds** (which is why those are excluded). The pilot gave 0 of 2 rejects; that is not enough data to quote a rate, so the 40-60% budget assumption stays until the first 20 real clips are scored. Every clip also gets a human glance (section 4).

**What "we own it" can honestly mean.** In the US, purely AI-generated material is not copyrightable: the Copyright Office's Part 2 report (2025-01-29) says "given current generally available technology, prompts alone do not provide sufficient human control to make users of an AI system the authors of the output" ([copyright.gov](https://copyright.gov/newsnet/2025/1060.html)). So: the provider's terms give us (at best) the contractual right to use the outputs commercially, and nobody else can claim authorship of them, but **we cannot stop a third party copying a clip, and we cannot sell the clips as an exclusive asset**. What we have is a licence plus exclusivity in practice (nobody else has our file), plus protection for human-authored parts (selection, arrangement, editing, the finished explainer videos). Runway says outright "OUTPUTS MAY NOT BE UNIQUE AND SIMILAR OUTPUTS MAY BE GENERATED FOR OTHER USERS" (section 10.1(a)); Google reserves the same ("Google won't claim ownership over that content" while reserving the right to generate similar content for others, Gemini API Additional Terms). Do not market the library as "exclusive" or "copyrighted".

## 2. Comparison of what exists now

Price per second, no audio unless said. 5 s clip = 5x. "Audio" = native audio generated (we strip it; some providers charge more for it, so turn it off where an option exists).

### 2.1 Callable from our AWS accounts (Amazon Bedrock)

Checked with `aws bedrock list-foundation-models --by-output-modality VIDEO` on 2026-11-26:

| Region | Account | Video-output models |
|---|---|---|
| us-west-2 (prod's region) | `qa` 552357225438 | **`luma.ray-v2:0` only** (Luma AI, ACTIVE, ON_DEMAND, text input, video output) |
| eu-west-1 (QA's home), us-east-1, eu-north-1 | `qa` | **none** (Nova Reel is not listed; a secondary source says `amazon.nova-reel-v1:0/1:1` retired 2026-09-30, unverified) |
| us-west-2 | prod (`default`) | not checked: the brief forbids touching prod. Model availability is per region, so expect the same single model; the prod account would also need Luma access enabled and its own quota. |

Notes on Luma Ray2 on Bedrock (measured): async only (`start_async_invoke`, output to an S3 bucket **in us-west-2**), `duration` 5 s or 9 s, `resolution` 540p or 720p, aspect ratios incl. 9:16 (per AWS docs, [model-parameters-luma](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-luma.html)), `loop` flag. **Quota: 1 concurrent request** (`On-demand model inference concurrent requests for Luma Ray V2`, not adjustable in qa): a second `start_async_invoke` while one runs fails with ThrottlingException. A 5 s clip took about 60 s. Output is silent H.264. 540p returned **960x544 @ 24 fps**. Price: AWS Price List API (`AmazonBedrockFoundationModels`, us-west-2, queried today): **$0.75/s at 540p, $1.50/s at 720p**, so $3.75 or $7.50 per 5 s clip. Luma's own pages say Ray2 and Dream Machine are deprecated and Ray3.2 is current (secondary source, unverified; Bedrock still lists Ray2 as ACTIVE). Luma Ray3/3.2 are not on Bedrock.

### 2.2 External APIs (each needs an account the owner creates)

| Option | Quality for general b-roll (evidence) | Length / resolution / 9:16 | Audio | Price (source) | API |
|---|---|---|---|---|---|
| **Google Veo 3.1 / 3.1 Fast / 3.1 Lite** | Top-tier realism; Artificial Analysis (AA) arena puts Veo 3.1 at Elo 1094 in an undated snapshot, behind Seedance 2.0 (1211), HappyHorse (1211), Kling 3.0 Omni (1099) ([AA](https://artificialanalysis.ai/video/leaderboard/text-to-video), secondary snapshot). | 4/6/8 s; 720p and 1080p, 4K on Standard; 16:9 and 9:16 (Lite: [Google blog 2026-03-31](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/)) | Native; Runway lets you set `audio:false` ([Runway API ref](https://docs.dev.runwayml.com/api/)); Vertex video-only is cheaper (secondary: $0.20/s Standard) | Gemini API with audio (secondary, Apr 2026): Lite $0.05 (720p) / $0.08 (1080p); Fast $0.10 / $0.12; Standard $0.40. **Gemini API preview models were shut down 2026-10-22** ([AI Studio docs](https://aistudio.google.com/docs/video)); GA is on Vertex ("Gemini Enterprise Agent Platform"); Vertex prices **unverified** (page would not load). Via Runway no-audio: Veo 3.1 $0.20/s, Fast $0.10/s (**verified**, [Runway pricing](https://docs.dev.runwayml.com/guides/pricing/)) | Vertex AI, Runway, fal etc. |
| **Google Gemini Omni Flash 1.2** (`gemini-omni-1.2-flash`) | Led AA text-to-video with audio in an Aug 2026 roundup (1245 Elo, secondary) | 3 to 15 s; 360p/720p/1080p/4K ([AI Studio docs](https://aistudio.google.com/docs/video)) | Native | Google pricing page footnote: **about $0.07 per second of 720p video** (verified, [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing)); via Runway 7/10/21 credits/s at 720p/1080p/4K tiers = $0.07 to $0.21/s | Gemini API |
| **Runway Gen-4.5** | Marketed as Runway's flagship; no independent score found | 2 to 10 s (integer); `1280:720` and `720:1280` (9:16) (Runway API ref, verified) | No audio parameter | **12 credits/s = $0.12/s** (credit = $0.01; verified). Gen-4 Turbo $0.05/s | Runway API |
| **Kling 3.0** (Kuaishou) | Kling 3.0 Omni Elo 1099 (AA, secondary) | 3-15 s (secondary); 1080p; 9:16 | with/without | Via Runway: Standard 9 credits/s no audio = $0.09/s, Pro $0.12/s (verified). Direct: $0.10 to $0.48/s (secondary, unverified) | Kling Open Platform, Runway, resellers |
| **Seedance 2.0 / 2.5** (ByteDance) | Top of the AA arena (2.0: Elo 1211-1274 in two snapshots; secondary) | 4-30 s; 480p to 4K | native | Via Runway: 2.0 Mini 7/15 credits/s (480p/720p) = $0.07/$0.15; 2.0 Fast $0.11/$0.24; 2.0 $0.14/$0.30/$0.40/$1.50 (480p/720p/1080p/4K); 2.5 $0.20/$0.30/$0.68/$1.10 (verified) | Runway, BytePlus (not read) |
| **Wan 3.0** (Alibaba) | AA Nov 13 2026 ranking lists it first (MarkTechPost, secondary) | 480p/720p/1080p | ? | Via Runway $0.05/$0.10/$0.20 per s (480p/720p/1080p), "Prime" $0.068/$0.14/$0.28 (verified). **Weights are NOT open** (see 2.3) | Runway, Alibaba cloud |
| **MiniMax H3 / Hailuo 2.3** | MiniMax-H3 Elo 1242 in Aug 2026 (secondary) | 768p, 2K; 6 s or 10 s (Hailuo 2.3) | ? | Official ([platform.minimax.io pricing](https://platform.minimax.io/docs/guides/pricing-video), verified): H3 768p $0.08/s, 2K $0.13/s, Lite 768p $0.04/s; Hailuo 2.3 768p 6 s $0.28, 1080p 6 s $0.49 | MiniMax API |
| **OpenAI Sora 2** | n/a | n/a | n/a | **Shut down 2026-09-24** ("The Sora 2 models and Videos API were shut down on September 24, 2026"; [OpenAI model page](https://developers.openai.com/api/docs/models/sora-2), verified). Not an option. | none |
| **Luma Ray3.2 / Agents API** | Marketed for pro pipelines; no independent score | 5 s or 10 s blocks; 360p to 1080p; 9:16, 1:1, 21:9 ([Luma API pricing](https://lumalabs.ai/api/pricing)) | n/a | Credits: T2V 5 s = 20 / 50 / 100 / 400 credits at 360p / 540p / 720p / 1080p; USD per credit depends on plan or contract (verified: not published). Secondary: about $0.17/s | Luma API (direct) |
| **Pika** | Not researched in depth | | | **Unverified**, no source read | |
| **Moonvalley Marey** (trained only on licensed data) | Marketed as the "clean" model for pros; no independent score | 5 s / 10 s, up to 1080p | no | Conflicting: fal.ai Marey Realism V1.5 $1.50 per 5 s (secondary); a reseller $3.90/s (secondary). No official price sheet found; Moonvalley's terms URL returned 404 | Moonvalley, fal.ai |
| **Adobe Firefly Video** (marketed "commercially safe") | Mixed reviews in Adobe's own community (secondary) | up to 1080p, 5 s | no | Firefly Services rate card: Video Model 1 at 540p 0.4 "Operations" per second, 720p 2.5, 1080p 5 (Adobe help page, secondary read); USD per Operation not published; "rates negotiated individually" (community answer). Endpoint `generateVideoV3` reported. | Firefly Services API (enterprise contract) |
| **Amazon Nova Reel** | n/a | | | Not listed in `qa` in any region; reported retired (secondary, unverified) | |

### 2.3 Open weights we could self-host (single L40S 48 GB, g6e.xlarge, $1.974/h in eu-north-1 per `backend/scripts/gpu_lab.py`)

| Model | Licence (source) | What it is | Fit on L40S / time |
|---|---|---|---|
| **Wan 2.2 (A14B and TI2V-5B)** | **Apache 2.0**, "We claim no rights over the your generated contents" ([HF model card](https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B)) | 480p/720p, 5 s, 24 fps. This is the **last open Wan**: Wan 2.5, 2.6, 2.7 and 3.0 are API-only (secondary: howaiworks.ai, atlascloud; one site claims otherwise, treat as wrong) | A14B: card says single GPU needs 80 GB or offload flags, so on 48 GB it needs offloading (slow; time not stated, unverified). TI2V-5B: "under 9 minutes" for 5 s 720p on one 24 GB consumer GPU ([card](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B)); an L40S should be similar or faster, **estimate** about $0.30 per clip of GPU. |
| **LTX-Video / LTX-2 / 2.3** (Lightricks) | "Community licence", not OSI: free commercial use only under **$10M annual revenue**; above that a paid licence (secondary: wavespeed, press; primary PDF not read) | 1216x704 @ 30 fps (0.9.x), 4K and audio in 2.3 (22B) | Not measured. Fast (the 2B distilled is "real-time capable"). Quality below Wan 2.2/Veo for realism (unverified). |
| **HunyuanVideo / 1.5** (Tencent) | **Licence "does not apply in the European Union, United Kingdom and South Korea"**, 100M MAU cap, no use of outputs to train other models ([LICENSE](https://huggingface.co/tencent/HunyuanVideo/blob/main/LICENSE), verified for the original; 1.5's licence text not seen) | 480p/720p, 121 frames; 14 GB with offload (GitHub README) | **Do not use** if any operator, customer or server is in the EU/UK. |
| **CogVideoX, Mochi 1** | Not checked this session (Mochi 1 was Apache 2.0 at launch, CogVideoX-5B under a custom licence: from memory, **unverified**) | older, lower quality | skip |

**GPU test: not run.** The rule was "only if the research shows it is worth it". It does not yet: the best open model we may legally use (Wan 2.2) is a year old, its realism is below the API leaders on every ranking found, and its per-clip cost (about $0.30 plus set-up) is similar to the cheap APIs. Worth reconsidering only if the owner wants zero per-clip terms. Worst case if we do: two sessions of 90 min on g6e.xlarge = 2 x (1.974 x 1.5 = $2.96) = $5.92 plus disk; `gpu_lab.py up` prints the exact number before starting.

## 3. Ownership and licence terms, quoted from the provider (URL, read 2026-11-26)

Reading rule: what matters for a library is (a) who owns outputs, (b) commercial use, (c) "may not resell/distribute outputs as media or build a competing library", (d) training, (e) indemnity, (f) watermark/disclosure. Our actual use is **embedding clips in customers' finished explainer videos**, not selling or distributing the clip files; (c) only bites if we ever let customers browse and download raw clips.

| Provider | Ownership / commercial | Restrictions that matter for a library | Indemnity | Watermark / disclosure |
|---|---|---|---|---|
| **Runway** ([runway.com/terms-of-use](https://runway.com/terms-of-use)) | "The Company does not claim ownership of any of your Inputs or Outputs." (s4.4) "Subject to your compliance with the Agreement, the Company does not restrict your commercial use of your Outputs." | s1.3(a): "you shall not license, sell, rent, lease, transfer, assign, reproduce, distribute, host, or similarly exploit" the Services (read as the Services; applies to outputs only in context, **ask Runway if we want to host a downloadable clip library**). s5(viii): may not use Outputs "to create, train, develop, or improve similar or competitive products". Runway may train on Inputs and Outputs (s4.4). | We indemnify Runway (s9); **Runway indemnifies nobody** | none found; s10.1(a) "OUTPUTS MAY NOT BE UNIQUE AND SIMILAR OUTPUTS MAY BE GENERATED FOR OTHER USERS". These are the web terms; the **API terms may differ: unverified**. |
| **Luma** ([lumalabs.ai/legal/tos](https://lumalabs.ai/legal/tos), also governs Bedrock? **unverified**: on Bedrock the AWS service terms apply) | "Customer owns and retains all right, title, and interest in and to the Output"; commercial use only "if the Outputs were produced during an active Subscription Term" | May not "distribute, sell, or otherwise make available any Output through any marketplace or store not owned or operated by Luma" (not applicable to paid subscriptions that permit commercial use); may not use Outputs "to create, test, train" AI models; Luma may train on outputs | We indemnify Luma for claims from Input or Output | Luma may embed watermarks/content credentials, we must not remove them; **a person-like output must be publicly disclosed as AI-generated** |
| **Google Gemini API** (Additional Terms, Dec 2025 archive: [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms-archive/terms_12_18_25)) | "Google won't claim ownership over that content." "You're responsible for your use of generated content." Paid tier: Google does not use prompts or responses to improve products | Unpaid tier: Google may use content to train. | none on the Gemini API (the indemnity is Cloud-only) | SynthID watermark on Veo output (Google docs; this session could not load the Veo page, **unverified**) |
| **Google Cloud / Vertex** ([Generative AI Indemnified Services](https://cloud.google.com/terms/generative-ai-indemnified-services)) | Google Cloud customers keep their data and outputs (standard Cloud terms, not re-read) | Preview products: evaluation and testing only unless permitted; **use GA versions** | Search result quote: the indemnity applies to "Gemini Enterprise Agent Platform API (formerly Vertex AI API) used with generally available versions of these foundation models: Codey, Gemini, Imagen, PaLM, **Veo**". The indemnity text itself and whether Omni Flash is covered: **not read, unverified** | SynthID |
| **Kling** ([kling.ai/docs/user-policy](https://kling.ai/docs/user-policy), page would not load fully) | Secondary summaries: user keeps IP and Kling "does not claim ownership"; free plan not commercial | Broad licence back to Kling (secondary: includes model training); watermark removal tied to paid plan | not found | watermark on free tier |
| **MiniMax / ByteDance / Alibaba (Wan 3.0 API)** | **Unverified**: terms pages not read | | | |
| **Moonvalley Marey** | Marketed: "fully licensed" training data (press, fal.ai listing carries "Commercial use"); **official terms 404, unverified** | | Marketing mentions enterprise IP protections; not read | |
| **Adobe Firefly** ([Gen AI user guidelines](https://www.adobe.com/legal/licenses-terms/adobe-gen-ai-user-guidelines.html)) | Page read says nothing on ownership or indemnity. "commercially safe" is Adobe's marketing; **indemnity for API video unverified** (a community moderator links price to indemnity, not authoritative). | users "must not remove, alter, or disable any Content Credentials" | **unverified** | Content Credentials |
| **Wan 2.2 / HunyuanVideo / LTX** | see 2.3 | | none (open weights) | none |

Provider "commercially safe" claims are only as good as the contract: **only Google Cloud (Veo GA on Vertex) has an indemnity we found named in a Google page**; every other provider either indemnifies nobody or we could not read it. For a library reused in many customers' videos, indemnity is worth real money, so this weighs towards Google on Vertex and away from the aggregators. One more caution: a model hosted by Runway (Veo, Kling, Seedance, Wan) is probably governed by Runway's terms plus the upstream vendor's acceptable-use terms: **unverified**.

## 4. Ranking for our use

Criteria: quality for artefact-free general b-roll (weighted most), price, terms, how fast we can start. Quality evidence is thin and conflicting: the Artificial Analysis arena is blind human preference **with audio, mixed prompts, not our b-roll**, and three snapshots disagree on the order (Seedance 2.0 first in April and in the undated one, Gemini Omni Flash first in August, Wan 3.0 first on November 13). Treat the arena as "these are all near the top", not as a ranking.

1. **Google: Veo 3.1 (GA on Vertex) and Gemini Omni Flash 1.2.** Cheapest credible top-tier quality ($0.07/s Omni 720p verified; Veo Lite/Fast $0.05-0.12), the only indemnity found, 9:16 and 1080p native, 4-8 s clips. Risks: Vertex pricing and the Veo GA model list not read; new Google Cloud account; native audio is on by default (turn off or strip).
2. **Runway API (Gen-4.5 plus its hosted Kling 3.0, Veo 3.1, Wan 3.0, Seedance 2.x).** Not one model but one account with all the strong competitors and verified per-second prices; terms read and permissive for commercial use (no indemnity, no uniqueness). The right instrument for the blind pilot. 9:16 native on Gen-4.5.
3. **Luma Ray2 on Bedrock.** Only option callable with no new account, price verified on the AWS price list, our own pilot looked clean, billing on the AWS invoice. But 5-10x the price, "540p" is 960x544 and 720p costs $7.50 a clip, concurrency 1, and Luma calls Ray2 deprecated.

Runners-up worth a look in the pilot if cost matters: MiniMax H3 ($0.08/s, official price read) and Kling 3.0 Standard ($0.09/s via Runway). Not recommended: Sora (shut down), Hunyuan (EU/UK excluded), LTX (revenue-gated licence), Wan 2.2 self-host (older, similar per-clip cost).

**Only marketing so far (no independent evidence found):** "Gen-4.5 is the most realistic", Firefly "commercially safe" for video via API, Marey "clean data = no legal risk", Luma Ray3.2 "pro pipeline" claims, any provider's "no artefacts" statement.

## 5. Hallucination control plan

### 5.1 Scenes that are safe to generate (reliably clean on current models)

Safe: calm landscapes and aerials; sky and cloud time-lapses; forest light, leaves, moss; sea and rivers shot wide with slow swells (the pilot's waves clip was clean but slightly smooth); fog, rain on glass, snow falling; empty interiors with moving light (offices, rooms, cafes, libraries); macro textures (dew, honey in a jar, coffee beans); steam; candles and bokeh lights; abstract flowing particles, gradients, fibre-optic and circuit macros; space and planets; slow architecture glides with **no readable signs**.
Why these work: continuous textures with no identity to keep (a cloud has no wrong shape), no articulated bodies, simple camera motion (one slow move), little occlusion.

Avoid (reject-prone, and mostly not needed because stock footage already covers them): people (faces, hands, walking gaits, crowds), hands typing or pouring, animals with legs in motion (bees, birds, elephants), vehicles driving (wheels, plates), anything with text, signs, logos, screens, books with legible pages, clocks, flags, maps, liquids being poured or splashing close up, fast motion, fire close up, complex machinery (gears are borderline: kept at 1), reflections in water with detailed buildings, bridges and railings (geometry drift), named real places (the model invents the landmark). Where the demand mining wants a person (commuters, hands typing) the library does not serve it: stock stays the provider for those beats.

### 5.2 Prompt pattern

`<one subject>, <one slow camera move>, <light and time of day>, <lens/format>. Photorealistic footage, no people, no text.`
- One subject, one verb, one camera move ("camera slowly pushes forward", "locked-off", "slow lateral glide"). Never two actions.
- Say "locked-off" or "steady" for geometry-heavy scenes; add "wide shot" to hide detail.
- Name the light ("soft morning light", "golden hour"): lighting consistency is the easiest thing for the model to hold.
- Durations 4 to 6 s (artefacts grow with length; the engine uses clips of 2-12 s, docs/CLIPS.md).
- Negative prompt where supported (Veo via Runway `negativePrompt`, Vertex `negativePrompt`; not Gen-4.5 or Luma Ray2): `people, faces, hands, text, letters, logos, watermark, signs, flicker, distortion, morphing, blur, low quality, cartoon`. Where not supported, the same exclusions go at the end of the prompt as "no people, no text".
- Fixed `seed` per prompt where offered, so a re-run after a QA reject varies on purpose (new seed) and a good clip is reproducible.
- Generate at the native 16:9; for 9:16 and 1:1 crop (section 8), do not re-generate.

### 5.3 Automated QA pipeline (`backend/scripts/video_catalog_qa.py`, tested by `backend/tests/test_video_catalog_qa.py` with synthetic ffmpeg videos)

1. **Technical** (ffprobe): readable, 3 to 10 s, width >= 640, audio stream noted (stripped at ingest).
2. **Temporal heuristics** on 160x90 grey frames at the native 24 fps via ffmpeg and numpy (no OpenCV): (a) *sudden change*: a frame step at least 6x its local median and above 0.06 mean abs difference = cut, pop or an object swapping; (b) *flicker*: 3 alternating luminance jumps of at least 0.035; (c) *content replaced*: correlation between consecutive frames collapses against its neighbours; (d) *freeze*: run of identical frames over 0.8 s; (e) *static*: median step under 0.0015 (b-roll that never moves is a photo). The tests prove (a), (b), (d), (e) fire on synthetic clips made with ffmpeg and that a clean moving clip raises nothing. These cannot see slow morphing of a shape (that is the vision layer's job) and are tuned on synthetic data only: **re-tune after the first 20 real clips**. Flicker at the 24 fps rate would alias away at lower analysis rates, hence the native rate.
3. **Vision rubric** (Claude through Bedrock `llm.complete`, same helper and review model as `engine/clips.py verify`): 6 frames per clip (5%, 25%, two consecutive frames at 50% about 0.25 s apart, 75%, 95%); score 0-10 in `anatomy, objects, physics, text_logos, geometry, texture_flicker, realism, subject_match`; JSON out. Cost measured: **$0.0005 per clip** (one Haiku-class call).
4. **Reject rules** (`decide`): any technical or temporal issue rejects; any severe category (`anatomy, objects, physics, text_logos, geometry, texture_flicker`) under 5 rejects; any category under 7 rejects; unreadable vision answer rejects (fails closed, like `verify`). **Review** (human): vision check not run, verdict "fail" without a low score, or mean under 8.0. **Accept**: everything else.
5. **Human review sheet**: `video_catalog_qa.py sheet *.mp4 --out sheet.png` (6 frames per clip per row) plus one markdown row per clip (`review_row`: decision, scores, reasons, empty "ok / redo / drop" column). A person looks at **every** accepted clip once (100 rows at a glance, minutes), at full speed for the review band. The vision model is a filter, not an authority: it scored the pilot clips 8-10 on everything and my own viewing agrees, but "agrees" is n=2.
6. **Redo budget**: a rejected prompt is regenerated up to twice with new seeds; a prompt rejected 3 times is dropped or rewritten (it is probably a risky scene).

Rubric text lives in the code (`RUBRIC`, `VISION_SYSTEM`); change it there, not here.

## 6. Budget plan for 100 accepted clips

5 s clip = 5 x per-second price (Veo: 6 s, the nearest allowed length, noted). Cost per accepted clip = generation cost / (1 - reject rate). QA vision adds $0.0005 per candidate (nothing). Totals for the 100 accepted clips at reject rates **40% / 50% / 60%** (multipliers 1.67 / 2.0 / 2.5). Candidates must be **at least** the number of accepted clips at 0% rejects.

| Model (source, status) | Cost per generated clip | Per accepted clip at 50% | 100 clips at 40% / 50% / 60% |
|---|---|---|---|
| Gemini Omni Flash 1.2, 720p, 5 s (Google footnote ~$0.07/s; includes audio we cannot turn off: unverified) | $0.35 | $0.70 | $58 / $70 / $88 |
| Veo 3.1 Lite 1080p, 6 s, Gemini-API-style price with audio $0.08/s (Vertex price unverified; Gemini API preview is shut down) | $0.48 | $0.96 | $80 / $96 / $120 |
| Veo 3.1 Fast via Runway, no audio, 6 s ($0.10/s, verified) | $0.60 | $1.20 | $100 / $120 / $150 |
| Runway Gen-4.5, 5 s ($0.12/s, verified) | $0.60 | $1.20 | $100 / $120 / $150 |
| Kling 3.0 Standard via Runway, 5 s ($0.09/s, verified) | $0.45 | $0.90 | $75 / $90 / $113 |
| MiniMax H3 768p, 5 s ($0.08/s official) | $0.40 | $0.80 | $67 / $80 / $100 |
| Wan 3.0 720p via Runway, 5 s ($0.10/s) | $0.50 | $1.00 | $83 / $100 / $125 |
| Seedance 2.0 Mini 720p via Runway, 5 s ($0.15/s) | $0.75 | $1.50 | $125 / $150 / $188 |
| Veo 3.1 Standard via Runway, no audio, 6 s ($0.20/s) | $1.20 | $2.40 | $200 / $240 / $300 |
| Seedance 2.0 720p via Runway, 5 s ($0.30/s) | $1.50 | $3.00 | $250 / $300 / $375 |
| **Luma Ray2 Bedrock 540p, 5 s ($0.75/s, AWS price list)** | $3.75 | $7.50 | $625 / $750 / $938 |
| Luma Ray2 Bedrock 720p, 5 s ($1.50/s) | $7.50 | $15.00 | $1,250 / $1,500 / $1,875 |
| Wan 2.2 TI2V-5B self-hosted, L40S at $1.974/h, about 9 min (estimate; GPU only, plus up to $6 of set-up sessions) | about $0.30 | about $0.60 | $50 / $60 / $75 |

Mind the reject-rate assumption: 40-60% is a guess for the risky kinds of scene, the library scene list (section 9) avoids those, so reality may be 20-40% (cheaper). Not included: your time reviewing, upscaling (if 1080p is needed from a 720p model: an upscale pass on the same GPU or a provider tool, unpriced), storage (a 5 s 1080p H.264 clip is about 3-6 MB, 100 clips under 1 GB: pennies in S3).

### Recommended pilot (about 10 prompts, identical prompts, blind)

Use prompts 1, 11, 23, 24, 35, 37, 47, 53, 64, 77 of the list in section 9 (one per cluster, mix of easy and risky). Each prompt on:
- **Veo 3.1 Fast via Runway, no audio, 6 s: $0.60 x 10 = $6.00**
- **Runway Gen-4.5, 5 s: $0.60 x 10 = $6.00**
- Gemini Omni Flash 1.2 (Gemini API, 5 s: about $0.35 x 10 = $3.50) once the Google key exists
- optionally Kling 3.0 Standard via Runway ($4.50) and MiniMax H3 ($4.00)
- Luma Ray2 on Bedrock stays at the 2 clips already made ($7.50); more would cost $3.75 each.
**Total for the two top candidates plus Omni: about $15.50; with Kling and MiniMax about $24**; including one retry per failure about $30. Then compare QA scores and the contact sheets side by side, blind, and pick one model for the 100.

### Which pilot calls need no new account?

- **Bedrock `qa`: Luma Ray2 only** (done, section 7). Nothing else callable.
- **Self-hosted open weights on the GPU lab** (Wan 2.2): possible with `gpu_lab.py up`, not done (reasons in 2.3).
- Everything else needs an account the owner creates:
  1. **Runway**: sign up at dev.runwayml.com, create an organisation and API key, buy credits (credits are $0.01 each; that credits are prepaid per project is from Runway's pricing page, but whether an auto-top-up exists was not checked: leave auto-recharge OFF so the balance is the cap; buy $30 first). Store the key in SSM `/videomk/runway_api_key` (SecureString) in `qa` only.
  2. **Google Cloud (Vertex)**: create a project with billing, **set a budget with alert and a daily quota cap** (Vertex quotas: requests per minute for Veo; set the lowest), enable the Vertex AI API, create a service account with only `aiplatform.user`; store the JSON in SSM `/videomk/vertex_sa_json`. Or the Gemini API key `/videomk/gemini_api_key` (AI Studio spend cap in the console) for Omni Flash. Check that the model we want is GA (indemnity applies to GA only).
  3. **MiniMax** (optional): platform.minimax.io, prepaid balance, key to `/videomk/minimax_api_key`.
  Spend caps to set: Runway $30 prepaid; Google budget alert at $30 with a hard quota; MiniMax $10 prepaid.


## 7. Pilot actually run: Luma Ray2 on Bedrock (`qa`, us-west-2)

Spend ledger (also in `.../scratchpad/video_catalog/spend_ledger.txt`). Cap: USD 10. Bedrock bills on completion; the cost is computed from the AWS Price List rate (Cost Explorer lags a day, so the invoice line is **not yet confirmed**).

| Time (2026-11-26) | Call | Result | Cost |
|---|---|---|---|
| 12:27 | `luma.ray-v2:0` 5 s, 540p, 16:9, "valley" | Completed (~60 s) | $3.75 |
| 12:27 | second call in the same second ("waves") | **ThrottlingException** (concurrency quota 1), no charge | $0 |
| ~12:30 | "waves" 5 s, 540p, 16:9 | Completed | $3.75 |
| | **Total estimated** | 2 clips | **$7.50 of $10.00** |

Housekeeping: a temporary S3 bucket `videomk-qa-vidpilot-552357225438` (us-west-2) was created for the async output (Bedrock needs an output bucket in the model's region) and **deleted** afterwards; local copies are in the scratchpad. Nothing else was created in the account. QA vision scoring used Haiku 5.5 through Bedrock: about $0.001 for both clips.

Files in `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/video_catalog/`: `ray2_valley.mp4`, `ray2_waves.mp4`, `sheet_ray2.png` (frame grid, 6 frames per clip), `qa_valley.json`, `qa_waves.json`.

Prompts: "valley" = *Slow aerial glide forward over a calm green mountain valley at sunrise, soft mist lying in the low areas, gentle steady camera movement, natural light, photorealistic nature footage*; "waves" = *Gentle ocean waves rolling onto a sandy beach at golden hour, wide shot, slow steady camera, natural light, photorealistic nature footage*.

**What I saw on the frames (viewed, 6 per clip):**
- *Valley*: realistic: hills, a thin layer of mist, a soft sunrise sky. The camera drifts forward and the mist band slides plausibly. Hill outlines, mist edge and tree clumps stay stable from start to end; no warping, no text, no flicker I could see. It is soft (540p source, looks like slightly diffused photography) and the grass foreground is a little smeared.
- *Waves*: a wave rolls in, breaks into white foam and washes onto wet sand with a believable sheen. The foam edge and the horizontal swell look natural; the water surface is slightly smooth and over-processed (the vision model said the same), and the beach has a single hard line where the wash ends that looks a bit too straight. No impossible physics visible.
- Both clips: silent; 960x544 at 24 fps; 5.17 s.
- Limits of this evidence: **two clips, easy prompts, still frames only** (I cannot watch motion: motion defects are only covered by the temporal heuristics, which found nothing). Not enough to quote a reject rate.

**QA scores (`video_catalog_qa.py score`):** both ACCEPT. Valley: anatomy 10, objects 8, physics 8, text 10, geometry 7, texture/flicker 8, realism 8, subject 9 (cost $0.0005). Waves: 10 / 8 / 8 / 10 / 8 / 8 / realism 7 / 9, mean 8.5 (cost $0.0005); temporal: median step 0.0082, max 0.0146, no spikes, no flicker, no freeze. The vision model (Haiku-class) is generous: it never gave a score under 7 to either clip, and I did not stress-test it with a bad clip from a real model, only the synthetic videos in the tests. Expect it to miss subtle artefacts: the human sheet stays.

Takeaways: Ray2 can deliver clean calm-nature b-roll, but at 960x544 the library would need upscaling for a 1080p timeline (the engine's clips are 1280x720; `docs/CLIPS.md`), and $0.75 to $1.50 per second makes it the wrong choice for 100 clips unless nothing else is obtainable.

## 8. Catalog plan (design only; the image builder owns the shared pieces)

**Shared with the image catalog (not re-designed here):** content-hash ids (sha256 of the final normalised mp4, prefix `vid_`), Cohere Embed v4 embeddings through Bedrock (never Titan), S3 Vectors index, provenance metadata, QA to prod promotion without paying twice (copy the S3 object and its vector rows across accounts; the provenance row carries the generation record so prod never regenerates).

**What differs for video:**
- **Master**: generate at 16:9 (the engine plays 1280x720 H.264, 30 fps, no audio; for 4K videos 1920x1080, `clips.clip_size`). Store the provider's original (kept for re-crops and upscale) and the normalised master. Sizes: provider original 5 s 720p-1080p about 2-8 MB, normalised 1280x720 about 1 MB per 5 s (docs/CLIPS.md says about 1 MB per 10 s), so 100 clips are about 100-600 MB: negligible.
- **Safe crop**: prompts keep the subject centre-weighted ("subject in the centre of frame") because `clips.transcode` already crops 9:16 with the offset `(ih-oh)*0.46` and 1:1 centred; QA reviews the 9:16 and 1:1 crops of every accepted clip on the sheet (add the crop thumbnails to the sheet in a later iteration). Do not generate 9:16 natively (Veo and Gen-4.5 can, but the crop of a landscape master is reusable for all three shapes, and costs nothing).
- **Frames to embed**: 3 frames per clip (the same `verify_frame_times` points 12/50/88%) embedded with Cohere Embed v4 (image) plus the generation prompt and the "serves" queries embedded as text; the vector row stores `clip_id`, `seconds`, `has_motion`, `qa_scores`, `model`, `prompt`, `licence_basis`. Search = text query embedding against the frame vectors, max-pooled per clip (several frames per clip, unlike one image per row).
- **"serves" list**: each clip gets 5-15 generic queries it answers (examples: "waves crashing on a coast", "calm sea at sunset", "ocean waves", "olas del mar"), written in English and Spanish, embedded as text so a planner query matches either the frames or a serves phrase. The serves are generated once with a short Claude call from the prompt and checked by a person.
- **Length use**: the engine plays library clips **once, never looped, last frame held at most 0.5 s** (`MONTAGE_MAX_HOLD_S = 0.5`, `engine/clips.py`); so the library must contain clips at least as long as the beat. Library clips are 4-6 s (sea, sky 6 s). A beat longer than the clip falls back to another candidate or to stock (the montage path of the last commit already assembles 2-4 short clips). A 5 s clip covers a 12-14 word beat; at about 2.5 words/s that is most clip beats (CLIPS.md: 10-18 words).
- **Credits and attribution**: library clips carry no third-party credit; the on-screen credit is not needed. If a provider requires disclosure (Luma: when a person-like output appears; none shown since we exclude people) we log it in the provenance row. Keep the SynthID/Content Credentials metadata in the stored original and do not strip it (Luma and Adobe terms forbid removal); the normalised master is a re-encode that drops container metadata, so the **original with credentials is kept**.

**Plugging into `scout_clip` (behind a flag):** `engine/clips.py scout_clip` gathers candidates from stock sources and reviews and verifies them. Add `library` as one more provider **ahead of stock**, enabled by `VIDEO_LIBRARY_ENABLED=1` (default off), implemented as a function `library_candidates(query, alt, orientation)` returning the same candidate dicts (`url`, `source="library"`, `licence="owned"`, `seconds`, poster URLs) from an S3 Vectors query (top 5 clip candidates above a similarity threshold). Library candidates then pass through the **same** `_review` (poster frames) and `verify` (3 frames, score >= `VERIFY_MIN_SCORE`) as stock; a library clip that fails verification for this beat simply loses, stock is searched next. The no-loop rule and `transcode` normalisation are unchanged. The stock credit line is skipped for `source="library"`. Telemetry: count library hits so we can see how much of the demand is served (see clusters below) and which `serves` queries missed. Nothing in this section is implemented: this is the plan.

**Demand mined from real plans** (QA bucket `videomk-qa-552357225438`, `generation/v2/*/plan_r*.json`, 156 plan files, 152 prefixes; 80 `clip_query` scenes in 46 distinct videos; method: keyword clusters, overlapping, counts are beats and distinct videos):

| Cluster (examples of real queries) | Beats | Videos | In the library? |
|---|---|---|---|
| Forest, jungle, mist, sunbeams, leaves, dew ("misty fern forest", "forest sunlight through trees", "fresh green leaves water droplets") | 21 | 14 | yes: cluster A |
| People walking city streets, crowds, trams, plazas ("people walking city street morning", "yellow tram city street") | 14 | 13 | **no (people): stock**; empty streets and light trails in D |
| Sky, clouds, fields, savanna, wheat ("blue sky white clouds", "wheat fields wind landscape", "savanna africa sunrise grass") | 15 | 9 | yes: cluster B |
| Sea, waves, coast ("ocean waves rolling", "storm waves crashing coast", "night ocean waves") | 10 | 9 | yes: cluster C |
| Parks, children, family, cafes (people) | 12 | 8 | **no (people): stock**; empty park/playground in D/H |
| Festive lights, Christmas markets, night | 9 | 7 | yes: cluster E (lights only, no crowds) |
| Skyline, rooftops, apartment windows, dusk | 8 | 6 | yes: cluster D |
| River, lake, golden-hour reflections | 8 | 6 | yes: cluster C |
| Hands, typing, office, stairs, bathroom routine | 6 | 5 | partial: empty office/desk (H); hands: stock |
| Steam, hot drink, coconut, coffee | 5 | 4 | yes: cluster F |
| Waterfall, lava, microscope, servers, film crew | 5 | 4 | partial: waterfall, servers, microscopic abstract (C, G); crew: stock |
| Bees, hive, flowers | 5 | 3 | **no (insect legs)**: stock |

So roughly **60% of the real clip demand is scenery, light, sky, sea and objects that the library can serve; about 40% involves people, hands or insects and stays with stock** (judgement from the 80 queries, not measured against a catalogue). A library of the 100 prompts below is expected to cover those 60% only if the planner's wording matches the "serves" list: measure with `clip_supply.py` style hit rates once built. Caveat: only 80 queries from QA plans (mostly test videos, many repeated topics such as Paris, Rome, Christmas markets, bees), so the clusters are indicative.

## 9. First 100 scene prompts (ordered by expected reuse: clusters A to I in demand order)

Same list as JSON for the generator: `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/gen/prompts100.json`. Every prompt avoids people, hands, animals, vehicles, text and named places, serves at least three different video topics (last column), and gets the suffix shown in the header. Durations: 5 s; 6 s where the move is a glide, aerial or time-lapse. Ordering inside clusters is by demand (first the most-requested wording).

| # | Cluster | Generation prompt (append: `Slow, steady camera, natural light, photorealistic footage, no people, no text.`) | Dur | Serves (>= 3 video topics) |
|---|---|---|---|---|
| 1 | A forest | sunbeams streaming through tall green forest canopy, dust motes drifting, camera slowly pushing forward | 6 s | photosynthesis, life on earth, relaxation, autumn/seasons, ecology |
| 2 | A forest | dense ferns and moss in misty woodland, slow lateral camera glide at ground level | 6 s | prehistoric life, rainforests, calm, climate |
| 3 | A forest | green leaves with dew drops swaying gently in soft morning light, macro, shallow depth of field | 5 s | photosynthesis, plants, spring, wellbeing |
| 4 | A forest | golden autumn leaves drifting down through still air in a park, soft backlight | 6 s | autumn, seasons, time passing, nostalgia |
| 5 | A forest | aerial slow glide over an unbroken green forest at sunrise with low mist between hills | 6 s | climate, geography, travel, conservation |
| 6 | A forest | tall pine forest in winter fog, snow on branches, slow forward move | 5 s | winter, solitude, climate, travel |
| 7 | A forest | tropical rainforest canopy after rain, steam rising, slow tilt up the trunks | 5 s | biodiversity, climate, travel, evolution |
| 8 | A forest | a narrow dirt path winding through a sunlit birch forest, camera gliding along it | 5 s | journeys, walking, wellbeing, nature |
| 9 | A forest | fresh green seedlings growing in dark soil, soft light, macro, slow push-in | 5 s | growth, farming, startups, biology |
| 10 | A forest | sunlit meadow edge with tall grass and wildflowers moving in the wind, forest behind | 5 s | spring, farming, wellbeing, biodiversity |
| 11 | B sky and land | clear blue sky with soft white clouds drifting slowly, camera tilted up | 6 s | weather, science (why sky is blue), kids, travel |
| 12 | B sky and land | time-lapse of towering cumulus clouds building over open fields | 6 s | weather, storms, climate, geography |
| 13 | B sky and land | dark storm clouds rolling over a flat plain, moody light, no lightning | 5 s | storms, climate, news mood, drama |
| 14 | B sky and land | golden wheat field rippling in the wind at sunset, wide, camera gliding sideways | 5 s | farming, food, history, calm |
| 15 | B sky and land | African-style savanna with tall dry grass at sunrise, a lone acacia tree, haze, no animals | 5 s | evolution, Africa, geography, travel |
| 16 | B sky and land | aerial slow pass over a patchwork of farmland fields in spring light | 6 s | agriculture, land use, economy, travel |
| 17 | B sky and land | desert road stretching to the horizon under dramatic clouds, locked-off view, heat haze | 5 s | travel, news mood, journeys, climate |
| 18 | B sky and land | sunrise over layered hills with fog in the valleys, wide landscape, slow drone push | 5 s | geography, mornings, motivation, travel |
| 19 | B sky and land | starry night sky with the Milky Way slowly rotating above dark mountains | 5 s | space, night, wonder, time |
| 20 | B sky and land | sunset sky with orange and purple clouds slowly changing over a calm horizon | 5 s | endings, reflection, travel, weather |
| 21 | B sky and land | snow-capped mountains at dawn with drifting clouds, wide aerial | 6 s | geography, climate, travel, achievement |
| 22 | B sky and land | rain falling on a green field, soft grey light, slow camera, droplets on grass | 5 s | weather, water cycle, farming, mood |
| 23 | C sea | calm ocean waves rolling toward a sandy beach at golden hour, wide, steady | 5 s | sea, travel, relaxation, climate |
| 24 | C sea | storm waves breaking against dark rocky coast, spray, overcast light, wide shot from a distance | 5 s | sea, storms, coastlines, drama |
| 25 | C sea | open ocean surface with long gentle swells under clouds, camera low and steady | 5 s | oceans, shipping, climate, calm |
| 26 | C sea | dark ocean waves at night under a starry sky, moonlight shimmer on the water | 5 s | night, sea stories, calm, sleep |
| 27 | C sea | sunlight rays penetrating clear shallow turquoise water over a sandy seabed, no animals | 5 s | oceans, holidays, light physics, calm |
| 28 | C sea | aerial view of waves washing along a long empty coastline, slow flyover | 6 s | coasts, travel, climate, geography |
| 29 | C sea | sea foam retreating over wet sand with reflections of the sky, close, slow | 5 s | beach, tides, meditation, travel |
| 30 | C sea | lighthouse on a rocky headland at dusk, waves below, beam sweeping softly, no text | 5 s | stories, sea, travel, history |
| 31 | C sea | calm mountain lake reflecting peaks in the early morning, mist on the water | 5 s | calm, geography, travel, mornings |
| 32 | C sea | slow river flowing through a green valley, gentle ripples, aerial follow | 6 s | rivers, water cycle, geography, calm |
| 33 | C sea | evening light glittering on calm river water, soft golden bokeh | 5 s | golden hour, cities, romance, calm |
| 34 | C sea | a waterfall in a green gorge with mist, wide, locked-off, long exposure look | 5 s | nature travel, power of water, geography, calm |
| 35 | D city | aerial dusk view of a city skyline with glowing windows, slow drift, no readable signs | 6 s | cities, housing, property, economy, travel |
| 36 | D city | sunrise over city rooftops seen from a high window, warm light, gentle haze | 5 s | mornings, housing, cities, motivation |
| 37 | D city | empty cobblestone street in a European old town at golden hour, locked-off, soft light | 5 s | Europe travel, history, restaurants, culture |
| 38 | D city | long-exposure light trails of traffic on a city road at night, blurred, no identifiable vehicles | 5 s | cities, commuting, economy, night |
| 39 | D city | aerial view of a dense city at night with lights twinkling, slow forward | 6 s | cities, energy, news mood, tech |
| 40 | D city | modern glass office towers reflecting a cloudy sky, slow upward tilt | 5 s | business, finance, economy, work |
| 41 | D city | view along a quiet residential street of apartment buildings in soft morning light, locked-off | 5 s | housing, rent, neighbourhoods, family |
| 42 | D city | city river at dusk with bridge lights reflecting in the water, slow pan, no text | 5 s | Paris/Rome-style travel, evenings, cities, romance |
| 43 | D city | empty city park with green trees and a winding path, sun through leaves, camera gliding | 5 s | parks, wellbeing, family, cities |
| 44 | D city | rooftop terraces and chimneys in a warm Mediterranean town at sunset, aerial drift | 6 s | Spain/Italy travel, history, holidays, housing |
| 45 | D city | heat haze shimmering over an empty sunlit city street in summer, locked-off | 5 s | summer, climate, cities, energy |
| 46 | D city | rain streaks on a window with blurred city lights behind, shallow focus | 5 s | moods, evenings, cities, stories |
| 47 | E lights | warm string lights glowing over a wooden market stall at night, bokeh, no readable signs | 5 s | Christmas markets, winter, festivals, food |
| 48 | E lights | rows of softly glowing paper lanterns at night, gentle sway | 5 s | festivals, Asia travel, celebration, calm |
| 49 | E lights | snowflakes falling slowly in front of warm blurred lights, night | 5 s | winter, holidays, mood, endings |
| 50 | E lights | candles flickering on a dark wooden table, close, slow | 5 s | reflection, ceremony, history, calm |
| 51 | E lights | fireworks bursting softly over a dark city skyline, distant, wide | 5 s | celebration, new year, news mood, cities |
| 52 | E lights | golden bokeh lights shimmering in the dark, abstract, slow drift | 6 s | intros, backgrounds, celebration, night |
| 53 | F food and objects | steam curling above a white cup of hot tea on a wooden table, soft window light, close | 5 s | autumn, cosy, cafes, mornings, wellbeing |
| 54 | F food and objects | steam rising from a bowl of hot soup on a rustic table, close, shallow focus | 5 s | food, winter, cooking, home |
| 55 | F food and objects | fresh coconut halves with white flesh on a wooden board, soft light, slow push-in | 5 s | food, tropics, health, products |
| 56 | F food and objects | whole fruits and vegetables arranged on a market table in soft daylight, slow slide | 5 s | food, health, farming, shopping |
| 57 | F food and objects | loaf of crusty bread on a linen cloth with warm light and a bit of steam, close | 5 s | food, bakery, home, history |
| 58 | F food and objects | coffee beans in a burlap sack, macro slow slide, warm light | 5 s | coffee, trade, farming, mornings |
| 59 | F food and objects | golden honey in a glass jar catching light, honeycomb beside it, macro, locked-off | 5 s | honey, food, health, bees topics |
| 60 | F food and objects | olive branch with ripe olives swaying in light wind, soft focus | 5 s | Mediterranean, food, farming, history |
| 61 | F food and objects | a closed leather notebook, a pen and a plant on a sunlit desk, subtle light movement | 5 s | study, work, planning, productivity |
| 62 | F food and objects | old stone wall with ivy swaying slightly in breeze, warm light | 5 s | history, ruins, gardens, culture |
| 63 | F food and objects | candle-lit antique books on a wooden shelf, dust drifting in light, slow push-in | 6 s | history, learning, libraries, stories |
| 64 | G tech and abstract | rows of server racks with softly blinking indicator lights in a dark data centre corridor, no readable labels | 5 s | cloud, AI, security, business, data |
| 65 | G tech and abstract | glowing fibre-optic strands with light pulses travelling along them, abstract macro | 5 s | internet, networks, tech, speed |
| 66 | G tech and abstract | close view of a circuit board with tiny glowing traces, slow slide, no readable text | 5 s | hardware, AI, manufacturing, tech |
| 67 | G tech and abstract | abstract flowing particles forming wave patterns in blue and teal, smooth, slow | 5 s | AI, data, intros, finance |
| 68 | G tech and abstract | abstract network of glowing nodes and lines slowly rotating on dark background | 5 s | networks, social media, AI, systems |
| 69 | G tech and abstract | slow macro of liquid-metal-like ripples, silver and blue, abstract, no objects | 5 s | backgrounds, tech, design, intros |
| 70 | G tech and abstract | soft gradient colour clouds morphing slowly, pastel, abstract, seamless motion | 5 s | backgrounds, wellbeing, finance, kids |
| 71 | G tech and abstract | planet Earth slowly rotating in space with city lights on the night side | 5 s | globalisation, climate, space, news |
| 72 | G tech and abstract | slow flight through a star field with distant nebula colours | 5 s | space, wonder, science, intros |
| 73 | G tech and abstract | microscopic view: translucent round cells drifting in a pale blue fluid, abstract, no text | 6 s | biology, health, evolution, bacteria |
| 74 | G tech and abstract | a spinning wind turbine on a green hill under a blue sky, wide, locked-off | 5 s | energy, climate, economy, farming |
| 75 | G tech and abstract | rows of solar panels glinting in morning sun, slow aerial glide | 6 s | energy, climate, business, rural |
| 76 | G tech and abstract | rotating mechanical gears with brass finish in soft light, no text, slow | 5 s | industry, how things work, history, process |
| 77 | H workplace and home | a bright empty modern office with sunlight moving across desks and chairs, locked-off | 5 s | work, offices, business, remote work |
| 78 | H workplace and home | a laptop on a tidy desk beside a plant and window, screen dark, soft light shifting | 5 s | work, productivity, study, tech |
| 79 | H workplace and home | sunlight moving across a bright apartment living room with a sofa and plants, locked-off | 5 s | housing, home, wellbeing, interiors |
| 80 | H workplace and home | sunlight entering through a window with sheer curtains moving gently, bedroom, morning | 5 s | mornings, housing, sleep, wellbeing |
| 81 | H workplace and home | an empty classroom with sunlight through tall windows and dust floating | 5 s | education, kids, schools, learning |
| 82 | H workplace and home | an empty café interior with warm light and plants, no signs, slow dolly | 5 s | cafes, business, evenings, culture |
| 83 | H workplace and home | a quiet library corridor with tall shelves and soft light, slow push-in | 5 s | study, history, learning, stories |
| 84 | H workplace and home | an empty workshop with tools hanging on a wall in warm light, subtle dust, locked-off | 5 s | craft, industry, DIY, history |
| 85 | H workplace and home | a modern kitchen with morning light on a clean counter and a fruit bowl, slow push | 5 s | home, cooking, housing, wellbeing |
| 86 | H workplace and home | an empty children's playground in soft morning light with swing moving gently in breeze | 5 s | family, parks, childhood, cities |
| 87 | H workplace and home | a tidy nursery room with soft toys and warm light, locked-off, no people | 5 s | parenting, family, childhood, home |
| 88 | H workplace and home | empty bench by a lake with morning mist, locked-off, trees swaying slightly | 5 s | calm, reflection, parks, wellbeing |
| 89 | I time and weather | snow falling gently over a quiet village rooftops at dusk, wide, locked-off | 5 s | winter, holidays, travel, calm |
| 90 | I time and weather | spring blossom branches against blue sky swaying in a light breeze, close | 5 s | spring, seasons, Japan travel, renewal |
| 91 | I time and weather | time-lapse sunrise over calm water with the sun climbing through pink clouds | 6 s | new beginnings, mornings, motivation, endings |
| 92 | I time and weather | fog drifting through a quiet valley at dawn, slow, wide | 6 s | calm, mystery, geography, mornings |
| 93 | I time and weather | raindrops creating ripples on a still pond, close, soft light | 5 s | calm, weather, water cycle, mood |
| 94 | I time and weather | lightning-free dark clouds moving fast in time-lapse over mountains | 6 s | weather, storms, news mood, time |
| 95 | I time and weather | sunset time-lapse over rooftops with changing sky colours, locked-off | 6 s | time passing, cities, endings, reflection |
| 96 | I time and weather | dust and golden light drifting in a ray inside an old stone hall, no people | 6 s | history, mystery, churches, ruins |
| 97 | I time and weather | ancient stone ruins in warm evening light with grass moving in the wind, wide, locked-off | 5 s | history, travel, Rome/Greece, archaeology |
| 98 | I time and weather | ancient olive grove at sunrise with long shadows and mist, slow glide | 6 s | history, Mediterranean, farming, travel |
| 99 | I time and weather | autumn lake with colourful trees reflected in still water, slow drift | 6 s | autumn, travel, calm, seasons |
| 100 | I time and weather | aerial view of a calm winding river through autumn forest | 6 s | autumn, rivers, geography, travel |

## 10. What the owner must do or approve

1. **Approve the pilot spend** (about $15 to $30) and create the accounts in section 6 (Runway first, Google second). Keys go in SSM `/videomk/runway_api_key`, `/videomk/gemini_api_key` or `/videomk/vertex_sa_json`, **QA account only**; set the spend caps listed there.
2. **Decide the legal position** on "our own library": we get a contractual right to use outputs, not copyright; do not market clips as exclusive. Ask a lawyer before any plan that lets customers download raw clips (Runway s1.3(a), Luma marketplace clause).
3. **Ask Google Cloud sales/support** to confirm in writing which video models are GA and covered by the generative AI indemnity (Veo 3.1 GA yes per the list quoted above; Omni Flash not confirmed).
4. **Pick the model after the blind pilot**, then approve the 100-clip run (one batch, $50 to $300 depending on the model).
5. Prod: Luma on Bedrock would also need model access and a quota request in the prod account (only if Ray2 is chosen; not recommended).

## 11. What I could not verify

- Vertex AI Veo and Omni Flash prices and GA list (pricing pages truncated or not loadable); Vertex "video-only" discount (secondary only); whether Gemini Omni Flash can drop audio and what it costs then.
- Google's Veo output ownership clause and SynthID text; the indemnity document text (only the covered-service list was seen in a search snippet).
- Kling, MiniMax, ByteDance (Seedance), Alibaba (Wan 3.0), Moonvalley, Pika, Adobe Firefly API terms and indemnity; Firefly's USD price per Operation; Moonvalley's official price.
- Whether Runway-hosted third-party models carry extra upstream terms, and Runway's API (not web) terms.
- Luma terms for API/Bedrock use (we read the consumer/web ToS); Ray2 deprecation status (secondary).
- Prod account's Bedrock video access (not touched).
- Quality: no independent test of our scene types exists; arena Elo is with audio and mixed prompts, snapshots conflict; the only first-hand evidence is 2 Luma Ray2 clips viewed as still frames.
- Self-host timings on an L40S (not measured: no GPU session was run), LTX-2.x and Hunyuan 1.5 licence texts, CogVideoX and Mochi licences.
- AWS billing for the two Ray2 calls (estimated at $7.50 from the Price List API; Cost Explorer not yet updated).
- Thresholds of the temporal QA were tuned on synthetic clips only.

## 12. Sources (all read 2026-11-26)

AWS Price List API (`AmazonBedrockFoundationModels`, provider Luma AI, us-west-2); `aws bedrock list-foundation-models` in `qa`; Runway pricing https://docs.dev.runwayml.com/guides/pricing/ and API reference https://docs.dev.runwayml.com/api/ and terms https://runway.com/terms-of-use; Luma terms https://lumalabs.ai/legal/tos and API pricing https://lumalabs.ai/api/pricing; Google pricing https://aistudio.google.com/docs/pricing, video docs https://aistudio.google.com/docs/video, Veo 3.1 Lite https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/, indemnified services https://cloud.google.com/terms/generative-ai-indemnified-services; MiniMax https://platform.minimax.io/docs/guides/pricing-video; OpenAI https://developers.openai.com/api/docs/models/sora-2; Wan 2.2 https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B and https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B; HunyuanVideo https://huggingface.co/tencent/HunyuanVideo/blob/main/LICENSE and https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5; LTX https://huggingface.co/Lightricks/LTX-Video and https://static.lightricks.com/legal/ltx-2-open-weights-license-0.X.pdf; US Copyright Office https://copyright.gov/newsnet/2025/1060.html; Artificial Analysis https://artificialanalysis.ai/video/leaderboard/text-to-video (snapshots via search); secondary: MarkTechPost 2026-11-13, howaiworks.ai, atlascloud.ai, dev.to, cut.pro, fal.ai, AIReiter, Adobe help rate card.
