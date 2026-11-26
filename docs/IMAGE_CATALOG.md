# videomk image catalog

videomk's own library of generated images: made once, reused across many videos, stored privately, searched by the director before it goes to stock photos. Nothing here is switched on by default.
This document is in the order of the work: 1 research, 2 demand, 3 design and the director, 4 feedback loop, 5 generation, 6 promotion, 7 the pilot, 8 tests and decisions.

Reading guide: **measured** = a number computed from QA data or a real call in this build; **cited** = from a provider page (the URL is given); **estimated** = my arithmetic or opinion;
**not verified** = I could not read the primary source. Prices and terms change: re-read the cited pages before an owner decision that depends on them.

## 0. Decision (2026-11-26): generation is OpenAI gpt-image-2.6-flare

The owner chose OpenAI's best image model and no legacy Bedrock model. `catalog_generate.py` now calls **`gpt-image-2.6-flare`** (OpenAI Images API, `POST /v1/images/generations`), 2048x1152 (16:9), `quality: high`, JPEG. The Stability/Bedrock paths (Control Structure, Style Guide, Fast Upscale, composition guides, `--anchor`, seeds) are **removed from the generator**; sections 1.1 and 7 below are history of the earlier Bedrock pilot.
* **Model choice (measured):** the QA key lists `gpt-image-2.6-flare`, `gpt-image-2.6-sunburst`, `gpt-image-2.5-flare/sunburst`, `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1-mini`, `chatgpt-image-latest`. 2.6 is the newest; OpenAI's guide says Sunburst is for editing precision and Flare for fast, high-quality everyday generation, which is our use. Both have the same price. GA/preview status is not stated on the pages I could read (**not verified**).
* **Price (cited):** https://developers.openai.com/api/docs/pricing: image output USD 30 per 1M tokens, text input USD 5 per 1M (batch half). The pages publish no per-image table for 2.6, so the price is **measured** from the response `usage`: 2048x1152 high = 1413 output tokens = **USD 0.0424** (plus about USD 0.0001 of prompt); medium 1212 tokens = USD 0.0364; 1792x1008 medium 1056 tokens = USD 0.0317. Pilot calls cost USD 0.0437 each at high.
* **Quality choice:** high, because it costs only USD 0.006 more than medium and the fine detail (rock, foliage, mist) is visibly better in the side-by-side probe. Re-measure if the size changes.
* **Cap:** `Spend.reserve` is called before every paid call with USD 0.055 (generation) + 0.01 (check) + 0.0005 (embedding); the REAL cost from `usage` is charged afterwards and logged. No seed exists in the API: items are idempotent through the marker row, and `--regen` simply generates again (a different picture).
* **Composition:** free text-to-image; no guide images. The house prompt (bottom quarter calm, centred subject) plus the negative list (appended as "Avoid: ...") are sent; the vision check, Cohere embedding, duplicate check and demand rules are unchanged.
* **Key:** SSM SecureString `/videomk/openai_api_key` in the profile's account (or `OPENAI_API_KEY` in the environment); never logged. The request goes to OpenAI directly (plain HTTPS), so generation prompts leave AWS: they are generic catalog subjects, never user content.
* **Pilot 2026-11-26:** `docs/image_catalog/pilot_openai_plan.json` (8 people-free items, 10 generations): 6 kept, 4 rejected by the strict check on the first pass (2 re-run, both kept), total about USD 0.45 including checks; about USD 0.07 per kept image at this hit rate. People/objects (coffee cup, honeycomb, desk) that the Bedrock method could not produce now work. Sunburst was not compared.

## 1. Research: which model, which licence

### 1.1 What the QA account can call on Amazon Bedrock today (measured, 2026-11-26)

`aws bedrock list-foundation-models --by-output-modality IMAGE`, then a real `InvokeModel` for each model that looked usable (profile `qa`, account 552357225438):

| Model (Bedrock id) | Region | Status | Result of a real call |
|---|---|---|---|
| Amazon Nova Canvas, Titan Image Generator v2 | us-east-1 | end of life | `ResourceNotFoundException: This model version has reached the end of its life` |
| Stability Stable Image Ultra 1.0, Core 1.0, SD3.5 Large | us-west-2 only | LEGACY | `Access denied. This Model is marked by provider as Legacy and you have not been actively using the model in the last 30 days` |
| Stability Stable Image **Control Structure**, **Control Sketch**, **Style Guide**, **Fast Upscale**, Inpaint, Search and Replace, Outpaint, ... | us-west-2, us-east-1, us-east-2 (inference profile `us.stability...`) | ACTIVE | **works** (Control Structure, Style Guide and Fast Upscale were called) |
| eu-west-1 (QA's own region) and every other region I listed | | | no image model at all |

So: **no Bedrock text-to-image model is callable from QA.** The only active generators are Stability's image-service models, which take a guide or reference image plus a prompt. That is usable:
a *Control Structure* call takes a prompt and a simple drawing and keeps the drawing's composition, which is exactly what we need to force "subject in the middle third, calm bottom quarter".
The drawings are made by `backend/scripts/catalog_layouts.py` from nothing (no third-party image is ever an input). *Style Guide* takes a prompt and a style reference picture and gives free composition in the same look.
The Stability models run in us-west-2 (Oregon) from QA's eu-west-1 account via the `us.` inference profile; the pictures are our own output, not user data, so the region hop has no privacy cost.

Prices (cited): https://aws.amazon.com/bedrock/pricing/ lists, for the Stability image-service models, Control Structure USD 0.07, Style Guide USD 0.07, Fast Upscale USD 0.03 per image. Those are the prices the generator uses and the spend log records;
a QA bill check at the end of the month is the real confirmation (**not verified** against an invoice). The AWS page does not list Stable Image Ultra/Core/SD3.5 Large any more (third-party blogs from 2024 said USD 0.14 / 0.04 / 0.08; not verified, and they are not callable anyway).

### 1.2 External options

Collected from each provider's own pages on 2026-11-26 (a research sub-task, summarised by a small reader model: the sentences below are as relayed; the URL is where to re-read them).
"Library use" means: may we put outputs into a catalog that many customers' videos then use?

| Provider and model | Price per image (cited) | Max size | API | Quality evidence |
|---|---|---|---|---|
| Google **Nano Banana 2.1** (Gemini image) | about USD 0.034 at 1K, 0.050 at 2K, 0.113 at 4K | 4K | Gemini API | Artificial Analysis arena Elo 1175 (v2.1 snapshot) |
| Google Nano Banana 2 / Pro | 0.067 (1K) / 0.134 (1K-2K) | 4K | yes | Elo 1145 / 1117 |
| OpenAI **GPT-Image-2** (high / medium / low) | 0.211 / 0.053 / 0.006 (1024x1024); 0.165 / 0.041 / 0.005 (1024x1536) | | OpenAI API | Elo 1196 (high). Medium is not on the board |
| OpenAI GPT-Image-2.5 / 2.6 | per token only (image output USD 30 per million tokens) | | yes | Elo 1264 at "max", about USD 0.21 |
| Black Forest Labs FLUX.2 pro | 0.03 first megapixel, 0.015 each further one | per MP | api.bfl.ai | Elo about 1003 |
| Ideogram 4.x | 0.03 / 0.06 / 0.10 | 2K | yes | Elo 1004-1026; strongest at text rendering, which we do not need |
| Recraft V4.1 | 0.035 (utility); 0.21 (pro) | | yes | Elo 1026 |
| Adobe Firefly Services | contract (0.5 "operations" per image; dollar price **not verified**, a third party says USD 0.02-0.10 with a large minimum) | | enterprise contract | no benchmark found |
| Midjourney | | | **no API** | not usable from a pipeline |
| Imagen 4, Nova Canvas, GPT-Image-1 | | | **retired** (Imagen 4 on the Gemini API 2026-08, Nova Canvas 2026-09, GPT-Image-1 2026-10; from provider notices relayed by search, not from a deprecation page) | |

Sources: https://aistudio.google.com/docs/pricing, https://developers.openai.com/api/docs/guides/image-generation, https://developers.openai.com/api/docs/pricing, https://bfl.ai/pricing, http://ideogram.ai/pricing/?pricing_tab=api,
https://www.recraft.ai/docs/api-reference/pricing, https://artificialanalysis.ai/image/leaderboard/text-to-image (arena Elo is general-prompt preference voting, **not** a stock-photo realism test; I found no independent stock-photo benchmark).
FLUX.1 **dev** weights are licensed non-commercial; this is why the API models (FLUX.2 pro) are the only FLUX option for us. Stability's open-weights licence (https://stability.ai/license): free commercial use below USD 1M annual revenue, an enterprise licence above it;
that licence covers the self-hosted weights. The Bedrock-hosted models are used under AWS's terms plus Stability's.

### 1.3 Ownership and licence, from the provider's own words

Quoted as relayed by the reader (fragments are marked with an ellipsis). **None of this is legal advice; the owner should have counsel read the actual agreements before the bulk.**

* **Amazon Bedrock** (https://aws.amazon.com/service-terms/): section 50.2 "The output that you generate using AI Services is Your Content." Section 50.5 "you may not use an AI Service to generate Content for the express purpose of training an AI model or service."
  Section 50.12.1 treats third-party models on Bedrock as "Third-Party Content", so the model provider's own terms also apply. Section 50.12.6 forbids altering provenance data ("modify, tamper with, remove, obscure, or otherwise alter such Provenance Data").
  Indemnity (section 50.10): "AWS will defend you and your employees, officers, and directors against any third-party claim", limited to the listed "Indemnified Generative AI Services": that list names Amazon Titan Image Generator and **no Stability model**
  (so the Stability models we can call are, as far as I could read, **not indemnified by AWS**; **not verified** beyond one reading). Nothing in these terms forbids putting outputs in a library.
* **Stability AI** (https://stability.ai/license, https://stability.ai/terms-of-service): licence "as between you and Stability, you own outputs generated from the Core Models or Derivative Works"; terms of service section 4(a) "we assign to you all of our right, title, and interest (if any) in the Outputs";
  section 8(b) "you may not use any Outputs to train a model that competes with Stability AI or that third party"; section 3(b)(3) forbids reselling "the Services, Software, or API, or access to" them (access, not outputs). Section 11: you indemnify them; they do not indemnify you.
  A stock library is not mentioned or forbidden. It **is** a restriction if we ever train a model on the catalog.
* **Google Gemini API** (https://aistudio.google.com/docs/terms): "Google won't claim ownership over that content." "You may not use the Services to develop models that compete with the Services". The Prohibited Use Policy applies.
  No indemnity in the API terms I read; Google Cloud (Vertex) has a separate "Generative AI Indemnified Services" list (https://cloud.google.com/terms/generative-ai-indemnified-services) whose coverage of the Nano Banana models I could **not verify**.
  Gemini images probably carry an invisible SynthID watermark (stated for Imagen 4; **not verified** for Gemini image models).
* **OpenAI** (https://openai.com/policies/business-terms/, https://openai.com/policies/service-terms/): "OpenAI hereby assigns to Customer all OpenAI's right, title, and interest, if any, in and to Output." "Output may not be unique, and other users may receive similar content."
  No use of Output to "develop artificial intelligence models that compete with OpenAI's products and services". Indemnification covers third-party claims about Output with exclusions (you knew or should have known it infringed, you disabled safety features, you modified or combined it, trademark claims),
  and the Business Terms say it is not subject to a liability cap. Likeness: no reproducing "a person's likeness without consent". The best contractual position of the group (assignment plus indemnity).
* **Black Forest Labs** (https://bfl.ai/legal/terms-of-service): "We claim no ownership rights in and to Your Content." BFL gets a licence to use inputs and outputs to develop its services (opt-out by email). Section 1.3(n) bars you to "use Output to train, distill or fine-tune any other AI models". Selling information from the Services is barred "except for Outputs". No indemnity.
* **Ideogram** (https://ideogram.ai/legal/tos): "we hereby assign to you all right, title and interest in and to such User Output" and "we do not restrict your ability to use User Output for your own purposes (including for commercial purposes)"; Ideogram "expressly disclaim[s] any liability arising from your use of any User Output for a commercial purpose"; a clause against exploiting "the Services for any commercial purpose" is ambiguous for an API pipeline. Free-tier images are public. No indemnity.
* **Recraft** (https://www.recraft.ai/terms): paid users own their assets, free-tier assets are Recraft's; "Assets may not be used to train artificial intelligence models"; a clause against using the Services or Assets "to develop goods or services that compete with Recraft" could be argued against a stock library. **Risk: ask in writing.**
* **Adobe Firefly**: enterprise IP indemnity "will require a new contracting event" (https://business.adobe.com/products/firefly-business/firefly-ai-approach.html); the contract and price are **not verified** (the rate card returned 403).
* **Midjourney**: no API; terms page unreadable (403); not a candidate.

Content policy in one line: every provider forbids sexual content involving minors, non-consensual intimate imagery, graphic violence and real-person deepfakes; OpenAI and others also restrict likeness. Our house rule (no recognisable people, no logos, no text) is stricter than all of them.

### 1.4 Is a generated image ours? What "we own it" can honestly mean

* **United States.** The Copyright Office's report on copyrightability (Part 2, 29 January 2025) concludes (as relayed by law-firm summaries, I could not read the PDF) that "given current generally available technology, prompts alone do not provide sufficient human control to make users of an AI system the authors of the output."
  Human selection, arrangement and creative modification can be protected; a purely generated picture, probably not.
* **United Kingdom.** The Copyright, Designs and Patents Act section 9(3) nominally protects "computer-generated works" for 50 years, but the government reported in March 2026 that it "may repeal it"; do not rely on it.
* **EU** (my own summary, **not fetched**): protection needs the author's own intellectual creation, so purely machine-made output generally has none. China has granted protection where human input was substantial; Japan, Canada and Australia follow the human-authorship principle (also from memory, **not verified**).

So the honest meaning of "these images are our company's property" is **not** "nobody else may copy them". It is:

1. **Contract.** The provider has assigned us whatever rights exist in the output (Stability ToS 4(a), AWS 50.2, OpenAI 4.1, Google "won't claim ownership"). We hold that assignment and nobody else has a claim through the provider.
2. **Provenance.** Every catalog row records prompt, negative prompt, model, version, seed, date, cost, plan and review (section 3). If anyone challenges an image we can show exactly how and when it was made, and that no third-party image was an input.
3. **Selection and arrangement.** The curated, reviewed collection, its metadata and its house style are our own work (a compilation can be protected even when single images are not).
4. **Controlled distribution.** The files are private; customers never receive the files, only rendered videos. The terms can say what customers may do with the finished video, and that the library, its metadata and its selection are videomk's property and may not be extracted or scraped.
5. **A moat of cost and consistency**, not of copyright: copying 100 images is easy, producing a consistent, reviewed, searchable, always-growing library tied to what directors actually ask for is not.

What to tell customers (for the legal builder; facts only): the images in the videomk library were generated for videomk with AI tools, under the tool providers' terms that assign their rights in the output to videomk; videomk owns the library, its metadata and its selection and licenses use of the images
inside the videos you make with videomk; as with any AI-generated image, copyright protection for a single generated picture may be limited by law, and videomk does not promise exclusivity; the images contain no people's likenesses, no logos and no text; the library is not for download or resale as images.

### 1.5 Recommendation

**Primary (what we can use today, measured): Stability Stable Image Control Structure on Amazon Bedrock, with our own composition guides, followed by Fast Upscale.** USD 0.07 + 0.03 = USD 0.10 per kept image before rejections (cited prices), photoreal (see the pilot: section 7), composition-controlled, no external account,
output assigned to us by Stability's terms and AWS's. Weaknesses to carry: no AWS indemnity for Stability models (not verified); the best use is landscapes, skies, objects and macro: scenes with people need free composition and are weaker; the guide-based method is a workaround for the retirement of text-to-image on Bedrock.
**Fallback (also Bedrock, measured):** Stability Style Guide (USD 0.07 + 0.03 upscale): free composition anchored on an approved image of our own, so the look stays one house style. I generated three comparison images (section 7).

**What I recommend the owner creates for the bulk** (not done: I may not sign up or enter keys): an account with **Google AI Studio / Google Cloud for Nano Banana 2.1** (about USD 0.034 per 1K image, 4K available, best Elo per dollar; key stored in SSM as `/videomk/google_ai_key`; ask Google Cloud about indemnity coverage for it),
or **OpenAI GPT-Image-2 at medium quality** (USD 0.053, the strongest contract: assignment plus uncapped indemnity; key `/videomk/openai_api_key`). Both would give free composition and people-free-by-prompt scenes at a quality the Bedrock workaround does not match; adding either to `catalog_generate.py` is one function (`generate_image`) and one price entry.
Until then the bulk can go ahead on the Bedrock path (about USD 40 for 100 kept images at the pilot's hit rate; see section 7).

## 2. Demand: what the director actually searches for

Everything in this section was **measured** from QA by `backend/scripts/catalog_demand.py` (read-only: list and get on the assets bucket with the `qa` profile). Data and report are in `docs/image_catalog/` (`demand_queries.json`, `demand_report.json`, `candidates.json`).

* Source: the latest plan of each of the 152 videos in `generation/v2/*/plan_r*.json` (156 files). Image beats (`image_query`), gallery beats (`image_queries`) and annotated images; the user's own photos (`photo`/`photos`) are excluded.
  Narration, titles and user text are never read into the data file. Phrases that look personal were dropped by the same filter the demand table uses (46 dropped: 31 "address" words such as street/apartment, 5 first person, 5 first names, 4 family words, 1 digits).
* Result: **442 generic image searches, 393 distinct phrases, from 72 videos** (the other 80 videos used no stock image search: clips, charts, user photos). One video alone asked 47 phrases.
* **Honest limits of this data:** QA is a test environment. Many plans are repeats of the same topics (Paris and Rome landmarks, human evolution fossils, bees, Greenwich), written by the builders. The numbers show the *shape* of demand, not a customer population.
  They are enough to say what kind of image is reusable; they are not enough to rank 100 images with confidence. The feedback loop (section 4) replaces this analysis with production demand.

### 2.1 What the demand looks like

Clustering the 393 phrases by Cohere meaning (greedy, cosine >= 0.62) gives 268 clusters; only **18 are asked by three or more different videos**. The biggest, by distinct videos:

| Videos | Searches | Cluster (example) | Catalog material? |
|---|---|---|---|
| 13 | 14 | eiffel tower paris daytime / champ de mars | **No**: a specific landmark. A generated Eiffel Tower can be wrong in detail; stock photos are the right source |
| 7 / 7 / 6 / 6 | 12 / 7 / 8 / 8 | colosseum, louvre pyramid, pantheon, trevi fountain | No: specific landmarks |
| 5 | 5 | roman forum ruins columns | partly: "ancient ruins with columns" (c101) |
| 3 | 5 | honeycomb cells with honey (5 wordings) | **Yes** (c064) |
| 3 | 3 | rainbow over green field after rain | **Yes** |
| 3 | 4 | oil tanker / container ship at sea | **Yes** |
| 2-3 | 3-6 | calm alpine lake at dawn, misty mountain lake, forest path in autumn, sunrise over calm sea, desert dunes, starry sky over sea, blue whale, emperor penguins, coral reef | Yes for the scenery; species and fossils are niche |

**Finding 1:** the single biggest block of demand (about a third of searches) is specific landmarks, museums, fossils and species. That is *not* catalog material (a generated image of a named thing is risky and a stock photo of the real thing is better).
**Finding 2:** the reusable block is scenery and mood (sunrise over mountains, mist over a lake, forest path, desert dunes, rainbow, starry sea, coast at sunset), plus a thin layer of everyday work and people scenes (typing on a laptop, handshake, tired worker at a desk).
**Finding 3:** the director writes many wordings for the same scene (five phrasings of "honeycomb", eight of "Eiffel Tower"), so one image answers many phrases and the embedding search is the right tool, not exact matching.

### 2.2 The proposed 100 and what they would cover

`candidates.json` holds 100 proposed images, ranked by measured demand. Each has a title, category, the description that is also the generation subject, whether people appear (hands and silhouettes only), and the measured count of videos, phrases and searches whose phrase scores >= 0.40 against its description.
A house-style prompt is added by `common/catalog_style.full_prompt` (below). **18 of the 100 are backed by three or more distinct videos in QA; the rest are common stock staples I expect to be reusable but QA cannot prove.** The list is a proposal for the owner, not a plan to execute.

Top of the ranking (videos / phrases that fall within 0.40 of the description): ruins with columns 5/2, sunrise over a mountain landscape 4/7, forest path in sunlight 4/5, pine forest in morning fog 4/5, container ship at sea 4/3, calm alpine lake at dawn 3/6, misty mountain valley 3/5, autumn forest colours 3/5, honeycomb 3/5, eagle in flight 3/4, rainbow over green fields 3/4, rocky coastline at sunset 3/3, snow capped peaks 3/3, rice terraces 3/3, erupting volcano at night 3/3, starry night over a calm sea 3/3, water droplet macro 3/3, medieval castle 3/3.

**House style (one place: `common/catalog_style.py`, version `house-v1`)**: editorial documentary photograph, natural light, 35 mm full-frame look, gentle film-like grade with slightly muted warm natural colours, calm optimistic mood.
**Composition for 16:9 that survives 9:16 and 1:1:** the subject sits in the middle third of the frame; nothing important touches the left or right edge (the 9:16 crop keeps the central 31.6 percent of the width, the 1:1 crop the central 56.3 percent: `catalog_style.CROPS`/`crop_box`);
the bottom quarter is calm, low-detail and a little darker for white captions. **People:** only small, from behind, silhouettes or hands, never a face. **Negative prompt:** text, letters, numbers, logos, brands, watermark, signs with writing, readable screens, recognisable person, face close-up, deformed hands, warped objects, cartoon, 3D render, oversaturation, borders.

### 2.3 Coverage estimate

Two measurements, both on the 442 real searches:

* **Description match (measured, text against text):** the best of the 100 descriptions per phrase. At similarity >= 0.30 it satisfies 47.1 percent of searches, >= 0.35: 37.1, **>= 0.40: 28.1**, >= 0.45: 21.9, >= 0.50: 15.6, >= 0.55: 11.5. The median best score is 0.29. This is an upper estimate of what a text index would do; the real index is of image vectors.
* **Real image vectors (measured on the pilot images only, section 7):** the scores the engine will actually see (text query against the image's Cohere image vector).

Reading: with a threshold around the point where a human would still call the match right, the top 100 would answer **roughly 20 to 30 percent of QA's image searches**; the rest are landmarks, species and topics that stay with stock. That is the honest ceiling on this data, and it is exactly why the feedback loop exists:
the catalog grows by demand, not by guess, and each addition must serve three or more different prompts.

## 3. Design: storage, metadata, vectors, search, the director

Code: `backend/lambdas/common/catalog.py` (runtime), `catalog_style.py`, `catalog_privacy.py`, `catalog_store.py` (offline tools), `backend/lambdas/engine/catalog_pick.py` (the director), `backend/catalog.py` (CDK).

**Per stage (qa, prod), with `-c imageCatalog=1` only:**

| Resource | Name | Notes |
|---|---|---|
| Private bucket | `videomk-<stage>-catalog-<account>` | block all public access, S3-managed encryption, SSL only, versioned, **retained** on stack deletion (the images cost money) |
| Objects | `o/<sha256>.jpg` original (up to 3840 px), `p/<sha256>.jpg` preview 1280 px, `t/<sha256>.jpg` thumbnail 384 px | immutable: the key IS the SHA-256 of the original; an upload is "put if absent" and is verified by hash |
| Metadata table | `videomk-<stage>-catalog-items`, key `id` (= sha256), PITR | `title, category, tags (house style version), serves, prompt, negative_prompt, subject, model, method, layout, seed, created, cost_usd, licence, provenance{provider, plan, plan_item}, review_status, review{verdict}, width, height, style_version, promoted_from, promoted_at, sha256`; plan bookkeeping rows `plan#<plan>#<item>` for idempotency |
| Vector index | `catalog-images` in vector bucket `videomk-<stage>-catalog-vec-<account>`, 1024 d, cosine, float32 | Cohere Embed v4 through Bedrock (never Titan): images are `search_document` (embedded from the 384 px thumbnail, as the media library does), text queries are `search_query`; key = id; metadata `title`, `category` |
| Demand table | CDK-named, key `phrase` + `video`, TTL attribute `expires` | section 4 |

**Search:** `catalog.search(query, aspect, k)` embeds the query (`search_query`), queries the index, and returns `[{id, score, title, category, crop_aspect, aspect_ok}]` best first, `score` = 1 - cosine distance. It never raises: any failure returns an empty list so the director goes to stock.

**The director (`beat_handler.make_photo`)**, only when the CATALOG_* environment exists (the flag): before the stock search, `catalog_pick.try_catalog` takes the top 3 matches and for each, in order:
1. the score must reach `CATALOG_MIN_SCORE` (default in code 0.35; the deploy can set `-c catalogMinScore=<n>`; chosen from the measurement in section 7);
2. the metadata row must say `review_status = approved`;
3. a small vision model (the same `REVIEW_MODEL` the stock reviewer and the clip check use) is shown the 1280 px preview, the narration and the intended subject and must answer JSON `{"fits": true}`: **fail closed** (an error, an unreadable answer, anything but boolean true is a no);
4. the original is read, cut to the video's aspect with the centred crop rules (9:16, 1:1, 4:5 keep the subject by construction) and bounded to the usual stock size (`assets.max_side_for`, 4K aware).
Nothing passes: the existing stock path runs exactly as before. A human pick in the editor skips the catalog. The cost of the check is added to the video's stock cost.
The ledger gets `{source: "videomk-library", license: "videomk library", creator: "videomk"}` and **no credit line** is shown or written (`assets.credits_block` leaves this source out); every other source still gets its credit.
Catalog objects are never served: the beat Lambda reads an original and bakes it into the rendered video like a stock photo.

**IAM (the beat Lambda only, no wildcard resources):** `s3:GetObject` on `<bucket>/o/*` and `<bucket>/p/*`; `dynamodb:GetItem` on the items table; `dynamodb:UpdateItem` on the demand table; `s3vectors:QueryVectors`/`GetVectors` on the one index ARN; `ssm:GetParameter` on `/videomk/catalog_demand_salt`.
It cannot write images, list the bucket, or touch another table. (Bedrock invoke rights for the embedding and the check are the ones the beat Lambda already has.) `account_deletion.py` lists the new resources as optional exemptions: they hold no personal data.

**Flag:** `-c imageCatalog=1` (default off). Off: the template has no catalog resource and no CATALOG_ variable, `try_catalog` returns at once, the demand log does nothing: nothing changes. To switch on for a stage: deploy with the flag, create the salt (`aws ssm put-parameter --name /videomk/catalog_demand_salt --type SecureString --value "$(openssl rand -hex 32)"`),
`catalog_promote.py --from local:<folder> --to qa --no-dry-run`, and watch the demand table.

## 4. The feedback loop

**What is logged**, for every image search the engine runs while the flag is on (`catalog.log_demand`, called from `catalog_pick.try_catalog`): the **generic search phrase** (the director's own 2-6 word phrase, never the user's prompt, photos or narration), `outcome` (`catalog` answered, `rejected` a match existed but failed a check, `none` nothing reached the threshold; in the last two stock is used),
`best_score`, a counter, first and last seen, and a reference to the video: **HMAC-SHA256 of the video id with a secret salt kept in SSM, 16 hex characters** (`catalog_privacy.video_ref`). Without the salt it cannot be reversed or linked to a user or video; no user id is stored. Distinct videos for a phrase = the number of rows under that phrase.
**Retention 12 months** (DynamoDB TTL on `expires`).

**What is filtered** (`catalog_privacy.generic_phrase`, deterministic, no model, errs on the side of dropping; the logger writes nothing when it returns nothing). Rejected: empty or longer than 10 words / 80 characters; emails; URLs and domain endings; **any digit** (phones, addresses, years); address words (street, avenue, calle, apartment, zip...);
first person and possessives (my, our, mi, nuestro, notre ... and any `x's`); family and acquaintance words in English, Spanish, Italian and French (wife, son, mi hijo, madre, boss, friend ...); titles with a name (Mr Smith, Sra. Lopez); "named/called/llamado"; "at home/en casa"; and about 380 common first names in five languages.
It is tested with examples (`tests/test_image_catalog.py`): "Carlos at the beach", "my wife in the kitchen", "mi hijo jugando", "call 555 123 4567", "maria@example.com", "12 Baker Street London", "calle Mayor 5", "granny's flat", "my boss at work", "photo of Mr Smith" are all refused. Known costs: a few landmarks ("queen's house") and any phrase with a digit ("1920s office") are dropped on purpose.
It cannot catch an unusual surname or a private place name with no marker word; the 12-month expiry, the absence of any user or video identity, and the owner's review of every plan before anything is generated are the other layers. (The existing small-model approach is not used in the logger: it would cost money and add latency to every image beat; `catalog_plan.py` uses it offline, per candidate.)

**The plan (`backend/scripts/catalog_plan.py`):** reads the demand table (or `--demand-json`), drops phrases the catalog already answers (best score against the catalog's vectors >= `--covered`, default 0.40), clusters the rest by meaning, keeps clusters asked by **at least 3 different videos and 3 different wordings**
(one image for three or more completely different prompts), asks a small model to turn each into a generic reusable subject or to say it is a specific landmark, species, person or brand (then it is dropped and listed under `rejected_clusters`), and writes a plan with generation subject, layout, the `serves` examples, distinct videos and the estimated cost per image.
It generates nothing and spends only embeddings and one small-model call per cluster. `approved_by` is empty: the owner reviews, edits and fills it before `catalog_generate.py` will accept the plan.

## 5. The generation tool

`backend/scripts/catalog_generate.py plan.json --store local:<folder>|qa --max-usd 5 --yes [--regen] [--only ids]`

* **Refuses** without `--yes` (it prints the estimate and exits), without `approved_by`, with an item that does not list 3 different prompts it serves, with `--store prod` (nothing is generated into prod: promote instead) and with the `default` (production) AWS profile.
* **Hard cap (current, see section 0):** `Spend.reserve` is called before every paid call with a reserve of 0.055 for the OpenAI image + 0.01 for the check + 0.0005 for the embedding (real token cost charged after; the old Bedrock figures in this paragraph are history) and refuses when the run total would pass `--max-usd` (default 5). Every charge is appended to `docs/image_catalog/spend_log.jsonl` with the item, what and the running total.
* **Per image:** generate (Control Structure from a composition guide, or Style Guide from the catalog's first approved image) -> **vision check** with Claude (adherence, quality >= 7, no visible text, no logo or brand, no recognisable real person or face close-up, no anatomy problem, no warped objects, nothing unsafe, subject survives centred 9:16 and 1:1 crops, calm bottom for captions, natural editorial style: **all** must hold, an unreadable answer fails)
  -> only a pass is upscaled (Fast Upscale 4x, stored at up to 3840 px) so rejects cost 0.07, not 0.10 -> Cohere image embedding -> **duplicate check** against the stored vectors (cosine >= 0.92: dropped) -> originals, preview, thumbnail, vector and metadata row (`review_status: approved`, with the verdict stored).
  A rejected picture is never stored; with `--regen` it is generated once more with another seed if the cap allows.
* **Idempotent** by plan item id (a marker row `plan#<plan>#<item>`): re-running skips finished items and costs nothing.
* A failed call is not retried silently; the item stays open; whatever was charged is in the log.

## 6. Promotion without paying twice

`backend/scripts/catalog_promote.py --from qa --to prod [--no-dry-run --yes-prod]` (also `--from local:<folder> --to qa`).
Dry run is the default and writes nothing. It copies, per approved image: the three objects (each verified by checksum after the write; the original must hash to its own id both in the source before and in the target after), the **vector read from the source index** (no embedding call exists in this script), and the metadata row **last** (a row means a complete image),
with `promoted_from` (the source store) and `promoted_at`. Idempotent by content hash: an image complete in the target is skipped, a half-copied one is resumed. Images that are not `approved`, have a corrupted original or lack an object or vector are refused and listed.
It refuses to write to prod without `--no-dry-run` and `--yes-prod`, and refuses `--from prod`. No model is called, so nothing is generated or embedded twice: the cost of an image is paid once, in QA (or on a laptop), and its copy to prod is a few S3 and S3 Vectors requests.
Tests use local stores as fakes; I never ran it against prod.

## 7. The pilot (measured, QA account, 2026-11-26)

**What was run:** `docs/image_catalog/pilot_plan.json` (21 items: 17 composition-guided plus 4 style-guide comparisons) through `catalog_generate.py` in three runs (the second and third after I tightened the checker and the guides; see below), into a **local store** (the QA stack with the catalog is not deployed: deploying was out of scope).
Spend, every call in `docs/image_catalog/spend_log.jsonl`: **USD 4.90 of the USD 20 allowance** (probes USD 0.24; generation, upscaling, vision checks and embeddings USD 4.66). Not counted: a few cents of Cohere text embeddings for the demand analysis (about 900 short phrases) and the plan test.
Prices used are the AWS list prices in 1.1; the AWS invoice has not been checked.

**Hit rate of my own vision check (Claude Haiku 5.5, strict: every flag must pass):** 12 pictures kept out of 61 generated, i.e. **20 percent per picture** (62 percent per item: 10 of 16 composition-guided items and 2 of 5 style-guided items produced a kept picture after up to 2 attempts each, across 3 runs). By method: composition-guided 10 kept of 47 generated, style-guide 2 kept of 14.
Reasons for rejection, in order: the bottom quarter not calm enough for white captions (about two thirds of all rejections: white foam, bright leaves, glints, glossy highlights), subject not surviving a centred 9:16 crop (sun off-centre, handle cut), saturation, wrong content (the style guide drifted to mountains when asked for dunes or autumn), screen text or a brand-like mark on a laptop, distorted fingers, an unreadable checker answer (fixed: the answer is now stored for diagnosis).
Two items hit a transient Bedrock `ServiceUnavailable` and were retried in the next run at no cost. The strictness is deliberate (a bad image is reused in many videos); it also means **a kept image cost USD 0.39 in this pilot** (USD 4.66 for 12), not USD 0.10. The 100-image bulk would therefore be about USD 40 on this method and these checks (tuned guides should do better), and that is the number to plan with. (`catalog_plan.py` quotes the no-retry price, USD 0.10 per attempt, so its totals are a floor.)

**What the 12 look like** (contact sheet `scratchpad/catalog/pilot_contact_sheet.png`, which I viewed): ten landscape-and-sky photographs that read as one product: the same cool-warm dawn palette, soft haze, 35 mm look, no text, no logos, no people; the dunes and the forest at the extremes of "calm". Honest faults:
the **alpine lake** has a pyramid-shaped rock in the middle of the water that looks like a second mountain (both the composition-guided and the style-guided versions have a rock: the model reads our guide's centre as an island); the **autumn forest** and the **rainbow** are noticeably more saturated than the rest (the checker flagged "slightly saturated"; they would stand out in a montage next to the dawn pictures);
the **pine forest** has a busy forest floor in the bottom quarter (it passed the checker but is the weakest for captions); **dunes** have no focal subject (a pattern, fine as a backdrop); the **countryside hills** have no stone wall although the brief asked for one (the checker said so, and it was kept as a generic hills image: its metadata still says "stone wall" in the prompt, so its `serves` list should not claim stone walls).
The Control Structure result is clearly sharper and better composed than the Style Guide result: the style-guided pictures keep the look (that is its purpose) but follow the composition of the anchor, ignore the layout and drift in content. 4K originals (3840 px) are produced by the 4x fast upscaler from a 1344 px image; at 100 percent they are soft but clean (not inspected pixel by pixel; the 1080p videos use a quarter of that size).
**Not achievable with this method (tried):** hands typing on a keyboard, coffee cup on a table, honeycomb macro (screens show text and brand marks, glossy highlights break the calm bottom, honeycomb looks like 3D blocks): **the people-and-objects half of the demand list needs a text-to-image model with free composition** (decision 1 in section 9).
**Style recommendation, with this evidence:** one **photoreal natural-light editorial landscape and mood style** (the house style as written). An illustrative style was not tested; photoreal is what the stock photos it replaces look like, and the checker and the viewer both found the photoreal output convincing.

**Threshold, measured on the real image vectors.** Cohere text query against the pilot images' vectors, for all 442 real searches (`pilot_vs_demand.json`): the correct matches score about 0.40 to 0.56 ("calm alpine lake at dawn" to the lake 0.53, "english countryside rolling hills" 0.56, "forest path autumn leaves" 0.56, "rainbow over green field after rain" 0.56),
loosely right ones 0.33 to 0.40 ("camel in desert dunes" 0.36, "mount everest himalaya peak" to the snow peak 0.36), and wrong ones 0.29 and below ("jebel irhoud morocco cave" 0.29 to the dunes, "golden sunrise ocean waves" 0.29 to the dunes). The default threshold is therefore **0.35** (`catalog.DEFAULT_MIN_SCORE`, `-c catalogMinScore`): below it nothing is worth a verification call, above it the small-model check decides.
The median best score of a real search against these 12 images is 0.15; 9.0 percent of searches reach 0.30, 7.0 percent 0.35 and 5.7 percent 0.40 with only 12 images (6 of the 12 serve three or more different videos at 0.35).
**Coverage estimate for the top 100 (estimated, not measured):** the description-level measurement of 2.3 is 28 percent at a text similarity of 0.40; for the 51 phrase-image pairs where the description scored 0.40 or more, the real image vector scored on average 0.097 lower (0.51 against 0.41), so the real threshold of 0.35 corresponds to a description threshold of about 0.45, where the 100 descriptions answered **21.9 percent of QA's image searches**; I would plan for **15 to 22 percent** once the images the checker or the method cannot produce (people, objects) are taken out. Production demand will differ.

## 8. Tests

`backend/tests/test_image_catalog.py` (no network: Bedrock, S3, S3 Vectors and DynamoDB are fakes or local stores, the CDK tests synthesise the real stack):
privacy filter (names, "my wife", addresses, emails, phone numbers, URLs, possessives, over-long and digit phrases refused; generic phrases kept), salted video hash, demand-log writes (hashed video, 12-month TTL, nothing personal, no write without the salt or the table),
search ordering and failure handling, the director (flag off touches nothing; a good verified approved match is cropped and recorded with no credit line; below threshold, unapproved, "no", malformed and failing verifier all fall back to stock and log the outcome), crop rules, the credit block,
the generator (plan refusals, the cap stopping before the call that would pass it and the log adding up, storage layout and metadata fields, idempotent re-run, rejection and single regeneration, duplicate drop, fail-closed judge, refusal of prod and of the default profile and of a missing `--yes`, composition guides),
promotion (dry run writes nothing, copies objects plus vectors plus rows with provenance, idempotent and resumable, refuses unapproved or corrupted images, stops on a checksum mismatch, prod needs `--yes-prod`, nothing flows out of prod), the plan (covered phrases dropped, three different videos and wordings required, landmarks rejected, not runnable until approved),
and the template (flag off: no catalog resource or variable; flag on: private encrypted versioned bucket, items and demand tables with TTL, index `catalog-images` 1024 d cosine, no public policy, beat-Lambda statements with no wildcard resource and no write or delete on the catalog).
`test_account_deletion_cdk.py` was extended: the catalog resources are listed as optional exemptions (no personal data), the per-user prefix scan still passes.

## 9. Decisions and actions for the owner

1. **(Decided: OpenAI gpt-image-2.6-flare, section 0.)** Older text: approve (or change) the model path. Today only the Bedrock Control Structure / Style Guide path is callable. For the 100-image bulk either accept it (about USD 40 at the pilot's hit rate, section 7) or create an API account: **Google AI Studio / Cloud (Nano Banana 2.1, key in SSM `/videomk/google_ai_key`)** or **OpenAI (GPT-Image-2 medium, key `/videomk/openai_api_key`)**. Neither was created or called.
2. **Have counsel read the ownership terms** quoted in 1.3 (especially: Stability models on Bedrock are not on AWS's indemnified list as far as I could read; Stability's output assignment is "if any"; the competing-model clauses matter if we ever train on the catalog).
3. **Approve the 100-image plan** (`docs/image_catalog/candidates.json`) or edit it; nothing is generated until a plan file carries `approved_by`. Decide whether landmarks stay with stock (my recommendation) and whether people scenes (hands, silhouettes) are wanted: the pilot shows they are the weak spot of this method.
4. **Decide the threshold** (section 7 explains the measured score distribution) and whether to ship the first catalog behind `-c imageCatalog=1` in QA only.
5. **Create the salt** `/videomk/catalog_demand_salt` in each stage before switching the flag on (command in section 3), and tell the legal builder the facts in 1.4 (the images are videomk's property by assignment, provenance and selection; copyright in single images may be limited; no people, logos or text).
6. **The pilot catalog lives on this laptop** (a local store), because deploying the QA stack was out of my scope. After deploying with the flag: `catalog_promote.py --from local:<folder> --to qa --no-dry-run` copies it without regenerating or re-embedding; then `--from qa --to prod` (with `--yes-prod`) when approved.
