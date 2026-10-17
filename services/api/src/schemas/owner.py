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


# --- Checkpoint D: AI schemas ---


class MenuIngestRequest(BaseModel):
    """Request to analyze a menu photo or text via AI."""

    image_url: str
    language: str = "it"


class AIMenuItemParsed(BaseModel):
    """Structured output expected from VLM menu analysis."""

    name: str
    description: str | None = None
    category: str = "other"
    price: float = 0.0
    unit_cost: float = 0.0
    ingredients: list[str] = []
    allergens: list[str] = []
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_gluten_free: bool = False


class AIMenuIngestResult(BaseModel):
    """Top-level wrapper for VLM ingest response."""

    items: list[AIMenuItemParsed]


class MenuIngestResponse(BaseModel):
    """Response after AI menu ingest — created item IDs."""

    created_count: int
    items: list[OwnerMenuItemResponse]


class DailyBriefAction(BaseModel):
    type: str
    item: str
    reason: str


class DailyBriefResponse(BaseModel):
    date: str
    summary: str
    actions: list[DailyBriefAction]


class SimulateRequest(BaseModel):
    scenario: str = "weekend_rush"
    parameters: dict | None = None


class SimulateRecommendation(BaseModel):
    action: str
    item: str | None = None
    shift: str | None = None
    quantity: int | None = None
    extra_staff: int | None = None


class SimulateResponse(BaseModel):
    scenario: str
    predicted_covers: int
    predicted_revenue_eur: float
    recommendations: list[SimulateRecommendation]

