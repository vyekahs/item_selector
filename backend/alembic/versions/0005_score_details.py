"""persist per-axis scoring details on opportunity_scores

Revision ID: 0005_details
Revises: 0004_avg_price
Create Date: 2026-04-20

``calculate_opportunity_score`` already returns a rich ``details``
dict (competition.vacancy, competition.demand_factor, customs raw %,
etc.) but the scheduler was dropping it on the floor. Persisting the
dict to a JSONB column lets the UI surface the exact calculation that
produced each sub-score without re-hitting upstream APIs.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_details"
down_revision = "0004_avg_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunity_scores",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("opportunity_scores", "details")
