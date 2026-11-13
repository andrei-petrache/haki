"""add estimated to catalog_sources

Expand-only: one NOT NULL boolean with the server default false.
PostgreSQL 11+ stores the default once, without rewriting the table, and
fills both the existing sources (all measured data) and the inserts of the
previous version's import, which does not know the column. A rollback pin
keeps working.

Revision ID: 86cd2342c565
Revises: 16842891ab04
Create Date: 2026-11-13 12:12:18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86cd2342c565"
down_revision: str | Sequence[str] | None = "16842891ab04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "catalog_sources",
        sa.Column("estimated", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("catalog_sources", "estimated")
