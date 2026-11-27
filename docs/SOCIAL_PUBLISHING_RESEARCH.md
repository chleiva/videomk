# Social publishing from videomk: research and recommendation (2026-11-27)

Read-only research. No accounts created, nothing posted, nothing bought.
Tags: **VERIFIED** = primary page read on 2026-11-27 (platform docs, price page, policy). **SECONDARY** = vendor blog, forum, press or search summary. **UNVERIFIED** = not confirmed (general knowledge or inference; check before relying). **ESTIMATE** = my effort or cost guess, not a sourced fact.
Method note: Google, TikTok, LinkedIn, X and Ayrshare pages were fetched and read as text; Meta pages via Meta's own `.md` doc endpoints. Apple developer docs could not be read (JS-rendered).

## 1. Headline findings

1. **YouTube changed in the last month and is now the easiest platform.** On 2026-11-02 Google reversed the 2020 rule: videos uploaded from unverified API projects are no longer forced private; privacy defaults to public (VERIFIED: YouTube Data API revision history, "November 2, 2026"; same text on the Quota and Compliance Audits guide and videos.insert page, last updated 2026-11-23). No audit is needed to upload public or unlisted within the default quota.
2. **But the default YouTube cap is 100 `videos.insert` calls per day for the whole Cloud project** (VERIFIED: videos.insert page, "100 calls per day... 1 unit in the Video Uploads quota bucket"; granular buckets introduced 2026-06-01). Upload cost fell from ~1600 units to ~100 on 2025-12-04 (VERIFIED, revision history), then moved to its own bucket. Raising it needs an API Compliance Audit plus the Quota Extension Form (VERIFIED).
3. **TikTok is the slow one.** Direct Post by an unaudited client is private-only (SELF_ONLY), max 5 posting users per 24 h, and every posting account must itself be private at post time (VERIFIED: Content Sharing Guidelines, updated 2026-08-04). Public posting needs a separate audit; TikTok publishes no timeline (SECONDARY: "weeks, variable").
4. **Instagram needs a professional (Business/Creator) account on the user side and Meta Advanced Access on ours**, which requires App Review **and** Business Verification (VERIFIED: Instagram Platform overview and App Review docs). Personal Instagram accounts cannot be published to via API (VERIFIED: "Instagram professional account" requirement).
5. **No platform-owned MCP server exists for organic posting** except possibly X (SECONDARY, Blotato survey 2026-10-12, vendor-authored). MCP is the wrong layer for this backend feature (section 5).
6. **Sign in with Google does not give us YouTube posting.** Our consent screen currently asks only `openid email profile` (non-sensitive; `docs/AUTH_SOCIAL.md`). Posting needs a new, separate sensitive scope and an offline refresh token, which means a dedicated "Connect YouTube" flow (section 6).

## 2. Decision table per platform (direct official API)

| | YouTube | TikTok | Instagram Reels | LinkedIn | X | Facebook Page Reels | Threads |
|---|---|---|---|---|---|---|---|
| **User needs** | Google account with channel | TikTok account | Business or Creator account (VERIFIED) | LinkedIn member (page posting needs page admin role) | X account | Page admin (`pages_manage_posts`) | Threads account |
| **Our scope(s)** | `youtube.upload` (VERIFIED: listed in videos.insert; scope list "Manage your YouTube videos") | `video.publish` (Direct Post) or `video.upload` (inbox draft) (VERIFIED) | `instagram_business_basic` + `instagram_business_content_publish` (Instagram Login), or `instagram_basic` + `instagram_content_publish` (+`pages_read_engagement`) (VERIFIED) | `w_member_social` via "Share on LinkedIn" product (VERIFIED); `w_organization_social` for pages | `tweet.write`, `media.write`?, `offline.access` (tweet.write, offline.access VERIFIED; media.write UNVERIFIED) | `pages_manage_posts` + Facebook Login (VERIFIED) | `threads_content_publish` (VERIFIED) |
| **Approval before real users** | Google sensitive-scope verification, "up to 10 days", needs demo video (VERIFIED). Scope is sensitive: SECONDARY, confirm in Console Data Access page. Unverified app = 100 new-user cap (VERIFIED) | App review "several days to two weeks" (VERIFIED, TikTok FAQ) AND content audit for public posts (VERIFIED needed; duration SECONDARY weeks). Mobile app must be live in App Store/Play, public website with ToS/Privacy (VERIFIED) | Business Verification + App Review for Advanced Access (VERIFIED). No official lead time; forum reports 2 to 8+ weeks (SECONDARY) | "Share on LinkedIn" is added from the Developer Portal Products tab (VERIFIED); lead time UNVERIFIED. Page posting needs Community Management API approval (SECONDARY from access page) | No review documented; pay-per-use credits (VERIFIED) | Advanced Access review (UNVERIFIED for Pages specifically) | Without Advanced Access you can post only for app "Threads testers" (VERIFIED) |
| **Before approval** | Works for 100 users, public/unlisted allowed (VERIFIED) | Private-only, 5 users/24 h, accounts must be private (VERIFIED) | Only users with a role on our app (VERIFIED) | Dev accounts only (UNVERIFIED) | Works immediately | Testers only (UNVERIFIED) | Testers only (VERIFIED) |
| **Quota / limits** | 100 uploads/day per project (VERIFIED) | ~15 posts/day/creator; 6 init requests/min per token; 20 creator_info/min (VERIFIED) | 100 API posts/24 h per account (VERIFIED; page also says 50 for carousels, inconsistent) | Not found (UNVERIFIED) | Pay per call | 30 reels/24 h per Page (VERIFIED) | 250 posts/24 h (VERIFIED) |
| **Cost to us** | $0 | $0 | $0 | $0 | $0.015 per post create; $0.20 if the post text contains a URL (VERIFIED, docs.x.com). Media upload line item not listed (UNVERIFIED) | $0 | $0 |
| **Video limits** | 256 GB, `video/*` (VERIFIED). Title max 100 chars in Shorts UI (VERIFIED) | MP4/MOV/WebM, H.264/H.265/VP8/VP9, 23-60 fps, 360-4096 px per side, up to 4 GB; duration per creator (`max_video_post_duration_sec`; 3, 5 or 10 min); chunks 5-64 MB (VERIFIED) | MP4/MOV, H.264 or HEVC, AAC, 23-60 fps, max 1920 horizontal px, 25 Mbps, 3 s to 15 min, 300 MB, 9:16 recommended, moov atom first, public URL for pull (VERIFIED) | MP4, 3 s to 30 min, 75 KB to 500 MB (VERIFIED, Videos API) | 20 min / 8 GB default; 125 min / 16 GB for Premium (VERIFIED) | 9:16, 3 to 90 s, H.264/H.265 (VERIFIED) | Video URL must be public; limits not read (UNVERIFIED). Text 500 chars (VERIFIED) |
| **Shorts/Reels rules** | Any square or vertical video up to 3 min is auto-classified as a Short (VERIFIED, YouTube Help, since 2024-10-15). No API flag | n/a (one format) | `media_type=REELS` (VERIFIED) | n/a | n/a | Reels endpoint `video_reels` | n/a |
| **Schedule** | Yes: `status.publishAt`, video must be private and never published (VERIFIED) | No scheduling in the API read (UNVERIFIED); we would hold and post ourselves | No native param; app-side scheduling is expected (VERIFIED wording) | UNVERIFIED | We schedule ourselves | Yes: `SCHEDULED`, 10 min to 29 days ahead (VERIFIED) | Not documented; app-side |
| **AI label field** | `status.containsSyntheticMedia` (VERIFIED) | `post_info.is_aigc=true` adds "Creator labeled as AI-generated" (VERIFIED) | `is_ai_generated=true` on the container (VERIFIED) | none found (UNVERIFIED) | none found (UNVERIFIED) | none found (UNVERIFIED) | `is_made_with_ai=true` (VERIFIED) |
| **Token life** | Access 1 h (UNVERIFIED); refresh token valid until revoked, dies after 6 months unused, 7 days if consent screen is in Testing (VERIFIED), max 100 live refresh tokens per account per client (VERIFIED) | Access 2 h, refresh 180 days, refresh rotates every use (VERIFIED, TikTok token mgmt page) | Short-lived 1 h, long-lived 60 days, refreshable (VERIFIED, Instagram overview). Unified Login system-user token expiry is configurable (VERIFIED) | 60 days, no programmatic refresh except limited partners; user re-consents (VERIFIED) | 2 h unless `offline.access`, then refresh token (VERIFIED) | Page tokens (UNVERIFIED) | Long-lived tokens (VERIFIED existence) |
| **Rough build ESTIMATE** | 3 to 4 days on top of foundation | 5 to 7 days + 2 days audit prep | 5 to 7 days + 3 days review prep | 3 days | 2 to 3 days | 3 to 4 days | 2 days (shares Meta app) |

Foundation (once, ESTIMATE 6 to 8 days): `social_connections` table (per user + platform, KMS envelope-encrypted tokens), OAuth start/callback Lambdas, Connect/Disconnect UI on web, iOS and Android, a publish job (SQS or Step Functions) that reads the S3 render and pushes with retries and status polling, revoke-on-disconnect, and deletion hook.

## 3. YouTube details (primary route for phase 1)

- **Auth:** OAuth 2.0 authorization code, `access_type=offline`, scope `https://www.googleapis.com/auth/youtube.upload` (VERIFIED). Embedded webviews are blocked by Google (`disallowed_useragent`, VERIFIED), so mobile must use the system browser or an in-app browser tab that returns to our HTTPS callback.
- **Verification:** sensitive scopes need review before any Google Account can grant access; "can take up to 10 days"; requires scope justification and a demo video; request the narrowest scope and declare it in the Data Access page (VERIFIED). While unverified: "unverified app" screen and 100 new users total (VERIFIED). Because our existing consent screen is already in verification with non-sensitive scopes, adding `youtube.upload` is a scope change that re-triggers review (VERIFIED principle: "account for the time needed to complete verification... for any new features that require a new scope"). UNVERIFIED: whether it can be folded into the in-flight submission; ask via the Verification Center.
- **Compliance audit** is only for raising quota above the default (VERIFIED: "must first complete an audit" for extra quota; submit the "Audit and Quota Extension Form"). No lead time published (UNVERIFIED).
- **Developer Policies obligations (VERIFIED, policy page updated 2026-11-06):**
  - Users must have final control over what is published; do not alter titles/descriptions after submission or append text (API name, dates) without explicit consent. Suggested titles must not be identical defaults for all users.
  - Privacy policy must be prominent, say we use YouTube API Services, link Google's privacy policy and `https://security.google.com/settings/security/permissions`, and explain what we store and share.
  - Easy in-product way to revoke; on revoke we must programmatically revoke the token immediately and delete the user's API data within 7 calendar days. Also delete when the user revokes at Google's page; periodically reconfirm tokens are still valid.
  - If we store YouTube API data (video IDs, stats) for over 30 days we must re-verify authorization and video existence every 30 days.
  - Never collect Google credentials.
- **Google API user-data Limited Use** language applies to data from the scopes the product policy names; whether YouTube scopes are covered is UNVERIFIED, so include Limited Use wording in the privacy policy anyway (cheap).
- **Inauthentic content risk:** YouTube renamed "repetitious content" to "inauthentic content" on 2025-07-15; it covers mass-produced, templated content and is a **monetization** rule (VERIFIED: YouTube Help 1311392, wording; press examples of narrated slideshows are SECONDARY). Our own `docs/ENGINE.md` guardrails already say: no one-click bulk, user can edit script, keep credits.
- **AI disclosure:** YouTube requires disclosure of realistic altered or synthetic content, including "AI generated music" and realistic generated scenes; not required for clearly non-realistic animation, or script/caption/thumbnail assistance (VERIFIED: YouTube Help 14328491). The API field is `status.containsSyntheticMedia`. **Product rule suggestion:** default it ON when a realistic presenter avatar or AI-generated music is in the render, show the toggle to the user, never silently off. Whether our TTS narration alone needs it is a judgment call (voice cloning of one's own voice is listed as not needed; synthetic voice of a non-person is not addressed, UNVERIFIED).
- **Other fields:** `paidProductPlacementDetails.hasPaidProductPlacement` no longer defaults to false (VERIFIED, 2026 revision history): set it explicitly. `selfDeclaredMadeForKids` should be asked of the user.
- **Cost:** $0. **Daily cap risk:** at 100/day total, one popular day exhausts every user. Implement a global counter, per-user daily limit, and a "try tomorrow" message; file the quota extension once usage reaches ~50% of the cap.

## 4. Other platforms: what is hard

**TikTok (VERIFIED unless noted).** Two modes. *Direct Post* (`/v2/post/publish/video/init/`, scope `video.publish`) and *Upload to inbox* (`/v2/post/publish/inbox/video/init/`, scope `video.upload`; the user taps a notification and finishes in TikTok). The private-only restriction is documented for Direct Post; the Upload page I read does not state it (UNVERIFIED whether inbox upload is also gated). Audit conditions and UX rules for Direct Post:
- Must call `creator_info/query` first and show the creator's nickname, available privacy options (dropdown, **no default**), interaction toggles (comment/duet/stitch, none pre-checked), and block posts longer than `max_video_post_duration_sec`.
- Must show a preview, let the user edit caption/hashtags, start sending only after explicit consent, and show the exact declaration text ("By posting, you agree to TikTok's Music Usage Confirmation", Branded Content variants).
- Commercial content toggle off by default with prescribed labels; "Branded content" cannot be private.
- No watermark/logo/promo text added to the video. Poll `publish/status/fetch`; tell users processing takes minutes.
- Intended use: authentic creators posting original content to their own profile; **not** internal/private tools or arbitrary copy from other platforms. App review also says development/test apps are not approved and the iOS/Android app must be live in the stores (VERIFIED).
- Use `PULL_FROM_URL` from our S3/CloudFront only after verifying domain or URL-prefix ownership in the TikTok portal; else `FILE_UPLOAD` in chunks.
- `is_aigc` label available; we should set it from the same product rule as YouTube.
- App review demo: up to 5 videos, 50 MB each, showing every scope end to end (SECONDARY: search summary of TikTok App Review Guidelines).

**Instagram / Meta (VERIFIED unless noted).** Three login variants (Unified Login, Instagram Login, Facebook Login). Instagram Login and Unified Login serve users without a Facebook Page. Flow: create container (`media_type=REELS`, `video_url` public, or resumable upload), poll `status_code` about once a minute up to 5 minutes, `media_publish`; unpublished container expires in 24 h. Standard Access with no review is only for a business you own (VERIFIED), i.e. we cannot serve customers without Advanced Access = App Review + Business Verification. Review needs privacy policy URL, app icon, reviewer login instructions, and a screencast per permission. Reviewer must be able to log in and test the app externally. Reels `is_ai_generated` supported. Instagram has Reels "trial_params" (non-follower trial reels) (VERIFIED). Business verification for Agilegency Ltd will need UK company documents (UNVERIFIED specifics).

**LinkedIn (VERIFIED unless noted).** "Share on LinkedIn" gives `w_member_social`; upload via Videos API then create a post; 3 s to 30 min, 75 KB to 500 MB MP4. Tokens last 60 days; programmatic refresh only for limited partners, so users must reconnect roughly every 60 days (VERIFIED), plan a reminder in the UI. Company pages need the Community Management API (approval program, SECONDARY). LinkedIn marketing API versions sunset on a rolling basis (version 202601 sunsets 2027-01-15, VERIFIED): pin and track versions.

**X (VERIFIED).** Pay-per-use since Feb 2026 (no subscription): $0.015 per post create, $0.20 if URL is in the post, reads $0.005. Media uploaded in chunks via `/2/media/upload/*`; default 20 min / 8 GB, Premium 125 min / 16 GB. OAuth 2.0 PKCE, tokens 2 h, refresh with `offline.access`.

## 5. MCP, aggregators, and native sharing

### B. MCP
- MCP is "an open-source standard for connecting AI applications to external systems" (VERIFIED, modelcontextprotocol.io). It is built for an agent choosing tools at runtime.
- Platform-owned: Blotato's 2026-10-12 survey of 891 social MCP servers found one platform-built server that publishes organic posts (X); Meta and TikTok have ads-only servers; LinkedIn and YouTube none (SECONDARY, vendor-authored and "on the pages we checked"). Buffer's first-party MCP (public beta March 2026) and aggregator MCPs (Upload-Post, Zernio, Postiz, Outstand) wrap their own REST APIs (SECONDARY/VERIFIED existence on vendor pages).
- **Verdict:** inappropriate for the in-app Publish button. Our flow needs deterministic calls, explicit per-post user consent and preview (TikTok and YouTube policies require it), token custody under our control, and idempotency. Putting an LLM tool-call in that path adds risk and no capability. MCP is relevant for a *separate agent feature* ("let Claude/ChatGPT publish for me") and for exposing videomk itself as an MCP server for the user's own agent; both are later and optional.

### C. Aggregators
| Vendor | How users link | Price (VERIFIED from vendor price pages, Nov 2026) | Notes |
|---|---|---|---|
| **Ayrshare** | White-label JWT linking URL per "User Profile"; customers never see Ayrshare (VERIFIED) | Launch $299/mo for 10 profiles, Business $599/mo for 30 profiles then tiers, Premium $149 single profile; profile = one customer with any number of networks | Priced for B2B, expensive per consumer user. X requires our own X OAuth1 keys in headers (VERIFIED in generateJWT docs). DPA exists, last modified 2026-08-24; sub-processors US-based (Google, Mailgun, Cloudflare, Stripe, DigitalOcean); SCCs defined (VERIFIED). UK addendum/IDTA UNVERIFIED |
| **Zernio (formerly Late; getlate.dev 301-redirects)** | "Build a platform": each customer gets a profile, connect accounts via API (VERIFIED docs landing) | 2 accounts free; $6/account/mo for 3-10, $3 for 11-100, $1 for 101+ (VERIFIED), X passthrough at X's rates | Cheapest at scale per linked account, but cost per *linked* account is a variable cost for free users. SOC 2 + GDPR paperwork via trust portal (vendor claim) |
| **Upload-Post** | Linking per profile, MCP, white-label on Professional (VERIFIED vendor page) | Free (10 uploads/mo, no TikTok); $24 for 5 profiles; $50 for 25; $147 for 75; $438 for 225 profiles | Cheapest per profile at scale (~$2); small vendor |
| **Postiz** | Self-host (AGPL-3.0, 42k stars) or cloud $29 to $99/mo for 5 to 100 channels (VERIFIED) | | Built as a team scheduler with API; not a multi-tenant embedded linking product, and self-hosting means we still need our own platform app approvals. Not a fit (inference) |
| **Buffer** | Personal API key per Buffer account; plans from $5 per channel/mo (VERIFIED price page) | | Every end user would need their own Buffer account; not a white-label fit (inference) |
| **Zapier/Make/Hootsuite** | Per-user automation tools | | Not embeddable in our UX (UNVERIFIED, inference) |

- **What an aggregator buys us:** their already-approved platform apps. We skip TikTok audit, Meta Business Verification/App Review, and Google verification for those channels, and ship in days. It does **not** remove the professional-account requirement on Instagram or the user-consent UX duties; whether each vendor's TikTok app is audited (so posts go public) is UNVERIFIED per vendor (bundle.social claims its own is, SECONDARY).
- **What it costs us:** per-linked-account fees; a second processor for tokens and videos (UK GDPR Art. 28 DPA, transfer mechanism, privacy policy update, deletion propagation); vendor lock-in and outage risk; each platform's policies still bind us (the vendor passes through their errors). The aggregator also holds the user's tokens, so account deletion must call the vendor delete-profile API (Ayrshare doc: deleting the profile via API stops billing, VERIFIED).
- **Rule:** wrap whichever one in our own `SocialPublisher` interface so a platform can be moved from aggregator to direct without UI changes.

### D. Native share fallback (zero approvals)
- **Android (VERIFIED):** `ACTION_SEND` with `EXTRA_STREAM` content URI (FileProvider; grant read permission) and `Intent.createChooser`. Instagram documents the same intent into the Feed composer: MP4/MKV, 3 s to 10 min, min 640x640 (VERIFIED). TikTok documents a "Share with TikTok by using Intents" section (VERIFIED title; details not read).
- **iOS (UNVERIFIED, Apple docs unreadable; general knowledge):** `UIActivityViewController` with a file URL; the host app only learns "completed or cancelled", not which app or whether the post happened. Instagram's documented iOS path covers photos via Document Interaction and universal links (VERIFIED); videos go through the normal share sheet (UNVERIFIED).
- **TikTok Share Kit (VERIFIED):** add Share Kit product to a TikTok developer app; iOS needs photo-library access and takes `localIdentifiers`; videos up to 10 min (region dependent); Android `ShareApi` or intents; lets us add a partner hashtag. Whether Share Kit needs app review is UNVERIFIED.
- **Limits:** no status, no URL back, no metadata guarantees, no AI-label field, user finishes in the other app. Good enough as phase 0 and as the permanent fallback for anyone who will not link accounts.

## 6. Sign in with Google reuse and token handling

- Our Google client is public (PKCE), scopes `openid email profile`, federated through Cognito (`docs/AUTH_SOCIAL.md`). A refresh token for `youtube.upload` has to come from an authorization-code flow with `access_type=offline` against **our backend** (Cognito will not be the custodian of that token; whether Cognito can surface Google IdP tokens is UNVERIFIED and we should not depend on it).
- Use a separate **web (confidential) OAuth client** in the same Google Cloud project for "Connect YouTube", incremental authorization, and let the user choose the Google account/channel independent of the one they signed in with (Apple-sign-in users must be able to connect too).
- Publish the consent screen to Production before launch: in Testing status external refresh tokens expire in 7 days (VERIFIED).
- Storage (all platforms): server-side only; encrypt with KMS envelope encryption per user; never logs, never client storage; store `client_secret` in Secrets Manager (TikTok forbids sharing or embedding it, VERIFIED); handle TikTok refresh rotation (replace stored token every refresh, VERIFIED); store Meta tokens with business ID and config ID (VERIFIED guidance); handle `invalid_grant`/disconnected as "Reconnect" state, not retries.
- Account deletion (`docs/ACCOUNT_DELETION.md` flow): on delete or disconnect revoke at Google (revocation required, VERIFIED), TikTok revoke endpoint (VERIFIED existence), delete rows, delete any retained YouTube API data within 7 days (VERIFIED), and call aggregator delete-profile if used.
- Privacy policy and store forms: add social-connection data categories, YouTube API Services wording, Google privacy link and permissions URL, and update Apple and Google Play data-safety forms. A user-data-deletion callback is expected by Meta (UNVERIFIED but typical; confirm in the App Dashboard checklist).

## 7. Recommendation

**Use a hybrid: share sheet first, YouTube direct second, then one aggregator for the slow platforms behind our own interface, and go direct on TikTok/Instagram only if volume justifies the audits.**

| Phase | Scope | Why | Calendar lead time |
|---|---|---|---|
| **0 (week 1)** | "Share" and "Save to device" on web (download), iOS (share sheet), Android (chooser, plus TikTok Share Kit and Instagram intents optional). Prefilled title/description/hashtags, AI-label reminder text. | No approvals, no tokens, no security surface | none |
| **1 (weeks 1 to 4)** | Foundation + **YouTube direct** (also gives Shorts for 9:16 under 3 min, scheduling via `publishAt`). | Cheapest, no audit needed for public upload as of 2026-11-02, we own tokens, matches `ENGINE.md` roadmap item "YouTube upload via the Data API" | Google sensitive-scope verification up to 10 days (VERIFIED); start the day the demo build works |
| **2 (weeks 3 to 6)** | **LinkedIn member posting direct** (self-serve product, 60-day reconnect). Start **TikTok app review + Meta Business Verification** in parallel while building. | LinkedIn is cheap; the other approvals are the long poles, start the clocks early | TikTok review several days to 2 weeks, audit weeks; Meta 2 to 8+ weeks (SECONDARY) |
| **2b (optional, weeks 3 to 5)** | Aggregator adapter (Zernio or Upload-Post first candidates on price; Ayrshare if white-label maturity matters more than cost) for TikTok, Instagram, Facebook, Threads, X | Ships these channels in days instead of months, while direct approvals are pending. Gate behind paid plan or credits | DPA + price negotiation days |
| **3 (after approvals)** | Move TikTok then Instagram to direct if aggregator per-account cost or reliability hurts; add X direct ($0.015/post) and Facebook Reels | Direct is $0 per account | n/a |

Rationale in one line: YouTube direct is cheap and now unblocked; TikTok and Meta approvals are slow and conditional on a live, store-published app and polished consent UX, so use the share sheet and an aggregator to bridge. Avoid MCP in the product path.

## 8. Owner action list (minimum)

1. **Google Cloud:** decide with the existing in-flight verification whether to add `youtube.upload` now or submit a second verification; create the web OAuth client; enable YouTube Data API v3; prepare a demo video of the connect and upload flow; keep consent screen in Production. Ask in the Verification Center if scope can be appended.
2. **Privacy policy / terms:** approve updates (YouTube API Services statement, Google privacy link, permissions revoke link, Limited Use wording, social data categories, aggregator as processor if used).
3. **TikTok for Developers:** create the app under Agilegency Ltd; add Login Kit, Content Posting API (Direct Post), Share Kit; prepare 1 to 5 demo videos (<=50 MB) showing the compliant UX; ensure iOS and Android apps are live in the stores and videomk.com shows ToS and Privacy links without opening a menu; later submit the content audit form with usage estimates.
4. **Meta for Developers:** create the app, start Business Verification for Agilegency Ltd (UK registration documents), prepare reviewer instructions, test credentials, and a screencast per permission.
5. **LinkedIn Developer Portal:** create the app, add "Share on LinkedIn" (and "Sign In with LinkedIn using OpenID Connect" if wanted); for company pages, apply to Community Management API.
6. **X Developer Console:** create the project and buy a small credit balance only when we decide to build X (optional).
7. **Aggregator (if chosen):** sign the DPA; confirm UK transfer mechanism; confirm which of their platform apps are audited (TikTok, Meta); confirm per-profile pricing at expected user count.
8. **Apple and Google Play:** update privacy nutrition label and Data safety form once connections ship.

## 9. Risks

- **YouTube 100 uploads/day shared across all users** (VERIFIED). Mitigate with counters, per-user limits, early quota extension.
- **Policy drift:** YouTube reversed its private-lock policy in Nov 2026; TikTok, Meta and LinkedIn docs changed within weeks (TikTok pages updated Aug and Nov 2026). Re-check docs before building each phase.
- **TikTok audit failure** is common when UX rules (no default privacy, consent text, creator_info) are missed (SECONDARY). Build the UI exactly per the Content Sharing Guidelines.
- **Instagram personal accounts** cannot publish via API; many of our users will fall back to the share sheet. Detect and explain.
- **Meta verification limbo** (forum reports of months, SECONDARY). Do not block the roadmap on it.
- **Aggregator cost model** (per connected account) can turn free users into a cost line; gate publishing behind paid plans or credits.
- **Low-originality and AI-content policies** (YouTube inauthentic content, labeling duties on all platforms): keep the user-edit step, no bulk publish, default labels on for realistic synthetic content.
- **Token expiry:** LinkedIn every 60 days, Google 6 months unused, Instagram 60 days; build "Reconnect" UX and expiry reminders.
- **4K masters:** several platforms cap resolution or size (Instagram 1920 px / 300 MB, FB Reels 9:16 up to 90 s, TikTok 4096 px). Publish a 1080p social rendition, not the 4K master.
- **UK GDPR:** Agilegency is controller; tokens and video content to an aggregator is a new transfer. Needs DPA and transfer mechanism before launch of that route.

## 10. Source list (primary pages read 2026-11-27)

- YouTube Data API: `developers.google.com/youtube/v3/docs/videos/insert`, `/docs/videos`, `/revision_history`, `/guides/quota_and_compliance_audits`, `/guides/uploading_a_video`, `/determine_quota_cost`; YouTube API Services Developer Policies `/terms/developer-policies`; YouTube Help 14328491 (altered/synthetic), 15424877 (3-minute Shorts), 1311392 (monetization policies).
- Google identity: `/identity/protocols/oauth2` (token expiry), `/oauth2/scopes`, `/oauth2/production-readiness/sensitive-scope-verification`, `/oauth2/web-server`, Cloud Help 7454865 (unverified apps).
- TikTok: `developers.tiktok.com/doc/` content-posting-api-get-started, content-sharing-guidelines, content-posting-api-reference-direct-post, -upload-video, -query-creator-info, -media-transfer-guide, oauth-user-access-token-management, app-review-guidelines, getting-started-faq, share-kit-ios-quickstart-v2, share-kit-android-quickstart-v2.
- Meta: `developers.facebook.com/documentation/instagram-platform/` content-publishing, instagram-graph-api/reference/ig-user/media, app-review, overview, sharing-to-feed, instagram-api-with-unified-login/authentication; threads/posts, threads/overview; video-api/guides/reels-publishing; development/release/business-verification.
- LinkedIn: learn.microsoft.com/en-us/linkedin/ (Share on LinkedIn, Videos API, Posts API, authorization code flow, increasing access, community management overview).
- X: docs.x.com pricing, media upload, OAuth 2.0 authorization code.
- MCP: modelcontextprotocol.io intro.
- Aggregators: ayrshare.com/pricing, docs (generateJWT, business plan), data-processing-agreement; zernio.com/pricing and docs; upload-post.com/pricing; postiz.com/pricing and GitHub; buffer.com/pricing and developers.buffer.com.
- SECONDARY: bundle.social blog (TikTok API approval, Meta app review), Blotato MCP survey (2026-10-12), Meta community forum threads, search-engine summaries.
