"""add quick_entries

Expand-only: one new table. The previous version of the app neither reads
nor writes it, so a rollback pin keeps working; quick entries are only
missing from its lists and totals until the next promotion. A nullable
meal_entries.food_id would have broken that rollback instead: the previous
version reads every entry's food.

Revision ID: e188c28f2378
Revises: ef6cd72f7e99
Create Date: 2026-11-12 16:37:43.272959

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e188c28f2378"
down_revision: str | Sequence[str] | None = "ef6cd72f7e99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "quick_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("eaten_on", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("calories", sa.Double(), nullable=False),
        sa.Column("protein", sa.Double(), nullable=False),
        sa.Column("carbs", sa.Double(), nullable=False),
        sa.Column("fat", sa.Double(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="ck_quick_entries_meal_type",
        ),
        sa.CheckConstraint(
            "calories >= 0 AND protein >= 0 AND carbs >= 0 AND fat >= 0",
            name="ck_quick_entries_non_negative_nutrients",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quick_entries_user_id_eaten_on",
        "quick_entries",
        ["user_id", "eaten_on"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_quick_entries_user_id_eaten_on", table_name="quick_entries")
    op.drop_table("quick_entries")
