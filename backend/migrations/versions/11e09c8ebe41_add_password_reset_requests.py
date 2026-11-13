"""add password_reset_requests

Expand-only: one new table, which the previous version of the app never
reads. One row per reset link asked for, so an account gets at most 3 an
hour; no token is stored (the reset token is a signed JWT). Rows go with
their user (ON DELETE CASCADE). A rollback pin keeps working.

Revision ID: 11e09c8ebe41
Revises: 86cd2342c565
Create Date: 2026-11-13 14:25:16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11e09c8ebe41"
down_revision: str | Sequence[str] | None = "86cd2342c565"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "password_reset_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_requests_user_id_created_at",
        "password_reset_requests",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_password_reset_requests_user_id_created_at",
        table_name="password_reset_requests",
    )
    op.drop_table("password_reset_requests")
