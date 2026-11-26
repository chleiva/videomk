# Presenters (talking avatars): design and prototype plan (2026-11-26)

Owner direction: presenters like Pictory's, **self-hosted with open models** (no per-minute API fee), faces **generated** (no actors to license), strict cost guardrails, everything commercially reusable with no royalty.

## Pipeline
1. **Once per presenter, offline**: generate a face (image model), check it against real faces (accidental likeness), make a short natural idle video of it (blink, slight head motion). The library of named presenters is fixed, so a presenter looks the same in every video.
2. **Per video**: the narration audio we already produce per beat drives a lip-sync model over the idle video; the result is one more layer of a scene (intro, outro, picture-in-picture), composited by the renderer. Rendered in parallel with the other scenes.
3. Presenter videos are labelled as AI-generated (YouTube/TikTok rules, EU transparency rules). A presenter is a paid extra in credits, like 4K.

## Models (licences read from the official repositories on 2026-11-26; dependencies still to be checked before launch)
| Model | Licence | Role |
|---|---|---|
| **MuseTalk** (TMElyralab) | MIT code; README: trained model usable "for any purpose, even commercially" | First choice for the per-video step: fast (near real time), redraws the mouth region. Dependencies to check: whisper, sd-vae-ft-mse, DWPose, S3FD. |
| **InfiniteTalk** (MeiGen-AI) | Apache 2.0 code and models | Quality comparison and candidate for making the idle videos (image to talking/moving video); heavy and slow. |
| LatentSync (ByteDance) | Apache 2.0 code; weights reported under OpenRAIL++; uses InsightFace (non-commercial models) | Not first: licence doubts. |
| LivePortrait | no standard licence detected; InsightFace dependency | Not first. |
| **SadTalker** | Apache 2.0 code BUT needs the Basel Face Model (non-commercial research licence); no release since June 2024 | **Ruled out** for commercial use (the owner's 2025 experiment in ~/code/animations used it). |
| Wav2Lip | non-commercial | Ruled out. |

## Cost estimates (to be replaced by measurements)
GPU $0.56 to $2.67 per hour depending on the instance (table below). Fast model: $0.02 to $0.04 per presenter minute; slow model: $0.17 to $0.50. A cold start adds 3 to 5 minutes. Production shape: a queue that scales to zero (no fixed monthly cost) until volume justifies a warm machine (about $730 to $1,000 a month).

## GPU lab guardrails (`backend/scripts/gpu_lab.py`; the only way a GPU machine is started)
Each one works without the others:
1. **Account quota**: 8 G-family vCPUs on QA in eu-north-1 (requested 2026-11-26) = at most ONE single-GPU instance can exist. No spot, no P instances (quota 0).
2. **The script refuses** a second instance, any type outside its list, and any session over 240 minutes (default 120). It prints the worst-case cost before starting ($1.89 for 2 h on g6.xlarge, $4.32 on g6e.xlarge, disk included).
3. **Deadline inside the machine**: the first line of its start-up script schedules shutdown at the deadline, and shutdown means TERMINATE (not stop), so nothing keeps billing.
4. **Idle watchdog inside the machine**: GPU idle for 25 minutes = shutdown.
5. **Backstop outside the machine**: a one-time EventBridge Scheduler rule terminates the instance 10 minutes after the deadline; if the rule cannot be created the instance is terminated at once. Its role may terminate only instances tagged `project=videomk-gpu-lab`.
6. **Sweep**: `gpu_lab.py sweep` terminates anything past its deadline (also run by `up`); `down` terminates now; `status` shows age, time left, cost so far and whether the backstop exists.
7. **Nothing lingers**: encrypted 150 GB disk deleted on termination, no public port (SSM only, a security group with no inbound rule), no Elastic IP, IMDSv2 only; the instance role can read and write only `s3://videomk-qa-…/lab/avatars/`.
QA account and eu-north-1 only (the script refuses any other account).

## Which GPU instance (prices read from the AWS price list, 2026-11-26)
eu-west-1 (where QA lives) only offers g4dn (2019) and g5 (2022), so the lab runs in **eu-north-1 (Stockholm)**: every current family, and the lowest European prices (15-20% under Frankfurt; us-east-1 is about 6% cheaper still). A first quota request in eu-west-1 was made by mistake and is not needed.
| Instance | GPU | GPU memory | $/hour (Stockholm) | Use |
|---|---|---|---|---|
| g4dn.xlarge | T4 (2019) | 16 GB | 0.558 | cheapest hour, slowest |
| **g6.xlarge** | L4 (2024) | 24 GB | 0.854 | default for a light model (MuseTalk) |
| g6.2xlarge | L4 | 24 GB | 1.037 | same GPU, more CPU for video encode/decode |
| g5.xlarge | A10G (2022) | 24 GB | 1.067 | faster than L4, older |
| **g6e.xlarge** | L40S (2024) | 48 GB | 1.974 | heavy models (InfiniteTalk) that need the memory |
| g7.2xlarge | RTX PRO 4500 Blackwell (newest) | 32 GB | 2.673 | to be measured |
What matters is **cost per presenter minute = price per hour x GPU seconds per video second**, not the hourly price: a GPU at twice the price that is three times faster is cheaper. That is unknown until measured, so the prototype measures MuseTalk on g6.xlarge and g4dn.xlarge and InfiniteTalk on g6e.xlarge (and g7 if the others leave a doubt), and the table gets a measured column.

## Prototype (next)
In short sessions on the instances above: MuseTalk and InfiniteTalk, with real videomk narration (one English, one Spanish clip, about 13 s each) and a test presenter image; outputs: side-by-side clips, seconds of GPU per second of video, peak GPU memory, cost per presenter minute. Then the owner judges the quality before anything is built into the product.
