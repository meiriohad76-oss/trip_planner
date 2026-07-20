/* ==========================================================================
   maps-data.js — points of interest for the interactive vacation maps.
   Loaded by maps.html as window.MAPDATA.

   One entry per section (usually one per hotel/base the trip stays at). Each has:
     hotel : { name, lat, lng }          — the base; rendered as the 🏡 marker,
                                            and every POI's distance is measured from it.
     pois  : [ POI, ... ]

   POI fields:
     name       (string)  original/local name — keep it findable on a map
     category   (enum)     one of the keys in CATS (see maps.html): attraction |
                           restaurant | supermarket | nature | pool | animal |
                           museum | castle | scenic | park | shopping
     lat, lng   (number)   REAL coordinates. Do not guess — geocode/verify each.
     desc       (string)   one or two sentences, in the site's language
     hours      (string)   opening hours as text (verify close to travel)
     drive_min  (number)   driving minutes from the hotel (verify with a router)
     pass       (bool)     optional: covered by the trip's discount pass/city card
     sunday     (enum)     supermarkets only: "open" | "limited" | "closed"

   NOTE: drive times and hours are estimates — re-verify before the trip.
   Delete the sample entries and fill with the real trip. Keep it valid JS.
   ========================================================================== */
window.MAPDATA = {

  /* ============================ Base 1 ============================ */
  base1: {
    hotel: { name: "Sample Hotel — Lakeside", lat: 47.3230, lng: 13.1330 },
    pois: [
      { name:"Old Town Square", category:"attraction", lat:47.3250, lng:13.1360, drive_min:5, pass:true,
        desc:"Historic pedestrian center with cafés, the market hall and the clock tower.",
        hours:"Open access · shops ~09:00–18:00" },
      { name:"Lake Promenade Beach", category:"nature", lat:47.3190, lng:13.1290, drive_min:4,
        desc:"Free swimming beach with a playground, boat rental and a shallow kids' area.",
        hours:"Free access · lifeguard Jul–Aug" },
      { name:"Family Restaurant Seehof", category:"restaurant", lat:47.3241, lng:13.1345, drive_min:5,
        desc:"Lake-view terrace, schnitzel and wood-fired pizza, high chairs and a kids' menu.",
        hours:"Daily 11:30–22:00 · kitchen to 21:00" },
      { name:"SPAR Supermarkt", category:"supermarket", lat:47.3268, lng:13.1372, drive_min:6, sunday:"closed",
        desc:"Full-size supermarket with a bakery counter; nearest large grocery to the hotel.",
        hours:"Mon–Fri 07:15–19:00 · Sat to 18:00" },
      { name:"Adventure Park Summit", category:"attraction", lat:47.2980, lng:13.1810, drive_min:18, pass:true,
        desc:"Cable car to a mountain playground, alpine coaster and easy panorama loops.",
        hours:"Season May–Oct · daily 09:00–16:30 · weather-dependent" },
    ],
  },

  /* ============================ Base 2 ============================ */
  base2: {
    hotel: { name: "Sample Hotel — Village", lat: 47.4600, lng: 12.9100 },
    pois: [
      { name:"Wildlife Park", category:"animal", lat:47.4720, lng:12.9450, drive_min:14, pass:true,
        desc:"Native alpine animals on a stroller-friendly loop; feeding times midday.",
        hours:"Daily 09:00–17:00" },
      { name:"Thermal Baths", category:"pool", lat:47.4510, lng:12.8880, drive_min:12,
        desc:"Indoor/outdoor thermal pools, water slides and a sauna world — top rainy-day option.",
        hours:"Daily 10:00–21:00" },
      { name:"Trattoria Bella Vista", category:"restaurant", lat:47.4592, lng:12.9112, drive_min:3,
        desc:"Family-run Italian in the village center, big portions, garden seating.",
        hours:"Tue–Sun 12:00–22:00 · Mon closed" },
      { name:"BILLA Supermarkt", category:"supermarket", lat:47.4585, lng:12.9138, drive_min:4, sunday:"limited",
        desc:"Central grocery with a deli; one of the few open (short hours) on Sundays.",
        hours:"Mon–Sat 07:30–19:00 · Sun 10:00–13:00" },
    ],
  },

};
