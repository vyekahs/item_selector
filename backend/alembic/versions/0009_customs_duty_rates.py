"""customs_duty_rates table (base + KCFTA per HS)

Revision ID: 0009_duty_rates
Revises: 0008_duty
Create Date: 2026-04-21

관세청_품목번호별 관세율표 fileData에서 A(기본) + FCN1(한-중 FTA)
두 세율구분만 뽑아 HS 10자리별로 저장. 상품에 매핑된 HS코드가
있으면 scorer가 customs_duty_pct NULL일 때 이 테이블을 조회해
자동 적용한다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_duty_rates"
down_revision = "0008_duty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customs_duty_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hs_code", sa.String(length=10), nullable=False, unique=True),
        sa.Column("base_duty_pct", sa.Numeric(5, 4), nullable=True),
        sa.Column("kcfta_duty_pct", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "effective_start",
            sa.Date(),
            nullable=True,
            comment="관세율 적용 개시일 (YYYY-MM-DD)",
        ),
        sa.Column(
            "effective_end",
            sa.Date(),
            nullable=True,
            comment="관세율 적용 만료일",
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
        "ix_customs_duty_rates_hs_code_prefix",
        "customs_duty_rates",
        ["hs_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_customs_duty_rates_hs_code_prefix", "customs_duty_rates")
    op.drop_table("customs_duty_rates")
