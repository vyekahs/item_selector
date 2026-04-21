"""Shared fixtures for cross-agent integration tests.

Strategy
--------
Integration tests exercise **multiple layers** in the same test case —
for example: scheduler jobs feed data into the DB, then the FastAPI
routes read it out via the HTTP stack. They therefore need both:

* A per-test DB session that the SAVEPOINT wrapper rolls back at
  teardown (no leakage between tests).
* A ``TestClient`` whose ``get_db`` dependency yields *that same*
  session so API writes and scheduler writes see the same transaction.

Postgres is mandatory: if a server isn't reachable at ``DATABASE_URL``
(or the default) the entire module is skipped, mirroring the behaviour
of ``tests/db`` / ``tests/api`` / ``tests/scheduler``.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
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
    # ``backend/tests/integration/conftest.py`` → backend/
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def _integration_test_db_url() -> Generator[str, None, None]:
    db_name = f"itemselector_inttest_{uuid.uuid4().hex[:10]}"
    admin_url = _admin_url()
    try:
        admin_engine = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", future=True
        )
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except OperationalError as exc:
        pytest.skip(
            f"PostgreSQL not reachable for integration tests at {admin_url}: {exc}",
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

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
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
def _integration_alembic_config(_integration_test_db_url: str) -> Config:
    backend_root = _backend_root()
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _integration_test_db_url)
    os.environ["DATABASE_URL"] = _integration_test_db_url
    return cfg


@pytest.fixture(scope="session")
def integration_db_engine(
    _integration_test_db_url: str, _integration_alembic_config: Config
) -> Generator[Engine, None, None]:
    command.upgrade(_integration_alembic_config, "head")
    engine = create_engine(_integration_test_db_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(
    integration_db_engine: Engine,
) -> Generator[Session, None, None]:
    """SAVEPOINT-wrapped per-test session.

    ``join_transaction_mode="create_savepoint"`` so business code's
    ``session.commit()`` calls only release a savepoint, leaving the
    outer transaction available for rollback at teardown.
    """
    connection = integration_db_engine.connect()
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
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """``TestClient`` with ``get_db`` → the shared integration session.

    The scheduler job fixtures below also bind their work to this same
    session so an end-to-end test can:

        1. Run ``CollectKeywordsJob.run(db_session)``
        2. Hit ``GET /opportunities`` via the test client
        3. See the scheduler's writes reflected in the HTTP response.
    """

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


class _NoCloseSession:
    """Proxy that forwards everything to the real session except ``close``.

    :class:`app.scheduler.runner.JobRunner` always calls ``session.close()``
    in a ``finally`` block, but integration tests want every retry /
    ``SessionLocal`` call to share the same SAVEPOINT-wrapped session so
    the outer transaction rolls back cleanly.
    """

    def __init__(self, session: Session):
        self._session = session

    def close(self) -> None:  # noqa: D401 — no-op
        return None

    def __getattr__(self, item: str):  # noqa: D401 — proxy
        return getattr(self._session, item)


@pytest.fixture()
def session_factory(db_session: Session) -> Callable[[], Session]:
    """Factory the :class:`JobRunner` can use per attempt."""
    return lambda: _NoCloseSession(db_session)  # type: ignore[return-value]
