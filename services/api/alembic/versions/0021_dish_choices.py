"""Dish choices: groups, choices and the order line snapshot.

Revision ID: 0021_dish_choices
Revises: 0020_money_goes_global
Create Date: 2026-11-06 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021_dish_choices"
down_revision: str | None = "0020_money_goes_global"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLERGEN_CHECK = (
    "ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',"
    "'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[]"
)
FALSE = sa.text("false")


def upgrade() -> None:
    op.create_table(
        "menu_choice_group",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("min_select", sa.Integer(), nullable=False),
        sa.Column("max_select", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("kind IN ('pick', 'add', 'leave_out')", name="chk_choice_group_kind"),
        sa.CheckConstraint(
            "min_select >= 0 AND max_select >= 1 AND min_select <= max_select",
            name="chk_choice_group_select",
        ),
        sa.UniqueConstraint("menu_item_id", "label", name="uq_choice_group_label"),
    )
    op.create_index("idx_choice_group_item", "menu_choice_group", ["menu_item_id"])
    op.create_table(
        "menu_choice",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_choice_group.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("price_delta", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_delta", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "allergens",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("allergen_verified", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("is_vegetarian", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("is_vegan", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("price_delta >= 0 AND cost_delta >= 0", name="chk_choice_money"),
        sa.CheckConstraint(f"allergens <@ {ALLERGEN_CHECK}", name="chk_choice_allergens"),
        sa.CheckConstraint(
            "NOT (is_vegan AND NOT is_vegetarian)", name="chk_choice_vegan_vegetarian"
        ),
        sa.CheckConstraint(
            "NOT is_vegan OR NOT ("
            "allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[])",
            name="chk_choice_vegan_allergens",
        ),
        sa.CheckConstraint(
            "NOT is_vegetarian OR NOT ("
            "allergens && ARRAY['fish','crustaceans','molluscs']::text[])",
            name="chk_choice_vegetarian_allergens",
        ),
        sa.UniqueConstraint("group_id", "label", name="uq_choice_label"),
    )
    op.create_index("idx_choice_group", "menu_choice", ["group_id"])
    op.add_column(
        "order_item",
        sa.Column(
            "choices", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("order_item", "choices")
    op.drop_table("menu_choice")
    op.drop_table("menu_choice_group")
