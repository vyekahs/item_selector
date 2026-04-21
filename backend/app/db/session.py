"""Database engine and session factory.

Reads ``DATABASE_URL`` from the environment. This is supplied by the
docker-compose stack (Infra Agent) and defaults to a local socket
suitable for running migrations/seeds against a locally-started
postgres container.
"""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://itemselector:change_me_in_production"
    "@localhost:5432/itemselector"
)


def get_database_url() -> str:
    """Return the DATABASE_URL from env, falling back to a local dev URL."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return (and lazily construct) the process-wide SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            future=True,
        )
    return _SessionFactory


def SessionLocal() -> Session:  # noqa: N802 - keep factory-style name
    """Create a new Session bound to the shared engine."""
    return _get_session_factory()()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency-style generator yielding a Session.

    Not currently wired into any router — Backend API Agent will
    consume this when adding endpoints.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_tests(url: str | None = None) -> Engine:
    """Force-reconstruct the engine (used by the test harness).

    Exposed so tests can point the engine at a test DB without relying
    on module reloading.
    """
    global _engine, _SessionFactory
    if url is not None:
        os.environ["DATABASE_URL"] = url
    _engine = None
    _SessionFactory = None
    return get_engine()
