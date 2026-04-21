"""Per-test DB fixtures for scheduler tests.

Mirrors ``tests/db/conftest.py``: a fresh database is created at session
start, alembic-migrated to ``head``, then dropped at teardown. Each
test gets a SAVEPOINT-wrapped session that is fully rolled back so
schedulers can't leak state into each other.

The fixtures additionally:

* expose a ``session_factory`` callable matching what
  :class:`app.scheduler.runner.JobRunner` expects.
* skip the entire module if Postgres is not reachable (same as the
  other DB-bound suites).
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

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
def _scheduler_test_db_url() -> Generator[str, None, None]:
    db_name = f"itemselector_schedtest_{uuid.uuid4().hex[:10]}"
    admin_url = _admin_url()
    try:
        admin_engine = create_engine(
            admin_url, isolation_level="AUTOCOMMIT", future=True
        )
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except OperationalError as exc:
        pytest.skip(
            f"PostgreSQL not reachable for scheduler tests at {admin_url}: {exc}",
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
def _scheduler_alembic_config(_scheduler_test_db_url: str) -> Config:
    backend_root = _backend_root()
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _scheduler_test_db_url)
    os.environ["DATABASE_URL"] = _scheduler_test_db_url
    return cfg


@pytest.fixture(scope="session")
def scheduler_db_engine(
    _scheduler_test_db_url: str, _scheduler_alembic_config: Config
) -> Generator[Engine, None, None]:
    command.upgrade(_scheduler_alembic_config, "head")
    engine = create_engine(_scheduler_test_db_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(scheduler_db_engine: Engine) -> Generator[Session, None, None]:
    """SAVEPOINT-wrapped session, mirroring ``tests/api/conftest`` behaviour.

    ``join_transaction_mode="create_savepoint"`` so business code that
    issues ``session.commit()`` only releases a savepoint, leaving the
    outer transaction available for rollback at teardown.
    """
    connection = scheduler_db_engine.connect()
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


class _NoCloseSession:
    """Proxy that forwards everything to the real session except ``close``.

    The :class:`JobRunner` always calls ``session.close()`` in a
    ``finally`` block, but in tests we want all retry attempts to share
    the same SAVEPOINT-wrapped session so the per-test rollback can
    clean up cleanly. This wrapper turns ``close`` into a no-op while
    preserving the rest of the SQLAlchemy ORM surface.
    """

    def __init__(self, session: Session):
        self._session = session

    def close(self) -> None:
        # Intentional no-op — outer fixture owns the lifecycle.
        return None

    def __getattr__(self, item: str):  # noqa: D401 — proxy
        return getattr(self._session, item)


@pytest.fixture()
def session_factory(db_session: Session) -> Callable[[], Session]:
    """Factory the :class:`JobRunner` calls per attempt.

    Returns the *same* underlying session each time but wrapped so
    ``close()`` is a no-op — all attempts land inside the test's
    SAVEPOINT and roll back together at teardown.
    """

    return lambda: _NoCloseSession(db_session)  # type: ignore[return-value]
