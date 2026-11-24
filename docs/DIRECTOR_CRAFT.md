# What the director knows about engaging videos (2026-11-24)

The pause and big-word rules were seasoning the model applied by default ("include a few silent beats"), and once it printed "SILENCE" over a picture. They are now decisions, and the prompt carries a craft section distilled from the research below (`plan.system_prompt`, "Craft"). Most sources are vendor and creator blogs: the numbers are rules of thumb, not measurements; the Mayer principles are the only peer-reviewed ground.

| Principle | Where it comes from | What the director is told |
|---|---|---|
| The opening decides who stays: hook in the first 3 to 15 s, curiosity not the full answer | explainer-video guides (Wyzowl, Yans Media, Entrepreneur), YouTube retention guides: the curve rarely recovers what it loses early | open with a surprising fact, a vivid question or a tension; never greet or announce the agenda; open a question early, pay it off later |
| Change something on screen often, but plan it | pattern-interrupt guides (every few seconds to a minute); excess cutting costs viewers | change the picture every beat; vary visual type, pace or music at section changes, turns and surprises |
| B-roll only helps when it illustrates what is said (3 to 7 % in one controlled creator test; generic footage did nothing) | Opus B-roll test (single creator, anecdotal) | the picture must show what is being said at that moment |
| Slow down for what matters; a 1 to 2 s pause before a key statement | pacing guides | vary rhythm; pauses only for a named reason (a number or fact landing, a picture that is the point, a mood change, before the key line) |
| Signaling and coherence: highlight what is essential, cut the decorative | Mayer's multimedia principles | on screen only key words, numbers and labels, never the narrated sentence |
| Segmenting: one idea per chunk, with clear transitions | Mayer segmenting principle | one idea per beat; sections hand over with a link; chapters |
| Personalization and voice: conversational language | Mayer (human voice, conversational style) | short sentences, concrete nouns, numbers with a comparison |

## Pauses and the big word
- A pause is a beat with no narration; the director writes `why` (kept in the plan for review, never shown).
- Guidance: usually none under 2 minutes, about one every 2 to 3 minutes in longer videos; never two in a row, first or last; hard cap one in four (`enforce_silence`). In staged videos each section may use at most one.
- The big word is optional and rare, and defaults to none. A word about the pause or sound (silence, pause, quiet, listen, breathe, music and translations) is dropped by the sanitizer.

## Sources
- Wyzowl, "How long should my explainer video be"; Yans Media, "7 explainer video openings that hook viewers in 5 seconds"; Vyond, "6 explainer video best practices"; VEED, "how to get and keep attention"
- Search Engine Land, "Audience retention"; pixflow, "YouTube video retention editing"; Opus, "Does B-roll increase watch time?"
- Mayer's 12 principles of multimedia instruction (NUS Medicine summary; Cambridge Handbook of Multimedia Learning; PMC7940870)

## Not done
- Nothing measures whether the new guidance improves retention: it needs real viewing data (the app has no analytics). Until then these are informed defaults.
- The research found no reliable words-per-minute figure; the engine keeps its own measured 2.4 words per second.
