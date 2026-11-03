"""Add table bills and orders.bill_id.

Revision ID: 0010_bills
Revises: 0009_venues_options
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_bills"
down_revision: str | None = "0009_venues_options"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bills",
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
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dining_table.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bill_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'live'")),
        sa.Column("bill_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method", sa.Text(), nullable=True),
        sa.Column("payment_reference", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=True),
        sa.Column("tax_jurisdiction", sa.Text(), nullable=True),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('open', 'settled')", name="chk_bills_status"),
        sa.CheckConstraint("source IN ('live', 'simulated')", name="chk_bills_source"),
        sa.CheckConstraint(
            "payment_method IS NULL OR payment_method IN "
            "('cash','card','wallet','raast','bank_transfer')",
            name="chk_bills_payment_method",
        ),
        sa.CheckConstraint(
            "source = 'simulated' OR bill_no IS NOT NULL", name="chk_bills_live_number"
        ),
        sa.CheckConstraint(
            "status = 'open' OR (payment_method IS NOT NULL AND total IS NOT NULL "
            "AND settled_at IS NOT NULL)",
            name="chk_bills_settled_complete",
        ),
        sa.CheckConstraint(
            "payment_reference IS NULL OR length(payment_reference) <= 64",
            name="chk_bills_reference_len",
        ),
        sa.UniqueConstraint("restaurant_id", "bill_no", name="uq_bills_restaurant_bill_no"),
    )
    op.create_index(
        "uq_bills_one_open_per_table",
        "bills",
        ["table_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "idx_bills_restaurant_status", "bills", ["restaurant_id", "status", "opened_at"]
    )
    op.add_column(
        "orders",
        sa.Column(
            "bill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bills.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_orders_bill_id", "orders", ["bill_id"])


def downgrade() -> None:
    op.drop_index("idx_orders_bill_id", table_name="orders")
    op.drop_column("orders", "bill_id")
    op.drop_index("idx_bills_restaurant_status", table_name="bills")
    op.drop_index("uq_bills_one_open_per_table", table_name="bills")
    op.drop_table("bills")
