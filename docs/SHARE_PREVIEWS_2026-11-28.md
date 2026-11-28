# Share previews (R170), 28 Nov 2026

Owner's problem (27 Nov): a video shared on LinkedIn or WhatsApp shows a white or odd preview. Cause, from the code: the first frame of our videos is often blank (a whiteboard starts empty, a character scene starts on a bare backdrop), and a watch link had no server-side tags (the web watch page is drawn by JavaScript, which link crawlers do not run). Branch `share-previews`; nothing is deployed.

## Design

A link preview is made by a crawler that fetches the URL, reads `og:*` / `twitter:*` tags from the HTML as delivered (no JavaScript) and fetches `og:image`. So a share needs three things: a public page with the tags, a good 1.91:1 picture, and a way for the owner to switch it on and off.

* **Cover.** `backend/lambdas/engine/cover.py` designs one picture per video from the plan: the first scene in its settled state (the board with its first drawings, the presenter and title panel, the first photo), the title in large type, the VideoMK mark. Two JPEGs: `og` 1200x630 (under 280 KB, WhatsApp drops images above about 300 KB) and `own` (the video's own shape, long side at most 1280). For 9:16 and 1:1 the og card puts the art beside a title panel instead of cropping a stripe. The title sits inside the middle of the picture so a 1:1 or 4:5 crop keeps it. The first chunk of the render makes them, finalize copies them next to the MP4 and stores `cover_uri` / `cover_og_uri`; list_videos returns `cover_url` (presigned) and the web player uses it as poster. The WIP also lets the renderer hold the cover over the first frames of the MP4 (`cover.in_frame`, off unless the timeline asks); that part is not exercised here.
* **Share page.** `backend/lambdas/share/share_page.py`: a static HTML page with title, description (first paragraph of the video's description, links and chapters dropped), `og:image` (1200x630 with width/height/alt), `twitter:card=summary_large_image`, canonical URL, `og:locale`, a plain `<video controls poster>` and the "Made with VideoMK" link. No JavaScript. No `og:video` by default (none of WhatsApp, LinkedIn, iMessage, X, Slack plays it inline from a page tag, and a video tag can make some drop the image); `video_tags=True` exists for later.
* **Backend.** `backend/share_stack.py`, a separate stack (`videomk-<stage>-share`, about 30 resources, nothing added to the main stack, no cross-stack reference): private S3 bucket of copies `<token>/{index.html, og.jpg, poster.jpg, video.mp4}`, CloudFront in front (OAC, HTTPS only, GET/HEAD, CSP, `X-Robots-Tag: noindex`, a CloudFront Function maps `/<token>` to its index.html), and one Lambda behind an HTTP API with a JWT authorizer on the same Cognito pool: `POST|GET|DELETE /users/{user_id}/videos/{video_id}/share` (`lambdas/share/share_api.py`). The page is rendered once at share time, so a crawler never waits on a function.
* **Apps.** Web: the watch page More menu gets "Share link with preview" (creates, then the browser share sheet or copy) and "Stop sharing the link" when shared (`frontend/src/lib/share.ts`, `WatchPage.tsx`, strings en/es). Hidden unless `PUBLIC_SHARE_API_BASE` is set at build time. The existing Share button (the MP4 file) is untouched.

## Privacy rules and how each is met

* Opt-in per video: nothing is public until the owner calls POST for that video.
* Revocable: DELETE removes all four objects, clears the record and invalidates the CDN path. Sharing again makes a NEW token, the old address stays dead.
* Unguessable: 128 random bits, 22 URL-safe characters (`secrets.token_urlsafe(16)`); the bucket cannot be listed.
* Nothing personal on the page: no user id, email or video id; title and description are escaped (tested with script/HTML injection); the page sets `no-referrer`.
* No indexing: `<meta robots noindex>` and the `X-Robots-Tag` header. "Listed" sharing is a later, separate choice.
* Owner only: JWT sub must equal the path user and own the record; another person's video answers 404. Only files inside `videos/<user>/<video>/` of the assets bucket are copied, so a tampered record cannot expose anything else.
* The shared video is a copy, so the private bucket and its signed links are never exposed.

## Tests

`backend/tests/test_share.py` (17 cases): page tags and escaping, no-cover fallback, token validity, blurb, create/idempotent/revoke/re-share on fake S3 and DynamoDB (moto), owner-only and foreign-object refusal, videos without covers, the cover shapes and byte limits for four aspects, the stack's shape (bucket blocked, CloudFront https, every route JWT, IAM scoped), the CloudFront Function run through node. `frontend/src/lib/share.test.ts`. Existing `tests/test_engine.py` still passes.

## What is built and what is not

Built: cover design, share page, share API and stack, web UI, tests, this document.

Not built or not verified:
* iOS (`ShareLink`) and Android (`ACTION_SEND` of the URL) still share the MP4 file. Needed: a client call to the share API (address from config or `capabilities`), then share the returned URL, plus a Stop sharing item. Not done: no compile or simulator run was possible here.
* Real crawlers (WhatsApp, LinkedIn Post Inspector, iMessage, X card validator, Slack, Facebook debugger) have not been run against a deployed page. WhatsApp's 300 KB image limit and LinkedIn's cache (it keeps a preview for days; use Post Inspector after a change) are from public documentation, not tested.
* Revocation on video delete and on account deletion is wired (2026-11-28, branch `weekly-and-deletion`): `DELETE .../videos/{id}` (launcher) and the account deleter's `videos` step call `common/share_revoke.revoke_item(row, strict=True)` BEFORE the row (which holds `share_token`) goes: the four files under `<token>/` are deleted and `/<token>` and `/<token>/*` invalidated. Strict means a failure is not swallowed: video delete answers 503 `share_revoke_failed` and keeps the video (repeat the DELETE); the account step is retried with the existing backoff, then `stuck` + alarm / SQS dead-letter. Repeating is safe (deleting absent keys is not an error). It only works where the main stack is given the share stack's names: `cdk deploy videomk-<stage> ... -c shareBucket=<ShareBucketName output> -c shareDistributionId=<ShareDistributionId output>` (deploy the share stack first, then the main stack with both flags; one without the other is refused; absent = no variable, no permission, nothing called). Rights added: `s3:DeleteObject` on that bucket's objects and `cloudfront:CreateInvalidation` on that one distribution, for the launcher and the account worker only. Limit: a shared copy whose video row is already gone cannot be found (the token lives on the row); the share bucket has no per-user index.
* Custom host (`share.videomk.com`): supported by `-c shareHost -c shareCertArn` (ACM certificate in us-east-1) but the DNS alias is manual. Without it the link is a `*.cloudfront.net` address, which looks less trustworthy in chats.
* Per-share cost: a copy of the MP4 in S3 plus egress through CloudFront; no lifecycle expiry yet (add one, or an owner-visible list of active shares).
* The cover pipeline (first chunk, finalize copy, list_videos) is covered by unit tests of the design only, not by a full render; the older videos have no cover until a backfill script is run (not written). `og:video` and the in-frame MP4 cover are off.
* No "Made with VideoMK" analytics or visitor count.

## Deploying (after the owner reads this)

1. Main stack: deploy the engine and list_videos changes (covers). Normal deploy.
2. Share stack, per stage, from `backend/`:
   `cdk deploy videomk-<stage>-share -c stage=<stage> -c share=1 -c sharePoolId=<UserPoolId output> -c shareClientIds=<app client ids> -c shareVideosTable=<videos table name>` (add `-c shareHost=... -c shareCertArn=...` for a custom host). Note the `ShareApiUrl` output.
3. Web: build with `PUBLIC_SHARE_API_BASE=<ShareApiUrl>` and deploy with `backend/scripts/site.sh app` (prod account). Without the variable the menu items do not appear.
4. Check one share by hand: open the URL, run the platform debuggers, then Stop sharing and confirm 403/404.
