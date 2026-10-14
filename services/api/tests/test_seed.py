"""Tests for database seed idempotency, row counts, and QR token stability."""

import pytest
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.restaurant import Restaurant


@pytest.mark.asyncio
async def test_seed_data_idempotent_and_stable_tokens(db_session: AsyncSession):
    """Seed runs twice inside db_session: asserts row counts and stable table tokens."""
    data = load_seed_data("data/seed/trattoria_da_mario.json")
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
    assert len(tokens_run_1) == 6
    assert all(bool(token) for token in tokens_run_1.values())

    # --- Run 2 (idempotency verification) ---
    await seed_data(data, db_session, rotate_qr=False)

    # 1. Assert exactly 1 restaurant with matching slug
    res_rest = await db_session.execute(
        select(func.count()).select_from(Restaurant).where(Restaurant.slug == slug)
    )
    assert res_rest.scalar() == 1

    # 2. Assert exactly 6 dining tables for this restaurant
    res_tables = await db_session.execute(
        select(func.count())
        .select_from(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
    )
    assert res_tables.scalar() == 6

    # 3. Assert exactly 25 menu items for this restaurant
    res_items = await db_session.execute(
        select(func.count()).select_from(MenuItem).where(MenuItem.restaurant_id == restaurant.id)
    )
    assert res_items.scalar() == 25

    # 4. Assert exactly 50 menu translations (IT + EN for each item) for this restaurant
    res_trans = await db_session.execute(
        select(func.count())
        .select_from(MenuTranslation)
        .join(MenuItem, MenuTranslation.menu_item_id == MenuItem.id)
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    assert res_trans.scalar() == 50

    # 5. Assert exactly 1 unverified item (allergen_verified is False) for this restaurant
    res_unverified = await db_session.execute(
        select(func.count())
        .select_from(MenuItem)
        .where(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.allergen_verified.is_(False),
        )
    )
    assert res_unverified.scalar() == 1

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
    data = load_seed_data("data/seed/trattoria_da_mario.json")
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

    assert len(tokens_2) == 6
    # Each token should have changed
    for label, token in tokens_1.items():
        assert tokens_2[label] != token
