"""API tests: simulated demo orders, deterministic brief, forecast_run storage and what-if."""

import time
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.config import settings
from src.models.forecast import ForecastRun
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.redis_client import redis_client


@pytest.fixture
async def seeded_restaurant(db_session: AsyncSession) -> Restaurant:
    data = load_seed_data("data/seed/trattoria_da_mario.json")
    await seed_data(data, db_session, rotate_qr=False)
    res = await db_session.execute(
        select(Restaurant).where(Restaurant.slug == "trattoria-da-mario")
    )
    return res.scalar_one()


@pytest.fixture(autouse=True)
async def _reset_simulate_rate_limit():
    """Each test starts with a fresh demo:simulate bucket for the test client's IP."""
    key = "rate_limit:demo:simulate:127.0.0.1"
    await redis_client.delete(key)
    yield
    await redis_client.delete(key)


def _as_owner(client: AsyncClient) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, sign_value(f"owner:{int(time.time()) + 3600}"))


async def _simulate(client: AsyncClient, slug: str, **body) -> dict:
    with patch.object(settings, "demo_mode", True):
        resp = await client.post(f"/api/restaurants/{slug}/demo/simulate-orders", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_simulate_orders_404_when_demo_mode_false(
    client: AsyncClient, seeded_restaurant: Restaurant
):
    _as_owner(client)
    with patch.object(settings, "demo_mode", False):
        resp = await client.post(
            f"/api/restaurants/{seeded_restaurant.slug}/demo/simulate-orders", json={}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_simulated_orders_feed_brief_and_forecast(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    slug = seeded_restaurant.slug
    _as_owner(client)

    summary = await _simulate(client, slug, days=56)
    n = summary["orders_created"]
    assert n > 500

    rows = (
        await db_session.execute(
            select(Order.source, Order.status, func.count())
            .where(Order.restaurant_id == seeded_restaurant.id)
            .group_by(Order.source, Order.status)
        )
    ).all()
    assert rows == [("simulated", "bumped", n)]

    # Re-running replaces simulated history instead of adding to it
    assert (await _simulate(client, slug, days=56))["orders_created"] == n
    total = (
        await db_session.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.restaurant_id == seeded_restaurant.id)
        )
    ).scalar_one()
    assert total == n

    # Simulated tickets never reach the kitchen display
    kitchen = await client.get(f"/api/restaurants/{slug}/kitchen/orders")
    assert kitchen.status_code == 200
    assert kitchen.json()["orders"] == []

    # No inference client on app.state in tests: the brief must still work (template path)
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    brief = resp.json()
    assert brief["summary_source"] == "template"
    assert "simulated" in brief["summary"]
    assert brief["data_sources"]["live"] == 0
    assert brief["data_sources"]["simulated"] > 0

    k = brief["kpis"]
    assert k["orders"] == brief["data_sources"]["simulated"]
    assert k["aov_eur"] == pytest.approx(k["revenue_eur"] / k["orders"], abs=0.01)
    assert 0 < k["margin_pct"] < 100

    classes = {m["menu_class"] for m in brief["menu_engineering"]}
    assert classes <= {"star", "plowhorse", "puzzle", "dog"}
    assert "star" in classes and "dog" in classes
    assert 3 <= len(brief["actions"]) <= 5

    fc = brief["forecast"]
    assert fc["low_confidence"] is False
    assert fc["history_days"] == 56
    methods = {b["method"]: b for b in fc["backtest"]}
    assert {"seasonal_naive", "trailing_4w_mean"} <= set(methods)
    assert methods[fc["method"]]["wape"] <= methods["seasonal_naive"]["wape"]
    assert len({p["date"] for p in fc["points"]}) == 7
    assert all(p["lo"] <= p["forecast"] <= p["hi"] for p in fc["points"])

    # Forecast is stored once and reused while the history is unchanged
    with patch.object(settings, "demo_mode", False):
        again = (await client.get(f"/api/restaurants/{slug}/ai/brief")).json()
    assert again["forecast"]["run_id"] == fc["run_id"]
    runs = (
        await db_session.execute(
            select(func.count())
            .select_from(ForecastRun)
            .where(ForecastRun.restaurant_id == seeded_restaurant.id)
        )
    ).scalar_one()
    assert runs == 1

    # What-if: demand surge is exact arithmetic on the same baseline
    resp = await client.post(
        f"/api/restaurants/{slug}/ai/simulate",
        json={"scenario": "demand_surge", "multiplier": 1.5},
    )
    assert resp.status_code == 200, resp.text
    wi = resp.json()
    assert wi["explanation_source"] == "template"
    assert wi["delta"]["revenue_eur"] == pytest.approx(
        wi["baseline"]["revenue_eur"] * 0.5, abs=0.02
    )
    assert wi["delta"]["margin_eur"] == pytest.approx(wi["baseline"]["margin_eur"] * 0.5, abs=0.02)
    assert wi["assumptions"]

    item_id = brief["menu_engineering"][0]["item_id"]
    resp = await client.post(
        f"/api/restaurants/{slug}/ai/simulate",
        json={"scenario": "price_change", "item_id": item_id, "change_pct": 10},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["item"] == brief["menu_engineering"][0]["name"]


@pytest.mark.asyncio
async def test_brief_with_no_orders_returns_empty_template(
    client: AsyncClient, seeded_restaurant: Restaurant
):
    _as_owner(client)
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{seeded_restaurant.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    brief = resp.json()
    assert brief["kpis"]["orders"] == 0
    assert brief["actions"] == []
    assert brief["forecast"]["low_confidence"] is True
    assert brief["summary_source"] == "template"


@pytest.mark.asyncio
async def test_whatif_unknown_item_returns_422(client: AsyncClient, seeded_restaurant: Restaurant):
    _as_owner(client)
    resp = await client.post(
        f"/api/restaurants/{seeded_restaurant.slug}/ai/simulate",
        json={
            "scenario": "price_change",
            "item_id": "00000000-0000-0000-0000-000000000000",
            "change_pct": 5,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_regenerating_demo_data_drops_stale_forecast(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    slug = seeded_restaurant.slug
    _as_owner(client)

    await _simulate(client, slug, days=28, seed=1)
    with patch.object(settings, "demo_mode", False):
        first = (await client.get(f"/api/restaurants/{slug}/ai/brief")).json()

    await _simulate(client, slug, days=28, seed=2)
    runs = (
        await db_session.execute(
            select(func.count())
            .select_from(ForecastRun)
            .where(ForecastRun.restaurant_id == seeded_restaurant.id)
        )
    ).scalar_one()
    assert runs == 0

    with patch.object(settings, "demo_mode", False):
        second = (await client.get(f"/api/restaurants/{slug}/ai/brief")).json()
    assert second["forecast"]["run_id"] != first["forecast"]["run_id"]


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_health_stays_responsive_while_forecast_recomputes(
    client: AsyncClient, seeded_restaurant: Restaurant
):
    """A slow forecast (CPU-bound in production) must not block other requests."""
    import asyncio
    import time as clock

    from src.services import brief as brief_module

    slug = seeded_restaurant.slug
    _as_owner(client)
    await _simulate(client, slug, days=28)

    real_forecast = brief_module.forecast
    started: list[float] = []

    def slow_forecast(fi):
        started.append(clock.monotonic())
        clock.sleep(1.5)  # blocks whatever thread runs it, like model fitting does
        return real_forecast(fi)

    with (
        patch.object(brief_module, "forecast", slow_forecast),
        patch.object(settings, "demo_mode", False),
    ):
        brief_task = asyncio.create_task(client.get(f"/api/restaurants/{slug}/ai/brief"))
        while not started:  # if the forecast blocked the loop, this resumes only after it
            await asyncio.sleep(0.01)
        health = await client.get("/health")
        health_latency = clock.monotonic() - started[0]
        brief_resp = await brief_task

    assert health.status_code == 200
    assert brief_resp.status_code == 200, brief_resp.text
    assert health_latency < 0.75, f"/health finished {health_latency:.2f}s after forecast start"
