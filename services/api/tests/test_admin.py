"""Onboarding commands."""

import pytest
from scripts.admin import AdminError, add_user, create_restaurant
from sqlalchemy import select

from src.models.user import Membership
from src.passwords import verify_password


async def test_create_restaurant_and_add_owner(db_session):
    r = await create_restaurant(
        db_session,
        slug="cafe-x",
        name="Cafe X",
        city="Lahore",
        jurisdiction="PB",
        currency="PKR",
        timezone="Asia/Karachi",
    )
    u = await add_user(
        db_session,
        email="Boss@CafeX.pk",
        name="Boss",
        restaurant_slug="cafe-x",
        role="owner",
        password="long-enough-pass",
    )
    assert r.tax_jurisdiction == "PB"
    assert u.email == "boss@cafex.pk"
    assert verify_password("long-enough-pass", u.password_hash)
    m = (
        await db_session.execute(select(Membership).where(Membership.user_id == u.id))
    ).scalar_one()
    assert m.role == "owner"


async def test_unknown_jurisdiction_is_rejected(db_session):
    with pytest.raises(AdminError, match="No tax rates"):
        await create_restaurant(
            db_session,
            slug="cafe-y",
            name="Y",
            city="Karachi",
            jurisdiction="SD",
            currency="PKR",
            timezone="Asia/Karachi",
        )


async def test_existing_user_gets_second_membership(db_session):
    await create_restaurant(
        db_session,
        slug="a1",
        name="A1",
        city="Lahore",
        jurisdiction="PB",
        currency="PKR",
        timezone="Asia/Karachi",
    )
    await create_restaurant(
        db_session,
        slug="a2",
        name="A2",
        city="Islamabad",
        jurisdiction="ICT",
        currency="PKR",
        timezone="Asia/Karachi",
    )
    u1 = await add_user(
        db_session,
        email="s@x.pk",
        name="S",
        restaurant_slug="a1",
        role="staff",
        password="pw-123456",
    )
    u2 = await add_user(
        db_session, email="s@x.pk", name="S", restaurant_slug="a2", role="owner", password=None
    )
    assert u1.id == u2.id


async def test_short_password_rejected(db_session):
    await create_restaurant(
        db_session,
        slug="a3",
        name="A3",
        city="Lahore",
        jurisdiction="PB",
        currency="PKR",
        timezone="Asia/Karachi",
    )
    with pytest.raises(AdminError, match="at least 8"):
        await add_user(
            db_session,
            email="n@x.pk",
            name="N",
            restaurant_slug="a3",
            role="owner",
            password="short",
        )
