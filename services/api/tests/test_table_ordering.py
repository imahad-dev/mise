"""Safer table ordering: the table must be open, a visit's orders wait for the waiter until
one is approved, the table code, and per-phone order limits."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, open_table, settle

from src.auth import AUTH_COOKIE_NAME, GUEST_COOKIE_NAME, sign_value
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.redis_client import redis_client


@dataclass
class TV:
    r: Restaurant
    t1: DiningTable
    naan: MenuItem  # 60
    karahi: MenuItem  # 1100
    s1: GuestSession


def _item(rid: uuid.UUID, name: str, price: str) -> MenuItem:
    item = MenuItem(
        restaurant_id=rid,
        category="mains",
        price=Decimal(price),
        unit_cost=Decimal("1.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


async def new_session(db: AsyncSession, tv: TV) -> GuestSession:
    s = GuestSession(
        restaurant_id=tv.r.id,
        table_id=tv.t1.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture
async def tv(db_session: AsyncSession) -> TV:
    r = Restaurant(
        name="Ordering Venue",
        slug=f"ordering-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(r)
    await db_session.flush()
    t1 = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    naan, karahi = _item(r.id, "Naan", "60.00"), _item(r.id, "Chicken Karahi", "1100.00")
    db_session.add_all([t1, naan, karahi])
    await db_session.flush()
    venue = TV(r, t1, naan, karahi, None)  # type: ignore[arg-type]
    venue.s1 = await new_session(db_session, venue)
    return venue


async def post_order(
    client: AsyncClient,
    session: GuestSession,
    item: MenuItem,
    qty: int = 1,
    key: str | None = None,
    **extra,
):
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    return await client.post(
        "/api/orders",
        json={
            "idempotency_key": key or uuid.uuid4().hex,
            "items": [{"menu_item_id": str(item.id), "quantity": qty}],
            **extra,
        },
    )


async def staff(client: AsyncClient, db: AsyncSession, tv: TV) -> None:
    await as_member(client, db, tv.r.id, "staff")


async def act(client: AsyncClient, tv: TV, what: str):
    return await client.post(f"/api/restaurants/{tv.r.slug}/tables/{tv.t1.id}/{what}")


async def order_row(db: AsyncSession, order_id: str) -> Order:
    return (
        await db.execute(
            select(Order)
            .where(Order.id == uuid.UUID(order_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def floor_tile(client: AsyncClient, tv: TV) -> dict:
    resp = await client.get(f"/api/restaurants/{tv.r.slug}/floor")
    assert resp.status_code == 200, resp.text
    return next(t for t in resp.json()["tiles"] if t["label"] == "T1")


async def test_order_before_the_table_is_open_is_refused(client, db_session, tv):
    resp = await post_order(client, tv.s1, tv.naan)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "table_not_open"
    assert (
        await db_session.scalar(select(Order.id).where(Order.guest_session_id == tv.s1.id))
    ) is None


async def test_first_order_waits_for_the_waiter_and_is_not_on_any_bill(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    resp = await post_order(client, tv.s1, tv.karahi, 2)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_approval"
    assert body["over_first_order_cap"] is False
    row = await order_row(db_session, body["id"])
    assert row.bill_id is None
    assert row.sitting_id == sitting.id
    await db_session.refresh(tv.s1)
    assert tv.s1.sitting_id == sitting.id
    # No bill exists, so the guest has nothing to pay and the Floor shows no running total.
    assert (await client.get("/api/guest/bill")).status_code == 404
    assert (await db_session.scalar(select(Bill.id).where(Bill.table_id == tv.t1.id))) is None
    # The guest can still follow the waiting order.
    got = await client.get(f"/api/orders/{body['id']}")
    assert got.status_code == 200
    assert got.json()["status"] == "pending_approval"
    # Kitchen does not see it.
    await staff(client, db_session, tv)
    kitchen = await client.get(f"/api/restaurants/{tv.r.slug}/kitchen/orders")
    assert kitchen.status_code == 200
    assert body["id"] not in {o["id"] for o in kitchen.json()["orders"]}
    t = await floor_tile(client, tv)
    assert t["state"] == "approval_needed"
    assert t["running_total"] is None
    assert Decimal(t["pending_order_total"]) == Decimal("2200.00")


async def test_second_order_while_the_first_waits_also_waits_and_floor_sums_both(
    client, db_session, tv
):
    await open_table(db_session, tv.t1.id)
    first = (await post_order(client, tv.s1, tv.naan, 1)).json()
    # One test transaction: now() is the same for both orders, so date the first one back.
    await db_session.execute(
        update(Order)
        .where(Order.id == uuid.UUID(first["id"]))
        .values(placed_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    second = await post_order(client, tv.s1, tv.karahi, 3)
    assert second.status_code == 201
    assert second.json()["status"] == "pending_approval"
    await staff(client, db_session, tv)
    t = await floor_tile(client, tv)
    assert t["pending_order_id"] == first["id"]  # the oldest
    assert Decimal(t["pending_order_total"]) == Decimal("3360.00")
    assert t["pending_order_items"] == 4


async def test_approve_sends_every_waiting_order_to_the_kitchen_on_one_bill(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan, 1)).json()["id"]
    o2 = (await post_order(client, tv.s1, tv.karahi, 1)).json()["id"]
    await staff(client, db_session, tv)
    resp = await act(client, tv, "approve")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"table_id": str(tv.t1.id), "order_ids": [o1, o2], "status": "placed"}
    r1, r2 = await order_row(db_session, o1), await order_row(db_session, o2)
    assert (r1.status, r2.status) == ("placed", "placed")
    assert r1.bill_id is not None and r1.bill_id == r2.bill_id
    kitchen = await client.get(f"/api/restaurants/{tv.r.slug}/kitchen/orders")
    assert {o1, o2} <= {o["id"] for o in kitchen.json()["orders"]}
    t = await floor_tile(client, tv)
    assert Decimal(t["running_total"]) == Decimal("1160.00")
    assert t["pending_order_id"] is None

    # Once approved, the visit's later orders go straight to the kitchen on the same bill.
    later = await post_order(client, tv.s1, tv.naan, 2)
    assert later.status_code == 201
    assert later.json()["status"] == "placed"
    assert (await order_row(db_session, later.json()["id"])).bill_id == r1.bill_id


async def test_approve_twice_replays_and_decline_after_approve_is_already_handled(
    client, db_session, tv
):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan)).json()["id"]
    await staff(client, db_session, tv)
    first = await act(client, tv, "approve")
    second = await act(client, tv, "approve")
    assert first.status_code == second.status_code == 200
    assert second.json() == {"table_id": str(tv.t1.id), "order_ids": [o1], "status": "placed"}
    late = await act(client, tv, "decline")
    assert late.status_code == 409
    assert late.json()["detail"] == "Already handled"
    assert (await order_row(db_session, o1)).status == "placed"


async def test_approve_or_decline_with_nothing_waiting_is_already_handled(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    await staff(client, db_session, tv)
    for what in ("approve", "decline"):
        resp = await act(client, tv, what)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Already handled"


async def test_decline_cancels_without_a_bill_and_the_guest_can_order_again(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.karahi)).json()["id"]
    user = await as_member(client, db_session, tv.r.id, "staff")
    resp = await act(client, tv, "decline")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"table_id": str(tv.t1.id), "order_ids": [o1], "status": "cancelled"}
    row = await order_row(db_session, o1)
    assert row.status == "cancelled"
    assert row.voided_at is not None
    assert row.void_reason == "Declined by waiter"
    assert row.voided_by == user.id
    assert row.bill_id is None
    assert (await db_session.scalar(select(Bill.id).where(Bill.table_id == tv.t1.id))) is None
    await db_session.refresh(sitting)
    assert sitting.closed_at is None
    again = await post_order(client, tv.s1, tv.naan)
    assert again.status_code == 201
    assert again.json()["status"] == "pending_approval"


async def test_settle_never_includes_a_waiting_order(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan, 2)).json()["id"]
    await staff(client, db_session, tv)
    assert (await act(client, tv, "approve")).status_code == 200
    bill_id = (await order_row(db_session, o1)).bill_id
    # A waiting order on the same visit, e.g. one that raced the approval.
    other = await new_session(db_session, tv)
    db_session.add(
        Order(
            guest_session_id=other.id,
            restaurant_id=tv.r.id,
            table_id=tv.t1.id,
            sitting_id=sitting.id,
            status="pending_approval",
            total=Decimal("1100.00"),
            idempotency_key="raced",
            payload_hash="x",
        )
    )
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(tv.s1.id)))
    guest_bill = await client.get("/api/guest/bill")
    assert guest_bill.status_code == 200
    assert Decimal(guest_bill.json()["subtotal"]) == Decimal("120.00")
    detail = await client.get(f"/api/restaurants/{tv.r.slug}/bills/{bill_id}")
    assert Decimal(detail.json()["subtotal"]) == Decimal("120.00")
    resp = await settle(client, tv.r.slug, bill_id)
    assert resp.status_code == 200, resp.text
    bill = await db_session.get(Bill, bill_id)
    await db_session.refresh(bill)
    assert bill.subtotal == Decimal("120.00")


async def test_code_is_asked_once_and_wrong_codes_lock_the_phone(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id, code="4821")
    await redis_client.delete(f"code_lock:{tv.s1.id}", f"code_attempts:{tv.s1.id}")
    missing = await post_order(client, tv.s1, tv.naan)
    assert missing.status_code == 403
    assert missing.json()["detail"]["error"] == "code_required"
    for _ in range(5):
        wrong = await post_order(client, tv.s1, tv.naan, code="0000")
        assert wrong.status_code == 403
        assert wrong.json()["detail"]["error"] == "code_required"
    locked = await post_order(client, tv.s1, tv.naan, code="4821")
    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many tries. Please wait a minute and ask your waiter."
    assert (
        await db_session.scalar(select(Order.id).where(Order.guest_session_id == tv.s1.id))
    ) is None

    # Another phone at the table, with the right code: bound to the visit, never asked again.
    s2 = await new_session(db_session, tv)
    ok = await post_order(client, s2, tv.naan, code="4821")
    assert ok.status_code == 201, ok.text
    await db_session.refresh(s2)
    assert s2.sitting_id == sitting.id
    again = await post_order(client, s2, tv.naan)
    assert again.status_code == 201


async def test_a_right_code_resets_the_wrong_count(client, db_session, tv):
    await open_table(db_session, tv.t1.id, code="4821")
    await redis_client.delete(f"code_lock:{tv.s1.id}", f"code_attempts:{tv.s1.id}")
    for _ in range(4):
        assert (await post_order(client, tv.s1, tv.naan, code="0000")).status_code == 403
    assert (await post_order(client, tv.s1, tv.naan, code="4821")).status_code == 201
    assert await redis_client.get(f"code_attempts:{tv.s1.id}") is None


async def test_fourth_order_in_five_minutes_is_limited_but_replays_are_not(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    keys = []
    for _ in range(3):
        resp = await post_order(client, tv.s1, tv.naan)
        assert resp.status_code == 201
        keys.append(resp.json()["idempotency_key"])
    replay = await post_order(client, tv.s1, tv.naan, key=keys[0])
    assert replay.status_code == 200
    fourth = await post_order(client, tv.s1, tv.naan)
    assert fourth.status_code == 429
    assert fourth.json()["detail"] == "You're ordering quickly! Please wait a moment and try again."


async def test_replay_of_a_waiting_order_after_the_table_closed_returns_it(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    first = await post_order(client, tv.s1, tv.naan, key="same-key")
    assert first.status_code == 201
    sitting.closed_at = datetime.now(UTC)
    sitting.close_reason = "staff_closed"
    await db_session.flush()
    replay = await post_order(client, tv.s1, tv.naan, key="same-key")
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["status"] == "pending_approval"
    fresh = await post_order(client, tv.s1, tv.naan)
    assert fresh.status_code == 409
    assert fresh.json()["detail"]["error"] == "table_not_open"


async def test_a_big_first_order_is_still_created_but_flagged(client, db_session, tv):
    # Menu average (60 + 1100) / 2 = 580; cap = 580 x 4 = 2320.
    await open_table(db_session, tv.t1.id)
    small = await post_order(client, tv.s1, tv.karahi, 2)  # 2200: under the cap
    assert small.json()["over_first_order_cap"] is False
    big = await post_order(client, tv.s1, tv.naan, 3)  # 2200 + 180 waiting: over
    assert big.status_code == 201
    assert big.json()["status"] == "pending_approval"
    assert big.json()["over_first_order_cap"] is True


async def test_more_than_thirty_items_is_refused(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(tv.s1.id)))
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "big",
            "items": [
                {"menu_item_id": str(tv.naan.id), "quantity": 20},
                {"menu_item_id": str(tv.karahi.id), "quantity": 11},
            ],
        },
    )
    assert resp.status_code == 422
    assert "That's a big order! Please ask your waiter." in resp.text


async def test_approve_and_decline_are_404_for_non_members(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    await post_order(client, tv.s1, tv.naan)
    other = Restaurant(
        name="Other",
        slug=f"other-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(other)
    await db_session.flush()
    await as_member(client, db_session, other.id, "owner")
    for what in ("approve", "decline"):
        assert (await act(client, tv, what)).status_code == 404
    client.cookies.delete(AUTH_COOKIE_NAME)
    for what in ("approve", "decline"):
        assert (await act(client, tv, what)).status_code == 401
    assert (
        await db_session.scalar(select(TableSitting.id).where(TableSitting.table_id == tv.t1.id))
    ) is not None
