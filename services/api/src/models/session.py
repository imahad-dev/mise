"""Guest session database model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class GuestSession(Base):
    __tablename__ = "guest_session"
    __table_args__ = (
        CheckConstraint(
            "allergens_to_avoid <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_guest_session_allergens",
        ),
        CheckConstraint(
            "dietary_preferences <@ ARRAY['vegetarian','vegan','gluten_free']::text[]",
            name="chk_guest_session_dietary",
        ),
        Index("idx_guest_session_restaurant_id", "restaurant_id"),
        Index("idx_guest_session_table_id", "table_id"),
        Index("idx_guest_session_cleanup", "restaurant_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurant.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dining_table.id", ondelete="SET NULL"),
        nullable=True,
    )
    language: Mapped[str] = mapped_column(Text, nullable=False)
    dietary_preferences: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    allergens_to_avoid: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
    restaurant: Mapped["Restaurant"] = relationship(  # noqa: F821
        "Restaurant", back_populates="guest_sessions"
    )
    table: Mapped["DiningTable | None"] = relationship("DiningTable")  # noqa: F821
