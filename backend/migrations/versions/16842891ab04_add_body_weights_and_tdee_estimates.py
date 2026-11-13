"""add body_weights, tdee_estimates and the user's target mode and goal

Expand-only. Two new tables, which the previous version of the app never
reads, and two new columns on users: target_mode, NOT NULL with the
server default 'manual' (PostgreSQL 11+ stores the default once, without
rewriting the table, and fills the previous version's inserts), and the
nullable goal_kg_per_week. Their CHECK constraints are checked against
values that are all the default or null. A rollback pin keeps working.
The lock on users lasts as long as that check (under the 10 s
lock_timeout in env.py).

Revision ID: 16842891ab04
Revises: e8f9768dc81c
Create Date: 2026-11-13 11:57:07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16842891ab04"
down_revision: str | Sequence[str] | None = "e8f9768dc81c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "target_mode", sa.String(length=10), server_default="manual", nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "goal_kg_per_week",
            sa.Numeric(precision=3, scale=2, asdecimal=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_users_target_mode", "users", "target_mode IN ('manual', 'adaptive')"
    )
    op.create_check_constraint(
        "ck_users_goal_kg_per_week", "users", "goal_kg_per_week BETWEEN -1 AND 0.5"
    )
    op.create_table(
        "body_weights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column(
            "weight_kg",
            sa.Numeric(precision=5, scale=2, asdecimal=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "measured_on >= '2000-01-01'", name="ck_body_weights_measured_on"
        ),
        sa.CheckConstraint(
            "weight_kg BETWEEN 20 AND 400", name="ck_body_weights_weight_kg"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "measured_on", name="uq_body_weights_user_id_measured_on"
        ),
    )
    op.create_table(
        "tdee_estimates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("tdee_kcal", sa.Integer(), nullable=True),
        sa.Column("slope_kg_per_week", sa.Float(), nullable=True),
        sa.Column("trend_weight_kg", sa.Float(), nullable=True),
        sa.Column(
            "goal_kg_per_week",
            sa.Numeric(precision=3, scale=2, asdecimal=False),
            nullable=True,
        ),
        sa.Column("weigh_ins", sa.Integer(), nullable=False),
        sa.Column("logged_days", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'collecting') = (tdee_kcal IS NULL)",
            name="ck_tdee_estimates_tdee_when_adaptive",
        ),
        sa.CheckConstraint(
            "status IN ('collecting', 'adaptive')", name="ck_tdee_estimates_status"
        ),
        sa.CheckConstraint(
            "tdee_kcal BETWEEN 1200 AND 5000", name="ck_tdee_estimates_tdee_kcal"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "week_start", name="uq_tdee_estimates_user_id_week_start"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("tdee_estimates")
    op.drop_table("body_weights")
    op.drop_constraint("ck_users_goal_kg_per_week", "users", type_="check")
    op.drop_constraint("ck_users_target_mode", "users", type_="check")
    op.drop_column("users", "goal_kg_per_week")
    op.drop_column("users", "target_mode")
