"""Seed + related keyword expansion.

Strategy
--------
1. Load every ``is_seed=True`` keyword from ``keywords`` grouped by
   ``category_id``. Markers are derived per-category so a kitchen seed
   doesn't get filtered out by pet-domain markers (or vice versa).
2. For each seed, call :meth:`NaverSearchAdClient.fetch` once. Naver
   keywordstool returns a flat ``keywordList`` of ~600 candidates per
   seed; each row's ``relKeyword`` is a related term with volume data.
3. Keep only the top-``PER_SEED_TOP_N`` rows above
   ``MIN_MONTHLY_VOLUME``, then filter against the seed's category
   markers — unfiltered, the tail is mostly zero-demand noise or
   brand-name co-occurrences.
4. Upsert previously-unseen terms with ``is_seed=False``,
   ``status=PENDING``, and the parent seed's ``category_id`` so
   :mod:`collect_metrics` picks them up next run and opportunities
   stay grouped by category.

We never delete keywords here; downgrading to ``DEPRECATED`` is a
manual operator action.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import (
    NaverSearchAdClientProtocol,
    get_naver_searchad_client,
)
from app.models import Keyword, KeywordStatus
from app.scheduler.base import ScheduledJob

__all__ = ["CollectKeywordsJob"]


# Per-seed cap: only keep the top-N related keywords by monthly volume.
# Naver returns ~600 candidates per seed; unfiltered that explodes the
# downstream metric-collection workload with mostly-garbage terms.
PER_SEED_TOP_N: int = 20

# Drop related keywords with effectively no demand — not worth sourcing.
MIN_MONTHLY_VOLUME: int = 100

# Naver searchad rate-limits burst requests; 1s between seeds keeps us well
# under their documented 30 req/min quota.
INTER_SEED_DELAY_SEC: float = 1.0

# Domain marker auto-extraction: keep Korean 2-gram/3-gram fragments that
# recur across at least ``MIN_SEED_OCCURRENCE`` distinct seeds. A candidate
# must contain at least one marker to be considered on-topic. Filters out
# Naver's co-occurrence noise (e.g. brand names, tangential categories).
MIN_SEED_OCCURRENCE: int = 2
MARKER_NGRAM_SIZES: tuple[int, ...] = (2, 3)

_KOREAN_RUN_RE = re.compile(r"[가-힣]+")


def _extract_korean_ngrams(text: str, n: int) -> set[str]:
    out: set[str] = set()
    for chunk in _KOREAN_RUN_RE.findall(text):
        for i in range(len(chunk) - n + 1):
            out.add(chunk[i : i + n])
    return out


def _derive_markers(seeds: list[str]) -> set[str]:
    counter: Counter[str] = Counter()
    for seed in seeds:
        ngrams: set[str] = set()
        for n in MARKER_NGRAM_SIZES:
            ngrams |= _extract_korean_ngrams(seed, n)
        for ng in ngrams:
            counter[ng] += 1
    return {ng for ng, c in counter.items() if c >= MIN_SEED_OCCURRENCE}


class CollectKeywordsJob(ScheduledJob):
    """Expand seed keywords with their 연관 키워드."""

    name: str = "collect_keywords"
    max_attempts: int = 3

    def __init__(
        self,
        *,
        searchad_client: NaverSearchAdClientProtocol | None = None,
    ):
        super().__init__()
        self._searchad = searchad_client

    def _client(self) -> NaverSearchAdClientProtocol:
        return self._searchad or get_naver_searchad_client()

    async def run(self, session: Session) -> dict[str, Any]:
        client = self._client()

        seeds: list[tuple[str, int | None]] = list(
            session.execute(
                select(Keyword.term, Keyword.category_id).where(
                    Keyword.is_seed.is_(True)
                )
            ).all()
        )
        if not seeds:
            return {"seed_count": 0, "new_keywords": 0}

        # Index existing terms once so we can dedup cheaply.
        existing: set[str] = set(
            session.execute(select(Keyword.term)).scalars().all()
        )
        seed_set: set[str] = {term.strip() for term, _ in seeds}

        # Group seed terms by category so marker extraction stays in-domain.
        # A single-seed category has no overlap → skip the marker filter for it
        # (no reliable way to auto-pick markers from 1 sample).
        seeds_by_cat: dict[int | None, list[str]] = {}
        for term, cat_id in seeds:
            seeds_by_cat.setdefault(cat_id, []).append(term)
        markers_by_cat: dict[int | None, set[str]] = {
            cat_id: _derive_markers(terms) for cat_id, terms in seeds_by_cat.items()
        }

        new_terms: dict[str, int | None] = {}
        filtered_off_topic = 0
        calls_made = 0
        # Call one seed at a time so we can track "top-N per seed" and apply
        # the seed's own category markers. API cost is equal regardless.
        for idx, (seed_term, seed_cat_id) in enumerate(seeds):
            if idx > 0:
                await asyncio.sleep(INTER_SEED_DELAY_SEC)
            rows = await client.fetch([seed_term])
            calls_made += 1
            markers = markers_by_cat.get(seed_cat_id, set())
            # Sort by volume desc, keep top-N above the volume floor.
            ranked = sorted(
                (r for r in rows if r.total_monthly_volume >= MIN_MONTHLY_VOLUME),
                key=lambda r: r.total_monthly_volume,
                reverse=True,
            )[:PER_SEED_TOP_N]
            for row in ranked:
                term = (row.term or "").strip()
                if (
                    not term
                    or term in seed_set
                    or term in existing
                    or term in new_terms
                ):
                    continue
                if markers and not any(m in term for m in markers):
                    filtered_off_topic += 1
                    continue
                new_terms[term] = seed_cat_id

        for term in sorted(new_terms):
            session.add(
                Keyword(
                    term=term,
                    is_seed=False,
                    status=KeywordStatus.PENDING,
                    category_id=new_terms[term],
                    last_collected_at=None,
                )
            )
        if new_terms:
            session.commit()

        return {
            "seed_count": len(seeds),
            "api_calls": calls_made,
            "new_keywords": len(new_terms),
            "markers_by_category": {
                str(k): sorted(v) for k, v in markers_by_cat.items()
            },
            "filtered_off_topic": filtered_off_topic,
        }
