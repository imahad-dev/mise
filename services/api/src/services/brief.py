"""Daily brief: deterministic facts and ranked actions; the LLM only narrates them.

Action formulas (all weekly, documented in docs/analytics.md):
- promote_puzzle: +PROMOTE_UPLIFT x weekly_units x unit_margin
- reprice_plowhorse: what-if price_change of +REPRICE_PCT% at the default price elasticity
- review_dog: weekly_units x (median_unit_margin - unit_margin), the gain if its volume moved
  to a median-margin dish
- prep_target: ceil of the summed upper forecast bound for the next service day (no EUR impact)
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.models.forecast import ForecastRun
from src.models.menu import MenuItem, MenuTranslation
from src.services import analytics
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
        rows = [(r["item_id"], r["date"], r["daypart"], r["units"]) for r in daily]
        fi = build_input(
            rows, await analytics.promotions(db, restaurant.id), first, w.end - timedelta(days=1)
        )
        params["history_start"] = first.isoformat()
        result = forecast(fi)
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
                "item_id": i,
                "item": name(i),
                "title": f"Promote {name(i)}",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "unit_margin_eur": t["unit_margin"],
                    "median_units": thresholds["median_units"],
                },
                "estimated_impact_eur_per_week": round(
                    PROMOTE_UPLIFT * t["weekly_units"] * t["unit_margin"], 2
                ),
                "formula": f"{PROMOTE_UPLIFT} x weekly_units x unit_margin_eur",
            }
        )

    for i in sorted(by_class["plowhorse"], key=lambda i: -totals[i]["units"])[:2]:
        t = totals[i]
        price = t["revenue"] / t["units"]
        base = ItemBaseline(i, name(i), t["weekly_units"], price, price - t["unit_margin"])
        wi = run_whatif("price_change", [base], {"item_id": i, "change_pct": REPRICE_PCT})
        money.append(
            {
                "type": "reprice_plowhorse",
                "item_id": i,
                "item": name(i),
                "title": f"Raise the price of {name(i)} by {REPRICE_PCT}%",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "avg_price_eur": round(price, 2),
                    "unit_margin_eur": t["unit_margin"],
                    "median_unit_margin_eur": thresholds["median_unit_margin_eur"],
                },
                "estimated_impact_eur_per_week": wi["delta"]["margin_eur"],
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
        gap = thresholds["median_unit_margin_eur"] - t["unit_margin"]
        money.append(
            {
                "type": "review_dog",
                "item_id": i,
                "item": name(i),
                "title": f"Review {name(i)} (rework, reprice or replace)",
                "evidence": {
                    "weekly_units": t["weekly_units"],
                    "unit_margin_eur": t["unit_margin"],
                    "median_unit_margin_eur": thresholds["median_unit_margin_eur"],
                },
                "estimated_impact_eur_per_week": round(t["weekly_units"] * gap, 2),
                "formula": "weekly_units x (median_unit_margin_eur - unit_margin_eur)",
            }
        )

    money.sort(key=lambda a: -(a["estimated_impact_eur_per_week"] or 0))
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
                    "item": ", ".join(name(i) for i, _ in top),
                    "title": f"Prep targets for {first_day}",
                    "evidence": {
                        f"{name(i)} forecast / prep": f"{round(v[0], 1)} / {math.ceil(v[1])}"
                        for i, v in top
                    },
                    "estimated_impact_eur_per_week": None,
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
    text = (
        f"In the {w['days']} days to {w['end']}: {k['orders']} orders, revenue "
        f"EUR {k['revenue_eur']}, average order EUR {k['aov_eur']}, contribution margin "
        f"EUR {k['contribution_margin_eur']} ({k['margin_pct']}%)."
    )
    money = [a for a in facts["actions"] if a["estimated_impact_eur_per_week"] is not None]
    if money:
        text += (
            f" Top action: {money[0]['title']} "
            f"(estimated EUR {money[0]['estimated_impact_eur_per_week']} per week)."
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
    names = await item_names(db, restaurant)
    sources = await analytics.order_counts_by_source(db, w)
    kpis = await analytics.kpis(db, w)
    totals = analytics.item_totals(await analytics.daily_item_sales(db, w), w.days / 7)
    classes, thresholds = analytics.classify_menu(totals)
    pairings = [
        {**p, "a_name": names.get(p["a"], ""), "b_name": names.get(p["b"], "")}
        for p in await analytics.top_pairings(db, w)
    ]
    peaks = await analytics.peak_hours(db, w)
    fc, run_id = await get_or_run_forecast(db, restaurant, today)
    await db.commit()

    actions = build_actions(totals, classes, thresholds, fc, names)
    backtest = (fc.get("backtest") or {}).get("methods", {})
    facts = {
        "restaurant": restaurant.name,
        "window": {
            "start": w.start.isoformat(),
            "end": (w.end - timedelta(days=1)).isoformat(),
            "days": w.days,
        },
        "data_sources": sources,
        "kpis": kpis,
        "actions": [
            {k: a[k] for k in ("rank", "title", "evidence", "estimated_impact_eur_per_week")}
            for a in actions
        ],
        "top_pairings": [
            {"items": f"{p['a_name']} + {p['b_name']}", "lift": p["lift"]} for p in pairings
        ],
        "peak_hours": peaks,
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
            "item_id": i,
            "name": names.get(i, "Unknown item"),
            "units": t["units"],
            "weekly_units": t["weekly_units"],
            "revenue_eur": t["revenue"],
            "unit_margin_eur": t["unit_margin"],
            "contribution_eur": t["contribution"],
            "menu_class": classes[i],
        }
        for i, t in sorted(totals.items(), key=lambda kv: -kv[1]["units"])
    ]
    return {
        "date": today.isoformat(),
        "window_start": facts["window"]["start"],
        "window_end": facts["window"]["end"],
        "data_sources": sources,
        "kpis": kpis,
        "menu_engineering": menu,
        "thresholds": thresholds,
        "pairings": pairings,
        "peak_hours": peaks,
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
    menu = {
        str(m.id): m
        for m in (
            await db.execute(select(MenuItem).where(MenuItem.restaurant_id == restaurant.id))
        ).scalars()
    }
    baselines = [
        ItemBaseline(
            i, names.get(i, ""), t["weekly_units"], float(menu[i].price), float(menu[i].unit_cost)
        )
        for i, t in totals.items()
        if i in menu
    ]
    result = run_whatif(scenario, baselines, params)
    d = result["delta"]
    template = (
        f"Estimated weekly change: revenue {d['revenue_eur']:+.2f} EUR, contribution margin "
        f"{d['margin_eur']:+.2f} EUR, under the assumptions listed."
    )
    item_id = params.get("item_id")
    # Ids are dropped: their digits would otherwise count as "allowed" numbers.
    llm_facts = {
        **{k: v for k, v in result.items() if k != "params"},
        "item": names.get(str(item_id)) if item_id else None,
        "params": {k: v for k, v in params.items() if k != "item_id"},
    }
    explanation, source = await narrate(
        inference, db, llm_facts, template, task="explanation of this what-if calculation"
    )
    return {
        **result,
        "item": names.get(str(item_id)) if item_id else None,
        "window_start": w.start.isoformat(),
        "window_end": (w.end - timedelta(days=1)).isoformat(),
        "data_sources": sources,
        "explanation": explanation,
        "explanation_source": source,
    }
