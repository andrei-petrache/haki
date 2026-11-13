"""add consents and erasures

Expand-only: two new tables, which the previous version of the app never
reads. consents holds each consent given (purpose, version, the language
and hash of the text shown, when; withdrawn_at once withdrawn), and goes
with its user (ON DELETE CASCADE). erasures is the log a restore applies
again (app/erasures.py): no foreign key on purpose, so it outlives the
account it names, and no personal data (an id and its created_at).
A rollback pin keeps working.

Revision ID: 8f1c9488f26e
Revises: 11e09c8ebe41
Create Date: 2026-11-13 15:21:22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f1c9488f26e"
down_revision: str | Sequence[str] | None = "11e09c8ebe41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('health_data')", name="ck_consents_purpose"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consents_user_id_purpose", "consents", ["user_id", "purpose"], unique=False
    )
    op.create_table(
        "erasures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('account', 'consent')", name="ck_erasures_kind"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("erasures")
    op.drop_index("ix_consents_user_id_purpose", table_name="consents")
    op.drop_table("consents")
