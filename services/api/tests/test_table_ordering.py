"""Safer table ordering: the table must be open, a visit's orders wait for the waiter until
one is approved, the table code, and per-phone order limits."""

import json
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
from src.services.bills import VISIT_ENDED, session_is_current

CHANGED = "The order changed. Please check the table again."


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


async def act(client: AsyncClient, tv: TV, what: str, order_ids: list[str]):
    """Approve or decline the waiting orders the waiter saw on the tile."""
    return await client.post(
        f"/api/restaurants/{tv.r.slug}/tables/{tv.t1.id}/{what}", json={"order_ids": order_ids}
    )


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
    assert t["pending_order_ids"] == [first["id"], second.json()["id"]]
    assert Decimal(t["pending_order_total"]) == Decimal("3360.00")
    assert t["pending_order_items"] == 4


async def test_approve_sends_every_waiting_order_to_the_kitchen_on_one_bill(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan, 1)).json()["id"]
    o2 = (await post_order(client, tv.s1, tv.karahi, 1)).json()["id"]
    await staff(client, db_session, tv)
    resp = await act(client, tv, "approve", [o1, o2])
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
    first = await act(client, tv, "approve", [o1])
    second = await act(client, tv, "approve", [o1])
    assert first.status_code == second.status_code == 200
    assert second.json() == {"table_id": str(tv.t1.id), "order_ids": [o1], "status": "placed"}
    late = await act(client, tv, "decline", [o1])
    assert late.status_code == 409
    assert late.json()["detail"] == "Already handled"
    assert (await order_row(db_session, o1)).status == "placed"


async def test_approve_or_decline_with_nothing_waiting_is_already_handled(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    await staff(client, db_session, tv)
    for what in ("approve", "decline"):
        resp = await act(client, tv, what, [str(uuid.uuid4())])
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Already handled"


async def test_decline_cancels_without_a_bill_and_the_guest_can_order_again(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.karahi)).json()["id"]
    user = await as_member(client, db_session, tv.r.id, "staff")
    resp = await act(client, tv, "decline", [o1])
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


async def test_settle_never_includes_a_waiting_order(client, db_session, tv, monkeypatch):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan, 2)).json()["id"]
    await staff(client, db_session, tv)
    assert (await act(client, tv, "approve", [o1])).status_code == 200
    bill_id = (await order_row(db_session, o1)).bill_id
    # A waiting order on the same visit, e.g. one that raced the approval.
    other = await new_session(db_session, tv)
    raced = Order(
        guest_session_id=other.id,
        restaurant_id=tv.r.id,
        table_id=tv.t1.id,
        sitting_id=sitting.id,
        status="pending_approval",
        total=Decimal("1100.00"),
        idempotency_key="raced",
        payload_hash="x",
    )
    db_session.add(raced)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(tv.s1.id)))
    guest_bill = await client.get("/api/guest/bill")
    assert guest_bill.status_code == 200
    assert Decimal(guest_bill.json()["subtotal"]) == Decimal("120.00")
    detail = await client.get(f"/api/restaurants/{tv.r.slug}/bills/{bill_id}")
    assert Decimal(detail.json()["subtotal"]) == Decimal("120.00")
    events = record_declined(monkeypatch)
    resp = await settle(client, tv.r.slug, bill_id)
    assert resp.status_code == 200, resp.text
    bill = await db_session.get(Bill, bill_id)
    await db_session.refresh(bill)
    assert bill.subtotal == Decimal("120.00")
    # Settling closes the visit: the waiting order is cancelled, never left behind.
    row = await order_row(db_session, str(raced.id))
    assert (row.status, row.void_reason, row.bill_id) == ("cancelled", "Table closed", None)
    assert declined_for(events, tv, str(raced.id)) == {f"orders:{raced.id}", f"kitchen:{tv.r.id}"}


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
    oid = (await post_order(client, tv.s1, tv.naan)).json()["id"]
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
        assert (await act(client, tv, what, [oid])).status_code == 404
    client.cookies.delete(AUTH_COOKIE_NAME)
    for what in ("approve", "decline"):
        assert (await act(client, tv, what, [oid])).status_code == 401
    assert (
        await db_session.scalar(select(TableSitting.id).where(TableSitting.table_id == tv.t1.id))
    ) is not None


async def test_approve_covers_only_the_orders_the_waiter_saw(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan)).json()["id"]
    await staff(client, db_session, tv)
    seen = (await floor_tile(client, tv))["pending_order_ids"]
    assert seen == [o1]
    # The guest adds a big order after the waiter read the tile.
    o2 = (await post_order(client, tv.s1, tv.karahi, 2)).json()["id"]
    await staff(client, db_session, tv)
    stale = await act(client, tv, "approve", seen)
    assert stale.status_code == 409
    assert stale.json()["detail"] == CHANGED
    assert [(await order_row(db_session, o)).status for o in (o1, o2)] == ["pending_approval"] * 2
    assert (await db_session.scalar(select(Bill.id).where(Bill.table_id == tv.t1.id))) is None
    fresh = (await floor_tile(client, tv))["pending_order_ids"]
    assert sorted(fresh) == sorted([o1, o2])  # one test transaction: same placed_at
    resp = await act(client, tv, "approve", fresh)
    assert resp.status_code == 200, resp.text
    assert [(await order_row(db_session, o)).status for o in (o1, o2)] == ["placed"] * 2


async def test_a_late_decline_never_cancels_a_fresh_order(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan)).json()["id"]
    await staff(client, db_session, tv)
    assert (await act(client, tv, "decline", [o1])).status_code == 200
    o2 = (await post_order(client, tv.s1, tv.karahi)).json()["id"]
    await staff(client, db_session, tv)
    # A retried "Not now" for the first order replays; the re-order still waits.
    replay = await act(client, tv, "decline", [o1])
    assert replay.status_code == 200, replay.text
    assert replay.json()["order_ids"] == [o1]
    assert (await order_row(db_session, o2)).status == "pending_approval"
    # A stale tile that mixes the two is refused.
    mixed = await act(client, tv, "decline", [o1, o2])
    assert mixed.status_code == 409
    assert mixed.json()["detail"] == CHANGED
    assert (await order_row(db_session, o2)).status == "pending_approval"
    # Approving the declined order is no replay either: the tile is stale.
    stale = await act(client, tv, "approve", [o1])
    assert (stale.status_code, stale.json()["detail"]) == (409, CHANGED)


async def test_refused_orders_do_not_use_up_the_order_limit(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    risky = _item(tv.r.id, "House Curry", "500.00")
    risky.allergen_verified = False
    db_session.add(risky)
    await db_session.flush()
    asked = await post_order(client, tv.s1, risky)
    assert asked.status_code == 409
    assert asked.json()["detail"]["error"] == "allergen_ack_required"
    confirmed = await post_order(client, tv.s1, risky, acknowledge_allergen_risk=True)
    assert confirmed.status_code == 201, confirmed.text
    for _ in range(2):
        assert (await post_order(client, tv.s1, tv.naan)).status_code == 201
    fourth = await post_order(client, tv.s1, tv.naan)
    assert fourth.status_code == 429
    assert fourth.json()["detail"] == "You're ordering quickly! Please wait a moment and try again."


async def test_an_ended_visit_is_told_before_any_code_is_tried(client, db_session, tv):
    await open_table(db_session, tv.t1.id, code="4821")
    await redis_client.delete(f"code_lock:{tv.s1.id}", f"code_attempts:{tv.s1.id}")
    # The phone scanned before the table was cleared.
    tv.t1.cleared_at = tv.t1.reset_at = datetime.now(UTC)
    await db_session.flush()
    resp = await post_order(client, tv.s1, tv.naan, code="0000")
    assert resp.status_code == 409
    assert resp.json()["detail"] == VISIT_ENDED
    assert await redis_client.get(f"code_attempts:{tv.s1.id}") is None


async def test_a_phone_from_an_earlier_sitting_must_scan_again(client, db_session, tv):
    first = await open_table(db_session, tv.t1.id)
    assert (await post_order(client, tv.s1, tv.naan)).status_code == 201
    first.closed_at = datetime.now(UTC)
    first.close_reason = "staff_closed"
    await db_session.flush()
    second = await open_table(db_session, tv.t1.id)
    resp = await post_order(client, tv.s1, tv.naan)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "table_not_open"
    await db_session.refresh(tv.s1)
    assert tv.s1.sitting_id == first.id  # never re-bound to the new party's sitting
    # A phone that scans now joins the new sitting on its first order.
    s2 = await new_session(db_session, tv)
    assert (await post_order(client, s2, tv.naan)).status_code == 201
    await db_session.refresh(s2)
    assert s2.sitting_id == second.id


def record_declined(monkeypatch) -> list[dict]:
    events: list[dict] = []

    async def fake(channel: str, message: str) -> None:
        events.append({"channel": channel, **json.loads(message)})

    for target in ("src.redis_client.publish_event", "src.routers.floor.publish_event"):
        monkeypatch.setattr(target, fake)
    return events


def declined_for(events: list[dict], tv: TV, order_id: str) -> set[str]:
    return {
        e["channel"]
        for e in events
        if e.get("event") == "order_declined" and e.get("order_id") == order_id
    } & {f"orders:{order_id}", f"kitchen:{tv.r.id}"}


async def guest_sees(client: AsyncClient, tv: TV, order_id: str) -> str:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(tv.s1.id)))
    resp = await client.get(f"/api/orders/{order_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


async def test_closing_the_table_cancels_its_waiting_orders(client, db_session, tv, monkeypatch):
    await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan)).json()["id"]
    events = record_declined(monkeypatch)
    user = await as_member(client, db_session, tv.r.id, "staff")
    resp = await client.delete(f"/api/restaurants/{tv.r.slug}/tables/{tv.t1.id}/sitting")
    assert resp.status_code == 200, resp.text
    row = await order_row(db_session, o1)
    assert (row.status, row.void_reason, row.voided_by) == ("cancelled", "Table closed", user.id)
    assert row.voided_at is not None and row.bill_id is None
    assert declined_for(events, tv, o1) == {f"orders:{o1}", f"kitchen:{tv.r.id}"}
    assert await guest_sees(client, tv, o1) == "cancelled"


async def test_an_idle_close_cancels_the_waiting_orders(client, db_session, tv, monkeypatch):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = (await post_order(client, tv.s1, tv.naan)).json()["id"]
    long_ago = datetime.now(UTC) - timedelta(hours=3)
    sitting.opened_at = long_ago
    await db_session.execute(
        update(Order).where(Order.id == uuid.UUID(o1)).values(placed_at=long_ago)
    )
    await db_session.flush()
    events = record_declined(monkeypatch)
    late = await post_order(client, await new_session(db_session, tv), tv.naan)
    assert late.status_code == 409
    assert late.json()["detail"]["error"] == "table_not_open"
    await db_session.refresh(sitting)
    assert sitting.close_reason == "idle_timeout"
    row = await order_row(db_session, o1)
    assert (row.status, row.void_reason, row.voided_by) == ("cancelled", "Table closed", None)
    assert row.voided_at is not None
    assert declined_for(events, tv, o1) == {f"orders:{o1}", f"kitchen:{tv.r.id}"}
    assert await guest_sees(client, tv, o1) == "cancelled"


async def sitting_row(db: AsyncSession, sitting_id: uuid.UUID) -> TableSitting:
    return await db.get(TableSitting, sitting_id, populate_existing=True)


async def approved_order(client, db_session, tv: TV, item: MenuItem, session=None) -> str:
    order_id = (await post_order(client, session or tv.s1, item)).json()["id"]
    await staff(client, db_session, tv)
    assert (await act(client, tv, "approve", [order_id])).status_code == 200
    return order_id


async def test_settling_closes_the_sitting_and_the_table_can_be_opened_again(
    client, db_session, tv
):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = await approved_order(client, db_session, tv, tv.naan)
    resp = await settle(client, tv.r.slug, (await order_row(db_session, o1)).bill_id)
    assert resp.status_code == 200, resp.text
    row = await sitting_row(db_session, sitting.id)
    assert row.close_reason == "settled" and row.closed_at is not None
    assert (await floor_tile(client, tv))["sitting_open"] is False
    reopen = await client.post(f"/api/restaurants/{tv.r.slug}/tables/{tv.t1.id}/sitting")
    assert reopen.status_code == 201, reopen.text


async def void(client, tv: TV, order_id: str):
    return await client.post(
        f"/api/restaurants/{tv.r.slug}/orders/{order_id}/void", json={"reason": "Guest left"}
    )


async def test_voiding_the_last_order_closes_the_sitting(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = await approved_order(client, db_session, tv, tv.naan)
    assert (await void(client, tv, o1)).status_code == 200
    row = await sitting_row(db_session, sitting.id)
    assert row.close_reason == "cancelled" and row.closed_at is not None


async def test_voiding_one_of_two_orders_keeps_the_sitting_open(client, db_session, tv):
    sitting = await open_table(db_session, tv.t1.id)
    o1 = await approved_order(client, db_session, tv, tv.naan)
    assert (await post_order(client, tv.s1, tv.karahi)).status_code == 201  # placed directly
    assert (await void(client, tv, o1)).status_code == 200
    row = await sitting_row(db_session, sitting.id)
    assert row.closed_at is None


async def guest_status(client: AsyncClient, session: GuestSession) -> tuple[bool, bool]:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    resp = await client.get("/api/guest/session")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "code" not in body
    return body["sitting_open"], body["code_required"]


async def test_guest_status_follows_the_sitting(client, db_session, tv):
    assert await guest_status(client, tv.s1) == (False, False)
    await open_table(db_session, tv.t1.id)
    assert await guest_status(client, tv.s1) == (True, False)
    o1 = await approved_order(client, db_session, tv, tv.naan)
    resp = await settle(client, tv.r.slug, (await order_row(db_session, o1)).bill_id)
    assert resp.status_code == 200, resp.text
    assert await guest_status(client, tv.s1) == (False, False)


async def test_guest_status_asks_for_the_code_until_the_phone_has_entered_it(
    client, db_session, tv
):
    await open_table(db_session, tv.t1.id, code="4821")
    await redis_client.delete(f"code_lock:{tv.s1.id}", f"code_attempts:{tv.s1.id}")
    assert await guest_status(client, tv.s1) == (True, True)
    assert (await post_order(client, tv.s1, tv.naan, code="4821")).status_code == 201
    assert await guest_status(client, tv.s1) == (True, False)


async def test_guest_status_of_a_phone_from_an_earlier_sitting(client, db_session, tv):
    first = await open_table(db_session, tv.t1.id)
    assert (await post_order(client, tv.s1, tv.naan)).status_code == 201
    first.closed_at = datetime.now(UTC)
    first.close_reason = "staff_closed"
    await db_session.flush()
    await open_table(db_session, tv.t1.id, code="4821")
    assert await guest_status(client, tv.s1) == (False, False)


async def test_guest_status_at_a_counter(client, db_session, tv):
    counter = DiningTable(
        restaurant_id=tv.r.id, label="C1", kind="counter", qr_token=uuid.uuid4().hex
    )
    db_session.add(counter)
    await db_session.flush()
    s = GuestSession(
        restaurant_id=tv.r.id,
        table_id=counter.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(s)
    await db_session.flush()
    assert await guest_status(client, s) == (True, False)


async def test_a_phone_that_scans_after_a_reset_is_current_even_if_the_clock_stepped_back(
    client, db_session, tv
):
    # The wall clock stepped back after the table reset: the reset looks later than "now".
    tv.t1.cleared_at = tv.t1.reset_at = datetime.now(UTC) + timedelta(minutes=1)
    await db_session.flush()
    resp = await client.post("/api/guest/sessions", json={"qr_token": tv.t1.qr_token})
    assert resp.status_code == 201, resp.text
    scanned = await db_session.get(GuestSession, uuid.UUID(resp.json()["id"]))
    assert await session_is_current(db_session, scanned)


async def scan(client: AsyncClient, db: AsyncSession, tv: TV) -> GuestSession:
    resp = await client.post("/api/guest/sessions", json={"qr_token": tv.t1.qr_token})
    assert resp.status_code == 201, resp.text
    return await db.get(GuestSession, uuid.UUID(resp.json()["id"]))


async def test_a_reset_after_the_clock_stepped_back_still_ends_the_earlier_phones(
    client, db_session, tv
):
    # A reset stamped by a clock an hour fast; then the clock steps back to the true time.
    ahead = datetime.now(UTC) + timedelta(hours=1)
    tv.t1.cleared_at = tv.t1.reset_at = ahead
    await db_session.flush()
    phone = await scan(client, db_session, tv)  # party 2, never orders
    assert phone.created_at > ahead
    assert await session_is_current(db_session, phone)
    await staff(client, db_session, tv)
    resp = await client.post(
        f"/api/restaurants/{tv.r.slug}/tables/{tv.t1.id}/clear", json={"force": True}
    )
    assert resp.status_code == 200, resp.text
    reset = await db_session.scalar(select(DiningTable.reset_at).where(DiningTable.id == tv.t1.id))
    assert reset > phone.created_at  # never stamped before the earlier reset or its phones
    assert not await session_is_current(db_session, phone)
    assert await session_is_current(db_session, await scan(client, db_session, tv))


async def test_settling_moves_the_reset_forward_even_if_the_clock_stepped_back(
    client, db_session, tv
):
    tv.t1.cleared_at = tv.t1.reset_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()
    await open_table(db_session, tv.t1.id)
    payer = await scan(client, db_session, tv)
    bystander = await scan(client, db_session, tv)  # same party, never orders
    o1 = await approved_order(client, db_session, tv, tv.naan, payer)
    resp = await settle(client, tv.r.slug, (await order_row(db_session, o1)).bill_id)
    assert resp.status_code == 200, resp.text
    assert not await session_is_current(db_session, bystander)
    assert not await session_is_current(db_session, payer)
    assert await session_is_current(db_session, await scan(client, db_session, tv))


async def test_voiding_every_order_moves_the_reset_forward(client, db_session, tv):
    tv.t1.cleared_at = tv.t1.reset_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()
    await open_table(db_session, tv.t1.id)
    payer = await scan(client, db_session, tv)
    bystander = await scan(client, db_session, tv)
    o1 = await approved_order(client, db_session, tv, tv.naan, payer)
    assert (await void(client, tv, o1)).status_code == 200
    assert not await session_is_current(db_session, bystander)
    assert await session_is_current(db_session, await scan(client, db_session, tv))


async def test_guest_status_of_a_phone_left_from_the_last_party(client, db_session, tv):
    await open_table(db_session, tv.t1.id)
    leftover = await new_session(db_session, tv)  # scanned with party 1, never ordered
    o1 = await approved_order(client, db_session, tv, tv.naan)
    resp = await settle(client, tv.r.slug, (await order_row(db_session, o1)).bill_id)
    assert resp.status_code == 200, resp.text
    await open_table(db_session, tv.t1.id, code="4821")
    # As create_order would judge it: the visit ended, so no table and no code to ask for.
    assert await guest_status(client, leftover) == (False, False)
    assert (await post_order(client, leftover, tv.naan, code="4821")).status_code == 409
