"""Add table kind and clearing, service calls, restaurant service_extra_label.

Revision ID: 0011_service_calls
Revises: 0010_bills
Create Date: 2026-10-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_service_calls"
down_revision: str | None = "0010_bills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dining_table",
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'table'")),
    )
    op.add_column("dining_table", sa.Column("cleared_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "chk_dining_table_kind", "dining_table", "kind IN ('table','counter')"
    )
    op.add_column("restaurant", sa.Column("service_extra_label", sa.Text(), nullable=True))
    op.create_table(
        "service_call",
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
            sa.ForeignKey("dining_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("reason IN ('help','water','extra')", name="chk_service_call_reason"),
    )
    op.create_index(
        "uq_service_call_open_per_table",
        "service_call",
        ["table_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index("idx_service_call_restaurant", "service_call", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_service_call_restaurant", table_name="service_call")
    op.drop_index("uq_service_call_open_per_table", table_name="service_call")
    op.drop_table("service_call")
    op.drop_column("restaurant", "service_extra_label")
    op.drop_constraint("chk_dining_table_kind", "dining_table", type_="check")
    op.drop_column("dining_table", "cleared_at")
    op.drop_column("dining_table", "kind")
