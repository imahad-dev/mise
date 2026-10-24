"""Bill schemas: staff list/detail/settle and the guest bill status."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class BillLine(BaseModel):
    name: str
    option_label: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class TaxPreview(BaseModel):
    payment_class: Literal["standard", "digital"]
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal


class BillSummary(BaseModel):
    id: uuid.UUID
    bill_no: int | None
    table_label: str | None
    status: str
    opened_at: datetime
    order_count: int
    subtotal: Decimal
    bill_requested_at: datetime | None


class BillListResponse(BaseModel):
    bills: list[BillSummary]
    restaurant_timezone: str


class BillDetail(BillSummary):
    lines: list[BillLine]
    preview_standard: TaxPreview | None
    preview_digital: TaxPreview | None
    payment_method: str | None
    payment_reference: str | None
    tax_jurisdiction: str | None
    tax_rate: Decimal | None
    tax_amount: Decimal | None
    total: Decimal | None
    settled_at: datetime | None
    restaurant_name: str
    restaurant_city: str | None
    restaurant_timezone: str
    currency: str


class SettleBillRequest(BaseModel):
    payment_method: Literal["cash", "card", "wallet", "raast", "bank_transfer"]
    payment_reference: str | None = Field(default=None, max_length=64)


class GuestBillResponse(BaseModel):
    bill_no: int | None
    status: str
    bill_requested_at: datetime | None
