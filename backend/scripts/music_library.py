#!/usr/bin/env python3
"""Build the curated background-music library with Google's Lyria 3.5 (Gemini API): generate, listen, approve, publish.

  pip install google-genai                      # once (the script imports it only when generating)
  export GEMINI_API_KEY=...                     # or GEMINI_API_KEY=... in the repo's .env (create it at https://aistudio.google.com/apikey; Lyria needs a paid tier)
  python scripts/music_library.py list                              # the 24 briefs
  python scripts/music_library.py generate [--only id,id] [--budget 3.00]   # about $0.08 per track; writes drafts to ./music-draft/
  (listen to music-draft/*.mp3; delete or regenerate the ones you do not like, edit descriptions in music-draft/catalog.json)
  python scripts/music_library.py publish --profile qa [--only id,id]       # uploads the approved tracks and the catalogue to s3://<assets bucket>/music/

The catalogue's `description` is what the planner reads to choose a track, so it says what to EXPECT (mood, instruments, energy, what it suits). Edit it freely.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

COST_PER_TRACK = 0.08          # Lyria 3.5, per song, from the pricing page (check it before a big run)
MODEL = "lyria-3.5"
COMMON = ("Instrumental background music for an explainer video. No vocals, no lyrics, no spoken words, no sound effects. Steady and unobtrusive under a narrator's voice: "
          "no sudden loud moments, no abrupt endings, a gentle intro and a fade-friendly ending. About two minutes. ")

# id, title, mood tags, energy 1-5, bpm, key, brief (what to make), description (what the planner reads: what to expect and what it suits)
BRIEFS = [
    ("calm-pad-dawn", "Calm pad, dawn", ["calm", "reflective"], 1, 62, "A minor", "Slow weightless ambient synth pads with a few soft bell notes, 62 bpm, A minor, spacious reverb, no drums.",
     "Slow, weightless ambient pads with a few soft bell notes, no drums. Very quiet and spacious: science, nature, meditation, long explanations."),
    ("soft-piano-memory", "Soft piano, memory", ["emotional", "thoughtful"], 2, 72, "C major", "Gentle felt piano arpeggios over a warm string pad, 72 bpm, C major, tender and nostalgic.",
     "Gentle felt-piano arpeggios over warm strings, tender and a little nostalgic. History, people, personal stories, reflection."),
    ("lofi-evening", "Lo-fi evening", ["relaxed", "modern"], 2, 78, "D dorian", "Mellow lo-fi hip hop with dusty drums, warm Rhodes chords and a soft bass, 78 bpm, relaxed swing.",
     "Mellow lo-fi: dusty drums, warm electric piano, soft bass, relaxed swing. Everyday topics, culture, modern life, study and how-to."),
    ("bright-pluck-morning", "Bright plucks, morning", ["upbeat", "positive"], 3, 100, "G major", "Upbeat bright major-key plucked strings and light claps, 100 bpm, optimistic and clean.",
     "Upbeat, bright plucked strings and light claps, optimistic and clean. Tips, learning, kids, positive news, everyday science."),
    ("cinematic-rise", "Cinematic rise", ["tense", "epic"], 3, 60, "D minor", "Deep drones and slowly building cinematic strings with sparse low hits, 60 bpm, d minor, restrained and spacious, no loud climax.",
     "Deep drones and slowly building strings, sparse low hits, never loud. Documentary, space, mystery, big ideas, stakes."),
    ("tense-pulse", "Tense pulse", ["tense", "urgent"], 3, 96, "E minor", "Dark pulsing synth bass, ticking hi-hats and low strings, 96 bpm, e minor, suspenseful but restrained.",
     "Dark pulsing bass with ticking hats and low strings, suspenseful but restrained. News, risk, finance, problems, thrillers."),
    ("acoustic-warm", "Acoustic warm", ["warm", "human"], 3, 88, "D major", "Warm fingerpicked and strummed acoustic guitar with a light shaker groove and soft upright bass, 88 bpm, D major, friendly.",
     "Warm strummed and fingerpicked acoustic guitar, light shaker, soft bass. Travel, food, family, nature, human stories."),
    ("minimal-tech", "Minimal tech", ["clean", "modern"], 3, 108, "F minor", "Clean minimal electronic music: sparse bell-like arpeggios, a soft steady kick and subtle sub bass, 108 bpm, f minor.",
     "Clean, minimal electronic: sparse bell-like arpeggios, soft steady kick. Technology, software, data, engineering."),
    ("uplifting-business", "Uplifting business", ["uplifting", "motivating"], 3, 104, "C major", "Uplifting corporate pop instrumental with bright piano, plucks, handclaps and a steady beat, 104 bpm, C major, builds gently.",
     "Uplifting and steady: bright piano, plucks, handclaps, gentle build. Business, progress, achievements, product stories."),
    ("dreamy-bells", "Dreamy bells", ["wonder", "gentle"], 1, 66, "F major", "Music-box bells and celesta over airy pads, 66 bpm, F major, magical and gentle, no drums.",
     "Music-box bells and celesta over airy pads, magical and gentle, no drums. Wonder, space, childhood, fairy-tale stories."),
    ("nature-strings", "Nature strings", ["calm", "organic"], 2, 70, "E major", "Calm organic chamber strings with soft flute and harp, 70 bpm, e major, open and breathing like a landscape.",
     "Calm chamber strings with flute and harp, open like a landscape. Nature, wildlife, geography, travel scenery."),
    ("travel-folk", "Travel folk", ["adventurous", "warm"], 4, 112, "A major", "Light upbeat folk instrumental with acoustic guitar, mandolin, soft stomp and clap rhythm, 112 bpm, A major, adventurous and sunny.",
     "Sunny upbeat folk: acoustic guitar, mandolin, soft stomp and clap. Travel, adventure, cultures, road trips."),
    ("mediterranean-sun", "Mediterranean sun", ["warm", "romantic"], 3, 92, "E minor", "Warm Mediterranean instrumental with nylon-string guitar, soft hand percussion and a light accordion, 92 bpm, e minor, sunlit.",
     "Sunlit nylon-string guitar with soft hand percussion and a touch of accordion. Southern Europe, food, cities, holidays."),
    ("jazz-cafe", "Jazz cafe", ["relaxed", "sophisticated"], 2, 84, "Bb major", "Soft late-night jazz trio instrumental: brushed drums, upright bass and gentle piano, 84 bpm, Bb major, unhurried.",
     "Late-night jazz trio: brushed drums, upright bass, gentle piano, unhurried. Culture, design, food, city life, interviews."),
    ("documentary-wonder", "Documentary wonder", ["curious", "uplifting"], 2, 76, "G major", "Gentle documentary underscore with warm strings, soft piano and light percussion, 76 bpm, G major, curious and wide-eyed.",
     "Gentle documentary underscore: warm strings, soft piano, light percussion, curious and wide-eyed. Science and discovery explainers."),
    ("history-solemn", "History, solemn", ["serious", "reflective"], 2, 64, "D minor", "Solemn reflective underscore with low cello, soft piano and distant pads, 64 bpm, d minor, dignified, no drums.",
     "Solemn and dignified: low cello, soft piano, distant pads, no drums. History, war and memory, serious subjects."),
    ("inspire-build", "Inspire, building", ["inspiring", "hopeful"], 4, 98, "E major", "Inspirational instrumental that builds slowly from piano to light strings and soft drums, 98 bpm, E major, hopeful, never bombastic.",
     "Hopeful, slowly building from piano to strings and soft drums, never bombastic. Success stories, motivation, the takeaway of a talk."),
    ("playful-kids", "Playful", ["playful", "light"], 4, 118, "C major", "Playful light instrumental with pizzicato strings, xylophone and a bouncy bass, 118 bpm, C major, cheerful and whimsical.",
     "Cheerful and whimsical: pizzicato strings, xylophone, bouncy bass. Kids, fun facts, light-hearted explainers."),
    ("mystery-night", "Mystery, night", ["mysterious", "dark"], 2, 68, "C# minor", "Mysterious night underscore: muted piano, soft low synth drone, subtle textures, 68 bpm, c sharp minor, creeping but quiet.",
     "Quiet, creeping mystery: muted piano, low drone, subtle textures. Unsolved questions, the unknown, true-crime-style explainers."),
    ("electro-chill", "Electro chill", ["chill", "modern"], 3, 100, "A minor", "Chilled electronic instrumental with warm synth chords, soft side-chained pads and a light beat, 100 bpm, a minor, smooth.",
     "Smooth chilled electronic: warm synth chords, soft pads, light beat. Technology, startups, modern culture."),
    ("hopeful-ambient-piano", "Hopeful ambient piano", ["hopeful", "calm"], 2, 74, "Eb major", "Ambient piano with a slowly evolving string pad and soft reverb tails, 74 bpm, Eb major, hopeful and open.",
     "Hopeful ambient piano over a slow string pad. Health, wellbeing, the future, positive closing moments."),
    ("meditative-drone", "Meditative drone", ["calm", "still"], 1, 50, "C major", "Meditative evolving drone with singing bowls and very soft pads, no rhythm, no melody, slow and still.",
     "Almost still: evolving drone, singing bowls, very soft pads, no rhythm. Silent beats, breathing and mindfulness, minimal narration."),
    # ---- round 2 (2026-11-24): more dynamic and more varied, after the first round turned out calm-heavy (nothing above 118 bpm, no groove- or percussion-led tracks)
    ("driving-electro-pop", "Driving electro pop", ["energetic", "modern"], 5, 124, "F# minor", "Driving modern electro-pop instrumental: four-on-the-floor kick, bright plucked synth arpeggios, side-chained pads and a rolling bass, 124 bpm, f sharp minor, energetic and propulsive but clean and steady, no drops.",
     "Driving four-on-the-floor electro pop with bright synth plucks and rolling bass: propulsive and modern, steady energy. Product launches, innovation, fast-moving tech, countdowns and top-10 lists."),
    ("indie-pop-sunshine", "Indie pop sunshine", ["upbeat", "fresh"], 4, 116, "A major", "Bright indie-pop instrumental: clean jangly electric guitar, handclaps, bouncy bass, glockenspiel accents and live drums, 116 bpm, A major, sunny and fresh.",
     "Bright indie pop: jangly guitar, handclaps, bouncy bass, glockenspiel. Lifestyle, tips and hacks, creators, youth culture, feel-good explainers."),
    ("funk-groove", "Funk groove", ["groovy", "fun"], 4, 108, "E minor", "Tight instrumental funk groove: slap bass, clean wah-wah rhythm guitar, crisp drums and short muted horn stabs, 108 bpm, e minor, groovy but light.",
     "Groovy funk: slap bass, wah guitar, tight drums, light horn stabs. Fun facts, music and culture, design, quirky history, lighter business topics."),
    ("boom-bap-beat", "Boom-bap beat", ["urban", "confident"], 4, 92, "G minor", "Instrumental boom-bap hip hop beat: punchy dusty drums, warm Rhodes chords, deep bass and vinyl crackle, 92 bpm, g minor, confident head-nod groove.",
     "Confident head-nod hip-hop beat: punchy dusty drums, Rhodes, deep bass. Urban culture, money and markets, street history, sneaker and fashion stories."),
    ("synthwave-drive", "Synthwave drive", ["retro", "driving"], 4, 104, "A minor", "Retro synthwave instrumental: gated snare, pulsing analog bass, shimmering arpeggiated synths and warm pads, 104 bpm, a minor, nostalgic and driving.",
     "Retro 80s synthwave: pulsing bass, shimmering arpeggios, gated drums. Tech and gaming history, cars, the 80s and 90s, sci-fi, the future."),
    ("cinematic-percussive-drive", "Cinematic percussive drive", ["epic", "intense"], 5, 128, "C minor", "Intense cinematic hybrid-orchestral instrumental: driving taiko-style percussion, repeating low string ostinato and rising brass textures, 128 bpm, c minor, relentless forward motion, steady level, no huge crescendo.",
     "Driving percussion and a relentless string ostinato: intense, high stakes, steady level. Sports, space race, wars and rivalries, disasters, big battles of ideas."),
    ("rock-guitar-light", "Rock guitar, light", ["energetic", "bold"], 4, 120, "E major", "Light energetic instrumental rock: overdriven but clean-ish electric guitar riff, live drums with a steady backbeat and a driving bass, 120 bpm, E major, bold but not loud.",
     "Light, energetic rock: a clean riff, steady backbeat, driving bass. Sports, startups and challengers, cars, courage and competition."),
    ("bossa-nova-sunny", "Bossa nova, sunny", ["relaxed", "warm"], 3, 100, "D major", "Sunny bossa nova instrumental: nylon-string guitar with the classic syncopated rhythm, soft brushed percussion, upright bass and a little flute, 100 bpm, D major.",
     "Sunny bossa nova: syncopated nylon guitar, brushes, upright bass. Food and drink, Brazil and Latin culture, beaches, easy lifestyle topics."),
    ("afrobeat-sunny", "Afrobeat, sunny", ["rhythmic", "joyful"], 4, 112, "G major", "Joyful instrumental Afrobeat-inspired groove: interlocking clean guitar plucks, layered hand percussion, a rolling bass and bright mallet accents, 112 bpm, G major, steady and warm.",
     "Joyful interlocking guitars and layered percussion with a rolling bass. World cultures, music and dance, markets and cities, celebration, growth."),
    ("swing-jazz-upbeat", "Swing jazz, upbeat", ["jaunty", "nostalgic"], 4, 138, "F major", "Upbeat instrumental swing: walking upright bass, swing drums with brushes, bright piano and a light clarinet, 138 bpm, F major, jaunty and good-humoured.",
     "Jaunty swing with walking bass, clarinet and bright piano. The 1920s to 40s, history with a smile, trivia, cities like New York and Paris, quirky stories."),
    ("baroque-strings-light", "Baroque strings, light", ["elegant", "clever"], 3, 100, "G major", "Elegant light baroque-style instrumental: harpsichord and pizzicato strings with a flowing violin line, 100 bpm, G major, orderly and clever, not heavy.",
     "Elegant harpsichord and strings in a baroque style: orderly and clever. European history, science and mathematics, art, architecture, royalty."),
    ("newsroom-pulse", "Newsroom pulse", ["urgent", "informative"], 4, 120, "D minor", "Modern newsroom instrumental: a steady ticking pulse, low synth bass, punchy staccato strings and crisp percussion, 120 bpm, d minor, urgent but not alarming, consistent level.",
     "A steady ticking pulse, staccato strings and crisp percussion: urgent but not alarming. News roundups, current affairs, politics and economy, explainers about what just happened."),
    ("space-synth-wonder", "Space synth wonder", ["awe", "futuristic"], 3, 84, "B minor", "Futuristic space-themed instrumental: slowly evolving analog synth pads, soft pulsing arpeggios, deep sub bass and a few airy lead notes, 84 bpm, b minor, awe-inspiring and wide.",
     "Evolving synth pads, soft pulsing arpeggios, deep bass: vast and futuristic. Space, physics, artificial intelligence, the far future, science fiction."),
    ("east-asian-serene", "East Asian, serene", ["serene", "elegant"], 2, 80, "D minor", "Serene instrumental with East Asian-inspired colours: plucked zither-style strings, soft bamboo flute, gentle taiko-like low drum touches and warm pads, 80 bpm, pentatonic, d minor, calm and refined.",
     "Plucked zither strings, bamboo flute and warm pads, calm and refined. East Asia, tea, gardens and philosophy, travel in Japan and China, mindful topics."),
    # ---- round 2b: topics the first 37 briefs did not serve (coding and deep focus, comedy, noir mystery, retro gaming)
    ("deep-focus-electronic", "Deep focus electronic", ["focused", "steady"], 2, 90, "A minor", "Minimal deep-focus electronic instrumental: a soft steady pulse, muted warm bass, sparse airy synth textures and a very quiet hi-hat, 90 bpm, a minor, almost no melody, constant and unobtrusive so it never competes with speech.",
     "Steady minimal electronic with almost no melody: it stays out of the way. Coding and programming, software and data tutorials, study, long technical explanations."),
    ("sitcom-quirky", "Sitcom quirky", ["funny", "light"], 4, 112, "F major", "Light comic sitcom-style instrumental: pizzicato strings, clarinet, bouncy upright bass, finger snaps and a muted trombone, 112 bpm, F major, cheeky and good-humoured, steady level.",
     "Cheeky and light: pizzicato, clarinet, bouncy bass, finger snaps. Funny explainers, myths and mistakes, awkward situations, parodies, everyday absurdities."),
    ("noir-slow-jazz", "Noir slow jazz", ["mysterious", "smoky"], 2, 70, "E minor", "Slow smoky noir jazz instrumental: muted trumpet, brushed drums, upright bass and a lonely piano, 70 bpm, e minor, late night and mysterious.",
     "Smoky noir: muted trumpet, brushes, lonely piano. True crime and unsolved cases, detective stories, scandals, dark history of cities."),
    ("chiptune-adventure", "Chiptune adventure", ["playful", "retro"], 4, 126, "C major", "Upbeat chiptune video-game instrumental: 8-bit square and triangle wave melodies, a bouncy bass, light noise drums, 126 bpm, C major, adventurous and nostalgic, no harsh sounds.",
     "8-bit game music: bouncy, nostalgic and adventurous. Video games and their history, retro tech, programming for fun, quests and challenges, playful tech topics."),
]
SPEC = {b[0]: dict(zip(("id", "title", "mood", "energy", "bpm", "key", "brief", "description"), b)) for b in BRIEFS}
DRAFT = os.path.join(os.getcwd(), "music-draft")


def load_dotenv_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    for d in (os.getcwd(), os.path.join(os.path.dirname(__file__), "..", ".."), os.path.join(os.path.dirname(__file__), "..")):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for line in open(p):
                m = re.match(r"\s*GEMINI_API_KEY\s*=\s*['\"]?([^'\"\s#]+)", line)
                if m:
                    return m.group(1)
    return ""


def duration_of(path: str) -> float:
    from engine import media

    return media.ffprobe_duration(path)


def generate_one(client, spec: dict) -> bytes:
    prompt = f"{COMMON}{spec['brief']}"
    try:
        interaction = client.interactions.create(model=MODEL, input=prompt)
    except TypeError:  # an SDK version that takes the request as one object
        interaction = client.interactions.create(request={"model": MODEL, "input": prompt})
    return base64.b64decode(interaction.output_audio.data)


def cmd_list(_a) -> None:
    for s in SPEC.values():
        print(f"{s['id']:24s} energy {s['energy']} {s['bpm']:3d} bpm {s['key']:9s} {s['description'][:78]}")
    print(f"\n{len(SPEC)} briefs, about ${len(SPEC) * COST_PER_TRACK:.2f} to generate them all.")


def cmd_generate(a) -> int:
    key = load_dotenv_key()
    if not key:
        print("No GEMINI_API_KEY (environment or .env). Create one at https://aistudio.google.com/apikey and link a paid billing account: Lyria has no free tier.", file=sys.stderr)
        return 2
    try:
        from google import genai
    except ImportError:
        print("pip install google-genai", file=sys.stderr)
        return 2
    client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})   # Lyria 3.5 is served on v1beta
    ids = [i for i in (a.only.split(",") if a.only else SPEC) if i]
    unknown = [i for i in ids if i not in SPEC]
    if unknown:
        print("unknown ids:", unknown, file=sys.stderr)
        return 2
    os.makedirs(DRAFT, exist_ok=True)
    cat_path = os.path.join(DRAFT, "catalog.json")
    catalog = json.load(open(cat_path)) if os.path.isfile(cat_path) else {"version": 1, "tracks": []}
    known = {t["id"]: t for t in catalog["tracks"]}
    spent = 0.0
    for tid in ids:
        out = os.path.join(DRAFT, f"{tid}.mp3")
        if os.path.isfile(out) and not a.force:
            print(f"{tid}: already generated (use --force to make it again)")
            continue
        if spent + COST_PER_TRACK > a.budget:
            print(f"stopping: the next track would pass the ${a.budget:.2f} budget")
            break
        spec = SPEC[tid]
        print(f"{tid}: generating...", flush=True)
        for attempt in (1, 2):
            try:
                audio = generate_one(client, spec)
                break
            except Exception as e:
                print(f"   attempt {attempt} failed: {type(e).__name__}: {str(e)[:200]}")
                audio = b""
                time.sleep(4)
        if not audio:
            continue
        with open(out, "wb") as fh:
            fh.write(audio)
        spent += COST_PER_TRACK
        secs = round(duration_of(out), 1)
        known[tid] = {"id": tid, "title": spec["title"], "description": spec["description"], "mood": spec["mood"], "energy": spec["energy"], "bpm": spec["bpm"], "key": spec["key"], "seconds": secs,
                      "prompt": spec["brief"], "source": f"Google Lyria 3.5 (Gemini API), generated {time.strftime('%Y-%m-%d')}, SynthID-watermarked"}
        print(f"   {secs:.0f} s -> {out}")
        catalog["tracks"] = [known[k] for k in SPEC if k in known]
        json.dump(catalog, open(cat_path, "w"), indent=1)
    print(f"done. about ${spent:.2f} spent. Listen to {DRAFT}/*.mp3, delete the ones you do not want, then publish.")
    return 0


def cmd_publish(a) -> int:
    import boto3

    cat_path = os.path.join(DRAFT, "catalog.json")
    if not os.path.isfile(cat_path):
        print("nothing to publish: run generate first", file=sys.stderr)
        return 2
    catalog = json.load(open(cat_path))
    only = set(a.only.split(",")) if a.only else None
    tracks = [t for t in catalog["tracks"] if os.path.isfile(os.path.join(DRAFT, t["id"] + ".mp3")) and (only is None or t["id"] in only)]
    if not tracks:
        print("no approved tracks (a track is approved when its mp3 is still in the draft folder)", file=sys.stderr)
        return 2
    s = boto3.Session(profile_name=a.profile, region_name=a.region)
    bucket = a.bucket or f"videomk-{a.profile}-{s.client('sts').get_caller_identity()['Account']}"
    s3 = s.client("s3")
    for t in tracks:
        s3.upload_file(os.path.join(DRAFT, t["id"] + ".mp3"), bucket, f"music/{t['id']}.mp3", ExtraArgs={"ContentType": "audio/mpeg"})
        print("uploaded", t["id"])
    public = {"version": 1, "tracks": [{k: v for k, v in t.items() if k not in ("prompt", "source")} for t in tracks]}   # the planner never needs the prompt or provenance
    s3.put_object(Bucket=bucket, Key="music/catalog.json", Body=json.dumps(public, indent=1).encode(), ContentType="application/json")
    json.dump({"version": 1, "tracks": tracks}, open(os.path.join(DRAFT, "published.json"), "w"), indent=1)   # the full record, with prompts and provenance, stays with you
    print(f"published {len(tracks)} tracks and the catalogue to s3://{bucket}/music/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("generate")
    g.add_argument("--only", default="")
    g.add_argument("--budget", type=float, default=3.0)
    g.add_argument("--force", action="store_true")
    p = sub.add_parser("publish")
    p.add_argument("--profile", default="qa")
    p.add_argument("--region", default="eu-west-1")
    p.add_argument("--bucket", default="")
    p.add_argument("--only", default="")
    a = ap.parse_args()
    return {"list": lambda: cmd_list(a) or 0, "generate": lambda: cmd_generate(a), "publish": lambda: cmd_publish(a)}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
