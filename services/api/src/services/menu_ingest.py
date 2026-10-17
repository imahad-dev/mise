"""Menu ingest service — VLM-powered menu photo analysis.

Orchestrates: image → VLM call → parse structured JSON → create MenuItems + Translations.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.inference.metrics import record_metrics
from src.models.audit import AuditLog
from src.models.menu import MenuItem, MenuTranslation
from src.schemas.owner import AIMenuIngestResult

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.inference.client import InferenceClient

logger = logging.getLogger(__name__)

_INGEST_SYSTEM_PROMPT = (
    "You are a restaurant menu analysis assistant. "
    "Analyze the provided menu image and extract structured data for each dish. "
    "Return a JSON object with an 'items' array. Each item must have: "
    "name (string), description (string or null), category (string), "
    "price (number), unit_cost (number, estimate if unknown), "
    "ingredients (string array), allergens (string array from EU-14: "
    "gluten, milk, eggs, fish, crustaceans, molluscs, tree_nuts, peanuts, "
    "soy, celery, mustard, sesame, sulphites, lupin), "
    "is_vegetarian (bool), is_vegan (bool), is_gluten_free (bool)."
)


async def ingest_menu_from_image(
    *,
    inference: InferenceClient,
    db: AsyncSession,
    restaurant_id: uuid.UUID,
    image_url: str,
    language: str,
) -> list[MenuItem]:
    """Analyze a menu image via VLM and create menu items.

    Returns the list of created MenuItem objects with translations loaded.
    """
    messages = [
        {"role": "system", "content": _INGEST_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Analyze this menu photo. Language: {language}"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]

    result, metrics = await inference.vision(
        messages,
        schema=AIMenuIngestResult,
    )

    # Parse items from result (could be dict or Pydantic model)
    if isinstance(result, dict):
        items_data = result.get("items", [])
    else:
        items_data = [item.model_dump() for item in result.items]

    created_items: list[MenuItem] = []
    for item_data in items_data:
        if isinstance(item_data, dict):
            parsed = item_data
        else:
            parsed = item_data.model_dump() if hasattr(item_data, "model_dump") else dict(item_data)

        menu_item = MenuItem(
            restaurant_id=restaurant_id,
            category=parsed.get("category", "other"),
            price=Decimal(str(parsed.get("price", 0))),
            unit_cost=Decimal(str(parsed.get("unit_cost", 0))),
            ingredients=parsed.get("ingredients", []),
            allergens=parsed.get("allergens", []),
            is_vegetarian=parsed.get("is_vegetarian", False),
            is_vegan=parsed.get("is_vegan", False),
            is_gluten_free=parsed.get("is_gluten_free", False),
            allergen_verified=False,
            dietary_verified=False,
        )
        db.add(menu_item)
        await db.flush()

        translation = MenuTranslation(
            menu_item_id=menu_item.id,
            language=language,
            name=parsed.get("name", "Unnamed"),
            description=parsed.get("description"),
        )
        db.add(translation)
        created_items.append(menu_item)

    # Audit log
    audit = AuditLog(
        restaurant_id=restaurant_id,
        event_type="ai_menu_ingest",
        actor="owner",
        payload={
            "image_url": image_url,
            "language": language,
            "items_created": len(created_items),
        },
    )
    db.add(audit)
    await db.commit()

    # Record metrics after commit
    await record_metrics(db, metrics)

    # Re-fetch with translations loaded
    item_ids = [item.id for item in created_items]
    stmt = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(MenuItem.id.in_(item_ids))
        .order_by(MenuItem.sort_order)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
