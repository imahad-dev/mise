"""Table sitting: one party's visit to one table, from staff open to close."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class TableSitting(Base):
    __tablename__ = "table_sitting"
    __table_args__ = (
        CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('settled', 'cancelled', 'staff_closed', 'idle_timeout')",
            name="chk_table_sitting_close_reason",
        ),
        CheckConstraint(
            "(closed_at IS NULL) = (close_reason IS NULL)",
            name="chk_table_sitting_closed_pair",
        ),
        CheckConstraint("code IS NULL OR code ~ '^[0-9]{4}$'", name="chk_table_sitting_code"),
        Index("idx_table_sitting_table_id", "table_id"),
        Index(
            "uq_table_sitting_open_per_table",
            "table_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dining_table.id", ondelete="CASCADE"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    table: Mapped["DiningTable"] = relationship("DiningTable", lazy="raise")  # noqa: F821
