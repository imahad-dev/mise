"""Bill schemas: staff list/detail/settle and the guest bill status."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Method = Literal["cash", "card", "wallet", "raast", "bank_transfer"]


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


class PaymentClaim(BaseModel):
    method: str
    reference: str | None
    total: Decimal
    claimed_at: datetime


class BillOrder(BaseModel):
    order_id: uuid.UUID
    placed_at: datetime
    status: str
    device_label: str
    joined_late: bool
    voided: bool
    void_reason: str | None
    lines: list[BillLine]


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
    claim: PaymentClaim | None
    # Bill total for the claimed method now, minus what the guest said they sent; >0 still due.
    amount_due_after_claim: Decimal | None
    reused_reference_bill_no: int | None
    orders: list[BillOrder]
    settled_by_name: str | None


class SettleBillRequest(BaseModel):
    payment_method: Method
    payment_reference: str | None = Field(default=None, max_length=64)
    # What the staff member saw: the server refuses with 409 if its recomputation differs.
    expected_total: Decimal
    expected_method: Method
    acknowledge_reused_reference: bool = False

    @model_validator(mode="after")
    def _same_method(self) -> "SettleBillRequest":
        if self.expected_method != self.payment_method:
            raise ValueError("expected_method must equal payment_method")
        return self


class VoidOrderRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 200:
            raise ValueError("Reason: 1-200 characters")
        return v


class GuestBillResponse(BaseModel):
    bill_no: int | None
    status: str
    bill_requested_at: datetime | None
