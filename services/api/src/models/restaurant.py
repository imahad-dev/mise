"""Restaurant database model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Restaurant(Base):
    __tablename__ = "restaurant"
    __table_args__ = (
        CheckConstraint(
            "(default_language = ANY(languages)) IS TRUE", name="chk_restaurant_default_language"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'Europe/Rome'")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'EUR'"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{en}'"),
    )
    default_language: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    menu_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    onboarding: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    tables: Mapped[list["DiningTable"]] = relationship(  # noqa: F821
        "DiningTable",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(  # noqa: F821
        "MenuItem",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    guest_sessions: Mapped[list["GuestSession"]] = relationship(  # noqa: F821
        "GuestSession",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        "Order",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )
