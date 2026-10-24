"""Table bills: orders join the table's open bill; list, detail, settle, guest request."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


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
