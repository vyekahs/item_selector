"""Auto-discover sourceable keywords from 관세청 imports + Naver signals.

Pipeline
--------
1. ``import_stats``의 최근 3개월 vs 직전 3개월 비교로 **수입 급증** HS 코드 Top N
2. 평균 수입단가 필터 (박리·고가 제외) + 인증 필수 카테고리 HS 제외
3. 각 HS의 ``name_ko``로 Naver 쇼핑 상위 상품 제목 수집
4. 제목에서 2-/3-gram 한글 조각 빈도 분석 → 제품 정의 토큰 추출
5. 후보 토큰별 Naver searchad로 월 검색량 + 경쟁도 조회
6. ``combined_score`` = log(수입액) × 0.4 + log(검색량) × 0.3 + 수입성장률 × 0.3
7. ``seed_candidates`` 테이블 upsert (term 기준)

Throttling
----------
* Naver searchad: 1초 간격 (30 req/min 공식 한도의 절반)
* Naver shopping: 배치당 0.3초

Re-runs are idempotent — ``term`` UNIQUE 제약으로 기존 행이 업데이트됨.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import re
from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients import (
    get_naver_searchad_client,
    get_naver_shopping_client,
)
from app.clients.base import ApiError
from app.models import HsCode, ImportStat, SeedCandidate

logger = logging.getLogger(__name__)


# --- tuning knobs ----------------------------------------------------

TOP_HS_LIMIT: int = 500
MIN_IMPORT_GROWTH_PCT: float = 50.0           # 최근 3개월 +50%↑ 급증만
MIN_UNIT_PRICE_KRW: int = 5_000               # 박리 상품 제외
MAX_UNIT_PRICE_KRW: int = 100_000             # 초보 자본 부담 제외
TOKENS_PER_HS: int = 5                        # HS당 추출 후보 토큰 수
NGRAM_SIZES: tuple[int, ...] = (2, 3)
MIN_TOKEN_FREQ: int = 3                       # 전체 제목에서 최소 n회 나와야
TOP_CANDIDATES_BY_HS: int = 3                 # HS 내 상위 몇 개까지 searchad로 검증
MIN_MONTHLY_VOLUME: int = 500                 # 월 검색량 최소치
SEARCHAD_DELAY_SEC: float = 1.0

USD_KRW: Decimal = Decimal("1380")            # 대략값; 환율 보정은 추후

# HS 앞자리 기반 인증/규제 제외 리스트 (초보 셀러 부담 카테고리).
# 01-24: 동식물/식품/음료 · 30: 의약품 · 33: 화장품 · 85: 전기기기 ·
# 87-89: 차/비행기/선박 · 9018-9022: 의료기기 · 93: 무기
_EXCLUDE_HS_PREFIXES: tuple[str, ...] = (
    *(f"{i:02d}" for i in range(1, 25)),
    "30", "33", "85", "87", "88", "89", "93",
    "9018", "9019", "9020", "9021", "9022",
)

_KOREAN_RUN_RE = re.compile(r"[가-힣]+")
# 너무 일반적인 토큰은 사전 제외 — 포함돼봐야 시드로 무의미.
_STOP_TOKENS: set[str] = {
    "상품", "제품", "용품", "신상", "인기", "추천", "무료", "배송", "정품",
    "판매", "특가", "할인", "세일", "증정", "사은품", "본사", "직영",
    "당일발송", "무배", "빠른배송", "국내산", "수입",
}


def _extract_ngrams(text: str) -> list[str]:
    out: list[str] = []
    for chunk in _KOREAN_RUN_RE.findall(text):
        for n in NGRAM_SIZES:
            for i in range(len(chunk) - n + 1):
                tok = chunk[i : i + n]
                if tok not in _STOP_TOKENS:
                    out.append(tok)
    return out


def _excluded_hs(code: str) -> bool:
    return any(code.startswith(pfx) for pfx in _EXCLUDE_HS_PREFIXES)


def _fetch_top_hs(
    session: Session, today: dt.date | None = None
) -> list[dict[str, Any]]:
    """Top HS codes by 3-month import value + 3-month growth rate.

    Returns rows with keys: hs_code, recent_value, prior_value,
    recent_qty, growth_pct, unit_price_krw.
    """
    today = today or dt.date.today()
    # Compare the 3 most-recent complete months vs the 3 preceding.
    # Import data lags ~1 month so "today - 1 month" is the freshest YYYY-MM.
    latest = today.replace(day=1) - dt.timedelta(days=1)  # last day of prev month
    recent_start = (latest.replace(day=1) - dt.timedelta(days=62)).strftime("%Y-%m")
    recent_end = latest.strftime("%Y-%m")
    prior_start = (latest.replace(day=1) - dt.timedelta(days=150)).strftime("%Y-%m")
    prior_end = (latest.replace(day=1) - dt.timedelta(days=63)).strftime("%Y-%m")

    recent = dict(
        session.execute(
            select(
                ImportStat.hs_code,
                func.sum(ImportStat.import_value_usd).label("val"),
            )
            .where(ImportStat.year_month >= recent_start)
            .where(ImportStat.year_month <= recent_end)
            .group_by(ImportStat.hs_code)
        ).all()
    )
    prior = dict(
        session.execute(
            select(
                ImportStat.hs_code,
                func.sum(ImportStat.import_value_usd).label("val"),
            )
            .where(ImportStat.year_month >= prior_start)
            .where(ImportStat.year_month <= prior_end)
            .group_by(ImportStat.hs_code)
        ).all()
    )
    qty_recent = dict(
        session.execute(
            select(
                ImportStat.hs_code,
                func.sum(ImportStat.import_quantity).label("qty"),
            )
            .where(ImportStat.year_month >= recent_start)
            .where(ImportStat.year_month <= recent_end)
            .group_by(ImportStat.hs_code)
        ).all()
    )

    rows: list[dict[str, Any]] = []
    for hs, recent_val in recent.items():
        if recent_val is None or float(recent_val) <= 0:
            continue
        if _excluded_hs(hs):
            continue
        prior_val = float(prior.get(hs) or 0)
        recent_val_f = float(recent_val)
        if prior_val == 0:
            growth = 100.0 if recent_val_f > 0 else 0.0
        else:
            growth = (recent_val_f - prior_val) / prior_val * 100.0
        if growth < MIN_IMPORT_GROWTH_PCT:
            continue
        qty = float(qty_recent.get(hs) or 0)
        if qty <= 0:
            continue
        unit_price_krw = int((recent_val_f * float(USD_KRW)) / qty)
        if not (MIN_UNIT_PRICE_KRW <= unit_price_krw <= MAX_UNIT_PRICE_KRW):
            continue
        rows.append(
            {
                "hs_code": hs,
                "recent_value_usd": recent_val_f,
                "recent_value_krw": int(recent_val_f * float(USD_KRW)),
                "growth_pct": growth,
                "unit_price_krw": unit_price_krw,
            }
        )

    rows.sort(key=lambda r: r["recent_value_usd"], reverse=True)
    return rows[:TOP_HS_LIMIT]


async def _mine_tokens_for_hs(
    hs_code: str, name_ko: str
) -> list[tuple[str, int]]:
    """Search Naver shopping with HS name_ko; return top-N (token, freq)."""
    client = get_naver_shopping_client()
    try:
        result = await client.fetch(name_ko, display=40)
    except Exception:
        logger.exception("shopping fetch failed for hs=%s", hs_code)
        return []
    counter: Counter[str] = Counter()
    for item in result.items:
        for tok in _extract_ngrams(item.title or ""):
            counter[tok] += 1
    return [(t, c) for t, c in counter.most_common(TOKENS_PER_HS) if c >= MIN_TOKEN_FREQ]


async def _fetch_search_volume(term: str) -> tuple[int, float | None] | None:
    """Return (monthly_volume, growth_3m_pct) via Naver searchad."""
    client = get_naver_searchad_client()
    try:
        rows = await client.fetch([term])
    except ApiError as exc:
        logger.warning("searchad failed for %r: %s", term, exc)
        return None
    # searchad returns keywordList; match by exact term.
    exact = next((r for r in rows if r.term == term), None)
    if exact is None:
        return None
    return (exact.total_monthly_volume, None)  # growth not directly available


def _combined_score(
    import_krw_3m: int,
    volume: int,
    import_growth_pct: float,
) -> float:
    vol_score = math.log10(max(volume, 1)) * 10  # 0-60
    imp_score = math.log10(max(import_krw_3m, 1)) * 5  # 0-50
    growth_score = min(import_growth_pct, 300.0) / 5  # 0-60
    return round(vol_score + imp_score + growth_score, 2)


async def run(session: Session) -> dict[str, Any]:
    logger.info("discover_seeds: fetching top HS")
    hs_rows = _fetch_top_hs(session)
    logger.info(
        "discover_seeds: %d HS codes survived import filters", len(hs_rows)
    )
    if not hs_rows:
        return {"hs_count": 0, "candidates": 0}

    # Attach name_ko per HS.
    codes = [r["hs_code"] for r in hs_rows]
    names = dict(
        session.execute(
            select(HsCode.code, HsCode.name_ko).where(HsCode.code.in_(codes))
        ).all()
    )

    seen_terms: set[str] = set()
    scored: list[dict[str, Any]] = []

    for row in hs_rows:
        name_ko = (names.get(row["hs_code"]) or "").strip()
        if not name_ko:
            continue
        tokens = await _mine_tokens_for_hs(row["hs_code"], name_ko)
        if not tokens:
            continue
        # Take top ``TOP_CANDIDATES_BY_HS`` tokens from this HS.
        for term, _freq in tokens[:TOP_CANDIDATES_BY_HS]:
            if term in seen_terms:
                continue
            seen_terms.add(term)
            vol_result = await _fetch_search_volume(term)
            await asyncio.sleep(SEARCHAD_DELAY_SEC)
            if vol_result is None:
                continue
            volume, search_growth = vol_result
            if volume < MIN_MONTHLY_VOLUME:
                continue
            score = _combined_score(
                row["recent_value_krw"], volume, row["growth_pct"]
            )
            scored.append(
                {
                    "term": term,
                    "hs_code": row["hs_code"],
                    "import_value_krw_3m": row["recent_value_krw"],
                    "import_growth_3m_pct": round(row["growth_pct"], 2),
                    "avg_unit_price_krw": row["unit_price_krw"],
                    "monthly_search_volume": volume,
                    "search_growth_3m_pct": search_growth,
                    "combined_score": score,
                    "last_refreshed_at": dt.datetime.utcnow(),
                }
            )

    if not scored:
        logger.info("discover_seeds: no candidates passed volume filter")
        return {"hs_count": len(hs_rows), "candidates": 0}

    # Upsert by term.
    stmt = insert(SeedCandidate).values(scored)
    stmt = stmt.on_conflict_do_update(
        index_elements=["term"],
        set_={
            "hs_code": stmt.excluded.hs_code,
            "import_value_krw_3m": stmt.excluded.import_value_krw_3m,
            "import_growth_3m_pct": stmt.excluded.import_growth_3m_pct,
            "avg_unit_price_krw": stmt.excluded.avg_unit_price_krw,
            "monthly_search_volume": stmt.excluded.monthly_search_volume,
            "search_growth_3m_pct": stmt.excluded.search_growth_3m_pct,
            "combined_score": stmt.excluded.combined_score,
            "last_refreshed_at": stmt.excluded.last_refreshed_at,
        },
    )
    session.execute(stmt)
    session.commit()

    logger.info("discover_seeds: upserted %d candidates", len(scored))
    return {"hs_count": len(hs_rows), "candidates": len(scored)}
