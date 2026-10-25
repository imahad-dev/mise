# Table self-service, counter pickup, Floor view and pay-it-forward — design

Date: 2026-10-25. Status: approved in brainstorming, pending spec review. Builds on
`feat/pakistan-foundation` (spec `2026-10-22-pakistan-demo-foundation-design.md`).
Research: `docs/research/2026-10-25-cafe-counter-notes.md`,
`docs/research/2026-10-25-floor-view-notes.md`.

## Goal

Let a guest do everything from their phone — order, call a waiter, choose how to pay and report
a payment — while staff stay in control of every rupee. Add counter/pickup ordering for both
venues, a live camera-free Floor view with service-timing alerts, and a pay-it-forward chai.
Zero tolerance for money errors: the amount staff confirm is always the amount recorded.

## Non-goals

Real payment processing or bank verification of transaction ids (impossible without a gateway;
staff check their own banking app), refunds, split payments, service charge, server sections,
sound or push alerts, SMS, a public "Now serving" screen, counter history in the simulator,
channel-margin analytics, Urdu.

## 1. Guest flows

### At a table (both venues)
- Ordering unchanged (menu, size picker, tax note, more rounds onto the table's open bill).
- **Call waiter** (menu and order pages): reasons `help` "Need help", `water` "Water, please",
  `extra` = the venue's `service_extra_label` (Angeethi "More naan / roti", Kehwa "More napkins /
  cutlery"). Afterwards the button reads "Waiter called · m:ss" until resolved. One open call
  per table; a new call is refused for 60 s after the previous one.
- **Pay bill** (order page) replaces "Request bill". A sheet shows lines, subtotal and the total
  for each method: Cash, Card, JazzCash / Easypaisa, Raast QR, Bank transfer, each with its tax
  rate. Choosing a method records a claim and also counts as requesting the bill:
  - Cash → "A waiter is coming to collect Rs X."
  - Card → "A waiter is bringing the card machine."
  - JazzCash / Easypaisa / Raast QR / Bank transfer → the venue's payment details with copy
    buttons; the guest pays in their own app, enters the transaction id, taps "I've paid" →
    "Payment sent — waiting for staff to confirm."
  - Demo venues show the details inside a banner: "Sample payment details — demo only. Do not
    send money." Sample values are visibly invalid (`0000 SAMPLE`).
  - The guest may change method until staff confirm; the latest claim wins.
  - Settled → "Paid · Bill no. 0042 · thank you." If the bill contained pay-it-forward chai:
    "You bought N chai for someone who needs it. Shukriya."

### At the counter (Kehwa "Counter / Pickup", Angeethi "Takeaway / Parcel")
1. The counter QR's menu header says "Counter order — pay first, then collect".
2. After ordering the guest sees a large pickup number (`K-042` at Kehwa, `P-042` at Angeethi)
   and the same Pay sheet ("Pay at the counter or from your phone").
3. Staff confirm payment → the order reaches the kitchen → "Paid — preparing your order".
4. Kitchen bump → "Ready — collect K-042 at the counter".
5. Staff tap Collected → "Collected · enjoy!"
- No Call waiter on counter sessions. A paid counter order cannot be added to; a further purchase
  is a new order. Unpaid, unclaimed counter orders expire after 30 minutes.
- Pickup numbers run per venue per local day from 001 upward and never wrap (K-1000 follows
  K-999). Uncollected orders from an earlier day show a "Yesterday" tag.

## 2. Staff screens

### Floor view (`/floor`, first in "Service", staff and owner)
Tiles per table (counter tables excluded): label, state text + icon + colour, time in state,
running total, open call reason. Red first, then amber, then table order; a list on phones.

| State | Rule | Amber / red |
|---|---|---|
| Free | no guest session started after `cleared_at` and no open bill | — |
| Seated, no order | a session started after `cleared_at`, no open bill | 3 / 5 min |
| Ordered | open bill with at least one `placed` order | 12 / 18 min from the oldest `placed` order |
| Served | open bill, every active order bumped | timer only |
| Paying | open bill with a claim or `bill_requested_at` | 3 / 5 min from the claim/request |
| Needs clearing | latest bill settled after `cleared_at`, no newer open bill | 2 / 5 min from settle |
| Waiter called | an open service call — overrides all of the above | red immediately |

Precedence: Waiter called > Paying > Ordered > Served > Seated > Needs clearing > Free (an open
bill always outranks Needs clearing, so dessert after paying shows Ordered).
Actions: Done (resolve call), Mark cleared, Open bill. Sidebar badge "Floor (n)" = red + amber
tiles. Timers tick client-side from the server's `server_time` offset; tiles reload on events
from the kitchen SSE channel and every 30 s. A pay-it-forward tile shows "Pay-it-forward chai:
N waiting" with "Give one".

### Bills page
- Tabs Tables / Counter. Rows show claim chips: "Guest paying: Raast · ref 4471…",
  "Guest paying: cash", "Card machine requested".
- Confirm sheet: table or pickup number, amount and reference in large type, the instruction
  "Check your JazzCash / bank app for ref … and Rs … before confirming", method pre-filled from
  the claim and changeable, warnings for amount mismatch and reused reference (§4), then
  "Confirm received".
- Each order on a table bill shows "New device" when its guest session differs from the first
  session on that bill; staff can **void** a `placed` or `bumped` order with a reason before the
  bill is settled.
- Counter tab: Awaiting payment (Confirm received / Cancel), Preparing, Ready (Collected, with
  60 s Undo).

### Kitchen display
Counter tickets show "PICKUP K-042" in large type. Pay-it-forward handouts show
"PAY-IT-FORWARD · Chai". Unpaid counter orders never appear.

### Owner settings (Tables & QR page)
Payment details (Raast ID, JazzCash, Easypaisa, IBAN, account title), pickup prefix, extra call
reason. The counter QR is listed and printable like table QRs. Demo venues keep `sample: true`
(cannot be switched off while `DEMO_MODE`).

## 3. Data model and API

### Migration `0011_floor_counter`
| Where | Change |
|---|---|
| `dining_table` | `kind` text `table`/`counter` (default `table`, check), `cleared_at` timestamptz null |
| `restaurant` | `pickup_prefix` text null, `service_extra_label` text null, `payment_details` JSONB default `{}` |
| `orders` | status adds `awaiting_payment` (check updated); `collected_at`, `collected_by` (user id), `voided_at`, `voided_by`, `void_reason` |
| `bills` | status adds `cancelled` (check updated; cancelled bills need `cancelled_at`, `cancelled_by`, `cancel_reason`); `pickup_day` date null, `pickup_no` int null, unique (`restaurant_id`, `pickup_day`, `pickup_no`); `claimed_method`, `claimed_reference` (≤64), `claimed_total`, `claimed_at`; `settled_by` (user id) |
| new `service_call` | `id`, `restaurant_id`, `table_id`, `reason` (`help`/`water`/`extra`), `created_at`, `resolved_at`, `resolved_by`; partial unique (`table_id`) where `resolved_at is null` |
| new `pay_forward` | `id`, `restaurant_id`, `kind` (`bought`/`given`), `quantity` int > 0, `order_id` null, `user_id` null, `created_at`; balance = Σ bought − Σ given |

Voided orders use status `cancelled` plus the void columns; "active orders" already exclude
`cancelled`. Pay-it-forward chai is a normal menu item flagged in seed data by key
`pay_forward_chai`; settling a bill writes one `bought` row per such line quantity.

### Behaviour
- **Counter QR** = `dining_table.kind='counter'`. Orders keep that `table_id`. Each counter order
  opens its own bill (`table_id` null on the bill, `bill_no` assigned, `pickup_day` = local date,
  `pickup_no` = max for that day + 1) under the existing per-restaurant advisory lock. The order
  starts `awaiting_payment`.
- **Settling** a counter bill flips its order to `placed` and publishes `order_placed`. Settling
  any bill writes pay-forward `bought` rows and records `settled_by`.
- **Expiry**: when the counter list is read, unpaid and unclaimed counter orders older than 30
  minutes are cancelled (with their bills cancelled — bills gain status `cancelled`), under row
  locks, in the same transaction.
- **Claims** set `claimed_*` and `bill_requested_at`; they never settle.
- **Floor state** is one pure function `table_state(facts, now, thresholds) -> TileState` fed by
  one query per venue.
- **Analytics** exclude `awaiting_payment` and `cancelled` orders and cancelled bills; pay-forward
  handouts never count as revenue (no bill).

### API (every route has a response_model; staff routes use `restaurant_access`)
Guest (guest cookie):
- `GET /api/guest/bill` — lines, per-method previews, payment details (+sample flag), claim,
  pickup number, order status, pay-forward thank-you count.
- `POST /api/guest/bill/payment` `{method, reference?}` — reference required for wallet, raast,
  bank_transfer; idempotent for the same method + reference.
- `POST /api/guest/service-calls` `{reason}`; `GET /api/guest/service-calls/current`.

Staff:
- `GET /api/restaurants/{slug}/floor` — tiles, counts, thresholds, `server_time`, pay-forward
  balance.
- `POST …/tables/{table_id}/clear`
- `POST …/service-calls/{call_id}/resolve`
- `GET …/bills?kind=table|counter&status=…`
- `POST …/bills/{bill_id}/settle` — now requires `expected_total` and `expected_method`.
- `POST …/bills/{bill_id}/cancel` `{reason}` — unpaid counter bills only.
- `POST …/orders/{order_id}/void` `{reason}` — orders on an open bill.
- `POST …/orders/{order_id}/collect`, `POST …/orders/{order_id}/uncollect` (within 60 s).
- `POST …/pay-forward/give` `{quantity: 1}`.
Owner: `PATCH …/settings` `{payment_details?, pickup_prefix?, service_extra_label?}`.

Events on `kitchen:{restaurant_id}`: `service_call_opened`, `service_call_resolved`,
`payment_claimed`, `table_cleared`, `order_voided`, `order_collected`, `pay_forward_given`, plus
existing `order_placed`, `bill_*`. Payloads carry ids only.

## 4. Safeguards (zero margin for money errors)

1. **Claimed total**: the claim stores `claimed_total`; if the bill total later differs, staff see
   "Guest sent Rs A · bill is now Rs B · Rs (B−A) still due" (or "Rs … overpaid").
2. **Expected total on settle**: settle sends `expected_total` and `expected_method`; the server
   recomputes under the row lock and returns 409 with the fresh bill if either differs (new order,
   void, method change, rate change at midnight).
3. **Reused reference**: a claim reference already used on another bill of the same venue in the
   last 7 days is flagged; confirming needs `acknowledge_reused_reference: true`.
4. **No auto-settle**: nothing settles without a staff action; the confirm sheet tells staff to
   check their banking app.
5. **New device + void**: orders from a session other than the bill's first session are marked;
   staff can void with a reason; voids are audited.
6. **Accountability**: settle, void, cancel, collect, uncollect, clear, resolve and give record the
   user id (columns above and `audit_log`).
7. **Expiry vs claims**: expiry skips claimed bills; cancelling a claimed bill requires a reason
   and shows "Guest says they paid by … — any refund happens outside Mise".
8. **Collect undo** within 60 s.
9. **Payment detail validation**: IBAN `PK` + 22 characters (24 total) with mod-97 checksum;
   JazzCash/Easypaisa numbers `03` + 9 digits; Raast ID is a valid mobile number or IBAN; account
   title 2–80 characters. Demo sample values bypass validation only when `sample: true` and are
   always shown under the demo banner.
10. **Pickup numbers** unique per venue per day; no wrap; older uncollected orders tagged.
11. **Pay-forward balance** never below zero (locked decrement); handouts are not revenue.
12. **Privacy**: payment references and details never reach the language model or brief facts.

## 5. Error handling

| Situation | Result |
|---|---|
| Claim or settle on a settled bill | 409 |
| Method outside the five, or missing reference for wallet/raast/bank | 422 |
| Reference > 64 chars or with control characters | 422 |
| Settle with stale `expected_total`/`expected_method` | 409 + fresh bill |
| Reused reference without acknowledgement | 409 with the other bill number |
| Clear a table with an open bill | 409 "Settle the bill first" |
| Collect an order that isn't bumped, or uncollect after 60 s | 409 |
| Cancel a paid bill, or a claimed bill without reason | 409 / 422 |
| Void on a settled bill, or void the last active order then settle | 409 / settle 422 "No active orders" |
| Service call from a counter session | 422 |
| Second open call / call within 60 s | 409 / 429 |
| Pay-forward give with balance 0 | 409 "None waiting" |
| Non-member or another venue's ids | 404 |
| Invalid payment details | 422 with the field |

## 6. Testing

1. **Money agreement (pure + property tests)**: for random subtotals, methods, venues and dates,
   guest preview = staff preview = settle = printed bill = analytics; exact cases at .50 and
   across 1 July 2026 (preview 23:59, settle 00:01 → 409). After random sequences of order, void,
   claim, settle: brief revenue = Σ settled subtotals; unpaid/voided/cancelled never counted.
2. **Concurrency (real database, parallel clients)**: two staff confirm one bill → one wins;
   claim + new order + settle on one table ×20 → no lost order, totals add up, never settled at a
   wrong amount; 30 simultaneous counter orders → pickup 001–030, no gaps or repeats; expiry vs
   settle → paid-and-placed or expired, never both; double-tapped waiter call → one call; two
   "Give one" taps with balance 1 → one succeeds.
3. **Guest abuse and failure**: double "I've paid" and retry after a dropped connection → one
   claim; Raast → cash → card → latest wins; session expiry and re-scan → same bill, can pay;
   guessed ids for other tables/venues → 404; `<script>`/emoji/500-char references → rejected or
   inert text; every order-page state before the bill exists, while paying, after paying.
4. **Owner and staff failure**: clear with open bill refused; void last order → settle refused;
   collect before bump refused; cancel paid refused; isolation test covers every new `{slug}`
   route plus id-crossing tests on floor, tables, calls, bills, orders, pay-forward; brief facts
   scanned for payment references (none).
5. **Floor view**: every transition and precedence case (dessert after paying, scan before last
   clear, call overriding and clearing); thresholds at exactly 3/5/12/18/2/5 min; timers correct
   with a client clock 10 minutes off.
6. **Browser stories (Playwright)**:
   1. Angeethi family: 1 kg karahi + naan, call for water, pay by Raast with a reference, staff
      confirm and print, table → Needs clearing → Free.
   2. Guest chooses Raast then cash; staff confirm the cash total at 16%.
   3. Chai ordered during a pending payment: "Rs … still due" shown; first confirm refused and
      refreshed.
   4. Kehwa counter: K-001; barista sees nothing until cash is confirmed; kitchen → Ready on the
      phone → Collected → Undo → Collected.
   5. An unpaid counter order backdated 31 minutes disappears from the queue.
   6. A second phone orders on T3: "New device" shown; staff void it with a reason.
   7. Two staff browsers confirm the same bill: one wins, the other sees "already settled".
   8. A guest buys a pay-it-forward chai; the tile shows 1 waiting; staff give one; the kitchen
      shows the PAY-IT-FORWARD ticket; the tile shows 0 and "Give one" is disabled.
   9. All guest screens at 360 px with slow-3G throttling; "I've paid" survives a dropped
      connection.
7. `make verify-f` passes all steps on a fresh stack.

## 7. What a real deployment must still verify

The demo cannot check a transaction id with a bank. Confirming a digital payment is a staff check
of the venue's own banking or wallet app; the confirm sheet says so, and the README states it.

## Project rule changes

`CLAUDE.md` Architecture: "Guests never settle bills; every settle carries the expected total and
method and is refused on mismatch." README describes only what is implemented and tested.
