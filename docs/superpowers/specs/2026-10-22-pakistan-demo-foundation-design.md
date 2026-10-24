# Pakistan demo foundation — design

Date: 2026-10-22. Status: approved in brainstorming, pending spec review.
Research: `docs/research/2026-10-22-pakistan-restaurant-research.md` (notes in
`docs/research/2026-10-22-pakistan-notes/`).

## Goal

Turn Mise into a convincing demo for Pakistani restaurants: two fictional PKR venues (a desi
family restaurant in Lahore and a café in Islamabad), menus with portion sizes, table bills with
payment recording and payment-method-dependent sales tax, and real per-restaurant account
isolation. This is priority 1 of the localization roadmap:

1. **This spec:** isolation, venues, portion options, bills and tax, demo data.
2. Later: café counter/pickup flow, kitchen stations, channel and margin analytics.
3. Later: Urdu in the guest app (replaces Italian), WhatsApp `wa.me` share link.

## Non-goals (this phase)

Service charge, split payments, voiding bills, takeaway bills without a table, real payment
processing, any tax-authority integration, Urdu, self-service sign-up, cross-venue comparison.

## Build order

1. Accounts and restaurant isolation (everything else depends on it).
2. Venues, portion options and the PKR seed data.
3. Bills, tax engine, Bills page and sample bill.
4. Simulator, analytics updates, tests and scripts moved to the new venues.

## 1. Accounts and restaurant isolation

A restaurant owner or staff member can only ever see restaurants they belong to. No owner can
learn anything about another restaurant, including whether it exists.

**Today:** one global `owner_api_key` and one `staff_pin`; the `mise_auth` cookie stores only
`role:exp`, so any signed-in user can open any slug.

**Data:**
- `users`: `id`, `email` (unique, stored lower-case), `name`, `password_hash`, timestamps.
  Hash: stdlib `hashlib.scrypt` with a random 16-byte salt per user, stored as
  `scrypt$n$r$p$salt_b64$hash_b64`; verify with `secrets.compare_digest`. No new dependency.
- `memberships`: `id`, `user_id`, `restaurant_id`, `role` (`owner` | `staff`), unique
  (`user_id`, `restaurant_id`).

**Cookie:** `mise_auth` = signed `user_id:exp` (8 hours, httpOnly, same flags as today). No role
in the cookie. Old `role:exp` cookies fail validation (401) and the user signs in again.

**Login:** `POST /api/auth/login` takes `{email, password}`. Same 401 message for unknown email
and wrong password. The existing rate limit (5 failures per 5 minutes per client IP) stays.
`GET /api/auth/me` returns the user's name and email. `owner_api_key` and `staff_pin` are removed
from settings, `.env.example` and docs.

**Access check:** one dependency, `restaurant_access(slug, roles)`, loads the restaurant and the
caller's membership in a single query and returns both.
- No membership, or unknown slug → **404 "Restaurant not found"** (identical responses).
- Member but role not allowed (staff on an owner-only route) → 403.
- Every route with `{slug}` uses it: menu, tables, kitchen orders, kitchen SSE stream, bump,
  bills, brief, what-if, simulator, menu ingest, analytics. The SSE stream checks access before
  subscribing.
- `GET /api/restaurants` (staff or owner) returns only the caller's venues: `slug`, `name`,
  `city`, `role`.

**Guests** are unchanged: the QR token fixes the restaurant and the `mise_guest` cookie is bound
to that session. Guest routes never take a slug from the client for writes.

**Demo accounts** (seeded only when `DEMO_MODE=true`): "Demo owner" with `owner` membership in
both demo venues; one demo staff user per venue. `POST /api/auth/demo-login` takes
`{role, venue?}` and signs in as the matching seeded user; it stays disabled outside demo mode.
Demo users belong to nothing else and no other user belongs to the demo venues.

**Onboarding a client** (no public sign-up): `scripts/admin.py`
- `create-restaurant --slug --name --city --jurisdiction --currency --timezone`
  (rejects a jurisdiction with no tax rates)
- `add-user --email --name --restaurant --role` (prompts for the password; never echoes it)

This works both for one installation per client and for several clients on one installation.

**Owner app:** login page takes email and password. A `useVenue()` hook loads
`GET /api/restaurants`, keeps the chosen slug in `localStorage` (wrapped in try/catch, falls back
to the first venue), and replaces the seven hard-coded `DEFAULT_SLUG` constants. The sidebar
header shows a venue switcher ("Angeethi House · Lahore") when the user has more than one venue,
plain text otherwise.

## 2. Venues and portion options

**Restaurants** gain `city` (text) and `tax_jurisdiction` (text, `PB` or `ICT` for now).

**`menu_item_options`:** `id`, `menu_item_id`, `label` (e.g. "Half", "Full", "½ kg", "1 kg",
"Regular", "Large"), `price`, `unit_cost`, `sort_order`, timestamps.
- A dish with options keeps `menu_items.price` / `unit_cost` equal to its cheapest option, so
  existing readers keep working and the menu can show "from Rs 1,100".
- Dishes without options are unchanged.

**`order_items`** gain `option_id` (nullable FK) and `option_label` (snapshot text). Unit price and
cost are snapshotted from the option. The order request carries `option_id` per line; the server
looks up price and cost and never trusts client numbers. The idempotency payload hash includes
`option_id`.

**Guest menu:** a dish with options opens a `Sheet` with one row per option (label and price) and
an "Add" button; a dish without options adds in one tap as today. Cart lines and the order page
show "Chicken Karahi — Full". The menu header says "Prices exclude sales tax, which is added to
your bill."

**Kitchen ticket** shows `kitchen_name — option_label`.

**Currency:** both venues use PKR. Prices render with the shared `formatPrice` as `Rs 2,100`
(whole rupees, no decimals). The owner app's `eur()` helper is removed.

## 3. Bills and tax

**`bills`:**

| Column | Notes |
|---|---|
| `id`, `restaurant_id`, `table_id` | |
| `bill_no` | Per-venue sequence, assigned at open under the existing restaurant row lock; unique (`restaurant_id`, `bill_no`). Shown as "Bill no. 0042". |
| `status` | `open` or `settled`. Partial unique index: one `open` bill per table. |
| `bill_requested_at` | Set by the guest's "Request bill". |
| `payment_method` | `cash`, `card`, `wallet`, `raast`, `bank_transfer`; set at settle. |
| `payment_reference` | Optional, max 64 chars. |
| `subtotal`, `tax_jurisdiction`, `tax_rate`, `tax_amount`, `total` | Snapshotted at settle. |
| `source` | `live` or `simulated`, like orders. |
| `opened_at`, `settled_at` | |

**`orders`** gain `bill_id`. Placing a table order joins the table's open bill or opens one. Both
order placement and settle lock the bill row; an order arriving after settle opens a new bill. A
unique-index clash on open is retried once. Cancelled orders are excluded from the subtotal.

**Tax rates** live in `data/tax_rates.json`, reviewed in git:

```json
[
  {"jurisdiction": "PB",  "payment_class": "standard", "rate": "0.16", "effective_from": "2026-07-01",
   "source": "Punjab Sales Tax on Services Act 2012, Second Schedule Part III S/N 4(b), as amended by Punjab Finance Act 2026 (L of 2026), in force 1 July 2026"},
  {"jurisdiction": "PB",  "payment_class": "digital",  "rate": "0.08", "effective_from": "2026-07-01",
   "source": "Same, S/N 4(a): eight percent without input tax adjustment, payment by debit or credit card, mobile wallet or QR scanning (was five percent)"},
  {"jurisdiction": "ICT", "payment_class": "standard", "rate": "0.15", "effective_from": "2023-07-01",
   "source": "ICT (Tax on Services) Ordinance 2001, Schedule Table-1 S/N 1(ii)(b), as amended up to 30-06-2025 (FBR); entry substituted by Finance Act 2023; not changed by Finance Act 2026"},
  {"jurisdiction": "ICT", "payment_class": "digital",  "rate": "0.05", "effective_from": "2023-07-01",
   "source": "Same, S/N 1(ii)(a): five percent, payment by debit or credit card, mobile wallet or QR scanning, no input tax adjustment"}
]
```

**Verified 2026-10-24 against official texts** (`docs/research/2026-10-24-tax-rate-verification.md`):
the enacted Punjab Finance Act 2026 (punjablaws.gov.pk), PRA's 17th-edition consolidated Act
2026-27, FBR's ICT Ordinance amended up to 30-06-2025, and the federal Finance Act 2026 (which
does not amend the ICT Ordinance).

- The reduced rate applies only to **debit or credit card, mobile wallet or QR scanning**. So
  `card`, `wallet` and `raast` (Raast QR) → class `digital`; `cash` and `bank_transfer` → class
  `standard`. Punjab's law says "sixteen percent for others", so bank transfer is 16% there. ICT's
  text says "fifteen percent where payment received in cash" and is silent on bank transfer; we
  apply the standard rate and label that as our assumption.
- `tax_for(jurisdiction, payment_method, on_date, subtotal) -> (rate, amount)`: pure function; picks
  the latest entry with `effective_from <= on_date`; amount rounded half-up to whole rupees.
- The file is validated at startup (rates in [0, 1], unique jurisdiction/class/date, known
  classes); an invalid file stops the API from starting.

**API** (all with `response_model`):
- `GET /api/restaurants/{slug}/bills?status=open|settled` (staff or owner): table label, bill no.,
  opened time, order count, running subtotal, `bill_requested_at`.
- `GET /api/restaurants/{slug}/bills/{id}`: lines grouped by dish and option (name, option, qty,
  unit price, line total), subtotal, and two server-computed previews: cash (rate, tax, total) and
  card, wallet or QR (rate, tax, total). Settled bills also return the snapshot.
- `POST /api/restaurants/{slug}/bills/{id}/settle` `{payment_method, payment_reference?}`: 409 if
  already settled, 422 if no active orders or no tax rate for the date (bill stays open, error
  logged). Publishes a bill event on the venue's channel.
- `POST /api/guest/bill-request` (guest cookie): 404 if the session's table has no open bill;
  idempotent. Publishes a bill event.

**Owner app — Bills page** (nav item, staff and owner):
- Open bills for the current venue, live over SSE, "Bill requested" chip, requested bills first.
- Detail: grouped lines, subtotal, cash vs digital previews side by side, payment method buttons
  (Cash, Card, JazzCash/Easypaisa, Raast QR, Bank transfer), optional reference, "Mark paid".
- After settle: the printable sample bill.

**Guest app:** "Request bill" on the order status page → "Bill requested — a waiter will bring it
to your table." After settle: "Paid · Bill no. 0042 · thank you".

**Sample bill** (print page, 80 mm, browser print): venue name and city, "Bill no.", date and
time, table, lines with options, subtotal, "Sales tax (illustrative) 8% — digital payment",
total, payment method. Footer, always:
**"Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority."**
Never: a fiscal invoice number, a QR code, an FBR or provincial authority logo, the word
"invoice" outside that footer, "FBR integrated" or "compliant". An unsettled bill's print page
shows "Not settled yet" only.

## 4. Demo data and simulated history

`data/seed/trattoria_da_mario.json` is replaced by:

- **`angeethi_house.json`** — slug `angeethi-house`, Lahore, `PB`, PKR, `Asia/Karachi`,
  languages `["en"]`. Tables T1–T8 and family hall F1–F4 (labels only). About 30 dishes: BBQ
  (chicken tikka, seekh kebab, malai boti), Karahi (chicken, mutton; Half/Full or ½ kg/1 kg),
  Handi (boneless; Half/Full), Daal & Sabzi, Rice (biryani single/double, pulao), Tandoor (roti,
  naan, garlic naan, cheese naan), Sides (raita, salad), Desserts (kheer, gulab jamun), Drinks
  (lassi, fresh lime, soft drink, mineral water small/large, chai).
- **`kehwa_and_crumb.json`** — slug `kehwa-and-crumb`, Islamabad, `ICT`, PKR, `Asia/Karachi`,
  languages `["en"]`. Tables T1–T8. About 28 items: Hot coffee (americano, cappuccino, latte,
  Spanish latte; Regular/Large), Iced (iced latte, caramel frappé; Regular/Large), Chai & Kehwa
  (karak, kashmiri, green kehwa), Bakery (croissant, almond croissant, brownie, banana bread),
  Breakfast (pancakes, French toast), Sandwiches (club, chicken pesto melt), Desserts
  (cheesecake, molten lava cake).

Prices sit inside the research's 2025–26 ranges (e.g. chicken karahi ½ kg Rs 1,100 / 1 kg
Rs 2,100, mutton karahi 1 kg Rs 4,500, naan Rs 60, cappuccino Rs 650 / 790, croissant Rs 450).
Unit costs use the research's estimated food-cost bands (mutton 40–48%, daal ~20%, breads ~15%,
coffee ~30%). Allergens follow standard recipes with `allergen_verified: false`. Each file has a
`"_note"` saying prices and costs are illustrative. IDs: `uuid5(namespace, "slug:item_key")` and
`uuid5(namespace, "slug:item_key:option_label")`. `scripts/seed.py` matches items by `key`, no
longer by the Italian name.

**Simulator** (extended, still pure and seeded):
- Each seed file has a `simulation` block overriding `SimAssumptions`. Angeethi: lunch 13–16,
  dinner 20–23, weekends ~1.8× weekdays, larger parties. Kehwa: afternoon 15–18 (counted as
  `lunch`), evening 20–23 (`dinner`, matching Islamabad's 2026 11pm dine-in cut-off), parties of
  1–3.
- Item popularity comes from a per-item `sim_weight` in the seed (replacing the random
  permutation); option choice from `option_weights`.
- Each simulated party is one bill, settled 45–75 minutes after placement, payment method drawn
  from the venue's mix (assumption, labelled in `docs/analytics.md`): Angeethi cash 60 / card 20 /
  wallet 15 / raast 5; Kehwa cash 35 / card 40 / wallet 15 / raast 10. Tax via `tax_for`.
  Bills and orders are `source='simulated'`.

**Analytics:**
- `_eur` fields are renamed (`revenue`, `unit_margin`, `contribution`, `aov`,
  `contribution_margin`, `estimated_impact_per_week`); the brief returns `currency`.
- Menu engineering groups by (dish, option): "Chicken Karahi — Half" and "— Full" are rows.
- New brief block **payment mix and tax**: share of settled bills and revenue by cash vs digital,
  tax collected per rate, and "digital tax saving" (tax at the cash rate minus tax actually
  charged on digital bills). Code computes every number; the model only phrases, and the summary
  passes the existing number check.

**Other moves:** `demo_restaurant_slug` becomes `demo_restaurant_slugs`; `/api/demo/info` returns
a table QR per venue; `simulate.py`, `verify_phase1.sh`, `verify_d.sh` and `e2e/flows.spec.ts`
use `angeethi-house` (plus one Kehwa order in e2e). All `trattoria-da-mario` references and the
Italian seed are removed. The `it` code path stays until Urdu replaces it (priority 3).

## 5. Error handling

| Situation | Result |
|---|---|
| Wrong email or password | 401 "Invalid credentials" (same for both); rate limit unchanged |
| Old-format or expired cookie | 401; owner app redirects to login |
| Not a member / unknown slug | 404 "Restaurant not found" |
| Staff on owner-only route | 403 |
| Unknown option, option of another dish, missing option on a dish with options | 422 |
| Order during settle | Bill row lock; later request sees settled and opens a new bill |
| Settle settled bill | 409 |
| Settle bill without active orders | 422 |
| Reference over 64 chars | 422 |
| Bill request without open bill | 404; repeat is idempotent |
| No tax rate for date | 422 "No tax rate configured", logged, bill stays open |
| Invalid `tax_rates.json` | API fails to start with a clear message |
| Print page for unsettled bill | "Not settled yet", no bill |

Money is `Decimal` throughout; tax is rounded once, on the bill.

## 6. Testing

Existing tests move to the new accounts and venues; none are weakened, skipped or marked xfail.

- **Unit:** `tax_for` (PB cash 16%, PB card 8%, ICT wallet 5%, date before a rate starts,
  Rs 0.50 rounding); tax file validation; scrypt hash and verify; option snapshot; simulator
  determinism and payment mix within tolerance; sample bill always has the footer and no other
  "invoice".
- **API (Docker):** isolation test that walks the FastAPI route table and asserts 404 across
  venues for every `{slug}` route; login and roles; orders with options; bill lifecycle (open,
  add order, request, settle, new bill); parallel settle vs order; the 409 and 422 cases; brief
  payment mix and `currency`.
- **Migrations:** up, down and check (already in `make verify-f`).
- **Frontend (Vitest):** `useVenue` storage fallback, option picker logic, `formatPrice` PKR.
- **Browser (Playwright):** demo owner switches venues; guest orders a Full karahi plus naan and
  requests the bill; staff see the chip, settle by card, sample bill shows 8% and the footer; a
  Kehwa order reaches its kitchen; Kehwa staff opening Angeethi gets "not found".
- `make verify-f` passes all 10 steps on a fresh stack.

## Project rule changes

- `CLAUDE.md`: auth is per-user with restaurant memberships; every `{slug}` route uses
  `restaurant_access`; demo bills must never imitate a tax invoice. (The language rule changes in
  priority 3.)
- `README.md` and `docs/` describe only what is implemented and tested.

## Open assumptions (verify with real owners)

Payment mix, whether service charge is customary and taxed, how split payments are taxed, the
ICT rate for bank transfers, Sindh and KP rates (not used by the demo venues, unverified),
family-hall table labelling, café pickup by token, kitchen ticket language. Full list in the
research report.

## Follow-up idea (not in this spec)

**Floor view / table alerts** (inspired by a reel on camera-based table monitoring): a live table
board — free, seated, ordered, waiting, bill requested, needs cleaning — with alerts such as
"Table 2 seated 5 min, no order". Mise can derive this from data it already has (QR scan opens a
guest session, orders, bill request, settle) with no cameras, which avoids video privacy issues,
hardware cost and the free-only rule. Candidate for priority 2 alongside kitchen stations.
