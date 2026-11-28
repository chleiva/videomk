# Characters that speak different languages in one video: diagnosis and design (2026-11-27)

Status: analysis and design only. Nothing was built, deployed or run. Requirement R169. Branch `multilingual-design`, written against `ccr-3c41ecff-680028`.
Read this together with `docs/LANGUAGES.md`, `docs/VOICE_QUALITY_IT_ES_2026-11-27.md`, `docs/ART_DIRECTION.md`, `docs/CREATE_API.md` ("Video look") and `docs/PLANS.md`.

## 1. What happened in the owner's video

### 1.1 The video

Searched the QA videos table (all accounts) for requests from 25 to 27 November that mention languages, characters or speaking. One request matches the owner's description, made at 22:11 UTC on 27 November by the admin tester account:

- `video_id` `e4db46c1-f31d-509c-9d14-4a4541e92af3`, status COMPLETE, 121 s, 15 beats, 9:16, cost $0.1018 (script $0.0580, speech $0.0438).
- Request (dictated, so rough): "video for children of speaking in different languages okay so can we English Italian Spanish German French and talk about topic that is really important for children so".
- Title the planner wrote: "Hola, Hello, Ciao: ¡hablar muchos idiomas!". Cast `parrot` (Paco) and `turtle` (Tula), look `cartoon`, recipe `conversation`, chosen by the person (`look.by = "you"`).

It is the only video in the window that asks for several languages; I cannot prove it is the one the owner means ("different cartoon characters speak in different languages"), but its result is exactly what he describes. A second request check at 22:15:57 UTC (`BRIEF_CHECK ... unsupported=True`) produced no video, so it was declined. I cannot see its text; if it was a retry in other words ("a French fox and a German bear ..."), see 1.3 step 2.

### 1.2 What the plan and the timeline contain

From `generation/v2/<id>/plan_r1.json` and `timeline_r1.json` on the QA bucket:

- `language: "es"` for the whole plan; `region: "GB"`; `tts` is Polly generative, no language code anywhere.
- `voices: {"parrot": "Pedro", "turtle": "Lupe"}`: both Spanish (es-US) voices.
- Every one of the 15 lines is Spanish. The other languages appear only as quoted vocabulary inside Spanish sentences, for example beat 4 (turtle): "En inglés se dice hello. Y para decir gracias, se dice thank you. Repite conmigo: hello, thank you.", beat 6: "En italiano dicen ciao, ... grazie.", beat 8: "En alemán se dice hallo ... danke.", beat 10: "En francés se dice bonjour ... merci". The parrot answers "¡Hello! ¡Thank you!", "Ciao, grazie.", "¡Hallo! ¡Danke!", "Bonjour, merci." Pedro and Lupe therefore read "hello", "ciao", "danke", "bonjour" with Spanish phonetics: the owner's "Spanish voice trying to speak other languages".
- `captions: false` in the request options, so no caption text was on screen; the only text was the card headings, all Spanish ("¿Cómo se dice hola?").
- Description and sources are Spanish (two Spanish Wikipedia pages).

### 1.3 Why, step by step (file and line, branch `ccr-3c41ecff-680028`)

1. **One language was fixed before the writer started.** The request carried `options.language = "es"` (field of the create request, `request_json` on the video row; the app's narration-language row, `OptionsSheet.kt:118`, offers "same as description" or an explicit language; the app was set to Spanish or the client sent it). An explicit language wins: `engine/director.py:42` runs `lang_mod.detect(prompt, ...)` only `if language not in voices.enabled()`. The request is English, so "auto" would have given English; either way the plan has exactly one language (`plan.py:896` `"language": language`), as the product contract says (`docs/LANGUAGES.md`). Nothing in `engine/language.py` can return two languages (`detect` returns one code; `heuristic` at `language.py:30-48` counts common words of one language).
2. **The request check did not refuse or change the intent, but it is not prepared for it.** The log line for this request is `BRIEF_CHECK ms=591 source=model block=False unsupported=False questions=0` (CloudWatch `/aws/lambda/video_brief`, 22:11:01). The prompt (`common/intake.py:198-213`) says the app makes videos "in English or Spanish" (the stage's languages are substituted at `intake.py:232-240`) and declares unsupported only "a request ... written for a language other than English or Spanish" (kind `language`). A request written in English that asks for French lines passes; a request written in French passes only when French is enabled. The check never reads "several languages in one video" as a feature, so it neither flags nor routes it. Nothing normalised the intent here; it was simply never represented.
3. **The writer was told to use one language and the dialogue contract has no language.** `engine/plan.py:164`: "write EVERYTHING viewers read or hear (title, description, narration, scene text) in Spanish". The cartoon conversation block (`engine/art_direction.py:287-300`) says "one beat is ONE line of one character ... first person", and lists no language per speaker. With those two instructions the only way for the model to satisfy "speaking in different languages" was to make a language lesson in Spanish. The topic ("talk about a topic really important for children") was read as the subject "languages are good for children", which the model wrote about, not in.
4. **The voices are decided by the one language, after the model.** The model's own `voices` are replaced for every cartoon cast: `art_direction._enforce_cartoon` (`art_direction.py:~503-523`) sets `plan["voices"][c] = presenter_policy.voice_for(c, language, taken)` with `language = str(plan.get("language"))[:2]`; `presenter_policy.voice_for` (`presenter_policy.py:128-133`) picks from `CAST[cid]["voices"][language]`, hand-picked for English and Spanish only (Paco: Pedro; Tula: Lupe), else the resolver for the one language. There is no way for a speaker to have another language.
5. **The speech call cannot switch language either.** `tts.PollyTTS._ask` (`tts.py:127`) sends `VoiceId`, `Engine`, `TextType="text"` and the text, with no `LanguageCode` and no SSML (the voice study confirms this, `VOICE_QUALITY_IT_ES_2026-11-27.md:29`). Polly's generative voices are monolingual for the nine languages here (`voice_data.VOICES[...]["also"]` is empty for every one; only the three English-India voices have `hi-IN`). A monolingual voice given French text reads it with its own language's sounds. So even a correct French line given to Pedro would have been a Spanish accent. The only cure is a French voice for the French line.
6. **Everything downstream follows the one language:** length estimates and word budgets (`plan.py:352 words_per_s(language)`, `length.py:144 estimate_speech(..., plan.get("language"), voice)`), numbers (`numfmt.language_scope`), the end card (`timeline.py:178 made_with(plan.get("language"))`), the research (Spanish Wikipedia), the description labels (`finalize_handler.py:63`).

Root cause in one sentence: the system is built around ONE language per video, chosen before the script, and the script, the voices, the speech call and the captions all take that language; the request to have several languages was never captured as data, so the writer made a Spanish lesson and Polly's monolingual Spanish voices read the foreign words.

## 2. Design

### 2.1 Decisions in brief

1. The video keeps one **main language** (the viewer's: the request's language or the explicit option, exactly as today). New: each speaker may have its own **spoken language**; each line is written and spoken in its speaker's language.
2. Characters take turns in a cartoon conversation. Each speaker has its own voice IN ITS language, chosen by the existing resolver. No `<lang>` tags and no `LanguageCode` in stage 1: a separate voice per language is the reliable fix.
3. One script call writes the whole dialogue with every line tagged by speaker (the language follows the speaker), plus a one-line translation into the main language per line (optional).
4. Captions show each line in its own language; a smaller second line shows the translation in the main language, on by default (decision D3).
5. Stage 1 is explicit per-character languages in cartoon conversations of 2 to 3 characters; implicit and phrasebook ("greet in five languages") come later.

### 2.2 (a) How the request is understood

Three kinds of request, one extractor.

| Kind | Example | What is extracted |
|---|---|---|
| Explicit | "a French fox, a German bear and an Italian owl talk about the sea" | `speakers: [{character: fox, language: fr}, {character: bear, language: de}, {character: owl, language: it}]` |
| Implicit | "characters speaking different languages", "each one in their own language" | `languages: []` with `implicit: true`; stage 2 picks languages (see below) |
| Learning | "the parrot says hello in five languages", "teach children greetings in English, Italian, Spanish, German and French" | `mode: "phrasebook"`, `languages: [en, it, es, de, fr]` |

Where it runs: a new small module `engine/polyglot.py` (new file, no collision), called from `director.direct` right after the language is settled (`director.py:42`) and before `art_direction.decide`. Cheap and deterministic first, as `language.py` does: a regex over the nine language names written in the nine languages ("French", "francés", "französisch", "français" ...) and over "different languages", "each in their own language", "in X and Y". Only when that fires (almost no request) one small-model call (about $0.0005) returns `{"speakers": [{"character": "fox"|null, "language": "fr"}], "mode": "conversation"|"phrasebook", "main": "<code or null>", "translate": true|false|null}` in JSON. The same function must also be callable from the request check so the app can answer with a note ("Each character will speak its own language; French, German and Italian are available").

How the owner or the UX expresses it later: extend the create request `cast` entries. Keep the old form and accept an object form per entry:

```json
"cast": ["fox", {"id": "bear", "language": "de"}, {"id": "owl", "language": "it"}],
"translation": "auto" | "on" | "off"
```

Normalisation (`common/look_choice.py` `parse`, line 46-80): `cast` stays a list of ids (so `Direction.cast`, `art_direction`, tests and the Android client that sends strings are untouched) and the new optional map `cast_languages: {"bear": "de", "owl": "it"}` is returned beside it. Rules: a language must be in `voices.enabled()` and `READY` (else 400 with a Localized message, as `sf_launcher.py:129-135` does for `language`), at most 3 cast entries (already `MAX_CAST`), a language given for a character not in the cast is an error, `cast_languages` without a `cast` of at least 2 is accepted for 1 character only if it equals the main language (otherwise `"reason": "needs_two"` and a note: one character cannot take turns with itself in stage 1). `look_choice.resolve` returns the languages it will use (and `reason` when it changed them) so the picker can show "Fox: French" chips. Chips in the picker are a later UI task: the data contract above is all stage 1 needs. The request check prompt receives the same list in its form-values line (`intake.clean_options` keeps only known keys: add `cast_languages` there, otherwise the check cannot see the form's choice).

Implicit request ("different languages"): stage 2. Choose the languages from the stage's `enabled()` list excluding the main language first, in a fixed, kind order: the first character keeps the main language only if the request is a language-learning one; otherwise each character gets a different language, taken in the order [en, es, fr, de, it, pt, nl, pl, fi] filtered to languages with at least one voice that fits the character's gender (nl, pl, fi have no man's voice: give those to the women characters). The note tells the person which languages were chosen and why (`plan.look.note`-style, as looks do: "adapted is said, never refused").

### 2.3 (b) Plan schema and the script writer

Additive, optional fields only; a plan without them is a plan of today.

```json
{
  "language": "en",                       // main language: unchanged meaning (the viewer's; title, description, sources, end card, card headings)
  "polyglot": {"mode": "conversation", "translate": true,
               "speakers": {"fox": "fr", "bear": "de", "owl": "it"}},   // present only when more than one language is spoken
  "voices": {"fox": "Remi", "bear": "Lennart", "owl": "Lorenzo"},        // unchanged shape: one voice per speaker, now in the speaker's language
  "beats": [{"speaker": "fox", "lang": "fr",                               // lang optional: defaults to polyglot.speakers[speaker]
             "narration": "Bonjour ! Aujourd'hui, on parle de la mer.",
             "translation": "Hello! Today we talk about the sea.",        // optional, in the main language
             "scene": {...}}]
}
```

- `plan.language` stays the main language so everything that is not a spoken line (title, description, end card, chapter titles, research language, numbers on cards) is unchanged. A helper `plan_langs.beat_lang(plan, beat)` (new file) returns `beat["lang"] or polyglot.speakers.get(speaker) or plan["language"]`; every place that read `plan.get("language")` for a line goes through it (list in 2.6).
- The voice map keeps its shape because a speaker has one language in conversation mode. Phrasebook mode (one character, several languages) adds `polyglot.voice_by_lang: {"parrot": {"fr": "Remi", ...}}` and `beat_voice` (`voices.py:269-279`) looks there first (stage 3).
- The writer: **one call** for the whole dialogue, not one per speaker. A conversation is only coherent when the model sees both sides; one call per speaker would give lines that do not answer each other, and costs 2 to 3 times the input tokens (the notes are the large part). The prompt block of `art_direction.prompt_block` (line 287) gets a polyglot variant, written once in English:
  - "EACH CHARACTER SPEAKS ITS OWN LANGUAGE: fox speaks French, bear speaks German, owl speaks Italian. Write every line of a character ONLY in its language (no word of the other languages except a name or a word the line is about)."
  - "The characters understand each other: each line reacts to the previous one, in the speaker's own language, using words a child who does not speak that language could still follow from the tone and the picture (repeat a key word, name things, short sentences)."
  - "Also write for every beat `translation`: the same line in {main language}, one sentence per sentence, no commentary."
  - "Scene text (heading, points) of a beat is written in the language of the beat's speaker; the title, description and chapter titles are in {main language}."
  - Per-language line length: each line is 8 to 18 words today (`art_direction.py:~290`); with several languages the number of words changes with the language (`length.WORDS_PER_S`: Finnish 1.95 a second against French 3.03). So the prompt gives each character a line length in words computed from `CONVERSATION_BEAT_S` (6 s) times `plan.words_per_s(lang)` of its language ("fox: 15 to 20 words, bear: 12 to 16 words ..."), not one range for all.
- The "total words" and the length check (`plan.length_problem`, `long_problem`, `plan.py:375-430`) count words of one language. For a polyglot plan they must count seconds instead: sum of `length.estimate_speech(narration, beat_lang, voice)` over the beats against the target seconds. That function already takes a language and a voice; only the callers pass the plan language today. The rewrite loop (`plan.py:1010-1070`) is unchanged.
- Validation after the call: (1) every beat has a speaker in `polyglot.speakers`; (2) for each line a language check: `language.heuristic(line)` when it is sure (3 or more common words), else ONE batched small-model call for all unsure lines (about $0.001 per video); a line in the wrong language is rewritten once (the existing retry with the complaint appended, `plan.py:1067`); if still wrong, the line is kept and a warning recorded (`plan.warnings`), never silently dropped; (3) `translation` present for every line when `translate` is true, else the translation is requested once with a small call for the missing lines.
- The planner stage structure (`staged.generate` for long videos, per-section calls) needs the same block in each section prompt and the same per-speaker language; conversation beats are short (6 s), so videos up to about 3 minutes use `plan.generate_plan` in one call; staged generation is a stage-2 test.

### 2.4 (c) Voices

Voice per speaker is `voices.cast_voices` (`voices.py:~232-262`) called per speaker with the speaker's language instead of the plan's: a loop `for sid, lang in speakers: voices.resolve(want, lang, region, taken)`. `presenter_policy.voice_for(cid, language, taken)` already accepts any language (hand-picked list for en/es, resolver otherwise), so `_enforce_cartoon` only has to pass `beat language of the speaker` instead of `plan.language` (one expression at `art_direction.py:~518`). The `taken` list already stops two speakers sharing a voice when the language has enough voices.

Best lively voice per language, from `voice_data.py` and the voice study (lively family = not in `voices.STEADY`; new takes each time, more pitch movement; the steady family is smooth but flat). This is a recommendation for a default table, to be expressed as data in `presenter_policy` or `voices` and kept consistent with whatever the voices job decides; do not hard-code names in new code, call the resolver:

| Language | Woman | Man | Notes |
|---|---|---|---|
| en | Ruth, Joanna, Salli | Matthew, Stephen, Kenneth, Nate | plenty |
| es | Lupe (es-US) | Carlos (es-US), Pedro and Andres are steady | Spain has only Lucia and Sergio, both steady |
| fr | Ambre | Florian | Ambre and Florian are generative-only and lively; Lea, Gabrielle, Isabelle, Remi, Liam are steady |
| de | Vicki, Tina | Lennart | Daniel is steady |
| it | Beatrice | Lorenzo | Bianca steady; Italian has only these three voices |
| pt (Brazil) | Camila, Carolina | Leo | |
| nl | Lisa (nl-BE), Laura (steady) | none | two women only |
| pl | Ola, Ewa (both steady) | none | two women only |
| fi | Suvi | none | one voice in all |

Polly's bilingual voices: for these nine languages there is none. `voice_data.VOICES[*].also` is empty except `Arjun`, `Kajal`, `Kiara` (en-IN with hi-IN), which does not help here. The `<lang xml:lang="...">` tag is listed as available on generative by the voice study (`VOICE_QUALITY_IT_ES_2026-11-27.md:145`, read from the AWS documentation) but nobody has tried whether a monolingual generative voice changes its phonetics inside it, and Polly documents the tag per voice and language pair. I did not test it (the QA profile is read-only and no Polly synthesis was run; no paid spend at all in this analysis). A test that settles it costs under $0.01: six sentences (about 300 characters at $30 per million characters) with Lupe reading a French sentence inside `<lang xml:lang="fr-FR">`. Do it in stage 3, it only matters for code-switching words (2.9).

Character-to-language mapping:
- The person decides: "the owl is Italian" wins over everything. No character is "naturally" a language (the owl is Otto, the professor, in any language).
- When the request says only the languages ("a fox and a bear, one in French and one in German"), assign in the order the characters and the languages are named.
- When nothing is said: the first character keeps the main language unless the request is about learning; the others get languages in the kind order of 2.2. Prefer to give nl, pl, fi to women characters (they only have women's voices); the cast table carries each character's gender through its first English voice (`presenter_policy.voice_for`, line 132).
- Same language for two speakers: the resolver gives two different voices (`taken` in `cast_voices`), as for a Spanish conversation today. Italian, Dutch, Polish and Finnish have 3, 2, 2 and 1 voices: a third Italian speaker, a second Finnish one, share a voice with a note (the existing behaviour, `voices.py:~257`); the planner should not plan that: the intake note says so ("Finnish has one voice").
- Region: `voices.default_voice(language, region)` is for the narrator only; in a polyglot video the viewer's region does not decide a foreign voice (a GB viewer still gets a fr-FR voice for French). Brief wishes that name an accent ("a Canadian French fox") work through the existing resolver call because it receives the speaker's language.

### 2.5 (d) Captions and on-screen text

- All nine ready languages are Latin script and covered by Inter, Playfair Display, DejaVu Sans Mono and STIX (`docs/LANGUAGES.md` fonts row); a polyglot video of these nine needs no font work. Korean (and Hindi, Chinese, Japanese, Arabic) cannot be used: no Hangul (or other) glyphs in any font, `voices.READY` excludes `ko` for that reason. A request for them gets the existing note of languages that can.
- Captions come from the timeline's per-scene `words` (`timeline.py:144-161`), aligned from the audio and the line's text: each line's words are already in its own language and nothing else is needed for the first row.
- Translation line: `translation` is drawn as a smaller second row under the caption row for the duration of its line (one `draw_captions` extension in `scenes/captions.py`; it needs the line's text and start/end, not word timing, so no alignment is needed). It uses the same band as captions; the presenter layout already reserves that band when captions are on (`presenter.py:267-307`, `ctx.captions`).
- Which language is the translation in: the main language, which is the request's language (or the explicit option): a Spanish-speaking owner who writes in Spanish sees Spanish translations, an English request sees English. That is what makes the translation line unambiguous.
- Default: `translation: "auto"` means ON when the video has two or more spoken languages and the main language is not the line's language, and shown even if the person turned captions off (a video whose lines nobody understands is broken; the translation is the only text). The create option `captions=false` still turns off the caption row of lines in the main language (decision D3).
- Card headings and points are in the language of the beat's speaker (so "Bonjour" is on the card while the fox says it); the card heading of a line is not translated (the translation line already is).
- A small language marker (a flag-less two-letter chip "FR") next to the speaker is optional, stage 2. Flags are not used (a flag is a country, not a language).

### 2.6 (e) Word timing, cache, length, ducking, music

- `align.align_words(samples, sr, text)` is language-agnostic (syllable weights, `align.py:44`, cover all Latin vowels) and is given the line's own text; the accuracy figures per language are those of `docs/LANGUAGES.md` (Polish weakest, one word in 53 about 0.8 s late). No change.
- Audio cache: `plan.tts_hash` hashes provider, voice, style, text, engine, region and rate (`plan.py:487-498`). A different voice and a different text already make a different key, so nothing is added and old plans keep their hashes. Only if stage 3 starts sending a `LanguageCode` or SSML, that choice is appended to the hash parts the same way `engine` and `rate` were, only when set.
- Length fit: `length.rate_for(language, voice)` and `_measured` already scale from the VOICE's own language and one measured sentence (`length.py:54-72`); the lines of a polyglot plan must pass the line's language and voice: change `length.beat_seconds` (line 144) and `plan.tts_hash`-adjacent callers to `plan_langs.beat_lang(plan, beat)`. The budget of words per line uses `plan.words_per_s(lang)` (`plan.py:352`). `timeline.stretch_to` (the 1.6 s hold and sharing) works on measured seconds and is unchanged.
- Ducking and music: nothing depends on language. Turn-taking gaps between speakers of different languages should be 0.25 to 0.35 s (a handover between voices that do not share language rhythm sounds rushed at the conversation default); this is the existing `lead`/`tail` pause constants of `length._pauses`, not a new mechanism; judge it on the QA video before changing anything.
- Numbers: `numfmt.language_scope(timeline.language)` is one language per scene draw (`renderer.py:157`). A card in French inside an English video would show "3.3" instead of "3,3". Stage 1: scene draw uses the beat's language (the scope call takes `beat_lang`); the planner is also told numbers on cards follow the card's language (`plan.py:41-43` rules already say "write 3.3, the video shows it the way the viewer's language writes it"). Units (km, °C) are the same in all nine languages except that the speech is read by the line's voice, which reads "km" and "°C" in its own language: write units spelled out in the line ("kilómetros", "Grad Celsius") exactly as the existing quality rules ask for the single-language case.

### 2.7 (f) Research, end card, description, request check

- Research (`research.gather_notes`, Wikipedia of the language) uses the MAIN language: the notes are facts for the writer; the writer translates them into each line's language (the models do this well; Wikipedias of some languages are not needed). Names and numbers stay as in the notes.
- End card ("Made with VideoMK", `timeline.py:178`): the main language. Description and chapter labels (`finalize_handler.py:63`, `assets.credits_block`): the main language, and the description gets one added sentence naming the languages spoken ("Fox speaks French, Bruno speaks German ..."), written by the planner in the main language. Sources/credits: main language, as now.
- The request check prompt (`common/intake.py:198-213`): add one paragraph under SUPPORTED: "A video may have characters who speak different languages (French, German, Italian ... the languages above), each with their own voice, taking turns; the request being written in one language and asking for lines in others is NORMAL and is never `unsupported` and never a `block`. 'language' unsupported only means the request cannot be understood as one of the languages." The check should also return `polyglot: {"languages": [...], "mode": ..., "translate": ...}` in its JSON (the model reads the request anyway); the engine's `polyglot.py` extractor then needs no second call. If the person asks for a language outside the enabled set ("a Japanese owl"), the answer is a note with the nearest options, not a refusal of the video (as looks do): the video is made with the languages that exist and the note says which were dropped.
  - Note on the 22:15:57 declined request: until the request text is known, it is possible the check declined a polyglot request (a French or German phrase in an English request; the `kind: "language"` rule). Read `unsupported.kind` for that request id in the brief response log before building; it is the cheapest first step of stage 0.

### 2.8 (g) Same language twice, and the learning mode

- Same language twice: ordinary. Two speakers French, one German: three voices from the resolver (fr has men and women). The writer is told the language of each speaker, not "one per language".
- Phrasebook mode (`mode: "phrasebook"`): one character repeats the same sentence in each language, for language learning ("hello in five languages"). Two shapes, both with the contract above:
  - Host plus guests (recommended): one character in the main language (the host, the child's language) and up to two more characters, each speaking its own language, repeating the host's phrase ("In French we say: Bonjour! ... Bonjour!"). Five languages with three characters on screen is the limit: the guests rotate languages (see below).
  - One polyglot character (the parrot repeating in five languages): the picture is one character while the voice changes with every language (`polyglot.voice_by_lang`). It works for a parrot, which imitates; for a fox it is odd. This is stage 3 and an open decision.
- Five languages and two characters: the owner's request. The honest design: a cartoon cast is 2 or 3 characters, so five languages cannot be five characters. Options: (i) a guest character takes the languages in turn and its voice changes with each (`voice_by_lang`), clearly signalled by the language chip; (ii) limit to 3 languages and say so; (iii) five rounds, each round in a language with the same two characters speaking the same two sentences ("¡Hola! Hello! Ciao!" greeting) in the matching voices, each of the two characters keeping ONE voice and the one language of its own, with a separate narrator-less summary in the main language. Recommendation: (i) with a visible language chip, in stage 3; in stage 1 a request for more languages than characters is reduced to the characters' languages and said in a note.

### 2.9 (h) Limits

- Languages per video: at most 3 in stage 1 (one per character, `MAX_CAST` = 3); 5 in phrasebook mode (stage 3).
- Minimum length: `look_choice.CONVERSATION_MIN_SECONDS = 20` already; with languages the minimum is 6 s a line, so 3 languages need at least 30 s and 2 languages 20 s. A video shorter than that falls back to 2 languages and a note.
- Looks: cartoon conversation only (`recipe` `conversation` and `conversation_board`). Whiteboard narration has one voice and one language; "a whiteboard where different voices speak different languages" is out of scope: the look is adapted to a cartoon conversation when the request is polyglot and the look was not explicitly chosen as whiteboard; when the person chose whiteboard, the board stays and the lines become one language with the vocabulary quoted, with a note saying why. Footage (real) look: out of scope, same note.
- A single presenter (one character): no polyglot except phrasebook with `voice_by_lang` (stage 3).
- Plan tiers (`docs/PLANS.md`): no new tier rule. The cost of a polyglot video is the cost of a normal one plus about 15 percent (2.10), the length limits are those of the plan (Free 30 s: a 30 s polyglot video can have 2 languages, 3 would need 30 s and a minimum of 6 s a line: allowed exactly at 30 s). Free users are not blocked from the feature; it follows the plan's length cap.

### 2.10 Cost and latency

- Script: one extra output per line (`translation`, about the same words) adds about 40 percent to the output tokens of the dialogue; the dialogue is about a third of the script cost; the planner already costs $0.058 for 121 s (`c_script`). Expect +$0.01 to +0.02 per two minutes (about +$0.005 to +$0.01 per video minute), plus the optional language check call (about $0.001) and the optional extractor call ($0.0005 when it fires).
- Speech: Polly generative characters are the same text length as now: $0.0438 for 121 s, the same per minute. The translation is not spoken. Nothing else is billed.
- Latency: no extra step in the happy path (one script call, the same parallel speech); the extractor adds under 1 s only for polyglot requests; the language check adds about 1 s; a wrong-language rewrite adds one planner retry (about 10 to 20 s) only when it fires.

### 2.11 (j) Risks and how each is handled

| Risk | What happens | Handling |
|---|---|---|
| Names | "Paco" in a French line is read with French sounds; "Fox" is not a name in German | names of characters are written as in the cast table in every language; the writer is told to use them only as vocatives; judged on QA |
| Accent of a voice with another language's words | a Spanish voice must never read French text (the owner's case) | each line goes to a voice of ITS language: enforced in `beat_voice` and by a post-plan audit `voice_language == line_language` (new, like the existing plan audit); a mismatch is a bug, not a note |
| Code-switching inside one line ("Hola, how are you") | the speaker's voice reads the foreign words with its own accent | stage 1: the writer is told not to mix; the audit flags a line whose heuristic language is not its speaker's; stage 3: test `<lang xml:lang>` on generative (about $0.01) and use it only for words the line is about, only if it works for that voice and language pair |
| Polly SSML on generative | `<emphasis>`, `<prosody pitch>`, `amazon:effect` are refused with `InvalidSsmlException: Unsupported Generative feature` (study, line 143) | no SSML in stage 1 or 2 |
| Numbers and units | French "3,3", German "3,3", English "3.3" on cards; "km" read in the voice's own language | numbers on cards follow the beat's language (2.6); units spelled out in lines |
| Few voices | nl, pl, fi: women only; fi: one voice | character gender is a hint only; `voice_notes` records the substitution; the note tells the person |
| Quality of foreign text | nobody who speaks the languages has judged the writing (`LANGUAGES.md` limit 1) | QA proof with native-speaker review where possible; the translation line makes a wrong line visible |
| Coherence | each speaker answers in another language | one call, the "react to the previous line" rule, the translation line as a check; one planner retry if two lines in a row do not follow |
| Heuristic language check | short lines (under 4 words) give no verdict | batched small-model check for unsure lines |
| Collision with other work | see section 4 | stage 1 touches a few lines in shared files |

## 3. Staged plan

Effort assumes one engineer or agent who knows the repo; "day" means one working day including tests. All tests are plain pytest on the Mac (no heavy builds); the QA proofs are API requests on QA.

### Stage 0: check the request check (0.5 day, can run now)

- Read the brief-check response for the 22:15:57 request (`video_brief` logs and the `RequestIntakeSafetyTable`, read-only) and learn whether a polyglot request was declined as `kind: "language"`.
- Fix the wording of `common/intake.py:198-213` as in 2.7 (the paragraph only) and add `cast_languages` to `intake.clean_options`. Test `tests/test_intake*.py`: a request in English that asks for French and German lines is not unsupported and not a block (model stubbed); the form-values line carries `cast_languages`.
- Collides with nothing in the two running branches (intake is not touched by them).

### Stage 1: explicit languages per character, cartoon conversation (5 to 7 days). Shippable alone.

Behaviour: "a French fox and a German bear talk about the sea" (and the create request with `cast_languages`) makes a conversation in which each character speaks its own language with a voice of that language; captions in each language with a translation line in the main language; the title, description and end card are in the main language.

Work items:
1. `common/look_choice.py`: accept object entries in `cast` (`{"id", "language"}`), return `cast` (ids, unchanged) and `cast_languages`; validations of 2.2; `resolve` and `capabilities` carry the languages and the limits; pin tests in `tests/test_look_choice.py` (ids only: same as today; object form; unknown language; language for a character not in the cast; more than 3; one character; shorter than 30 s).
2. `engine/polyglot.py` (new): `extract(prompt, options, enabled, ask_small) -> Polyglot | None` (regex first, one model call when it fires; reads `options["cast_languages"]` first, which wins), `Polyglot` data class (speakers map, mode, translate, main), `block(...)` text for the writer, `languages_of(plan)`. Tests `tests/test_polyglot.py`: explicit, implicit, learning, form wins over words, language not enabled, nine-language names in nine languages, no false positive on "I want to learn French grammar" (one language, one video).
3. `engine/plan_langs.py` (new, 20 lines): `beat_lang(plan, beat)`, `speaker_lang(plan, sid)`.
4. `engine/director.py` (near line 42 and 91-96): call the extractor after the language is set; pass `polyglot` to `art_direction.decide/policies/prompt_block`; the main language is the existing one.
5. `engine/art_direction.py`: `Direction` gets `polyglot`; `prompt_block` (line 287) inserts the polyglot variant for conversations; `_enforce_cartoon` (lines ~503-523) passes each speaker's language to `presenter_policy.voice_for`; `Direction.summary()` records the languages. Overlaps: see section 4.
6. `engine/plan.py`: validation keeps `lang` and `translation` per beat and `polyglot` at plan level (`_validate_plan`, around lines 878-896); per-line language check and one retry; the length check by seconds for a polyglot plan (`length_problem`/`long_problem`); `tts_hash` unchanged. Tests: a plan of 12 beats in 3 languages passes; a French line in the German speaker's turn is rewritten once; a plan without `polyglot` produces byte-identical results to today (golden tests exist for plans).
7. `engine/length.py` (144, 255): `estimate_speech`/`beat_seconds` take the line's language. Test: a Finnish line of 14 words is estimated longer than a French line of 14 words with the same fit.
8. `engine/voices.py` (`beat_voice` unchanged in stage 1; `cast_voices` no change needed if `_enforce_cartoon` resolves per speaker): test that three speakers of fr, de, it get three voices of those languages, and that two French speakers get two different voices.
9. A plan audit rule `voice language equals line language` for every spoken beat (where the existing plan audit lives; `quality.py` or `plan.py`): hard failure in tests, a warning plus a repair (re-cast) in production.
10. Timeline and render: `timeline.py` carries `translation` per spoken scene; `scenes/captions.py` draws the second row (new function beside `draw_captions`, same band), `renderer.py:157` sets `numfmt.language_scope` from the beat's language. Test: a scene with a translation draws two rows within the caption band for 9:16 and 16:9, no overlap with the character feet (`presenter.py:267-307`).
11. `finalize_handler.py` description: one sentence naming the speakers' languages (written by the planner); end card unchanged.
12. `docs/LANGUAGES.md` (a section "Several languages in one video") and `docs/CREATE_API.md` (the `cast` object form, `translation`): the contract.

QA proof (stage 1), on QA with a Max/admin account, cartoon, 9:16 and 16:9, 60 s:
1. "A French fox, a German bear and an Italian owl explain why the sea is salty": three voices, each line in its language (read the plan: `beats[*].lang`, `voices`, `polyglot`), translation row visible (frame grabs at three times), audit passes, description names the languages.
2. The same with `cast_languages` in the request and a neutral prompt: the form wins.
3. English request with the owner's words ("a video with characters speaking different languages"): stage 1 does not pick languages by itself; it makes a normal English conversation and the note says "name the languages for each character" (stage 2 picks them). Check that nothing breaks and the note is shown.
4. Two speakers of the same language (fr, fr): two different French voices.
5. Dutch with a male-gendered character: a woman's voice and a note.
6. A regression run of the existing conversation and single-language videos in en and es: identical plan hashes and audio keys (no new audio is made for an unchanged plan).
Listening check by the owner (or a native speaker) on 3 samples: pronunciation of each line, turn-taking gaps, name pronunciation.

### Stage 2: implicit languages, more tests, whiteboard and short videos (3 to 4 days, after stage 1)

- Implicit requests ("different languages"): the kind-order assignment of 2.2 and the note.
- A whiteboard or footage request that is polyglot: adapt the look to a cartoon conversation, with the note (2.9).
- Staged generation (`staged.generate`, long videos) carries the polyglot block per section; test a 3-minute video.
- Language chip (two-letter) next to the speaker; the picker's data (`capabilities` already lists languages per character with voice counts: "Finnish: 1 voice").
- QA: the owner's own dictated request, 120 s, 3 characters; a 3-minute video; a whiteboard request.

### Stage 3: phrasebook and the polyglot character, `<lang>` test (4 to 6 days, after the voices job merges)

- `polyglot.mode = "phrasebook"`, host plus guests, up to 5 languages; `polyglot.voice_by_lang` and `beat_voice` change (a core `voices.py` function).
- Run the `<lang xml:lang>` test (under $0.01) and decide on code-switching words with a flagged list of voice and language pairs.
- QA: "the parrot teaches hello in five languages" (the owner's first request); check chips, five voices, translation lines.

Total honest range: stage 0 half a day, stage 1 five to seven days, stage 2 three to four, stage 3 four to six: about two weeks to everything, one week to the first shippable stage. Estimates carry the usual risk of the writer's output quality (prompt iterations) and of the render band for the translation row on 9:16.

## 4. Collisions with the running branches

`polly-lively-defaults` (voices, `voices.py`, `voice_data.py`, `presenter_policy.CAST`, `length.py`, script prompt) and `round2-followups` (whiteboard and on-demand fixes):

| File | Stage 1 change | Overlap |
|---|---|---|
| `engine/voices.py` | none in stage 1 (stage 3: `beat_voice`) | does not collide in stage 1 |
| `engine/voice_data.py` | none | none |
| `engine/presenter_policy.py` | none (voice_for already takes a language); the default table of 2.4 is data owned by the voices job | none if the voices job lands the cast table first; the polyglot design reads whatever `CAST[...]["voices"]` it has |
| `engine/length.py` | callers pass the beat's language (2 lines, `beat_seconds`, line 255) | collides with the length fits of the voices job: apply after that merge, or only change the two call sites |
| `engine/plan.py` (script prompt, `_validate_plan`) | new fields and a length check by seconds | the voices job edits the script prompt: the polyglot block is a separate function in `polyglot.py` appended where the other blocks are, so the conflict is one line |
| `engine/art_direction.py` | prompt block and `_enforce_cartoon` | `round2-followups` touches whiteboard parts of the same file: different functions; rebase |
| `common/look_choice.py`, `common/intake.py` | contract and prompt | nobody else is known to touch them |
| `scenes/captions.py`, `timeline.py`, `renderer.py` | translation row, language scope | the whiteboard fixes touch the renderer and timeline: small hunks |

Can start now, in parallel with the voices job: stage 0, `look_choice` (items 1), `polyglot.py` and `plan_langs.py` (2, 3), the captions translation row (10), the intake prompt (0), documentation (12), the audit rule (9) as a function with a stub for voice names. Must wait for the voices merge: `length.py` call sites (7), the cast table for default languages, any hand-picked voice table, `voices.cast_voices` changes of stage 3, and the real voice choices in the QA proof (so the listening test judges the final voices).

## 5. Open decisions for the owner

| # | Question | Recommendation |
|---|---|---|
| D1 | Five languages with two or three characters: what do we do? | One guest character takes languages in turn with a changing voice and a language chip (stage 3); in stage 1 reduce to the characters' languages and say so |
| D2 | Should a character be locked to a language, or may the app choose when only "different languages" is said? | The person's choice always wins; otherwise the app chooses in the kind order and says it |
| D3 | Translation line on by default, even with captions off? | Yes: on by default when languages differ, shown even when captions are off, one switch (`translation: auto/on/off`) |
| D4 | Main language for the translation: the request's language? | Yes; the app's narration-language option overrides, as today |
| D5 | Whiteboard requests that ask for several voices | Adapt to a cartoon conversation with a note unless the person chose whiteboard explicitly |
| D6 | Dutch, Polish and Finnish have only women's voices | Allow; the note tells the person; give those languages to women characters by default |
| D7 | Code-switching inside one line | Not in stage 1; decide after the $0.01 `<lang>` test in stage 3 |
| D8 | Ship stage 0 and stage 1 before the voices job merges? | Stage 0 and the contract parts yes; the QA listening test after the merge, so the voices judged are final |

## 6. What was not done

No code was changed, no tests or builds were run, nothing was deployed, no Polly synthesis was made (no paid spend). QA data was read-only (videos table, plan and timeline in S3, Lambda logs). The statement that `<lang>` is available on generative comes from the earlier study's reading of the AWS documentation, not from a test of this analysis; the pronunciation effect on a monolingual generative voice is unknown. The identification of the owner's video is by match of request and result, not confirmed with the owner. The second request check (22:15:57, declined) could not be read.
