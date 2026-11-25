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

## Pauses, how much the narrator talks, and music levels (2026-11-25)
**Finding:** an explainer is carried by its words, so a silent beat feels like a mistake there; a video built on pictures and mood (the person's own photos, travel, memories, tributes) is carried by the pictures, so a narrator who never stops turns an album into a lecture. The amount of silence therefore depends on the kind of video, not on a single rule.
- Sources (practical guides, not studies): a short pause before a key image or after an important term gives the picture room ([CapCut](https://www.capcut.com/create/photo-transition-timing-for-voiceover-slideshows)); an ending can hold a final picture while the music resolves or fades ([Narakeet](https://narakeet.com/docs/how-to/pause-voiceover-narration.html), [Capture](https://order.capture.com/blogs/insights/how-to-make-a-slideshow)); strategic silence amplifies emotional moments ([Fiveable](https://fiveable.me/filmmaking-for-journalists/unit-1/pacing-rhythm/study-guide/8KEiWbhX8vIlW4iP)); identical durations make a sequence feel automated even when the images are strong ([Sonilo](https://sonilo.com/blog/guides/make-slideshow-with-music)); audiences read photographs the way they read words, so they need time ([Descript](https://www.descript.com/blog/article/why-you-should-use-still-photographs-in-your-next-video)).
- Mixing guides put the voice around -12 to -6 dB and the music 10 to 20 dB below it while someone speaks (-18 to -24 dB), with ducking of 6 to 12 dB, attack 30 to 80 ms and release 250 to 700 ms, and warn that cutting 15 to 20 dB on every line lets the audience hear the automation, and that silence under a voice is as distracting as music that is too loud ([PremiumBeat](https://www.premiumbeat.com/blog/video-tutorial-mixing-voice-over-with-music-bed-using-dynamic-controls), [CapCut](https://www.capcut.com/create/audio-ducking-for-clear-dialogue-in-video)). I found no source on swells at the opening and ending; raising the bed where nobody speaks is general practice, written here as a design choice.
- **What the engine does:** music at about 22 % of the narration under speech, ducked by a sidechain (attack 15 ms, release 450 ms: inside those ranges), final mix levelled to -14 LUFS; in every pause beat the bed rises about 2.2x (about -6 dB) with 0.8 s ramps.
- **What changed:** the director's pause rule is type-aware (explanations, news, tutorials and lists: rarely; picture and mood videos: after every two to four narrated beats, up to one beat in three, `enforce_silence(share=0.34)` for videos of the person's photos); a new automatic guide, `photo-memories`, is added to every video made from the person's photos (short narration lines, let the pictures breathe, vary the rhythm, short first and last lines); and those videos get `intro_s = 2.5` (music and the first picture before the first word) and `outro_s = 3.5` (a held last picture with only the music), both with the bed raised like in a pause.
- **Not done:** pauses for other picture-led videos (travel without the person's photos, nature) rely on the guides only (the travel guide now suggests holding a striking view with only the music); no per-beat music volume control for the director; the narrator's breathing between sentences is whatever the voice service does.
