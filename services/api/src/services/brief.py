"""Daily brief: deterministic facts and ranked actions; the LLM only narrates them.

Action formulas (all weekly, documented in docs/analytics.md):
- promote_puzzle: +PROMOTE_UPLIFT x weekly_units x unit_margin
- reprice_plowhorse: what-if price_change of +REPRICE_PCT% at the default price elasticity
- review_dog: weekly_units x (median_unit_margin - unit_margin), the gain if its volume moved
  to a median-margin dish
- prep_target: ceil of the summed upper forecast bound for the next service day (no money impact)
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.models.forecast import ForecastRun
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.services import analytics, pay_forward
from src.services.forecast import HORIZON_DAYS, build_input, forecast
from src.services.narrative import narrate
from src.services.whatif import DEFAULT_PRICE_ELASTICITY, ItemBaseline, run_whatif

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.inference.client import InferenceClient
    from src.models.restaurant import Restaurant

WINDOW_DAYS = 28
FORECAST_HISTORY_DAYS = 91
PROMOTE_UPLIFT = 0.20
REPRICE_PCT = 5.0
MAX_MONEY_ACTIONS = 4


async def item_names(db: AsyncSession, restaurant: Restaurant) -> dict[str, str]:
    """Display name per item id: English translation, else the restaurant default language."""
    rows = await db.execute(
        select(MenuTranslation.menu_item_id, MenuTranslation.language, MenuTranslation.name)
        .join(MenuItem)
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    names: dict[str, str] = {}
    for item_id, lang, name in rows.all():
        if lang == "en" or (lang == restaurant.default_language and str(item_id) not in names):
            names[str(item_id)] = name
    return names


def local_today(restaurant: Restaurant) -> date:
    return datetime.now(ZoneInfo(restaurant.timezone)).date()


def row_names(totals: dict[str, dict], names: dict[str, str]) -> dict[str, str]:
    """Display names by menu item id (forecast, prep) plus one per row key.

    An option row reads "{dish} — {option label}".
    """
    out = dict(names)
    for key, t in totals.items():
        dish = names.get(t["item_id"], "Unknown item")
        out[key] = f"{dish} — {t['option_label']}" if t["option_label"] else dish
    return out


async def current_prices(
    db: AsyncSession, restaurant: Restaurant
) -> dict[str, tuple[float, float]]:
    """Current menu (price, unit_cost) per row key: the item id, and item:option per option."""
    rows = await db.execute(
        select(MenuItem.id, MenuItem.price, MenuItem.unit_cost).where(
            MenuItem.restaurant_id == restaurant.id
        )
    )
    prices = {str(i): (float(p), float(c)) for i, p, c in rows.all()}
    options = await db.execute(
        select(
            MenuItemOption.menu_item_id,
            MenuItemOption.id,
            MenuItemOption.price,
            MenuItemOption.unit_cost,
        )
        .join(MenuItem)
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    for item_id, option_id, p, c in options.all():
        prices[analytics.row_key(str(item_id), str(option_id))] = (float(p), float(c))
    return prices


def item_baselines(
    totals: dict[str, dict], names: dict[str, str], prices: dict[str, tuple[float, float]]
) -> list[ItemBaseline]:
    """What-if baselines per menu item: option rows summed, prices weighted by their units.

    Exact for the scenarios: a uniform price change or demand multiplier on the summed row
    gives the same totals as applying it to every option row.
    """
    acc: dict[str, list[float]] = {}  # item_id -> [weekly_units, revenue/wk, cost/wk]
    for key, t in totals.items():
        if key not in prices:  # deleted item or option: skip
            continue
        price, cost = prices[key]
        a = acc.setdefault(t["item_id"], [0.0, 0.0, 0.0])
        a[0] += t["weekly_units"]
        a[1] += t["weekly_units"] * price
        a[2] += t["weekly_units"] * cost
    return [
        ItemBaseline(i, names.get(i, ""), u, rev / u if u else 0.0, cost / u if u else 0.0)
        for i, (u, rev, cost) in acc.items()
    ]


def baseline_for(item_id: str, name: str, totals: dict, price: float, cost: float) -> ItemBaseline:
    """What-if baseline: recent weekly units at the current menu price and cost.

    The brief's reprice action uses it per row; the what-if endpoint's item_baselines gives
    the same baseline for a dish without options, so both agree there.
    """
    return ItemBaseline(item_id, name, totals["weekly_units"], price, cost)


async def get_or_run_forecast(
    db: AsyncSession, restaurant: Restaurant, today: date
) -> tuple[dict, uuid.UUID]:
    """Reuse the latest forecast_run for the same history, otherwise backtest, fit and store."""
    w = analytics.Window(
        restaurant.id, restaurant.timezone, today - timedelta(days=FORECAST_HISTORY_DAYS), today
    )
    counts = await analytics.order_counts_by_source(db, w)
    params = {
        "history_end": (today - timedelta(days=1)).isoformat(),
        "order_count": sum(counts.values()),
        "sources": counts,
        "horizon_days": HORIZON_DAYS,
    }
    latest = (
        await db.execute(
            select(ForecastRun)
            .where(ForecastRun.restaurant_id == restaurant.id)
            .order_by(ForecastRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and all(latest.params.get(k) == v for k, v in params.items()):
        return latest.metrics, latest.id

    daily = await analytics.daily_item_sales(db, w)
    if daily:
        first = min(r["date"] for r in daily)
        # Forecast is per menu item: build_input sums the option rows of a dish.
        rows = [(r["item_id"], r["date"], r["daypart"], r["units"]) for r in daily]
        fi = build_input(
            rows, await analytics.promotions(db, restaurant.id), first, w.end - timedelta(days=1)
        )
        params["history_start"] = first.isoformat()
        # Model fitting is CPU-bound; run it off the event loop so other requests keep flowing.
        result = await asyncio.to_thread(forecast, fi)
    else:
        result = forecast(build_input([], [], w.start, w.start))

    run = ForecastRun(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        horizon_days=HORIZON_DAYS,
        model_name=result["model_name"] or "none",
        metrics=result,
        params=params,
    )
    db.add(run)
    await db.flush()
    return result, run.id


def build_actions(
    totals: dict[str, dict],
    classes: dict[str, str],
    thresholds: dict,
    fc: dict,
    names: dict[str, str],
    prices: dict[str, tuple[float, float]],
) -> list[dict]:
    """3-5 ranked actions with evidence and an estimated weekly impact (see module docstring)."""

    def name(i: str) -> str:
        return names.get(i, "Unknown item")

    money: list[dict] = []
    by_class = {
        c: [i for i, k in classes.items() if k == c] for c in ("puzzle", "plowhorse", "dog")
    }

    for i in sorted(by_class["puzzle"], key=lambda i: -totals[i]["unit_margin"])[:2]:
        t = totals[i]
        money.append(
            {
                "type": "promote_puzzle",
                "item_id": t["item_id"],
                "option_id": t["option_id"],
                "item": name(i),
                "title": f"Promote {name(i)}",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "unit_margin": t["unit_margin"],
                    "median_units": thresholds["median_units"],
                },
                "estimated_impact_per_week": round(
                    PROMOTE_UPLIFT * t["weekly_units"] * t["unit_margin"], 2
                ),
                "formula": f"{PROMOTE_UPLIFT} x weekly_units x unit_margin",
            }
        )

    plowhorses = [i for i in by_class["plowhorse"] if i in prices]  # deleted items: skip
    for i in sorted(plowhorses, key=lambda i: -totals[i]["units"])[:2]:
        t = totals[i]
        price, cost = prices[i]
        base = baseline_for(i, name(i), t, price, cost)
        wi = run_whatif("price_change", [base], {"item_id": i, "change_pct": REPRICE_PCT})
        money.append(
            {
                "type": "reprice_plowhorse",
                "item_id": t["item_id"],
                "option_id": t["option_id"],
                "item": name(i),
                "title": f"Raise the price of {name(i)} by {REPRICE_PCT}%",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "price": round(price, 2),
                    "unit_cost": round(cost, 2),
                    "median_unit_margin": thresholds["median_unit_margin"],
                },
                "estimated_impact_per_week": wi["delta"]["margin"],
                "formula": (
                    f"what-if price_change +{REPRICE_PCT}% at elasticity "
                    f"{DEFAULT_PRICE_ELASTICITY}: "
                    "new_units x (new_price - cost) - units x (price - cost)"
                ),
            }
        )

    dogs = sorted(by_class["dog"], key=lambda i: totals[i]["contribution"])[:1]
    for i in dogs:
        t = totals[i]
        gap = thresholds["median_unit_margin"] - t["unit_margin"]
        money.append(
            {
                "type": "review_dog",
                "item_id": t["item_id"],
                "option_id": t["option_id"],
                "item": name(i),
                "title": f"Review {name(i)} (rework, reprice or replace)",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "unit_margin": t["unit_margin"],
                    "median_unit_margin": thresholds["median_unit_margin"],
                },
                "estimated_impact_per_week": round(t["weekly_units"] * gap, 2),
                "formula": "weekly_units x (median_unit_margin - unit_margin)",
            }
        )

    money.sort(key=lambda a: -(a["estimated_impact_per_week"] or 0))
    actions = money[:MAX_MONEY_ACTIONS]

    if fc.get("points"):
        first_day = min(p["date"] for p in fc["points"])
        per_item: dict[str, list[float]] = {}
        for p in fc["points"]:
            if p["date"] == first_day:
                acc = per_item.setdefault(p["item_id"], [0.0, 0.0])
                acc[0] += p["forecast"]
                acc[1] += p["hi"]
        top = sorted(per_item.items(), key=lambda kv: -kv[1][0])[:3]
        if top:
            actions.append(
                {
                    "type": "prep_target",
                    "item_id": None,
                    "option_id": None,
                    "item": ", ".join(name(i) for i, _ in top),
                    "title": f"Prep targets for {first_day}",
                    "evidence": {
                        f"{name(i)} forecast / prep": f"{round(v[0], 1)} / {math.ceil(v[1])}"
                        for i, v in top
                    },
                    "estimated_impact_per_week": None,
                    "formula": "prep = ceil(sum over dayparts of the upper interval bound)",
                }
            )

    for rank, a in enumerate(actions, start=1):
        a["rank"] = rank
    return actions


def template_summary(facts: dict) -> str:
    k, w = facts["kpis"], facts["window"]
    if not k["orders"]:
        return (
            f"No orders between {w['start']} and {w['end']}. "
            "Generate demo data or take live orders to see analytics."
        )
    cur = facts["currency"]
    text = (
        f"In the {w['days']} days to {w['end']}: {k['orders']} orders, revenue "
        f"{cur} {k['revenue']}, average order {cur} {k['aov']}, contribution margin "
        f"{cur} {k['contribution_margin']} ({k['margin_pct']}%)."
    )
    money = [a for a in facts["actions"] if a["estimated_impact_per_week"] is not None]
    if money:
        text += (
            f" Top action: {money[0]['title']} "
            f"(estimated {cur} {money[0]['estimated_impact_per_week']} per week)."
        )
    pm = facts.get("payment_mix")
    if pm and (pm["bills"]["standard"] or pm["bills"]["digital"]):
        text += (
            f" Digital payments were {pm['digital_revenue_pct']}% of billed revenue and saved "
            f"guests {cur} {pm['digital_tax_saving']} in tax."
        )
    if facts["data_sources"]["simulated"]:
        text += " Figures include simulated demo orders."
    return text


async def compute_brief(
    db: AsyncSession, restaurant: Restaurant, inference: InferenceClient | None
) -> dict:
    today = local_today(restaurant)
    w = analytics.Window(
        restaurant.id, restaurant.timezone, today - timedelta(days=WINDOW_DAYS), today
    )
    week = analytics.Window(
        restaurant.id, restaurant.timezone, today - timedelta(days=6), today + timedelta(days=1)
    )
    names = await item_names(db, restaurant)
    sources = await analytics.order_counts_by_source(db, w)
    kpis = await analytics.kpis(db, w)
    totals = analytics.item_totals(await analytics.daily_item_sales(db, w), w.days / 7)
    rnames = row_names(totals, names)
    classes, thresholds = analytics.classify_menu(totals)
    payments = await analytics.payment_mix(db, w, restaurant)
    pairings = [
        {**p, "a_name": names.get(p["a"], ""), "b_name": names.get(p["b"], "")}
        for p in await analytics.top_pairings(db, w)
    ]
    peaks = await analytics.peak_hours(db, w)
    fc, run_id = await get_or_run_forecast(db, restaurant, today)
    await db.commit()

    actions = build_actions(
        totals, classes, thresholds, fc, rnames, await current_prices(db, restaurant)
    )
    backtest = (fc.get("backtest") or {}).get("methods", {})
    facts = {
        "restaurant": restaurant.name,
        "currency": restaurant.currency,
        "window": {
            "start": w.start.isoformat(),
            "end": (w.end - timedelta(days=1)).isoformat(),
            "days": w.days,
        },
        "data_sources": sources,
        "kpis": kpis,
        "actions": [
            {k: a[k] for k in ("rank", "title", "evidence", "estimated_impact_per_week")}
            for a in actions
        ],
        "top_pairings": [
            {"items": f"{p['a_name']} + {p['b_name']}", "lift": p["lift"]} for p in pairings
        ],
        "peak_hours": peaks,
        # Decimals as strings: the number guard reads numbers inside strings.
        "payment_mix": {
            "bills": payments["bills"],
            "revenue_share": payments["revenue_share"],
            "digital_revenue_pct": payments["digital_revenue_pct"],
            "tax_by_rate": [
                {"rate": str(r["rate"]), "tax": str(r["tax"])} for r in payments["tax_by_rate"]
            ],
            "digital_tax_saving": str(payments["digital_tax_saving"]),
        },
        "forecast": {
            "method": fc.get("method"),
            "low_confidence": fc.get("low_confidence"),
            "backtest_wape": {m: v["wape"] for m, v in backtest.items()},
        },
    }
    summary, source = await narrate(
        inference, db, facts, template_summary(facts), task="daily brief summary"
    )

    menu = [
        {
            "item_id": t["item_id"],
            "option_id": t["option_id"],
            "name": rnames[i],
            "units": t["units"],
            "weekly_units": t["weekly_units"],
            "revenue": t["revenue"],
            "unit_margin": t["unit_margin"],
            "contribution": t["contribution"],
            "menu_class": classes[i],
        }
        for i, t in sorted(totals.items(), key=lambda kv: -kv[1]["units"])
    ]
    return {
        "date": today.isoformat(),
        "currency": restaurant.currency,
        "window_start": facts["window"]["start"],
        "window_end": facts["window"]["end"],
        "data_sources": sources,
        "kpis": kpis,
        "menu_engineering": menu,
        "thresholds": thresholds,
        "pairings": pairings,
        "peak_hours": peaks,
        "payment_mix": payments,
        # Not narrated and not revenue: chai bought for others and handed out this week
        # (the last 7 local days, today included).
        "pay_forward": await pay_forward.window_totals(
            db, restaurant.id, week.params()["start"], week.params()["end"]
        ),
        "forecast": {
            "run_id": run_id,
            "method": fc.get("method"),
            "model_name": fc.get("model_name"),
            "history_days": fc.get("history_days", 0),
            "low_confidence": fc.get("low_confidence", True),
            "backtest": [{"method": m, **v} for m, v in backtest.items()],
            "points": [{**p, "name": names.get(p["item_id"], "")} for p in fc.get("points", [])],
        },
        "actions": actions,
        "summary": summary,
        "summary_source": source,
    }


async def compute_whatif(
    db: AsyncSession,
    restaurant: Restaurant,
    inference: InferenceClient | None,
    scenario: str,
    params: dict,
) -> dict:
    """What-if on the last WINDOW_DAYS of sales at current menu prices and costs."""
    today = local_today(restaurant)
    w = analytics.Window(
        restaurant.id, restaurant.timezone, today - timedelta(days=WINDOW_DAYS), today
    )
    names = await item_names(db, restaurant)
    sources = await analytics.order_counts_by_source(db, w)
    totals = analytics.item_totals(await analytics.daily_item_sales(db, w), w.days / 7)
    baselines = item_baselines(totals, names, await current_prices(db, restaurant))
    result = run_whatif(scenario, baselines, params, restaurant.currency)
    item_id = params.get("item_id")
    if item_id and any(t["item_id"] == str(item_id) and t["option_id"] for t in totals.values()):
        result["assumptions"].append(
            "Price change applies to every portion; current price shown is the "
            "units-weighted average of portion prices."
        )
    d = result["delta"]
    cur = restaurant.currency
    template = (
        f"Estimated weekly change: revenue {cur} {d['revenue']:+.2f}, contribution margin "
        f"{cur} {d['margin']:+.2f}, under the assumptions listed."
    )
    # Ids are dropped: their digits would otherwise count as "allowed" numbers.
    llm_facts = {
        **{k: v for k, v in result.items() if k != "params"},
        "currency": restaurant.currency,
        "item": names.get(str(item_id)) if item_id else None,
        "params": {k: v for k, v in params.items() if k != "item_id"},
    }
    explanation, source = await narrate(
        inference, db, llm_facts, template, task="explanation of this what-if calculation"
    )
    return {
        **result,
        "currency": restaurant.currency,
        "item": names.get(str(item_id)) if item_id else None,
        "window_start": w.start.isoformat(),
        "window_end": (w.end - timedelta(days=1)).isoformat(),
        "data_sources": sources,
        "explanation": explanation,
        "explanation_source": source,
    }
