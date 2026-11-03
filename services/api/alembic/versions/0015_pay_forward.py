"""Pay-it-forward chai: flagged menu items, a bought/given ledger, handout orders.

Revision ID: 0015_pay_forward
Revises: 0014_counter_pickup
Create Date: 2026-10-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_pay_forward"
down_revision: str | None = "0014_counter_pickup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "menu_item",
        sa.Column("is_pay_forward", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.drop_constraint("chk_orders_source", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_source", "orders", "source IN ('live', 'simulated', 'pay_forward')"
    )
    op.create_table(
        "pay_forward",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("kind IN ('bought','given')", name="chk_pay_forward_kind"),
        sa.CheckConstraint("quantity > 0", name="chk_pay_forward_quantity"),
    )
    op.create_index("idx_pay_forward_restaurant", "pay_forward", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_pay_forward_restaurant", table_name="pay_forward")
    op.drop_table("pay_forward")
    # Handout orders cannot satisfy the old source check; never delete orders silently.
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM orders WHERE source = 'pay_forward' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Pay-it-forward orders exist; run make reset before downgrading")
    op.drop_constraint("chk_orders_source", "orders", type_="check")
    op.create_check_constraint("chk_orders_source", "orders", "source IN ('live', 'simulated')")
    op.drop_column("menu_item", "is_pay_forward")
