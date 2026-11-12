"""add program_day_id to workouts

Expand-only: one nullable column without a default, its index and a
foreign key to program_days with ON DELETE SET NULL. Every existing
workout keeps null, which means "logged by hand" and is valid. The
previous version of the app neither reads nor writes the column and still
inserts workouts, so a rollback pin keeps working; workouts it starts from
a program get null. The foreign key is checked against a column that is
null everywhere, so adding it scans nothing, and the lock it takes on
workouts and program_days lasts as long as that check (under the 10 s
lock_timeout in env.py).

Revision ID: e8f9768dc81c
Revises: db5eae5df170
Create Date: 2026-11-12 18:50:55.821736

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f9768dc81c"
down_revision: str | Sequence[str] | None = "db5eae5df170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("workouts", sa.Column("program_day_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_workouts_program_day_id"), "workouts", ["program_day_id"], unique=False
    )
    op.create_foreign_key(
        "fk_workouts_program_day_id",
        "workouts",
        "program_days",
        ["program_day_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_workouts_program_day_id", "workouts", type_="foreignkey")
    op.drop_index(op.f("ix_workouts_program_day_id"), table_name="workouts")
    op.drop_column("workouts", "program_day_id")
