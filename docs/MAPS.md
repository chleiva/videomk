# Maps (the `map` element, phase 1)

One element, `map`, family Maps, at most 3 per video. The director gives **names**, never coordinates; the engine resolves, projects and draws them in the video's theme.

## Props
`{mode, title (<=50), caption (<=60), focus (1-4 names to frame), regions (<=12), points (<=8 names or {name, label (<=28)}), stops (2-8, in order), arcs (<=8 [from, to, label (<=22)])}`

| mode | shows | reveal |
|---|---|---|
| `focus` | frames 1-4 places (a country or state is tinted, a city is pinned, a named stretch of the world such as "Europe" or "Southeast Asia" only frames) | all at once, or one by one when 2+ |
| `regions` | countries or first-level areas (states, provinces) filled in the accent colour with their name; a small "Borders as of today" line | each region when its name is spoken |
| `points` | pins with a pulse, a label (and an optional second line) | each pin when named |
| `route` | stops joined by a great-circle line that grows with a moving head | each leg arrives as its stop is named |
| `arcs` | great-circle arcs that draw on, with an arrowhead and an optional label | each arc ends as its destination is named |

`focus` may also be given with any other mode to widen the frame ("Europe" around three cities). Anchors (`maps.anchors`) are the names in spoken order (for arcs the destination); the engine stores the times in `props["cues"]`, which `draw` honours through `easing.reveal_times`.

## How it works
- **Resolver** (`scenes/elements/_resolve.py`). Offline first: Natural Earth countries (names, long names, translations, ISO3 codes, aliases such as USA, UK, Czechia, Cote d'Ivoire, Burma, Holland), first-level areas, and 7,342 populated places. Names are folded (accents, case, punctuation, "St." = "Saint"). `City, Country` qualifiers work. Role decides what a name may be: `shape` (regions: country, then area), `point` (pins: city, then the label point of a country/area), `any` (focus: country, area, city, or a named frame). Same-name candidates are accepted only when one clearly dominates (5x the population, or the same spot); otherwise `Ambiguous`. Bare "Washington", "Georgia", "Korea" are refused. Region aliases that belong to several provinces ("Tuscany") are refused, not guessed. Anything Natural Earth does not know, for pins only, goes to Wikidata (`wbsearchentities` then `wbgetentities`, P625 on Earth): at most 4 s per call, at most 8 lookups and 20 s per map, a descriptive User-Agent, an in-memory cache, and only an exact label/alias match is accepted (several matches must lie within 50 km). Failure anywhere raises, and the beat becomes a title card (`fallback`: the title or the main place).
- **prepare** returns `{"resolved": {"role|name": entity}}` (small JSON: ids for polygons, lon/lat for points); `draw` uses it, and resolves offline from the same data when it is absent, so `draw` never touches the network.
- **Projection by extent** (`_project.py`, numpy only): Equal Earth for the whole world, an orthographic globe (with horizon clipping) for continents, Albers conic for countries and regions, Mercator near the equator or for small areas. Framing ignores far-flung territories (Azores, Alaska, French Guiana) unless they are within 5 degrees of the main land (Russia and Fiji are framed whole).
- **Camera**: fits the content with padding and eases in once (0.8x to 1x in 1.5 s). Labels (halo text) are placed once at the final camera with simple collision avoidance against other labels, pins, the title and the footer.
- **Performance**: the projected base map is cached per props (`lru_cache`); once the camera settles the painted base is cached per theme, so a frame is a copy plus the animating parts. Measured at 1920x1080, supersampled: first frame (builds the model) 0.1-0.4 s once per scene; settled frames 0.03-0.12 s; mid-camera frames 0.06-0.13 s.

## Data (`backend/lambdas/engine/assets/geo/`, about 2.3 MB)
Built by `backend/scripts/build_geo.py` from Natural Earth vector GeoJSON (naturalearthdata.com, mirrored at github.com/nvkelso/natural-earth-vector), **public domain** (no permission or attribution needed; we credit it anyway):
`ne_110m_admin_0_countries`, `ne_50m_admin_0_countries`, `ne_110m_land`, `ne_50m_land`, `ne_10m_admin_1_states_provinces`, `ne_10m_populated_places_simple`. Geometry is simplified (Douglas-Peucker, 0.003 degrees at 50m, 0.008 for areas), quantised to 0.001 degree, delta coded and zlib compressed in `.npz` files. `_geo.py` loads them lazily and caches them. Natural Earth draws de facto boundaries and its own neutral treatment of disputed areas; we draw nothing beyond it, and no historical borders. Wikidata coordinates are CC0.

## Limits
Areas exist only where Natural Earth has first-level areas (provinces, not always regions: no Tuscany, Catalonia, Scotland, Normandy). Tiny states without a polygon at 50m may be missing. A city name shared by cities that Natural Earth lists once ("Cambridge") resolves to the listed one. Labels are English as written by the director. Wikidata needs the network (offline names never do).

## Next (not built)
Choropleth (values per country or area, legend), a rotating globe that settles on a place, a locator inset beside another scene, city-street maps from OpenStreetMap (ODbL, attribution), multi-province regions (union of provinces for "Tuscany"), historical borders (only with a licensed dataset), lakes and rivers, editor fields on the phone apps.
