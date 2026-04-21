"""add china_domestic_shipping_krw + intl_shipping_krw to products

Revision ID: 0007_shipping
Revises: 0006_chinese_term
Create Date: 2026-04-21

사용자가 수입 시나리오를 조정할 수 있도록 현지 배송비(중국 국내)와
국제 배송비를 상품 단위로 저장한다. 값이 NULL이면 FunctionalScorer가
기본값(0원 / 개당 4,000원 추정)을 쓴다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_shipping"
down_revision = "0006_chinese_term"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("china_domestic_shipping_krw", sa.Integer(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("intl_shipping_krw", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "intl_shipping_krw")
    op.drop_column("products", "china_domestic_shipping_krw")
