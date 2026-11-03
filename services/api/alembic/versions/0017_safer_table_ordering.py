"""Table sittings: staff-opened tables, first-order approval, optional per-sitting code.

Revision ID: 0017_safer_table_ordering
Revises: 0016_pay_forward_hardening
Create Date: 2026-10-31 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_safer_table_ordering"
down_revision: str | None = "0016_pay_forward_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "table_sitting",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dining_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "opened_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("code_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('settled', 'cancelled', 'staff_closed', 'idle_timeout')",
            name="chk_table_sitting_close_reason",
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (close_reason IS NULL)",
            name="chk_table_sitting_closed_pair",
        ),
        sa.CheckConstraint("code IS NULL OR code ~ '^[0-9]{4}$'", name="chk_table_sitting_code"),
    )
    op.create_index("idx_table_sitting_table_id", "table_sitting", ["table_id"])
    op.create_index(
        "uq_table_sitting_open_per_table",
        "table_sitting",
        ["table_id"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )

    op.add_column(
        "restaurant",
        sa.Column(
            "sitting_code_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "restaurant",
        sa.Column(
            "first_order_cap_multiplier",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("4"),
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "sitting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("table_sitting.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_orders_sitting_id", "orders", ["sitting_id"])
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status",
        "orders",
        "status IN ('awaiting_payment', 'pending_approval', 'placed', 'bumped', 'cancelled')",
    )

    op.add_column(
        "guest_session",
        sa.Column(
            "sitting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("table_sitting.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_guest_session_sitting_id", "guest_session", ["sitting_id"])


def downgrade() -> None:
    op.drop_index("idx_guest_session_sitting_id", table_name="guest_session")
    op.drop_column("guest_session", "sitting_id")
    # The old constraint has no waiting status: a waiting order (never on a bill) is cancelled.
    op.execute("UPDATE orders SET status = 'cancelled' WHERE status = 'pending_approval'")
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status",
        "orders",
        "status IN ('awaiting_payment', 'placed', 'bumped', 'cancelled')",
    )
    op.drop_index("idx_orders_sitting_id", table_name="orders")
    op.drop_column("orders", "sitting_id")
    op.drop_column("restaurant", "first_order_cap_multiplier")
    op.drop_column("restaurant", "sitting_code_required")
    op.drop_index("uq_table_sitting_open_per_table", table_name="table_sitting")
    op.drop_index("idx_table_sitting_table_id", table_name="table_sitting")
    op.drop_table("table_sitting")
