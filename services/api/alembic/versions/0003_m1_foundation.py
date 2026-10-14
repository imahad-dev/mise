"""M1 foundation tables: restaurant, dining_table, menu_item, menu_translation,
guest_session, orders, order_item, audit_log.

Revision ID: 0003_m1_foundation
Revises: 0002_uuid_default
Create Date: 2026-10-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_m1_foundation"
down_revision: str | None = "0002_uuid_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. restaurant
    op.create_table(
        "restaurant",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'Europe/Rome'"), nullable=False),
        sa.Column("currency", sa.Text(), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{en}'"),
            nullable=False,
        ),
        sa.Column("default_language", sa.Text(), server_default=sa.text("'en'"), nullable=False),
        sa.Column("menu_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("onboarding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(default_language = ANY(languages)) IS TRUE",
            name="chk_restaurant_default_language",
        ),
        sa.PrimaryKeyConstraint("id", name="restaurant_pkey"),
        sa.UniqueConstraint("slug", name="restaurant_slug_key"),
    )

    # 2. dining_table
    op.create_table(
        "dining_table",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "restaurant_id",
            sa.UUID(),
            sa.ForeignKey(
                "restaurant.id", ondelete="CASCADE", name="fk_dining_table_restaurant_id"
            ),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("qr_token", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="dining_table_pkey"),
        sa.UniqueConstraint("qr_token", name="dining_table_qr_token_key"),
    )
    op.create_index("idx_dining_table_restaurant_id", "dining_table", ["restaurant_id"])

    # 3. menu_item
    op.create_table(
        "menu_item",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "restaurant_id",
            sa.UUID(),
            sa.ForeignKey("restaurant.id", ondelete="CASCADE", name="fk_menu_item_restaurant_id"),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "ingredients",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "allergens",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "allergen_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_vegetarian", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_vegan", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_gluten_free", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "dietary_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allergens <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_menu_item_allergens",
        ),
        sa.CheckConstraint(
            "NOT (is_vegan AND NOT is_vegetarian)",
            name="chk_menu_item_vegan_implies_vegetarian",
        ),
        sa.CheckConstraint(
            "NOT (is_gluten_free AND 'gluten' = ANY(allergens))",
            name="chk_menu_item_gluten_free_contradiction",
        ),
        sa.CheckConstraint(
            "NOT is_vegan OR NOT ("
            "allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[])",
            name="chk_menu_item_vegan_contradiction",
        ),
        sa.CheckConstraint(
            "NOT is_vegetarian OR NOT ("
            "allergens && ARRAY['fish','crustaceans','molluscs']::text[])",
            name="chk_menu_item_vegetarian_contradiction",
        ),
        sa.CheckConstraint("price >= 0 AND unit_cost >= 0", name="chk_menu_item_price_positive"),
        sa.PrimaryKeyConstraint("id", name="menu_item_pkey"),
    )
    op.create_index("idx_menu_item_restaurant_id", "menu_item", ["restaurant_id"])
    op.create_index(
        "idx_menu_item_active",
        "menu_item",
        ["restaurant_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_menu_item_listing",
        "menu_item",
        ["restaurant_id", "available", "sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 4. menu_translation
    op.create_table(
        "menu_translation",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "menu_item_id",
            sa.UUID(),
            sa.ForeignKey(
                "menu_item.id", ondelete="CASCADE", name="fk_menu_translation_menu_item_id"
            ),
            nullable=False,
        ),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="menu_translation_pkey"),
        sa.UniqueConstraint("menu_item_id", "language", name="menu_translation_item_lang_key"),
    )
    op.create_index("idx_menu_translation_item_id", "menu_translation", ["menu_item_id"])

    # 5. guest_session
    op.create_table(
        "guest_session",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "restaurant_id",
            sa.UUID(),
            sa.ForeignKey(
                "restaurant.id", ondelete="CASCADE", name="fk_guest_session_restaurant_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "table_id",
            sa.UUID(),
            sa.ForeignKey("dining_table.id", ondelete="SET NULL", name="fk_guest_session_table_id"),
            nullable=True,
        ),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column(
            "dietary_preferences",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "allergens_to_avoid",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allergens_to_avoid <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_guest_session_allergens",
        ),
        sa.CheckConstraint(
            "dietary_preferences <@ ARRAY['vegetarian','vegan','gluten_free']::text[]",
            name="chk_guest_session_dietary",
        ),
        sa.PrimaryKeyConstraint("id", name="guest_session_pkey"),
    )
    op.create_index("idx_guest_session_restaurant_id", "guest_session", ["restaurant_id"])
    op.create_index("idx_guest_session_table_id", "guest_session", ["table_id"])
    op.create_index("idx_guest_session_cleanup", "guest_session", ["restaurant_id", "expires_at"])

    # 6. orders
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "guest_session_id",
            sa.UUID(),
            sa.ForeignKey(
                "guest_session.id", ondelete="RESTRICT", name="fk_orders_guest_session_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "restaurant_id",
            sa.UUID(),
            sa.ForeignKey("restaurant.id", ondelete="CASCADE", name="fk_orders_restaurant_id"),
            nullable=False,
        ),
        sa.Column(
            "table_id",
            sa.UUID(),
            sa.ForeignKey("dining_table.id", ondelete="SET NULL", name="fk_orders_table_id"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'placed'"), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "allergen_conflict_acknowledged",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "allergens_to_avoid",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "dietary_preferences",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "placed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("bumped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('placed', 'bumped', 'cancelled')", name="chk_orders_status"),
        sa.CheckConstraint("total >= 0", name="chk_orders_total"),
        sa.CheckConstraint(
            "allergens_to_avoid <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_orders_allergens",
        ),
        sa.CheckConstraint(
            "dietary_preferences <@ ARRAY['vegetarian','vegan','gluten_free']::text[]",
            name="chk_orders_dietary",
        ),
        sa.PrimaryKeyConstraint("id", name="orders_pkey"),
        sa.UniqueConstraint(
            "guest_session_id", "idempotency_key", name="orders_guest_idempotency_key"
        ),
    )
    op.create_index("idx_orders_restaurant_id", "orders", ["restaurant_id"])
    op.create_index("idx_orders_guest_session_id", "orders", ["guest_session_id"])
    op.create_index("idx_orders_table_id", "orders", ["table_id"])
    op.create_index(
        "idx_orders_kitchen_query",
        "orders",
        ["restaurant_id", "status", "placed_at"],
    )

    # 7. order_item
    op.create_table(
        "order_item",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "order_id",
            sa.UUID(),
            sa.ForeignKey("orders.id", ondelete="CASCADE", name="fk_order_item_order_id"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            sa.UUID(),
            sa.ForeignKey("menu_item.id", ondelete="RESTRICT", name="fk_order_item_menu_item_id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("kitchen_name", sa.Text(), nullable=False),
        sa.Column(
            "allergens",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("allergen_verified", sa.Boolean(), nullable=False),
        sa.Column("allergen_status", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 20", name="chk_order_item_quantity"),
        sa.CheckConstraint("unit_price >= 0 AND unit_cost >= 0", name="chk_order_item_unit_prices"),
        sa.CheckConstraint(
            "notes IS NULL OR length(notes) <= 500", name="chk_order_item_notes_length"
        ),
        sa.CheckConstraint(
            "allergen_status IN ('contains', 'unverified', 'no_declared_match')",
            name="chk_order_item_allergen_status",
        ),
        sa.CheckConstraint(
            "allergens <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
            "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]",
            name="chk_order_item_allergens",
        ),
        sa.PrimaryKeyConstraint("id", name="order_item_pkey"),
    )
    op.create_index("idx_order_item_order_id", "order_item", ["order_id"])
    op.create_index("idx_order_item_menu_item_id", "order_item", ["menu_item_id"])

    # 8. audit_log
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "restaurant_id",
            sa.UUID(),
            sa.ForeignKey("restaurant.id", ondelete="CASCADE", name="fk_audit_log_restaurant_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="audit_log_pkey"),
    )
    op.create_index("idx_audit_log_restaurant_id", "audit_log", ["restaurant_id"])
    op.create_index(
        "idx_audit_log_query",
        "audit_log",
        ["restaurant_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("order_item")
    op.drop_table("orders")
    op.drop_table("guest_session")
    op.drop_table("menu_translation")
    op.drop_table("menu_item")
    op.drop_table("dining_table")
    op.drop_table("restaurant")
