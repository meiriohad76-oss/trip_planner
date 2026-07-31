#!/usr/bin/env python3
"""
regions.py — the things that change when the trip is not in Central Europe.

This skill grew up around an Austrian family trip, and several assumptions from
that trip leaked into the schema and the map. They are wrong almost everywhere
else:

  * "supermarkets close on Sunday" is a DACH rule. Israel closes SATURDAY and
    trades normally on Sunday. Much of the Gulf shuts Friday morning. Japan,
    the United States and most of Asia close nothing, so the badge is noise.
  * kilometres and °C are not universal.
  * Waze does not operate in Japan; Google Maps is deliberately crippled in
    mainland China and South Korea. A nav button that opens a blank map is
    worse than no button.

Each profile records only what changes behaviour, and every non-obvious entry
carries a `note` so a reader can check it rather than trust it.

    from regions import profile
    p = profile("IL")
    p["closed_days"]   -> ["Sa"]           days shops/attractions commonly shut
    p["short_days"]    -> ["Fr"]           days that commonly close early
    p["badge"]         -> True             is a closed-day badge informative?
    p["distance"]      -> "km"
    p["temperature"]   -> "C"
    p["nav"]           -> ["waze", "gmaps"]

Unknown country codes fall back to a neutral profile with the badge OFF, which
is the safe default: showing no badge is a small loss, showing a confidently
wrong one is the failure this skill exists to prevent.
"""

# Weekday codes match osm_hours.DAYS: Mo Tu We Th Fr Sa Su
_DEFAULT = {
    "closed_days": [], "short_days": [], "badge": False,
    "distance": "km", "temperature": "C", "nav": ["waze", "gmaps"],
    "note": "No closed-day rule recorded — badge suppressed rather than guessed.",
}

# Sunday-closing countries. In DACH this is statutory (Ladenschlussgesetz and
# equivalents) and is the single most useful thing the map can tell a family.
_SUNDAY_CLOSED = {
    "AT": "Shops shut Sundays and public holidays by law; petrol stations and "
          "station shops are the usual exceptions.",
    "DE": "Ladenschlussgesetz — shops shut Sundays; Bahnhof and airport shops open.",
    "CH": "Shops shut Sundays outside stations and airports.",
    "NO": "Only small shops (<100 m²) may open Sundays.",
    "PL": "Sunday trading ban on most Sundays, with a few trading Sundays a year.",
    "HU": None, "SK": None, "HR": None, "LI": None, "LU": None,
    "BE": None, "NL": None, "DK": None, "IS": None, "SI": None,
    "GR": None, "IT": None, "ES": None, "PT": None, "FR": None,
    "CZ": "Larger shops shut on several public holidays; Sundays mostly open.",
}

# Friday/Saturday rest countries. The exact pattern differs and the difference
# matters on the ground, so each carries a note.
_FRI_SAT = {
    "IL": {"closed_days": ["Sa"], "short_days": ["Fr"],
           "note": "Shabbat: most shops shut Friday afternoon until Saturday "
                   "night. Sunday is a normal working day. Jerusalem is stricter "
                   "than Tel Aviv, where some venues stay open."},
    "SA": {"closed_days": ["Fr"], "short_days": [],
           "note": "Friday is the rest day; many shops also close briefly at "
                   "each prayer time."},
    "KW": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "QA": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "BH": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "OM": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "JO": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "EG": {"closed_days": ["Fr"], "short_days": [],
           "note": "Friday rest day; many shops reopen after afternoon prayers."},
    "AE": {"closed_days": [], "short_days": ["Fr"],
           "note": "The UAE moved to a Sat-Sun weekend in January 2022 with a "
                   "half-day Friday. Malls trade all week; Friday mornings are "
                   "quieter. Do not assume the old Fri-Sat pattern."},
    "MV": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "AF": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "IR": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
    "BD": {"closed_days": ["Fr"], "short_days": [], "note": "Friday rest day."},
}

# Countries with a partial Sunday restriction — open, but not normally.
_SHORT_SUNDAY = {
    "GB": "Sunday Trading Act: shops over 280 m² in England and Wales may open "
          "for only six hours on a Sunday (usually 10:00-16:00 or 11:00-17:00). "
          "Scotland is unrestricted.",
}

# Open-seven-days countries: the badge would be pure noise, so it is off.
_ALWAYS_OPEN = ["JP", "US", "CA", "AU", "NZ", "KR", "CN", "TW", "HK", "SG",
                "TH", "VN", "MY", "ID", "PH", "IN", "MX", "BR", "AR", "CL",
                "IE", "SE", "FI", "EE", "LV", "LT", "TR", "ZA", "MA",
                "PE", "CO", "CR", "UY", "RO", "BG", "RS", "UA", "GE", "AL"]

# Distance units. Only a handful of places use miles day to day.
_MILES = {"US", "GB", "LR", "MM"}
_FAHRENHEIT = {"US", "BS", "BZ", "KY", "PW", "FM", "MH"}

# Navigation apps that actually work in-country.
_NAV = {
    "JP": (["gmaps"], "Waze does not operate in Japan."),
    "KR": (["naver"], "South Korea restricts map-data export, so Google Maps "
                      "gives no driving directions. Naver or Kakao is what "
                      "people actually use."),
    "CN": (["amap"], "Google services are blocked in mainland China; Amap "
                     "(Gaode) or Baidu Maps is required. Note Chinese maps use "
                     "the GCJ-02 datum, so raw OSM WGS-84 coordinates land "
                     "roughly 300-500 m off unless converted."),
}

_CLOSED_DAY_LABEL = {"Mo": "Mondays", "Tu": "Tuesdays", "We": "Wednesdays",
                     "Th": "Thursdays", "Fr": "Fridays", "Sa": "Saturdays",
                     "Su": "Sundays"}


def _build():
    out = {}
    for cc, note in _SUNDAY_CLOSED.items():
        out[cc] = dict(_DEFAULT, closed_days=["Su"], short_days=[], badge=True,
                       note=note or "Sunday is the common closing day.")
    for cc, spec in _FRI_SAT.items():
        out[cc] = dict(_DEFAULT, badge=bool(spec["closed_days"] or spec["short_days"]),
                       **spec)
    for cc, note in _SHORT_SUNDAY.items():
        out[cc] = dict(_DEFAULT, closed_days=[], short_days=["Su"], badge=True,
                       note=note)
    for cc in _ALWAYS_OPEN:
        out.setdefault(cc, dict(_DEFAULT,
                                note="Shops and attractions generally trade seven "
                                     "days; a closed-day badge would be noise."))
    for cc in dict.fromkeys(list(out) + sorted(_MILES | _FAHRENHEIT | set(_NAV))):
        p = out.setdefault(cc, dict(_DEFAULT))
        if cc in _MILES:
            p["distance"] = "mi"
        if cc in _FAHRENHEIT:
            p["temperature"] = "F"
        if cc in _NAV:
            apps, why = _NAV[cc]
            p["nav"] = apps
            p["note"] = (p.get("note", "") + " " + why).strip()
    return out


PROFILES = _build()


def profile(country_code):
    """Look up a profile. Unknown codes get the neutral, badge-off default."""
    if not country_code:
        return dict(_DEFAULT)
    return dict(PROFILES.get(country_code.upper(), _DEFAULT))


def closed_day_label(codes):
    """['Sa'] -> 'Saturdays'; ['Fr','Sa'] -> 'Fridays and Saturdays'."""
    names = [_CLOSED_DAY_LABEL.get(c, c) for c in codes]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


if __name__ == "__main__":
    for cc in ["AT", "DE", "IL", "AE", "SA", "JP", "US", "KR", "CN", "GB", "XX"]:
        p = profile(cc)
        print(f"{cc}: closed={p['closed_days'] or '-'} short={p['short_days'] or '-'} "
              f"badge={p['badge']} {p['distance']}/{p['temperature']} nav={p['nav']}")
        print(f"    {p['note']}")
