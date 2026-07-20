# vacation-site-builder

A [Claude Code](https://claude.com/claude-code) skill that builds a complete, deployable **family vacation website** — sightseeing and logistics, no trails or hiking.

Give it your bases, dates, and kids' ages, and it produces a two-page site:

- **`index.html`** — hero with a live countdown, a day-by-day itinerary per base, a hotels & rental-car table, discount/city-card coverage tables, opening hours, a rainy-day alternatives bank, and a localStorage packing checklist.
- **`maps.html` + `maps-data.js`** — an interactive Leaflet map per base: filter by category, search, sort by distance from the hotel, with drive times, opening hours, pass badges, Sunday-supermarket badges, and one-tap Waze / Google Maps navigation.

## What makes it different

The value isn't the itinerary prose — any LLM writes "visit the old town." The value is that the site is **real and usable on the trip**:

- **Real photos, never invented URLs.** `scripts/fetch_photos.py` pulls verified images from Wikimedia Commons and writes an attribution `credits.json`. Anything it can't resolve becomes a gradient tile — never a fake `<img src>`.
- **Verified coordinates, drive times and opening hours** — or an explicit "couldn't confirm."
- **Discount-card coverage** cross-checked so the itinerary and maps agree.
- **Deploys** cleanly to Vercel as plain static files.

Light/dark theme, reveal animations, sticky scroll-spy nav, RTL (Hebrew/Arabic) support.

> For running/hiking/cycling routes with GPX and elevation, use the sibling skill [trail-route-planner](https://github.com/sdanpo/trail-route-planner) instead.

## Install

Clone into your Claude Code skills directory:

```bash
git clone https://github.com/sdanpo/vacation-site-builder ~/.claude/skills/vacation-site-builder
```

Then just ask Claude Code to build a vacation site, or run `/vacation-site-builder`.

## Layout

```
vacation-site-builder/
├── SKILL.md                 # workflow + guardrails
├── scripts/
│   └── fetch_photos.py      # Wikimedia Commons downloader + credits.json
└── references/
    ├── itinerary.html       # main page template (full design system + JS)
    ├── maps.html            # interactive Leaflet maps page
    └── maps-data.js         # POI data schema with samples
```
