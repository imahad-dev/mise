"""Simulator: venue profiles, per-item and option weights, one settled bill per party."""

import uuid
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill
from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.models.order import Order, OrderItem
from src.models.restaurant import Restaurant
from src.services.simulator import (
    SEED_ITEM_NAMESPACE,
    SimAssumptions,
    SimItem,
    generate_orders,
    persist_simulation,
)
from src.services.tax import tax_for

TZ = ZoneInfo("Asia/Karachi")
START = date(2026, 8, 1)
OPT_A, OPT_B = uuid.UUID(int=101), uuid.UUID(int=102)
ITEMS = [
    SimItem(id=uuid.UUID(int=1), weight=2.0),
    SimItem(id=uuid.UUID(int=2), weight=10.0, options=((OPT_A, 0.7), (OPT_B, 0.3))),
    SimItem(id=uuid.UUID(int=3), weight=5.0),
    SimItem(id=uuid.UUID(int=4), weight=1.0),
]


def _flat(orders):
    return [(o.placed_at, o.lines, o.payment_method, o.settle_after) for o in orders]


def test_weights_options_and_determinism():
    a = SimAssumptions(days=56, seed=3, promo_item_rank=None)
    first = generate_orders(ITEMS, START, a, TZ)
    assert first
    assert _flat(first) == _flat(generate_orders(list(reversed(ITEMS)), START, a, TZ))

    units: Counter = Counter()
    options: Counter = Counter()
    for o in first:
        for (item, option), q in o.lines.items():
            units[item] += q
            if item == uuid.UUID(int=2):
                assert option in (OPT_A, OPT_B)
                options[option] += q
            else:
                assert option is None
    assert units.most_common(1)[0][0] == uuid.UUID(int=2)
    share_a = options[OPT_A] / sum(options.values())
    assert abs(share_a - 0.7) <= 0.05

    for o in first:
        assert 45 <= o.settle_after <= 75
        assert o.payment_method in {"cash", "card", "wallet", "raast"}


def test_payment_and_options_do_not_move_the_order_stream():
    a = SimAssumptions(days=14, seed=9, promo_item_rank=None)
    plain = [SimItem(id=i.id, weight=i.weight) for i in ITEMS]
    other_mix = SimAssumptions(days=14, seed=9, promo_item_rank=None, payment_mix=(("card", 1.0),))
    base = generate_orders(plain, START, a, TZ)
    varied = generate_orders(ITEMS, START, other_mix, TZ)
    assert [o.placed_at for o in base] == [o.placed_at for o in varied]

    def dishes(o) -> Counter:  # units per item, summed over options
        c: Counter = Counter()
        for (item, _), q in o.lines.items():
            c[item] += q
        return c

    assert [dishes(o) for o in base] == [dishes(o) for o in varied]
    assert {o.payment_method for o in varied} == {"card"}


def test_mix_with_no_accepted_method_is_refused():
    a = SimAssumptions(days=3, payment_mix=(("wallet", 0.5), ("raast", 0.5)))
    with pytest.raises(ValueError, match="no weight on the methods accepted"):
        generate_orders(ITEMS, START, a, TZ, {"cash", "card"})


def test_from_profile_converts_lists_and_rejects_unknown_keys():
    a = SimAssumptions.from_profile(
        {
            "lunch_hours": [13, 16],
            "payment_mix": [["cash", 0.5], ["card", 0.5]],
            "weights": {"x": 2},
            "option_weights": {"x": [1]},
        }
    )
    assert a.lunch_hours == (13, 16)
    assert a.payment_mix == (("cash", 0.5), ("card", 0.5))
    with pytest.raises(ValueError):
        SimAssumptions.from_profile({"zipf": 1.0})
    with pytest.raises(ValueError):
        SimAssumptions.from_profile({"payment_mix": [["cheque", 1.0]]})


async def _seeded(db: AsyncSession) -> Restaurant:
    await seed_data(load_seed_data("data/seed/angeethi_house.json"), db, rotate_qr=False)
    return (
        await db.execute(select(Restaurant).where(Restaurant.slug == "angeethi-house"))
    ).scalar_one()


@pytest.mark.asyncio
@pytest.mark.timeout(240)
async def test_persist_simulation_writes_one_settled_bill_per_party(db_session: AsyncSession):
    restaurant = await _seeded(db_session)
    profile = restaurant.onboarding["simulation"]
    karahi_key = uuid.uuid5(SEED_ITEM_NAMESPACE, "angeethi-house:chicken_karahi")
    assert profile["weights"]["chicken_karahi"] > 0
    assert profile["option_weights"]["chicken_karahi"] == [0.55, 0.45]

    a = SimAssumptions.from_profile(profile)
    tz = ZoneInfo(restaurant.timezone)
    summary = await persist_simulation(db_session, restaurant, a)
    n = summary["orders_created"]
    assert n > 500
    assert summary["bills_created"] == n

    rows = (
        await db_session.execute(
            select(Order.total, Order.placed_at, Bill)
            .join(Bill, Bill.id == Order.bill_id)
            .where(Order.restaurant_id == restaurant.id, Order.source == "simulated")
        )
    ).all()
    assert len(rows) == n  # every simulated order has a bill
    methods: Counter = Counter()
    for total, placed_at, bill in rows:
        assert (bill.source, bill.bill_no, bill.status, bill.table_id) == (
            "simulated",
            None,
            "settled",
            None,
        )
        assert bill.opened_at == placed_at
        assert timedelta(minutes=45) <= bill.settled_at - placed_at <= timedelta(minutes=75)
        assert bill.subtotal == total
        rate, tax = tax_for(
            "PB", bill.payment_method, bill.settled_at.astimezone(tz).date(), bill.subtotal
        )
        assert (bill.tax_rate, bill.tax_amount) == (rate, tax)
        assert bill.total == bill.subtotal + bill.tax_amount
        assert (bill.tax_jurisdiction, bill.tax_pricing) == ("PB", "on_top")
        methods[bill.payment_method] += 1
    for method, share in a.payment_mix:
        assert abs(methods[method] / n - share) <= 0.05, (method, methods)

    # Items with options always carry one; the karahi options follow their weights loosely
    missing = (
        await db_session.execute(
            select(func.count())
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.restaurant_id == restaurant.id,
                OrderItem.menu_item_id == karahi_key,
                OrderItem.option_id.is_(None),
            )
        )
    ).scalar_one()
    assert missing == 0

    async def bill_counts() -> tuple[int, int]:
        total_bills = (
            await db_session.execute(
                select(func.count()).select_from(Bill).where(Bill.restaurant_id == restaurant.id)
            )
        ).scalar_one()
        orphans = (
            await db_session.execute(
                select(func.count())
                .select_from(Bill)
                .where(
                    Bill.restaurant_id == restaurant.id,
                    ~select(Order.id).where(Order.bill_id == Bill.id).exists(),
                )
            )
        ).scalar_one()
        return total_bills, orphans

    assert await bill_counts() == (n, 0)
    # Re-running replaces bills with the orders: same count, nothing left behind
    again = await persist_simulation(db_session, restaurant, a)
    assert again["orders_created"] == n
    assert await bill_counts() == (n, 0)


@pytest.mark.asyncio
@pytest.mark.timeout(240)
async def test_longest_history_still_bills_every_order(db_session: AsyncSession):
    """days=120 (the API maximum) reaches before 1 July 2026; the earlier Punjab rate applies."""
    restaurant = await _seeded(db_session)
    a = replace(SimAssumptions.from_profile(restaurant.onboarding["simulation"]), days=120)
    summary = await persist_simulation(db_session, restaurant, a, today=date(2026, 10, 24))
    assert summary["start_date"] < "2026-07-01"
    counts = (
        await db_session.execute(
            select(func.count(Order.id), func.count(Order.bill_id)).where(
                Order.restaurant_id == restaurant.id, Order.source == "simulated"
            )
        )
    ).one()
    assert counts[0] == summary["orders_created"] > 0
    assert counts[1] == counts[0]
    early = (
        await db_session.execute(
            select(func.count())
            .select_from(Bill)
            .where(
                Bill.restaurant_id == restaurant.id,
                Bill.payment_method != "cash",
                Bill.tax_rate == Decimal("0.05"),
            )
        )
    ).scalar_one()
    assert early > 0  # digital bills settled before 1 July 2026 use 5%


@pytest.mark.asyncio
async def test_simulated_uk_bills_include_vat_and_use_cash_or_card(db_session: AsyncSession):
    restaurant = Restaurant(
        name="UK Cafe",
        slug=f"uk-{uuid.uuid4().hex[:8]}",
        timezone="Europe/London",
        currency="GBP",
        tax_jurisdiction="GB",
    )
    db_session.add(restaurant)
    await db_session.flush()
    db_session.add(
        MenuItem(
            restaurant_id=restaurant.id,
            category="mains",
            price=Decimal("12.50"),
            unit_cost=Decimal("4.00"),
        )
    )
    await db_session.flush()
    await persist_simulation(db_session, restaurant, SimAssumptions(days=14))
    bills = (
        (await db_session.execute(select(Bill).where(Bill.restaurant_id == restaurant.id)))
        .scalars()
        .all()
    )
    assert bills
    assert {b.payment_method for b in bills} == {"cash", "card"}
    for b in bills:
        assert b.payment_method in ("cash", "card")
        assert b.tax_pricing == "included"
        assert b.total == b.subtotal
        assert b.tax_amount == (b.subtotal * b.tax_rate / (1 + b.tax_rate)).quantize(
            Decimal("0.01"), "ROUND_HALF_UP"
        )


@pytest.mark.asyncio
async def test_simulation_without_tax_jurisdiction_writes_no_bills(db_session: AsyncSession):
    restaurant = Restaurant(
        name="No Tax Cafe", slug=f"no-tax-{uuid.uuid4().hex[:8]}", timezone="Asia/Karachi"
    )
    db_session.add(restaurant)
    await db_session.flush()
    db_session.add(
        MenuItem(
            restaurant_id=restaurant.id,
            category="mains",
            price=Decimal("500.00"),
            unit_cost=Decimal("200.00"),
        )
    )
    await db_session.flush()
    summary = await persist_simulation(db_session, restaurant, SimAssumptions(days=7))
    assert summary["orders_created"] > 0
    assert summary["bills_created"] == 0
    bills = (
        await db_session.execute(
            select(func.count()).select_from(Bill).where(Bill.restaurant_id == restaurant.id)
        )
    ).scalar_one()
    assert bills == 0


SPICE = (uuid.UUID(int=201), uuid.UUID(int=202))
EXTRA = uuid.UUID(int=203)


def test_choices_never_shift_the_order_stream():
    a = SimAssumptions(days=28, seed=5, promo_item_rank=None)
    plain = generate_orders(ITEMS, START, a, TZ)
    with_choices = [
        replace(i, required=((1, SPICE),), extras=((1, (EXTRA,)),)) if i.id == ITEMS[0].id else i
        for i in ITEMS
    ]
    drawn = generate_orders(with_choices, START, a, TZ)
    assert _flat(plain) == _flat(drawn)
    picks = [ids for o in drawn for ids in o.choices.values()]
    assert picks and all(any(s in ids for s in SPICE) for ids in picks)
    assert any(EXTRA in ids for ids in picks)


@pytest.mark.asyncio
@pytest.mark.timeout(240)
async def test_dish_with_a_sold_out_required_group_is_never_simulated(db_session: AsyncSession):
    restaurant = await _seeded(db_session)
    karahi = uuid.uuid5(SEED_ITEM_NAMESPACE, "angeethi-house:chicken_karahi")
    required = select(MenuChoiceGroup.id).where(
        MenuChoiceGroup.menu_item_id == karahi, MenuChoiceGroup.min_select > 0
    )
    for c in await db_session.scalars(select(MenuChoice).where(MenuChoice.group_id.in_(required))):
        c.available = False
    await db_session.flush()
    a = SimAssumptions.from_profile(restaurant.onboarding["simulation"])
    assert (await persist_simulation(db_session, restaurant, a))["orders_created"] > 0
    sold = await db_session.scalar(
        select(func.count()).select_from(OrderItem).where(OrderItem.menu_item_id == karahi)
    )
    assert sold == 0


def test_required_groups_draw_their_minimum_and_extras_respect_their_maximum():
    sides = tuple(uuid.UUID(int=210 + n) for n in range(4))
    adds = tuple(uuid.UUID(int=220 + n) for n in range(6))
    a = SimAssumptions(days=28, seed=5, promo_item_rank=None)
    items = [
        replace(i, required=((2, sides),), extras=((1, adds),)) if i.id == ITEMS[0].id else i
        for i in ITEMS
    ]
    picks = [ids for o in generate_orders(items, START, a, TZ) for ids in o.choices.values()]
    assert picks
    for ids in picks:
        assert len({s for s in ids if s in sides}) == sum(s in sides for s in ids) == 2
        assert sum(e in adds for e in ids) <= 1
