"""Tests verifying that all database CHECK constraints and FK RESTRICT rules reject invalid data."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_test_restaurant(db: AsyncSession, slug: str | None = None) -> str:
    rest_id = str(uuid.uuid4())
    rest_slug = slug or f"test-rest-{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO restaurant (id, name, slug, languages, default_language)
            VALUES (:id, 'Test Trattoria', :slug, ARRAY['en', 'it'], 'it')
            """
        ),
        {"id": rest_id, "slug": rest_slug},
    )
    return rest_id


async def _create_test_menu_item(db: AsyncSession, restaurant_id: str) -> str:
    item_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO menu_item (
                id, restaurant_id, category, price, unit_cost,
                ingredients, allergens, allergen_verified,
                is_vegetarian, is_vegan, is_gluten_free, dietary_verified
            )
            VALUES (
                :id, :restaurant_id, 'Primi', 12.00, 3.00,
                ARRAY['pasta'], ARRAY['gluten'], true,
                true, false, false, true
            )
            """
        ),
        {"id": item_id, "restaurant_id": restaurant_id},
    )
    return item_id


async def _create_test_session(db: AsyncSession, restaurant_id: str) -> str:
    session_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO guest_session (
                id, restaurant_id, language, expires_at
            )
            VALUES (
                :id, :restaurant_id, 'it', now() + interval '2 hours'
            )
            """
        ),
        {"id": session_id, "restaurant_id": restaurant_id},
    )
    return session_id


async def _create_test_order(db: AsyncSession, restaurant_id: str, session_id: str) -> str:
    order_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO orders (
                id, guest_session_id, restaurant_id, status, total,
                idempotency_key, payload_hash
            )
            VALUES (
                :id, :session_id, :restaurant_id, 'placed', 12.00,
                'idem-key-1', 'dummy-hash'
            )
            """
        ),
        {"id": order_id, "session_id": session_id, "restaurant_id": restaurant_id},
    )
    return order_id


async def assert_violates(
    db_session: AsyncSession,
    sql: str,
    params: dict[str, Any] | None,
    expected_constraint: str,
) -> None:
    """Assert that executing sql with params inside a savepoint raises IntegrityError or DBAPIError.

    Inverting the nesting (with pytest.raises outside begin_nested) ensures the savepoint's
    rollback is triggered and cleanly released, preventing InFailedSQLTransactionError.
    """
    with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(text(sql), params or {})
    err_msg = str(exc_info.value).lower()
    assert expected_constraint.lower() in err_msg, (
        f"Expected {expected_constraint!r} not found in error message: {exc_info.value!r}"
    )


@pytest.mark.asyncio
async def test_restaurant_default_language_not_in_languages(db_session: AsyncSession):
    """CHECK constraint: default_language = ANY(languages) IS TRUE."""
    sql = """
    INSERT INTO restaurant (name, slug, languages, default_language)
    VALUES ('Bad Lang', 'bad-lang', ARRAY['it'], 'fr')
    """
    await assert_violates(db_session, sql, None, "chk_restaurant_default_language")


@pytest.mark.asyncio
async def test_menu_item_bad_allergen_code(db_session: AsyncSession):
    """CHECK constraint: allergens must strictly belong to the EU-14 set."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO menu_item (
        restaurant_id, category, price, unit_cost, allergens
    )
    VALUES (
        :restaurant_id, 'Primi', 10.00, 2.00, ARRAY['invalid_allergen']::text[]
    )
    """
    await assert_violates(db_session, sql, {"restaurant_id": rest_id}, "chk_menu_item_allergens")


@pytest.mark.asyncio
async def test_menu_item_vegan_with_milk_rejected(db_session: AsyncSession):
    """CHECK constraint: vegan item cannot declare animal-product allergens like milk."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO menu_item (
        restaurant_id, category, price, unit_cost,
        is_vegan, is_vegetarian, allergens
    )
    VALUES (
        :restaurant_id, 'Dolci', 5.00, 1.00,
        true, true, ARRAY['milk']::text[]
    )
    """
    await assert_violates(
        db_session, sql, {"restaurant_id": rest_id}, "chk_menu_item_vegan_contradiction"
    )


@pytest.mark.asyncio
async def test_menu_item_gluten_free_with_gluten_rejected(db_session: AsyncSession):
    """CHECK constraint: is_gluten_free contradicts gluten allergen."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO menu_item (
        restaurant_id, category, price, unit_cost,
        is_gluten_free, allergens
    )
    VALUES (
        :restaurant_id, 'Primi', 8.00, 1.50,
        true, ARRAY['gluten']::text[]
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"restaurant_id": rest_id},
        "chk_menu_item_gluten_free_contradiction",
    )


@pytest.mark.asyncio
async def test_order_item_quantity_zero_rejected(db_session: AsyncSession):
    """CHECK constraint: quantity must be at least 1."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)
    session_id = await _create_test_session(db_session, rest_id)
    order_id = await _create_test_order(db_session, rest_id, session_id)

    sql = """
    INSERT INTO order_item (
        order_id, menu_item_id, quantity, unit_price, unit_cost,
        item_name, kitchen_name, allergen_verified, allergen_status
    )
    VALUES (
        :order_id, :menu_item_id, 0, 12.00, 3.00,
        'Pasta', 'Pasta', true, 'no_declared_match'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"order_id": order_id, "menu_item_id": item_id},
        "chk_order_item_quantity",
    )


@pytest.mark.asyncio
async def test_order_item_quantity_twenty_one_rejected(db_session: AsyncSession):
    """CHECK constraint: quantity cannot exceed 20."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)
    session_id = await _create_test_session(db_session, rest_id)
    order_id = await _create_test_order(db_session, rest_id, session_id)

    sql = """
    INSERT INTO order_item (
        order_id, menu_item_id, quantity, unit_price, unit_cost,
        item_name, kitchen_name, allergen_verified, allergen_status
    )
    VALUES (
        :order_id, :menu_item_id, 21, 12.00, 3.00,
        'Pasta', 'Pasta', true, 'no_declared_match'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"order_id": order_id, "menu_item_id": item_id},
        "chk_order_item_quantity",
    )


@pytest.mark.asyncio
async def test_orders_bad_status(db_session: AsyncSession):
    """CHECK constraint: status must be in ('placed', 'bumped', 'cancelled')."""
    rest_id = await _create_test_restaurant(db_session)
    session_id = await _create_test_session(db_session, rest_id)

    sql = """
    INSERT INTO orders (
        guest_session_id, restaurant_id, status, total,
        idempotency_key, payload_hash
    )
    VALUES (
        :session_id, :restaurant_id, 'delivering', 10.00,
        'idem-key-2', 'hash-123'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"session_id": session_id, "restaurant_id": rest_id},
        "chk_orders_status",
    )


@pytest.mark.asyncio
async def test_order_item_bad_allergen_status(db_session: AsyncSession):
    """CHECK constraint: allergen_status IN ('contains', 'unverified', 'no_declared_match')."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)
    session_id = await _create_test_session(db_session, rest_id)
    order_id = await _create_test_order(db_session, rest_id, session_id)

    sql = """
    INSERT INTO order_item (
        order_id, menu_item_id, quantity, unit_price, unit_cost,
        item_name, kitchen_name, allergen_verified, allergen_status
    )
    VALUES (
        :order_id, :menu_item_id, 1, 12.00, 3.00,
        'Pasta', 'Pasta', true, 'safe'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"order_id": order_id, "menu_item_id": item_id},
        "chk_order_item_allergen_status",
    )


@pytest.mark.asyncio
async def test_guest_session_bad_dietary_preference_rejected(db_session: AsyncSession):
    """CHECK constraint: dietary_preferences on guest_session."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO guest_session (
        restaurant_id, language, dietary_preferences, expires_at
    )
    VALUES (
        :restaurant_id, 'en', ARRAY['paleo']::text[], now() + interval '1 hour'
    )
    """
    await assert_violates(db_session, sql, {"restaurant_id": rest_id}, "chk_guest_session_dietary")


@pytest.mark.asyncio
async def test_orders_bad_dietary_preference_rejected(db_session: AsyncSession):
    """CHECK constraint: dietary_preferences on orders."""
    rest_id = await _create_test_restaurant(db_session)
    session_id = await _create_test_session(db_session, rest_id)
    sql = """
    INSERT INTO orders (
        guest_session_id, restaurant_id, status, total,
        idempotency_key, payload_hash, dietary_preferences
    )
    VALUES (
        :session_id, :restaurant_id, 'placed', 15.00,
        'idem-key-diet', 'hash-xyz', ARRAY['keto']::text[]
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"session_id": session_id, "restaurant_id": rest_id},
        "chk_orders_dietary",
    )


@pytest.mark.asyncio
async def test_order_item_cannot_reference_hard_deleted_menu_item(db_session: AsyncSession):
    """Foreign key ON DELETE RESTRICT: order_item prevents hard delete of menu_item."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)
    session_id = await _create_test_session(db_session, rest_id)
    order_id = await _create_test_order(db_session, rest_id, session_id)

    # Insert order item referencing menu_item
    await db_session.execute(
        text(
            """
            INSERT INTO order_item (
                order_id, menu_item_id, quantity, unit_price, unit_cost,
                item_name, kitchen_name, allergen_verified, allergen_status
            )
            VALUES (
                :order_id, :menu_item_id, 2, 12.00, 3.00,
                'Pasta', 'Pasta', true, 'no_declared_match'
            )
            """
        ),
        {"order_id": order_id, "menu_item_id": item_id},
    )

    sql = "DELETE FROM menu_item WHERE id = :item_id"
    await assert_violates(db_session, sql, {"item_id": item_id}, "fk_order_item_menu_item_id")


@pytest.mark.asyncio
async def test_menu_item_vegetarian_with_fish_rejected(db_session: AsyncSession):
    """CHECK constraint: vegetarian item cannot declare fish allergen."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO menu_item (
        restaurant_id, category, price, unit_cost,
        is_vegetarian, allergens
    )
    VALUES (
        :restaurant_id, 'Secondi', 14.00, 4.00,
        true, ARRAY['fish']::text[]
    )
    """
    await assert_violates(
        db_session, sql, {"restaurant_id": rest_id}, "chk_menu_item_vegetarian_contradiction"
    )


@pytest.mark.asyncio
async def test_menu_item_vegan_without_vegetarian_rejected(db_session: AsyncSession):
    """CHECK constraint: vegan item must also be marked vegetarian."""
    rest_id = await _create_test_restaurant(db_session)
    sql = """
    INSERT INTO menu_item (
        restaurant_id, category, price, unit_cost,
        is_vegan, is_vegetarian
    )
    VALUES (
        :restaurant_id, 'Secondi', 14.00, 4.00,
        true, false
    )
    """
    await assert_violates(
        db_session, sql, {"restaurant_id": rest_id}, "chk_menu_item_vegan_implies_vegetarian"
    )


@pytest.mark.asyncio
async def test_orders_duplicate_session_idempotency_key_rejected(db_session: AsyncSession):
    """UNIQUE constraint: duplicate (guest_session_id, idempotency_key) must be rejected."""
    rest_id = await _create_test_restaurant(db_session)
    session_id = await _create_test_session(db_session, rest_id)
    idem_key = "unique-key-1"

    # First insert succeeds
    await db_session.execute(
        text(
            """
            INSERT INTO orders (
                guest_session_id, restaurant_id, status, total,
                idempotency_key, payload_hash
            )
            VALUES (
                :session_id, :restaurant_id, 'placed', 10.00,
                :idem_key, 'hash1'
            )
            """
        ),
        {"session_id": session_id, "restaurant_id": rest_id, "idem_key": idem_key},
    )

    # Second insert with same session and idempotency key must fail
    sql = """
    INSERT INTO orders (
        guest_session_id, restaurant_id, status, total,
        idempotency_key, payload_hash
    )
    VALUES (
        :session_id, :restaurant_id, 'placed', 10.00,
        :idem_key, 'hash2'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"session_id": session_id, "restaurant_id": rest_id, "idem_key": idem_key},
        "orders_guest_idempotency_key",
    )


@pytest.mark.asyncio
async def test_orders_same_idempotency_key_different_sessions_allowed(db_session: AsyncSession):
    """The same idempotency key in two different guest sessions is allowed."""
    rest_id = await _create_test_restaurant(db_session)
    session_1 = await _create_test_session(db_session, rest_id)
    session_2 = await _create_test_session(db_session, rest_id)
    shared_key = "shared-client-uuid-1234"

    # Insert into session 1
    await db_session.execute(
        text(
            """
            INSERT INTO orders (
                guest_session_id, restaurant_id, status, total,
                idempotency_key, payload_hash
            )
            VALUES (
                :session_id, :restaurant_id, 'placed', 15.00,
                :idem_key, 'hash1'
            )
            """
        ),
        {"session_id": session_1, "restaurant_id": rest_id, "idem_key": shared_key},
    )

    # Insert into session 2 with identical idempotency key must succeed
    await db_session.execute(
        text(
            """
            INSERT INTO orders (
                guest_session_id, restaurant_id, status, total,
                idempotency_key, payload_hash
            )
            VALUES (
                :session_id, :restaurant_id, 'placed', 20.00,
                :idem_key, 'hash2'
            )
            """
        ),
        {"session_id": session_2, "restaurant_id": rest_id, "idem_key": shared_key},
    )

    # Verify both orders exist
    res = await db_session.execute(
        text("SELECT count(*) FROM orders WHERE idempotency_key = :idem_key"),
        {"idem_key": shared_key},
    )
    assert res.scalar() == 2


@pytest.mark.asyncio
async def test_menu_translation_duplicate_item_language_rejected(db_session: AsyncSession):
    """UNIQUE constraint: duplicate (menu_item_id, language) must be rejected."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)

    # First translation for 'it'
    await db_session.execute(
        text(
            """
            INSERT INTO menu_translation (menu_item_id, language, name)
            VALUES (:item_id, 'it', 'Primo Nome')
            """
        ),
        {"item_id": item_id},
    )

    # Second translation for 'it' on same item must fail
    sql = """
    INSERT INTO menu_translation (menu_item_id, language, name)
    VALUES (:item_id, 'it', 'Secondo Nome')
    """
    await assert_violates(db_session, sql, {"item_id": item_id}, "menu_translation_item_lang_key")


@pytest.mark.asyncio
async def test_orders_negative_total_rejected(db_session: AsyncSession):
    """CHECK constraint: orders.total >= 0."""
    rest_id = await _create_test_restaurant(db_session)
    session_id = await _create_test_session(db_session, rest_id)

    sql = """
    INSERT INTO orders (
        guest_session_id, restaurant_id, status, total,
        idempotency_key, payload_hash
    )
    VALUES (
        :session_id, :restaurant_id, 'placed', -0.01,
        'neg-total-key', 'hash'
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"session_id": session_id, "restaurant_id": rest_id},
        "chk_orders_total",
    )


@pytest.mark.asyncio
async def test_order_item_notes_over_500_chars_rejected(db_session: AsyncSession):
    """CHECK constraint: length(notes) <= 500 on order_item."""
    rest_id = await _create_test_restaurant(db_session)
    item_id = await _create_test_menu_item(db_session, rest_id)
    session_id = await _create_test_session(db_session, rest_id)
    order_id = await _create_test_order(db_session, rest_id, session_id)

    # 500 characters must succeed
    notes_500 = "x" * 500
    await db_session.execute(
        text(
            """
            INSERT INTO order_item (
                order_id, menu_item_id, quantity, unit_price, unit_cost,
                item_name, kitchen_name, allergen_verified, allergen_status, notes
            )
            VALUES (
                :order_id, :menu_item_id, 1, 10.00, 2.00,
                'Pasta', 'Pasta', true, 'no_declared_match', :notes
            )
            """
        ),
        {"order_id": order_id, "menu_item_id": item_id, "notes": notes_500},
    )

    # 501 characters must be rejected
    notes_501 = "y" * 501
    sql = """
    INSERT INTO order_item (
        order_id, menu_item_id, quantity, unit_price, unit_cost,
        item_name, kitchen_name, allergen_verified, allergen_status, notes
    )
    VALUES (
        :order_id, :menu_item_id, 1, 10.00, 2.00,
        'Pasta 2', 'Pasta 2', true, 'no_declared_match', :notes
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"order_id": order_id, "menu_item_id": item_id, "notes": notes_501},
        "chk_order_item_notes_length",
    )


@pytest.mark.asyncio
async def test_orders_bumped_without_bumped_at_rejected(db_session: AsyncSession):
    """CHECK constraint: bumped orders must have bumped_at timestamp."""
    rest_id = await _create_test_restaurant(db_session)
    session_id = await _create_test_session(db_session, rest_id)

    sql = """
    INSERT INTO orders (
        guest_session_id, restaurant_id, status, total,
        idempotency_key, payload_hash, bumped_at
    )
    VALUES (
        :session_id, :restaurant_id, 'bumped', 12.00,
        'bump-no-ts', 'hash', NULL
    )
    """
    await assert_violates(
        db_session,
        sql,
        {"session_id": session_id, "restaurant_id": rest_id},
        "chk_orders_bumped_at_required",
    )
