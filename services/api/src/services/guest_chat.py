"""Guest chat service — LLM-powered menu assistant.

Builds context from the restaurant menu (never the guest's allergen profile), calls LLM,
validates structured response, records metrics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.inference.metrics import record_metrics
from src.inference.rate_limit import check_guest_chat_limit
from src.models.menu import MenuItem
from src.schemas.guest import AIChatResult

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.inference.client import InferenceClient

logger = logging.getLogger(__name__)


def _build_menu_context(items: list[MenuItem], language: str) -> str:
    """Build a concise menu summary for the system prompt."""
    lines: list[str] = []
    for item in items:
        if not item.available:
            continue
        trans = next((t for t in item.translations if t.language == language), None)
        if not trans and item.translations:
            trans = item.translations[0]
        name = trans.name if trans else "?"
        allergen_str = ", ".join(item.allergens) if item.allergens else "none"
        lines.append(
            f"- {name} (€{item.price}, allergens: {allergen_str}, "
            f"{'V' if item.is_vegetarian else ''}{'VG' if item.is_vegan else ''}"
            f"{'GF' if item.is_gluten_free else ''})"
        )
    return "\n".join(lines) if lines else "No menu items available."


async def handle_guest_chat(
    *,
    inference: InferenceClient,
    db: AsyncSession,
    restaurant_id: uuid.UUID,
    session_id: uuid.UUID,
    guest_language: str,
    message: str,
) -> dict:
    """Process a guest chat message and return AI response.

    Privacy: the guest's allergen and dietary profile is never sent to the model. Allergen
    safety is shown by the deterministic allergen filter, not by the chat.

    Returns dict with 'reply' and 'suggested_items'.
    """
    # Enforce per-session rate limit
    await check_guest_chat_limit(str(session_id))

    # Fetch menu for context
    stmt = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.deleted_at.is_(None),
        )
        .order_by(MenuItem.sort_order)
    )
    res = await db.execute(stmt)
    items = list(res.scalars().all())

    menu_context = _build_menu_context(items, guest_language)

    system_prompt = (
        f"You are a friendly restaurant menu assistant. "
        f"Respond in {guest_language}. "
        "Never claim a dish is safe for an allergy; tell the guest to use the menu's "
        "allergen filter and to confirm with staff.\n\n"
        f"Current menu:\n{menu_context}\n\n"
        f"Return a JSON object with 'reply' (string) and "
        f"'suggested_items' (array of objects with 'name' and 'reason')."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    result, metrics = await inference.chat(
        messages,
        schema=AIChatResult,
        response_format={"type": "json_object"},
    )

    # Record metrics
    await record_metrics(db, metrics)

    # Normalize result
    if isinstance(result, dict):
        return {
            "reply": result.get("reply", ""),
            "suggested_items": result.get("suggested_items", []),
        }
    return result.model_dump()
