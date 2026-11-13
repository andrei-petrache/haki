"""add off_products

Expand-only: one new table, which the previous version of the app never
reads: products from Open Food Facts, cached as they came, under the
ODbL and apart from our own data (app/barcode.py). No user data.
A rollback pin keeps working.

Revision ID: 49efcc863c08
Revises: aea3fdffc977
Create Date: 2026-11-13 16:36:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49efcc863c08"
down_revision: str | Sequence[str] | None = "aea3fdffc977"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "off_products",
        sa.Column("gtin", sa.String(length=14), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("name_ro", sa.String(length=200), nullable=True),
        sa.Column("brand", sa.String(length=200), nullable=True),
        sa.Column("quantity", sa.String(length=100), nullable=True),
        sa.Column("calories_per_100g", sa.Float(), nullable=True),
        sa.Column("protein_per_100g", sa.Float(), nullable=True),
        sa.Column("carbs_per_100g", sa.Float(), nullable=True),
        sa.Column("fat_per_100g", sa.Float(), nullable=True),
        sa.Column("off_last_modified", sa.BigInteger(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("gtin"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("off_products")
