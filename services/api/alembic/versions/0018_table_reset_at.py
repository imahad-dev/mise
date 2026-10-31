"""dining_table.reset_at: when the table last reset, only ever moving forward.

Revision ID: 0018_table_reset_at
Revises: 0017_safer_table_ordering
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_table_reset_at"
down_revision: str | None = "0017_safer_table_ordering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dining_table", sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True))
    # The resets so far, as session_is_current judged them: clear, settle, or cancel.
    op.execute(
        """
        UPDATE dining_table t SET reset_at = greatest(
            t.cleared_at,
            (SELECT max(b.settled_at) FROM bills b
              WHERE b.table_id = t.id AND b.status = 'settled'),
            (SELECT max(b.cancelled_at) FROM bills b
              WHERE b.table_id = t.id AND b.status = 'cancelled')
        )
        """
    )


def downgrade() -> None:
    op.drop_column("dining_table", "reset_at")
