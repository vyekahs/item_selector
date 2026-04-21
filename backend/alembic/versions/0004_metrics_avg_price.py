"""add shopping_avg_price_krw to keyword_metrics

Revision ID: 0004_avg_price
Revises: 0003_widen_growth
Create Date: 2026-04-20

The OpportunityResponse schema has had ``smartstore_avg_price_krw``
(and ``coupang_avg_price_krw``) slots from day one but there was no
DB backing. This column captures the Naver 쇼핑 API ``avg_price`` —
≈ the smart-store shelf average since smartstore dominates Naver's
shopping index. Coupang pricing stays unused under Option A.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_avg_price"
down_revision = "0003_widen_growth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "keyword_metrics",
        sa.Column("shopping_avg_price_krw", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("keyword_metrics", "shopping_avg_price_krw")
