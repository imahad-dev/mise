"""Add orders.source (live/simulated) and the forecast_run table.

Revision ID: 0007_order_source_forecast_run
Revises: 0006_update_metrics_provider
Create Date: 2026-10-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_order_source_forecast_run"
down_revision: str | None = "0006_update_metrics_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'live'")),
    )
    op.create_check_constraint("chk_orders_source", "orders", "source IN ('live', 'simulated')")
    op.create_index("idx_orders_analytics", "orders", ["restaurant_id", "source", "placed_at"])

    op.create_table(
        "forecast_run",
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
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint("horizon_days >= 1", name="chk_forecast_run_horizon"),
    )
    op.create_index(
        "idx_forecast_run_restaurant_created", "forecast_run", ["restaurant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_forecast_run_restaurant_created", table_name="forecast_run")
    op.drop_table("forecast_run")
    op.drop_index("idx_orders_analytics", table_name="orders")
    op.drop_constraint("chk_orders_source", "orders", type_="check")
    op.drop_column("orders", "source")
