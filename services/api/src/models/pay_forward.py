"""Pay-it-forward ledger: chai bought by guests for someone else, and handed out by staff."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PayForward(Base):
    __tablename__ = "pay_forward"
    __table_args__ = (
        CheckConstraint("kind IN ('bought','given')", name="chk_pay_forward_kind"),
        CheckConstraint("quantity > 0", name="chk_pay_forward_quantity"),
        Index("idx_pay_forward_restaurant", "restaurant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
