"""Seed database from JSON file.

Usage:
    docker compose exec -T api python scripts/seed.py [--file data/seed/trattoria_da_mario.json]
"""

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
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
        path = Path.cwd() / path

    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


async def seed_data(data: dict[str, Any]) -> None:
    """Seed restaurant, tables, menu items, and translations into database."""
    rest_data = data["restaurant"]
    tables_data = data.get("tables", [])
    items_data = data.get("items", [])

    async with async_session_factory() as session:
        # 1. Upsert Restaurant
        stmt = (
            select(Restaurant)
            .options(
                selectinload(Restaurant.tables),
                selectinload(Restaurant.menu_items).selectinload(MenuItem.translations),
            )
            .where(Restaurant.slug == rest_data["slug"])
        )
        res = await session.execute(stmt)
        restaurant = res.scalar_one_or_none()

        if restaurant is None:
            restaurant = Restaurant(
                name=rest_data["name"],
                slug=rest_data["slug"],
                timezone=rest_data.get("timezone", "Europe/Rome"),
                currency=rest_data.get("currency", "EUR"),
                languages=rest_data.get("languages", ["en", "it"]),
                default_language=rest_data.get("default_language", "it"),
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
            restaurant.active = rest_data.get("active", True)
            await session.flush()
            print(f"Updated restaurant: {restaurant.name} ({restaurant.slug})")

        # 2. Upsert Dining Tables
        existing_tables_by_token = {t.qr_token: t for t in restaurant.tables}
        for t_info in tables_data:
            qr_token = t_info["qr_token"]
            label = t_info["label"]
            if qr_token in existing_tables_by_token:
                existing_tables_by_token[qr_token].label = label
            else:
                new_table = DiningTable(
                    restaurant_id=restaurant.id,
                    label=label,
                    qr_token=qr_token,
                )
                session.add(new_table)
        await session.flush()
        print(f"Seeded {len(tables_data)} dining tables.")

        # 3. Upsert Menu Items and Translations
        existing_items = {m_item.id: m_item for m_item in restaurant.menu_items}

        items_created = 0
        items_updated = 0
        for item_data in items_data:
            item_key = item_data.get("key") or item_data["translations"]["it"]["name"]
            item_uuid = uuid.uuid5(SEED_ITEM_NAMESPACE, f"{restaurant.slug}:{item_key}")
            target_item = existing_items.get(item_uuid)

            if target_item is None:
                # Fallback: check if existing item has matching Italian translation name
                for m_item in restaurant.menu_items:
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
                target_item.allergen_verified = item_data.get(
                    "allergen_verified", False
                )
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

        await session.commit()
        total_items = len(items_data)
        print(
            f"Menu items seed finished: {items_created} created, {items_updated} updated (total {total_items} items)."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mise database")
    parser.add_argument(
        "--file",
        default="data/seed/trattoria_da_mario.json",
        help="Path to seed JSON file",
    )
    args = parser.parse_args()
    seed_payload = load_seed_data(args.file)
    asyncio.run(seed_data(seed_payload))


if __name__ == "__main__":
    main()
