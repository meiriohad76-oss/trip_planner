#!/usr/bin/env python3
"""
osm_hours.py — a deliberately small, deliberately cautious reader for the
OpenStreetMap `opening_hours` grammar.

WHY THIS IS NOT A REGEX
-----------------------
`opening_hours` is a real grammar, and naive string matching gets it backwards.
The string

    Mo-Fr 07:15-19:30; Sa 07:15-18:00; Su off

contains "Su", so "is 'Su' in the string" reports the shop as OPEN on Sunday.
It is closed. That is the exact inverse of the truth, on the exact badge this
skill markets (supermarkets in AT/DE mostly close on Sundays).

WHAT THIS MODULE PROMISES
-------------------------
`sunday_state()` returns "open" | "limited" | "closed" | None.

**None means "I could not tell" and is a first-class answer.** It is returned
for anything involving seasons, week numbers, holiday-only rules, or syntax this
subset does not model. Callers must treat None as "needs a human" — never as a
default. Guessing here is worse than admitting ignorance, because a family
drives to a closed supermarket on the strength of a badge.

For full grammar support (seasonal ranges, public holidays, "open on the day we
are actually going"), use opening_hours.js in the browser. This module exists so
the build step can fill the common cases and flag the rest.
"""
import re

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY_IX = {d: i for i, d in enumerate(DAYS)}

# Constructs this subset does NOT model. Their presence forces None.
TOO_COMPLEX = re.compile(
    r"(week\s|\bPH\b|\bSH\b|easter|sunrise|sunset|dawn|dusk|"
    r"\b\d{4}\b|"                                  # explicit years
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|"  # seasonal ranges
    r"\[|\]|>|<)",
    re.I,
)


def _expand(day_spec):
    """'Mo-Fr' -> {0,1,2,3,4}; 'Sa,Su' -> {5,6}; 'Su' -> {6}. None if unparseable."""
    out = set()
    for part in day_spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([A-Za-z]{2})\s*-\s*([A-Za-z]{2})", part)
        if m:
            a, b = m.group(1).title(), m.group(2).title()
            if a not in DAY_IX or b not in DAY_IX:
                return None
            i, j = DAY_IX[a], DAY_IX[b]
            out |= set(range(i, j + 1)) if i <= j else (set(range(i, 7)) | set(range(0, j + 1)))
            continue
        p = part.title()
        if p in DAY_IX:
            out.add(DAY_IX[p])
        else:
            return None
    return out


def _minutes(rng):
    """'10:00-13:00' -> 180. None if not a plain time range."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", rng.strip())
    if not m:
        return None
    a = int(m.group(1)) * 60 + int(m.group(2))
    b = int(m.group(3)) * 60 + int(m.group(4))
    if b <= a:            # overnight or malformed — out of scope
        return None
    return b - a


def day_state(spec, weekday, limited_below_minutes=300):
    """Return "open" | "limited" | "closed" | None for one weekday.

    `weekday` is 0=Monday … 6=Sunday, or a two-letter code ("Sa", "Fr").

    Which day matters is NOT universal, which is why this is parameterised.
    Austria and Germany close on Sunday; Israel closes Saturday (and Friday
    afternoon); much of the Gulf closes Friday midday; Japan, the US and most
    of Asia close nothing. Hardcoding Sunday produces a badge that is wrong or
    meaningless outside Central Europe. See scripts/regions.py.

    "limited" means open, but for a notably short window (default: under 5h).
    """
    if isinstance(weekday, str):
        weekday = DAY_IX.get(weekday.title())
    if weekday is None or not (0 <= weekday <= 6):
        return None
    if not spec or not isinstance(spec, str):
        return None
    s = spec.strip()
    low = s.lower()

    if low in ("24/7",):
        return "open"
    if low in ("closed", "off"):
        return "closed"
    if TOO_COMPLEX.search(s):
        return None

    week = _week_minutes(s)
    if week is None:
        return None
    day_rule = week[weekday]

    if day_rule is None:
        # The day never appears. In this grammar an unmentioned day is closed,
        # but real-world data is sloppy enough that we only trust that when the
        # spec actually enumerates days.
        others = [d for i, d in enumerate(DAYS) if i != weekday]
        return "closed" if re.search(r"\b(" + "|".join(others) + r")\b", s) else None
    if day_rule == 0:
        return "closed"

    # "limited" is RELATIVE to the rest of the week, not an absolute cutoff.
    # An absolute threshold does not travel: Israeli Friday trading of
    # 08:00-14:00 is 6 h, which clears a 5 h bar, yet it is plainly a short day
    # beside the 13 h Su-Th norm. Compare against the week's typical open day.
    full = sorted(m for m in week if m)
    if full:
        typical = full[len(full) // 2]           # median open day
        if day_rule < 0.7 * typical:
            return "limited"
    return "limited" if day_rule < limited_below_minutes else "open"


def _week_minutes(s):
    """Open minutes for each weekday, or None where the day is unmentioned.

    Returns None entirely if any rule uses syntax this subset cannot model.
    """
    week = [None] * 7
    for rule in s.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        m = re.match(r"^([A-Za-z]{2}(?:\s*[-,]\s*[A-Za-z]{2})*)\s+(.*)$", rule)
        if not m:
            # A bare time range with no day prefix means "every day".
            mins = _minutes(rule)
            if mins is not None:
                week = [mins] * 7
                continue
            if rule.lower() in ("off", "closed"):
                return [0] * 7
            return None
        days, rest = _expand(m.group(1)), m.group(2).strip()
        if days is None:
            return None
        if rest.lower() in ("off", "closed"):
            for d in days:
                week[d] = 0
            continue
        total = 0
        for chunk in rest.split(","):
            mins = _minutes(chunk)
            if mins is None:
                return None
            total += mins
        for d in days:
            week[d] = total
    return week


def sunday_state(spec, limited_below_minutes=300):
    """Back-compat shim. Prefer day_state() with the destination's rest day."""
    return day_state(spec, 6, limited_below_minutes)


# --- self-test: real strings pulled from live Overpass responses --------------
CASES = [
    ("Mo-Fr 07:15-19:30; Sa 07:15-18:00; Su off",          "closed"),   # the inverted-regex trap
    ("Mo-Fr 06:50-19:00; Sa 06:50-18:00",                  "closed"),   # Sunday unmentioned
    ("Mo-Su 11:30-20:30",                                  "open"),
    ("24/7",                                               "open"),
    ("closed",                                             "closed"),
    ("Su 10:00-13:00",                                     "limited"),
    ("Mo-Sa 08:00-20:00; Su 09:00-12:00",                  "limited"),
    ("Mo-Sa 08:00-20:00; Su 09:00-18:00",                  "open"),
    ("Su,Sa 10:00-16:00",                                  "open"),
    ("May 3 - Sep 30: 09:00-18:00",                        None),       # seasonal -> unknown
    ("Mo-Fr 09:00-17:00; PH off",                          None),       # holidays -> unknown
    ("sunrise-sunset",                                     None),
    ("Tu-Su 10:00-18:00",                                  "open"),
    ("", None),
    (None, None),
]

# Non-Sunday cases — the whole point of parameterising the day.
DAY_CASES = [
    # Israel: closed Saturday (Shabbat), Friday short, Sunday a normal workday.
    ("Su-Th 08:00-21:00; Fr 08:00-14:00; Sa off", "Sa", "closed"),
    ("Su-Th 08:00-21:00; Fr 08:00-14:00; Sa off", "Fr", "limited"),
    ("Su-Th 08:00-21:00; Fr 08:00-14:00; Sa off", "Su", "open"),
    # Gulf: Friday opens only after midday prayers. 8 h against a 13 h norm —
    # "limited" is the useful answer, because a family arriving at 10:00 finds
    # the doors shut.
    ("Sa-Th 09:00-22:00; Fr 14:00-22:00", "Fr", "limited"),
    ("Sa-Th 09:00-22:00; Fr off", "Fr", "closed"),
    # Japan / US: open every day — the badge should say nothing useful.
    ("09:00-23:00", "Su", "open"),
    ("09:00-23:00", "Sa", "open"),
    ("Mo-Su 10:00-20:00", "We", "open"),
    # Weekday closures happen everywhere (museums shut Mondays).
    ("Tu-Su 10:00-18:00", "Mo", "closed"),
    ("Tu-Su 10:00-18:00", "Tu", "open"),
    # Bad input
    ("Mo-Fr 09:00-17:00", "Xx", None),
]

if __name__ == "__main__":
    bad = 0
    print("Sunday cases (back-compat shim):")
    for spec, want in CASES:
        got = sunday_state(spec)
        ok = got == want
        bad += not ok
        print(f"{'✓' if ok else '✗'} {str(spec)[:44]:46s} -> {str(got):8s} (want {want})")
    print("\nArbitrary-weekday cases:")
    for spec, day, want in DAY_CASES:
        got = day_state(spec, day)
        ok = got == want
        bad += not ok
        print(f"{'✓' if ok else '✗'} [{day}] {str(spec)[:40]:42s} -> {str(got):8s} (want {want})")
    total = len(CASES) + len(DAY_CASES)
    print(f"\n{total-bad}/{total} passed")
    raise SystemExit(1 if bad else 0)
