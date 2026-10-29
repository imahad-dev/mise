"""Portion options: guest menu, order snapshot, validation, idempotency, kitchen ticket."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


@dataclass
class KarahiSetup:
    restaurant: Restaurant
    karahi: MenuItem
    naan: MenuItem
    half: MenuItemOption
    full: MenuItemOption
    other_item_option: MenuItemOption


def _item(restaurant_id: uuid.UUID, name: str, price: str, cost: str, sort: int) -> MenuItem:
    item = MenuItem(
        restaurant_id=restaurant_id,
        category="mains",
        price=Decimal(price),
        unit_cost=Decimal(cost),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=sort,
    )
    item.translations = [MenuTranslation(language="en", name=name)]
    return item


@pytest_asyncio.fixture
async def karahi_setup(client: AsyncClient, db_session: AsyncSession) -> KarahiSetup:
    restaurant = Restaurant(
        name="Options Venue",
        slug=f"options-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(restaurant)
    await db_session.flush()

    table = DiningTable(restaurant_id=restaurant.id, label="T1", qr_token=uuid.uuid4().hex)
    karahi = _item(restaurant.id, "Chicken Karahi", "1100", "500", 1)
    naan = _item(restaurant.id, "Naan", "60.00", "9.00", 2)
    other = _item(restaurant.id, "Mutton Karahi", "2300", "1060", 3)
    db_session.add_all([table, karahi, naan, other])
    await db_session.flush()

    half = MenuItemOption(
        menu_item_id=karahi.id, label="Half", price=Decimal("1100.00"), unit_cost=Decimal("500.00")
    )
    full = MenuItemOption(
        menu_item_id=karahi.id,
        label="Full",
        price=Decimal("2100.00"),
        unit_cost=Decimal("950.00"),
        sort_order=1,
    )
    other_opt = MenuItemOption(
        menu_item_id=other.id, label="Half", price=Decimal("2300.00"), unit_cost=Decimal("1060.00")
    )
    db_session.add_all([half, full, other_opt])

    session = GuestSession(
        restaurant_id=restaurant.id,
        table_id=table.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    return KarahiSetup(restaurant, karahi, naan, half, full, other_opt)


async def test_menu_lists_options(client, karahi_setup):
    menu = (await client.get("/api/guest/menu")).json()
    karahi = next(i for i in menu["items"] if i["name"] == "Chicken Karahi")
    assert [(o["label"], o["price"]) for o in karahi["options"]] == [
        ("Half", "1100.00"),
        ("Full", "2100.00"),
    ]
    assert "unit_cost" not in karahi["options"][0]
    naan = next(i for i in menu["items"] if i["name"] == "Naan")
    assert naan["options"] == []


async def test_order_snapshots_option_price(client, karahi_setup):
    s = karahi_setup
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "k1",
            "items": [
                {"menu_item_id": str(s.karahi.id), "option_id": str(s.full.id), "quantity": 1},
                {"menu_item_id": str(s.naan.id), "quantity": 4},
            ],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "2340.00"
    assert body["currency"] == "PKR"
    line = next(i for i in body["items"] if i["menu_item_id"] == str(s.karahi.id))
    assert line["option_label"] == "Full" and line["unit_price"] == "2100.00"


@pytest.mark.parametrize("case", ["missing", "foreign", "unknown", "on_plain_item"])
async def test_bad_options_are_422(client, karahi_setup, case):
    s = karahi_setup
    item = {"menu_item_id": str(s.karahi.id), "quantity": 1}
    if case == "foreign":
        item["option_id"] = str(s.other_item_option.id)  # option of a different dish
    elif case == "unknown":
        item["option_id"] = "00000000-0000-0000-0000-000000000000"
    elif case == "on_plain_item":
        item = {"menu_item_id": str(s.naan.id), "option_id": str(s.full.id), "quantity": 1}
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": f"bad-{case}",
            "items": [item],
            "acknowledge_allergen_risk": True,
        },
    )
    assert resp.status_code == 422


async def test_same_dish_two_sizes_is_not_a_replay(client, karahi_setup):
    s = karahi_setup

    def body(opt):
        return {
            "idempotency_key": "same-key",
            "acknowledge_allergen_risk": True,
            "items": [{"menu_item_id": str(s.karahi.id), "option_id": str(opt.id), "quantity": 1}],
        }

    assert (await client.post("/api/orders", json=body(s.half))).status_code == 201
    assert (await client.post("/api/orders", json=body(s.full))).status_code == 409


async def test_kitchen_ticket_shows_option(client, db_session, karahi_setup):
    s = karahi_setup
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "kitchen-1",
            "acknowledge_allergen_risk": True,
            "items": [
                {"menu_item_id": str(s.karahi.id), "option_id": str(s.full.id), "quantity": 1}
            ],
        },
    )
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    await as_member(client, db_session, s.restaurant.id, "staff")
    kitchen = await client.get(f"/api/restaurants/{s.restaurant.slug}/kitchen/orders")
    assert kitchen.status_code == 200
    order = next(o for o in kitchen.json()["orders"] if o["id"] == order_id)
    assert [(i["kitchen_name"], i["option_label"]) for i in order["items"]] == [
        ("Chicken Karahi", "Full")
    ]


async def test_two_sizes_of_one_dish_make_two_lines(client, karahi_setup):
    s = karahi_setup
    resp = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "two-sizes",
            "acknowledge_allergen_risk": True,
            "items": [
                {"menu_item_id": str(s.karahi.id), "option_id": str(s.half.id), "quantity": 1},
                {"menu_item_id": str(s.karahi.id), "option_id": str(s.full.id), "quantity": 1},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "3200.00"
    assert sorted((i["option_label"], i["unit_price"]) for i in body["items"]) == [
        ("Full", "2100.00"),
        ("Half", "1100.00"),
    ]


async def test_identical_replay_returns_same_order(client, karahi_setup):
    s = karahi_setup
    body = {
        "idempotency_key": "replay",
        "acknowledge_allergen_risk": True,
        "items": [{"menu_item_id": str(s.karahi.id), "option_id": str(s.full.id), "quantity": 1}],
    }
    first = await client.post("/api/orders", json=body)
    again = await client.post("/api/orders", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["currency"] == "PKR"
    fetched = await client.get(f"/api/orders/{first.json()['id']}")
    assert fetched.status_code == 200 and fetched.json()["currency"] == "PKR"
