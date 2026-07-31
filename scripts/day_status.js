#!/usr/bin/env node
/**
 * day_status.js — evaluate OSM opening_hours for specific trip dates.
 *
 *   npm install opening_hours@3.8.0
 *   node scripts/day_status.js < input.json > output.json
 *
 * stdin:  { "country": "AT",
 *           "dates": ["2026-08-05", "2026-08-06"],
 *           "pois": [ { "id": "base1:0", "hours": "Mo-Fr 09:00-17:00; PH off" } ] }
 *
 * stdout: { "base1:0": { "2026-08-05": { "s": "open", "iv": "09:00-17:00" },
 *                        "2026-08-06": { "s": "closed" } } }
 *
 * WHY THIS RUNS AT BUILD TIME, NOT IN THE BROWSER
 * -----------------------------------------------
 * opening_hours.js is the only thing that reads the full grammar — seasonal
 * ranges like "May 3 - Sep 30", public holidays, the lot. But it needs
 * opening_hours.min.js + suncalc + i18next, about 291 KB minified across three
 * CDN scripts. This site is meant to work as plain static files on a phone with
 * one bar of signal in an Alpine valley, and its guardrail is "only Leaflet and
 * fonts from a CDN".
 *
 * A trip has maybe 15 dates, so evaluating every POI against every date here
 * produces a table of a few KB. The page ships that table and needs no new
 * JavaScript at all.
 *
 * HOLIDAY COVERAGE IS NOT UNIVERSAL
 * ---------------------------------
 * opening_hours.js THROWS on a `PH` rule when it has no holiday data for the
 * country — verified: Austria resolves Nationalfeiertag correctly, while Israel
 * and Japan raise "There are no holidays (PH) defined for country il/jp".
 * That is a hard failure, so it is caught: the PH clause is stripped, the rest
 * is evaluated, and every date is marked `ph: true` meaning "this ignores public
 * holidays — check them separately". fetch_holidays.py supplies that list.
 */
'use strict';

// Resolve from the project directory as well as from next to this script:
// the build is normally run as `node scripts/day_status.js` from the project
// root, where node_modules lives, and bare require() only looks alongside the
// script itself.
let oh;
for (const where of [null, process.cwd(), require('path').join(process.cwd(), 'node_modules')]) {
  try {
    oh = where ? require(require('path').join(where, 'node_modules', 'opening_hours'))
               : require('opening_hours');
    break;
  } catch (e) { /* try the next location */ }
}
if (!oh) {
  try { oh = require(require('path').join(process.cwd(), 'node_modules', 'opening_hours')); }
  catch (e) { /* reported below */ }
}
if (!oh) {
  console.error('day_status.js: opening_hours is not installed.\n' +
                '  Run:  npm install opening_hours@3.8.0\n' +
                '  (build-time only — nothing is added to the shipped site.)');
  process.exit(2);
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', d => { buf += d; });
    process.stdin.on('end', () => resolve(buf));
    process.stdin.on('error', reject);
  });
}

/** "Mo-Fr 09:00-17:00; PH off" -> "Mo-Fr 09:00-17:00" */
function stripPH(spec) {
  return spec.split(';')
             .filter(r => !/\bPH\b/.test(r))
             .join(';')
             .replace(/,\s*PH\b/g, '')
             .replace(/\bPH\s*,\s*/g, '')
             .trim()
             .replace(/^;+|;+$/g, '');
}

function hhmm(d) {
  return String(d.getHours()).padStart(2, '0') + ':' +
         String(d.getMinutes()).padStart(2, '0');
}

/**
 * Typographic normalisation ONLY — never a guess at meaning.
 * Hand-authored data routinely uses en/em dashes ("11:30–22:00") and NBSPs,
 * which are invisible to a human and fatal to the parser. Converting them is
 * safe. Prose like "Free access · lifeguard Jul-Aug" is NOT rescued here: it
 * has no defined meaning in the grammar and is reported as unparseable.
 */
function normalise(spec) {
  return String(spec)
    .replace(/[‐-―−]/g, '-')   // en/em dash, minus sign
    .replace(/[   ]/g, ' ')    // non-breaking spaces
    .replace(/[：]/g, ':')                // fullwidth colon (CJK data)
    .replace(/\s+/g, ' ')
    .trim();
}

function build(spec, cc) {
  // Returns {oh, phUnsupported} or null if the value cannot be parsed at all.
  try {
    return { oh: new oh(spec, { address: { country_code: cc } }), ph: true };
  } catch (e) {
    const msg = String((e && e.message) || e);
    if (/no holidays \(PH\) defined/i.test(msg) && /\bPH\b/.test(spec)) {
      const stripped = stripPH(spec);
      if (stripped) {
        try {
          return { oh: new oh(stripped, { address: { country_code: cc } }), ph: false };
        } catch (e2) { /* fall through */ }
      }
    }
    return null;
  }
}

(async function main() {
  let input;
  try {
    input = JSON.parse(await readStdin());
  } catch (e) {
    console.error('day_status.js: stdin is not valid JSON — ' + e.message);
    process.exit(2);
  }
  const cc = String(input.country || '').toLowerCase();
  const dates = input.dates || [];
  const out = {};
  let evaluated = 0, unparsed = 0, phDropped = 0;

  for (const poi of (input.pois || [])) {
    if (!poi.hours) continue;
    const built = build(normalise(poi.hours), cc);
    if (!built) {
      // Unparseable is a real answer. Recording nothing is better than
      // recording a guess; the map shows "hours not evaluated".
      unparsed++;
      continue;
    }
    if (!built.ph) phDropped++;
    const perDate = {};
    for (const date of dates) {
      try {
        const noon = new Date(date + 'T12:00:00');
        const dayStart = new Date(date + 'T00:00:00');
        const dayEnd = new Date(date + 'T23:59:59');
        const iv = built.oh.getOpenIntervals(dayStart, dayEnd);
        const rec = { s: iv.length ? 'open' : 'closed' };
        if (iv.length) {
          rec.iv = iv.map(x => hhmm(x[0]) + '-' + hhmm(x[1])).join(', ');
        }
        if (!built.ph) rec.ph = true;   // public holidays NOT accounted for
        void noon;
        perDate[date] = rec;
      } catch (e) {
        perDate[date] = { s: 'unknown' };
      }
    }
    out[poi.id] = perDate;
    evaluated++;
  }

  console.error(`day_status.js: ${evaluated} POIs x ${dates.length} dates evaluated` +
                (phDropped ? `, ${phDropped} ignored public holidays (no PH data for "${cc}")` : '') +
                (unparsed ? `, ${unparsed} hours strings could not be parsed` : ''));
  process.stdout.write(JSON.stringify(out));
})();
