"""add language to users

Expand-only: one nullable column without a default. The previous version
of the app neither reads nor writes it and still inserts users, so a
rollback pin keeps working.

Revision ID: 8a95f327ef75
Revises: e188c28f2378
Create Date: 2026-11-12 16:43:10.678064

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a95f327ef75"
down_revision: str | Sequence[str] | None = "e188c28f2378"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("language", sa.String(length=5), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "language")
