"""Analytics, forecast, what-if and narration tests on a golden synthetic dataset (no database)."""

import json
import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from src.services.analytics import classify_menu, item_totals
from src.services.brief import baseline_for, build_actions, template_summary
from src.services.forecast import build_input, forecast
from src.services.narrative import narrate, numbers_grounded, numbers_in_text
from src.services.simulator import (
    SimAssumptions,
    generate_orders,
    popularity_ranking,
    promo_window,
)
from src.services.whatif import ItemBaseline, run_whatif

TZ = ZoneInfo("Europe/Rome")
START = date(2026, 8, 1)
ITEM_IDS = [uuid.UUID(int=i + 1) for i in range(25)]


def golden_input(days: int = 56, seed: int = 42):
    """Simulated orders aggregated exactly like analytics.daily_item_sales (local day, daypart)."""
    a = SimAssumptions(days=days, seed=seed)
    rows = []
    for o in generate_orders(ITEM_IDS, START, a, TZ):
        local = o.placed_at.astimezone(TZ)
        daypart = "lunch" if local.hour < 16 else "dinner"
        rows.extend((str(k), local.date(), daypart, q) for k, q in o.lines.items())
    window = promo_window(a, START)
    promo_item = str(popularity_ranking(ITEM_IDS, seed)[a.promo_item_rank])
    promos = [(promo_item, window[0], window[1])] if window else []
    return build_input(rows, promos, START, START + timedelta(days=days - 1))


# --- Simulator ---


def test_simulator_is_seeded_and_structured():
    a = SimAssumptions(days=14, seed=7)
    first = generate_orders(ITEM_IDS, START, a, TZ)
    second = generate_orders(ITEM_IDS, START, a, TZ)
    assert [(o.placed_at, o.lines) for o in first] == [(o.placed_at, o.lines) for o in second]
    assert first, "expected orders"
    for o in first:
        hour = o.placed_at.astimezone(TZ).hour
        assert 12 <= hour < 15 or 19 <= hour < 23
        assert all(1 <= q <= 20 for q in o.lines.values())
    # Zipf: the rank-0 item outsells the last-ranked item
    ranked = popularity_ranking(ITEM_IDS, 7)
    units = {i: 0 for i in ITEM_IDS}
    for o in first:
        for k, q in o.lines.items():
            units[k] += q
    assert units[ranked[0]] > units[ranked[-1]]


# --- Menu engineering ---


def test_classify_menu_golden():
    totals = {
        "star": {"units": 100, "unit_margin": 10.0},
        "plow": {"units": 90, "unit_margin": 2.0},
        "puzzle": {"units": 10, "unit_margin": 12.0},
        "dog": {"units": 5, "unit_margin": 1.0},
        "mid": {"units": 50, "unit_margin": 5.0},  # equals both medians -> star
    }
    classes, thresholds = classify_menu(totals)
    assert thresholds == {"median_units": 50, "median_unit_margin_eur": 5.0}
    assert classes == {
        "star": "star",
        "plow": "plowhorse",
        "puzzle": "puzzle",
        "dog": "dog",
        "mid": "star",
    }


def test_item_totals_margin_and_weekly_units():
    daily = [
        {"item_id": "a", "units": 3, "revenue": 30.0, "cost": 9.0},
        {"item_id": "a", "units": 1, "revenue": 10.0, "cost": 3.0},
    ]
    t = item_totals(daily, weeks=2)["a"]
    assert t == {
        "units": 4,
        "revenue": 40.0,
        "cost": 12.0,
        "contribution": 28.0,
        "unit_margin": 7.0,
        "weekly_units": 2.0,
    }


# --- Forecast ---


def test_forecast_backtest_beats_naive_on_structured_data():
    result = forecast(golden_input())
    methods = result["backtest"]["methods"]
    assert set(methods) == {"seasonal_naive", "trailing_4w_mean", "hgb"}
    naive = methods["seasonal_naive"]["wape"]
    assert methods[result["method"]]["wape"] < naive
    assert methods["hgb"]["wape"] < naive
    assert result["low_confidence"] is False
    assert result["history_days"] == 56


def test_forecast_golden_metrics_are_deterministic_and_complete():
    fi = golden_input()
    first, second = forecast(fi), forecast(fi)
    assert first == second
    n_series = len(fi.series)
    assert len(first["points"]) == n_series * 7
    for m in first["backtest"]["methods"].values():
        assert m["n_points"] == n_series * 14
        assert 0 < m["wape"] < 1.5
        assert m["mae"] > 0
    dates = sorted({p["date"] for p in first["points"]})
    assert dates[0] == (START + timedelta(days=56)).isoformat()
    assert len(dates) == 7
    assert all(p["lo"] <= p["forecast"] <= p["hi"] for p in first["points"])


def test_forecast_low_history_uses_baseline_without_backtest():
    result = forecast(golden_input(days=10))
    assert result["low_confidence"] is True
    assert result["backtest"] is None
    assert result["method"] == "trailing_4w_mean"
    assert result["points"]


def test_forecast_empty_history():
    result = forecast(build_input([], [], START, START))
    assert result["points"] == [] and result["low_confidence"] is True


# --- What-if arithmetic ---

ITEMS = [
    ItemBaseline("a", "Pasta", weekly_units=100, price=10.0, unit_cost=4.0),
    ItemBaseline("b", "Steak", weekly_units=20, price=30.0, unit_cost=12.0),
]


def test_whatif_price_change():
    r = run_whatif("price_change", ITEMS, {"item_id": "a", "change_pct": 10, "elasticity": -0.5})
    # Pasta: units 100 -> 95, price 10 -> 11
    assert r["baseline"] == {"revenue_eur": 1600.0, "margin_eur": 960.0}
    assert r["result"] == {"revenue_eur": 95 * 11 + 600, "margin_eur": 95 * 7 + 360}
    assert r["delta"] == {"revenue_eur": 45.0, "margin_eur": 65.0}
    assert any("elasticity -0.5" in s for s in r["assumptions"])


def test_whatif_promotion():
    r = run_whatif("promotion", ITEMS, {"item_id": "b", "discount_pct": 20})
    # Steak: price 30 -> 24, units 20 x (1 + -2.0 x -20%) = 28
    assert r["result"]["revenue_eur"] == pytest.approx(1000 + 28 * 24)
    assert r["delta"]["margin_eur"] == pytest.approx(28 * 12 - 20 * 18)


def test_whatif_demand_surge():
    r = run_whatif("demand_surge", ITEMS, {"multiplier": 1.25})
    assert r["delta"] == {"revenue_eur": 400.0, "margin_eur": 240.0}


def test_whatif_rejects_bad_input():
    with pytest.raises(ValueError):
        run_whatif("price_change", ITEMS, {"item_id": "missing"})
    with pytest.raises(ValueError):
        run_whatif("weather", ITEMS, {})


# --- Brief actions ---


def test_build_actions_ranked_with_formulas():
    totals = {
        "star": {
            "units": 100,
            "weekly_units": 25,
            "unit_margin": 10.0,
            "revenue": 1500.0,
            "contribution": 1000.0,
        },
        "plow": {
            "units": 90,
            "weekly_units": 22.5,
            "unit_margin": 2.0,
            "revenue": 900.0,
            "contribution": 180.0,
        },
        "puzzle": {
            "units": 10,
            "weekly_units": 2.5,
            "unit_margin": 12.0,
            "revenue": 200.0,
            "contribution": 120.0,
        },
        "dog": {
            "units": 5,
            "weekly_units": 1.25,
            "unit_margin": 1.0,
            "revenue": 25.0,
            "contribution": 5.0,
        },
        "mid": {
            "units": 50,
            "weekly_units": 12.5,
            "unit_margin": 5.0,
            "revenue": 500.0,
            "contribution": 250.0,
        },
    }
    classes, thresholds = classify_menu(totals)
    fc = {
        "points": [
            {
                "date": "2026-10-21",
                "item_id": "star",
                "daypart": "lunch",
                "forecast": 3.0,
                "lo": 1.0,
                "hi": 5.2,
            },
            {
                "date": "2026-10-21",
                "item_id": "star",
                "daypart": "dinner",
                "forecast": 4.0,
                "lo": 2.0,
                "hi": 6.1,
            },
            {
                "date": "2026-10-22",
                "item_id": "plow",
                "daypart": "dinner",
                "forecast": 9.0,
                "lo": 5.0,
                "hi": 12.0,
            },
        ]
    }
    names = {k: k.title() for k in totals}
    # Current menu (price, cost); plowhorse is unchanged since the window: 10 and 8
    prices = {
        "star": (15.0, 5.0),
        "plow": (10.0, 8.0),
        "puzzle": (20.0, 8.0),
        "dog": (5.0, 4.0),
        "mid": (10.0, 5.0),
    }
    actions = build_actions(totals, classes, thresholds, fc, names, prices)

    assert 3 <= len(actions) <= 5
    assert [a["rank"] for a in actions] == list(range(1, len(actions) + 1))
    by_type = {a["type"]: a for a in actions}
    assert by_type["promote_puzzle"]["estimated_impact_eur_per_week"] == 6.0  # 0.2 x 2.5 x 12
    assert by_type["review_dog"]["estimated_impact_eur_per_week"] == 5.0  # 1.25 x (5 - 1)
    # Plowhorse: price 10, cost 8; +5% at -0.8 -> 22.5 x 0.96 x 2.5 - 22.5 x 2 = 9.0
    assert by_type["reprice_plowhorse"]["estimated_impact_eur_per_week"] == 9.0
    assert actions[-1]["type"] == "prep_target"
    assert actions[-1]["evidence"] == {"Star forecast / prep": "7.0 / 12"}
    money = [a["estimated_impact_eur_per_week"] for a in actions[:-1]]
    assert money == sorted(money, reverse=True)


# --- Narration: invented numbers and LLM-down template path ---

FACTS = {
    "window": {"start": "2026-09-22", "end": "2026-10-19", "days": 28},
    "kpis": {"orders": 812, "revenue_eur": 12345.67, "margin_pct": 72.9},
}


def test_numbers_in_text_parses_separators_and_decimals():
    assert numbers_in_text("EUR 12,345.67 from 812 orders, 72.9%") == [
        (12345.67, 2),
        (812.0, 0),
        (72.9, 1),
    ]


def test_numbers_grounded_accepts_restated_and_rounded_facts():
    assert numbers_grounded("812 orders brought EUR 12,345.67 (about 12346), 72.9%.", FACTS)
    assert numbers_grounded("Revenue was strong over 28 days.", FACTS)


def test_numbers_grounded_rejects_invented_numbers():
    assert not numbers_grounded("Revenue grew 15% to EUR 12,345.67.", FACTS)
    assert not numbers_grounded("Expect 900 orders next week.", FACTS)


class _FakeInference:
    def __init__(self, summary=None, exc=None):
        self.summary, self.exc = summary, exc

    async def chat(self, messages, **kwargs):
        if self.exc:
            raise self.exc
        content = json.dumps({"summary": self.summary})
        metrics = {
            "model": "m",
            "endpoint": "chat",
            "tokens_in": 1,
            "tokens_out": 1,
            "latency_ms": 1,
        }
        return {"choices": [{"message": {"content": content}}]}, metrics


class _FakeDb:
    def add(self, obj):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_narrate_rejects_invented_number_and_uses_template():
    text, source = await narrate(
        _FakeInference("Revenue rose 18% to EUR 12,345.67."), _FakeDb(), FACTS, "TEMPLATE", "t"
    )
    assert (text, source) == ("TEMPLATE", "template")


@pytest.mark.asyncio
async def test_narrate_accepts_grounded_text():
    text, source = await narrate(
        _FakeInference("812 orders and EUR 12,345.67 in 28 days."), _FakeDb(), FACTS, "T", "t"
    )
    assert source == "llm" and text.startswith("812 orders")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inference",
    [None, _FakeInference(exc=HTTPException(status_code=503, detail="ai_unavailable"))],
)
async def test_narrate_llm_down_uses_template(inference):
    assert await narrate(inference, _FakeDb(), FACTS, "TEMPLATE", "t") == ("TEMPLATE", "template")


def test_template_summary_only_uses_fact_numbers():
    facts = {
        **FACTS,
        "kpis": {
            "orders": 812,
            "revenue_eur": 12345.67,
            "aov_eur": 15.2,
            "contribution_margin_eur": 9000.1,
            "margin_pct": 72.9,
        },
        "data_sources": {"live": 0, "simulated": 812},
        "actions": [{"title": "Promote Puzzle", "estimated_impact_eur_per_week": 6.0}],
    }
    text = template_summary(facts)
    assert "simulated" in text
    assert numbers_grounded(text, facts)


def test_brief_reprice_matches_whatif_at_current_menu_price():
    """After a price change the brief and the what-if page give the same margin delta."""
    totals = {
        "plow": {
            "units": 90,
            "weekly_units": 22.5,
            "unit_margin": 2.0,
            "revenue": 900.0,
            "contribution": 180.0,
        },
        "star": {
            "units": 100,
            "weekly_units": 25,
            "unit_margin": 10.0,
            "revenue": 1500.0,
            "contribution": 1000.0,
        },
        "dog": {
            "units": 5,
            "weekly_units": 1.25,
            "unit_margin": 1.0,
            "revenue": 25.0,
            "contribution": 5.0,
        },
    }
    classes = {"plow": "plowhorse", "star": "star", "dog": "dog"}
    thresholds = {"median_units": 90, "median_unit_margin_eur": 2.0}
    names = {k: k.title() for k in totals}
    # The owner raised the plowhorse from its historical 10.00 to 11.00 yesterday
    prices = {"plow": (11.0, 8.0), "star": (15.0, 5.0), "dog": (5.0, 4.0)}

    actions = build_actions(totals, classes, thresholds, {"points": []}, names, prices)
    reprice = next(a for a in actions if a["type"] == "reprice_plowhorse")

    # The what-if endpoint builds its baselines the same way, over the whole menu
    baselines = [baseline_for(i, names[i], t, *prices[i]) for i, t in totals.items()]
    whatif = run_whatif("price_change", baselines, {"item_id": "plow", "change_pct": 5})

    assert reprice["estimated_impact_eur_per_week"] == whatif["delta"]["margin_eur"]
    assert reprice["evidence"]["price_eur"] == 11.0
    # 22.5 x 0.96 x (11.55 - 8) - 22.5 x 3 = 9.18
    assert whatif["delta"]["margin_eur"] == 9.18
