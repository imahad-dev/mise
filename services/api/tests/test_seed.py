"""Tests for database seed idempotency, row counts, and QR token stability."""

import uuid
from datetime import UTC, date, datetime

import pytest
import scripts.seed as seed_module
from scripts.seed import (
    SEED_ITEM_NAMESPACE,
    find_seed_for_slug,
    load_seed_data,
    seed_data,
    seed_demo_users,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.restaurant import Restaurant
from src.models.user import Membership, User
from src.services.tax import TaxRateError

ANGEETHI = "data/seed/angeethi_house.json"
KEHWA = "data/seed/kehwa_and_crumb.json"
HALF_KG = "\u00bd kg"


@pytest.mark.asyncio
async def test_seed_data_idempotent_and_stable_tokens(db_session: AsyncSession):
    """Seed runs twice inside db_session: asserts row counts and stable table tokens."""
    data = load_seed_data(ANGEETHI)
    slug = data["restaurant"]["slug"]

    # --- Run 1 ---
    await seed_data(data, db_session, rotate_qr=False)

    res_rest_record = await db_session.execute(select(Restaurant).where(Restaurant.slug == slug))
    restaurant = res_rest_record.scalar_one()

    res_tables_1 = await db_session.execute(
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    tables_1 = list(res_tables_1.scalars().all())
    tokens_run_1 = {t.label: t.qr_token for t in tables_1}

    # Verify initial table tokens are valid non-empty strings
    assert len(tokens_run_1) == 13
    assert all(bool(token) for token in tokens_run_1.values())

    # --- Run 2 (idempotency verification) ---
    await seed_data(data, db_session, rotate_qr=False)

    # 1. Assert exactly 1 restaurant with matching slug
    res_rest = await db_session.execute(
        select(func.count()).select_from(Restaurant).where(Restaurant.slug == slug)
    )
    assert res_rest.scalar() == 1

    # 2. Assert exactly 13 dining tables (T1-T8, F1-F4, Takeaway) for this restaurant
    res_tables = await db_session.execute(
        select(func.count())
        .select_from(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
    )
    assert res_tables.scalar() == 13

    # 3. Assert exactly 27 menu items for this restaurant
    res_items = await db_session.execute(
        select(func.count()).select_from(MenuItem).where(MenuItem.restaurant_id == restaurant.id)
    )
    assert res_items.scalar() == 27

    # 4. Assert exactly 27 menu translations (EN for each item) for this restaurant
    res_trans = await db_session.execute(
        select(func.count())
        .select_from(MenuTranslation)
        .join(MenuItem, MenuTranslation.menu_item_id == MenuItem.id)
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    assert res_trans.scalar() == 27

    # 5. Assert every item is unverified (allergen_verified is False) for this restaurant
    res_unverified = await db_session.execute(
        select(func.count())
        .select_from(MenuItem)
        .where(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.allergen_verified.is_(False),
        )
    )
    assert res_unverified.scalar() == 27

    # 5b. Exactly one item is the pay-it-forward chai, flagged by its seed key
    flagged = (
        (
            await db_session.execute(
                select(MenuItem.id).where(
                    MenuItem.restaurant_id == restaurant.id, MenuItem.is_pay_forward
                )
            )
        )
        .scalars()
        .all()
    )
    assert flagged == [uuid.uuid5(SEED_ITEM_NAMESPACE, f"{slug}:pay_forward_chai")]

    # 6. Assert unchanged table tokens after second run
    res_tables_2 = await db_session.execute(
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    tables_2 = list(res_tables_2.scalars().all())
    tokens_run_2 = {t.label: t.qr_token for t in tables_2}

    assert tokens_run_1 == tokens_run_2


@pytest.mark.asyncio
async def test_seed_data_rotate_qr(db_session: AsyncSession):
    """rotate_qr=True generates new tokens for existing tables."""
    data = load_seed_data(ANGEETHI)
    slug = data["restaurant"]["slug"]

    await seed_data(data, db_session, rotate_qr=False)
    res_rest = await db_session.execute(select(Restaurant).where(Restaurant.slug == slug))
    restaurant = res_rest.scalar_one()

    res_1 = await db_session.execute(
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    tokens_1 = {t.label: t.qr_token for t in res_1.scalars().all()}

    # Re-seed with rotate_qr=True
    await seed_data(data, db_session, rotate_qr=True)
    res_2 = await db_session.execute(
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    tokens_2 = {t.label: t.qr_token for t in res_2.scalars().all()}

    assert len(tokens_2) == 13
    # Each token should have changed
    for label, token in tokens_1.items():
        assert tokens_2[label] != token


async def _counts(db: AsyncSession) -> tuple[int, int, int]:
    return (
        (await db.execute(select(func.count()).select_from(Restaurant))).scalar_one(),
        (await db.execute(select(func.count()).select_from(MenuItem))).scalar_one(),
        (await db.execute(select(func.count()).select_from(MenuItemOption))).scalar_one(),
    )


@pytest.mark.asyncio
async def test_both_venues_seed_idempotently_with_stable_ids(db_session: AsyncSession):
    angeethi, kehwa = load_seed_data(ANGEETHI), load_seed_data(KEHWA)
    await seed_data(angeethi, db_session)
    await seed_data(kehwa, db_session)
    first = await _counts(db_session)
    await seed_data(angeethi, db_session)
    await seed_data(kehwa, db_session)
    assert await _counts(db_session) == first
    assert first[0] == 2
    labels = dict(
        (await db_session.execute(select(Restaurant.slug, Restaurant.service_extra_label))).all()
    )
    assert labels["angeethi-house"] == "More naan / roti"
    assert labels["kehwa-and-crumb"] == "More napkins / cutlery"
    details = dict(
        (await db_session.execute(select(Restaurant.slug, Restaurant.payment_details))).all()
    )
    assert details["angeethi-house"]["sample"] is True
    assert details["kehwa-and-crumb"]["raast_id"] == "0000 SAMPLE"
    prefixes = dict(
        (await db_session.execute(select(Restaurant.slug, Restaurant.pickup_prefix))).all()
    )
    assert prefixes == {"angeethi-house": "P", "kehwa-and-crumb": "K"}
    counters = (
        await db_session.execute(
            select(Restaurant.slug, DiningTable.label)
            .join(DiningTable, DiningTable.restaurant_id == Restaurant.id)
            .where(DiningTable.kind == "counter")
        )
    ).all()
    assert sorted(counters) == [("angeethi-house", "Takeaway"), ("kehwa-and-crumb", "Counter")]

    karahi_id = uuid.uuid5(SEED_ITEM_NAMESPACE, "angeethi-house:chicken_karahi")
    karahi = (
        await db_session.execute(
            select(MenuItem).options(selectinload(MenuItem.options)).where(MenuItem.id == karahi_id)
        )
    ).scalar_one()
    assert [o.label for o in karahi.options] == [HALF_KG, "1 kg"]
    assert karahi.price == 1100
    assert karahi.options[1].id == uuid.uuid5(
        SEED_ITEM_NAMESPACE, "angeethi-house:chicken_karahi:1 kg"
    )


@pytest.mark.asyncio
async def test_item_price_follows_cheapest_option(db_session: AsyncSession):
    data = load_seed_data(KEHWA)
    for item in data["items"]:
        if item["key"] == "cappuccino":
            item["price"], item["unit_cost"] = 1, 1  # a stale top-level price must not win
    await seed_data(data, db_session)
    cappuccino = (
        await db_session.execute(
            select(MenuItem).where(
                MenuItem.id == uuid.uuid5(SEED_ITEM_NAMESPACE, "kehwa-and-crumb:cappuccino")
            )
        )
    ).scalar_one()
    assert (cappuccino.price, cappuccino.unit_cost) == (650, 190)


@pytest.mark.asyncio
async def test_reseed_deletes_options_no_longer_in_the_file(db_session: AsyncSession):
    data = load_seed_data(ANGEETHI)
    await seed_data(data, db_session)
    for item in data["items"]:
        if item["key"] == "chicken_karahi":
            item["options"] = [o for o in item["options"] if o["label"] == HALF_KG]
    await seed_data(data, db_session)
    labels = (
        (
            await db_session.execute(
                select(MenuItemOption.label).where(
                    MenuItemOption.menu_item_id
                    == uuid.uuid5(SEED_ITEM_NAMESPACE, "angeethi-house:chicken_karahi")
                )
            )
        )
        .scalars()
        .all()
    )
    assert list(labels) == [HALF_KG]


@pytest.mark.asyncio
async def test_seed_demo_users_owner_in_both_staff_in_one(db_session: AsyncSession):
    await seed_data(load_seed_data(ANGEETHI), db_session)
    await seed_data(load_seed_data(KEHWA), db_session)
    users = load_seed_data("data/seed/demo_users.json")
    await seed_demo_users(users, db_session)
    await seed_demo_users(users, db_session)  # second run changes nothing

    rows = (
        await db_session.execute(
            select(User.email, Restaurant.slug, Membership.role)
            .join(Membership, Membership.user_id == User.id)
            .join(Restaurant, Restaurant.id == Membership.restaurant_id)
            .order_by(User.email, Restaurant.slug)
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("demo-owner@mise.demo", "angeethi-house", "owner"),
        ("demo-owner@mise.demo", "kehwa-and-crumb", "owner"),
        ("demo-staff+angeethi-house@mise.demo", "angeethi-house", "staff"),
        ("demo-staff+kehwa-and-crumb@mise.demo", "kehwa-and-crumb", "staff"),
    ]
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 3


def test_find_seed_for_slug_skips_demo_users_and_malformed_files(tmp_path, monkeypatch):
    seed_dir = tmp_path / "data" / "seed"
    seed_dir.mkdir(parents=True)
    (seed_dir / "a_broken.json").write_text("{not json", encoding="utf-8")
    (seed_dir / "b_wrong_shape.json").write_text('{"restaurant": "oops"}', encoding="utf-8")
    (seed_dir / "c_list.json").write_text("[1, 2]", encoding="utf-8")
    (seed_dir / "d_demo_users.json").write_text('{"owner": {}, "staff": []}', encoding="utf-8")
    (seed_dir / "e_venue.json").write_text('{"restaurant": {"slug": "x"}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    warnings: list[str] = []
    monkeypatch.setattr(seed_module.logger, "warning", lambda msg, *a: warnings.append(msg % a))
    assert find_seed_for_slug("x") == {"restaurant": {"slug": "x"}}
    assert find_seed_for_slug("nope") is None
    assert any("a_broken.json" in w for w in warnings)
    assert any("b_wrong_shape.json" in w for w in warnings)
    assert not any("d_demo_users.json" in w for w in warnings)


@pytest.mark.asyncio
async def test_reseed_moves_the_pay_forward_flag_back_to_the_seed_chai(db_session: AsyncSession):
    data = load_seed_data(ANGEETHI)
    await seed_data(data, db_session)
    rid = await db_session.scalar(
        select(Restaurant.id).where(Restaurant.slug == data["restaurant"]["slug"])
    )
    chai = uuid.uuid5(SEED_ITEM_NAMESPACE, f"{data['restaurant']['slug']}:pay_forward_chai")
    # The owner moves the flag to an item of their own (one flagged item per venue).
    await db_session.execute(
        update(MenuItem).where(MenuItem.id == chai).values(is_pay_forward=False)
    )
    own = MenuItem(
        restaurant_id=rid, category="Drinks", price=100, unit_cost=10, is_pay_forward=True
    )
    db_session.add(own)
    await db_session.flush()
    await seed_data(data, db_session)
    flagged = (
        await db_session.scalars(
            select(MenuItem.id).where(MenuItem.restaurant_id == rid, MenuItem.is_pay_forward)
        )
    ).all()
    assert list(flagged) == [chai]


@pytest.mark.asyncio
async def test_reseed_keeps_the_pickup_prefix_while_counter_orders_are_open(
    db_session: AsyncSession,
):
    data = load_seed_data(ANGEETHI)
    await seed_data(data, db_session)
    restaurant = await db_session.scalar(
        select(Restaurant).where(Restaurant.slug == data["restaurant"]["slug"])
    )
    restaurant.pickup_prefix = "Q"
    counter = await db_session.scalar(
        select(DiningTable.id).where(
            DiningTable.restaurant_id == restaurant.id, DiningTable.kind == "counter"
        )
    )
    open_bill = Bill(
        restaurant_id=restaurant.id,
        table_id=counter,
        bill_no=1,
        pickup_day=date(2026, 10, 28),
        pickup_no=1,
    )
    db_session.add(open_bill)
    await db_session.flush()
    await seed_data(data, db_session)
    assert restaurant.pickup_prefix == "Q"  # guests already hold Q-numbers

    open_bill.status, open_bill.cancelled_at = "cancelled", datetime.now(UTC)
    await db_session.flush()
    await seed_data(data, db_session)
    assert restaurant.pickup_prefix == data["restaurant"]["pickup_prefix"]


@pytest.mark.asyncio
async def test_seed_refuses_a_jurisdiction_in_another_currency(db_session: AsyncSession):
    data = load_seed_data(ANGEETHI)
    data["restaurant"]["tax_jurisdiction"] = "GB"  # the file bills in PKR
    with pytest.raises(TaxRateError, match="currency"):
        await seed_data(data, db_session)
