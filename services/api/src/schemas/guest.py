"""Guest session and menu schemas."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

EU14Allergen = Literal[
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
]

DietaryPreference = Literal["vegetarian", "vegan", "gluten_free"]
SupportedLanguage = Literal["en", "it"]


class CreateGuestSessionRequest(BaseModel):
    qr_token: str
    language: SupportedLanguage = "it"
    dietary_preferences: list[DietaryPreference] = []
    allergens_to_avoid: list[EU14Allergen] = []


class PatchGuestSessionRequest(BaseModel):
    language: SupportedLanguage | None = None
    dietary_preferences: list[DietaryPreference] | None = None
    allergens_to_avoid: list[EU14Allergen] | None = None


class GuestSessionResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    table_id: uuid.UUID | None
    language: str
    dietary_preferences: list[str]
    allergens_to_avoid: list[str]
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GuestMenuItemResponse(BaseModel):
    id: uuid.UUID
    category: str
    price: Decimal
    name: str
    description: str | None = None
    ingredients: list[str]
    allergens: list[str]
    allergen_verified: bool
    dietary_verified: bool
    is_vegetarian: bool
    is_vegan: bool
    is_gluten_free: bool
    available: bool
    featured: bool
    sort_order: int
    image_url: str | None = None
    allergen_status: str
    matched_allergens: list[str]

    # Explicitly guarantee unit_cost is not in schema
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class GuestMenuResponse(BaseModel):
    items: list[GuestMenuItemResponse]
