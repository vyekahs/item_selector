"""international_shipping_rates table + product weight/method

Revision ID: 0012_shipping
Revises: 0011_ad_cost
Create Date: 2026-04-21

협력사 국제배송비 테이블 (LCL해운 + 해운(자가)) 추가 + Product에
개당 무게, 선호 운송방식 컬럼 추가.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_shipping"
down_revision = "0011_ad_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "international_shipping_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "method",
            sa.String(length=32),
            nullable=False,
            comment="'lcl' (LCL해운) or 'sea_self' (해운(자가))",
        ),
        sa.Column("max_weight_kg", sa.Numeric(7, 2), nullable=False),
        sa.Column("general_seller_krw", sa.Integer(), nullable=False),
        sa.Column("super_seller_krw", sa.Integer(), nullable=False),
        sa.Column("partner_krw", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint(
            "method", "max_weight_kg", name="shipping_rate_unique_method_weight"
        ),
    )
    op.create_index(
        "ix_intl_shipping_method_weight",
        "international_shipping_rates",
        ["method", "max_weight_kg"],
    )
    op.add_column(
        "products", sa.Column("unit_weight_kg", sa.Numeric(6, 3), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column(
            "shipping_method",
            sa.String(length=32),
            nullable=True,
            comment="'lcl' / 'sea_self' / NULL(auto by weight)",
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "shipping_method")
    op.drop_column("products", "unit_weight_kg")
    op.drop_index("ix_intl_shipping_method_weight", "international_shipping_rates")
    op.drop_table("international_shipping_rates")
