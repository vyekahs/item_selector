"""Tests for ``GET /opportunities``."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Category, Keyword, KeywordMetric, OpportunityScore


def _seed_keyword(
    session: Session,
    *,
    term: str,
    total_score: float,
    category_id: int | None = None,
    snapshot_date: dt.date | None = None,
    is_excluded: bool = False,
    competition_score: float = 15.0,
) -> Keyword:
    kw = Keyword(term=term, category_id=category_id)
    session.add(kw)
    session.flush()
    session.add(
        OpportunityScore(
            keyword_id=kw.id,
            snapshot_date=snapshot_date or dt.date.today(),
            total_score=total_score,
            demand_score=20,
            growth_score=15,
            competition_score=competition_score,
            customs_score=15,
            trend_score=8,
            stability_score=4,
            is_excluded=is_excluded,
            exclusion_reasons="seasonal" if is_excluded else None,
        )
    )
    session.add(
        KeywordMetric(
            keyword_id=kw.id,
            snapshot_date=snapshot_date or dt.date.today(),
            monthly_search_volume=28_000,
            growth_rate_3m=0.19,
        )
    )
    session.flush()
    return kw


def test_list_opportunities_empty(client: TestClient) -> None:
    """Empty DB → empty list (not 404)."""
    response = client.get("/opportunities")
    assert response.status_code == 200
    assert response.json() == []


def test_list_opportunities_ranks_by_total_score(
    client: TestClient, api_db_session: Session
) -> None:
    _seed_keyword(api_db_session, term="고양이 자동급수기", total_score=87)
    _seed_keyword(api_db_session, term="강아지 장난감", total_score=73)
    _seed_keyword(api_db_session, term="고양이 사료", total_score=91)
    api_db_session.commit()

    response = client.get("/opportunities")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3

    # Sorted by total_score desc.
    terms = [row["term"] for row in body]
    assert terms == ["고양이 사료", "고양이 자동급수기", "강아지 장난감"]
    # Ranks are 1-based and continuous.
    assert [row["rank"] for row in body] == [1, 2, 3]
    # 1688 deep link present.
    assert all(row["search_1688_url"].startswith("https://s.1688.com/") for row in body)
    # Metrics bundle is populated.
    assert body[0]["metrics"]["monthly_search_volume"] == 28_000
    assert body[0]["metrics"]["search_growth_3m"] == pytest.approx(0.19, rel=1e-3)


def test_list_opportunities_filters_by_category(
    client: TestClient, api_db_session: Session
) -> None:
    pet_cat = Category(name="반려동물용품")
    home_cat = Category(name="생활용품")
    api_db_session.add_all([pet_cat, home_cat])
    api_db_session.flush()

    _seed_keyword(api_db_session, term="펫 A", total_score=80, category_id=pet_cat.id)
    _seed_keyword(api_db_session, term="생활 A", total_score=90, category_id=home_cat.id)
    api_db_session.commit()

    response = client.get("/opportunities", params={"category_id": pet_cat.id})
    assert response.status_code == 200
    body = response.json()
    assert [row["term"] for row in body] == ["펫 A"]
    assert body[0]["category_id"] == pet_cat.id
    assert body[0]["category_name"] == "반려동물용품"


def test_list_opportunities_respects_limit_and_min_score(
    client: TestClient, api_db_session: Session
) -> None:
    for idx, score in enumerate([95, 82, 73, 55, 40]):
        _seed_keyword(api_db_session, term=f"kw-{idx}", total_score=score)
    api_db_session.commit()

    response = client.get("/opportunities", params={"limit": 2, "min_score": 70})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(row["total_score"] >= 70 for row in body)


def test_list_opportunities_hides_excluded_by_default(
    client: TestClient, api_db_session: Session
) -> None:
    _seed_keyword(api_db_session, term="통과", total_score=85)
    _seed_keyword(
        api_db_session, term="규제걸림", total_score=99, is_excluded=True
    )
    api_db_session.commit()

    default = client.get("/opportunities").json()
    assert [row["term"] for row in default] == ["통과"]

    with_excluded = client.get(
        "/opportunities", params={"include_excluded": "true"}
    ).json()
    terms = {row["term"] for row in with_excluded}
    assert terms == {"통과", "규제걸림"}


def test_list_opportunities_validates_params(client: TestClient) -> None:
    # limit out of range
    assert client.get("/opportunities", params={"limit": 0}).status_code == 422
    assert client.get("/opportunities", params={"limit": 101}).status_code == 422
    # min_score out of range
    assert client.get("/opportunities", params={"min_score": -1}).status_code == 422
    assert client.get("/opportunities", params={"min_score": 101}).status_code == 422
