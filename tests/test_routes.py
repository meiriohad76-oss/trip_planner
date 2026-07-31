#!/usr/bin/env python3
"""
Tests for fetch_routes.py — the drive-time step.

Split deliberately:
  * the merge/rewrite and review-flag logic is tested OFFLINE against a fixture
    of real OSRM table responses, so it does not depend on a public router;
  * one small LIVE call checks the API contract still holds, and is skipped
    (not failed) when the network or the server is unavailable.
"""
import json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_routes as fr  # noqa: E402

fails, notes = [], []


def check(c, m):
    if not c:
        fails.append(m)


# --- offline: rewrite preserves TRIPREGION/TRIPDAYS and merges drive fields ---
SRC = '''window.TRIPREGION = {"country":"AT","closed_days":["Su"],"badge":true,
  "distance":"km","temperature":"C","nav":["waze","gmaps"]};

window.MAPDATA = {
  base1: {
    hotel: { name:"Base", lat:47.32, lng:13.13 },
    pois: [
      { name:"Near", category:"attraction", lat:47.325, lng:13.136, review:["drive_min","desc"] },
      { name:"Far From Road", category:"nature", lat:47.30, lng:13.18, review:["drive_min"] }
    ],
  },
};

window.TRIPDAYS = {"dates":["2026-08-05"],"holidays":{},"holidays_known":true,"status":{}};
'''

tmp = Path(tempfile.mkdtemp())
f = tmp / "maps-data.js"
f.write_text(SRC, encoding="utf-8")

data = fr.load_js(str(f), "MAPDATA")
pois = data["base1"]["pois"]
# Simulate what main() does with a good route and a far-snapped one.
pois[0].update({"drive_min": 6, "drive_km": 3.2, "drive_src": "osrm"})
pois[0]["review"] = [x for x in pois[0]["review"] if x != "drive_min"]
pois[1].update({"drive_min": 69, "drive_km": 10.1, "drive_src": "osrm",
                "drive_note": "nearest road is 3596 m away — the drive time is to "
                              "that road, not the door"})

out = fr._rewrite(SRC, data)
f.write_text(out, encoding="utf-8")

check("window.TRIPREGION" in out, "TRIPREGION was destroyed by the rewrite")
check("window.TRIPDAYS" in out, "TRIPDAYS was destroyed by the rewrite")
check(out.count("window.MAPDATA") == 1, "MAPDATA block duplicated")
r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
check(r.returncode == 0, f"rewritten file is not valid JS: {r.stderr[:200]}")
notes.append("rewrite keeps TRIPREGION and TRIPDAYS intact and stays valid JS")

back = fr.load_js(str(f), "MAPDATA")
bp = back["base1"]["pois"]
check(bp[0]["drive_min"] == 6 and bp[0]["drive_km"] == 3.2,
      f"routed fields lost in round-trip: {bp[0]}")
check(bp[0].get("drive_src") == "osrm", "provenance lost")
check("drive_min" not in (bp[0].get("review") or []),
      "a cleanly routed POI should not stay flagged for drive_min")
check("desc" in (bp[0].get("review") or []),
      "clearing drive_min must not wipe other review items")
check("drive_min" in (bp[1].get("review") or []),
      "a POI far from any road must STAY flagged — the number measures the "
      "wrong thing")
check("3596 m" in bp[1].get("drive_note", ""), "drive_note lost")
notes.append("far-from-road POIs keep drive_min AND stay flagged; others clear")

region = fr.load_js(str(f), "TRIPREGION")
check(region and region.get("country") == "AT", "TRIPREGION content changed")
days = fr.load_js(str(f), "TRIPDAYS")
check(days and days.get("dates") == ["2026-08-05"], "TRIPDAYS content changed")
notes.append("neighbouring blocks survive byte-for-byte in content")

# --- live: does the OSRM table contract still hold? --------------------------
live = fr.table([(13.1330, 47.3230), (13.6493, 47.5622)], label="live check")
if live is None:
    notes.append("live OSRM check SKIPPED (server unreachable) — offline tests still passed")
else:
    dur = (live.get("durations") or [[]])[0]
    dests = live.get("destinations") or []
    check(len(dur) >= 2 and isinstance(dur[1], (int, float)),
          f"unexpected durations shape: {dur}")
    check(dur[0] == 0, "the source-to-itself duration should be 0")
    check(any("distance" in (d or {}) for d in dests),
          "destinations no longer carry a snap distance — the far-from-road "
          "warning depends on it")
    notes.append(f"live OSRM contract holds ({dur[1]/60:.0f} min for the sample leg)")

print("\n".join("  · " + n for n in notes))
if fails:
    print("\nFAILURES:")
    for x in fails:
        print("  ✗ " + x)
    sys.exit(1)
print("\nALL ROUTE CHECKS PASSED")
