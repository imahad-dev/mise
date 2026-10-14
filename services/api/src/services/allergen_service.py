"""Allergen matching service adhering to EU-14 standards and strict status precedence.

Status precedence (server-authoritative):
1 (highest): contains        — Item allergens ∩ guest allergens_to_avoid ≠ ∅
2:          unverified      — allergen_verified = false (no overlap, but not verified)
3 (lowest):  no_declared_match — allergen_verified = true, no overlap (not a safety guarantee)
"""

from collections.abc import Sequence
from typing import Literal

EU_14_ALLERGENS: tuple[str, ...] = (
    "gluten",
    "milk",
    "eggs",
    "fish",
    "crustaceans",
    "molluscs",
    "tree_nuts",
    "peanuts",
    "soy",
    "celery",
    "mustard",
    "sesame",
    "sulphites",
    "lupin",
)

AllergenStatus = Literal["contains", "unverified", "no_declared_match"]


def compute_allergen_status(
    item_allergens: Sequence[str] | set[str] | None,
    allergen_verified: bool,
    guest_allergens_to_avoid: Sequence[str] | set[str] | None,
) -> AllergenStatus:
    """Compute the allergen status of an item relative to a guest's allergens to avoid.

    Precedence:
    1. contains (if intersection > 0, regardless of verified flag)
    2. unverified (if allergen_verified is False)
    3. no_declared_match (if allergen_verified is True and no intersection)
    """
    item_set = set(item_allergens) if item_allergens is not None else set()
    avoid_set = set(guest_allergens_to_avoid) if guest_allergens_to_avoid is not None else set()

    # Priority 1: contains
    if bool(item_set & avoid_set):
        return "contains"

    # Priority 2: unverified
    if not allergen_verified:
        return "unverified"

    # Priority 3: no declared match
    return "no_declared_match"
