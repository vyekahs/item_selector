"""Shared fixtures for HTTP API tests.

Strategy
--------
* Reuses the per-session test DB created by ``backend/tests/db/conftest.py``
  (same Alembic-built schema). The fixtures here transitively pull in
  ``db_session`` from there.
* Wraps each test in a SAVEPOINT so DB writes performed by the route
  handler roll back at the end.
* Overrides FastAPI's ``get_db`` dependency to yield the test session
  instead of opening a fresh, non-transactional one.
* Skips the entire module if Postgres isn't reachable (mirrors
  ``tests/db`` behaviour) so `pytest` stays green on machines without a
  running compose stack.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.deps import get_db
from app.main import app

DEFAULT_ADMIN_URL = (
    "postgresql+psycopg://itemselector:change_me_in_production"
    "@localhost:5432/postgres"
)


def _admin_url() -> str:
    override = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if override:
        return override
    base = os.environ.get("DATABASE_URL") or DEFAULT_ADMIN_URL
    url = make_url(base)
    return url.set(database="postgres").render_as_string(hide_password=False)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def _api_test_db_url() -> Generator[str, None, None]:
    db_name = f"itemselector_apitest_{uuid.uuid4().hex[:10]}"
    admin_url = _admin_url()
    try:
        admin_engine = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", future=True
        )
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except OperationalError as exc:
        pytest.skip(
            f"PostgreSQL not reachable for API tests at {admin_url}: {exc}",
            allow_module_level=False,
        )
    finally:
        try:
            admin_engine.dispose()
        except Exception:  # pragma: no cover
            pass

    test_url = (
        make_url(admin_url)
        .set(database=db_name)
        .render_as_string(hide_password=False)
    )
    yield test_url

    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", future=True
    )
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def _api_alembic_config(_api_test_db_url: str) -> Config:
    backend_root = _backend_root()
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _api_test_db_url)
    os.environ["DATABASE_URL"] = _api_test_db_url
    return cfg


@pytest.fixture(scope="session")
def api_db_engine(
    _api_test_db_url: str, _api_alembic_config: Config
) -> Generator[Engine, None, None]:
    command.upgrade(_api_alembic_config, "head")
    engine = create_engine(_api_test_db_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def api_db_session(api_db_engine: Engine) -> Generator[Session, None, None]:
    """Per-test SAVEPOINT-wrapped session, also wired into ``get_db``.

    Uses the canonical SQLAlchemy "join_transaction_mode=create_savepoint"
    recipe so service-code ``session.commit()`` calls only release a
    savepoint, leaving the outer transaction intact for rollback.
    """
    connection = api_db_engine.connect()
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


@pytest.fixture()
def client(api_db_session: Session) -> Generator[TestClient, None, None]:
    """``TestClient`` with ``get_db`` overridden to use the test session."""

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield api_db_session
        finally:
            # Don't close -- the session is owned by the api_db_session
            # fixture which handles teardown.
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
