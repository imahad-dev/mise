"""Deterministic what-if calculator. Pure arithmetic; formulas documented in docs/analytics.md.

Baseline is weekly: units per item from recent sales, at the current menu price and cost.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PRICE_ELASTICITY = -0.8  # % change in units per 1% change in price
DEFAULT_PROMO_ELASTICITY = -2.0  # promotions draw more response than list-price changes


@dataclass(frozen=True)
class ItemBaseline:
    item_id: str
    name: str
    weekly_units: float
    price: float
    unit_cost: float


def _totals(items: list[ItemBaseline], units: dict[str, float], price: dict[str, float]):
    revenue = sum(units[i.item_id] * price[i.item_id] for i in items)
    margin = sum(units[i.item_id] * (price[i.item_id] - i.unit_cost) for i in items)
    return revenue, margin


def _r(x: float) -> float:
    return round(x, 2)


def run_whatif(scenario: str, items: list[ItemBaseline], params: dict) -> dict:
    """Return weekly baseline vs scenario revenue and contribution margin, plus assumptions.

    Scenarios:
    - price_change: item_id, change_pct (e.g. 5 = +5%), elasticity (default -0.8)
    - promotion: item_id, discount_pct (e.g. 20), elasticity (default -2.0)
    - demand_surge: multiplier (e.g. 1.3), applied to every item's units
    """
    by_id = {i.item_id: i for i in items}
    units = {i.item_id: i.weekly_units for i in items}
    price = {i.item_id: i.price for i in items}
    base_rev, base_margin = _totals(items, units, price)
    new_units, new_price = dict(units), dict(price)
    assumptions: list[str] = [
        "Baseline is average weekly units over the analysis window at current menu price and cost.",
    ]

    if scenario in ("price_change", "promotion"):
        item = by_id.get(str(params.get("item_id")))
        if item is None:
            raise ValueError("item_id must be a menu item with sales in the analysis window")
        if scenario == "price_change":
            pct = float(params.get("change_pct", 5.0))
            elasticity = float(params.get("elasticity", DEFAULT_PRICE_ELASTICITY))
        else:
            pct = -float(params.get("discount_pct", 20.0))
            elasticity = float(params.get("elasticity", DEFAULT_PROMO_ELASTICITY))
        if not -90.0 <= pct <= 100.0:
            raise ValueError("price change must be between -90% and +100%")
        new_price[item.item_id] = item.price * (1 + pct / 100)
        new_units[item.item_id] = item.weekly_units * max(0.0, 1 + elasticity * pct / 100)
        assumptions += [
            f"Price of {item.name} changes by {_r(pct)}% to {_r(new_price[item.item_id])} EUR.",
            f"Units respond with elasticity {elasticity}: units x (1 + {elasticity} x {_r(pct)}%).",
            "No effect on other items (no cannibalization or halo modeled).",
        ]
    elif scenario == "demand_surge":
        m = float(params.get("multiplier", 1.3))
        if not 0.0 < m <= 5.0:
            raise ValueError("multiplier must be in (0, 5]")
        new_units = {k: v * m for k, v in units.items()}
        assumptions += [
            f"Every item's units are multiplied by {m}; menu mix is unchanged.",
            "No kitchen capacity limit, staffing cost or price change is modeled.",
        ]
    else:
        raise ValueError(f"unknown scenario '{scenario}'")

    rev, margin = _totals(items, new_units, new_price)
    return {
        "scenario": scenario,
        "params": params,
        "baseline": {"revenue_eur": _r(base_rev), "margin_eur": _r(base_margin)},
        "result": {"revenue_eur": _r(rev), "margin_eur": _r(margin)},
        "delta": {"revenue_eur": _r(rev - base_rev), "margin_eur": _r(margin - base_margin)},
        "assumptions": assumptions,
    }
