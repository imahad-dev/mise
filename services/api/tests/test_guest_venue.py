"""The guest API names only the scanned venue and never serves another venue's data."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import approve_order, open_table

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


def _item(rid: uuid.UUID, name: str) -> MenuItem:
    item = MenuItem(
        restaurant_id=rid,
        category="mains",
        price=Decimal("100.00"),
        unit_cost=Decimal("1.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


async def _venue(db: AsyncSession, name: str, dish: str):
    r = Restaurant(
        name=name,
        slug=f"v-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db.add(r)
    await db.flush()
    t = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    item = _item(r.id, dish)
    db.add_all([t, item])
    await db.flush()
    s = GuestSession(
        restaurant_id=r.id,
        table_id=t.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db.add(s)
    await db.flush()
    return r, t, item, s


def _as_guest(client: AsyncClient, s: GuestSession) -> None:
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(s.id)))


@pytest.mark.asyncio
async def test_qr_token_names_its_venue_and_its_languages_and_nothing_else(client, db_session):
    r, t, _, _ = await _venue(db_session, "Venue A", "Dish A")
    res = await client.get(f"/api/guest/venues/{t.qr_token}")
    assert res.status_code == 200
    assert res.json() == {"slug": r.slug, "name": "Venue A", "languages": ["en"], "default_language": "en"}


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["not-a-token", "x" * 300, "%00", "' OR 1=1 --"])
async def test_unknown_qr_token_is_404(client, token):
    res = await client.get(f"/api/guest/venues/{token}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_session_create_and_status_carry_the_venue(client, db_session):
    r, t, _, _ = await _venue(db_session, "Venue A", "Dish A")
    created = await client.post(
        "/api/guest/sessions",
        json={
            "qr_token": t.qr_token,
            "language": "en",
            "dietary_preferences": [],
            "allergens_to_avoid": [],
        },
    )
    assert created.status_code == 201
    assert created.json()["venue"] == {"slug": r.slug, "name": "Venue A", "languages": ["en"], "default_language": "en"}
    status = await client.get("/api/guest/session")  # the create call set the cookie
    assert status.status_code == 200
    assert status.json()["venue"] == {"slug": r.slug, "name": "Venue A", "languages": ["en"], "default_language": "en"}


@pytest.mark.asyncio
async def test_a_guest_never_gets_another_venues_menu_order_bill_or_call(client, db_session):
    _, _, _, sa = await _venue(db_session, "Venue A", "Dish A")
    rb, tb, dish_b, sb = await _venue(db_session, "Venue B", "Dish B")

    # Venue B: a real order and a service call from B's own guest.
    await open_table(db_session, tb.id)
    _as_guest(client, sb)
    order = await client.post(
        "/api/orders",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "items": [{"menu_item_id": str(dish_b.id), "quantity": 1}],
        },
    )
    assert order.status_code in (200, 201, 202), order.text
    b_order = order.json()["id"]
    await approve_order(b_order)
    call = await client.post("/api/guest/service-calls", json={"reason": "water"})
    assert call.status_code in (200, 201), call.text

    # Venue A's guest asks for all of it.
    _as_guest(client, sa)
    menu = (await client.get("/api/guest/menu")).text
    assert "Dish B" not in menu and "Venue B" not in menu and rb.slug not in menu
    assert (await client.get(f"/api/orders/{b_order}")).status_code == 404
    assert (await client.get(f"/api/guest/bill?order_id={b_order}")).status_code == 404
    current = await client.get("/api/guest/service-calls/current")
    assert current.status_code == 200
    assert current.json()["call"] is None


@pytest.mark.asyncio
async def test_session_create_with_a_nul_byte_token_is_404(client):
    res = await client.post(
        "/api/guest/sessions",
        json={
            "qr_token": "abc" + chr(0) + "def",
            "language": "en",
            "dietary_preferences": [],
            "allergens_to_avoid": [],
        },
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Unknown QR token"
