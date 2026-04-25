"""detail_pages.template_name column

Revision ID: 0016_dp_template
Revises: 0015_detail_pages
Create Date: 2026-04-21

Adds ``template_name`` (nullable=False, default ``detail_page_v1.html``)
to ``detail_pages`` so each row remembers which Jinja2 template was
chosen at ingest/regenerate time. Server default lets the migration run
on a populated table without backfill.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_dp_template"
down_revision = "0015_detail_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "detail_pages",
        sa.Column(
            "template_name",
            sa.String(length=64),
            nullable=False,
            server_default="detail_page_v1.html",
        ),
    )


def downgrade() -> None:
    op.drop_column("detail_pages", "template_name")
