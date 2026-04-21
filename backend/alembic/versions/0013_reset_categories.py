"""Reset categories to Naver-aligned top-level scheme.

Revision ID: 0013_categories
Revises: 0012_shipping
Create Date: 2026-04-21

Pet-only subcategory tree (사료/간식/장난감/위생용품/케이지) is replaced
with Coupang-fee-aligned top-level categories inserted at boot by
``app/scripts/seed.py``. Existing keyword/hs_code assignments are
wiped — seed keywords get reclassified via ``POST /keywords/seed`` and
expanded keywords inherit their parent seed's category.
"""
from __future__ import annotations

from alembic import op

revision = "0013_categories"
down_revision = "0012_shipping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FKs so we can clear categories cleanly.
    op.execute("UPDATE keywords SET category_id = NULL")
    op.execute("UPDATE hs_codes SET category_id = NULL")
    op.execute("DELETE FROM categories")
    # seed.py reinserts the new top-level rows on container boot.


def downgrade() -> None:
    # Data-only migration; forward-only.
    pass
