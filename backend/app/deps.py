"""FastAPI dependency wiring.

Routers should ``Depends(...)`` on the helpers exposed here so we have a
single seam to swap real implementations for stubs/fakes in tests.

Most external-API client factories live in :mod:`app.clients` and can be
used directly via ``Depends(get_xxx_client)``. We intentionally do **not**
re-export every factory here -- routers import them lazily (deferred
import) where needed so that an in-progress Data Collection Agent build
does not break the rest of the API.
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_session as _get_session


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a SQLAlchemy ``Session``.

    Thin wrapper around :func:`app.db.session.get_session` so test
    overrides only have to patch one symbol.
    """
    yield from _get_session()


# Reusable type alias for "give me a DB session" -- keeps router
# signatures concise and consistent.
DbSession = Annotated[Session, Depends(get_db)]
