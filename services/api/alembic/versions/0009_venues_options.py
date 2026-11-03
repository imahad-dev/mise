"""Add venue city and tax jurisdiction, menu item options, order item option snapshot.

Revision ID: 0009_venues_options
Revises: 0008_users_memberships
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_venues_options"
down_revision: str | None = "0008_users_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("restaurant", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("restaurant", sa.Column("tax_jurisdiction", sa.Text(), nullable=True))
    op.create_table(
        "menu_item_option",
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
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("price >= 0", name="chk_menu_item_options_price"),
        sa.CheckConstraint("unit_cost >= 0", name="chk_menu_item_options_cost"),
        sa.UniqueConstraint("menu_item_id", "label", name="uq_menu_item_options_label"),
    )
    op.create_index("idx_menu_item_options_item", "menu_item_option", ["menu_item_id"])
    op.add_column(
        "order_item",
        sa.Column(
            "option_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_item_option.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("order_item", sa.Column("option_label", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_item", "option_label")
    op.drop_column("order_item", "option_id")
    op.drop_index("idx_menu_item_options_item", table_name="menu_item_option")
    op.drop_table("menu_item_option")
    op.drop_column("restaurant", "tax_jurisdiction")
    op.drop_column("restaurant", "city")
