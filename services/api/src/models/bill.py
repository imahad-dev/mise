"""Table bill: the orders of one table sitting, settled once with a tax snapshot."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'settled', 'cancelled')", name="chk_bills_status"),
        CheckConstraint("source IN ('live', 'simulated')", name="chk_bills_source"),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN "
            "('cash','card','wallet','raast','bank_transfer')",
            name="chk_bills_payment_method",
        ),
        CheckConstraint(
            "source = 'simulated' OR bill_no IS NOT NULL", name="chk_bills_live_number"
        ),
        CheckConstraint(
            "status <> 'settled' OR (payment_method IS NOT NULL AND total IS NOT NULL "
            "AND settled_at IS NOT NULL)",
            name="chk_bills_settled_complete",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR cancelled_at IS NOT NULL",
            name="chk_bills_cancelled_complete",
        ),
        CheckConstraint(
            "claimed_method IS NULL OR claimed_method IN "
            "('cash','card','wallet','raast','bank_transfer')",
            name="chk_bills_claimed_method",
        ),
        CheckConstraint(
            "claimed_reference IS NULL OR length(claimed_reference) <= 64",
            name="chk_bills_claimed_reference_len",
        ),
        CheckConstraint(
            "payment_reference IS NULL OR length(payment_reference) <= 64",
            name="chk_bills_reference_len",
        ),
        CheckConstraint(
            "service_charge_rate >= 0 AND service_charge_rate <= 0.20 "
            "AND service_charge_amount >= 0",
            name="chk_bills_service_charge",
        ),
        CheckConstraint("tax_pricing IN ('on_top', 'included')", name="chk_bills_tax_pricing"),
        CheckConstraint("(pickup_no IS NULL) = (pickup_day IS NULL)", name="chk_bills_pickup_pair"),
        UniqueConstraint("restaurant_id", "bill_no", name="uq_bills_restaurant_bill_no"),
        UniqueConstraint("restaurant_id", "pickup_day", "pickup_no", name="uq_bills_pickup_no"),
        Index(
            "uq_bills_one_open_per_table",
            "table_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("idx_bills_restaurant_status", "restaurant_id", "status", "opened_at"),
        Index("idx_bills_table_settled", "table_id", "settled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dining_table.id", ondelete="SET NULL"), nullable=True
    )
    bill_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Counter bills only: the guest's pickup number, per venue per local day.
    pickup_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    pickup_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'live'"))
    bill_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tax_jurisdiction: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    tax_pricing: Mapped[str | None] = mapped_column(Text, nullable=True)  # on_top | included
    service_charge_rate: Mapped[Decimal] = mapped_column(
        Numeric(4, 4), nullable=False, server_default=text("0")
    )
    service_charge_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    # The guest's choice on the optional service charge, with their payment claim.
    claimed_service_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    claimed_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
