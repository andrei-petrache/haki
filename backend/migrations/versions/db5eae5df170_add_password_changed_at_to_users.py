"""add password_changed_at to users

Expand-only: one nullable column without a default. The previous version
of the app neither reads nor writes it and still inserts users, so a
rollback pin keeps working. After such a rollback the previous version
ignores the column and the tokens' "pwc" claim: tokens refused because of a
password change are accepted again until they expire, and a new change
signs nobody out, until the next promotion.

Revision ID: db5eae5df170
Revises: 8a95f327ef75
Create Date: 2026-11-12 17:39:01.488090

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db5eae5df170"
down_revision: str | Sequence[str] | None = "8a95f327ef75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "password_changed_at")
