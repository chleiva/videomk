# Legal drafts: notes for the owner (2026-11-26)

Files: `frontend/src/pages/privacy.astro`, `terms.astro`, `delete-account.astro`, `support.astro`, `frontend/src/data/legal.ts` (identity, dates, law, age), `frontend/src/components/LegalDoc.astro` (now also renders tables and the optional address chips), `BaseLayout.astro` (footer now links Delete account), `ConsentToast.tsx` (see mismatch 7). Research: `docs/LEGAL_RESEARCH.md`. These are practical, plain-language drafts, not legal advice. A lawyer review is advisable but is not a gate for publishing.

## 1. Blanks to fill (all in `frontend/src/data/legal.ts`; nothing is invented)
| Item | Today | Proposed default |
|---|---|---|
| Company name, contact email | `Agilegency Ltd`, `hello@videomk.com` (already in the file) | keep; consider a `privacy@videomk.com` alias later |
| Registered address, company number | empty (`COMPANY_ADDRESS`, `COMPANY_NUMBER`); pages show them only when filled | fill with the registered office and Companies House number: UK law expects a company website to show them, and Apple/Google may ask |
| Governing law | `England and Wales` (it was in the old terms) | keep if the company is English; change the constant otherwise |
| Regulator named | ICO or local authority (`REGULATOR`) | keep; if you serve many EU users, consider naming an EU representative (UK GDPR/EU GDPR Art. 27) |
| Minimum age | 13, or the higher local age (`MIN_AGE`) | **Owner decided 16 on 2026-11-26** (simple EU compliance). Store age-rating / target-audience answers must say 16+ |
| Liability floor | greater of 12 months paid and GBP 100 (old text kept) | keep |
| Notice of term changes | 14 days | keep or lengthen to 30 |
| Response times | 30 days for privacy requests, "two working days" for support (old text kept) | keep |
| DMCA/notice contact | same support email, subject "Notice" | optional: register a US DMCA agent with the US Copyright Office if you have US users; not required for the page |
| Last updated | 26 November 2026 (`EFFECTIVE`) | bump on every change |

## 2. Old text versus reality (fixed in the new text)
1. Privacy said logs are deleted after 14 days. True for CloudWatch (`log_retention=TWO_WEEKS`, `backend_stack.py:181`), but Step Functions keeps each execution's history, which contains the prompt and options, for 90 days after the run and cannot be deleted earlier (AWS quota page; also noted in `docs/ACCOUNT_DELETION.md` section 5). Now in the retention table and on the delete page. Closing the gap needs a backend change (shorter history needs an AWS Support request; or stop passing the prompt in the execution input).
2. Privacy said photo coordinates are "not kept". The phone sends coordinates rounded to ~1 km (`common/photo_ids.py:55`); the engine drops them after naming the place (`engine/usermedia.py:157`), but `media_meta` with those coordinates is part of the Step Functions execution input (`sf_launcher.py:92-94,299`), so they sit in the 90-day history. The new text says so. Backend fix: strip lat/lon before `start_execution`.
3. Privacy said servers are in "Ireland and the United States". Production is `us-west-2` only (`docs/DEPLOY.md`); Ireland is QA. Polly runs in `us-east-1`; Claude 5.x uses Bedrock global profiles, which AWS may route to any commercial region. All now stated.
4. "None of our providers may use your content to train" is not true of Tavily, whose policy lets it use query data to improve its service and pass queries to search indexes. Now disclosed, with a warning not to put personal details in research prompts. Options: ask Tavily for a data processing agreement or zero-retention terms, or switch provider.
5. "Anthropic's Claude models receive your text" was reworded: per the AWS Bedrock page, model makers have no access to prompts or logs; the models run inside AWS.
6. Providers list lacked NASA, Wikipedia, Polly's region, Cohere. Added. Pexels API keys were paused when last checked (`docs/CLIPS.md`); it is listed because the code is wired for it (confirm).
7. The home page cookie banner offered "optional cookies to help us improve videomk", but there are none (no analytics code in `frontend/src` or either app). Reworded to an honest notice with one OK button (`ConsentToast.tsx`).
8. "Share a video link: anyone can watch" was only true on iPhone, where `ShareLink` passes a playback URL that expires after 1 hour (`get_video.py:151`); Android shares the downloaded file. Now describes both.
9. Backups "overwritten on their normal cycles": production tables use point-in-time recovery, 35 days. Now stated, including for safety records (can outlive the 90 days by up to 35 days in backup).
10. "Purchase records kept as the law requires" and "payments handled by Apple or Google": no purchase flow exists and account deletion deletes all wallet rows. Text now says no payments yet.
11. Delete page said "in the app" only; the website has no delete button. Now says so. It also lists what can remain (90-day history, 35-day backups, safety records).
12. Removed "videos are labelled as made with AI where the app or store requires it" (cannot be shown in code). The terms now put the disclosure duty on the user.
13. Removed the `OWNER REVIEW` comments from the page sources (their content is in this file).
14. The old terms had no safety-enforcement or appeal wording, no credits detail (4K doubles; expired refunds as 24 h credits; welcome credits expire in 30 days), no likeness clause, no notice procedure. Added from `docs/CREDITS.md`, `docs/INTAKE_AND_SAFETY.md`.

## 3. What each section rests on (code and docs)
| Section | Basis |
|---|---|
| Privacy 2 collected data | `docs/CREATE_API.md`, `docs/MEDIA_LIBRARY.md`, `common/photo_ids.py`, `common/library.py`, `sf_launcher.py` (`X-Timezone`, request record `_register_intent` stores the prompt), Android manifest (INTERNET, RECORD_AUDIO only), iOS `Info.plist` (microphone, speech) |
| 4 processors | `docs/DEPLOY.md` (Polly us-east-1, Bedrock models, global profiles), `engine/websearch.py` (Tavily, 200-char query), `docs/CLIPS.md` (stock sources), `docs/AUTH_SOCIAL.md` |
| 5 photos / My media | `docs/MEDIA_LIBRARY.md` (security table, "no staff tool lists photos"), `backend_stack.py` lifecycle rules (uploads 2 days, working files 7 days) |
| 7 safety | `common/safety.py`, `docs/INTAKE_AND_SAFETY.md` (160-char excerpt, hash, 90 days, 3 stops/24 h pause, 8 stops/30 days hold) |
| 8 Google/Apple | `social_auth.py` attribute mapping (name, given/family name, email, email_verified; no picture), scopes `openid email profile`, `docs/AUTH_SOCIAL.md`, `docs/ACCOUNT_DELETION.md` section 4 (Apple revoke, no Google token kept) |
| 10 retention | `backend_stack.py`, `media_library.py`, `request_intake.py`, `account_deletion.py` (PITR in prod, TTLs), Step Functions quotas page |
| 13 rights | `docs/ACCOUNT_DELETION.md` (timing: data within minutes, Cognito after 65 to 75 minutes) |
| 15 cookies | `frontend/src/lib/auth.ts` (localStorage tokens), `PromptForm.tsx` (sessionStorage), `ConsentToast.tsx`; apps: `SecureTokenStore` (Keystore), no analytics SDKs (grep of both apps and the frontend found none) |
| Terms credits | `docs/CREDITS.md`; acceptable use is the category list in `common/safety.CATEGORIES`; enforcement is `common/safety.py` constants |

## 4. Facts to confirm (I could not prove these from code or docs)
1. Bedrock "does not use inputs to train models" (carried over from the old policy and AWS's public statements; the AWS page I read only confirmed that model makers cannot see prompts). Confirm against the AWS Service Terms and, for Cohere, the Bedrock model terms.
2. "Staff do not read prompts or look at photos except to fix a fault you ask about, a safety report, or by law". True as a tooling statement (no staff tool lists photos); confirm it matches how you will operate. Staff with AWS admin rights can technically read data.
3. IP addresses: no API Gateway access logs or analytics were found, but AWS (API Gateway, CloudFront, Cognito, CloudTrail) sees IPs. The text says "your IP address when you connect". Confirm whether you enable access logging later (then add its retention).
4. Tavily queries: code clips them to 200 chars and sends no account data; a query written by the model from a prompt could still include a name the user typed. The text warns users; confirm the planner prompt tells the model not to put personal names into queries.
5. Background music is generated by videomk (`docs/MUSIC.md`: synthesised in-house; confirm it is still the case at launch) and narration uses Polly generative voices. If you switch voice provider (code supports Gemini/OpenAI TTS behind flags), name it in the policy.
6. The photo "ten thumbnails to a sheet" description and "originals deleted as soon as the cleaned copy is made" come from the old text and `docs/PHOTOS.md`; spot-check on QA.
7. My media search words are not stored (docs say used only to answer; logs hold ids and counts). If you store them, add them to the policy and to the store labels (Search history).
8. Cognito hosted UI cookies and sign-in logs: described generically.
9. Account-deletion gaps: a person on a safety hold who deletes the account leaves the hold behind (owner decision, `docs/ACCOUNT_DELETION.md` section 9). If you switch on `-c accountTombstone=1`, add the sentence proposed in section 7 of that file to Privacy section 10, and update the delete page.
10. Device checks: DeviceCheck/App Attest/Play Integrity are planned, not built. When added, the policy needs a device-identifier line and the store labels change (Device ID, Fraud prevention).
11. When payments launch: add receipts/transaction data, tax records, refund terms, Apple/Google billing terms, and update the store labels (Purchases).
12. URLs are live? `docs/DEPLOY.md` says production's custom domain is off until a Route 53 zone exists. The pages say `videomk.com/privacy` etc. and the stores need those URLs working before review.
13. Support reply time and 30-day answers are commitments: confirm you can meet them.
14. Report-a-video: the terms and support page point to email. Google Play expects in-app reporting for AI-generated content (`docs/ANDROID_RELEASE.md`): the email route is not an in-app one.

## 5. videomk's own AI media library (owner addition, 2026-11-26)
Written into Terms section 12, Terms section 10 (labelling), the Terms at-a-glance, and Privacy sections 2, 7 and 10. Statements made: images and clips come from a library videomk made with commercial generative models and reviewed; "we own or control all rights we have in it", with an honest note that purely AI-generated material may have limited copyright; users may use it in their videos incl. commercially, no credit needed, but no resale or redistribution as media, no extraction, no competing library, no model training; it is not made from any user's content and user prompts, photos and uploads never create or improve it; generic scenes, no real people by design, any likeness unintended; labelled as AI where platforms require, and users must disclose (YouTube, TikTok, Instagram); stock sources keep their own licences and credits.
To confirm before launch: (a) the licence terms of every commercial generative model you use allow commercial reuse and sublicensing of outputs to your users (check each vendor); (b) the library really is generated only from prompts you write; (c) whether you apply an AI label to the file or on screen (the terms say "where a platform or the app asks for it"; align with what you build); (d) the data safety/App Privacy answers do not change, since library media is not user data.
**Demand log (not built yet)**: Privacy section 2 and the retention table say: generic image search phrases written by the director (not the prompt, not photos, no account identifier beyond a count of distinct videos), personal-looking phrases filtered out before storage, aggregated, not linked to a person, kept while useful. Confirm when built: nothing is stored that identifies the account (not even a hashed id), the personal-phrase filter exists and is tested, whether any retention limit is set (the text promises none; consider adding one, for example 12 months, and say it), and the table is covered by the account-deletion coverage guard (it should not need to be if it holds no user key).

## 6. Clauses to have a lawyer look at later
1. Liability cap and exclusion wording (Terms 17) and the light indemnity (18), against consumer-law rules in the UK, EU and your main markets.
2. Governing law and courts (Terms 20) if the company is not English; the consumer carve-out.
3. The licence of user content (Terms 6) and the "we own or control all rights we have" wording for AI library media (Terms 12).
4. Legal bases and transfers: reliance on provider SCCs and data frameworks without having signed your own addenda; whether Tavily needs a controller-to-controller or processor agreement; an EU/UK representative.
5. Minimum age and parental-permission wording (13, up to 16 in some EU states) and the App Store/Play age rating answers.
6. Automated safety decisions (pauses, holds, 90-day records) under GDPR Art. 22 and legitimate-interest balancing; the appeal promise.
7. Copyright notice procedure (Terms 15), the DMCA safe harbour if you serve US users (agent registration).
8. Apple as third-party beneficiary clause (standard, check against Apple's minimum EULA terms).

## 7. Store-form answers (derived from the policy)
### Google Play Data safety
| Data type | Collected | Shared | Optional | Purpose | Notes |
|---|---|---|---|---|---|
| Personal info: Name | Yes (only via Google/Apple sign-in) | No | Yes | Account management | |
| Personal info: Email address | Yes | No | No | Account management, app functionality | |
| Personal info: User IDs | Yes | No | No | App functionality, account management | Cognito sub |
| Photos and videos: Photos | Yes (chosen or added to My media) | No | Yes | App functionality | metadata stripped on device |
| Photos and videos: Videos | Yes (the videos made for the user) | No | No | App functionality | |
| App activity: Other user-generated content | Yes (prompts, answers, edits) | See note | No | App functionality | Tavily receives short search queries derived from prompts and may use them to improve its service; Google's rule excludes service providers acting on your behalf, and Tavily is borderline. Conservative answer: declare Yes, shared, for this type with purpose App functionality; the lenient answer is No |
| Location: Approximate location | Yes (rounded to ~1 km, from photo data, optional) | No | Yes | App functionality | no location permission requested |
| Audio | No | | | | dictation is done by the OS recogniser |
| Device or other IDs, Diagnostics, Financial info, Messages | No | | | | update when device checks or billing arrive |
| Security practices | Encrypted in transit: Yes. Encrypted at rest: say so in the description only (not a form field). Deletion: Yes, in app and web URL `https://videomk.com/delete-account`. Users can request deletion of some data (videos, photos) without deleting the account: Yes. Data not sold, no ads. |
Other Play items: privacy policy URL `https://videomk.com/privacy`; target audience 13+; in-app reporting of AI content is expected (see fact 14).

### Apple App Privacy ("nutrition labels")
| Category | Data type | Linked to you | Used for tracking | Purpose |
|---|---|---|---|---|
| Contact Info | Name (federated sign-in only), Email Address | Yes | No | App Functionality |
| User Content | Photos or Videos; Other User Content (prompts) | Yes | No | App Functionality |
| Location | Coarse Location (optional, rounded place from photo data) | Yes (place name is stored with the video) | No | App Functionality |
| Identifiers | User ID | Yes | No | App Functionality |
| Usage Data, Diagnostics, Purchases, Search History, Audio | Not collected by us | | | confirm fact 7 for Search History |
Tracking: none ("Data Not Used to Track You"): no advertising identifier, no third-party advertising or analytics SDK. Privacy policy URL `https://videomk.com/privacy`. Support URL `https://videomk.com/support`. Account deletion in app exists (5.1.1(v)). AI-generated content: the age-rating questionnaire asks about user-generated and AI content; answer as the product behaves and expect 12+ to 13+ (confirm in the result).

### Google OAuth consent screen
App name `videomk`; user support email `hello@videomk.com`; developer contact email: the same; app home page `https://videomk.com` (must link to the privacy policy: the footer does); privacy policy `https://videomk.com/privacy`; terms `https://videomk.com/terms`; authorised domain `videomk.com` (verify in Search Console); scopes `openid`, `email`, `profile` only (non-sensitive: no verification review beyond branding). The Privacy section 8 states exactly what is received and that no other Google data is accessed (Limited Use is not triggered, but the statement is there).

### Sign in with Apple
Services ID with domain and return URLs from `docs/AUTH_SOCIAL.md`; privacy policy URL in App Store Connect; in-app account deletion with token revocation (flag `appleRevoke`, off by default: switch it on before submission); handle Hide My Email addresses (`@privaterelay.appleid.com`): if you ever email users, register your sending domain and addresses with Apple's private email relay service in the developer account; the policy says relay addresses are separate accounts.
