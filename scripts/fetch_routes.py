#!/usr/bin/env python3
"""
fetch_routes.py — replace guessed drive times with routed ones.

    python3 scripts/fetch_routes.py maps-data.js

`drive_min` is the last field on the site that is normally whatever the model
guessed; fetch_places.py deliberately flags it for review on every POI rather
than inventing a number. This fills it from a real router and clears the flag.

HOW
---
One OSRM *table* call per base gives the hotel-to-everywhere row in a single
request — far kinder to a public instance than one route call per POI. Results
are cached on disk, so re-running after fixing one base costs almost nothing.

SNAP DISTANCE IS A QUALITY SIGNAL, NOT NOISE
--------------------------------------------
A router cannot drive to a coordinate; it snaps to the nearest road first. A few
tens of metres is normal (a measured sample snapped between 7 m and 174 m). A
snap of hundreds of metres means the point is not near a drivable road — a
mountain summit, an island, the middle of a pedestrian zone — and the returned
duration is the time to somewhere else. Those POIs keep `drive_min` but gain a
`drive_note` and stay flagged for review, because "23 min" to the wrong place is
worse than no number.

WHAT IT DOES NOT DO
-------------------
No traffic, no time of day, no toll or ferry preferences: OSRM's public demo
server routes on a free-flow road graph. Treat the numbers as "typical clear
road" and keep the existing "verify close to travel" note on the site.
"""
import hashlib, json, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "trip-planner/1.0 (https://github.com/meiriohad76-oss/trip_planner)"}
# Public demo servers. project-osrm.org is the reference instance; both are
# volunteer-run and rate-limited, hence the throttle and the cache.
OSRM_MIRRORS = [
    "https://router.project-osrm.org",
    "https://routing.openstreetmap.de/routed-car",
]
CACHE_DIR = Path(".osrm-cache")
CACHE_TTL_S = 30 * 24 * 3600      # road networks change slowly
MAX_COORDS = 90                   # public table service caps the matrix size
SNAP_WARN_M = 300                 # beyond this, the router is routing elsewhere

_last = [0.0]


def _throttle(gap=1.2):
    d = time.time() - _last[0]
    if d < gap:
        time.sleep(gap - d)
    _last[0] = time.time()


def load_js(path, var):
    src = Path(path).read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp()) / "d.js"
    tmp.write_text(src + f"\nconsole.log(JSON.stringify(window.{var}||null));",
                   encoding="utf-8")
    r = subprocess.run(["node", "-e", f"global.window={{}};require('{tmp}')"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"✗ {path} is not valid JavaScript:\n{r.stderr[:400]}")
    return json.loads(r.stdout.strip() or "null")


def table(coords, label=""):
    """coords = [(lng,lat), ...] with the hotel first. Returns the API payload."""
    path = ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in coords)
    qs = urllib.parse.urlencode({"sources": "0", "annotations": "duration,distance"})
    key = hashlib.sha256((path + qs).encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL_S:
        print(f"    {label} (cached)")
        return json.loads(cached.read_text(encoding="utf-8"))

    for base in OSRM_MIRRORS:
        url = f"{base}/table/v1/driving/{path}?{qs}"
        host = base.split("//")[1].split("/")[0]
        _throttle()
        t0 = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=40) as r:
                d = json.load(r)
            if d.get("code") != "Ok":
                print(f"      ! {label} {host}: {d.get('code')} {d.get('message','')[:60]}")
                continue
            CACHE_DIR.mkdir(exist_ok=True)
            cached.write_text(json.dumps(d), encoding="utf-8")
            print(f"    {label} {time.time()-t0:.1f}s via {host}")
            return d
        except Exception as e:  # noqa: BLE001
            print(f"      ! {label} {host}: {type(e).__name__} after {time.time()-t0:.0f}s")
    return None


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield i, seq[i:i + n]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    data = load_js(path, "MAPDATA") or {}
    if not data:
        sys.exit("✗ window.MAPDATA is empty")

    src = Path(path).read_text(encoding="utf-8")
    filled = far = failed = 0

    for bkey, base in data.items():
        hotel = base.get("hotel") or {}
        pois = base.get("pois") or []
        try:
            hlat, hlng = float(hotel["lat"]), float(hotel["lng"])
        except Exception:  # noqa: BLE001
            print(f"  ✗ {bkey}: hotel has no usable coordinates — skipping")
            continue

        usable = []
        for i, p in enumerate(pois):
            try:
                usable.append((i, float(p["lat"]), float(p["lng"])))
            except Exception:  # noqa: BLE001
                continue
        print(f"  {bkey}: routing {len(usable)} POIs from {hotel.get('name','base')}")

        for offset, group in chunks(usable, MAX_COORDS - 1):
            coords = [(hlng, hlat)] + [(lng, lat) for _, lat, lng in group]
            d = table(coords, label=f"{bkey} [{offset + 1}-{offset + len(group)}]")
            if not d:
                failed += len(group)
                continue
            durations = (d.get("durations") or [[]])[0]
            distances = (d.get("distances") or [[]])[0]
            dests = d.get("destinations") or []
            for j, (idx, _, _) in enumerate(group):
                dur = durations[j + 1] if len(durations) > j + 1 else None
                dist = distances[j + 1] if len(distances) > j + 1 else None
                snap = (dests[j + 1] or {}).get("distance") if len(dests) > j + 1 else None
                p = pois[idx]
                def keep_flagged(poi):
                    """Make sure drive_min is listed for review — these numbers
                    are real but measure the wrong thing, so they must not look
                    settled just because a router produced them."""
                    rev = list(poi.get("review") or [])
                    if "drive_min" not in rev:
                        rev.append("drive_min")
                    poi["review"] = rev

                if dur is None:
                    # OSRM returns null when a point cannot be reached by road at
                    # all — an island, or across an unrouteable border.
                    p["drive_note"] = "no road route found"
                    keep_flagged(p)
                    failed += 1
                    continue
                p["drive_min"] = int(round(dur / 60))
                if dist is not None:
                    p["drive_km"] = round(dist / 1000, 1)
                p["drive_src"] = "osrm"
                if snap is not None and snap > SNAP_WARN_M:
                    p["drive_note"] = (f"nearest road is {int(snap)} m away — the drive "
                                       f"time is to that road, not the door")
                    keep_flagged(p)
                    far += 1
                else:
                    filled += 1
                    rev = [x for x in (p.get("review") or []) if x != "drive_min"]
                    if rev:
                        p["review"] = rev
                    else:
                        p.pop("review", None)

    print(f"\n  {filled} drive times routed and cleared for review")
    if far:
        print(f"  ⚠ {far} POIs are more than {SNAP_WARN_M} m from any road — they keep "
              f"`drive_min` but stay flagged, with a note saying what it measures")
    if failed:
        print(f"  ⚠ {failed} POIs could not be routed at all")

    # Rewrite only the drive fields, so hand-edited prose elsewhere survives.
    out = _rewrite(src, data)
    Path(path).write_text(out, encoding="utf-8")
    print(f"\nUpdated {path}. Times are free-flow (no traffic, no time of day) — "
          f"keep the 'verify close to travel' note on the site.")
    print("Routing © OpenStreetMap contributors via OSRM (ODbL) — credit it in the footer.")


def _rewrite(src, data):
    """Swap in a freshly rendered MAPDATA block, leaving everything else alone.

    maps-data.js also holds window.TRIPREGION and window.TRIPDAYS, which are
    written by other scripts and must survive untouched — so this replaces
    exactly the MAPDATA block rather than regenerating the whole file.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fetch_places import render  # noqa: E402

    bases = [{"key": k, "label": k, "hotel": v.get("hotel", {}),
              "pois": v.get("pois", [])} for k, v in data.items()]
    # prof=None so render() emits only MAPDATA and leaves TRIPREGION alone.
    generated = render(bases, "en")
    start_tok = "window.MAPDATA = {"
    block = start_tok + generated.split(start_tok, 1)[1].rstrip()

    i = src.find(start_tok)
    if i == -1:
        sys.exit("✗ could not find 'window.MAPDATA = {' to replace")
    # The block ends at the first line that is exactly "};" — render() and the
    # shipped template both close it that way.
    j = src.find("\n};", i)
    if j == -1:
        sys.exit("✗ could not find the end of the MAPDATA block")
    return src[:i] + block + src[j + 3:]


if __name__ == "__main__":
    main()
