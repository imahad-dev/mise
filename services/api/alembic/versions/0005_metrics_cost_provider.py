"""Add cost_usd, provider, and rate_limit_info to metrics_sample.

Revision ID: 0005_metrics_cost_provider
Revises: 0004_orders_bumped_check
Create Date: 2026-10-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_metrics_cost_provider"
down_revision: str | None = "0004_orders_bumped_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metrics_sample",
        sa.Column("provider", sa.String(20), nullable=False, server_default="mock"),
    )
    op.add_column(
        "metrics_sample",
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.add_column(
        "metrics_sample",
        sa.Column("rate_limit_info", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("metrics_sample", "rate_limit_info")
    op.drop_column("metrics_sample", "cost_usd")
    op.drop_column("metrics_sample", "provider")
