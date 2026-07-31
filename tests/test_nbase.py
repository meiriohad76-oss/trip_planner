#!/usr/bin/env python3
"""Prove the maps template handles N bases and shouts on mismatch."""
import re, shutil, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent.parent / "references"
HTML = (SRC / "maps.html").read_text(encoding="utf-8")

def base(n, lat, lng):
    return f'''base{n}: {{ hotel:{{name:"Base {n}",lat:{lat},lng:{lng}}},
      pois:[{{name:"POI {n}A",category:"attraction",lat:{lat+0.01},lng:{lng+0.01},drive_min:5}},
            {{name:"POI {n}B",category:"restaurant",lat:{lat+0.02},lng:{lng+0.02},drive_min:8}}] }},'''

def section(n):
    return f'''<section id="sec-{n}"><div class="wrap">
  <div class="sec-head"><h2>Base {n}</h2></div>
  <div class="controls" id="ctrl-{n}"></div>
  <div class="maparea"><div class="mapbox"><div id="map{n}" class="lmap"></div></div>
  <div><div class="listcount" id="count-{n}"></div><div class="listbox" id="list-{n}"></div></div></div>
  <div class="legend" id="legend-{n}"></div>
</div></section>'''

def build_page(n_sections, n_data):
    """Replace the two sample sections with n_sections, and data with n_data bases."""
    start = HTML.index('<section id="sec-1">')
    end = HTML.index("<footer>")
    page = HTML[:start] + "\n".join(section(i) for i in range(1, n_sections + 1)) + "\n\n" + HTML[end:]
    data = "window.MAPDATA = {\n" + "\n".join(
        base(i, 47.0 + i * 0.5, 13.0 + i * 0.5) for i in range(1, n_data + 1)) + "\n};"
    return page, data

def run(pw, n_sections, n_data):
    tmp = Path(tempfile.mkdtemp())
    page, data = build_page(n_sections, n_data)
    (tmp / "maps.html").write_text(page, encoding="utf-8")
    (tmp / "maps-data.js").write_text(data, encoding="utf-8")
    b = pw.chromium.launch(); pg = b.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)))
    pg.goto((tmp / "maps.html").as_uri()); pg.wait_for_timeout(1800)
    built = pg.evaluate("()=>[...document.querySelectorAll('.listbox')].filter(e=>e.children.length).length")
    b.close()
    return built, [e for e in errs if "ERR_" not in e]

fails = []
with sync_playwright() as pw:
    # 5 bases, 5 sections -> all build, no errors
    built, errs = run(pw, 5, 5)
    print(f"  · 5 bases / 5 sections -> {built} maps built, {len(errs)} errors")
    if built != 5: fails.append(f"5-base trip built only {built} maps")
    if errs: fails.append(f"5-base trip logged errors: {errs}")

    # 3 bases of data but only 2 sections -> builds 2, shouts about the third
    built, errs = run(pw, 2, 3)
    print(f"  · 3 bases / 2 sections -> {built} maps built, {len(errs)} errors")
    if built != 2: fails.append(f"expected 2 maps, got {built}")
    if not any("no matching HTML section" in e for e in errs):
        fails.append(f"no error about the missing section: {errs}")

    # 2 bases of data but 3 sections -> shouts about the orphan section
    built, errs = run(pw, 3, 2)
    print(f"  · 2 bases / 3 sections -> {built} maps built, {len(errs)} errors")
    if built != 2: fails.append(f"expected 2 maps, got {built}")
    if not any("no matching key" in e for e in errs):
        fails.append(f"no error about the orphan section: {errs}")

    # empty data -> one clear error, no crash
    built, errs = run(pw, 2, 0)
    print(f"  · 0 bases / 2 sections -> {built} maps built, {len(errs)} errors")
    if not any("MAPDATA is empty" in e for e in errs):
        fails.append(f"no error for empty MAPDATA: {errs}")

if fails:
    print("\nFAILURES:")
    [print("  ✗ " + f) for f in fails]
    sys.exit(1)
print("\nALL N-BASE CHECKS PASSED")
