# Selection without bloating the context: audit, pattern, migration (2026-11-27)

The owner's idea: the planner says what it wants ("British English") and tooling finds the exact thing, instead of every option being pasted into the planner's prompt. This document says what the engine does today for each kind of thing, the pattern now applied to voices, and what to move next.

Token figures are **estimates at 2.8 characters per token**, calibrated on real planner calls of 2026-11-27 (13,400 tokens of input for a 37,500-character prompt; this prompt is dense in braces and quotes, so it tokenises heavier than prose). Bedrock's token counter does not support the planner model, so sections could not be counted exactly; character counts are exact. Treat the token column as right to about 10 percent.

## 1. Audit: how each kind of thing reaches a model today

The planner (the script model, `engine/plan.system_prompt`) is called once per video, or once per section for a long video (each section call carries the whole prompt again). A typical call is 14,000 to 17,000 tokens of input, of which the request and research notes are 500 to 3,000.

| Thing | Options that exist | How it reaches a model today | Size in the planner prompt | Risk as it grows |
|---|---|---|---|---|
| **Voices** | 55 (was 28) | **Before:** the full list of the video's language in the prompt, the model picked a name. **Now:** intent fields only; a resolver casts (section 2) | Voices block 2,014 chars (about 720 tokens) for English before, of which the list was 548 chars (about 195 tokens); **now 1,621 chars (about 580 tokens) and constant** | Was linear in the catalogue. Now none |
| **Scene types and elements, with every option** | 13 built-in types, image/gallery, clip/montage, 29 elements in 10 families (4 more hidden) | Every type with all its properties is in the prompt, always (`scene_docs`, `registry.docs_by_family`) | Elements 13,577 chars (about 4,850 tokens); clip 3,968 (1,400); built-ins 2,508 (900); image 666 (240). **About 7,400 tokens, half the prompt** | **Highest.** Every new element adds 400 to 500 characters to every call, for every video, forever |
| **Music** | 40 tracks | The whole library (id, length, energy, tempo, a sentence each) is in the prompt; the model picks ids | 8,639 chars (about 3,100 tokens) with the sound-effect rule | **High.** Linear: 100 tracks would be about 7,500 tokens |
| **Rules and craft** | - | Fixed text | about 6,100 chars (2,200 tokens) | Grows by hand only |
| **Craft guides (skills)** | 30 guides | **Already two-step:** a small model sees a one-line menu (3,388 chars, about 1,200 tokens of the cheap model) and picks one or two; only those bodies reach the planner | about 3,900 chars (1,400 tokens) for a typical video | Low. The menu grows on the cheap model only |
| **Engagement rules** | - | Fixed text | 2,230 chars (800 tokens) | None |
| **Look of the video** (photo, cartoon, whiteboard, presenter) | 4 looks | **Already policy code:** rules plus, for whiteboard, one small-model judgement; the planner gets only the block of the look that was chosen | 0 when not chosen | None |
| **Presenter cast** | 10 characters | **Already a resolver:** `presenter_policy.cast` picks by the kind of video and topic words; no model call; character, side and voice are filled in by code | 1,578 chars (560 tokens) only in presenter videos; no list of characters | None |
| **Cartoon scenes** | a catalogue in S3 | **Already retrieval:** embedding search on the request returns 3 (or 6) candidates; only those ids are shown | about 60 chars per candidate | None. This is the model to copy |
| **Whiteboard objects** | 354 drawings | The ids of ALL objects, grouped by category, are in the prompt of a whiteboard video. **Hybrid search built 2026-11-28 (`engine/whiteboard/retrieval.py`, setting `WB_SEARCH`, shipped OFF)**: see docs/WHITEBOARD_DRAWING_SEARCH_2026-11-28.md | **Corrected: 3,704 chars (about 1,300 tokens), not 9,372, and not cut at the 9,000 cap** (the cap would bite at about 900 drawings). Search shows about 1,230 chars: saves about 880 tokens per call | Retrieval recall of what the planner chose was 65 % (K 60) to 88 % (K 200): it picks associated pictures (sun, wind, bank) that topic words do not reach, so it stays off until the library is far larger |
| **Backgrounds** | 6 styles, 5 palettes per theme, 4 pre-rendered loops | A separate small-model call with the short menu; a wish in the request ("purple 3D background") is settled by code with no model call | 0 in the planner; about 360 tokens on the cheap model | Low while loops are few; linear in loops |
| **Photos and clips (stock and our catalogues)** | unbounded | **Already search:** the planner writes a query (`image_query`, clip queries); stock search and the embedding catalogues resolve it; reviewers pick | 0 (only the rule text) | None |
| **Themes, mood** | 3 and 3 | Enumerated in the output format | a few tokens | None |
| **Sound effects** | a handful | Listed in the music rule | about 140 tokens | Low |

**So the owner's question "maybe it is already implemented like that" has a mixed answer.** The catalogues (photos, clips, cartoon scenes), the craft guides, the looks and the presenter cast already work that way. Voices did not (now they do). The two big lists still pasted in full are **the elements and their options (about half the prompt)** and **the music library (about a fifth)**; the whiteboard object list is the same problem inside whiteboard videos.

## 2. The pattern: intent in, resolver out (applied to voices)

1. **The planner states intent in a few structured fields.** For a speaker: `{"accent": "British", "gender": "male", "pace": "slow"}`, every field optional; `{}` means "the viewer's default"; `{"name": "Brian"}` when the request names a voice. The prompt lists only the accent words of the video's language (eight words for English) and how many women's and men's voices exist (so a dialogue is planned within what is possible).
2. **A resolver casts it: plain code, no model call** (`engine/voices.resolve`, `cast_voices`). It scores every free voice of the language: gender asked (6 points), accent asked (5; a neighbouring accent 3), the viewer's own accent when none was asked (2), the region's default voice (1), measured pace as a tie-break (0.5). A wrong gender is heard at once and a neighbouring accent is not, hence the order.
3. **Fallbacks are explicit and recorded.** No Irish male voice: the British one, and the plan says so in `voice_notes` ("no Irish voice for a male speaker: Brian (British, male) speaks instead"); the same line goes to the warnings. Accents nobody has a voice for map to the nearest (Scottish to British, Argentinian to Mexican, Portugal to Brazilian, Canadian English to American).
4. **Region defaults are unchanged** (Ruth, Amy, Kajal, ... Lucia, Mia, Lupe) and the request still wins over the region.
5. **The catalogue is data** (`engine/voice_data.py`, rebuilt from Polly by a script), with only what can be supported: language, accent, gender, engines, measured pace. There are no "warm" or "calm" labels because nobody has evidence for them; the planner's "pace" maps to the measured rate, and nothing else about manner is matched. Listening to the voices and adding honest tags (suits children's content, authoritative) is the natural next step, and the resolver would use them without any prompt change.

### What it saved, honestly

- English: the voices block went from 2,014 to 1,621 characters (**about 140 tokens, 1 percent of the prompt**). Spanish: 1,690 to 1,582 (about 40 tokens). Small, because the per-language list was small.
- The real gain is that **it no longer grows**: listing all 55 voices would have been about 550 tokens, and a provider with 200 voices would not fit at all. German (6 voices), French (8) and the rest were added at no prompt cost.
- **It also fixed a quality problem.** Plan audit (`scripts/eval_plans.py`, real planner calls, 2026-11-27):

| Case | Before (names from a list) | After (intent + resolver) |
|---|---|---|
| English solo, US | ok, Ruth | ok, Ruth |
| English, viewer in India, asks for a British voice | ok, Amy | ok, Amy |
| English dialogue of three | ok (Ruth, Matthew, Amy) | ok (Ruth, Brian, Russell; narrator Danielle) |
| Spanish solo, Mexico | ok, Mia | ok, Mia |
| **Spanish dialogue of three women** | **FAIL: one of the women was given Sergio, a man's voice** | **ok: Lucia, Mia, Lupe; narrator Sergio** |
| French solo (new) | not available (declined by rule) | ok, Léa |
| German dialogue of two (new) | not available | ok (Vicki, Daniel; narrator Tina) |
| Polish, asks for a male narrator (new) | not available | ok, Ola, with the note "no free male voice in Polish" |

  The five cases run both before and after are at least as good, one that failed now passes, and three new-language cases pass (a sixth case, a children's explainer, passed before and was not run again to stay inside the spending limit). The total input tokens of a call cannot be compared between runs (research notes differ from run to run by hundreds of tokens), so the saving above is from the prompt text itself, not from the totals. The audit cost $1.27 in model calls.

## 3. Resolver or tool call? An honest comparison

| | Resolver (intent in the plan, code matches afterwards) | Native tool use (`find_voice(...)` returns 3 candidates, the model picks) |
|---|---|---|
| Model round trips | none extra | at least one extra per kind of thing; the whole prompt is sent again each turn (14,000+ tokens, about 3 cents uncached) |
| Latency | none | 5 to 20 seconds per extra turn of the big model |
| Precision | as good as the fields and the scoring; cannot weigh something the fields do not express | the model sees real candidates and their descriptions and can weigh them against the script |
| Predictability, testability | deterministic: every case is a unit test | varies run to run |
| Failure modes | a wish outside the fields is ignored (recorded) | loops, extra turns, a tool the model forgets to call |
| When the model must know what exists in order to plan | weak: it plans blind | strong |

The deciding question is the last row. **A voice, a music track or a background does not change what the script says**, so the planner does not need to see the options: intent plus a resolver is enough, cheaper and testable. **An element does change the plan** (whether a comparison table exists decides how the beat is written), so the planner must know what exists; there the answer is a short menu first and the detail only for what was chosen.

## 4. Migration plan (only voices are implemented now)

| Order | Thing | Move to | Expected saving | Risk |
|---|---|---|---|---|
| 0 | The fixed part of the planner prompt | **Prompt caching** of the static prefix (scene list, rules), where the model on Bedrock supports it. Not a selection change, but the biggest lever: cached input is billed at a fraction, and a long video sends the same prefix once per section | most of the input cost of every call after the first within the cache window; to be measured | Low: no behaviour change. Needs the static text to come first and the per-video parts last |
| 1 | **Music** | **Resolver.** The planner states `{"mood": "calm", "energy": 2, "genre": "ambient", "changes": [{"beat": 9, "mood": "tense", "energy": 4}]}`; code matches against the library's own fields (mood, energy, bpm, description words), or by embedding the description as the catalogues do | about 2,900 tokens per call (a fifth of the prompt), and the library can grow freely | Medium. Today the model reads each track's sentence and chooses with the script in mind; a resolver must be compared on the plan audit and by ear on a handful of videos before switching |
| 2 | **Whiteboard objects** | **Retrieval**, like cartoon scenes: embed the request and the section goals, show the 40 to 60 closest drawings instead of all 354; `whiteboard/library` already resolves a plain name or synonym to an id | about 2,500 tokens per whiteboard call, and the menu stops being cut at its cap | Medium. A board needs many small objects; too short a menu makes boards sparse. Keep a core set always listed |
| 3 | **Elements and their options** | **Two-step (category, then detail).** The planner prompt keeps one line per element (name, what it is for: about 60 characters each, 2,000 characters in all) so it can still plan with everything in view; the full property list of an element is supplied only for the elements the plan uses, in a second, cheaper step that fills in the properties (the scene-repair step, `quality.repair_scenes`, already works this way for invalid scenes) | up to about 4,000 tokens of the big model per call; grows by one line, not one paragraph, per new element | **Highest.** It adds a model step and changes how every scene is written; property quality could drop. Do it last, behind a flag, with the plan audit and a visual review before and after. If prompt caching (step 0) lands first, most of the cost reason disappears and only the growth reason remains |
| 4 | Backgrounds | Resolver over loop tags once the loops pass about 20 (`{"feel": "calm, deep blue"}`); today's small-model call with a short menu is fine | about 300 tokens of the cheap model | Low |
| - | Photos, clips, cartoon scenes, craft guides, looks, presenter cast | Leave as they are: already search, two-step or policy code | - | - |

Rule of thumb for anything new: **if the choice does not change the script, the planner states intent and code resolves it; if it does, show a one-line menu and fetch the detail on demand; if the set is large or open, search it.** The full list of anything should not be added to the planner prompt again.
