"""Per-language labels for sizes, choice groups and choices (guest-facing only).

Revision ID: 0022_label_translations
Revises: 0021_dish_choices
Create Date: 2026-11-12 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_label_translations"
down_revision: str | None = "0021_dish_choices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("menu_item_option", "menu_choice_group", "menu_choice")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "translations",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "translations")
