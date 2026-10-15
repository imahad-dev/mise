"""Kitchen display and bump/recall schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KitchenOrderItemResponse(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    kitchen_name: str
    quantity: int
    notes: str | None
    allergens: list[str]
    allergen_status: str
    allergen_verified: bool
    conflict_with_order_allergens: bool
    matched_allergens: list[str]

    model_config = ConfigDict(from_attributes=True)


class KitchenOrderResponse(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    table_id: uuid.UUID | None
    table_label: str | None = None
    status: str
    allergens_to_avoid: list[str]
    dietary_preferences: list[str]
    allergen_conflict_acknowledged: bool
    placed_at: datetime
    bumped_at: datetime | None
    items: list[KitchenOrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class KitchenOrdersListResponse(BaseModel):
    orders: list[KitchenOrderResponse]
