"""Per-country tax: bill pricing snapshot, optional service charge.

Revision ID: 0020_money_goes_global
Revises: 0019_order_void_kind
Create Date: 2026-11-03 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_money_goes_global"
down_revision: str | None = "0019_order_void_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZERO = sa.text("0")


def upgrade() -> None:
    op.add_column(
        "restaurant",
        sa.Column("service_charge_rate", sa.Numeric(4, 4), nullable=False, server_default=ZERO),
    )
    op.create_check_constraint(
        "chk_restaurant_service_charge_rate",
        "restaurant",
        "service_charge_rate >= 0 AND service_charge_rate <= 0.20",
    )
    op.add_column("bills", sa.Column("tax_pricing", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_bills_tax_pricing", "bills", "tax_pricing IN ('on_top', 'included')"
    )
    op.add_column(
        "bills",
        sa.Column("service_charge_rate", sa.Numeric(4, 4), nullable=False, server_default=ZERO),
    )
    op.add_column(
        "bills",
        sa.Column("service_charge_amount", sa.Numeric(10, 2), nullable=False, server_default=ZERO),
    )
    op.add_column(
        "bills",
        sa.Column(
            "claimed_service_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "chk_bills_service_charge",
        "bills",
        "service_charge_rate >= 0 AND service_charge_rate <= 0.20 AND service_charge_amount >= 0",
    )
    # Every bill so far was Pakistani: tax on top.
    op.execute("UPDATE bills SET tax_pricing = 'on_top' WHERE tax_rate IS NOT NULL")


def downgrade() -> None:
    # Dropping tax_pricing means VAT-inclusive bills read as tax-on-top afterwards.
    op.drop_constraint("chk_bills_service_charge", "bills", type_="check")
    op.drop_column("bills", "claimed_service_included")
    op.drop_column("bills", "service_charge_amount")
    op.drop_column("bills", "service_charge_rate")
    op.drop_constraint("chk_bills_tax_pricing", "bills", type_="check")
    op.drop_column("bills", "tax_pricing")
    op.drop_constraint("chk_restaurant_service_charge_rate", "restaurant", type_="check")
    op.drop_column("restaurant", "service_charge_rate")
