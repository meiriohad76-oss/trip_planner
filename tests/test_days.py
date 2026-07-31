#!/usr/bin/env python3
"""
End-to-end test for the per-date open/closed feature.

Runs the real build (build_days.py -> day_status.js -> opening_hours.js), then
renders the result in a browser and asserts the badges say the right thing on
the right day. Requires `npm install opening_hours@3.8.0` and network access for
the holiday lookup.
"""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "references"

# 2026-08-15 is a Saturday AND Austria's Mariä Himmelfahrt.
# 2026-08-17 is an ordinary Monday.
DATA = """
window.TRIPREGION = {"country":"AT","closed_days":["Su"],"short_days":[],"badge":true,
                     "distance":"km","temperature":"C","nav":["waze","gmaps"]};
window.MAPDATA = {
  base1: {
    hotel: { name:"Base", lat:47.3230, lng:13.1330 },
    pois: [
      { name:"Weekday Shop", category:"supermarket", lat:47.3250, lng:13.1360, drive_min:5,
        hours:"Mo-Fr 08:00-18:00; Sa 08:00-12:00; Su off" },
      { name:"Summer Gorge", category:"attraction", lat:47.3190, lng:13.1290, drive_min:4,
        hours:"May 1-Sep 30: 09:00-17:00" },
      { name:"Winter Only", category:"attraction", lat:47.3195, lng:13.1295, drive_min:6,
        hours:"Nov 1-Mar 31: 10:00-16:00" },
      { name:"Holiday Closer", category:"museum", lat:47.3260, lng:13.1370, drive_min:8,
        hours:"Mo-Su 10:00-17:00; PH off" },
      { name:"Prose Hours", category:"restaurant", lat:47.3270, lng:13.1380, drive_min:3,
        hours:"open-ish most afternoons" },
      { name:"No Hours At All", category:"nature", lat:47.3280, lng:13.1390, drive_min:9 }
    ]
  }
};
"""

fails, notes = [], []


def check(c, m):
    if not c:
        fails.append(m)


tmp = Path(tempfile.mkdtemp())
shutil.copy(SRC / "maps.html", tmp / "maps.html")
(tmp / "maps-data.js").write_text(DATA, encoding="utf-8")

# opening_hours must be resolvable from the build directory
nm = os.environ.get("TRIP_NODE_MODULES")
if nm and Path(nm).exists():
    try:
        os.symlink(nm, tmp / "node_modules")
    except OSError:
        pass

r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_days.py"),
                    str(tmp / "maps-data.js"), "2026-08-15", "2026-08-17"],
                   capture_output=True, text=True, cwd=tmp)
print(r.stdout.strip())
if r.returncode != 0:
    print("build_days.py failed:\n" + (r.stderr or "")[:600])
    sys.exit(1)

built = (tmp / "maps-data.js").read_text(encoding="utf-8")
check("window.TRIPDAYS" in built, "TRIPDAYS was not written into maps-data.js")
m = re.search(r"window\.TRIPDAYS = (\{.*?\});\s*$", built, re.S)
check(bool(m), "could not parse the TRIPDAYS block")
days = json.loads(m.group(1)) if m else {}

# --- data-level assertions ---------------------------------------------------
st = days.get("status", {})
check(days.get("dates") == ["2026-08-15", "2026-08-16", "2026-08-17"],
      f"unexpected date list: {days.get('dates')}")
check(days.get("holidays", {}).get("2026-08-15"),
      "Mariä Himmelfahrt (15 Aug) not detected as an Austrian holiday")
check(st.get("base1:0", {}).get("2026-08-16", {}).get("s") == "closed",
      "Sunday 16 Aug should be closed for a 'Su off' shop")
check(st.get("base1:0", {}).get("2026-08-17", {}).get("s") == "open",
      "Monday 17 Aug should be open for a Mo-Fr shop")
check(st.get("base1:1", {}).get("2026-08-17", {}).get("s") == "open",
      "the summer-season gorge should be open in August")
check(st.get("base1:2", {}).get("2026-08-17", {}).get("s") == "closed",
      "the winter-only attraction should be closed in August")
check(st.get("base1:3", {}).get("2026-08-15", {}).get("s") == "closed",
      "'PH off' museum should be closed on Mariä Himmelfahrt")
check(st.get("base1:3", {}).get("2026-08-17", {}).get("s") == "open",
      "'PH off' museum should be open on an ordinary Monday")
check("base1:4" not in st, "prose hours must NOT be given a fabricated status")
check("base1:5" not in st, "a POI with no hours must not appear in the table")
notes.append("seasonal, weekday, Sunday and public-holiday cases all correct")
notes.append("unparseable prose and missing hours produce no entry, not a guess")

# --- browser-level assertions ------------------------------------------------
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((tmp / "maps.html").as_uri())
    pg.wait_for_timeout(1800)
    check(not errs, f"JS errors: {errs}")

    txt = pg.inner_text("#list-1")
    # Assert on the banner container, NOT the section: the day-picker <option>
    # for 15 Aug is legitimately labelled "... — Maria Himmelfahrt", so the
    # holiday name is present in the section on every date.
    banner = pg.inner_text("#ctrl-1-hol")
    check("Himmelfahrt" in banner,
          f"holiday banner not shown for the selected date (banner={banner!r})")
    check("Closed" in txt, "no closed badge on the holiday/Saturday view")
    check("hours not evaluated" in txt, "prose-hours POI should say hours not evaluated")
    notes.append("holiday banner and 'hours not evaluated' render")

    # switch to Monday 17 Aug and re-check
    pg.select_option("#ctrl-1-day", "2026-08-17")
    pg.wait_for_timeout(600)
    txt2 = pg.inner_text("#list-1")
    check("Open" in txt2, "nothing open on an ordinary Monday?")
    check("08:00-18:00" in txt2, "opening interval not shown for the weekday shop")
    check("Himmelfahrt" not in pg.inner_text("#ctrl-1-hol"),
          "holiday banner still shown after switching to a non-holiday day")
    notes.append("day picker re-renders: Monday shows open + intervals, banner clears")

    # the winter-only attraction must stay closed on both dates
    cards = pg.eval_on_selector_all(
        "#list-1 .lc", "els=>els.map(e=>e.textContent)")
    winter = [c for c in cards if "Winter Only" in c]
    check(winter and "Closed" in winter[0],
          "winter-only attraction should be closed in August")
    notes.append("out-of-season attraction correctly closed in August")
    b.close()

print("\n".join("  · " + n for n in notes))
if fails:
    print("\nFAILURES:")
    for f in fails:
        print("  ✗ " + f)
    sys.exit(1)
print("\nALL DAY-STATUS CHECKS PASSED")
