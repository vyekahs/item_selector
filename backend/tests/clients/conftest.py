"""Shared fixtures for client tests.

We build on top of the session-scoped DB bootstrap from
:mod:`tests.db.conftest` (per-session database + alembic upgrade), but
define a **savepoint-wrapped** per-test session that tolerates the
``ApiCacheStore.set()`` code path calling ``session.commit()``
explicitly.

Skipped silently when Postgres isn't reachable (see
:mod:`tests.db.conftest` for the gating behaviour).
"""
from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

# Re-import the session-scoped bootstrap fixtures verbatim.
from tests.db.conftest import (  # noqa: F401
    _alembic_config,
    _test_db_url,
    db_engine,
)


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Per-test session using the canonical ``create_savepoint`` recipe.

    Production code calls ``session.commit()`` inside
    :class:`ApiCacheStore.set`. Without ``join_transaction_mode=...`` a
    commit would release the outer transaction and break rollback. The
    savepoint recipe makes commits release a SAVEPOINT instead, leaving
    the outer transaction intact.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        future=True,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
