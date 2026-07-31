#!/usr/bin/env python3
"""
Render maps.html under several country profiles and assert the region-specific
behaviour is right — not just "Austria still works".

The failure this guards against is subtle and confident: a badge that says
"Closed Sundays" in Tel Aviv, where Sunday is a normal working day and Saturday
is the day everything shuts.
"""
import json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from playwright.sync_api import sync_playwright  # noqa: E402
from regions import profile  # noqa: E402

SRC = ROOT / "references"

POIS = """[
 {name:"Market", category:"supermarket", lat:LAT2, lng:LNG2, drive_min:5, HOURS},
 {name:"Museum", category:"museum", lat:LAT3, lng:LNG3, drive_min:12}
]"""


def page(country, lat, lng, closed_days):
    prof = profile(country)
    region = {
        "country": country,
        "closed_days": prof["closed_days"], "short_days": prof["short_days"],
        "badge": prof["badge"], "distance": prof["distance"],
        "temperature": prof["temperature"], "nav": prof["nav"],
    }
    pois = (POIS.replace("LAT2", str(lat + 0.01)).replace("LNG2", str(lng + 0.01))
                .replace("LAT3", str(lat + 0.02)).replace("LNG3", str(lng + 0.02))
                .replace("HOURS", "closed_days:" + json.dumps(closed_days)
                         if closed_days else "hours:\"09:00-22:00\""))
    return (f"window.TRIPREGION = {json.dumps(region)};\n"
            f"window.MAPDATA = {{ base1: {{ hotel:{{name:\"Base\",lat:{lat},lng:{lng}}},"
            f" pois: {pois} }} }};")


CASES = [
    # country, coords,          closed_days on the POI,   expect in badge,  must NOT appear
    ("AT", (47.32, 13.13), {"Su": "closed"}, ["Closed Sundays"], ["Saturdays"]),
    ("IL", (32.07, 34.77), {"Sa": "closed", "Fr": "limited"},
     ["Closed Saturdays", "Fri — short hours"], ["Closed Sundays"]),
    ("SA", (24.71, 46.67), {"Fr": "closed"}, ["Closed Fridays"], ["Closed Sundays"]),
    ("JP", (35.68, 139.70), None, [], ["Closed Sundays", "Closed Saturdays"]),
    ("US", (28.53, -81.37), None, [], ["Closed Sundays"]),
]

fails, notes = [], []

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for country, (lat, lng), cd, want, forbid in CASES:
        tmp = Path(tempfile.mkdtemp())
        shutil.copy(SRC / "maps.html", tmp / "maps.html")
        (tmp / "maps-data.js").write_text(page(country, lat, lng, cd), encoding="utf-8")
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto((tmp / "maps.html").as_uri())
        pg.wait_for_timeout(1500)
        txt = pg.inner_text("#list-1")
        hrefs = pg.eval_on_selector_all("#list-1 a", "e=>e.map(x=>x.href)")
        labels = pg.eval_on_selector_all("#list-1 a", "e=>e.map(x=>x.textContent.trim())")

        if errs:
            fails.append(f"{country}: JS errors {errs}")
        for w in want:
            if w not in txt:
                fails.append(f"{country}: expected {w!r} in the card, not found")
        for f in forbid:
            if f in txt:
                fails.append(f"{country}: {f!r} must NOT appear")

        prof = profile(country)
        # Units. Match the actual distance format "~12.3 km" — a bare " mi"
        # substring also matches " min", which is a different field entirely.
        unit = "mi" if prof["distance"] == "mi" else "km"
        wrong = "km" if unit == "mi" else "mi"
        if not re.search(rf"~[\d.]+ {unit}\b", txt):
            fails.append(f"{country}: no '~N {unit}' distance found")
        if re.search(rf"~[\d.]+ {wrong}\b", txt):
            fails.append(f"{country}: distances shown in {wrong}, expected {unit}")

        # nav apps that actually work here
        if "waze" in prof["nav"] and not any("waze.com" in h for h in hrefs):
            fails.append(f"{country}: expected a Waze link")
        if "waze" not in prof["nav"] and any("waze.com" in h for h in hrefs):
            fails.append(f"{country}: Waze link present but Waze does not operate there")
        if "naver" in prof["nav"] and not any("naver.com" in h for h in hrefs):
            fails.append(f"{country}: expected a Naver link")
        if "gmaps" not in prof["nav"] and any("google.com/maps" in h for h in hrefs):
            fails.append(f"{country}: Google Maps link present but it is unusable there")

        notes.append(f"{country}: badge={'on' if prof['badge'] else 'off'} "
                     f"units={unit} nav={'+'.join(prof['nav'])} "
                     f"({len(set(labels))} distinct buttons)")
        pg.close()

    # Korea specifically: no Google, yes Naver
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(SRC / "maps.html", tmp / "maps.html")
    (tmp / "maps-data.js").write_text(page("KR", 37.56, 126.97, None), encoding="utf-8")
    pg = b.new_page()
    pg.goto((tmp / "maps.html").as_uri())
    pg.wait_for_timeout(1500)
    hrefs = pg.eval_on_selector_all("#list-1 a", "e=>e.map(x=>x.href)")
    if any("google.com/maps" in h for h in hrefs):
        fails.append("KR: Google Maps link rendered (no driving directions in Korea)")
    if not any("naver.com" in h for h in hrefs):
        fails.append("KR: no Naver link")
    notes.append("KR: Google Maps suppressed, Naver used instead")
    pg.close()
    b.close()

print("\n".join("  · " + n for n in notes))
if fails:
    print("\nFAILURES:")
    for f in fails:
        print("  ✗ " + f)
    sys.exit(1)
print("\nALL REGION CHECKS PASSED")
