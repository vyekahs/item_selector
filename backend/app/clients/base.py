"""Common base types for external API clients.

This module intentionally keeps the ``BaseApiClient`` surface small --
each concrete client defines its own ``fetch(...)`` signature because
the upstream APIs vary too much to share one. The ``Protocol`` style is
applied at the sub-module level (one Protocol per client file).

What *is* shared:

* :class:`ApiError` / :class:`RateLimitError` / :class:`AuthError` --
  transport-layer error hierarchy every client raises.
* :func:`use_mock_clients` -- honoured by every ``get_*_client()``
  factory so the whole system flips between Mock and Real in one env
  var (``USE_MOCK_CLIENTS``).
* :func:`load_sample_json` -- shared helper for Mock clients that read
  canned responses from :mod:`app.clients.mocks`.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


# ---- errors ---------------------------------------------------------


class ApiError(RuntimeError):
    """Generic external-API failure (non-2xx response, JSON decode error, etc.)."""


class RateLimitError(ApiError):
    """Upstream or local rate-limit enforcement tripped.

    Raised both by :mod:`app.ratelimit` (when the local token bucket is
    empty *and* blocking wait is disabled) and by real API clients when
    they see HTTP 429.
    """


class AuthError(ApiError):
    """Missing/invalid credentials.

    Real client stubs raise this when an API key env var is unset so the
    caller gets a clear, actionable message rather than a cryptic HTTP
    401 from the upstream service.
    """


# ---- environment flag ----------------------------------------------


def use_mock_clients() -> bool:
    """Return True when the process should use Mock clients.

    The default is **True** so that developer laptops and CI can run
    the full pipeline end-to-end without any external API keys. Flip
    ``USE_MOCK_CLIENTS=false`` in ``.env`` to route to the Real clients.
    """
    raw = os.environ.get("USE_MOCK_CLIENTS", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# ---- sample JSON loader --------------------------------------------


MOCKS_DIR = Path(__file__).resolve().parent / "mocks"


@lru_cache(maxsize=128)
def load_sample_json(filename: str) -> Any:
    """Load ``app/clients/mocks/<filename>`` as parsed JSON.

    Cached because samples are read-only and re-parsing on every mock
    fetch would be wasteful. Returns a deep-copyable structure
    (``dict``/``list``/primitive), so callers should copy before
    mutating.
    """
    path = MOCKS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"sample fixture not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---- base client (marker) ------------------------------------------


class BaseApiClient:
    """Optional shared base. Concrete clients may inherit for a common tag.

    We deliberately *do not* put ``async def fetch(...)`` here -- each
    client's signature differs (e.g. ``fetch(keywords: list[str])`` vs
    ``fetch(hs_code: str, year_month: str)``). Instead, each client
    file declares its own ``Protocol`` class for structural typing.

    Subclasses are free to store a shared ``httpx.AsyncClient``, a
    rate-limiter, and a cache here later; for now this is just a common
    nominal ancestor to help isinstance() checks in tests.
    """

    #: Default cache TTL (seconds). Individual clients override.
    default_cache_ttl: int = 3600
