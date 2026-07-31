#!/usr/bin/env python3
"""
Offline tests for fetch_places.py.

Uses a fixture of REAL Overpass elements (captured live from overpass-api.de
around Werfenweng and Salzburg) so the transform logic is testable without
depending on the public Overpass instances, whose response times were measured
swinging between 0.5 s and a 504 within a single hour.

Network behaviour (mirrors, cache, throttling) is deliberately not covered here.
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_places as fp  # noqa: E402

# Real elements, trimmed to the tags that matter. Sourced from live queries.
FIXTURE = [
    {"type": "node", "id": 1, "lat": 47.3474, "lon": 13.2008,
     "tags": {"name": "Billa", "shop": "supermarket",
              "opening_hours": "Mo-Fr 06:50-19:00; Sa 06:50-18:00"}},
    {"type": "node", "id": 2, "lat": 47.3465, "lon": 13.2011,
     "tags": {"name": "Lidl", "shop": "supermarket",
              "opening_hours": "Mo-Fr 07:15-19:30; Sa 07:15-18:00; Su off"}},
    {"type": "node", "id": 3, "lat": 47.3128, "lon": 13.1893,
     "tags": {"name": "Liechtensteinklamm", "tourism": "attraction",
              "opening_hours": "May 3 - Sep 30: 09:00 - 18:00"}},
    {"type": "node", "id": 4, "lat": 47.3206, "lon": 13.1517,
     "tags": {"name": "Anema & Core", "amenity": "restaurant",
              "cuisine": "pizza", "opening_hours": "Mo-Su 11:30-20:30",
              "wheelchair": "yes", "highchair": "yes"}},
    {"type": "way", "id": 5, "center": {"lat": 47.4795, "lon": 13.1394},
     "tags": {"name": "Burg Hohenwerfen", "historic": "castle",
              "website": "https://www.salzburg-burgen.at"}},
    {"type": "node", "id": 6, "lat": 47.7998, "lon": 13.0439,
     "tags": {"name": "Mirabell-Congress-Garage", "amenity": "parking",
              "fee": "yes", "capacity": "700", "parking": "underground"}},
    {"type": "node", "id": 7, "lat": 47.3342, "lon": 13.0761,
     "tags": {"name": "Wenger Wasserfall", "natural": "waterfall"}},
    # --- things that must be DROPPED ---
    {"type": "node", "id": 8, "lat": 47.30, "lon": 13.10,
     "tags": {"amenity": "restaurant"}},                       # no name
    {"type": "node", "id": 9, "tags": {"name": "No coords", "tourism": "museum"}},
    {"type": "node", "id": 10, "lat": 47.31, "lon": 13.11,
     "tags": {"name": "Bench", "amenity": "bench"}},           # uncategorised
    # --- duplicate of #1 (node + way of the same shop) ---
    {"type": "way", "id": 11, "center": {"lat": 47.3475, "lon": 13.2009},
     "tags": {"name": "Billa", "shop": "supermarket"}},
]

fails, notes = [], []


def check(cond, msg):
    if not cond:
        fails.append(msg)


pois = [p for p in (fp.to_poi(e, "en") for e in FIXTURE) if p]
notes.append(f"{len(FIXTURE)} raw elements -> {len(pois)} POIs")

check(len(pois) == 8, f"expected 8 POIs after dropping 3 bad ones, got {len(pois)}")
names = {p["name"] for p in pois}
check("Bench" not in names, "uncategorised amenity=bench was kept")
check("No coords" not in names, "element without coordinates was kept")

# First occurrence wins: the fixture intentionally contains a second "Billa"
# (the way duplicate, with no opening_hours) to exercise dedupe. Indexing by
# last-wins would silently test the wrong record.
by_name = {}
for p in pois:
    by_name.setdefault(p["name"], p)

# --- categories -------------------------------------------------------------
expect = {"Billa": "supermarket", "Lidl": "supermarket",
          "Liechtensteinklamm": "attraction", "Anema & Core": "restaurant",
          "Burg Hohenwerfen": "castle", "Mirabell-Congress-Garage": "parking",
          "Wenger Wasserfall": "nature"}
for n, c in expect.items():
    check(by_name.get(n, {}).get("category") == c,
          f"{n}: expected category {c}, got {by_name.get(n,{}).get('category')}")
notes.append("all 7 categories mapped correctly")

# --- the Sunday trap --------------------------------------------------------
check(by_name["Lidl"].get("sunday") == "closed",
      f"'Su off' must be closed, got {by_name['Lidl'].get('sunday')}")
check(by_name["Billa"].get("sunday") == "closed",
      f"unmentioned Sunday must be closed, got {by_name['Billa'].get('sunday')}")
notes.append("'Su off' correctly read as closed, not open")

# --- unknowns are flagged, never guessed ------------------------------------
lk = by_name["Liechtensteinklamm"]
check("hours" in lk, "seasonal hours string should still be carried through")
check("sunday" not in lk, "sunday must not be set for a non-supermarket")
wf = by_name["Wenger Wasserfall"]
check("hours" not in wf, "a POI with no OSM hours must not invent them")
check("hours" in wf.get("review", []), "missing hours must be flagged for review")
notes.append("missing fields omitted and listed in `review`, not guessed")

# --- provenance -------------------------------------------------------------
check(all(p.get("source") == "osm" for p in pois), "every POI needs source:'osm'")
check(all(re.fullmatch(r"(node|way)/\d+", p.get("osm", "")) for p in pois),
      "every POI needs a resolvable osm id")
check(by_name["Burg Hohenwerfen"]["osm"] == "way/5", "way id/centre not handled")
check(all("drive_min" in p.get("review", []) for p in pois),
      "drive_min must always be flagged — this script does not route")
notes.append("provenance + drive_min flag present on every POI")

# --- tickets & parking & family --------------------------------------------
check("tickets" in lk.get("review", []), "ticketed attraction should flag `tickets`")
check("tickets" not in by_name["Anema & Core"].get("review", []),
      "a restaurant should not flag `tickets`")
pk = by_name["Mirabell-Congress-Garage"]["parking"]
check(pk.get("fee") is True and pk.get("capacity") == "700"
      and pk.get("type") == "underground", f"parking fields wrong: {pk}")
check(by_name["Anema & Core"]["family"] == {"wheelchair": "yes", "highchair": "yes"},
      "family tags not captured")
check(by_name["Burg Hohenwerfen"].get("website", "").startswith("https://"),
      "website (the only honest ticket link) not captured")
notes.append("parking, family and ticket-review fields populated")

# --- dedupe -----------------------------------------------------------------
deduped = fp.dedupe(pois)
check(sum(1 for p in deduped if p["name"] == "Billa") == 1,
      "node+way duplicate of the same shop was not deduped")
notes.append(f"dedupe: {len(pois)} -> {len(deduped)}")

# --- rendered output must be valid JS and re-parse ---------------------------
js = fp.render([{"key": "base1", "label": "Test",
                 "hotel": {"name": "H", "lat": 47.4, "lng": 13.2},
                 "pois": deduped}], "en")
tmp = Path(tempfile.mkdtemp())
(tmp / "d.js").write_text(js, encoding="utf-8")
r = subprocess.run(["node", "--check", str(tmp / "d.js")], capture_output=True, text=True)
check(r.returncode == 0, f"rendered maps-data.js is not valid JS: {r.stderr[:200]}")

dump = tmp / "dump.js"
dump.write_text(js + "\nconsole.log(JSON.stringify(window.MAPDATA));", encoding="utf-8")
r = subprocess.run(["node", "-e", f"global.window={{}};require('{dump}')"],
                   capture_output=True, text=True)
if r.returncode == 0:
    data = json.loads(r.stdout.strip())
    got = len(data["base1"]["pois"])
    check(got == len(deduped), f"round-trip lost POIs: {got} != {len(deduped)}")
    check(data["base1"]["pois"][0].get("source") == "osm", "source lost in render")
    notes.append(f"render round-trips through node: {got} POIs intact")
else:
    fails.append(f"could not evaluate rendered JS: {r.stderr[:200]}")

print("\n".join("  · " + n for n in notes))
if fails:
    print("\nFAILURES:")
    for f in fails:
        print("  ✗ " + f)
    sys.exit(1)
print("\nALL FETCH_PLACES CHECKS PASSED")
