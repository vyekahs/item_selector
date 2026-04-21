"""Cache package.

Exposes :class:`ApiCacheStore` -- a thin SQLAlchemy-backed wrapper
around the ``api_cache`` table. Used by the :mod:`app.clients` layer to
satisfy the "24h PostgreSQL cache" requirement for heavily rate-limited
upstreams (notably Coupang Partners: 10 req/h).
"""
from __future__ import annotations

from .api_cache import ApiCacheStore

__all__ = ["ApiCacheStore"]
