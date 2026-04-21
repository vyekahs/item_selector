"""add user-editable customs_duty_pct to products

Revision ID: 0008_duty
Revises: 0007_shipping
Create Date: 2026-04-21

관세율은 HS코드와 한-중 FTA 적용 여부에 따라 달라진다. 동일 HS라도
- 일반 기본 관세: 대체로 8% (품목별 상이)
- 한-중 FTA: 대상 품목은 0~5% (원산지 증명서 필요)

사용자가 상품 단위로 적용할 관세율을 직접 지정할 수 있게 컬럼 추가.
NULL이면 scorer 기본값(8%) 사용.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_duty"
down_revision = "0007_shipping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("customs_duty_pct", sa.Numeric(5, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "customs_duty_pct")
