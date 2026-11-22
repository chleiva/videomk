# videomk

Turn an idea into a narrated, animated explainer video: structured scenes (diagrams, charts, timelines, stats, quotes,
licensed photos picked by a vision model), captions, music, SFX, and an editor to review and change any part of it.
Serverless-only: Lambda + Step Functions + S3, zero cost at idle.

```
frontend/   Astro + React + Tailwind (Cognito Hosted UI, PKCE)
backend/    AWS CDK (Python)
  lambdas/
    sf_launcher.py, list_videos.py, get_video.py     API handlers (auth, quota, validation)
    generate_video/                                   v1 pipeline (generated stills + MoviePy)
    engine/                                           v2 engine: scenes, renderer, TTS, plan, handlers
    common/                                           identity, http, secrets (SSM first), usage quota
  layers/build_layer.sh                               builds Lambda layers for linux/x86_64 (no Docker)
  scripts/local_render.py                             render a timeline locally with the same code as the Lambdas
  tests/                                              53 tests (moto), incl. an end-to-end run of every handler
docs/ENGINE.md                                        architecture, evidence, cost model, deploy runbook, what's unverified
```

```bash
# tests (62 backend; `-m 'not slow'` skips the ~2 min of real-video end-to-end runs)
cd backend && pip install -r requirements-dev.txt && pytest

# render the demo timeline locally (chunked, parallel, with audio)
python scripts/local_render.py tests/fixtures/demo_timeline.json /tmp/demo.mp4

# frontend
cd frontend && npm ci && npm run build && npm test
```

Read `docs/ENGINE.md` before deploying: it has the runbook, the breaking changes from the hardening pass, and an explicit
list of what has and hasn't been verified.
