"""HS 부호 lookup adapter (관세청 / data.go.kr).

The 관세청 HS부호 dataset on data.go.kr is published as a downloadable
Excel/CSV file (``fileData``) — **not** an HTTP API. We therefore:

1. Import the file once into the ``hs_codes`` table via
   ``scripts/import_hs_codes.py`` (see that script for the data.go.kr
   download instructions).
2. Look up codes through this client, which queries the local table.

Because the upstream dataset changes only at year boundaries, callers
that hit the DB directly are also fine — this adapter just keeps the
"all upstream lookups go through ``app.clients``" symmetry intact for
the scheduler/scoring code.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.contracts.dto import HsCodeDTO
from app.models import HsCode

from .base import BaseApiClient, load_sample_json, use_mock_clients

CACHE_TTL_SECONDS: int = 30 * 86_400  # parity with other clients (unused for DB)


# ---- protocol ------------------------------------------------------


class HsCodeClientProtocol(Protocol):
    cache_ttl: int

    async def fetch(self, query: str) -> list[HsCodeDTO]:
        """Return HS code rows matching ``query`` (substring on ko/en name).

        Empty ``query`` returns the full table (capped at 200 rows for
        safety).
        """
        ...


# ---- mock ----------------------------------------------------------


class MockHsCodeClient(BaseApiClient):
    """Reads the bundled sample JSON. Used in unit tests + when
    ``USE_MOCK_CLIENTS=true`` on a fresh DB without the imported file.
    """

    cache_ttl: int = CACHE_TTL_SECONDS

    def __init__(self, sample_file: str = "hs_code_sample_1.json"):
        self._sample = load_sample_json(sample_file)

    async def fetch(self, query: str) -> list[HsCodeDTO]:
        items = (self._sample.get("body") or {}).get("items", [])
        rows = [
            HsCodeDTO(
                code=str(it.get("hsSgn") or it.get("code", "")),
                name_ko=str(it.get("korHsnm") or it.get("name_ko", "")),
                name_en=it.get("engHsnm") or it.get("name_en") or None,
            )
            for it in items
        ]
        if not query:
            return rows
        q = query.strip().lower()
        matched = [
            r
            for r in rows
            if q in r.name_ko.lower() or (r.name_en and q in r.name_en.lower())
        ]
        return matched or rows


# ---- DB-backed real client ----------------------------------------


class DbHsCodeClient(BaseApiClient):
    """Reads ``hs_codes`` table populated by ``scripts/import_hs_codes.py``.

    No external HTTP call — the file is downloaded out-of-band from
    data.go.kr (``관세청_HS부호``, ``fileData`` entry) and bulk-loaded.
    """

    cache_ttl: int = CACHE_TTL_SECONDS
    MAX_ROWS: int = 200

    def __init__(self, session_factory):  # type: ignore[no-untyped-def]
        # ``session_factory`` is expected to be ``app.db.session.SessionLocal``
        # or a callable returning a Session. Keep it lazy so the import
        # at module level doesn't require a live DB.
        self._session_factory = session_factory

    async def fetch(self, query: str) -> list[HsCodeDTO]:
        session: Session = self._session_factory()
        try:
            stmt = select(HsCode).limit(self.MAX_ROWS)
            if query:
                pattern = f"%{query.strip()}%"
                stmt = select(HsCode).where(
                    or_(HsCode.name_ko.ilike(pattern), HsCode.name_en.ilike(pattern))
                ).limit(self.MAX_ROWS)
            rows = session.execute(stmt).scalars().all()
            return [
                HsCodeDTO(code=r.code, name_ko=r.name_ko, name_en=r.name_en)
                for r in rows
            ]
        finally:
            session.close()


# ---- factory -------------------------------------------------------


def get_hs_code_client() -> HsCodeClientProtocol:
    if use_mock_clients():
        return MockHsCodeClient()
    # Lazy import to avoid pulling SessionLocal during cold paths
    # (e.g. CLI tools that don't talk to the DB).
    from app.db.session import SessionLocal

    return DbHsCodeClient(session_factory=SessionLocal)
