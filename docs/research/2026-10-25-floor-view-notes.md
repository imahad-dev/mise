# Floor view research notes (2026-10-25)

Purpose: inform a camera-free "Floor view" (table map + service-timing alerts) for Mise.
Legend: [S] = sourced from the cited page; [I] = my inference. Pages were read on 2026-10-25 unless noted.
Gaps are stated, not filled. Tool budget was small and the search API was rate limited, so coverage is uneven.

## 1. Table status models

### Lightspeed Restaurant (L-Series) [S]
Source: https://resto-support.lightspeedhq.com/hc/en-us/articles/226306187-Understanding-table-status (page screenshots dated 2020; page still live 2026)
- The page says "three statuses" but lists five colours:
  - no colour: no active order; "customers may be seated waiting to order"
  - green: order in progress
  - orange: order ready for the customer (only with Lightspeed Kitchen, table service mode), i.e. kitchen bump drives a colour
  - red: receipt printed, payment not yet processed; the table returns to its original status after finalising
  - blue: new takeaway/delivery order that needs accepting
- No dirty/bussing state and no timers on this page.

### Square for Restaurants [S]
Sources: https://squareup.com/help/us/en/article/8146-customize-table-management-settings ; https://squareup.com/help/gb/en/article/7920-seating-status-with-square-for-restaurants-and-reservation-integrations
- Floor plan indicators: shows time elapsed since a check was opened, plus colour indicators set per device "mode": "Turn Yellow After" X and "Turn Red After" Y (the values are configured by the venue; the page gives no defaults).
- Seating an OpenTable booking can auto-open a check; the timer starts at zero and keeps running. Such tables are purple.
- Staff can see which tables are empty, when seated, how long seated, and whether a seated table "has not yet been waited on". The page does not say how that last state is drawn.
- Merged tables show as linked and occupied. "Track seating" (cover count, optional seat positions) is a separate setting.
- No dirty/bussing state found.

### TouchBistro [S]
Source: https://help.touchbistro.com/s/article/understanding-your-floor-plan-screen (Dec 2024)
- Unopened table colour = its section colour. Opened table colour = the assigned server's colour. So colour encodes section and server, not stage.
- Each table tile shows name/number, order number and cover count, "how long the party has been at the table", and the running total.
- Separate Reservations app: tables colour-coded by status in AM/PM views (https://www.touchbistro.com/help/articles/reservations-additional-floorplan-options; seen as search excerpt only).
- No dirty state or alert thresholds found.

### Toast [S/gap]
- Toast's own colour key was not retrievable (support.toasttab.com returned 403 to my fetch). Search snippets only: release notes say green/red/yellow table status colours were lightened and the empty-table outline is blue; tables seated via Toast Tables are purple (limited release). I did not verify a dirty/needs-bussing state in Toast. Treat Toast as unverified.

### Other systems with explicit dirty/clean [S]
- Oracle Simphony: statuses Open / Occupied / Closed plus decorators Clean / Dirty / Closed / Reserved. Clean/dirty set manually via long-press "Set as Clean/Dirty"; dirty = unavailable for seating, clean = available. No auto method described, no timers on that page. https://docs.oracle.com/cd/F32325_01/doc.192/f32329/c_tms_table_status.htm
- Xenial Genius POS table map: Dirty, Open, Ordered, Paid, Printed, Seated (dirty = unavailable, needs cleaning; printed = occupied with check printed). Seen via search snippet only; the page 404'd on fetch. https://resources.xenial.com/product-documentation/en/genius-point-of-sale/enterprise-pos/enterprise-pos-app/table-service-features/table-map-overview.html
- Katalyst: Clean, Seated, Check Dropped, Dirty; Clean/Seated/Dirty auto, others manual (search snippet; https://customer-portal.katalystos.com/knowledge/managing-table-status).
- SpotOn guide: after guests leave, reset and sanitise, then "servers mark the table as available in the POS" which updates reservations in real time. https://www.spoton.com/blog/steps-of-service/

### OpenTable / Resy, Oscar
- OpenTable GuestCenter and Resy status docs: not found. Gap.
- Oscar (oscar.qa/products/restaurants): only marketing copy: centrally synced floor map, staff can change table status from anywhere, auto table/order assignment. No state list. [S]

### Synthesis
- Common state vocabulary across vendors [I, from the above]: available/clean, seated (no order), ordered/in progress, food ready, check printed/dropped, paid, dirty. Not every vendor has every state; the lifecycle stages map consistently.
- Colour conventions are NOT standard [I]. Lightspeed: none/green/orange/red/blue. Square: yellow/red are elapsed-time warnings, purple is a booking source. TouchBistro: colours encode section/server. Only red = "attention/late or check out" recurs. Designers should not assume green=OK; use labels and icons as well as colour.

## 2. Timing alerts

### Vendor mechanics [S]
- Square: venue-configured yellow and red thresholds on elapsed time since check opened (no defaults published), shown on the floor plan; no acknowledge/dismiss: colour is purely derived from elapsed time and clears when the check closes [I for the "no dismiss" part: none documented].
- TouchBistro: elapsed-time label on the tile only; no thresholds.
- Lightspeed: state colour change only (orange = ready, red = check printed).

### Industry guidance (not vendor thresholds) [S]
- RestaurantOwner "Basic Steps of Service" (2020 PDF, template; ok as guidance): https://www.restaurantowner.com/webinar/data/2020/CompetentServiceCaringHospitality-StepsofService.pdf
  - server greeting within 1 min of seating
  - beverage order within 1-2 min of seating; first drinks delivered 2-4 min after order
  - appetizer order within 3 min of seating
  - entree order within 5 min of appetizer order; entree ticket goal 10-12 min (15 max when full)
  - two-bite check-back within 2 min of food delivery
  - check presented ~2 min after dessert plates cleared; payment processed within 1 min of card/cash presented
  - table turned within 2 min of guests leaving
- SpotOn (Oct 2025): greet within 1 min of seating; drinks arrive 3-5 min after order; appetizers 5-15 min; two-bite check within 2 min. https://www.spoton.com/blog/steps-of-service/
- A Quizlet study guide says drinks within 3 min of order (low-authority; ignore).
- Not found: an authoritative source for dwell/turn time in casual dining (typical figures like 45-90 min are in my head but unsourced here; do not cite), or a standard check-drop-to-payment target beyond the 1 min payment above. These are house policies, vary by concept.

### Alert display and acknowledgement
- Documented: colour change by elapsed time (Square), timer badge (Square, TouchBistro). No acknowledge/dismiss mechanism found in any vendor doc read. [I] Likely pattern: alert clears when the next stage event happens (order placed, bill settled), not by manual dismissal.

## 3. Needs-cleaning / bussing
- Oracle: manual Set as Clean / Set as Dirty, manual only [S]. Katalyst: Dirty auto after payment, Clean set (auto or manual per snippet; unclear) [S, weak]. SpotOn: staff mark available after reset [S].
- Duration: guidance says reset within 2 min of guests leaving (RestaurantOwner) [S]. No vendor data on actual bussing time. 
- [I] The tap-to-clear is the only reliable signal without sensors; auto-clear after N minutes would silently lie.

## 4. Multi-device
- TouchBistro: floors selectable; table colours by section/server; staff assigned to sections ("assigning staff to tables, sections and floors") [S, link only]. Oracle: employee indicator colour and section colour shown by default and can be hidden [S].
- Square: floor plan available on Register, Terminal, Handheld; merged-table view across devices [S].
- Oscar: "centrally synced" map, status changeable from anywhere [S, marketing].
- Not found: explicit manager-vs-server view docs. [I] Typical split: server sees own section/tables by default, manager sees all with filter by section/server.

## 5. Camera-based monitoring and privacy
- Products found [S, vendor/press claims]:
  - Presto Vision at Outback (Bloomin' Brands): alerts managers/servers via wearables; vendor says footage deleted after 30 days and no PII tracked; press criticised it as surveillance. https://thetakeout.com/outback-ai-nannycam-surveillance-presto-vision-1839103568 ; https://www.fsrmagazine.com/industry-news/outback-testing-computer-vision-platform/
  - TableWatch (DifiNative/Intel doc): table status via vision, on-premise processing, claims GDPR compliance. https://builders.intel.com/docs/networkbuilders/intelligent-automated-table-management-with-vision-al-1760461726.pdf
  - Sciforce case study: camera zones per table, rule engine moves status e.g. Available -> Waiting for Waiter. https://www.sciforce.solutions/case-studies/computer-vision-restaurant-service-optimization
  - Berry AI: claims no facial recognition. https://www.berry-ai.com/technology
- Privacy/regulation: I did not retrieve legal sources. Only facts: press backlash (Takeout) and vendors' own privacy claims; independent audits not found. Regulatory specifics (GDPR video surveillance, Pakistan law) are unresearched: do not assert them. [gap]
- [I] Justification for camera-free: needs hardware and install, guest-surveillance optics, consent/notice duties, error-prone matching of "staff present"; QR/POS events give status deterministically and cheaply.

## 6. Pakistan
- Oscar POS: marketing says table management, waitlist, reservations, synced floor map (oscar.qa is the Qatar site; Pakistan-specific page not confirmed). Bizbuddy/FoodBucket list Oscar among top Pakistani POS (search snippets, https://foodbucket.io/blog/5-best-restaurant-pos-point-in-sale-in-pakistan).
- Blink Co: search snippets mention table reservations, live order tracking, POS with tablet-based services; nothing on floor-map states. [gap, snippet-level only]
- No evidence found of service-timing alerts in local POS.

## Implications for the design
States derived from our events (scan, order, kitchen bump, bill request, settle) [I]:
1. `available` : no open session; also after clear.
2. `seated` : guest scanned QR, no order yet. Timer from scan. (Lightspeed: "no colour, seated waiting to order".)
3. `ordered` : order placed, kitchen not yet bumped. Timer from order.
4. `served` (food ready/delivered) : kitchen bump on all items (Lightspeed orange = ready). Caveat: bump = ready, not delivered; label it "Ready/Served" and do not claim delivery.
5. `bill_requested` : guest asked for bill (Lightspeed red / Katalyst check dropped analogue). Timer from request.
6. `needs_clearing` : staff settled. Cleared only by manual staff tap -> `available` (Oracle/SpotOn pattern). No auto-expiry.
Transitions: scan -> seated; first order -> ordered; all items bumped -> served; additional order after served -> ordered; bill request -> bill_requested; settle -> needs_clearing; staff tap -> available. Stale-session timeout is a product choice (unsourced).

Default thresholds (all configurable per venue; Square also configures per-venue and publishes no defaults). Warn/late pairs from the RestaurantOwner/SpotOn guidance [S] with my labelling [I]:
- seated, no order: amber 3 min, red 5 min. Basis: greet within 1 min, drinks order 1-2 min, appetizer order within 3 min. The 5-min red matches the reel's example, which is not a standard. Because the guest orders by QR, "no order" means undecided, not unserved: pair with a "call waiter" flag if we have it.
- ordered, not bumped: amber 12 min, red 18 min. Basis: entree goal 10-12 min, 15 max when full. Use ticket-level data if available (items differ).
- served, no bill request: no alert (long dwell is revenue, not a fault); show the elapsed timer only. Optional two-bite check-back is 2 min, too fine for a first version.
- bill_requested, not settled: amber 3 min, red 5 min. Basis: payment within 1 min of presenting; the extra slack covers payment method handoff. Weakest sourcing: choose and say so in the UI copy.
- needs_clearing: amber 2 min, red 5 min. Basis: turn within 2 min of guests leaving.
Alert behaviour: colour + text + icon (colours are not standardised across vendors; accessibility). Alerts derive from elapsed time and clear on the next transition; no dismissal needed, as no vendor documents one. Show elapsed timer on every non-available tile (Square/TouchBistro). Default view for servers: own section; managers: all, with section/server filter (TouchBistro section/server model).
Copy caution: say "no order yet", not "no waiter", since we cannot know waiter presence.

Unverified/skipped: Toast colour key, OpenTable/Resy states, actual table-turn benchmarks, privacy law, Pakistani POS floor-map detail.
