"""add client_key to meal_entries and quick_entries

Expand-only: one nullable UUID column on each table, without a default,
and a unique index on (user_id, client_key) over the rows that have a key
only. Every existing entry keeps null, which the index leaves out; the
previous version neither reads nor writes the column and still inserts.
A rollback pin keeps working. Building the indexes reads each table once
under a lock that blocks writes, as long as that read (small tables, and
under the 10 s lock_timeout in env.py).

Revision ID: aea3fdffc977
Revises: 8f1c9488f26e
Create Date: 2026-11-13 15:35:01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aea3fdffc977"
down_revision: str | Sequence[str] | None = "8f1c9488f26e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("meal_entries", "quick_entries")


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.add_column(table, sa.Column("client_key", sa.Uuid(), nullable=True))
        op.create_index(
            f"uq_{table}_user_id_client_key",
            table,
            ["user_id", "client_key"],
            unique=True,
            postgresql_where=sa.text("client_key IS NOT NULL"),
            sqlite_where=sa.text("client_key IS NOT NULL"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(TABLES):
        op.drop_index(f"uq_{table}_user_id_client_key", table_name=table)
        op.drop_column(table, "client_key")
