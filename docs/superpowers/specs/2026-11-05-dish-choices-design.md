# Dish page and choices

Date: 2026-11-05. Status: approved in conversation, awaiting written review.
Spec 3A of 3 (1: safer table ordering, 2: money goes global, 3A: this, 3B: four identities).

## Why

A guest should be able to tap a dish photo and make it theirs: spicy or mild, no sugar, extra
milk. Today a dish has one kind of choice, its size, and nothing else reaches the kitchen.
Restaurant systems (Toast, Aloha) all use the same model: each dish has choice groups, each
required or optional, with a minimum, a maximum and a price per choice. Ordering-app vendors claim
10–20% higher order values from add-ons. That is their marketing, not independent proof, so Mise
measures it for each venue.

Choices touch price, allergens and the kitchen ticket, so this ships before any restyling. It is
built on today's look using the shared house classes, so that spec 3B can skin it per venue.

## Decisions

1. **Sizes stay as they are.** `menu_item_option` keeps its table, its reports and its place in the
   order line. The dish page shows size as the first group; no size data moves.
2. **Choices are new data on the dish.** Two new tables hold what can be chosen. What was chosen is
   stored as a snapshot on the order line, so old bills never change.
3. **The phone sends only ids.** The server works out every price and every allergen.
4. **A choice can add an allergen and can never remove one.**
5. **Out of scope:** discounts for leaving something out (no negative prices), combos and meal
   deals, choices that depend on other choices, editing a line in the cart (remove and add again),
   photo upload and venue looks (3B), translated choice names (labels are single-language, like
   size labels today).

## 1. Data

### Menu

`menu_choice_group`: `id`, `menu_item_id` (cascade), `label`, `kind`, `min_select`, `max_select`,
`sort_order`.

| kind | Meaning | Example |
|---|---|---|
| `pick` | Choose among versions of the dish | Spice: Mild / Medium / Hot |
| `add` | Things added, usually paid | Extras: Extra milk +£0.50 |
| `leave_out` | Things removed, always free | Leave out: Onions |

`menu_choice`: `id`, `group_id` (cascade), `label`, `price_delta`, `cost_delta`, `allergens`,
`allergen_verified`, `is_vegetarian`, `is_vegan`, `available`, `is_default`, `sort_order`.

Database checks:

- `0 <= min_select <= max_select`, and `max_select >= 1`.
- `price_delta >= 0`, `cost_delta >= 0`.
- `allergens` uses the same fourteen values as `menu_item`.
- `NOT (is_vegan AND NOT is_vegetarian)`, and a vegan choice carries no animal allergen.
- A vegetarian choice carries no fish, crustaceans or molluscs, as for dishes.
- Labels are unique inside their parent.

`allergen_verified`, `is_vegetarian` and `is_vegan` default to false, which is the safe answer for
a choice nobody has confirmed.

Checked in the save path, because these rules span rows:

- `leave_out` choices have zero price, zero cost and no allergens. They add nothing, so they are
  always saved as confirmed, vegetarian and vegan: "Onions" never marks a line unverified.
- A group has no more `is_default` choices than its `max_select`.
- A pay-it-forward dish has no choice groups: the person who receives it is not the person
  ordering.

Each failure is a 422.

### Order line

`order_item` gains `choices` (JSONB, default `[]`):

```json
[{"choice_id": "…", "group": "Extras", "kind": "add", "label": "Extra milk",
  "price_delta": "0.50", "cost_delta": "0.12", "allergens": ["milk"]}]
```

JSONB rather than a child table: it is an immutable snapshot, and every place that loads
`Order.items` keeps working without a new eager load under `lazy="raise"`. A deleted choice leaves
old lines untouched, so choices can be hard-deleted.

## 2. Placing an order

`OrderItemRequest` gains `choice_ids: list[UUID]` (default empty, at most 30, no repeats). The
server, for each line:

1. **Resolves** every id against the dish's own groups. An unknown id is 422 `choices_changed`:
   it may be a choice the owner deleted while it sat in a saved cart.
2. **Checks availability.** A sold-out choice is 409 `unavailable_choices`, naming the dish and the
   choice, in the same shape as `unavailable_items`.
3. **Checks each group.** The count must lie between `min_select` and `max_select`. A failure is
   422 `choices_changed`. This also catches a cart saved before the owner edited the dish.
4. **Prices.** `unit_price = (size price or dish price) + sum(price_delta)`. `unit_cost` likewise.
5. **Allergens.** The line's allergens are the union of the dish's and the chosen choices'.
   `allergen_verified` is true only if the dish and every chosen choice are verified. The status
   comes from `compute_allergen_status` on that union.

All three order-line creators go through `snapshot_order_item`, which gains
`choices: list[MenuChoice] = ()`. Live orders pass the guest's. The simulator passes its draw (see
section 6). Pay-forward passes none.

Three existing code paths must change with it:

- **The allergen acknowledgement in `create_order`** today reads only `item.allergens`. It moves
  after choice resolution and reads the union, so "Extra milk" for a guest avoiding milk stops at
  `allergen_ack_required` like any other conflict.
- **`compute_payload_hash`** includes the sorted `choice_ids`, in both the hash and the sort key.
  Two lines that differ only by choice stay different, and a retry with the same choices stays a
  retry.
- **`bill_lines`** groups by dish, size, choices and unit price. Without this, "No sugar" and
  "Less sugar" at the same price would merge into one line. Voided lines follow the same key.

A dish whose required group has no available choice cannot be ordered. The guest menu marks it
sold out and the server refuses it.

VAT, the service charge, the first-order cap, settle and bills need no other change: they all work
from `unit_price`.

## 3. Allergen rules

This is the section a reviewer should read twice.

- A choice's allergens are added to the line, never taken away.
- "Leave out" has no allergen effect at all. "Leave out: Nuts" does not make a dish nut-free,
  because of cross-contact in the kitchen. The allergen stays listed and the status stays as it was.
- Those groups and every `leave_out` group show: "Leaving something out doesn't make a dish safe for an allergy.
  Please ask a member of staff."
- A choice label cannot promise safety. Saving a label with a word ending in `free`, containing
  `allerg`, or starting with `safe` (any case) is refused with 422. "Sugar free" is therefore
  refused too; the owner writes "No sugar".
- Any group with a choice starting "No " shows the leave-out notice below, whatever its kind, so
  "No nuts" in a pick group warns the guest too.
- The dish page has no free-text box. A guest typing "I'm allergic" there could be missed, so that
  stays a conversation with staff. `notes` stays in the API, unused by this page.
- The guest menu sends `allergen_status` and `matched_allergens` for each choice, computed by the
  same function and the guest's session. A conflicting choice shows the same chip as a dish, and
  stays selectable: the warning and the acknowledgement are the existing safeguard.
- A dietary filter marks a choice that doesn't fit ("Not vegan") using the choice's own flags.
  An unconfirmed choice therefore never claims to be vegan.
- The model never sees a guest's choices, and never decides any of this.

## 4. Guest dish page

Tapping a dish's photo or name opens the dish page: a full-height `Sheet` on phones, with the phone's
Back button closing it (one `pushState` entry). It replaces the current size chooser.

Top to bottom: large photo (or the existing no-photo layout), name, description, allergen chips,
size, then each choice group, then a fixed footer with quantity, the live total and the action.

- A group with a minimum and a maximum of one uses radio buttons; anything else uses checkboxes,
  because a radio button can't be cleared. Native inputs, rows at least 44px tall. Each group says
  what it needs in words: "Choose 1", "Up to 3", "Optional".
- A paid choice shows "+£0.50". A sold-out choice is shown disabled with "Sold out".
- Available `is_default` choices start selected. A required group with no default starts empty, so
  the guest must decide. Spice has no default; sugar defaults to Normal.
- The action reads "Add to order · £7.50" when complete. While a required group is empty it reads
  "Choose spice", and tapping it scrolls to that group, highlights it and moves focus there. The
  button is never disabled, because a disabled button can't explain itself.
- The total updates on every tap and is announced politely to screen readers.
- The menu's + button adds in one tap when the dish has no size and its defaults satisfy every
  required group. Otherwise it opens the dish page.
- A dish with no sizes and no groups still opens the page from its photo, with quantity and Add.

**Cart.** A line's identity becomes dish + size + sorted choice ids. Two coffees with different
choices are two lines. Lines list their choices under the name. `allergenStatus` on the line is the
worst of the dish and its chosen choices, for display only; the server decides.

**When the server refuses.** `unavailable_choices`: the order stays in the cart and the guest sees
"Sorry, Extra milk has just run out." with that line marked. `choices_changed`: "This dish has
changed. Please choose again." and the dish page opens for that line. Nothing is ever silently
dropped or swapped, and nothing is charged.

## 5. Kitchen, staff and bills

- **Kitchen.** Choices appear under the dish name. `leave_out` choices are shown in strong capitals
  with "NO" ("NO ONIONS") so a cook can't miss them.
- **The Floor approval tile** stays a count and a total ("3 items · Rs 1,200"): it lists no dishes
  today, and this spec does not add them.
- **Guest order page and bills.** Lines list choices. Paid extras show their price. `BillLine`,
  `VoidedLine` and the kitchen and order item schemas gain
  `choices: [{label, kind, price_delta}]`.
- Bills keep their wording rules. Nothing here adds tax-invoice language.

## 6. Owner and reports

**Menu page.** Each dish gains a Choices section: add, edit, reorder and delete groups and choices,
with the existing allergen picker and a "confirmed" tick for allergens. Routes use
`restaurant_access`, answer 404 to non-members and have a `response_model`. Limits: 8 groups per
dish, 20 choices per group. Editing never touches past orders.

**Report.** One new card, computed by code:

- **How often extras are added:** order lines with at least one priced choice ÷ all order lines.
- **Extras sales**, in the venue's currency, using the same `_NET` scaling as other sales, so it is
  excl. VAT where that applies.
- **Top five extras** by count.

Same date range and settled-order filter as the existing sales figures. Dish revenue and margin
already include extras through `unit_price`, so no menu-engineering row changes. Menu engineering
rows stay per dish and size. The what-if tool changes base prices only, and says so.

The morning brief and service report are unchanged: the model gets no new figures.

**Seed and simulator.** `data/seed/*.json` items gain optional `choice_groups`. Angeethi House and
Kehwa & Crumb get realistic groups (spice on karahi, sugar and milk on tea, extras on baked goods).
The simulator draws choices from a seeded generator of its own, so existing draws and report
figures for dishes without choices stay the same, and the report has data in demos.

## Error handling

| Case | Result |
|---|---|
| Choice unknown to this dish | 422 `choices_changed` |
| Repeated choice | 422, order not placed |
| Too few or too many in a group | 422 `choices_changed` |
| Sold-out choice | 409 `unavailable_choices` |
| Chosen allergen conflicts, no acknowledgement | 409 `allergen_ack_required` |
| Required group entirely sold out | Dish shown sold out; 409 `unavailable_items` |
| Choices on a pay-it-forward dish | 422 on save |
| Label promises safety | 422 on save |
| Same idempotency key, different choices | Existing conflict response |

## Testing

- **Money:**
  - unit price and cost with a size and several extras;
  - PK, GB and AE-DU bills with extras, VAT and service charge to the penny;
  - a phone-supplied price is impossible (the request has no such field);
  - a menu price change leaves old lines and bills unchanged.
- **Allergens:**
  - extra milk for a guest avoiding milk stops at the acknowledgement;
  - an unconfirmed choice makes the line unverified;
  - leave-out never changes allergens or status;
  - label refusals;
  - the kitchen line shows the union.
- **Validation:** every row of the error table.
- **Idempotency:** same choices in any order is a retry; different choices on the same key conflict.
- **Bills:** same price, different choices stay separate lines, including after a void.
- **Migration:** up, down and drift check.
- **Reports:** attach rate and extras sales on known orders; excl. VAT for GB; no change to existing
  figures for dishes without choices; simulator determinism.
- **Front end:** cart line identity, dish-page group rules, the "Choose spice" action, the + button
  rule, refusal messages, and kitchen and bill rendering.
- **Browser story, with real taps:** phone guest opens a dish, is sent to the missing spice choice,
  adds extra milk, sees the warning, orders; staff approve; the kitchen sees "NO ONIONS"; the bill
  lists the extra; staff settle.

## Docs

`README.md` and `docs/architecture.md` describe choices once built and tested. `CLAUDE.md` gains one
rule: a choice can add an allergen, never remove one.
