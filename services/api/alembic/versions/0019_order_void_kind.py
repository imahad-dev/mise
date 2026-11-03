"""orders.void_kind: why an order was cancelled, as code (never matched from free text).

Revision ID: 0019_order_void_kind
Revises: 0018_table_reset_at
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_order_void_kind"
down_revision: str | None = "0018_table_reset_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("void_kind", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_orders_void_kind", "orders", "void_kind IN ('staff', 'declined', 'table_closed')"
    )
    # The reasons the server wrote so far (DECLINED, TABLE_CLOSED); any other was typed by staff.
    op.execute(
        """
        UPDATE orders SET void_kind = CASE void_reason
            WHEN 'Declined by waiter' THEN 'declined'
            WHEN 'Table closed' THEN 'table_closed'
            ELSE 'staff' END
        WHERE status = 'cancelled' AND (voided_at IS NOT NULL OR void_reason IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.drop_constraint("chk_orders_void_kind", "orders", type_="check")
    op.drop_column("orders", "void_kind")
