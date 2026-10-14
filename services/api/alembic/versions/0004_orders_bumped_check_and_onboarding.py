"""Enforce bumped_at on bumped orders and non-null default on restaurant onboarding.

Revision ID: 0004_orders_bumped_check
Revises: 0003_m1_foundation
Create Date: 2026-10-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_orders_bumped_check"
down_revision: str | None = "0003_m1_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Backfill bumped_at for existing bumped orders before applying constraint
    op.execute(
        "UPDATE orders "
        "SET bumped_at = COALESCE(updated_at, NOW()) "
        "WHERE status = 'bumped' AND bumped_at IS NULL"
    )

    # 2. Add CHECK constraint on orders: bumped orders must have bumped_at timestamp
    op.create_check_constraint(
        "chk_orders_bumped_at_required",
        "orders",
        "(status <> 'bumped') OR (bumped_at IS NOT NULL)",
    )

    # 3. Backfill NULL onboarding JSONB to empty dict
    op.execute("UPDATE restaurant SET onboarding = '{}'::jsonb WHERE onboarding IS NULL")

    # 4. Alter restaurant.onboarding to NOT NULL DEFAULT '{}'::jsonb
    op.alter_column(
        "restaurant",
        "onboarding",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        "restaurant",
        "onboarding",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )
    op.drop_constraint("chk_orders_bumped_at_required", "orders", type_="check")
