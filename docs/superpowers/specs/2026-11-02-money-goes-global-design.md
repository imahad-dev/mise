# Money goes global: per-country tax, VAT-inclusive prices and an optional service charge

Date: 2026-11-02. Status: approved in conversation, awaiting written review.
Spec 2 of 3 (1: safer table ordering, 3: four venues, four identities).

## Why

Mise will run venues in Pakistan (Lahore, Islamabad), the UK (Manchester) and the UAE (Dubai),
each in its own currency and under its own tax rules. Today the tax engine knows only the
Pakistani way: sales tax is added on top of menu prices, the rate depends on how the guest pays,
and amounts round to whole rupees. The UK and UAE work the other way round: the menu price
already includes VAT, the rate does not depend on the payment method, and amounts keep pence or
fils. A wrong bill is not acceptable, so the engine must handle both, from data, with sources.

## What guests and owners told us (research, 2026-11-02)

- Guests everywhere complain most about charges that appear only at the end. UK law (DMCC Act
  2024, in force 6 April 2025, CMA price-transparency guidance): optional charges must be
  disclosed before purchase; compulsory ones must be inside the price shown.
- UK guests distrust a service charge that is not clearly optional. A discretionary service
  charge is outside the scope of VAT; a compulsory one is standard-rated (HMRC; VAT Notice 709/1).
- UK owners: an optional 12.5% service charge on top of VAT-inclusive prices is the norm. The
  Employment (Allocation of Tips) Act 2023, in force 1 July 2024, requires 100% of tips and
  service charges to reach staff within a month.
- HMRC VAT Notice 700 §17.6: caterers may work VAT out on the total and must not always round it
  down; rounding to the nearest penny is allowed.
- UAE: VAT 5%, and "the advertised price shall include the Tax" (Federal Decree-Law No. 8 of
  2017, Art. 38; Cabinet Decision No. 52 of 2017, Art. 27). Several guides report that standalone
  Dubai restaurants must not add a service charge; hotels and special zones add 10%.
- Pakistan: the Punjab revenue authority itself tells guests to pay by card (16% cash, 8% card).
  Guests complain of being charged the cash rate or refused card. Mise already shows both totals.

## Decisions

1. **Approach A**: extend the existing data-driven tax engine; no per-country code paths.
2. **Each venue reports in its own currency.** No exchange rates and no combined total.
3. **Optional service charge** set by the owner, offered only where the jurisdiction data allows
   it. For now that is GB only. Never compulsory, never taxed, never counted as sales.
4. **Out of scope**: UK zero-rated cold takeaway (counter sales use 20%, which never under-charges
   VAT and leaves the guest's price unchanged); UAE cash rounding to 25 fils (no official rule
   found; cash bills show exact fils); hotel and zone fees; Pakistani service charges; Arabic.
   The UK and UAE end-to-end browser stories land with spec 3, which creates those venues.

## 1. Tax data and the sums

### Data

`data/tax_rates.json` keeps its list of dated rates. `payment_class` gains `"any"`. New entries,
each with its source:

| jurisdiction | payment_class | rate | effective_from | source |
|---|---|---|---|---|
| GB | any | 0.20 | 2011-01-04 | VAT Notice 709/1; standard rate |
| AE-DU | any | 0.05 | 2018-01-01 | Federal Decree-Law No. 8 of 2017, Art. 3 and 38 |

A new `data/tax_jurisdictions.json` holds the per-jurisdiction rules:

```json
{
  "PB":    {"name": "Punjab, Pakistan",  "currency": "PKR", "pricing": "on_top",   "rounding": "1",
            "methods": ["cash", "card", "wallet", "raast", "bank_transfer"], "service_charge": null},
  "ICT":   {"name": "Islamabad, Pakistan", "currency": "PKR", "pricing": "on_top", "rounding": "1",
            "methods": ["cash", "card", "wallet", "raast", "bank_transfer"], "service_charge": null},
  "GB":    {"name": "United Kingdom",    "currency": "GBP", "pricing": "included", "rounding": "0.01",
            "methods": ["cash", "card"], "service_charge": "optional_outside_tax"},
  "AE-DU": {"name": "Dubai, UAE",        "currency": "AED", "pricing": "included", "rounding": "0.01",
            "methods": ["cash", "card"], "service_charge": null}
}
```

- `pricing`: `on_top` (tax added to menu prices) or `included` (menu prices include tax).
- `rounding`: the money unit every tax, service and total amount rounds to, half up.
- `methods`: the only payment methods a venue in that jurisdiction may settle with.
- `service_charge`: `null` (not offered) or `optional_outside_tax`.

The loader refuses, with a clear error:
- a rate whose jurisdiction has no entry;
- a jurisdiction that has both `any` rates and `standard`/`digital` rates;
- an unknown `pricing`, `service_charge` or method, a non-positive `rounding`, or an empty
  `methods` list.

A venue's `tax_jurisdiction` must exist in this file and its `currency` must match the
jurisdiction's. This is checked wherever either is set (seed and admin scripts; owner settings
cannot change either), and `NULL` keeps today's
meaning (no tax configured, previews absent, settle refused).

### The sums

One pure function, `charge_for(...)`, returns `(rate, tax, total, pricing)` for a subtotal (the
sum of menu-price lines); the existing `tax_for(...)` keeps its `(rate, tax)` shape on top of it:

- `on_top`: `tax = round(subtotal × rate)`, `total = subtotal + tax`. Identical to today.
- `included`: `total = subtotal`; `tax = round(total × rate ÷ (1 + rate))`. The guest pays the
  menu price to the penny.

VAT is worked out once on the bill total, not per line (allowed by HMRC Notice 700 §17.6).
`round` is half up to the jurisdiction's `rounding` unit, in one helper used everywhere.

Examples: £24.00 at 20% → VAT £4.00, total £24.00. AED 105.00 at 5% → VAT 5.00, total 105.00.
£10.99 at 20% → VAT £1.83 (1.831…), total £10.99.

## 2. Bills, settle and reports

- **Snapshot.** `bill` gains `tax_pricing` (`on_top`/`included`), `service_charge_rate` and
  `service_charge_amount` (both default 0). A migration sets `tax_pricing='on_top'` on existing
  settled bills. A settled bill always reads the way it was charged.
- **Bill total.** `on_top`: subtotal + tax + service. `included`: subtotal + service.
- **Payment methods.** Previews, the guest pay sheet, the guest payment claim and settle offer and
  accept only the jurisdiction's `methods`. Any other method is refused with 422.
- **Previews.** Where the jurisdiction uses `any`, there is one preview; the API keeps
  `preview_standard`/`preview_digital` for compatibility and fills both with the same values,
  plus a new `tax_included: bool` on each preview.
- **Settle.** Unchanged in shape and safety: same locks, staff send `expected_total` and method,
  a mismatch is refused. The request gains `service_included: bool` (default false).
- **Reports.** Every sales figure built from order lines (revenue, margin, average order value,
  menu engineering, forecast inputs, what-if, the morning brief and the service report) is
  reported **excluding VAT** for `included` venues: each order's money is divided by
  `1 + tax_rate` from its settled bill's snapshot (current menu prices in what-if use the rate
  in force today). Pakistan figures are unchanged (tax was
  never in them). Labels say "excl. VAT" where it applies.
- The cash-versus-digital tax card is shown only where the jurisdiction splits by method.
- Pay-forward amounts stay at menu prices; nothing about pay-forward changes.

## 3. Optional service charge

- **Setting.** `restaurant.service_charge_rate`, a fraction from 0 to 0.20, default 0. Settable
  through the existing settings `PATCH` only when the jurisdiction's `service_charge` is
  `optional_outside_tax`; otherwise 422.
- **Where it applies.** Table bills only. Counter bills never carry one.
- **Amount.** `round(subtotal × service_charge_rate)` on the menu-price subtotal, a separate line
  after VAT. Never part of VAT, never counted in sales.
- **Before ordering.** When the rate is above 0, the guest menu shows one line under the venue
  name: "An optional 12.5% service charge is added to table bills." (DMCC disclosure.)
- **Guest choice.** The pay sheet shows "Add optional service (12.5%): £3.00" as a switch, on by
  default; the total updates on tap. The guest's payment claim records `service_included`.
- **Staff.** The settle dialog starts from the guest's choice (or on when there is no claim);
  staff can change it if the guest asks in person. `expected_total` includes the service charge
  or not; a mismatch is refused, so the choice cannot be lost or silently reversed.
- **Wording.** Always "Optional service". No compulsory service charge exists in Mise.
- **Report.** A daily "Service charge collected (for staff)" figure, kept apart from revenue,
  with a one-line note that UK law (in force 1 July 2024) requires it to reach staff in full.
  Mise records it; it does not pay anyone.

## 4. Screens

- **Guest:**
  - prices exactly as now, in the venue's currency;
  - for `included` venues, one total with "Includes VAT 20%: £4.00" under it;
  - the service switch where it applies;
  - only the venue's methods (UK and UAE: Cash, Card);
  - Pakistan unchanged;
  - English and Italian strings for every new line.
- **Staff and owner:**
  - bills page and settle dialog as above;
  - Settings shows a read-only "Prices include VAT 20% (United Kingdom)" line, plus the
    service-charge percentage where allowed;
  - reports use "excl. VAT" labels, the Pakistan-only tax card, and the service-charge figure.
- **Model:** the morning brief and service report receive the same computed figures; the model
  only phrases them and its text still passes the number-consistency check.
- **No tax-invoice look:** bills never show a VAT number or the words "VAT invoice", "tax
  invoice" or "receipt". They say "VAT 20% included" only.

## Testing

- **Tax engine:**
  - all existing Pakistan tests pass unchanged;
  - GB and AE-DU property tests over many random totals: tax + amount excl. VAT == total, and
    total == menu price;
  - the worked examples above;
  - every loader refusal.
- **Bills:**
  - full order → bill → settle on GB and AE-DU fixture venues, with and without service;
  - refused methods (Raast on a GB venue);
  - service refused for AE-DU and Pakistani venues and never on counter bills;
  - settle mismatch with and without service;
  - migration up, down and drift check.
- **Reports:** the same orders give the same Pakistan figures as before and VAT-excluded figures
  for GB; service charge stays out of revenue.
- **Front end:**
  - pay-sheet component tests (one total, VAT line, switch, filtered methods);
  - settle-dialog tests;
  - menu notice;
  - `formatPrice` for GBP and AED in `en` and `it`.
- **Browser stories:** UK and UAE end-to-end stories come with spec 3, when those venues exist.
