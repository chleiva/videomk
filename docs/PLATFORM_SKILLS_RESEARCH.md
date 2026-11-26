# Platform skills: research and evidence (2026-11-26)

What a very good video looks like on each platform, what the platforms themselves say, and how strongly each claim is supported. The guides that came out of it are in `backend/lambdas/engine/skills/platform-*.md`; how they are selected is in `docs/SKILLS.md`.

**How this was gathered, and its limits.** Web searches on 2026-11-26 plus one direct page read (LinkedIn Marketing Solutions, video ads tips). Most platform help centres render poorly for automated readers: the X Business best-practices page returned HTTP 403, and TikTok, Meta and YouTube help pages were seen through search summaries, not read in full. So "primary" below means the platform's own page was named by the search and its content summarised; I mark where a number only exists on a third-party site. Nothing here was measured on our own viewers (the app has no analytics). Retention and engagement benchmarks come from vendor datasets, which differ in sample, metric and year; where two datasets disagree I say so and do not pick a winner.

Evidence grades: **A** = stated by the platform itself; **B** = a named dataset from a vendor (size and year given), consistent with others; **C** = single vendor or creator-advice claim, repeated without a source, or datasets that conflict. Folklore is labelled as such.

## 1. The ten strongest findings

| # | Standard | Grade | Source |
|---|---|---|---|
| 1 | The first seconds decide: YouTube Studio reports "viewed vs swiped away" for Shorts and a 30-second "intro" retention figure for long videos; creator and tool guides put the hook window at 1-3 s (Shorts/TikTok/Reels) and the first 30 s (long-form). The exact thresholds (70% viewed, 60% at 30 s) are third-party rules of thumb. | A for the metrics existing, C for the thresholds | [vidIQ Shorts hooks](https://vidiq.com/blog/post/viral-video-hooks-youtube-shorts/), [vidIQ retention](https://vidiq.com/blog/post/audience-retention-secrets-youtube/) |
| 2 | LinkedIn: "key message in the first 10 seconds", point made in the first 5 s for ~30 s videos; 7-15 s videos saw up to a 300% lift in completion rates (LinkedIn data, 2025); burn in subtitles because many members watch with sound off; positioning as a thought leader for awareness. | A | [LinkedIn video ads tips](https://business.linkedin.com/advertise/ads/sponsored-content/video-ads/tips) (read directly) |
| 3 | Sound-off is the default on feeds: LinkedIn says 79% of feed videos are watched with sound off (2021 LinkedIn blog; the ad page later says "almost 80%"). The much-quoted "85% of Facebook video is watched muted" comes from a 2016 Digiday article on two publishers (a 3-second view counts), so it is old and narrow. Meta's captions-add-12%-view-time figure is repeated by caption vendors with no primary link; an independent Instapage A/B found only +5% view time. Conclusion: captions on, strongly; the percentages are indicative only. | A (LinkedIn), C (the rest) | [LinkedIn 2021 blog](https://business.linkedin.com/marketing-solutions/blog/video-marketing-/2021/4-tips-for-better-video-ads-on-linkedin-in-2021), [Digiday 2016](https://digiday.com/media/silent-world-Facebook-video/), [3Play](https://www.3playmedia.com/blog/captions-increase-viewership-for-facebook-video-ads/), [Instapage](https://instapage.com/blog/closed-captioning-mute-videos) |
| 4 | X advises movement and clear branding in the first 3 seconds, and captions or text overlays so the message lands without audio (its own playbook links captions to longer view times). Length guidance (about 15 s or less) is a 2020 Twitter/GroupM write-up, not current. | A (3 s, captions), C (length) | [X Business playbook](https://business.twitter.com/content/dam/business-twitter/en/resources/downloadables/objective-playbooks/objective-playbook-preroll-views.pdf), [Social Media Examiner](https://www.socialmediaexaminer.com/4-ways-to-use-video-in-twitter-ads/) |
| 5 | Shorter videos hold a larger share: Wistia's 2026 State of Video (13M+ videos): under a minute averages a 52% engagement rate (average share watched); 1-3 minute videos have about twice the engagement rate of 30-60 minute ones, though far less total watch time. Wistia notes the length-engagement relationship is stable year to year. | B | [Wistia State of Video](https://www.wistia.com/state-of-video), [Wistia webinar recap](https://wistia.com/learn/marketing/state-of-video-webinar-recap) |
| 6 | Best length is NOT settled for social video: Socialinsider 2026 (9.8M Reels, 1K-1M followers) finds 45-60 s the best engagement rate (0.35%), over 3 min worst (0.15%); Buffer 2026 (2.7M Reels) finds 90 s-3 min best for reach versus each account's baseline. TikTok: Buffer 2025 (1.1M videos) found over 1 minute gets 63.8% more watch time than 30-60 s, while Socialinsider finds ~30 s best for engagement rate and 2-3 min for views, and Fanpage Karma (32,000 TikToks) 30-90 s for interaction. Both Buffer and Socialinsider say length is not decisive. We therefore set a default band and let the requested length win. | B (conflicting) | [Socialinsider Reels](https://www.socialinsider.io/blog/instagram-reels-length/), [Buffer Reels](https://buffer.com/resources/instagram-reels-length), [Buffer TikTok](https://buffer.com/resources/longer-tiktoks-get-more-views-data/), [Socialinsider TikTok](https://www.socialinsider.io/blog/how-long-are-tiktok-videos/), [Fanpage Karma](https://www.fanpagekarma.com/insights/optimal-tiktok-video-length/) |
| 7 | Safe zones: all vertical platforms draw UI over the frame. TikTok publishes official safe-zone templates; third-party measurements of its margins disagree (bottom 320 vs 440 px of 1920, i.e. 17-23%; right 60-120 px; top 108-160 px). For Reels ads Meta's guardrail implies roughly top 14%, bottom 35% (40% with disclaimers), sides 6% (the figures appear on a secondary blog, not on Meta's page I could read; organic Reels has no published margins). Shorts' margins were not found in a primary source. The three platforms differ, so one conservative vertical safe area is the practical rule. | C (numbers), A (that zones exist) | [Emplifi](https://emplifi.io/resources/blog/tiktok-ad-specs), [ManyPixels](https://www.manypixels.co/blog/social-media-design/tiktok-ad-specs), [Sirency](https://www.sirency.com/blog/instagram-reels-safe-zone), [Lilach Bullock](https://www.lilachbullock.com/instagram-reels-safe-zone/) |
| 8 | AI disclosure is a rule on every vertical platform and YouTube. YouTube: creators must disclose meaningfully altered or synthetic content that looks realistic (upload "altered content" setting; label in the description, in the player for photorealistic content; undisclosed content can be labelled by YouTube and repeat offenders penalised; disclosure does not limit reach or monetisation). TikTok: label all AI-generated content with realistic images, audio or video; auto-labels via C2PA content credentials that creators cannot remove. Meta: "AI info" label, required for photorealistic video or realistic audio created or modified with AI; the help pages differ on images. | A | [YouTube Help](https://support.google.com/youtube/answer/14328491), [TikTok support](https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content), [Meta help](https://www.meta.com/help/artificial-intelligence/1783222608822690/) |
| 9 | YouTube Partner Program "inauthentic content" (renamed from "repetitious content", effective 2025-07-15): mass-produced or repetitive videos, e.g. narrated stories that differ only superficially or slideshows reusing the same narration, are not monetisable. YouTube called it a clarification, did not name AI, and has not published exact definitions. Our narrated, researched, sourced videos with varied scenes are the opposite of the examples, but templated output across many videos is the risk. | A (rule), C (scope) | [Search Engine Journal](https://www.searchenginejournal.com/youtube-targets-mass-produced-content-in-monetization-update/550337/), [Plagiarism Today](https://www.plagiarismtoday.com/2025/07/08/youtube-targets-inauthentic-content/), [TechCrunch](https://techcrunch.com/2025/07/09/youtube-prepares-crackdown-on-mass-produced-and-repetitive-videos-as-concern-over-ai-slop-grows) |
| 10 | LinkedIn orientation is unsettled: LinkedIn Creative Labs findings reported by PPC Land say vertical had 34% longer dwell time than square and horizontal 59% more than 1:1 (the reported results conflict). Native uploads beat YouTube links (Socialinsider: about 38% more engagement; external links reportedly cost up to 30% of reach: vendor claims). LinkedIn shows creators watch time and average watch time. Our default (4:5 at 1 min) stays; the length and the point-first structure are the stronger levers. | C | [PPC Land](https://ppc.land/linkedin-creative-labs-reveals-what-makes-b2b-video-content-successful/), [Socialinsider LinkedIn](https://www.socialinsider.io/blog/linkedin-video-marketing/), [NetInfluencer](https://www.netinfluencer.com/linkedin-focus-on-view-duration-signals-growing-investment-in-video-content/) |

## 2. Platform by platform

### YouTube (long-form)
- **Rewards (stated):** watch time and viewer satisfaction through retention curves. Studio shows average view duration, percentage viewed and the first-30-second "intro" figure. The claim that early retention is a heavily weighted signal is creator folklore (C).
- **Hook:** payoff or question in the first sentence; match the title and thumbnail promise within about the first 15 s (C, consistent across vidIQ, 1of10, Epidemic Sound). 60% still watching at 30 s is "good" per vidIQ and 70%+ per 1of10: not YouTube numbers.
- **Structure:** chapters (descriptive titles), re-hooks every 2-3 minutes for long videos (creator practice; C). Wistia: instructional 3-5 minute videos average a 43% engagement rate (74% for instructional specifically): B.
- **Format:** 16:9, 1080p; 4K only worth it here (our decision in `format_options`). Loudness: YouTube normalises down to about -14 LUFS and does not boost quiet audio (B: many mastering sources agree; the YouTube page itself was not read). Our renderer already targets -14 LUFS, true peak -1.5 dB.
- **Text/metadata:** title specific and honest; description plain; 3 or fewer hashtags is a common recommendation (C). End screens and "subscribe" are optional; begging is a creator-advice "avoid" (C).
- **Policy:** altered/synthetic content label for realistic material; inauthentic-content rule (finding 9).

### YouTube Shorts
- **Rewards:** "viewed vs swiped away" and average percentage viewed are the Studio metrics (A that they exist); threshold values (70% viewed, 90% average viewed, under 30% swipe in 3 s) are third-party and inconsistent (C).
- **Length:** up to 3 minutes now; sources agree 15-45 s is the retention sweet spot (OpusClip analysis, secondhand: C). Vertical 9:16, 1080x1920.
- **Hook:** treat frame one as the thumbnail; say the payoff in 5-10 words; stack text, audio and visual hooks (vidIQ, Opus; C).
- **Ending:** a loop (last line returning to the first) is a creator tactic (C): replays raise average percentage viewed above 100%.

### TikTok
- **Rewards:** the platform's own creator guidance stresses watch time, completion, shares and replays; third-party studies consistently say the first 3 s determine continuation (SocialPilot, 1.5M posts, Q1 2025: B/C).
- **Length:** conflicting data, finding 6. Default 20-40 s, up to ~60 s.
- **Safe zone:** official templates exist; right column of buttons and a caption block over the bottom (finding 7). TikTok shows up to 4 lines of caption text.
- **Audio:** trending sounds are not available to us (and licensing is separate). No official LUFS target for TikTok or Instagram; the "-10 to -12 LUFS" claim on vendor blogs is unsupported (C). -14 LUFS is a safe, non-clipping choice because platforms mostly normalise loud audio down.
- **Tone:** native, direct, casual (creator consensus, C).
- **Policy:** realistic AI content must be labelled; TikTok adds invisible watermarks and reads C2PA. Hootsuite's reading that AI-written scripts and generic text-to-speech voice-overs do not need a label is a secondary interpretation: our product should still suggest the label for anything realistic (our scenes are stock footage and photographs, not synthetic people).

### Instagram Reels
- **Rewards:** Meta has said Reels are ranked by predicted watch time, completion, likes, shares and saves (widely reported creator-guidance statements: C, not re-verified here).
- **Length:** conflicting (finding 6). Default 15-30 s, up to 45-60 s for a story.
- **Safe zone:** finding 7 (ads: 14% top, 35% bottom, 6% sides; treat as a cautious default for organic).
- **Policy:** "AI info" label; Meta penalises unlabelled photorealistic AI video (A); I did not find a verifiable current statement on Instagram's unoriginal-content (reposting) policy.

### Instagram feed video
- Muted autoplay in feed makes pictures and large text the carrier (C, extrapolating from Meta's silent-autoplay behaviour: "85%" figures are 2016 Facebook data). Crop note: the profile grid is 3:4 and crops 4:5 posts at the edges (A for the grid ratio; I rely on it only to keep key content central). Same AI-label rules as Reels.

### LinkedIn
- See findings 2, 3, 10. Official: key message by 10 s, burn in captions, concise and visually compelling, 7-15 s videos complete most, longer content can drive as many views and clicks (so length is for the purpose).
- **Rewards:** vendor pages say native video and dwell time (C; no LinkedIn document found). LinkedIn itself highlights average watch time as the metric (A via Digiday/NetInfluencer reporting).
- **Tone:** professional with a point of view (LinkedIn's "thought leader" wording, A; the rest creator consensus, C).
- **Overlays:** the player's controls and caption box take the bottom of the frame; I found no published safe-zone fractions.

### X
- Finding 4. Vertical video ads are sound-on by default per X's own page, so audio can matter; the feed still plays muted until tapped. Length and aspect specs: not confirmed (the official page was blocked). Timeline cropping of previews to centre is widely observed but unconfirmed here.

### Facebook Reels (not given its own guide)
Same vertical frame and Meta label rules as Instagram Reels; Facebook is the source of the dated "85% muted" figure. Covered by the `reels` guide; not worth a separate file until it is a platform in the app.

### Website / embed ("Just a video")
No platform. Wistia's data is the best evidence (finding 5): short videos hold more; use chapters and re-hooks for long ones. Must stand alone: muted-capable, no platform context.

## 3. What the engine already does, and the gaps
- **Captions** (`engine/frame.py` `_CAPTION`): 9:16 box bottom edge at y=1670 of 1920 (87% of height; 250 px = 13% clear below), 58 px type, max 900 px wide, 7 words per page, plus a right strip of 130 px (12%) reserved; content above y=1450. 1:1 bottom 1020/1080; 4:5 bottom 1290/1350 (4% clear); 16:9 bottom 1010/1080.
- **Gap versus the research:** the 9:16 bottom clearance (13%) is smaller than TikTok's measured 17-23% and much smaller than Meta's ads guidance (35%). For Reels/TikTok the caption box sits where the platform's own caption and buttons draw. 4:5 and 1:1 have almost no bottom clearance (the feed player's controls and 4:5 grid crop). Not changed here: moving captions changes every vertical render and layout (the content box above them shrinks), which needs a visual review, so the guides tell the planner to keep its own text out of the unsafe bands and the table in section 4 lists the renderer work.

## 4. Engine and renderer changes the standards imply (not made)

| Change | Why (evidence) | Effort |
|---|---|---|
| Per-platform caption position and safe area (TikTok/Reels: bottom 25-35%, Shorts and 4:5/1:1 separately), moving `_CAPTION` bottom up and shrinking the content box; side margin about 6-12% | Finding 7; current 13% bottom clearance | 2-3 days with visual review of all scene types per aspect |
| Platform-specific caption style (words per line 4-6 on TikTok/Reels, active-word highlight) | TikTok/Reels native look (C) | 1 day |
| Loudness target per platform (keep -14; allow a quieter -16 for LinkedIn and no limiter-induced clipping) | No official targets except YouTube -14 (finding in section 2); low value | 0.5 day, low priority |
| Cut-cadence enforcement: a beat holds one scene; short-form has about one beat per 10 s (`plan.SHORT_BEAT_S`), so a 3-5 s cadence needs sub-beat cuts (clip montages already do this for visual topics; a second image per beat or a gallery auto-split would do it for others) | Short-form creators cut every 2-4 s (C); our beat budget makes 8-18 word beats the lower bound | 3-5 days |
| Platform end cards or loop-friendly endings (render a last frame that matches the first; no outro) | Loop/replay tactic (C) | 1 day for a loop-friendly crossfade; end cards not worth it (we invent no brand or handle) |
| AI-disclosure hint in the publish step: tell the person that YouTube, TikTok and Meta require labelling realistic synthetic content, with the exact setting name; C2PA content credentials in the exported MP4 (TikTok reads them) | Finding 8 | 1 day for the hint; 3-5 days for C2PA signing |
| First-frame check: the first frame already shows the topic (no black or title-only frame under 1 min) | Frame one is the thumbnail for Shorts/Reels (C) | 1 day |
| Platform-specific length bands in the planner's word budget (the budget follows the requested length; the platform default is only a suggestion) | Finding 6: evidence conflicts, so no change | none |

## 5. Weakly supported claims we use anyway (and why they are cheap to follow)
- Hook in 2-3 s, text kept out of the right and bottom bands, captions on: all are low risk if wrong (no viewer is harmed by a stronger first line or by safe margins).
- Short lengths as defaults: evidence conflicts, so the guides say "the length asked for wins".
- Platform tone descriptions: creator consensus, not measured; they affect vocabulary only.
- Trending sounds and hashtags: not used (not available to us, and the platforms' own guidance is vague).
