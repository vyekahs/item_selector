"""Tests for :class:`CollectKeywordsJob`.

Drives the job with an injected mock searchad client so the assertions
focus on persistence behaviour rather than the network layer.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.contracts.dto import KeywordVolumeDTO
from app.models import Keyword, KeywordStatus
from app.scheduler.jobs import CollectKeywordsJob


class _StubSearchAdClient:
    """Mimic Naver keywordstool: flat ``keywordList`` where each row IS a
    related keyword (not nested inside the seed row)."""

    cache_ttl = 86_400

    def __init__(self, related_per_term: dict[str, list[str]]):
        self._related = related_per_term
        self.calls: list[list[str]] = []

    async def fetch(self, keywords: list[str]) -> list[KeywordVolumeDTO]:
        self.calls.append(list(keywords))
        out: list[KeywordVolumeDTO] = []
        # Production code calls one seed per request; flatten the related
        # list into KeywordVolumeDTO rows just like the real API does.
        for kw in keywords:
            for related in self._related.get(kw, []):
                out.append(
                    KeywordVolumeDTO(
                        term=related,
                        pc_monthly_volume=100,
                        mobile_monthly_volume=200,
                        total_monthly_volume=300,
                        competition_index=0.4,
                        related_keywords=[],
                    )
                )
        return out


def _seed(session, term: str, *, is_seed: bool = True) -> Keyword:
    kw = Keyword(term=term, is_seed=is_seed, status=KeywordStatus.ACTIVE)
    session.add(kw)
    session.flush()
    return kw


def test_collect_keywords_inserts_new_related_terms(db_session):
    _seed(db_session, "고양이 자동급수기")
    _seed(db_session, "강아지 사료")

    client = _StubSearchAdClient(
        {
            "고양이 자동급수기": ["자동 급수기", "고양이 분수기"],
            "강아지 사료": ["애견 사료", "프리미엄 사료"],
        }
    )
    job = CollectKeywordsJob(searchad_client=client)
    metrics = asyncio.run(job.run(db_session))

    assert metrics["seed_count"] == 2
    assert metrics["new_keywords"] == 4

    terms = set(db_session.execute(select(Keyword.term)).scalars().all())
    assert "자동 급수기" in terms
    assert "고양이 분수기" in terms
    assert "애견 사료" in terms
    assert "프리미엄 사료" in terms


def test_collect_keywords_dedupes_against_existing(db_session):
    # The seed term itself should never re-insert.
    _seed(db_session, "고양이 자동급수기")
    # A pre-existing related term should also be ignored.
    db_session.add(
        Keyword(
            term="자동 급수기",
            is_seed=False,
            status=KeywordStatus.PENDING,
        )
    )
    db_session.flush()

    client = _StubSearchAdClient(
        {"고양이 자동급수기": ["자동 급수기", "새 키워드"]}
    )
    job = CollectKeywordsJob(searchad_client=client)
    metrics = asyncio.run(job.run(db_session))

    assert metrics["new_keywords"] == 1
    terms = set(db_session.execute(select(Keyword.term)).scalars().all())
    assert "새 키워드" in terms


def test_collect_keywords_no_seeds_is_noop(db_session):
    client = _StubSearchAdClient({})
    job = CollectKeywordsJob(searchad_client=client)
    metrics = asyncio.run(job.run(db_session))

    assert metrics == {"seed_count": 0, "new_keywords": 0}
    assert client.calls == []


def test_collect_keywords_calls_once_per_seed(db_session):
    # Naver API cost is equal for batch sizes 1–5, and per-seed ranking
    # requires 1 call per seed. 7 seeds → 7 calls.
    for i in range(7):
        _seed(db_session, f"seed{i}")

    client = _StubSearchAdClient(
        {f"seed{i}": [f"related{i}"] for i in range(7)}
    )
    job = CollectKeywordsJob(searchad_client=client)
    metrics = asyncio.run(job.run(db_session))

    assert metrics["api_calls"] == 7
    assert metrics["new_keywords"] == 7


def test_collect_keywords_inserted_rows_are_pending_non_seed(db_session):
    _seed(db_session, "seed1")
    client = _StubSearchAdClient({"seed1": ["new1"]})
    job = CollectKeywordsJob(searchad_client=client)
    asyncio.run(job.run(db_session))

    new = db_session.execute(
        select(Keyword).where(Keyword.term == "new1")
    ).scalar_one()
    assert new.is_seed is False
    assert new.status == KeywordStatus.PENDING
    assert new.last_collected_at is None
