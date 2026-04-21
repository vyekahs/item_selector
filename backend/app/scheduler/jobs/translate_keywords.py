"""Fill ``keywords.chinese_term`` via Google Cloud Translation.

Runs hourly; skips keywords that already have a translation.
Idempotent and cheap (Google Translate v2 free tier covers 500K
chars/month, and our whole vocabulary is a few hundred chars).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import (
    GoogleTranslateClientProtocol,
    get_google_translate_client,
)
from app.clients.google_translate import QuotaExceededError
from app.models import Keyword
from app.scheduler.base import ScheduledJob

__all__ = ["TranslateKeywordsJob"]


class TranslateKeywordsJob(ScheduledJob):
    """Populate ``chinese_term`` for keywords that don't have one yet."""

    name: str = "translate_keywords"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        translate_client: GoogleTranslateClientProtocol | None = None,
        batch_limit: int = 200,
    ):
        super().__init__()
        self._client = translate_client
        self._batch_limit = batch_limit

    def _translator(self) -> GoogleTranslateClientProtocol:
        return self._client or get_google_translate_client()

    async def run(self, session: Session) -> dict[str, Any]:
        translator = self._translator()

        stmt = (
            select(Keyword)
            .where(Keyword.chinese_term.is_(None))
            .order_by(Keyword.id.asc())
            .limit(self._batch_limit)
        )
        pending: list[Keyword] = list(session.execute(stmt).scalars())
        if not pending:
            return {"pending": 0, "translated": 0, "failures": []}

        translated = 0
        failures: list[str] = []
        quota_hit = False
        for kw in pending:
            try:
                zh = await translator.translate(kw.term)
            except QuotaExceededError as exc:
                # Budget reached — stop the loop so we don't spam retries
                # against an already-blown quota. The un-translated
                # keywords keep ``chinese_term=None`` and will be picked
                # up on the next scheduler run.
                quota_hit = True
                failures.append(f"quota_exceeded_after={translated}: {exc}")
                break
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{kw.term}: {type(exc).__name__}")
                continue
            kw.chinese_term = zh.strip() or None
            translated += 1

        session.commit()
        return {
            "pending": len(pending),
            "translated": translated,
            "quota_exceeded": quota_hit,
            "failures": failures,
        }
