#!/usr/bin/env python3
"""
fetch_places.py — build maps-data.js from OpenStreetMap instead of from memory.

    python3 fetch_places.py bases.json maps-data.js

bases.json:

  {
    "lang": "en",
    "bases": [
      { "key": "base1", "label": "Werfenweng",
        "hotel": { "name": "Hotel Alpenblick", "lat": 47.4550, "lng": 13.2340 },
        "radius_km": 15 },
      { "key": "base2", "label": "Ellmau",
        "hotel": { "name": "Hotel Kaiserblick", "search": "Ellmau, Austria" } }
    ]
  }

A hotel is either explicit `lat`/`lng`, or a `search` string geocoded through
Nominatim. `radius_km` defaults to 15.

WHAT THIS IS AND IS NOT
-----------------------
This does NOT replace the verification step in SKILL.md. On a live sample only
about half of OSM POIs carried `opening_hours`, and OSM data can be years stale.

What it does is change the research subagent's job from "find and transcribe 30
places" — which is where invented coordinates and opening hours come from — into
"confirm these 30 and fill the gaps", which is faster and far harder to fake.

Every POI it emits carries:
    source    : "osm"                     provenance, rendered on the site
    osm       : "node/123456"             the exact object, so anyone can check
    review    : ["hours", "drive_min"]    fields a human still must supply

Fields it cannot fill are LEFT OUT and listed in `review`. Nothing is guessed.
`drive_min` is always in `review`: straight-line distance is not a drive time,
and this script does not route (see the OSRM step in ROADMAP.md).
"""
import hashlib, json, re, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osm_hours import day_state  # noqa: E402
from regions import profile, closed_day_label  # noqa: E402

UA = {"User-Agent": "trip-planner/1.0 (https://github.com/meiriohad76-oss/trip_planner)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"

# The public Overpass instances are volunteer infrastructure and their
# performance genuinely swings: the same trivial query measured 0.5 s and then
# 18.5 s (and a 504) within the same hour. Try them in order rather than failing
# a whole build because one endpoint is having a bad afternoon.
#
# PLANET-WIDE INSTANCES ONLY. This matters more than it looks.
# Several public Overpass endpoints serve a REGIONAL EXTRACT and answer an
# out-of-area query with an empty result and HTTP 200 — no error at all.
# overpass.osm.ch (Switzerland) returned 0 restaurants for an Austrian village
# in 0.5 s while overpass-api.de returned 26 for the identical query. Used as a
# fallback it would silently produce a half-empty site, which is exactly the
# failure mode this whole skill exists to prevent. Verify any mirror you add
# against a query with a known non-zero answer before trusting it.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Chunk responses are cached on disk, keyed by query hash. Overpass is slow and
# rate-limited; re-running a build after a crash, or tweaking one base, should
# not re-query everything. Delete the directory to force a refresh.
CACHE_DIR = Path(".osm-cache")
CACHE_TTL_S = 7 * 24 * 3600

# OSM selector -> the category enum used by maps.html / maps-data.js.
# Order matters: the first match wins, so specific types beat generic ones.
#
# PERFORMANCE NOTE — read before adding a selector.
# Overpass cost is dominated by `way`/`relation` selectors over a large radius:
# `way["natural"="water"]["name"]` at r=14 km pulls whole lake and river
# geometries and pushed a full run past 200 s, while the same run using node
# selectors plus a handful of cheap ways completes in seconds. Every selector
# below requires ["name"] where possible — an unnamed POI is useless on a map
# anyway, and the filter is applied server-side.
#
#   * exact `=` matches only — a `~"^(a|b)$"` regex is evaluated per element
#     and measurably slower than two exact selectors
#   * `node` and `way`, never `nwr` — relations pull multipolygon geometry
#     (nature reserves, lakes) and dominate the runtime
#   * always `["name"]`, filtered server-side; an unnamed POI is useless anyway
#
NODE_ONLY = [
    ("scenic",     [("tourism", "viewpoint")]),
    ("nature",     [("natural", "waterfall"), ("natural", "cave_entrance"),
                    ("natural", "peak")]),
    ("park",       [("leisure", "playground")]),
    ("restaurant", [("amenity", "restaurant")]),
    ("attraction", [("aerialway", "station")]),
]
# Types that are genuinely mapped as areas as often as points.
NODE_AND_WAY = [
    ("supermarket", [("shop", "supermarket")]),
    ("shopping",    [("shop", "mall"), ("shop", "department_store")]),
    ("museum",      [("tourism", "museum")]),
    ("castle",      [("historic", "castle"), ("historic", "fort")]),
    ("animal",      [("tourism", "zoo")]),
    ("pool",        [("leisure", "water_park"), ("amenity", "public_bath")]),
    ("park",        [("tourism", "theme_park")]),
    ("attraction",  [("tourism", "attraction")]),
    # Parking is a real trip-planning problem at Alpine attractions: lots fill
    # by 10am and many are paid. Fetched from OSM, never guessed.
    ("parking",     [("amenity", "parking")]),
]

# Family-relevant OSM tags that the current template ignores but shouldn't.
FAMILY_TAGS = ["wheelchair", "changing_table", "highchair", "kids_area", "baby_feeding"]

_last = [0.0]


def _throttle(gap=1.1):
    """Nominatim asks for <=1 req/s; Overpass is shared community infrastructure."""
    d = time.time() - _last[0]
    if d < gap:
        time.sleep(gap - d)
    _last[0] = time.time()


def _req(url, data=None, timeout=50, retries=3, label=""):
    """Retries are LOUD. A silent retry loop is indistinguishable from a hang —
    three quiet 90 s timeouts cost several minutes with no output at all."""
    for attempt in range(retries):
        _throttle()
        t0 = time.time()
        try:
            r = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(r, timeout=timeout) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            print(f"      ! {label} HTTP {e.code} after {time.time()-t0:.0f}s"
                  f" (attempt {attempt+1}/{retries})")
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"      ! {label} {type(e).__name__} after {time.time()-t0:.0f}s"
                  f" (attempt {attempt+1}/{retries})")
            if attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def wait_for_slot(base_url, max_wait=90):
    """Overpass gives each IP a small number of concurrent slots (typically 2).

    Once they are used, further requests QUEUE server-side and then trip the
    client timeout — which looks exactly like the server being down, and tempts
    you into retrying harder, which makes it worse. /api/status reports when a
    slot frees, so wait for it instead. This is also simply the polite way to
    use shared volunteer infrastructure.
    """
    status = base_url.replace("/api/interpreter", "/api/status")
    try:
        req = urllib.request.Request(status, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode()
    except Exception:  # noqa: BLE001 — status is best-effort
        return
    if "slots available now" in txt:
        return
    waits = [int(m) for m in re.findall(r"in (\d+) seconds", txt)]
    if not waits:
        return
    w = min(min(waits) + 2, max_wait)
    if w > 0:
        print(f"      … rate-limited, waiting {w}s for an Overpass slot")
        time.sleep(w)


def overpass(query, label=""):
    """Run one Overpass query: cache first, then each mirror in turn.

    Returns the element list, or None if every mirror failed. None is a real
    answer the caller must handle — a partial build that says so is far better
    than a build that silently drops a category.
    """
    key = hashlib.sha256(query.encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL_S:
        print(f"    {label}  (cached)")
        return json.loads(cached.read_text(encoding="utf-8")).get("elements", [])

    payload = urllib.parse.urlencode({"data": query}).encode()
    for mirror in OVERPASS_MIRRORS:
        host = mirror.split("//")[1].split("/")[0]
        wait_for_slot(mirror)
        try:
            # Short client timeout on purpose: a degraded mirror should cost us
            # ~25 s, not a minute, because there are three more to try. The
            # server-side [timeout:] in the query is set to match.
            d = _req(mirror, data=payload, retries=1, timeout=26,
                     label=f"{label} {host}")
            CACHE_DIR.mkdir(exist_ok=True)
            cached.write_text(json.dumps(d), encoding="utf-8")
            return d.get("elements", [])
        except Exception:  # noqa: BLE001 — try the next mirror
            continue
    return None


def geocode(q):
    d = _req(NOMINATIM + "?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1}), timeout=30)
    if not d:
        return None
    return float(d[0]["lat"]), float(d[0]["lon"])


def build_chunks(lat, lng, radius_m, per_chunk=3):
    """Several small queries instead of one big union.

    One 32-selector union against the public Overpass instance ran for minutes
    and repeatedly hit the client timeout; the same selectors split into chunks
    of ~6 return in seconds each. Chunking also means a single slow category
    cannot stall the whole build, and the caller can show real progress.
    """
    a = f"(around:{radius_m},{lat},{lng})"
    sels = []
    for _, tagpairs in NODE_ONLY:
        for k, v in tagpairs:
            sels.append(f'node["{k}"="{v}"]["name"]{a};')
    for _, tagpairs in NODE_AND_WAY:
        for k, v in tagpairs:
            sels.append(f'node["{k}"="{v}"]["name"]{a};')
            sels.append(f'way["{k}"="{v}"]["name"]{a};')
    return ["[out:json][timeout:25];(\n" + "\n".join(sels[i:i + per_chunk])
            + "\n);out center tags 250;"
            for i in range(0, len(sels), per_chunk)]


# Tag -> category, checked in order so specific types beat generic ones.
# Kept separate from RULES because RULES now uses regex selectors that are not
# worth re-parsing, and because a wrong category here is silent on the map.
CATEGORISE = [
    ("supermarket", lambda t: t.get("shop") == "supermarket"),
    ("shopping",    lambda t: t.get("shop") in ("mall", "department_store")),
    ("museum",      lambda t: t.get("tourism") == "museum"),
    ("castle",      lambda t: t.get("historic") in ("castle", "fort")),
    ("animal",      lambda t: t.get("tourism") == "zoo"),
    ("pool",        lambda t: t.get("leisure") == "water_park"
                              or t.get("amenity") == "public_bath"),
    ("park",        lambda t: t.get("tourism") == "theme_park"
                              or t.get("leisure") == "playground"),
    ("scenic",      lambda t: t.get("tourism") == "viewpoint"),
    ("nature",      lambda t: t.get("natural") in ("waterfall", "cave_entrance", "peak")
                              or t.get("leisure") == "nature_reserve"),
    ("parking",     lambda t: t.get("amenity") == "parking"),
    ("restaurant",  lambda t: t.get("amenity") == "restaurant"),
    ("attraction",  lambda t: t.get("aerialway") == "station"
                              or t.get("tourism") == "attraction"),
]


def categorise(tags):
    for cat, test in CATEGORISE:
        try:
            if test(tags):
                return cat
        except Exception:  # noqa: BLE001 — a malformed tag must not kill the run
            continue
    return None


def pick_name(tags, lang):
    """Local name first — it is what road signs and Google Maps will show."""
    return (tags.get("name")
            or tags.get(f"name:{lang}")
            or tags.get("int_name")
            or tags.get("brand"))


def to_poi(el, lang, prof=None):
    prof = prof or {}
    tags = el.get("tags") or {}
    name = pick_name(tags, lang)
    if not name:
        return None
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lng = el.get("lon") or (el.get("center") or {}).get("lon")
    if lat is None or lng is None:
        return None
    cat = categorise(tags)
    if not cat:
        return None

    poi = {
        "name": name,
        "category": cat,
        "lat": round(float(lat), 6),
        "lng": round(float(lng), 6),
        "source": "osm",
        "osm": f"{el['type']}/{el['id']}",
    }
    review = ["drive_min"]          # never routed here, always needs filling

    hours = tags.get("opening_hours")
    if hours:
        poi["hours"] = hours
    else:
        review.append("hours")

    # Closing-day state, for whichever day this COUNTRY actually rests on.
    # Austria closes Sunday, Israel Saturday, Saudi Arabia Friday; Japan and the
    # US close nothing, and there the badge is suppressed entirely. See
    # scripts/regions.py — hardcoding Sunday was an Austria-only assumption.
    watch = list(prof.get("closed_days", [])) + list(prof.get("short_days", []))
    if cat in ("supermarket", "shopping") and watch:
        states = {}
        unknown = False
        for d in watch:
            st = day_state(hours, d)
            if st:
                states[d] = st
            else:
                unknown = True
        if states:
            poi["closed_days"] = states
        if unknown:
            # Unknown is not "closed". Say so and make a human resolve it.
            review.append("closed_days")

    # The official site is the ONLY ticket link we will emit. Deep links into a
    # booking flow are not in OSM, and a fabricated one sends a family to a dead
    # page with their card out. A human upgrades this to a real ticket URL after
    # visiting the site (see "tickets" in the review list).
    site = tags.get("website") or tags.get("contact:website")
    if site:
        poi["website"] = site
    if tags.get("phone") or tags.get("contact:phone"):
        poi["phone"] = tags.get("phone") or tags["contact:phone"]
    if tags.get("cuisine"):
        poi["cuisine"] = tags["cuisine"]

    fam = {k: tags[k] for k in FAMILY_TAGS if k in tags}
    if fam:
        poi["family"] = fam

    if cat == "parking":
        p = {}
        if tags.get("fee") in ("yes", "no"):
            p["fee"] = tags["fee"] == "yes"
        for k_osm, k_out in (("capacity", "capacity"), ("parking", "type"),
                             ("maxstay", "maxstay"), ("charge", "charge"),
                             ("capacity:disabled", "disabled")):
            if tags.get(k_osm):
                p[k_out] = tags[k_osm]
        if p:
            poi["parking"] = p
        # Live occupancy is not in OSM, and a stale "spaces free" number is
        # worse than none. Say what we know: size, price, type.
        if "fee" not in p:
            review.append("parking.fee")

    # Paid, ticketed places should end up with a real booking link.
    if cat in ("attraction", "museum", "castle", "animal", "pool", "park"):
        review.append("tickets")

    review.append("desc")           # OSM has no prose; a human writes this
    poi["review"] = review
    return poi


def dedupe(pois):
    """Same name within ~150 m is the same place mapped twice (node + way)."""
    out = []
    for p in pois:
        dup = False
        for q in out:
            if p["name"].lower() == q["name"].lower() and \
               abs(p["lat"] - q["lat"]) < 0.0015 and abs(p["lng"] - q["lng"]) < 0.0022:
                dup = True
                break
        if not dup:
            out.append(p)
    return out


def cap_per_category(pois, limits):
    kept, counts = [], {}
    for p in sorted(pois, key=lambda x: (len(x.get("review", [])), x["name"])):
        c = p["category"]
        if counts.get(c, 0) >= limits.get(c, 12):
            continue
        counts[c] = counts.get(c, 0) + 1
        kept.append(p)
    return kept


LIMITS = {"restaurant": 10, "supermarket": 6, "parking": 8, "scenic": 6,
          "nature": 8, "attraction": 14, "museum": 6, "castle": 5,
          "pool": 5, "animal": 4, "park": 6, "shopping": 3}


def js_value(v):
    return json.dumps(v, ensure_ascii=False)


def render(bases, lang, prof=None, country=""):
    L = ['/* ==========================================================================',
         '   maps-data.js — GENERATED by scripts/fetch_places.py from OpenStreetMap.',
         '',
         '   Every POI carries source:"osm" and an osm id you can open at',
         '   https://www.openstreetmap.org/<osm> to check it yourself.',
         '',
         '   THIS FILE IS NOT FINISHED. Each POI has a `review` array listing the',
         '   fields a human still has to supply or confirm:',
         '     drive_min  — always: this script does not route. Use a real router.',
         '     hours      — OSM had none, or they need confirming against the',
         '                  official site (OSM hours are frequently years stale).',
         '     closed_days— the hours string was too complex to read safely, or',
         '                  the country has no recorded closing-day rule.',
         '     desc       — OSM carries no prose; write one or two sentences.',
         '   Delete each entry from `review` as you confirm it, and drop the key',
         '   entirely once the array is empty. tests/validate_data.py reports what',
         '   is left.',
         '   ========================================================================== */']
    # Region settings the map reads: which day to badge, units, nav apps.
    prof = prof or {}
    if prof:
        L += ['window.TRIPREGION = ' + js_value({
            "country": country,
            "closed_days": prof.get("closed_days", []),
            "short_days": prof.get("short_days", []),
            "badge": prof.get("badge", False),
            "distance": prof.get("distance", "km"),
            "temperature": prof.get("temperature", "C"),
            "nav": prof.get("nav", ["waze", "gmaps"]),
            "note": prof.get("note", ""),
        }) + ';', '']
    L += ['window.MAPDATA = {', '']
    for b in bases:
        L.append(f'  /* ==================== {b["label"]} ==================== */')
        L.append(f'  {b["key"]}: {{')
        h = b["hotel"]
        L.append(f'    hotel: {{ name: {js_value(h["name"])}, '
                 f'lat: {h["lat"]}, lng: {h["lng"]} }},')
        L.append("    pois: [")
        for p in b["pois"]:
            bits = [f'name:{js_value(p["name"])}', f'category:{js_value(p["category"])}',
                    f'lat:{p["lat"]}', f'lng:{p["lng"]}']
            # Order matters only for readability. drive_* are written by
            # fetch_routes.py; hours_note carries prose that the
            # opening_hours grammar cannot express.
            for k in ("hours", "hours_note", "closed_days", "drive_min", "drive_km",
                      "drive_src", "drive_note", "pass", "website", "phone",
                      "cuisine", "parking"):
                if k in p:
                    bits.append(f'{k}:{js_value(p[k])}')
            if "family" in p:
                bits.append(f'family:{js_value(p["family"])}')
            # Optional: a hand-authored POI has no OSM provenance, and
            # inventing one would be worse than omitting it.
            if p.get("source"):
                bits.append(f'source:{js_value(p["source"])}')
            if p.get("osm"):
                bits.append(f'osm:{js_value(p["osm"])}')
            if p.get("review"):
                bits.append(f'review:{js_value(p["review"])}')
            L.append("      { " + ", ".join(bits) + " },")
        L.append("    ],")
        L.append("  },")
        L.append("")
    L.append("};")
    return "\n".join(L) + "\n"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    out_path = sys.argv[2]
    lang = cfg.get("lang", "en")
    # ISO-3166 alpha-2 of the destination. Drives the closing-day badge, units
    # and which navigation apps actually work. Without it the badge is
    # suppressed rather than guessed — see scripts/regions.py.
    country = (cfg.get("country") or "").upper()
    prof = profile(country)
    if not country:
        print("  ! no \"country\" in the config — closing-day badge, units and "
              "nav apps fall back to neutral defaults. Set it (e.g. \"AT\", "
              "\"IL\", \"JP\") for correct behaviour.")
    else:
        watch = prof["closed_days"] + prof["short_days"]
        print(f"  country {country}: "
              + (f"watching {closed_day_label(watch)}" if watch
                 else "no closing-day rule — badge off")
              + f", {prof['distance']}/{prof['temperature']}, nav={'+'.join(prof['nav'])}")
        print(f"    {prof['note']}")
    bases, total_review = [], 0

    for b in cfg["bases"]:
        h = dict(b["hotel"])
        if "lat" not in h or "lng" not in h:
            q = h.get("search") or b.get("label")
            print(f"  geocoding {q!r} …")
            got = geocode(q)
            if not got:
                print(f"  ✗ could not geocode {q!r} — skipping base {b['key']}")
                continue
            h["lat"], h["lng"] = got
            print(f"    -> {h['lat']:.5f},{h['lng']:.5f}  (verify this is the right place)")

        radius = int(float(b.get("radius_km", 15)) * 1000)
        chunks = build_chunks(h["lat"], h["lng"], radius)
        print(f"  querying Overpass around {b.get('label', b['key'])} "
              f"(r={radius/1000:.0f} km, {len(chunks)} chunks) …")
        raw, failed, empty_chunks = [], 0, 0
        for i, q in enumerate(chunks, 1):
            t0 = time.time()
            els = overpass(q, label=f"chunk {i}/{len(chunks)}")
            if els is not None and not els:
                # Legitimate for a rare category, suspicious across the board —
                # it is the signature of a regional-extract mirror.
                empty_chunks += 1
            if els is None:
                # One dead chunk must not lose the other categories. Say which
                # ones are missing so they can be re-run or filled by hand.
                failed += 1
                print(f"    chunk {i}/{len(chunks)}  FAILED on every mirror — "
                      f"categories in this chunk are MISSING from the output")
                continue
            raw += els
            print(f"    chunk {i}/{len(chunks)}  {time.time()-t0:5.1f}s  {len(els):4d} elements")
        if failed:
            print(f"    ⚠ {failed}/{len(chunks)} chunks failed — this base is INCOMPLETE. "
                  f"Re-run to retry (successful chunks are cached).")
        if empty_chunks >= len(chunks) - 1 and not failed:
            print(f"    ⚠ {empty_chunks}/{len(chunks)} chunks came back EMPTY. Either the "
                  f"coordinates are wrong, or a mirror is serving a regional extract "
                  f"that does not cover this area. Check the hotel lat/lng first.")

        pois = [p for p in (to_poi(e, lang, prof) for e in raw) if p]
        pois = cap_per_category(dedupe(pois), LIMITS)
        n_rev = sum(len(p.get("review", [])) for p in pois)
        total_review += n_rev
        by_cat = {}
        for p in pois:
            by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
        print(f"    {len(raw)} raw -> {len(pois)} POIs  "
              + " ".join(f"{k}:{v}" for k, v in sorted(by_cat.items())))
        print(f"    {n_rev} fields still need a human")
        bases.append({"key": b["key"], "label": b.get("label", b["key"]),
                      "hotel": h, "pois": pois})

    Path(out_path).write_text(render(bases, lang, prof, country), encoding="utf-8")
    print(f"\nWrote {out_path} — {sum(len(b['pois']) for b in bases)} POIs "
          f"across {len(bases)} bases.")
    print(f"{total_review} review items outstanding. Run tests/validate_data.py "
          f"to see them, and do NOT ship while `hours` or `closed_days` are unresolved.")
    print("Data © OpenStreetMap contributors (ODbL) — credit it in the footer.")


if __name__ == "__main__":
    main()
