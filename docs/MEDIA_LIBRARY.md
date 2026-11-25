# My media: a private photo library with search (designed 2026-11-25)

People keep their photos in videomk, find them by describing them ("my holidays in Thailand in 2024"), organise them in collections, and make videos
from them without picking files each time. Free accounts get **2 GB**, Pro **100 GB** a month, plus add-on blocks of **100 GB**
(server settings, no app update).

## What the person sees (UX)
**A "Media" tab** next to Videos (bottom bar on both apps).
1. **Header**: title, a slim storage meter ("1.2 GB of 2 GB", turns amber at 85 %, red when full) that opens the *Storage* sheet (plan, usage, what
   happens when it is full; the upgrade button appears only when the server says `can_upgrade`, so nothing is shown that does not work yet).
2. **Search bar**: "Search your photos - try 'beach in Thailand 2024'". Typing runs a search after a short pause. The question is understood, and
   what was understood is shown as removable chips ("Thailand", "2024") above the results, so the person sees why a photo is there and can drop a
   chip. Empty search shows the timeline.
3. **Collections strip** (horizontal): cards with a cover, name and count, and a "+" card. A photo can be in several collections (like tags), so
   "Family" and "Thailand" can both hold the same photo. Opening one shows its photos; long-press renames or deletes (the photos stay in the library).
4. **Timeline grid**: square thumbnails, 3 columns on a phone (4 on tablets), grouped under sticky headers (month and year; day when a month has many),
   newest first by the day the photo was taken (upload day when unknown). Tap opens the viewer (swipe between photos, pinch to zoom, info with date,
   place, size and collections, add to collection, delete, "Make a video from this").
5. **Selecting**: long-press a photo to start selecting, drag to select more. A bottom bar offers *Add to collection*, *Make a video*, *Delete*;
   "Select all in this view" when searching ("make a video of everything from Thailand 2024" is search, select all, make a video).
6. **Adding photos**: "+" opens the system photo picker (multi-select, no limit per batch). Uploading runs in a queue with one calm banner at the top
   ("Uploading 37 of 120 - 640 MB") with pause and cancel. Photos already in the library (same content) are skipped and counted ("12 were already
   in your library"). When the storage would be exceeded the photos that fit are uploaded and the rest are named in one clear message with the
   Storage sheet one tap away. The banner survives leaving the tab; if the app is closed the queue stops and resumes on next launch (no silent loss).
7. **Making a video from my media**: in the composer, next to the photo button there is **"My media"**. It opens the same grid with the search bar and
   selection (up to 100). When the video prompt itself describes photos ("a video of my holidays in Thailand in 2024"), the sheet opens with
   **"Photos from your prompt"** already searched, preselected and with the chips visible; the person can adjust and confirm. The selection joins any photos
   picked from the phone (100 in total) and the length hint ("About 85 of your 100 photos fit in 2 minutes...") applies to the total.
8. **Empty, loading and error states**: friendly empty state with one button; skeleton tiles while loading; offline shows what is cached; every error says
   what to do next. Accessibility labels for every control (the photo's date and place are its label), Dynamic Type, reduced motion.
9. **Privacy copy** (on the first visit and in Settings): "Your photos are private to you. Only you can see them. Nobody at videomk browses them.
   They are used to find your photos and to make the videos you ask for. Delete any photo or everything, any time."

## How it works (backend)
```
phone ──(1) POST /library/uploads {size, sha256, taken?, lat?, lon?}──► API Lambda: auth, quota, dedupe, place name from the coordinates (then forgotten)
      ◄── presigned POST (key o/<you>/<id>.jpg, size <= declared, JPEG only, Intelligent-Tiering) ──
phone ──(2) upload straight to S3 ──► media bucket ──event──► SQS ──► Ingest Lambda (max 6 at once)
        Ingest: checks key owner and size, decodes the JPEG (bomb-safe), writes a 480 px thumbnail, asks Cohere Embed v4 for the image embedding,
        stores the vector in S3 Vectors, marks the photo ready. Bad file: deleted, quota released.
phone ──(3) GET /library/items, /library/search ──► items + short-lived presigned thumbnail links (only for photos the caller owns)
generate {library_media:[ids]} ──► launcher checks every id belongs to the caller, copies them to the video's own uploads (the engine is unchanged)
```
* **One bucket for media** (`videomk-<stage>-media-<account>`), private, TLS only, encrypted at rest, no CORS, no public policy, no listing by the apps.
  Keys: `o/<user>/<id>.jpg` (the photo as uploaded: already upright, at most 2048 px, no metadata, made by the app) and `t/<user>/<id>.jpg` (thumbnail); separate top-level prefixes so only originals trigger processing.
* **DynamoDB `MediaTable`** (on demand): `m#<id>` photo (status, bytes, size, taken, added, place, country, hash, collection ids), `h#<sha256>` dedupe pointer,
  `c#<id>` collection, `cm#<collection>#<sort>#<id>` membership (so a collection lists in time order), `facets` (counts per year, country, place for chips),
  `stats` (bytes used, photo count). GSI `Timeline` (user, sort) is sparse: only ready photos. GSI `Pending` lists photos waiting for their file, for the sweeper.
* **S3 Vectors** index `photos` (1024 dimensions, cosine). Each vector's metadata: `user`, `ts` (taken, epoch seconds), `year`, `country`, `place`.
  Cohere Embed v4 (through Amazon Bedrock) puts photos and text in one space, so a text query finds photos directly (checked on real photos: every test description ranked the right photo first, even from a 256 px thumbnail; we embed a 384 px copy).
* **Search**: the question is read by the small model into `{text, from, to, places}`; places must be words from the person's own library (their facets), dates
  are checked. `text` is empty when the question only names a place or time ("my holidays in Thailand in 2024"), then the answer is the timeline filtered by
  those, chronological and complete (not a top-N guess). Otherwise: embed the text, query the vectors with filter `user = caller` plus the date and place
  filters, then read the rows to confirm each is the caller's and ready.
* **Place and time**: the phone sends the capture time and coordinates rounded to ~1 km at upload; the server turns them into a place name offline (same data as
  video photos) and **keeps only the name and country**, never the coordinates (the same rule as for videos).
* **Entitlements**: `AccountFlagsTable` (only an admin script can write it) holds `storage_plan`, `storage_extra_gb`, `storage_until`. Absent means free. Runtime
  functions only read it. A lapsed plan never deletes anything: the library becomes read, download and delete only until the person is back under the limit.

## Security (strictness is the point)
| Threat | Control |
|---|---|
| Reading or changing someone else's photos | The user id is only ever the Cognito `sub` from the verified token; the path id must equal it (403 otherwise). Every DynamoDB key and S3 key is built server-side from that `sub`; ids from the client are only ever looked up under the caller's own partition. A photo id that is not the caller's is "not found". Presigned links are made only after that lookup. |
| Tampered paging cursor | The cursor holds only the sort position; the partition key is always rebuilt from the token, never read from the cursor. |
| Vector search leaking another user's photo | Every query is built in one function that always adds `user = caller` to the filter (unit test: no query can be built without it), the results are looked up again under the caller's partition, and anything that is not the caller's is dropped and logged as `LIBRARY_FOREIGN_VECTOR` (an alarm on it is still to be wired to a notification topic). |
| Uploading something else, too large, or into another path | The presigned POST fixes the key (under the caller's prefix), `Content-Type: image/jpeg`, a size range up to the size declared, and the storage class; the ingest step decodes the file and refuses anything that is not a real JPEG within the pixel limit, deleting it. A key outside `o/<sub>/` is ignored and deleted. |
| Filling the account to cost us money | The declared sizes are reserved against the quota before any slot is issued (conditional update: no overspend under concurrency); daily caps on upload slots and on searches; the object cannot exceed what was declared. Unfinished slots are released by an hourly sweeper after 45 minutes (a file that arrived but was not processed is processed then). |
| Mass download of the bucket by a bug | Only the media Lambdas' roles can touch the bucket (the video launcher may only read `o/*` of a library photo to copy it); API Gateway authoriser on every route. |
| Prompt injection through a search | The model only returns a small JSON object that is validated; place words must be in the user's own vocabulary; nothing else it says is used. |
| Photos left behind | Delete removes the file, thumbnail, vector, rows and counts. `purge_user` removes everything of an account (the delete-account flow calls it). The 2-day expiry of uploads still applies to the video flow's temporary copies. |
| Reading by staff | No staff tool lists photos; logs never contain keys, names, places or queries (only ids and counts). |

## Cost (estimates; check the AWS pages for exact current prices)
| Item | Price | Per 1,000 photos (1.5 MB each, 1.5 GB) | Pro account full (100 GB, ~66,000 photos) |
|---|---|---|---|
| S3 Intelligent-Tiering, uploaded straight into it (no transition fee) | $0.023/GB-month at first, $0.0125 after 30 days unwatched, $0.004 after 90 days (still instant, no retrieval fee); monitoring $0.0025 per 1,000 objects | about $0.03 first month, $0.006 at rest | $2.30 first month, about $0.40 at rest, plus $0.17 monitoring |
| Thumbnails (480 px, about 30 KB, Standard) | $0.023/GB | $0.0007 | $0.05 |
| Cohere image embedding (384 px copy) | priced per image token, once per photo; measure on QA with the cost report before relying on it | about $0.1-0.5 (estimate) | $7-30 once (estimate) |
| S3 Vectors | storage about $0.06/GB-month (4 KB per vector), small put and query charges | $0.0003 | about $0.02 a month |
| DynamoDB on demand | about 3 writes per photo once | $0.004 | $0.25 once |
| Search (Cohere text + small model + vector query) | | about $0.0004 per search | |
| Viewing: thumbnails cached on the phone, full photo only when opened | $0.09/GB out | | a heavy month under $0.10 |
A Pro account that uses all 100 GB costs about **$0.6 a month at rest** (after the first 90 days) plus a one-off ~$4 to index; a free account at its 2 GB about $0.01 a month.
Pro pricing is the owner's decision; at $3.99 the margin is large and leaves room for the add-on blocks. Levers if needed: CloudFront for viewing, moving untouched
photos to Glacier Instant Retrieval after a year, and keeping the original-resolution file only for Pro.

## API (all routes need the Cognito token; `{user}` must be the caller's id)
Photo object: `{id, taken?: "YYYY-MM-DDTHH:MM:SS" (wall-clock time at the place, no zone), added: "YYYY-MM-DDTHH:MM:SSZ" (UTC), place?: "Phuket, Thailand", w, h, bytes, thumb_url, collections: [ids]}`; `GET .../items/{id}` adds `url`.
* `GET /users/{user}/library/summary` -> `{plan: "free"|"pro", limit_bytes, used_bytes, read_only (true when used > limit: a lapsed plan; uploads are refused, everything else works), count, can_upgrade, years: [{year, count}], places: [{name, country, count}], collections: [{id, name, emoji, count, cover_id?, cover_thumb_url?}]}`
* `POST /users/{user}/library/uploads` `{items: [{size, sha256, taken?, lat?, lon?}]}` (1..100) -> `{uploads: [{index, status: "upload"|"duplicate"|"no_space"|"rejected", id?, url?, fields?, duplicate_of?, reason?}], used_bytes, limit_bytes}`. Send `fields` as form fields, then the file last, to `url`. `no_space` for items that do not fit in the remaining storage. Asking again for a photo whose upload never finished (same sha256) returns a fresh link for the SAME photo id; `duplicate` is only answered for a photo that is really in the library.
* Photos that are still uploading or being indexed are not listed until they are ready (usually seconds after the upload finished). Upload links live 15 minutes.
* `GET /users/{user}/library/items?limit=60&cursor=&from=YYYY-MM-DD&to=&collection=&place=` -> `{items: [photo], cursor?}` newest first; `cursor` is opaque.
* `GET /users/{user}/library/items/{id}` -> `photo + {url}` (valid 10 minutes)
* `POST /users/{user}/library/items/delete` `{ids: [..<=100]}` -> `{deleted, used_bytes}`
* `POST /users/{user}/library/search` `{query, limit?: 1..100 (60)}` -> `{understood: {text?, from?, to?, places: [..], chips: [{kind: "place"|"date"|"topic", label}]}, items: [photo], mode: "timeline"|"semantic"}`; `chips` for the UI; removing a chip = search again with `{query, drop: [chip labels]}`
* `GET /users/{user}/library/collections` -> `{collections: [...]}`; `POST` same path `{name (1..40), emoji?}` -> collection; `POST .../collections/{cid}` `{name?, emoji?}`; `POST .../collections/{cid}/delete`; `POST .../collections/{cid}/items` `{add?: [ids], remove?: [ids]}` (<=100 each)
* Video: `POST /users/{user}/videos/generate` accepts `library_media: [ids]` (library photo ids); together with `media` at most 100. Unknown, foreign or unready ids give 400.
Errors: 400 bad input, 401, 403, 404, 409 conflict, 413, 429 (with `Retry-After`), 402 `{code: "storage_full", used_bytes, limit_bytes}` when nothing at all fits.
Client rules: cache thumbnails by photo id (the links expire after 1 hour but the image never changes), never assume `url` outlives 10 minutes, compute `sha256` of the exact bytes that will be uploaded.

## Not now
People tagging, original-resolution storage, video storage (the library holds photos; a clip import is next), sharing albums with others, offline sync of the whole library, CloudFront, in-app purchase for Pro and add-ons (the plan fields and screens are ready; billing comes with the store work).


## Backlog (parked by the owner, 2026-11-25)
- **Use my media automatically**: a switch (in the composer options or in Settings) so the video prompt itself filters My media in the cloud, with no manual selection: "make a video of my previous holidays in Thailand" finds the Thailand photos (search already understands place and time) and uses them. Not built: today the person selects photos, with a "Photos from your prompt" shortcut in the picker that runs the same search on the phone side and preselects. Server side it needs a `library_query` option on generate (the launcher runs `search` for the caller, caps at 100, keeps day order) and a clear line in the app saying which photos were found.
