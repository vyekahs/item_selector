"""add expected_sell_price_krw to products (manual override)

Revision ID: 0010_sell_price
Revises: 0009_duty_rates
Create Date: 2026-04-21

사용자가 마진 시뮬레이션을 위해 판매가를 수동으로 지정할 수 있게
컬럼 추가. NULL이면 scorer가 Naver 쇼핑 평균가(keyword_metrics)로
폴백하고, 그것도 없으면 unit_cost × 3 휴리스틱.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_sell_price"
down_revision = "0009_duty_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("expected_sell_price_krw", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "expected_sell_price_krw")
