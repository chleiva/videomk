# 3D presenters: licence research, experiments and recommendation (2026-11-26)

Context: the MuseTalk lip-sync prototype (docs/AVATARS.md) moved the mouth well but left the rest of the face dead. This document evaluates the 3D route: audio drives a facial rig (NVIDIA Audio2Face-3D, or Epic's MetaHuman Animator), the rig is rendered on a server, and the video is composited into a scene like any other layer.

Conventions: every legal or technical claim carries the provider's own URL, a quoted sentence, and "seen" = the date I read it (all 2026-11-26 unless stated). **UNVERIFIED** marks anything I could not read from the provider or measure myself. Nothing here is legal advice.

How I read Epic's pages: unrealengine.com and dev.epicgames.com answer plain HTTP clients with 403, so I read them in a browser session (public pages, no login, nothing accepted or clicked). blender.org and docs.blender.org sit behind a bot challenge that I did not try to bypass: Blender claims below come from search snippets of blender.org pages and are marked UNVERIFIED (direct reading).

---

## Part 1A. MetaHuman / Unreal Engine: what would we owe?

### What Epic's pages say

| # | Claim | Source (seen 2026-11-26) | Quoted |
|---|---|---|---|
| 1 | MetaHuman has no separate fee; it rides on the Unreal Engine licence | https://www.metahuman.com/en-US/license (FAQ "How much do I have to pay for MetaHuman?") | "MetaHuman is included as part of your standard Unreal Engine license, meaning it's free to use for anyone making under $1 million USD in revenue and standard Unreal Engine terms apply above that threshold." |
| 2 | No extra licence from UE 5.6 | same page | "No. From Unreal Engine 5.6, your use of MetaHuman is included under the terms of your existing Unreal Engine license." |
| 3 | No royalty for rendered video | same page | "MetaHuman characters and animation are classed as Non-Engine Products under the Unreal Engine EULA, so neither their use as linear media output or at runtime in games (or other interactive applications) using engines other than Unreal Engine triggers royalty obligations." |
| 4 | Seat licence above $1M | same page | "If you make over $1 million USD in annual gross revenue and render MetaHuman characters and animation outside of Unreal Engine, you'll need an Unreal Engine seat license; below that threshold, Unreal Engine is free to use." |
| 5 | Rendered video is royalty free | https://www.unrealengine.com/eula/unreal, section 4(a)(i) | "You will not be obligated to pay us any royalty payments for Distributing Products that (i) do not include any Engine Code, (ii) do not require any Engine Code to run and (iii) do not include Starter Content in source format ("Non-Engine Products") to any person or entity. This means, for example, you will not be obligated to pay us royalties for Distributing: rendered video files (e.g., broadcast or streamed video files, cartoons, movies, or images) created using the Engine Code..." |
| 6 | Seat price | https://www.unrealengine.com/en-US/license | "$1,850 per seat per year." and "If you're using Unreal Engine for commercial purposes, have generated more than $1 million in the past 12 months, and are not creating a game or application that relies on engine code at runtime and will be licensed to third party end users, then a seat license fee is required." |
| 7 | The $1M indie exception is measured on the whole company group | EULA 6(b)(i) | "During any period that you, together with any entities in your corporate group, have generated less than $1,000,000 USD in gross revenue over the last 12 months, the Seat subscription requirement will not apply to your Users. ... revenue includes any advances received or other funds raised." |
| 8 | Seats are per human developer | EULA 6(a) | "An individual Seat is personal to the User to which it has been assigned" and "'Seat' means the right granted to you by Epic to allow one User to access and use the Licensed Technology on your behalf" |
| 9 | Royalty product rate and threshold (applies only if a product is NOT royalty-free) | EULA 3(a) of the Royalty Addendum and 4(b) | "The Royalty Rate is equal to 5% of all Royalty Revenue" and "you will not be obligated to pay us royalty payments under this Agreement unless a Product directly generates more than $1,000,000 USD in gross revenue." |
| 10 | Credit line | EULA 7(a) | "If a Product you develop under this Agreement has credits, you must place the following notices in the credits ...: "[Product name] uses Unreal(R) Engine. Unreal(R) is a trademark or registered trademark of Epic Games, Inc. ..."" |
| 11 | MetaHuman Creator/Animator outputs are licensed under the same EULA | https://www.unrealengine.com/ue-devs-can-now-choose-to-train-ai-models-on-their-projects (dated 2026-10-29) | "MetaHuman Creator, MetaHuman Animator, and Mesh to MetaHuman are licensed under the Unreal Engine EULA." |

### The "train or test AI/ML" clause (the report was right, with a nuance)

* Epic's own announcement, dated **October 29, 2026**: "We've deleted two restrictions from Section 6e (General Restrictions) of the EULA ... The restriction on using MetaHuman digital characters and animation curves, or rendered output made to replicate MetaHuman functionality, to build or enhance a database or to train or test AI, machine learning, deep learning, or neural network technologies." (https://www.unrealengine.com/ue-devs-can-now-choose-to-train-ai-models-on-their-projects)
* The EULA change log lists it as "EULA update 22 (October 30, 2026): Removes the restrictions in Section 6(e) on using the Licensed Technology as training or prompt input for generative AI, and on using MetaHuman digital characters and animation curves to build databases or to train or test AI and machine learning technologies." (https://www.unrealengine.com/eula-change-log/unreal). The restriction had been added by update 21 on June 3, 2025.
* The live EULA text I read (https://www.unrealengine.com/eula/unreal) now lists in 6(e) only: breaking the law, renting/leasing, misappropriating other Epic products, patent claims, security interests, and distribution outside sections 4 and 5. No AI clause.
* **Nuances.** (a) The metahuman.com FAQ I read the same day still carries the old sentence ("you may not use MetaHuman characters or animation curves to build or enhance any database or train or test artificial intelligence, machine learning ..."): the FAQ is stale or the page is cached; the EULA and change log govern. (b) Existing users are not moved automatically: "If you already use Unreal Engine, you can choose to accept the new EULA at any time on the Unreal Engine EULA acceptance page." (the owner must accept it on his own account). (c) Fab assets are separate: "Sellers can still choose whether to allow AI training on their content by using the 'NoAI' tag." (d) This matters to us mainly if MetaHuman output is ever used to train something; for plain rendering of presenters it was never a blocker, because "You can use MetaHuman characters and animation in workflows that incorporate artificial intelligence technology" (metahuman.com FAQ).

### What we would owe, in plain words

1. **Today and below $1M of company revenue (including funds raised, whole corporate group): nothing.** Unreal Engine, MetaHuman Creator and MetaHuman Animator are free. No royalty on rendered video in any case (rows 3 and 5).
2. **Above $1M of gross revenue in the trailing 12 months: seat subscriptions, $1,850 per seat per year, for each person who accesses Unreal Engine** (row 4, 6, 8). Not a percentage. 1 to 2 seats for an artist/engineer = $1,850 to $3,700 a year. This starts the moment the company crosses $1M over any 12-month window ("During any period that you ... have generated less than $1,000,000").
3. **What we do NOT owe:** no per-video or per-minute fee, no 5% royalty on video files, no fee to NVIDIA/Epic per render, no extra MetaHuman licence.
4. **The part I cannot settle from Epic's pages (needs Epic's written answer, see the email below):**
   * **Hosted multi-tenant rendering.** The EULA defines "Distribute" to include "make its functionality available on a network", and the Non-Engine exemption is for Products that "do not require any Engine Code to run". A service that renders on Epic's engine for each customer arguably "requires Engine Code to run" on our servers, but the only thing that leaves the building is a video file. The pricing page frames royalty for "a game or application that relies on engine code at runtime and will be licensed to third party end users", which a render service is not. My reading: video files are Non-Engine Products and our render farm is internal use, so seats (above $1M) are the only cost. **UNVERIFIED by Epic.** The downside if Epic reads it the other way is the 5% royalty on revenue the product generates above $1M lifetime, with the service itself as the "Product".
   * **Seats for a headless server.** The EULA ties seats to human "Users". Whether an unattended render worker needs a seat of its own, or only the people who operate it, is not stated. **UNVERIFIED.**
   * **"UE-Only Content" vs "all engines".** The Epic Content License Agreement, MetaHuman Content Addendum, says: "MetaHuman Content that you acquire may only be used and shared as UE-Only Content." (https://www.unrealengine.com/eula/content). The MetaHuman FAQ says MetaHuman characters "can be used across all engines and creative software". Rendering inside Unreal satisfies both readings, so the plan "render in Unreal, ship video" is safe either way; exporting a MetaHuman to Blender is the contested step.
   * **Presets as our recurring named presenters.** Nothing I read forbids using an unmodified preset as a recurring character in videos (the Content EULA says "You also own the copyright interest you acquire in the depiction of rendered MetaHuman Content in Projects" and "you may freely Distribute Licensed Content incorporated into rendered linear media products"). Two cautions: presets are shared by every other MetaHuman user, so they are not exclusive (any competitor can show the same face); and the Content EULA bars selling Licensed Content "on a 'stand-alone basis'". A video of the preset is not stand-alone content, so it should be fine. **Epic has not confirmed that reading.**
   * **Fab terms for community preset characters** (if we buy rather than use Epic's presets): https://www.fab.com/eula (Last updated: October 1st, 2024): "you may freely Distribute a Project that is a rendered linear media product ... rendered video files (e.g., broadcast or streamed video files, cartoons, movies, or images)", "Subject to any applicable restrictions in Section 6". Each listing can carry extra limits; read each one.
5. **Revenue thresholds, summarised:** $1M gross over 12 months (company group, incl. funding) = free to seat-required. $1M lifetime per royalty product / $10k per quarter only matter if Epic classes the service as a Royalty Product (then 5%, or 3.5% for Epic Games Store parity releases, which cannot apply to us).
6. **Accepting terms is the owner's job:** an Epic account, the Unreal Engine EULA and (for MetaHuman downloads) the Epic Content License Agreement. I accepted nothing.

### Email to Epic (ready to send)

Where to send it: Epic publishes no licensing email address. The contact route on both metahuman.com/license and unrealengine.com/license is a web form ("Contact us" / "Get in touch": https://forms.unrealengine.com/s/lead?language=en_US&sourcepage=MetaHuman , reached via https://www.metahuman.com/license/contact-us). The form's own text: "Looking for premium support, private training, custom licensing terms, and/or royalty-free distribution of commercial off-the-shelf products?" The unrealengine.com/license page adds "Sign in (or create an Epic Games account) and someone from our team will be in touch." Form details and sign-in are the owner's. **A reply is not guaranteed** and no response time is published.

> Subject: Licensing question: server-side MetaHuman rendering for a video-generation service
>
> Hello,
>
> We are a small company (gross revenue well under US$1M) building a web and mobile service that turns a user's text into narrated explainer videos. We would like to add a recurring on-screen presenter: a MetaHuman (an unmodified Epic preset, or a character from Fab) whose face is animated from the narration audio with MetaHuman Animator and rendered by Unreal Engine on our own cloud GPU servers, headless, with Movie Render Queue. Customers pay us credits and receive an MP4; they never receive Unreal Engine, MetaHuman assets, or any engine code.
>
> Could you confirm in writing, under the Unreal Engine EULA (update 22) and the Epic Content License Agreement:
> 1. The rendered MP4 files are Non-Engine Products (section 4(a)(i)) and no royalty is owed on them, even though they are sold to end customers inside a hosted service where each video is rendered on demand on our servers.
> 2. Our hosted render service itself is not a "Royalty Product" because customers do not run or access Engine Code ("make its functionality available on a network" in the definition of Distribute).
> 3. While our gross revenue over any 12 months is under $1,000,000, no seat or fee applies to headless render workers or to the engineers who operate them. Above $1,000,000, do seats apply only to the humans who open the editor, or also to each unattended render server (automatically scaled up and down, many instances)?
> 4. An unmodified MetaHuman preset may be used as a recurring named presenter in videos we sell, and the MetaHuman Content Addendum's "UE-Only Content" rule is satisfied by rendering inside Unreal Engine.
> 5. Whether the credit line in section 7(a) applies to videos that have no credits.
> 6. Whether any attribution or "AI-generated" labelling requirement applies to videos using MetaHuman Animator audio-driven animation.
>
> If a custom agreement is the right route for a hosted rendering service, please tell us how to start one.
>
> Thank you,
> [name, company, country, Epic account email]

---

## Part 1B. NVIDIA Audio2Face-3D: licences and what the outputs are

### Components and their exact licences

| Component | Licence | Source (seen) | Quoted |
|---|---|---|---|
| Hub repo | no top-level licence | https://github.com/NVIDIA/Audio2Face-3D (GitHub API: `license: null`) | n/a: it is an index of the pieces below |
| **SDK** (C++/CUDA/TensorRT, runs the models, includes the blendshape solver) | **MIT** | https://github.com/NVIDIA/Audio2Face-3D-SDK/blob/main/LICENSE.txt | "Permission is hereby granted, free of charge, to any person obtaining a copy of this software ... to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software" |
| Training framework | Apache-2.0 | https://github.com/NVIDIA/Audio2Face-3D-Training-Framework (GitHub API) | n/a (standard) |
| Maya ACE plugin, UE5 plugin (v2.5 for UE 5.5/5.6, has a MetaHuman sample) | MIT | hub README (2026-11-26) | n/a |
| **Models** (v3.0 diffusion; v2.3/2.3.1 regression for Mark, Claire, James) | **NVIDIA Open Model License**, Last Modified October 24, 2025; **not gated** on Hugging Face (API: `gated: False`) | https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/ and https://huggingface.co/nvidia/Audio2Face-3D-v3.0 ("This model is ready for commercial/non-commercial use.") | see below |
| **Audio2Emotion** models (v2.2, v3.0 experimental) | separate "nvidia-audio2emotion-license", **gated: owner must click through on Hugging Face** | https://huggingface.co/nvidia/Audio2Emotion-v2.2 | "This model and any technology included with this model may only be used in connection with the NVIDIA Audio2Face project"; "You may not use this model or any of its components for the purpose of emotion recognition." Gate text: "you have to accept the conditions to access its files and content" |
| **Sample dataset** (Claire, 3D training data) | "nvidia-audio2face-sample-data-license" | https://huggingface.co/datasets/nvidia/Audio2Face-3D-Dataset-v1.0.0-claire/blob/main/LICENSE | "solely to train and evaluate models using NVIDIA Audio2Face"; Section 2(c) forbids to "sell, rent, sublicense, transfer, distribute, offer or otherwise make the Sample Dataset and Derivative Works" available. Not needed by us. |
| **NIM container** | NVIDIA Software License Agreement + Product Specific Terms for AI Products; docs for 1.3 say a NVIDIA AI Enterprise subscription is needed; NGC login | https://catalog.ngc.nvidia.com/orgs/nim/nvidia/containers/audio2face-3d (search result summary; **UNVERIFIED in detail**) | We do not need it: the MIT SDK plus the open models run without NGC. |

### What the Open Model License allows a hosted commercial service (read in full 2026-11-26)

* "Models are commercially usable." "NVIDIA does not claim ownership to any outputs generated using the Models or Derivative Models." "NVIDIA claims no ownership rights in outputs. You are responsible for outputs and their subsequent uses."
* Licence grant: "a perpetual, worldwide, non-exclusive, no-charge, royalty-free, revocable (as stated in Section 2.1) license to publicly perform, publicly display, reproduce, use, create derivative works of, make, have made, sell, offer for sale, distribute (through multiple tiers of distribution) and import the Model."
* **Hosted service:** the licence has no clause restricting running the model as a service or SaaS, and none requiring a per-use fee. Redistribution conditions apply only "If you distribute the Model": give the licence and include "Licensed by NVIDIA Corporation under the NVIDIA Open Model License". We would not distribute the model (it stays on our servers).
* **"Built on NVIDIA Cosmos"** attribution applies only to NVIDIA Cosmos models, not Audio2Face.
* **Conditions to watch:** (1) "If You bypass, disable, reduce the efficacy of, or circumvent any technical limitation, safety guardrail ... your rights under this Agreement will automatically terminate" (we should not touch guardrails; Audio2Face has none that I found); (2) "Use of the Models under the Agreement must be consistent with NVIDIA's Trustworthy AI terms" (https://www.nvidia.com/en-us/agreements/trustworthy-ai/terms/, **not read**: UNVERIFIED); (3) the licence is "revocable" and NVIDIA "may update this Agreement to comply with legal and regulatory requirements at any time and You agree to either comply with any updated license or cease"; (4) "You will indemnify and hold harmless NVIDIA from and against any claim by any third party arising out of or related to your use or distribution of the Model, Derivative Models or outputs"; (5) citation request in the SDK README for publications (not a licence term).
* **Net:** for animation curves generated by the models and rendered on our servers into videos we sell: allowed, royalty-free, no NVIDIA account, no click-through (for the A2F models; Audio2Emotion needs the owner's click). The models themselves are free of any NVIDIA charge.
* **The sample characters (Mark, Claire, James) are the open question.** The model data ship the characters' skin geometry and 52 blendshape deltas inside the model files (npz), so they are part of "the Model" under the licence (commercially usable), but I found no statement about the right to use the characters' faces as a brand presenter, nor whether Claire/James/Mark are scans of real people. For the experiment I use only geometry vertices from the public model files; **for a product I would not ship these heads** (likeness/publicity rights unknown, and the mesh has no faces, eyes, teeth or hair in the model files).

### What the outputs are (read from the model card, SDK headers and config files; confirmed by my run in Part 2)

* Model card (https://huggingface.co/nvidia/Audio2Face-3D-v3.0): "Facial motion on skin, tongue, jaw, and eyeballs"; architecture "Transformer, Diffusion", 1.8e8 parameters; "Audio input is encoded and concatenated with emotion label, then passed into diffusion-mechanism to output facial motion sequence."
* SDK `executor.h`: geometry results = skin geometry (24,002 vertices x 3), tongue geometry (5,602 vertices), jaw transform (15 floats), eyes rotation (4 floats). The blendshape executor additionally solves the skin to **52 ARKit-named blendshape weights** (+ tongue weights) with a solver whose config is in `bs_skin_config_*.json`.
* The model has 10 emotion inputs: amazement, anger, cheekiness, disgust, fear, grief, joy, outofbreath, pain, sadness (model.json). They come from Audio2Emotion (gated) or can be set by hand.
* Eye controls in the config (`model_config_*.json`): `blink_strength`, `saccade_strength` (0.6 default), `eyeballs_strength`, `eye_saccade_seed`, `eyelid_open_offset`: blinks and saccades are generated by the post-processing/animator, not recorded.
* **Best model:** v3.0 (diffusion, "multi" identity: Claire, James, Mark; HF last modified 2025-10-21). Regression v2.3/2.3.1 is single-identity, faster per frame but older; v3.0 is the newest and the one I measured.

### Hardware and software for inference

* Model card: TensorRT, "Tested GPUs: T4, T10, A10, A40, L4, L40S, A100, RTX 6000 Ada, ... RTX 3080/3090/4080/4090/5090"; Linux or Windows. SDK README: "CUDA 12.8.0+ ... TensorRT >=10.13, <11.0 ... 4GB+ GPU memory recommended", build with `g++/make/CMake`.
* **Linux headless inference path that worked:** build the MIT C++ SDK from source (about 15 minutes on 4 vCPUs) with CUDA 12.9 + TensorRT 10.13 from NVIDIA's public apt repository (no login), convert the ONNX to a TensorRT engine with `trtexec` (public), and drive it from a small C++ program (my `a2f_dump.cpp`). Python bindings exist for the data-prep scripts only; there is no pip package for inference. The NIM container is the alternative (gRPC), but needs NGC and its own terms.
* Gotchas I hit: the apt repo now defaults to TensorRT 11, which the SDK rejects (pin `10.13.3.9-1+cuda12.9` for all libnvinfer packages and also install the `-dev` packages for the ONNX parser and plugin); the SDK needs a static zlib >= 1.3.1 (`ZLIB_ROOT` to the packman copy).

---

## Part 1C. Rendering a 3D character headless on a server

| Route | Licence | Headless on a Linux GPU | Cost / notes |
|---|---|---|---|
| **Blender (Cycles, GPU/OptiX)** | Blender is GPL; the licence applies to the application, not to what you render. From blender.org's FAQ as shown in a search snippet: "The output of Blender, in the form of .blend files, is considered program output, and the sole copyright of the user." and the manual: the GPL "only applies to the Blender application and not the artwork you create with it" (https://www.blender.org/support/faq/ , https://docs.blender.org/manual/en/latest/getting_started/about/license.html ; **UNVERIFIED by direct reading**: both sites refuse non-browser clients and sit behind a bot challenge I did not bypass). Python scripts that call Blender's API must be GPL if published. | **Yes, measured** (Blender 4.2.23 tarball from download.blender.org, `-b`, OptiX on an A10G, no display). | Free. Cycles at 1080p is slow (see Part 2). EEVEE (rasterised) is much faster but needs an OpenGL/EGL context; **not tested**. |
| **Unreal Engine headless (Movie Render Queue, `-RenderOffscreen`)** | Epic EULA above | Linux builds exist; getting one requires the owner's Epic login (Launcher on Linux, or GitHub source access linked to an Epic account). **Not tested.** MetaHuman 5.8 notes: "Offline and real-time facial MetaHuman Animator functionality available on Linux and macOS" (https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine, seen 2026-11-26). Known Linux issue in the 5.8 notes: assembling characters repeatedly can exhaust RAM. Whether the audio solve and the MRQ render can be driven fully unattended from the command line: **UNVERIFIED** (the 5.8 notes mention "unattended processing", the docs have "Batch Processing in the Content Browser"). | Free below $1M (Part 1A). Quality is the best of all routes (hair strands, skin shaders, eye/teeth, Lumen). Cost per frame depends on quality preset: seconds per frame for cinematic, tens of ms for real-time quality. **UNVERIFIED, estimate.** |
| **three.js / Babylon.js in headless Chrome** | MIT / Apache-2.0 | WebGL on a GPU in headless Chrome with EGL works in general; capture frames through Puppeteer. **Not tested.** | Real-time speed (tens of ms per frame), PBR quality below Unreal and Blender, but cheapest by far; the browser side is also where the existing renderer (Remotion/Chrome) of videomk lives, so it composites naturally. |

### Where to get a head with the 52 ARKit blendshapes (state in Nov 2026)

* **NVIDIA sample characters (Mark, Claire, James).** Skin vertices (24,002) and 52 blendshape deltas are inside the Hugging Face model files (`bs_skin_*.npz`, key `neutral`, `poseNames`, `frontalMask`); no triangles, no eyes, teeth, hair, no textures. Licence = Open Model License (models "commercially usable"); likeness rights **UNVERIFIED**. Used in Part 2B as a proof of motion only.
* **Ready Player Me: do not use.** The public service closed on January 31, 2026 after Netflix bought it (TechCrunch, 2025-12-19, https://techcrunch.com/2025/12/19/netflix-acquires-gaming-avatar-maker-ready-player-me/ ; closure summary via search, **UNVERIFIED in primary**); its developer APIs went offline.
* **Face Cap model in three.js examples** (`examples/models/gltf/facecap.glb`, 52 ARKit morph targets, eyes, teeth): the example page credits "model by Face Cap" (https://github.com/mrdoob/three.js/blob/dev/examples/webgl_morphtargets_webcam.html) but neither three.js nor bannaflak.com/face-cap states a licence for the model. **Treat as not licensed for commercial use**; not used.
* **Sketchfab CC0/CC-BY heads:** downloads need a Sketchfab login (owner action); availability of an ARKit-52 head with a clean licence **UNVERIFIED**.
* **MetaHuman presets:** best look; usable in Unreal under the EULA (Part 1A); export to Blender/Maya through "MetaHuman for Maya/Houdini ... free to download via the Fab Marketplace under the Standard License" (metahuman.com FAQ), with the UE-Only caveat.
* **Reallusion Character Creator / commissioning an artist:** paid per seat or per head; prices **UNVERIFIED**. A commissioned head with a work-for-hire contract is the cleanest licence for a branded, exclusive presenter.

What each looks like (eyes / teeth / hair / skin): NVIDIA mesh: bare skin only, I had to add spheres for eyes, ellipsoids for teeth and a dark cavity (see Part 2B); no hair or lashes. MetaHuman: sculpted eyes with caustic/iris detail, teeth, tongue, strand hair, eyelashes, 8K skin; the reference for "natural". Reallusion CC: good teeth/tongue/eyes, hair cards, stylised skin. Generic ARKit heads from three.js examples: low-poly eyes and teeth, painted textures.

---

## Part 2B. Rendering the animation on a 3D head (Blender headless): what it looks like

**What I rendered.** Blender 4.2.23 (GPL, downloaded from download.blender.org), Cycles, OptiX on the A10G, no display. Head = NVIDIA's sample character "Claire" from the public model file (24,002 vertices and 52 blendshape deltas; licence = NVIDIA Open Model License, "commercially usable"; **likeness rights unknown, so this is a proof of motion, not a product asset**). The model files contain no triangles, so I reconstructed faces with a cylindrical-projection Delaunay triangulation (script `build_mesh.py`), added spheres as eyes (procedural iris, driven by A2F's eyeball rotation, median-centred), flattened ellipsoids as teeth (lower one follows the lip), a dark cavity for the mouth, painted brows/lashes/lips as vertex colours, skin shader with subsurface, three area lights, neutral grey background. A2F weights drive the 52 shapes exactly as emitted (60 fps, rendered at 30 fps). Added by me and **not from Audio2Face**: procedural head sway (about 1.5 to 2 degrees, plus a little nod with jaw opening) and procedural blinks (random, mean 4 s gap; in the English clip only one fell inside 12.7 s, at 9.9 s). 1920x1080 H.264 with the real narration muxed in.

* `s3://videomk-qa-552357225438/lab/avatars/out/a2f_head_en.mp4` (en.wav, neutral emotion) and `.../a2f_head_es.mp4` (es.wav, emotion "joy" 0.8). Local copies: `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/avatar3d/a2f_head_en.mp4` and `a2f_head_es.mp4`; frame sheets in `.../avatar3d/fx/` (`sheet_en.png`, `sheet_es.png`, `blink_sheet.png`).
* **Render cost (measured):** English, 380 frames, 733 s; Spanish, 407 frames, 778 s, the two jobs running in parallel on 4 vCPUs and one A10G at 1080p, 24 samples, OptiX denoise: about 1.9 s per frame per job.

**Honest description of what I saw (I extracted frames and looked at them):**
* **Motion: this is what the test is about, and it is convincing in part.** The jaw, lips (rounding, closing, wide smile), brows and cheeks move smoothly with the speech in both languages. In the Spanish clip the "joy" emotion gives a clearly alive face: wide smile, raised outer brows (up to 0.43), the mouth shapes follow the syllables. With neutral emotion the English face is calm: brows barely move (0.09 average outer-up), which reads as "reading a script". Eyes: the eyeballs move continuously and shift gaze, which already removes the "dead stare" of MuseTalk; in the blink frames the lids close and open over about 0.25 s (the blink is my generator, the lid shapes are A2F's rig). Subtle head sway adds life (mine).
* **Lip-sync accuracy on Spanish:** the mouth opens on the open vowels and closes on b/m/p segments (mouthClose peaks at 0.6 to 0.85 in the weight plots); I judged by eye on sampled frames and the weight curves, not with a lip-sync metric: **UNVERIFIED quantitatively**. The A2F model is trained on multiple languages (the sample set includes Mandarin clips), and the Spanish curves look as articulate as the English.
* **Mesh and skin quality: poor, and this is a limitation of my head, not of the animation.** Around the mouth, cheeks, eye sockets, ears and neck the triangulation I reconstructed leaves holes and speckled fragments (a "stubble" of missing triangles); the model files ship vertices without faces, and the 2.5D reconstruction cannot recover the folds of the lip and eyelid geometry. The skin is a flat colour with no pores, no texture, no hair, no eyelashes (the lash line is a dark vertex colour) and a bald head; teeth are a plain white band; the eyes are sphere-and-shader and look rather glossy and wide. It would not pass as a presenter; at thumbnail size the motion is readable, at full size the mesh holes are the first thing you see.
* **What a production-quality head adds:** a proper closed mesh with its own topology (no holes, correct lip and eyelid loops), skin textures and a skin shader, strand or card hair, eyebrows and lashes that move with the shapes, teeth and tongue rigged to the jaw, believable eyes with a cornea and wet edge, and a shoulders-and-clothes body. These are exactly what a MetaHuman or a commissioned head supplies. They do not change the motion data; they decide whether the motion is believed.
* **Artefacts to know:** the eyelid fragments flicker during blinks; the mouth cavity is a static ellipsoid; the neck/shoulder boundary has gaps; head rotation is limited to a few degrees because the back of the head is not meshed.

## Part 2C. MetaHuman test the owner can run (about 1 hour of hands-on once the engine is installed)

I could not run this (it needs the owner's Epic login and licence acceptances). Everything below is taken from Epic's documentation pages read on 2026-11-26; **I have not clicked through it**, so menu names are as documented and a label may differ slightly in the release you install.

### Does it run on a MacBook?
* **Unreal Engine 5.8 (the current release in Epic's documentation): yes, MetaHuman Animator now runs on macOS.** Epic's 5.8 release notes: "MetaHuman Animator now supports Linux and macOS ... You can generate facial animation from performance capture on Linux and macOS, without requiring access to a Windows machine." and "Offline and real-time facial MetaHuman Animator functionality available on Linux and macOS." (https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine). In 5.7 the Creator was on Mac/Linux but Animator was deferred, so **use 5.8, not 5.6/5.7**. Audio-driven animation is part of MetaHuman Animator (page "Audio Driven Animation", prerequisites: "An Unreal Engine 5.6 (or later) project. The MetaHuman Animator plugin enabled.").
* **Apple Silicon:** Epic's hardware page lists the recommended GPU as "At least nVIDIA RTX 3070, AMD RX 6800 XT, or Apple M2 Ultra, with 8GB VRAM", CPU "at least 16 physical, high performance cores with 32GB RAM", and for Creator "Mac users with an M1 chip won't be able to render strands, so a newer chip is required" (https://dev.epicgames.com/documentation/metahuman/hardware-requirements). So a MacBook Pro with an M2 or newer and 32 GB or more should work but slowly; **a base MacBook Air will struggle**; this is a recommendation, not a hard minimum (**UNVERIFIED on your exact model**). macOS version and Xcode requirements: **UNVERIFIED** (the Epic Games Launcher shows them on the engine tile; Unreal on Mac normally needs Xcode installed from the App Store).
* **If the Mac is too weak:** the cheapest fallback is a Windows or Linux machine with an NVIDIA GPU (a cloud GPU instance by the hour, e.g. an AWS g5.xlarge Windows instance at about $1.5/hour or a Linux g5 at about $1.07/hour; prices from docs/AVATARS.md for Linux; Windows price **UNVERIFIED**) used through remote desktop; it needs the same Epic login on that machine.

### Known issues to expect (from Epic's 5.8 known-issues page)
"Animation generated from audio processing is output at a fixed frame rate of 30fps and cannot be configured to match your project's target frame rate." (fine for this test). A forum thread reports a long freeze (about 20 s) when generating from an audio clip in 5.6: do not click twice.

### Files (already prepared)
`/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/avatar3d/en.wav` (English, 12.7 s) and `.../es.wav` (Spanish, 13.6 s): the same two narrations used for every experiment. (16 kHz mono copies `en_16k.wav` and `es_16k.wav` sit beside them; MetaHuman Animator accepts any format Unreal imports, so use the originals.)

### Steps
1. **Account and launcher (owner).** Create or sign in to an Epic Games account, install the Epic Games Launcher for macOS (epicgames.com download page), accept the Unreal Engine EULA when prompted (**this is the licence acceptance I cannot do for you**; if you already have an account, also accept EULA update 22 on the Unreal Engine EULA acceptance page if you want the AI-clause removal, not needed for this test).
2. **Install the engine.** Launcher > Unreal Engine > Library > install **5.8** (latest). Before installing click **Options** and tick **MetaHuman Creator Core Data** (without it there are no presets: Epic's page says it "includes presets, grooms, texture models"). Disk and time: tens of GB, 20 to 60 minutes depending on the line (**size UNVERIFIED**).
3. **New project.** Launch > Games (or "Film / Video & Live Events") > **Blank**, Blueprint, no starter content, name it `AvatarTest`. (The first launch compiles shaders: 5 to 15 minutes on a Mac.)
4. **Plugins.** Edit > Plugins > search "MetaHuman" > enable **MetaHuman Creator** and **MetaHuman Animator** > Restart Now.
5. **Make the presenter.** In the Content Browser right-click an empty area > **MetaHuman > MetaHuman Character**, name it `MHC_presenter`, double-click to open MetaHuman Creator. In the ribbon open **Library** and pick a preset: choose an adult with a plain, symmetrical, neutral look and no strong styling (the preset names are shown as thumbnails in the Library; I could not read a list of names: **pick visually**; a clean-shaven mid-age preset with short hair reads as the most neutral presenter). Applying a preset "copies the entire preset onto your current character" (Epic's Presets page), so nothing is modified in the library.
6. **Assemble.** In the ribbon open **Assembly**, choose **UE Cine** (the "highest fidelity" pipeline for offline rendering) and run it. Epic's page: "To be assembled, a character must be rigged and the high-resolution textures downloaded", so the first assembly downloads data from Epic's MetaHuman service (needs the internet and your login). Expected: 10 to 30 minutes. Result: a folder `Content/MetaHumans/<name>/` with a Blueprint `BP_<name>`.
7. **Import the audio.** Drag `en.wav` and `es.wav` from Finder into the Content Browser (creates two SoundWave assets).
8. **Solve the face from audio (the MetaHuman Animator audio workflow, from Epic's page "Audio Driven Animation").** Right-click in the Content Browser > **MetaHuman Animator > MetaHuman Performance**. Double-click it. In Details: **Input Type = Audio**; **Audio** = `en`; **Visualization Mesh** = the face mesh of your character. Leave **Generate Blinks** on and **Head Movement** on (5.6+); leave **Realtime Audio** off ("uses the real-time algorithm ... which does not produce head motion"); **Solve Overrides > mood** = Auto Detect for the first run. Click **Process**. When finished, click **Export Level Sequence** and assign your character blueprint (or Export Animation).
9. **Second run for expression.** Duplicate the Performance asset for `es`, then repeat with a mood override (Happy, intensity about 0.7) on one of the clips. Compare Auto Detect vs Happy.
10. **Render a video.** Open the exported Level Sequence. In Sequencer add an **Audio track** with the same wav (so the video has sound) and a **Camera Cut** with a camera framed on the head and shoulders, 1920x1080. Add a light (a Directional Light plus Sky Light, or use the MetaHuman lighting scenarios from Epic's page "Custom Lighting Scenarios and Render Settings"). Then **Window > Cinematics > Movie Render Queue** (enable the plugin if missing), add the sequence, Settings: Output resolution 1920x1080, format **Apple ProRes** (macOS) or **PNG sequence** (then join with `ffmpeg -framerate 30 -i name.%04d.png -i en.wav -c:v libx264 -pix_fmt yuv420p out.mp4`), anti-aliasing Spatial Samples 4 to 8, then **Render (Local)**. If the Mac has little memory, use Sequencer's simpler **Render Movie** button first.
11. **What to look at.** Blinks (frequency, shape), eye movement, brows when the mood changes, subtle head motion, lip closure on b/m/p in the Spanish clip, teeth and tongue visibility, skin and hair at 1080p.
12. **How long.** Install 20 to 60 min; first project start 5 to 15 min; assembly 10 to 30 min; each audio solve 1 to 3 min (**UNVERIFIED**); each 13 s render at 1080p 5 to 20 min on an Apple laptop. First time total 2 to 3 hours with downloads; if the engine and character are already installed, the audio-to-video loop is about an hour. Please write down the minutes each step takes: they feed the cost model.

What to send back: the two MP4s, the time of each step, and whether Epic's EULA acceptance page asked anything unexpected.

---

## Part 2A. Audio2Face-3D v3.0 on the lab GPU: measured results

Setup (all public, no login, nothing accepted): g5.xlarge (A10G 24 GB, eu-north-1), Ubuntu 22.04 Deep Learning AMI, driver 580; CUDA 12.9 and TensorRT 10.13.3.9 from NVIDIA's apt repository; SDK built from `github.com/NVIDIA/Audio2Face-3D-SDK` (MIT); models `nvidia/Audio2Face-3D-v3.0` from Hugging Face without a token; ONNX to TensorRT engine with `trtexec` (**147 s, one time**). My driver `a2f_dump.cpp` (kept in the scratchpad `avatar3d/lab/`) feeds the 16 kHz narration and writes CSVs. Identity = "Claire" (index 0), fixed noise seed. **Audio2Emotion was not used (gated: needs the owner's Hugging Face click); emotions were set by hand.**

| Measurement | en.wav (12.66 s) | es.wav (13.55 s) |
|---|---|---|
| Frames out | 760 (**60 fps**) | 814 |
| Values per frame | 68 blendshape weights (52 ARKit skin + 16 tongue), 6 eye values, 16 jaw values (a 4x4 matrix) | same |
| GPU network, geometry only (skin+tongue+jaw+eyes) | 0.30 s = **0.023 s per audio second** | 0.32 s = 0.024 |
| With the blendshape solve (CPU solver) | 2.0 to 2.3 s = **0.16 to 0.18 s per audio second** | 2.1 to 2.3 s |
| Peak GPU memory (nvidia-smi, 0.2 s sampling) | **3,165 MiB** (includes the CUDA context) | 3,165 MiB |
| Cold start (load engine + first run) | 41 s wall | 6 s wall once warm |

So the animation step is almost free: a presenter minute costs 1.4 s (network only) to 11 s (with the CPU solve; the SDK also has a GPU solver `useGpuSolver`, untested) of GPU time, about **$0.0004 to $0.003 per presenter minute** at $1.067/h. Compare with the rendering step below, which dominates.

### Plots (proof of what comes out of the audio alone)
Files in `/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/avatar3d/`: `a2f_en_all.png`, `a2f_es_all.png` (neutral emotion), `a2f_en_joy.png`, `a2f_es_joy.png`, `a2f_en_sad.png`, `a2f_en_anger.png`, `a2f_en_amaze.png`. Raw CSVs are in `a2f2/` there and in `s3://videomk-qa-552357225438/lab/avatars/out/a2f2/`.

Findings (numbers computed from the CSVs):

| Channel | Result with neutral emotion | With emotion set by hand (0.8) |
|---|---|---|
| **Mouth/jaw** | jawOpen up to 0.46, mouthClose, funnel, pucker all follow the syllables (clear). Both languages. | similar, plus smile mean 0.30 (joy) |
| **Blinks** | **None.** eyeBlink weights never exceed 0.10 and only drift slowly with the gaze (0 blink peaks above 0.5 in every run, en and es). | still none (max 0.17 in anger, 0.16 in sadness) |
| **Eye gaze** | Eyeball rotation changes continuously (several degrees, range about -3 to 7 degrees on one axis, jitter plus slow drift with a few step changes), only **weakly related to speech** (correlation with jawOpen 0.04; with the smoothed audio loudness 0.16 to 0.26 across en/es, i.e. it tends to drift up while talking and settle in pauses). The fast part is generated saccades from a seed table (`saccade_strength` 0.6, `eye_saccade_seed`, `saccade_rot_matrix` of 5,000 samples in the model data), not from the audio. | same character |
| **Brows** | almost none: browOuterUp mean 0.09 (max 0.16), browDown 0.06, browInnerUp 0.02 | joy: outerUp mean 0.23 max 0.42, innerUp 0.20; sadness: innerUp 0.40, browDown 0.20; anger: browDown 0.58; amazement: outerUp mean 0.47 max 0.64 |
| **Head motion** | **None** (the model outputs no head pose) | none |
| Cheeks, squint, nose | nearly 0 | cheek/nose activity appears with emotion (smile, anger) |

Reading: the SDK's eyelid blink is a manual parameter (`blinkOffset * blinkStrength` in `multitrack_animator_cuda.cu`), not a prediction: **blinks must be added by us** (a random generator is trivial, I used one in the render, clearly marked); **head motion must be added by us**; **brow and upper-face expression comes only from the emotion input** (Audio2Emotion is gated and licensed "only with Audio2Face"; or we choose emotions per scene from the script, which fits videomk since the planner knows the tone of each beat). Gaze is plausible-looking noise. MetaHuman Animator's audio solve, by comparison, advertises blinks, head movement and mood from the audio in one step ("Audio Driven Animation can now generate head movement straight onto your MetaHuman"; options "Generate Blinks", mood "Auto Detect"), i.e. it covers the three gaps A2F leaves; whether it looks better is exactly what the owner's test should show.


## Part 2D. Cost and design estimate for a production pipeline

Legend: **M** = measured in this lab (g5.xlarge, A10G, $1.067/h in eu-north-1), **E** = my estimate (not measured), **U** = unverified assumption.

### GPU seconds and dollars per presenter minute (1 presenter minute = 60 s of narration = 1,800 frames at 30 fps)

| Step | Route A: Audio2Face-3D + Blender | Route B: MetaHuman Animator + Unreal |
|---|---|---|
| Face animation from audio | **M** 1.4 s (network only) to 11 s (with CPU blendshape solve) = $0.0004 to $0.003. Cold start of the engine 6 to 41 s (**M**), TensorRT engine built once (147 s, **M**). | **E/U** audio solve 1 to 3 min per clip in the editor (Epic gives no number; the 5.6 forum thread reports a ~20 s freeze); whether it can run headless: **U** |
| Render | **M, Blender Cycles OptiX, 1080p, 24 samples + OptiX denoise: about 2 s wall per frame per job with two jobs in parallel on 4 vCPUs (about 1 s of machine per frame)**, so about 1,800 s of machine per presenter minute = **about $0.53**. This is the number that kills Cycles for production. | **E/U** Movie Render Queue, 1080p, real-time-quality scalability, 0.1 to 1.5 s per frame = 3 to 45 min = **$0.05 to $0.80**; plus 1 to 3 min per job to start the editor and load shaders (**U**) |
| Faster render option | **E** a rasterised engine (Blender EEVEE, or three.js in headless Chrome) at 0.03 to 0.15 s per frame = 1 to 4.5 min = **$0.02 to $0.08**; quality drops (no subsurface, simpler hair) | **E** UE with Lumen off, Epic scalability, 540p picture-in-picture: roughly a quarter of the pixels |
| Total per presenter minute | **$0.53 (Cycles, M)** or **about $0.03 to $0.09 (rasterised, E)** | **about $0.10 to $0.85 (E/U)** |
| Reference | MuseTalk lip-sync estimate in docs/AVATARS.md: $0.02 to $0.04 per presenter minute (an estimate there too) | |

Ways to cut render cost whatever the route: render the presenter at its on-screen size (picture-in-picture 540p is a quarter of the pixels), 24 fps instead of 30, render only the beats where the presenter speaks, render in parallel across several spot-free on-demand instances (the quota allows one instance in the QA account; production quota is a separate topic), and cache nothing across videos (each narration is different).

### Engineering effort (days, **E**)

| Task | Route A | Route B |
|---|---|---|
| Animation service (audio in, curves out), containerised | 3 (driver exists; build recipe above; queue, retries, TensorRT engine baked in the image) | 4 to 8 (editor automation or commandlet for the audio solve, **U** feasibility on Linux) |
| Head asset(s) with eyes, teeth, hair, skin, ARKit 52 | 5 to 10 (commission or license heads; Blender shaders for eyes/skin/hair; eye and teeth rigging) | 1 to 2 (presets) |
| Render service (headless, queue, GPU scheduling) | 3 to 4 | 4 to 6 (Unreal Linux image, MRQ command line, shader cache, cold start) |
| Blinks, head motion, mood per scene | 2 (procedural blinks and head sway; mood from the planner) | 0.5 (solve options) |
| Compositing in a scene, transparent layer, tests | 2 | 2 |
| **Total** | **about 13 to 21 days** | **about 11 to 19 days** |

### Risks
* **A:** the head asset is the whole product (no licensed production head is in hand); the NVIDIA heads are not usable for a brand presenter (likeness unknown; no faces in the model files); output has no blinks, head motion or audio-driven brows (we add them, so it will look less "alive" than a captured performance); Cycles cost; NVIDIA's licence is revocable and can be updated.
* **B:** Epic legal ambiguity for a hosted multi-tenant service (Part 1A open questions); Unreal on Linux headless needs the owner's Epic login and a heavy image; MetaHuman Animator audio solve on a server is **U**; presets are not exclusive; Epic's Linux known issue (memory exhaustion when assembling); real cost not measured.
* **Both:** "AI-generated" labelling duties as in docs/AVATARS.md; a presenter that looks almost-but-not-quite human can be worse than a stylised one (uncanny valley), which is why the owner's own eyes must judge the MetaHuman test before anything is built.

### Presenter library and compositing
* **Library:** 4 to 8 fixed named presenters (for route B: unmodified MetaHuman presets with a fixed outfit and camera; for route A: commissioned heads), each with a fixed camera, lens and light so a presenter looks the same in every video. Per presenter store: the assembled asset, a camera/light preset, and a 3 s idle loop (blinks plus sway) used for silent stretches.
* **Per video:** narration beat audio (already produced per beat) goes to the animation service, then the render service, which returns a clip with **alpha** (Blender: transparent film; Unreal: render with alpha enabled; both give PNG sequences) encoded as VP9 WebM with alpha (plays in Chrome, the engine's renderer) or ProRes 4444; fallback is a chroma green background (#00B140) plus keying, which loses hair detail and spills green into the skin. The scene renderer then places the presenter as one more layer (full-height cut-out, picture-in-picture or corner), exactly as docs/AVATARS.md describes for the MuseTalk video.
* Lip-sync is per narration, the idle loop is per presenter; both are labelled as AI-generated in the video metadata.

### Recommendation

1. **Do not build anything yet. Run the owner's MetaHuman test (Part 2C, 1 to 3 hours) and send Epic the email (Part 1A).** The MetaHuman route has the complete character (eyes, teeth, hair, skin, blinks, head motion and mood in one solve), the licence costs nothing below $1M and at most seats above it, and rendering inside Unreal keeps us inside the two readings of the "UE-Only" rule. It is the only route where the quality question can be answered in an afternoon without engineering.
2. **If the MetaHuman clips look good to the owner: build route B first**, with the decision criteria below. Route A's animation half is excellent value (about 1 to 10 s of GPU per minute, MIT code, open model, no account), so keep it as the licence-clean plan B and for a possible hybrid (NVIDIA publishes a UE5 plugin, MIT, v2.5 for UE 5.5/5.6 with a MetaHuman sample, to drive a MetaHuman from Audio2Face; **not tested**), but its render and head problems are the larger part of the work.
3. **Decision criteria (all must hold to start route B):** (a) the owner judges the 1080p MetaHuman clips natural enough to charge credits for (blinks, eyes, brows, Spanish lip closure); (b) Epic's written answer confirms that rendered video from a hosted service owes no royalty and that headless workers do not need seats below $1M (or states the price); (c) a prototype render on a lab GPU is under about $0.15 per presenter minute at presenter size (needs the owner's Epic login to build the Linux image); (d) the audio solve can run unattended on Linux; (e) at least four distinct presets look different enough to be a library. If (b) fails: route A with a commissioned head. If (a) fails for both: keep the MuseTalk idle-video route and spend on a better idle loop (the dead face was its weakness; adding procedural blinks and gaze to the idle video is far cheaper than any 3D route).
4. Whatever is chosen, the A2F finding stands: blinks and head motion are never given by A2F; they are ours to synthesise, and brow expression must come from an explicit emotion per scene.


---

## Spend, state and what is open

* **GPU spend:** one session only (of the two allowed), a g5.xlarge (A10G) in eu-north-1. Worst case printed before starting: **$2.35** (120 min + 10 min grace, 150 GB disk). It ran 70 minutes and was terminated with `gpu_lab.py down`: about **$1.3** (status line: "about $1.24 so far" at minute 69, plus a few cents of disk). g6.xlarge had no capacity in any zone; g5.xlarge started on the second zone. The second session was not needed.
* **Left running:** nothing (`gpu_lab.py status` printed "no lab instance exists"; an EC2 describe in eu-north-1 showed the instance in `shutting-down`, then no pending/running/stopping/stopped instances).
* **S3 artefacts** (QA bucket, prefix `lab/avatars/`): `out/a2f_head_en.mp4`, `out/a2f_head_es.mp4`, `out/a2f/`, `out/a2f2/` (animation CSVs: `*_bs.csv` 52 skin + 16 tongue weights per frame at 60 fps, `*_eyes.csv` 6 values, `*_jaw.csv` 4x4 matrix), `out/test*` (render tests), `in/` (scripts and inputs).
* **Not verified:** Epic's reading of hosted rendering and seats for servers; Epic's current text on the stale metahuman.com FAQ; Trustworthy AI terms of NVIDIA; NIM terms; Blender statements read directly; Windows GPU price; MetaHuman preset names; every step of Part 2C (I could not run it); Unreal on Linux headless; EEVEE and three.js render speed; lip-sync accuracy as a number; the second-order claim that Claire/James/Mark are scans of real people (unknown).
* **Owner actions:** (1) run Part 2C and watch the two Spanish/English clips; (2) send the Epic email via the form and, if you use Unreal, accept the Unreal Engine EULA (and update 22) on your own Epic account; (3) optional, to get emotion from audio: accept the gated licence on https://huggingface.co/nvidia/Audio2Emotion-v2.2 (Hugging Face login, "Agree and access repository"), create a read token and save it where you decide for the lab (I did not need it: emotions were set by hand); (4) decide on a licensed head if route A continues (commission or license); (5) for any Unreal Linux work: your Epic login is needed to obtain the Linux build.
