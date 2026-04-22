"""Verify ``alembic upgrade head`` / ``downgrade base`` are reversible."""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

EXPECTED_TABLES = {
    "categories",
    "hs_codes",
    "keywords",
    "keyword_hs_mappings",
    "keyword_metrics",
    "import_stats",
    "opportunity_scores",
    "products",
    "product_scores",
    "channel_profits",
    "feedbacks",
    "coupang_fees",
    "exchange_rates",
    "api_cache",
    "customs_duty_rates",
    "international_shipping_rates",
    "seed_candidates",
}


def _table_names(engine: Engine) -> set[str]:
    inspector = inspect(engine)
    # Filter out alembic's own bookkeeping table.
    return {
        name for name in inspector.get_table_names()
        if name != "alembic_version"
    }


def test_upgrade_head_creates_all_tables(db_engine: Engine) -> None:
    """db_engine fixture has already run ``upgrade head``."""
    actual = _table_names(db_engine)
    missing = EXPECTED_TABLES - actual
    extra = actual - EXPECTED_TABLES
    assert not missing, f"missing tables after upgrade: {missing}"
    assert not extra, f"unexpected tables after upgrade: {extra}"


def test_downgrade_then_upgrade_round_trip(
    db_engine: Engine,
    _alembic_config: Config,
) -> None:
    """downgrade base → drops everything; upgrade head → re-creates."""
    # downgrade
    command.downgrade(_alembic_config, "base")
    after_down = _table_names(db_engine)
    assert after_down == set(), (
        f"tables remained after downgrade base: {after_down}"
    )

    # upgrade back
    command.upgrade(_alembic_config, "head")
    after_up = _table_names(db_engine)
    assert after_up == EXPECTED_TABLES, (
        f"tables after re-upgrade != expected: {after_up ^ EXPECTED_TABLES}"
    )
