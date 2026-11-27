# Speech cost and alternatives (2026-11-27)

Answers the owner's questions: is speech a major cost driver, are OpenAI's models cheaper than Polly, and could an open model on an EC2 GPU do the job. It updates `docs/VOICES_RESEARCH_2026-11-27.md` (quality evidence and provider detail live there); **every price and status below was read again on the provider's own page on 2026-11-27**, not copied from that document or from memory.

Labels: **V** = the provider's own page read on 2026-11-27. **S** = a third party. **CNV** = could not verify (what was tried is said). Cost per minute assumes **900 characters = 1 minute of narration**. "Elo" is the Artificial Analysis blind listening arena (English, short clips, 106 models; `artificialanalysis.ai/text-to-speech/leaderboard`, read 2026-11-27).

## 1. Decision (confirmed by the owner on 2026-11-27)

1. **Stay on Amazon Polly generative as the base.** No provider switch and no self-hosting now.
2. **OpenAI is not an option**: all three of its speech models shut down on 2027-01-06.
3. **Speechify Simba 3.5 and Inworld TTS-2 are recorded as candidates** for a later blind listening test and a possible premium-voice option. Nothing is built for them now.
4. The larger savings are not in speech (section 2).

## 2. Where the money goes: speech is about 14 % of a minute of video

Measured on 85 QA videos, 25 to 27 November (`docs/PLANS_PROPOSAL_2026-11-27.md`, section 1):

| Per minute of video | Cost | Share |
|---|---|---|
| Rendering (Lambda), 720p/1080p | about $0.070 | 41 % |
| Script and planning (Sonnet 5.5) | $0.061 | 36 % |
| **Voice (Polly generative)** | **$0.023** | **14 %** |
| Web research | $0.012 | 7 % |
| Checks | $0.003 | 2 % |
| Total | about $0.169 | |

A credit costs $0.15 at the median, so the voice is about 2 cents of each credit. **Speech is the third cost, not the first.** If speech were free tomorrow a credit would cost $0.13 instead of $0.15. Halving the voice price (the best any quality-equal provider offers) saves about 1 cent per credit.

What would move the needle more: the script model is 36 % of the cost and its prompt is 14,000 to 17,000 tokens that are almost the same in every video (and are sent again for every section of a long video); caching that fixed part of the prompt, where the model on Bedrock supports it, and moving the long lists out of it (`docs/SELECTION_ARCHITECTURE.md`) attacks the largest API line. Rendering is 41 %: it is Lambda seconds times memory, so the render memory setting and the seconds per frame are worth more than any voice price. Either is worth several times a change of voice provider.

## 3. Polly against the alternatives

| Provider / model | $ per 1M characters (or native unit) | $ per minute | Native word timings | Our 10 languages | Elo | Status |
|---|---|---|---|---|---|---|
| **Polly Generative (today)** | 30 | 0.027 | No | 10 of 10 (Portuguese is Brazilian only) | 1063 | Current |
| Polly Neural / Long-Form | 16 / 100 | 0.0144 / 0.090 | Yes | not checked | 895 / 1029 | Current |
| OpenAI `tts-1` | 15 | 0.0135 | No | English-optimised | 1087 | **Shuts down 2027-01-06** |
| OpenAI `tts-1-hd` | 30 | 0.027 | No | same | 1109 | **Shuts down 2027-01-06** |
| OpenAI `gpt-4o-mini-tts` | $12 per 1M audio tokens out | CNV | No | same | not ranked | **Shuts down 2027-01-06** |
| Gemini 3.8 Flash TTS | $9 per 1M audio tokens, $18 from 2027-01-01 | 0.0136, then 0.0272 | No | 10 of 10 | 1286 | "Preview" on the Cloud price page; price doubles on 1 January |
| Gemini 3.8 Flash-Lite TTS | $6, then $12 | 0.0091, then 0.0182 | No | 9 of 10 (no Finnish) | 1265 | same |
| Google Chirp 3 HD | 30 | 0.027 | No | 10 of 10 | 1062 | Current |
| Azure Neural / HD | 15 / 22 | 0.0135 / 0.0198 | Yes (HD Omni: word boundary events) | CNV per language | 1033 / 1152 | Current |
| ElevenLabs v4 | 80 | 0.072 | Characters (endpoint exists; v4 on it CNV) | 10 of 10 | 1340 | Current; paid plan for commercial use |
| ElevenLabs v4 Turbo | 40 | 0.036 | same | 10 of 10 | 1343 | Current |
| **Speechify Simba 3.5** | 15 / 12 / 10 by plan | 0.0135 / 0.0108 / 0.009 | **Yes (word-level)** | 10 of 10 | 1296 | Current; first 500,000 characters a month free, commercial use included |
| **Inworld TTS-2** | 25 on demand; 20 to 12.5 on plans | 0.0225; 0.018 to 0.011 | **Yes (word and character)** | 10 of 10 (Finnish in its second tier) | 1272 | Current; commercial licence on demand |
| Inworld TTS-2 Flash | 15; 10 to 7 on plans | 0.0135; 0.009 to 0.006 | Yes | same | 1216 | Current |
| Cartesia Sonic 3.6 | 50 / 39.2 / 37.4 by plan | 0.045 / 0.035 / 0.034 | CNV today | 10 of 10 | 1297 | Current |
| Deepgram Aura-2 | 30 | 0.027 | CNV | 6 of 10 | not ranked | Current |
| Amazon Nova 2.5 Sonic (Bedrock) | $12 per 1M speech tokens out | CNV | No | not read | not ranked | Speech-to-speech over a stream, not a text-to-speech endpoint |

Sources (all V, read 2026-11-27): `aws.amazon.com/polly/pricing/` ("Generative voices are priced at $30 per 1 million characters"; Neural $16; Long-Form $100; Standard $4; free tier 100,000 generative characters a month for the first 12 months); `docs.aws.amazon.com/polly/latest/dg/generative-voices.html` ("Support for generating speech marks is currently not available"); `developers.openai.com/api/docs/deprecations`, `.../guides/text-to-speech`, `.../pricing`; `aistudio.google.com/docs/pricing` ("Audio tokens correspond to 25 tokens per second of audio"), `cloud.google.com/text-to-speech/pricing`; Microsoft's Retail Prices API `prices.azure.com/api/retail/prices` (the Azure pricing page itself rendered no figures) and `learn.microsoft.com/.../high-definition-voices`; `elevenlabs.io/pricing/api`, `elevenlabs.io/terms-of-use`; `speechify.ai/text-to-speech-api`; `inworld.ai/pricing`, `docs.inworld.ai/tts/capabilities/timestamps.md`; `cartesia.ai/pricing`; `deepgram.com/pricing`; Bedrock model cards and the Bedrock price feed.

### OpenAI in detail (the owner's question)

- **Status (V):** the deprecations page lists `tts-1`, `tts-1-hd` and `gpt-4o-mini-tts` (both snapshots) as announced 2026-10-01 with shutdown **2027-01-06**, replacement `gpt-realtime-2.1-mini`. The text-to-speech guide says the three "are deprecated and will shut down on January 6, 2027". Yesterday's document gave 2027-01-14 for one of them; the deprecations page read today says 01-06 for all three. The replacement is a Realtime (voice-agent) model, not a drop-in for the speech endpoint. No newer text-to-speech model is listed.
- **Price (V):** `tts-1` $15 and `tts-1-hd` $30 per 1M characters, so `tts-1` is half Polly's price and `tts-1-hd` the same. `gpt-4o-mini-tts` is priced per audio token and OpenAI publishes no tokens-per-minute figure, so its cost per minute cannot be verified.
- **Quality:** Elo 1087 and 1109 against Polly's 1063: about the same, not better in a way a listener would notice (a 46-point gap is a 57 % preference).
- **Word timings (V):** none; the endpoint returns audio only (4,096 characters at most per request). Our aligner would be kept.
- **Terms (V):** the customer owns the output; the usage policy requires "a clear disclosure to end users that the TTS voice they are hearing is AI-generated".
- **Answer:** cheaper only for the weaker model, about the same quality, and gone in six weeks. Do not build on it.

### What a switch would need in our engine

The engine already has a provider interface (`engine/tts.py`: Polly, OpenAI, Gemini, a mock). A new provider is one class returning samples at 24 kHz. Word timing comes from the audio itself (`engine/align.py`, mean error 70 to 145 ms by language, `docs/LANGUAGES.md`), so a provider without timestamps works as Polly does today; one with native word timings (Speechify, Inworld, Azure HD) could replace the estimate with exact times, which mainly helps Polish. What would really cost work: a voice catalogue for the new provider (the resolver in `engine/voices.py` is provider-neutral in design but its data is Polly's), the measured pace of each voice for the length fit, a key in Secrets Manager and its failure handling, text leaving AWS (a privacy-policy line), and listening.

## 4. Self-hosted open models on EC2: not viable now

### Candidates (licence files and model cards read 2026-11-27; V unless marked)

| Model (Elo) | Weights licence | Commercial use | Our 10 languages | Fits a 24 GB GPU | Verdict |
|---|---|---|---|---|---|
| Fish Audio Drama 3 (1278) | Fish Audio Community License v1.0 | Only under $500,000 annual revenue, and no "hosted service" (with a carve-out for narrating content your own product generates) | 10 of 10 | **No**: 35B parameters, 35.9 GB of weights | Too large; licence has a revenue cap |
| Breeze TTS 2 (1230) | Research and non-commercial | No | English and Chinese | Yes | Not licensable |
| **Ming-3.0-tts 0.5B (1179)** | **MIT** | **Yes** | **5 of 10** (en, es, fr, de, ko; no it, pt, nl, pl, fi) | Yes (0.5B) | The only clean candidate above Polly; built-in voices are Chinese and English, others by cloning; **no published speed figure** |
| Phonon 31M (1107) | Apache-2.0 (English); the Spanish, French, German, Portuguese models are CC BY-NC | English only | 1 of 10 | Yes (runs on CPU) | English only |
| Fish S2 Pro (1104) | Research licence | No | 10 of 10 | Yes | Not licensable |
| Step-Audio-EditX (1101) | Code Apache-2.0; weights unclear on the card | Unclear | zh, en, ja, ko | Yes | Licence unclear, wrong languages |
| Voxtral TTS (1094) | CC BY-NC 4.0 | No | 7 of 10 | Yes | Not licensable |
| Magpie 357M (1064) | NVIDIA Open Model License (card: "ready for commercial use"; licence text not read) | Probably | 7 of 10 (no nl, pl, fi) | Yes | Polly's level, not above it |
| Kokoro 82M (1060) | Apache-2.0 | Yes | 5 of 10 (no de, nl, pl, fi, ko); 3 Spanish voices, 1 French | Yes | Polly's level, fewer languages and voices |
| Chatterbox (1021) | MIT | Yes | 10 of 10 | Yes | **Below** Polly; its README says it is retired and unmaintained since August 2026 |
| Higgs V3 (1035), XTTS v2 (917) | Non-commercial (Higgs); XTTS not re-read | No | - | - | Below Polly |

No candidate publishes a real-time factor on a T4, A10G or L4 (the GPUs of g4dn, g5, g6). The published figures are on H100/H200 cards, which cost several dollars an hour.

### The cost model for our pattern

EC2 on demand, us-east-1, Linux (V, AWS price feed published 2026-11-24): **g4dn.xlarge $0.526 an hour, g6.xlarge $0.805, g5.xlarge $1.006**, billed per second.

- Narration is needed **inside a request, within seconds**, one or two sentences at a time, many beats in parallel. An instance started on demand takes minutes to boot and load a model (the only official statement found: a SageMaker endpoint for a TTS model "takes several minutes to reach the InService status"; a third-party figure for a small model on an A10G is about 43 seconds, S). So the GPU would have to be **always on**, or the first video after a quiet period waits minutes or falls back to Polly.
- **Always on, the break-even against Polly is about 19.5 minutes of narration every hour**: $0.526 an hour divided by $0.027 a minute. That is about **470 minutes a day, 14,200 minutes a month**, on the cheapest GPU and before paying for a second instance (one instance is a single point of failure), storage, monitoring and the engineering. On a g5 it is about 37 minutes every hour.
- For scale: 14,200 minutes of narration a month is roughly 5,000 to 14,000 videos a month. Below that, Polly's pay-per-character price is cheaper than an idle GPU, and it scales to parallel beats with no queue.
- The owner's rule that **any EC2 instance must auto-terminate** is the opposite of what low latency needs: an instance that terminates when idle means a cold start for the next request. The two only meet with a "warm while there is traffic, Polly as the fallback while it boots" design, which is real work to build and operate.
- **Risk for a solo founder:** GPU capacity shortages, driver and model updates, a voice that changes when the model is updated (videos edited months later would not match), no provider behind the commercial licence, and quality in Spanish and the new languages that nobody has measured (the arena is English only).

**Plainly: not viable now.** The only open model that beats Polly with a clean licence covers half our languages and has no speed evidence; the volume is two to three orders of magnitude below break-even. It becomes worth a fresh look when narration passes roughly **10,000 minutes a month** AND an openly licensed model covers the ten languages at clearly better quality than Polly. No instance was launched for this research.

## 5. Recommendation

- **Stay on Polly generative as the default.** It is in-account (no text leaves AWS, no key), has all ten languages, costs 2 cents of a 15-cent credit, and the 27 voices and 7 languages added today cost nothing extra.
- **Do not switch to OpenAI** (shutting down) **or self-host** (not viable at this volume).
- **Later, a hybrid is the sensible upgrade:** Polly as the default and one premium provider as a Max feature or a general upgrade. The two that are cheaper than Polly, far better in blind tests and give native word timings are **Speechify Simba 3.5** ($0.009 to $0.0135 a minute, Elo 1296) and **Inworld TTS-2** ($0.011 to $0.0225 a minute, Elo 1272). ElevenLabs v4 is the best (Elo 1340) at 2.7 times Polly's price: a premium tier, not a default. Gemini 3.8 Flash TTS is strong and cheap until 31 December, then Polly's price, with no word timings and a "preview" label.
- **Before any switch: the blind listening test** already designed in `docs/VOICES_RESEARCH_2026-11-27.md` section 7 (about $1, one afternoon), in English AND Spanish, since none of the evidence above tests Spanish or five-minute consistency. Nothing to build until the owner has listened.

## 6. Could not verify

- Cost per minute of OpenAI `gpt-4o-mini-tts`, the OpenAI realtime models and Amazon Nova Sonic (no published tokens per second of audio).
- Whether ElevenLabs v4 is supported on the with-timestamps endpoint; whether Cartesia Sonic 3.6 and Deepgram Aura-2 return word timings (not on the pages read today).
- Azure HD per-language coverage of our ten languages.
- Any open model's speed on a T4, A10G or L4; any official EC2 cold-start figure for a TTS model.
- OpenAI's Service-Specific Terms were not read (the services agreement was).
- Quality of every provider in Spanish, French, German, Italian, Portuguese, Dutch, Polish and Finnish: the arena is English only.
