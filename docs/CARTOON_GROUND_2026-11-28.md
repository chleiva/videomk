# Cartoon characters stand on the ground (2026-11-28)

Owner report: in the 9:16 conversation "Sea request: French fox, German bear, Italian owl explain why the sea is salty" (QA video v3_sea) the three characters stood on the lighthouse cliff and the owl's
feet were over the sea. "You cannot have 3 characters floating in the air; they need to be on the ground, so we need to know positionally where to put the characters on the background. I discard
this background; I do not want them on the border of a cliff. If there is anything like this, remove it."
The faded "La salinita" card in the screenshot is a normal cross-fade between two scenes (owner confirmed), not a bug; not touched.

## What it was
Backdrop `tall_lighthouse_cliff` ("Lighthouse on a cliff (vertical)", 9:16, in all three beats of the plan). Before this work a backdrop was only a picture: the presenter layout put the figures
at fixed shares of the frame (9:16: x at 0.18 / 0.50 / 0.82 of the width, feet on the line just above the caption band) whatever the picture showed there.

## The rule
1. A backdrop is eligible for characters only if it has a **stand zone** with a **ground line** (below). No zone, no line, or retired: the backdrop stays available for scenes without characters only.
2. Characters are placed **feet on the zone** by the same function the renderer uses (`engine/stand_zone.py`, called from `presenter.layout`): the feet row is searched from the nominal floor upward
   inside the ground-line band, figures get smaller with distance when the ground has depth, slots move sideways to ground that holds the feet. Figures cut at the waist (16:9, 1:1, 4:5) have their
   feet under the frame or under the captions: the ground must be there and reach the bottom edge.
3. **Refusal:** when the ground cannot hold the cast, `holds()` is False. `art_direction.stand_backdrops` (policy time) keeps only backdrops that hold the cast, and when none of the topic's
   candidates does it searches the catalog wider (top 60 hits, soft score floor) for ones that do; none -> no backdrop (the plain gradient background with glow and contact shadows stays).
   `art_direction._enforce_cartoon` filters again with the real aspect and cast size (also replaces or removes a backdrop set by an earlier step), then runs the hard check
   (`stand_zone.strip_violations`) and records every repair in `plan["look"]["repairs"]`. At render time a layout that cannot place the cast (`unplaced`) does not draw the backdrop.
4. **Hard check** (`stand_zone.violations(plan, aspect)`): for every presenter scene with a backdrop: not retired, has a zone, holds the cast, every foot point is on the ground mask (not on a hazard
   polygon), and every foot Y lies inside the ground-line band.

## The data (stored with the catalogue item)
* `backend/lambdas/common/vector_stand_zones.json` (ships with the Lambda code; the engine reads this) and, per item, `stand` in `s3://<catalog bucket>/v/<id>/meta.json`.
* Per backdrop: `usable`, `native` shape, `ground` (polygons, picture coordinates 0..1, y down), `hazards` (polygons), `reason`, `model`, and **`ground_line` per served shape**
  (16:9 and 1:1 for a landscape picture, 9:16 and 4:5 for a tall one; the scene is never stretched, other shapes are a centre crop exactly as `vector_scene.frame_for` does):
  `{y, band: [lo, hi], figure_h, max_cast, casts: [..]}`. `y` is the feet row as a share of the frame height (1.0: figure cut at the waist, ground reaches the bottom edge), `band` the allowed rows for
  depth, `figure_h` the figure's height as a share of the frame at the line, `casts` the cast sizes the placement holds.
* **Required:** tests assert every eligible backdrop has a line, every placed foot is on the ground and inside the band, and every catalogue item has a stand record (so a new backdrop must supply one).
* How derived: `backend/scripts/vector_stand_audit.py` sends each thumbnail with a labelled 0.1 grid to Bedrock (QA, eu-west-1) and asks for walkable ground polygons, hazard polygons and a verdict;
  `backend/scripts/vector_stand_build.py` snaps ground that ends within 4 percent (7 percent at the bottom) of the edge to it, shrinks the ground by 2.2 percent of the height (the scene's push-in and parallax
  move the picture a little), derives the lines with the engine's own placement, and draws the contact sheet. Retire/restore a backdrop by setting `disabled` on its record
  (zones file, index item, bucket `meta.json`); `vector_catalog.search` skips `disabled` items.
* Spend: Sonnet 5.5 for all 157 (about USD 0.83) plus Haiku 5.5 cross-check (about USD 0.1): about USD 0.95 of the USD 2.00 budget (ledger: the models' own `cost` in the audit JSON files).

## What was retired / restricted (QA)
* **`tall_lighthouse_cliff` RETIRED**: `disabled: true` + reason in `v/tall_lighthouse_cliff/meta.json` (QA bucket; the original is saved at /tmp/gnd/meta_lighthouse_orig.json and is the same file without the three
  `disabled*` keys), in the index item (`vector_catalog_index.json`) and in the zones file. Reversible: remove the flag (set `disabled` false) in those three places.
* Of 157 backdrops: **123 eligible for characters, 33 not for characters** (no flat ground: sea, sky, space, rivers, tabletops, steep slopes, cliff edges), **1 retired**. Of the eligible ones most are
  restricted by shape: see the table (max cast per shape). Tall (9:16) scenes: 6 of 18 can hold characters in 9:16 (4 hold three), 12 hold some cast in 4:5.
* Nothing is deleted anywhere. **The retirement takes effect in a video only when the code is deployed** (the index and the zones file ship in the Lambda zip); the bucket flag is the catalogue record.

## Audit table
(contact sheets: ~/Downloads/videomk-looks/web/ground/index.html; green = ground, red = hazards, yellow = ground line, cyan = the other served shape)

| backdrop | verdict | max cast 16:9 / 9:16 / 1:1 / 4:5 | reason |
|---|---|---|---|
| abstract_desert_moon | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Flat purple desert floor in the foreground, wide, with rocks at the corners. |
| abstract_dunes_minimal | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open sand foreground; plants and dunes at corners are obstacles. |
| abstract_misty_lake_minimal | eligible | 16:9:0 9:16:0 1:1:1 4:5:0 | Only a narrow dark green foreground strip below the lake; lake and bushes are hazards. |
| abstract_mountain_layers | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Dark green meadow in foreground between bushes, mountains behind. |
| abstract_waves_geometric | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Only sea and sky; bushes in corners are not walkable ground. |
| airport_apron_sky | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat airport apron; carts, cones and bushes at edges. |
| airport_runway_plane | eligible | 16:9:0 9:16:0 1:1:2 4:5:0 | Grass strip in front of the runway is flat and wide; bushes at the corners. |
| alien_planet_surface | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat orange alien desert; craters and rocks at edges avoided. |
| autumn_forest_path | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide sandy path and grass in foreground; bushes and trees at the sides. |
| autumn_lake_reflection | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is a lake; only a thin far shore strip is ground. |
| bank_building | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide paved plaza in front of building; fountain and bushes at edges. |
| basketball_court_park | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat basketball court surface in foreground, fence behind. |
| bedroom_window_morning | eligible | 16:9:1 9:16:0 1:1:1 4:5:0 | Wooden floor right of bed and rug area, bed blocks left. |
| bicycle_lane_city | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Grass lawn in foreground, with road, tram track and bushes behind. |
| camping_lake_night | eligible | 16:9:3 9:16:0 1:1:3 4:5:0 | Grassy lakeside foreground wide enough; lake behind, rocks, fire pit and log are obstacles. |
| campus_quad_autumn | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open lawn in foreground; bushes at the bottom corners. |
| candy_hills | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Rainbow path winds through the meadow; bushes frame the lower corners. |
| canyon_river_rafting | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Canyon river fills the foreground; only thin sandy banks, too narrow to stand. |
| cargo_ship_sea | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly sea with a ship; only small bushes and rocks at the corners. |
| cave_valley_stone_age | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide green meadow in foreground below river; river and rocks behind. |
| cherry_blossom_temple | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Stone path and lawns in front of gate; bushes frame the corners. |
| circuit_board_city | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Green circuit-board plain in foreground, bushes in lower corners, chips behind. |
| city_skyline_day | eligible | 16:9:0 9:16:0 1:1:1 4:5:0 | Narrow pavement strip below railing; bushes at corners, river behind. |
| city_skyline_dusk | eligible | 16:9:1 9:16:0 1:1:2 4:5:0 | Narrow stone promenade at bottom in front of the harbor water; bushes at corners. |
| classroom_window_view | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Central aisle between desks is the only open floor, fairly narrow. |
| cloud_kingdom | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat cream cloud floor in foreground, bushes and blue clouds at corners. |
| coast_cliffs | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Grass strip in foreground; sea and cliffs behind, rocks at sides. |
| coin_hills_whimsical | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide grassy meadow in foreground, stream and bushes at the sides. |
| container_port_cranes | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat grey quay in foreground; bushes at corners, containers and water behind. |
| cooling_tower_steam | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Foreground grass bank below the river is wide and flat. |
| cycling_road_hills | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Grassy meadow foreground with road; bicycle and signpost occupy left, bushes at corners. |
| dairy_farm_barn | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open grass meadow in foreground, pond and bushes at the sides. |
| data_center_landscape | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open grass meadow in foreground, rocks and bushes at corners. |
| deep_ocean_reef | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Sandy seabed in the foreground, flanked by rocks and corals. |
| desert_canyon | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Flat desert sand floor with winding path; rocks and cacti at edges. |
| desert_solar_plant | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open sandy desert foreground in front of solar panel rows. |
| dna_lab_window | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Narrow laboratory bench top with objects; no walkable ground for characters. |
| dutch_windmill_polder | eligible | 16:9:0 9:16:0 1:1:2 4:5:0 | Grass strip in front of the river is the only reachable flat ground. |
| egypt_pyramids_desert | eligible | 16:9:0 9:16:0 1:1:1 4:5:0 | Desert sand in front of and behind the oasis pond; water in middle. |
| ev_charging_street | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide asphalt road in foreground, bushes at corners, car on sidewalk behind. |
| factory_skyline | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Open dirt yard between pipes and crates, beyond railway tracks. |
| farmland_patchwork | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Open green meadow in foreground with dirt path; fence and bushes at sides. |
| financial_district_night | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is river water; only distant far bank and bushes, no walkable ground. |
| flower_meadow | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Grassy meadow with dirt path in foreground; fence and flowers at the sides. |
| football_stadium | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grass football pitch in foreground, bushes in corners. |
| forest_cottage_kids | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat meadow in foreground; stream, mushrooms and house excluded. |
| galaxy_planets_view | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat lunar plain in foreground; sky and boulders at sides. |
| geothermal_steam | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Flat brown dirt foreground between rocks, wide enough for three characters. |
| glacier_arctic | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Narrow snowy foreground strip below icy water; ice blocks at both sides. |
| greek_temple_ruins | eligible | 16:9:1 9:16:0 1:1:1 4:5:0 | Only the grassy meadow at the bottom is flat; cliff, sea and trees around. |
| greenhouse_rows | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide dirt path in front of greenhouse; bushes at lower corners. |
| harbour_boats | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Only a thin dock strip at the bottom, blocked by barrels and crate; water above. |
| health_clinic_garden | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide paved path and lawn in front of clinic, bushes at corners. |
| highway_interchange | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Grass meadow in foreground below the highway, bushes at corners. |
| home_garden_backyard | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Open lawn in front of raised beds; bushes and pots at corners. |
| hospital_exterior | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide lawn and paved path in front of hospital; bushes in corners. |
| hydro_dam | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is river water; only steep hillsides and dam, no flat ground. |
| iceberg_sea_polar | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly water; only narrow corner ice shelves at edges. |
| japanese_pagoda_garden | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is pond and bushes; no flat walkable ground. |
| kitchen_window_garden | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Kitchen counter and windowsill are table surfaces cluttered with objects, not ground. |
| laboratory_building | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide lawn and path in front of building; bushes at the corners. |
| library_entrance_hall | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Flat library floor with rug in foreground; shelves, plants and pedestal at edges. |
| library_interior_view | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Small visible floor patch behind the big desk; the foreground is a table. / no shape has a ground line the engine can place on |
| living_room_plants | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Cream rug floor in front of sofa, foreground plants at corners. |
| mangrove_coast | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Scene is shallow water with mangroves; no walkable ground for characters. |
| market_square_stalls | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Open cobblestone plaza in front of fountain, market stalls at both sides. |
| mars_surface_rover | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Flat red desert floor in foreground; rocks at bottom corners, rover in middle. |
| medieval_castle_hill | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Front meadow is flat grass; bushes at corners and village houses behind. |
| medieval_village_street | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Open cobblestone square in foreground; well, cart and bushes at edges excluded. |
| microscope_lab_bench | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Close-up of a lab bench with objects; the surface is a table. |
| misty_lake_dawn | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly lake; only a narrow diagonal dock, bushes in corners; no wide flat ground. |
| modern_office_exterior | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide lawn and curved path in front of building; bushes at corners. |
| moon_base_surface | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat lunar surface with craters; rocks at the bottom corners. |
| mountain_lake | eligible | 16:9:1 9:16:0 1:1:1 4:5:0 | Only a narrow grass strip at the bottom; lake and rocks elsewhere. |
| mountain_pass_road | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Flat grassy meadow in foreground; stream, bushes and road beyond. |
| observatory_night | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide grassy hill foreground; rocks at both corners excluded. |
| office_tower_dusk | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grass lawn in foreground, bushes in corners, tram tracks and trees behind. |
| offshore_wind_farm | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly open sea; only tall bushes in corners, no flat ground. |
| old_harbour_fort | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Grass strip at bottom is flat, bordered by water, bushes and fort. |
| old_town_street | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide cobblestone plaza in foreground, bushes at corners, wall behind. |
| pharmacy_street | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Sidewalk strip in front of shop plus road below; bushes at corners. |
| pine_forest_valley | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Open grassy meadow in foreground, river and rocks to sides. |
| pirate_cove_island | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide sandy beach in foreground, water and treasure chest at sides |
| playground_empty | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grassy lawn in the foreground; sandbox and play structures are obstacles. |
| power_lines_sunset | eligible | 16:9:1 9:16:0 1:1:2 4:5:0 | Grassy field with a road; wide flat band across the lower middle. |
| railway_station_platform | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide flat pavement in foreground below platform edge, bushes in corners. |
| rainbow_meadow | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat meadow in front of pond, bushes in corners. |
| research_lab_dusk | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide lawn and curved path in front of building, bushes at corners. |
| rice_terraces | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Flat grassy foreground at bottom; terraces are steep, foliage at corners. |
| river_valley_morning | eligible | 16:9:1 9:16:0 1:1:1 4:5:0 | Grass strip along bottom in front of river; river blocks middle. |
| road_trip_highway | eligible | 16:9:3 9:16:0 1:1:3 4:5:0 | Wide asphalt road in foreground is flat and walkable; desert and sky around it. |
| robotics_lab_window | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Only a narrow workbench shelf with machines; the lower area is a wall and plants. |
| rocket_launch_pad | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide green meadow in foreground; bushes at corners, launch pad and sea behind. |
| roman_aqueduct | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grass field and dirt path in front of aqueduct, bushes at corners. |
| rooftop_city_view | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Paved terrace floor in front of a low parapet wall, wide enough. |
| running_track | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide red running track in foreground; bushes in corners avoided. |
| satellite_dish_field | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide grassy field in foreground; bushes at corners and sky behind excluded. |
| savanna_acacia | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Open flat savanna grass in middle and foreground; termite mound and bushes excluded. / no shape has a ground line the engine can place on |
| savanna_sunset_acacia | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat savanna grassland; dark bushes in the lower corners. |
| school_building_exterior | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat lawn in foreground; bushes at the bottom corners avoided. |
| science_museum_exterior | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide plaza in front of building; fountain and bushes in corners are hazards. |
| server_corridor | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Tiled server-room aisle floor between racks, narrowing toward the door; plants at corners. |
| silk_road_oasis | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide open sandy courtyard in front of the gate, with clear foreground. |
| skate_park | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide concrete skatepark floor in foreground, bowl and bushes at sides excluded. |
| ski_slope_lifts | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide flat snowy slope in foreground between trees, room for three. |
| skyscraper_district | eligible | 16:9:3 9:16:0 1:1:3 4:5:0 | Wide paved plaza in front of fountain, benches at the sides. |
| smart_city_day | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide open grass lawn in foreground, bushes at corners, city behind. |
| snowman_field_kids | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open snowy field in the foreground; snowmen and sled are obstacles. |
| snowy_forest_night | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open snowy clearing in foreground, trees and bushes at sides. |
| snowy_peaks_cabin | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open snowy field in foreground, rocks and trees at sides. |
| solar_wind_farm | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Grass strip in front of the road is flat, but the foreground plants and fence frame it. |
| spa_stones_pond | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grass lawn in foreground below the pond; bushes at corners. |
| space_playground_kids | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat sandy playground floor in foreground; purple bushes at corners. |
| space_station_earth | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Space scene with space station and Earth globe; no walkable ground. |
| spring_hills_flowers | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open grass meadow in foreground, river and bushes at sides. |
| spring_orchard | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide grassy meadow in the foreground with a path; bushes at the corners. |
| stock_exchange_facade | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide flat stone plaza in front of building steps, bushes at corners. |
| stone_bridge_river | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is river water; bridge is a narrow, distant, elevated structure. |
| study_desk_window | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Desk tabletop with objects in a window scene; no real ground for standing. |
| submarine_deep_sea | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Sandy seabed in foreground, rocks at both sides, water above. |
| suburb_street_morning | eligible | 16:9:0 9:16:0 1:1:1 4:5:0 | Front lawn and road strips are walkable; bins and bushes block the corners. |
| sunrise_over_ocean | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly sea and sky; only rocks and bushes at the corners, no flat ground. |
| suspension_bridge_traffic | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Mostly water and bridge; only bushy hill corners, no flat ground. |
| swimming_pool | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Tiled pool deck strip in front of the pool, bushes at corners. |
| tall_castle_tower | eligible | 16:9:0 9:16:3 1:1:0 4:5:3 | Grassy hill foreground flat enough for two characters; bushes at edges. |
| tall_city_tower | eligible | 16:9:0 9:16:0 1:1:0 4:5:3 | Wide grass lawn and paved plaza in foreground; planters and trees at sides. |
| tall_forest_trail | eligible | 16:9:0 9:16:2 1:1:0 4:5:1 | Winding dirt path in foreground is flat, fits two characters; rocks and ferns at sides. |
| tall_future_city_vertical | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Small grass strip at bottom; water and city behind, trees at sides. / no shape has a ground line the engine can place on |
| tall_home_garden_vertical | eligible | 16:9:0 9:16:2 1:1:0 4:5:2 | Sandy garden path and grass; flowerbeds, watering can and bushes block sides. |
| tall_hospital_tower | eligible | 16:9:0 9:16:0 1:1:0 4:5:3 | Grass lawn and beige path in front of hospital; bushes at corners. |
| tall_lighthouse_cliff | RETIRED | 16:9:0 9:16:0 1:1:0 4:5:0 | retired: no flat ground, cliff edge and sea under the feet |
| tall_ocean_lighthouse_night | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is water and steep rocks; island rock is jagged and small. |
| tall_rainbow_vertical | eligible | 16:9:0 9:16:3 1:1:0 4:5:2 | Wide grassy hill meadow, bushes frame the lower corners. |
| tall_rocket_vertical | eligible | 16:9:0 9:16:0 1:1:0 4:5:1 | Grass field in foreground below launch pad; bushes at corners. |
| tall_skyline_vertical | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is river and bushes; bridge is narrow with a rail, no flat ground. |
| tall_snow_peak_vertical | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Small grass strip at the bottom in front of lake, bushes on both sides. / no shape has a ground line the engine can place on |
| tall_space_vertical | eligible | 16:9:0 9:16:0 1:1:0 4:5:2 | Flat lunar plain in foreground, bordered by rocks and mountains. |
| tall_sunflower_field | eligible | 16:9:0 9:16:0 1:1:0 4:5:3 | Grass strip in front of sunflowers, foreground leaves block the corners; room for two. |
| tall_sunset_beach_vertical | eligible | 16:9:0 9:16:3 1:1:0 4:5:3 | Wide sandy beach in foreground, sea behind, palm fronds in corners. |
| tall_train_viaduct | eligible | 16:9:0 9:16:0 1:1:0 4:5:1 | Small grassy meadow in lower center, surrounded by bushes and trees. |
| tall_waterfall_forest | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is a pool and mossy boulders; no flat walkable ground. |
| tall_wind_turbines_vertical | eligible | 16:9:0 9:16:3 1:1:0 4:5:3 | Wide grassy hill meadow in foreground; flowers and bushes at bottom corners. |
| telescope_hill_stars | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide grassy hill foreground, bushes at corners, telescope and observatory beside it. |
| tennis_court | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide flat clay tennis court in foreground; bushes at corners, net behind. |
| thunderstorm_plains | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open green meadow in foreground, bushes in bottom corners. |
| toy_village | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide green meadow in front of the train track, bushes in corners. |
| train_through_hills | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Flat grass meadow in front of bridge, bushes at the corners. |
| tropical_beach | eligible | 16:9:1 9:16:0 1:1:3 4:5:0 | Wide sandy beach in foreground, sea behind, leaves at corners. |
| tropical_river_jungle | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Only a small sandy strip at the bottom, partly blocked by boat and plants. |
| underwater_castle_kids | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide sandy seabed in foreground; castle, chest and rocks are obstacles behind. |
| viking_fjord | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is water; land is only small distant shores. |
| vineyard_hills | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Open grass meadow in the foreground, vines and bushes at the sides. |
| volcano_island | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is water and rocks; only a distant island, no flat standing ground. |
| waterfall_jungle | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Foreground is a pool of water with foliage; no flat walkable ground. |
| wheat_field_tractor | not for characters | 16:9:0 9:16:0 1:1:0 4:5:0 | Wheat field with a dirt strip; foreground wheat and bushes block low ground. / no shape has a ground line the engine can place on |
| winter_village | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide open snowy field in foreground, fence and bushes at edges. |
| workshop_exterior | eligible | 16:9:0 9:16:0 1:1:3 4:5:0 | Wide dirt yard in front of barn, foreground barrel and crate at edges. |

## Sea request re-rendered locally (no Lambda)
`backend/scripts/ground_stills.py`: 9:16 on `tall_sunset_beach_vertical`, 16:9 on `camping_lake_night`, three characters (fox, bear, owl), stills in ~/Downloads/videomk-looks/web/ground/
(`*_beat1..3.png`, `*_marks.png` with the foot points and band). In 9:16 the three stand on the sand strip (feet on the ground line at 0.75 of the height, just over the caption lines).

## Not verified / known limits
* Zone polygons come from a vision model on 384 px thumbnails, checked by eye on contact sheets and on two stills; I did not inspect every polygon edge at full size. The beach (`tall_sunset_beach_vertical`)
  has the feet right at the foam line, credible but tight.
* Prod: nothing touched. To repeat there: the same `meta.json` updates in the prod catalog bucket (`stand` + the `disabled` keys of `tall_lighthouse_cliff`; script: the loop in this doc's
  work, upload `/tmp/gnd/meta_new/*.json`, regenerate with `vector_stand_build.py`) and deploy the code (zones file, index flag).
* `vector_catalog_index.py` regenerates the index: it must keep the `disabled` flag (re-apply from the zones file) until it is taught to copy it.
* 16:9 is strict: figures are cut at the waist and the ground must reach the bottom edge at the slot positions (shift limit 0.07 of the width), so only 33 backdrops hold even one character in 16:9
  and 3 hold three; the square crop (1:1) serves most. Raising it needs the 16:9 layout to move the characters to ground, not only the slots.
* The first-frame ground can differ by a few pixels over the scene (parallax and push-in move the nearest layers); covered by the 2.2 percent shrink, not measured frame by frame.
* A "plain floor backdrop" is the existing plain background with glow and contact shadow, not a new drawn floor.
* Haiku cross-check agreed with the final verdict on 120 of 131 backdrops it reached (the rest differ mainly where Sonnet was stricter); only the first model's polygons are used.
* Tests run: test_stand_zone, test_art_direction, test_presenters, test_vector_policy, test_vector_catalog, test_el_vector_scene, test_vector_character_cast, test_vector_presenter (all pass). The full suite was not run.
