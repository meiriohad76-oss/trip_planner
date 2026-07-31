#!/usr/bin/env python3
"""
validate_data.py — check maps-data.js before it ships.

    python3 tests/validate_data.py path/to/maps-data.js

Catches the mistakes that otherwise surface as a blank map on a phone in a car
park: a missing coordinate, a category the template does not know, a
`closed_days` value outside the enum, two POIs at the same spot, an unresolved `review` flag.

Exit codes:
    0  clean, or advisory warnings only
    1  errors — do not deploy
    2  outstanding `review` items (data is real but unfinished)
"""
import json, subprocess, sys, tempfile
from pathlib import Path

# Must match CATS in references/maps.html.
CATEGORIES = {"attraction", "nature", "park", "pool", "animal", "museum",
              "castle", "scenic", "shopping", "restaurant", "supermarket",
              "parking"}
DAY_STATE = {"open", "limited", "closed"}
DAYS = {"Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"}


def load(path):
    """Evaluate maps-data.js in node and hand back plain data."""
    src = Path(path).read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp()) / "d.js"
    tmp.write_text(src + "\nconsole.log(JSON.stringify(window.MAPDATA));",
                   encoding="utf-8")
    r = subprocess.run(["node", "-e", f"global.window={{}};require('{tmp}')"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"✗ {path} is not valid JavaScript:\n{r.stderr[:500]}")
        sys.exit(1)
    return json.loads(r.stdout.strip())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    data = load(sys.argv[1])
    errors, warns, review = [], [], {}
    total = 0

    if not isinstance(data, dict) or not data:
        print("✗ window.MAPDATA is empty")
        sys.exit(1)

    for key, base in data.items():
        where = f"{key}"
        hotel = base.get("hotel") or {}
        for f in ("name", "lat", "lng"):
            if hotel.get(f) is None:
                errors.append(f"{where}.hotel is missing `{f}`")
        if isinstance(hotel.get("lat"), (int, float)) and not -90 <= hotel["lat"] <= 90:
            errors.append(f"{where}.hotel.lat out of range: {hotel['lat']}")

        pois = base.get("pois") or []
        if not pois:
            warns.append(f"{where} has no POIs")
        seen = []
        for i, p in enumerate(pois):
            total += 1
            at = f"{where}.pois[{i}] {p.get('name','(unnamed)')!r}"

            if not p.get("name"):
                errors.append(f"{at}: missing name")
            cat = p.get("category")
            if cat not in CATEGORIES:
                errors.append(f"{at}: category {cat!r} is not one the map knows "
                              f"({', '.join(sorted(CATEGORIES))})")

            for f in ("lat", "lng"):
                v = p.get(f)
                if not isinstance(v, (int, float)):
                    errors.append(f"{at}: {f} is {v!r}, not a number")
            lat, lng = p.get("lat"), p.get("lng")
            if isinstance(lat, (int, float)) and not -90 <= lat <= 90:
                errors.append(f"{at}: lat out of range ({lat})")
            if isinstance(lng, (int, float)) and not -180 <= lng <= 180:
                errors.append(f"{at}: lng out of range ({lng})")
            # A POI thousands of km from its base is almost always swapped lat/lng.
            if all(isinstance(x, (int, float)) for x in (lat, lng, hotel.get("lat"), hotel.get("lng"))):
                if abs(lat - hotel["lat"]) > 3 or abs(lng - hotel["lng"]) > 3:
                    warns.append(f"{at}: >3° from its base — swapped lat/lng?")

            cd = p.get("closed_days")
            if cd is not None:
                if not isinstance(cd, dict):
                    errors.append(f"{at}: closed_days must be an object like "
                                  f'{{"Sa": "closed"}}, got {cd!r}')
                else:
                    for day, st in cd.items():
                        if day not in DAYS:
                            errors.append(f"{at}: closed_days key {day!r} is not a "
                                          f"weekday code {sorted(DAYS)}")
                        if st not in DAY_STATE:
                            errors.append(f"{at}: closed_days[{day!r}]={st!r}, "
                                          f"expected one of {sorted(DAY_STATE)}")
            if cat == "supermarket" and cd is None and "closed_days" not in (p.get("review") or []):
                warns.append(f"{at}: supermarket with no closed_days and no review flag "
                             f"(fine if this country trades seven days)")

            dm = p.get("drive_min")
            if dm is not None and not isinstance(dm, (int, float)):
                errors.append(f"{at}: drive_min={dm!r} is not a number")

            # Only meaningful once we know both are numbers — a string coord is
            # already an error above, and comparing it here would crash.
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                for olat, olng, oname in seen:
                    if abs(olat - lat) < 0.0004 and abs(olng - lng) < 0.0006:
                        warns.append(f"{at}: within ~50 m of {oname!r} — duplicate?")
                        break
                seen.append((lat, lng, p.get("name")))

            for r in (p.get("review") or []):
                review[r] = review.get(r, 0) + 1

    print(f"Checked {total} POIs across {len(data)} bases.\n")
    for w in warns:
        print("  ⚠ " + w)
    for e in errors:
        print("  ✗ " + e)

    if review:
        print("\nOutstanding review items (fetched data is real but unfinished):")
        for k, v in sorted(review.items(), key=lambda x: -x[1]):
            print(f"  · {k:14s} {v} POIs")
        print("\nResolve these, remove them from each POI's `review` array, then "
              "re-run. Do not ship with `hours` or `closed_days` outstanding.")

    if errors:
        print(f"\n{len(errors)} error(s) — do not deploy.")
        sys.exit(1)
    if review:
        print(f"\nNo errors, but {sum(review.values())} review items remain.")
        sys.exit(2)
    print("\nAll checks passed — data is clean.")


if __name__ == "__main__":
    main()
