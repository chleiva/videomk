# Video languages: what "support all" takes, and what is supported (2026-11-27)

A video can be narrated in a language that the apps themselves are not translated into: the apps stay English and Spanish (`docs/I18N.md`), the VIDEO can be French. This document is about the language of the video.

## In one screen

- Polly's generative engine offers **10 languages** (55 voices; the dated list is `docs/POLLY_GENERATIVE_VOICES_2026-11-27.md`). "All generative languages" therefore means these ten: there is no generative Arabic, Hebrew, Chinese, Japanese or Hindi-only voice to support.
- **READY and on by default:** English, Spanish.
- **READY, behind the config list, on for QA:** French, German, Italian, Brazilian Portuguese, Dutch, Polish, Finnish.
- **NEEDS WORK:** Korean (voices exist and word timing works; no bundled font has Hangul).
- **NOT YET:** nothing else can be done with this voice engine.

## The switch

`VIDEO_LANGUAGES` (comma list) on the engine, the launcher and the request check. Default `en,es`. Only languages in `engine/voices.READY` count, so listing `ko` does nothing yet.

- Stage setting: `stages.json` → `"videoLanguages"` (QA has all nine), or `-c videoLanguages=en,es,fr` at deploy. Production has none, so it stays English and Spanish until the owner adds the line.
- `READY_LANGUAGES` (`readyLanguages`) is a different, older switch: which languages the create form OFFERS to pick explicitly. It was left at `en,es` everywhere: on QA a video becomes French because the request is written in French (language "auto"), not because the form lists French. The form can list them later by setting `readyLanguages`; the labels are ready (`format_options.LANGUAGE_LABELS`).

## What each language needs, and where it stands

| Need | How it is met | English, Spanish | French, German, Italian, Portuguese, Dutch, Polish, Finnish | Korean |
|---|---|---|---|---|
| A generative voice | Polly, `us-east-1` | 21 and 7 voices | 8, 6, 3, 3, 2, 2, 1 voices | 2 voices |
| Default voice by region | `voices.default_voice` | English as chosen by the owner, India now Kiara; Spanish since 2026-11-27: Sergio in Spain, Lupe for everyone else | since 2026-11-27 a lively voice wherever the accent has one (French Ambre; `docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md`), chosen by measurement, not by ear: owner to confirm | Seoyeon |
| Script in the language | the planner model writes in it (one line of the prompt names the language) | proven | plans made in French, German and Polish passed the plan audit; **the writing quality has not been judged by a native speaker** | not tried |
| Language detection | word lists first (free), the small model when unsure | as before | a clear request is recognised without a model call; a short one ("Roma") goes to the small model | the small model |
| Request check and safety | the check model reads any language ("Requests can be in any language; judge them the same way"); its prompt names the stage's languages | as before | works; the deterministic fallback list used only when the model call fails is English and Spanish | same |
| Refusal message | lists every enabled language | "English and Spanish" | "English, Spanish, French, ..." | - |
| Fonts for captions and on-screen text | Inter, Playfair Display, DejaVu Sans Mono, STIX | complete | **complete: every letter of every language, checked glyph by glyph in tests** (only the capital ẞ is missing, in DejaVu, STIX and the two handwriting fonts; a capitalised ß is written SS) | **no Hangul in any font** |
| Whiteboard handwriting | Patrick Hand, Caveat: the fonts, AND the pen-stroke tables the marker writes from (`assets/whiteboard/glyphs_*.json`) | complete | complete since 2026-11-27 (languages-qa-fixes): the fonts always had the letters, but **the stroke tables had no ą ć ę ł ń ś ź ż, š ž, ÿ, ĳ or „** and the earlier test only looked at the fonts, so the first Polish video had gaps ("sł ońce") and untraced letters. The tables now hold all of Latin-1 and Latin Extended-A (329 signs a hand) and the test walks every letter of every language against them; a sign still missing is written from the font at its own width with a plain pen path over it (`hand._fallback`) | none |
| Line breaking | at spaces | fine | fine (French puts a space before ? and :, so a lone "?" can be highlighted as its own caption word: cosmetic) | Korean breaks at spaces too, but lines are denser: untested |
| Word timing from the audio | `engine/align.py` | 96 and 97 ms mean error | 71 to 145 ms (table below) | 73 ms |
| Numbers | `engine/numfmt.py` | 1,250.5 and 1250,5 | decimal comma, thousands spaced from five digits (12 345,6): the international form | decimal point |
| Length fit (speaking rate) | `engine/length.py`, `engine/plan.words_per_s` | four voices fitted on 1,700 real beats; word budget 2.4 words a second | since 2026-11-27: the default voice of each language fitted on a 70-word passage and, for fr, de, it, pt, pl, the four beats of a QA video; the other voices are that fit scaled by their one sentence; **the word budget follows the language** (table below) | one sentence |
| Research | the Wikipedia of the language; web research told the language | as before | fr, de, it, pt, nl, pl, fi Wikipedias | ko |
| Stock photo and clip search | the planner writes the search words | in the video's language or English, as before | **told to write search words in English** | - |
| Presenter characters | a voice of the language for the character's gender (`presenter_policy.voice_for`) | English hand-picked; Spanish Lupe and Carlos (Spain: Lucia and Sergio) | a lively voice of the character's gender and the viewer's accent (Ambre, Florian, Vicki or Tina, Lennart, Beatrice, Lorenzo, Camila or Carolina, Leo); Dutch, Polish and Finnish have no male voice, so David, Mateo and the male animals get a woman's voice there | - |
| Closing card | "Made with VideoMK" in the language | yes | yes | written, unused |
| Description: "Image credits:", "Sources:", the "Intro" chapter | `engine/assets.LABELS` | yes | yes since 2026-11-27 (it was English: "Sources:" under a French description) | written |
| App strings | EN/ES only (`docs/I18N.md`) | yes | the app stays in English or Spanish; server messages too | same |

### Word timing, measured

Polly generative returns no word timings, so words are placed from the audio. Measured against Polly's exact word marks (neural engine, the standard voice of each language, two sentences each; the fixtures of one sentence per language are in `backend/tests/fixtures/speech/` and tested):

| Language | Mean error | 90th percentile | Worst word |
|---|---|---|---|
| English | 96 ms | 213 ms | 315 ms |
| Spanish | 97 ms | 200 ms | 388 ms |
| French | 81 ms | 155 ms | 248 ms |
| German | 104 ms | 203 ms | 320 ms |
| Italian | 128 ms (was 354) | 286 ms | 535 ms (was 2,018) |
| Portuguese | 94 ms | 192 ms | 428 ms |
| Dutch | 105 ms | 242 ms | 360 ms |
| Polish | 134 ms | 247 ms | 812 ms |
| Finnish | 71 ms (was 240) | 196 ms | 305 ms (was 1,243) |
| Korean | 73 ms (was 208) | 174 ms | 338 ms |

Two changes to the aligner, both for every language: a Hangul block counts as a syllable, and a comma that was pinned to the wrong silence is released when the two phrases around it would otherwise be spoken at very different paces (Italian and Finnish hold double consonants as long as a short breath; that was the 2-second error). The 47 existing sync tests pass unchanged and the English and Spanish numbers did not move. Honest limits: the measurement is on the neural engine's audio (the generative engine has no marks to compare with) and on two sentences per language. Polish is the weakest: one word in 53 was 0.8 s late.

## Known limits of the seven new languages

1. **Nobody who speaks them has watched a video yet.** The plan audit checks structure, cast and language code, not prose quality. First step on QA: one video per language, watched by a native speaker where possible.
2. **Voices were not chosen by ear.** Since 2026-11-27 the default of each accent is a lively voice where Polly has one, chosen by measured pitch movement (`docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md`); Canadian French and Polish have only steady voices. Owner's decision 2026-11-28: every Dutch video uses the lively Flemish Lisa (Laura is the second voice) and Belgian French uses Ambre (fr-FR) instead of Isabelle; neither was judged by a native listener.
3. **Few voices in three languages:** Dutch 2 and Polish 2 (all women), Finnish 1. A request for a male narrator there gets a woman's voice and the plan records it (`voice_notes`).
4. **Wishes written in the request are read in English and Spanish only** where they are read by rules: "whiteboard", "cartoon", "with a presenter", "no background", gestures cued by "first, second". In other languages the request check (a model) still understands the look asked for, but the rule-based shortcuts do not fire. The video is made; the wish may be missed.
5. **Numbers:** German, Italian, Dutch and Portuguese more often group thousands with a point (12.345,6); we write 12 345,6, which is correct and unambiguous but less customary.
6. **Filler-phrase bans** ("in this video", "welcome") are listed in English and Spanish; other languages are told "nor their equivalents".
7. **Pace and length (corrected 2026-11-27, see "Length in other languages").** The first five QA videos showed the limit was not the one written here: the time estimate from one sentence was within 5 percent; what was wrong was the budget counted in WORDS at the English rate. Non-default voices still rest on one sentence each, and Dutch and Finnish on one passage.
8. **Edit by text, captions, chapters** use the same code paths and were not separately exercised per language.

## Length in other languages (2026-11-27, branch `languages-qa-fixes`)

**What was seen:** in the first French and Portuguese 45 s videos the narration ended at 34.7 and 36.9 s; the last board and caption stood still for 8 to 11 s with music only (English: 42.5 s).

**Cause:** the writer is given a budget in words (89 for 45 s) at 2.4 words a second, an English figure. Characters predict speaking time, words do not:

| Language (default voice) | Words a second, measured | Words asked for 45 s | for 60 s |
|---|---|---|---|
| English (Ruth), Spanish (Lucia) | 2.63 (median of 174 videos); budget 2.4, unchanged | 89 | 130 |
| French (Ambre since 2026-11-27; Léa was 3.03) | 3.41 | 116 | 169 |
| Portuguese (Camila) | 3.09 | 105 | 153 |
| Dutch (Lisa since 2026-11-28, 5 beats; Laura was 2.79) | 2.83 | 95 | 138 |
| German (Vicki) | 2.66 | 90 | 131 |
| Italian (Beatrice since 2026-11-27, on real beats; Bianca was 2.59) | 2.54 | 86 | 125 |
| Polish (Ola) | 2.37 | 80 | 117 |
| Finnish (Suvi) | 1.95 (one passage) | 66 | 96 |

Measured on one explainer passage of 65 to 76 words per language (Polly generative, the default voice) and the four beats of the QA video of the language where there is one; the two agree within 1 percent for every language that has both. The 81 French words that were delivered are 26.7 s of speech; a 45 s video needs about 38.

**What changed:**
1. `plan.expected_words(minutes, photos, language)`: the budget in the prompt, the "too short, write it again" check and the "too long" check count in the language's words. English and Spanish are exactly as before.
2. `length.RATES` has a fit for the default voice of each new language (error on the QA videos and the passage: at most 5 percent; before: 4 percent long for Léa, 6 to 8 percent short for Vicki, Camila and Laura).
3. `length.extend_script` (director, before the cut step; not for English and Spanish, not for photo videos): a script estimated so short that holding every scene 1.6 s longer cannot reach the length is sent to the writer ONCE to be lengthened, beat by beat, existing sentences kept word for word. One call of the script model when it happens. Recorded in `research.length_extended` and as a plan warning.
4. `timeline.stretch_to`, every language, with the measured audio: what is still missing after every spoken scene is held 1.6 s longer goes to the last scene only if it is 2.5 s or less; more is shared by all spoken scenes. A video is still never shorter than asked (the product's promise, `docs/QUALITY_REVIEW.md` 11); it no longer reaches its length by freezing its last picture.

**Replay on the two QA plans with their real audio** (`tests/fixtures/plans/`): French, script unchanged: narration ends at 40.1 s instead of 34.8, every scene held 3.4 s instead of the last one 8.7 s; with the script lengthened as asked (+35 words): 42.2 s. Portuguese: 40.6 s instead of 37.0; lengthened (+27 words): 42.6 s. **Not measured on a real new video yet.**

## Fixed words that are still English in every language (looked for on 2026-11-27)

None of these is new with the seven languages: Spanish videos have them too. Listed so that nobody is surprised.

| Where the viewer sees it | Text | Code |
|---|---|---|
| On-screen credit of a stock photo or clip | "Photo: Ana (Unsplash License)", "Video: Ana / Pexels" | `engine/assets.credit_line`, `engine/stock.credit_line`, `engine/clips.credit_line` |
| Attribution lines of the description | "Photo by ... on Unsplash", "Video by ... on Pexels" | deliberate: the provider's own wording |
| Centre of a donut chart that is not percentages | "Total" | `scenes/elements/data.py` |
| Note on a map of today's borders | "Borders as of today" | `scenes/elements/_mapdraw.py` |
| Between the two sides of a comparison | "VS" | `scenes/elements/compare_process.py` (understood everywhere; left) |
| A whiteboard drawing the library does not have | its English name in a box ("prism") unless the director gave a `label` | `whiteboard/spec.py` |
| Photo videos: a collage or frame without a title, a photo story without chapter titles | "Photos", "Photo", "Part 2" | `scenes/elements/photo_layouts.py`, `engine/curate.py` |
| A video without a title | "Untitled" | `handlers/finalize_handler.py` |
| Presenter characters' roles | English and Spanish only ("Teacher", "Profesora") | `presenter_policy.py` (used in the director's prompt; not seen drawn in a video: not checked further) |

The closing card is in the language for all nine (tested). App and server messages (refusals, the reason a look was chosen, the maintenance notice) are English or Spanish by design (`docs/I18N.md`).

## Korean: what it needs (not done)

1. A Korean font licensed for bundling (Noto Sans KR is under the SIL Open Font License, which allows it), in the three weights the engine draws with (regular, semibold, bold). **Size not measured here** (no font was downloaded): Korean fonts carry about 11,000 Hangul glyphs and are several MB per weight, so expect an addition in the order of 10 to 20 MB to the engine layer; measure it, and check the total against the Lambda limit of 250 MB unzipped, before committing to it.
2. Font fallback in `engine/canvas.load_font`: today one family draws everything; Korean text needs the Korean font and Latin text keeps Inter, per run of characters or per video language.
3. Serif titles (Playfair), code (DejaVu Mono) and maths (STIX) scenes need a Korean fallback as well.
4. Line breaking and fitting: Korean lines carry more per character; the caption width and the "characters per line" limits of every element were tuned for Latin text.
5. The whiteboard look needs a Korean handwriting font; until then the whiteboard policy must not be offered for Korean.
6. The missing-glyph test (`tests/test_languages.py`) already fails for Korean on purpose: add `ko` to `voices.READY` only when it passes.

## Adding a language later

`engine/voices.py` (`LANGUAGES`, `NATIVE`, `READY`, `_DEFAULT`), a word list in `engine/language.py`, a sample sentence in `scripts/polly_voice_catalog.py` (then `--write --measure`), a pangram and a speech fixture in `tests/test_languages.py`, its number style in `engine/numfmt.COMMA_LANGUAGES`, a label in `format_options.LANGUAGE_LABELS`, the closing-card line in `engine/language.py`.

## Several languages in one video (switch `POLYGLOT`, QA only)

Design: `docs/MULTILINGUAL_CONVERSATIONS_DESIGN_2026-11-27.md`; request contract (`cast` entries with a language, `translation`): `docs/CREATE_API.md`.

The video keeps ONE main language (the viewer's: title, description, end card, translation row). In a cartoon conversation of 2 or 3 characters each character may speak its own language, with a voice of that language (`plan.polyglot.speakers`, `plan.voices`). Code: `engine/polyglot.py` (intent from the form, then from the words; one small model call only when the words do not settle it; languages to characters; the writer's paragraph; `prepare` and `finish` called by `director.direct`), `engine/plan_langs.py` (language of each line: heuristic, then one batched small call; one rewrite; the audit voice language equals line language), `scenes/captions.py` (the translation row, smaller, under the caption row, shown even with captions off). Without `POLYGLOT` nothing here runs and plans are unchanged.

Limits of this first stage: at most 3 languages (more are reduced to the characters' languages, with a note), cartoon conversation only (a whiteboard or footage look the person chose stays one language, with a note), no code-switching inside one line, Dutch, Polish and Finnish only with women's voices. Not yet: the length fit estimates each line with the plan's main language (`engine/length.py`, waits for the voices merge), phrasebook mode.
