# Why Italian and Spanish sound flat, and what makes them good (2026-11-27)

The owner listened to the QA videos of 2026-11-27: German (Vicki, Daniel) sounds natural and expressive; Italian (Bianca) sounds "robotized"; the Spanish
voices "are not great". This is the investigation: what is really synthesised, what was measured, what was changed, and what to decide by ear.

Branch `voices-quality` (two commits, not merged, not deployed). Samples: `~/Downloads/videomk-looks/web/voices/` (21 MP3 and `voices_index.json`).

**Later the same day:** the owner decided speech stays on Polly, Spain keeps a Castilian voice (Sergio) and everyone else hears Lupe. Every other voice was
measured, the defaults of every language followed, and what the first QA videos with lively voices showed (length, register, music level) was fixed:
`docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md`. Sections 5 and 7 below (other providers, the open choice for Spain) are history.

## The answer in five lines

1. **Nothing falls back.** Italian, Spanish and German go through the same code and the stored audio is, sample for sample, Polly's generative engine.
2. **Polly's "generative" engine is two families of voices.** 18 voices are *steady*: the same audio every time, each sentence read alone, pitch movement
   no better than the neural engine. 37 are *lively*: a new take each time, the voice lifts for a question or a lively text, about twice the pitch movement.
3. **German's default is a lively voice (Vicki). Italian's (Bianca) and both Spanish defaults the owner hears (Lucia for Spain and anywhere outside the
   Americas, Mia for Latin America) are steady ones.** Bianca is the flattest of the 16 voices measured. That is the cause.
4. **Italian and Latin American Spanish have lively voices in Polly today** (Beatrice, Lorenzo; Lupe, Carlos): the branch makes Beatrice and Lupe the defaults.
   **Spain does not**: Lucia and Sergio are both steady. Spain needs the owner's ear: Sergio, a Latin American lively voice, or another provider.
5. **A second, separate loss affects every language:** the engine asked Polly for 16 kHz PCM, so nothing above 8 kHz ever reached a video. The branch asks for
   the engine's own 24 kHz.

## 1. What is really synthesised

Videos checked (QA, eu-west-1, read only): Italian `e65f7fc0` (Bianca), Spanish `132eb29b` and `65eaa9b9` (Lucia), `901331b5` (Lupe), German `13924af5`
(Vicki), `eb5aba9c` (Vicki and Daniel). Eleven more Spanish plans of the day were read for their voice only.

| Question | Finding | Evidence |
|---|---|---|
| Which engine? | `generative`, in `us-east-1`, for all three languages | `plan.tts` of every plan; `v2_plan` and `v2_beat` set no `POLLY_ENGINE`, so the code default applies; the speech cost recorded for the Italian video (0.0135 USD) is its 447 characters at the generative price |
| A silent fallback to neural or standard? | **No** | The first beat of the Italian and of a Spanish video was synthesised again from the plan's text with the generative engine: **bit-identical to the stored audio**. The same text with the neural engine is another waveform (correlation 0.07). Polly raises `EngineNotSupportedException` rather than switching engine, and `PollyTTS.synth` has no retry with another engine |
| The text sent | The beat's narration exactly as stored in the plan: plain text, no SSML, no `<prosody>`, no rate, no `LanguageCode` (not needed: these voices speak one language) | `beat_handler.make_audio` to `tts.PollyTTS.synth`; proven by the bit-identical result above |
| Sentence splitting | One request per beat (one to three sentences, 13 to 30 words), never per caption phrase | `plan.beats[].narration`; see section 3 for what that costs |
| Time-stretching to fit a length | **None.** Length is met by cutting sentences and by pauses between beats (`engine/length.py`); the audio is only trimmed of silence at both ends | `tts.synth_beat`, `audio.build_narration` |
| Sample rate | **16 kHz PCM from Polly, stretched to 24 kHz by linear interpolation.** Nothing above 8 kHz | `PollyTTS.PCM_RATE`; spectrum of the stored Italian beats: 99.9 percent of the energy below 7.7 kHz |
| Loudness | One pass of `loudnorm` (I -14, LRA 11) on the whole mix, then a limiter; AAC 192 kbps | `media.mix_audio`. The same for every language |
| Anything different for German? | **No difference in code.** The difference is the voice | Same handler, same settings in all six plans |
| Which voices the owner heard | Italian: Bianca. Spanish from the owner's account (region GB): **Lucia** in six videos, Pedro in one. The QA tester (region US) got Lupe | `plan.voices` of today's Spanish plans |

So the two robotic languages and the natural one differ in exactly one thing: the default voice.

## 2. Two families inside "generative"

Each of the 55 generative voices said one sentence twice. 18 returned the same audio both times; 37 returned two different takes:

- **Steady (18):** Andrés, Ayanda, Bianca, Céline, Daniel, Ewa, Gabrielle, Isabelle, Kajal, Laura, Léa, Liam, Lucia, Mia, Ola, Pedro, Rémi, Sergio.
- **Lively (37):** every other voice, among them Vicki, Tina, Lennart, Hannah, Sabrina, Beatrice, Lorenzo, Lupe, Carlos, Ruth, Amy, Brian.

The steady list is **exactly** the list of voices Polly does not offer in eu-west-2 and ca-central-1 (`voice_data.PARTIAL_REGIONS`): Amazon itself deploys
them as a separate group. Amazon does not document the split; "two families" is our reading of three measurements that agree:

| Behaviour | Steady (Bianca, Lucia, Mia) | Lively (Beatrice, Lupe, Vicki) |
|---|---|---|
| Same text twice | identical audio | a different take (Beatrice, three takes: spread 6.3 to 6.7 st, median pitch 191 to 224 Hz) |
| Whole paragraph against one sentence per request | no change at all (Bianca 2.93 / 2.93 / 2.93 st): each sentence is read alone | the paragraph is livelier (Beatrice 6.6 st whole, 6.0 in pairs, 5.5 sentence by sentence) |
| A lively text against a plain one | the voice stays where it is (Bianca's median pitch 194 to 195 Hz, Mia 211 to 211) | the voice lifts (Beatrice 168 to 224 Hz, Lupe 216 to 258, Vicki 192 to 213) |
| Against the same voice in the **neural** engine | no livelier: Bianca 2.8 / 2.9 st generative, 3.1 / 3.0 neural; Lucia 3.2 / 3.3 against 3.6 / 3.5; Mia 3.0 / 3.2 against 3.7 / 3.8 | n/a (most have no neural version) |
| `<prosody rate="108%">` | ignored by Bianca and Lucia (identical measures) | applied (Beatrice 164 to 173 words a minute) |

A steady "generative" voice is, for expression, a neural voice at the generative price. Daniel, the German man the owner also liked, is the liveliest of the
steady family (3.8 / 4.3 st), which is why German passed with both voices.

## 3. Measurements

Two passages per language, written for this test (in `voices_index.json`): an explanation of why the sky is blue (about 60 words) and a children's passage
with two questions and three exclamations (about 65 words). Each voice, one request per passage, MP3 24 kHz. Measured with a small autocorrelation pitch
tracker (numpy, 10 ms frames) and the engine's own word aligner. "st" is semitones. *Pitch spread* is the standard deviation of pitch around the voice's
median; *range* is the 5th to 95th percentile span; *question ending* is the pitch of the end of a question against the body of the same sentence (positive =
rises); *exclamation peak* is how far above the voice's median an exclamation reaches. Ranked by pitch spread inside each language.

**Italian**

| Voice | Locale | Family | Pitch spread (st): explanation / children | Pitch range 5-95% (st) | Median pitch (Hz) | Question ending (st) | Exclamation peak (st) | Loudness spread (dB) | Words per minute | Pauses in the children's passage |
|---|---|---|---|---|---|---|---|---|---|---|
| Lorenzo | it-IT | lively | 5.0 / 6.8 | 15.3 / 20.9 | 116 / 136 | +1.1 | +9.7 | 4.4 / 4.7 | 164 / 165 | 8 x 0.39 s |
| Beatrice | it-IT | lively | 5.0 / 6.6 | 15.6 / 19.5 | 168 / 224 | +7.5 | +10.9 | 4.2 / 4.5 | 160 / 164 | 8 x 0.28 s |
| Bianca (default) | it-IT | steady | 2.8 / 2.9 | 9.2 / 9.6 | 194 / 195 | -1.9 | +5.9 | 3.1 / 3.5 | 165 / 134 | 11 x 0.45 s |
| OpenAI gpt-realtime-2.1-mini cedar | n/a | n/a | 4.1 / 2.9 | 13.9 / 10.1 | 136 / 129 | -3.8 | +5.1 | 3.9 / 3.8 | 155 / 138 | 15 x 0.45 s |
| OpenAI gpt-realtime-2.1-mini marin | n/a | n/a | 3.7 / 3.8 | 12.4 / 13.1 | 181 / 178 | -2.0 | +6.0 | 3.8 / 3.7 | 155 / 139 | 18 x 0.40 s |
| OpenAI gpt-4o-mini-tts cedar | n/a | n/a | 3.4 / 2.9 | 11.8 / 10.1 | 152 / 148 | -3.9 | +4.0 | 4.3 / 4.5 | 147 / 137 | 17 x 0.46 s |
| OpenAI gpt-4o-mini-tts coral | n/a | n/a | 2.9 / 3.3 | 10.2 / 11.0 | 190 / 220 | -8.9 | +4.7 | 4.7 / 4.3 | 140 / 134 | 18 x 0.41 s |
| OpenAI gpt-4o-mini-tts marin | n/a | n/a | 2.9 / 2.4 | 9.8 / 8.0 | 189 / 191 | -0.9 | +3.8 | 4.2 / 4.0 | 141 / 139 | 16 x 0.43 s |
| OpenAI gpt-4o-mini-tts nova | n/a | n/a | 2.5 / 3.0 | 8.4 / 10.5 | 170 / 194 | -3.5 | +4.9 | 4.5 / 4.6 | 146 / 141 | 16 x 0.38 s |

**Spanish (Spain)**

| Voice | Locale | Family | Pitch spread (st): explanation / children | Pitch range 5-95% (st) | Median pitch (Hz) | Question ending (st) | Exclamation peak (st) | Loudness spread (dB) | Words per minute | Pauses in the children's passage |
|---|---|---|---|---|---|---|---|---|---|---|
| Sergio | es-ES | steady | 3.9 / 4.0 | 12.8 / 13.5 | 91 / 100 | +6.7 | +7.7 | 3.8 / 3.8 | 195 / 171 | 15 x 0.32 s |
| Lucia (default) | es-ES | steady | 3.2 / 3.3 | 10.6 / 11.7 | 194 / 197 | +7.1 | +7.4 | 3.8 / 3.9 | 194 / 159 | 12 x 0.47 s |
| OpenAI gpt-realtime-2.1-mini cedar | n/a | n/a | 4.0 / 4.4 | 11.9 / 14.7 | 140 / 148 | +3.4 | +8.7 | 3.6 / 3.8 | 180 / 168 | 14 x 0.40 s |
| OpenAI gpt-realtime-2.1-mini marin | n/a | n/a | 3.6 / 3.8 | 11.9 / 12.3 | 188 / 188 | +0.1 | +8.5 | 3.7 / 3.3 | 162 / 174 | 9 x 0.49 s |
| OpenAI gpt-4o-mini-tts cedar | n/a | n/a | 3.4 / 3.3 | 10.4 / 10.4 | 142 / 141 | +3.2 | +6.1 | 4.3 / 4.2 | 154 / 156 | 16 x 0.43 s |
| OpenAI gpt-4o-mini-tts coral | n/a | n/a | 3.3 / 3.1 | 11.3 / 9.8 | 210 / 218 | +8.4 | +4.8 | 4.4 / 4.2 | 140 / 137 | 19 x 0.43 s |
| OpenAI gpt-4o-mini-tts marin | n/a | n/a | 3.3 / 3.1 | 11.5 / 10.2 | 189 / 196 | -0.7 | +5.1 | 3.7 / 4.1 | 170 / 160 | 12 x 0.42 s |
| OpenAI gpt-4o-mini-tts nova | n/a | n/a | 2.8 / 2.8 | 9.5 / 9.7 | 170 / 176 | +0.5 | +2.7 | 3.8 / 4.2 | 152 / 144 | 17 x 0.41 s |

**Spanish (Latin America)**

| Voice | Locale | Family | Pitch spread (st): explanation / children | Pitch range 5-95% (st) | Median pitch (Hz) | Question ending (st) | Exclamation peak (st) | Loudness spread (dB) | Words per minute | Pauses in the children's passage |
|---|---|---|---|---|---|---|---|---|---|---|
| Lupe (default) | es-US | lively | 5.0 / 5.2 | 15.6 / 16.4 | 216 / 258 | +0.9 | +8.7 | 4.2 / 4.4 | 168 / 168 | 10 x 0.39 s |
| Carlos | es-US | lively | 4.0 / 5.8 | 13.9 / 18.8 | 110 / 128 | +10.5 | +11.7 | 4.5 / 4.5 | 185 / 190 | 10 x 0.27 s |
| Pedro | es-US | steady | 3.3 / 4.2 | 11.3 / 13.9 | 96 / 104 | +3.5 | +9.9 | 3.4 / 3.3 | 188 / 168 | 15 x 0.30 s |
| Andres | es-MX | steady | 3.4 / 3.9 | 11.6 / 12.8 | 95 / 104 | +3.7 | +7.6 | 3.4 / 3.2 | 182 / 173 | 15 x 0.30 s |
| Mia (default) | es-MX | steady | 3.0 / 3.2 | 10.5 / 11.1 | 211 / 211 | +5.2 | +7.2 | 3.1 / 3.3 | 176 / 147 | 14 x 0.41 s |
| OpenAI gpt-realtime-2.1-mini cedar | n/a | n/a | 4.3 / 4.6 | 13.7 / 15.7 | 148 / 144 | -6.1 | +6.3 | 3.7 / 3.8 | 182 / 160 | 17 x 0.37 s |
| OpenAI gpt-realtime-2.1-mini marin | n/a | n/a | 2.9 / 3.3 | 9.7 / 10.9 | 187 / 206 | +2.6 | +6.2 | 3.6 / 3.3 | 176 / 173 | 10 x 0.45 s |
| OpenAI gpt-4o-mini-tts cedar | n/a | n/a | 3.2 / 3.6 | 10.5 / 11.2 | 141 / 155 | -2.9 | +5.3 | 3.9 / 4.2 | 146 / 143 | 17 x 0.43 s |
| OpenAI gpt-4o-mini-tts coral | n/a | n/a | 3.2 / 2.8 | 10.5 / 9.0 | 183 / 211 | -1.2 | +4.5 | 4.2 / 3.8 | 145 / 139 | 16 x 0.39 s |
| OpenAI gpt-4o-mini-tts marin | n/a | n/a | 2.9 / 3.2 | 9.8 / 10.3 | 197 / 218 | -1.8 | +4.5 | 3.6 / 3.6 | 151 / 146 | 13 x 0.47 s |
| OpenAI gpt-4o-mini-tts nova | n/a | n/a | 2.5 / 2.4 | 8.1 / 8.2 | 170 / 182 | -0.0 | +4.9 | 3.8 / 3.9 | 157 / 155 | 13 x 0.46 s |

**German (reference)**

| Voice | Locale | Family | Pitch spread (st): explanation / children | Pitch range 5-95% (st) | Median pitch (Hz) | Question ending (st) | Exclamation peak (st) | Loudness spread (dB) | Words per minute | Pauses in the children's passage |
|---|---|---|---|---|---|---|---|---|---|---|
| Lennart | de-DE | lively | 3.7 / 6.3 | 12.0 / 21.4 | 108 / 151 | +7.6 | +10.8 | 4.2 / 4.5 | 185 / 185 | 11 x 0.31 s |
| Vicki (default) | de-DE | lively | 3.6 / 5.6 | 11.4 / 16.1 | 192 / 213 | +7.9 | +11.7 | 3.7 / 4.5 | 172 / 170 | 9 x 0.29 s |
| Sabrina (default) | de-CH | lively | 3.9 / 5.0 | 12.2 / 14.5 | 186 / 204 | +4.3 | +10.7 | 4.3 / 4.3 | 168 / 156 | 14 x 0.37 s |
| Tina | de-DE | lively | 3.3 / 5.0 | 10.5 / 14.8 | 184 / 209 | +9.5 | +10.8 | 3.4 / 4.0 | 155 / 165 | 9 x 0.32 s |
| Daniel | de-DE | steady | 3.8 / 4.3 | 12.9 / 14.6 | 100 / 107 | +3.2 | +10.3 | 3.6 / 3.8 | 185 / 155 | 15 x 0.31 s |
| Hannah (default) | de-AT | lively | 2.5 / 4.4 | 8.2 / 13.0 | 192 / 217 | +7.3 | +8.1 | 3.8 / 4.4 | 188 / 177 | 11 x 0.32 s |

Reading it:

- **Italian.** Bianca is last by a wide margin: half the spread of Beatrice and Lorenzo, her questions *fall* (-1.9 st), her exclamations reach half as
  high, and on the children's passage she slows to 134 words a minute with long pauses (0.45 s). Beatrice and Lorenzo are livelier than every German voice.
- **Spain.** Only two voices, both steady. Sergio moves more than Lucia (3.9 / 4.0 against 3.2 / 3.3) and that is all Polly has.
- **Latin America.** Lupe and Carlos are lively; Mia, Andrés and Pedro are steady. Mia is the second flattest voice measured.
- **Are the defaults the most expressive available?** German: yes in practice (Vicki; Lennart is a little above). Italian: no, the least. Spain: no (Sergio),
  but nothing lively exists. Latin America: no for MX and the rest of Latin America (Mia), yes for US viewers (Lupe).
- **The QA videos agree with the test passages:** Bianca in the Italian video 2.8 st, Lucia in two Spanish videos 3.6, Lupe 4.7, Vicki 4.0 (narration) and
  5.5 (dialogue), Daniel 4.3.

Limits of these numbers: pitch movement is not the same thing as sounding natural (a voice can move a lot and still sound wrong), nobody listened, each
lively voice was measured on one take (takes differ by about 0.3 st of spread), and the question and exclamation columns rest on two and three sentences.
They say which voices are flat with confidence; which lively voice is *best* is for the owner's ear.

## 4. What Polly offers inside the generative engine

Read from the AWS documentation on 2026-11-27 (`supportedtags`, `prosody-tag`, `generative-voices`, `API_SynthesizeSpeech`) and tried:

| Lever | Documentation | Measured |
|---|---|---|
| `<emphasis>`, `<prosody pitch>`, `amazon:effect` (drc, whisper, soft, timbre), newscaster style, auto-breaths | not available on generative | each one is refused with `InvalidSsmlException: Unsupported Generative feature`. **There is no tag that adds expression** |
| `<prosody rate / volume>` | "partial"; around whole sentences only | rate 108 percent: applied by Beatrice, ignored by Bianca and Lucia. Speed, not expression |
| `<s>`, `<p>`, `<break>`, `<lang>`, `<sub>`, `<say-as>`, `<w>` | available | `<s>` and `<p>` change nothing for the steady voices; for Beatrice they behave like splitting the request (a little less lively) |
| Whole paragraph against sentence by sentence | not documented | steady voices: no effect. Lively voices: more text in one request is livelier (table in section 2). Our beats (one to three sentences) sit between the two |
| Punctuation and wording | not documented | the strongest lever on a lively voice: the explanation rewritten with a question, two exclamations and shorter sentences took Beatrice from 5.0 to 6.8 st and lifted her median pitch 7 st; Lupe 5.0 to 5.4 and 5 st. On Bianca 2.8 to 3.1, on Mia nothing. Sample `voice_it_7` |
| Other engines | long-form exists for Spanish (Spain) only: Alba, Raúl, at 100 USD per million characters | Alba is the flattest voice of the whole study (2.0 / 2.5 st); Raúl 3.7 / 4.4, no better than Sergio at 3.3 times the price. Neural: see section 2. **No engine helps** |
| Sample rate | PCM: 8 or 16 kHz only. MP3 and OGG: up to 48 kHz; generative default 24 kHz | PCM 16 kHz: nothing above 8 kHz. MP3 or OGG at 24 kHz: speech up to about 11 kHz (energy above 8 kHz: -19 dB). 48 kHz adds nothing (the model makes 24 kHz). Below 7 kHz the MP3 is the same waveform as the PCM (25.7 dB match; OGG 22.7) |
| Speech marks (word times) | not available on generative | not needed: `engine/align.py` times the words from the audio |

Conclusion: inside Polly the delivery is decided by **which voice** (family), then by **how the script is written**, then a little by **how much text goes
in one request**. Tags do nothing.

## 5. Other providers

Tested with the key already in QA's parameter store (`/videomk/openai_api_key`). No Google or Gemini key exists in QA's parameter store or on this machine
(the laptop has a personal `gcloud` login for an unrelated project: not used). Nothing was signed up for.

**OpenAI, tested.**

- `gpt-4o-mini-tts` (the model `engine/tts.OpenAITTS` already calls), voices marin, cedar, coral, nova, with a style instruction written in the language
  asking for a native accent and a lively narrator: pitch spread 2.4 to 3.6 st. **No livelier than Bianca, Lucia and Mia**, and slower (134 to 170 words a
  minute). And OpenAI's deprecations page lists `gpt-4o-mini-tts`, `tts-1` and `tts-1-hd` for **shutdown on 2027-01-06** (read twice on 2026-11-27).
- `gpt-realtime-2.1-mini` (the replacement OpenAI names; Realtime API over a websocket, not `/v1/audio/speech`), told to read the text word for word:
  cedar 4.0 to 4.6 st in Spanish and 2.9 to 4.1 in Italian, marin 2.9 to 3.8. Better than the steady Polly voices, **below Beatrice, Lorenzo, Lupe and Carlos**. In 12 readings it
  **dropped a word once** ("las demás" became "demás"), which would put a word in the captions that is not spoken. Billed 20 audio tokens a second: 0.025 USD
  a minute for these samples (0.0085 to 0.0116 USD each), measured from the usage the API returned. 5.5 to 9.7 s to return a 20 to 27 s passage.
- Word times: none from either model. The engine does not need them (`engine/align.py` works from the audio: confidence 1.0 on all 36 OpenAI passages).
- Whether its Italian and its Castilian sound native cannot be measured here: samples 4 to 6 of each language.

**Not tested (no key). Facts read from each provider's own pages on 2026-11-27 by a research pass through a summarising fetch tool: check before relying
on one. Price per minute at 950 characters a minute.**

| Provider and model | Price | Per minute | Italian, Spanish | Word times | Notes |
|---|---|---|---|---|---|
| Amazon Polly generative (today) | 30 USD per million characters | 0.0285 | it-IT, es-ES, es-MX, es-US | none (we align from audio) | |
| Google Gemini 3.8 Flash TTS | 9 USD per million audio tokens until 2026-12-31, 18 from 2027-01-01 (25 tokens a second) | 0.0135, then 0.027 | both listed, no locale choice documented | not documented | style prompt and inline tags. The 2.5 preview model `engine/tts.GeminiTTS` names is listed for shutdown on 2026-12-18 |
| Google Cloud Chirp 3 HD | 30 USD per million characters | 0.0285 | it-IT, es-ES, es-US (no es-MX) | none (no `<mark>`) | |
| Azure neural HD (DragonHD) | 22 USD per million characters | 0.021 | it-IT (Isabella, Alessio), es-ES and es-MX (Ximena, Tristan) | documented for the "Omni" variant only | no `<prosody>` on HD |
| ElevenLabs v3 / v4 / Multilingual v2 | 80 USD per million characters | 0.076 | both; accent by voice | characters, from a separate endpoint | 2.7 times today's price |
| ElevenLabs Flash class | 40 USD per million characters | 0.038 | both | same | |
| Cartesia Sonic 3.6 | 37 to 50 USD per million characters by plan | 0.036 to 0.048 | both; a locale field exists | words (SSE endpoint) | monthly plan |

## 6. What was changed (branch `voices-quality`, from `origin/ccr-3c41ecff-680028`)

**Commit 1: the full band.** `engine/tts.PollyTTS` asks for MP3 at 24 kHz and decodes it with the ffmpeg the render already ships (24 kHz is the narration
rate: no resampling). New plans record `tts.rate: 24000` (`POLLY_SAMPLE_RATE` to override) and the rate is part of the audio cache key; plans made before
keep 16 kHz PCM and their keys, so an edit of an old video never mixes two sounds. If the decode fails the beat falls back to PCM and prints
`polly_fullband_fallback`; `engine_selftest` now reports `decode_mp3`. Checked against Polly through the real code path: energy above 8 kHz goes from
nothing real to -19 dB. This is for every language, German included: samples `voice_de_1` (today) and `voice_de_2` (full band) are the same take.

**Commit 2: the defaults.** `engine/voices.py`: Italian Bianca to **Beatrice**; Latin America Mia to **Lupe** (already the US default); "Latin American" asked
in a brief now prefers es-US; a Mexican accent asked by name is still Mia or Andrés. `voices.STEADY` records the 18 steady voices and why.
`engine/length.py`: a length fit for Beatrice (she takes 0.88 of Bianca's time) and Italian words per second 2.59 to 2.85. Spain is **not** changed.

Tests: `tests/test_voice_quality.py` (new, 5 tests) and the expectations of `test_languages.py` and `test_engine.py` that named the old defaults. Run:
`test_voice_quality`, `test_languages`, `test_length_fit`, `test_presenters`, `test_engine`: all pass. The whole suite was not run (the laptop's limit).

## 7. Recommendation

| Language, region | Today | Recommended | Why |
|---|---|---|---|
| Italian | Bianca | **Beatrice** (man: Lorenzo) | twice the movement, questions rise; same price. In commit 2 |
| Spanish, Latin America (MX and the rest) | Mia | **Lupe** (man: Carlos) | the only lively Spanish voices in Polly; Lupe is already what US viewers get. In commit 2. To confirm by ear: Lupe's accent is Polly's "US Spanish", not Mexican |
| Spanish, US | Lupe | Lupe | no change |
| Spanish, Spain | Lucia | **owner's choice between three, after listening** | (a) Sergio: Castilian, a little livelier, still steady (`es-ES_2`); (b) Lupe or Carlos: lively, Latin American accent (`es-ES_3`); (c) another provider for Spain only |
| Spanish, anywhere else (the owner's own videos: region GB) | Lucia | the same decision as Spain; if a Latin American accent is acceptable there, Lupe is a one-line change | |
| German | Vicki | Vicki | no change |

Synthesis changes, in order of value:

1. Ship both commits (after the owner has heard `it_1` against `it_2`, `es-LA_1` against `es-LA_2`, `de_1` against `de_2`).
2. **Write for the voice.** On lively voices the script is the strongest lever (section 4). The director prompt for narration should ask for spoken rhythm:
   a real question where one fits, an exclamation where it is earned, a short sentence after a long one. Not done here: it changes every video and needs
   the owner's ear on `voice_it_7` first (it may be too excited for an explainer).
3. Consecutive beats of one speaker could be synthesised as one request and cut at the pauses, for a little more liveliness on lively voices (about 10
   percent of spread). Not done: it breaks per-beat caching and cheap single-beat edits for a small gain.
4. The steady voices are also hard-wired elsewhere: the Spanish voices of the presenter characters (`presenter_policy.CAST`: Mia, Lucia) and, by the same
   split, other languages' defaults (French Léa where Ambre and Florian are lively; Indian English Kajal where Kiara and Arjun are; Dutch Laura, Polish Ola,
   Canadian and Belgian French have no lively alternative). French was not measured here: measure, listen, then switch.

**Should Italian and Spanish move to another provider?** Italian and Latin American Spanish: **no**. The best voices measured for both are already in Polly
at today's price, with the catalogue, the cast and the timings untouched. Spain is the open case: Polly has no lively Castilian voice. OpenAI is not the
answer on today's evidence (its current speech models end on 2027-01-06; the replacement is livelier than Lucia but below Polly's lively voices, can drop a
word, and needs a websocket client). If the owner rejects both Sergio and a Latin American accent for Spain, the candidates to test next, each needing a key,
are Azure DragonHD es-ES (cheaper than Polly) and Gemini 3.8 Flash TTS (cheaper until its price doubles in January), then ElevenLabs (2.7 times the price).

Cost per minute of video narration:

| | Before | After |
|---|---|---|
| Italian | Bianca 0.026 USD | Beatrice 0.029 USD (she speaks faster: more characters in a minute) |
| Latin America | Mia 0.025 USD | Lupe 0.027 USD |
| Spain | Lucia 0.028 USD | Sergio 0.030; Lupe 0.027; OpenAI Realtime 0.025; Azure HD 0.021 (not tested); ElevenLabs v3 0.076 (not tested) |
| Full band | | no change: the same characters |

What another provider would break, for the record: the 55-voice catalogue and the resolver are Polly's (`voices.beat_voice` gives every speaker the one
plan-wide voice on any other provider, so a dialogue loses its distinct voices until a cast is built for that provider); the length fits (`length.RATES`) are
per Polly voice; plan limits and cost reporting assume price per character (OpenAI and Gemini bill audio tokens); text leaves AWS; a model that reads
"word for word" by instruction can still change a word. Timings do not break: they come from the audio.

## 8. Not verified

- **How any of this sounds.** Every claim here is a measurement; the samples are for the owner.
- Accent quality of the OpenAI voices in Italian and Castilian.
- That the Lambda's ffmpeg decodes MP3: it is the `imageio-ffmpeg` build and `engine_selftest` now checks it, but nothing was deployed or invoked. If it
  cannot, videos still render, at 16 kHz, with `polly_fullband_fallback` in the log.
- The whole test suite (five files were run).
- Gemini, Chirp 3 HD, Azure, ElevenLabs, Cartesia: no key, nothing synthesised. Their prices and dates were read once through a summarising tool.
- Amazon's reason for the two families: not documented; the split itself is measured.

## 9. Spend

1.46 USD of the 3 USD limit: Polly generative 1.00, Polly long-form 0.14, Polly neural 0.04, OpenAI `gpt-4o-mini-tts` 0.15 (estimated from audio length),
OpenAI Realtime 0.12 (from the usage returned). Ledger: one line per request, kept with the lab scripts in the session scratchpad.
