"""A tea with choices, ready to order, shared by the choice tests (import `tea_setup` to use it)."""

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


async def build_tea(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    jurisdiction: str = "PB",
    currency: str = "PKR",
    timezone: str = "Asia/Karachi",
    price: str = "300.00",
    milk: str = "50.00",
    honey: str = "30.00",
    avoid: tuple[str, ...] = ("milk",),
    service_charge_rate: str = "0",
) -> TeaSetup:
    """A tea with one required pick, two extras and a leave-out, ordered by a guest avoiding
    `avoid`. The guest cookie is set and the table is open."""
    restaurant = Restaurant(
        name="Choices Venue",
        slug=f"choices-{uuid.uuid4().hex[:8]}",
        currency=currency,
        timezone=timezone,
        languages=["en"],
        default_language="en",
        tax_jurisdiction=jurisdiction,
        service_charge_rate=Decimal(service_charge_rate),
    )
    db_session.add(restaurant)
    await db_session.flush()

    table = DiningTable(restaurant_id=restaurant.id, label="T1", qr_token=uuid.uuid4().hex)
    tea = MenuItem(
        restaurant_id=restaurant.id,
        category="drinks",
        price=Decimal(price),
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
        price_delta=Decimal(milk),
        cost_delta=Decimal("12.00"),
        allergens=["milk"],
        allergen_verified=True,
        sort_order=0,
    )
    honey_choice = MenuChoice(
        group_id=extras.id, label="Honey", price_delta=Decimal(honey), sort_order=1
    )
    no_sugar = MenuChoice(group_id=leave.id, label="Sugar", allergen_verified=True)
    db_session.add_all([mild, hot, extra_milk, honey_choice, no_sugar])

    session = GuestSession(
        restaurant_id=restaurant.id,
        table_id=table.id,
        language="en",
        allergens_to_avoid=list(avoid),
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    await open_table(db_session, table.id)
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    return TeaSetup(restaurant, tea, mild, hot, extra_milk, honey_choice, no_sugar)


@pytest_asyncio.fixture
async def tea_setup(client: AsyncClient, db_session: AsyncSession) -> TeaSetup:
    """Pakistan (Punjab): tea Rs 300, extra milk Rs 50, a guest avoiding milk."""
    return await build_tea(client, db_session)


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
