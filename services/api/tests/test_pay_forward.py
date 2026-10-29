"""Pay-it-forward chai: bought on settle, handed out by staff, never counted as revenue."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.helpers import as_member, make_user, settle, sign_in
from tests.test_bills import bill_id_of, guest, place
from tests.test_floor_api import record_events

from src.config import settings
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order, OrderItem
from src.models.pay_forward import PayForward
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.user import User
from src.services import analytics
from src.services.bills import local_date
from src.services.simulator import SimAssumptions, persist_simulation

ROUNDS = 3


@dataclass
class PfVenue:
    r: Restaurant
    t1: DiningTable
    naan: MenuItem
    chai: MenuItem
    party: GuestSession


def _item(rid: uuid.UUID, name: str, price: str, cost: str, pay_forward: bool) -> MenuItem:
    item = MenuItem(
        restaurant_id=rid,
        category="drinks",
        price=Decimal(price),
        unit_cost=Decimal(cost),
        allergen_verified=True,
        dietary_verified=True,
        is_pay_forward=pay_forward,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


@pytest_asyncio.fixture
async def pf(db_session: AsyncSession) -> PfVenue:
    r = Restaurant(
        name="Pay Forward Venue",
        slug=f"pf-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(r)
    await db_session.flush()
    t1 = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    naan = _item(r.id, "Naan", "60.00", "9.00", False)
    chai = _item(r.id, "Pay-it-forward chai", "250.00", "45.00", True)
    db_session.add_all([t1, naan, chai])
    await db_session.flush()
    party = GuestSession(
        restaurant_id=r.id,
        table_id=t1.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(party)
    await db_session.flush()
    return PfVenue(r, t1, naan, chai, party)


def one(key: str | None = None) -> dict:
    """A give body: one chai, a fresh idempotency key unless one is given."""
    return {"quantity": 1, "idempotency_key": key or uuid.uuid4().hex}


def url(v: PfVenue, suffix: str) -> str:
    return f"/api/restaurants/{v.r.slug}{suffix}"


async def rows(db: AsyncSession, v: PfVenue) -> list[PayForward]:
    return list(
        (
            await db.scalars(
                select(PayForward)
                .where(PayForward.restaurant_id == v.r.id)
                .order_by(PayForward.created_at, PayForward.kind)
            )
        ).all()
    )


async def balance(client: AsyncClient, v: PfVenue) -> int:
    resp = await client.get(url(v, "/floor"))
    assert resp.status_code == 200, resp.text
    return resp.json()["pay_forward_balance"]


async def buy_and_settle(client, db_session, v: PfVenue, chai: int = 1) -> uuid.UUID:
    order_id = await place(client, v.party, [(v.chai, chai), (v.naan, 1)])
    bill_id = await bill_id_of(db_session, order_id)
    await as_member(client, db_session, v.r.id, "staff")
    resp = await settle(client, v.r.slug, bill_id)
    assert resp.status_code == 200, resp.text
    return order_id


async def test_settle_records_bought_chai(client, db_session, pf):
    order_id = await buy_and_settle(client, db_session, pf, chai=2)
    [row] = await rows(db_session, pf)
    assert (row.kind, row.quantity, row.order_id, row.user_id) == ("bought", 2, order_id, None)
    assert await balance(client, pf) == 2
    guest(client, pf.party)
    bill = await client.get("/api/guest/bill")
    assert bill.status_code == 200, bill.text
    assert bill.json()["status"] == "settled"
    assert bill.json()["pay_forward_count"] == 2


async def test_open_bill_has_no_thank_you_and_no_bought_rows(client, db_session, pf):
    await place(client, pf.party, [(pf.chai, 1)])
    guest(client, pf.party)
    assert (await client.get("/api/guest/bill")).json()["pay_forward_count"] == 0
    assert await rows(db_session, pf) == []


async def test_voided_chai_is_not_bought(client, db_session, pf):
    chai_order = await place(client, pf.party, [(pf.chai, 1)])
    naan_order = await place(client, pf.party, [(pf.naan, 1)])
    bill_id = await bill_id_of(db_session, naan_order)
    await as_member(client, db_session, pf.r.id, "staff")
    void = await client.post(url(pf, f"/orders/{chai_order}/void"), json={"reason": "Mistake"})
    assert void.status_code == 200, void.text
    assert (await settle(client, pf.r.slug, bill_id)).status_code == 200
    assert await rows(db_session, pf) == []
    assert await balance(client, pf) == 0


async def test_give_one(client, db_session, pf, monkeypatch):
    await buy_and_settle(client, db_session, pf)
    staff = await as_member(client, db_session, pf.r.id, "staff")
    events = record_events(monkeypatch, "src.routers.floor.publish_event")

    resp = await client.post(url(pf, "/pay-forward/give"), json=one())
    assert resp.status_code == 200, resp.text
    assert resp.json()["pay_forward_balance"] == 0
    order_id = uuid.UUID(resp.json()["order_id"])
    assert [e["event"] for e in events] == ["pay_forward_given", "order_placed", "order_placed"]
    assert all(e["order_id"] == str(order_id) for e in events)

    order = (
        await db_session.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one()
    assert (order.source, order.status, order.total) == ("pay_forward", "placed", Decimal("0"))
    assert (order.bill_id, order.table_id) == (None, None)
    [line] = order.items
    assert (line.item_name, line.quantity) == ("Pay-it-forward chai", 1)
    assert (line.unit_price, line.unit_cost) == (Decimal("0.00"), Decimal("45.00"))
    session = await db_session.get(GuestSession, order.guest_session_id)
    assert session.table_id is None
    assert session.expires_at <= await db_session.scalar(select(func.clock_timestamp()))

    given = [r for r in await rows(db_session, pf) if r.kind == "given"]
    assert [(r.quantity, r.order_id, r.user_id) for r in given] == [(1, order_id, staff.id)]
    audit = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.restaurant_id == pf.r.id, AuditLog.event_type == "pay_forward_given"
            )
        )
    ).one()
    assert audit.actor == f"user:{staff.id}"

    kitchen = (await client.get(url(pf, "/kitchen/orders"))).json()["orders"]
    tickets = {o["id"]: o for o in kitchen}
    assert tickets[str(order_id)]["pay_forward"] is True
    assert tickets[str(order_id)]["table_label"] is None
    assert [o["pay_forward"] for o in kitchen if o["id"] != str(order_id)] == [False]

    again = await client.post(url(pf, "/pay-forward/give"), json=one())
    assert again.status_code == 409
    assert again.json()["detail"] == "None waiting"
    assert await balance(client, pf) == 0


async def test_give_validates_quantity_and_venue(client, db_session, pf):
    await buy_and_settle(client, db_session, pf)
    give = url(pf, "/pay-forward/give")
    for body in ({**one(), "quantity": 2}, {**one(), "quantity": 0}, {"quantity": 1}, {}):
        assert (await client.post(give, json=body)).status_code == 422
    other = Restaurant(
        name="Other",
        slug=f"pf-other-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(other)
    await db_session.flush()
    await as_member(client, db_session, other.id, "owner")
    assert (await client.post(give, json=one())).status_code == 404
    assert [r.kind for r in await rows(db_session, pf)] == ["bought"]


async def test_handouts_are_not_revenue(client, db_session, pf):
    await buy_and_settle(client, db_session, pf)
    give = await client.post(url(pf, "/pay-forward/give"), json=one())
    assert give.status_code == 200, give.text
    today = local_date(pf.r, datetime.now(UTC))
    w = analytics.Window(
        pf.r.id, pf.r.timezone, today - timedelta(days=1), today + timedelta(days=1)
    )
    k = await analytics.kpis(db_session, w)
    # The sale counts once (250 chai + 60 naan); the handout counts nowhere.
    assert (k["orders"], k["revenue"]) == (1, 310.0)
    units = {r["item_id"]: r["units"] for r in await analytics.daily_item_sales(db_session, w)}
    assert units == {str(pf.chai.id): 1, str(pf.naan.id): 1}
    assert await analytics.order_counts_by_source(db_session, w) == {"live": 1, "simulated": 0}

    await as_member(client, db_session, pf.r.id, "owner")
    with patch.object(settings, "demo_mode", False):
        resp = await client.get(url(pf, "/ai/brief"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["pay_forward"] == {"bought": 1, "given": 1}


async def test_flag_is_read_when_ordered_not_when_settled(client, db_session, pf):
    # Flagged after the order: no credit.
    pf.chai.is_pay_forward = False
    await db_session.flush()
    first = await place(client, pf.party, [(pf.chai, 1)])
    pf.chai.is_pay_forward = True
    await db_session.flush()
    await as_member(client, db_session, pf.r.id, "staff")
    assert (await settle(client, pf.r.slug, await bill_id_of(db_session, first))).status_code == 200
    assert await rows(db_session, pf) == []

    # Unflagged after the order: still credited, and the credit can still be handed out.
    party2 = GuestSession(
        restaurant_id=pf.r.id,
        table_id=pf.t1.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        created_at=await db_session.scalar(select(func.clock_timestamp())),
    )
    db_session.add(party2)
    await db_session.flush()
    second = await place(client, party2, [(pf.chai, 1)])
    pf.chai.is_pay_forward = False
    await db_session.flush()
    assert (
        await settle(client, pf.r.slug, await bill_id_of(db_session, second))
    ).status_code == 200
    assert [(r.kind, r.order_id) for r in await rows(db_session, pf)] == [("bought", second)]
    give = await client.post(url(pf, "/pay-forward/give"), json=one())
    assert give.status_code == 200, give.text
    handout = (
        await db_session.execute(
            select(OrderItem).where(OrderItem.order_id == uuid.UUID(give.json()["order_id"]))
        )
    ).scalar_one()
    assert (handout.menu_item_id, handout.is_pay_forward) == (pf.chai.id, False)


async def test_pay_forward_item_cannot_vanish_while_chai_wait(client, db_session, pf):
    await buy_and_settle(client, db_session, pf)
    await as_member(client, db_session, pf.r.id, "owner")
    chai_url = url(pf, f"/menu-items/{pf.chai.id}")
    waiting = "1 chai are still waiting to be given; give them out before removing this item"

    unflag = await client.patch(chai_url, json={"is_pay_forward": False})
    assert (unflag.status_code, unflag.json()["detail"]) == (409, waiting)
    delete_resp = await client.delete(chai_url)
    assert (delete_resp.status_code, delete_resp.json()["detail"]) == (409, waiting)

    second = await client.patch(url(pf, f"/menu-items/{pf.naan.id}"), json={"is_pay_forward": True})
    assert second.status_code == 409
    assert second.json()["detail"] == "Another item is already the pay-it-forward chai"

    assert (await client.post(url(pf, "/pay-forward/give"), json=one())).status_code == 200
    unflag = await client.patch(chai_url, json={"is_pay_forward": False})
    assert unflag.status_code == 200, unflag.text
    assert unflag.json()["is_pay_forward"] is False
    flag_naan = await client.patch(
        url(pf, f"/menu-items/{pf.naan.id}"), json={"is_pay_forward": True}
    )
    assert flag_naan.status_code == 200, flag_naan.text


async def test_one_live_pay_forward_item_per_venue(db_session, pf):
    from sqlalchemy.exc import IntegrityError

    pf.naan.is_pay_forward = True
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_give_replay_returns_the_first_handout(client, db_session, pf, monkeypatch):
    await buy_and_settle(client, db_session, pf, chai=2)
    events = record_events(monkeypatch, "src.routers.floor.publish_event")
    body = one("retry-me")
    first = await client.post(url(pf, "/pay-forward/give"), json=body)
    again = await client.post(url(pf, "/pay-forward/give"), json=body)
    assert (first.status_code, again.status_code) == (200, 200)
    assert (
        again.json()
        == first.json()
        == {
            "order_id": first.json()["order_id"],
            "pay_forward_balance": 1,
        }
    )
    assert [r.kind for r in await rows(db_session, pf)] == ["bought", "given"]
    handouts = await db_session.scalar(
        select(func.count()).where(Order.restaurant_id == pf.r.id, Order.source == "pay_forward")
    )
    assert handouts == 1
    assert [e["event"] for e in events] == ["pay_forward_given", "order_placed", "order_placed"]


async def test_thank_you_counts_only_this_phone(client, db_session, pf):
    other = GuestSession(
        restaurant_id=pf.r.id,
        table_id=pf.t1.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(other)
    await db_session.flush()
    mine = await place(client, pf.party, [(pf.chai, 2)])
    theirs = await place(client, other, [(pf.chai, 1), (pf.naan, 1)])
    bill_id = await bill_id_of(db_session, mine)
    assert await bill_id_of(db_session, theirs) == bill_id
    await as_member(client, db_session, pf.r.id, "staff")
    assert (await settle(client, pf.r.slug, bill_id)).status_code == 200
    for session, count in ((pf.party, 2), (other, 1)):
        guest(client, session)
        assert (await client.get("/api/guest/bill")).json()["pay_forward_count"] == count


# --- Concurrency: committed data, parallel clients ---


@pytest_asyncio.fixture
async def committed_pf():
    rid, chai_id = uuid.uuid4(), uuid.uuid4()
    slug = f"pf-par-{uuid.uuid4().hex[:8]}"
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=rid,
                name="Parallel Pay Forward",
                slug=slug,
                currency="PKR",
                timezone="Asia/Karachi",
                languages=["en"],
                default_language="en",
                tax_jurisdiction="PB",
            )
        )
        await s.flush()
        chai = _item(rid, "Pay-it-forward chai", "250.00", "45.00", True)
        chai.id = chai_id
        s.add(chai)
        staff = await make_user(s, [(rid, "staff")])
        await s.commit()
    try:
        yield rid, slug, staff
    finally:
        async with async_session_factory() as s:
            await s.execute(delete(PayForward).where(PayForward.restaurant_id == rid))
            await s.execute(delete(AuditLog).where(AuditLog.restaurant_id == rid))
            await s.execute(delete(Order).where(Order.restaurant_id == rid))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == rid))
            await s.execute(delete(MenuTranslation).where(MenuTranslation.menu_item_id == chai_id))
            await s.execute(delete(MenuItem).where(MenuItem.restaurant_id == rid))
            await s.execute(delete(Restaurant).where(Restaurant.id == rid))
            await s.execute(delete(User).where(User.id == staff.id))
            await s.commit()


async def test_parallel_gives_never_go_below_zero(committed_pf):
    rid, slug, staff = committed_pf
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a,
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b,
        ):
            sign_in(a, staff)
            sign_in(b, staff)
            give = f"/api/restaurants/{slug}/pay-forward/give"
            for _ in range(ROUNDS):
                async with async_session_factory() as s:
                    s.add(PayForward(restaurant_id=rid, kind="bought", quantity=1))
                    await s.commit()
                results = await asyncio.gather(a.post(give, json=one()), b.post(give, json=one()))
                codes = sorted(r.status_code for r in results)
                assert codes == [200, 409], [r.text for r in results]
                refused = next(r for r in results if r.status_code == 409)
                assert refused.json() == {"detail": "None waiting"}
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override

    async with async_session_factory() as s:
        handouts = await s.scalar(
            select(func.count()).where(Order.restaurant_id == rid, Order.source == "pay_forward")
        )
        given = await s.scalar(
            select(func.count()).where(PayForward.restaurant_id == rid, PayForward.kind == "given")
        )
    assert (handouts, given) == (ROUNDS, ROUNDS)


async def test_simulator_never_sells_pay_forward_chai(db_session, pf):
    a = SimAssumptions(days=7, seed=7)
    summary = await persist_simulation(db_session, pf.r, a)
    assert summary["orders_created"] > 0
    lines = (
        await db_session.scalars(
            select(OrderItem.menu_item_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.restaurant_id == pf.r.id, Order.source == "simulated")
        )
    ).all()
    assert pf.naan.id in lines
    assert pf.chai.id not in lines


async def test_parallel_same_key_gives_once(committed_pf):
    rid, slug, staff = committed_pf
    async with async_session_factory() as s:
        s.add(PayForward(restaurant_id=rid, kind="bought", quantity=2))
        await s.commit()
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a,
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b,
        ):
            sign_in(a, staff)
            sign_in(b, staff)
            give = f"/api/restaurants/{slug}/pay-forward/give"
            body = one("same-tap")
            results = await asyncio.gather(a.post(give, json=body), b.post(give, json=body))
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json()["order_id"] == results[1].json()["order_id"]
    async with async_session_factory() as s:
        given = await s.scalar(
            select(func.count()).where(PayForward.restaurant_id == rid, PayForward.kind == "given")
        )
    assert given == 1


async def _counter_party(db: AsyncSession, v: PfVenue) -> GuestSession:
    counter = DiningTable(
        restaurant_id=v.r.id, label="Counter", kind="counter", qr_token=uuid.uuid4().hex
    )
    db.add(counter)
    await db.flush()
    party = GuestSession(
        restaurant_id=v.r.id,
        table_id=counter.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(party)
    await db.flush()
    return party


async def test_chai_on_an_expired_counter_bill_settled_late_is_bought_once(client, db_session, pf):
    party = await _counter_party(db_session, pf)
    order_id = await place(client, party, [(pf.chai, 1)])
    bill_id = await bill_id_of(db_session, order_id)
    await as_member(client, db_session, pf.r.id, "staff")
    await db_session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(placed_at=datetime.now(UTC) - timedelta(minutes=31))
    )
    assert (await client.get(url(pf, "/bills?kind=counter"))).status_code == 200  # expires it
    assert await db_session.scalar(select(Bill.status).where(Bill.id == bill_id)) == "cancelled"
    assert await rows(db_session, pf) == []

    assert (await settle(client, pf.r.slug, bill_id)).status_code == 200  # money came late
    assert (await settle(client, pf.r.slug, bill_id)).status_code == 409
    [row] = await rows(db_session, pf)
    assert (row.kind, row.quantity, row.order_id) == ("bought", 1, order_id)
    assert await balance(client, pf) == 1


async def test_chai_on_a_cancelled_bill_is_never_bought(client, db_session, pf):
    party = await _counter_party(db_session, pf)
    counter_bill = await bill_id_of(db_session, await place(client, party, [(pf.chai, 2)]))
    table_order = await place(client, pf.party, [(pf.chai, 1)])
    table_bill = await bill_id_of(db_session, table_order)
    await as_member(client, db_session, pf.r.id, "staff")
    cancel = await client.post(url(pf, f"/bills/{counter_bill}/cancel"), json={"reason": "Left"})
    assert cancel.status_code == 200, cancel.text
    void = await client.post(url(pf, f"/orders/{table_order}/void"), json={"reason": "Left"})
    assert void.status_code == 200, void.text
    statuses = (
        await db_session.scalars(select(Bill.status).where(Bill.id.in_([counter_bill, table_bill])))
    ).all()
    assert list(statuses) == ["cancelled", "cancelled"]
    for bill_id in (counter_bill, table_bill):  # a staff cancel is final
        assert (await settle(client, pf.r.slug, bill_id)).status_code == 409
    assert await rows(db_session, pf) == []
    assert await balance(client, pf) == 0
