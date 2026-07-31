#!/usr/bin/env python3
"""Render maps.html headlessly and assert the fixes actually hold in a browser."""
import json, shutil, sys, tempfile, os, re
from pathlib import Path
from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent.parent / "references"

# Deliberately hostile data: a string lat, an out-of-range lat, a missing lng,
# a quote-injection name, and a non-numeric drive_min.
DATA = """
window.MAPDATA = {
  base1: {
    hotel: { name: "Test Base", lat: 47.3230, lng: 13.1330 },
    pois: [
      { name:"Good Attraction", category:"attraction", lat:47.3250, lng:13.1360, drive_min:5, pass:true,
        desc:"A real one.", hours:"09:00-18:00" },
      { name:"String Coords", category:"museum", lat:"47.3300", lng:"13.1400", drive_min:7,
        desc:"Coords as strings." },
      { name:"Bad Lat", category:"nature", lat:999, lng:13.14, drive_min:3 },
      { name:"Missing Lng", category:"pool", lat:47.33, drive_min:4 },
      { name:"Evil <img src=x onerror=alert(1)> \\" Name", category:"restaurant", lat:47.326, lng:13.137, drive_min:2 },
      { name:"NaN Drive", category:"supermarket", lat:47.327, lng:13.138, drive_min:"soon", closed_days:{Su:"closed"} }
    ],
  },
  base2: {
    hotel: { name: "Second Base", lat: 47.4600, lng: 12.9100 },
    pois: [
      { name:"Wildlife Park", category:"animal", lat:47.4720, lng:12.9450, drive_min:14, pass:true, desc:"Animals." }
    ],
  },
};
"""

def main():
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(SRC / "maps.html", tmp / "maps.html")
    (tmp / "maps-data.js").write_text(DATA, encoding="utf-8")

    fails, notes = [], []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        errors, warnings = [], []
        pg.on("console", lambda m: (errors if m.type == "error" else warnings).append(m.text))
        pg.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        pg.goto((tmp / "maps.html").as_uri())
        pg.wait_for_timeout(2500)

        # --- no uncaught JS errors (tile 404s are fine, they're network) ---
        real = [e for e in errors if "ERR_" not in e and "tile" not in e.lower()]
        if real:
            fails.append(f"JS errors: {real}")

        # --- bad coords skipped, good ones kept ---
        n1 = pg.eval_on_selector_all("#list-1 .lc", "els=>els.length")
        if n1 != 4:
            fails.append(f"expected 4 valid POIs in base1 (2 dropped), got {n1}")
        skipped = [w for w in warnings if "skipped for invalid lat/lng" in w]
        if not skipped:
            fails.append("no console.warn for skipped POIs")
        else:
            notes.append(f"warned: {skipped[0][:90]}")

        # --- second map still built ---
        if pg.eval_on_selector_all("#list-2 .lc", "els=>els.length") != 1:
            fails.append("base2 map did not build")

        # --- string coords survive and produce a valid nav link ---
        hrefs = pg.eval_on_selector_all("#list-1 a.waze", "els=>els.map(e=>e.href)")
        for h in hrefs:
            m = re.search(r"ll=([-\d.]+)%2C([-\d.]+)", h) or re.search(r"ll=([-\d.]+),([-\d.]+)", h)
            if not m:
                fails.append(f"malformed waze href: {h}")
            else:
                la, ln = float(m.group(1)), float(m.group(2))
                if not (-90 <= la <= 90 and -180 <= ln <= 180):
                    fails.append(f"out-of-range coords in href: {h}")
        notes.append(f"{len(hrefs)} nav links, all well-formed")

        # --- XSS: the evil name must be text, not markup ---
        if pg.eval_on_selector_all("#list-1 img", "els=>els.length"):
            fails.append("XSS: injected <img> rendered in list")
        evil = pg.eval_on_selector_all("#list-1 .lc h4", "els=>els.map(e=>e.textContent)")
        if not any("onerror" in t for t in evil):
            notes.append("evil name not present (check)")
        else:
            notes.append("evil name rendered as inert text")

        # --- NaN drive_min degrades to a dash, not "NaN", in the meta line ---
        metas = pg.eval_on_selector_all("#list-1 .lc .cat", "els=>els.map(e=>e.textContent)")
        bad_meta = [m for m in metas if "NaN" in m or "undefined" in m]
        if bad_meta:
            fails.append(f"NaN/undefined leaked into meta line: {bad_meta}")
        if not any("—" in m for m in metas):
            fails.append(f"non-numeric drive_min did not degrade to a dash: {metas}")
        notes.append("non-numeric drive_min degrades to '—'")

        # --- ARIA ---
        aria = pg.evaluate("""()=>({
          listRole: document.getElementById('list-1').getAttribute('role'),
          listLabel: !!document.getElementById('list-1').getAttribute('aria-label'),
          live: document.getElementById('count-1').getAttribute('aria-live'),
          mapLabel: !!document.getElementById('map1').getAttribute('aria-label'),
          pressed: [...document.querySelectorAll('#ctrl-1 .fb')].map(b=>b.getAttribute('aria-pressed')),
          searchLabel: !!document.querySelector('#ctrl-1 [data-role=search]').getAttribute('aria-label'),
          sortLabelled: !!document.querySelector('label[for="ctrl-1-sort"]'),
          items: [...document.querySelectorAll('#list-1 .lc')].map(e=>e.getAttribute('role')),
          focusable: [...document.querySelectorAll('#list-1 .lc')].every(e=>e.tabIndex===0),
          total: document.querySelectorAll('[aria-label],[aria-pressed],[aria-live],[role]').length
        })""")
        if aria["listRole"] != "list": fails.append("list role missing")
        if not aria["listLabel"]: fails.append("list aria-label missing")
        if aria["live"] != "polite": fails.append("count aria-live missing")
        if not aria["mapLabel"]: fails.append("map aria-label missing")
        if not all(p in ("true", "false") for p in aria["pressed"]): fails.append("filter aria-pressed missing")
        if not aria["searchLabel"]: fails.append("search aria-label missing")
        if not aria["sortLabelled"]: fails.append("sort <label for> missing")
        if not all(r == "listitem" for r in aria["items"]): fails.append("listitem roles missing")
        if not aria["focusable"]: fails.append("cards not keyboard focusable")
        notes.append(f"{aria['total']} aria/role attributes present")

        # --- filter toggles flip aria-pressed and change the count ---
        before = pg.inner_text("#count-1")
        pg.click('#ctrl-1 .fb[data-cat="attraction"]')
        pg.wait_for_timeout(300)
        after = pg.inner_text("#count-1")
        press = pg.get_attribute('#ctrl-1 .fb[data-cat="attraction"]', "aria-pressed")
        if before == after: fails.append("filter click did not change count")
        if press != "false": fails.append(f"aria-pressed not updated on toggle (got {press})")
        pg.click('#ctrl-1 .fb[data-cat="attraction"]')
        pg.wait_for_timeout(200)

        # --- search works ---
        pg.fill("#ctrl-1-q", "wildlife")
        pg.wait_for_timeout(300)
        if pg.eval_on_selector_all("#list-1 .lc", "e=>e.length") != 0:
            fails.append("search did not filter base1")
        pg.fill("#ctrl-1-q", "good")
        pg.wait_for_timeout(300)
        if pg.eval_on_selector_all("#list-1 .lc", "e=>e.length") != 1:
            fails.append("search did not match 'good'")
        pg.fill("#ctrl-1-q", "")
        pg.wait_for_timeout(200)

        # --- keyboard activation ---
        pg.focus("#list-1 .lc")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(400)
        if not pg.eval_on_selector_all("#list-1 .lc.active", "e=>e.length"):
            fails.append("Enter key did not activate a card")

        # --- markers on the map ---
        pins = pg.eval_on_selector_all("#map1 .pinwrap", "e=>e.length")
        if pins < 4:
            fails.append(f"expected >=4 markers (4 POIs + hotel), got {pins}")
        notes.append(f"{pins} markers rendered on map1")

        # --- no horizontal scroll at phone width ---
        pg.set_viewport_size({"width": 390, "height": 800})
        pg.wait_for_timeout(600)
        ov = pg.evaluate("()=>document.documentElement.scrollWidth-document.documentElement.clientWidth")
        if ov > 2:
            fails.append(f"horizontal overflow at 390px: {ov}px")

        b.close()

    print("\n".join("  · " + n for n in notes))
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print("  ✗ " + f)
        sys.exit(1)
    print("\nALL CHECKS PASSED")

main()
