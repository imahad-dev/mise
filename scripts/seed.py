"""Seed database from JSON file.

Usage:
    docker compose exec -T api python scripts/seed.py [--file data/seed/angeethi_house.json ...]
        [--demo-users data/seed/demo_users.json] [--rotate-qr]
"""

import argparse
import asyncio
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.config import settings
from src.database import async_session_factory
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption, MenuTranslation
from src.models.restaurant import Restaurant
from src.models.user import Membership, User
from src.passwords import hash_password
from src.services.payment_details import validate_payment_details
from src.services.simulator import SEED_ITEM_NAMESPACE, SimAssumptions

logger = logging.getLogger(__name__)

DEFAULT_SEED_FILES = ["data/seed/angeethi_house.json", "data/seed/kehwa_and_crumb.json"]
DEFAULT_DEMO_USERS_FILE = "data/seed/demo_users.json"


def simulation_profile(data: dict[str, Any]) -> dict[str, Any] | None:
    """The seed's `simulation` block plus per-item `weights` and `option_weights` (by item
    key), validated, as stored in restaurant.onboarding["simulation"]; None without a block."""
    sim = data.get("simulation")
    if sim is None:
        return None
    SimAssumptions.from_profile(sim)  # raises on unknown keys or bad values
    weights: dict[str, float] = {}
    option_weights: dict[str, list[float]] = {}
    for item in data.get("items", []):
        if "sim_weight" in item:
            weights[item["key"]] = item["sim_weight"]
        if "option_weights" in item:  # a count mismatch falls back to equal weights
            option_weights[item["key"]] = item["option_weights"]
    return {**sim, "weights": weights, "option_weights": option_weights}


def load_seed_data(file_path: str) -> dict[str, Any]:
    """Load and parse seed JSON file synchronously."""
    path = Path(file_path)
    if not path.is_absolute():
        if not path.exists():
            # Search upwards from cwd and script directory
            for base in [Path.cwd(), Path(__file__).resolve().parent]:
                for parent in [base, *base.parents]:
                    candidate = parent / file_path
                    if candidate.is_file():
                        path = candidate
                        break
                if path.is_file():
                    break
        else:
            path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def find_seed_for_slug(slug: str) -> dict[str, Any] | None:
    """Return the seed in data/seed/*.json whose restaurant.slug is slug, or None."""
    for base in [Path.cwd(), *Path(__file__).resolve().parents]:
        seed_dir = base / "data" / "seed"
        if seed_dir.is_dir():
            for path in sorted(seed_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    logger.warning("Skipping unreadable seed file %s", path)
                    continue
                rest = data.get("restaurant") if isinstance(data, dict) else None
                if not isinstance(rest, dict):
                    if (
                        not isinstance(data, dict) or "owner" not in data
                    ):  # demo_users.json
                        logger.warning(
                            "Skipping seed file without a restaurant: %s", path
                        )
                    continue
                if rest.get("slug") == slug:
                    return data
            return None
    return None


async def seed_data(
    data: dict[str, Any],
    session: AsyncSession,
    rotate_qr: bool = False,
) -> None:
    """Seed restaurant, tables, menu items, and translations into database.

    Does not commit; caller manages transaction lifecycle.
    """
    rest_data = data["restaurant"]
    tables_data = data.get("tables", [])
    items_data = data.get("items", [])
    profile = simulation_profile(data)

    payment_details = validate_payment_details(
        rest_data.get("payment_details", {}),
        allow_sample=rest_data["slug"] in settings.demo_restaurant_slugs,
    )

    # 1. Upsert Restaurant
    stmt_rest = select(Restaurant).where(Restaurant.slug == rest_data["slug"])
    res_rest = await session.execute(stmt_rest)
    restaurant = res_rest.scalar_one_or_none()

    if restaurant is None:
        restaurant = Restaurant(
            name=rest_data["name"],
            slug=rest_data["slug"],
            city=rest_data.get("city"),
            tax_jurisdiction=rest_data.get("tax_jurisdiction"),
            service_extra_label=rest_data.get("service_extra_label"),
            pickup_prefix=rest_data.get("pickup_prefix"),
            payment_details=payment_details,
            timezone=rest_data.get("timezone", "Asia/Karachi"),
            currency=rest_data.get("currency", "PKR"),
            languages=rest_data.get("languages", ["en"]),
            default_language=rest_data.get("default_language", "en"),
            onboarding=rest_data.get("onboarding", {}),
            active=rest_data.get("active", True),
        )
        session.add(restaurant)
        await session.flush()
        print(f"Created restaurant: {restaurant.name} ({restaurant.slug})")
    else:
        restaurant.name = rest_data["name"]
        restaurant.city = rest_data.get("city")
        restaurant.tax_jurisdiction = rest_data.get("tax_jurisdiction")
        restaurant.service_extra_label = rest_data.get("service_extra_label")
        restaurant.pickup_prefix = rest_data.get("pickup_prefix")
        if "payment_details" in rest_data:
            restaurant.payment_details = payment_details
        restaurant.timezone = rest_data.get("timezone", "Asia/Karachi")
        restaurant.currency = rest_data.get("currency", "PKR")
        restaurant.languages = rest_data.get("languages", ["en"])
        restaurant.default_language = rest_data.get("default_language", "en")
        if "onboarding" in rest_data:
            restaurant.onboarding = rest_data["onboarding"]
        restaurant.active = rest_data.get("active", True)
        await session.flush()
        print(f"Updated restaurant: {restaurant.name} ({restaurant.slug})")
    if profile is not None:  # a new dict: JSONB does not track in-place mutation
        restaurant.onboarding = {**(restaurant.onboarding or {}), "simulation": profile}
        await session.flush()

    # 2. Upsert Dining Tables via explicit query (no relationship traversal)
    stmt_tables = select(DiningTable).where(DiningTable.restaurant_id == restaurant.id)
    res_tables = await session.execute(stmt_tables)
    existing_tables_by_label = {t.label: t for t in res_tables.scalars().all()}

    for t_info in tables_data:
        label = t_info["label"]
        if label in existing_tables_by_label:
            target_table = existing_tables_by_label[label]
            target_table.kind = t_info.get("kind", "table")
            if rotate_qr or not target_table.qr_token:
                target_table.qr_token = secrets.token_urlsafe(12)
        else:
            new_table = DiningTable(
                restaurant_id=restaurant.id,
                label=label,
                kind=t_info.get("kind", "table"),
                qr_token=secrets.token_urlsafe(12),
            )
            session.add(new_table)
    await session.flush()

    # 3. Upsert Menu Items and Translations via explicit query with selectinload
    stmt_items = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations), selectinload(MenuItem.options))
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    res_items = await session.execute(stmt_items)
    existing_items_list = list(res_items.scalars().all())
    existing_items_by_id = {m.id: m for m in existing_items_list}

    items_created = 0
    items_updated = 0
    for item_data in items_data:
        item_uuid = uuid.uuid5(
            SEED_ITEM_NAMESPACE, f"{restaurant.slug}:{item_data['key']}"
        )
        target_item = existing_items_by_id.get(item_uuid)
        options_data = item_data.get("options", [])
        if options_data:  # the item's own price is its cheapest option
            cheapest = min(options_data, key=lambda opt: opt["price"])
            item_data = {
                **item_data,
                "price": cheapest["price"],
                "unit_cost": cheapest["unit_cost"],
            }

        if target_item is None:
            target_item = MenuItem(
                id=item_uuid,
                restaurant_id=restaurant.id,
                category=item_data["category"],
                price=item_data["price"],
                unit_cost=item_data["unit_cost"],
                ingredients=item_data.get("ingredients", []),
                allergens=item_data.get("allergens", []),
                allergen_verified=item_data.get("allergen_verified", False),
                is_vegetarian=item_data.get("is_vegetarian", False),
                is_vegan=item_data.get("is_vegan", False),
                is_gluten_free=item_data.get("is_gluten_free", False),
                dietary_verified=item_data.get("dietary_verified", False),
                available=item_data.get("available", True),
                featured=item_data.get("featured", False),
                sort_order=item_data.get("sort_order", 0),
            )
            session.add(target_item)
            await session.flush()

            # Add translations
            for lang, tr_val in item_data["translations"].items():
                tr = MenuTranslation(
                    menu_item_id=target_item.id,
                    language=lang,
                    name=tr_val["name"],
                    description=tr_val.get("description"),
                )
                session.add(tr)
            items_created += 1
        else:
            target_item.category = item_data["category"]
            target_item.price = item_data["price"]
            target_item.unit_cost = item_data["unit_cost"]
            target_item.ingredients = item_data.get("ingredients", [])
            target_item.allergens = item_data.get("allergens", [])
            target_item.allergen_verified = item_data.get("allergen_verified", False)
            target_item.is_vegetarian = item_data.get("is_vegetarian", False)
            target_item.is_vegan = item_data.get("is_vegan", False)
            target_item.is_gluten_free = item_data.get("is_gluten_free", False)
            target_item.dietary_verified = item_data.get("dietary_verified", False)
            target_item.available = item_data.get("available", True)
            target_item.featured = item_data.get("featured", False)
            target_item.sort_order = item_data.get("sort_order", 0)

            # Upsert translations
            existing_trans = {t.language: t for t in target_item.translations}
            for lang, tr_val in item_data["translations"].items():
                if lang in existing_trans:
                    existing_trans[lang].name = tr_val["name"]
                    existing_trans[lang].description = tr_val.get("description")
                else:
                    session.add(
                        MenuTranslation(
                            menu_item_id=target_item.id,
                            language=lang,
                            name=tr_val["name"],
                            description=tr_val.get("description"),
                        )
                    )
            items_updated += 1

        # Options: matched by stable id; any option no longer in the file is deleted.
        existing_options = (
            {opt.id: opt for opt in target_item.options}
            if item_uuid in existing_items_by_id
            else {}
        )
        wanted_ids = set()
        for position, opt_data in enumerate(options_data):
            opt_id = uuid.uuid5(
                SEED_ITEM_NAMESPACE,
                f"{restaurant.slug}:{item_data['key']}:{opt_data['label']}",
            )
            wanted_ids.add(opt_id)
            if opt_id in existing_options:
                opt = existing_options[opt_id]
                opt.label = opt_data["label"]
                opt.price = opt_data["price"]
                opt.unit_cost = opt_data["unit_cost"]
                opt.sort_order = position
            else:
                session.add(
                    MenuItemOption(
                        id=opt_id,
                        menu_item_id=target_item.id,
                        label=opt_data["label"],
                        price=opt_data["price"],
                        unit_cost=opt_data["unit_cost"],
                        sort_order=position,
                    )
                )
        for opt_id, opt in existing_options.items():
            if opt_id not in wanted_ids:
                await session.delete(opt)

    await session.flush()
    total_items = len(items_data)
    print(
        f"Menu items seed finished: {items_created} created, "
        f"{items_updated} updated (total {total_items} items)."
    )

    # 4. Print label-to-token table
    res_tables_display = await session.execute(
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    tables_display = list(res_tables_display.scalars().all())
    print("\n--- Dining Tables (Label -> QR Token) ---")
    print(f"{'Label':<15} | {'QR Token':<20}")
    print("-" * 38)
    for t in tables_display:
        print(f"{t.label:<15} | {t.qr_token:<20}")
    print("-" * 38 + "\n")


async def seed_demo_users(data: dict[str, Any], session: AsyncSession) -> None:
    """Create the demo owner and per-venue staff users with their memberships.

    Demo users get a random unusable password: they sign in only through demo-login.
    Does not commit; caller manages transaction lifecycle.
    """
    owner = data["owner"]
    wanted: list[tuple[str, str, str, str]] = [
        (owner["email"], owner["name"], slug, "owner") for slug in owner["venues"]
    ]
    wanted += [
        (u["email"], u["name"], u["venue"], "staff") for u in data.get("staff", [])
    ]

    slugs = {slug for _, _, slug, _ in wanted}
    res = await session.execute(select(Restaurant).where(Restaurant.slug.in_(slugs)))
    venue_ids = {r.slug: r.id for r in res.scalars().all()}

    for email, name, slug, role in wanted:
        if slug not in venue_ids:
            print(f"Demo user {email}: venue {slug} is not seeded, skipped.")
            continue
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                name=name,
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )
            session.add(user)
            await session.flush()
        else:
            user.name = name
        member = (
            await session.execute(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.restaurant_id == venue_ids[slug],
                )
            )
        ).scalar_one_or_none()
        if member is None:
            session.add(
                Membership(user_id=user.id, restaurant_id=venue_ids[slug], role=role)
            )
        else:
            member.role = role
    await session.flush()


async def async_main(args: argparse.Namespace) -> None:
    payloads = [load_seed_data(f) for f in (args.file or DEFAULT_SEED_FILES)]
    users_file = args.demo_users or (
        DEFAULT_DEMO_USERS_FILE if settings.demo_mode else None
    )
    async with async_session_factory() as session:
        for payload in payloads:
            await seed_data(payload, session, rotate_qr=args.rotate_qr)
        if users_file:
            await seed_demo_users(load_seed_data(users_file), session)
            print(f"Demo users seeded from {users_file}.")
        await session.commit()
        print("Seed successfully committed to database.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mise database")
    parser.add_argument(
        "--file",
        action="append",
        help="Seed JSON file (repeatable); defaults to both demo venues",
    )
    parser.add_argument(
        "--demo-users",
        help="Demo users JSON file; applied by default only when DEMO_MODE is true",
    )
    parser.add_argument(
        "--rotate-qr",
        action="store_true",
        default=False,
        help="Regenerate QR tokens for all existing dining tables",
    )
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
