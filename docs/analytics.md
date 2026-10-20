# Analytics, Forecast and What-if

Everything on the owner **Revenue Brief** (`/brief`) and **What-if** (`/ai`) pages is computed
deterministically from order history. The language model never produces a number: it may only
write a short plain-language summary of facts that were already computed, and that text is
rejected unless every number in it appears in those facts.

Code: `services/api/src/services/` — `analytics.py`, `forecast.py`, `brief.py`, `whatif.py`,
`narrative.py`, `simulator.py`.

## Data

- Source of truth is the immutable `order_item` snapshot (`quantity`, `unit_price`, `unit_cost`)
  taken when the order was placed. Later menu price or cost edits do not rewrite history.
- Cancelled orders are excluded. Dates and hours use the restaurant's timezone.
- **Daypart**: local hour before 16:00 is `lunch`, otherwise `dinner`.
- `orders.source` is `live` or `simulated`. Analytics include both; every response reports the
  count of each (`data_sources`) and the UI shows a "Simulated data" banner when any simulated
  orders are in the window.
- Analysis window for KPIs, menu engineering and what-if: the last **28 days** ending yesterday.

## KPIs

- Revenue = Σ quantity × unit_price
- Orders = distinct orders; AOV = revenue / orders
- Contribution margin = Σ quantity × (unit_price − unit_cost); margin % = margin / revenue

## Menu engineering

Per item: popularity = units sold in the window; unit margin = contribution / units.
Thresholds are the **medians** across items sold in the window (values equal to the median
count as high):

| | margin ≥ median | margin < median |
|---|---|---|
| **units ≥ median** | star | plowhorse |
| **units < median** | puzzle | dog |

Items with no sales in the window are not classified.

## Pairings and peak hours

- Pair lift = P(A and B in an order) / (P(A) × P(B)) over orders in the window. Pairs seen
  together in fewer than 5 orders are dropped. Top 5 by lift.
- Peak hours: the 3 local hours with the most orders, as average orders and revenue per day.

## Forecast

Target: units per item per daypart per day, for the next **7 days**.

Candidates:

1. **Seasonal naive**: same weekday last week, `y[t−7]`.
2. **Trailing 4-week mean**: mean of `y[t−7], y[t−14], y[t−21], y[t−28]` (weeks available).
3. **Gradient boosting**: scikit-learn `HistGradientBoostingRegressor` (Poisson loss, 200
   iterations, learning rate 0.05, 15 leaves, min 20 samples per leaf, fixed random state),
   pooled over all item × daypart series, with features: day of week, daypart, lag-7, lag-14,
   28-day rolling mean ending at `t−7`, and promotion flag. All features are known at a 7-day
   horizon, so no recursive prediction is needed.

Promotion flags come from `audit_log` events of type `promotion`
(`menu_item_id`, `start_date`, `end_date`); the simulator writes these. Future days are
forecast with the promotion flag **off**.

**Backtest**: rolling origin over the last 14 days of history — two folds, each fitting on data
before the origin and predicting the next 7 days. Metrics across all series and both folds:

- WAPE = Σ|actual − forecast| / Σ actual
- MAE = mean |actual − forecast|

The method with the lowest WAPE is used (ties go to the simpler method). The brief shows the
chosen method's WAPE next to the seasonal-naive WAPE. No other accuracy claim is made.

**Interval**: the 80th percentile of backtest residuals scaled by √max(forecast, 1), applied as
forecast ± q·√max(forecast, 1), floored at 0. It is an empirical band from the backtest, not a
guaranteed coverage.

**Limits**

- Fewer than 14 days of history: no backtest, the trailing mean is used, and the forecast is
  flagged **low confidence**.
- Gradient boosting is only a candidate with at least 42 days of history (14 backtest days +
  lag-14 + 14 days of training rows). Otherwise only the baselines are compared.
- Cold start: when a lag is missing, the mean of the known history is used.
- No weather, holidays, events, reservations, price changes or new items are modeled.
- A forecast is stored in `forecast_run` (`model_name`, `metrics` holds the backtest results
  and forecast points, `params` the history range and order counts). It is reused until the
  history changes.

## Brief actions

3 to 5 actions, money actions ranked by estimated weekly impact, then a prep action:

| Action | Picked | Estimated impact per week |
|---|---|---|
| Promote puzzle | top 2 puzzles by unit margin | 0.20 × weekly units × unit margin (assumes featuring lifts units 20%) |
| Reprice plowhorse | top 2 plowhorses by units | what-if price change +5% at elasticity −0.8 on the current menu price and cost (margin delta; same baseline as the What-if page) |
| Review dog | dog with the lowest contribution | weekly units × (median unit margin − unit margin) |
| Prep targets | top 3 items by forecast for the next day | none; prep = ceil(Σ dayparts upper interval bound) |

Weekly units = units in the window / 4. Each action lists its evidence numbers and formula.

## Summary text and the numbers guard

The facts (KPIs, actions with evidence, pairings by item name, peak hours, forecast method and
backtest WAPE) are sent to the configured model with an instruction to only restate numbers. The
response is accepted only if every number in it equals a number in the facts rounded to the
same number of decimals (thousands separators allowed). Otherwise, or if the model is
unavailable (no client, daily cap, 429, error), a template summary built from the same facts is
used. `summary_source` says which one was used.

Only aggregate business data goes to the model. No guest, allergen, dietary or personal data is
included.

## What-if calculator

Baseline: weekly units per item over the analysis window (units / 4) at **current** menu price
and cost. Output: weekly baseline vs scenario revenue and contribution margin, the deltas, and
the assumptions applied.

| Scenario | Inputs | Formula |
|---|---|---|
| `price_change` | item, change % (−90…+100), elasticity (default −0.8) | price′ = p(1+c); units′ = units × max(0, 1 + e·c) |
| `promotion` | item, discount % (1…90), elasticity (default −2.0) | price′ = p(1−d); units′ = units × max(0, 1 + e·(−d)) |
| `demand_surge` | multiplier (0…5] | units′ = units × m for every item |

Not modeled: cannibalization or halo effects on other items, kitchen capacity, staffing cost.
The model may write an explanation under the same numbers guard; otherwise a template is used.

## Simulated demo data

`make simulate` (or `POST /api/restaurants/{slug}/demo/simulate-orders`, owner only, DEMO_MODE
only, or the **Generate demo data** button) replaces the restaurant's simulated orders with a
seeded synthetic history ending yesterday. Live orders are never touched. It is limited to 3
runs per hour per client IP, and concurrent runs for one restaurant are serialized by a row
lock (`FOR NO KEY UPDATE` on the restaurant), so two simultaneous requests end with the data of
one run. Orders go through the
same snapshot code as live orders, are stored as `status='bumped'` (so they never appear on the
kitchen display) and `source='simulated'`, under one synthetic expired guest session with no
allergen or dietary data.

Assumptions (`SimAssumptions`, all parameters):

| Assumption | Default |
|---|---|
| Days, seed | 56 days, seed 42 |
| Orders (tables) per lunch, Mon→Sun | 7, 8, 8, 9, 11, 15, 13 (Poisson means) |
| Orders per dinner, Mon→Sun | 10, 11, 12, 14, 22, 26, 16 |
| Service windows (local) | lunch 12:00–15:00, dinner 19:00–23:00, uniform arrival minute |
| Party size 1–6 | 10%, 45%, 15%, 22%, 4%, 4% |
| Dishes per order | max(party size, Poisson(1.4 × party size)) |
| Item popularity | Zipf, weight ∝ 1 / rank^1.0, rank from a seeded shuffle of the menu |
| Promotion | the rank-6 item, days 21–27, demand weight × 1.8 (disable with `--no-promo`) |
| Noise | daily multiplicative factor exp(N(0, 0.12)) on arrival rates |

Item choice is independent of course or category; quantities are capped at 20 per line.
