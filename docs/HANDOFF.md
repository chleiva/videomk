# Handoff: continue this work in a local session

Read this first, then `README.md`, `docs/PRODUCER.md`, `docs/ENGINE.md`, `docs/DEPLOY.md`, `docs/mobile/{SPEC,PRICING,DESIGN_BRIEF}.md`. Branch: `ccr-3c41ecff-680028`.

## What the product is
videomk: AI explainer-video generator. A **Producer** agent turns a brief (+ optional uploaded photos) into a video: story, AI narration, and a visual track (open-license library photos picked by an LLM reviewer, user photos, AI-directed whiteboard sketches, maps, charts, scene cards). Serverless only (Lambda + Step Functions + S3 + DynamoDB + Cognito + API Gateway), zero idle cost, no Fargate. Native apps planned (Swift/SwiftUI, Kotlin/Compose); no analytics vendors (own CloudWatch telemetry); credits only through App Store / Google Play.

## Decisions made (do not re-litigate)
- No generated images in the base product (premium-only later). No own-voice narration; narration is always AI. Dictating the brief is fine. Clips: highlight reel only, deferred; photos first.
- Uploaded photos: cheap small-vision-model risk review in batches (also captions), flag `/videomk/flags/photo_review` = on|log_only|off. Not a legal safeguard.
- Sketches: LLM writes a compact drawing program (icon composition + simple stroke paths + labels), renderer animates it. Spike not started.
- Pricing (superseded by `docs/CREDITS.md`: 1 credit per started minute, 5 welcome + 2 daily expiring free credits): earlier 5 credits per started minute; packs 100/220/2400 credits for $9.99/$19.99/$199.99; free = 3 videos on day one then 1 per day. Target 7x margin: worst-pack margin with Producer density and uploads says 7 credits/min (current bonuses) or 6 with smaller bonuses. **User has not chosen yet.** `backend/scripts/pricing_model.py` and `docs/mobile/PRICING.md` still need updating.
- Upload limits proposed: free 5 photos per video; paid 4 photos per minute, max 60 per video.

## AWS
- `qa` profile: account 552357225438, eu-west-1 (use for all testing). `default` profile: 464863885161, us-west-2 = production, go-live later. The old account 593549830025 is removed and must never be used.
- Stages in `backend/stages.json`; deploy with `backend/scripts/deploy.sh qa`. Nothing has been deployed or bootstrapped yet. Never put keys in chat or git: SSM SecureString `/videomk/unsplash_access_key` (and `/videomk/gemini_api_key` / `/videomk/openai_api_key` only if those TTS providers are chosen; the default, Polly, needs none). Enable Bedrock Claude model access in eu-west-1.

## Next steps, in order
1. Deploy QA (`docs/DEPLOY.md`), fix permission errors, run the selftest Lambda, then a real end-to-end video with the mock then real TTS.
2. Verify live: Bedrock calls, Gemini TTS, Unsplash (needs production app approval for scale), Openverse, presigned URLs.
3. Pricing: lock 6 or 7 credits/min, update `pricing_model.py` + tests + PRICING.md.
4. Producer engine: multiple visuals per beat, word-accurate alignment, photo upload + risk review, sketch spike, maps, conversational editing.
5. Design gaps: iPad, Live Activity, widgets, empty/offline/error states, large text. The design board source lives in the cloud session scratchpad only; re-export from the published artifact if needed.
6. Mobile apps (iOS needs Xcode, so it can only be built locally).

## Waiting on the owner (remind them)
- **Apple DeviceCheck key** (Apple developer account, team 39ANXJNUTL) for the abuse controls: one welcome grant per device, App Attest. To go in `.env`.
- Separate **Tavily key** for videomk (it shares Plorer's key today), later.
- Open decisions: in-app purchase products in App Store Connect, Exa as a second search provider, compressing narration audio.
