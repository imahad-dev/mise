"""Pay-it-forward hardening: line snapshot of the flag, one flagged item, idempotent gives.

Revision ID: 0016_pay_forward_hardening
Revises: 0015_pay_forward
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_pay_forward_hardening"
down_revision: str | None = "0015_pay_forward"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_item",
        sa.Column("is_pay_forward", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Lines sold before this migration take the item's current flag; handouts stay false.
    op.execute(
        "UPDATE order_item oi SET is_pay_forward = true FROM menu_item m, orders o "
        "WHERE oi.menu_item_id = m.id AND m.is_pay_forward AND oi.order_id = o.id "
        "AND o.source <> 'pay_forward'"
    )
    op.create_index(
        "uq_menu_item_pay_forward",
        "menu_item",
        ["restaurant_id"],
        unique=True,
        postgresql_where=sa.text("is_pay_forward AND deleted_at IS NULL"),
    )
    op.add_column("pay_forward", sa.Column("idempotency_key", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_pay_forward_idempotency", "pay_forward", ["restaurant_id", "idempotency_key"]
    )
    op.create_index("idx_pay_forward_order", "pay_forward", ["order_id"])


def downgrade() -> None:
    op.drop_index("idx_pay_forward_order", table_name="pay_forward")
    op.drop_constraint("uq_pay_forward_idempotency", "pay_forward", type_="unique")
    op.drop_column("pay_forward", "idempotency_key")
    op.drop_index("uq_menu_item_pay_forward", table_name="menu_item")
    op.drop_column("order_item", "is_pay_forward")
