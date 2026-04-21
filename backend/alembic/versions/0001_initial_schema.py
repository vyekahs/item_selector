"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-18

Hand-written initial migration covering every model in
:mod:`app.models`. We do not use ``--autogenerate`` so the intent of
each table/column/index is explicit.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- enums ------------------------------------------------------------
    # Each enum is created exactly once via an explicit ``CREATE TYPE``
    # call. All Column declarations below reuse the same instance with
    # ``create_type=False`` so SQLAlchemy never tries to emit the type
    # again as a side-effect of the first table that uses it.
    bind = op.get_bind()
    keyword_status_col = postgresql.ENUM(
        "PENDING",
        "ACTIVE",
        "DEPRECATED",
        "EXCLUDED",
        name="keyword_status",
        create_type=False,
    )
    sales_channel_col = postgresql.ENUM(
        "SMARTSTORE",
        "COUPANG",
        name="sales_channel",
        create_type=False,
    )
    product_recommendation_col = postgresql.ENUM(
        "GO",
        "CONDITIONAL",
        "PASS",
        name="product_recommendation",
        create_type=False,
    )
    # Explicit one-off creation (no checkfirst=False — be re-runnable).
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE keyword_status AS ENUM "
            "('PENDING','ACTIVE','DEPRECATED','EXCLUDED'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE sales_channel AS ENUM ('SMARTSTORE','COUPANG'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE product_recommendation AS ENUM "
            "('GO','CONDITIONAL','PASS'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )

    # ---- categories -------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "categories.id",
                ondelete="RESTRICT",
                name="fk_categories_parent_id_categories",
            ),
            nullable=True,
        ),
        sa.Column(
            "is_certification_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    # ---- hs_codes ---------------------------------------------------------
    op.create_table(
        "hs_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name_ko", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "categories.id",
                ondelete="SET NULL",
                name="fk_hs_codes_category_id_categories",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(code) IN (6, 10)", name="ck_hs_codes_code_length_6_or_10"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hs_codes"),
        sa.UniqueConstraint("code", name="uq_hs_codes_code"),
    )
    op.create_index("ix_hs_codes_code", "hs_codes", ["code"])
    op.create_index("ix_hs_codes_category_id", "hs_codes", ["category_id"])

    # ---- keywords ---------------------------------------------------------
    op.create_table(
        "keywords",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "categories.id",
                ondelete="SET NULL",
                name="fk_keywords_category_id_categories",
            ),
            nullable=True,
        ),
        sa.Column(
            "is_seed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status",
            keyword_status_col,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keywords"),
        sa.UniqueConstraint("term", name="uq_keywords_term"),
    )
    op.create_index("ix_keywords_term", "keywords", ["term"])
    op.create_index("ix_keywords_category_id", "keywords", ["category_id"])

    # ---- keyword_hs_mappings ----------------------------------------------
    op.create_table(
        "keyword_hs_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "keyword_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "keywords.id",
                ondelete="CASCADE",
                name="fk_keyword_hs_mappings_keyword_id_keywords",
            ),
            nullable=False,
        ),
        sa.Column(
            "hs_code",
            sa.String(length=10),
            sa.ForeignKey(
                "hs_codes.code",
                ondelete="CASCADE",
                name="fk_keyword_hs_mappings_hs_code_hs_codes",
            ),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(4, 3),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "is_manual",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_keyword_hs_mappings_confidence_between_0_and_1",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_hs_mappings"),
        sa.UniqueConstraint("keyword_id", "hs_code", name="keyword_hs_unique"),
    )
    op.create_index(
        "ix_keyword_hs_mappings_keyword_id",
        "keyword_hs_mappings",
        ["keyword_id"],
    )
    op.create_index(
        "ix_keyword_hs_mappings_hs_code",
        "keyword_hs_mappings",
        ["hs_code"],
    )

    # ---- keyword_metrics --------------------------------------------------
    op.create_table(
        "keyword_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "keyword_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "keywords.id",
                ondelete="CASCADE",
                name="fk_keyword_metrics_keyword_id_keywords",
            ),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("monthly_search_volume", sa.Integer(), nullable=True),
        sa.Column("competition_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("naver_shopping_count", sa.Integer(), nullable=True),
        sa.Column("blog_post_count", sa.Integer(), nullable=True),
        sa.Column("youtube_video_count", sa.Integer(), nullable=True),
        sa.Column("growth_rate_3m", sa.Numeric(7, 4), nullable=True),
        sa.Column("growth_rate_6m", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_metrics"),
        sa.UniqueConstraint(
            "keyword_id",
            "snapshot_date",
            name="keyword_metric_unique_snapshot",
        ),
    )
    op.create_index(
        "ix_keyword_metrics_keyword_id_snapshot_date",
        "keyword_metrics",
        ["keyword_id", "snapshot_date"],
    )

    # ---- import_stats -----------------------------------------------------
    op.create_table(
        "import_stats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "hs_code",
            sa.String(length=10),
            sa.ForeignKey(
                "hs_codes.code",
                ondelete="CASCADE",
                name="fk_import_stats_hs_code_hs_codes",
            ),
            nullable=False,
        ),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column(
            "country_code",
            sa.String(length=3),
            server_default=sa.text("'CN'"),
            nullable=False,
        ),
        sa.Column("import_quantity", sa.Numeric(20, 3), nullable=True),
        sa.Column("import_value_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_stats"),
        sa.UniqueConstraint(
            "hs_code",
            "year_month",
            "country_code",
            name="import_stat_unique_period",
        ),
    )
    op.create_index(
        "ix_import_stats_hs_code_year_month",
        "import_stats",
        ["hs_code", "year_month"],
    )

    # ---- opportunity_scores -----------------------------------------------
    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "keyword_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "keywords.id",
                ondelete="CASCADE",
                name="fk_opportunity_scores_keyword_id_keywords",
            ),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("demand_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("growth_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("competition_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("customs_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("trend_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("stability_score", sa.Numeric(6, 2), nullable=False),
        sa.Column(
            "is_excluded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("exclusion_reasons", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity_scores"),
        sa.UniqueConstraint(
            "keyword_id",
            "snapshot_date",
            name="opportunity_score_unique_snapshot",
        ),
    )
    op.create_index(
        "ix_opportunity_scores_snapshot_date_total_score",
        "opportunity_scores",
        ["snapshot_date", "total_score"],
    )

    # ---- products ---------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "keyword_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "keywords.id",
                ondelete="SET NULL",
                name="fk_products_keyword_id_keywords",
            ),
            nullable=True,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("cny_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("moq", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
    )
    op.create_index("ix_products_keyword_id", "products", ["keyword_id"])

    # ---- product_scores ---------------------------------------------------
    op.create_table(
        "product_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "products.id",
                ondelete="CASCADE",
                name="fk_product_scores_product_id_products",
            ),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("opportunity_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("profit_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("risk_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("stability_score", sa.Numeric(6, 2), nullable=False),
        sa.Column(
            "recommendation",
            product_recommendation_col,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_scores"),
        sa.UniqueConstraint(
            "product_id",
            "snapshot_date",
            name="product_score_unique_snapshot",
        ),
    )
    op.create_index("ix_product_scores_product_id", "product_scores", ["product_id"])

    # ---- channel_profits --------------------------------------------------
    op.create_table(
        "channel_profits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "product_score_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "product_scores.id",
                ondelete="CASCADE",
                name="fk_channel_profits_product_score_id_product_scores",
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sales_channel_col,
            nullable=False,
        ),
        sa.Column("unit_cost_krw", sa.Numeric(12, 2), nullable=False),
        sa.Column("expected_price_krw", sa.Numeric(12, 2), nullable=False),
        sa.Column("platform_fee_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("ad_cost_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("unit_profit_krw", sa.Numeric(12, 2), nullable=False),
        sa.Column("margin_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("roi_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("breakeven_units", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_profits"),
        sa.UniqueConstraint(
            "product_score_id",
            "channel",
            name="channel_profit_unique_per_score_channel",
        ),
    )
    op.create_index(
        "ix_channel_profits_product_score_id",
        "channel_profits",
        ["product_score_id"],
    )

    # ---- feedbacks --------------------------------------------------------
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "products.id",
                ondelete="CASCADE",
                name="fk_feedbacks_product_id_products",
            ),
            nullable=False,
        ),
        sa.Column(
            "purchased",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("monthly_sales", sa.Integer(), nullable=True),
        sa.Column("actual_revenue", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feedbacks"),
    )
    op.create_index("ix_feedbacks_product_id", "feedbacks", ["product_id"])

    # ---- coupang_fees -----------------------------------------------------
    op.create_table(
        "coupang_fees",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_path", sa.String(length=255), nullable=False),
        sa.Column("fee_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_coupang_fees"),
        sa.UniqueConstraint(
            "category_path",
            "effective_from",
            name="coupang_fee_unique_category_period",
        ),
    )
    op.create_index(
        "ix_coupang_fees_effective_from", "coupang_fees", ["effective_from"]
    )

    # ---- exchange_rates ---------------------------------------------------
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("currency_pair", sa.String(length=10), nullable=False),
        sa.Column("rate", sa.Numeric(14, 6), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exchange_rates"),
    )
    op.create_index(
        "ix_exchange_rates_pair_fetched_at",
        "exchange_rates",
        ["currency_pair", "fetched_at"],
    )

    # ---- api_cache --------------------------------------------------------
    op.create_table(
        "api_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=512), nullable=False),
        sa.Column(
            "response_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_cache"),
        sa.UniqueConstraint("cache_key", name="uq_api_cache_cache_key"),
    )
    op.create_index("ix_api_cache_cache_key", "api_cache", ["cache_key"])
    op.create_index("ix_api_cache_expires_at", "api_cache", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    # Drop in reverse dependency order.
    op.drop_index("ix_api_cache_expires_at", table_name="api_cache")
    op.drop_index("ix_api_cache_cache_key", table_name="api_cache")
    op.drop_table("api_cache")

    op.drop_index("ix_exchange_rates_pair_fetched_at", table_name="exchange_rates")
    op.drop_table("exchange_rates")

    op.drop_index("ix_coupang_fees_effective_from", table_name="coupang_fees")
    op.drop_table("coupang_fees")

    op.drop_index("ix_feedbacks_product_id", table_name="feedbacks")
    op.drop_table("feedbacks")

    op.drop_index("ix_channel_profits_product_score_id", table_name="channel_profits")
    op.drop_table("channel_profits")

    op.drop_index("ix_product_scores_product_id", table_name="product_scores")
    op.drop_table("product_scores")

    op.drop_index("ix_products_keyword_id", table_name="products")
    op.drop_table("products")

    op.drop_index(
        "ix_opportunity_scores_snapshot_date_total_score",
        table_name="opportunity_scores",
    )
    op.drop_table("opportunity_scores")

    op.drop_index("ix_import_stats_hs_code_year_month", table_name="import_stats")
    op.drop_table("import_stats")

    op.drop_index(
        "ix_keyword_metrics_keyword_id_snapshot_date",
        table_name="keyword_metrics",
    )
    op.drop_table("keyword_metrics")

    op.drop_index(
        "ix_keyword_hs_mappings_hs_code", table_name="keyword_hs_mappings"
    )
    op.drop_index(
        "ix_keyword_hs_mappings_keyword_id", table_name="keyword_hs_mappings"
    )
    op.drop_table("keyword_hs_mappings")

    op.drop_index("ix_keywords_category_id", table_name="keywords")
    op.drop_index("ix_keywords_term", table_name="keywords")
    op.drop_table("keywords")

    op.drop_index("ix_hs_codes_category_id", table_name="hs_codes")
    op.drop_index("ix_hs_codes_code", table_name="hs_codes")
    op.drop_table("hs_codes")

    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_table("categories")

    # ---- enums ------------------------------------------------------------
    bind.execute(sa.text("DROP TYPE IF EXISTS product_recommendation"))
    bind.execute(sa.text("DROP TYPE IF EXISTS sales_channel"))
    bind.execute(sa.text("DROP TYPE IF EXISTS keyword_status"))
