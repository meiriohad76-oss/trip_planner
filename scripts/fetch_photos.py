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
    { "key": "zell-am-see", "search": "Zell am See lake summer", "must": ["Zell"] },
    { "key": "familypark",  "search": "Familypark Neusiedlersee", "width": 1600 }
  ]

- "key"    -> output filename img/<key>.jpg AND the credits.json key you reference
             from the HTML (see credits.json written next to the images).
- "file"   -> exact Commons File: title. Most reliable — prefer this once you know it.
- "search" -> full-text Commons search; the top *photo* result is used. Use to
             discover a file, then pin it with "file" for reproducibility.
- "must"   -> optional list of words that must appear in the file title. Use the
             place name — it is the cheapest way to stop a search drifting to a
             photogenic neighbour ("Salzburg old town" can otherwise resolve to
             a photo of a scale MODEL of the old town).
- "width"  -> longest-edge px for the downloaded rendition (default 1600).

ALWAYS read the resolved filename this script prints. It guarantees a real,
correctly-typed, properly-attributed photo — it cannot guarantee the photo is
of the thing you meant. If the name looks off, pin the right one with "file".

Output:
- img/<key>.jpg (or .png) for every entry that resolved.
- img/credits.json  { key: {src, file, author, license, page} }  — REQUIRED for
  attribution. Render these credits in the page footer (CC licenses require it).
  Use the "src" field for the <img> filename; it carries the real extension.

Only Commons (freely licensed) RASTER PHOTOS are fetched. Commons namespace 6
also contains SVG logos, coats of arms, maps, PDFs and video — those are
rejected, never renamed to .jpg. Every download is byte-checked for a real
JPEG/PNG magic number before it counts as resolved.

Entries that cannot be resolved are reported and skipped — they are NOT
invented. A destination with no real photo gets a gradient tile in the HTML
(see the .banner.grad / .ph classes), never a fake image.
"""
import json, sys, os, re, time, urllib.parse, urllib.request, urllib.error

API = "https://commons.wikimedia.org/w/api.php"
UA  = "trip-planner/1.0 (Claude Code skill; contact via repo owner)"


_last_call = [0.0]


def _get(params, _retries=3):
    """GET the Commons API, throttled and with backoff on 429/5xx.

    Commons rate-limits anonymous clients; without this a run of 20 photos
    silently loses entries to HTTP 429 and the page ends up with gradient
    tiles where a real photo was available.
    """
    for attempt in range(_retries):
        gap = time.time() - _last_call[0]
        if gap < 0.5:
            time.sleep(0.5 - gap)
        url = API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _last_call[0] = time.time()
                return json.load(r)
        except urllib.error.HTTPError as ex:
            _last_call[0] = time.time()
            if ex.code in (429, 500, 502, 503) and attempt < _retries - 1:
                time.sleep(2 ** attempt * 1.5)
                continue
            raise
    raise RuntimeError("unreachable")


# Only real raster photographs. Commons namespace 6 also holds SVG logos, coats
# of arms, maps, PDFs and video — those are NOT photos of the place and must
# never be written out as <key>.jpg.
PHOTO_MIMES = ("image/jpeg", "image/png")

# Raster *drawings* pass a bitmap/MIME check but are still not photographs of a
# place — a PNG "Flag of Austria" or "Coat of Arms of Tyrol" is exactly the kind
# of plausible-but-wrong image this script exists to prevent.
NOT_A_PHOTO = re.compile(
    r"\b(flag|coat[ _-]?of[ _-]?arms|wappen|logo|seal|emblem|crest|icon|"
    r"map|karte|plan|diagram|chart|graph|schema|drawing|zeichnung|"
    r"poster|banner|sign|blazon|stamp|banknote|coin)\b",
    re.I,
)


def _looks_like_photo(title):
    """Extension is a photo extension AND the title is not obviously a graphic."""
    if title.lower().rsplit(".", 1)[-1] not in ("jpg", "jpeg", "png"):
        return False
    stem = title.split(":", 1)[-1].rsplit(".", 1)[0]
    return not NOT_A_PHOTO.search(stem)


# Real photos of the wrong thing: a museum's scale model, a painting of the
# castle, a postcard reproduction. These pass every type check.
WRONG_SUBJECT = re.compile(
    r"\b(model|modell|maquette|replica|miniature|painting|gemälde|engraving|"
    r"lithograph|postcard|ansichtskarte|reconstruction|panorama ?view of the model)\b",
    re.I,
)


def search_file(query, must=None):
    """Return the top *photo* File: title for a Commons search, or None.

    `filetype:bitmap` filters out SVG/PDF/video at the API level; the title
    checks are a second line of defence, because a bad hit here silently
    produces a wrong image on the site ("Austria flag" -> a coat of arms,
    "Salzburg old town" -> a photo of a tactile *model* of the old town).
    Skipping is always better than downloading the wrong thing.

    `must` is an optional list of words that MUST appear in the file title —
    the cheapest way to keep a search anchored to the actual place.
    """
    d = _get({
        "action": "query", "format": "json", "list": "search",
        "srsearch": query + " filetype:bitmap", "srnamespace": 6, "srlimit": 20,
    })
    hits = [h["title"] for h in d.get("query", {}).get("search", [])]
    cands = [t for t in hits if _looks_like_photo(t)]
    cands = [t for t in cands if not WRONG_SUBJECT.search(t)]
    if must:
        cands = [t for t in cands
                 if all(w.lower() in t.lower() for w in must)]
    # Prefer JPEG: on Commons photographs are overwhelmingly .jpg, while PNG
    # skews towards renders, screenshots and graphics.
    jpegs = [t for t in cands if t.lower().endswith((".jpg", ".jpeg"))]
    return (jpegs or cands or [None])[0]


def _clean(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def file_info(title, width):
    """Return (thumb_url, ext, credits) for a File: title, or (None, reason).

    Rejects anything that is not a raster photo. An explicitly named "file"
    entry gets the same check as a search hit — a hand-typed
    "Coat of arms of Tyrol.svg" is just as wrong as a bad search result.
    """
    if not title.lower().startswith("file:"):
        title = "File:" + title
    d = _get({
        "action": "query", "format": "json", "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|mediatype|extmetadata", "iiurlwidth": width,
    })
    pages = d.get("query", {}).get("pages", {})
    for _, page in pages.items():
        ii = page.get("imageinfo")
        if not ii:
            return None
        info = ii[0]

        # --- reject non-photos ------------------------------------------------
        mime = (info.get("mime") or "").lower()
        mediatype = (info.get("mediatype") or "").upper()
        if mediatype and mediatype != "BITMAP":
            raise ValueError(f"{title} is {mediatype}, not a photo")
        if mime and mime not in PHOTO_MIMES:
            raise ValueError(f"{title} is {mime}, not a photo")
        if not _looks_like_photo(title):
            raise ValueError(f"{title} is not a .jpg/.png photo")
        # ----------------------------------------------------------------------

        ext = ".png" if mime == "image/png" else ".jpg"
        meta = info.get("extmetadata", {})
        author = _clean(meta.get("Artist", {}).get("value", "")) or "Unknown"
        lic = (meta.get("LicenseShortName", {}).get("value")
               or meta.get("License", {}).get("value") or "see Commons page")
        return info.get("thumburl") or info.get("url"), ext, {
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
                title = search_file(e["search"], e.get("must"))
            if not title:
                missing.append((key, "no file / search miss"))
                continue
            res = file_info(title, e.get("width", 1600))
            if not res:
                missing.append((key, f"no imageinfo for {title}"))
                continue
            url, ext, cred = res
            dest = os.path.join(outdir, key + ext)
            download(url, dest)
            # verify we actually got image bytes, not an error page
            with open(dest, "rb") as fh:
                head = fh.read(8)
            if not (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG")):
                os.remove(dest)
                raise ValueError("downloaded bytes are not a JPEG/PNG")
            cred["src"] = os.path.basename(dest)   # what the HTML should reference
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
