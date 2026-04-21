"""Shared fixtures for DB tests.

Strategy
--------
* Each test module gets its **own** brand-new database
  (``itemselector_test_<random>``), created at session start and
  dropped at session end. This isolates concurrent test runs.
* The schema is materialized via Alembic (``upgrade head``) — the same
  code path used in production.
* Function-scoped ``db_session`` fixture wraps each test in a
  ``SAVEPOINT`` rollback so tests can't leak state into each other.

Skipping
--------
If postgres is not reachable (e.g. ``docker compose up postgres`` was
not run), every test in this directory is skipped with a clear reason
instead of failing — that lets the rest of the suite stay green.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

# Default to the dev compose mapping (host port 5432). Override via env.
DEFAULT_ADMIN_URL = (
    "postgresql+psycopg://itemselector:change_me_in_production"
    "@localhost:5432/postgres"
)


def _admin_url() -> str:
    # Allow override; otherwise reuse the postgres maintenance DB on the
    # same server as DATABASE_URL.
    override = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if override:
        return override
    base = os.environ.get("DATABASE_URL") or DEFAULT_ADMIN_URL
    url = make_url(base)
    # IMPORTANT: ``str(url)`` masks the password as ``***``. We must
    # use ``render_as_string(hide_password=False)`` so the credentials
    # round-trip back into a usable conninfo string.
    return url.set(database="postgres").render_as_string(hide_password=False)


def _backend_root() -> Path:
    # ``backend/tests/db/conftest.py`` → backend/
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def _test_db_url() -> Generator[str, None, None]:
    """Create a fresh database for the test session and drop it at the end."""
    db_name = f"itemselector_test_{uuid.uuid4().hex[:10]}"
    admin_url = _admin_url()

    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except OperationalError as exc:
        pytest.skip(
            f"PostgreSQL not reachable for DB tests at {admin_url}: {exc}",
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

    # Teardown: terminate connections, then drop.
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
def _alembic_config(_test_db_url: str) -> Config:
    backend_root = _backend_root()
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _test_db_url)
    # env.py reads DATABASE_URL directly — keep both consistent.
    os.environ["DATABASE_URL"] = _test_db_url
    return cfg


@pytest.fixture(scope="session")
def db_engine(_test_db_url: str, _alembic_config: Config) -> Generator[Engine, None, None]:
    """Engine bound to the per-session test DB, after ``alembic upgrade head``."""
    command.upgrade(_alembic_config, "head")
    engine = create_engine(_test_db_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Per-test transactional session.

    Uses the SAVEPOINT pattern so the outer transaction can be rolled
    back at the end of the test, leaving the schema clean for the next.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionFactory = sessionmaker(bind=connection, autoflush=False, autocommit=False, future=True)
    session = SessionFactory()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
