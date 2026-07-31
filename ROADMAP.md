# trip-planner — improvements, features & data sources

Every API in this document was called live on 2026-07-31 from a clean sandbox with
no API key. Response times and sample payloads are real, not estimated. Anything
that could not be verified is marked **unverified** — same discipline the skill
demands of its own output.

---

## The gap this closes

SKILL.md tells the builder to verify coordinates, drive times and opening hours
"with a router, not a guess" — but ships no router, no geocoder and no hours
source. The whole verification burden falls on a research subagent reading
websites, which is slow, expensive and the single most likely place a plausible
wrong number enters the site.

Nine free, keyless APIs cover most of it. The point is not "more data" — it is
moving facts from *asserted by an LLM* to *fetched from a source with a URL*.

---

## Verified data sources

| Source | What it gives | Latency | Key | License |
|---|---|---|---|---|
| **Overpass (OSM)** | POIs + `opening_hours` + coords + wheelchair tags | 1.9 s / 24 POIs | none | ODbL |
| **Nominatim** | Geocode a hotel/town name → lat,lon | 0.6 s | none | ODbL |
| **OSRM** | Real driving time + distance | 0.5 s | none | ODbL |
| **Open-Meteo forecast** | 16-day daily temp + precip probability | 0.4 s | none | CC BY |
| **Open-Meteo climate** | Seasonal normals for trips >16 days out | 0.7 s | none | CC BY |
| **Nager.Date** | Public holidays (20 found for AT 2026) | 0.3 s | none | MIT |
| **Wikipedia REST** | One-paragraph place summary | 11.5 s ⚠ | none | CC BY-SA |
| **Commons geosearch** | Photos *by coordinate* rather than by name | 0.9 s | none | various CC |
| **Frankfurter** | ECB FX rates for a budget column | 0.7 s | none | ECB data |

⚠ Wikipedia REST was slow on first call (cold cache); subsequent calls were fast.
Treat 11 s as the worst case and fetch in parallel.

**Usage limits are real.** Nominatim asks for ≤1 req/s and a genuine User-Agent;
the public OSRM and Overpass instances are shared community infrastructure. Every
one of these needs the same throttle-and-backoff that `fetch_photos.py` now has.
Do not fan 200 requests at them from a subagent.

---

## Ranked proposals

### 1. `scripts/fetch_places.py` — Overpass → `maps-data.js` ★ highest value

One query returned 24 POIs around a base in 1.9 s, with exactly the fields the
POI schema needs: `name`, `lat`, `lng`, `opening_hours`, plus `website` and
`wheelchair` tags the template does not yet use.

Measured coverage on the sample: **12/24 had `opening_hours`**, 2/24 a website,
4/24 a wheelchair tag. So this is a *starting point that still needs
verification*, not a replacement for it — which is the honest framing. It flips
the research subagent's job from "find and transcribe 30 POIs" to "confirm these
30 and fill the 50% of gaps", which is both faster and much harder to fabricate.

Ships with a `source: "osm"` field per POI so the site can distinguish fetched
facts from asserted ones.

### 2. Parse `opening_hours` properly — do not regex it

OSM stores hours in a real grammar. During testing, a naive "is `Su` in the
string" check mislabelled `Mo-Fr 07:15-19:30; Sa 07:15-18:00; Su off` as
*open Sundays* — the exact opposite of the truth, on the exact feature the skill
markets (the supermarket Sunday badge).

`opening_hours.js` (228 KB, on jsDelivr, verified reachable) parses the grammar
including `Su off`, seasonal ranges like `May 3 - Sep 30`, and public holidays.
Feed it the Nager.Date holiday list and the map can answer the question that
actually matters: **"is this open on the specific day we plan to go?"**

That turns a static hours string into a per-day open/closed badge. It is the
single biggest usability win on the list.

### 3. Real drive times from OSRM

`13.1330,47.3230 → 13.6493,47.5622` returned **77 min / 79 km in 0.5 s**. The
schema's `drive_min` is currently whatever the model guessed. One call per POI
per base makes every number on the site traceable. Cache the matrix in
`maps-data.js` so the page stays a static file.

### 4. Weather → the rainy-day bank, wired up

The rainy-day section exists but is inert. Open-Meteo returns 16-day forecasts;
for trips further out, the climate API returns seasonal normals (August maxima
around 25 °C for the sample coordinate). Two uses:

- **At build time:** if a base averages 12 rain days in August, say so and size
  the indoor list accordingly.
- **At runtime:** a small fetch on the live site turns the rainy-day bank into
  "tomorrow is 80% rain — here are today's indoor options near Base 2."

This is the feature most likely to get used *during* the trip, which is the
skill's stated goal.

### 5. Public holidays — a real trap in German-speaking Europe

20 Austrian holidays for 2026 in 0.3 s. On Mariä Himmelfahrt (15 Aug, mid-trip
for the README's demo) supermarkets close and attractions run Sunday hours. The
site should flag holiday-affected days on the itinerary. Cheap to add, prevents
a genuinely ruined day.

### 6. Photo pipeline: geosearch *alongside* text search — not instead of

Commons geosearch finds photos by coordinate, so it structurally cannot drift to
a photogenic neighbour. But testing showed it is **not uniformly better**:

| Place | Text search | Geosearch |
|---|---|---|
| Salzburg old town | a *tactile model* of the old town ✗ | a random Getreidegasse doorway ~ |
| Hohenwerfen Castle | excellent castle photos ✓ | nothing within 700 m ✗ |
| Zell am See | a `.tif` postcard ✗ | `Zell-am-See.jpg` ✓ |

The right design is **both, then prefer agreement**: run each, and if a file
appears in both result sets, that is the confident pick. Otherwise present the
top candidate from each with its filename and let the builder choose. Geosearch
also naturally supplies a *fallback* when a text search is rejected by the
existing filters.

### 7. Accessibility & family data already in OSM, unused

`wheelchair`, `changing_table`, `highchair`, `kids_area`, `baby_feeding` are all
standard OSM tags and came back in the same Overpass query at no extra cost. For
a skill whose whole premise is *family* travel, a stroller/step-free badge is a
better fit than most of what is on the map today.

### 8. Smaller wins

- **Currency** — Frankfurter for a "roughly what this costs at home" column.
- **Sunset times** — SunCalc (8 KB, no network) for "leave the viewpoint by 20:41."
- **Offline / PWA** — a service worker caching tiles and pages. Families lose
  signal in Alpine valleys; a trip site that dies without data fails at the exact
  moment it is needed. This is a genuine differentiator and nothing else on this
  list matters as much when you are standing in a car park with one bar.
- **Print stylesheet** — one page per base, for the glovebox.
- **`maps-data.js` schema validation** — a `tests/validate_data.py` that fails on
  a missing coordinate or a bad `sunday` enum before deploy, not in the browser.

---

## What I would *not* build

- **Live transit/timetable data.** Not verified here, coverage is patchy outside
  cities, and stale departure times are worse than none.
- **Hotel/flight price APIs.** All require keys, most forbid caching prices, and
  the numbers go stale before the trip.
- **Scraping attraction sites for prices.** Brittle and legally murky; the
  existing `coupon-research.md` playbook already handles this with human judgment.

---

## Suggested order

1. `fetch_places.py` (Overpass) + `validate_data.py` — biggest verification win
2. `opening_hours.js` + holidays — the correctness bug and the per-day badge
3. OSRM drive times — removes the last guessed number
4. Weather-driven rainy-day bank
5. Geosearch in the photo pipeline
6. PWA/offline

Steps 1–3 turn "the model asserted it" into "a source returned it" for every
factual field on the site. That is the skill's whole thesis, finished.
