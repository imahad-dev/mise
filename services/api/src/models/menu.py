"""Menu item and translation database models."""

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
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class MenuItem(Base):
    __tablename__ = "menu_item"
    __table_args__ = (
        CheckConstraint(
            "allergens <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_menu_item_allergens",
        ),
        CheckConstraint(
            "NOT (is_vegan AND NOT is_vegetarian)",
            name="chk_menu_item_vegan_implies_vegetarian",
        ),
        CheckConstraint(
            "NOT (is_gluten_free AND 'gluten' = ANY(allergens))",
            name="chk_menu_item_gluten_free_contradiction",
        ),
        CheckConstraint(
            "NOT is_vegan OR NOT ("
            "allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[])",
            name="chk_menu_item_vegan_contradiction",
        ),
        CheckConstraint(
            "NOT is_vegetarian OR NOT ("
            "allergens && ARRAY['fish','crustaceans','molluscs']::text[])",
            name="chk_menu_item_vegetarian_contradiction",
        ),
        CheckConstraint(
            "price >= 0 AND unit_cost >= 0",
            name="chk_menu_item_price_positive",
        ),
        Index("idx_menu_item_restaurant_id", "restaurant_id"),
        Index(
            "idx_menu_item_active",
            "restaurant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # At most one live pay-it-forward item per venue: give hands out exactly that one.
        Index(
            "uq_menu_item_pay_forward",
            "restaurant_id",
            unique=True,
            postgresql_where=text("is_pay_forward AND deleted_at IS NULL"),
        ),
        Index(
            "idx_menu_item_listing",
            "restaurant_id",
            "available",
            "sort_order",
            postgresql_where=text("deleted_at IS NULL"),
        ),
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
    category: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    ingredients: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    allergens: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    allergen_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegetarian: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_gluten_free: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    dietary_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Bought for someone else: settling writes a pay_forward 'bought' row per line.
    is_pay_forward: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        "Restaurant", back_populates="menu_items", lazy="raise"
    )
    translations: Mapped[list["MenuTranslation"]] = relationship(
        "MenuTranslation",
        back_populates="menu_item",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    options: Mapped[list["MenuItemOption"]] = relationship(
        "MenuItemOption",
        back_populates="menu_item",
        cascade="all, delete-orphan",
        order_by="MenuItemOption.sort_order",
        lazy="raise",
    )
    choice_groups: Mapped[list["MenuChoiceGroup"]] = relationship(
        "MenuChoiceGroup",
        back_populates="menu_item",
        cascade="all, delete-orphan",
        order_by="MenuChoiceGroup.sort_order",
        lazy="raise",
    )


class MenuItemOption(Base):
    __tablename__ = "menu_item_option"
    __table_args__ = (
        CheckConstraint("price >= 0", name="chk_menu_item_options_price"),
        CheckConstraint("unit_cost >= 0", name="chk_menu_item_options_cost"),
        UniqueConstraint("menu_item_id", "label", name="uq_menu_item_options_label"),
        Index("idx_menu_item_options_item", "menu_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="options", lazy="raise")


class MenuTranslation(Base):
    __tablename__ = "menu_translation"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "language", name="menu_translation_item_lang_key"),
        Index("idx_menu_translation_item_id", "menu_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem", back_populates="translations", lazy="raise"
    )


ALLERGEN_CHECK = (
    "ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
    "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]"
)


class MenuChoiceGroup(Base):
    __tablename__ = "menu_choice_group"
    __table_args__ = (
        CheckConstraint("kind IN ('pick', 'add', 'leave_out')", name="chk_choice_group_kind"),
        CheckConstraint(
            "min_select >= 0 AND max_select >= 1 AND min_select <= max_select",
            name="chk_choice_group_select",
        ),
        UniqueConstraint("menu_item_id", "label", name="uq_choice_group_label"),
        Index("idx_choice_group_item", "menu_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_item.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, nullable=False)
    max_select: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem", back_populates="choice_groups", lazy="raise"
    )
    choices: Mapped[list["MenuChoice"]] = relationship(
        "MenuChoice",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="MenuChoice.sort_order",
        lazy="raise",
    )


class MenuChoice(Base):
    __tablename__ = "menu_choice"
    __table_args__ = (
        CheckConstraint("price_delta >= 0 AND cost_delta >= 0", name="chk_choice_money"),
        CheckConstraint(f"allergens <@ {ALLERGEN_CHECK}", name="chk_choice_allergens"),
        CheckConstraint("NOT (is_vegan AND NOT is_vegetarian)", name="chk_choice_vegan_vegetarian"),
        CheckConstraint(
            "NOT is_vegan OR NOT ("
            "allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[])",
            name="chk_choice_vegan_allergens",
        ),
        UniqueConstraint("group_id", "label", name="uq_choice_label"),
        Index("idx_choice_group", "group_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_choice_group.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    cost_delta: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    allergens: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    # All three default to false: the safe answer for a choice nobody has confirmed.
    allergen_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegetarian: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    group: Mapped["MenuChoiceGroup"] = relationship(
        "MenuChoiceGroup", back_populates="choices", lazy="raise"
    )
