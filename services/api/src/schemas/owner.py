"""Owner schemas for menu items and table management."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OwnerMenuTranslation(BaseModel):
    language: str
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OwnerMenuItemResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    category: str
    price: Decimal
    unit_cost: Decimal
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
    translations: list[OwnerMenuTranslation]
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PatchMenuItemRequest(BaseModel):
    price: Decimal | None = Field(default=None, ge=Decimal("0.00"), allow_inf_nan=False)
    unit_cost: Decimal | None = Field(default=None, ge=Decimal("0.00"), allow_inf_nan=False)
    available: bool | None = None
    featured: bool | None = None
    sort_order: int | None = None
    ingredients: list[str] | None = None
    allergens: list[str] | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    is_gluten_free: bool | None = None


class OwnerTableResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    label: str
    qr_token: str
    guest_url: str

    model_config = ConfigDict(from_attributes=True)


class StatusOkResponse(BaseModel):
    status: Literal["ok"]
