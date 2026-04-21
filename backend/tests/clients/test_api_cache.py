"""``ApiCacheStore`` integration tests against a real PostgreSQL DB.

Skipped when Postgres isn't reachable (see ``tests/db/conftest.py``).

Coverage:

* ``set`` then ``get`` round-trips the JSON payload.
* Expired rows behave like a miss for ``get`` / ``has``.
* ``set`` UPSERTs (calling ``set`` twice with the same key replaces the
  payload but leaves a single row).
* ``delete`` removes a single row.
* ``delete_expired`` only removes rows whose ``expires_at`` is in the
  past.
"""
from __future__ import annotations

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import ApiCacheStore
from app.models import ApiCache


def test_set_get_roundtrip(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    payload = {"items": [{"id": 1}], "total": 1}

    store.set("naver:keyword:test", payload, ttl_seconds=3600)

    assert store.has("naver:keyword:test") is True
    cached = store.get("naver:keyword:test")
    assert cached == payload


def test_get_returns_none_on_miss(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    assert store.get("does-not-exist") is None
    assert store.has("does-not-exist") is False


def test_expired_entries_treated_as_miss(db_session: Session) -> None:
    store = ApiCacheStore(db_session)

    with freeze_time("2026-04-18 10:00:00"):
        store.set("k", {"v": 1}, ttl_seconds=60)
        assert store.get("k") == {"v": 1}

    # Jump well past the TTL window.
    with freeze_time("2026-04-18 10:05:00"):
        assert store.get("k") is None
        assert store.has("k") is False


def test_set_upserts_in_place(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    store.set("k", {"v": 1}, ttl_seconds=600)
    store.set("k", {"v": 2}, ttl_seconds=600)

    # Single row, latest payload.
    rows = (
        db_session.execute(select(ApiCache).where(ApiCache.cache_key == "k"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].response_json == {"v": 2}


def test_delete_removes_single_key(db_session: Session) -> None:
    store = ApiCacheStore(db_session)
    store.set("a", {"x": 1}, ttl_seconds=60)
    store.set("b", {"x": 2}, ttl_seconds=60)

    assert store.delete("a") == 1
    assert store.get("a") is None
    assert store.get("b") == {"x": 2}


def test_delete_expired_only_removes_old_rows(db_session: Session) -> None:
    store = ApiCacheStore(db_session)

    with freeze_time("2026-04-18 10:00:00"):
        store.set("fresh", {"v": "f"}, ttl_seconds=3600)
        store.set("stale", {"v": "s"}, ttl_seconds=10)

    with freeze_time("2026-04-18 10:01:00"):
        removed = store.delete_expired()
        assert removed == 1
        assert store.get("fresh") == {"v": "f"}
        assert store.get("stale") is None


def test_set_rejects_non_positive_ttl(db_session: Session) -> None:
    store = ApiCacheStore(db_session)

    with pytest.raises(ValueError):
        store.set("k", {}, ttl_seconds=0)
    with pytest.raises(ValueError):
        store.set("k", {}, ttl_seconds=-5)
