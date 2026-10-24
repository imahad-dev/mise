"""Onboard a client restaurant and its users (there is no public sign-up).

Usage:
    docker compose exec api python scripts/admin.py create-restaurant \
        --slug cafe-x --name "Cafe X" --city Lahore --jurisdiction PB \
        --currency PKR --timezone Asia/Karachi
    docker compose exec api python scripts/admin.py add-user \
        --email boss@cafex.pk --name Boss --restaurant cafe-x --role owner

add-user prompts for the password (never taken from argv, never printed). A user who already
exists is only given another membership; no password is asked for.
"""

import argparse
import asyncio
import getpass
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import async_session_factory
from src.models.restaurant import Restaurant
from src.models.user import Membership, User
from src.passwords import hash_password
from src.services import tax

MIN_PASSWORD_LENGTH = 8


class AdminError(Exception):
    pass


async def create_restaurant(
    db: AsyncSession,
    *,
    slug: str,
    name: str,
    city: str,
    jurisdiction: str,
    currency: str,
    timezone: str,
) -> Restaurant:
    if jurisdiction not in tax.jurisdictions():
        known = ", ".join(sorted(tax.jurisdictions()))
        raise AdminError(
            f"No tax rates for jurisdiction {jurisdiction!r} (known: {known})"
        )
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise AdminError(f"Currency must be 3 uppercase letters, got {currency!r}")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise AdminError(f"Unknown timezone {timezone!r}") from e
    taken = await db.execute(select(Restaurant.id).where(Restaurant.slug == slug))
    if taken.scalar_one_or_none() is not None:
        raise AdminError(f"Restaurant slug {slug!r} already exists")
    restaurant = Restaurant(
        slug=slug,
        name=name,
        city=city,
        tax_jurisdiction=jurisdiction,
        currency=currency,
        timezone=timezone,
        languages=["en"],
        default_language="en",
    )
    db.add(restaurant)
    await db.flush()
    return restaurant


async def user_exists(db: AsyncSession, email: str) -> bool:
    found = await db.execute(select(User.id).where(User.email == email.strip().lower()))
    return found.scalar_one_or_none() is not None


async def add_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    restaurant_slug: str,
    role: str,
    password: str | None,
) -> User:
    if role not in ("owner", "staff"):
        raise AdminError("Role must be 'owner' or 'staff'")
    email = email.strip().lower()
    restaurant = (
        await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    ).scalar_one_or_none()
    if restaurant is None:
        raise AdminError(f"No restaurant with slug {restaurant_slug!r}")
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        if password is None or len(password) < MIN_PASSWORD_LENGTH:
            raise AdminError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        user = User(email=email, name=name, password_hash=hash_password(password))
        db.add(user)
        await db.flush()
    existing = await db.execute(
        select(Membership.id).where(
            Membership.user_id == user.id, Membership.restaurant_id == restaurant.id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AdminError(f"{email} is already a member of {restaurant_slug!r}")
    db.add(Membership(user_id=user.id, restaurant_id=restaurant.id, role=role))
    await db.flush()
    return user


async def _run(args: argparse.Namespace) -> None:
    async with async_session_factory() as db:
        if args.command == "create-restaurant":
            r = await create_restaurant(
                db,
                slug=args.slug,
                name=args.name,
                city=args.city,
                jurisdiction=args.jurisdiction,
                currency=args.currency,
                timezone=args.timezone,
            )
            await db.commit()
            print(f"Created restaurant {r.slug}")
            return
        password = None
        if not await user_exists(db, args.email):
            password = getpass.getpass("Password: ")
            if getpass.getpass("Repeat password: ") != password:
                raise AdminError("Passwords do not match")
        u = await add_user(
            db,
            email=args.email,
            name=args.name,
            restaurant_slug=args.restaurant,
            role=args.role,
            password=password,
        )
        await db.commit()
        print(f"Added {u.email} to {args.restaurant} as {args.role}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mise onboarding")
    sub = parser.add_subparsers(dest="command", required=True)
    cr = sub.add_parser("create-restaurant")
    cr.add_argument("--slug", required=True)
    cr.add_argument("--name", required=True)
    cr.add_argument("--city", required=True)
    cr.add_argument("--jurisdiction", required=True)
    cr.add_argument("--currency", default="PKR")
    cr.add_argument("--timezone", default="Asia/Karachi")
    au = sub.add_parser("add-user")
    au.add_argument("--email", required=True)
    au.add_argument("--name", required=True)
    au.add_argument("--restaurant", required=True)
    au.add_argument("--role", required=True, choices=["owner", "staff"])
    try:
        asyncio.run(_run(parser.parse_args()))
    except AdminError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
