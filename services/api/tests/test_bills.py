"""Table bills: orders join the table's open bill; list, detail, settle, guest request."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, make_user, sign_in

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.user import User


@dataclass
class Venue:
    r: Restaurant
    t1: DiningTable
    t2: DiningTable
    karahi: MenuItem
    naan: MenuItem
    half: MenuItemOption
    full: MenuItemOption
    session_t1: GuestSession
    session_t2: GuestSession


def _item(restaurant_id: uuid.UUID, name: str, price: str, sort: int) -> MenuItem:
    item = MenuItem(
        restaurant_id=restaurant_id,
        category="mains",
        price=Decimal(price),
        unit_cost=Decimal("1.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=sort,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


@pytest_asyncio.fixture
async def venue(db_session: AsyncSession) -> Venue:
    r = Restaurant(
        name="Bills Venue",
        slug=f"bills-{uuid.uuid4().hex[:8]}",
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
    t2 = DiningTable(restaurant_id=r.id, label="T2", qr_token=uuid.uuid4().hex)
    karahi = _item(r.id, "Chicken Karahi", "1100.00", 1)
    naan = _item(r.id, "Naan", "60.00", 2)
    db_session.add_all([t1, t2, karahi, naan])
    await db_session.flush()
    half = MenuItemOption(
        menu_item_id=karahi.id, label="Half", price=Decimal("1100.00"), unit_cost=Decimal("1.00")
    )
    full = MenuItemOption(
        menu_item_id=karahi.id,
        label="Full",
        price=Decimal("2100.00"),
        unit_cost=Decimal("1.00"),
        sort_order=1,
    )
    expires = datetime.now(UTC) + timedelta(hours=2)
    s1 = GuestSession(restaurant_id=r.id, table_id=t1.id, language="en", expires_at=expires)
    s2 = GuestSession(restaurant_id=r.id, table_id=t2.id, language="en", expires_at=expires)
    db_session.add_all([half, full, s1, s2])
    await db_session.flush()
    return Venue(r, t1, t2, karahi, naan, half, full, s1, s2)


def guest(client: AsyncClient, session: GuestSession) -> None:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))


async def place(client: AsyncClient, session: GuestSession, lines: list[tuple]) -> uuid.UUID:
    """Post an order as the session's guest; lines are (item, qty) or (item, qty, option)."""
    guest(client, session)
    items = [
        {
            "menu_item_id": str(line[0].id),
            "quantity": line[1],
            **({"option_id": str(line[2].id)} if len(line) > 2 else {}),
        }
        for line in lines
    ]
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": items,
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


async def bill_id_of(db: AsyncSession, order_id: uuid.UUID) -> uuid.UUID | None:
    return (await db.execute(select(Order.bill_id).where(Order.id == order_id))).scalar_one()


async def test_first_order_opens_bill_and_second_joins_it(client, db_session, venue):
    o1 = await place(client, venue.session_t1, [(venue.naan, 2)])
    o2 = await place(client, venue.session_t1, [(venue.naan, 1)])
    b1, b2 = await bill_id_of(db_session, o1), await bill_id_of(db_session, o2)
    assert b1 is not None
    assert b1 == b2


async def test_tables_get_separate_bills_with_increasing_numbers(client, db_session, venue):
    await place(client, venue.session_t1, [(venue.naan, 1)])
    await place(client, venue.session_t2, [(venue.naan, 1)])
    nos = sorted(
        (
            await db_session.execute(select(Bill.bill_no).where(Bill.restaurant_id == venue.r.id))
        ).scalars()
    )
    assert nos == [1, 2]


async def test_one_open_bill_per_table_is_enforced(db_session, venue):
    db_session.add(
        Bill(
            restaurant_id=venue.r.id, table_id=venue.t1.id, bill_no=90, status="open", source="live"
        )
    )
    db_session.add(
        Bill(
            restaurant_id=venue.r.id, table_id=venue.t1.id, bill_no=91, status="open", source="live"
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_live_bill_needs_a_number(db_session, venue):
    db_session.add(
        Bill(
            restaurant_id=venue.r.id,
            table_id=venue.t1.id,
            bill_no=None,
            status="open",
            source="live",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


def bills_url(venue: Venue, suffix: str = "") -> str:
    return f"/api/restaurants/{venue.r.slug}/bills{suffix}"


async def bill_no_of(db: AsyncSession, bill_id: uuid.UUID) -> int | None:
    return (await db.execute(select(Bill.bill_no).where(Bill.id == bill_id))).scalar_one()


async def test_detail_groups_lines_and_previews_both_rates(client, db_session, venue):
    await place(client, venue.session_t1, [(venue.karahi, 1, venue.full), (venue.naan, 4)])
    await place(client, venue.session_t1, [(venue.naan, 2)])
    await as_member(client, db_session, venue.r.id, "staff")
    listing = await client.get(bills_url(venue, "?status=open"))
    assert listing.status_code == 200, listing.text
    bill = listing.json()["bills"][0]
    assert bill["table_label"] == "T1"
    assert bill["order_count"] == 2
    assert bill["subtotal"] == "2460.00"
    d = (await client.get(bills_url(venue, f"/{bill['id']}"))).json()
    assert [(ln["name"], ln["option_label"], ln["quantity"]) for ln in d["lines"]] == [
        ("Chicken Karahi", "Full", 1),
        ("Naan", None, 6),
    ]
    assert d["lines"][1]["line_total"] == "360.00"
    assert d["subtotal"] == "2460.00"
    assert d["restaurant_timezone"] == "Asia/Karachi"
    assert listing.json()["restaurant_timezone"] == "Asia/Karachi"
    assert d["preview_standard"] == {
        "payment_class": "standard",
        "tax_rate": "0.16",
        "tax_amount": "394.00",
        "total": "2854.00",
    }
    assert d["preview_digital"] == {
        "payment_class": "digital",
        "tax_rate": "0.08",
        "tax_amount": "197.00",
        "total": "2657.00",
    }
    assert (d["restaurant_name"], d["restaurant_city"], d["currency"]) == (
        "Bills Venue",
        "Lahore",
        "PKR",
    )
    assert d["status"] == "open"
    assert d["total"] is None


async def test_settle_by_card_snapshots_tax_and_next_order_opens_new_bill(
    client, db_session, venue
):
    o1 = await place(client, venue.session_t1, [(venue.karahi, 1, venue.full), (venue.naan, 6)])
    bill_id = await bill_id_of(db_session, o1)
    bill_no = await bill_no_of(db_session, bill_id)
    await as_member(client, db_session, venue.r.id, "staff")
    url = bills_url(venue, f"/{bill_id}/settle")

    resp = await client.post(url, json={"payment_method": "card", "payment_reference": "AUTH123"})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["status"] == "settled"
    assert (d["payment_method"], d["payment_reference"]) == ("card", "AUTH123")
    assert d["tax_jurisdiction"] == "PB"
    assert Decimal(d["tax_rate"]) == Decimal("0.08")
    assert d["subtotal"] == "2460.00"
    assert Decimal(d["tax_amount"]) == Decimal("197")
    assert Decimal(d["total"]) == Decimal(d["subtotal"]) + Decimal(d["tax_amount"])
    assert d["settled_at"] is not None

    stored = (await db_session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()
    assert stored.status == "settled"
    assert stored.total == Decimal("2657.00")

    again = await client.post(url, json={"payment_method": "cash"})
    assert again.status_code == 409

    settled = (await client.get(bills_url(venue, "?status=settled"))).json()["bills"]
    assert [b["id"] for b in settled] == [str(bill_id)]
    assert (await client.get(bills_url(venue, "?status=open"))).json()["bills"] == []

    o2 = await place(client, venue.session_t1, [(venue.naan, 1)])
    new_bill = await bill_id_of(db_session, o2)
    assert new_bill is not None
    assert new_bill != bill_id
    assert await bill_no_of(db_session, new_bill) == bill_no + 1


async def test_settle_validation(client, db_session, venue):
    o1 = await place(client, venue.session_t1, [(venue.naan, 1)])
    bill_t1 = await bill_id_of(db_session, o1)
    o2 = await place(client, venue.session_t2, [(venue.naan, 1)])
    bill_t2 = await bill_id_of(db_session, o2)
    await as_member(client, db_session, venue.r.id, "staff")

    too_long = await client.post(
        bills_url(venue, f"/{bill_t1}/settle"),
        json={"payment_method": "cash", "payment_reference": "x" * 65},
    )
    assert too_long.status_code == 422
    unknown = await client.post(
        bills_url(venue, f"/{bill_t1}/settle"), json={"payment_method": "bitcoin"}
    )
    assert unknown.status_code == 422

    order = (await db_session.execute(select(Order).where(Order.id == o2))).scalar_one()
    order.status = "cancelled"
    await db_session.flush()
    empty = await client.post(
        bills_url(venue, f"/{bill_t2}/settle"), json={"payment_method": "cash"}
    )
    assert empty.status_code == 422
    assert empty.json()["detail"] == "No active orders"

    missing = await client.post(
        bills_url(venue, f"/{uuid.uuid4()}/settle"), json={"payment_method": "cash"}
    )
    assert missing.status_code == 404

    for bid in (bill_t1, bill_t2):
        assert (await client.get(bills_url(venue, f"/{bid}"))).json()["status"] == "open"


async def test_no_tax_rate_keeps_bill_open(client, db_session, venue, monkeypatch):
    o1 = await place(client, venue.session_t1, [(venue.naan, 3)])
    bill_id = await bill_id_of(db_session, o1)
    await as_member(client, db_session, venue.r.id, "staff")
    monkeypatch.setattr("src.services.bills.default_rates", lambda: ())

    resp = await client.post(
        bills_url(venue, f"/{bill_id}/settle"), json={"payment_method": "card"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "No tax rate configured"

    d = (await client.get(bills_url(venue, f"/{bill_id}"))).json()
    assert d["status"] == "open"
    assert d["settled_at"] is None
    assert d["total"] is None
    assert d["preview_standard"] is None
    assert d["preview_digital"] is None


async def test_guest_request_bill_and_status(client, db_session, venue):
    guest(client, venue.session_t1)
    assert (await client.get("/api/guest/bill")).status_code == 404
    assert (await client.post("/api/guest/bill-request")).status_code == 404

    await place(client, venue.session_t2, [(venue.naan, 1)])
    o1 = await place(client, venue.session_t1, [(venue.naan, 2)])
    bill_id = await bill_id_of(db_session, o1)

    guest(client, venue.session_t1)
    first = await client.post("/api/guest/bill-request")
    assert first.status_code == 200, first.text
    requested_at = first.json()["bill_requested_at"]
    assert requested_at is not None
    repeat = await client.post("/api/guest/bill-request")
    assert repeat.status_code == 200
    assert repeat.json()["bill_requested_at"] == requested_at

    status_resp = await client.get("/api/guest/bill")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert {k: body[k] for k in ("bill_no", "status", "bill_requested_at")} == {
        "bill_no": await bill_no_of(db_session, bill_id),
        "status": "open",
        "bill_requested_at": requested_at,
    }

    await as_member(client, db_session, venue.r.id, "staff")
    bills = (await client.get(bills_url(venue, "?status=open"))).json()["bills"]
    assert [(b["table_label"], b["bill_requested_at"]) for b in bills] == [
        ("T1", requested_at),
        ("T2", None),
    ]

    settled = await client.post(
        bills_url(venue, f"/{bill_id}/settle"), json={"payment_method": "cash"}
    )
    assert settled.status_code == 200, settled.text
    guest(client, venue.session_t1)
    assert (await client.get("/api/guest/bill")).json()["status"] == "settled"


# --- Concurrency: committed data, independent sessions and clients ---

ROUNDS = 10


@pytest_asyncio.fixture
async def committed_venue():
    restaurant_id = uuid.uuid4()
    table_id = uuid.uuid4()
    item_id = uuid.uuid4()
    session_id = uuid.uuid4()
    slug = f"bills-par-{uuid.uuid4().hex[:8]}"
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=restaurant_id,
                name="Parallel Bills",
                slug=slug,
                currency="PKR",
                timezone="Asia/Karachi",
                languages=["en"],
                default_language="en",
                tax_jurisdiction="PB",
            )
        )
        await s.flush()
        s.add(
            DiningTable(
                id=table_id, restaurant_id=restaurant_id, label="P1", qr_token=uuid.uuid4().hex
            )
        )
        s.add(
            MenuItem(
                id=item_id,
                restaurant_id=restaurant_id,
                category="breads",
                price=Decimal("60.00"),
                unit_cost=Decimal("9.00"),
                allergen_verified=True,
            )
        )
        await s.flush()
        s.add(MenuTranslation(menu_item_id=item_id, language="en", name="Naan"))
        s.add(
            GuestSession(
                id=session_id,
                restaurant_id=restaurant_id,
                table_id=table_id,
                language="en",
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
        )
        staff = await make_user(s, [(restaurant_id, "staff")])
        await s.commit()
    try:
        yield restaurant_id, slug, item_id, session_id, staff
    finally:
        async with async_session_factory() as s:
            await s.execute(delete(AuditLog).where(AuditLog.restaurant_id == restaurant_id))
            await s.execute(delete(Order).where(Order.restaurant_id == restaurant_id))
            await s.execute(delete(Bill).where(Bill.restaurant_id == restaurant_id))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == restaurant_id))
            await s.execute(delete(MenuTranslation).where(MenuTranslation.menu_item_id == item_id))
            await s.execute(delete(MenuItem).where(MenuItem.restaurant_id == restaurant_id))
            await s.execute(delete(DiningTable).where(DiningTable.restaurant_id == restaurant_id))
            await s.execute(delete(Restaurant).where(Restaurant.id == restaurant_id))
            await s.execute(delete(User).where(User.id == staff.id))
            await s.commit()


@pytest.mark.timeout(120)
async def test_parallel_settle_and_order(committed_venue):
    restaurant_id, slug, item_id, session_id, staff = committed_venue

    def order_body() -> dict:
        return {
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(item_id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        }

    async def committed_bill_of(order_id: str) -> uuid.UUID | None:
        async with async_session_factory() as s:
            return (
                await s.execute(select(Order.bill_id).where(Order.id == uuid.UUID(order_id)))
            ).scalar_one()

    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        async with (
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={GUEST_COOKIE_NAME: sign_value(str(session_id))},
            ) as guest_client,
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as staff_client,
        ):
            sign_in(staff_client, staff)
            for n in range(ROUNDS):
                first = await guest_client.post("/api/orders", json=order_body())
                assert first.status_code == 201, first.text
                bill_id = await committed_bill_of(first.json()["id"])
                settle_req = staff_client.post(
                    f"/api/restaurants/{slug}/bills/{bill_id}/settle",
                    json={"payment_method": "cash"},
                )
                order_req = guest_client.post("/api/orders", json=order_body())
                # Alternate who starts first so both lock orders (order then settle, and
                # settle then order) are exercised.
                if n % 2:
                    racing, settle = await asyncio.gather(order_req, settle_req)
                else:
                    settle, racing = await asyncio.gather(settle_req, order_req)
                assert settle.status_code == 200, settle.text
                assert racing.status_code == 201, racing.text
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override

    async with async_session_factory() as s:
        orders = list(
            (await s.execute(select(Order).where(Order.restaurant_id == restaurant_id))).scalars()
        )
        bills = {
            b.id: b
            for b in (
                await s.execute(select(Bill).where(Bill.restaurant_id == restaurant_id))
            ).scalars()
        }
    assert len(orders) == 2 * ROUNDS
    assert all(o.bill_id in bills for o in orders)
    settled = [b for b in bills.values() if b.status == "settled"]
    assert len(settled) == ROUNDS
    assert sum(b.status == "open" for b in bills.values()) <= 1
    for o in orders:
        bill = bills[o.bill_id]
        if bill.status == "settled":
            assert o.placed_at <= bill.settled_at
    # Each settle snapshot covers exactly the orders on its bill: none joined after settle.
    for bill in settled:
        assert bill.subtotal == sum(o.total for o in orders if o.bill_id == bill.id)
    assert sorted(b.bill_no for b in bills.values()) == list(range(1, len(bills) + 1))


async def test_other_venue_bill_is_404_under_my_slug(client, db_session, venue):
    other = Restaurant(
        name="Other Venue",
        slug=f"bills-other-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(other)
    await db_session.flush()
    table = DiningTable(restaurant_id=other.id, label="B1", qr_token=uuid.uuid4().hex)
    bread = _item(other.id, "Roti", "40.00", 1)
    db_session.add_all([table, bread])
    await db_session.flush()
    session = GuestSession(
        restaurant_id=other.id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    their_bill = await bill_id_of(db_session, await place(client, session, [(bread, 2)]))

    await as_member(client, db_session, venue.r.id, "owner")
    detail = await client.get(bills_url(venue, f"/{their_bill}"))
    assert detail.status_code == 404
    settle = await client.post(
        bills_url(venue, f"/{their_bill}/settle"), json={"payment_method": "cash"}
    )
    assert settle.status_code == 404
    stored = (await db_session.execute(select(Bill).where(Bill.id == their_bill))).scalar_one()
    assert stored.status == "open"
    assert stored.settled_at is None


async def test_settled_bill_shows_snapshot_subtotal(client, db_session, venue):
    o1 = await place(client, venue.session_t1, [(venue.karahi, 1, venue.full), (venue.naan, 6)])
    bill_id = await bill_id_of(db_session, o1)
    await as_member(client, db_session, venue.r.id, "staff")
    resp = await client.post(
        bills_url(venue, f"/{bill_id}/settle"), json={"payment_method": "cash"}
    )
    assert resp.status_code == 200, resp.text

    order = (await db_session.execute(select(Order).where(Order.id == o1))).scalar_one()
    order.status = "cancelled"
    await db_session.flush()

    detail = (await client.get(bills_url(venue, f"/{bill_id}"))).json()
    assert detail["subtotal"] == "2460.00"
    assert detail["total"] == "2854.00"
    listed = (await client.get(bills_url(venue, "?status=settled"))).json()["bills"]
    assert [b["subtotal"] for b in listed] == ["2460.00"]


async def test_base_price_edit_refused_on_dish_with_sizes(client, db_session, venue):
    await as_member(client, db_session, venue.r.id, "owner")
    url = f"/api/restaurants/{venue.r.slug}/menu-items"
    for body in ({"price": "9.00"}, {"unit_cost": "9.00"}):
        resp = await client.patch(f"{url}/{venue.karahi.id}", json=body)
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Edit the size prices instead"
    ok = await client.patch(f"{url}/{venue.karahi.id}", json={"available": False})
    assert ok.status_code == 200
    assert ok.json()["available"] is False
    # A dish without sizes still takes a base price.
    plain = await client.patch(f"{url}/{venue.naan.id}", json={"price": "70.00"})
    assert plain.status_code == 200
    assert Decimal(plain.json()["price"]) == Decimal("70.00")
