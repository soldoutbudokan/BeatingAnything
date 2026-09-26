# NFL wind venue map — September 26, 2026

**Fixed map: 20 permanently open-field U.S. venues, 21 home teams, and 175 eligible 2025 regular-season games.** This is a venue/forecast-station identity artifact; no game scores, market returns, recorded game wind, or game-level roof states were used.

The machine-readable map is `data/raw/nfl-wind-revisions-2026-09-26/venue-map.json`. Top-level `venues[]` exposes `stadium_id`, `station`, and `home_teams`; `eligible_games[]` supplies `game_id`, `stadium_id`, `station`, `location`, `gameday`, and other fixture metadata. A separate `venue-fixture-metadata-2025.csv` contains the 272 regular-season fixtures with outcome/weather columns omitted.

Eligibility requires all of: season 2025, `game_type == REG`, `location == Home`, and an exact `(stadium_id, home_team)` match to this fixed table. The retained nflverse schedule uses several old naming-rights aliases. More seriously, some international games retain their nominal home stadium ID: **stadium ID alone is insufficient.** The exclusions are 7 neutral/international fixtures and 90 fixtures at covered or retractable-roof venues. Both New York teams share the same venue/station.

| Stadium ID | Physical venue for 2025 | Home teams | Fixed MOS station | Station latitude, longitude | Eligible games |
| --- | --- | --- | --- | --- | ---: |
| BAL00 | M&T Bank Stadium | BAL | KBWI | 39.1733, -76.6841 | 9 |
| BOS00 | Gillette Stadium | NE | KOWD | 42.1912, -71.1733 | 9 |
| BUF00 | Highmark Stadium (1973 venue) | BUF | KBUF | 42.9408, -78.7358 | 9 |
| CAR00 | Bank of America Stadium | CAR | KCLT | 35.2226, -80.9543 | 8 |
| CHI98 | Soldier Field | CHI | KMDW | 41.7860, -87.7524 | 8 |
| CIN00 | Paycor Stadium | CIN | KLUK | 39.1033, -84.4186 | 9 |
| CLE00 | Huntington Bank Field (1999 lakefront venue) | CLE | KBKL | 41.5175, -81.6833 | 8 |
| DEN00 | Empower Field at Mile High | DEN | KBJC | 39.9088, -105.1172 | 9 |
| GNB00 | Lambeau Field | GB | KGRB | 44.4794, -88.1367 | 8 |
| JAX00 | EverBank Stadium (2025 configuration) | JAX | KCRG | 30.3361, -81.5147 | 8 |
| KAN00 | GEHA Field at Arrowhead Stadium | KC | KMKC | 39.1230, -94.5930 | 9 |
| MIA00 | Hard Rock Stadium | MIA | KOPF | 25.9102, -80.2828 | 8 |
| NAS00 | Nissan Stadium (1999 venue) | TEN | KBNA | 36.1189, -86.6892 | 9 |
| NYC01 | MetLife Stadium | NYG, NYJ | KTEB | 40.8590, -74.0562 | 16 |
| PHI00 | Lincoln Financial Field | PHI | KPHL | 39.8734, -75.2266 | 8 |
| PIT00 | Acrisure Stadium | PIT | KAGC | 40.3547, -79.9217 | 8 |
| SEA00 | Lumen Field | SEA | KBFI | 47.5300, -122.3000 | 8 |
| SFO01 | Levi's Stadium | SF | KSJC | 37.3594, -121.9244 | 8 |
| TAM00 | Raymond James Stadium | TB | KTPA | 27.9619, -82.5403 | 8 |
| WAS00 | Northwest Stadium | WAS | KADW | 38.8108, -76.8670 | 8 |

Station coordinates, elevations, network IDs, and archive-start metadata come directly from the [IEM station service](https://mesonet.agron.iastate.edu/sites/networks.php), through its `geojson/network.php?network=XX_ASOS` endpoint. The 15 state-network responses used here are retained and hashed in `venue-source-metadata/`; each venue entry supplies its exact source URL. The mapping chooses geographically nearby airports before the forecast revision test. It does **not** claim they are the nearest available stations, quantify venue-to-station distances, or calibrate airport wind to field-level wind. No station will be replaced because of its observed weather or test result. Missing coverage remains missing. [IEM documents GFS MOS as site-specific forecast guidance](https://mesonet.agron.iastate.edu/mos/); root separately acquired and audited the fixed stations' forecast archives.

Static architectural classification is distinct from a recorded game's roof state. The [government stadium-development study, PDF pages 53–54](https://www.leg.mn.gov/docs/2004/other/040634/stadium/www.stadium.state.mn.us/meetings/031209/031209_agenda.pdf#page=53) records original open-field configurations for most retained physical facilities. This is historical facility evidence, **not** a contemporaneous 2025 engineering certificate. The map includes venue-specific club, operator, architect, contractor, or municipal corroboration. Examples include [Carolina's explicit stadium facts](https://www.panthers.com/stadium/facts), [Gillette's outdoor field space](https://www.gillettestadium.com/event-spaces/), [the MetLife operator's venue description](https://www.metlifestadium.com/news/detail/metlife-stadium-selected-as-host-venue-for-fifa-world-cup-26-final), and [Levi's operator announcement identifying an outdoor stadium](https://levisstadium.com/2014/05/toyota-named-exclusive-auto-partner-stadium-49ers/).

A fixed spectator canopy is compatible with an open playing field. Miami's architect describes its [open-air canopy](https://www.hok.com/projects/view/miami-dolphins-hard-rock-stadium/); Seattle's operator specifies [roof protection for 70% of seats](https://www.lumenfield.com/venue-info/stadium-history-facts). Such structures can shield or channel wind, so airport forecasts remain exposure proxies. SoFi's covered playing field is excluded even though its sides are open. Atlanta, Dallas, Houston, Indianapolis, and Arizona are excluded regardless of whether a retractable roof happened to open on game day. Detroit, Minnesota, New Orleans, Las Vegas, and both Los Angeles teams are also excluded.

Venue-era distinctions matter. Buffalo uses the original 1973 stadium in 2025; the club's [August 2025 announcement](https://www.buffalobills.com/news/buffalo-bills-and-pepsico-beverages-announce-extension-of-28-year-partnership-into-new-highmark-stadium) places its replacement opening in 2026. Cleveland uses its lakefront venue rather than the [new enclosed 2029 stadium](https://browns.1rmg.com/press-releases/haslam-sports-group-alongside-aecom-hunt-and-turner-joint-venture-announce-groundbreaking-of-the-new-huntington-bank-field/). Jacksonville's [2025 media guide](https://static.www.nfl.com/league/apps/league-site/media-guides/2025/JAX.pdf) separates the existing stadium from the later canopy project. Nashville likewise uses the original venue. The map must not be reused for later seasons without reviewing these changes.

Remaining uncertainties: current IEM coordinates do not certify an unchanged historical sensor location; distant airport terrain, lake/coastal exposure, and stadium bowl geometry can produce substantial wind differences. Historic roof classification is manually reconciled to the retained 2025 physical venue identifiers. Nothing here supplies an independent original schedule-publication timestamp or proves weather information was executable in a betting market. No MOS downloads were performed by this mapping task.

Map SHA-256: `0e6113684297a5139d33090b27c9174446013e5f2b7e7197c0b92138d165049c`.
