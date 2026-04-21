"""add chinese_term to keywords for 1688 search URLs

Revision ID: 0006_chinese_term
Revises: 0005_details
Create Date: 2026-04-21

1688 decodes the ``keywords=`` URL param as GBK, so passing Korean
UTF-8 bytes produces mojibake (臧曥晞歆...). We translate each keyword
to Simplified Chinese once and persist it here; the opportunity
service uses this when building the deep-link.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_chinese_term"
down_revision = "0005_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "keywords",
        sa.Column("chinese_term", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("keywords", "chinese_term")
