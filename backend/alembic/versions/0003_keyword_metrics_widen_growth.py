"""widen keyword_metrics growth_rate columns

Revision ID: 0003_keyword_metrics_widen_growth
Revises: 0002_hs_codes_name_text
Create Date: 2026-04-20

Growth rates arrive here in **percent form** (e.g. 574.33 = +574%).
Real-world leading indicators (blog buzz, YouTube uploads) can easily
exceed ±1000% month-over-month when the prior window is near zero,
which overflows ``Numeric(7, 4)`` (cap ~999.9999).

Widen to ``Numeric(10, 4)`` so the raw upstream value can round-trip
through the DB without truncation. The opportunity scorer already caps
these values at ±200% when computing the trend axis, so the wider
column is just for audit / debugging.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0003_widen_growth"
down_revision = "0002_hs_codes_name_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "keyword_metrics",
        "growth_rate_3m",
        existing_type=sa.Numeric(7, 4),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "keyword_metrics",
        "growth_rate_6m",
        existing_type=sa.Numeric(7, 4),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "keyword_metrics",
        "growth_rate_6m",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(7, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "keyword_metrics",
        "growth_rate_3m",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(7, 4),
        existing_nullable=True,
    )
