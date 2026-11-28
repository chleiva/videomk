# Sea backdrop 2 (2026-11-28)

Problem (QA run 6, 9:16 cartoon sea): the video got a house-and-rainbow meadow. The sea-defects fix moved the dry sand of `tall_sunset_beach_vertical` below the caption lines, so no water backdrop holds a cast in 9:16; the planner then took the neutral open-ground (meadow) candidates.

## Fix
1. Theme kept. `art_direction.sea_topic` (sea, ocean, beach, coast, lake, river, harbour, reef, island, lighthouse, tide, waves, whales, Spanish forms; word-bounded, so "seasons" and "search" do not match). For such a topic `stand_backdrops` only considers catalog backdrops whose id, tags or title name water (`_sea_ids`); with none that holds the cast and scores credibly, it returns the new drawn ground `ground_beach` (never the meadow or the neutral query). `_enforce_cartoon` fallback uses `themed_ground(text)` too (beach for a sea plan, `ground_floor` otherwise).
2. `ground_beach` (stand_zone.BEACH_ID, `stand_zone.DRAWN`): procedural_ground draws sky, sun or moon, clouds, a SEA band with glints and foam above the horizon, and a DRY SAND floor (pebbles) from the horizon to the bottom edge. Zone = same geometry as `ground_floor` (ground from horizon down, no hazards), so feet are always below the foam line and above the captions; ground lines derived by `scripts/procedural_ground_build.py` (now writes both records). I did NOT restore a stand zone on the tall beach picture: its dry sand lies below the caption lines, so a drawn strip is the safe route.
3. Card top margin: `presenter.CARD_TOP` = 9:16 310, 1:1 150, 4:5 150 design units. The content card (title included) never starts above it. A constant of the shape: no watermark or account input. The mark (auto lockup 9:16 y 200 to 286; 1:1 and 4:5 y 38 to 146 at most) stays above it. 4:5 was added because it shares the 1:1 corner. This moves the card down by about 150 / 80 / 70 units in 9:16 / 1:1 / 4:5 (16:9 unchanged).

## Tests
`tests/test_sea_backdrop2.py` (22): sea request in 9:16, 4:5, 1:1, 16:9 for casts of 1 to 3, with a meadow-biased search, an empty search and no search: every id is wet or `ground_beach`, holds the cast, no stand-zone violation; sea word detection; enforce fallback; beach floor is sand and sea is blue above the horizon and feet are below it; card top constant and clear of the mark. Updated two assertions in `test_stand_zone.py` (sea fallback is the beach). Green: test_stand_zone, test_art_direction, test_presenters, test_vector_presenter, test_presenter_arms, test_vector_character_cast, test_watermark_decoupled.

Stills: ~/Downloads/videomk-looks/web/sea-backdrop-2/ (sea_backdrop_2_sheet.jpg, 8 PNGs: four shapes, paper and midnight).

## Not verified
No live planner or deploy run; the catalog search was stubbed. `_sea_ids` relies on index tags (loose tags such as city skylines tagged "river" can pass the theme filter but still need a credible score, or the beach is used). Catalog water backdrops in 1:1 and 16:9 were not re-rendered. Title clearance was checked by geometry (mark rects), not by a watermarked render.
