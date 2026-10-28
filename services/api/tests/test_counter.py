"""Counter pickup: orders held until paid, daily numbers, expiry, cancel and collection."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, make_user, settle, sign_in
from tests.test_floor_api import record_events

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.user import User
from src.services import analytics
from src.services.bills import local_date, session_is_current
from src.services.counter import pickup_label

ROUNDS = 20


@dataclass
class CounterVenue:
    r: Restaurant
    counter: DiningTable
    t1: DiningTable
    naan: MenuItem


@pytest_asyncio.fixture
async def cv(db_session: AsyncSession) -> CounterVenue:
    r = Restaurant(
        name="Counter Venue",
        slug=f"counter-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
        pickup_prefix="K",
    )
    db_session.add(r)
    await db_session.flush()
    counter = DiningTable(
        restaurant_id=r.id, label="Counter", kind="counter", qr_token=uuid.uuid4().hex
    )
    t1 = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    naan = MenuItem(
        restaurant_id=r.id,
        category="breads",
        price=Decimal("60.00"),
        unit_cost=Decimal("9.00"),
        allergen_verified=True,
        dietary_verified=True,
    )
    naan.translations = [MenuTranslation(language="en", name="Naan")]
    db_session.add_all([counter, t1, naan])
    await db_session.flush()
    return CounterVenue(r, counter, t1, naan)


async def seat(db: AsyncSession, table: DiningTable) -> GuestSession:
    s = GuestSession(
        restaurant_id=table.restaurant_id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return s


async def order(client: AsyncClient, cv: CounterVenue, session: GuestSession) -> dict:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(cv.naan.id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def bill_of(db: AsyncSession, order_id: str) -> Bill:
    return (
        await db.execute(
            select(Bill)
            .join(Order, Order.bill_id == Bill.id)
            .where(Order.id == uuid.UUID(order_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def guest_bill(client: AsyncClient, session: GuestSession) -> dict:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    resp = await client.get("/api/guest/bill")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def kitchen(client: AsyncClient, cv: CounterVenue) -> dict[str, dict]:
    resp = await client.get(f"/api/restaurants/{cv.r.slug}/kitchen/orders")
    assert resp.status_code == 200, resp.text
    return {o["id"]: o for o in resp.json()["orders"]}


async def counter_list(client: AsyncClient, cv: CounterVenue, status: str = "open") -> dict:
    resp = await client.get(f"/api/restaurants/{cv.r.slug}/bills?kind=counter&status={status}")
    assert resp.status_code == 200, resp.text
    return {b["id"]: b for b in resp.json()["bills"]}


def test_pickup_label_never_wraps():
    assert pickup_label("K", 1) == "K-001"
    assert pickup_label("P", 999) == "P-999"
    assert pickup_label("K", 1000) == "K-1000"
    assert pickup_label(None, 42) == "K-042"


async def test_counter_lifecycle(client, db_session, cv, monkeypatch):
    events = record_events(
        monkeypatch, "src.routers.orders.publish_event", "src.routers.bills.publish_event"
    )
    s = await seat(db_session, cv.counter)
    assert await session_is_current(db_session, s)
    o1 = await order(client, cv, s)
    assert o1["status"] == "awaiting_payment"
    b1 = await bill_of(db_session, o1["id"])
    today = local_date(cv.r, datetime.now(UTC))
    assert (b1.table_id, b1.bill_no, b1.pickup_day, b1.pickup_no) == (None, 1, today, 1)
    assert [e["event"] for e in events] == ["bill_opened"]
    g = await guest_bill(client, s)
    assert (g["pickup_label"], g["order_status"]) == ("K-001", "awaiting_payment")

    # A second order from the same session never joins: its own bill and number.
    o2 = await order(client, cv, s)
    b2 = await bill_of(db_session, o2["id"])
    assert (b2.id != b1.id, b2.bill_no, b2.pickup_no) == (True, 2, 2)
    assert (await guest_bill(client, s))["pickup_label"] == "K-002"

    await as_member(client, db_session, cv.r.id, "staff")
    assert await kitchen(client, cv) == {}
    rows = await counter_list(client, cv)
    assert rows[str(b1.id)]["pickup_label"] == "K-001"
    assert rows[str(b1.id)]["order_status"] == "awaiting_payment"
    assert rows[str(b1.id)]["order_id"] == o1["id"]
    assert rows[str(b1.id)]["pickup_yesterday"] is False
    # Table and counter tabs never mix.
    tables = await client.get(f"/api/restaurants/{cv.r.slug}/bills?kind=table")
    assert tables.json()["bills"] == []

    events.clear()
    settled = await settle(client, cv.r.slug, b1.id)
    assert settled.status_code == 200, settled.text
    assert settled.json()["order_status"] == "placed"
    assert {"event": "order_placed", "order_id": o1["id"]} in events
    ticket = (await kitchen(client, cv))[o1["id"]]
    assert ticket["pickup_label"] == "K-001"
    assert o2["id"] not in await kitchen(client, cv)

    collect = f"/api/restaurants/{cv.r.slug}/orders/{o1['id']}/collect"
    uncollect = f"/api/restaurants/{cv.r.slug}/orders/{o1['id']}/uncollect"
    assert (await client.post(collect)).status_code == 409  # placed, not ready
    bumped = await client.post(f"/api/restaurants/{cv.r.slug}/kitchen/orders/{o1['id']}/bump")
    assert bumped.status_code == 200
    assert bumped.json()["pickup_label"] == "K-001"
    assert (await guest_bill(client, s))["order_status"] == "awaiting_payment"  # latest is o2
    client.cookies.delete(GUEST_COOKIE_NAME)

    events.clear()
    done = await client.post(collect)
    assert done.status_code == 200, done.text
    assert done.json()["order_status"] == "collected"
    assert events == [{"event": "order_collected", "order_id": o1["id"]}] * 2
    audit = await db_session.scalar(
        select(AuditLog.event_type).where(
            AuditLog.restaurant_id == cv.r.id, AuditLog.event_type == "order_collected"
        )
    )
    assert audit == "order_collected"
    assert (await client.post(collect)).status_code == 409
    # Recall cannot undo a collected order (Undo is uncollect).
    recall = f"/api/restaurants/{cv.r.slug}/kitchen/orders/{o1['id']}/recall"
    assert (await client.post(recall)).status_code == 409

    back = await client.post(uncollect)
    assert back.status_code == 200, back.text
    assert (back.json()["order_status"], back.json()["collected_at"]) == ("bumped", None)
    assert (await client.post(uncollect)).status_code == 409  # not collected
    assert (await client.post(collect)).status_code == 200
    await db_session.execute(
        update(Order)
        .where(Order.id == uuid.UUID(o1["id"]))
        .values(collected_at=datetime.now(UTC) - timedelta(seconds=61))
    )
    assert (await client.post(uncollect)).status_code == 409


async def test_guest_sees_bumped_and_collected(client, db_session, cv):
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    b = await bill_of(db_session, o["id"])
    await as_member(client, db_session, cv.r.id, "staff")
    assert (await settle(client, cv.r.slug, b.id)).status_code == 200
    assert (await guest_bill(client, s))["order_status"] == "placed"
    client.cookies.delete(GUEST_COOKIE_NAME)
    await client.post(f"/api/restaurants/{cv.r.slug}/kitchen/orders/{o['id']}/bump")
    assert (await guest_bill(client, s))["order_status"] == "bumped"
    client.cookies.delete(GUEST_COOKIE_NAME)
    await client.post(f"/api/restaurants/{cv.r.slug}/orders/{o['id']}/collect")
    assert (await guest_bill(client, s))["order_status"] == "collected"


async def test_collect_refuses_table_orders(client, db_session, cv):
    s = await seat(db_session, cv.t1)
    o = await order(client, cv, s)
    assert o["status"] == "placed"
    await as_member(client, db_session, cv.r.id, "staff")
    await client.post(f"/api/restaurants/{cv.r.slug}/kitchen/orders/{o['id']}/bump")
    resp = await client.post(f"/api/restaurants/{cv.r.slug}/orders/{o['id']}/collect")
    assert resp.status_code == 409


async def test_counter_guest_can_claim(client, db_session, cv):
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    resp = await client.post("/api/guest/bill/payment", json={"method": "cash"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["pickup_label"] == "K-001"
    assert (await bill_of(db_session, o["id"])).claimed_method == "cash"
    # No waiter calls from the counter.
    assert (
        await client.post("/api/guest/service-calls", json={"reason": "help"})
    ).status_code == 422


async def test_day_rollover_restarts_numbers_and_tags_yesterday(
    client, db_session, cv, monkeypatch
):
    s = await seat(db_session, cv.counter)
    o1 = await order(client, cv, s)
    tomorrow = local_date(cv.r, datetime.now(UTC)) + timedelta(days=1)
    monkeypatch.setattr("src.services.counter.local_date", lambda r, at: tomorrow)
    o2 = await order(client, cv, s)
    b1, b2 = await bill_of(db_session, o1["id"]), await bill_of(db_session, o2["id"])
    assert (b2.pickup_day, b2.pickup_no, b2.bill_no) == (tomorrow, 1, 2)
    await as_member(client, db_session, cv.r.id, "staff")
    rows = await counter_list(client, cv)
    assert rows[str(b1.id)]["pickup_yesterday"] is True
    assert rows[str(b2.id)]["pickup_yesterday"] is False


async def test_numbers_continue_past_999(client, db_session, cv):
    today = local_date(cv.r, datetime.now(UTC))
    db_session.add(
        Bill(
            restaurant_id=cv.r.id,
            bill_no=50,
            pickup_day=today,
            pickup_no=999,
            status="cancelled",
            cancelled_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    b = await bill_of(db_session, o["id"])
    assert (b.pickup_no, b.bill_no) == (1000, 51)
    assert (await guest_bill(client, s))["pickup_label"] == "K-1000"


async def _backdate(db: AsyncSession, order_id: str, minutes: int) -> None:
    await db.execute(
        update(Order)
        .where(Order.id == uuid.UUID(order_id))
        .values(placed_at=datetime.now(UTC) - timedelta(minutes=minutes))
    )


async def test_expiry_cancels_only_unclaimed_unpaid(client, db_session, cv):
    stale, claimed, paid, fresh = [await seat(db_session, cv.counter) for _ in range(4)]
    o_stale = await order(client, cv, stale)
    o_claimed = await order(client, cv, claimed)
    assert (
        await client.post("/api/guest/bill/payment", json={"method": "cash"})
    ).status_code == 200
    o_paid = await order(client, cv, paid)
    o_fresh = await order(client, cv, fresh)
    await as_member(client, db_session, cv.r.id, "staff")
    assert (
        await settle(client, cv.r.slug, (await bill_of(db_session, o_paid["id"])).id)
    ).status_code == 200
    for o in (o_stale, o_claimed, o_paid):
        await _backdate(db_session, o["id"], 31)
    await _backdate(db_session, o_fresh["id"], 29)

    open_rows = await counter_list(client, cv)
    b_stale = await bill_of(db_session, o_stale["id"])
    assert str(b_stale.id) not in open_rows
    assert (b_stale.status, b_stale.cancel_reason) == ("cancelled", "Expired unpaid")
    assert (
        await db_session.get(Order, uuid.UUID(o_stale["id"]), populate_existing=True)
    ).status == ("cancelled")
    assert (await bill_of(db_session, o_claimed["id"])).status == "open"
    assert (await bill_of(db_session, o_paid["id"])).status == "settled"
    assert (await bill_of(db_session, o_fresh["id"])).status == "open"
    cancelled = await counter_list(client, cv, "cancelled")
    assert cancelled[str(b_stale.id)]["order_status"] == "cancelled"


async def test_cancel_counter_bill(client, db_session, cv):
    plain, claimed, paid, table = (
        await seat(db_session, cv.counter),
        await seat(db_session, cv.counter),
        await seat(db_session, cv.counter),
        await seat(db_session, cv.t1),
    )
    o_plain = await order(client, cv, plain)
    o_claimed = await order(client, cv, claimed)
    assert (
        await client.post(
            "/api/guest/bill/payment", json={"method": "wallet", "reference": "TX4471"}
        )
    ).status_code == 200
    o_paid = await order(client, cv, paid)
    o_table = await order(client, cv, table)
    await as_member(client, db_session, cv.r.id, "staff")

    ids = {}
    for name, o in (
        ("plain", o_plain),
        ("claimed", o_claimed),
        ("paid", o_paid),
        ("table", o_table),
    ):
        ids[name] = (await bill_of(db_session, o["id"])).id
    base = f"/api/restaurants/{cv.r.slug}/bills"
    assert (await settle(client, cv.r.slug, ids["paid"])).status_code == 200

    resp = await client.post(f"{base}/{ids['plain']}/cancel", json={"reason": "Guest left"})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["status"], resp.json()["cancel_reason"]) == ("cancelled", "Guest left")
    assert resp.json()["order_status"] == "cancelled"

    assert (await client.post(f"{base}/{ids['claimed']}/cancel", json={})).status_code == 422
    resp = await client.post(f"{base}/{ids['claimed']}/cancel", json={"reason": "Never paid"})
    assert resp.status_code == 200, resp.text
    audit = (
        (
            await db_session.execute(
                select(AuditLog.payload).where(
                    AuditLog.restaurant_id == cv.r.id, AuditLog.event_type == "bill_cancelled"
                )
            )
        )
        .scalars()
        .all()
    )
    noted = [p for p in audit if p["bill_id"] == str(ids["claimed"])]
    assert noted[0]["claimed_method"] == "wallet"
    assert noted[0]["claimed_reference_last4"] == "4471"

    assert (
        await client.post(f"{base}/{ids['paid']}/cancel", json={"reason": "x"})
    ).status_code == 409
    assert (
        await client.post(f"{base}/{ids['table']}/cancel", json={"reason": "x"})
    ).status_code == 409
    assert (
        await client.post(f"{base}/{ids['plain']}/cancel", json={"reason": "x"})
    ).status_code == 409


async def test_analytics_exclude_awaiting_payment(client, db_session, cv):
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    today = local_date(cv.r, datetime.now(UTC))
    w = analytics.Window(
        cv.r.id, cv.r.timezone, today - timedelta(days=1), today + timedelta(days=1)
    )
    assert (await analytics.kpis(db_session, w))["orders"] == 0
    assert await analytics.daily_item_sales(db_session, w) == []
    await as_member(client, db_session, cv.r.id, "staff")
    assert (
        await settle(client, cv.r.slug, (await bill_of(db_session, o["id"])).id)
    ).status_code == 200
    k = await analytics.kpis(db_session, w)
    assert (k["orders"], k["revenue"]) == (1, 60.0)
    assert len(await analytics.daily_item_sales(db_session, w)) == 1


# --- Concurrency: committed data, parallel clients ---


@pytest_asyncio.fixture
async def committed_counter():
    rid, item_id, counter_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    slug = f"counter-par-{uuid.uuid4().hex[:8]}"
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=rid,
                name="Parallel Counter",
                slug=slug,
                currency="PKR",
                timezone="Asia/Karachi",
                languages=["en"],
                default_language="en",
                tax_jurisdiction="PB",
                pickup_prefix="K",
            )
        )
        await s.flush()
        s.add(
            DiningTable(
                id=counter_id,
                restaurant_id=rid,
                label="Counter",
                kind="counter",
                qr_token=uuid.uuid4().hex,
            )
        )
        s.add(
            MenuItem(
                id=item_id,
                restaurant_id=rid,
                category="breads",
                price=Decimal("60.00"),
                unit_cost=Decimal("9.00"),
                allergen_verified=True,
            )
        )
        await s.flush()
        s.add(MenuTranslation(menu_item_id=item_id, language="en", name="Naan"))
        staff = await make_user(s, [(rid, "staff")])
        await s.commit()
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        yield rid, slug, item_id, counter_id, staff
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override
        async with async_session_factory() as s:
            await s.execute(delete(AuditLog).where(AuditLog.restaurant_id == rid))
            await s.execute(delete(Order).where(Order.restaurant_id == rid))
            await s.execute(delete(Bill).where(Bill.restaurant_id == rid))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == rid))
            await s.execute(delete(MenuTranslation).where(MenuTranslation.menu_item_id == item_id))
            await s.execute(delete(MenuItem).where(MenuItem.restaurant_id == rid))
            await s.execute(delete(DiningTable).where(DiningTable.restaurant_id == rid))
            await s.execute(delete(Restaurant).where(Restaurant.id == rid))
            await s.execute(delete(User).where(User.id == staff.id))
            await s.commit()


async def _new_sessions(rid: uuid.UUID, counter_id: uuid.UUID, n: int) -> list[uuid.UUID]:
    async with async_session_factory() as s:
        sessions = [
            GuestSession(
                restaurant_id=rid,
                table_id=counter_id,
                language="en",
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
            for _ in range(n)
        ]
        s.add_all(sessions)
        await s.commit()
        return [x.id for x in sessions]


async def _post_order(session_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={GUEST_COOKIE_NAME: sign_value(str(session_id))},
    ) as c:
        resp = await c.post(
            "/api/orders",
            json={
                "idempotency_key": uuid.uuid4().hex,
                "items": [{"menu_item_id": str(item_id), "quantity": 1}],
                "acknowledge_allergen_risk": True,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()


@pytest.mark.timeout(120)
async def test_parallel_counter_orders_get_numbers_1_to_30(committed_counter):
    rid, _slug, item_id, counter_id, _staff = committed_counter
    sessions = await _new_sessions(rid, counter_id, 30)
    await asyncio.gather(*(_post_order(sid, item_id) for sid in sessions))
    async with async_session_factory() as s:
        rows = (
            await s.execute(select(Bill.pickup_no, Bill.bill_no).where(Bill.restaurant_id == rid))
        ).all()
    assert sorted(r.pickup_no for r in rows) == list(range(1, 31))
    assert sorted(r.bill_no for r in rows) == list(range(1, 31))


@pytest.mark.timeout(180)
async def test_expiry_racing_settle_never_mixes(committed_counter):
    rid, slug, item_id, counter_id, staff = committed_counter
    sessions = await _new_sessions(rid, counter_id, ROUNDS)
    orders = [await _post_order(sid, item_id) for sid in sessions]
    async with async_session_factory() as s:
        bill_ids = {
            o["id"]: (await s.scalar(select(Order.bill_id).where(Order.id == uuid.UUID(o["id"]))))
            for o in orders
        }
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as staff_a,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as staff_b,
    ):
        sign_in(staff_a, staff)
        sign_in(staff_b, staff)
        # Staff saw each bill before expiry: 60 + tax for cash.
        first = await staff_a.get(f"/api/restaurants/{slug}/bills/{bill_ids[orders[0]['id']]}")
        total = next(m["total"] for m in first.json()["methods"] if m["method"] == "cash")
        for n, o in enumerate(orders):
            # Only this round's order is past the 30 minutes: one bill races per round.
            async with async_session_factory() as s:
                await s.execute(
                    update(Order)
                    .where(Order.id == uuid.UUID(o["id"]))
                    .values(placed_at=datetime.now(UTC) - timedelta(minutes=31))
                )
                await s.commit()
            settle_req = staff_a.post(
                f"/api/restaurants/{slug}/bills/{bill_ids[o['id']]}/settle",
                json={"payment_method": "cash", "expected_method": "cash", "expected_total": total},
            )
            read_req = staff_b.get(f"/api/restaurants/{slug}/bills?kind=counter")
            if n % 2:
                settled, listed = await asyncio.gather(settle_req, read_req)
            else:
                listed, settled = await asyncio.gather(read_req, settle_req)
            assert listed.status_code == 200, listed.text
            assert settled.status_code in (200, 409), settled.text
    async with async_session_factory() as s:
        rows = (
            await s.execute(
                select(Bill.status, Order.status)
                .join(Order, Order.bill_id == Bill.id)
                .where(Bill.restaurant_id == rid)
            )
        ).all()
    assert len(rows) == ROUNDS
    outcomes = [(b, o) for b, o in rows]
    assert set(outcomes) <= {("settled", "placed"), ("cancelled", "cancelled")}, outcomes


async def test_counter_session_is_always_current(db_session, cv):
    s = await seat(db_session, cv.counter)
    cv.counter.cleared_at = datetime.now(UTC) + timedelta(minutes=1)  # a reset after the scan
    cv.t1.cleared_at = cv.counter.cleared_at
    await db_session.flush()
    assert await session_is_current(db_session, s)
    assert not await session_is_current(db_session, await seat(db_session, cv.t1))


async def _expired(client, db_session, cv) -> tuple[GuestSession, dict, Bill, str]:
    """A counter order left unpaid for 31 minutes and expired by a list read; its cash total."""
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    b = await bill_of(db_session, o["id"])
    await as_member(client, db_session, cv.r.id, "staff")
    detail = (await client.get(f"/api/restaurants/{cv.r.slug}/bills/{b.id}")).json()
    total = next(m["total"] for m in detail["methods"] if m["method"] == "cash")
    await _backdate(db_session, o["id"], 31)
    # Reading open bills with no kind expires too.
    assert str(b.id) not in {
        x["id"] for x in (await client.get(f"/api/restaurants/{cv.r.slug}/bills")).json()["bills"]
    }
    assert (await bill_of(db_session, o["id"])).status == "cancelled"
    return s, o, b, total


async def test_expired_order_can_still_be_settled(client, db_session, cv, monkeypatch):
    events = record_events(monkeypatch, "src.routers.bills.publish_event")
    _s, o, b, total = await _expired(client, db_session, cv)
    assert {"event": "order_cancelled", "order_id": o["id"]} in events
    events.clear()
    resp = await client.post(
        f"/api/restaurants/{cv.r.slug}/bills/{b.id}/settle",
        json={"payment_method": "cash", "expected_method": "cash", "expected_total": total},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["status"], body["order_status"], body["cancel_reason"]) == (
        "settled",
        "placed",
        None,
    )
    assert {"event": "order_revived", "order_id": o["id"]} in events
    assert {"event": "order_placed", "order_id": o["id"]} in events
    revived = await db_session.scalar(
        select(AuditLog.actor).where(
            AuditLog.restaurant_id == cv.r.id, AuditLog.event_type == "bill_revived"
        )
    )
    assert revived.startswith("user:")
    assert o["id"] in await kitchen(client, cv)


async def test_expired_order_revived_by_guest_claim(client, db_session, cv):
    s, o, b, _total = await _expired(client, db_session, cv)
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(s.id)))
    resp = await client.post("/api/guest/bill/payment", json={"method": "cash"})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["status"], resp.json()["order_status"]) == ("open", "awaiting_payment")
    client.cookies.delete(GUEST_COOKIE_NAME)
    row = (await counter_list(client, cv))[str(b.id)]
    assert row["claim"]["method"] == "cash"
    # A claimed bill is never expired again.
    assert (await bill_of(db_session, o["id"])).status == "open"


async def test_staff_cancelled_bill_is_never_revived(client, db_session, cv):
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    b = await bill_of(db_session, o["id"])
    await as_member(client, db_session, cv.r.id, "staff")
    detail = (await client.get(f"/api/restaurants/{cv.r.slug}/bills/{b.id}")).json()
    total = next(m["total"] for m in detail["methods"] if m["method"] == "cash")
    base = f"/api/restaurants/{cv.r.slug}/bills/{b.id}"
    assert (await client.post(f"{base}/cancel", json={"reason": "Guest left"})).status_code == 200
    resp = await client.post(
        f"{base}/settle",
        json={"payment_method": "cash", "expected_method": "cash", "expected_total": total},
    )
    assert (resp.status_code, resp.json()["detail"]) == (409, "Bill is not open")
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(s.id)))
    assert (
        await client.post("/api/guest/bill/payment", json={"method": "cash"})
    ).status_code == 409


async def test_awaiting_payment_cannot_be_bumped_or_voided(client, db_session, cv):
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    await as_member(client, db_session, cv.r.id, "staff")
    bump = await client.post(f"/api/restaurants/{cv.r.slug}/kitchen/orders/{o['id']}/bump")
    assert (bump.status_code, bump.json()["detail"]) == (409, "Awaiting payment")
    void = await client.post(
        f"/api/restaurants/{cv.r.slug}/orders/{o['id']}/void", json={"reason": "x"}
    )
    assert (void.status_code, void.json()["detail"]) == (409, "Awaiting payment")


async def test_pickup_prefix_locked_while_counter_orders_open(client, db_session, cv):
    await as_member(client, db_session, cv.r.id, "owner")
    url = f"/api/restaurants/{cv.r.slug}/settings"
    s = await seat(db_session, cv.counter)
    o = await order(client, cv, s)
    client.cookies.delete(GUEST_COOKIE_NAME)
    resp = await client.patch(url, json={"pickup_prefix": "Q"})
    assert (resp.status_code, resp.json()["detail"]) == (
        409,
        "Finish open counter orders before changing the prefix",
    )
    # The same value, or leaving it out, is not a change.
    assert (await client.patch(url, json={"pickup_prefix": "K"})).status_code == 200
    assert (await client.patch(url, json={})).json()["pickup_prefix"] == "K"
    b = await bill_of(db_session, o["id"])
    assert (
        await client.post(f"/api/restaurants/{cv.r.slug}/bills/{b.id}/cancel", json={})
    ).status_code == 200
    cleared = await client.patch(url, json={"pickup_prefix": None})
    assert (cleared.status_code, cleared.json()["pickup_prefix"]) == (200, None)
    assert (await client.patch(url, json={"pickup_prefix": "Q"})).json()["pickup_prefix"] == "Q"
