"""Analytics, forecast, what-if and narration tests on a golden synthetic dataset (no database)."""

import json
import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from src.services.analytics import classify_menu, item_totals
from src.services.brief import (
    build_actions,
    item_baselines,
    row_names,
    template_summary,
)
from src.services.forecast import build_input, forecast
from src.services.narrative import narrate, numbers_grounded, numbers_in_text
from src.services.simulator import (
    SimAssumptions,
    SimItem,
    generate_orders,
    popularity_ranking,
    promo_window,
)
from src.services.whatif import ItemBaseline, run_whatif

TZ = ZoneInfo("Europe/Rome")
START = date(2026, 8, 1)
ITEM_IDS = [uuid.UUID(int=i + 1) for i in range(25)]
# Zipf-shaped weights (1 / rank) so the golden data keeps a clear popularity spread
SIM_ITEMS = [SimItem(id=i, weight=1 / (n + 1)) for n, i in enumerate(ITEM_IDS)]


def golden_input(days: int = 56, seed: int = 42):
    """Simulated orders aggregated exactly like analytics.daily_item_sales (local day, daypart)."""
    a = SimAssumptions(days=days, seed=seed)
    rows = []
    for o in generate_orders(SIM_ITEMS, START, a, TZ):
        local = o.placed_at.astimezone(TZ)
        daypart = "lunch" if local.hour < 18 else "dinner"
        rows.extend((str(item), local.date(), daypart, q) for (item, _), q in o.lines.items())
    window = promo_window(a, START)
    promo_item = str(popularity_ranking(SIM_ITEMS)[a.promo_item_rank])
    promos = [(promo_item, window[0], window[1])] if window else []
    return build_input(rows, promos, START, START + timedelta(days=days - 1))


# --- Simulator ---


def test_simulator_is_seeded_and_structured():
    a = SimAssumptions(days=14, seed=7)
    first = generate_orders(SIM_ITEMS, START, a, TZ)
    second = generate_orders(SIM_ITEMS, START, a, TZ)
    assert [(o.placed_at, o.lines) for o in first] == [(o.placed_at, o.lines) for o in second]
    assert first, "expected orders"
    for o in first:
        hour = o.placed_at.astimezone(TZ).hour
        assert 12 <= hour < 15 or 19 <= hour < 23
        assert all(1 <= q <= 20 for q in o.lines.values())
    # Weighted popularity: the rank-0 item outsells the last-ranked item
    ranked = popularity_ranking(SIM_ITEMS)
    units = {i: 0 for i in ITEM_IDS}
    for o in first:
        for (k, option), q in o.lines.items():
            assert option is None  # these items have no options
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
    assert thresholds == {"median_units": 50, "median_unit_margin": 5.0}
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
        "item_id": "a",
        "option_id": None,
        "option_label": None,
        "units": 4,
        "revenue": 40.0,
        "cost": 12.0,
        "contribution": 28.0,
        "unit_margin": 7.0,
        "weekly_units": 2.0,
    }


def test_item_totals_one_row_per_option():
    def row(option, label, units, revenue):
        return {
            "item_id": "k",
            "option_id": option,
            "option_label": label,
            "units": units,
            "revenue": revenue,
            "cost": 4.0 * units,
        }

    daily = [
        row("half", "½ kg", 2, 20.0),
        row("full", "1 kg", 1, 19.0),
        row("half", "½ kg", 1, 10.0),
    ]
    t = item_totals(daily, weeks=1)
    assert set(t) == {"k:half", "k:full"}
    assert t["k:half"]["units"] == 3 and t["k:half"]["option_label"] == "½ kg"
    # Bare item ids keep the dish name (forecast and prep look names up by item id)
    assert row_names(t, {"k": "Karahi"}) == {
        "k": "Karahi",
        "k:half": "Karahi — ½ kg",
        "k:full": "Karahi — 1 kg",
    }


def test_whatif_dish_with_options_equals_per_option_sum():
    """The summed what-if baseline of a dish gives the same deltas as its option rows."""
    totals = {
        "k:half": {"item_id": "k", "weekly_units": 10.0},
        "k:full": {"item_id": "k", "weekly_units": 4.0},
        "x": {"item_id": "x", "weekly_units": 5.0},
    }
    prices = {"k:half": (11.0, 5.0), "k:full": (21.0, 9.5), "x": (3.0, 1.0)}
    summed = item_baselines(totals, {"k": "Karahi", "x": "Tea"}, prices)
    assert {b.item_id for b in summed} == {"k", "x"}
    per_option = [ItemBaseline(i, i, totals[i]["weekly_units"], *prices[i]) for i in totals]

    got = run_whatif("price_change", summed, {"item_id": "k", "change_pct": 10})["delta"]
    parts = [
        run_whatif("price_change", per_option, {"item_id": o, "change_pct": 10})["delta"]
        for o in ("k:half", "k:full")
    ]
    for key in ("revenue", "margin"):
        assert got[key] == pytest.approx(sum(p[key] for p in parts), abs=0.02)

    got = run_whatif("demand_surge", summed, {"multiplier": 1.5})
    want = run_whatif("demand_surge", per_option, {"multiplier": 1.5})
    assert got["baseline"] == pytest.approx(want["baseline"], abs=0.02)
    assert got["delta"] == pytest.approx(want["delta"], abs=0.02)


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
    assert r["baseline"] == {"revenue": 1600.0, "margin": 960.0}
    assert r["result"] == {"revenue": 95 * 11 + 600, "margin": 95 * 7 + 360}
    assert r["delta"] == {"revenue": 45.0, "margin": 65.0}
    assert any("elasticity -0.5" in s for s in r["assumptions"])


def test_whatif_promotion():
    r = run_whatif("promotion", ITEMS, {"item_id": "b", "discount_pct": 20})
    # Steak: price 30 -> 24, units 20 x (1 + -2.0 x -20%) = 28
    assert r["result"]["revenue"] == pytest.approx(1000 + 28 * 24)
    assert r["delta"]["margin"] == pytest.approx(28 * 12 - 20 * 18)


def test_whatif_demand_surge():
    r = run_whatif("demand_surge", ITEMS, {"multiplier": 1.25})
    assert r["delta"] == {"revenue": 400.0, "margin": 240.0}


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
    for key, t in totals.items():  # shape of item_totals rows without options
        t.update(item_id=key, option_id=None)
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
    assert by_type["promote_puzzle"]["estimated_impact_per_week"] == 6.0  # 0.2 x 2.5 x 12
    assert by_type["review_dog"]["estimated_impact_per_week"] == 5.0  # 1.25 x (5 - 1)
    # Plowhorse: price 10, cost 8; +5% at -0.8 -> 22.5 x 0.96 x 2.5 - 22.5 x 2 = 9.0
    assert by_type["reprice_plowhorse"]["estimated_impact_per_week"] == 9.0
    assert actions[-1]["type"] == "prep_target"
    assert actions[-1]["evidence"] == {"Star forecast / prep": "7.0 / 12"}
    assert by_type["promote_puzzle"]["item_id"] == "puzzle"
    assert by_type["promote_puzzle"]["option_id"] is None
    money = [a["estimated_impact_per_week"] for a in actions[:-1]]
    assert money == sorted(money, reverse=True)


def test_actions_for_option_rows_carry_ids_and_prep_names_the_dish():
    """Rows are keyed item:option, but forecast points (prep) use bare menu item ids."""

    def row(item, option, label, units, margin):
        return {
            "item_id": item,
            "option_id": option,
            "option_label": label,
            "units": units,
            "weekly_units": units / 4,
            "unit_margin": margin,
            "revenue": 0.0,
            "contribution": units * margin,
        }

    totals = {
        "k:half": row("k", "half", "½ kg", 100, 10.0),
        "k:full": row("k", "full", "1 kg", 5, 1.0),
        "m:half": row("m", "half2", "½ kg", 90, 2.0),
        "m:full": row("m", "full2", "1 kg", 10, 12.0),
    }
    classes, thresholds = classify_menu(totals)
    names = row_names(totals, {"k": "Chicken Karahi", "m": "Mutton Karahi"})
    prices = {key: (20.0, 10.0) for key in totals}
    point = {"date": "2026-10-21", "daypart": "dinner", "forecast": 4.0, "lo": 2.0, "hi": 6.0}
    fc = {"points": [{**point, "item_id": "k"}, {**point, "item_id": "m", "forecast": 3.0}]}

    actions = build_actions(totals, classes, thresholds, fc, names, prices)

    prep = actions[-1]
    assert prep["type"] == "prep_target"
    assert prep["item"] == "Chicken Karahi, Mutton Karahi"
    assert prep["evidence"] == {
        "Chicken Karahi forecast / prep": "4.0 / 6",
        "Mutton Karahi forecast / prep": "3.0 / 6",
    }
    money = [a for a in actions if a["type"] != "prep_target"]
    assert money
    for a in money:
        assert a["item_id"] in {"k", "m"} and a["option_id"] is not None
        assert " — " in a["item"]


# --- Narration: invented numbers and LLM-down template path ---

FACTS = {
    "window": {"start": "2026-09-22", "end": "2026-10-19", "days": 28},
    "kpis": {"orders": 812, "revenue": 12345.67, "margin_pct": 72.9},
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
        "currency": "PKR",
        "kpis": {
            "orders": 812,
            "revenue": 12345.67,
            "aov": 15.2,
            "contribution_margin": 9000.1,
            "margin_pct": 72.9,
        },
        "data_sources": {"live": 0, "simulated": 812},
        "actions": [{"title": "Promote Puzzle", "estimated_impact_per_week": 6.0}],
    }
    text = template_summary(facts)
    assert "simulated" in text
    assert "PKR 12345.67" in text and "EUR" not in text
    assert numbers_grounded(text, facts)


def test_template_summary_states_digital_share_and_saving():
    facts = {
        **FACTS,
        "currency": "PKR",
        "kpis": {
            "orders": 4,
            "revenue": 4500.0,
            "aov": 1125.0,
            "contribution_margin": 2000.0,
            "margin_pct": 44.4,
        },
        "data_sources": {"live": 4, "simulated": 0},
        "actions": [],
        "payment_mix": {
            "bills": {"standard": 2, "digital": 2},
            "revenue_share": {"standard": 0.3333, "digital": 0.6667},
            "digital_revenue_pct": 66.67,
            "tax_by_rate": [{"rate": "0.08", "tax": "240.00"}, {"rate": "0.16", "tax": "240.00"}],
            "digital_tax_saving": "240.00",
        },
    }
    text = template_summary(facts)
    assert "Digital payments were 66.67% of billed revenue" in text
    assert "saved guests PKR 240.00 in tax" in text
    assert numbers_grounded(text, facts)


def test_brief_reprice_matches_whatif_at_current_menu_price():
    """For a dish without options, the brief's reprice and the what-if page agree.

    After a price change both use the current menu price, so the margin deltas match.
    """
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
    for key, t in totals.items():
        t.update(item_id=key, option_id=None)
    classes = {"plow": "plowhorse", "star": "star", "dog": "dog"}
    thresholds = {"median_units": 90, "median_unit_margin": 2.0}
    names = {k: k.title() for k in totals}
    # The owner raised the plowhorse from its historical 10.00 to 11.00 yesterday
    prices = {"plow": (11.0, 8.0), "star": (15.0, 5.0), "dog": (5.0, 4.0)}

    actions = build_actions(totals, classes, thresholds, {"points": []}, names, prices)
    reprice = next(a for a in actions if a["type"] == "reprice_plowhorse")

    # The what-if endpoint's baselines, over the whole menu
    baselines = item_baselines(totals, names, prices)
    whatif = run_whatif("price_change", baselines, {"item_id": "plow", "change_pct": 5})

    assert reprice["estimated_impact_per_week"] == whatif["delta"]["margin"]
    assert reprice["evidence"]["price"] == 11.0
    # 22.5 x 0.96 x (11.55 - 8) - 22.5 x 3 = 9.18
    assert whatif["delta"]["margin"] == 9.18
