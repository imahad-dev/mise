"""Guest payment: per-method totals, the guest's claim and the guest bill."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.schemas.bills import BillLine, GuestBillResponse, TaxPreview

# ASCII only: Unicode digits, control characters and markup are refused.
REFERENCE = re.compile(r"[A-Za-z0-9 _\-./#]{1,64}", re.ASCII)
NEEDS_REFERENCE = {"wallet", "raast", "bank_transfer"}


class MethodPreview(TaxPreview):
    method: str
    label: str


class PaymentClaim(BaseModel):
    method: str
    reference: str | None
    total: Decimal
    claimed_at: datetime


class PaymentDetails(BaseModel):
    raast_id: str | None = None
    jazzcash: str | None = None
    easypaisa: str | None = None
    iban: str | None = None
    account_title: str | None = None
    sample: bool = False


class VoidedLine(BaseModel):
    name: str
    option_label: str | None
    quantity: int


class GuestPaymentRequest(BaseModel):
    method: Literal["cash", "card", "wallet", "raast", "bank_transfer"]
    reference: str | None = Field(None, max_length=64)

    @model_validator(mode="after")
    def _reference_rule(self) -> "GuestPaymentRequest":
        if self.method not in NEEDS_REFERENCE:
            self.reference = None  # cash and card carry no reference
            return self
        ref = (self.reference or "").strip(" ")
        if not ref:
            raise ValueError("A transaction reference is required for this method")
        if not REFERENCE.fullmatch(ref):
            raise ValueError("Reference: 1-64 letters, digits, spaces or _ - . / #")
        self.reference = ref
        return self


class GuestBillDetail(GuestBillResponse):
    lines: list[BillLine]
    subtotal: Decimal
    currency: str
    methods: list[MethodPreview]
    payment_details: PaymentDetails
    claim: PaymentClaim | None
    voided: list[VoidedLine]
    order_status: str | None
    pickup_label: str | None = None
    pay_forward_count: int = 0
