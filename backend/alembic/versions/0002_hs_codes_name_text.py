"""widen hs_codes.name_ko and name_en to TEXT

Revision ID: 0002_hs_codes_name_text
Revises: 0001_initial_schema
Create Date: 2026-04-20

관세청 공식 HS 부호 파일에는 255자를 초과하는 한글 품목명이 다수 존재한다
(예: 합성섬유 혼방직물의 세부 조성 설명 등). 초기 마이그레이션이 VARCHAR(255)로
제한했던 것을 TEXT로 확장한다. name_en도 동일하게 처리 (10자리 코드는 영문도
장황한 케이스가 있음).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0002_hs_codes_name_text"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "hs_codes",
        "name_ko",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "hs_codes",
        "name_en",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "hs_codes",
        "name_en",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "hs_codes",
        "name_ko",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
