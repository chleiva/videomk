# Video providers for the b-roll library: is anything better than Gemini Omni Flash 1.2? (2026-11-27)

Follow-up to `docs/VIDEO_CATALOG.md` (2026-11-26). Read-only research: no purchase, no account, no paid call.
Tags: **VERIFIED** = primary page read today (provider docs, price page, AWS docs). **SECONDARY** = reseller, blog, press, or a leaderboard read through a page summariser. **UNVERIFIED** = not confirmed; do not rely on it. Nothing was filled from memory.

## 1. The answer in six lines

1. **Nobody is clearly better than Omni Flash 1.2 on quality.** On the one leaderboard with a dated page (LMArena text-to-video, 2026-11-08) Omni 1.2 Flash is #1 (1540) and Veo 3.1 is far behind (1363). On Artificial Analysis (AA) v2.1, Omni 1.2 Flash is #6 (1152), 23 Elo below #1 Wan 3.0 (1175), with MiniMax H3 (1164) and Seedance 2.5 (1154) between them. That is a near-tie, not a ranking. No independent test of nature b-roll exists.
2. **Native 4K exists, but at a price.** The only priced API where the vendor says "native 4K" is **Kling 3.0 / O3 4K: $0.42/s direct (Kling price table), $0.43/s through Runway**. Google's 1080p and 4K are explicitly upsampled/upscaled (Omni: Google's pricing footnote; Veo 3.1: Google's Jan 2026 blog "state-of-the-art upscaling").
3. **Native 1080p:** only Luma states it ("1080p outputs are natively supported across the model", Luma API pricing page). Kling, Wan 3.0, MiniMax, Seedance publish 1080p/2K/4K options but do **not** say native or upscaled on the pages read. Must be measured in the pilot.
4. **Price:** Omni is still the cheapest top-quality option at 720p ($0.07/s). Native 4K costs about 2x Omni's upsampled 4K and 6x its 720p.
5. **Through AWS:** Bedrock has only Luma Ray2 (Nova Reel is end-of-life, 2026-09-30). But **Runway's API (which hosts Kling 3.0 4K, Seedance, Veo, Wan, MiniMax, Gemini Omni) can be bought through AWS Marketplace and billed on the AWS invoice** (Runway docs, VERIFIED; per-model Marketplace rates NOT verified).
6. **What the engine really needs:** `docs/VIDEO_CATALOG.md` s8 says the engine plays 1280x720 clips, and 1920x1080 for 4K videos. So the practical target is clean **1080p**, not 3840x2160. Native 4K is only worth paying for if we later want 4K clips.

## 2. Independent quality evidence

| Source (date) | Top of the list | Notes |
|---|---|---|
| **LMArena text-to-video** ([arena.ai](https://arena.ai/leaderboard/text-to-video), page dated 2026-11-08; SECONDARY, read through a summariser) | 1 Gemini Omni 1.2 Flash 1540; 2 Omni 1.1 Flash 1513; 3 gemini-omni-flash 1509; 4 Grok Imagine Video 1.5 1488; 5 Seedance 2.0 (720p) 1483; 6 Seedance 2.5 (720p) 1479; 7 Wan 3.0 1476; 8 SkyReels V4; 9 FLUX 3 Video; 10 Meta Muse Video; 11 MiniMax H3 1456; 14-15 Veo 3.1 1363 | Blind votes, mixed prompts, with audio. Kling not in the top 15. |
| **AA text-to-video v2.1, with audio** ([artificialanalysis.ai](https://artificialanalysis.ai/video/leaderboard/text-to-video); fetched 2026-11-27, snapshot date not stated; SECONDARY) | 1 Wan 3.0 1175; 2 Utopai X 1173 (no API); 3 MiniMax H3 768p 1164; 4 Hyperflow H3 1156 (not yet available); 5 Seedance 2.5 1154; **6 Gemini Omni Flash 1.2 1152**; 7 MAGI-2 1150; 11 Kling 4.0 1144; 14 Seedance 2.0 1135 | Veo 3.1 is not in the top 20. AA's "price per minute" column matches the vendors' own rates (Omni $6.26/min at 1080p = $0.104/s; Wan 3.0 $12/min = $0.20/s). |
| **AA silent board (what we use: we strip audio)** (same page) | HeyGen Video 1 1147, MAGI-2 1144, Hyperflow H3 1141, Utopai X 1141, Wan 3.0 1138 | Only the top 5 were shown. Omni's silent score is unknown. |
| Nature/landscape reviews | Veo and Luma named most often for landscapes (generic 2026 roundups, undated, none cover Kling 4.0, Seedance 2.5 or Wan 3.0) | SECONDARY, weak. |

Caveats: both arenas test short mixed prompts at 720p to 1080p with audio. **Nobody ranks native 4K, and nobody ranks calm nature b-roll.** The old VIDEO_CATALOG note that Omni "led AA" in August is superseded: it is now #6 on AA v2.1 and #1 on LMArena.

## 3. Candidates: resolution, length, 9:16, audio, access, terms

Prices are USD per second of output, no audio where that option exists. "Native?" is what the vendor page says, not what we measured.

| Candidate | Native resolution evidence | Clip length | 9:16 | Audio optional | API for EU/UK company | Price/s by resolution (source) |
|---|---|---|---|---|---|---|
| **Gemini Omni 1.2 Flash** (Vertex GA 2026-11-05, endpoint `global`; also Gemini API) | **Not native above 720p.** Google footnote: "$0.104/s for 1080p with upsampling", "$0.209/s for 4K with upsampling" (VERIFIED, aistudio.google.com/docs/pricing). Options 360p/720p/1080p/4K | 3-15 s (VERIFIED) | 16:9, 9:16 (Vertex doc) | Not stated; pricing says "(with audio)" for all rates. Unverified that audio-off is cheaper | Vertex: yes, global, data-residency/CMEK controls listed (VERIFIED). Gemini API: not checked for EU/UK | 360p $0.023, **720p $0.0695**, 1080p $0.104, 4K $0.209 (5,792/8,688/17,376 tokens/s x $12/M; VERIFIED on cloud.google.com pricing and AI Studio) |
| **Veo 3.1** (`veo-3.1-generate-001`, `-fast-`: GA 2025-11-17; Lite: **Preview**) | **Upscaled**: Google blog 2026-01 "Generate videos 1080p and 4K with state-of-the-art upscaling" (VERIFIED, blog.google). Fast/Lite: 720p, 1080p only (Vertex doc) | 4, 6, 8 s (VERIFIED) | 9:16, 16:9 (VERIFIED) | **Yes**: video-only SKU (VERIFIED) | Vertex, but **only `us-central1`** (VERIFIED). Gemini API preview shut down 2026-10-22 | Video-only: Standard 720p/1080p $0.20, 4K $0.40; Fast $0.08 / $0.10 / 4K $0.25 (the Fast model doc lists no 4K: conflict); Lite $0.03 / $0.05. With audio: Std $0.40 / 4K $0.60; Fast $0.10 / $0.12 / $0.30; Lite $0.05 / $0.08 (VERIFIED on cloud.google.com pricing; the page's unit is "/ 1 count", read as per second because the numbers equal the per-second rates on Runway and in the Gemini API era) |
| **Kling 3.0 / O3** (Kuaishou) | **4K: "cinema-grade native 4K video output"** (Kling's own credit guide, VERIFIED); fal says "Native 4K, no post-processing upscale" (SECONDARY). 720p/1080p: not stated. No independent pixel test found | 3-15 s (VERIFIED) | 4K: 2160x3840 (Runway API ref, VERIFIED); Pro 1080x1920 | **Yes** at 720p/1080p (cheaper without); 4K price same either way (VERIFIED) | Kling Open Platform (contract party "Kling AI Pte." per search snippet; EU/UK terms not read). Also via Runway, fal | Direct: 720p **$0.084**, 1080p **$0.112**, **4K $0.42**; with audio $0.126 / $0.168 / $0.42 (VERIFIED, kling.ai/document-api/pricing). Runway: Standard $0.09 (720p), Pro $0.12 (1080p), 4K **$0.43** (VERIFIED) |
| **Kling 4.0** (Oct 2026) | Kling page says "up to native 4K" but the same page says 1080p/4K are "coming soon": inconsistent (VERIFIED page, UNVERIFIED claim). Runway lists only 720p/1080p | 3-30 s (VERIFIED, Kling page) | 9:16 yes | Audio included, no toggle (Runway) | Same as above | Direct: 720p $0.157, 1080p $0.235, 4K $0.549 (VERIFIED, Kling price table). Runway: 720p $0.157 ($0.126 promo to 2026-11-30), 1080p $0.235 ($0.188 promo) |
| **Seedance 2.0 / 2.5** (ByteDance) | 4K offered. A BytePlus-hosted article says Seedance 2.0 renders "true 4K", AI-written page, no test (SECONDARY). 2.5: native vs upscaled **not stated** (UNVERIFIED) | 4-30 s (Runway) | 3840-class ratios incl. 2160x3840 (Runway ref) | Boolean on Runway, default on | BytePlus ModelArk; also **AWS Marketplace listing "Dreamina Seedance 2.0", sold by BytePlus** (VERIFIED, private-offer pricing); EU/UK availability not stated | Runway (VERIFIED): 2.0 $0.14/$0.30/$0.40/**$1.50** (480p/720p/1080p/4K); 2.5 $0.20/$0.30/$0.68/**$1.10**. BytePlus direct 2.5 4K about $4.568 per 5 s = $0.91/s (SECONDARY, neoteo reading BytePlus docs). Volcano Engine 4K about RMB 6.03/s (SECONDARY) |
| **Wan 3.0** (Alibaba; API only, closed) | 480p/720p/1080p, **no 4K**. Native vs upscaled not stated (VERIFIED page, gap) | up to 30 s (VERIFIED) | Not stated | Not stated on Alibaba pages | **Alibaba Model Studio has Germany (Frankfurt) and US regions** (VERIFIED). Also Runway | Singapore $0.05/$0.10/$0.20 (480p/720p/1080p). **Frankfurt, US, HK $0.0413/$0.0825/$0.165** (VERIFIED, alibabacloud.com/help/en/model-studio/wan3-0-video). Prime tier (more capacity) $0.068/$0.14/$0.28 on Runway |
| **MiniMax H3** | 768p and **2K**; 2K origin not stated, and a "768P to 2K regeneration" SKU exists, so 2K may be upscaled (UNVERIFIED) | 4-15 s (VERIFIED) | Not named on the page; Runway lists 9:16 | **Yes**: `generate_audio:false` (VERIFIED) | MiniMax API; EU/UK not checked | 768p $0.08, **2K $0.13**, Lite 768p $0.04 (VERIFIED, platform.minimax.io pricing). Runway: 768p $0.10, 2K $0.15 |
| **Luma Ray3.2** (direct Luma API) | **"1080p outputs are natively supported across the model"**; HDR/EXR native; no 4K (VERIFIED, lumalabs.ai/api/pricing) | 5 s or 10 s | 9:16 yes | Not mentioned | Luma API direct; not on Bedrock | Credits per 5 s: 360p 20, 540p 50, 720p 100, **1080p 400** (10 s = 3x). **USD per credit is not published** (VERIFIED gap). One secondary guess ($0.003/credit) gives $0.06/s at 720p and $0.24/s at 1080p: UNVERIFIED |
| **Luma Ray2 on Bedrock** | 540p (960x544 measured) and 720p | 5 s or 9 s | yes | Silent output | **Bedrock us-west-2 only; Active; billed via AWS Marketplace on the AWS bill** (VERIFIED) | 540p $0.75, 720p $1.50 (AWS Price List, VERIFIED 2026-11-26) |
| **Runway Gen-4.5** | 720p only (1280:720, 720:1280; VERIFIED) | 2-10 s | yes | no audio param | Runway API | $0.12 (VERIFIED) |
| **HappyHorse 1.1 (Alibaba)** | 720p/1080p; native not stated | 3-15 s | yes | n/a | Alibaba Model Studio | 1080p $0.18 Singapore, about $0.165 other regions (SECONDARY: search snippet of the Alibaba page, not opened) |
| **Grok Imagine Video 1.5** (xAI) | 480p/720p/1080p on Runway; xAI's own page lists only $0.08/s and "us-east-1, us-west-2", conflicts with other pages | n/a | n/a | n/a | xAI listing on AWS Marketplace exists; rates not read | Runway: $0.10 / $0.16 / $0.29 (1080p) (VERIFIED). LMArena #4 |
| **Moonvalley Marey** | 1080p, 5 s (SECONDARY) | 5 s | ? | no | direct/enterprise | No official price; reseller $3.90/s (SECONDARY). Clean-data marketing; indemnity UNVERIFIED |
| **Adobe Firefly Video** | up to 1080p (2025 sources only) | 5 s | ? | no | Firefly Services contract | No USD price per Operation found; 2026 pages not found. UNVERIFIED |
| **Amazon Nova Reel** | n/a | n/a | n/a | n/a | **End of life 2026-09-30** ("Requests to this model fail", Bedrock model card, VERIFIED) | n/a |

## 4. Ownership, commercial use, indemnity (only what was read)

| Provider | Commercial use / ownership | IP indemnity |
|---|---|---|
| Google Cloud (Vertex) | Standard Cloud terms (not re-read). | **Yes for Veo GA**: "Agent Platform API (formerly Vertex AI API) used with generally available versions of these foundation models: Codey, Gemini, Imagen, PaLM, Veo" (VERIFIED, page last modified 2026-07-20). **Omni 1.2 Flash is GA on Vertex but not named**; "Gemini" is listed, so coverage is plausible but UNVERIFIED: ask Google in writing. Veo 3.1 Lite is Preview, so not covered. |
| Runway | "does not claim ownership of any of your Inputs or Outputs"; "does not restrict your commercial use of your Outputs"; may train on Inputs/Outputs; no standalone API terms on the page; US-based service, New York law, JAMS arbitration (VERIFIED, runway.com/terms-of-use). Third-party (Kling, Veo, Seedance) upstream terms: UNVERIFIED | **None** (we indemnify Runway, s9) |
| Kling | Paid users may use outputs commercially; user keeps IP (SECONDARY readings of kling.ai/docs/user-policy, which would not load); broad licence back to Kling | None found |
| Alibaba, MiniMax, ByteDance/BytePlus, Luma API, Moonvalley, Adobe | Not read this session (Luma web ToS was read yesterday: owner of Output during an active subscription, we indemnify Luma) | Not found or UNVERIFIED |

US copyright caveat from VIDEO_CATALOG s1 stands: no model gives us copyright in pure AI output; we get a contractual right to use it.

## 5. Reaching video models through AWS

- **Bedrock (VERIFIED, Bedrock "Models at a glance" + model cards, 2026-11-27):** the only video-generation models are **Luma Ray2** (us-west-2, Active, third-party, billed through AWS Marketplace) and Nova Reel (EOL). TwelveLabs models are video understanding, not generation. No Veo, Kling, Seedance, Ray3 or Wan on Bedrock.
- **AWS Marketplace billing (VERIFIED):** **Runway Dev** ("sold by Runway, deployed on AWS"): subscribing links a Runway API project to our AWS account; usage is reported to AWS and appears on the AWS bill; existing credits are spent first; public listing needs Runway approval before AWS billing starts; no extra credit purchase or auto-billing while subscribed. Not stated: which models are included and whether Marketplace rates equal $0.01/credit (UNVERIFIED). **BytePlus "Dreamina Seedance 2.0"** is also listed (private-offer pricing, 480p-4K). An **xAI Grok Imagine** listing exists (rates not read).
- **Google on our AWS bill: no.** Vertex needs a Google Cloud account.
- So "billing and terms stay in AWS" is achievable only for **Luma Ray2 (Bedrock)** and **Runway (and its hosted models) via Marketplace**. Terms are still the vendor's (Runway's, for hosted models); AWS only moves the invoice.

## 6. Cost of 100 clips x 10 s = 1,000 s, before rejects

Multiply by 1.67 for a 40% reject rate (167 generations). 720p column is 768p for H3. "Native?" is the vendor claim from section 3.

| Candidate | 720p | 1080p | Highest res (native?) |
|---|---|---|---|
| Gemini Omni 1.2 Flash | **$70** | $104 (upsampled) | 4K $209 (upsampled) |
| Veo 3.1 Fast, video-only (Vertex) | $80 | $100 (but max 8 s: 100 x 8 s = $80) | 4K $250 (doc conflict; upscaled) |
| Veo 3.1 Standard, video-only | $200 | $200 | 4K $400 (upscaled) |
| Veo 3.1 Lite video-only (Preview, no indemnity) | $30 | $50 | none |
| **Kling 3.0 direct, no audio** | $84 | **$112** | **4K $420 (native per Kling)**; via Runway $90 / $120 / **$430** |
| Kling 4.0 direct | $157 | $235 | 4K $549 (claim unverified) |
| Seedance 2.0 via Runway | $300 | $400 | 4K $1,500 (native unconfirmed) |
| Seedance 2.5 via Runway | $300 | $680 | 4K $1,100 (native unconfirmed) |
| **Wan 3.0 Alibaba Frankfurt** | $83 | **$165** | 1080p (native unconfirmed). Singapore/Runway: $100 / $200 |
| MiniMax H3 direct | $80 | none (2K $130) | 2K $130 (native unconfirmed) |
| Luma Ray3.2 | $60 (UNVERIFIED rate) | $240 (UNVERIFIED rate; 1080p native per Luma) | 1080p |
| Runway Gen-4.5 | $120 | none | 720p |
| Luma Ray2 Bedrock | $1,500 | none | 540p $750 |
| HappyHorse 1.1 (Alibaba SG) | n/a | $180 (SECONDARY) | 1080p |

With 40% rejects, the headline numbers become: Omni 1080p $174, Kling 3.0 1080p $187, Kling 3.0 4K $701, Wan 3.0 Frankfurt 1080p $276.

## 7. Ranking

1. **Best quality: Gemini Omni 1.2 Flash** (LMArena #1, AA #6, 3-15 s, 9:16, GA on Vertex). Not distinguishable from Wan 3.0, MiniMax H3 and Seedance 2.5 on AA. Its weakness is exactly the owner's concern: nothing above 720p is native.
2. **Best native resolution per dollar: Kling 3.0** (direct or via Runway): the only priced native-4K API ($0.42/s), and 1080p at $0.112/s no-audio. Quality rank is lower in the arenas than Omni (Kling is not in LMArena's top 15), so it may win on sharpness and lose on realism. Runner-up for native 1080p: Wan 3.0 from Frankfurt ($0.165/s, EU region, AA #1) and Luma Ray3.2 (native 1080p stated, price unknown).
3. **Best overall for 100 x 8-10 s clips: Omni 1.2 Flash for the 720p/1080p library ($70 to $104 per 1,000 s), with Kling 3.0 as the 4K/sharp-detail fallback and Wan 3.0 (Frankfurt) as the EU-region alternative.** If a named IP indemnity is the deciding factor: Veo 3.1 Fast video-only GA on Vertex ($0.10/s at 1080p, upscaled, us-central1 only, 8 s max), which scores far lower in the arenas.
4. Only if billing must sit on AWS: Runway via AWS Marketplace (Kling 3.0 4K and Gemini Omni both hosted), at the price of Runway's no-indemnity terms and unverified Marketplace rates.

## 8. Risks

- "Native" is a vendor claim for Kling 4K only. No independent pixel-level test was found (one blog says 38 of 40 clips checked in DaVinci Resolve: SECONDARY). Kling 3.0 renders 8-bit SDR (SECONDARY).
- Omni and Veo are Google products priced per second as "upsampled"; a 4K Omni master is not 4K detail.
- Seedance 2.5 4K was reported opened on 2026-11-16/17 (SECONDARY); BytePlus ModelArk availability and EU/US access are inconsistent across sources.
- Kling 4.0: page contradicts itself on 4K and on API availability; Runway promo price ends 2026-11-30.
- Leaderboards are with-audio, mixed prompts; the silent board is the relevant one and only its top 5 were visible.
- Veo 3.1 GA is `us-central1` only: a data-residency issue for an EU/UK company if prompts or outputs are personal data (they are not for b-roll, but check the DPA). Omni 1.2 Flash uses a `global` endpoint.
- Prices move monthly (Kling 4.0 promo, Runway credits). Re-read the pages on the buy day.
- Not read: Kling, Alibaba, MiniMax, BytePlus terms; Runway's hosted-model upstream terms; EU/UK sign-up restrictions for each vendor.

## 9. Blind pilot (about $55)

Same 10 prompts from VIDEO_CATALOG s9 (1, 11, 23, 24, 35, 37, 47, 53, 64, 77), 6 s, 16:9, audio off where possible, three seeds only on any failures:

| Run | Cost for 10 x 6 s |
|---|---|
| Omni 1.2 Flash 1080p | $6.3 |
| Omni 1.2 Flash 4K, 3 prompts | $3.8 |
| Kling 3.0 Pro 1080p, no audio | $6.7 |
| Kling 3.0 4K, 3 prompts | $7.6 |
| Wan 3.0 1080p (Frankfurt region) | $9.9 |
| MiniMax H3 2K | $7.8 |
| Seedance 2.0 1080p, 5 prompts | $12.0 |
| Veo 3.1 Fast video-only 1080p (indemnity control) | $6.0 |

Tests:
1. **Blind rating** of the contact sheets by two people, then the existing `video_catalog_qa.py` score.
2. **Effective-resolution test**: for every clip measure the radially averaged spatial-frequency spectrum (ffmpeg frames + numpy). A 1080p or 4K file whose energy cuts off at about 720p-equivalent is upsampled. This settles "native" without trusting any vendor.
3. **Crop test**: 9:16 centre crop of each 16:9 master, since the library crops rather than generating 9:16.
4. **Artefact rate** per model on the 10 prompts (target under 40%), and motion smoothness at 8-10 s (artefacts grow with length).
5. **Does audio-off change quality or price** (Omni: confirm whether it can be disabled at all).
6. **Ask Google in writing** whether Omni 1.2 Flash on Vertex is under the generative AI indemnity, and ask Runway what the AWS Marketplace rates are per model.

## 10. Sources read 2026-11-27

Google: cloud.google.com/vertex-ai/generative-ai/pricing (fetched with curl, text extracted); docs.cloud.google.com Veo 3.1 model page, Gemini Omni 1.2 Flash model page, "generate videos from text" page; aistudio.google.com/docs/pricing and /docs/video; cloud.google.com/terms/generative-ai-indemnified-services; blog.google Veo 3.1 Ingredients to Video. Kling: kling.ai/document-api/pricing/base/video.md; kling.ai/blog/kling-video-3-0-credit-cost-guide; kling.ai/ja/feature/kling-4-ai-video-generation. Runway: docs.dev.runwayml.com/guides/pricing, /api, /usage/aws-marketplace; runway.com/terms-of-use. MiniMax: platform.minimax.io pricing-video and video-generation. Alibaba: alibabacloud.com/help/en/model-studio/wan3-0-video, wan3-0-video-prime, blog 603452. Luma: lumalabs.ai/api/pricing, lumalabs.ai/pricing. AWS: Bedrock model-cards, Nova Reel and Ray2 cards, model-parameters-luma; Marketplace BytePlus Seedance 2.0 listing. Leaderboards: artificialanalysis.ai/video/leaderboard/text-to-video; arena.ai/leaderboard/text-to-video. Secondary: fal.ai Kling 4K page, technode (2026-11-17), neoteo, byteplus.com/en/topic/578667, cut.pro Marey, review roundups.
