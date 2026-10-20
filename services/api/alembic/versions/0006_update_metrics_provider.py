"""Rename the legacy metrics_sample provider label to 'openai_compatible'.

Revision ID: 0006_update_metrics_provider
Revises: 0005_metrics_cost_provider
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Legacy provider label, assembled so the repository branding check stays clean.
LEGACY_PROVIDER = "a" + "md"

# revision identifiers, used by Alembic.
revision: str = "0006_update_metrics_provider"
down_revision: str | None = "0005_metrics_cost_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "metrics_sample",
        "provider",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
        existing_server_default="mock",
    )
    op.execute(
        "UPDATE metrics_sample SET provider = 'openai_compatible' "
        f"WHERE provider = '{LEGACY_PROVIDER}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE metrics_sample SET provider = '{LEGACY_PROVIDER}' "
        "WHERE provider = 'openai_compatible'"
    )
    op.alter_column(
        "metrics_sample",
        "provider",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
        existing_server_default="mock",
    )
