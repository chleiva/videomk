# Watermark (requirement R098, owner 2026-11-27)

> "A non-disruptive watermark that I can use to create promotional videos. With my premium account, when I add the company watermark, I can create videos that I can share ... with the videomk logo there, so people know it was created using videomk."

Backend and engine are built (flag on by default, nothing visible to users until the apps send or save the option). The apps and the web app only need to add the option (section 7).

## 1. What it is
* **`videomk` mode (everyone):** the VideoMK mark (one play triangle and two stars, docs/BRAND.md section 2), white with a soft shadow, drawn by the renderer on every frame. Optional `style: lockup` adds the word "VideoMK"; optional `end_card` appends a 2.4 s "Made with VideoMK" card after the last scene (off by default).
* **`custom` mode (premium):** the person's own logo (PNG, JPEG or SVG up to 2 MB, saved once, used on every video unless a request says otherwise), in its own colours.
* **`none`:** no watermark (the default).
* **Server side, not an overlay:** it is part of the render (`engine/watermark.py`, called last in `Renderer.frame_at`), so a client cannot drop it, and it is the same in previews, finals, edits and thumbnails.

## 2. Design rules (so it never disrupts)
| Rule | Value |
|---|---|
| Size | `small` = mark height 5 % of the short side (54 px at 1080p), `medium` = 7 %. A wide logo is capped at 6.3 x that height (the VideoMK lockup is 4.27 x; the mark alone 1.09 x). Drawn for the real output size from a 1024 px source that is only scaled down: crisp at 720p, 1080p and 4K (checked at 100 %). |
| Opacity | 0.2 to 1.0, default **0.65** |
| Margin | 3.5 % of the short side (2 % when something is near) |
| Colour | videomk mark: **white with a soft dark shadow on dark or mid pictures, brand ink (#11142b) with a soft white glow on light pictures**, blended smoothly by the brightness under the mark (never light-on-light; docs/brand/README.md). A custom logo is never tinted (it gets only the soft shadow). |
| Fade | In over 0.6 s at the start of the video (first chunk only); out with the closing fade to black. |
| Never on | the **captions** (their widest possible box), the **clip credit line** (top right), and for `auto` in 9:16 the **platform UI zones** |

Default corner (`position: auto`): **16:9 bottom right**; **9:16 top left** just under the platform header (TikTok / Reels / Shorts keep the top ~160 px, the right 130 px and the bottom 320 px for their own buttons; the mark sits in x 0-950, y 162-1600); **1:1 and 4:5 top left** (the captions use almost the whole bottom width there).
If the wanted spot touches a protected zone: smaller margin (2 %), then it shrinks (a corner the person chose: down to 60 %; the default corner: to 70 % and then the other corners are tried at full size), then it moves to the next corner. The rules are pure functions (`engine/watermark_spec.layout`), tested for every aspect, resolution, position, size, style, logo shape and with captions on and off. A chosen bottom corner in 1:1 or 4:5 usually ends up top left because the caption box nearly fills the width: the result is in `layout()['position']` if an app ever wants to say so.
**A top corner gets a band of its own (2026-11-27, after the first real QA videos: a 9:16 logo sat on the first letters of a list heading).** In 9:16, 1:1 and 4:5 a mark that ends up in a top corner makes every scene's content box start below it (`watermark_spec.content_inset`, `Frame.top_inset`: mark bottom + 18 design px; 104 px in 9:16, 40 px in 1:1, 30 px in 4:5 for the small mark; at most a tenth of the height). Only videos with such a mark change; the clip credit line and the captions stay where they are. Segment hashes of watermarked videos carry a version (`wmv`), so no old segment is reused.
Not guaranteed: in **16:9** scenes sit at fixed heights and are not moved; the default corner there is bottom right (free), the mark alone fits beside the content in any corner, but a wide lockup or logo in a *chosen* top corner can still touch a heading.

**Checked on Lambda (QA, 2026-11-27):** videomk lockup + end card, 16:9 1080p (bottom right, crisp, fades in, end card shown); custom logo, 9:16 720p (top left under the platform header, own colours, leaves with the closing fade). 1:1, 4:5 and 4K were checked with the same renderer locally only.

## 3. Options (one object everywhere)
```
watermark: { mode: "none"|"videomk"|"custom", position: "auto"|"tl"|"tr"|"bl"|"br", opacity: 0.2..1.0 (0.65), size: "small"|"medium",
             style: "mark"|"lockup" (videomk only), end_card: true|false (videomk only), presence: "always"|"moments" (videomk only; absent = always, or moments for a premium account) }
```
Strict validation (400 `'watermark': ...`, unknown keys refused). Absent in a create request = the person's saved default, else the stack policy (below).

## 4. API (all Cognito, caller = path user)
| Call | What |
|---|---|
| `GET /users/{user}/watermark` | `{watermark: saved settings with defaults + has_logo (+ logo_url, a 5 minute link to the person's own logo)}, capabilities: {...}}` |
| `PUT /users/{user}/watermark` | save the default settings (body = the object above; `mode` required). `custom` needs premium and a stored logo (403 `watermark_premium`, 400 `watermark_logo_missing`); `none` is refused to a non-premium account when the stack forces the mark (403 `watermark_required`). |
| `DELETE /users/{user}/watermark` | forget the settings and the logo |
| `PUT /users/{user}/watermark/logo` | `{"data": "<base64>"}`, premium only, 20 uploads a day (429 `rate_limited`) |
| `DELETE /users/{user}/watermark/logo` | remove the logo (a saved `custom` falls back to `videomk`) |
| `GET /users/{user}/capabilities` | now also has `watermark: {modes: [{id, available, label, requires?}], positions, sizes, styles, style_options: [{id, available, label}], presences: [{id, available, label, note, requires?}], default_presence, opacity: {min, max, default}, premium, forced, forced_watermark?, forced_note?, end_card, logo: {max_bytes, max_px, types}}` (only where the stack has the feature on). When `forced` is true: `forced_watermark` is the exact object every video of this account gets and `forced_note` the line to show; `modes[none]`, `modes[custom]`, `style_options[mark]` and `presences[moments]` are `available: false`. |
| `POST /users/{user}/videos/generate` | optional `watermark` object. Resolution order: the request, else the saved default, else policy. Refusals happen before anything is charged. |
Error bodies are `{message (localized EN/ES), code}`; codes: `invalid`, `watermark_premium`, `watermark_required`, `watermark_logo_missing`, `logo_too_big`, `logo_type`, `logo_svg`, `logo_px`, `logo_empty`, `rate_limited`.

## 5. Entitlements and policy (owner decision 2026-11-27: free videos always carry the name)
* **Premium** (may use `custom`, `none`, `moments`): any of `flags.watermark_custom = true` (`AWS_PROFILE=<stage> python backend/scripts/wallet_admin.py watermark you@example.com [--off]`; works in production), an active Pro library plan (`flags.storage_plan = pro`, not lapsed), or an unlimited test account (not in production). The flags table is written only by an admin; no function can grant itself premium.
* **Owner policy `forceWatermark`: ON in QA and prod** (`backend/stages.json` `"forceWatermark": true` under both stages; `-c forceWatermark=0|1` on a deploy overrides; before 2026-11-27 it was a deploy flag, default off). Every video of a **non-premium** account carries exactly this, whatever the request or the saved settings say (`watermark_store.FORCED_SPEC`):
  `{"mode": "videomk", "style": "lockup", "presence": "always", "end_card": true, "position": "auto", "size": "small", "opacity": 0.65}`
  i.e. the mark **and the word "videomk"**, for the whole video, in the quiet corner of the shape, plus the closing "Made with videomk" card. `none`, `custom`, the mark without the name, `moments`, another corner, size or opacity are not available to them (an opacity of 0.2 would be a way round it). A create request that asks for something else is not refused: it simply gets the forced mark (an explicit `custom` is still answered 403 `watermark_premium`). `PUT /watermark` with `mode: none` or `presence: moments` answers 403 `watermark_required`.
* **Premium accounts** choose: `none`, their own logo, or the videomk mark `always` / `moments`. A premium account's videomk mark without a stated `presence` is **`moments`** (`PREMIUM_DEFAULT_PRESENCE`). Nothing saved and nothing asked: no watermark.
* **The owner's own promo videos:** `chris@plorer.ai` is premium for watermark purposes with a saved default of lockup + `moments` + end card (set with `wallet_admin.py watermark <email> --default moments`; see the report of 2026-11-27 for what was set where). Undo: `wallet_admin.py watermark <email> --off --default moments` (removes the flag and the saved default).
* A saved `custom` whose plan lapsed or whose logo was deleted quietly falls back (the forced mark when forced, else none); an explicit `custom` request is refused with the reason.
* Feature switch: `-c watermark=0` removes the routes and the function; the launcher then ignores a `watermark` option and capabilities does not list it (the workflow input is exactly what it always was).

### The look that was chosen (judged on real frames, 2026-11-27)
| | value | why |
|---|---|---|
| Artwork | the lockup: the mark + the word "VideoMK" | the name is the point (marketing, and free use is not a way round paying) |
| Size | `small`, and the lockup is drawn at 92 % of the mark's height (`LOCKUP_SCALE`): **212 x 50 design px** (1080p), 20 % of the width of a vertical video; in 16:9 it sits in the corner beside the caption box and is shrunk to **148 x 35** | the word decides the size: its capitals are 25 design px (17 px at 720p), what the word measured in the previous lockup (257 x 41; its word was a larger share of the height, the new one has the stars above the play). In 16:9 the slot beside the captions is 35 px tall, so the capitals are 18 design px there (12 px at 720p; the previous lockup's word was 21): still readable, checked on real frames 2026-11-27 |
| Opacity | **0.65** (the documented default, kept) | compared 0.65 and 0.8 at two sizes on a bright cartoon frame, busy volcano footage and a dark 3D loop: at 0.65 the name reads on all three and stays behind the content; 0.8 starts to compete with captions. No backing plate: the soft shadow (white mark) or soft glow (ink mark on light pictures) was enough on every frame looked at |
| Corner | 16:9 bottom right; 9:16 top left under the platform header (x 38, y 200); 1:1 and 4:5 top left (x 38, y 38); the scenes start below it (band of 109 / 27 / 17 design px) | unchanged rules of section 2: never on captions, the credit line, headings or the platform UI zones |
| Fades | `always`: in over 0.6 s at the start, out with the closing fade. `moments`: see below | |
| End card | 2.4 s "Made with videomk" / "Hecho con videomk" + videomk.com | closes every free video |

### `presence: "moments"` (videomk mode only; `watermark_spec.moments`)
The lockup comes and goes instead of sitting there: it fades in gently, stays about 4 seconds and fades out; the closing card ends the video when `end_card` is on.
* **Timing:** each appearance = 0.6 s eased fade in + 4.0 s fully visible + 0.6 s eased fade out (5.2 s). The first starts at **1.2 s** (never over the first second of the opening). Then about one **every 30 s** (30, 60, 90 ...), moved to the **nearest scene change within 8 s** and starting 0.3 s into the new scene; a scene change that opens an **emphasis scene** (counter, stat, chart, pie, bar race, ranking, scale compare) is skipped, and if 30 s falls inside such a scene with no calm change nearby it waits for the next calm scene. Appearances keep at least 12 s apart and the last one has left 1 s before the closing card or the final fade. A video too short for one (under about 8 s of content) gets none.
* **Examples:** a 30 s video: one appearance (1.2 to 6.4 s), then the closing card. A 61 s video with scene changes at 9, 20, 28, 40, 50: 1.2 s and about 28.3 s. Five minutes: about ten.
* **Chunked rendering:** the appearances are worked out once when the timeline is built (`timeline.watermark.windows`, video seconds) and each render chunk gets them in its own time (`timeline._chunk_watermark`), so every chunk draws exactly what the whole video would (tested frame against frame). The chunk's own appearances are part of its hash (`wmv` 3), so a chunk with the mark and the same scenes without it never share a cached segment.
* The scenes' top band (9:16, 1:1, 4:5) stays reserved for the whole video, also while the mark is away, so nothing shifts when it arrives.

## 6. How it flows (and what is stored)
1. Launcher: `validate_options` (strict) -> `apply_watermark` (premium, saved default, policy; nothing for `none`) -> `options.watermark` in the Step Functions input.
2. Plan step: `plan["watermark"]`; a custom logo is **copied from the private store into the video's own folder** (`generation/v2/<video>/assets/watermark.png`, no expiry tag) with its content hash, so every re-render and edit of that video uses the logo as it was; if the logo vanished the video gets the videomk mark when the stack forces one, else none: it never fails a video.
3. Timeline: `timeline["watermark"]` (+ an optional end-card scene: silent, `title` type, EN/ES text); `chunk_plan` hashes include the watermark (and whether it is the first chunk), videos without one hash exactly as before so existing caches stay valid; `chunk_timeline` carries it.
4. Render chunk: `Renderer.wm` is built once per chunk (the logo is read through the same loader as photos, only from this video's `assets/`).
**Stored:** `watermark/<user>/profile.json` and `logo.png` in the private assets bucket (default encryption, never public, a presigned 5 minute link only to the owner). Deleted with the account (`ASSET_USER_PREFIXES`, the deletion worker's IAM, the daily upload counter `wmlogo:`; covered by the deletion tests). No logs of the image or the settings.

## 7. Logo upload safety
* Type from the **content** (PNG / JPEG / SVG magic bytes), never the name or declared type; at most 2 MB (also a 3 MB request body cap) and 2000 px per side (the decoder's pixel limit is set before decoding: no decompression bomb).
* Decoded and **re-encoded** to a fresh PNG (no EXIF, text chunks or profiles; a JPEG with a description comes back clean), trimmed of empty margins, scaled to at most 1024 px.
* SVG: refused if it has a DOCTYPE or entity, script, foreignObject, iframe, `@import`, `javascript:`, or any `href` that is not `#id` or an embedded PNG/JPEG (no network or file access is possible); it is drawn once with resvg and **only the PNG is stored**.
* Per-user paths only; an id that is not a plain id is a 403; one person cannot read or change another's.

## 8. What the apps and the web app need to build (the UX agents)
Where: **Create > Options sheet** (a single row "Watermark", collapsed to its value: *None* / *videomk* / *Your logo*), and **Settings > Watermark** (the saved default: the same controls plus the logo picker). Nothing on the main Create screen.
| Control | Option | EN | ES |
|---|---|---|---|
| Row | mode | Watermark | Marca de agua |
| Values | `none` / `videomk` / `custom` | None / videomk / Your logo | Ninguna / videomk / Tu logo |
| `custom` locked (not premium) | | Your logo (Pro) | Tu logo (Pro) |
| Position | `position` | Position: Auto, Top left, Top right, Bottom left, Bottom right | Posición: Automática, Arriba izquierda, Arriba derecha, Abajo izquierda, Abajo derecha |
| Size | `size` | Size: Small, Medium | Tamaño: Pequeña, Mediana |
| Opacity | `opacity` | Opacity | Opacidad |
| Style (videomk) | `style` | Mark only / With name | Solo el icono / Con el nombre |
| End card (videomk) | `end_card` | Add a "Made with videomk" ending | Añadir un final «Hecho con videomk» |
| Logo | `PUT .../logo` | Choose logo / Remove logo | Elegir logo / Quitar logo |
| Presence (videomk) | `presence` | Always visible / Now and then (notes: "Stays in the corner for the whole video." / "Fades in for a few seconds near the start and about every 30 seconds.") | Siempre visible / De vez en cuando ("Se queda en la esquina durante todo el video." / "Aparece unos segundos cerca del inicio y más o menos cada 30 segundos.") |
| Forced policy | `capabilities.watermark.forced` | The videomk watermark is included on this plan. | La marca de agua de videomk va incluida en este plan. |
**Free accounts (forced, the normal case in QA and prod since 2026-11-27):** show the Watermark row as a fixed value, not a control: "videomk" with `forced_note` under it ("The videomk watermark is included on this plan."), no mode, style, presence, position, size or opacity controls, and do not send `watermark` in the create request. The video gets the lockup for its whole length and the closing card. **Premium accounts:** the full controls, plus the Presence row when the mode is videomk; preselect `default_presence` (`moments`) when nothing is saved. Labels and notes for the presence row come localized in `capabilities.watermark.presences`.
Use `capabilities.watermark` to decide what is shown (`available: false` = show locked or hidden; `requires: premium`). Send `watermark` in the create request only when the person changed it for this video (otherwise the saved default applies). Show a small preview (a rounded rectangle with the mark in the chosen corner) rather than a long explanation. Error `code`s above have localized `message`s.

## 9. Tests (`backend/tests/test_watermark.py`, 111 tests; presence and the forced policy: `backend/tests/test_watermark_presence.py`, 16 tests)
Options (strict and lenient), placement for 4 aspects x 3 resolutions x captions on/off x every position, size, style and logo shape (inside the frame, off the captions and the credit, inside the UI-safe area), frames of the real renderer (corner and size per aspect and resolution incl. 720p and 4K, exact no-op without a watermark, opacity, fade in on the first chunk only, closing fade, ink on light and white on dark, never on the real caption pixels, custom colours kept, unreadable logo draws nothing), timeline and chunk hashes, end card, the policy matrix, the launcher (feature off sends nothing new, premium, saved default, forced), the plan step's logo copy, the API with moto (settings, premium gate, logo checks incl. scripts, entities, file references, bombs, wrong types, metadata stripping, rate limit, other users, locale), capabilities, and the CDK template (routes behind Cognito, rights, flags). Account deletion has the watermark objects and the counter in its seed.

## 10. Files
`engine/watermark_spec.py` (options and placement, no dependencies), `engine/watermark.py` (drawing), `engine/assets/watermark/{mark,lockup}.{svg,png}` (made by `scripts/watermark_assets.py` from docs/brand/final/mark-white.svg and lockup-horizontal-white.svg), hooks in `engine/renderer.py` and `engine/timeline.py`, `engine/handlers/plan_handler.py`, `common/watermark_store.py`, `watermark_api.py`, `capabilities_api.py`, `sf_launcher.py`, `common/deletion.py`, `common/i18n.py` (`wm.*`), `watermark_feature.py` (CDK), small additions in `backend_stack.py`, `account_deletion.py`, `scripts/wallet_admin.py`.

## 11. With plans on (2026-11-27, `docs/PLANS.md` section 4)
The **plan** decides, through `watermark_store.rights()`: Free = the videomk mark with the name (`style: lockup`) and the end card, always (the person keeps the corner and the size; opacity at least 0.65); Pro = may remove it; Max = also its own logo. So section 5 changes where plans are on: an active Pro *storage* flag no longer gives the logo (own logo is Max only), the admin flag `watermark_custom` stays an override (own logo, nothing forced, any plan), an unlimited test account has the rights of Max, and `forceWatermark` is not consulted (Free is always forced). Refusals carry `requires_plan`; an explicit mode the plan lacks is 403 `plan_watermark`; capabilities adds `modes[].requires_plan`. The "moments" mode named in the plans is not in the engine yet (`watermark_spec.MODES`); the rights already list it for Pro and Max.
