# Photos elements (`photo_collage`, `photo_frame`, `chapter_card`)

Family `Photos`. Code: `backend/lambdas/engine/scenes/elements/photo_layouts.py` (sanitize, prepare, docs, chapter card), `_photo_collage.py`, `_photo_frame.py`, `_photo_kit.py` (cached sprites, backdrop, label, chip). Tests: `backend/tests/test_el_photo_layouts.py`. They show the user's OWN photos only (ids from `media_items`), so a video made from up to 100 photos can show nearly all of them: about 9 per collage.

## photo_collage
Props: `photos` 3-9 ids (`^P\d{1,3}$`; 2 are accepted), `style` mosaic|polaroids|grid|filmstrip|stack (absent: polaroids up to 4 photos, grid for 7+ of one orientation, else mosaic), `title` (<=50), `subtitle` (<=80), `alt` (<=70); optional `captions` (filled by the planner, one per photo).
- `prepare` patches `photos` (the ids that exist), `assets`, `ratios`, `orientations`, `captions` (filtered alike); fewer than 2 resolved raises (fallback: title card).
- `anchors` = captions (else "photo N"); `cues` and `draw` use `reveal_times(n, dur, props["cues"])`; the first photo is never later than 0.35 s, all appear before the end.
- Mosaic: templates (one hero tile + 1-4 columns) are scored by how much each photo would be cropped; a tile far from its photo's shape shows the photo whole over a blurred copy. Polaroids: white frames, angles from the ids (+-2.5..9 deg), fly in. Grid: equal tiles in 1-3 rows, pop-in. Filmstrip: one strip (<=5) or two (opposite drift), frames dim until their reveal, the newest has an accent outline. Stack: dropped on one another, last one largest.
- Background: the first photo, blurred and darkened (paper theme: washed), cached. Title/subtitle: lower-third at the bottom left, above `ctx.bottom`; the layout area shrinks to leave room for it.
- draw never needs assets: with none (or unreadable ones) it draws placeholder tiles in the same layout.

## photo_frame
Props: `photo` (one id), `style` polaroid|matte|tilted|film|pinned (default polaroid), `title`, `subtitle`, `date_label` (<=30), `alt`. `prepare` returns `{asset, ratio}` and raises for an unknown id. Photos are shown whole (portrait/square get a side layout: label column on the left); slow 5% zoom; polaroid puts the title in its caption strip; date as an accent chip.

## chapter_card
Props: `title` (<=60), `subtitle` (<=100), `kicker` (<=40, shown uppercase, letter-spaced), `photo` (optional hero id). `prepare` returns `{asset}` or `{}` (never raises). Kicker fades in, accent bar grows, title reveals word by word, subtitle follows. With a hero: heavily darkened blur and light text; without: theme ambience with quiet rings. `min_seconds=3`.

## Cost
At 1920x1080 with 9 photos a warm frame takes 0.05-0.16 s; the first frame of a scene (tiles, shadows, blur, built once and cached) 0.2-0.4 s.
