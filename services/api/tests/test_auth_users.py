"""Per-user login, sessions and restaurant access."""

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, make_user

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.models.restaurant import Restaurant


@pytest.fixture
async def two_restaurants(db_session: AsyncSession) -> tuple[Restaurant, Restaurant]:
    a = Restaurant(
        name="A",
        slug="venue-a",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    b = Restaurant(
        name="B",
        slug="venue-b",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


async def test_login_with_email_and_password(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await make_user(
        db_session, [(a.id, "owner")], email="owner@example.com", password="s3cret-pass"
    )
    resp = await client.post(
        "/api/auth/login", json={"email": "Owner@Example.com", "password": "s3cret-pass"}
    )
    assert resp.status_code == 200
    assert AUTH_COOKIE_NAME in resp.cookies
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


async def test_wrong_password_and_unknown_email_look_the_same(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await make_user(db_session, [(a.id, "owner")], email="o2@example.com", password="right-pass")
    wrong = await client.post(
        "/api/auth/login", json={"email": "o2@example.com", "password": "nope"}
    )
    unknown = await client.post(
        "/api/auth/login", json={"email": "who@example.com", "password": "nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_old_role_cookie_is_rejected(client):
    client.cookies.set(AUTH_COOKIE_NAME, sign_value(f"owner:{int(time.time()) + 3600}"))
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_non_member_gets_404_and_staff_gets_403(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await as_member(client, db_session, a.id, "staff")
    other = await client.get("/api/restaurants/venue-b/menu-items")
    unknown = await client.get("/api/restaurants/no-such-venue/menu-items")
    assert other.status_code == unknown.status_code == 404
    assert other.json() == unknown.json()  # a non-member cannot tell the venue exists
    assert (await client.get("/api/restaurants/venue-a/menu-items")).status_code == 403
    assert (await client.get("/api/restaurants/venue-a/kitchen/orders")).status_code == 200


async def test_my_restaurants_lists_only_memberships(client, db_session, two_restaurants):
    a, _ = two_restaurants
    await as_member(client, db_session, a.id, "owner")
    resp = await client.get("/api/restaurants")
    assert resp.status_code == 200
    rows = resp.json()["restaurants"]
    assert [r["slug"] for r in rows] == ["venue-a"]
    assert rows[0]["role"] == "owner"
    assert rows[0]["city"] is None
