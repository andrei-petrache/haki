"""add favourited_at to foods

Expand-only: one nullable column without a default. The previous version
of the app neither reads nor writes it, so a rollback pin keeps working.

Revision ID: ef6cd72f7e99
Revises: f187f906dc7d
Create Date: 2026-11-11 23:13:27.353319

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ef6cd72f7e99"
down_revision: str | Sequence[str] | None = "f187f906dc7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "foods", sa.Column("favourited_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("foods", "favourited_at")
