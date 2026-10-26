"""Counter pickup: orders held until paid, daily pickup numbers, collection.

Revision ID: 0014_counter_pickup
Revises: 0013_payment_claims
Create Date: 2026-10-27 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_counter_pickup"
down_revision: str | None = "0013_payment_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status",
        "orders",
        "status IN ('awaiting_payment', 'placed', 'bumped', 'cancelled')",
    )
    op.add_column("orders", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("collected_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "orders_collected_by_fkey", "orders", "users", ["collected_by"], ["id"], ondelete="SET NULL"
    )
    op.create_check_constraint(
        "chk_orders_collected", "orders", "collected_at IS NULL OR status = 'bumped'"
    )

    op.add_column("bills", sa.Column("pickup_day", sa.Date(), nullable=True))
    op.add_column("bills", sa.Column("pickup_no", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        "uq_bills_pickup_no", "bills", ["restaurant_id", "pickup_day", "pickup_no"]
    )
    op.create_check_constraint(
        "chk_bills_pickup_pair", "bills", "(pickup_no IS NULL) = (pickup_day IS NULL)"
    )

    op.add_column("restaurant", sa.Column("pickup_prefix", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurant", "pickup_prefix")

    op.drop_constraint("chk_bills_pickup_pair", "bills", type_="check")
    op.drop_constraint("uq_bills_pickup_no", "bills", type_="unique")
    op.drop_column("bills", "pickup_no")
    op.drop_column("bills", "pickup_day")

    # Held counter orders cannot satisfy the old status check; never delete orders silently.
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM orders WHERE status = 'awaiting_payment' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Orders awaiting payment exist; run make reset before downgrading")
    op.drop_constraint("chk_orders_collected", "orders", type_="check")
    op.drop_constraint("orders_collected_by_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "collected_by")
    op.drop_column("orders", "collected_at")
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status", "orders", "status IN ('placed', 'bumped', 'cancelled')"
    )
