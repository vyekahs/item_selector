"""source_products + detail_pages tables

Revision ID: 0015_detail_pages
Revises: 0014_candidates
Create Date: 2026-04-21

상세페이지 자동 생성기 (detail-page generator) Module A.

``source_products`` stores the raw payload posted by the Chrome
extension when scraping a 1688/Taobao product page.
``detail_pages`` tracks the asynchronous Korean-localized rendering
pipeline (status: pending → processing → done/failed) and the path
of the resulting JPG.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_detail_pages"
down_revision = "0014_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "source_platform",
            sa.String(length=16),
            nullable=False,
            comment="'1688' or 'taobao'",
        ),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
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
        sa.UniqueConstraint("source_url", name="uq_source_products_source_url"),
    )

    op.create_table(
        "detail_pages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_product_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "source_products.id",
                ondelete="CASCADE",
                name="fk_detail_pages_source_product_id_source_products",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="pending | processing | done | failed",
        ),
        sa.Column("title_ko", sa.String(length=200), nullable=True),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
        "ix_detail_pages_source_product_id",
        "detail_pages",
        ["source_product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_detail_pages_source_product_id", "detail_pages")
    op.drop_table("detail_pages")
    op.drop_table("source_products")
