# Safer table ordering, smarter Floor view and daily service report — design

Date: 2026-10-31. Status: approved in brainstorming, pending spec review. Builds on
`feat/pakistan-foundation` (merged to `main` in `d9ef7bd`), which added the Floor view, call
waiter, pay-at-table and counter pickup.
Research: `docs/research/2026-10-30-venue-brands-guest-ux-security.md`.

This is sub-project 1 of the new direction (per-venue branding, a simpler guest app, overseas
venues, Mise's own identity). Sub-projects 2 (currency/tax engine) and 3 (brand kits and
archetypes) are separate specs; this one does not touch pricing, currency or theming.

## Goal

Close the remote fake-order gap a QR menu has today — anyone who photographs or guesses a
table's QR code can order and never show up — without adding friction a real guest notices.
Staff open a table before it can order and approve its first order with one tap; after that,
ordering is as fast as it is today. Make the existing Floor view show the new waiting moments as
alerts, and add a daily service report built only from recorded times. No cameras, no new guest
accounts, no technical words on any guest or staff screen — everyday restaurant language only
(waiter, table, order, bill, kitchen, ready).

## Non-goals

Camera-based or computer-vision table monitoring (a later, separate sub-project if a venue ever
asks for it — see the research doc); a "food delivered to the table" tap (the kitchen's existing
ready/bump already marks this); split payments, service charge, server sections; SMS or push
alerts; changing counter/pickup ordering (it already pays before the kitchen starts, which is
equivalent protection); currency, tax or branding work (separate specs).

## 1. The sitting

A **sitting** is one party's visit to one table, from when staff open it to when it closes.

New table `table_sitting`:
- `id`, `table_id` (FK `dining_table`, cascade delete)
- `opened_at`, `opened_by_user_id` (FK `user`)
- `code` (4 digits, text, nullable — set only when the venue requires a code)
- `code_required` (bool, snapshot of the venue's setting at open time, so a later settings change
  never invalidates a code a guest already has)
- `closed_at`, `close_reason` (`settled` | `cancelled` | `staff_closed` | `idle_timeout`),
  nullable until closed
- Index on `(table_id, closed_at)` — the open sitting for a table is the row with
  `closed_at IS NULL`; a `CheckConstraint` and a partial unique index
  (`WHERE closed_at IS NULL`) guarantee at most one open sitting per table.

`Restaurant` gains two columns: `sitting_code_required` (bool, default `true` for the two
overseas venues and `false` for the two local ones, per the brainstorming decision — each owner
can change it) and `first_order_cap_multiplier` (numeric, default `4`, used in §3).

`Order` gains `sitting_id` (FK `table_sitting`, nullable — null for counter/pickup orders, which
have no sitting) and a new status value: the existing
`status IN ('awaiting_payment', 'placed', 'bumped', 'cancelled')` check becomes
`status IN ('awaiting_payment', 'pending_approval', 'placed', 'bumped', 'cancelled')`.
`pending_approval` is only reachable for a table order that is the first in its sitting.

### Opening, closing, idle timeout

- **Open:** a staff action on a Floor tile, `POST /api/restaurants/{slug}/tables/{id}/sitting`.
  Creates the sitting; if `sitting_code_required`, generates a random 4-digit code and returns it
  for staff to read aloud. Fails 409 if a sitting is already open (the Floor tile already shows
  "Open table" only on a `free` tile, so this is a race guard, not the main UI path).
- **Close (staff):** `DELETE` on the same resource, `close_reason='staff_closed'`. Refused (409)
  if the table has an open, unsettled bill — "Settle the bill first" — because money must never
  be left behind.
- **Close (settle/cancel):** the existing settle and cancel-bill code paths close the table's open
  sitting as their last step, inside the same transaction, with `close_reason='settled'` or
  `'cancelled'`.
- **Idle timeout:** a sitting with no order, call or payment activity for 90 minutes closes
  itself. Implemented the same way the existing guest-session cleanup runs (periodic job), not a
  live check on every request, so there is no per-request latency cost. "Activity" = any `Order`,
  `ServiceCall` or bill-claim row referencing the sitting/table with a newer timestamp than
  `opened_at`. An open unpaid bill is never idle-closed (same rule as staff close).

### Guest session binding

`GuestSession` gains `sitting_id` (nullable FK, set the first time a guest on that table
successfully places or confirms an order against an open sitting — not at QR scan, since
browsing must work before the table is open). A session only orders against its own sitting; if
the sitting closes, the session's next order attempt gets the "table closed" guest message
(§2), not a 404 or 500.

## 2. The code and the guest order path

When `sitting_code_required` is true, a session's **first order attempt** (not browsing) for a
table prompts for the 4-digit code via a modal, once per phone. `POST .../guest-sessions/{id}/verify-code`
checks it against the open sitting's `code`; on success the session's `sitting_id` is set and no
further prompts occur for that phone for that sitting. 5 wrong attempts in a row → 60-second
lock, tracked in Redis by session id (same pattern as `enforce_ip_limit`), reset on a correct
code or when the sitting closes.

Guest order submission (`POST .../orders`) now branches on table state, each with its own guest
message, never a bare error:

| Table state | Guest sees | Server behaviour |
|---|---|---|
| No open sitting | Bottom bar: "Your table will be ready in a moment. A waiter is on the way." + "Call waiter" button. Order button disabled. | `GET` table/session status returns `sitting_open: false`; the guest-web polls this on the existing SSE channel so the bar switches the moment staff open the table — no reload. |
| Sitting open, code required, not yet verified | Code modal on first order attempt. | 403 with a machine code the guest-web maps to the modal; never shown as raw text to the guest. |
| Sitting open, verified (or no code required), first order of the sitting | "Sent! Your waiter is confirming your order." | Order created with `status='pending_approval'`. Not sent to kitchen yet. |
| First order approved | "Confirmed, it's being cooked" (live update via existing SSE, no refresh). | Staff approval moves `status` to `placed`; kitchen sees it from this point. |
| First order declined | "Your waiter will come to your table to help." (never "rejected") | Staff decline cancels the order (`status='cancelled'`, `voided_at` set) and returns the cart contents to the guest-web so nothing is lost. |
| Any later order in the sitting | Goes straight to `placed`, as today. | No approval step after the first. |
| Table closed mid-session | "Thanks for visiting!" + link to the menu. No error screen. | Order endpoint returns a specific closed-table response instead of creating a row. |

**Rate and size limits** (server-side, in addition to the existing IP limit):
- 3 orders per guest session per 5 minutes.
- 30 items per order.
- The first order of a sitting is capped at `avg_menu_item_price × first_order_cap_multiplier`
  (computed from that restaurant's current menu, not cached, since menus change rarely and this
  only runs once per sitting). Over the cap: the order is still created as `pending_approval` —
  never silently blocked — with a flag so the guest-web shows "That's a big order! Your waiter
  will confirm it with you." instead of implying an error.

All of the above are additions to `routers/guest.py` and `services/` — no existing call-waiter,
pay-at-table or counter-pickup behaviour changes.

## 3. Floor view and staff screens

**New Floor tile states**, added to the existing `free | seated | ordered | served | paying |
needs_clearing | called` set in `services/floor.py`:
- `free` tile gains a sub-state when a guest session exists on that table with no open sitting:
  shown as the same `free` tile but with a pulsing badge "Guests waiting to order · m:ss",
  timed from the guest session's `created_at`. Alert thresholds (reusing the existing
  amber/red `THRESHOLDS` pattern): amber at 1 minute, red at 3.
- New state `approval_needed`: a sitting has an order with `status='pending_approval'`. Shown as
  "Approve · N items · {total}" with **Approve** / **Not now** buttons directly on the tile, and
  pushed to the top of the Floor board as a red alert once past 2 minutes (amber at 1 minute).
  This takes priority over `seated`/`ordered` for display, since it blocks the kitchen.
- The existing `seated` timer now starts from `table_sitting.opened_at` rather than from the
  guest session, since the sitting is the more accurate "party is here" signal and staff action
  (not a guest's phone connecting) is what should start the clock.

`Open table` and `Close table` become tile actions, following the existing Floor tile action
pattern (same place as today's "Call waiter" acknowledgement). `Show code` (when one was
generated) displays the 4 digits in large text for staff to read aloud; it never appears on any
guest-facing screen or printed ticket.

**Approve/Not now** calls `POST .../orders/{id}/approve` or `/decline`. Both are idempotent: a
second tap after the first succeeded returns the current state rather than erroring, and if
Approve and Not now are tapped by two staff within the same race, whichever the database commits
first wins (optimistic row lock on the order, same technique the existing bump/void endpoints
use) and the loser's tap shows "Already handled."

All of this is additions to `routers/floor.py`, `services/floor.py` and the owner-web
`FloorTile`/`floor.ts` files — the existing tile rendering, sorting and SSE wiring are extended,
not replaced.

## 4. Daily service report

A new card under Reports in the owner app, computed entirely from `table_sitting`, `Order` and
`ServiceCall` timestamps — no new tracking, no model involvement beyond phrasing the one-line
summary (which must pass the existing `narrative.py` number-consistency check, same as every
other report).

Numbers shown, for a chosen day:
- **Tables served** (count of sittings with `close_reason` in `settled`/`cancelled` that day) and
  **average time per table** (`closed_at - opened_at`).
- **Average wait per stage:** sitting opened → first order placed; order placed → kitchen bump;
  bill requested → settled. Each computed from existing timestamps already on `Order`/`Bill`.
- **Busiest hour** and **slowest hour** (by average total table time), with which stage drove the
  slowest hour.
- **Alerts today:** a count of tiles that reached `red` for each reason (seated-no-order,
  order-no-kitchen-bump, approval-needed, bill-not-settled), derived by replaying the same
  `_level()` thresholds in `services/floor.py` against the day's recorded timestamps — not a
  separate alert log, so there is one source of truth for what counts as "late."
- Simulated-demo sittings are counted separately and labelled, following the same
  `source IN ('live','simulated')` split the analytics scope already uses.

This is a new `services/service_report.py` (pure functions, following the `services/floor.py`
style of taking plain data in and returning plain data out) plus one router endpoint and one
owner-web page section.

## 5. Error handling

- **Two staff act on the same thing at once:** covered per-case in §2 and §3 (idempotent
  approve/decline, optimistic locking, "Already handled").
- **Phone or connection drops:** the guest-web already recovers cart and order state on reload
  (existing behaviour); the existing idempotency key on order creation prevents a dropped
  request from being double-submitted when retried. No new mechanism needed here.
- **Nobody approves the first order:** it turns red at 2 minutes on the Floor board and stays
  `pending_approval` indefinitely — never auto-approved (money/food risk) and never auto-cancelled
  (a guest who is genuinely waiting must not lose their order silently).
- **Closing a table with money outstanding:** refused with "Settle the bill first", covered in
  §1; this is the one case where staff cannot close a table, by design.
- **Sitting closes while a guest is mid-checkout:** the Pay sheet (existing pay-at-table flow) is
  unaffected, since a bill belongs to the table/session already and settling it is what closes
  the sitting in the first place — there is no ordering path left to block.

## 6. Testing

- **API unit/integration tests:** open/close/idle-timeout state machine for `table_sitting`;
  code verification success, failure, and lockout; first-order approval/decline and the status
  transition it drives; the two staff-race cases in §3; the 3-orders-per-5-minutes and
  30-item limits; the first-order cap flag.
- **Floor service unit tests:** new tile states and their alert thresholds, following the
  existing `floor.test.ts`/`test_floor.py` pattern of pure-function tests on `TableFacts`.
- **Service report unit tests:** each computed number against a constructed set of sittings and
  orders with known timestamps, including the busiest/slowest-hour and alert-count logic.
- **End-to-end test** (extends `e2e/self-service.spec.ts`): scan while closed → see the waiting
  message → staff open the table → guest places first order → staff approve → guest places a
  second order (goes straight to kitchen) → guest pays → staff settle → sitting closes → table
  shows free again.
- **One e2e run with a simulated drop** between order submission and the SSE update, confirming
  the guest-web recovers state on reload without a duplicate order.

## 7. CLAUDE.md update

This spec requires one architecture-rule addition once implemented: guest order submission must
never create a `placed` order for a table without an open sitting, mirroring the existing
"guests never settle bills" rule. This will be added to `CLAUDE.md` alongside the implementation,
not before — per the project's existing practice of updating `CLAUDE.md` in the same change that
implements the rule.
