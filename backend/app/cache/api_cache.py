"""PostgreSQL-backed response cache for external APIs.

The ``api_cache`` table (see :class:`app.models.ApiCache`) stores a
``(cache_key, response_json, expires_at)`` triple per request. This
module provides a small, transactional wrapper so client code doesn't
have to know the schema.

Why Postgres (not Redis)?
-------------------------
Per spec §3.4, Coupang Partners is 10 req/hour. Losing a Redis cache
on restart could blow the daily quota in seconds, so the cache must be
durable. Redis is still used -- just for *rate-limiting token buckets*
(see :mod:`app.ratelimit`), not for response caching.

Usage
-----
.. code-block:: python

    from app.cache import ApiCacheStore
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        store = ApiCacheStore(session)
        cached = store.get("coupang:search:휴대용선풍기")
        if cached is None:
            response = await client.fetch(...)
            store.set("coupang:search:휴대용선풍기", response, ttl_seconds=86400)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import ApiCache


def _utcnow() -> datetime:
    """tz-aware UTC now. Factored out to ease freezegun testing."""
    return datetime.now(tz=timezone.utc)


class ApiCacheStore:
    """Tiny repository for the ``api_cache`` table.

    The class does **not** own the SQLAlchemy session -- callers pass
    one in so lifecycle (commit/rollback, SAVEPOINT in tests) stays
    with them. Every write method commits on success; read methods
    never commit.
    """

    def __init__(self, session: Session):
        self._session = session

    # ---- reads -------------------------------------------------------

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Return the cached JSON, or ``None`` if miss / expired.

        Expired rows are **not** deleted here (that is the job of
        :meth:`delete_expired`) -- they are simply treated as a miss.
        This keeps reads cheap and predictable.
        """
        stmt = select(ApiCache).where(ApiCache.cache_key == cache_key)
        row = self._session.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        if row.expires_at <= _utcnow():
            return None
        return dict(row.response_json)

    def has(self, cache_key: str) -> bool:
        """Cheap existence check (still respects expiry)."""
        return self.get(cache_key) is not None

    # ---- writes ------------------------------------------------------

    def set(
        self,
        cache_key: str,
        response_json: dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        """UPSERT ``(cache_key, response_json, expires_at)``.

        Uses Postgres ``ON CONFLICT`` so concurrent callers don't need
        an explicit existence check.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        stmt = pg_insert(ApiCache).values(
            cache_key=cache_key,
            response_json=response_json,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ApiCache.cache_key],
            set_={
                "response_json": stmt.excluded.response_json,
                "expires_at": stmt.excluded.expires_at,
                "updated_at": now,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def delete(self, cache_key: str) -> int:
        """Delete a single key. Returns the number of rows removed."""
        stmt = delete(ApiCache).where(ApiCache.cache_key == cache_key)
        result = self._session.execute(stmt)
        self._session.commit()
        return result.rowcount or 0

    def delete_expired(self) -> int:
        """Remove rows whose ``expires_at`` is in the past.

        Scheduler agent will call this periodically to keep the table
        bounded. Returns the number of rows removed.
        """
        stmt = delete(ApiCache).where(ApiCache.expires_at <= _utcnow())
        result = self._session.execute(stmt)
        self._session.commit()
        return result.rowcount or 0
