# The best out of Polly: lively defaults everywhere, and what the lively voices need (2026-11-27)

Owner's decision: speech stays on Amazon Polly's generative engine. This is the follow-up to `docs/VOICE_QUALITY_IT_ES_2026-11-27.md` (Polly's 55 generative
voices are two families: 18 *steady* ones that read flat and identically every time, 37 *lively* ones with about twice the pitch movement). That study
measured Italian, Spanish and German; this one measures every voice and acts on it, and fixes what the first four QA videos with lively voices showed.

Branch `polly-lively-defaults` (from `origin/ccr-3c41ecff-680028`, not merged, not deployed). Samples for the owner: `~/Downloads/videomk-looks/web/voices2/`
(14 MP3 and `voices2_index.json`). Nobody has listened to anything here: every claim is a measurement.

## In one screen

1. **Defaults.** Every language and region now has a lively default voice and a lively second voice (the other gender) wherever Polly has one for that
   accent. Changed: French Léa to **Ambre** (man: Rémi to **Florian**), Indian English Kajal to **Kiara**, the German man Daniel to **Lennart**, the Spanish
   man outside Spain Pedro to **Carlos**. Spanish by the owner's rule: Spain keeps a Castilian voice, **Sergio** (woman: Lucia); every other viewer,
   wherever they are or if we do not know, hears **Lupe** (man: Carlos). English is as it was, India apart.
2. **No lively voice exists** for Castilian Spanish, Mexican Spanish, Canadian French, Belgian French, Dutch of the Netherlands, Polish and South African
   English. Those keep a steady voice of their own accent; nothing was swapped for another accent (Spain apart, by decision).
3. **The resolver** prefers a lively voice inside the accent asked or the viewer's own; a steady voice asked for by name is given.
4. **The cartoon cast** has a lively voice per character in every language, and the characters of one video share the viewer's accent.
5. **Length.** Lively voices take a different time for the same text on every take (a beat 5 to 13 percent, a video up to 12). The fits are now made on
   real beats, and a guard cuts whole sentences out of the audio when the speech breaks the window: **a first render is never longer than the length asked
   plus 5 percent**, for any voice.
6. **The lengthening step** is shown the grounding notes and told to add content, never to say a sentence again.
7. **Register.** A lively voice sometimes says one beat far above the others (Beatrice 271 Hz against 175 to 200). One request for the whole narration
   does not fix it, nor does a lead-in sentence; saying the outlier again and keeping the nearest take does (Italian 7.6 to 1.9 semitones in the QA video's case).
8. **Music.** Every beat reaches the mix at one speech level, so the music is ducked as far under a quiet voice as under Ruth.
9. **Wording.** A modest "spoken rhythm" rule is in the director's prompt. It changes how the scripts read; it does not measurably change pitch spread.

## 1. Every voice, measured

Method of the first study, unchanged: each voice says the same sentence twice (identical audio = steady; `voices.STEADY`, 18 voices, confirmed for all 55)
and the two standard passages of its language (an explanation of why the sky is blue, about 60 words; a children's passage with two questions and three
exclamations, about 65 words), one request per passage, MP3 24 kHz. *Pitch spread* is the standard deviation of pitch around the voice's median, in
semitones (st); *range* the 5th to 95th percentile span. One take per lively voice (takes differ by about 0.3 st). The passages of the new languages were
written for this test and are in `voices2_index.json`. Sorted by locale, liveliest on the children's passage first.

| Voice | Locale | Gender | Family | Pitch spread (st): explanation / children | Pitch range 5-95% (st) | Median pitch (Hz) | Words per minute | Question ending (st) | Exclamation peak (st) |
|---|---|---|---|---|---|---|---|---|---|
| Hannah | de-AT | female | lively | 2.5 / 4.4 | 8.2 / 13.0 | 192 / 217 | 188 / 177 | +7.3 | +8.1 |
| Sabrina | de-CH | female | lively | 3.9 / 5.0 | 12.2 / 14.5 | 186 / 204 | 168 / 156 | +4.3 | +10.7 |
| Lennart | de-DE | male | lively | 3.7 / 6.3 | 12.0 / 21.4 | 108 / 151 | 185 / 185 | +7.6 | +10.8 |
| Vicki | de-DE | female | lively | 3.6 / 5.6 | 11.4 / 16.1 | 192 / 213 | 172 / 170 | +7.9 | +11.7 |
| Tina | de-DE | female | lively | 3.3 / 5.0 | 10.5 / 14.8 | 184 / 209 | 155 / 165 | +9.5 | +10.8 |
| Daniel | de-DE | male | steady | 3.8 / 4.3 | 12.9 / 14.6 | 100 / 107 | 185 / 155 | +3.2 | +10.3 |
| Russell | en-AU | male | lively | 3.3 / 6.9 | 10.6 / 21.0 | 108 / 158 | 200 / 172 | +3.8 | +10.8 |
| Curtis | en-AU | male | lively | 4.1 / 6.5 | 13.1 / 18.3 | 143 / 225 | 175 / 171 | +2.4 | +9.0 |
| Olivia | en-AU | female | lively | 3.9 / 5.0 | 12.1 / 15.8 | 229 / 288 | 182 / 172 | +0.4 | +6.5 |
| Amy | en-GB | female | lively | 4.8 / 6.6 | 15.3 / 20.0 | 178 / 236 | 178 / 161 | -11.0 | +10.1 |
| Brian | en-GB | male | lively | 5.4 / 6.6 | 17.7 / 20.9 | 125 / 250 | 177 / 142 | -0.2 | +6.2 |
| Niamh | en-IE | female | lively | 3.7 / 5.7 | 11.6 / 18.1 | 182 / 245 | 188 / 165 | +8.9 | +9.2 |
| Arjun | en-IN | male | lively | 4.9 / 7.5 | 15.4 / 22.2 | 89 / 123 | 179 / 160 | +7.6 | +11.3 |
| Kiara | en-IN | female | lively | 4.6 / 4.8 | 14.2 / 16.1 | 240 / 272 | 181 / 177 | +5.4 | +8.5 |
| Kajal | en-IN | female | steady | 3.0 / 3.3 | 9.7 / 10.1 | 239 / 237 | 210 / 176 | -5.7 | +4.5 |
| Aria | en-NZ | female | lively | 4.1 / 5.4 | 12.5 / 17.0 | 202 / 247 | 186 / 176 | +5.4 | +8.5 |
| Jasmine | en-SG | female | lively | 4.0 / 5.3 | 12.6 / 17.1 | 196 / 238 | 167 / 160 | +2.8 | +9.9 |
| Matthew | en-US | male | lively | 5.2 / 7.7 | 17.5 / 23.7 | 105 / 155 | 200 / 167 | +2.6 | +10.8 |
| Kenneth | en-US | male | lively | 4.9 / 7.3 | 16.0 / 22.4 | 120 / 212 | 184 / 163 | +2.3 | +9.5 |
| Nate | en-US | male | lively | 4.7 / 7.2 | 15.0 / 21.8 | 117 / 195 | 187 / 165 | +8.2 | +10.5 |
| Stephen | en-US | male | lively | 6.0 / 6.6 | 20.0 / 20.8 | 146 / 206 | 181 / 153 | +8.6 | +9.4 |
| Danielle | en-US | female | lively | 4.8 / 6.4 | 15.4 / 19.5 | 172 / 225 | 180 / 164 | +4.5 | +11.2 |
| Joanna | en-US | female | lively | 4.8 / 6.3 | 14.4 / 18.8 | 153 / 236 | 180 / 165 | +1.7 | +9.0 |
| Ruth | en-US | female | lively | 4.4 / 6.1 | 13.8 / 18.9 | 173 / 224 | 177 / 156 | +4.7 | +10.8 |
| Tiffany | en-US | female | lively | 4.7 / 5.7 | 14.9 / 17.8 | 185 / 261 | 167 / 157 | -3.6 | +9.0 |
| Salli | en-US | female | lively | 3.6 / 5.4 | 11.2 / 17.0 | 208 / 260 | 173 / 159 | +7.3 | +9.1 |
| Ayanda | en-ZA | female | steady | 4.9 / 5.1 | 15.6 / 16.9 | 166 / 172 | 173 / 153 | -3.1 | +9.7 |
| Sergio | es-ES | male | steady | 3.9 / 4.0 | 12.8 / 13.5 | 91 / 100 | 195 / 171 | +6.7 | +7.7 |
| Lucia | es-ES | female | steady | 3.2 / 3.3 | 10.6 / 11.7 | 194 / 197 | 194 / 159 | +7.1 | +7.4 |
| Andrés | es-MX | male | steady | 3.4 / 3.9 | 11.6 / 12.8 | 95 / 104 | 182 / 173 | +3.7 | +7.6 |
| Mia | es-MX | female | steady | 3.0 / 3.2 | 10.5 / 11.1 | 211 / 211 | 176 / 147 | +5.2 | +7.2 |
| Carlos | es-US | male | lively | 4.0 / 5.8 | 13.9 / 18.8 | 110 / 128 | 185 / 190 | +10.5 | +11.7 |
| Lupe | es-US | female | lively | 5.0 / 5.2 | 15.6 / 16.4 | 216 / 258 | 168 / 168 | +0.9 | +8.7 |
| Pedro | es-US | male | steady | 3.3 / 4.2 | 11.3 / 13.9 | 96 / 104 | 188 / 168 | +3.5 | +9.9 |
| Suvi | fi-FI | female | lively | 3.2 / 3.8 | 10.0 / 11.5 | 161 / 165 | 121 / 119 | -1.9 | +9.8 |
| Isabelle | fr-BE | female | steady | 2.5 / 2.7 | 8.1 / 9.3 | 173 / 170 | 211 / 172 | +0.7 | +3.8 |
| Liam | fr-CA | male | steady | 3.5 / 3.8 | 11.0 / 13.1 | 95 / 97 | 217 / 178 | +2.7 | +6.8 |
| Gabrielle | fr-CA | female | steady | 3.5 / 3.7 | 11.1 / 12.2 | 173 / 166 | 202 / 165 | +4.9 | +6.9 |
| Florian | fr-FR | male | lively | 4.3 / 5.4 | 14.3 / 16.8 | 151 / 167 | 225 / 223 | -3.1 | +10.0 |
| Ambre | fr-FR | female | lively | 3.7 / 5.1 | 12.4 / 15.7 | 217 / 230 | 205 / 204 | +9.5 | +9.1 |
| Rémi | fr-FR | male | steady | 3.8 / 4.2 | 12.5 / 14.6 | 98 / 100 | 213 / 175 | +9.4 | +8.8 |
| Léa | fr-FR | female | steady | 2.7 / 2.9 | 9.0 / 10.0 | 192 / 194 | 198 / 158 | +8.3 | +6.6 |
| Céline | fr-FR | female | steady | 1.9 / 2.1 | 6.2 / 6.8 | 212 / 214 | 204 / 160 | +5.3 | +3.1 |
| Lorenzo | it-IT | male | lively | 5.0 / 6.8 | 15.3 / 20.9 | 116 / 136 | 164 / 165 | +1.1 | +9.7 |
| Beatrice | it-IT | female | lively | 5.0 / 6.6 | 15.6 / 19.5 | 168 / 224 | 160 / 164 | +7.5 | +10.9 |
| Bianca | it-IT | female | steady | 2.8 / 2.9 | 9.2 / 9.6 | 194 / 195 | 165 / 134 | -1.9 | +5.9 |
| Seoyeon | ko-KR | female | lively | 4.2 / 4.5 | 12.9 / 14.1 | 230 / 213 | 118 / 114 | -4.8 | +5.7 |
| Hyunduk | ko-KR | male | lively | 3.9 / 3.5 | 12.3 / 11.0 | 128 / 119 | 113 / 117 | -2.3 | +5.8 |
| Lisa | nl-BE | female | lively | 4.8 / 5.0 | 14.7 / 15.3 | 165 / 193 | 178 / 181 | +1.5 | +9.3 |
| Laura | nl-NL | female | steady | 2.9 / 3.3 | 9.6 / 10.8 | 196 / 199 | 193 / 157 | +1.6 | +5.3 |
| Ola | pl-PL | female | steady | 3.0 / 3.4 | 10.4 / 12.0 | 183 / 183 | 137 / 126 | +5.5 | +8.8 |
| Ewa | pl-PL | female | steady | 2.9 / 3.3 | 9.7 / 10.9 | 144 / 144 | 123 / 116 | +7.7 | +7.4 |
| Leo | pt-BR | male | lively | 4.4 / 5.9 | 14.3 / 19.7 | 131 / 160 | 187 / 178 | -5.1 | +10.9 |
| Camila | pt-BR | female | lively | 4.3 / 5.5 | 13.3 / 16.0 | 202 / 237 | 198 / 177 | -1.8 | +9.4 |
| Carolina | pt-BR | female | lively | 4.0 / 5.2 | 12.1 / 16.0 | 218 / 237 | 207 / 186 | -3.6 | +9.2 |

Reading it:

- The families separate cleanly on the children's passage: steady voices 2.1 to 4.4 st (their median pitch does not move between the two passages), lively
  ones 4.4 to 7.7 and their pitch lifts. Three lively voices are only mildly so: Suvi (3.2 / 3.8), Hyunduk (3.9 / 3.5) and Hannah on plain text (2.5).
- **French:** Ambre and Florian are lively (3.7 / 5.1 and 4.3 / 5.4). Léa, the default until today, is as flat as Bianca was (2.7 / 2.9); Céline is the
  flattest voice of all 55 (1.9 / 2.1). Rémi is the best of the steady ones (3.8 / 4.2).
- **English:** every voice is lively but Kajal (India) and Ayanda (South Africa). Ayanda is steady by the test (the same audio twice, pitch 166 / 172 Hz on
  both passages) yet moves a lot (4.9 / 5.1): the best steady voice measured.
- **Portuguese:** all three are lively and alike; Camila stays. **Dutch:** Laura (Netherlands) is steady, Lisa (Flemish) lively. **Polish:** both steady
  and alike. **Finnish:** one voice.

## 2. Defaults, before and after

| Language, viewer | Old default | New default | Family | Pitch spread (st): explanation / children | Why |
|---|---|---|---|---|---|
| English, US, Canada and anywhere unlisted | Ruth | Ruth | lively | 4.4 / 6.1 | already lively; kept (the others of the accent measure alike) |
| English, UK | Amy | Amy | lively | 4.8 / 6.6 | already lively |
| English, Australia | Olivia | Olivia | lively | 3.9 / 5.0 | already lively |
| English, India | Kajal | **Kiara** | lively | 4.6 / 4.8 | Kajal is steady (3.0 / 3.3); Kiara is lively |
| English, Ireland | Niamh | Niamh | lively | 3.7 / 5.7 | already lively |
| English, New Zealand | Aria | Aria | lively | 4.1 / 5.4 | already lively |
| English, Singapore | Jasmine | Jasmine | lively | 4.0 / 5.3 | already lively |
| English, South Africa | Ayanda | Ayanda | steady | 4.9 / 5.1 | the accent has no lively voice: kept (its only voice) |
| Spanish, Spain | Lucia | **Sergio** | steady | 3.9 / 4.0 | Lucia is steady (3.2 / 3.3); Sergio is the Castilian voice that moves more (owner's decision: Spain keeps a Castilian voice) |
| Spanish, Latin America and US | Lupe | Lupe | lively | 5.0 / 5.2 | already lively |
| Spanish, any other country or none known | Lucia | **Lupe** | lively | 5.0 / 5.2 | Lucia is steady (3.2 / 3.3); Lupe is lively (owner's decision: every viewer outside Spain) |
| French, France and anywhere unlisted | Léa | **Ambre** | lively | 3.7 / 5.1 | Léa is steady (2.7 / 2.9); Ambre is lively |
| French, Canada | Gabrielle | Gabrielle | steady | 3.5 / 3.7 | the accent has no lively voice: kept (Liam 3.5 / 3.8: no better) |
| French, Belgium | Isabelle | Isabelle | steady | 2.5 / 2.7 | the accent has no lively voice: kept (its only voice) |
| German, Germany and anywhere unlisted | Vicki | Vicki | lively | 3.6 / 5.6 | already lively; kept (the others of the accent measure alike) |
| German, Austria | Hannah | Hannah | lively | 2.5 / 4.4 | already lively |
| German, Switzerland | Sabrina | Sabrina | lively | 3.9 / 5.0 | already lively |
| Italian | Beatrice | Beatrice | lively | 5.0 / 6.6 | already lively |
| Portuguese | Camila | Camila | lively | 4.3 / 5.5 | already lively; kept (the others of the accent measure alike) |
| Dutch, Netherlands and anywhere unlisted | Laura | Laura | steady | 2.9 / 3.3 | the accent has no lively voice: kept (its only voice) |
| Dutch, Belgium | Lisa | Lisa | lively | 4.8 / 5.0 | already lively |
| Polish | Ola | Ola | steady | 3.0 / 3.4 | the accent has no lively voice: kept (Ewa 2.9 / 3.3: no better) |
| Finnish | Suvi | Suvi | lively | 3.2 / 3.8 | already lively |
| Korean (not enabled) | Seoyeon | Seoyeon | lively | 4.2 / 4.5 | already lively |

The default second voice (what `voices.resolve` gives the other gender when nothing else is asked; `voices.second_voice`):

| Language, viewer | Old second voice | New second voice | Family | Pitch spread (st) | Note |
|---|---|---|---|---|---|
| English, US, Canada and anywhere unlisted | Matthew | Matthew | lively | 5.2 / 7.7 |  |
| English, UK | Brian | Brian | lively | 5.4 / 6.6 |  |
| English, Australia | Russell | Russell | lively | 3.3 / 6.9 |  |
| English, India | Arjun | Arjun | lively | 4.9 / 7.5 |  |
| English, Ireland | Matthew | Matthew | lively | 5.2 / 7.7 | the accent has no voice of that gender: American |
| English, New Zealand | Matthew | Matthew | lively | 5.2 / 7.7 | the accent has no voice of that gender: American |
| English, Singapore | Matthew | Matthew | lively | 5.2 / 7.7 | the accent has no voice of that gender: American |
| English, South Africa | Matthew | Matthew | lively | 5.2 / 7.7 | the accent has no voice of that gender: American |
| Spanish, Spain | Sergio | **Lucia** | steady | 3.2 / 3.3 |  |
| Spanish, Latin America and US | Pedro | **Carlos** | lively | 4.0 / 5.8 |  |
| Spanish, any other country or none known | Sergio | **Carlos** | lively | 4.0 / 5.8 |  |
| French, France and anywhere unlisted | Rémi | **Florian** | lively | 4.3 / 5.4 |  |
| French, Canada | Liam | Liam | steady | 3.5 / 3.8 |  |
| French, Belgium | Rémi | **Florian** | lively | 4.3 / 5.4 | the accent has no voice of that gender: French (France) |
| German, Germany and anywhere unlisted | Daniel | **Lennart** | lively | 3.7 / 6.3 |  |
| German, Austria | Daniel | **Lennart** | lively | 3.7 / 6.3 | the accent has no voice of that gender: German (Germany) |
| German, Switzerland | Daniel | **Lennart** | lively | 3.7 / 6.3 | the accent has no voice of that gender: German (Germany) |
| Italian | Lorenzo | Lorenzo | lively | 5.0 / 6.8 |  |
| Portuguese | Leo | Leo | lively | 4.4 / 5.9 |  |
| Dutch, Netherlands and anywhere unlisted | none | none | | | the language has women's voices only |
| Dutch, Belgium | none | none | | | the language has women's voices only |
| Polish | none | none | | | the language has women's voices only |
| Finnish | none | none | | | the language has women's voices only |
| Korean (not enabled) | Hyunduk | Hyunduk | lively | 3.9 / 3.5 |  |

**Accents with no lively voice (recorded in `voices.py` and tested):** es-ES (Lucia, Sergio), es-MX (Mia, Andrés), fr-CA (Gabrielle, Liam), fr-BE
(Isabelle), nl-NL (Laura), pl-PL (Ola, Ewa), en-ZA (Ayanda). Their viewers keep their accent. Two the owner may want to decide by ear, neither done here:
Dutch could be the Flemish Lisa (4.8 / 5.0) for everyone, and Belgian French could be Ambre.

**To hear before shipping:** the German man. Daniel is the steady voice the owner heard in a QA video and liked; by the rule he gives way to Lennart
(equal on a plain explanation, 3.7 against 3.8; far livelier on a lively text, 6.3 against 4.3). Samples `polly_de-DE_old_Daniel` and
`polly_de-DE_new_Lennart`. Daniel stays available by name and is the second man of a German conversation.

## 3. The resolver (`voices.resolve`)

- A lively voice scores `W_LIVELY` (0.9) more than a steady one: enough to win inside an accent and gender (Florian before Rémi, Lennart before Daniel,
  Kiara before Kajal, Carlos before Pedro), more than pace (0.5), less than the viewer's own accent (2.0) and than the step from the accent asked to its
  neighbour (5.0 against 3.0), so a Castilian, Mexican or Canadian wish is never answered with a livelier voice of another accent.
- The viewer's default voice counts only inside the accent asked (it could otherwise outweigh that accent now that it is also lively: caught by a test,
  "una voz mexicana" for a Mexican viewer had become Lupe).
- An accent Polly does not have in Latin America (Argentinian, Colombian, ...) is now answered by the lively Latin American pair first (Lupe, Carlos), then
  the Mexican voices; the note still says what was substituted.
- With no accent asked, a Latin American viewer's next voice after Lupe and Carlos is Mexican before Castilian.
- A voice asked for by name is given, steady or not. No two speakers of a conversation share a voice while the language has another.
- English is unchanged except where a steady voice was involved (India).

## 4. The cartoon cast (`presenter_policy.CAST`, `voice_for`)

| Character | English | Spanish (not Spain) | Spanish (Spain) | French | German | Italian | Portuguese | Dutch | Polish | Finnish |
|---|---|---|---|---|---|---|---|---|---|---|
| Inés (ines, teacher, female) | Ruth | Lupe | Lucia (was Lupe) | Ambre | Vicki | Beatrice | Camila | Laura | Ola | Suvi |
| David (david, engineer, male) | Matthew | Carlos (was Pedro) | Sergio (was Pedro) | Florian | Lennart | Lorenzo | Leo | Laura | Ola | Suvi |
| Priya (priya, doctor, female) | Kiara (was Kajal) | Lupe (was Mia) | Lucia (was Mia) | Ambre | Tina (was Vicki) | Beatrice | Camila | Laura | Ola | Suvi |
| Mateo (mateo, chef, male) | Stephen | Carlos (was Andrés) | Sergio (was Andrés) | Florian | Lennart | Lorenzo | Leo | Laura | Ola | Suvi |
| Fox (fox, guide for children, female) | Joanna | Lupe (was Lucia) | Lucia | Ambre | Vicki | Beatrice | Carolina (was Camila) | Laura | Ola | Suvi |
| Hugo (owl, owl professor, male) | Brian | Carlos (was Sergio) | Sergio | Florian | Lennart | Lorenzo | Leo | Laura | Ola | Suvi |
| Bruno (bear, caring bear, male) | Stephen | Carlos (was Andrés) | Sergio (was Andrés) | Florian | Lennart | Lorenzo | Leo | Laura | Ola | Suvi |
| Mika (cat, curious cat, female) | Olivia | Lupe (was Mia) | Lucia (was Mia) | Ambre | Vicki | Beatrice | Carolina (was Camila) | Laura | Ola | Suvi |
| Paco (parrot, travelling parrot, male) | Nate | Carlos (was Pedro) | Sergio (was Pedro) | Florian | Lennart | Lorenzo | Leo | Laura | Ola | Suvi |
| Tula (turtle, wise turtle, female) | Amy | Lupe | Lucia (was Lupe) | Ambre | Tina (was Vicki) | Beatrice | Camila | Laura | Ola | Suvi |

How a character's voice is chosen outside English: a voice of the character's gender that is, in this order, free (not taken by another character of the
video), of the viewer's accent (then the nearest accent), lively rather than steady, and first in the character's own order. English keeps its hand-picked
cast, the same for every viewer.

- **Character:** where a language gives a choice between lively voices of one accent, the character decides. German: the fox and the cat (young, quick) and
  the teacher get Vicki (the liveliest on a children's text, 172 words a minute), the doctor and the turtle (calm, unhurried) get Tina (155 words a minute).
  Portuguese: the fox and the cat get Carolina (218 Hz, 207 words a minute), the teacher, the doctor and the turtle Camila (202 Hz, 198). The owl (older,
  calm) is a man everywhere: Brian in English; elsewhere each language has one lively man (Carlos, Florian, Lennart, Lorenzo, Leo), so he shares it with the
  other male characters. Spanish, French and Italian have one lively woman each (Lupe, Ambre, Beatrice): every female character has that voice.
- **One accent per video** (QA 2026-11-27: a Latin American conversation had the fox on Lucia, Castilian, and the bear on Andrés, Mexican, both steady). The
  region now reaches the cast (`plan["region"]` is set before the cast is given voices). The same conversation is now Lupe and Carlos; in Spain Lucia and
  Sergio; in Canada Gabrielle and Liam. Limits of the catalogue: a second woman in a Latin American conversation is Mia (Mexican: one accent away), a
  second woman in Spain is Lupe, a second man in Latin America is Pedro (same accent, steady).
- Dutch, Polish and Finnish have no man's voice: the male characters speak with a woman's voice, as before.

## 5. Length

**What QA saw:** the Italian video came out 51.4 s for 45 s asked. Beatrice took 48.1 s for the script; her fit, made that morning from two lab passages,
predicted 41. The script had been lengthened because of that estimate. With every silence at its floor the video was still 51.4 s. Lupe, the other way,
was 11 percent faster than her fit in one video, and the scenes were held longer to fill the time.

**Fits on real beats** (`length.RATES`): one scale per voice on the shape of its language, from real narration beats (the beats of QA plans, one request
each, as the engine asks them) together with the 60-word explanation.

| Voice | Fit (s per character, pause, digit) | Real beats (takes) | Explanation passage against real beats | One beat: standard deviation (range) | A whole video or take against the fit | Words a second | Real time against the estimate before |
|---|---|---|---|---|---|---|---|
| Beatrice | 0.0591, 0.351, 0.21 | 12 | 0.92 | 8 % (0.88 to 1.12) | 1.02, 1.00, 1.01 | 2.54 | 1.15 |
| Lorenzo | 0.0594, 0.353, 0.21 | 4 | 0.87 | 13 % (0.90 to 1.19) | 1.05 | 2.51 | 1.22 |
| Lupe | 0.0518, 0.337, 0.14 | 23 | 1.10 | 5 % (0.91 to 1.08) | 1.04, 0.96, 1.01, 0.97, 0.97 | 2.77 | 0.93 |
| Carlos | 0.0491, 0.320, 0.13 | 5 | 1.06 | 6 % (0.89 to 1.07) | 0.98 | 3.02 | 1.00 |
| Sergio | 0.0478, 0.311, 0.13 | 5 | 1.03 | 3 % (0.95 to 1.04) | 0.99 | 3.10 | 1.00 |
| Ambre | 0.0455, 0.271, 0.16 | 4 | 1.01 | 8 % (0.90 to 1.10) | 0.99 | 3.41 | 1.10 |
| Florian | 0.0411, 0.245, 0.15 | 4 | 1.02 | 6 % (0.92 to 1.07) | 0.99 | 3.78 | 1.03 |
| Kiara | 0.0552, 0.328, 0.20 | 4 | 0.98 | 1 % (1.00 to 1.02) | 1.01 | 2.78 | 1.09 |
| Arjun | 0.0562, 0.334, 0.20 | 4 | 0.96 | 2 % (0.98 to 1.03) | 1.01 | 2.74 | 1.08 |
| Lennart | 0.0488, 0.290, 0.18 | 4 | 0.99 | 4 % (0.97 to 1.05) | 1.01 | 3.01 | 0.96 |

- **The spread no fit removes.** Across the 108 real QA beats on disk: a lively voice's beat is off by 4 to 10 percent (standard deviation; Lorenzo 13), a
  whole video by up to 12 (Vicki 0.90 and 1.06 of her fit in two videos); steady voices 1 to 7 a beat and at most 4 a video. A lab passage is not a real beat: Beatrice
  read her passages 8 percent faster than real beats, Lupe 10 percent slower. Vicki, Camila and Laura run 4 to 6 percent faster than their fits of this
  morning (7, 13 and 8 beats); left as they are, noted.
- **An unfitted voice** is scaled from a fitted voice of its own family (Léa for the steady French voices: scaling them from Ambre would have added 10 percent).
- **Word budgets** follow the default voice: French 3.41 words a second (Ambre; Léa was 3.03), Italian 2.54 (Beatrice on real beats; 2.85 came from her
  passages). English and Spanish budgets are unchanged.
- **The Spanish men are fast** (Sergio 3.10 words a second, Carlos 3.02; the Spanish budget was fitted on Lucia's 2.63). Their scripts are now lengthened
  like those of the newer languages (`length.EXTEND_FAST`); without that a video for Spain would hold every scene 1.6 s and freeze the last one.

**The guard** (`engine/speechcut.py`, `timeline_handler.fit_speech`, `length.overrun`, `length.pick_cut`). The product's promise (engine/length.py): a
video is at least as long as asked and at most 5 percent longer; videos normally land 0.4 s past the length asked. On a first render, once the audio is
measured:

1. the silences around every beat are shortened to their floors (as before);
2. if the video is still past the window, whole sentences are cut **out of the stored audio**, at the pauses between sentences: first the sentences the
   lengthening step added (now remembered in `plan["length_added"]`), then by the rules of the script cut (never the opening line, never the last line, a
   beat keeps at least 6 words), each time the sentence that lands nearest 3 percent over;
3. if it is then short, the existing even spreading applies.

No synthesis and no model call: the cut is silence to silence, the remaining audio is stored under the hash of the remaining text (an edit of that text
finds it; nothing is overwritten), its words are timed again, and the plan records what went (`length_cut`). A sentence is cut only if its pauses are
found in the audio where the aligner puts them, the sentences between them are spoken at a believable pace, and what remains still aligns with its text;
otherwise it is left alone. Nothing is read from storage when the video fits. A video with no cuttable sentence left stays long and logs `LENGTH_OVER`.

On the real Italian video (its stored audio): 51.4 s becomes **46.9 s** (window: 47.25) by removing "Si perde prima di raggiungerci." and "Il blu ci
arriva da ogni parte.", the two echoes the lengthening step had added. Of the 43 sentences in the 24 kHz QA beats, 40 can be cut cleanly.
With the new fit the same script would not have been lengthened at all (estimate 45.3 s).

## 6. The lengthening step (`length.extend_script`)

It added "Il blu ci arriva da ogni parte", "Si perde prima di raggiungerci", "Cambia la strada, non la luce": each says the sentence before again. Cause:
it was told to add sentences but forbidden new facts, and was shown no notes. Now:

- the prompt asks of every new sentence what the viewer learns from it, forbids saying a neighbour again in other words (with that example), a slogan or
  an echo of the point, and prefers returning a beat unchanged to repeating;
- the grounding notes of the video are passed in (3,000 characters), so what is added can be a fact;
- a new sentence most of whose words are already in its beat is refused in code (`length.restates`: catches "Cambia la strada, non la luce"; an echo in
  entirely different words passes, which is why the prompt forbids it and the guard cuts added sentences first).

Run once on the Italian script with the real model (no notes): it added "Lo vediamo quando un prisma o la pioggia separano i colori.", "Il rosso invece
tende a proseguire dritto, quasi senza deviare.", "Gli strati vicini all'orizzonte filtrano la luce come un lungo tunnel.", "Lo stesso accade all'alba,
quando il sole sale dall'orizzonte.": an example, a contrast, a comparison, a consequence. One run; not judged by a native speaker.

## 7. Register from beat to beat (`engine/register.py`)

Median pitch of each beat, Italian QA plan (Beatrice, 4 beats) and Spanish QA plan (Lupe, 5 beats). *Spread* is the distance in semitones between the
highest and the lowest beat. Pitch spread inside beats stayed 4.7 to 5.3 st in every variant: liveliness within a beat is not at stake.

| Approach | Italian: beat medians (Hz) | Spread (st) | Spanish: beat medians (Hz) | Spread (st) |
|---|---|---|---|---|
| One request per beat (today), the QA video's take | 200, 175, 178, 271 | 7.6 | 203, 253, 210, 222, 198 | 4.3 |
| the same, a second take | 185, 175, 183, 180 | 1.0 | 205, 214, 197, 216, 210 | 1.6 |
| the same, a third take | 245, 164, 186, 253 | 7.6 | 211, 219, 209, 237, 232 | 2.2 |
| The whole narration in ONE request, cut at the beats, take 1 | 213, 181, 162, 244 | 7.0 | 205, 237, 210, 222, 203 | 2.7 |
| the same, take 2 | 181, 178, 196, 216 | 3.4 | 196, 232, 211, 212, 205 | 2.9 |
| The last sentence of the beat before as a lead-in, cut off | 185, 170, 178, 250 | 6.6 | 205, 228, 188, 210, 203 | 3.3 |

- **One request does not give one register.** The voice changes register inside a request, from paragraph to paragraph, as much as between requests. And
  cutting is not safe: two of the fourteen cuts fell about 2.5 s from where they belonged (a beat came out 14.6 s instead of 12.1) although every piece
  still "aligned" with full confidence. It would also end per-beat caching and parallel synthesis.
- **A lead-in does not either**, costs 15 to 48 percent more characters, and needs the same cut.
- **The register follows the text and the take.** The last Italian beat ("... cambia solo il suo viaggio. Cambia la strada, non la luce.") came out high in
  5 of 6 takes with Beatrice, and with Lorenzo too (157 Hz against 107 to 126): short emphatic lines pull a lively voice into an excited register. The
  steady voices of the QA videos stayed within 0.8 st (Lucia, Andrés); Sergio, also steady, ranged 3 st over the five beats of the Spanish plan (92 to
  110 Hz) and would do so identically every time: a steady voice's register follows the text only, so saying it again changes nothing.

**What is done: take selection.** Every beat is said once, as always, and the median pitch of that first take is written next to its audio. A beat more
than 2 st from the speaker's register (4 st when every sentence of it is a question or exclamation) is said again, at most twice, and the take nearest the
register is kept. The register is the median of the lower half of the first takes of the speaker's beats (the excursions are upward). Beats are made in
parallel, so each function reads the others' first takes from storage (a wait of at most 4 s): no shared state, no new permission, per-beat caching and
word timing untouched (a take is whole). Lively Polly voices only; `REGISTER_RETAKES=0` turns it off.

The engine's own code run on the two plans, the first takes being the three takes above and every retake a new Polly request:

| First takes | Italian: before (st) | after (st) | extra characters | Spanish: before (st) | after (st) | extra characters |
|---|---|---|---|---|---|---|
| the QA video's | 7.6 | **1.9** (270 Hz became 194) | 49 % | 4.0 | **2.8** (250 Hz became 233) | 47 % |
| take 1 | 1.0 | 1.0 | 0 | 1.7 | 1.7 | 0 |
| take 2 | 7.4 | **4.2** (two beats said three times; the last one never came out low) | 97 % | 2.4 | **1.9** | 26 % |
| mean | 5.3 | 2.3 | 49 % | 2.7 | 2.1 | 24 % |

It meets the aim (under about 2.5 st) in four of six cases and always improves or leaves alone; a text that pulls the voice up three times in a row stays
high (the Italian last beat: the kind of line the new lengthening prompt and the wording rule now discourage). Cost: the retakes only, about a quarter to a
half more characters for a video with a lively voice (0.004 to 0.01 USD on a 45 s video), nothing for steady voices; latency up to 4 s of waiting plus one
or two requests of 1 to 3 s for the beats said again, in parallel with the other beats' media. A third retake would catch more of the stubborn beats for
more characters: not done.

## 8. Music under a quieter voice (`audio.level_speech`)

Polly's voices do not come at one level: speech power is -23.6 dB for Sergio, -22.9 for Beatrice (and -23.7 to -21.3 from one of her beats to the next),
-21.7 for Ruth, -20.4 for Kiara, -16.3 for Tina. The music bed is ducked by how loud the voice is, so under a quieter voice it was ducked less and sat
nearer: QA measured 9.9 dB under Beatrice against 11.5 to 14.1 before. The duck target was not changed; every beat is now brought to Ruth's speech level
(at most 6 dB either way, never into clipping) before the mix. With the engine's ducking filter and a steady stand-in for music:

| Voice (QA stems) | Music under speech, as stored | levelled |
|---|---|---|
| Ruth | 21.1 dB | 21.2 dB |
| Beatrice | 18.0 dB (3.1 less than Ruth) | 20.3 dB (0.8 less) |
| Lupe | 19.6 dB | 20.1 dB |
| Lucia and Andrés | 19.8 dB | 20.7 dB |

The absolute figures depend on the track (the stand-in is not a real one); the difference between voices is what the levelling removes. English with
Ruth or Amy is unchanged (a gain of 0.0 and about +0.3 dB).

## 9. Wording for the voice (`plan.SPOKEN_RHYTHM_RULE`)

The first study found that a rewrite with a question, two exclamations and short sentences lifted Beatrice from 5.0 to 6.8 st and read like a children's
programme. The rule added to the director's prompt is modest: vary the length of sentences, a real question where a viewer would ask one (answered at
once, never one in every beat), the connectives and everyday forms of the spoken language, numbers the way they are said, at most one exclamation mark in
a video, no slogan as a last line. It applies to every language and to every section of a long video; `SPOKEN_RHYTHM=0` turns it off.

Three 45 s plans written by the real model without and with the rule (plan stage only, no research), each said beat by beat by the default voice, one take:

| Plan (voice) | Pitch spread inside beats (st): before / after | Range 5-95% (st) | Between beats (st) | Sentences: mean words (sd) | Questions | Exclamations |
|---|---|---|---|---|---|---|
| English, volcanoes (Ruth) | 4.3 / 4.2 | 14.1 / 14.0 | 6.3 / 0.4 | 10.0 (3.0) / 11.6 (5.4) | 1 / 1 | 0 / 0 |
| Spanish, the stock market (Lupe) | 4.8 / 4.7 | 15.6 / 14.8 | 3.4 / 1.0 | 7.6 (3.0) / 10.7 (3.8) | 1 / 1 | 0 / 0 |
| Italian, the blue sky (Beatrice) | 5.2 / 5.2 | 16.1 / 15.0 | 4.2 / 2.3 | 11.1 (3.8) / 11.0 (1.2) | 1 / 1 | 0 / 0 |

Honest reading: **the rule does not move pitch spread** (differences are inside the 0.3 st of take noise). The director already wrote one question and no
exclamations without it. What changed is the text: fewer strings of very short sentences, more linking ("so it slowly rises", "y tú, al comprarlas, te
vuelves socio", "así que invierte con calma"), no punch line at the end. The register between beats was steadier in all three "after" scripts (6.3 to 0.4,
3.4 to 1.0, 4.2 to 2.3), which fits the finding of section 7 that short emphatic lines pull the voice up, but three plans and one take each cannot prove
it. Going further (more questions, exclamations) is what the first study showed lifts the voice, and is the owner's call by ear (`voice_it_7` of the first
sample set).

## 10. Tests

`tests/test_polly_lively.py` (new, 56 tests): the table of defaults and second voices for 34 language and region pairs, the accents without a lively
voice, Spain's rule, the resolver's preference and its limits, steady voices by name, conversations, the cast per language and per region, the fits and
Beatrice's real beats, the sentence cut on audio, the guard on the Italian plan (added sentences first; then the script-cut rules; a video that fits is
untouched), the timeline step with storage, the lengthening prompt and the echo check with the Italian plan, the register (pitch measurement, the
reference, who is said again, the step with takes, the three real takes of the Italian beats), the speech level, the wording rule in every language.
Fixture: `tests/fixtures/plans/it_blue_sky_beatrice_plan.json`. Expectations that named the old defaults were updated in `test_languages.py`,
`test_engine.py`, `test_voice_quality.py`, `test_presenters.py`, `test_length_fit.py`.

Run, one process: `test_polly_lively`, `test_voice_quality`, `test_languages`, `test_length_fit`, `test_presenters`, `test_engine`, `test_art_direction`,
`test_length`, `test_staged` (605 tests) and `test_engine`, `test_silence`, `test_sync`, `test_quality_fixes`, `test_looks`, `test_skills`,
`test_making_status`, `test_create_options`, `test_quality_backlog` (377): all pass. The whole suite was not run (the laptop's limit).

## 11. Not verified

- **How any of it sounds.** Nobody listened: not the new defaults, not a sentence cut out of real audio, not a beat said again, not the levelled mix.
- Nothing was deployed. The guard, the register step and the levelling have run on real audio on this laptop and in tests with fake storage, never on
  Lambda. The register step waits for other functions' files in S3: its timing in a real run is untested (on any error the first take stands).
- The register step's success rate rests on two plans and three takes of each.
- The writing in French, German, Portuguese, Dutch, Polish and Finnish with the new rule was not generated or read. The Italian additions were read by
  nobody who speaks Italian.
- Accent quality: Lupe's accent is Polly's "US Spanish" and now reaches every Spanish speaker outside Spain; Kiara, Ambre, Florian, Lennart and Carlos
  have never been heard by the owner.
- The new voices' fits rest on 4 or 5 real beats each (Beatrice 12, Lupe 23).
- A cartoon video's voices for French, German, Italian and Portuguese viewers changed and none was rendered.

## 12. Spend

1.66 USD of the 2 USD limit: Polly generative 1.28 (every voice on two passages 0.82, the register study 0.19 and its real retakes 0.04, real beats of
eight voices 0.14, the six narrations of the wording test 0.10), the script model 0.38 (twelve calls for six plans 0.376, one lengthening call 0.006). No
other provider was called. Ledger: one line per request, with the lab scripts, in the session scratchpad (`lab2/ledger.jsonl`). The samples cost nothing
(takes already paid for).
