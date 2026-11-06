"""Placing an order with dish choices: server prices, allergen union, hashing, snapshots."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import open_table

from src.auth import GUEST_COOKIE_NAME, sign_value
from src.models.dining_table import DiningTable
from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem, MenuTranslation
from src.models.order import OrderItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession


@dataclass
class TeaSetup:
    restaurant: Restaurant
    tea: MenuItem
    mild: MenuChoice
    hot: MenuChoice
    extra_milk: MenuChoice
    honey: MenuChoice
    no_sugar: MenuChoice


@pytest_asyncio.fixture
async def tea_setup(client: AsyncClient, db_session: AsyncSession) -> TeaSetup:
    """A tea with one required pick, two extras and a leave-out, ordered by a guest avoiding milk.

    Built to be reused: the guest cookie is set and the table is open.
    """
    restaurant = Restaurant(
        name="Choices Venue",
        slug=f"choices-{uuid.uuid4().hex[:8]}",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(restaurant)
    await db_session.flush()

    table = DiningTable(restaurant_id=restaurant.id, label="T1", qr_token=uuid.uuid4().hex)
    tea = MenuItem(
        restaurant_id=restaurant.id,
        category="drinks",
        price=Decimal("300.00"),
        unit_cost=Decimal("60.00"),
        ingredients=[],
        allergens=[],
        allergen_verified=True,
        dietary_verified=True,
        sort_order=1,
    )
    tea.translations = [MenuTranslation(language="en", name="Tea")]
    db_session.add_all([table, tea])
    await db_session.flush()

    spice = MenuChoiceGroup(
        menu_item_id=tea.id, label="Spice", kind="pick", min_select=1, max_select=1, sort_order=0
    )
    extras = MenuChoiceGroup(
        menu_item_id=tea.id, label="Extras", kind="add", min_select=0, max_select=2, sort_order=1
    )
    leave = MenuChoiceGroup(
        menu_item_id=tea.id,
        label="Leave out",
        kind="leave_out",
        min_select=0,
        max_select=1,
        sort_order=2,
    )
    db_session.add_all([spice, extras, leave])
    await db_session.flush()

    mild = MenuChoice(group_id=spice.id, label="Mild", allergen_verified=True, sort_order=0)
    hot = MenuChoice(group_id=spice.id, label="Hot", allergen_verified=True, sort_order=1)
    extra_milk = MenuChoice(
        group_id=extras.id,
        label="Extra milk",
        price_delta=Decimal("50.00"),
        cost_delta=Decimal("12.00"),
        allergens=["milk"],
        allergen_verified=True,
        sort_order=0,
    )
    honey = MenuChoice(
        group_id=extras.id, label="Honey", price_delta=Decimal("30.00"), sort_order=1
    )
    no_sugar = MenuChoice(group_id=leave.id, label="Sugar", allergen_verified=True)
    db_session.add_all([mild, hot, extra_milk, honey, no_sugar])

    session = GuestSession(
        restaurant_id=restaurant.id,
        table_id=table.id,
        language="en",
        allergens_to_avoid=["milk"],
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    await open_table(db_session, table.id)
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    return TeaSetup(restaurant, tea, mild, hot, extra_milk, honey, no_sugar)


async def order(client, key, lines, ack=False):
    return await client.post(
        "/api/orders",
        json={"idempotency_key": key, "items": lines, "acknowledge_allergen_risk": ack},
    )


def line(s, *choices, quantity=1):
    return {
        "menu_item_id": str(s.tea.id),
        "quantity": quantity,
        "choice_ids": [str(c.id) for c in choices],
    }


async def test_server_prices_the_line(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k1", [line(s, s.mild, s.extra_milk, quantity=2)], ack=True)
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "700.00"
    item = body["items"][0]
    assert item["unit_price"] == "350.00"
    assert [c["label"] for c in item["choices"]] == ["Mild", "Extra milk"]
    assert "cost_delta" not in item["choices"][0]


async def test_cost_is_snapshotted(client, tea_setup, db_session):
    s = tea_setup
    resp = await order(client, "k2", [line(s, s.mild, s.extra_milk)], ack=True)
    row = await db_session.get(OrderItem, uuid.UUID(resp.json()["items"][0]["id"]))
    assert row.unit_cost == Decimal("72.00")
    assert row.allergens == ["milk"]


async def test_extra_milk_stops_at_the_acknowledgement(client, tea_setup):
    s = tea_setup  # this session avoids milk
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "allergen_ack_required"
    assert resp.json()["detail"]["items"][0]["matched_allergens"] == ["milk"]
    resp = await order(client, "k3", [line(s, s.mild, s.extra_milk)], ack=True)
    assert resp.status_code == 201
    assert resp.json()["items"][0]["allergen_status"] == "contains"


async def test_unconfirmed_choice_needs_the_acknowledgement(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k4", [line(s, s.mild, s.honey)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["items"][0]["status"] == "unverified"


async def test_leave_out_changes_nothing(client, tea_setup):
    s = tea_setup
    item = (await order(client, "k5", [line(s, s.mild, s.no_sugar)])).json()["items"][0]
    assert item["allergens"] == []
    assert item["allergen_status"] == "no_declared_match"
    assert item["unit_price"] == "300.00"


async def test_repeated_choice_is_refused(client, tea_setup):
    s = tea_setup
    resp = await order(client, "k6", [line(s, s.mild, s.mild)])
    assert resp.status_code == 422


async def test_missing_required_choice_is_choices_changed(client, tea_setup):
    resp = await order(client, "k7", [line(tea_setup)])
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "choices_changed"


async def test_sold_out_choice_is_refused(client, tea_setup, db_session):
    s = tea_setup
    s.mild.available = False
    await db_session.flush()
    resp = await order(client, "k8", [line(s, s.mild)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_choices"


async def test_required_group_sold_out_stops_the_dish(client, tea_setup, db_session):
    s = tea_setup
    s.mild.available = False
    s.hot.available = False
    await db_session.flush()
    resp = await order(client, "k9", [line(s)])
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "unavailable_items"


async def test_retry_with_choices_in_any_order_is_a_retry(client, tea_setup):
    s = tea_setup
    first = await order(client, "k10", [line(s, s.mild, s.no_sugar)])
    again = await order(client, "k10", [line(s, s.no_sugar, s.mild)])
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


async def test_same_key_with_other_choices_conflicts(client, tea_setup):
    s = tea_setup
    assert (await order(client, "k11", [line(s, s.mild)])).status_code == 201
    assert (await order(client, "k11", [line(s, s.hot)])).status_code == 409


def test_a_line_without_choices_keeps_its_old_hash():
    from src.routers.orders import compute_payload_hash
    from src.schemas.orders import OrderItemRequest

    menu_item_id = uuid.UUID(int=1)
    canonical = [{"menu_item_id": str(menu_item_id), "option_id": "", "quantity": 1, "notes": ""}]
    expected = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    assert (
        compute_payload_hash([OrderItemRequest(menu_item_id=menu_item_id, quantity=1)]) == expected
    )


async def test_menu_price_change_leaves_old_lines(client, tea_setup, db_session):
    s = tea_setup
    placed = (await order(client, "k12", [line(s, s.mild, s.no_sugar)])).json()
    s.tea.price = Decimal("999.00")
    await db_session.flush()
    fetched = (await client.get(f"/api/orders/{placed['id']}")).json()
    assert fetched["items"][0]["unit_price"] == "300.00"
