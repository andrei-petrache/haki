"""add the catalog: sources, foods, exercises and links

Revision ID: f187f906dc7d
Revises: 3bf97e2ee106
Create Date: 2026-11-11 19:50:01.914259

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f187f906dc7d"
down_revision: str | Sequence[str] | None = "3bf97e2ee106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    # Expand only: an extension, three new tables with their indexes, and one
    # nullable column with no default
    # on foods and on exercises. The previous version of the app runs on this
    # schema too (it never names the new columns, so they stay NULL), which
    # the rollback pin needs. The tables are empty here: the catalog's rows
    # come from the import (app/catalog_import.py), not from a migration.
    # Trigram matching, for the LIKE '%word%' of the catalog search. A trusted
    # extension: the database owner may create it, no superuser needed
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "catalog_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("license", sa.String(length=50), nullable=False),
        sa.Column("attribution", sa.String(length=1000), nullable=False),
        sa.Column("attribution_required", sa.Boolean(), nullable=False),
        sa.Column("share_alike", sa.Boolean(), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "catalog_exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_ro", sa.String(length=100), nullable=True),
        sa.Column("search_text", sa.String(length=250), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("equipment", sa.String(length=30), nullable=True),
        sa.Column("level", sa.String(length=30), nullable=True),
        sa.Column("force", sa.String(length=30), nullable=True),
        sa.Column("mechanic", sa.String(length=30), nullable=True),
        sa.Column("primary_muscles", postgresql.JSONB(), nullable=False),
        sa.Column("secondary_muscles", postgresql.JSONB(), nullable=False),
        sa.Column("image_refs", postgresql.JSONB(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "source_ref", name="uq_catalog_exercises_source_id_source_ref"
        ),
    )
    op.create_table(
        "catalog_foods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_ro", sa.String(length=100), nullable=True),
        sa.Column("search_text", sa.String(length=250), nullable=False),
        sa.Column("calories_per_100g", sa.Double(), nullable=False),
        sa.Column("protein_per_100g", sa.Double(), nullable=False),
        sa.Column("carbs_per_100g", sa.Double(), nullable=False),
        sa.Column("fat_per_100g", sa.Double(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "calories_per_100g >= 0 AND protein_per_100g >= 0 "
            "AND carbs_per_100g >= 0 AND fat_per_100g >= 0",
            name="ck_catalog_foods_non_negative_nutrients",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "source_ref", name="uq_catalog_foods_source_id_source_ref"
        ),
    )
    # Built on empty tables, so no lock is held for long
    op.create_index(
        "ix_catalog_foods_search_text_trgm",
        "catalog_foods",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_catalog_exercises_search_text_trgm",
        "catalog_exercises",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_catalog_exercises_primary_muscles",
        "catalog_exercises",
        ["primary_muscles"],
        postgresql_using="gin",
        postgresql_ops={"primary_muscles": "jsonb_path_ops"},
    )
    # Adding a nullable column without a default only changes the catalog in
    # PostgreSQL; no row is rewritten. The unique constraints build an index
    # under a lock that blocks writes to the table for as long as that takes,
    # a moment at today's sizes. The foreign keys check existing rows, all
    # NULL here.
    op.add_column(
        "exercises", sa.Column("catalog_exercise_id", sa.Integer(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_exercises_user_id_catalog_exercise_id",
        "exercises",
        ["user_id", "catalog_exercise_id"],
    )
    op.create_foreign_key(
        "fk_exercises_catalog_exercise_id",
        "exercises",
        "catalog_exercises",
        ["catalog_exercise_id"],
        ["id"],
    )
    op.add_column("foods", sa.Column("catalog_food_id", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        "uq_foods_user_id_catalog_food_id", "foods", ["user_id", "catalog_food_id"]
    )
    op.create_foreign_key(
        "fk_foods_catalog_food_id",
        "foods",
        "catalog_foods",
        ["catalog_food_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema.

    Drops the catalog and every link to it: never on a database with real
    data (expand-only: a release removes things in a later step, if at all).
    """
    op.drop_constraint("fk_foods_catalog_food_id", "foods", type_="foreignkey")
    op.drop_constraint("uq_foods_user_id_catalog_food_id", "foods", type_="unique")
    op.drop_column("foods", "catalog_food_id")
    op.drop_constraint(
        "fk_exercises_catalog_exercise_id", "exercises", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_exercises_user_id_catalog_exercise_id", "exercises", type_="unique"
    )
    op.drop_column("exercises", "catalog_exercise_id")
    op.drop_index(
        "ix_catalog_exercises_primary_muscles", table_name="catalog_exercises"
    )
    op.drop_index(
        "ix_catalog_exercises_search_text_trgm", table_name="catalog_exercises"
    )
    op.drop_index("ix_catalog_foods_search_text_trgm", table_name="catalog_foods")
    op.drop_table("catalog_foods")
    op.drop_table("catalog_exercises")
    op.drop_table("catalog_sources")
    # pg_trgm stays: dropping an extension is not this migration's to undo
