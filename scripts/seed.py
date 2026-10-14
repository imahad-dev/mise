"""Seed database from JSON file.

Usage:
    docker compose exec -T api python scripts/seed.py [--file data/seed/trattoria_da_mario.json] [--rotate-qr]
"""

import argparse
import asyncio
import json
import secrets
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.database import async_session_factory
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuTranslation
from src.models.restaurant import Restaurant

SEED_ITEM_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d")


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

    # 1. Upsert Restaurant
    stmt_rest = select(Restaurant).where(Restaurant.slug == rest_data["slug"])
    res_rest = await session.execute(stmt_rest)
    restaurant = res_rest.scalar_one_or_none()

    if restaurant is None:
        restaurant = Restaurant(
            name=rest_data["name"],
            slug=rest_data["slug"],
            timezone=rest_data.get("timezone", "Europe/Rome"),
            currency=rest_data.get("currency", "EUR"),
            languages=rest_data.get("languages", ["en", "it"]),
            default_language=rest_data.get("default_language", "it"),
            onboarding=rest_data.get("onboarding", {}),
            active=rest_data.get("active", True),
        )
        session.add(restaurant)
        await session.flush()
        print(f"Created restaurant: {restaurant.name} ({restaurant.slug})")
    else:
        restaurant.name = rest_data["name"]
        restaurant.timezone = rest_data.get("timezone", "Europe/Rome")
        restaurant.currency = rest_data.get("currency", "EUR")
        restaurant.languages = rest_data.get("languages", ["en", "it"])
        restaurant.default_language = rest_data.get("default_language", "it")
        if "onboarding" in rest_data:
            restaurant.onboarding = rest_data["onboarding"]
        restaurant.active = rest_data.get("active", True)
        await session.flush()
        print(f"Updated restaurant: {restaurant.name} ({restaurant.slug})")

    # 2. Upsert Dining Tables via explicit query (no relationship traversal)
    stmt_tables = select(DiningTable).where(DiningTable.restaurant_id == restaurant.id)
    res_tables = await session.execute(stmt_tables)
    existing_tables_by_label = {t.label: t for t in res_tables.scalars().all()}

    for t_info in tables_data:
        label = t_info["label"]
        if label in existing_tables_by_label:
            target_table = existing_tables_by_label[label]
            if rotate_qr or not target_table.qr_token:
                target_table.qr_token = secrets.token_urlsafe(12)
        else:
            new_table = DiningTable(
                restaurant_id=restaurant.id,
                label=label,
                qr_token=secrets.token_urlsafe(12),
            )
            session.add(new_table)
    await session.flush()

    # 3. Upsert Menu Items and Translations via explicit query with selectinload
    stmt_items = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(MenuItem.restaurant_id == restaurant.id)
    )
    res_items = await session.execute(stmt_items)
    existing_items_list = list(res_items.scalars().all())
    existing_items_by_id = {m.id: m for m in existing_items_list}

    items_created = 0
    items_updated = 0
    for item_data in items_data:
        item_key = item_data.get("key") or item_data["translations"]["it"]["name"]
        item_uuid = uuid.uuid5(SEED_ITEM_NAMESPACE, f"{restaurant.slug}:{item_key}")
        target_item = existing_items_by_id.get(item_uuid)

        if target_item is None:
            # Fallback: check if existing item has matching Italian translation name
            for m_item in existing_items_list:
                for trans in m_item.translations:
                    if (
                        trans.language == "it"
                        and trans.name == item_data["translations"]["it"]["name"]
                    ):
                        target_item = m_item
                        break
                if target_item is not None:
                    break

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


async def async_main(args: argparse.Namespace) -> None:
    seed_payload = load_seed_data(args.file)
    async with async_session_factory() as session:
        await seed_data(seed_payload, session, rotate_qr=args.rotate_qr)
        await session.commit()
        print("Seed successfully committed to database.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mise database")
    parser.add_argument(
        "--file",
        default="data/seed/trattoria_da_mario.json",
        help="Path to seed JSON file",
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
