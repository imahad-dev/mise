"""Choices on bills and kitchen tickets; VAT and service stay right with extras."""

import uuid
from decimal import Decimal

import pytest_asyncio
from tests.choices_setup import build_tea, line, order, tea_setup  # noqa: F401 - fixture
from tests.helpers import approve_order, as_member, settle
from tests.test_bills import bill_id_of

from src.models.bill import Bill


@pytest_asyncio.fixture
async def gb_tea(client, db_session):
    return await build_tea(
        client,
        db_session,
        jurisdiction="GB",
        currency="GBP",
        timezone="Europe/London",
        price="3.00",
        milk="0.50",
        honey="0.30",
        avoid=(),
        service_charge_rate="0.125",
    )


@pytest_asyncio.fixture
async def dubai_tea(client, db_session):
    return await build_tea(
        client,
        db_session,
        jurisdiction="AE-DU",
        currency="AED",
        timezone="Asia/Dubai",
        price="3.00",
        milk="0.50",
        honey="0.30",
        avoid=(),
    )


async def settled_bill(client, db, s, choices, method="cash", **settle_kwargs):
    """Order the tea with these choices, have staff approve and settle it, return the Bill."""
    placed = await order(client, uuid.uuid4().hex, [line(s, *choices)], ack=True)
    assert placed.status_code == 201, placed.text
    await approve_order(placed.json()["id"])
    bill_id = await bill_id_of(db, uuid.UUID(placed.json()["id"]))
    await as_member(client, db, s.restaurant.id, "staff")
    resp = await settle(client, s.restaurant.slug, bill_id, method, **settle_kwargs)
    assert resp.status_code == 200, resp.text
    return await db.get(Bill, bill_id, populate_existing=True)


async def test_same_price_different_choices_stay_separate_lines():
    from src.models.order import Order, OrderItem
    from src.services.bills import bill_lines

    def oi(label):
        return OrderItem(
            item_name="Tea",
            option_label=None,
            unit_price=Decimal("300.00"),
            quantity=1,
            choices=[
                {
                    "choice_id": str(uuid.uuid4()),
                    "group": "Sugar",
                    "kind": "pick",
                    "label": label,
                    "price_delta": "0.00",
                }
            ],
        )

    lines, subtotal = bill_lines([Order(items=[oi("No sugar"), oi("Less sugar"), oi("No sugar")])])
    assert sorted((ln.choices[0].label, ln.quantity) for ln in lines) == [
        ("Less sugar", 1),
        ("No sugar", 2),
    ]
    assert subtotal == Decimal("900.00")


async def test_kitchen_ticket_shows_choices_and_the_union(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    placed = await order(client, "kk", [line(s, s.mild, s.extra_milk, s.no_sugar)], ack=True)
    await approve_order(placed.json()["id"])
    await as_member(client, db_session, s.restaurant.id, "staff")
    orders = (await client.get(f"/api/restaurants/{s.restaurant.slug}/kitchen/orders")).json()[
        "orders"
    ]
    item = orders[0]["items"][0]
    assert [(c["kind"], c["label"]) for c in item["choices"]] == [
        ("pick", "Mild"),
        ("add", "Extra milk"),
        ("leave_out", "Sugar"),
    ]
    assert "milk" in item["allergens"]
    assert "cost_delta" not in item["choices"][0]


async def test_gb_vat_is_inside_the_price_with_extras(client, gb_tea, db_session):
    """£3.00 tea + £0.50 milk: the guest pays the menu price, VAT worked out on the total."""
    bill = await settled_bill(client, db_session, gb_tea, [gb_tea.mild, gb_tea.extra_milk])
    assert (str(bill.total), str(bill.tax_amount)) == ("3.50", "0.58")


async def test_dubai_vat_is_inside_the_price_with_extras(client, dubai_tea, db_session):
    bill = await settled_bill(client, db_session, dubai_tea, [dubai_tea.mild, dubai_tea.extra_milk])
    assert (str(bill.total), str(bill.tax_amount)) == ("3.50", "0.17")


async def test_pakistan_bill_with_extras_adds_tax_on_top(client, tea_setup, db_session):  # noqa: F811
    """Rs 350 at the 16% cash rate: tax 56, total 406."""
    s = tea_setup
    bill = await settled_bill(client, db_session, s, [s.mild, s.extra_milk])
    assert (bill.subtotal, bill.tax_amount, bill.total) == (
        Decimal("350.00"),
        Decimal("56.00"),
        Decimal("406.00"),
    )


async def test_gb_service_charge_includes_extras(client, gb_tea, db_session):
    """Optional 12.5% of £3.50 = £0.44, on top of the menu price."""
    s = gb_tea
    bill = await settled_bill(client, db_session, s, [s.mild, s.extra_milk], service_included=True)
    assert (str(bill.service_charge_amount), str(bill.total)) == ("0.44", "3.94")
