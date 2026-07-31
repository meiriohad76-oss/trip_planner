#!/usr/bin/env python3
"""
build_days.py — precompute "is this open on the day we are going?"

    npm install opening_hours@3.8.0          # build-time only
    python3 scripts/build_days.py maps-data.js 2026-08-05 2026-08-19

Reads maps-data.js, evaluates every POI's opening_hours against every date of
the trip, fetches the destination's public holidays, and writes the result back
into the same file as `window.TRIPDAYS`.

WHY PRECOMPUTE
--------------
Reading the full OSM opening_hours grammar (seasonal ranges, public holidays)
needs opening_hours.js plus suncalc and i18next — roughly 291 KB across three
CDN scripts. This site is meant to work as plain static files on a phone with
one bar in an Alpine valley, and its guardrail is "only Leaflet and fonts from
a CDN". A fifteen-day trip produces a table of a few KB instead, and the page
needs no new JavaScript.

HOLIDAYS: TWO SEPARATE GAPS, BOTH SURFACED
------------------------------------------
1. opening_hours.js has no holiday data for many countries. Verified: Austria
   resolves Nationalfeiertag; Israel and Japan throw. day_status.js catches
   that, drops the PH clause and marks those dates `ph: true`.
2. Nager.Date covers 202 countries but NOT Israel, Thailand, the UAE or India —
   exactly the places running a non-Gregorian holiday calendar. When the country
   is missing, this says so loudly and asks for manual research instead of
   silently reporting no holidays.
"""
import json, subprocess, sys, tempfile, urllib.error, urllib.request
from datetime import date, timedelta
from pathlib import Path

UA = {"User-Agent": "trip-planner/1.0 (https://github.com/meiriohad76-oss/trip_planner)"}
NAGER = "https://date.nager.at/api/v3/PublicHolidays/{year}/{cc}"
ROOT = Path(__file__).resolve().parent


def load_js(path, var):
    """Evaluate maps-data.js in node and return one of its globals."""
    src = Path(path).read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp()) / "d.js"
    tmp.write_text(src + f"\nconsole.log(JSON.stringify(window.{var}||null));",
                   encoding="utf-8")
    r = subprocess.run(["node", "-e", f"global.window={{}};require('{tmp}')"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"✗ {path} is not valid JavaScript:\n{r.stderr[:400]}")
    return json.loads(r.stdout.strip() or "null")


def daterange(a, b):
    d0 = date.fromisoformat(a)
    d1 = date.fromisoformat(b)
    if d1 < d0:
        sys.exit("✗ end date is before start date")
    if (d1 - d0).days > 120:
        sys.exit("✗ more than 120 days — that is not a family holiday, refusing "
                 "to build a table that size")
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def holidays(cc, dates):
    """{date: name} for the trip window, or None when the country is unsupported."""
    if not cc:
        return None
    years = sorted({d[:4] for d in dates})
    found, supported = {}, False
    for y in years:
        try:
            req = urllib.request.Request(NAGER.format(year=y, cc=cc.upper()), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            supported = True
            for h in data:
                if h["date"] in dates:
                    found[h["date"]] = h.get("localName") or h.get("name")
        except urllib.error.HTTPError as e:
            if e.code in (404, 204):
                continue          # country not in Nager.Date
            print(f"  ! holiday lookup for {cc} {y}: HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! holiday lookup for {cc} {y}: {type(e).__name__}")
    return found if supported else None


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    dates = daterange(start, end)

    region = load_js(path, "TRIPREGION") or {}
    data = load_js(path, "MAPDATA") or {}
    cc = (region.get("country") or "").upper()
    if not cc:
        print("  ! no window.TRIPREGION.country — holidays cannot be looked up and "
              "opening_hours cannot resolve public-holiday rules. Set it first.")

    pois, index = [], []
    for bkey, base in data.items():
        for i, p in enumerate(base.get("pois") or []):
            pid = f"{bkey}:{i}"
            index.append(pid)
            if p.get("hours"):
                pois.append({"id": pid, "hours": p["hours"]})

    print(f"  {len(dates)} dates x {len(pois)} POIs with hours "
          f"({len(index) - len(pois)} have none)")

    payload = json.dumps({"country": cc, "dates": dates, "pois": pois})
    r = subprocess.run(["node", str(ROOT / "day_status.js")], input=payload,
                       capture_output=True, text=True, cwd=Path(path).resolve().parent)
    if r.returncode != 0:
        sys.exit("✗ " + (r.stderr.strip() or "day_status.js failed"))
    for line in r.stderr.strip().splitlines():
        if line.startswith("day_status.js:"):
            print("  " + line)
    status = json.loads(r.stdout or "{}")

    hol = holidays(cc, dates)
    if hol is None and cc:
        print(f"  ⚠ Nager.Date has no holiday data for {cc}. Israel, Thailand, the "
              f"UAE and India are all missing, and those are exactly the places "
              f"with a non-Gregorian calendar. RESEARCH THE PUBLIC HOLIDAYS FOR "
              f"THESE DATES BY HAND — the site will not warn about them otherwise.")
    elif hol:
        for d, n in sorted(hol.items()):
            print(f"  · holiday during the trip: {d} {n}")
    elif cc:
        print("  · no public holidays fall inside the trip window")

    ph_blind = sum(1 for v in status.values()
                   for rec in v.values() if rec.get("ph"))
    if ph_blind:
        print(f"  ⚠ {ph_blind} POI-days ignore public holidays (opening_hours.js has "
              f"no PH data for {cc}) — the map flags these as 'holiday: verify'.")

    block = json.dumps({"dates": dates,
                        "holidays": hol if hol is not None else {},
                        "holidays_known": hol is not None,
                        "status": status}, ensure_ascii=False)

    src = Path(path).read_text(encoding="utf-8")
    marker = "window.TRIPDAYS = "
    lines = [ln for ln in src.splitlines() if not ln.startswith(marker)]
    out = "\n".join(lines).rstrip() + "\n\n" + (
        "/* Per-date open/closed, precomputed by scripts/build_days.py so the page\n"
        "   needs no opening_hours.js at runtime. Rebuild if hours or dates change. */\n"
        + marker + block + ";\n")
    Path(path).write_text(out, encoding="utf-8")
    print(f"\nWrote window.TRIPDAYS into {path} "
          f"({len(status)} POIs, {len(dates)} dates, {len(block)//1024} KB).")


if __name__ == "__main__":
    main()
