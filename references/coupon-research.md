# Deals, coupons & savings research — per region

A reusable playbook for finding **real, tourist-usable savings** for a trip's
attractions, restaurants and daily spend, in whatever region the site is being
built for. Run this as a research step; surface the findings to the user. **Do not
put anything on the site unless the user asks** — this produces a briefing, and the
user decides what (if anything) becomes a "book-ahead & save" note or a price
column later.

## The core lesson (start here — it saves hours)

For **self-operated attractions** (a specific cable car, alpine coaster, thermal
spa, gorge, theme park, zoo), the classic coupon **aggregators are almost always a
dead end**. Expect this pattern and verify rather than assume:

- **Groupon and its local clones** usually carry only *overnight hotel + spa
  packages* or generic big-city theme parks — not day tickets to the specific
  attractions a family visits. Groupon has also **withdrawn from many markets**
  (e.g. `groupon.at` now redirects to `groupon.de`). Search it, but expect nothing.
- The **real savings** almost always come from two places instead:
  1. **The attraction's OWN online shop** — dynamic/early-bird pricing, online-vs-
     box-office gap, family/combo tickets, evening/last-hours rates, kids/birthday
     free.
  2. **Free regional guest cards** and paid **city/region cards** — so the family
     does not *pay* for things already covered.

So the research is less "find a promo code" and more "map where the money actually
leaks and where the region's own systems plug it." Report honestly when a channel
has nothing — a verified "nothing here" is a useful finding, not a failure.

## Method

Spawn **one research subagent per base/region** (parallel), each covering the whole
checklist below for that region's real attractions and restaurants. Feed each agent
the actual attraction list from the destination research (step 1 of the skill) so it
checks *your* attractions, not generic ones. Demand, per channel: the **site/app
name + URL**, the **specific offer** (if any), the **rough discount**, **blackout
dates / validity in the travel month**, and **whether a foreign tourist can actually
use it** (many deals are members-only, residents-only, or app-region-locked).

## Channel checklist (run every one, per region)

### 1. Coupon aggregators (expect little — but check)
- **Groupon** (national domain, and note redirects), and the country's local
  equivalents (e.g. DE/AT: DailyDeal; think "deal + <country>" in the local
  language). Search each target attraction by name.

### 2. Ticket resellers (tourist-friendly, sometimes small codes)
- **GetYourGuide**, **Tiqets**, **Klook**, **Musement**, **Headout**, **Civitatis**.
  These sell English, mobile, foreign-card-friendly tickets. Occasionally a small
  site-wide code (~5–10%). Treat any promo *code* found on a blog as **unverified**
  until it applies at checkout.

### 3. The attraction's OWN site — where the real money is
For each paid attraction, check for:
- **Online vs box-office** price gap (buying online often saves a few € *and* skips
  the queue; some spas **refuse entry without an online ticket** on busy days).
- **Dynamic / early-bird pricing** (cheaper the earlier you book — often 4+ days).
- **Family / combo / 2-day tickets.**
- **Evening / "last 2 hours" / afternoon** reduced rates.
- **Free thresholds** — under-3 / under-6 free, **birthday child free**, senior rates.
- Cash-only / no-online attractions — note them so nobody hunts for a nonexistent code.

### 4. Regional guest cards & city/region cards (the biggest lever)
- **Free guest card** given at check-in by partner lodging (huge in Alpine
  regions — e.g. Kärnten guest card, Saalfelden-Leogang Card, Saalbach-Hinterglemm
  JOKER CARD; elsewhere "guest card", "visitor card", "Gästekarte", "carta ospiti").
  List **what it already covers free** so the family does not buy tickets or coupons
  for free things. Cross-check against the site's discount-card coverage table.
- **Paid city/region cards** (e.g. Kärnten Card, Salzburg Card, city passes). Do a
  quick **worth-it check**: does the family's planned attraction mix exceed the card
  price? State the break-even.
- **Beware mis-tagging:** verify each attraction's status on the card — the research
  we ran found items wrongly assumed "paid" that were actually **free with the card**
  (and vice-versa). Never guess coverage.

### 5. Restaurant & food savings
- **Reservation-discount apps:** **TheFork** (a.k.a. LaFourchette / ElTenedor,
  Europe-wide — often 20–50% off à la carte or "yums" loyalty), **OpenTable** (mostly
  US/UK). Check coverage in the specific towns.
- **Local tactics that beat any coupon:** the **fixed lunch menu** (Mittagsmenü /
  menu del giorno / menú del día / plat du jour) is often half the dinner price for
  the same kitchen; **"kids eat free"** promos; hotel/guest-card **restaurant
  discounts**; **tourist menus**. Note these as tactics, not codes.
- **Family/chain apps:** many casual chains have an app with a signup coupon —
  region-dependent; check the ones actually present near each base.

### 6. Surplus-food & anti-waste apps (great for families, region-dependent)
Recommend only the ones **actually active in the destination**. Verify coverage per
region/town, don't assume:
- **Too Good To Go** — bakeries/supermarkets/restaurants sell end-of-day "surprise
  bags" cheap; very widely active across Europe + parts of North America. Usually the
  best single recommendation where it operates.
- **Karma** (Sweden/Nordics/UK/France), **Olio** (free food sharing, UK-strong),
  **Phenix** (France), **Motatos/Matsmart** (Nordics discount grocery). Pick by region.
- Note: these apps need a local-ish account but **work fine for tourists** with the
  app + a card; flag any that are strictly resident-locked.

### 7. Supermarket / fuel loyalty (for a self-catering family)
- Region's grocery loyalty program (e.g. **jö Bonus Club** in Austria, **PAYBACK** in
  Germany, **Nectar** in the UK) — usually free to join, instant member prices; worth
  it for a multi-week self-catering stay. Note Sunday-closing (already on the map).
- Fuel/discount-store apps if a road trip.

### 8. Membership / auto-club discounts (usually NOT for tourists)
- Auto clubs (ÖAMTC/ARBÖ in AT, ADAC in DE, TCS in CH, AA/RAC in UK) and warehouse
  clubs list attraction discounts but are **members-only** — flag as *not usable* by a
  foreign tourist unless they already hold a reciprocal membership.

### 9. Local-language search (finds what English misses)
Search in the **destination's language** — deals, family combos and guest-card perks
are often only published locally. E.g. "<attraction> Gutschein / Rabatt / Familienticket"
(DE), "sconto / biglietto famiglia" (IT), "réduction / billet famille" (FR),
"descuento / entrada familiar" (ES).

## Verification discipline (same ethos as the rest of the skill)

- **Never invent a promo code, price, or discount %.** If you can't confirm a current
  offer, give the **URL to check** and label it *unverified*.
- **Always note validity in the travel month** — deals expire and spas have seasonal
  **blackout dates**; a deal that's dead in August is not a deal.
- **Always note tourist-usability** — members-only, residents-only, or app not live in
  the region ⇒ say so plainly.
- Prefer the **official attraction/tourism-board page** over blogs and coupon
  listicles for prices and card coverage.

## How to present the findings

Return a concise briefing **grouped by region**, then by channel, with a short
"most-actionable" list at the end (e.g. "buy Familypark online 4+ days ahead", "do
the spa on family-discount day", "install Too Good To Go — active in these towns",
"ask both hotels for the free guest card"). Keep the honest "nothing usable here"
lines — they stop the user re-hunting.

**Only if the user then asks to put it on the site**, good homes for it are:
- a small **"Book ahead & save"** note under the tickets/discount-card section,
- an extra **price / official-booking-link** column in the hours or coverage table,
- a short **"Apps to install"** card (Too Good To Go, TheFork, the region's guest-card
  app, the grocery loyalty app).
Until then, this stays a briefing — do not modify the site.
