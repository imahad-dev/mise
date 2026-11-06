"""Order and order item database models."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_payment', 'pending_approval', 'placed', 'bumped', 'cancelled')",
            name="chk_orders_status",
        ),
        CheckConstraint("total >= 0", name="chk_orders_total"),
        CheckConstraint(
            "allergens_to_avoid <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_orders_allergens",
        ),
        CheckConstraint(
            "dietary_preferences <@ ARRAY['vegetarian','vegan','gluten_free']::text[]",
            name="chk_orders_dietary",
        ),
        CheckConstraint(
            "(status <> 'bumped') OR (bumped_at IS NOT NULL)",
            name="chk_orders_bumped_at_required",
        ),
        CheckConstraint("source IN ('live', 'simulated', 'pay_forward')", name="chk_orders_source"),
        CheckConstraint("voided_at IS NULL OR status = 'cancelled'", name="chk_orders_void"),
        CheckConstraint(
            "void_kind IN ('staff', 'declined', 'table_closed')", name="chk_orders_void_kind"
        ),
        CheckConstraint("collected_at IS NULL OR status = 'bumped'", name="chk_orders_collected"),
        UniqueConstraint(
            "guest_session_id", "idempotency_key", name="orders_guest_idempotency_key"
        ),
        Index("idx_orders_restaurant_id", "restaurant_id"),
        Index("idx_orders_guest_session_id", "guest_session_id"),
        Index("idx_orders_table_id", "table_id"),
        Index("idx_orders_kitchen_query", "restaurant_id", "status", "placed_at"),
        Index("idx_orders_analytics", "restaurant_id", "source", "placed_at"),
        Index("idx_orders_bill_id", "bill_id"),
        Index("idx_orders_sitting_id", "sitting_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    guest_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("guest_session.id", ondelete="RESTRICT"),
        nullable=False,
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
    bill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bills.id", ondelete="SET NULL"),
        nullable=True,
    )
    sitting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sitting.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'placed'"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'live'"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    allergen_conflict_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    allergens_to_avoid: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    dietary_preferences: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    bumped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who cancelled it, for the guest: void_reason is free text typed by staff.
    void_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    restaurant: Mapped["Restaurant"] = relationship(  # noqa: F821
        "Restaurant", back_populates="orders", lazy="raise"
    )
    guest_session: Mapped["GuestSession"] = relationship("GuestSession", lazy="raise")  # noqa: F821
    table: Mapped["DiningTable | None"] = relationship("DiningTable", lazy="raise")  # noqa: F821
    sitting: Mapped["TableSitting | None"] = relationship("TableSitting", lazy="raise")  # noqa: F821
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class OrderItem(Base):
    __tablename__ = "order_item"
    __table_args__ = (
        CheckConstraint("quantity >= 1 AND quantity <= 20", name="chk_order_item_quantity"),
        CheckConstraint("unit_price >= 0 AND unit_cost >= 0", name="chk_order_item_unit_prices"),
        CheckConstraint(
            "notes IS NULL OR length(notes) <= 500", name="chk_order_item_notes_length"
        ),
        CheckConstraint(
            "allergen_status IN ('contains', 'unverified', 'no_declared_match')",
            name="chk_order_item_allergen_status",
        ),
        CheckConstraint(
            "allergens <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_order_item_allergens",
        ),
        Index("idx_order_item_order_id", "order_id"),
        Index("idx_order_item_menu_item_id", "menu_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_item_option.id", ondelete="SET NULL"),
        nullable=True,
    )
    option_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Immutable snapshot of what the guest chose: old bills never change.
    choices: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    kitchen_name: Mapped[str] = mapped_column(Text, nullable=False)
    allergens: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    allergen_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allergen_status: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The item's pay-it-forward flag when ordered: settle credits this, not the current flag.
    is_pay_forward: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items", lazy="raise")
    menu_item: Mapped["MenuItem"] = relationship("MenuItem", lazy="raise")  # noqa: F821
