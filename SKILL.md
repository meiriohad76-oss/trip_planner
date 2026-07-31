---
name: trip-planner
description: Build and deploy a family trip website — day-by-day itinerary per base, hotels, discount-card coverage, opening hours, packing list, plus an interactive Leaflet map of attractions, restaurants and supermarkets with drive times and one-tap navigation. Every photo, coordinate and opening hour is verified, never invented. Use when asked to build a trip, holiday or vacation website or itinerary site for sightseeing. NOT for trails, hiking, running or GPX routes — use trail-route-planner for those.
---

# Trip planner

Turn "build me a website for our family trip" into a polished, deployed site —
**sightseeing, attractions, food and logistics, no trails or hiking**. If the user
wants runs/hikes/GPX, that is the `trail-route-planner` skill instead; this one is
for families who want museums, cable cars, lakes, playgrounds and restaurants.

The value is **not** the itinerary prose — any LLM can write "visit the old town."
The value is that the site is real and usable on the trip: every **photo is a real
Wikimedia image of the real place** (never a hallucinated `<img src>`), every
**coordinate, drive time and opening hour is verified**, every attraction is tagged
with which **discount card** covers it, and it **deploys**. Do not skip the
verification steps — they are the point.

## Ask first (these change the whole site)

1. **Where & when** — bases (towns/hotels) and exact dates. Dates drive the
   countdown, the per-day headers, and seasonal opening hours.
2. **Who** — ages of kids especially. "2 toddlers" vs "two teens" produces
   different attractions and pacing.
3. **Language & direction** — English? Hebrew/RTL? German? Set `lang`/`dir` and the
   font accordingly (the templates are LTR English; RTL notes are inline).
4. **Discount cards** — is there a region card, guest card, or hotel card? These
   decide the "what's free" tables and the pass badges on the maps.
5. **How much do they have already** — a booking confirmation, a list of must-dos,
   a hotel address? Pull real data in rather than inventing it.

## What the site contains (all trail-free)

A two-page site, both self-contained, sharing one design system:

- **`index.html`** — hero + live countdown + count-up stats; one section per base
  with a banner and day-by-day cards; hotels & rental-car table; discount-card
  coverage cards + table; opening-hours table; rainy-day alternatives bank;
  localStorage packing checklist; footer with photo credits.
- **`maps.html`** + **`maps-data.js`** — an interactive Leaflet map per base:
  filter by category, search, sort by distance from the hotel, popups and list
  cards with drive time, opening hours, pass badge, supermarket Sunday badge, and
  Waze + Google Maps navigation buttons.
- **`img/`** — real Wikimedia photos + `credits.json` (attribution is required).

## Workflow

### 0. Pull the map data from OpenStreetMap first
Before any research subagent runs, fetch what OSM already knows:

```
python3 scripts/fetch_places.py bases.json maps-data.js
python3 tests/validate_data.py maps-data.js
```

`bases.json` needs a `"country"` (ISO-3166 alpha-2). It drives the closing-day
badge, distance units and which navigation apps actually work — see
`scripts/regions.py`. Without it those all fall back to neutral defaults and the
badge is suppressed rather than guessed.

This does **not** replace step 1 — on a live sample only about half of OSM POIs
carried `opening_hours`, and OSM can be years stale. It changes the subagent's
job from "find and transcribe 30 places" (where invented coordinates come from)
to "confirm these 30 and fill the gaps".

Every POI carries `source:"osm"` and an `osm` id you can open at
`openstreetmap.org/<id>`, plus a `review` array naming the fields still missing.
Feed that file to the step-1 subagents and tell them to resolve the `review`
items. `validate_data.py` lists what is outstanding; **do not deploy while
`hours` or `sunday` are unresolved**.

Credit OpenStreetMap (ODbL) in the footer — it is a licence condition.

### 0b. Precompute "is it open on the day we go?"
After the hours are filled in and verified:

```
npm install opening_hours@3.8.0        # build-time only, never shipped
python3 scripts/build_days.py maps-data.js 2026-08-05 2026-08-19
```

This evaluates every POI against every trip date using the real OSM
`opening_hours` grammar — seasonal ranges, weekday rules, public holidays — and
writes a few-KB `window.TRIPDAYS` table into `maps-data.js`. The map then shows
a day picker and per-day open/closed badges **with no extra JavaScript**;
doing it in the browser would cost ~291 KB across three CDN scripts on a page
whose whole point is working offline.

**`hours` must be OSM syntax** (`Mo-Fr 09:00-17:00; Su off`,
`May 1-Oct 31: 09:00-16:30`) for this to work. Prose like "Daily 9-6 ish" cannot
be parsed; the POI is reported and simply drops out of the day view. Put prose
in `hours_note` instead.

Two holiday gaps are surfaced, never hidden:
- `opening_hours.js` has no `PH` data for many countries (Austria works; Israel
  and Japan throw). Those dates are marked "holidays not checked".
- Nager.Date has no data for Israel, Thailand, the UAE or India. The script says
  so and asks you to research those holidays by hand.

### 1. Research the destinations — in parallel, per base
Spawn a subagent per base/region. Demand from each, as structured data:
- **Attractions with real `lat,lon`** — cable cars, parks, lakes, castles,
  museums, animal parks, thermal baths, playgrounds. Not just names — coordinates.
- **Family fit**: age suitability, indoor/outdoor, how long it takes.
- **Verified opening hours + season** (these are wrong online constantly — prefer
  official sites), and whether a **discount card** covers it.
- **Drive time from the hotel** (a router, not a guess).
- **Restaurants** (family-friendly, near each base) and **supermarkets** with
  hours for the destination's **closing day** — Austria and Germany rest on
  Sunday, Israel on Saturday (and Friday afternoon), much of the Gulf on Friday,
  while Japan, the US and most of Asia close nothing. `scripts/regions.py` holds
  the rule per country; the map badges the right day, or hides the badge.
- **Rainy-day indoor options** per region.
Tell them to say "could not verify" rather than invent an address, hour, or coord.

### 2. Hunt deals & savings — per region (optional, ask first)
If the user wants the trip to be economical, run a **deals & savings pass** per
region following `references/coupon-research.md`. Spawn one research subagent per
base, feeding it the real attraction/restaurant list from step 1, and check every
channel in that playbook: coupon aggregators (Groupon & local clones — usually a
dead end, verify anyway), ticket resellers (GetYourGuide/Tiqets/Klook), the
**attraction's own online shop** (dynamic/early-bird/family/evening rates — where
the real savings are), **free guest cards + paid region/city cards** (so nobody
pays for what's already free), **restaurant savings** (TheFork, fixed lunch menus,
kids-eat-free), **surplus-food apps active in that region** (Too Good To Go, Karma,
Olio…), and grocery loyalty programs. Follow the same verification discipline as
the rest of the skill: **never invent a promo code or price**, always note blackout
dates and tourist-usability, prefer official pages. Deliver it as a briefing grouped
by region with a short "most-actionable" list. **Do not put any of it on the site
unless the user explicitly asks** — the playbook lists where it fits if they do.

### 3. Get REAL photos — never hand-write an image URL
Pick hero + per-base banner + a few marquee attraction photos. For each, find the
Wikimedia Commons file, then:

```
python3 scripts/fetch_photos.py photos.json img/
```

`photos.json` is `[{ "key": "...", "file": "Commons File.jpg" | "search": "...",
"must": ["Place"] }]`. It downloads real images and writes `img/credits.json`.
Reference each photo in the HTML using `credits[key].src` (it carries the real
extension — usually `.jpg`, sometimes `.png`).

The script rejects anything that is not a raster photograph: SVG logos, coats of
arms, maps and PDFs all live in the same Commons namespace and would otherwise be
saved as `<key>.jpg` and render broken. It also byte-checks the download.

**Read the filename it prints for every photo.** It guarantees a real,
correctly-typed, correctly-attributed image — it cannot guarantee the image is of
the thing you meant ("Salzburg old town" once resolved to a photo of a scale
*model* of the old town). Add `"must": ["Salzburg"]` to anchor a search, and pin
the exact `"file"` once you have confirmed a good one.

**Anything unresolved gets a gradient tile** (`.banner.grad` / `.ph` classes),
never a fake photo. Render `credits.json` in the footer — CC licenses require
attribution (the template already fetches it).

### 4. Build the pages from the templates
Copy the three reference files into the project and fill them with real content:
- `references/itinerary.html` → `index.html`
- `references/maps.html` → `maps.html`
- `references/maps-data.js` → `maps-data.js`

They are complete, working files. Duplicate the marked blocks (one `<section>` per
base, one `.day` per day, one POI per attraction). Keep the design tokens identical
across both pages so they read as one site. For RTL, set `<html dir="rtl">` and an
RTL font; the layout uses logical properties so it already flips.

**Both templates have a `TEMPLATE CONFIG` block — read it before editing.**
- `maps.html` builds one map per key in `MAPDATA`, paired with the Nth
  `<section>`: base 1 → `#map1 #ctrl-1 #list-1 #count-1 #legend-1`, base 2 → `…2`,
  and so on. Any number of bases works. If the data and the sections disagree in
  either direction, the console says exactly which ids to fix — check it.
- `itinerary.html` takes the departure date from `CONFIG.departure` (`YYYY-MM-DD`).
  The config block also lists the per-trip edits that are *not* driven from JS:
  `<title>`, the `.logo`, the nav `<li>`s, the hero eyebrow/`<h1>`, the
  `data-to` stat counters and the footer. Work through that list — a leftover
  "Vacation 2026" in the header is the most common miss.

Data hygiene that makes or breaks it:
- Every map POI needs a **real** `lat,lng`, a `category`, `drive_min`, and
  (attractions) verified `hours`. Supermarkets need `closed_days`, e.g.
  `{Su:"closed"}` in Austria or `{Sa:"closed",Fr:"limited"}` in Israel.
- `maps.html` reads `window.TRIPREGION` for the closing day, units and nav apps.
- Tag each attraction with `pass:true` only if the discount card genuinely covers
  it — cross-check against the coverage table so the two pages agree.
- Days with no verified photo use `.ph` gradient tiles; bases with no photo use
  `.banner.grad`. Never stretch one photo across unrelated days.

### 5. Verify before shipping
- Run the test suite first — it catches structural mistakes before you look at
  content:
  ```
  python3 tests/validate_data.py maps-data.js   # schema + outstanding review items
  python3 tests/test_maps.py                    # coords, ARIA, XSS, mobile overflow
  python3 tests/test_nbase.py                   # every base builds
  python3 tests/test_fetch_places.py            # OSM transform (offline fixture)
  python3 tests/test_regions.py                 # AT/IL/SA/JP/US/KR behaviour
  python3 tests/test_days.py                    # per-date open/closed + holidays
  python3 scripts/osm_hours.py                  # opening-hours reader
  python3 scripts/regions.py                    # country profiles
  ```
- Open both pages in a browser (`vercel:verification` or the `run` skill / a local
  `python3 -m http.server`). **Check the browser console** — the templates report
  skipped POIs and base/section mismatches there rather than failing silently.
  Then check: countdown shows a sane number, maps render with
  pins, filters/search/sort work, nav scroll-spy highlights, dark mode looks right,
  and it does not scroll horizontally on mobile width.
- Spot-check 2–3 drive times and opening hours against source — if one is fabricated
  they all lose trust.
- Confirm every `<img>` resolves (no broken images) and credits show in the footer.

### 6. Deploy
This kind of static site deploys cleanly on Vercel (the sibling project already
uses it). Use the `vercel:deploy` skill, or `vercel --prod`. Commit only when the
user asks; if deploying from a fresh repo, `vercel` links it first. Give the user
the URL.

## Guardrails
- **No trails, hikes, runs, GPX, or elevation content.** That is a different skill.
  If the user wants both, build this and suggest `trail-route-planner` for the runs.
- **No invented photos, coordinates, hours, or prices.** Verify or use a fallback
  (gradient tile) and say what you could not confirm.
- Keep both pages self-contained (only Leaflet + fonts from CDN, as in the
  templates) so they work as plain static files and on any host.
- Drive times and opening hours are estimates — put a "verify close to travel" note
  on the hours table (the template has one).

## Files
- `scripts/fetch_places.py` — OpenStreetMap → `maps-data.js`. Fetches POIs,
  parking, opening hours and family/accessibility tags with `source:"osm"`
  provenance and `review` flags for anything it cannot fill.
- `scripts/osm_hours.py` — cautious reader for the OSM `opening_hours` grammar,
  for any weekday. Returns `None` rather than guessing; see its docstring for
  why a regex is wrong.
- `scripts/regions.py` — per-country closing days, units and usable nav apps.
  This is where the Austria-only assumptions were quarantined.
- `scripts/build_days.py` + `scripts/day_status.js` — precompute per-date
  open/closed with the full `opening_hours` grammar, plus public holidays.
- `scripts/fetch_photos.py` — Wikimedia Commons downloader + `credits.json` writer.
  Rejects non-photos (SVG/PDF/drawings), byte-checks each download, supports
  `"must"` to anchor a search to the right place.
- `references/itinerary.html` — the main page template (full design system + JS).
- `references/maps.html` — interactive Leaflet maps page template. Builds one map
  per key in `MAPDATA`, so any number of bases works.
- `references/maps-data.js` — POI data schema with sample entries.
- `references/coupon-research.md` — per-region deals & savings playbook (attraction/
  restaurant coupons, guest/city cards, surplus-food & loyalty apps like Too Good To
  Go and TheFork), with verification discipline and where findings fit on the site.
- `tests/test_maps.py`, `tests/test_nbase.py` — headless browser checks on the
  templates. Run them after editing a template.
