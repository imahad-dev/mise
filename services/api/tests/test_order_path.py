"""Tests for Checkpoint B:
Authentication, Guest Sessions, Orders Path, Kitchen, and Owner Management.
"""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, GUEST_COOKIE_NAME, sign_value
from src.config import settings
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.redis_client import redis_client


def assert_no_unit_cost(data: Any) -> None:
    """Recursively assert that 'unit_cost' is not present in any dictionary."""
    if isinstance(data, dict):
        assert "unit_cost" not in data, f"unit_cost leaked in response: {data}"
        for v in data.values():
            assert_no_unit_cost(v)
    elif isinstance(data, list):
        for item in data:
            assert_no_unit_cost(item)


@pytest.fixture
async def seeded_restaurant(db_session: AsyncSession) -> Restaurant:
    """Seed test database with Mario trattoria and return Restaurant."""
    data = load_seed_data("data/seed/trattoria_da_mario.json")
    await seed_data(data, db_session, rotate_qr=False)
    res = await db_session.execute(
        select(Restaurant).where(Restaurant.slug == "trattoria-da-mario")
    )
    return res.scalar_one()


@pytest.mark.asyncio
async def test_auth_login_and_cookie_flags(client: AsyncClient):
    """Test owner and staff login, cookie attributes (httponly, samesite), and me/logout."""
    # 1. Staff login
    resp_staff = await client.post(
        "/api/auth/login",
        json={"role": "staff", "secret": settings.staff_pin},
    )
    assert resp_staff.status_code == 200
    assert resp_staff.json() == {"status": "ok", "role": "staff"}

    # Verify cookie attributes
    set_cookie = resp_staff.headers.get("set-cookie", "")
    assert AUTH_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    # 2. Get me with staff cookie
    client.cookies.set(AUTH_COOKIE_NAME, resp_staff.cookies[AUTH_COOKIE_NAME])
    resp_me = await client.get("/api/auth/me")
    assert resp_me.status_code == 200
    assert resp_me.json() == {"role": "staff"}

    # 3. Logout
    resp_logout = await client.post("/api/auth/logout")
    assert resp_logout.status_code == 200

    # 4. Owner login
    resp_owner = await client.post(
        "/api/auth/login",
        json={"role": "owner", "secret": settings.owner_api_key},
    )
    assert resp_owner.status_code == 200
    assert resp_owner.json() == {"status": "ok", "role": "owner"}


@pytest.mark.asyncio
async def test_auth_login_rate_limiting(client: AsyncClient):
    """5 failed login attempts in Redis produces 429 on the 5th attempt."""
    test_ip = "127.0.0.1"
    rl_key = f"rate_limit:login:{test_ip}"
    await redis_client.delete(rl_key)

    try:
        # 4 failed attempts -> 401
        for _ in range(4):
            r = await client.post(
                "/api/auth/login",
                json={"role": "staff", "secret": "wrong_pin"},
            )
            assert r.status_code == 401

        # 5th failed attempt reaches limit -> 429
        r5 = await client.post(
            "/api/auth/login",
            json={"role": "staff", "secret": "wrong_pin"},
        )
        assert r5.status_code == 429
    finally:
        await redis_client.delete(rl_key)


@pytest.mark.asyncio
async def test_guest_session_flow_and_no_unit_cost(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Create guest session, fetch menu and session, and verify unit_cost is NEVER exposed."""
    # Get a valid table QR token
    res_t = await db_session.execute(
        select(DiningTable).where(DiningTable.restaurant_id == seeded_restaurant.id)
    )
    table = res_t.scalars().first()
    assert table is not None

    # 1. Create session
    resp_sess = await client.post(
        "/api/guest/sessions",
        json={
            "qr_token": table.qr_token,
            "language": "en",
            "dietary_preferences": ["vegetarian"],
            "allergens_to_avoid": ["gluten"],
        },
    )
    assert resp_sess.status_code == 201
    sess_data = resp_sess.json()
    assert sess_data["language"] == "en"
    assert_no_unit_cost(sess_data)

    # Check cookie
    assert GUEST_COOKIE_NAME in resp_sess.headers.get("set-cookie", "")

    # 2. GET /api/guest/session
    client.cookies.set(GUEST_COOKIE_NAME, resp_sess.cookies[GUEST_COOKIE_NAME])
    resp_get_sess = await client.get("/api/guest/session")
    assert resp_get_sess.status_code == 200
    assert_no_unit_cost(resp_get_sess.json())

    # 3. PATCH /api/guest/session
    resp_patch_sess = await client.patch(
        "/api/guest/session",
        json={"language": "it", "dietary_preferences": ["vegan"]},
    )
    assert resp_patch_sess.status_code == 200
    assert resp_patch_sess.json()["language"] == "it"
    assert_no_unit_cost(resp_patch_sess.json())

    # 4. GET /api/guest/menu
    resp_menu = await client.get("/api/guest/menu")
    assert resp_menu.status_code == 200
    menu_data = resp_menu.json()
    assert len(menu_data["items"]) == 25
    assert_no_unit_cost(menu_data)


@pytest.mark.asyncio
async def test_guest_menu_with_allergens_to_avoid(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Loading guest menu with non-empty allergens_to_avoid.

    Computes allergen status and matched_allergens.
    """
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        table_id=None,
        language="it",
        allergens_to_avoid=["gluten", "milk"],
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()

    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))
    resp = await client.get("/api/guest/menu")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data

    contains_items = [item for item in data["items"] if item["allergen_status"] == "contains"]
    assert len(contains_items) > 0
    for item in contains_items:
        assert len(item["matched_allergens"]) > 0
        assert any(a in ("gluten", "milk") for a in item["matched_allergens"])


@pytest.mark.asyncio
async def test_session_expiry_returns_401(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Expired guest sessions return 401 across all guest endpoints."""
    # Create expired session in DB
    expired_sess = GuestSession(
        restaurant_id=seeded_restaurant.id,
        table_id=None,
        language="it",
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    db_session.add(expired_sess)
    await db_session.flush()

    # Sign cookie
    cookie_val = sign_value(str(expired_sess.id))
    client.cookies.set(GUEST_COOKIE_NAME, cookie_val)

    # Try accessing session and menu
    r1 = await client.get("/api/guest/session")
    assert r1.status_code == 401

    r2 = await client.get("/api/guest/menu")
    assert r2.status_code == 401

    r3 = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "k",
            "items": [{"menu_item_id": str(uuid.uuid4()), "quantity": 1}],
        },
    )
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_order_idempotency_201_200_409(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Order placement idempotency:
    201 on new key, 200 on same key & hash, 409 on different hash.
    """
    # Create valid session
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        table_id=None,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))

    # Fetch menu items
    res_items = await db_session.execute(
        select(MenuItem).where(MenuItem.restaurant_id == seeded_restaurant.id).limit(2)
    )
    items = list(res_items.scalars().all())
    item1, item2 = items[0], items[1]

    idem_key = "order-idem-test-123"
    payload1 = {
        "idempotency_key": idem_key,
        "items": [{"menu_item_id": str(item1.id), "quantity": 2, "notes": "extra basil"}],
        "acknowledge_allergen_risk": True,
    }

    # 1. First placement -> 201 Created
    r1 = await client.post("/api/orders", json=payload1)
    assert r1.status_code == 201
    order1 = r1.json()
    assert order1["idempotency_key"] == idem_key
    assert_no_unit_cost(order1)

    # 2. Re-send exact same payload -> 200 OK (same order ID)
    r2 = await client.post("/api/orders", json=payload1)
    assert r2.status_code == 200
    assert r2.json()["id"] == order1["id"]

    # 3. Same idempotency key, different items -> 409 Conflict
    payload_diff = {
        "idempotency_key": idem_key,
        "items": [{"menu_item_id": str(item2.id), "quantity": 1}],
        "acknowledge_allergen_risk": True,
    }
    r3 = await client.post("/api/orders", json=payload_diff)
    assert r3.status_code == 409


@pytest_asyncio.fixture
async def concurrent_order_env():
    """Self-contained fixture creating committed test entities via real session factory.

    Teardown deletes all created records in strict FK dependency order:
    audit_log, orders, guest_session, menu_translation, menu_item, dining_table, restaurant.
    """
    restaurant_id = uuid.uuid4()
    slug = f"concurrent-{uuid.uuid4().hex[:8]}"
    table_id = uuid.uuid4()
    item_id = uuid.uuid4()
    trans_id = uuid.uuid4()
    guest_session_id = uuid.uuid4()

    async with async_session_factory() as session_db:
        restaurant = Restaurant(
            id=restaurant_id,
            name="Concurrent Trattoria",
            slug=slug,
            languages=["en", "it"],
            default_language="en",
            currency="EUR",
        )
        session_db.add(restaurant)
        await session_db.flush()

        table = DiningTable(
            id=table_id,
            restaurant_id=restaurant_id,
            label="T-Conc",
            qr_token=f"qr-{uuid.uuid4().hex[:12]}",
        )
        session_db.add(table)
        await session_db.flush()

        item = MenuItem(
            id=item_id,
            restaurant_id=restaurant_id,
            category="mains",
            price=Decimal("15.00"),
            unit_cost=Decimal("4.00"),
            ingredients=["flour", "water", "salt"],
            allergens=[],
            allergen_verified=True,
            dietary_verified=True,
            is_vegetarian=True,
            is_vegan=True,
            is_gluten_free=False,
            available=True,
        )
        session_db.add(item)
        await session_db.flush()

        translation = MenuTranslation(
            id=trans_id,
            menu_item_id=item_id,
            language="en",
            name="Concurrent Pasta",
            description="Fresh pasta",
        )
        session_db.add(translation)
        await session_db.flush()

        guest_session = GuestSession(
            id=guest_session_id,
            restaurant_id=restaurant_id,
            table_id=table_id,
            language="en",
            dietary_preferences=[],
            allergens_to_avoid=[],
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        session_db.add(guest_session)
        await session_db.commit()

    env_data = {
        "restaurant_id": restaurant_id,
        "table_id": table_id,
        "item_id": item_id,
        "guest_session_id": guest_session_id,
    }

    try:
        yield env_data
    finally:
        async with async_session_factory() as session_db:
            # 1. audit_log
            await session_db.execute(
                delete(AuditLog).where(AuditLog.restaurant_id == restaurant_id)
            )
            # 2. orders (cascades to order_item)
            await session_db.execute(delete(Order).where(Order.restaurant_id == restaurant_id))
            # 3. guest_session
            await session_db.execute(
                delete(GuestSession).where(GuestSession.restaurant_id == restaurant_id)
            )
            # 4. menu_translation
            await session_db.execute(
                delete(MenuTranslation).where(MenuTranslation.menu_item_id == item_id)
            )
            # 5. menu_item
            await session_db.execute(
                delete(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
            )
            # 6. dining_table
            await session_db.execute(
                delete(DiningTable).where(DiningTable.restaurant_id == restaurant_id)
            )
            # 7. restaurant
            await session_db.execute(delete(Restaurant).where(Restaurant.id == restaurant_id))
            await session_db.commit()


@pytest.mark.asyncio
async def test_concurrent_duplicate_posts_create_one_order(
    concurrent_order_env: dict[str, uuid.UUID],
):
    """Concurrent duplicate POST requests with the same idempotency key result in one order."""
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        guest_sess_id = concurrent_order_env["guest_session_id"]
        item_id = concurrent_order_env["item_id"]

        cookie_val = sign_value(str(guest_sess_id))
        cookies = {GUEST_COOKIE_NAME: cookie_val}
        idem_key = f"concurrent-{uuid.uuid4()}"
        payload = {
            "idempotency_key": idem_key,
            "items": [{"menu_item_id": str(item_id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        }

        async with (
            AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
            ) as ac1,
            AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", cookies=cookies
            ) as ac2,
        ):
            r1, r2 = await asyncio.gather(
                ac1.post("/api/orders", json=payload),
                ac2.post("/api/orders", json=payload),
            )

        assert r1.status_code in (200, 201)
        assert r2.status_code in (200, 201)
        assert r1.json()["id"] == r2.json()["id"]

        async with async_session_factory() as session_db:
            res_orders = await session_db.execute(
                select(Order).where(Order.idempotency_key == idem_key)
            )
            orders = list(res_orders.scalars().all())
            assert len(orders) == 1
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override


@pytest.mark.asyncio
async def test_allergen_acknowledgment_required_and_recorded(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Conflict with allergens_to_avoid requires acknowledgment.

    Returns 409 without ack, records audit on ack.
    """
    # Session avoids milk
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        table_id=None,
        language="en",
        allergens_to_avoid=["milk"],
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))

    # Find item with milk (e.g., Tiramisù or Margherita)
    res_milk = await db_session.execute(
        select(MenuItem).where(
            MenuItem.restaurant_id == seeded_restaurant.id,
            MenuItem.allergens.contains(["milk"]),
        )
    )
    milk_item = res_milk.scalars().first()
    assert milk_item is not None

    order_payload = {
        "idempotency_key": "ack-test-key",
        "items": [{"menu_item_id": str(milk_item.id), "quantity": 1}],
        "acknowledge_allergen_risk": False,
    }

    # 1. Unacknowledged -> 409 allergen_ack_required
    r_unack = await client.post("/api/orders", json=order_payload)
    assert r_unack.status_code == 409
    assert r_unack.json()["detail"]["error"] == "allergen_ack_required"

    # 2. Acknowledged -> 201 Created
    order_payload["acknowledge_allergen_risk"] = True
    r_ack = await client.post("/api/orders", json=order_payload)
    assert r_ack.status_code == 201
    assert r_ack.json()["allergen_conflict_acknowledged"] is True

    # 3. Verify audit log entry exists
    res_audit = await db_session.execute(
        select(AuditLog).where(
            AuditLog.restaurant_id == seeded_restaurant.id,
            AuditLog.event_type == "allergen_conflict_acknowledged",
        )
    )
    audit_ack = res_audit.scalars().first()
    assert audit_ack is not None

    # 4. Safe item with no conflicts: acknowledge_allergen_risk=True leaves it False
    res_safe = await db_session.execute(
        select(MenuItem).where(
            MenuItem.restaurant_id == seeded_restaurant.id,
            ~MenuItem.allergens.contains(["milk"]),
            MenuItem.allergen_verified.is_(True),
        )
    )
    safe_item = res_safe.scalars().first()
    assert safe_item is not None

    r_safe = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "safe-ack-flag-test-key",
            "items": [{"menu_item_id": str(safe_item.id), "quantity": 1}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert r_safe.status_code == 201
    assert r_safe.json()["allergen_conflict_acknowledged"] is False


@pytest.mark.asyncio
async def test_guest_isolation_404(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Guest A gets 404 when attempting to fetch Guest B's order (no enumeration, no 403)."""
    # Create Session A and Session B
    now = datetime.now(UTC)
    sess_a = GuestSession(
        restaurant_id=seeded_restaurant.id, language="it", expires_at=now + timedelta(hours=1)
    )
    sess_b = GuestSession(
        restaurant_id=seeded_restaurant.id, language="it", expires_at=now + timedelta(hours=1)
    )
    db_session.add_all([sess_a, sess_b])
    await db_session.flush()

    # Create Order for Guest B
    order_b = Order(
        guest_session_id=sess_b.id,
        restaurant_id=seeded_restaurant.id,
        status="placed",
        total=Decimal("15.00"),
        idempotency_key="key-b",
        payload_hash="hash-b",
    )
    db_session.add(order_b)
    await db_session.flush()

    # Guest A attempts to GET Order B -> 404
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(sess_a.id)))
    resp = await client.get(f"/api/orders/{order_b.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_snapshots_unchanged_after_later_menu_edit(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Order item snapshot columns remain unchanged even after menu item price changes."""
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        language="it",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))

    # Fetch menu item
    res = await db_session.execute(
        select(MenuItem).where(MenuItem.restaurant_id == seeded_restaurant.id).limit(1)
    )
    item = res.scalars().first()
    original_price = item.price

    # Place order
    r_order = await client.post(
        "/api/orders",
        json={
            "idempotency_key": "snapshot-test-key",
            "items": [{"menu_item_id": str(item.id), "quantity": 2}],
            "acknowledge_allergen_risk": True,
        },
    )
    assert r_order.status_code == 201
    order_id = r_order.json()["id"]

    # Edit menu item price in DB
    item.price = Decimal("99.99")
    await db_session.flush()

    # Fetch order again; snapshot unit_price must still reflect original_price
    r_check = await client.get(f"/api/orders/{order_id}")
    assert r_check.status_code == 200
    line_item = r_check.json()["items"][0]
    assert Decimal(str(line_item["unit_price"])) == original_price


@pytest.mark.asyncio
async def test_auth_matrix_401_and_403(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
):
    """Matrix test: unauthenticated -> 401, staff -> 403 on owner routes, owner -> 200 on all."""
    slug = seeded_restaurant.slug
    owner_cookie = sign_value(f"owner:{int(time.time()) + 3600}")
    staff_cookie = sign_value(f"staff:{int(time.time()) + 3600}")

    kitchen_url = f"/api/restaurants/{slug}/kitchen/orders"
    menu_url = f"/api/restaurants/{slug}/menu-items"
    tables_url = f"/api/restaurants/{slug}/tables"

    # --- 1. Unauthenticated (no cookie) -> 401 ---
    client.cookies.clear()
    assert (await client.get(kitchen_url)).status_code == 401
    assert (await client.get(menu_url)).status_code == 401
    assert (await client.get(tables_url)).status_code == 401

    # --- 2. Staff cookie -> 200 on kitchen, 403 on owner endpoints ---
    client.cookies.set(AUTH_COOKIE_NAME, staff_cookie)
    assert (await client.get(kitchen_url)).status_code == 200
    assert (await client.get(menu_url)).status_code == 403
    assert (await client.get(tables_url)).status_code == 403

    # --- 3. Owner cookie -> 200 on all endpoints ---
    client.cookies.set(AUTH_COOKIE_NAME, owner_cookie)
    assert (await client.get(kitchen_url)).status_code == 200
    assert (await client.get(menu_url)).status_code == 200
    assert (await client.get(tables_url)).status_code == 200


@pytest.mark.asyncio
async def test_kitchen_bump_idempotent_and_recall_timing(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Kitchen bump is idempotent; recall succeeds at 59s and is rejected at 61s."""
    slug = seeded_restaurant.slug
    staff_cookie = sign_value(f"staff:{int(time.time()) + 3600}")
    client.cookies.set(AUTH_COOKIE_NAME, staff_cookie)

    # Create order
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        language="it",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.flush()

    order = Order(
        guest_session_id=session.id,
        restaurant_id=seeded_restaurant.id,
        status="placed",
        total=Decimal("20.00"),
        idempotency_key="bump-recall-key",
        payload_hash="hash-bump",
    )
    db_session.add(order)
    await db_session.flush()
    order_id = order.id

    # 1. First bump -> status becomes bumped
    r_bump = await client.post(f"/api/restaurants/{slug}/kitchen/orders/{order_id}/bump")
    assert r_bump.status_code == 200
    bump_data = r_bump.json()
    assert bump_data["status"] == "bumped"
    first_bumped_at = bump_data["bumped_at"]

    # 2. Re-bump (idempotency check) -> returns same bumped_at
    r_rebump = await client.post(f"/api/restaurants/{slug}/kitchen/orders/{order_id}/bump")
    assert r_rebump.status_code == 200
    assert r_rebump.json()["bumped_at"] == first_bumped_at

    # 3. Simulate order bumped 59s ago -> recall allowed
    await db_session.execute(
        text("UPDATE orders SET bumped_at = :ts WHERE id = :id"),
        {"ts": datetime.now(UTC) - timedelta(seconds=59), "id": order_id},
    )
    db_session.expire_all()
    r_recall_59 = await client.post(f"/api/restaurants/{slug}/kitchen/orders/{order_id}/recall")
    assert r_recall_59.status_code == 200
    assert r_recall_59.json()["status"] == "placed"
    assert r_recall_59.json()["bumped_at"] is None

    # Re-bump and simulate 61s ago -> recall rejected with 409
    await client.post(f"/api/restaurants/{slug}/kitchen/orders/{order_id}/bump")
    await db_session.execute(
        text("UPDATE orders SET bumped_at = :ts WHERE id = :id"),
        {"ts": datetime.now(UTC) - timedelta(seconds=61), "id": order_id},
    )
    db_session.expire_all()
    r_recall_61 = await client.post(f"/api/restaurants/{slug}/kitchen/orders/{order_id}/recall")
    assert r_recall_61.status_code == 409


@pytest.mark.asyncio
async def test_owner_patch_resets_verified_flags_and_audit(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """Owner PATCH of allergens/ingredients resets allergen_verified;
    dietary flags reset dietary_verified.
    """
    slug = seeded_restaurant.slug
    owner_cookie = sign_value(f"owner:{int(time.time()) + 3600}")
    client.cookies.set(AUTH_COOKIE_NAME, owner_cookie)

    # Pick an item initially verified
    res = await db_session.execute(
        select(MenuItem)
        .where(
            MenuItem.restaurant_id == seeded_restaurant.id,
            MenuItem.allergen_verified.is_(True),
            MenuItem.dietary_verified.is_(True),
        )
        .limit(1)
    )
    item = res.scalars().first()
    assert item is not None

    # 1. Edit allergens -> resets allergen_verified
    r_patch_all = await client.patch(
        f"/api/restaurants/{slug}/menu-items/{item.id}",
        json={"allergens": ["sesame"]},
    )
    assert r_patch_all.status_code == 200
    assert r_patch_all.json()["allergen_verified"] is False
    assert r_patch_all.json()["dietary_verified"] is True  # Dietary unchanged

    # Verify audit row
    res_aud1 = await db_session.execute(
        select(AuditLog).where(
            AuditLog.restaurant_id == seeded_restaurant.id,
            AuditLog.event_type == "owner_allergen_edit",
        )
    )
    assert res_aud1.scalars().first() is not None

    # 2. Edit dietary -> resets dietary_verified
    r_patch_diet = await client.patch(
        f"/api/restaurants/{slug}/menu-items/{item.id}",
        json={"is_vegan": False},
    )
    assert r_patch_diet.status_code == 200
    assert r_patch_diet.json()["dietary_verified"] is False

    # 3. POST /verify -> resets both to True
    r_verify = await client.post(f"/api/restaurants/{slug}/menu-items/{item.id}/verify")
    assert r_verify.status_code == 200
    assert r_verify.json()["allergen_verified"] is True
    assert r_verify.json()["dietary_verified"] is True


@pytest.mark.asyncio
async def test_failing_redis_publish_does_not_fail_order(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """A failing Redis publish after order commit is logged and never fails the order."""
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        language="it",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))

    res = await db_session.execute(
        select(MenuItem).where(MenuItem.restaurant_id == seeded_restaurant.id).limit(1)
    )
    item = res.scalars().first()

    # Mock publish_event to raise an exception inside redis_client.publish
    with patch("src.redis_client.redis_client.publish", side_effect=RuntimeError("Redis down")):
        r = await client.post(
            "/api/orders",
            json={
                "idempotency_key": "redis-fail-test",
                "items": [{"menu_item_id": str(item.id), "quantity": 1}],
                "acknowledge_allergen_risk": True,
            },
        )
        assert r.status_code == 201
        assert r.json()["idempotency_key"] == "redis-fail-test"


@pytest.mark.asyncio
async def test_order_integrity_error_non_idempotency_reraised(
    client: AsyncClient,
    seeded_restaurant: Restaurant,
    db_session: AsyncSession,
):
    """IntegrityError not on orders_guest_idempotency_key must be re-raised."""
    session = GuestSession(
        restaurant_id=seeded_restaurant.id,
        language="en",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.flush()
    client.cookies.set(GUEST_COOKIE_NAME, sign_value(str(session.id)))

    res = await db_session.execute(
        select(MenuItem).where(MenuItem.restaurant_id == seeded_restaurant.id).limit(1)
    )
    item = res.scalars().first()

    from sqlalchemy.exc import IntegrityError

    # Non-idempotency IntegrityError (e.g. check constraint, not SQLSTATE 23505)
    non_idempotency_err = IntegrityError(
        "check constraint failed",
        orig=Exception("chk_orders_total"),
        params=None,
    )

    with (
        patch.object(AsyncSession, "commit", side_effect=non_idempotency_err),
        pytest.raises(IntegrityError),
    ):
        await client.post(
            "/api/orders",
            json={
                "idempotency_key": "non-idem-err-key",
                "items": [{"menu_item_id": str(item.id), "quantity": 1}],
                "acknowledge_allergen_risk": True,
            },
        )
