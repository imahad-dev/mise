"""API tests: simulated demo orders, deterministic brief, forecast_run storage and what-if."""

import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member

from src.auth import sign_value
from src.config import settings
from src.models.bill import Bill
from src.models.forecast import ForecastRun
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order, OrderItem
from src.models.restaurant import Restaurant
from src.redis_client import redis_client
from src.services.analytics import Window
from src.services.narrative import numbers_grounded


@pytest.fixture
async def seeded_restaurant(db_session: AsyncSession) -> Restaurant:
    data = load_seed_data("data/seed/angeethi_house.json")
    await seed_data(data, db_session, rotate_qr=False)
    res = await db_session.execute(select(Restaurant).where(Restaurant.slug == "angeethi-house"))
    return res.scalar_one()


@pytest.fixture(autouse=True)
async def _reset_simulate_rate_limit():
    """Each test starts with a fresh demo:simulate bucket for the test client's IP."""
    key = "rate_limit:demo:simulate:127.0.0.1"
    await redis_client.delete(key)
    yield
    await redis_client.delete(key)


async def _simulate(client: AsyncClient, slug: str, **body) -> dict:
    with patch.object(settings, "demo_mode", True):
        resp = await client.post(f"/api/restaurants/{slug}/demo/simulate-orders", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_simulate_orders_404_when_demo_mode_false(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    await as_member(client, db_session, seeded_restaurant.id, "owner")
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
    await db_session.execute(
        update(Restaurant).where(Restaurant.id == seeded_restaurant.id).values(currency="PKR")
    )
    await db_session.commit()
    await as_member(client, db_session, seeded_restaurant.id, "owner")

    summary = await _simulate(client, slug, days=56)
    n = summary["orders_created"]
    assert n > 500
    # The venue profile from the seed applies; the request still sets days and seed
    assert summary["assumptions"]["lunch_hours"] == [13, 16]
    assert summary["assumptions"]["payment_mix"][0] == ["cash", 0.6]
    assert summary["assumptions"]["days"] == 56
    assert summary["bills_created"] == n  # one settled bill per simulated party

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
    assert brief["currency"] == "PKR"
    assert "PKR " in brief["summary"] and "EUR" not in brief["summary"]
    assert brief["data_sources"]["live"] == 0
    assert brief["data_sources"]["simulated"] > 0

    k = brief["kpis"]
    assert k["orders"] == brief["data_sources"]["simulated"]
    assert k["aov"] == pytest.approx(k["revenue"] / k["orders"], abs=0.01)
    assert 0 < k["margin_pct"] < 100
    # Pakistan bills put tax on top: revenue stays the plain sum of order lines.
    wp = Window(
        seeded_restaurant.id,
        seeded_restaurant.timezone,
        date.fromisoformat(brief["window_start"]),
        date.fromisoformat(brief["window_end"]) + timedelta(days=1),
    ).params()
    gross = (
        await db_session.execute(
            select(func.sum(OrderItem.quantity * OrderItem.unit_price))
            .join(Order)
            .outerjoin(Bill, Bill.id == Order.bill_id)
            .where(
                Order.restaurant_id == seeded_restaurant.id,
                Order.status.in_(("placed", "bumped")),
                Order.source.in_(("live", "simulated")),
                or_(
                    Bill.status == "settled",
                    and_(Order.source == "simulated", Order.bill_id.is_(None)),
                ),
                Order.placed_at >= wp["start"],
                Order.placed_at < wp["end"],
            )
        )
    ).scalar_one()
    assert k["revenue"] == round(float(gross), 2)
    assert (brief["prices_include_tax"], brief["tax_split_by_method"]) == (False, True)
    assert "VAT" not in brief["summary"]

    classes = {m["menu_class"] for m in brief["menu_engineering"]}
    assert classes <= {"star", "plowhorse", "puzzle", "dog"}
    assert "star" in classes and "dog" in classes
    assert 3 <= len(brief["actions"]) <= 5
    # Actions name the menu item like menu_engineering rows do (never an item:option key)
    row_ids = {(m["item_id"], m["option_id"]) for m in brief["menu_engineering"]}
    for a in brief["actions"]:
        if a["type"] != "prep_target":
            assert (a["item_id"], a["option_id"]) in row_ids
        assert "Unknown item" not in a["item"]

    # One menu-engineering row per (dish, option): the karahi portions are separate rows
    karahi_id = (
        await db_session.execute(
            select(MenuTranslation.menu_item_id)
            .join(MenuItem)
            .where(
                MenuItem.restaurant_id == seeded_restaurant.id,
                MenuTranslation.name == "Chicken Karahi",
            )
        )
    ).scalar_one()
    rows = {m["name"]: m for m in brief["menu_engineering"]}
    for name in ("Chicken Karahi — ½ kg", "Chicken Karahi — 1 kg"):
        assert rows[name]["item_id"] == str(karahi_id)
        assert rows[name]["option_id"] is not None
    assert rows["Chicken Karahi — ½ kg"]["option_id"] != rows["Chicken Karahi — 1 kg"]["option_id"]

    # Every simulated party has a settled bill; the summary states digital share and saving
    pm = brief["payment_mix"]
    assert pm["bills"]["standard"] > 0 and pm["bills"]["digital"] > 0
    assert pm["revenue_share"]["digital"] > 0
    assert "Digital payments were" in brief["summary"]
    assert f"PKR {pm['digital_tax_saving']} in tax" in brief["summary"]
    assert f"Digital payments were {pm['digital_revenue_pct']}%" in brief["summary"]
    # Every number the summary states can be traced to the response itself.
    assert numbers_grounded(brief["summary"], {k: v for k, v in brief.items() if k != "summary"})

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
    assert wi["currency"] == "PKR"
    assert "PKR " in wi["explanation"] and "EUR" not in wi["explanation"]
    assert wi["delta"]["revenue"] == pytest.approx(wi["baseline"]["revenue"] * 0.5, abs=0.02)
    assert wi["delta"]["margin"] == pytest.approx(wi["baseline"]["margin"] * 0.5, abs=0.02)
    assert wi["assumptions"]

    plain = next(m for m in brief["menu_engineering"] if m["option_id"] is None)
    resp = await client.post(
        f"/api/restaurants/{slug}/ai/simulate",
        json={"scenario": "price_change", "item_id": plain["item_id"], "change_pct": 10},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["item"] == plain["name"]

    # A dish with options is addressed by its menu item id: the change applies to every portion
    resp = await client.post(
        f"/api/restaurants/{slug}/ai/simulate",
        json={"scenario": "price_change", "item_id": str(karahi_id), "change_pct": 10},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["item"] == "Chicken Karahi"
    assert resp.json()["delta"]["revenue"] != 0
    assert any("every portion" in a for a in resp.json()["assumptions"])


@pytest.mark.asyncio
async def test_brief_payment_mix_on_known_bills(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    """Four settled live bills: shares, tax per rate and the digital tax saving are exact."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from src.models.bill import Bill

    settled = datetime.now(UTC) - timedelta(days=1)
    known = [
        ("cash", "1000", "0.16", "160"),
        ("card", "2000", "0.08", "160"),
        ("wallet", "1000", "0.08", "80"),
        ("bank_transfer", "500", "0.16", "80"),
    ]
    for n, (method, subtotal, rate, tax) in enumerate(known, start=1):
        db_session.add(
            Bill(
                restaurant_id=seeded_restaurant.id,
                bill_no=n,
                status="settled",
                source="live",
                payment_method=method,
                subtotal=Decimal(subtotal),
                tax_jurisdiction="PB",
                tax_rate=Decimal(rate),
                tax_pricing="on_top",
                tax_amount=Decimal(tax),
                total=Decimal(subtotal) + Decimal(tax),
                opened_at=settled - timedelta(hours=1),
                settled_at=settled,
            )
        )
    await db_session.commit()
    await as_member(client, db_session, seeded_restaurant.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{seeded_restaurant.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_mix"] == {
        "bills": {"standard": 2, "digital": 2},
        "revenue_share": {"standard": 0.3333, "digital": 0.6667},
        "digital_revenue_pct": 66.67,
        "tax_by_rate": [{"rate": "0.08", "tax": "240.00"}, {"rate": "0.16", "tax": "240.00"}],
        "digital_tax_saving": "240.00",
    }


@pytest.mark.asyncio
async def test_brief_payment_mix_without_bills_is_zero(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    await as_member(client, db_session, seeded_restaurant.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{seeded_restaurant.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_mix"] == {
        "bills": {"standard": 0, "digital": 0},
        "revenue_share": {"standard": 0.0, "digital": 0.0},
        "digital_revenue_pct": 0.0,
        "tax_by_rate": [],
        "digital_tax_saving": "0.00",
    }


@pytest.mark.asyncio
async def test_brief_with_no_orders_returns_empty_template(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    await as_member(client, db_session, seeded_restaurant.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{seeded_restaurant.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    brief = resp.json()
    assert brief["kpis"]["orders"] == 0
    assert brief["actions"] == []
    assert brief["forecast"]["low_confidence"] is True
    assert brief["summary_source"] == "template"


@pytest.mark.asyncio
async def test_whatif_unknown_item_returns_422(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    await as_member(client, db_session, seeded_restaurant.id, "owner")
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
    await as_member(client, db_session, seeded_restaurant.id, "owner")

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
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    """A slow forecast (CPU-bound in production) must not block other requests."""
    import asyncio
    import time as clock

    from src.services import brief as brief_module

    slug = seeded_restaurant.slug
    await as_member(client, db_session, seeded_restaurant.id, "owner")
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


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_generate_demo_data_keeps_live_orders(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant
):
    """Live orders, their items and their guest session survive; simulated rows are replaced."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from src.auth import GUEST_COOKIE_NAME
    from src.models.menu import MenuItem
    from src.models.order import OrderItem
    from src.models.session import GuestSession

    slug = seeded_restaurant.slug
    guest = GuestSession(
        restaurant_id=seeded_restaurant.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(guest)
    await db_session.flush()
    item_ids = list(
        (
            await db_session.execute(
                select(MenuItem.id).where(MenuItem.restaurant_id == seeded_restaurant.id).limit(2)
            )
        ).scalars()
    )
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(guest.id)))
    placed = await client.post(
        "/api/orders",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "items": [{"menu_item_id": str(i), "quantity": 2} for i in item_ids],
            "acknowledge_allergen_risk": True,
        },
    )
    assert placed.status_code == 201, placed.text
    live_id = uuid.UUID(placed.json()["id"])

    async def snapshot():
        live = (
            await db_session.execute(select(Order.source).where(Order.id == live_id))
        ).scalar_one_or_none()
        live_items = (
            await db_session.execute(
                select(func.count()).select_from(OrderItem).where(OrderItem.order_id == live_id)
            )
        ).scalar_one()
        session_alive = (
            await db_session.execute(select(GuestSession.id).where(GuestSession.id == guest.id))
        ).scalar_one_or_none() is not None
        simulated = set(
            (
                await db_session.execute(
                    select(Order.id).where(
                        Order.restaurant_id == seeded_restaurant.id, Order.source == "simulated"
                    )
                )
            ).scalars()
        )
        return live, live_items, session_alive, simulated

    # A simulated-source order sharing the live session must not take the session with it.
    db_session.add(
        Order(
            guest_session_id=guest.id,
            restaurant_id=seeded_restaurant.id,
            status="bumped",
            source="simulated",
            total=0,
            idempotency_key="sim-shared-session",
            payload_hash="x",
            bumped_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    await as_member(client, db_session, seeded_restaurant.id, "owner")
    n1 = (await _simulate(client, slug, days=14, seed=1))["orders_created"]
    live, live_items, session_alive, sim_first = await snapshot()
    assert (live, live_items, session_alive) == ("live", 2, True)
    assert len(sim_first) == n1

    n2 = (await _simulate(client, slug, days=14, seed=2))["orders_created"]
    live, live_items, session_alive, sim_second = await snapshot()
    assert (live, live_items, session_alive) == ("live", 2, True)
    assert len(sim_second) == n2
    assert not sim_first & sim_second  # every simulated order was replaced


@pytest.mark.asyncio
async def test_demo_tools_404_for_non_demo_venue_even_in_demo_mode(
    client: AsyncClient, db_session: AsyncSession
):
    """An owner of a real venue cannot generate or reset demo data, nor write rows."""
    real = Restaurant(
        name="Real Venue",
        slug="real-venue",
        timezone="Asia/Karachi",
        currency="PKR",
        languages=["en"],
        default_language="en",
    )
    db_session.add(real)
    await db_session.flush()
    await as_member(client, db_session, real.id, "owner")
    with patch.object(settings, "demo_mode", True):
        sim = await client.post("/api/restaurants/real-venue/demo/simulate-orders", json={})
        reset = await client.post("/api/restaurants/real-venue/demo/reset")
    assert sim.status_code == 404
    assert reset.status_code == 404
    count = await db_session.scalar(
        select(func.count()).select_from(Order).where(Order.restaurant_id == real.id)
    )
    assert count == 0


async def _settled_order(
    db: AsyncSession,
    restaurant: Restaurant,
    lines: list[tuple[str, int, list[dict]]],
    *,
    n: int,
    pricing: str,
    rate: str,
    tax: str,
    jurisdiction: str,
) -> None:
    """One settled bill with one order. lines: (unit_price, quantity, choices snapshot)."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from src.models.session import GuestSession

    placed = datetime.now(UTC) - timedelta(days=1)
    item = (
        await db.execute(select(MenuItem).where(MenuItem.restaurant_id == restaurant.id).limit(1))
    ).scalar_one()
    guest = GuestSession(
        restaurant_id=restaurant.id, language="en", expires_at=placed + timedelta(hours=4)
    )
    db.add(guest)
    subtotal = sum(Decimal(p) * q for p, q, _ in lines)
    bill = Bill(
        restaurant_id=restaurant.id,
        bill_no=n,
        status="settled",
        source="live",
        payment_method="cash",
        subtotal=subtotal,
        tax_jurisdiction=jurisdiction,
        tax_rate=Decimal(rate),
        tax_pricing=pricing,
        tax_amount=Decimal(tax),
        total=subtotal + (Decimal(tax) if pricing == "on_top" else 0),
        opened_at=placed,
        settled_at=placed,
    )
    db.add(bill)
    await db.flush()
    order = Order(
        guest_session_id=guest.id,
        restaurant_id=restaurant.id,
        bill_id=bill.id,
        status="bumped",
        source="live",
        total=subtotal,
        idempotency_key=f"extras-{n}",
        payload_hash="x",
        placed_at=placed,
        bumped_at=placed,
    )
    db.add(order)
    await db.flush()
    for price, qty, choices in lines:
        db.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                quantity=qty,
                unit_price=Decimal(price),
                unit_cost=Decimal("1.00"),
                item_name="Coffee",
                kitchen_name="Coffee",
                allergen_verified=True,
                allergen_status="no_declared_match",
                choices=choices,
            )
        )
    await db.commit()


def _extra(label: str, delta: str) -> dict:
    return {
        "choice_id": str(uuid.uuid4()),
        "group": "Extras",
        "kind": "extra",
        "label": label,
        "price_delta": delta,
        "cost_delta": "0.00",
        "allergens": [],
    }


def _window(restaurant: Restaurant) -> Window:
    today = date.today()
    return Window(
        restaurant.id, restaurant.timezone, today - timedelta(days=3), today + timedelta(days=2)
    )


@pytest.mark.asyncio
async def test_extras_summary(db_session: AsyncSession, seeded_restaurant: Restaurant):
    """GB bill, VAT 20% included. Line A: 5.50 x2 with a 0.50 extra; line B: 3.00 plain.

    subtotal 14.00, VAT 2.33, so net factor 14.00 / 11.67; extras 2 x 0.50 / 1.19966 = 0.83.
    One of two lines carries a priced extra.
    """
    from src.services import analytics

    await _settled_order(
        db_session,
        seeded_restaurant,
        [("5.50", 2, [_extra("Extra milk", "0.50")]), ("3.00", 1, [])],
        n=1,
        pricing="included",
        rate="0.2000",
        tax="2.33",
        jurisdiction="GB",
    )
    summary = await analytics.extras_summary(db_session, _window(seeded_restaurant))
    assert summary["attach_rate_pct"] == 50.0
    assert summary["sales"] == pytest.approx(0.83, abs=0.005)
    assert summary["top"] == [{"label": "Extra milk", "count": 2}]


@pytest.mark.asyncio
async def test_extras_summary_tax_on_top_is_not_scaled(
    db_session: AsyncSession, seeded_restaurant: Restaurant
):
    """Tax on top (Pakistan): the extra counts at full price; free choices never count."""
    from src.services import analytics

    await _settled_order(
        db_session,
        seeded_restaurant,
        [
            ("5.50", 2, [_extra("Extra milk", "0.50"), _extra("Oat swap", "0.00")]),
            ("3.00", 1, [_extra("No sugar", "0.00")]),
        ],
        n=1,
        pricing="on_top",
        rate="0.1600",
        tax="2.24",
        jurisdiction="PB",
    )
    summary = await analytics.extras_summary(db_session, _window(seeded_restaurant))
    assert summary == {
        "attach_rate_pct": 50.0,
        "sales": 1.0,
        "top": [{"label": "Extra milk", "count": 2}],
    }


@pytest.mark.asyncio
async def test_extras_summary_empty(db_session: AsyncSession, seeded_restaurant: Restaurant):
    """An empty window, and one with only plain lines, give zeros, not a division error."""
    from src.services import analytics

    assert await analytics.extras_summary(db_session, _window(seeded_restaurant)) == {
        "attach_rate_pct": 0.0,
        "sales": 0.0,
        "top": [],
    }
    await _settled_order(
        db_session,
        seeded_restaurant,
        [("3.00", 1, [])],
        n=1,
        pricing="on_top",
        rate="0.1600",
        tax="0.48",
        jurisdiction="PB",
    )
    assert await analytics.extras_summary(db_session, _window(seeded_restaurant)) == {
        "attach_rate_pct": 0.0,
        "sales": 0.0,
        "top": [],
    }


@pytest.mark.asyncio
async def test_brief_carries_extras_but_the_model_never_sees_them(
    client: AsyncClient, db_session: AsyncSession, seeded_restaurant: Restaurant, monkeypatch
):
    await _settled_order(
        db_session,
        seeded_restaurant,
        [("5.50", 2, [_extra("Extra milk", "0.50")]), ("3.00", 1, [])],
        n=1,
        pricing="included",
        rate="0.2000",
        tax="2.33",
        jurisdiction="GB",
    )
    seen: dict = {}

    async def spy(inference, db, facts, template, task):
        seen.update(facts)
        return template, "template"

    monkeypatch.setattr("src.services.brief.narrate", spy)
    await as_member(client, db_session, seeded_restaurant.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(f"/api/restaurants/{seeded_restaurant.slug}/ai/brief")
    assert resp.status_code == 200, resp.text
    extras = resp.json()["extras"]
    assert extras["attach_rate_pct"] == 50.0
    assert extras["top"] == [{"label": "Extra milk", "count": 2}]
    assert seen and "extras" not in seen


@pytest.mark.asyncio
async def test_extras_summary_line_with_two_priced_extras(
    db_session: AsyncSession, seeded_restaurant: Restaurant
):
    """One line, quantity 2, extras +0.50 and +0.80 (tax on top): sales sum both, the line is
    one attach, and each label counts twice."""
    from src.services import analytics

    await _settled_order(
        db_session,
        seeded_restaurant,
        [("6.30", 2, [_extra("Extra milk", "0.50"), _extra("Extra shot", "0.80")])],
        n=1,
        pricing="on_top",
        rate="0.1600",
        tax="2.02",
        jurisdiction="PB",
    )
    summary = await analytics.extras_summary(db_session, _window(seeded_restaurant))
    assert summary["attach_rate_pct"] == 100.0
    assert summary["sales"] == pytest.approx(2.6)  # 2 x (0.50 + 0.80)
    assert summary["top"] == [
        {"label": "Extra milk", "count": 2},
        {"label": "Extra shot", "count": 2},
    ]
