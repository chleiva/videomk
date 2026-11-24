# Research for scripts: encyclopedia or web agent (2026-11-23)

`engine/director.py` first classifies the brief (`researcher.decide`, one small-model call, a fraction of a cent) and then:
- **encyclopedia** (timeless topics: how things work, history, science): a few Wikipedia pages, as before. Cheap and predictable.
- **web** (news, anything recent or time-sensitive, current prices, rankings, schedules, who holds a role now, niche facts a model may not know):
  a small research agent (`researcher.research_web`) searches the web and reads a few pages, then the script is written from that evidence.
Anything that goes wrong in the web path (no key, search error, nothing found, model error, time) falls back to the encyclopedia path. The video never fails because research did.
Without a search key (`/videomk/tavily_api_key` in SSM) the web path is simply off and no decision call is made.

## How the agent works
Native tool use on Bedrock (Haiku 5.5): tools `web_search(query, topic, time_range)` and `read_page(id)`. Budgets are hard limits: 4 searches, 2 page reads,
5 steps, 45 seconds, plus one tool-less final turn if the steps run out. Results are numbered sources (S1, S2, ...). The agent ends with a JSON verdict of which
sources were useful. The notes given to the script writer are **the evidence itself** (snippets and page text of the useful sources, dated), never an
LLM summary, so every fact can be traced to a page; the script writer cites only the sources it used (`sources_used`), which fill the video description.
The script prompt also gets today's date and a rule that time-sensitive facts must come from the notes, not memory.

## Security
- Search results and pages are untrusted data: wrapped as such, and the agent is told to ignore instructions in them. **The agent can only read pages a search returned, by id, never by URL** (tested: URLs and unknown ids are refused), so injected text cannot send it anywhere or exfiltrate data through a URL.
- Page reading uses the SSRF-safe fetcher (https only, public addresses only, every redirect hop checked; tested against 169.254.169.254, 127.0.0.1 and plain http), size-capped, text only, PDFs refused.
- Results are https only; images are not requested from the search provider.
- Hard budgets also cap cost (about $0.03-0.05 per web script: 2-4 searches at $0.008 plus a few cents of agent tokens; measured agent tokens in a live test were $0.0005).

## What we took from Plorer (`plorer-core`) and what we changed
Took: the cheap intent gate before searching; separate query preparation with provider options (topic, time range); budgeted ReAct loop; citation ids; fallback when search is unavailable.
Changed: native tool use instead of the XML-tag protocol (no parse retries); evidence-as-notes with a usefulness verdict; id-only page reads; SSRF-safe fetching (Plorer's `web_fetch` accepts any http/https URL including internal addresses and follows redirects: worth fixing there); no Exa yet (the provider is behind one `search` signature, add it beside `TavilyProvider`).

## Images from the internet: policy (decided 2026-11-23)
**Only images that are fully licensed for reuse, never anything copyrighted.** Web search is for text research only: the search request asks the provider for no images
(`include_images: false`, covered by a test) and nothing the agent finds on the web ever becomes a picture in a video. Pictures come only from sources with a clear open licence:
Unsplash (Unsplash License) and Openverse (CC0, public domain, CC BY), each credited on screen and in the description, and the user's own photos. Video clips follow the same rule: Pexels (Pexels License) and Wikimedia Commons (per-file CC0, public domain, plain CC BY) only; see `docs/CLIPS.md`. Candidates to add later, each
with machine-readable licence data: Wikimedia Commons (Commons API `extmetadata`), and public-domain collections (NASA, Library of Congress, Smithsonian, US government works).
A new source needs a documented licence check in code before it is used.

## Setup
The key is the same Tavily key Plorer uses (read from its Secrets Manager entry `tavily`, us-west-2, and copied to `/videomk/tavily_api_key` in SSM; never printed or committed). It is shared, so
usage and quota are shared with Plorer, and a rotation there must be repeated here. Create a separate key for videomk before launch if you want separate quotas and billing. To set or replace it:
`aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/tavily_api_key --value '<key>'` (never in chat or git). `WEB_RESEARCH=off`
on the plan function disables the web path without a deploy of code.
