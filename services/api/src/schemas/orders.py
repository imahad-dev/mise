"""Order schemas for guest ordering."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderItemRequest(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(..., ge=1, le=20)
    notes: str | None = Field(default=None, max_length=500)


class CreateOrderRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)
    items: list[OrderItemRequest] = Field(..., min_length=1, max_length=50)
    acknowledge_allergen_risk: bool = False


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    item_name: str
    kitchen_name: str
    allergens: list[str]
    allergen_verified: bool
    allergen_status: str
    notes: str | None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OrderResponse(BaseModel):
    id: uuid.UUID
    guest_session_id: uuid.UUID
    restaurant_id: uuid.UUID
    table_id: uuid.UUID | None
    status: str
    total: Decimal
    idempotency_key: str
    allergen_conflict_acknowledged: bool
    allergens_to_avoid: list[str]
    dietary_preferences: list[str]
    placed_at: datetime
    bumped_at: datetime | None
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True, extra="forbid")
