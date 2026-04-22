"""seed_candidates table

Revision ID: 0014_candidates
Revises: 0013_categories
Create Date: 2026-04-22

Staging table for auto-discovered seed suggestions. ``discover_seeds``
job mines 관세청 imports + Naver signals and writes candidates here;
the operator approves a subset via the UI and the approved rows get
promoted to ``keywords(is_seed=True)``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_candidates"
down_revision = "0013_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seed_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hs_code", sa.String(length=10), nullable=True, index=True),
        sa.Column("import_value_krw_3m", sa.BigInteger(), nullable=True),
        sa.Column("import_growth_3m_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("avg_unit_price_krw", sa.Integer(), nullable=True),
        sa.Column("monthly_search_volume", sa.Integer(), nullable=True),
        sa.Column("search_growth_3m_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("combined_score", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_seed_candidates_score",
        "seed_candidates",
        ["is_approved", "combined_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_seed_candidates_score", "seed_candidates")
    op.drop_table("seed_candidates")
