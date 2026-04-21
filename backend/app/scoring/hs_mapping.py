"""HS-code suggestion stub (기획서 §11 결정 5: 반자동 매핑).

Phase-1 plan: pure static dictionary keyed by category + a tiny set of
keyword keywords. Phase-2 plan (left as TODO): expand with embedding-
based similarity over the full HS code DB so that a freshly typed
keyword can fall back to the nearest semantic neighbours.

This module is intentionally side-effect-free: no DB lookup, no API
call. The Backend / Scheduler agent will turn the suggested codes into
``keyword_hs_mappings`` rows (with ``confidence`` set per the rule that
fired here).
"""
from __future__ import annotations

__all__ = ["suggest_hs_codes", "STATIC_CATEGORY_HS_MAP"]


# Static seeds covering 첫 카테고리 (반려동물용품) + 인접 카테고리.
# Each list is ordered most-likely → least-likely so callers can keep
# the head and discard the tail when truncating.
STATIC_CATEGORY_HS_MAP: dict[str, list[str]] = {
    "반려동물용품": [
        "2309.10",  # 개·고양이 사료 (소매용)
        "2309.90",  # 기타 사료 조제품
        "4201.00",  # 수의용품 (목줄·하네스)
        "9503.00",  # 완구류 (장난감)
        "3923.10",  # 플라스틱 보관용기 (사료통)
        "3924.90",  # 식탁/주방용 플라스틱제품 (급수기·식기)
        "8509.80",  # 가정용 전기기기 (자동급수기/급식기)
        "5605.00",  # 합성섬유 (배변패드 원단)
        "9404.90",  # 침구류 (애견 쿠션·매트)
        "9603.29",  # 솔·브러시 (그루밍)
    ],
    "사료": ["2309.10", "2309.90", "1005.90", "1213.00"],
    "간식": ["2309.10", "2309.90", "1905.90"],
    "장난감": ["9503.00", "4016.99", "6307.90"],
    "위생용품": ["5605.00", "4818.90", "3402.90"],
    "케이지": ["7323.99", "3923.10", "9403.20"],
    "주방용품": [
        "7323.93",
        "7323.99",
        "3924.10",
        "8205.51",
        "6911.10",
        "7615.10",
        "8210.00",
    ],
    "생활용품": [
        "3924.90",
        "9603.40",
        "6307.90",
        "3923.30",
        "3926.40",
    ],
    "디지털": [
        "8517.62",
        "8528.59",
        "8504.40",
        "8518.30",
        "8542.31",
    ],
    "패션잡화": [
        "4202.22",
        "6505.00",
        "7117.19",
        "9004.10",
    ],
    "스포츠": [
        "9506.91",
        "9506.62",
        "9506.99",
        "6404.11",
    ],
    "가전 소형": [
        "8509.40",
        "8516.71",
        "8516.79",
        "8509.80",
    ],
}

# Keyword-level overrides that win when the category lookup is too broad.
# Map a keyword *substring* (case-insensitive) to a prioritized HS list.
# Conservative on purpose -- false positives here ripple into customs
# import statistics, which then drive the customs subscore.
KEYWORD_HINTS: dict[str, list[str]] = {
    # 반려동물
    "급수기": ["8509.80", "3924.90"],
    "급식기": ["8509.80", "3924.90"],
    "정수기": ["8421.21", "8509.80"],     # 정수 필터
    "사료": ["2309.10", "2309.90"],
    "간식": ["2309.10", "2309.90"],
    "장난감": ["9503.00"],
    "쿠션": ["9404.90"],
    "매트": ["9404.90", "5705.00"],
    "쿨매트": ["9404.90", "3924.90"],
    "배변": ["5605.00", "4818.90"],
    "화장실": ["3924.90", "3923.10"],      # 플라스틱 용기
    "하네스": ["4201.00", "4202.92"],     # 가죽 수의용품
    "목줄": ["4201.00", "5609.00"],
    "유모차": ["8715.00"],                # 유모차류
    "타워": ["9403.60", "9404.90"],       # 캣타워 (가구/섬유)
    "캣휠": ["9503.00", "9506.91"],       # 운동용 장난감
    "드라이룸": ["8509.80", "8516.32"],   # 가전
    "급식": ["8509.80", "3924.90"],
    "카메라": ["8525.80", "8525.89"],
    "스마트": ["8543.70", "9503.00"],     # 스마트 장난감 류
    # 공용
    "선풍기": ["8414.51"],
    "텀블러": ["7323.93", "3924.10"],
}


def suggest_hs_codes(category_name: str, keyword: str) -> list[str]:
    """Return prioritized HS-code candidates for a (category, keyword) pair.

    Strategy:

    1. Start with the static category list (preserving order).
    2. Promote any keyword-hint codes to the front (deduplicated).
    3. Truncate to the first 10 candidates -- callers usually only
       want enough to sample the customs API for the strongest signal.

    Returns an empty list when nothing matches; the caller should
    treat that as "no customs evidence available" and let the
    opportunity scorer apply the neutral midpoint.

    Note
    ----
    This is a deliberately narrow Phase-1 implementation. The richer
    embedding-based path below is left as a TODO so we can iterate on
    the live HS-code DB (table ``hs_codes``) without breaking the
    scoring contract.
    """
    # TODO: embedding-based expansion -- hook a sentence-transformers
    # model over hs_codes.name_ko + name_en and return the top-K
    # nearest-neighbour codes when the static map produces nothing.
    base = list(STATIC_CATEGORY_HS_MAP.get(category_name, []))

    # Keyword-driven promotion (case-insensitive substring match).
    promoted: list[str] = []
    if keyword:
        kw_lower = keyword.lower()
        for hint, codes in KEYWORD_HINTS.items():
            if hint.lower() in kw_lower:
                for code in codes:
                    if code not in promoted:
                        promoted.append(code)

    # Merge: promoted first, then the rest of the category list, dedup.
    out: list[str] = []
    for code in promoted + base:
        if code not in out:
            out.append(code)
    return out[:10]
