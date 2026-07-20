---
name: vacation-site-builder
description: Build a complete, deployable family vacation website — a hero with a live countdown, a day-by-day itinerary per base, hotels & rental-car details, discount/city-card coverage tables, opening hours, a rainy-day alternatives bank, a packing checklist, and a separate interactive Leaflet map page of attractions, restaurants and supermarkets with drive times and one-tap navigation. Real Wikimedia photos, no invented image URLs. Use when asked to build a trip/holiday/vacation website or itinerary site for sightseeing (NOT trails/hiking/running — for those use trail-route-planner).
---

# Vacation site builder

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

### 1. Research the destinations — in parallel, per base
Spawn a subagent per base/region. Demand from each, as structured data:
- **Attractions with real `lat,lon`** — cable cars, parks, lakes, castles,
  museums, animal parks, thermal baths, playgrounds. Not just names — coordinates.
- **Family fit**: age suitability, indoor/outdoor, how long it takes.
- **Verified opening hours + season** (these are wrong online constantly — prefer
  official sites), and whether a **discount card** covers it.
- **Drive time from the hotel** (a router, not a guess).
- **Restaurants** (family-friendly, near each base) and **supermarkets** with
  **Sunday hours** — in AT/DE most close Sundays; the map badges this.
- **Rainy-day indoor options** per region.
Tell them to say "could not verify" rather than invent an address, hour, or coord.

### 2. Get REAL photos — never hand-write an image URL
Pick hero + per-base banner + a few marquee attraction photos. For each, find the
Wikimedia Commons file, then:

```
python3 scripts/fetch_photos.py photos.json img/
```

`photos.json` is `[{ "key": "...", "file": "Commons File.jpg" | "search": "..." }]`.
It downloads real images to `img/<key>.jpg` and writes `img/credits.json`. Reference
photos in the HTML as `img/<key>.jpg`. **Anything unresolved gets a gradient tile**
(`.banner.grad` / `.ph` classes), never a fake photo. Render `credits.json` in the
footer — CC licenses require attribution (the template already fetches it).

### 3. Build the pages from the templates
Copy the three reference files into the project and fill them with real content:
- `references/itinerary.html` → `index.html`
- `references/maps.html` → `maps.html`
- `references/maps-data.js` → `maps-data.js`

They are complete, working files. Duplicate the marked blocks (one `<section>` per
base, one `.day` per day, one POI per attraction). Keep the design tokens identical
across both pages so they read as one site. Set the countdown date, the section
ids, and the nav links. For RTL, set `<html dir="rtl">` and an RTL font; the layout
uses logical properties so it already flips.

Data hygiene that makes or breaks it:
- Every map POI needs a **real** `lat,lng`, a `category`, `drive_min`, and
  (attractions) verified `hours`. Supermarkets need `sunday: open|limited|closed`.
- Tag each attraction with `pass:true` only if the discount card genuinely covers
  it — cross-check against the coverage table so the two pages agree.
- Days with no verified photo use `.ph` gradient tiles; bases with no photo use
  `.banner.grad`. Never stretch one photo across unrelated days.

### 4. Verify before shipping
- Open both pages in a browser (`vercel:verification` or the `run` skill / a local
  `python3 -m http.server`). Check: countdown shows a sane number, maps render with
  pins, filters/search/sort work, nav scroll-spy highlights, dark mode looks right,
  and it does not scroll horizontally on mobile width.
- Spot-check 2–3 drive times and opening hours against source — if one is fabricated
  they all lose trust.
- Confirm every `<img>` resolves (no broken images) and credits show in the footer.

### 5. Deploy
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
- `scripts/fetch_photos.py` — Wikimedia Commons downloader + `credits.json` writer.
- `references/itinerary.html` — the main page template (full design system + JS).
- `references/maps.html` — interactive Leaflet maps page template.
- `references/maps-data.js` — POI data schema with sample entries.
