"""Payment claims, voids, settle accountability, venue payment details.

Revision ID: 0013_payment_claims
Revises: 0012_floor_indexes
Create Date: 2026-10-26 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_payment_claims"
down_revision: str | None = "0012_floor_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = "('cash','card','wallet','raast','bank_transfer')"


def _user_fk(table: str, col: str) -> None:
    op.create_foreign_key(f"{table}_{col}_fkey", table, "users", [col], ["id"], ondelete="SET NULL")


def upgrade() -> None:
    op.add_column("bills", sa.Column("claimed_method", sa.Text(), nullable=True))
    op.add_column("bills", sa.Column("claimed_reference", sa.Text(), nullable=True))
    op.add_column("bills", sa.Column("claimed_total", sa.Numeric(10, 2), nullable=True))
    op.add_column("bills", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bills", sa.Column("settled_by", sa.UUID(), nullable=True))
    op.add_column("bills", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bills", sa.Column("cancelled_by", sa.UUID(), nullable=True))
    op.add_column("bills", sa.Column("cancel_reason", sa.Text(), nullable=True))
    _user_fk("bills", "settled_by")
    _user_fk("bills", "cancelled_by")
    op.drop_constraint("chk_bills_status", "bills", type_="check")
    op.create_check_constraint(
        "chk_bills_status", "bills", "status IN ('open', 'settled', 'cancelled')"
    )
    op.drop_constraint("chk_bills_settled_complete", "bills", type_="check")
    op.create_check_constraint(
        "chk_bills_settled_complete",
        "bills",
        "status <> 'settled' OR (payment_method IS NOT NULL AND total IS NOT NULL "
        "AND settled_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "chk_bills_cancelled_complete", "bills", "status <> 'cancelled' OR cancelled_at IS NOT NULL"
    )
    op.create_check_constraint(
        "chk_bills_claimed_method",
        "bills",
        f"claimed_method IS NULL OR claimed_method IN {METHODS}",
    )
    op.create_check_constraint(
        "chk_bills_claimed_reference_len",
        "bills",
        "claimed_reference IS NULL OR length(claimed_reference) <= 64",
    )

    op.add_column("orders", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("voided_by", sa.UUID(), nullable=True))
    op.add_column("orders", sa.Column("void_reason", sa.Text(), nullable=True))
    _user_fk("orders", "voided_by")
    op.create_check_constraint(
        "chk_orders_void", "orders", "voided_at IS NULL OR status = 'cancelled'"
    )

    op.add_column(
        "restaurant",
        sa.Column(
            "payment_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("restaurant", "payment_details")

    op.drop_constraint("chk_orders_void", "orders", type_="check")
    op.drop_constraint("orders_voided_by_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "void_reason")
    op.drop_column("orders", "voided_by")
    op.drop_column("orders", "voided_at")

    # Cancelled bills cannot satisfy the old status check.
    op.execute("DELETE FROM bills WHERE status = 'cancelled'")
    op.drop_constraint("chk_bills_claimed_reference_len", "bills", type_="check")
    op.drop_constraint("chk_bills_claimed_method", "bills", type_="check")
    op.drop_constraint("chk_bills_cancelled_complete", "bills", type_="check")
    op.drop_constraint("chk_bills_settled_complete", "bills", type_="check")
    op.create_check_constraint(
        "chk_bills_settled_complete",
        "bills",
        "status = 'open' OR (payment_method IS NOT NULL AND total IS NOT NULL "
        "AND settled_at IS NOT NULL)",
    )
    op.drop_constraint("chk_bills_status", "bills", type_="check")
    op.create_check_constraint("chk_bills_status", "bills", "status IN ('open', 'settled')")
    op.drop_constraint("bills_cancelled_by_fkey", "bills", type_="foreignkey")
    op.drop_constraint("bills_settled_by_fkey", "bills", type_="foreignkey")
    for col in (
        "cancel_reason",
        "cancelled_by",
        "cancelled_at",
        "settled_by",
        "claimed_at",
        "claimed_total",
        "claimed_reference",
        "claimed_method",
    ):
        op.drop_column("bills", col)
