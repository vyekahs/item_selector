"""HS-code suggestion stub tests."""
from __future__ import annotations

from app.scoring.hs_mapping import STATIC_CATEGORY_HS_MAP, suggest_hs_codes


def test_known_category_returns_static_list():
    codes = suggest_hs_codes("반려동물용품", "사료")
    assert codes  # non-empty
    # Sanity: every returned code is an HS-style string.
    for c in codes:
        assert "." in c
        head, tail = c.split(".", 1)
        assert head.isdigit() and tail.isdigit()


def test_unknown_category_returns_empty_when_no_keyword_match():
    codes = suggest_hs_codes("UNKNOWN_CATEGORY", "_no_match_")
    assert codes == []


def test_keyword_hint_promotes_relevant_code():
    """급수기 hint should appear at the front even within 반려동물용품."""
    codes = suggest_hs_codes("반려동물용품", "고양이 자동급수기")
    assert codes[0] == "8509.80"


def test_truncated_to_ten():
    """Should never return more than ten candidates -- callers depend on this."""
    # 반려동물용품 list has 10 entries; any keyword hint must dedup, not extend past 10.
    codes = suggest_hs_codes("반려동물용품", "장난감 쿠션 매트 사료")
    assert len(codes) <= 10


def test_keyword_hint_works_for_unknown_category():
    """Even when the category isn't seeded, keyword hints still fire."""
    codes = suggest_hs_codes("UNKNOWN", "선풍기")
    assert codes == ["8414.51"]


def test_static_map_has_first_category():
    """Smoke check: 반려동물용품 (Phase-1 first category) must be seeded."""
    assert "반려동물용품" in STATIC_CATEGORY_HS_MAP
    assert len(STATIC_CATEGORY_HS_MAP["반려동물용품"]) >= 5


def test_dedup_preserves_priority():
    """Promoted hints must not appear twice if also present in the category list."""
    # 8509.80 is in 반려동물용품 list AND in the 급수기 hint.
    codes = suggest_hs_codes("반려동물용품", "급수기")
    assert codes.count("8509.80") == 1
