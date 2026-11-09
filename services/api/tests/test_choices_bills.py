"""Choices on bills and kitchen tickets; VAT and service stay right with extras."""

import uuid
from decimal import Decimal

import pytest_asyncio
from tests.choices_setup import build_tea, line, order, tea_setup  # noqa: F401 - fixture
from tests.helpers import approve_order, as_member, settle
from tests.test_bills import bill_id_of

from src.auth import GUEST_COOKIE_NAME
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

    lines, subtotal = bill_lines(
        [Order(items=[oi("No sugar"), oi("Less sugar")]), Order(items=[oi("No sugar")])]
    )
    # The exact order, merged across orders; no sorting here.
    assert [(ln.choices[0].label, ln.quantity) for ln in lines] == [
        ("Less sugar", 1),
        ("No sugar", 2),
    ]
    assert subtotal == Decimal("900.00")


async def test_reordered_groups_do_not_split_a_line():
    from src.models.order import Order, OrderItem
    from src.services.bills import bill_lines

    def choice(group, label):
        return {
            "choice_id": str(uuid.uuid4()),
            "group": group,
            "kind": "pick",
            "label": label,
            "price_delta": "0.00",
        }

    def oi(*chosen):
        return OrderItem(
            item_name="Tea",
            option_label=None,
            unit_price=Decimal("300.00"),
            quantity=1,
            choices=list(chosen),
        )

    lines, _ = bill_lines(
        [
            Order(items=[oi(choice("Spice", "Mild"), choice("Sugar", "Less"))]),
            Order(items=[oi(choice("Sugar", "Less"), choice("Spice", "Mild"))]),
        ]
    )
    assert [ln.quantity for ln in lines] == [2]


async def test_void_keeps_each_orders_choices(client, tea_setup, db_session):  # noqa: F811
    s = tea_setup
    guest_cookie = client.cookies.get(GUEST_COOKIE_NAME)
    live = await order(client, "v1", [line(s, s.mild, s.no_sugar)], ack=True)
    wrong = await order(client, "v2", [line(s, s.hot, s.no_sugar)], ack=True)
    await approve_order(live.json()["id"])
    await approve_order(wrong.json()["id"])
    staff = await as_member(client, db_session, s.restaurant.id, "staff")
    assert staff
    slug = s.restaurant.slug
    resp = await client.post(
        f"/api/restaurants/{slug}/orders/{wrong.json()['id']}/void", json={"reason": "Wrong"}
    )
    assert resp.status_code == 200, resp.text

    def labels(row):
        return [(c["kind"], c["label"]) for c in row["choices"]]

    bill_id = await bill_id_of(db_session, uuid.UUID(live.json()["id"]))
    detail = (await client.get(f"/api/restaurants/{slug}/bills/{bill_id}")).json()
    assert [labels(ln) for ln in detail["lines"]] == [[("pick", "Mild"), ("leave_out", "Sugar")]]

    client.cookies.set(GUEST_COOKIE_NAME, guest_cookie)
    raw = await client.get("/api/guest/bill")
    g = raw.json()
    assert [labels(ln) for ln in g["lines"]] == [[("pick", "Mild"), ("leave_out", "Sugar")]]
    assert [labels(v) for v in g["voided"]] == [[("pick", "Hot"), ("leave_out", "Sugar")]]
    assert "cost_delta" not in raw.text
    assert "cost_delta" not in str(detail)


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


async def test_same_labels_and_price_but_different_extra_prices_stay_separate():
    from src.models.order import Order, OrderItem
    from src.services.bills import bill_lines

    def oi(delta):
        return OrderItem(
            item_name="Tea",
            option_label=None,
            unit_price=Decimal("450.00"),  # 300 + 150 before a price change, 250 + 200 after
            quantity=1,
            choices=[
                {
                    "choice_id": str(uuid.uuid4()),
                    "group": "Extras",
                    "kind": "add",
                    "label": "Extra shot",
                    "price_delta": delta,
                }
            ],
        )

    lines, _ = bill_lines([Order(items=[oi("150.00")]), Order(items=[oi("200.00")])])
    assert sorted(ln.choices[0].price_delta for ln in lines) == [Decimal("150"), Decimal("200")]
