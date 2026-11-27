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
| Default voice by region | `voices.default_voice` | the owner's choices, unchanged | chosen without listening: owner to confirm | Seoyeon |
| Script in the language | the planner model writes in it (one line of the prompt names the language) | proven | plans made in French, German and Polish passed the plan audit; **the writing quality has not been judged by a native speaker** | not tried |
| Language detection | word lists first (free), the small model when unsure | as before | a clear request is recognised without a model call; a short one ("Roma") goes to the small model | the small model |
| Request check and safety | the check model reads any language ("Requests can be in any language; judge them the same way"); its prompt names the stage's languages | as before | works; the deterministic fallback list used only when the model call fails is English and Spanish | same |
| Refusal message | lists every enabled language | "English and Spanish" | "English, Spanish, French, ..." | - |
| Fonts for captions and on-screen text | Inter, Playfair Display, DejaVu Sans Mono, STIX | complete | **complete: every letter of every language, checked glyph by glyph in tests** (only the capital ẞ is missing, in DejaVu, STIX and the two handwriting fonts; a capitalised ß is written SS) | **no Hangul in any font** |
| Whiteboard handwriting | Patrick Hand, Caveat | complete | complete (tested) | none |
| Line breaking | at spaces | fine | fine (French puts a space before ? and :, so a lone "?" can be highlighted as its own caption word: cosmetic) | Korean breaks at spaces too, but lines are denser: untested |
| Word timing from the audio | `engine/align.py` | 96 and 97 ms mean error | 71 to 145 ms (table below) | 73 ms |
| Numbers | `engine/numfmt.py` | 1,250.5 and 1250,5 | decimal comma, thousands spaced from five digits (12 345,6): the international form | decimal point |
| Length fit (speaking rate) | `engine/length.py` | four voices fitted on 1,700 real beats | every voice measured on one sentence (approximate) | measured |
| Research | the Wikipedia of the language; web research told the language | as before | fr, de, it, pt, nl, pl, fi Wikipedias | ko |
| Stock photo and clip search | the planner writes the search words | in the video's language or English, as before | **told to write search words in English** | - |
| Presenter characters | a voice of the language for the character's gender (`presenter_policy.voice_for`) | hand-picked voices | by the resolver; Dutch, Polish and Finnish have no male voice, so David, Mateo and the male animals get a woman's voice there | - |
| Closing card | "Made with VideoMK" in the language | yes | yes | written, unused |
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
2. **Voices were not chosen by ear.** Defaults are the longest-standing voice per accent.
3. **Few voices in three languages:** Dutch 2 and Polish 2 (all women), Finnish 1. A request for a male narrator there gets a woman's voice and the plan records it (`voice_notes`).
4. **Wishes written in the request are read in English and Spanish only** where they are read by rules: "whiteboard", "cartoon", "with a presenter", "no background", gestures cued by "first, second". In other languages the request check (a model) still understands the look asked for, but the rule-based shortcuts do not fire. The video is made; the wish may be missed.
5. **Numbers:** German, Italian, Dutch and Portuguese more often group thousands with a point (12.345,6); we write 12 345,6, which is correct and unambiguous but less customary.
6. **Filler-phrase bans** ("in this video", "welcome") are listed in English and Spanish; other languages are told "nor their equivalents".
7. **The pace estimate for a new voice comes from one sentence**, so the length fit is less exact than for Ruth, Amy, Lucia and Lupe; the timeline's stretch and tighten steps absorb it, as they do today.
8. **Edit by text, captions, chapters** use the same code paths and were not separately exercised per language.

## Korean: what it needs (not done)

1. A Korean font licensed for bundling (Noto Sans KR is under the SIL Open Font License, which allows it), in the three weights the engine draws with (regular, semibold, bold). **Size not measured here** (no font was downloaded): Korean fonts carry about 11,000 Hangul glyphs and are several MB per weight, so expect an addition in the order of 10 to 20 MB to the engine layer; measure it, and check the total against the Lambda limit of 250 MB unzipped, before committing to it.
2. Font fallback in `engine/canvas.load_font`: today one family draws everything; Korean text needs the Korean font and Latin text keeps Inter, per run of characters or per video language.
3. Serif titles (Playfair), code (DejaVu Mono) and maths (STIX) scenes need a Korean fallback as well.
4. Line breaking and fitting: Korean lines carry more per character; the caption width and the "characters per line" limits of every element were tuned for Latin text.
5. The whiteboard look needs a Korean handwriting font; until then the whiteboard policy must not be offered for Korean.
6. The missing-glyph test (`tests/test_languages.py`) already fails for Korean on purpose: add `ko` to `voices.READY` only when it passes.

## Adding a language later

`engine/voices.py` (`LANGUAGES`, `NATIVE`, `READY`, `_DEFAULT`), a word list in `engine/language.py`, a sample sentence in `scripts/polly_voice_catalog.py` (then `--write --measure`), a pangram and a speech fixture in `tests/test_languages.py`, its number style in `engine/numfmt.COMMA_LANGUAGES`, a label in `format_options.LANGUAGE_LABELS`, the closing-card line in `engine/language.py`.
