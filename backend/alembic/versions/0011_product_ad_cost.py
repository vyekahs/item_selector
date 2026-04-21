"""add ad_cost_pct override to products

Revision ID: 0011_ad_cost
Revises: 0010_sell_price
Create Date: 2026-04-21

광고비 비율을 사용자가 지정할 수 있게 컬럼 추가. NULL이면 scorer가
채널별 기본값(스마트스토어 10%, 쿠팡 15%)을 쓴다. 0으로 지정하면
유기적 판매(광고 없음) 시나리오로 계산.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_ad_cost"
down_revision = "0010_sell_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("ad_cost_pct", sa.Numeric(5, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "ad_cost_pct")
