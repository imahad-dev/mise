"""Guest payment: per-method totals, the guest's claim and the guest bill."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.schemas.bills import REFERENCE, BillLine, GuestBillResponse, MethodPreview, PaymentClaim
from src.schemas.orders import LineChoice

NEEDS_REFERENCE = {"wallet", "raast", "bank_transfer"}


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
    choices: list[LineChoice] = []


class GuestPaymentRequest(BaseModel):
    method: Literal["cash", "card", "wallet", "raast", "bank_transfer"]
    reference: str | None = Field(None, max_length=64)
    service_included: bool = False

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
    service_charge_rate: Decimal
    service_charge_amount: Decimal
    payment_details: PaymentDetails
    claim: PaymentClaim | None
    voided: list[VoidedLine]
    order_status: str | None
    # What was paid: set only once the bill is settled (its snapshot).
    payment_method: str | None = None
    tax_rate: Decimal | None = None
    # True when the settled bill's VAT was inside the prices (UK, Dubai).
    tax_included: bool = False
    total: Decimal | None = None
    pickup_label: str | None = None
    pay_forward_count: int = 0
