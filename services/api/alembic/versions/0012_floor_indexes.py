"""Indexes for the floor view: latest call, session and settle per table.

Revision ID: 0012_floor_indexes
Revises: 0011_service_calls
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_floor_indexes"
down_revision: str | None = "0011_service_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("idx_service_call_table_created", "service_call", ["table_id", "created_at"])
    op.create_index("idx_guest_session_table_created", "guest_session", ["table_id", "created_at"])
    op.create_index("idx_bills_table_settled", "bills", ["table_id", "settled_at"])


def downgrade() -> None:
    op.drop_index("idx_bills_table_settled", table_name="bills")
    op.drop_index("idx_guest_session_table_created", table_name="guest_session")
    op.drop_index("idx_service_call_table_created", table_name="service_call")
