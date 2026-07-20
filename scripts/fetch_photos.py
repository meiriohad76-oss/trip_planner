#!/usr/bin/env python3
"""
fetch_photos.py — download REAL photos from Wikimedia Commons and write a
credits file. This is the anti-hallucination step: never hand-write an <img src>
pointing at a URL you did not verify returns a real photo of the real place.

Usage:
    python3 fetch_photos.py photos.json img/

photos.json is a list of objects. Two ways to specify each image:

  [
    { "key": "hero",        "file": "Hallstatt - Altstadt.jpg" },
    { "key": "zell-am-see", "search": "Zell am See lake summer" },
    { "key": "familypark",  "search": "Familypark Neusiedlersee", "width": 1600 }
  ]

- "key"    -> output filename img/<key>.jpg AND the credits.json key you reference
             from the HTML (see credits.json written next to the images).
- "file"   -> exact Commons File: title. Most reliable — prefer this once you know it.
- "search" -> full-text Commons search; the top image result is used. Use to
             discover a file, then pin it with "file" for reproducibility.
- "width"  -> longest-edge px for the downloaded rendition (default 1600).

Output:
- img/<key>.jpg for every entry that resolved.
- img/credits.json  { key: {file, author, license, page} }  — REQUIRED for
  attribution. Render these credits in the page footer (CC licenses require it).

Only Commons (freely licensed) images are fetched. Entries that cannot be
resolved are reported and skipped — they are NOT invented. A destination with no
real photo gets a gradient tile in the HTML (see the .banner.grad / .ph classes),
never a fake image.
"""
import json, sys, os, re, time, urllib.parse, urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA  = "vacation-site-builder/1.0 (Claude Code skill; contact via repo owner)"


def _get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def search_file(query):
    """Return the top File: title for a Commons full-text search, or None."""
    d = _get({
        "action": "query", "format": "json", "list": "search",
        "srsearch": query, "srnamespace": 6, "srlimit": 5,
    })
    hits = d.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def _clean(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def file_info(title, width):
    """Return (thumb_url, {author, license, page}) for a File: title, or None."""
    if not title.lower().startswith("file:"):
        title = "File:" + title
    d = _get({
        "action": "query", "format": "json", "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": width,
    })
    pages = d.get("query", {}).get("pages", {})
    for _, page in pages.items():
        ii = page.get("imageinfo")
        if not ii:
            return None
        info = ii[0]
        meta = info.get("extmetadata", {})
        author = _clean(meta.get("Artist", {}).get("value", "")) or "Unknown"
        lic = (meta.get("LicenseShortName", {}).get("value")
               or meta.get("License", {}).get("value") or "see Commons page")
        return info.get("thumburl") or info.get("url"), {
            "file": title.replace("File:", ""),
            "author": author,
            "license": _clean(lic),
            "page": info.get("descriptionurl", ""),
        }
    return None


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    spec = json.load(open(sys.argv[1]))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    credits, missing = {}, []

    for e in spec:
        key = e["key"]
        title = e.get("file")
        try:
            if not title and e.get("search"):
                title = search_file(e["search"])
            if not title:
                missing.append((key, "no file / search miss"))
                continue
            res = file_info(title, e.get("width", 1600))
            if not res:
                missing.append((key, f"no imageinfo for {title}"))
                continue
            url, cred = res
            dest = os.path.join(outdir, f"{key}.jpg")
            download(url, dest)
            credits[key] = cred
            print(f"  ✓ {key:22s} <- {cred['file']}  ({cred['license']})")
            time.sleep(0.4)  # be polite to the API
        except Exception as ex:  # noqa: BLE001
            missing.append((key, str(ex)))

    with open(os.path.join(outdir, "credits.json"), "w") as f:
        json.dump(credits, f, ensure_ascii=False, indent=1)
    print(f"\nWrote {len(credits)} images + credits.json to {outdir}")
    if missing:
        print("\nUNRESOLVED (fix the 'search'/'file' or use a gradient tile — do NOT invent a URL):")
        for k, why in missing:
            print(f"  ✗ {k}: {why}")


if __name__ == "__main__":
    main()
