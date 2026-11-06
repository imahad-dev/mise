"""Dish choices: every rule in one place. `item.choice_groups` and their `choices` must be loaded.

A choice can add an allergen and can never remove one.
"""

import re
import uuid
from decimal import Decimal

from fastapi import HTTPException, status

from src.models.menu import MenuChoice, MenuItem

# Whole words: "Freekeh" and "Saffron" are fine, "Nut free" and "Sugar-free" are not.
PROMISES_SAFETY = re.compile(r"\b(free|allergy|allergen|safe)\b", re.IGNORECASE)


def resolve_choices(item: MenuItem, choice_ids: list[uuid.UUID]) -> list[MenuChoice]:
    """The guest's picks for one line, or the refusal the guest must see."""
    if not choice_ids and not item.choice_groups:
        return []
    known = {c.id: c for g in item.choice_groups for c in g.choices}
    if any(i not in known for i in choice_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown choice for {item.id}",
        )
    chosen = [known[i] for i in choice_ids]
    sold_out = [c for c in chosen if not c.available]
    if sold_out:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "unavailable_choices",
                "unavailable_choices": [
                    {"menu_item_id": str(item.id), "choice_id": str(c.id), "label": c.label}
                    for c in sold_out
                ],
            },
        )
    picked = set(choice_ids)
    for g in item.choice_groups:
        count = sum(c.id in picked for c in g.choices)
        if not g.min_select <= count <= g.max_select:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"error": "choices_changed", "menu_item_id": str(item.id)},
            )
    return chosen


def can_be_ordered(item: MenuItem) -> bool:
    """False when a required group no longer has enough available choices."""
    return all(sum(c.available for c in g.choices) >= g.min_select for g in item.choice_groups)


def line_allergens(item: MenuItem, choices: list[MenuChoice]) -> tuple[list[str], bool]:
    """The union of dish and choice allergens, and whether all of it is confirmed."""
    allergens = list(item.allergens)
    for c in choices:
        allergens += [a for a in c.allergens if a not in allergens]
    return allergens, item.allergen_verified and all(c.allergen_verified for c in choices)


def snapshot_choices(item: MenuItem, choices: list[MenuChoice]) -> list[dict]:
    """JSON for `order_item.choices`, in menu order."""
    picked = {c.id for c in choices}
    return [
        {
            "choice_id": str(c.id),
            "group": g.label,
            "kind": g.kind,
            "label": c.label,
            "price_delta": str(c.price_delta),
            "cost_delta": str(c.cost_delta),
            "allergens": list(c.allergens),
        }
        for g in item.choice_groups
        for c in g.choices
        if c.id in picked
    ]


def check_label(label: str) -> None:
    if PROMISES_SAFETY.search(label):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='A choice can\'t promise safety. Write "No sugar", not "Sugar free".',
        )


def check_choice(
    kind: str, *, price_delta: Decimal, cost_delta: Decimal, allergens: list[str]
) -> None:
    if kind == "leave_out" and (price_delta or cost_delta or allergens):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Leaving something out is free and carries no allergens",
        )
