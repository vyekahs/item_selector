"""Alembic environment.

Reads the database URL from ``DATABASE_URL`` (with a sane local
fallback) and binds the autogenerate target to ``app.db.base.Base``.

Both online and offline modes are supported.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the models package so every model gets registered against
# ``Base.metadata`` (without this, autogenerate or ``create_all`` would
# only see whatever happens to already be imported).
from app.db.base import Base  # noqa: E402
from app.db.session import get_database_url  # noqa: E402
import app.models  # noqa: F401,E402  (side-effect: register models)

# ---- Alembic boilerplate ---------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the env-driven URL so neither developers nor CI need to keep
# ``alembic.ini`` in sync with secrets.
config.set_main_option("sqlalchemy.url", get_database_url())

target_metadata = Base.metadata


def _get_url() -> str:
    """Always trust the env var first; fall back to whatever Alembic was given."""
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emit SQL only)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    config.set_main_option("sqlalchemy.url", _get_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
