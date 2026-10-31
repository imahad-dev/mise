"""Order schemas for guest ordering."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ITEMS_PER_ORDER = 30  # portions across all lines


class OrderItemRequest(BaseModel):
    menu_item_id: uuid.UUID
    option_id: uuid.UUID | None = None
    quantity: int = Field(..., ge=1, le=20)
    notes: str | None = Field(default=None, max_length=500)


class CreateOrderRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)
    items: list[OrderItemRequest] = Field(..., min_length=1, max_length=50)
    acknowledge_allergen_risk: bool = False
    # The table's 4-digit code, read aloud by the waiter; only asked once per phone and visit.
    code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")

    @model_validator(mode="after")
    def _within_item_cap(self) -> "CreateOrderRequest":
        if sum(i.quantity for i in self.items) > MAX_ITEMS_PER_ORDER:
            raise ValueError("That's a big order! Please ask your waiter.")
        return self


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    option_id: uuid.UUID | None
    option_label: str | None
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
    currency: str
    idempotency_key: str
    allergen_conflict_acknowledged: bool
    allergens_to_avoid: list[str]
    dietary_preferences: list[str]
    placed_at: datetime
    bumped_at: datetime | None
    items: list[OrderItemResponse]
    # The visit's orders waiting for the waiter add up to more than the venue's first-order cap.
    over_first_order_cap: bool = False

    model_config = ConfigDict(from_attributes=True, extra="forbid")
