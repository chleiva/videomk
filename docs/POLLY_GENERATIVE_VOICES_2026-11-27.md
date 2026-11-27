# Amazon Polly generative voices: the full list (read from Polly on 2026-11-27)

Source: `aws polly describe-voices --engine generative`, run in every region below on 2026-11-27 by `backend/scripts/polly_voice_catalog.py --list` (rerun it to refresh; `--write --measure` rebuilds `backend/lambdas/engine/voice_data.py`). Nothing here is from memory.

## Totals

- **55 voices, 24 locales, 10 languages.** Every one of them synthesised a test sentence in `us-east-1` (generative engine) on the same day.
- Same 55 voices in: ap-northeast-1, ap-northeast-2, ap-southeast-1, ap-southeast-2, eu-central-1, us-east-1, us-west-2.
- `ca-central-1` has only 37: missing Andres, Ayanda, Bianca, Celine, Daniel, Ewa, Gabrielle, Isabelle, Kajal, Laura, Lea, Liam, Lucia, Mia, Ola, Pedro, Remi, Sergio.
- `eu-west-2` has only 37: missing Andres, Ayanda, Bianca, Celine, Daniel, Ewa, Gabrielle, Isabelle, Kajal, Laura, Lea, Liam, Lucia, Mia, Ola, Pedro, Remi, Sergio.
- No generative engine at all in: eu-west-1 (where the QA stack runs), eu-west-3, ap-south-1, sa-east-1. Polly's documentation also lists eu-central-2 and us-gov-west-1 (not checked: the QA account is not opted in). The engine calls Polly in `us-east-1` (`POLLY_REGION`), which has the full list: no change needed.
- Polly generative has **no** Arabic, Hebrew, Chinese, Japanese, Hindi-only, European Portuguese or any right-to-left voice. Hindi exists only as a second language (`also`) of the three Indian English voices.
- Polly publishes no description of a voice's character. The catalogue therefore holds only what can be supported: language, accent (locale), gender, engines, and a pace we measured. No "warm" or "calm" labels.

## By language

| Language | Voices | Women | Men | Accents (locales) | Default voice | Video language status |
|---|---|---|---|---|---|---|
| English | 21 | 13 | 8 | Australian (en-AU), British (en-GB), Irish (en-IE), Indian (en-IN), New Zealand (en-NZ), Singaporean (en-SG), American (en-US), South African (en-ZA) | Ruth | READY (on by default) |
| Spanish | 7 | 3 | 4 | Spanish (Spain) (es-ES), Mexican (es-MX), Latin American (US) (es-US) | Lucia | READY (on by default) |
| French | 8 | 5 | 3 | Belgian (fr-BE), Canadian (fr-CA), French (France) (fr-FR) | Lea | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| German | 6 | 4 | 2 | Austrian (de-AT), Swiss (de-CH), German (Germany) (de-DE) | Vicki | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Italian | 3 | 2 | 1 | Italian (it-IT) | Bianca | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Portuguese | 3 | 2 | 1 | Brazilian (pt-BR) | Camila | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Dutch | 2 | 2 | 0 | Belgian (Flemish) (nl-BE), Dutch (Netherlands) (nl-NL) | Laura | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Polish | 2 | 2 | 0 | Polish (pl-PL) | Ola | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Finnish | 1 | 1 | 0 | Finnish (fi-FI) | Suvi | READY (behind `VIDEO_LANGUAGES`, on for QA) |
| Korean | 2 | 1 | 1 | Korean (ko-KR) | Seoyeon | NEEDS WORK (no font with Hangul yet) |

## Every voice

Pace: the voice saying one fixed sentence of its language (the same content in every language, about 200 characters; the sentences are in `voice_data.SAMPLE`), generative engine, silence trimmed. One sentence per voice: good for ranking voices of one language against each other, not a precise rate. Words per minute are not comparable between languages (Finnish and Polish words are long); characters per minute are closer.

| Voice id | Name | Locale | Accent | Gender | Polly engines | Also speaks | Sentence (s) | Words/min | Chars/min |
|---|---|---|---|---|---|---|---|---|---|
| Hannah | Hannah | de-AT | Austrian | female | generative, neural | - | 11.23 | 171 | 1105 |
| Sabrina | Sabrina | de-CH | Swiss | female | generative, neural | - | 13.14 | 146 | 945 |
| Daniel | Daniel | de-DE | German (Germany) | male | generative, neural | - | 11.94 | 161 | 1040 |
| Lennart | Lennart | de-DE | German (Germany) | male | generative | - | 11.27 | 170 | 1102 |
| Tina | Tina | de-DE | German (Germany) | female | generative | - | 12.77 | 150 | 973 |
| Vicki | Vicki | de-DE | German (Germany) | female | generative, neural, standard | - | 12.16 | 158 | 1021 |
| Curtis | Curtis | en-AU | Australian | male | generative | - | 10.47 | 178 | 1055 |
| Olivia | Olivia | en-AU | Australian | female | generative, neural | - | 10.89 | 171 | 1013 |
| Russell | Russell | en-AU | Australian | male | generative, standard | - | 10.50 | 177 | 1052 |
| Amy | Amy | en-GB | British | female | generative, neural, standard | - | 12.02 | 155 | 918 |
| Brian | Brian | en-GB | British | male | generative, neural, standard | - | 11.72 | 159 | 942 |
| Niamh | Niamh | en-IE | Irish | female | generative, neural | - | 11.81 | 157 | 935 |
| Arjun | Arjun | en-IN | Indian | male | generative | hi-IN | 11.13 | 167 | 992 |
| Kajal | Kajal | en-IN | Indian | female | generative, neural | hi-IN | 9.96 | 187 | 1108 |
| Kiara | Kiara | en-IN | Indian | female | generative | hi-IN | 10.85 | 171 | 1018 |
| Aria | Aria | en-NZ | New Zealand | female | generative, neural | - | 11.01 | 169 | 1003 |
| Jasmine | Jasmine | en-SG | Singaporean | female | generative, neural | - | 12.02 | 155 | 918 |
| Danielle | Danielle | en-US | American | female | generative, long-form, neural | - | 11.44 | 163 | 965 |
| Joanna | Joanna | en-US | American | female | generative, neural, standard | - | 11.27 | 165 | 979 |
| Kenneth | Kenneth | en-US | American | male | generative | - | 10.46 | 178 | 1055 |
| Matthew | Matthew | en-US | American | male | generative, neural, standard | - | 10.34 | 180 | 1067 |
| Nate | Nate | en-US | American | male | generative | - | 10.09 | 184 | 1094 |
| Ruth | Ruth | en-US | American | female | generative, long-form, neural | - | 11.60 | 160 | 952 |
| Salli | Salli | en-US | American | female | generative, neural, standard | - | 11.40 | 163 | 968 |
| Stephen | Stephen | en-US | American | male | generative, neural | - | 10.34 | 180 | 1067 |
| Tiffany | Tiffany | en-US | American | female | generative | - | 12.39 | 150 | 891 |
| Ayanda | Ayanda | en-ZA | South African | female | generative, neural | - | 11.88 | 157 | 929 |
| Lucia | Lucia | es-ES | Spanish (Spain) | female | generative, neural, standard | - | 10.73 | 179 | 1046 |
| Sergio | Sergio | es-ES | Spanish (Spain) | male | generative, neural | - | 10.09 | 190 | 1112 |
| Andres | Andrés | es-MX | Mexican | male | generative, neural | - | 10.45 | 184 | 1074 |
| Mia | Mia | es-MX | Mexican | female | generative, neural, standard | - | 11.88 | 162 | 945 |
| Carlos | Carlos | es-US | Latin American (US) | male | generative | - | 10.34 | 186 | 1085 |
| Lupe | Lupe | es-US | Latin American (US) | female | generative, neural, standard | - | 11.21 | 171 | 1001 |
| Pedro | Pedro | es-US | Latin American (US) | male | generative, neural | - | 10.97 | 175 | 1022 |
| Suvi | Suvi | fi-FI | Finnish | female | generative, neural | - | 12.03 | 125 | 977 |
| Isabelle | Isabelle | fr-BE | Belgian | female | generative, neural | - | 10.27 | 193 | 1168 |
| Gabrielle | Gabrielle | fr-CA | Canadian | female | generative, neural | - | 11.10 | 178 | 1081 |
| Liam | Liam | fr-CA | Canadian | male | generative, neural | - | 10.78 | 184 | 1113 |
| Ambre | Ambre | fr-FR | French (France) | female | generative | - | 9.84 | 201 | 1220 |
| Celine | Céline | fr-FR | French (France) | female | generative, standard | - | 11.04 | 179 | 1087 |
| Florian | Florian | fr-FR | French (France) | male | generative | - | 9.47 | 209 | 1268 |
| Lea | Léa | fr-FR | French (France) | female | generative, neural, standard | - | 11.49 | 172 | 1044 |
| Remi | Rémi | fr-FR | French (France) | male | generative, neural | - | 10.67 | 186 | 1125 |
| Beatrice | Beatrice | it-IT | Italian | female | generative | - | 11.48 | 152 | 977 |
| Bianca | Bianca | it-IT | Italian | female | generative, neural, standard | - | 12.56 | 139 | 894 |
| Lorenzo | Lorenzo | it-IT | Italian | male | generative | - | 10.87 | 160 | 1032 |
| Hyunduk | Hyunduk | ko-KR | Korean | male | generative | - | 11.79 | 122 | 483 |
| Seoyeon | Seoyeon | ko-KR | Korean | female | generative, neural, standard | - | 12.65 | 114 | 450 |
| Lisa | Lisa | nl-BE | Belgian (Flemish) | female | generative, neural | - | 12.24 | 167 | 1118 |
| Laura | Laura | nl-NL | Dutch (Netherlands) | female | generative, neural | - | 12.59 | 162 | 1087 |
| Ewa | Ewa | pl-PL | Polish | female | generative, standard | - | 14.31 | 122 | 856 |
| Ola | Ola | pl-PL | Polish | female | generative, neural | - | 12.50 | 139 | 979 |
| Camila | Camila | pt-BR | Brazilian | female | generative, neural, standard | - | 11.22 | 176 | 1016 |
| Carolina | Carolina | pt-BR | Brazilian | female | generative | - | 11.43 | 173 | 997 |
| Leo | Leo | pt-BR | Brazilian | male | generative | - | 12.18 | 163 | 936 |

## Defaults (what a video gets when the request asks for nothing)

Unchanged, the owner's choices: **Ruth** for US English and anywhere without its own English accent (Canada too: Polly has no Canadian English voice); Amy (GB), Niamh (IE), Olivia (AU), Aria (NZ), Ayanda (ZA), Kajal (IN), Jasmine (SG); **Lucia** for Spain and anywhere outside the Americas; **Mia** (Mexican) for Latin America; Lupe for Spanish in the US.

New on 2026-11-27, chosen WITHOUT listening (the voice Polly has offered longest in each accent, the one that also exists in the neural engine): Léa (France), Gabrielle (Canada), Isabelle (Belgium); Vicki (Germany), Hannah (Austria), Sabrina (Switzerland); Bianca (Italy); Camila (Brazil); Laura (Netherlands), Lisa (Flanders); Ola (Poland); Suvi (Finland); Seoyeon (Korea, not enabled). **The owner should listen and confirm or change these**: they are one line each in `engine/voices.py` (`_DEFAULT`, `_BY_REGION`).

## Limits worth knowing

- Dutch (2), Polish (2) and Finnish (1) have **no male voice**. A request for a man's voice there gets a woman's voice and the plan says so (`voice_notes`); a Finnish dialogue is one voice for everyone.
- Portuguese is Brazilian only; a viewer in Portugal gets the Brazilian voice.
- Ewa (Polish) is the slowest voice of all (856 characters per minute); Florian (French) the fastest (1268).
- eu-west-2 and ca-central-1 lack 18 voices including Lucia, Mia and every Polish and Dutch one: never point `POLLY_REGION` there.
